"""Descarga masiva del recorte de IMERG para diciembre–abril (temporadas 2014-15 a 2025-26).

Salida: un archivo por mes en lluvia/datos/<producto>/imerg_<producto>_AAAA-MM.nc (tasa en mm/h, UTC, 30 min).
Solo se guarda el recorte (12 celdas); nunca se baja un gránulo completo (bloques de 64 KB + URL directa).

Robustez (pensada para dejarla corriendo toda la noche):
  - Caché por día: cada día terminado se guarda en lluvia/datos/<producto>/_cache/. Si el programa se corta (internet,
    NASA, apagón, Ctrl+C), al repetir el comando solo se rehacen los días que faltan.
  - Reintentos por gránulo (6, con pausas crecientes). Si se cae internet, espera a que vuelva (hasta 30 min por incidente)
    y reinicia la sesión con NASA. Un día con un gránulo imposible de leer NO se guarda (quedaría incompleto).
  - Rondas: al terminar, los días que fallaron se reintentan solos hasta N rondas, con pausa entre ellas.
  - Si un proceso se cae, el programa sigue con otro grupo de procesos en la ronda siguiente.
  - Un mes solo se escribe cuando todos sus días están completos y verificados. Escrituras atómicas (sin archivos a medias).
  - En Windows pide que el equipo no se suspenda mientras corre (no impide apagar ni cerrar la tapa si así lo configuraste).
  - Bitácora: lluvia/datos/<producto>/descarga.log

Uso (desde la raíz del proyecto):
  python lluvia/descargar_masivo.py --plan                    # qué falta (no descarga nada)
  python lluvia/descargar_masivo.py --medir                   # mide tu velocidad y estima horas y GB
  python lluvia/descargar_masivo.py --solo 2015-03            # un solo mes
  python lluvia/descargar_masivo.py --procesos 24 --url-directa   # todo (dic 2014 – abr 2026)
  python lluvia/descargar_masivo.py --verificar               # revisa los meses ya guardados
Requisitos: earthaccess, xarray, h5netcdf (psutil es opcional, solo para --medir).
"""
import argparse
import os
import re
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from descargar_imerg import PRODUCTOS, _login, buscar
from imerg_utils import bbox_quebradas, leer_granulo

CARPETA = Path(__file__).resolve().parent / "datos"
GRANULOS_DIA = 48
BLOQUE_KB = 64  # medido con gránulos reales: 64 KB -> 5 % del archivo; por defecto (5 MB) -> 102 %
REINTENTOS = 6
ESPERA_INTERNET_SEG = 1800
MAX_SIN_PROGRESO_SEG = 1200  # si un proceso pasa 20 min sin terminar un solo gránulo, se considera colgado y se mata
MAX_FALLOS_DIA = 3           # un día que falla 3 veces se aparta hasta que repitas el comando
HOSTS_INTERNET = ("https://urs.earthdata.nasa.gov", "https://data.gesdisc.earthdata.nasa.gov")
_ARCHIVO_LOG = None


def log(msg):
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(linea, flush=True)
    if _ARCHIVO_LOG is not None:
        with open(_ARCHIVO_LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")


# --------------------------------------------------------------------------- plan y rutas
def plan_meses(primera, ultima):
    """[(año, mes)] de las temporadas dic–abr: la temporada `y` va de dic y a abr y+1."""
    out = []
    for y in range(primera, ultima + 1):
        out += [(y, 12)] + [(y + 1, m) for m in (1, 2, 3, 4)]
    return out


def dias_mes(a, m):
    return pd.Period(f"{a}-{m:02d}").days_in_month


def ruta_mes(producto, a, m):
    return CARPETA / producto / f"imerg_{producto}_{a}-{m:02d}.nc"


def ruta_dia(producto, dia):  # dia = 'AAAAMMDD'
    return CARPETA / producto / "_cache" / f"{dia[:4]}-{dia[4:6]}" / f"imerg_{producto}_{dia}.nc"


def agrupar_por_dia(urls):
    """{'AAAAMMDD': [urls]} según la fecha UTC que lleva el nombre del gránulo."""
    out = {}
    for u in urls:
        m = re.search(r"3IMERG\.(\d{8})-S", u)
        if m:
            out.setdefault(m.group(1), []).append(u)
    return {d: sorted(v) for d, v in sorted(out.items())}


# --------------------------------------------------------------------------- red
def hay_internet(timeout=10):
    import requests

    for host in HOSTS_INTERNET:
        try:
            requests.head(host, timeout=timeout)  # cualquier respuesta HTTP cuenta: hay conexión
            return True
        except Exception:
            continue
    return False


def esperar_internet(max_seg=ESPERA_INTERNET_SEG):
    """Si no hay conexión, espera (pausas crecientes de 5 a 60 s) hasta que vuelva. Devuelve segundos esperados, -1 si se rindió."""
    if hay_internet():
        return 0
    t0, pausa = time.time(), 5
    while True:
        time.sleep(pausa)
        pausa = min(pausa * 2, 60)
        if hay_internet():
            return time.time() - t0
        if time.time() - t0 > max_seg:
            return -1


def hacer_abridor(fs, fs_plano, sesion, kw, url_directa, respaldo):
    """Arma abrir(url). Modos:
      - normal: fs.open(url) con la sesión autenticada; CADA petición pasa por el servidor de autenticación de NASA
        (que redirige al almacenamiento), con un costo fijo de ~1 s por petición.
      - url_directa: se resuelve UNA vez la URL de almacenamiento de cada gránulo y las lecturas van directo a ella.
    Si algo falla en un modo, se cae al siguiente (url_directa -> normal -> respaldo)."""
    def resolver(url):
        import requests

        r = sesion.get(url, headers={"Range": "bytes=0-0"}, allow_redirects=False, timeout=60)
        destino = r.headers.get("Location", "")
        if r.status_code not in (301, 302, 303, 307, 308) or not destino or "urs.earthdata" in destino:
            return None
        r2 = requests.get(destino, headers={"Range": "bytes=0-0"}, timeout=60)  # sin credenciales: la URL ya va firmada
        return destino, int(r2.headers["Content-Range"].rsplit("/", 1)[1])

    def abrir(url):
        if url_directa and sesion is not None:
            try:
                res = resolver(url)
                if res:
                    return fs_plano.open(res[0], mode="rb", size=res[1], **kw)
            except Exception:
                pass
        if fs is not None:
            try:
                return fs.open(url, mode="rb", **kw)
            except Exception:  # p. ej. 401 con el token
                pass
        return respaldo(url)

    return abrir


def crear_abridor(bloque_kb=BLOQUE_KB, url_directa=False):
    """Devuelve abrir(url) -> archivo remoto que se lee por bloques pequeños (solo trae lo necesario)."""
    import earthaccess
    import fsspec

    _login(earthaccess)
    kw = dict(block_size=bloque_kb * 1024, cache_type="blockcache")
    try:
        fs = earthaccess.get_fsspec_https_session()
    except Exception as e:
        fs = None
        print("Aviso: sin sesión fsspec propia (", repr(e)[:80], ") -> earthaccess.open")
    try:
        sesion = earthaccess.get_requests_https_session() if url_directa else None
    except Exception:
        sesion = None
    try:  # el sistema de archivos "plano" no lleva credenciales; se le pone un tiempo máximo por petición
        import aiohttp
        fs_plano = fsspec.filesystem("https", client_kwargs={"timeout": aiohttp.ClientTimeout(total=120)})
    except Exception:
        fs_plano = fsspec.filesystem("https")
    return hacer_abridor(fs, fs_plano, sesion, kw, url_directa,
                         lambda url: earthaccess.open([url], open_kwargs=kw)[0])


class Resiliente:
    """Abridor que se crea al primer uso y se puede reiniciar (nuevo login y nuevas conexiones) tras una caída."""

    def __init__(self, bloque_kb, url_directa):
        self.bloque_kb, self.url_directa, self._abrir = bloque_kb, url_directa, None

    def __call__(self, url):
        if self._abrir is None:
            self._abrir = crear_abridor(self.bloque_kb, self.url_directa)
        return self._abrir(url)

    def reiniciar(self):
        self._abrir = None


_ABRIDORES = {}  # uno por proceso trabajador: el login se hace una sola vez por proceso


def _abridor(bloque_kb, url_directa):
    k = (bloque_kb, url_directa)
    if k not in _ABRIDORES:
        _ABRIDORES[k] = Resiliente(bloque_kb, url_directa)
    return _ABRIDORES[k]


# --------------------------------------------------------------------------- lectura
def leer_urls(urls, bbox, abrir, reintentos=REINTENTOS, pausa_base=2, latido=None):
    """Lee el recorte de cada URL con reintentos. Se detiene en el primer gránulo imposible de leer
    (el día quedaría incompleto). Devuelve (partes, fallas, n_reintentos)."""
    partes, fallas, n_reint = [], [], 0
    for u in urls:
        nombre = u.rsplit("/", 1)[-1]
        if latido:
            latido()
        for intento in range(reintentos):
            f = None
            try:
                f = abrir(u)
                partes.append(leer_granulo(f, bbox, nombre=nombre))
                if latido:
                    latido()
                break
            except Exception as e:
                n_reint += 1
                if intento == reintentos - 1:
                    fallas.append((nombre, repr(e)[:150]))
                else:
                    if intento >= 1 and hasattr(abrir, "reiniciar"):
                        abrir.reiniciar()  # sesión nueva por si la anterior quedó rota
                    esperar_internet()
                    time.sleep(min(60, pausa_base * 2 ** intento))
            finally:
                if f is not None:
                    try:
                        f.close()
                    except Exception:
                        pass
        if fallas:
            break
    return partes, fallas, n_reint


def _reemplazar(tmp, ruta, intentos=8):
    """os.replace con reintentos: en Windows el antivirus u OneDrive pueden bloquear el archivo un instante."""
    for i in range(intentos):
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if i == intentos - 1:
                raise
            time.sleep(1 + i)


def guardar_nc(partes, ruta, producto):
    import xarray as xr

    da = xr.concat(partes, dim="time").sortby("time")
    da = da.isel(time=~da.indexes["time"].duplicated())
    da.attrs.update(units="mm/h", producto=PRODUCTOS[producto], tiempo="UTC, inicio del gránulo de 30 min")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    da.to_dataset(name="mm_h").to_netcdf(tmp)
    _reemplazar(tmp, ruta)  # el archivo final solo aparece cuando está completo
    return da


class Vigilante:
    """Mata el proceso si pasa `max_seg` sin dar señales de vida (un gránulo leído). Evita que una lectura de red
    colgada para siempre deje el programa esperando. Antes de morir deja una marca en disco con el día culpable,
    para que solo ese día cuente como fallo (los días sanos que se pierdan con el proceso se reintentan sin castigo)."""

    def __init__(self, max_seg, marca):
        self.max_seg, self.marca, self._t = max_seg, marca, None

    def _matar(self):
        try:
            self.marca.parent.mkdir(parents=True, exist_ok=True)
            self.marca.write_text("colgado")
        finally:
            os._exit(3)

    def latido(self):
        self.parar()
        self._t = threading.Timer(self.max_seg, self._matar)
        self._t.daemon = True
        self._t.start()

    def parar(self):
        if self._t is not None:
            self._t.cancel()
            self._t = None


def marca_colgado(producto, dia):
    return ruta_dia(producto, dia).with_suffix(".colgado")


def procesar_dia(producto, dia, urls, bbox, bloque_kb, url_directa, max_sin_progreso=0):
    """Lee los gránulos de un día y guarda su caché. NO lanza excepciones: devuelve siempre un diccionario."""
    t0 = time.time()
    try:
        ruta = ruta_dia(producto, dia)
        if ruta.exists():
            return dict(dia=dia, ok=True, n=len(urls), reint=0, seg=0.0)
        vig = Vigilante(max_sin_progreso, marca_colgado(producto, dia)) if max_sin_progreso else None
        try:
            partes, fallas, reint = leer_urls(urls, bbox, _abridor(bloque_kb, url_directa), latido=vig.latido if vig else None)
        finally:
            if vig:
                vig.parar()
        if fallas:
            return dict(dia=dia, ok=False, error=f"{fallas[0][0]}: {fallas[0][1]}", reint=reint, seg=time.time() - t0)
        if len(partes) != len(urls):
            return dict(dia=dia, ok=False, error=f"leídos {len(partes)} de {len(urls)}", reint=reint, seg=time.time() - t0)
        guardar_nc(partes, ruta, producto)
        return dict(dia=dia, ok=True, n=len(partes), reint=reint, seg=time.time() - t0)
    except Exception as e:  # nada debe tumbar al proceso trabajador
        return dict(dia=dia, ok=False, error=repr(e)[:150], reint=0, seg=time.time() - t0)


def urls_mes(producto, a, m, bbox, reintentos=REINTENTOS):
    """URLs de los gránulos del mes (consulta a NASA con reintentos)."""
    d = dias_mes(a, m)
    for intento in range(reintentos):
        try:
            res = buscar(producto, f"{a}-{m:02d}-01", f"{a}-{m:02d}-{d}", bbox)
            urls = {l for r in res for l in r.data_links()[:1] if l.startswith("https")}
            return sorted(urls), d
        except Exception as e:
            if intento == reintentos - 1:
                raise
            log(f"  búsqueda de {a}-{m:02d} falló ({repr(e)[:80]}); reintento {intento + 1}")
            esperar_internet()
            time.sleep(min(60, 2 * 2 ** intento))


def ensamblar_mes(producto, a, m, dias, encontrados, esperado, reint, seg):
    """Junta las cachés de los días en el archivo del mes, verificando que no falte ningún gránulo encontrado."""
    import xarray as xr

    partes = []
    for d in dias:
        with xr.open_dataset(ruta_dia(producto, d)) as ds:
            partes.append(ds["mm_h"].load())
    da = xr.concat(partes, dim="time").sortby("time")
    if da.sizes["time"] != encontrados or not da.indexes["time"].is_unique:
        raise RuntimeError(f"{a}-{m:02d}: {da.sizes['time']} pasos, se esperaban {encontrados}")
    ruta = ruta_mes(producto, a, m)
    guardar_nc([da], ruta, producto)
    nan = float(np.isnan(da.values).mean())
    fila = pd.DataFrame([dict(mes=f"{a}-{m:02d}", esperado=esperado, encontrados=encontrados, leidos=da.sizes["time"],
                              pct_nan=round(100 * nan, 2), segundos=round(seg), reintentos=reint)])
    res = ruta.parent / "resumen.csv"
    if res.exists():
        fila = pd.concat([pd.read_csv(res), fila]).drop_duplicates("mes", keep="last")
    fila.to_csv(res, index=False)
    aviso = "" if encontrados == esperado else f" | OJO: NASA tiene {encontrados} de {esperado} gránulos esperados"
    log(f"  MES LISTO {a}-{m:02d}: {da.sizes['time']} pasos, {nan * 100:.1f} % NaN, {reint} reintentos{aviso}")


# --------------------------------------------------------------------------- ejecución
def evitar_suspension(activar=True):
    if os.name != "nt":
        return
    try:
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activar else 0))
    except Exception:
        pass


def _matar_pool(pool):
    """Termina los procesos trabajadores (también los colgados) para que el programa pueda cerrar."""
    try:
        for proc in list(getattr(pool, "_processes", {}).values()):
            if proc.is_alive():
                proc.terminate()
    except Exception:
        pass


def _correr(tareas, procesos):
    """Ejecuta las tareas (clave, args de procesar_dia) y entrega (clave, resultado) a medida que terminan."""
    if procesos <= 1:
        for clave, args in tareas:
            yield clave, procesar_dia(*args)
        return
    pool = ProcessPoolExecutor(procesos)
    try:
        futuros = {pool.submit(procesar_dia, *args, MAX_SIN_PROGRESO_SEG): (clave, args[1]) for clave, args in tareas}
        for fut in as_completed(futuros):
            clave, dia = futuros[fut]
            try:
                yield clave, fut.result()
            except Exception as e:  # p. ej. un proceso trabajador murió: el día se reintenta en la ronda siguiente
                yield clave, dict(dia=dia, ok=False, error=f"proceso caído: {repr(e)[:100]}", reint=0, seg=0.0)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        _matar_pool(pool)


def ejecutar(producto, plan, bbox, bloque_kb, url_directa, procesos, rondas, espera_ronda):
    inicio = time.time()
    pendientes = [ym for ym in plan if not ruta_mes(producto, *ym).exists()]
    info = {}  # (a, m) -> dict(por_dia, esperado, encontrados, reint, seg)
    fallos_dia, solo_caidas = {}, False
    for ronda in range(1, rondas + 1):
        if not pendientes:
            break
        log(f"=== Ronda {ronda}/{rondas}: {len(pendientes)} meses pendientes ===")
        for ym in pendientes:
            if ym not in info:
                try:
                    urls, d = urls_mes(producto, *ym, bbox)
                except Exception as e:
                    log(f"  no pude consultar {ym[0]}-{ym[1]:02d}: {repr(e)[:100]}; queda para la ronda siguiente")
                    continue
                if not urls:
                    log(f"  {ym[0]}-{ym[1]:02d}: NASA no devolvió gránulos; se omite")
                    continue
                info[ym] = dict(por_dia=agrupar_por_dia(urls), esperado=d * GRANULOS_DIA, encontrados=len(urls), reint=0, seg=0.0)
        tareas, faltan = [], {}
        for ym in pendientes:
            if ym not in info:
                continue
            faltan[ym] = set()
            for dia, us in info[ym]["por_dia"].items():
                if fallos_dia.get(dia, 0) >= MAX_FALLOS_DIA:
                    faltan[ym].add(dia)  # apartado: el mes queda pendiente y se avisa al final
                elif not ruta_dia(producto, dia).exists():
                    tareas.append((ym, (producto, dia, us, bbox, bloque_kb, url_directa)))
                    faltan[ym].add(dia)
        total, hechos, fallos, caidas = len(tareas), 0, 0, 0
        apartados = sorted(d for d, n in fallos_dia.items() if n >= MAX_FALLOS_DIA and not ruta_dia(producto, d).exists())
        if apartados:
            log(f"  días apartados tras {MAX_FALLOS_DIA} fallos (repite el comando luego para reintentarlos): {', '.join(apartados)}")
        log(f"  {total} días por descargar con {procesos} procesos")

        def cerrar_meses_completos():
            for ym in list(faltan):
                if not faltan[ym] and not ruta_mes(producto, *ym).exists():
                    i = info[ym]
                    try:
                        ensamblar_mes(producto, *ym, sorted(i["por_dia"]), i["encontrados"], i["esperado"], i["reint"], i["seg"])
                    except Exception as e:
                        log(f"  ERROR al ensamblar {ym[0]}-{ym[1]:02d}: {repr(e)[:150]}")

        cerrar_meses_completos()  # meses cuyos días ya estaban en caché
        t_ronda = time.time()
        try:
            for ym, r in _correr(tareas, procesos):
                hechos += 1
                info[ym]["reint"] += r["reint"]
                info[ym]["seg"] += r["seg"]
                if r["ok"]:
                    faltan[ym].discard(r["dia"])
                else:
                    fallos += 1
                    caidas += str(r.get("error", "")).startswith("proceso caído")
                    if not str(r.get("error", "")).startswith("proceso caído"):
                        fallos_dia[r["dia"]] = fallos_dia.get(r["dia"], 0) + 1
                    log(f"  FALLÓ día {r['dia']}: {r.get('error', '?')}")
                if hechos % 10 == 0 or hechos == total:
                    v = hechos / (time.time() - t_ronda)
                    log(f"  días {hechos}/{total} ({fallos} fallos) | ~{(total - hechos) / v / 60:.0f} min restantes")
                cerrar_meses_completos()
        except KeyboardInterrupt:
            log("Interrumpido por el usuario. Lo ya descargado queda en caché: repite el comando para continuar.")
            raise SystemExit(1)
        for _, args in tareas:  # días que el vigilante marcó como colgados: esos sí cuentan como fallo
            marca = marca_colgado(producto, args[1])
            if marca.exists():
                fallos_dia[args[1]] = fallos_dia.get(args[1], 0) + 1
                log(f"  día {args[1]} se colgó (sin respuesta de la red por {MAX_SIN_PROGRESO_SEG // 60} min); fallo {fallos_dia[args[1]]}/{MAX_FALLOS_DIA}")
                marca.unlink(missing_ok=True)
        pendientes = [ym for ym in plan if not ruta_mes(producto, *ym).exists()]
        solo_caidas = fallos > 0 and caidas == fallos
        espera = min(espera_ronda, 30) if solo_caidas else espera_ronda  # un proceso caído no requiere esperar a NASA
        quedan = [d for ym in pendientes if ym in info for d in info[ym]["por_dia"] if not ruta_dia(producto, d).exists() and fallos_dia.get(d, 0) < MAX_FALLOS_DIA]
        if pendientes and not quedan and ronda < rondas:
            log("  solo quedan días apartados; no tiene sentido seguir esperando")
            break
        if pendientes and ronda < rondas:
            log(f"  faltan {len(pendientes)} meses; espero {max(espera, 1) // 60 if espera >= 60 else espera} {'min' if espera >= 60 else 's'} y reintento solo lo que falta")
            time.sleep(espera)
    horas = (time.time() - inicio) / 3600
    if pendientes:
        log(f"TERMINADO CON PENDIENTES en {horas:.1f} h: faltan {', '.join(f'{a}-{m:02d}' for a, m in pendientes)}. "
            "Repite el comando para completarlos.")
    else:
        log(f"TERMINADO en {horas:.1f} h: {len(plan)} meses completos. Revisa con --verificar.")


def verificar(producto, plan):
    import xarray as xr

    print(f"{'mes':>8s} {'pasos':>6s} {'esperado':>9s} {'saltos':>7s} {'%NaN':>6s}  estado")
    malos = 0
    for a, m in plan:
        r = ruta_mes(producto, a, m)
        esperado = dias_mes(a, m) * GRANULOS_DIA
        if not r.exists():
            print(f"{a}-{m:02d} {'':>6s} {esperado:9d} {'':>7s} {'':>6s}  FALTA")
            malos += 1
            continue
        with xr.open_dataset(r) as ds:
            t, v = ds["time"].values, ds["mm_h"].values
        saltos = int((np.diff(t).astype("timedelta64[m]").astype(int) != 30).sum())
        estado = "ok" if len(t) == esperado and saltos == 0 else "REVISAR"
        malos += estado != "ok"
        print(f"{a}-{m:02d} {len(t):6d} {esperado:9d} {saltos:7d} {100 * np.isnan(v).mean():6.1f}  {estado}")
    print(f"\n{len(plan) - malos}/{len(plan)} meses ok. 'REVISAR' = faltan gránulos o hay saltos distintos de 30 min (puede ser un hueco real de NASA).")


# --------------------------------------------------------------------------- medición
def _bytes_recibidos():
    try:
        import psutil
        return psutil.net_io_counters().bytes_recv
    except Exception:
        return None


def medir(producto, bbox, total_granulos, procesos, n=4):
    """Mide velocidad y tráfico reales con gránulos de un día de temporada y proyecta el total."""
    import earthaccess

    _login(earthaccess)
    urls, _ = urls_mes(producto, 2020, 2, bbox)
    configs = [(16, False), (64, False), (256, False), (64, True), (256, True)]
    paso = max(1, len(urls) // (n * len(configs)))
    muestra = urls[::paso]
    print(f"Muestra de {min(len(muestra), n * len(configs))} gránulos de feb-2020 (cierra descargas y videos mientras mide).")

    mbps = None
    try:  # velocidad cruda: 4 MB de un gránulo
        fs = earthaccess.get_fsspec_https_session()
        t0 = time.time()
        datos = fs.cat_file(muestra[0], start=0, end=4_000_000)
        mbps = len(datos) * 8 / 1e6 / (time.time() - t0)
        print(f"Velocidad cruda a NASA (una conexión): {mbps:.1f} Mbps")
    except Exception as e:
        print("No pude medir la velocidad cruda:", repr(e)[:100])

    filas = []
    for i, (kb, directa) in enumerate(configs):
        sub = muestra[i * n:(i + 1) * n]
        if not sub:
            break
        abrir = crear_abridor(kb, directa)
        b0, t0, cache = _bytes_recibidos(), time.time(), 0
        for u in sub:
            f = abrir(u)
            leer_granulo(f, bbox, nombre=u.rsplit("/", 1)[-1])
            cache += getattr(getattr(f, "cache", None), "total_requested_bytes", 0) or 0
            f.close()
        seg, b1 = (time.time() - t0) / len(sub), _bytes_recibidos()
        mb_cache = cache / 1e6 / len(sub)
        mb_pc = (b1 - b0) / 1e6 / len(sub) if None not in (b0, b1) else None
        filas.append((kb, directa, seg, mb_cache, mb_pc))

    print(f"\nTotal a descargar: {total_granulos:,} gránulos")
    print(f"{'config':>14s} {'seg/gránulo':>12s} {'MB leídos':>10s} {'MB red PC':>10s} {'GB total':>9s} {'h (1 proc.)':>12s} {f'h ({procesos} proc.)':>12s}")
    mejor, aviso = None, False
    for kb, directa, seg, mb, mb_pc in filas:
        gb = total_granulos * mb / 1024  # se proyecta con MB leídos (no se contamina con otro tráfico del PC)
        h1 = total_granulos * seg / 3600
        hp = h1 / procesos  # la velocidad de una conexión no limita al conjunto: se mide con el piloto
        flag = " *" if mb_pc is not None and mb_pc > 3 * mb + 1 else ""
        aviso = aviso or bool(flag)
        etiqueta = f"{kb}KB{' directa' if directa else ''}"
        print(f"{etiqueta:>14s} {seg:12.2f} {mb:10.2f} {'' if mb_pc is None else f'{mb_pc:.1f}':>10s}{flag:1s} {gb:9.1f} {h1:12.1f} {hp:12.1f}")
        if mejor is None or hp < mejor[2]:
            mejor = (kb, directa, hp)
    if mejor:
        print(f"\nMejor: bloque {mejor[0]} KB{' + --url-directa' if mejor[1] else ''}. Estimación: ~{mejor[2]:.1f} h con {procesos} procesos "
              f"(solo si NASA no te limita con tantos procesos en paralelo).")
    if aviso:
        print("* 'MB red PC' incluye todo el tráfico de tu PC y salió mucho mayor que lo leído: otra aplicación estaba usando internet.")


# --------------------------------------------------------------------------- principal
def main():
    global _ARCHIVO_LOG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=PRODUCTOS, default="early")
    ap.add_argument("--primera", type=int, default=2014, help="la temporada 2014 es dic-2014 a abr-2015")
    ap.add_argument("--ultima", type=int, default=2025, help="la temporada 2025 es dic-2025 a abr-2026")
    ap.add_argument("--solo", help="un solo mes, AAAA-MM (piloto)")
    ap.add_argument("--bloque-kb", type=int, default=BLOQUE_KB)
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--url-directa", action="store_true", help="resolver una vez la URL de almacenamiento por gránulo")
    ap.add_argument("--rondas", type=int, default=12, help="rondas de reintento de lo que falle (default 12)")
    ap.add_argument("--espera-ronda", type=int, default=600, help="segundos de pausa entre rondas (default 600: unas 2 h de paciencia en total)")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--verificar", action="store_true")
    a = ap.parse_args()

    plan = plan_meses(a.primera, a.ultima)
    if a.solo:
        y, m = map(int, a.solo.split("-"))
        plan = [(y, m)]
    total = sum(dias_mes(y, m) * GRANULOS_DIA for y, m in plan)
    hechos = sum(ruta_mes(a.producto, y, m).exists() for y, m in plan)
    print(f"{PRODUCTOS[a.producto]} | {len(plan)} meses | {total:,} gránulos esperados | {hechos} meses ya guardados")
    if a.plan:
        for y, m in plan:
            cdir = CARPETA / a.producto / "_cache" / f"{y}-{m:02d}"
            cache = len(list(cdir.glob("*.nc"))) if cdir.exists() else 0
            estado = "LISTO" if ruta_mes(a.producto, y, m).exists() else f"pendiente ({cache} días en caché)"
            print(f"  {y}-{m:02d}  {dias_mes(y, m) * GRANULOS_DIA:>5d} gránulos  {estado}")
        return
    if a.verificar:
        return verificar(a.producto, plan)
    bbox = bbox_quebradas()
    if a.medir:
        return medir(a.producto, bbox, total, a.procesos)

    (CARPETA / a.producto).mkdir(parents=True, exist_ok=True)
    _ARCHIVO_LOG = CARPETA / a.producto / "descarga.log"
    log(f"INICIO: {len(plan)} meses, {a.procesos} procesos, bloque {a.bloque_kb} KB, url_directa={a.url_directa}")
    evitar_suspension(True)
    try:
        ejecutar(a.producto, plan, bbox, a.bloque_kb, a.url_directa, a.procesos, a.rondas, a.espera_ronda)
    finally:
        evitar_suspension(False)


if __name__ == "__main__":
    main()

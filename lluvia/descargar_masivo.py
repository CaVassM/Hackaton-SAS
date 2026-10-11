"""Descarga masiva del recorte de IMERG para diciembre–abril (temporadas 2014-15 a 2025-26).

Un archivo por mes en lluvia/datos/<producto>/imerg_<producto>_AAAA-MM.nc (tasa en mm/h, UTC, 30 min).
Solo se guarda el recorte (12 celdas); nunca se baja un gránulo completo:
  - Con el tamaño de bloque por defecto de fsspec (5 MB) se baja el archivo ENTERO (7.5 MB por gránulo
    = ~650 GB en total). Aquí se lee con bloques de 64 KB: ~0.4 MB por gránulo (~5 %).
  - Un mes solo se guarda si TODOS los gránulos encontrados se leyeron; si algo falla, no se guarda y al repetir
    el comando se rehace ese mes. Los meses ya guardados se saltan (se puede cortar y reanudar).

Uso (desde la raíz del proyecto):
  python lluvia/descargar_masivo.py --plan                    # qué se va a descargar (no descarga nada)
  python lluvia/descargar_masivo.py --medir                   # mide tu velocidad y estima horas y GB
  python lluvia/descargar_masivo.py --solo 2015-03            # piloto con un solo mes
  python lluvia/descargar_masivo.py --procesos 4              # todo (dic 2014 – abr 2026)
Requisitos: earthaccess, xarray, h5netcdf (y psutil, opcional, para medir el tráfico real).
"""
import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from descargar_imerg import PRODUCTOS, _login, buscar
from imerg_utils import bbox_quebradas, leer_granulo

CARPETA = Path(__file__).resolve().parent / "datos"
GRANULOS_DIA = 48
BLOQUE_KB = 64  # medido con gránulos reales: 64 KB -> 5 % del archivo; por defecto (5 MB) -> 102 %


# --------------------------------------------------------------------------- plan
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


# --------------------------------------------------------------------------- lectura
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
    return hacer_abridor(fs, fsspec.filesystem("https"), sesion, kw, url_directa,
                         lambda url: earthaccess.open([url], open_kwargs=kw)[0])


def urls_mes(producto, a, m, bbox):
    d = dias_mes(a, m)
    res = buscar(producto, f"{a}-{m:02d}-01", f"{a}-{m:02d}-{d}", bbox)
    urls = {l for r in res for l in r.data_links()[:1] if l.startswith("https")}
    return sorted(urls), d


def leer_urls(urls, bbox, abrir, reintentos=3, cada=100):
    """Lee el recorte de cada URL. Devuelve (lista de DataArray, lista de (nombre, error))."""
    partes, fallas, t0 = [], [], time.time()
    for i, u in enumerate(urls, 1):
        nombre = u.rsplit("/", 1)[-1]
        for intento in range(reintentos):
            f = None
            try:
                f = abrir(u)
                partes.append(leer_granulo(f, bbox, nombre=nombre))
                break
            except Exception as e:  # un fallo de red no debe tumbar todo el mes
                if intento == reintentos - 1:
                    fallas.append((nombre, repr(e)[:150]))
                else:
                    time.sleep(2 ** intento)
            finally:
                if f is not None:
                    try:
                        f.close()
                    except Exception:
                        pass
        if cada and i % cada == 0:
            v = i / (time.time() - t0)
            print(f"    {i}/{len(urls)} gránulos | {v:.2f}/s | faltan ~{(len(urls) - i) / v / 60:.0f} min", flush=True)
    return partes, fallas


def _leer_lote(urls, bbox, bloque_kb, url_directa=False):  # se ejecuta dentro de cada proceso
    return leer_urls(urls, bbox, crear_abridor(bloque_kb, url_directa), cada=0)


def guardar_mes(partes, ruta, producto):
    import xarray as xr

    da = xr.concat(partes, dim="time").sortby("time")
    da = da.isel(time=~da.indexes["time"].duplicated())
    da.attrs.update(units="mm/h", producto=PRODUCTOS[producto], tiempo="UTC, inicio del gránulo de 30 min")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    da.to_dataset(name="mm_h").to_netcdf(tmp)
    os.replace(tmp, ruta)  # el archivo final solo aparece cuando está completo
    return da


def procesar_mes(producto, a, m, bbox, bloque_kb, abrir, pool=None, procesos=1, url_directa=False):
    ruta = ruta_mes(producto, a, m)
    if ruta.exists():
        return "ya existe, se salta"
    t0 = time.time()
    urls, dias = urls_mes(producto, a, m, bbox)
    esperado = dias * GRANULOS_DIA
    if not urls:
        return "NASA no devolvió gránulos; no se guardó"
    if pool is None:
        partes, fallas = leer_urls(urls, bbox, abrir)
    else:
        partes, fallas = [], []
        lotes = [urls[i::procesos] for i in range(procesos)]  # intercalados: cada proceso recorre todo el mes
        for p, f in pool.map(_leer_lote, lotes, [bbox] * procesos, [bloque_kb] * procesos, [url_directa] * procesos):
            partes += p
            fallas += f
    if fallas:
        for nombre, err in fallas[:3]:
            print(f"    falla: {nombre} -> {err}")
        return f"INCOMPLETO ({len(fallas)} fallas): NO se guardó; repite el comando para rehacerlo"
    da = guardar_mes(partes, ruta, producto)
    seg = time.time() - t0
    nan = float(np.isnan(da.values).mean())
    fila = pd.DataFrame([dict(mes=f"{a}-{m:02d}", esperado=esperado, encontrados=len(urls), leidos=len(partes),
                              pct_nan=round(100 * nan, 2), segundos=round(seg))])
    res = ruta.parent / "resumen.csv"
    fila.to_csv(res, mode="a", header=not res.exists(), index=False)
    aviso = "" if len(urls) == esperado else f" | OJO: NASA tiene {len(urls)} de {esperado} gránulos esperados"
    return f"ok: {len(partes)} gránulos, {nan * 100:.1f} % NaN, {seg / 60:.1f} min{aviso}"


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
        print(f"Velocidad cruda a NASA: {mbps:.1f} Mbps")
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
        hp = max(h1 / procesos, (gb * 1024 * 8 / mbps / 3600) if mbps else 0)  # tope: el ancho de banda
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=PRODUCTOS, default="early")
    ap.add_argument("--primera", type=int, default=2014, help="la temporada 2014 es dic-2014 a abr-2015")
    ap.add_argument("--ultima", type=int, default=2025, help="la temporada 2025 es dic-2025 a abr-2026")
    ap.add_argument("--solo", help="un solo mes, AAAA-MM (piloto)")
    ap.add_argument("--bloque-kb", type=int, default=BLOQUE_KB)
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--url-directa", action="store_true", help="resolver una vez la URL de almacenamiento por gránulo")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--medir", action="store_true")
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
            print(f"  {y}-{m:02d}  {dias_mes(y, m) * GRANULOS_DIA:>5d} gránulos  {'LISTO' if ruta_mes(a.producto, y, m).exists() else 'pendiente'}")
        return
    bbox = bbox_quebradas()
    if a.medir:
        return medir(a.producto, bbox, total, a.procesos)

    pool = ProcessPoolExecutor(a.procesos) if a.procesos > 1 else None
    abrir = None if pool else crear_abridor(a.bloque_kb, a.url_directa)
    t0 = time.time()
    for k, (y, m) in enumerate(plan, 1):
        print(f"[{k}/{len(plan)}] {y}-{m:02d} ...", flush=True)
        print("   ", procesar_mes(a.producto, y, m, bbox, a.bloque_kb, abrir, pool, a.procesos, a.url_directa), flush=True)
    print(f"Terminado en {(time.time() - t0) / 3600:.1f} h. Resumen por mes: {CARPETA / a.producto / 'resumen.csv'}")


if __name__ == "__main__":
    main()

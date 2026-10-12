"""Descarga y recorte de PERSIANN-CCS HORARIO (CHRS, UC Irvine) para la zona de las 17 quebradas. Se corre en una máquina con acceso a persiann.eng.uci.edu.

ESTADO: escrito y probado SOLO contra archivos sintéticos locales (ver salida/prueba_sintetica_decodificador.txt). Nunca se ejecutó contra el servidor real: el entorno
donde se escribió bloquea persiann.eng.uci.edu (error 403 de la política de red). Lo NO confirmado está marcado con [CONFIRMAR] y se resuelve con los modos --readme e --indice.

Lo que SÍ se sabe (readmes diario y 6-horario de CHRS, que comparten grilla con el horario):
  - grilla global 0.04°, 3000 filas x 9000 columnas, 60N-60S, 0-360E; primer valor = píxel noroeste centrado en 0.02E y 59.98N; filas hacia el sur, columnas hacia el este.
  - diario: float32 big-endian en mm/día, NODATA -9999 (archivo rgccs1d + YYDDD, .bin.gz). 6-horario: int16 big-endian en mm/6h x 100, NODATA -9999 (YYDDDHH).
Lo que NO se pudo confirmar (README horario no accesible): tipo de dato y escala del horario, patrón del nombre (se asume rgccs1h + YYDDDHH), si la hora del nombre marca
el INICIO o el FIN de la hora acumulada, y la latencia declarada. Se resuelven leyendo el README (--readme) y pasando --dtype/--escala/--convencion si hace falta.

Los archivos son globales y gzip: NO se puede leer solo un recorte por red; cada archivo se baja entero y se recorta al llegar (guarda solo ~10 x 10 píxeles).
Usa --medir antes de bajar nada para ver cuánto pesan.

Uso (desde la raíz del repositorio):
  python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --readme
  ... --indice                      # primer/último archivo y fecha del último (¿se sigue actualizando?)
  ... --medir 6                     # tamaño de 6 archivos de ejemplo y estimación del total
  ... --prueba                      # 3 ventanas: Quirio 23/03/2015, 2024-25 (2 días), reciente (2 últimos días del índice)
  ... --temporadas 2014 2025        # dic-abr de cada temporada (la 2014 es dic-2014 a abr-2015); reanuda lo ya guardado
  ... --solo 2015-03                # un solo mes
Salida: datos/persiann_ccs/persiann_ccs_AAAA-MM.nc (mm por hora, UTC, etiqueta = convención declarada) y caché diaria en datos/persiann_ccs/_cache/.
"""
import argparse
import gzip
import io
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parents[1]
CARPETA = AQUI / "datos" / "persiann_ccs"
BASE_DEFECTO = "https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/hrly/"
NFIL, NCOL, PASO, LAT0, LON0 = 3000, 9000, 0.04, 59.98, 0.02     # lat del centro de la fila i = LAT0 - PASO*i ; lon (0-360) de la columna j = LON0 + PASO*j
NODATA = -9999
PATRON = re.compile(r"^(?P<pref>[A-Za-z0-9_]*?)(?P<yy>\d{2})(?P<ddd>\d{3})(?P<hh>\d{2})?\.bin(?:\.gz)?$")
MARGEN = 0.05   # grados de margen alrededor del bbox de las cuencas


def bbox():
    import geopandas as gpd
    x0, y0, x1, y1 = gpd.read_file(RAIZ / "terreno" / "quebradas.geojson").total_bounds
    return x0 - MARGEN, y0 - MARGEN, x1 + MARGEN, y1 + MARGEN


def indices_recorte(bb):
    """Filas y columnas de la grilla global cuyos centros caen dentro del bbox (lon negativa -> 0-360)."""
    x0, y0, x1, y1 = bb
    filas = [i for i in range(NFIL) if y0 <= LAT0 - PASO * i <= y1]
    cols = [j for j in range(NCOL) if x0 + 360 <= LON0 + PASO * j <= x1 + 360]
    lat = np.round(LAT0 - PASO * np.array(filas), 4)
    lon = np.round(LON0 + PASO * np.array(cols) - 360, 4)
    return slice(filas[0], filas[-1] + 1), slice(cols[0], cols[-1] + 1), lat, lon


# ------------------------------------------------------------------ red
def get(url, intentos=5, espera=3, **kw):
    for k in range(intentos):
        try:
            r = requests.get(url, timeout=kw.pop("timeout", 90), **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):      # no se reintenta una denegación ni un archivo inexistente
                return r
        except requests.RequestException as e:
            err = e
        time.sleep(espera * (k + 1))
    raise RuntimeError(f"no se pudo obtener {url}: {err if 'err' in dir() else 'reintentos agotados'}")


def listar(base):
    r = get(base)
    if r.status_code != 200:
        raise SystemExit(f"El índice {base} respondió {r.status_code}.")
    nombres = sorted(set(re.findall(r'href="([^"?/][^"]*)"', r.text)))
    return [n for n in nombres if PATRON.match(n)]


def fecha_de(nombre):
    m = PATRON.match(nombre)
    yy = int(m["yy"])
    anio = 2000 + yy
    hh = int(m["hh"]) if m["hh"] else None
    return datetime(anio, 1, 1) + timedelta(days=int(m["ddd"]) - 1, hours=hh or 0), m["pref"], hh is not None


def nombre_de(t, pref, con_hora=True, gz=True):
    ddd = (t.date() - date(t.year, 1, 1)).days + 1
    return f"{pref}{t.year % 100:02d}{ddd:03d}{t.hour:02d}.bin" + (".gz" if gz else "") if con_hora else f"{pref}{t.year % 100:02d}{ddd:03d}.bin.gz"


# ------------------------------------------------------------------ decodificación
def inferir_formato(readme):
    """Intenta leer tipo y escala del README. Devuelve (dtype, escala) o (None, None) si no es concluyente."""
    t = readme.lower()
    escala = 100 if re.search(r"(\*|x|×)\s*100|mm/\w+\s*(\*|x|×)\s*100", t) else 1
    if "short" in t or "int16" in t or "2-byte" in t or "2 byte" in t:
        return ">i2", escala
    if "float" in t or "4-byte" in t or "4 byte" in t:
        return ">f4", 1
    return None, None


def decodificar(datos, dtype, escala):
    """Bytes (ya sin gzip) -> arreglo (3000, 9000) float32 en mm; NODATA -> NaN. Verifica el tamaño contra la grilla documentada."""
    esperado = NFIL * NCOL * np.dtype(dtype).itemsize
    if len(datos) != esperado:
        raise ValueError(f"tamaño {len(datos)} B != {esperado} B esperados para {dtype} en {NFIL}x{NCOL}: el tipo de dato o la grilla no coinciden con lo supuesto")
    a = np.frombuffer(datos, dtype=dtype).reshape(NFIL, NCOL)
    out = np.where(a == NODATA, np.nan, a.astype("float32") / escala).astype("float32")
    return out


def bajar_hora(base, t, pref, con_hora, dtype, escala, sl_f, sl_c):
    r = get(base + nombre_de(t, pref, con_hora))
    if r.status_code != 200:
        return None, r.status_code, 0
    crudo = gzip.decompress(r.content)
    return decodificar(crudo, dtype, escala)[sl_f, sl_c], 200, len(r.content)


def dia_a_npz(base, dia, cfg, hilos):
    """Un día UTC completo (24 horas) -> caché .npz. Devuelve (ok, faltantes)."""
    ruta = CARPETA / "_cache" / f"{dia:%Y-%m}" / f"{dia:%Y%m%d}.npz"
    if ruta.exists():
        return True, []
    horas = [datetime(dia.year, dia.month, dia.day, h) for h in range(24)]
    with ThreadPoolExecutor(hilos) as ex:
        res = list(ex.map(lambda t: bajar_hora(base, t, cfg["pref"], cfg["con_hora"], cfg["dtype"], cfg["escala"], cfg["sl_f"], cfg["sl_c"]), horas))
    ny, nx = cfg["sl_f"].stop - cfg["sl_f"].start, cfg["sl_c"].stop - cfg["sl_c"].start
    arr = np.stack([r[0] if r[0] is not None else np.full((ny, nx), np.nan, "float32") for r in res])
    faltan = [f"{t:%H}" for t, r in zip(horas, res) if r[0] is None]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ruta, mm=arr, horas=np.array([f"{t:%Y-%m-%dT%H}" for t in horas]), faltan=np.array(faltan))
    return not faltan, faltan


def ensamblar_mes(anio, mes, cfg):
    import xarray as xr
    dias = pd.date_range(f"{anio}-{mes:02d}-01", periods=pd.Period(f"{anio}-{mes:02d}").days_in_month).date
    partes = []
    for d in dias:
        ruta = CARPETA / "_cache" / f"{d:%Y-%m}" / f"{d:%Y%m%d}.npz"
        if not ruta.exists():
            continue
        z = np.load(ruta)
        partes.append(xr.DataArray(z["mm"], dims=("time", "lat", "lon"), coords=dict(time=pd.to_datetime(z["horas"], format="%Y-%m-%dT%H"), lat=cfg["lat"], lon=cfg["lon"])))
    if not partes:
        return None
    da = xr.concat(partes, "time").sortby("time")
    da.name = "mm_h"
    da.attrs.update(units="mm por intervalo horario", producto="PERSIANN-CCS hourly (CHRS, UCI)", tiempo_utc=f"marca de tiempo = hora del nombre del archivo (UTC); convención {cfg['convencion']} [CONFIRMAR con README]",
                    formato_origen=f"{cfg['dtype']} escala {cfg['escala']} NODATA {NODATA}", grilla="0.04 grados; centro de fila i = 59.98 - 0.04 i; centro de columna j = 0.02 + 0.04 j (0-360E); lon aquí en -180..180")
    ruta = CARPETA / f"persiann_ccs_{anio}-{mes:02d}.nc"
    da.to_dataset().to_netcdf(ruta)
    return ruta, da.sizes["time"]


# ------------------------------------------------------------------ modos
def configurar(a):
    base = a.url_base.rstrip("/") + "/"
    sl_f, sl_c, lat, lon = indices_recorte(bbox())
    cfg = dict(base=base, sl_f=sl_f, sl_c=sl_c, lat=lat, lon=lon, convencion=a.convencion)
    dtype, escala = a.dtype, a.escala
    nombres = None
    try:
        nombres = listar(base)
    except SystemExit:
        pass
    if nombres:
        t0, pref, con_hora = fecha_de(nombres[0])
        cfg.update(pref=pref, con_hora=con_hora, primero=t0, ultimo=fecha_de(nombres[-1])[0], n_archivos=len(nombres))
    else:
        cfg.update(pref=a.prefijo, con_hora=True)
    if dtype is None:
        r = get(base + "readme.hrly")
        if r.status_code == 200:
            dtype, escala_r = inferir_formato(r.text)
            escala = escala if escala is not None else escala_r
    if dtype is None:
        raise SystemExit("No pude inferir el tipo de dato del README horario. Léelo con --readme y pasa --dtype '>i2' (int16 big-endian) o '>f4' (float32 big-endian) y --escala (p. ej. 100).")
    cfg.update(dtype=dtype, escala=escala if escala is not None else 1)
    print(f"Formato: {cfg['dtype']} escala {cfg['escala']} | prefijo {cfg['pref']} | nombre con hora: {cfg['con_hora']} | recorte {cfg['sl_f']} x {cfg['sl_c']} ({len(cfg['lat'])} x {len(cfg['lon'])} píxeles)")
    return cfg


def modo_readme(a):
    base = a.url_base.rstrip("/") + "/"
    for n in ("readme.hrly", "README", "readme.txt"):
        r = get(base + n, intentos=2)
        if r.status_code == 200:
            print(f"--- {base + n}\n{r.text}")
            return
    print("No encontré el README en", base, "(probé readme.hrly, README, readme.txt). Revísalo en el portal.")


def modo_indice(a):
    nombres = listar(a.url_base.rstrip("/") + "/")
    print(f"{len(nombres)} archivos | primero: {nombres[0]} ({fecha_de(nombres[0])[0]}) | último: {nombres[-1]} ({fecha_de(nombres[-1])[0]})")
    print(f"Hoy (UTC) es {datetime.utcnow():%Y-%m-%d %H:%M}: el último archivo del índice tiene {(datetime.utcnow() - fecha_de(nombres[-1])[0]).total_seconds() / 3600:.0f} h de antigüedad (latencia aparente, a verificar contra el README).")


def modo_medir(a, cfg):
    nombres = listar(cfg["base"])
    idx = np.linspace(0, len(nombres) - 1, a.medir).astype(int)
    tam = []
    for i in idx:
        r = requests.head(cfg["base"] + nombres[i], timeout=60, allow_redirects=True)
        tam.append(int(r.headers.get("Content-Length", 0)))
        print(f"  {nombres[i]}: {tam[-1] / 1e6:.2f} MB")
    mb = np.mean(tam) / 1e6
    horas = 12 * 151 * 24
    print(f"Promedio {mb:.2f} MB/archivo. Dic-abr de 12 temporadas = {horas:,} archivos = {mb * horas / 1e3:.0f} GB a bajar (se descartan al recortar).")


def modo_prueba(a, cfg):
    pasos = [("Quirio 2015-03-23 (08:00-24:00 local = 13:00 UTC del 23 a 05:00 UTC del 24)", [date(2015, 3, 23), date(2015, 3, 24)]),
             ("Temporada 2024-25: 2024-12-02 y 2025-02-12 (días anómalos de IMERG)", [date(2024, 12, 2), date(2025, 2, 12)]),
             ("Reciente: los 2 últimos días completos del índice", [cfg["ultimo"].date() - timedelta(days=2), cfg["ultimo"].date() - timedelta(days=1)] if "ultimo" in cfg else [])]
    for titulo, dias in pasos:
        print("\n" + titulo)
        for d in dias:
            ok, faltan = dia_a_npz(cfg["base"], d, cfg, a.hilos)
            print(f"  {d}: {'ok' if ok else 'INCOMPLETO, faltan horas UTC ' + ','.join(faltan)}")
    for ym in sorted({(d.year, d.month) for _, ds in pasos for d in ds}):
        r = ensamblar_mes(*ym, cfg)
        if r:
            print("  guardado", r[0].name, f"({r[1]} horas)")


def modo_temporadas(a, cfg):
    meses = [(y, 12) for y in range(a.temporadas[0], a.temporadas[1] + 1)] + [(y + 1, m) for y in range(a.temporadas[0], a.temporadas[1] + 1) for m in (1, 2, 3, 4)]
    if a.solo:
        meses = [tuple(map(int, a.solo.split("-")))]
    for anio, mes in sorted(meses):
        dias = pd.date_range(f"{anio}-{mes:02d}-01", periods=pd.Period(f"{anio}-{mes:02d}").days_in_month).date
        malos = []
        for d in dias:
            ok, faltan = dia_a_npz(cfg["base"], d, cfg, a.hilos)
            if not ok:
                malos.append(f"{d}({','.join(faltan)})")
        r = ensamblar_mes(anio, mes, cfg)
        print(f"{anio}-{mes:02d}: {r[1] if r else 0} horas guardadas" + (f" | días incompletos: {malos}" if malos else ""), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url-base", default=BASE_DEFECTO)
    ap.add_argument("--readme", action="store_true")
    ap.add_argument("--indice", action="store_true")
    ap.add_argument("--medir", type=int, default=0)
    ap.add_argument("--prueba", action="store_true")
    ap.add_argument("--temporadas", type=int, nargs=2, metavar=("PRIMERA", "ULTIMA"))
    ap.add_argument("--solo")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--dtype", help="tipo del binario si el README no se puede leer: '>i2' o '>f4'")
    ap.add_argument("--escala", type=float)
    ap.add_argument("--prefijo", default="rgccs1h")
    ap.add_argument("--convencion", choices=["inicio", "fin"], default="inicio", help="la hora del nombre marca el inicio o el fin de la hora acumulada [CONFIRMAR]")
    a = ap.parse_args()
    CARPETA.mkdir(parents=True, exist_ok=True)
    if a.readme:
        return modo_readme(a)
    if a.indice:
        return modo_indice(a)
    cfg = configurar(a)
    if a.medir:
        return modo_medir(a, cfg)
    if a.prueba:
        return modo_prueba(a, cfg)
    if a.temporadas or a.solo:
        a.temporadas = a.temporadas or (2014, 2025)
        return modo_temporadas(a, cfg)
    ap.print_help()


if __name__ == "__main__":
    main()

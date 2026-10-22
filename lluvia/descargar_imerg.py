"""Descarga el recorte de IMERG (área de las 17 quebradas + 0.1°) a un NetCDF local.

Lee cada gránulo de 30 min directamente desde GES DISC (sin bajar el archivo global)
y guarda solo las celdas del área, como tasa en mm/h y en UTC (sin convertir todavía).

Uso (desde la raíz del proyecto):
  python lluvia/descargar_imerg.py --inspect
  python lluvia/descargar_imerg.py --producto early --inicio 2015-03-22 --fin 2015-03-24

Requisitos:  pip install earthaccess xarray h5netcdf
Credenciales: cuenta Earthdata en el archivo .netrc (earthaccess.login(strategy="netrc")).
Fechas en UTC. Las 15:10 hora de Perú son las 20:10 UTC.
"""
import argparse
from pathlib import Path

import pandas as pd

from imerg_utils import bbox_quebradas, leer_granulo

PRODUCTOS = {"early": "GPM_3IMERGHHE", "final": "GPM_3IMERGHH"}  # IMERG V07
CARPETA = Path(__file__).resolve().parent / "datos"


def _login(earthaccess):
    """Primero .netrc (en Windows se llama `_netrc` y va en C:\\Users\\<usuario>); si no, pide usuario y clave una vez."""
    try:
        if earthaccess.login(strategy="netrc").authenticated:
            return
    except Exception:
        pass
    earthaccess.login(strategy="interactive", persist=True)  # guarda las credenciales para la próxima


def buscar(producto, inicio, fin, bbox):
    import earthaccess

    _login(earthaccess)
    t0 = pd.Timestamp(inicio).strftime("%Y-%m-%dT00:00:00")
    t1 = pd.Timestamp(fin).strftime("%Y-%m-%dT23:59:59")
    return earthaccess.search_data(short_name=PRODUCTOS[producto], version="07",
                                   temporal=(t0, t1), bounding_box=bbox)


def inspeccionar(producto, inicio, bbox):
    """Imprime la estructura de un gránulo (variables y dimensiones), sin imprimir arreglos."""
    import earthaccess
    import xarray as xr

    res = buscar(producto, inicio, inicio, bbox)
    print(f"Gránulos encontrados ese día: {len(res)}")
    f = earthaccess.open(res[:1])[0]
    print("Enlace:", res[0].data_links()[0])
    ds = xr.open_dataset(f, group="Grid", engine="h5netcdf", decode_times=False)
    # print(ds) falla si el `dask` del entorno está dañado; se imprime a mano
    print("Dimensiones:", dict(ds.sizes))
    for nombre, v in ds.variables.items():
        print(f"  {nombre}: dims={v.dims} shape={v.shape} units={v.attrs.get('units')}")
    print("lon:", float(ds.lon[0]), "->", float(ds.lon[-1]), "| lat:", float(ds.lat[0]), "->", float(ds.lat[-1]))
    for v in ("precipitation", "precipitationCal"):
        if v in ds:
            print(v, "->", ds[v].dims, ds[v].attrs.get("units"), ds[v].attrs.get("_FillValue"))


def descargar(producto, inicio, fin, bbox):
    import earthaccess

    res = buscar(producto, inicio, fin, bbox)
    print(f"{len(res)} gránulos de {PRODUCTOS[producto]} entre {inicio} y {fin}")
    archivos = earthaccess.open(res)
    partes, fallas = [], 0
    for r, f in zip(res, archivos):
        try:
            partes.append(leer_granulo(f, bbox, nombre=r.data_links()[0]))
        except Exception as e:  # un gránulo malo no debe tumbar toda la descarga
            fallas += 1
            print("  falla:", r.data_links()[0].rsplit("/", 1)[-1], "->", repr(e)[:120])
    if not partes:
        raise SystemExit("No se pudo leer ningún gránulo.")
    import xarray as xr
    da = xr.concat(partes, dim="time").sortby("time")
    da.attrs.update(units="mm/h", producto=PRODUCTOS[producto], tiempo="UTC, inicio del gránulo de 30 min")
    CARPETA.mkdir(exist_ok=True)
    salida = CARPETA / f"imerg_{producto}_{inicio}_{fin}.nc"
    da.to_dataset(name="mm_h").to_netcdf(salida)
    print(f"Guardado: {salida}  ({da.sizes['time']} pasos de 30 min, {da.sizes['lat']}x{da.sizes['lon']} celdas, {fallas} fallas)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=PRODUCTOS, default="early")
    ap.add_argument("--inicio", default="2015-03-22")
    ap.add_argument("--fin", default="2015-03-24")
    ap.add_argument("--inspect", action="store_true", help="solo mostrar la estructura de un gránulo")
    a = ap.parse_args()
    bb = bbox_quebradas()
    print("Recorte (lon_min, lat_min, lon_max, lat_max):", tuple(round(x, 3) for x in bb))
    if a.inspect:
        inspeccionar(a.producto, a.inicio, bb)
    else:
        descargar(a.producto, a.inicio, a.fin, bb)

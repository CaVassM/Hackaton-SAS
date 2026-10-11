"""Utilidades de lluvia compartidas por los scripts de `lluvia/`.

- Pesos: fracción del área de cada quebrada que cae en cada celda de una grilla regular.
- IMERG: lectura de un gránulo de 30 min (HDF5, grupo "Grid") recortado al área.
- Conversión: tasa mm/h por media hora -> mm por hora, en hora de Perú (UTC-5).
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
GEOJSON_QUEBRADAS = RAIZ / "terreno" / "quebradas.geojson"
CRS_METRICO = "EPSG:32718"            # UTM 18S, el mismo del DEM
UTC_A_LOCAL = pd.Timedelta(hours=-5)  # Perú = UTC-5
RES_IMERG = 0.1                       # grados


# --------------------------------------------------------------------------- pesos
def centros_imerg(lon_min, lon_max, lat_min, lat_max):
    """Centros de celda de la grilla IMERG (bordes en múltiplos de 0.1°, centros en x.x5)."""
    lon = np.round(np.arange(np.floor(lon_min * 10) / 10 + 0.05, lon_max + 0.1, RES_IMERG), 2)
    lat = np.round(np.arange(np.floor(lat_min * 10) / 10 + 0.05, lat_max + 0.1, RES_IMERG), 2)
    return lon, lat


def calcular_pesos(gdf, lon_c, lat_c):
    """Peso de cada celda en cada quebrada (los pesos de una quebrada suman 1).

    `gdf`: quebradas en EPSG:4326 con `quebrada_id`. `lon_c`, `lat_c`: centros de celda.
    Las intersecciones se miden en UTM 18S (m²), no en grados.
    """
    import geopandas as gpd
    from shapely.geometry import box

    dlon = abs(float(np.median(np.diff(lon_c)))) if len(lon_c) > 1 else RES_IMERG
    dlat = abs(float(np.median(np.diff(lat_c)))) if len(lat_c) > 1 else RES_IMERG
    celdas = [
        dict(i_lat=i, i_lon=j, lat_centro=float(la), lon_centro=float(lo),
             geometry=box(lo - dlon / 2, la - dlat / 2, lo + dlon / 2, la + dlat / 2))
        for i, la in enumerate(lat_c) for j, lo in enumerate(lon_c)
    ]
    celdas = gpd.GeoDataFrame(celdas, crs="EPSG:4326").to_crs(CRS_METRICO)
    quebs = gdf[["quebrada_id", "geometry"]].to_crs(CRS_METRICO)
    inter = gpd.overlay(quebs, celdas, how="intersection", keep_geom_type=True)
    inter["area_km2_en_celda"] = inter.geometry.area / 1e6
    inter["peso"] = inter["area_km2_en_celda"] / inter.groupby("quebrada_id")["area_km2_en_celda"].transform("sum")
    cols = ["quebrada_id", "i_lat", "i_lon", "lat_centro", "lon_centro", "area_km2_en_celda", "peso"]
    return pd.DataFrame(inter[cols]).sort_values(["quebrada_id", "lat_centro", "lon_centro"]).reset_index(drop=True)


def leer_quebradas():
    import geopandas as gpd
    return gpd.read_file(GEOJSON_QUEBRADAS)


def bbox_quebradas(margen=RES_IMERG):
    """(lon_min, lat_min, lon_max, lat_max) de los 17 polígonos + margen en grados."""
    x0, y0, x1, y1 = leer_quebradas().total_bounds
    return x0 - margen, y0 - margen, x1 + margen, y1 + margen


# --------------------------------------------------------------------------- IMERG
def _tiempo_desde_nombre(nombre):
    """Inicio UTC del gránulo, p. ej. '...3IMERG.20150323-S200000-E202959...' -> 2015-03-23 20:00."""
    m = re.search(r"(\d{8})-S(\d{2})(\d{2})(\d{2})", str(nombre))
    if not m:
        return None
    f, h, mi, s = m.groups()
    return pd.Timestamp(f"{f[:4]}-{f[4:6]}-{f[6:]} {h}:{mi}:{s}")


def leer_granulo(archivo, bbox, nombre=None):
    """Lee un gránulo IMERG (ruta o archivo abierto) y devuelve la lluvia recortada.

    Devuelve DataArray (time, lat, lon) en mm/h (tasa), NaN donde no hay dato.
    El instante es el inicio UTC del gránulo (se saca del nombre; si no, del archivo).
    """
    import xarray as xr  # solo aquí: la tabla de pesos no lo necesita

    nombre = nombre or (archivo if isinstance(archivo, (str, Path)) else getattr(archivo, "path", ""))
    ds = xr.open_dataset(archivo, group="Grid", engine="h5netcdf", decode_times=False)
    var = "precipitation" if "precipitation" in ds else "precipitationCal"  # V07 / V06
    lon0, lat0, lon1, lat1 = bbox
    ilon = np.where((ds.lon.values >= lon0) & (ds.lon.values <= lon1))[0]
    ilat = np.where((ds.lat.values >= lat0) & (ds.lat.values <= lat1))[0]
    da = ds[var].isel(lon=ilon, lat=ilat).transpose("time", "lat", "lon").load()
    da = da.where(da >= 0)  # el relleno (-9999.9) pasa a NaN aunque no se haya enmascarado
    t = _tiempo_desde_nombre(nombre)
    if t is None:
        raise ValueError(f"No pude sacar la hora del nombre: {nombre!r}")
    da = da.isel(time=[0]).assign_coords(time=[t.to_datetime64()])
    da.name = "mm_h"
    ds.close()
    return da


def a_horario_local(da_mmh):
    """Tasa (mm/h) por media hora, en UTC -> mm por hora en hora de Perú (UTC-5).

    mm = valor x 0.5; se suman las dos medias horas de cada hora (NaN si falta una).
    La etiqueta de tiempo es el INICIO de la hora local (la fila 15:00 cubre 15:00-15:59).
    """
    mm = da_mmh * 0.5
    h = mm.resample(time="1h").sum(min_count=2)
    return h.assign_coords(time=h.time.values + np.timedelta64(int(UTC_A_LOCAL / pd.Timedelta("1s")), "s"))


def lluvia_por_quebrada(da, pesos, tol=0.011):
    """Σ peso × lluvia de la celda, por quebrada. `da`: (time, lat, lon). Devuelve DataFrame tiempo × quebrada."""
    out = {}
    lat, lon = da.lat.values, da.lon.values
    for q, g in pesos.groupby("quebrada_id"):
        serie = 0
        for r in g.itertuples():
            i, j = np.abs(lat - r.lat_centro).argmin(), np.abs(lon - r.lon_centro).argmin()
            if abs(lat[i] - r.lat_centro) > tol or abs(lon[j] - r.lon_centro) > tol:
                raise ValueError(f"La celda ({r.lat_centro}, {r.lon_centro}) de {q} no está en los datos.")
            serie = serie + r.peso * da.values[:, i, j]
        out[q] = serie
    return pd.DataFrame(out, index=pd.DatetimeIndex(da.time.values))

"""Prueba del 23/03/2015 (huaico de Quirio ~15:10 hora local).

Compara la lluvia horaria de Quirio según IMERG Early, IMERG Final, PISCOp_h y ERA5.
Sirve solo para VALIDAR que Early se comporta como las otras fuentes; ninguna entra al modelo
salvo Early. Todo en hora de Perú (UTC-5), etiqueta = inicio de la hora.

Uso (desde la raíz del proyecto):
  python lluvia/prueba_23mar2015.py --inspect-piscop RUTA/PISCOp_h_2015.nc
  python lluvia/prueba_23mar2015.py --early lluvia/datos/imerg_early_2015-03-22_2015-03-24.nc \
         --final-dir RUTA/CARPETA_IMERG_FINAL --piscop RUTA/PISCOp_h_2015.nc
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from imerg_utils import (a_horario_local, bbox_quebradas, calcular_pesos, leer_granulo,
                         leer_quebradas, lluvia_por_quebrada)

AQUI = Path(__file__).resolve().parent
QUEBRADA = "quirio"
EVENTO = pd.Timestamp("2015-03-23 15:10")  # hora local
DIA = slice("2015-03-23 00:00", "2015-03-23 23:00")
VENTANA = slice("2015-03-22 12:00", "2015-03-24 00:00")


def serie_early(ruta, pesos):
    da = xr.open_dataset(ruta)["mm_h"]
    return lluvia_por_quebrada(a_horario_local(da), pesos)[QUEBRADA]


def serie_final(carpeta, pesos, bbox):
    """Gránulos IMERG Final (HDF5) del 22 al 24/03/2015 UTC encontrados bajo `carpeta`."""
    archivos = sorted(p for p in Path(carpeta).rglob("*") if p.is_file() and
                      any(f"3IMERG.2015032{d}" in p.name for d in "234"))
    if not archivos:
        raise SystemExit(f"No encontré gránulos 3IMERG.2015032[2-4] en {carpeta}")
    da = xr.concat([leer_granulo(p, bbox) for p in archivos], dim="time").sortby("time")
    print(f"IMERG Final: {len(archivos)} gránulos leídos")
    return lluvia_por_quebrada(a_horario_local(da), pesos)[QUEBRADA]


def _coord(ds, opciones):
    return next(n for n in opciones if n in ds.coords or n in ds.dims)


def leer_piscop(ruta, variable=None):
    """DataArray (time, lat, lon) del NetCDF de PISCOp_h, tal como viene (sin corregir el desfase)."""
    ds = xr.open_dataset(ruta)
    lat, lon = _coord(ds, ["lat", "latitude", "y"]), _coord(ds, ["lon", "longitude", "x"])
    tiempo = _coord(ds, ["time", "date", "t"])
    if variable is None:
        variable = next(v for v in ds.data_vars if {lat, lon, tiempo} <= set(ds[v].dims))
    return ds[variable].rename({lat: "lat", lon: "lon", tiempo: "time"}).transpose("time", "lat", "lon")


def serie_era5(carpeta, anio=2015):
    """ERA5 (CSV de 2 puntos, tp en metros por hora, `valid_time` UTC = FIN de la hora acumulada).

    Se pasa a mm y a inicio de hora local: t - 1 h (inicio de la hora) - 5 h (UTC-5).
    Los pesos se calculan con celdas de 0.25° centradas en los puntos del CSV.
    """
    e = pd.read_csv(Path(carpeta) / f"era5_lluvia_chosica_{anio}.csv", parse_dates=["valid_time"])
    e["hora"] = e["valid_time"] - pd.Timedelta(hours=6)
    da = (e.assign(mm=e["tp"] * 1000).pivot(index="hora", columns=["latitude", "longitude"], values="mm"))
    lat = np.array(sorted({c[0] for c in da.columns})); lon = np.array(sorted({c[1] for c in da.columns}))
    arr = xr.DataArray(np.array([[da[(la, lo)].values for lo in lon] for la in lat]).transpose(2, 0, 1),
                       coords=dict(time=da.index.values, lat=lat, lon=lon), dims=("time", "lat", "lon"))
    pesos = calcular_pesos(leer_quebradas().query("quebrada_id == @QUEBRADA"), lon, lat, res=0.25)
    print("ERA5: pesos de Quirio ->", {f"{r.lat_centro}": round(r.peso, 2) for r in pesos.itertuples()})
    return lluvia_por_quebrada(arr, pesos, tol=0.01)[QUEBRADA]


def inspeccionar_piscop(ruta):
    ds = xr.open_dataset(ruta)
    print(ds)  # variables y dimensiones; no imprime arreglos completos
    t = ds[next(n for n in ["time", "date", "t"] if n in ds.coords)]
    print("Tiempo:", str(t.values[0]), "->", str(t.values[-1]), "| pasos:", t.size)


def serie_piscop(ruta, bbox, offset_h=None, referencia=None):
    """Serie de Quirio con sus propios pesos (la grilla de PISCOp_h puede ser distinta a la de IMERG).

    Si `offset_h` es None, prueba desfases de -12 a +12 h y elige el de mayor correlación con `referencia`.
    """
    da = leer_piscop(ruta)
    lon0, lat0, lon1, lat1 = bbox
    da = da.sel(lon=slice(lon0, lon1), lat=slice(lat0, lat1)) if da.lat[0] < da.lat[-1] else \
        da.sel(lon=slice(lon0, lon1), lat=slice(lat1, lat0))
    pesos = calcular_pesos(leer_quebradas().query("quebrada_id == @QUEBRADA"), da.lon.values, da.lat.values)
    s = lluvia_por_quebrada(da.load(), pesos)[QUEBRADA].astype(float)
    if offset_h is None:
        if referencia is None or s.index.intersection(referencia.dropna().index).size < 24:
            raise SystemExit("Con menos de 24 h de traslape no se puede estimar el desfase: pasa --piscop-offset.")
        r = {h: s.shift(freq=pd.Timedelta(hours=h)).corr(referencia) for h in range(-12, 13)}
        offset_h = max(r, key=lambda h: -1 if np.isnan(r[h]) else r[h])
        print("Correlación PISCOp_h vs IMERG Final por desfase (h):",
              {h: round(v, 2) for h, v in r.items() if h in (0, 5, 6, 7, 8, offset_h)})
        print(f"Desfase elegido: {offset_h:+d} h")
    return s.shift(freq=pd.Timedelta(hours=offset_h)), offset_h


def graficar(tabla, salida):
    import matplotlib.pyplot as plt

    estilos = {"IMERG Early": ("#2a78d6", "-"), "IMERG Final": ("#eb6834", "--"), "PISCOp_h": ("#1baf7a", ":"), "ERA5": ("#e87ba4", "-.")}
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    t = tabla.loc[VENTANA]
    for nombre, (c, ls) in estilos.items():
        if nombre in t:
            ax.plot(t.index, t[nombre], color=c, ls=ls, lw=2, label=nombre)
    ax.axvline(EVENTO, color="#52514e", lw=1.2)
    ax.annotate("Huaico\n15:10", (EVENTO, ax.get_ylim()[1]), xytext=(6, -6), textcoords="offset points",
                va="top", color="#0b0b0b", fontsize=9)
    ax.set_ylabel("mm por hora (hora de Perú)", color="#52514e")
    ax.set_title("Lluvia horaria sobre Quirio, 22–24 marzo 2015", color="#0b0b0b", loc="left", fontsize=12)
    ax.grid(axis="y", color="#e4e3df", lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#52514e")
    ax.legend(frameon=False, labelcolor="#0b0b0b")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(salida, dpi=150)
    plt.close(fig)


def resumen(tabla):
    d = tabla.loc[DIA]
    antes = tabla.loc["2015-03-23 12:00":"2015-03-23 15:00"].sum()
    fila = pd.DataFrame({
        "pico_mm_h": d.max().round(2),
        "hora_pico": d.idxmax().dt.strftime("%H:%M"),
        "total_23mar_mm": d.sum().round(1),
        "mm_12a16h": antes.round(1),
    })
    print(fila.to_string())
    print("\nCorrelación horaria (día 23):")
    print(d.corr(min_periods=12).round(2).to_string())  # NaN = menos de 12 horas en común


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--early")
    ap.add_argument("--final-dir")
    ap.add_argument("--piscop")
    ap.add_argument("--era5-dir", help="carpeta con era5_lluvia_chosica_AAAA.csv (solo validación)")
    ap.add_argument("--piscop-offset", type=int, help="desfase en horas; si falta, se estima")
    ap.add_argument("--inspect-piscop", metavar="RUTA", help="solo mostrar la estructura del NetCDF de PISCOp_h")
    ap.add_argument("--pesos", default=str(AQUI / "pesos_imerg.csv"))
    ap.add_argument("--out", default=str(AQUI / "salida"))
    a = ap.parse_args()

    if a.inspect_piscop:
        inspeccionar_piscop(a.inspect_piscop)
        raise SystemExit
    pesos = pd.read_csv(a.pesos).query("quebrada_id == @QUEBRADA")
    bbox = bbox_quebradas()
    series = {}
    if a.early:
        series["IMERG Early"] = serie_early(a.early, pesos)
    if a.final_dir:
        series["IMERG Final"] = serie_final(a.final_dir, pesos, bbox)
    if a.piscop:
        ref = series.get("IMERG Final", series.get("IMERG Early"))
        series["PISCOp_h"], _ = serie_piscop(a.piscop, bbox, a.piscop_offset, ref)
    if a.era5_dir:
        series["ERA5"] = serie_era5(a.era5_dir)
    if not series:
        raise SystemExit("Pasa al menos --early, --final-dir o --piscop.")
    tabla = pd.DataFrame(series)
    Path(a.out).mkdir(exist_ok=True)
    tabla.to_csv(Path(a.out) / "prueba_23mar2015.csv")
    resumen(tabla)
    graficar(tabla, Path(a.out) / "prueba_23mar2015.png")
    print(f"\nGuardado en {a.out}: prueba_23mar2015.png / .csv")

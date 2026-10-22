"""Comparación temporal IMERG Early vs PERSIANN-CCS (y contra pluviómetros si existen), por cuenca y por periodo común.

NECESITA datos que NO están en el repositorio: meses de PERSIANN-CCS (02_descargar_persiann_ccs.py) y, opcionalmente, series de pluviómetros en
datos/estaciones/*.csv con columnas: codigo, nombre, lat, lon, fecha_hora_local, mm  (mm por hora; vacío = faltante).
Sin PERSIANN-CCS descargado el script se detiene con un mensaje (no simula nada).

Qué hace (todo en HORA LOCAL de Perú, UTC-5, etiqueta = inicio de la hora, igual que el resto del proyecto):
  1. Lluvia por cuenca de cada producto = suma ponderada por área de sus celdas (pesos de salida/celdas_por_cuenca.csv; IMERG = los pesos del proyecto).
  2. Solo horas en que AMBOS tienen dato. Acumulados de 1, 3, 6 y 24 h: sesgo (PERSIANN - IMERG), razón de totales, correlación (Pearson y Spearman).
  3. Horas con lluvia (>= 0.1 mm/h) y lluvia intensa (>= 2 mm/h, el umbral del proyecto): acuerdo entre productos (POD, FAR, CSI de PERSIANN tomando IMERG como referencia
     NO como verdad) y máximos horarios por temporada.
  4. Huaicos del catálogo con hora: lluvia de 6 y 24 h hasta el huaico en cada producto y su percentil frente a ventanas que terminan a la MISMA hora del día.
  5. Disponibilidad operativa: --lat-imerg 4 y --lat-persiann H (la fila t solo puede usar lluvia con etiqueta <= t - lat - 1). Sin --lat-persiann solo se
     produce la comparación DIAGNÓSTICA (sin retraso) y el informe lo dice. La latencia de PERSIANN-CCS hay que tomarla de su README.
  6. Pluviómetros (si hay): cada producto se toma en la celda que contiene la estación (un pluviómetro es puntual y la celda es un área: la comparación no es de cuenca).
     Sesgo, MAE, correlación, POD/FAR de horas lluviosas e intensas, n de observaciones válidas y faltantes; marca `concluyente` solo con >= 300 horas válidas y >= 10 horas con lluvia.
Salida: salida/temporal_*.csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "lluvia")); sys.path.insert(0, str(RAIZ / "modelo"))
import features_lluvia as fl  # noqa: E402
from comun import eventos_catalogo  # noqa: E402

SALIDA = AQUI / "salida"
LLUVIA, INTENSA = 0.1, 2.0
MIN_HORAS, MIN_LLUVIOSAS = 300, 10


def cargar_persiann(carpeta, convencion):
    import xarray as xr, glob
    fs = sorted(glob.glob(str(Path(carpeta) / "persiann_ccs_????-??.nc")))
    if not fs:
        raise SystemExit(f"No hay meses de PERSIANN-CCS en {carpeta}. Corre primero 02_descargar_persiann_ccs.py (necesita acceso a persiann.eng.uci.edu). No se simulan datos.")
    da = xr.concat([xr.open_dataset(f)["mm_h"].load() for f in fs], dim="time").sortby("time")
    da = da.isel(time=~da.indexes["time"].duplicated())
    shift = 5 if convencion == "inicio" else 6        # etiqueta UTC -> inicio de la hora local
    return da.assign_coords(time=da.time.values - np.timedelta64(shift, "h"))


def serie_por_cuenca(da, pesos, tol):
    out = {}
    for q, g in pesos.groupby("quebrada_id"):
        s = 0
        for r in g.itertuples():
            c = da.sel(lat=r.lat_centro, lon=r.lon_centro, method="nearest", tolerance=tol)
            s = s + r.peso_cuenca_en_celda * c.to_series()
        out[q] = s
    return pd.DataFrame(out).astype("float64")


def acumular(df, h, lag):
    return df.shift(lag).rolling(h, min_periods=h).sum()


def contingencia(a, b, umbral):
    """a: producto evaluado, b: referencia. POD, FAR, CSI con hits/misses/falsas alarmas."""
    m = a.notna() & b.notna()
    A, B = a[m] >= umbral, b[m] >= umbral
    hit, miss, fa = int((A & B).sum()), int((~A & B).sum()), int((A & ~B).sum())
    return dict(n=int(m.sum()), eventos_ref=int(B.sum()), eventos_prod=int(A.sum()), POD=hit / (hit + miss) if hit + miss else np.nan,
                FAR=fa / (hit + fa) if hit + fa else np.nan, CSI=hit / (hit + miss + fa) if hit + miss + fa else np.nan)


def comparar(I, P, lat_i, lat_p):
    filas = []
    ix = I.index.intersection(P.index)
    I, P = I.loc[ix], P.loc[ix]
    for h in (1, 3, 6, 24):
        a, b = acumular(I, h, lat_i), acumular(P, h, lat_p)
        for q in I.columns:
            m = a[q].notna() & b[q].notna()
            x, y = a[q][m], b[q][m]
            filas.append(dict(quebrada=q, acumulado_h=h, horas_validas=int(m.sum()), IMERG_total_mm=x.sum() / h, PERSIANN_total_mm=y.sum() / h,
                              razon_PERSIANN_sobre_IMERG=(y.sum() / x.sum()) if x.sum() > 0 else np.nan, sesgo_mm=float((y - x).mean()) if m.sum() else np.nan,
                              pearson=x.corr(y) if m.sum() > 2 else np.nan, spearman=x.corr(y, method="spearman") if m.sum() > 2 else np.nan,
                              IMERG_max_mm=x.max() if m.sum() else np.nan, PERSIANN_max_mm=y.max() if m.sum() else np.nan))
    t1 = pd.DataFrame(filas)
    det = []
    for q in I.columns:
        for nom, u in (("lluvia>=0.1", LLUVIA), ("intensa>=2", INTENSA)):
            det.append(dict(quebrada=q, umbral=nom, **contingencia(P.shift(lat_p)[q], I.shift(lat_i)[q], u)))
    return t1, pd.DataFrame(det)


def huaicos(I, P, lat_i, lat_p):
    ev = eventos_catalogo()
    ev = ev[ev.hora_evento.notna()].copy()
    ix = I.index.intersection(P.index)
    filas = []
    ref = {}
    for h in (6, 24):
        ref[("I", h)], ref[("P", h)] = acumular(I.loc[ix], h, lat_i), acumular(P.loc[ix], h, lat_p)
    for r in ev.itertuples():
        t = pd.Timestamp(r.fecha) + pd.Timedelta(hours=int(r.hora_evento))
        if t not in ix or r.quebrada_id not in I.columns:
            continue
        f = dict(fecha=t.date(), hora=t.hour, quebrada=r.quebrada_id)
        for h in (6, 24):
            for k, nom in (("I", "IMERG"), ("P", "PERSIANN")):
                s = ref[(k, h)][r.quebrada_id]
                mismas = s[(s.index.hour == t.hour) & s.index.month.isin([12, 1, 2, 3, 4])].dropna()
                f[f"{nom}_{h}h_mm"] = s.get(t, np.nan)
                f[f"{nom}_{h}h_percentil_misma_hora"] = 100 * (mismas <= s.get(t, np.nan)).mean() if len(mismas) and pd.notna(s.get(t, np.nan)) else np.nan
        filas.append(f)
    return pd.DataFrame(filas)


def pluviometros(carpeta, IM, PE, lat_i, lat_p):
    fs = sorted(Path(carpeta).glob("*.csv"))
    if not fs:
        print("Sin series de pluviómetros en", carpeta, "-> se omite la comparación contra observaciones (pendiente de obtener los datos).")
        return None
    filas = []
    for f in fs:
        d = pd.read_csv(f, parse_dates=["fecha_hora_local"])
        for cod, g in d.groupby("codigo"):
            s = g.set_index("fecha_hora_local").mm.astype(float)
            lat, lon = g.lat.iloc[0], g.lon.iloc[0]
            for nom, da, lag in (("IMERG", IM, lat_i), ("PERSIANN", PE, lat_p)):
                c = da.sel(lat=lat, lon=lon, method="nearest").to_series().shift(lag)
                m = s.notna() & c.reindex(s.index).notna()
                x, y = s[m], c.reindex(s.index)[m]
                fila = dict(estacion=cod, nombre=g.nombre.iloc[0], producto=nom, horas_validas=int(m.sum()), horas_faltantes_estacion=int(s.isna().sum()),
                            horas_con_lluvia_obs=int((x >= LLUVIA).sum()), sesgo_mm=float((y - x).mean()) if m.sum() else np.nan, MAE_mm=float((y - x).abs().mean()) if m.sum() else np.nan,
                            pearson=x.corr(y) if m.sum() > 2 else np.nan)
                for u, n in ((LLUVIA, "lluvia"), (INTENSA, "intensa")):
                    k = contingencia(y, x, u)
                    fila.update({f"POD_{n}": k["POD"], f"FAR_{n}": k["FAR"], f"horas_obs_{n}": k["eventos_ref"]})
                fila["concluyente"] = bool(m.sum() >= MIN_HORAS and (x >= LLUVIA).sum() >= MIN_LLUVIOSAS)
                filas.append(fila)
    return pd.DataFrame(filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos-persiann", default=str(AQUI / "datos" / "persiann_ccs"))
    ap.add_argument("--datos-estaciones", default=str(AQUI / "datos" / "estaciones"))
    ap.add_argument("--convencion", choices=["inicio", "fin"], default="inicio")
    ap.add_argument("--lat-imerg", type=int, default=4)
    ap.add_argument("--lat-persiann", type=int, default=None, help="latencia de PERSIANN-CCS en horas, del README. Sin ella solo hay comparación diagnóstica")
    ap.add_argument("--salida", default=str(SALIDA))
    a = ap.parse_args()
    out = Path(a.salida); out.mkdir(exist_ok=True, parents=True)
    PE = cargar_persiann(a.datos_persiann, a.convencion)
    IM = fl._horario(RAIZ / "lluvia" / "datos" / "early")
    celdas = pd.read_csv(SALIDA / "celdas_por_cuenca.csv")
    wi, wp = celdas[celdas["producto"] == "IMERG"], celdas[celdas["producto"] == "PERSIANN-CCS"]
    I, P = serie_por_cuenca(IM, wi, 0.011), serie_por_cuenca(PE, wp, 0.011)
    I.index, P.index = pd.DatetimeIndex(I.index), pd.DatetimeIndex(P.index)
    I, P = I.asfreq("h"), P.asfreq("h")
    print(f"IMERG {I.index.min()} -> {I.index.max()} | PERSIANN {P.index.min()} -> {P.index.max()} | horas en común con dato: {int((I.notna().any(axis=1) & P.notna().any(axis=1)).sum()):,}")
    for nombre, li, lp in [("diagnostico_sin_retraso", 0, 0)] + ([("operativo", a.lat_imerg + 1, a.lat_persiann + 1)] if a.lat_persiann is not None else []):
        t1, t2 = comparar(I, P, li, lp)
        t1.to_csv(out / f"temporal_{nombre}_acumulados.csv", index=False); t2.to_csv(out / f"temporal_{nombre}_deteccion.csv", index=False)
        huaicos(I, P, li, lp).to_csv(out / f"temporal_{nombre}_huaicos.csv", index=False)
        print(f"[{nombre}] resumen de correlación Pearson por acumulado (mediana de cuencas):", t1.groupby("acumulado_h").pearson.median().round(2).to_dict())
    if a.lat_persiann is None:
        print("AVISO: no se pasó --lat-persiann; solo se hizo la comparación diagnóstica (sin retraso). Lee la latencia del README de PERSIANN-CCS y repite.")
    st = pluviometros(a.datos_estaciones, IM, PE, a.lat_imerg + 1, (a.lat_persiann + 1) if a.lat_persiann is not None else 0)
    if st is not None:
        st.to_csv(out / "temporal_pluviometros.csv", index=False); print(st.to_string(index=False))


if __name__ == "__main__":
    main()

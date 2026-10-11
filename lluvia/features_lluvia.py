"""Lluvia horaria por quebrada y features de lluvia (tabla 2).

Entrada : lluvia/datos/early/imerg_early_AAAA-MM.nc (IMERG Early, 30 min, UTC) + lluvia/pesos_imerg.csv
Salidas : lluvia/lluvia_horaria_quebradas.parquet  (hora, quebrada_id, mm)  mm por hora, hora de Perú
          lluvia/features_lluvia.parquet           (hora, quebrada_id, features...)

Convenciones
  - `hora` = INICIO de la hora local (UTC-5), igual que `hora` en las etiquetas: la fila t es la predicción hecha en el instante t.
  - LATENCIA: IMERG Early llega ~4 h tarde. La hora [h, h+1) solo se conoce desde h+1+4. Por eso, en la fila t solo se usan horas con
    etiqueta h <= t-5 (la hora [t-5, t-4) termina en t-4 h). Todas las features se calculan sobre esa lluvia ya "disponible".
  - Una ventana incompleta (por faltar datos: inicio de temporada o hueco entre temporadas) da NaN; no se rellena con ceros.

Features (R = lluvia horaria disponible, en mm/h)
  lluvia_3h, lluvia_6h, lluvia_24h   suma de las últimas 3, 6 y 24 horas disponibles
  int_max_24h                        máximo horario (mm/h) de las últimas 24 h
  tendencia_3h                       lluvia_3h(t) - lluvia_3h(t-3 h)
  horas_lluvia_24h                   horas con R >= UMBRAL_LLUVIA en las últimas 24 h
  lluvia_7d, lluvia_14d              suma de las últimas 168 y 336 horas
  lluvia_efectiva                    Pa(t) = R(t) + k*Pa(t-1), con k = 0.84 por DÍA aplicado por hora (k_h = 0.84**(1/24)); NaN en las primeras 14 d
  horas_desde_lluvia                 horas desde la última hora con R >= UMBRAL_LLUVIA (tope 336)
  lluvia_temporada                   lluvia acumulada desde el 1 de diciembre 00:00 local
  anomalia_14d                       percentil (0-100) de lluvia_14d frente a la misma fecha (+-7 días, misma hora) de temporadas ANTERIORES;
                                     NaN si hay menos de 3 temporadas previas (nunca usa años posteriores)

Uso:  python lluvia/features_lluvia.py            # calcula y guarda
      python lluvia/features_lluvia.py --prueba   # además prueba que ninguna feature mira el futuro
"""
import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from imerg_utils import a_horario_local, lluvia_por_quebrada

AQUI = Path(__file__).resolve().parent
LATENCIA_H = 4
REZAGO = LATENCIA_H + 1
UMBRAL_LLUVIA = 0.1      # mm/h: mínimo que IMERG detecta con sentido
K_DIARIO = 0.84
LIMITE_HORAS = 336       # 14 días
MIN_TEMPORADAS_REF = 3
VENTANA_DIAS_REF = 7
FEATURES = ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "tendencia_3h", "horas_lluvia_24h", "lluvia_7d",
            "lluvia_14d", "lluvia_efectiva", "horas_desde_lluvia", "lluvia_temporada", "anomalia_14d"]


# --------------------------------------------------------------------------- lluvia horaria por quebrada
def lluvia_horaria(carpeta, pesos):
    """DataFrame (horas locales continuas × quebradas) en mm/h; NaN fuera de las temporadas."""
    import xarray as xr

    partes = []
    for f in sorted(glob.glob(str(Path(carpeta) / "imerg_early_*.nc"))):
        with xr.open_dataset(f) as ds:
            partes.append(ds["mm_h"].load())
    da = xr.concat(partes, dim="time").sortby("time")
    da = da.isel(time=~da.indexes["time"].duplicated())
    serie = lluvia_por_quebrada(a_horario_local(da), pesos)
    serie.index = pd.DatetimeIndex(serie.index)
    return serie.astype("float64").asfreq("h")  # float64: las sumas de 14 días no deben acumular error de float32


# --------------------------------------------------------------------------- features
def _recursivas(v, k_h):
    """lluvia_efectiva y horas_desde_lluvia en una sola pasada. Un hueco de datos reinicia la cuenta."""
    n = len(v)
    pa, desde = np.full(n, np.nan), np.full(n, np.nan)
    acum, validas, ultima = 0.0, 0, None
    for i in range(n):
        x = v[i]
        if np.isnan(x):
            acum, validas, ultima = 0.0, 0, None
            continue
        validas += 1
        acum = x + k_h * acum
        if validas >= LIMITE_HORAS:
            pa[i] = acum
        ultima = 0 if x >= UMBRAL_LLUVIA else (None if ultima is None else ultima + 1)
        if ultima is not None:
            desde[i] = min(ultima, LIMITE_HORAS)
        elif validas >= LIMITE_HORAS:
            desde[i] = LIMITE_HORAS
    return pa, desde


def _anomalia(A):
    """A: (temporadas, desfase en horas) de lluvia_14d para una quebrada. Percentil frente a temporadas anteriores."""
    n_s, n_o = A.shape
    res = np.full_like(A, np.nan)
    saltos = np.arange(-VENTANA_DIAS_REF, VENTANA_DIAS_REF + 1) * 24
    pos = np.arange(n_o)[:, None] + saltos[None, :]
    dentro = (pos >= 0) & (pos < n_o)
    posc = np.clip(pos, 0, n_o - 1)
    for s in range(MIN_TEMPORADAS_REF, n_s):
        ref = np.concatenate([np.where(dentro, A[sp][posc], np.nan) for sp in range(s)], axis=1)
        cur = A[s][:, None]
        n = (~np.isnan(ref)).sum(axis=1)
        pct = 100 * ((ref < cur).sum(axis=1) + 0.5 * (ref == cur).sum(axis=1)) / np.where(n > 0, n, np.nan)
        pct[n < MIN_TEMPORADAS_REF * 8] = np.nan  # muy pocas referencias válidas
        pct[np.isnan(A[s])] = np.nan
        res[s] = pct
    return res


def features(R):
    """R: DataFrame (horas locales continuas × quebradas), mm por hora. Devuelve dict feature -> DataFrame."""
    idx = R.index
    L = R.shift(REZAGO)  # lluvia ya disponible en el instante t (latencia)
    out = {}
    s3 = L.rolling(3, min_periods=3).sum()
    out["lluvia_3h"] = s3
    out["lluvia_6h"] = L.rolling(6, min_periods=6).sum()
    out["lluvia_24h"] = L.rolling(24, min_periods=24).sum()
    out["int_max_24h"] = L.rolling(24, min_periods=24).max()
    out["tendencia_3h"] = s3 - s3.shift(3)
    out["horas_lluvia_24h"] = (L >= UMBRAL_LLUVIA).astype(float).where(L.notna()).rolling(24, min_periods=24).sum()
    out["lluvia_7d"] = L.rolling(168, min_periods=168).sum()
    out["lluvia_14d"] = L.rolling(336, min_periods=336).sum()

    k_h = K_DIARIO ** (1 / 24)
    pa, desde = {}, {}
    for c in L.columns:
        pa[c], desde[c] = _recursivas(L[c].to_numpy(dtype=float), k_h)
    out["lluvia_efectiva"] = pd.DataFrame(pa, index=idx)
    out["horas_desde_lluvia"] = pd.DataFrame(desde, index=idx)

    temporada = np.where(idx.month >= 6, idx.year, idx.year - 1)  # la temporada y va de dic y a abr y+1
    inicio = pd.to_datetime([f"{y}-12-01" for y in temporada])
    # la regla "antes del 1 de dic no cuenta" va sobre la hora en que la lluvia CAYÓ (R), no sobre cuándo queda disponible; luego se aplica la latencia
    despues = pd.DataFrame(np.broadcast_to(~np.asarray(idx < inicio)[:, None], R.shape), index=idx, columns=R.columns)
    acum_R = R.where(despues, 0.0).fillna(0.0).groupby(temporada).cumsum().where(R.notna())
    out["lluvia_temporada"] = acum_R.shift(REZAGO)

    off = ((idx - inicio) / pd.Timedelta(hours=1)).to_numpy().astype(int) + 24  # desfase desde el 1 de dic (con 24 h de holgura)
    n_o = 24 + 152 * 24 + 1                       # hasta el 1 de mayo: cubre toda la temporada
    en_temp = (off >= 0) & (off < n_o)            # las horas de mayo a noviembre quedan fuera (no se indexan con desfases negativos)
    temps = np.unique(temporada)
    sidx = np.searchsorted(temps, temporada)
    an = {}
    for c in L.columns:
        v14 = out["lluvia_14d"][c].to_numpy(dtype=float)
        m = en_temp & ~np.isnan(v14)
        A = np.full((len(temps), n_o), np.nan)
        A[sidx[m], off[m]] = v14[m]
        res = _anomalia(A)
        col = np.full(len(idx), np.nan)
        col[m] = res[sidx[m], off[m]]
        an[c] = col
    out["anomalia_14d"] = pd.DataFrame(an, index=idx)
    return out


def a_largo(feats, R):
    """Tabla larga (hora, quebrada_id, features...) sin las horas fuera de temporada."""
    ancho = pd.concat(feats, axis=1)
    largo = ancho.stack(level=1, future_stack=True)
    largo.index.names = ["hora", "quebrada_id"]
    largo = largo[FEATURES].dropna(how="all").astype("float32").reset_index()
    return largo


# --------------------------------------------------------------------------- prueba anti-futuro
def probar_sin_futuro(R, n=30, semilla=7):
    """Cambia TODA la lluvia posterior a la disponible en t (horas con etiqueta > t-5) y exige que las features de t no cambien."""
    rng = np.random.default_rng(semilla)
    col = "quirio" if "quirio" in R.columns else R.columns[0]
    base = features(R[[col]])
    validas = np.where(base["lluvia_14d"][col].notna().to_numpy() & (R.index.year >= 2018))[0]
    elegidas = rng.choice(validas, size=min(n, len(validas)), replace=False)
    fallos = 0
    for pos in elegidas:
        Rp = R[[col]].copy()
        futuro = np.arange(len(Rp)) > pos - REZAGO  # etiqueta > t-5: aún no disponible
        Rp.loc[futuro, col] = rng.uniform(0, 60, futuro.sum())  # lluvia inventada, enorme
        pert = features(Rp)
        for f in FEATURES:
            a, b = base[f][col].iloc[pos], pert[f][col].iloc[pos]
            if not (np.isclose(a, b, equal_nan=True, atol=1e-9)):
                fallos += 1
                print(f"  FUGA en {f} t={R.index[pos]}: {a} != {b}")
    # control positivo: cambiar la lluvia SÍ disponible debe mover las features (si no, la prueba no probaría nada)
    pos = elegidas[0]
    Rq = R[[col]].copy()
    Rq.iloc[pos - REZAGO, 0] += 25.0
    movidas = sum(not np.isclose(base[f][col].iloc[pos], features(Rq)[f][col].iloc[pos], equal_nan=True) for f in ("lluvia_3h", "lluvia_24h", "lluvia_7d"))
    print(f"Prueba anti-futuro: {len(elegidas)} instantes × {len(FEATURES)} features -> {fallos} fugas "
          f"| control positivo (cambiar la lluvia disponible mueve {movidas}/3 features)")
    return fallos == 0 and movidas == 3


# --------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default=str(AQUI / "datos" / "early"))
    ap.add_argument("--pesos", default=str(AQUI / "pesos_imerg.csv"))
    ap.add_argument("--prueba", action="store_true")
    a = ap.parse_args()

    pesos = pd.read_csv(a.pesos)
    R = lluvia_horaria(a.datos, pesos)
    print(f"Lluvia horaria: {R.shape[1]} quebradas, {int(R.iloc[:, 0].notna().sum()):,} horas con dato "
          f"({R.index.min():%Y-%m-%d %H:%M} -> {R.index.max():%Y-%m-%d %H:%M} hora de Perú)")
    largo = R.stack(future_stack=True).dropna().rename("mm").astype("float32").reset_index()
    largo.columns = ["hora", "quebrada_id", "mm"]
    largo.to_parquet(AQUI / "lluvia_horaria_quebradas.parquet", index=False)

    if a.prueba:
        ok = probar_sin_futuro(R)
        if not ok:
            raise SystemExit("La prueba anti-futuro FALLÓ: no se guardan las features.")
    tabla = a_largo(features(R), R)
    tabla.to_parquet(AQUI / "features_lluvia.parquet", index=False)
    print(f"features_lluvia.parquet: {len(tabla):,} filas × {len(FEATURES)} features")
    print("% NaN por feature:", {f: round(100 * tabla[f].isna().mean(), 1) for f in FEATURES})


if __name__ == "__main__":
    main()

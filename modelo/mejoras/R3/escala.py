"""R3: escala entre temporadas, sobre la PIEZA 1 del modelo en dos piezas (misma tabla de zona, mismas etiquetas, mismo XGBoost restringido).

Fijado ANTES de correr:
  3a Normalización causal, por celda IMERG, de VARS_NORM = lluvia_3h, lluvia_6h, lluvia_24h, int_max_24h, lluvia_7d (ya con la latencia de 4 h):
     - pclim: percentil frente a la climatología del MISMO MES, construida SOLO con las horas de entrenamiento de cada pliegue
              (rango medio: (n< + n=/2) / n).
     - p30  : percentil frente a los valores de los 30 días previos de la misma celda (ventana de 721 h, al menos 360 válidas). Causal, sin pliegue.
     Luego máximo y media entre las 5 celdas -> 20 variables, monotonía +1.
     Variantes: A_reemplazo = 20 normalizadas + horas_desde_lluvia (mín, media; -1) + horas_lluvia_24h (máx, media; +1) [sin cantidades crudas];
                A_agregado = las 23 de R1 + las 20 normalizadas.
  3b Cuenca alta (requiere lluvia/datos/early_ampliado, recuadro lat -12.3..-11.5, lon -77.0..-76.0): celdas IMERG con lon >= -76.55 (48 celdas: 6 columnas x 8 filas), máximo entre
     celdas de la lluvia de 3, 6 y 12 h (latencia 4 h), monotonía +1. Variantes: B = R1 + alta; AB = A_agregado + alta.
  Modelo: XGBoost restringido (PARAMS_XGB + CHICO), H como columna (+1), semillas 0-2. Validación LOSTO y LOSO (como R1).
  Umbral de ENTRENAMIENTO: por pliegue y H, cuantil 1-1/N de los puntajes del modelo sobre sus propias horas de entrenamiento (no mira la prueba).
     A nivel quebrada, lo mismo con el riesgo P1 x P2 (P2 "mezcla" del pliegue, de dos_piezas/salida/p2_por_pliegue.csv) sobre horas de entrenamiento x 17.
Uso: python modelo/mejoras/R3/escala.py [variante ...]     (default: V0 A_reemplazo A_agregado; B y AB cuando exista early_ampliado)
Salida: modelo/mejoras/R3/oof_<variante>.parquet (no va a git) y umbrales_entrenamiento_<variante>.csv
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1] / "dos_piezas"))
from base import FEATURES_ZONA, HORIZONTES, MONO_ZONA, RAIZ, SALIDA, pliegue_losto, tabla_zona, tormentas  # noqa: E402
from arboles import PARAMS_XGB  # noqa: E402
from restringido import CHICO  # noqa: E402

VARS_NORM = ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "lluvia_7d"]
LON_ALTA = -76.55
SEMILLAS = (0, 1, 2)
NS = (100, 50)
NORM = [f"{v}_{t}_{a}" for v in VARS_NORM for t in ("pclim", "p30") for a in ("max", "media")]
ALTA = ["alta_max_3h", "alta_max_6h", "alta_max_12h"]
REEMPLAZO = NORM + ["horas_desde_lluvia_min", "horas_desde_lluvia_media", "horas_lluvia_24h_max", "horas_lluvia_24h_media"]
VARIANTES = {"V0": FEATURES_ZONA, "A_reemplazo": REEMPLAZO, "A_agregado": FEATURES_ZONA + NORM,
             "B": FEATURES_ZONA + ALTA, "AB": FEATURES_ZONA + NORM + ALTA}
MONO = {**MONO_ZONA, **{c: 1 for c in NORM + ALTA}}
CACHE = AQUI / "celdas_norm.parquet"


# --------------------------------------------------------------------------- variables por celda
def por_celda():
    """(hora x celda) para VARS_NORM (con latencia) y p30. Devuelve dict v -> DataFrame, y p30 agregado (hora)."""
    import features_lluvia as fl

    datos, pesos = RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
    Rcel = fl.lluvia_celdas(datos, pesos)
    F = fl.features(Rcel, Rcel)
    return {v: F[v] for v in VARS_NORM}


def p30(X):
    """Percentil de cada valor frente a los 30 días previos (incluido él mismo: rango medio de la ventana)."""
    return X.rolling(721, min_periods=360).rank(pct=True, method="average")


def tabla_celdas():
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    C = por_celda()
    partes = {}
    for v, X in C.items():
        for c in X.columns:
            partes[f"{v}|{c}"] = X[c]
            partes[f"{v}_p30|{c}"] = p30(X[c])
    T = pd.DataFrame(partes)
    T.index.name = "hora"
    T = T[T.index.month.isin([12, 1, 2, 3, 4])].astype("float32")
    T.to_parquet(CACHE)
    return T


def alta():
    """Máximo de lluvia de 3/6/12 h entre las celdas de la cuenca alta (lon >= -76.55), con latencia."""
    import features_lluvia as fl
    import xarray as xr  # noqa: F401

    h = fl._horario(RAIZ / "lluvia" / "datos" / "early_ampliado")
    cols = {}
    for i, la in enumerate(h.lat.values):
        for j, lo in enumerate(h.lon.values):
            if lo >= LON_ALTA - 1e-6:
                cols[f"{la:.2f}_{lo:.2f}"] = h.values[:, i, j]
    R = pd.DataFrame(cols, index=pd.DatetimeIndex(h.time.values)).astype("float64").asfreq("h")
    L = R.shift(fl.REZAGO)
    out = pd.DataFrame({f"alta_max_{k}h": L.rolling(k, min_periods=k).sum().max(axis=1, skipna=False) for k in (3, 6, 12)})
    out.index.name = "hora"
    print(f"cuenca alta: {R.shape[1]} celdas", flush=True)
    return out.astype("float32")


def pclim(T, z_horas, train_mask):
    """Percentil climatológico por celda y mes con las horas de entrenamiento; agrega max/media entre celdas. Devuelve DataFrame alineado a z_horas."""
    out = {}
    mes = T.index.month.to_numpy()
    tr_horas = pd.DatetimeIndex(z_horas[train_mask]).unique()
    es_tr = T.index.isin(tr_horas)
    for v in VARS_NORM:
        cols = [c for c in T.columns if c.split("|")[0] == v]
        P = np.full((len(T), len(cols)), np.nan, dtype="float32")
        for k, c in enumerate(cols):
            x = T[c].to_numpy()
            for m in np.unique(mes):
                ref = np.sort(x[es_tr & (mes == m) & ~np.isnan(x)])
                sel = (mes == m) & ~np.isnan(x)
                lo, hi = np.searchsorted(ref, x[sel], "left"), np.searchsorted(ref, x[sel], "right")
                P[sel, k] = (lo + 0.5 * (hi - lo)) / len(ref)
        out[f"{v}_pclim_max"] = np.nanmax(np.where(np.isnan(P).any(axis=1, keepdims=True), np.nan, P), axis=1)
        out[f"{v}_pclim_media"] = np.where(np.isnan(P).any(axis=1), np.nan, P.mean(axis=1))
    D = pd.DataFrame(out, index=T.index)
    return D.reindex(pd.DatetimeIndex(z_horas)).to_numpy(), list(D.columns)


def p30_agregado(T):
    out = {}
    for v in VARS_NORM:
        X = T[[c for c in T.columns if c.split("|")[0] == f"{v}_p30"]]
        out[f"{v}_p30_max"] = X.max(axis=1, skipna=False)
        out[f"{v}_p30_media"] = X.mean(axis=1, skipna=False)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- OOF
def oof(z, cols, grupo, nombre, T, P2):
    usa_pclim = any("_pclim_" in c for c in cols)
    y, H = z.y.to_numpy(), z.H.to_numpy()
    lab = ~np.isnan(y)
    usar = cols + ["H"]
    mono = tuple(1 if c == "H" else MONO[c] for c in usar)
    P = {s: np.full(len(z), np.nan) for s in SEMILLAS}
    umbrales = []
    for g in np.unique(grupo):
        te = grupo == g
        tr = ~te & lab
        X = z[[c for c in usar if "_pclim_" not in c]].copy()
        if usa_pclim:
            M, nombres = pclim(T, z.hora.to_numpy(), ~te)
            X[nombres] = M
        X = X[usar]
        spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
        for s in SEMILLAS:
            m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=s).fit(X[tr], y[tr])
            P[s][te] = m.predict_proba(X[te])[:, 1]
            ptr = m.predict_proba(X[~te])[:, 1]          # puntajes en TODAS las horas de entrenamiento (también y=NaN): solo puntajes, sin etiquetas
            p2 = P2[(P2.esquema == nombre) & (P2.pliegue == g)].mezcla.to_numpy()
            assert len(p2) == 17
            for h in HORIZONTES:
                ph = ptr[H[~te] == h]
                riesgo = np.outer(ph, p2).ravel()
                for N in NS:
                    umbrales.append(dict(esquema=nombre, pliegue=g, semilla=s, H=h, N=N, tau=float(np.quantile(ph, 1 - 1 / N)),
                                         tau_riesgo=float(np.quantile(riesgo, 1 - 1 / N))))
    return P, pd.DataFrame(umbrales)


def main(variantes):
    z = tabla_zona()
    z["pliegue_losto"] = pliegue_losto(z.hora, z.temporada, tormentas())
    T = tabla_celdas()
    z = z.merge(p30_agregado(T), left_on="hora", right_index=True, how="left")
    if any(v in ("B", "AB") for v in variantes):
        z = z.merge(alta(), left_on="hora", right_index=True, how="left")
    for v in variantes:
        ruta = AQUI / f"oof_{v}.parquet"
        if ruta.exists():
            print(f"{v}: ya existe", flush=True)
            continue
        t0 = time.time()
        cols = VARIANTES[v]
        out = z[["hora", "H", "y", "n_y1", "temporada", "pliegue_losto"]].copy()
        ums = []
        P2 = pd.read_csv(SALIDA / "p2_por_pliegue.csv")
        for esquema, grupo in (("losto", z.pliegue_losto.to_numpy()), ("loso", z.temporada.to_numpy())):
            P, u = oof(z, cols, grupo, esquema, T, P2)
            for s in SEMILLAS:
                out[f"p_xgb{s}_{esquema}"] = P[s]
            ums.append(u)
        out.to_parquet(ruta, index=False)
        pd.concat(ums).to_csv(AQUI / f"umbrales_entrenamiento_{v}.csv", index=False)
        print(f"{v}: {len(cols)} variables, {(time.time() - t0) / 60:.1f} min | % NaN de variables: "
              f"{ {c: round(100 * float(z[c].isna().mean()), 1) for c in cols if c in z and z[c].isna().mean() > 0.05} }", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["V0", "A_reemplazo", "A_agregado"])

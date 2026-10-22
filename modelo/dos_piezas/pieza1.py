"""Pieza 1: ¿viene una tormenta peligrosa a Chosica? Predicciones FUERA DE MUESTRA sobre la tabla de zona (todas las horas, también las de y=NaN).

Fijado ANTES de correr (sin mirar resultados):
  - XGBoost restringido = el mismo del modelo actual: PARAMS_XGB + CHICO (profundidad 2, 150 árboles, min_child_weight 50), un modelo para los 4 H
    con H como columna (monótono +1), monotonía MONO_ZONA en la lluvia, scale_pos_weight = sqrt(neg/pos) del entrenamiento. Semillas 0, 1, 2.
  - Logística de referencia (= baseline log1p): un modelo por H; signo(x)*log(1+|x|), imputar mediana, estandarizar, C = 0.1, class_weight balanced.
  - Validación: LOSTO (dejar una tormenta fuera, 16 pliegues) y LOSO (dejar una temporada fuera, 12 pliegues).
Salida: modelo/dos_piezas/oof_zona.parquet (hora, H, y, temporada, pliegue_losto, p_<modelo>_<esquema>).
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from base import AQUI, FEATURES_ZONA, HORIZONTES, MONO_ZONA, pliegue_losto, tabla_zona, tormentas
from arboles import PARAMS_XGB
from restringido import CHICO

RUTA_OOF = AQUI / "oof_zona.parquet"
SEMILLAS = (0, 1, 2)
C_LOG = 0.1


def xgb_fit(X, y, semilla):
    cols = FEATURES_ZONA + ["H"]
    spw = float(np.sqrt((y == 0).sum() / (y == 1).sum()))
    mono = tuple(1 if c == "H" else MONO_ZONA[c] for c in cols)
    return xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=semilla).fit(X[cols], y)


def log_fit(X, y):
    m = make_pipeline(FunctionTransformer(lambda a: np.sign(a) * np.log1p(np.abs(a))), SimpleImputer(strategy="median"), StandardScaler(),
                      LogisticRegression(class_weight="balanced", C=C_LOG, max_iter=3000))
    return m.fit(X[FEATURES_ZONA], y)


def oof(z, grupo, nombre):
    """grupo: id de pliegue por fila. Entrena con las filas etiquetadas de los otros pliegues y predice TODAS las filas del pliegue."""
    lab = z.y.notna().to_numpy()
    y = z.y.to_numpy()
    H = z.H.to_numpy()
    out = {f"p_xgb{s}_{nombre}": np.full(len(z), np.nan) for s in SEMILLAS} | {f"p_log_{nombre}": np.full(len(z), np.nan)}
    for g in np.unique(grupo):
        te = grupo == g
        tr = ~te & lab
        if y[tr].sum() == 0:
            raise ValueError(f"pliegue {g} sin positivos en entrenamiento")
        for s in SEMILLAS:
            out[f"p_xgb{s}_{nombre}"][te] = xgb_fit(z[tr], y[tr], s).predict_proba(z.loc[te, FEATURES_ZONA + ["H"]])[:, 1]
        for h in HORIZONTES:
            trh, teh = tr & (H == h), te & (H == h)
            out[f"p_log_{nombre}"][teh] = log_fit(z[trh], y[trh]).predict_proba(z.loc[teh, FEATURES_ZONA])[:, 1]
        print(f"  {nombre} pliegue {g}: {int(te.sum()):,} filas, {int(np.nansum(y[te]))} positivas", flush=True)
    return out


def main():
    z = tabla_zona()
    t = tormentas()
    z["pliegue_losto"] = pliegue_losto(z.hora, z.temporada, t)
    cols = {}
    cols |= oof(z, z.pliegue_losto.to_numpy(), "losto")
    cols |= oof(z, z.temporada.to_numpy(), "loso")
    o = z[["hora", "H", "y", "n_y1", "temporada", "pliegue_losto"]].assign(**cols)
    o.to_parquet(RUTA_OOF, index=False)
    print(f"Guardado {RUTA_OOF.name}: {len(o):,} filas, NaN en p: {int(o.filter(like='p_').isna().sum().sum())}")


if __name__ == "__main__":
    main()

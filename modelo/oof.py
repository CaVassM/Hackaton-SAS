"""Predicciones FUERA DE MUESTRA (leave-one-season-out) del modelo restringido (AMBAS: monotonía + árboles pequeños, V1 + D, semilla 0).
Guarda modelo/oof_restringido.parquet (no va a git): hora, quebrada_id, H, y, temporada, p, más algunas variables para diagnóstico.
"""
import numpy as np
import pandas as pd
import xgboost as xgb

from arboles import PARAMS_XGB, temporadas_con_evento
from comun import RAIZ
from restringido import CHICO, COLS, MONO
from tabla3 import HORIZONTES, RUTA

RUTA_OOF = RAIZ / "modelo" / "oof_restringido.parquet"
RUTA_OOF_TODAS = RAIZ / "modelo" / "oof_restringido_todas.parquet"
EXTRA = ["lluvia_6h", "lluvia_24h", "lluvia_7d", "lluvia_14d", "reg_max_24h", "horas_desde_lluvia"]


def oof_restringido(semilla=0, forzar=False):
    if RUTA_OOF.exists() and not forzar:
        return pd.read_parquet(RUTA_OOF)
    t = pd.read_parquet(RUTA).reset_index(drop=True)
    usar = COLS + ["H"]
    mono = tuple(1 if c == "H" else MONO.get(c, 0) for c in usar)
    seasons = sorted({s for H in HORIZONTES for s in temporadas_con_evento(t[t.H == H])})
    y, temp = t.y.to_numpy(), t.temporada.to_numpy()
    p = np.full(len(t), np.nan)
    for s in seasons:
        te = temp == s
        spw = float(np.sqrt((y[~te] == 0).sum() / (y[~te] == 1).sum()))
        m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=semilla).fit(t.loc[~te, usar], y[~te])
        p[te] = m.predict_proba(t.loc[te, usar])[:, 1]
    sel = t.temporada.isin(seasons).to_numpy()
    out = t.loc[sel, ["hora", "quebrada_id", "H", "y", "temporada"] + EXTRA].assign(p=p[sel]).reset_index(drop=True)
    out.to_parquet(RUTA_OOF, index=False)
    return out


def oof_todas(semilla=0, forzar=False):
    """Igual que oof_restringido pero con las 12 temporadas: cada una se predice con un modelo entrenado en las otras 11 (las tranquilas también)."""
    if RUTA_OOF_TODAS.exists() and not forzar:
        return pd.read_parquet(RUTA_OOF_TODAS)
    t = pd.read_parquet(RUTA).reset_index(drop=True)
    usar = COLS + ["H"]
    mono = tuple(1 if c == "H" else MONO.get(c, 0) for c in usar)
    y, temp = t.y.to_numpy(), t.temporada.to_numpy()
    p = np.full(len(t), np.nan)
    for s in sorted(t.temporada.unique()):
        te = temp == s
        spw = float(np.sqrt((y[~te] == 0).sum() / (y[~te] == 1).sum()))
        m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=semilla).fit(t.loc[~te, usar], y[~te])
        p[te] = m.predict_proba(t.loc[te, usar])[:, 1]
    out = t[["hora", "quebrada_id", "H", "y", "temporada"]].assign(p=p)
    out.to_parquet(RUTA_OOF_TODAS, index=False)
    return out


if __name__ == "__main__":
    o = oof_todas()
    print(f"OOF (12 temporadas) guardado: {len(o):,} filas, temporadas {sorted(o.temporada.unique())}")

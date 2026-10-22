"""Paso 6: modelo restringido. XGBoost con restricciones físicas de monotonía en la lluvia y árboles pequeños, variables = originales (V1) + grupo regional D.
TODO fijado de antemano (sin mirar resultados):
  Monotonía (+1 = más valor nunca baja el riesgo): lluvia_3h, lluvia_6h, lluvia_24h, int_max_24h, horas_lluvia_24h, lluvia_7d, lluvia_14d, lluvia_efectiva,
     lluvia_temporada, reg_max_24h, reg_max_3h_24h, H.  (-1) horas_desde_lluvia.  Sin restricción: tendencia_3h y el terreno.
  Árboles pequeños: max_depth=2, n_estimators=150, min_child_weight=50 (el resto igual que PARAMS_XGB).
Variantes (3 semillas c/u): MONO (solo monotonía, capacidad original), CHICO (solo árboles pequeños), AMBAS (el modelo pre-especificado).
Referencias ya medidas: V1 (3.43), V1 + D sin restricciones (6.1).
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score

from arboles import PARAMS_XGB, temporadas_con_evento
from comun import SALIDA
from ingenieria import DIR, correr, lift_fold
from tabla3 import FEATURES_V1, GRUPOS_NUEVOS, HORIZONTES, RUTA

COLS = FEATURES_V1 + GRUPOS_NUEVOS["D regional"]
MONO = {**{c: 1 for c in ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "horas_lluvia_24h", "lluvia_7d", "lluvia_14d", "lluvia_efectiva",
                          "lluvia_temporada", "reg_max_24h", "reg_max_3h_24h"]}, "horas_desde_lluvia": -1}
CHICO = dict(max_depth=2, n_estimators=150, min_child_weight=50)
VARIANTES = {"MONO": (MONO, None), "CHICO": (None, CHICO), "AMBAS": (MONO, CHICO)}


def brecha(t, mono, params):
    """Calidad en entrenamiento (con los negativos reponderados) frente a la de la temporada de prueba. Semilla 0."""
    y, H, temp = t.y.to_numpy(), t.H.to_numpy(), t.temporada.to_numpy()
    seasons = sorted({s for h in HORIZONTES for s in temporadas_con_evento(t[t.H == h])})
    usar = COLS + ["H"]
    mono_t = tuple(1 if c == "H" else (mono or {}).get(c, 0) for c in usar)
    tr_l, te_l = [], []
    for s in seasons:
        te = temp == s
        spw = float(np.sqrt((y[~te] == 0).sum() / (y[~te] == 1).sum()))
        m = xgb.XGBClassifier(**{**PARAMS_XGB, **(params or {})}, scale_pos_weight=spw, monotone_constraints=mono_t, random_state=0).fit(t.loc[~te, usar], y[~te])
        idx = np.where(~te)[0]
        rng = np.random.default_rng(0)
        idx = np.concatenate([idx[y[idx] == 1], rng.choice(idx[y[idx] == 0], size=int(0.15 * (y[idx] == 0).sum()), replace=False)])
        p_tr = m.predict_proba(t.loc[idx, usar])[:, 1]
        w = np.where(y[idx] == 1, 1.0, 1 / 0.15)
        v = [average_precision_score(y[idx][H[idx] == h], p_tr[H[idx] == h], sample_weight=w[H[idx] == h]) / np.average(y[idx][H[idx] == h], weights=w[H[idx] == h])
             for h in HORIZONTES if y[idx][H[idx] == h].sum() > 0]
        tr_l.append(float(np.mean(v)))
        te_l.append(lift_fold(y[te], H[te], m.predict_proba(t.loc[te, usar])[:, 1]))
    return float(np.mean(tr_l)), float(np.mean(te_l))


def main():
    t = pd.read_parquet(RUTA).reset_index(drop=True)
    for nombre, (mono, params) in VARIANTES.items():
        for sem in (0, 1, 2):
            correr(t, COLS, f"R_{nombre}_semilla{sem}", sem, mono_extra=mono, params=params)
    ruta = DIR / "brecha_restringido.json"
    if not ruta.exists():
        ruta.write_text(json.dumps({n: brecha(t, m, p) for n, (m, p) in {"V1+D sin restricciones": (None, None), "AMBAS": VARIANTES["AMBAS"]}.items()}))
    print("Listo.", flush=True)


if __name__ == "__main__":
    main()

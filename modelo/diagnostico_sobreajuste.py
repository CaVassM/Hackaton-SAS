"""¿El grupo B (humedad previa) se memoriza? Compara la calidad en las temporadas de ENTRENAMIENTO con la de la temporada de PRUEBA (brecha de generalización),
y mide cuánto se parecen entre sí las variables lentas (ventanas largas) frente a las rápidas. XGBoost con PARAMS_XGB fijos, semilla 0, mismo LOSO.
"""
import numpy as np
import pandas as pd
import xgboost as xgb

from arboles import PARAMS_XGB, temporadas_con_evento
from ingenieria import lift_fold
from tabla3 import FEATURES_V1, GRUPOS_NUEVOS, HORIZONTES, RUTA

t = pd.read_parquet(RUTA).reset_index(drop=True)
y, H, temp = t.y.to_numpy(), t.H.to_numpy(), t.temporada.to_numpy()
seasons = sorted({s for h in HORIZONTES for s in temporadas_con_evento(t[t.H == h])})
conjuntos = {"V1 (13 variables)": FEATURES_V1, "V1 + B humedad previa": FEATURES_V1 + GRUPOS_NUEVOS["B humedad previa"], "V1 + D regional": FEATURES_V1 + GRUPOS_NUEVOS["D regional"]}
filas = []
for nombre, cols in conjuntos.items():
    usar = cols + ["H"]
    mono = tuple(1 if c == "H" else 0 for c in usar)
    tr_l, te_l = [], []
    for s in seasons:
        te = temp == s
        spw = float(np.sqrt((y[~te] == 0).sum() / (y[~te] == 1).sum()))
        m = xgb.XGBClassifier(**PARAMS_XGB, scale_pos_weight=spw, monotone_constraints=mono, random_state=0).fit(t.loc[~te, usar], y[~te])
        # entrenamiento: submuestra de las temporadas de entrenamiento con los mismos criterios (todas las filas con huaico + 15 % del resto, para ir rápido)
        idx = np.where(~te)[0]
        rng = np.random.default_rng(0)
        idx = np.concatenate([idx[y[idx] == 1], rng.choice(idx[y[idx] == 0], size=int(0.15 * (y[idx] == 0).sum()), replace=False)])
        # el lift con submuestra de negativos no es comparable en valor absoluto: se calcula la capacidad de ordenar con la tasa real, reponderando los negativos
        p_tr = m.predict_proba(t.loc[idx, usar])[:, 1]
        w = np.where(y[idx] == 1, 1.0, 1 / 0.15)
        from sklearn.metrics import average_precision_score
        v = []
        for h in HORIZONTES:
            k = H[idx] == h
            if y[idx][k].sum() > 0:
                v.append(average_precision_score(y[idx][k], p_tr[k], sample_weight=w[k]) / np.average(y[idx][k], weights=w[k]))
        tr_l.append(float(np.mean(v)))
        te_l.append(lift_fold(y[te], H[te], m.predict_proba(t.loc[te, usar])[:, 1]))
    filas.append(dict(conjunto=nombre, lift_entrenamiento=round(np.mean(tr_l), 1), lift_prueba=round(np.mean(te_l), 2), brecha=round(np.mean(tr_l) - np.mean(te_l), 1)))
    print(filas[-1], flush=True)
print("\n" + pd.DataFrame(filas).to_string(index=False))

# ¿qué tan "lentas" son las variables? autocorrelación a 24 h de cada variable (cerca de 1 = casi no cambia de un día al siguiente => puede identificar una tormenta concreta)
d = t[t.H == 6].sort_values(["quebrada_id", "hora"])
ac = {}
for c in FEATURES_V1 + GRUPOS_NUEVOS["B humedad previa"] + GRUPOS_NUEVOS["D regional"]:
    a = d.groupby("quebrada_id")[c].apply(lambda s: s.autocorr(24))
    ac[c] = round(float(a.mean()), 2)
print("\nAutocorrelación a 24 h (1 = muy lenta):", dict(sorted(ac.items(), key=lambda x: -x[1])))

"""Diagnóstico (NO selección): A2 + 24-72 h + UNA variable de estado a la vez, para interpretar qué impulsa el TSS de B1(a). Mismo diseño que fase_b1."""
import sys
from pathlib import Path
import numpy as np, pandas as pd, xgboost as xgb
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent)); sys.path.insert(0, str(AQUI.parent / "A"))
from fase_b1 import estado_horario, fila, A2, H_EV, base, features_intensidad, score_model_safe, PARAMS_XGB, CHICO, MODELO
from comun_v3 import etiquetar, eventos_lluvia, lluvia_zona, evaluar_loso
E = estado_horario()
base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
z = base.etiquetas_zona().merge(features_intensidad(), left_on="hora", right_index=True, how="left").merge(E, left_on="hora", right_index=True, how="left")
z["temporada"] = base.temporada_de(z.hora)
y, temp = z.y.to_numpy(), z.temporada.to_numpy(); lab = ~np.isnan(y)
ev = pd.read_parquet(AQUI / "fase_b1_eventos.parquet"); _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
filas = []
for extra in (["hum_suelo_5d"], ["dias_activ"], ["icen"]):
    usar = A2["A2_mas_72h"] + extra + ["H"]; mono = tuple(0 if c == "dias_activ" else 1 for c in usar)
    p = np.full(len(z), np.nan)
    for s in np.unique(temp):
        te, tr = temp == s, (temp != s) & lab
        spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
        p[te] = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=0).fit(z.loc[tr, usar], y[tr]).predict_proba(z.loc[te, usar])[:, 1]
    serie = pd.Series(p[z.H.to_numpy() == H_EV], index=z.hora[z.H == H_EV])
    ev["x"] = [score_model_safe(serie, r) for r in ev.itertuples()]
    r, _, res = evaluar_loso(ev, ciegos, "x")
    filas.append(fila("A2 + 24-72 h + " + extra[0], r, res, ciegos))
print(pd.DataFrame(filas).to_string(index=False))
d = ev[ev.disparador == 1]
print("dias_activ al inicio de los disparadores:", E.reindex(d.inicio).dias_activ.round(0).tolist())
print("dias_activ en no disparadores: % <= 7 días:", round(100 * (E.reindex(ev[ev.disparador == 0].inicio).dias_activ <= 7).mean(), 1))

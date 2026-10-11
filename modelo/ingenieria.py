"""Paso 5: ingeniería de variables y análisis de cuánto aporta cada variable/grupo (XGBoost, mismo LOSO y mismas métricas).

Todo con los hiperparámetros FIJOS de modelo/arboles.py (PARAMS_XGB). Reglas para no engañarse:
  - Piso de ruido: V1 y V2 con 3 semillas; una diferencia menor que el ruido entre semillas no cuenta.
  - Aporte de grupos: V2 sin cada grupo (quitar) y V1 más cada grupo (agregar).
  - Importancia por permutación en la temporada que queda fuera (por variable y por grupo): cuánto cae la calidad al barajar esa(s) columna(s).
  - Selección DENTRO de cada pliegue (top 10 por ganancia en entrenamiento): único modo honesto de "quedarse con las mejores".
  - Calidad = "lift medio": AUPRC de cada temporada dividido por su tasa de positivos, promediado sobre temporadas y horizontes.
Uso: python modelo/ingenieria.py   (reanuda: cada corrida queda en modelo/salida/ingenieria/)
"""
import json
import sys
import time
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from arboles import PARAMS_XGB, temporadas_con_evento
from comun import SALIDA
from metricas import metricas_por_temporada
from tabla3 import FEATURES_TERRENO, FEATURES_V1, FEATURES_V2, GRUPOS_NUEVOS, HORIZONTES, RUTA

DIR = SALIDA / "ingenieria"
DIR.mkdir(exist_ok=True)
BASE_CORTA = ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "tendencia_3h", "horas_lluvia_24h"]
BASE_LARGA = ["lluvia_7d", "lluvia_14d", "lluvia_efectiva", "horas_desde_lluvia", "lluvia_temporada"]
GRUPOS_PERM = {"base: lluvia corta": BASE_CORTA, "base: lluvia larga": BASE_LARGA, "base: terreno": FEATURES_TERRENO, **GRUPOS_NUEVOS, "H (horizonte)": ["H"]}
REPETICIONES = 3
K_SELECCION = 10


def lift_fold(y, H, p):
    v = [average_precision_score(y[H == h], p[H == h]) / y[H == h].mean() for h in HORIZONTES if y[H == h].sum() > 0]
    return float(np.mean(v))


def correr(t, cols, nombre, semilla=0, permutar=False, k_sel=None):
    import xgboost as xgb

    ruta = DIR / f"run_{nombre}.json"
    if ruta.exists():
        return json.loads(ruta.read_text())
    t0 = time.time()
    cols = list(cols)
    seasons = sorted({s for H in HORIZONTES for s in temporadas_con_evento(t[t.H == H])})
    y_all, H_all, temp = t.y.to_numpy(), t.H.to_numpy(), t.temporada.to_numpy()
    p = np.full(len(t), np.nan)
    rng = np.random.default_rng(semilla)
    perm, sel = [], Counter()

    for s in seasons:
        te = temp == s
        ytr = y_all[~te]
        spw = float(np.sqrt((ytr == 0).sum() / (ytr == 1).sum()))

        def ajustar(c):
            mono = tuple(1 if x == "H" else 0 for x in c + ["H"])
            m = xgb.XGBClassifier(**PARAMS_XGB, scale_pos_weight=spw, monotone_constraints=mono, random_state=semilla)
            return m.fit(t.loc[~te, c + ["H"]], ytr)

        m, cf = ajustar(cols), cols
        if k_sel:
            g = m.get_booster().get_score(importance_type="total_gain")
            cf = sorted(cols, key=lambda c: -g.get(c, 0))[:k_sel]
            sel.update(cf)
            m = ajustar(cf)
        Xte = t.loc[te, cf + ["H"]].reset_index(drop=True)
        pte = m.predict_proba(Xte)[:, 1]
        p[te] = pte
        if permutar:
            yte, Hte = y_all[te], H_all[te]
            base = lift_fold(yte, Hte, pte)
            for nom, gcols in {**{c: [c] for c in cf + ["H"]}, **{k: [c for c in v if c in Xte.columns] for k, v in GRUPOS_PERM.items()}}.items():
                if not gcols:
                    continue
                caidas = []
                for _ in range(REPETICIONES):
                    Xp = Xte.copy()
                    Xp[gcols] = Xte[gcols].to_numpy()[rng.permutation(len(Xte))]  # las columnas del grupo se barajan juntas
                    caidas.append(base - lift_fold(yte, Hte, m.predict_proba(Xp)[:, 1]))
                perm.append(dict(nombre=nom, es_grupo=nom in GRUPOS_PERM, temporada=s, caida=float(np.mean(caidas))))
    ev_all = t.assign(p=p)
    filas, lifts, det100, det50, bloques = [], {}, 0, 0, 0
    for H in HORIZONTES:
        d = ev_all[ev_all.H == H]
        con = temporadas_con_evento(d)
        n, _ = metricas_por_temporada(d[d.temporada.isin(con)], con, H)
        n["lift"] = n.AUPRC / n.base
        for s, v in n[n.N == 100].set_index("temporada").lift.items():
            lifts.setdefault(s, []).append(float(v))
        det100 += int(n[n.N == 100].detectados.sum()); det50 += int(n[n.N == 50].detectados.sum()); bloques += int(n[n.N == 100].bloques.sum())
    por_temp = {s: float(np.mean(v)) for s, v in lifts.items()}
    r = dict(nombre=nombre, n_variables=len(cols) if not k_sel else k_sel, lift_medio=float(np.mean(list(por_temp.values()))), lift_por_temporada=por_temp,
             detectados_N100=det100, detectados_N50=det50, bloques_total=bloques, minutos=round((time.time() - t0) / 60, 1),
             permutacion=perm, seleccion=dict(sel))
    ruta.write_text(json.dumps(r))
    print(f"  {nombre}: lift medio {r['lift_medio']:.2f} | detectados {det100}/{bloques} (N=100) | {r['minutos']} min", flush=True)
    return r


def main():
    t = pd.read_parquet(RUTA).reset_index(drop=True)
    print(f"V1 = {len(FEATURES_V1)} variables | V2 = {len(FEATURES_V2)} variables", flush=True)
    for sem in (0, 1, 2):
        correr(t, FEATURES_V1, f"V1_semilla{sem}", sem)
    correr(t, FEATURES_V2, "V2_semilla0", 0, permutar=True)
    for sem in (1, 2):
        correr(t, FEATURES_V2, f"V2_semilla{sem}", sem)
    for g, fs in GRUPOS_NUEVOS.items():
        correr(t, [c for c in FEATURES_V2 if c not in fs], f"V2_sin_{g[0]}")
    for g, fs in GRUPOS_NUEVOS.items():
        correr(t, FEATURES_V1 + fs, f"V1_mas_{g[0]}")
    correr(t, FEATURES_V2, "V2_seleccion_top10", k_sel=K_SELECCION)
    print("Listo.", flush=True)


if __name__ == "__main__":
    main()

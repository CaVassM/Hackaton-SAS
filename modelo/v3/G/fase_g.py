"""Fase G: ¿otro algoritmo mejora la pieza 1? Mismo protocolo que v3: mismas 13 variables, mismas etiquetas, LOSO por temporada,
puntaje por evento (máx. p_zona H = 3), umbral de máx. TSS con las otras temporadas, bootstrap por tormenta.

Fijado ANTES de correr (sin ajustar hiperparámetros mirando resultados):
  - XGBoost v3 (control).
  - Regresión logística: lluvia y dias_activ con log1p, H con log; estandarizada; C = 1; peso √(neg/pos) en positivos.
  - Random Forest: 300 árboles, min_samples_leaf = 50, max_features = sqrt; peso √(neg/pos).
  - LightGBM: mismos valores que XGBoost (profundidad 2, 150 árboles, lr 0.05, hessiana mínima 50, lambda 10, 0.8/0.8) y misma monotonía.
  - EBM (Explainable Boosting Machine, GAM aditivo): sin interacciones, 4 outer_bags, misma monotonía; peso √(neg/pos).
  - Promedio XGBoost + logística.
Regla: se adopta otro modelo solo si su TSS supera al control en >= 0.05 Y el límite inferior de su IC 90 % no es menor que el del control.
Salida: modelo/v3/G/g_modelos.csv
"""
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from interpret.glassbox import ExplainableBoostingClassifier

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent, AQUI.parent / "A", AQUI.parent / "B", AQUI.parent / "F"):
    sys.path.insert(0, str(p))
from comun_v3 import etiquetar, evaluar_loso, eventos_lluvia, lluvia_zona  # noqa: E402
from fase_b1 import CHICO, PARAMS_XGB, fila  # noqa: E402
import fase_f  # noqa: E402

COLS = fase_f.B1 + ["H"]
MONO = [0 if c == "dias_activ" else 1 for c in COLS]
LLUVIA = fase_f.A2["A2_mas_72h"]


def transf_log(X):
    X = X.copy()
    for c in LLUVIA + ["dias_activ"]:
        X[c] = np.log1p(X[c].clip(lower=0))
    X["H"] = np.log(X["H"])
    return X


def ajustar(nombre, Xtr, ytr, Xte):
    npos = (ytr == 1).sum()
    spw = float(np.sqrt((ytr == 0).sum() / npos))
    w = np.where(ytr == 1, spw, 1.0)
    if nombre == "xgb":
        m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=tuple(MONO), random_state=0)
        return m.fit(Xtr, ytr).predict_proba(Xte)[:, 1]
    if nombre == "logistica":
        A, B = transf_log(Xtr).fillna(0), transf_log(Xte).fillna(0)
        sc = StandardScaler().fit(A)
        m = LogisticRegression(C=1.0, max_iter=3000).fit(sc.transform(A), ytr, sample_weight=w)
        return m.predict_proba(sc.transform(B))[:, 1]
    if nombre == "rf":
        m = RandomForestClassifier(n_estimators=300, min_samples_leaf=50, max_features="sqrt", n_jobs=-1, random_state=0)
        return m.fit(Xtr.fillna(-1), ytr, sample_weight=w).predict_proba(Xte.fillna(-1))[:, 1]
    if nombre == "lightgbm":
        m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=4, max_depth=2, min_sum_hessian_in_leaf=50, reg_lambda=10,
                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, monotone_constraints=MONO, scale_pos_weight=spw,
                               random_state=0, verbose=-1)
        return m.fit(Xtr, ytr).predict_proba(Xte)[:, 1]
    if nombre == "ebm":
        m = ExplainableBoostingClassifier(interactions=0, outer_bags=4, monotone_constraints=MONO, random_state=0, n_jobs=-1)
        return m.fit(Xtr.fillna(0), ytr, sample_weight=w).predict_proba(Xte.fillna(0))[:, 1]
    raise ValueError(nombre)


CACHE_G = AQUI / "_cache"


def correr(nombre, limite_s=150):
    """Predice las temporadas que falten para `nombre` y las guarda una por una (permite correr por tramos)."""
    CACHE_G.mkdir(exist_ok=True)
    z = fase_f.tabla()
    t, y = z.temporada.to_numpy(), z.y.to_numpy()
    lab = ~np.isnan(y)
    t0 = time.time()
    for s in fase_f.TEMPS:
        f = CACHE_G / f"{nombre}_{s}.npy"
        if f.exists():
            continue
        if time.time() - t0 > limite_s:
            print("pausa", flush=True)
            return
        te, tr = t == s, (t != s) & lab
        np.save(f, ajustar(nombre, z.loc[tr, COLS], y[tr], z.loc[te, COLS]))
        print(f"  {nombre} {s} ({time.time() - t0:.0f} s)", flush=True)
    print(f"{nombre} completo", flush=True)


def main():
    pd.set_option("display.width", 230)
    z = fase_f.tabla()
    ev0 = pd.read_parquet(AQUI.parent / "A" / "fase_a_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    t, y = z.temporada.to_numpy(), z.y.to_numpy()
    lab = ~np.isnan(y)
    preds, filas = {}, []
    for nombre in [m for m in ["xgb", "logistica", "lightgbm", "rf", "ebm"] if not (m == "ebm" and os.environ.get("SIN_EBM"))]:
        t0 = time.time()
        p = np.full(len(z), np.nan)
        for s in fase_f.TEMPS:
            te, tr = t == s, (t != s) & lab
            f = CACHE_G / f"{nombre}_{s}.npy"
            p[te] = np.load(f) if f.exists() else ajustar(nombre, z.loc[tr, COLS], y[tr], z.loc[te, COLS])
        preds[nombre] = p
        print(f"  {nombre} listo en {time.time() - t0:.0f} s", flush=True)
    preds["xgb+logistica"] = (preds["xgb"] + preds["logistica"]) / 2
    etiquetas = {"xgb": "XGBoost v3 (control)", "logistica": "Regresión logística", "lightgbm": "LightGBM", "rf": "Random Forest",
                 "ebm": "EBM (GAM aditivo)", "xgb+logistica": "Promedio XGBoost + logística"}
    for k, p in preds.items():
        ev = ev0.copy()
        ev["s"] = fase_f.puntajes_evento(z, p, ev)
        r, _, res = evaluar_loso(ev, ciegos, "s")
        filas.append(fila(etiquetas[k], r, res, ciegos))
        print(filas[-1], flush=True)
    out = pd.DataFrame(filas)
    out.to_csv(AQUI / "g_modelos.csv", index=False)
    print(out.to_string(index=False))
    print("FIN", flush=True)


if __name__ == "__main__":
    correr(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "correr" else main()

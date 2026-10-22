"""Confirmación del hallazgo más fuerte del paso 5 (grupo D regional) para descartar que sea suerte de una semilla o de un solo tipo de modelo.
  - XGBoost: V1 + D con 2 semillas más.
  - Regresión logística (log1p, C=0.1) y Random Forest: V1 contra V1 + D, mismo LOSO y mismas métricas.
"""
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from arboles import temporadas_con_evento
from baseline_logistica import modelo as modelo_logistica
from comun import SALIDA
from ingenieria import DIR, correr
from metricas import metricas_por_temporada
from tabla3 import FEATURES_TERRENO, FEATURES_V1, GRUPOS_NUEVOS, HORIZONTES, RUTA


def loso_sklearn(t, cols, tipo, nombre):
    ruta = DIR / f"conf_{nombre}.json"
    if ruta.exists():
        return json.loads(ruta.read_text())
    lluvia = [c for c in cols if c not in FEATURES_TERRENO]
    lifts, det, bl = {}, 0, 0
    for H in HORIZONTES:
        d = t[t.H == H].reset_index(drop=True)
        con = temporadas_con_evento(d)
        X = d[cols].copy()
        if tipo == "logistica":
            X[lluvia] = np.sign(X[lluvia]) * np.log1p(X[lluvia].abs())
        p = np.full(len(d), np.nan)
        for s in con:
            te = (d.temporada == s).to_numpy()
            m = modelo_logistica(0.1) if tipo == "logistica" else make_pipeline(
                SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=200, min_samples_leaf=100, max_features="sqrt", max_samples=0.2,
                                                                         class_weight="balanced_subsample", n_jobs=4, random_state=0))
            m.fit(X[~te], d.y[~te])
            p[te] = m.predict_proba(X[te])[:, 1]
        sel = d.temporada.isin(con).to_numpy()
        n, _ = metricas_por_temporada(d[sel].assign(p=p[sel]), con, H)
        n["lift"] = n.AUPRC / n.base
        for s, v in n[n.N == 100].set_index("temporada").lift.items():
            lifts.setdefault(s, []).append(float(v))
        det += int(n[n.N == 100].detectados.sum()); bl += int(n[n.N == 100].bloques.sum())
    r = dict(nombre=nombre, lift_medio=float(np.mean([np.mean(v) for v in lifts.values()])), detectados=det, bloques=bl,
             por_temporada={s: float(np.mean(v)) for s, v in lifts.items()})
    ruta.write_text(json.dumps(r))
    print(f"  {nombre}: lift medio {r['lift_medio']:.2f} | detectados {det}/{bl}", flush=True)
    return r


def lift_desde_csv(ruta):
    n = pd.read_csv(ruta)
    n = n[n.N == 100].assign(lift=lambda d: d.AUPRC / d.base)
    return float(n.groupby("temporada").lift.mean().mean()), int(n.detectados.sum())


def main():
    t = pd.read_parquet(RUTA).reset_index(drop=True)
    D = GRUPOS_NUEVOS["D regional"]
    for s in (1, 2):
        correr(t, FEATURES_V1 + D, f"V1_mas_D_semilla{s}", s)
    log1 = loso_sklearn(t, FEATURES_V1, "logistica", "logistica_V1")
    log2 = loso_sklearn(t, FEATURES_V1 + D, "logistica", "logistica_V1_mas_D")
    rf1 = loso_sklearn(t, FEATURES_V1, "rf", "rf_V1")
    rf2 = loso_sklearn(t, FEATURES_V1 + D, "rf", "rf_V1_mas_D")
    xs = [json.load(open(DIR / f"run_V1_mas_D{x}.json")) for x in ("", "_semilla1", "_semilla2")]
    x1 = [json.load(open(DIR / f"run_V1_semilla{s}.json")) for s in range(3)]
    f = lambda r: f"{r['lift_medio']:.2f} ({r.get('detectados', r.get('detectados_N100'))}/{r.get('bloques', r.get('bloques_total'))})"
    print("\nCONFIRMACIÓN GRUPO D (lift medio y bloques detectados con N=100)")
    print("XGBoost  V1       :", " | ".join(f(r) for r in x1))
    print("XGBoost  V1 + D   :", " | ".join(f(r) for r in xs))
    print(f"Logística V1 -> V1 + D : {f(log1)} -> {f(log2)}")
    print(f"Random Forest V1 -> V1 + D : {f(rf1)} -> {f(rf2)}")
    print("\nPor temporada (lift), XGBoost semilla 0:  V1 vs V1 + D")
    a, b = x1[0]["lift_por_temporada"], xs[0]["lift_por_temporada"]
    print({s: f"{a[s]:.1f} -> {b[s]:.1f}" for s in a})


if __name__ == "__main__":
    main()

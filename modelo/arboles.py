"""Paso 4: XGBoost y Random Forest con la misma validación leave-one-season-out y las mismas métricas que la regresión logística.

Hiperparámetros FIJADOS DE ANTEMANO (sin ajustar con la validación: hay solo ~15 fechas con huaico y ajustar sobreajustaría la validación):
  XGBoost : un solo modelo para los 4 horizontes (H como columna) con restricción monótona creciente en H (la probabilidad no baja al subir H).
            200 árboles, profundidad 3, tasa de aprendizaje 0.05, submuestreo 0.8, min_child_weight 20, L2 = 10, sin parada temprana.
            scale_pos_weight = sqrt(negativos / positivos) del entrenamiento de cada pliegue. NaN se dejan tal cual (XGBoost los maneja).
  Random Forest: un modelo por H. 200 árboles, hojas de al menos 100 filas, max_features = sqrt, cada árbol ve el 20 % de las filas (max_samples),
            class_weight = "balanced_subsample". NaN imputados con la mediana del entrenamiento.
Uso: python modelo/arboles.py xgb | rf
Salidas (prefijo xgb_ o rf_): _resumen_por_H.csv, _por_temporada.csv, _sensibilidad_N.csv, _importancias.csv, _pr.png
"""
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline

from comun import SALIDA
from metricas import N_PROPUESTO, metricas_por_temporada, resumen_y_sensibilidad
from tabla3 import FEATURES_V1, HORIZONTES, RUTA

SEMILLA = 0


def temporadas_con_evento(d):
    return [s for s in sorted(d.temporada.unique()) if d.loc[d.temporada == s, "y"].sum() > 0]


def xgb_loso(t):
    import xgboost as xgb

    cols = FEATURES_V1 + ["H"]
    mono = tuple(1 if c == "H" else 0 for c in cols)
    seasons = sorted({s for H in HORIZONTES for s in temporadas_con_evento(t[t.H == H])})
    t = t.reset_index(drop=True)
    p = np.full(len(t), np.nan, dtype="float64")
    imp = {}
    for s in seasons:
        te = (t.temporada == s).to_numpy()
        y_tr = t.y[~te]
        spw = float(np.sqrt((y_tr == 0).sum() / (y_tr == 1).sum()))
        m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, min_child_weight=20, reg_lambda=10.0,
                              scale_pos_weight=spw, monotone_constraints=mono, tree_method="hist", n_jobs=4, random_state=SEMILLA, verbosity=0)
        m.fit(t.loc[~te, cols], y_tr)
        p[te] = m.predict_proba(t.loc[te, cols])[:, 1]
        imp[s] = m.get_booster().get_score(importance_type="total_gain")
        print(f"  pliegue {s}: scale_pos_weight={spw:.1f}", flush=True)
    t["p"] = p
    res = {}
    for H in HORIZONTES:
        d = t[t.H == H]
        con = temporadas_con_evento(d)
        ev = d[d.temporada.isin(con)]
        n, pr = metricas_por_temporada(ev, con, H)
        res[H] = dict(n=n, pr=pr, con_evento=con)
    imp = pd.DataFrame(imp).reindex(cols).fillna(0)
    return res, (imp / imp.sum()).mean(axis=1)


def rf_loso(t):
    res, imp = {}, []
    for H in HORIZONTES:
        d = t[t.H == H].reset_index(drop=True)
        con = temporadas_con_evento(d)
        p = np.full(len(d), np.nan)
        for s in con:
            te = (d.temporada == s).to_numpy()
            m = make_pipeline(SimpleImputer(strategy="median"),
                              RandomForestClassifier(n_estimators=200, min_samples_leaf=100, max_features="sqrt", max_samples=0.2, class_weight="balanced_subsample",
                                                     n_jobs=4, random_state=SEMILLA))
            m.fit(d.loc[~te, FEATURES_V1], d.y[~te])
            p[te] = m.predict_proba(d.loc[te, FEATURES_V1])[:, 1]
            imp.append(pd.Series(m[-1].feature_importances_, index=FEATURES_V1))
            print(f"  H={H} pliegue {s} listo", flush=True)
        ev = d[d.temporada.isin(con)].assign(p=p[d.temporada.isin(con).to_numpy()])
        n, pr = metricas_por_temporada(ev, con, H)
        res[H] = dict(n=n, pr=pr, con_evento=con)
    return res, pd.concat(imp, axis=1).mean(axis=1)


def main(modelo):
    t0 = time.time()
    t = pd.read_parquet(RUTA)
    res, imp = {"xgb": xgb_loso, "rf": rf_loso}[modelo](t)
    print(f"{modelo}: LOSO terminado en {(time.time() - t0) / 60:.1f} min")
    pd.concat([r["n"] for r in res.values()], ignore_index=True).to_csv(SALIDA / f"{modelo}_por_temporada.csv", index=False)
    resumen, sens = resumen_y_sensibilidad(res)
    resumen.to_csv(SALIDA / f"{modelo}_resumen_por_H.csv", index=False)
    sens.to_csv(SALIDA / f"{modelo}_sensibilidad_N.csv", index=False)
    imp.sort_values(ascending=False).round(4).to_csv(SALIDA / f"{modelo}_importancias.csv", header=["importancia"])
    pd.set_option("display.width", 220)
    print(f"\nRESUMEN POR H (N={N_PROPUESTO})\n" + resumen.to_string(index=False))
    print("\nSENSIBILIDAD A N\n" + sens[["H", "N", "pct_detectados", "pct_aleatorio", "falsos_episodios_por_temporada"]].to_string(index=False))
    print("\nIMPORTANCIAS (solo descriptivas)\n" + imp.sort_values(ascending=False).round(3).to_string())
    fig, ejes = plt.subplots(1, 4, figsize=(13, 3.6), facecolor="#fcfcfb", sharey=True)
    for ax, (H, r) in zip(ejes, res.items()):
        y, p = r["pr"]
        pr_, rc_, _ = precision_recall_curve(y, p)
        ax.plot(rc_, pr_, color="#2a78d6", lw=2)
        ax.axhline(y.mean(), color="#52514e", ls="--", lw=1.2)
        ax.set_yscale("log"); ax.set_ylim(top=1)
        ax.set_title(f"H = {H} h  (AUPRC {average_precision_score(y, p):.3f})", loc="left", fontsize=10, color="#0b0b0b")
        ax.set_xlabel("exhaustividad (recall)", color="#52514e"); ax.set_facecolor("#fcfcfb"); ax.grid(color="#e4e3df", lw=.8)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    ejes[0].set_ylabel("precisión (escala log)", color="#52514e")
    fig.suptitle(f"{'XGBoost' if modelo == 'xgb' else 'Random Forest'}, LOSO: precisión–recall fuera de muestra (línea punteada = tasa de positivos)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); fig.savefig(SALIDA / f"{modelo}_pr.png", dpi=150)


if __name__ == "__main__":
    main(sys.argv[1])

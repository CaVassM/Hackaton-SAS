"""Paso 3: línea base de regresión logística con validación leave-one-season-out (LOSO).

  - Un modelo por horizonte H. Pipeline: imputar NaN con la mediana (del entrenamiento) -> estandarizar -> LogisticRegression(class_weight="balanced").
  - Variables: FEATURES_V1 de modelo/tabla3.py (lluvia + terreno; sin anomalia_14d).
  - LOSO: se evalúa solo en temporadas con al menos un evento (para ese H); en cada pliegue se entrena con TODAS las demás temporadas
    (incluidas las que no tienen eventos). La validación es por temporada, nunca por fila.
  - Alertas: en cada temporada evaluada se marca el top 1/N de los puntajes (presupuesto de 1 alerta por cada N horas de cada quebrada).
  - Bloque de huaico = racha de horas consecutivas con y=1 en una quebrada. Detectado = al menos una alerta dentro del bloque.
  - Falsa alarma: hora de alerta con y=0; episodio = alertas de una quebrada separadas por <= 6 h. Ojo: y=0 es "sin noticia", no un cero seguro.
Uso: python modelo/baseline_logistica.py [base|log1p]   (log1p: transformación logarítmica + C=0.1, fijados de antemano)
Salidas en modelo/salida/ (prefijo baseline_ o baseline_log1p_): baseline_resumen_por_H.csv, baseline_por_temporada.csv, baseline_sensibilidad_N.csv, baseline_coeficientes_H6.csv, baseline_pr.png
"""
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from comun import SALIDA
from metricas import N_LISTA, N_PROPUESTO, episodios_falsos, metricas_por_temporada, resumen_y_sensibilidad
from tabla3 import FEATURES_TERRENO, FEATURES_V1, HORIZONTES, RUTA, bloques

VARIANTES = {  # fijadas de antemano, sin ajustarlas con los resultados de la validación
    "base": dict(prefijo="baseline", C=1.0, log=False),
    "log1p": dict(prefijo="baseline_log1p", C=0.1, log=True),  # signo(x)*log(1+|x|) en las variables de lluvia (colas largas) y regularización L2 más fuerte
}
VARS_LLUVIA = [f for f in FEATURES_V1 if f not in FEATURES_TERRENO]


def modelo(C=1.0):
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(class_weight="balanced", C=C, max_iter=2000))


def evaluar(t, H, C=1.0):
    d = t[t.H == H].reset_index(drop=True)
    con_evento = [s for s in sorted(d.temporada.unique()) if d.loc[d.temporada == s, "y"].sum() > 0]
    p = np.full(len(d), np.nan)
    coefs = {}
    for s in con_evento:
        te = (d.temporada == s).to_numpy()
        m = modelo(C).fit(d.loc[~te, FEATURES_V1], d.y[~te])
        p[te] = m.predict_proba(d.loc[te, FEATURES_V1])[:, 1]
        coefs[s] = m[-1].coef_[0]
    ev = d[d.temporada.isin(con_evento)].copy()
    ev["p"] = p[ev.index]
    n, pr = metricas_por_temporada(ev, con_evento, H)
    return dict(H=H, ev=ev, n=n, pr=pr, coefs=pd.DataFrame(coefs, index=FEATURES_V1), con_evento=con_evento)


def main(variante="base"):
    cfg = VARIANTES[variante]
    pref = cfg["prefijo"]
    t0 = time.time()
    t = pd.read_parquet(RUTA)
    if cfg["log"]:  # transformación elemento a elemento (sin parámetros que ajustar): no hay fuga entre entrenamiento y prueba
        t[VARS_LLUVIA] = np.sign(t[VARS_LLUVIA]) * np.log1p(t[VARS_LLUVIA].abs())
    res = {H: evaluar(t, H, cfg["C"]) for H in HORIZONTES}
    print(f"Entrenamiento y evaluación LOSO terminados en {time.time() - t0:.0f} s")

    sens = pd.concat([r["n"] for r in res.values()], ignore_index=True)
    sens.to_csv(SALIDA / f"{pref}_por_temporada.csv", index=False)
    resumen, sens_N = resumen_y_sensibilidad(res)
    resumen.to_csv(SALIDA / f"{pref}_resumen_por_H.csv", index=False)
    sens_N.to_csv(SALIDA / f"{pref}_sensibilidad_N.csv", index=False)
    pd.set_option("display.width", 220)
    print(f"\nRESUMEN POR H (1 alerta cada N={N_PROPUESTO} horas por quebrada)\n" + resumen.to_string(index=False))
    print("\nSENSIBILIDAD A N\n" + sens_N[["H", "N", "pct_detectados", "pct_aleatorio", "falsos_episodios_por_temporada", "falsas_horas_por_temporada"]].to_string(index=False))
    h6 = res[6]["n"][res[6]["n"].N == N_PROPUESTO][["temporada", "bloques", "detectados", "AUPRC", "base", "falsos_episodios", "falsas_horas"]].round(4)
    print("\nPOR TEMPORADA (H=6, N=100)\n" + h6.to_string(index=False))
    co = res[6]["coefs"]
    co["media"], co["signos_iguales"] = co.mean(axis=1), (np.sign(co.iloc[:, :-1]).nunique(axis=1) == 1)
    co.round(3).to_csv(SALIDA / f"{pref}_coeficientes_H6.csv")
    print("\nCOEFICIENTES ESTANDARIZADOS (H=6, media de los pliegues)\n" + co[["media", "signos_iguales"]].round(3).to_string())

    fig, ejes = plt.subplots(1, 4, figsize=(13, 3.6), facecolor="#fcfcfb", sharey=True)
    for ax, (H, r) in zip(ejes, res.items()):
        y, p = r["pr"]
        pr_, rc_, _ = precision_recall_curve(y, p)
        ax.plot(rc_, pr_, color="#2a78d6", lw=2)
        ax.axhline(y.mean(), color="#52514e", ls="--", lw=1.2)
        ax.set_yscale("log"); ax.set_ylim(top=1)
        ax.set_title(f"H = {H} h  (AUPRC {average_precision_score(y, p):.3f})", loc="left", fontsize=10, color="#0b0b0b")
        ax.set_xlabel("exhaustividad (recall)", color="#52514e"); ax.set_facecolor("#fcfcfb"); ax.grid(color="#e4e3df", lw=.8)
        ax.annotate(f"base {y.mean():.4f}", (0.55, y.mean()), xytext=(0, 4), textcoords="offset points", fontsize=8, color="#52514e")
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    ejes[0].set_ylabel("precisión (escala log)", color="#52514e")
    fig.suptitle(f"Regresión logística ({variante}), LOSO: curvas precisión–recall (predicciones fuera de muestra) y línea base = tasa de positivos", x=0.01, ha="left", fontsize=11, color="#0b0b0b")
    fig.tight_layout(); fig.savefig(SALIDA / f"{pref}_pr.png", dpi=150)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "base")

"""Compara todos los modelos con las mismas métricas (N = 100 alertas por cada 100 h por quebrada, validación por temporada).
La referencia "lluvia_efectiva cruda" no es un modelo: es el valor de esa variable usado directamente como puntaje.
Salidas: modelo/salida/comparacion_modelos.csv y comparacion_modelos.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from comun import SALIDA
from metricas import N_PROPUESTO, metricas_por_temporada, resumen_y_sensibilidad
from tabla3 import HORIZONTES, RUTA

MODELOS = [("Regresión logística", "baseline"), ("Logística + log1p", "baseline_log1p"), ("XGBoost", "xgb"), ("Random Forest", "rf")]


def referencia_cruda(t, col="lluvia_efectiva"):
    res = {}
    for H in HORIZONTES:
        d = t[t.H == H]
        con = [s for s in sorted(d.temporada.unique()) if d.loc[d.temporada == s, "y"].sum() > 0]
        ev = d[d.temporada.isin(con)].copy()
        ev["p"] = ev[col].fillna(ev[col].min())
        n, pr = metricas_por_temporada(ev, con, H)
        res[H] = dict(n=n, pr=pr, con_evento=con)
    return resumen_y_sensibilidad(res)[0]


def main():
    filas = []
    for nombre, pref in MODELOS:
        r = pd.read_csv(SALIDA / f"{pref}_resumen_por_H.csv")
        filas.append(r.assign(modelo=nombre))
    filas.append(referencia_cruda(pd.read_parquet(RUTA)).assign(modelo="lluvia_efectiva cruda (sin modelo)"))
    c = pd.concat(filas, ignore_index=True)[["modelo", "H", "bloques", "detectados", "pct_detectados", "pct_aleatorio", "AUPRC_media_por_temporada", "base",
                                              "AUPRC", "veces_la_base", "falsos_episodios_por_temporada"]]
    c.to_csv(SALIDA / "comparacion_modelos.csv", index=False)
    pd.set_option("display.width", 220)
    v = c.pivot(index="modelo", columns="H", values="detectados").reindex([m for m, _ in MODELOS] + ["lluvia_efectiva cruda (sin modelo)"])
    b = c[c.modelo == "XGBoost"].set_index("H").bloques
    print(f"BLOQUES DETECTADOS (alerta en 1 de cada {N_PROPUESTO} horas), de {dict(b)}\n" + v.to_string())
    print("\nAUPRC MEDIO POR TEMPORADA (base entre paréntesis en la última fila)\n" + c.pivot(index="modelo", columns="H", values="AUPRC_media_por_temporada").reindex(v.index).round(4).to_string())
    print("\nBase (tasa de positivos):", c[c.modelo == "XGBoost"].set_index("H").base.to_dict())

    colores = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
    fig, ax = plt.subplots(figsize=(10, 4.4), facecolor="#fcfcfb"); ax.set_facecolor("#fcfcfb")
    ancho = 0.16
    for i, m in enumerate(v.index):
        pct = [c[(c.modelo == m) & (c.H == H)].pct_detectados.iloc[0] for H in HORIZONTES]
        xs = np.arange(len(HORIZONTES)) + (i - 2) * ancho
        ax.bar(xs, pct, ancho * .9, color=colores[i], label=m)
        for x, p_ in zip(xs, pct):
            ax.text(x, p_ + .4, f"{p_:.0f}", ha="center", fontsize=8, color="#0b0b0b")
    alea = [c[(c.modelo == "XGBoost") & (c.H == H)].pct_aleatorio.iloc[0] for H in HORIZONTES]
    ax.scatter(np.arange(len(HORIZONTES)), alea, marker="_", s=900, color="#0b0b0b", zorder=3, label="al azar (esperado)")
    ax.set_xticks(range(len(HORIZONTES)), [f"H = {H} h" for H in HORIZONTES], color="#0b0b0b")
    ax.set_ylabel("% de huaicos con al menos una alerta antes", color="#52514e")
    ax.set_title("Con 1 alerta cada 100 horas por quebrada: ningún modelo supera con claridad al azar", loc="left", fontsize=11, color="#0b0b0b")
    ax.grid(axis="y", color="#e4e3df", lw=.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    ax.set_ylim(0, 30)
    fig.tight_layout(); fig.savefig(SALIDA / "comparacion_modelos.png", dpi=150)


if __name__ == "__main__":
    main()

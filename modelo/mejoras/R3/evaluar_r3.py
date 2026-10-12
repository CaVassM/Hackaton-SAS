"""R3: evaluación de las variantes de escala (pieza 1) con métrica PRINCIPAL = umbral sin información de la prueba.

Dos umbrales, ambos sin etiquetas de la prueba:
  - FIJO: cuantil 1-1/N de los puntajes fuera de muestra de las 12 temporadas juntas (como R1; usa la distribución de puntajes de todas, no etiquetas).
  - ENTRENAMIENTO: por pliegue, cuantil 1-1/N de los puntajes del modelo en sus propias horas de entrenamiento (escala.py). Es el operativo honesto.
Corte dentro de la temporada: solo secundario (usa información del futuro).
Niveles: zona (pieza 1 sola: horas de alerta por temporada, tormentas detectadas) y quebrada (riesgo P1 x P2: bloques detectados de 204, N = 100).
Azar con el mismo reparto de alertas por temporada: esperanza hipergeométrica (dos_piezas/evaluar.py).
Salidas en modelo/mejoras/R3/: r3_resumen.csv, r3_por_temporada.csv, r3.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1] / "dos_piezas"))
from base import HORIZONTES, SALIDA, tormenta_de_hora, tormentas  # noqa: E402
from evaluar import esperado_azar  # noqa: E402
from oof import RUTA_OOF_TODAS  # noqa: E402
from tabla3 import bloques  # noqa: E402

SEMILLAS = (0, 1, 2)
N = 100
ORDEN = ["V0", "A_reemplazo", "A_agregado", "B", "AB"]


def alertas(p, temp, fold, tau_fold, modo):
    if modo == "fijo":
        return p >= np.quantile(p, 1 - 1 / N)
    if modo == "entrenamiento":
        return p >= np.array([tau_fold[f] for f in fold])
    a = np.zeros(len(p), bool)
    for t in np.unique(temp):
        m = temp == t
        a[m] = p[m] >= np.quantile(p[m], 1 - 1 / N)
    return a


def contar(grupo, a, temp):
    g = pd.DataFrame({"g": grupo, "a": a, "t": temp}).dropna(subset=["g"])
    det = g.groupby("g").a.max()
    n_s = pd.Series(temp).value_counts().to_dict()
    k_s = pd.Series(temp[a]).value_counts().to_dict()
    largos = [(r.t, r.L) for r in g.groupby("g").agg(t=("t", "first"), L=("a", "size")).itertuples()]
    return int(det.sum()), len(det), esperado_azar(largos, n_s, k_s), g.assign(det=g.g.map(det)).groupby("t").g.nunique(), g[g.g.map(det)].groupby("t").g.nunique()


def main():
    pd.set_option("display.width", 250)
    torm = tormentas()
    q0 = pd.read_parquet(RUTA_OOF_TODAS)[["hora", "quebrada_id", "H", "y", "temporada"]]
    P2 = pd.read_csv(SALIDA / "p2_por_pliegue.csv")
    res, por_temp = [], []
    for v in [x for x in ORDEN if (AQUI / f"oof_{x}.parquet").exists()]:
        o = pd.read_parquet(AQUI / f"oof_{v}.parquet")
        U = pd.read_csv(AQUI / f"umbrales_entrenamiento_{v}.csv")
        U = U[U.N == N]
        for esq, clave in (("losto", "pliegue_losto"), ("loso", "temporada")):
            p2 = P2[P2.esquema == esq].rename(columns={"pliegue": clave})[[clave, "quebrada_id", "mezcla"]]
            for s in SEMILLAS:
                col = f"p_xgb{s}_{esq}"
                q = q0.merge(o[["hora", "H", "pliegue_losto", col]], on=["hora", "H"]).merge(p2, on=[clave, "quebrada_id"])
                q["r"] = q[col] * q.mezcla
                for H in HORIZONTES:
                    u = U[(U.esquema == esq) & (U.semilla == s) & (U.H == H)].set_index("pliegue")
                    # --- zona
                    d = o[(o.H == H) & o.y.notna()].reset_index(drop=True)
                    pos = (d.y == 1).to_numpy()
                    tor = np.full(len(d), np.nan, dtype=object)
                    tor[pos] = tormenta_de_hora(d.hora[pos], torm)
                    # --- quebrada
                    e = q[q.H == H].reset_index(drop=True)
                    b = bloques(e)
                    gb = np.full(len(e), np.nan)
                    gb[b.index.to_numpy()] = b.bloque.to_numpy()
                    for modo in ("fijo", "entrenamiento", "temporada"):
                        az = alertas(d[col].to_numpy(), d.temporada.to_numpy(), d[clave].to_numpy(), u.tau.to_dict(), modo)
                        t_det, t_tot, t_az, _, _ = contar(tor, az, d.temporada.to_numpy())
                        aq = alertas(e.r.to_numpy(), e.temporada.to_numpy(), e[clave].to_numpy(), u.tau_riesgo.to_dict(), modo)
                        b_det, b_tot, b_az, b_tot_t, b_det_t = contar(gb, aq, e.temporada.to_numpy())
                        horas = pd.Series(az).groupby(d.temporada.to_numpy()).sum()
                        res.append(dict(variante=v, esquema=esq, semilla=s, H=H, umbral=modo, horas_alerta_zona=int(az.sum()),
                                        pct_horas_2024_25=round(100 * horas.get("2024-25", 0) / max(az.sum(), 1)), tormentas=t_det, tormentas_azar=t_az,
                                        bloques=b_det, bloques_azar=b_az, bloques_total=b_tot, filas_alerta_quebrada=int(aq.sum())))
                        if s == 0 and H == 6 and modo != "temporada":
                            for t in sorted(d.temporada.unique()):
                                por_temp.append(dict(variante=v, esquema=esq, umbral=modo, temporada=t, horas_alerta_zona_H6=int(horas.get(t, 0)),
                                                     bloques_H6=int(b_tot_t.get(t, 0)), detectados_H6=int(b_det_t.get(t, 0))))
        print(f"{v} evaluada", flush=True)
    r = pd.DataFrame(res)
    r.to_csv(AQUI / "r3_detalle.csv", index=False)
    pt = pd.DataFrame(por_temp)
    pt.to_csv(AQUI / "r3_por_temporada.csv", index=False)
    # resumen: suma sobre H, media (y rango) de 3 semillas
    g = r.groupby(["variante", "esquema", "umbral", "semilla"]).agg(bloques=("bloques", "sum"), azar=("bloques_azar", "sum"), tormentas=("tormentas", "sum"),
                                                                     tormentas_azar=("tormentas_azar", "sum"), pct_2024_25=("pct_horas_2024_25", "mean"),
                                                                     filas_alerta=("filas_alerta_quebrada", "sum")).reset_index()
    s = g.groupby(["variante", "esquema", "umbral"]).agg(bloques_media=("bloques", "mean"), bloques_min=("bloques", "min"), bloques_max=("bloques", "max"),
                                                         azar=("azar", "mean"), tormentas_media=("tormentas", "mean"), tormentas_azar=("tormentas_azar", "mean"),
                                                         pct_horas_2024_25=("pct_2024_25", "mean"),
                                                         alertas_vs_1_100=("filas_alerta", "mean")).round(1).reset_index()
    s["veces_azar"] = (s.bloques_media / s.azar).round(2)   # el umbral de ENTRENAMIENTO no emite exactamente 1/100 a nivel quebrada: comparar con esto
    s["alertas_vs_1_100"] = (s.alertas_vs_1_100 / 28666).round(2)   # filas de alerta / (filas evaluadas / 100), 4 H
    s.to_csv(AQUI / "r3_resumen.csv", index=False)
    print("\nRESUMEN (N=100; bloques por quebrada sumados en H=3/6/12/24, de 204; tormentas de zona sumadas en los 4 H, de 36; media de 3 semillas)")
    print(s.to_string(index=False))
    porH = r[r.umbral != "temporada"].groupby(["variante", "esquema", "umbral", "H"]).bloques.mean().unstack("H").round(1)
    print("\nBloques por H (media 3 semillas)\n" + porH.to_string())
    print("\nPor temporada (H=6, semilla 0, LOSTO): horas de alerta de zona / detectados de bloques")
    x = pt[pt.esquema == "losto"]
    print(x.pivot_table(index="temporada", columns=["umbral", "variante"], values=["horas_alerta_zona_H6", "detectados_H6"]).to_string())
    figura(pt, s)


def figura(pt, s):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vs = [v for v in ORDEN if v in set(pt.variante)]
    colores = dict(zip(ORDEN, ["#eb6834", "#2a78d6", "#1baf7a", "#eda100", "#e87ba4"]))
    fig, ejes = plt.subplots(1, 2, figsize=(12.5, 4.6), facecolor="#fcfcfb", gridspec_kw=dict(width_ratios=[1.5, 1]))
    ax = ejes[0]
    x = pt[(pt.esquema == "losto") & (pt.umbral == "entrenamiento")]
    temps = sorted(x.temporada.unique())
    w = 0.8 / len(vs)
    for i, v in enumerate(vs):
        y = x[x.variante == v].set_index("temporada").reindex(temps).horas_alerta_zona_H6
        ax.bar(np.arange(len(temps)) + (i - (len(vs) - 1) / 2) * w, y, w - 0.02, color=colores[v], label=v)
    ax.set_xticks(np.arange(len(temps)), [t[2:] for t in temps], fontsize=8.5)
    ax.set_title("A. Horas de alerta de zona por temporada (H=6, 1/100, umbral de entrenamiento, LOSTO)", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8.5)
    ax = ejes[1]
    z = s[(s.esquema == "losto") & (s.umbral != "temporada")]
    for j, um in enumerate(("fijo", "entrenamiento")):
        for i, v in enumerate(vs):
            r = z[(z.variante == v) & (z.umbral == um)].iloc[0]
            xx = j + (i - (len(vs) - 1) / 2) * w
            ax.bar(xx, r.bloques_media, w - 0.02, color=colores[v])
            ax.plot([xx, xx], [r.bloques_min, r.bloques_max], color="#52514e", lw=1.2)
            ax.scatter([xx], [r.azar], marker="_", s=120, color="#0b0b0b", linewidths=2, zorder=3)
            ax.text(xx, r.bloques_max + 0.8, f"{r.bloques_media:.0f}", ha="center", fontsize=8, color="#52514e")
    ax.set_xticks([0, 1], ["umbral fijo", "umbral de entrenamiento"])
    ax.set_title("B. Bloques detectados por quebrada (de 204; raya = azar)", loc="left", fontsize=10)
    for a in ejes:
        a.set_facecolor("#fcfcfb")
        a.grid(axis="y", color="#e4e3df", lw=0.8)
        a.set_axisbelow(True)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(AQUI / "r3.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()

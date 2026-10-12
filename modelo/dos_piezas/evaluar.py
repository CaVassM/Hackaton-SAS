"""Evaluación del modelo en dos piezas (fase R1), todo fuera de muestra. Requiere pieza1.py, pieza2.py y modelo/oof.py (oof_restringido_todas).

  1. Pieza 1 sola (zona): AUPRC frente a la tasa base; tormentas y bloques de zona detectados con 1 alerta cada 100 h (y 1/50 h).
  3. Riesgo final por quebrada = P1 x P2 (mezcla): bloques detectados con 1 alerta cada 100 h por quebrada (y 1/50), frente al modelo actual
     (XGBoost restringido por quebrada, LOSO, semilla 0) y al azar. Diagnóstico: "solo P1" (todas las quebradas con el mismo puntaje).
  4. Tabla resumen por H.
Cortes de alerta: (A) UMBRAL FIJO = cuantil 1-1/N sobre las 12 temporadas (operativo; sin etiquetas);
                  (B) corte DENTRO de cada temporada con eventos (como el "19 %" del modelo actual; exige conocer la temporada).
Azar: mismas horas de alerta por temporada que el modelo, repartidas al azar dentro de la temporada; esperanza exacta (hipergeométrica):
      P(un bloque de L filas no recibe alerta) = prod_{i<L} (n_s - k_s - i) / (n_s - i).
Salidas en modelo/dos_piezas/salida/: pieza1_zona.csv, riesgo_por_H.csv, resumen_R1.csv, resumen_R1.png
"""
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from base import HORIZONTES, SALIDA, tormenta_de_hora, tormentas
from pieza1 import RUTA_OOF, SEMILLAS

sys.path.insert(0, str(SALIDA.parent.parent))
from oof import RUTA_OOF_TODAS  # noqa: E402
from tabla3 import bloques  # noqa: E402

NS = (100, 50)
PRINCIPAL_P2 = "mezcla"


def esperado_azar(largos_por_temp, n_s, k_s):
    """largos_por_temp: lista de (temporada, L). Esperanza de bloques con al menos una alerta al azar."""
    tot = 0.0
    for s, L in largos_por_temp:
        n, k = n_s[s], k_s.get(s, 0)
        i = np.arange(L)
        tot += 1 - np.prod(np.clip((n - k - i) / (n - i), 0, 1))
    return tot


def detectar(d, score, grupo, N, corte):
    """d: filas etiquetadas de un H (temporada, y). grupo: id de bloque/tormenta por fila (NaN fuera de positivos).
    Devuelve (detectados, total, azar esperado)."""
    s = d[score].to_numpy()
    temp = d.temporada.to_numpy()
    if corte == "fijo":
        alerta = s >= np.quantile(s, 1 - 1 / N)
    else:  # dentro de cada temporada
        alerta = np.zeros(len(d), bool)
        for t in np.unique(temp):
            m = temp == t
            alerta[m] = s[m] >= np.quantile(s[m], 1 - 1 / N)
    g = pd.DataFrame({"g": grupo, "a": alerta, "temp": temp}).dropna(subset=["g"])
    det = g.groupby("g").a.max()
    n_s = pd.Series(temp).value_counts().to_dict()
    k_s = pd.Series(temp[alerta]).value_counts().to_dict()
    largos = [(r.temp, r.L) for r in g.groupby("g").agg(temp=("temp", "first"), L=("a", "size")).itertuples()]
    if corte == "temporada":   # solo cuentan las temporadas con eventos (en las otras no hay nada que detectar)
        pass
    return int(det.sum()), len(det), esperado_azar(largos, n_s, k_s)


def lift_medio(d, score):
    v = [average_precision_score(g.y, g[score]) / g.y.mean() for _, g in d.groupby("temporada") if g.y.sum() > 0]
    return float(np.mean(v))


# --------------------------------------------------------------------------- 1. pieza 1 sola
def eval_zona(o, torm):
    filas = []
    for H in HORIZONTES:
        d = o[(o.H == H) & o.y.notna()].reset_index(drop=True)
        pos = (d.y == 1).to_numpy()
        tor = np.full(len(d), np.nan, dtype=object)
        tor[pos] = tormenta_de_hora(d.hora[pos], torm)
        nb = (d.hora.diff() != pd.Timedelta(hours=1)) | ~pd.Series(pos).shift(fill_value=False)   # bloques de zona: rachas de horas y=1
        blq = np.where(pos, nb.cumsum().to_numpy(), np.nan)
        for col in [c for c in o.columns if c.startswith("p_")]:
            modelo, esquema = col[2:].rsplit("_", 1)
            fila = dict(H=H, modelo=modelo, esquema=esquema, positivos=int(pos.sum()), AUPRC=average_precision_score(d.y, d[col]), base=d.y.mean(),
                        lift_medio_temporadas=lift_medio(d, col))
            for N in NS:
                for corte in ("fijo", "temporada"):
                    dd = d if corte == "fijo" else d[d.temporada.isin(d.temporada[pos].unique())]
                    sel = dd.index.to_numpy()
                    t_det, t_tot, t_az = detectar(dd, col, tor[sel], N, corte)
                    b_det, b_tot, b_az = detectar(dd, col, blq[sel], N, corte)
                    fila |= {f"tormentas_{corte}_N{N}": t_det, f"tormentas_azar_{corte}_N{N}": round(t_az, 1),
                             f"bloques_{corte}_N{N}": b_det, f"bloques_azar_{corte}_N{N}": round(b_az, 1)}
            fila["tormentas_total"], fila["bloques_zona_total"] = t_tot, b_tot
            filas.append(fila)
    r = pd.DataFrame(filas)
    r["veces_la_base"] = r.AUPRC / r.base
    return r


# --------------------------------------------------------------------------- 3. riesgo por quebrada
def tabla_riesgo(o, torm):
    q = pd.read_parquet(RUTA_OOF_TODAS)[["hora", "quebrada_id", "H", "y", "temporada", "p"]].rename(columns={"p": "p_actual"})
    P = pd.read_csv(SALIDA / "p2_por_pliegue.csv")
    q = q.merge(o.drop(columns=["y", "temporada", "n_y1"]), on=["hora", "H"], how="left")
    assert q.filter(like="p_").notna().all().all(), "faltan predicciones de la pieza 1 para alguna fila"
    for esquema, clave in (("losto", "pliegue_losto"), ("loso", "temporada")):
        p2 = P[P.esquema == esquema].rename(columns={"pliegue": clave})[[clave, "quebrada_id", PRINCIPAL_P2]].rename(columns={PRINCIPAL_P2: f"p2_{esquema}"})
        q = q.merge(p2, on=[clave, "quebrada_id"], how="left")
        assert q[f"p2_{esquema}"].notna().all()
        for col in [c for c in o.columns if c.startswith("p_") and c.endswith(esquema)]:
            q[f"r_{col[2:]}"] = q[col] * q[f"p2_{esquema}"]
    return q


def eval_riesgo(q):
    filas = []
    puntajes = {"actual": "p_actual"} | {c[2:]: c for c in q.columns if c.startswith("r_")} | {"soloP1_" + c[2:]: c for c in q.columns if c.startswith("p_") and c != "p_actual"}
    for H in HORIZONTES:
        d = q[q.H == H].reset_index(drop=True)
        b = bloques(d)
        grupo = np.full(len(d), np.nan)
        grupo[b.index.to_numpy()] = b.bloque.to_numpy()
        con = d.temporada[d.y == 1].unique()
        for nombre, col in puntajes.items():
            fila = dict(H=H, puntaje=nombre, bloques_total=int(b.bloque.nunique()), lift_medio_temporadas=lift_medio(d, col))
            for N in NS:
                for corte in ("fijo", "temporada"):
                    dd = d if corte == "fijo" else d[d.temporada.isin(con)]
                    det, tot, az = detectar(dd, col, grupo[dd.index.to_numpy()], N, corte)
                    fila |= {f"det_{corte}_N{N}": det, f"azar_{corte}_N{N}": round(az, 1)}
            filas.append(fila)
    return pd.DataFrame(filas)


def figura(rr):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = [("actual", "Modelo actual (por quebrada, LOSO)", "#eb6834"), ("xgb0_loso", "Dos piezas (LOSO)", "#2a78d6"), ("xgb0_losto", "Dos piezas (LOSTO)", "#1baf7a")]
    fig, ejes = plt.subplots(1, 2, figsize=(12, 4.6), facecolor="#fcfcfb", sharey=True)
    x = np.arange(len(HORIZONTES))
    w = 0.26
    titulos = {"fijo": "A. Umbral FIJO en las 12 temporadas (operativo)", "temporada": "B. Corte DENTRO de cada temporada (exige conocerla)"}
    for ax, corte in zip(ejes, ("fijo", "temporada")):
        ax.set_facecolor("#fcfcfb")
        for i, (k, et, c) in enumerate(series):
            r = rr[rr.puntaje == k].set_index("H").loc[list(HORIZONTES)]
            pct = 100 * r[f"det_{corte}_N100"] / r.bloques_total
            az = 100 * r[f"azar_{corte}_N100"] / r.bloques_total
            ax.bar(x + (i - 1) * w, pct, w - 0.02, color=c, label=et)
            ax.scatter(x + (i - 1) * w, az, marker="_", s=220, color="#0b0b0b", linewidths=2, zorder=3, label="azar (mismo reparto de alertas)" if i == 0 else None)
            for xi, v, n in zip(x + (i - 1) * w, pct, r[f"det_{corte}_N100"]):
                ax.text(xi, v + 0.6, f"{int(n)}", ha="center", fontsize=8, color="#52514e")
        ax.set_xticks(x, [f"H = {h} h" for h in HORIZONTES])
        ax.set_title(titulos[corte], loc="left", fontsize=10.5, color="#0b0b0b")
        ax.grid(axis="y", color="#e4e3df", lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    ejes[0].set_ylabel("% de huaicos (bloques) detectados", color="#52514e")
    h, et = ejes[1].get_legend_handles_labels()
    fig.legend(h[1:] + h[:1], et[1:] + et[:1], frameon=False, fontsize=9, loc="lower center", ncol=4)
    fig.suptitle("1 alerta cada 100 h por quebrada (número = bloques detectados; de 53 / 51 / 50 / 50)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(SALIDA / "resumen_R1.png", dpi=150)
    plt.close(fig)


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    torm = tormentas()
    o = pd.read_parquet(RUTA_OOF)
    rz = eval_zona(o, torm)
    rz.to_csv(SALIDA / "pieza1_zona.csv", index=False)
    print("1. PIEZA 1 SOLA (zona). Umbral FIJO; azar = mismo reparto de alertas por temporada")
    cols = ["H", "modelo", "esquema", "positivos", "veces_la_base", "lift_medio_temporadas", "tormentas_total", "tormentas_fijo_N100", "tormentas_azar_fijo_N100",
            "tormentas_fijo_N50", "tormentas_azar_fijo_N50", "bloques_zona_total", "bloques_fijo_N100", "bloques_azar_fijo_N100"]
    print(rz[cols].round(2).to_string(index=False))
    print("\n   Corte DENTRO de la temporada:")
    print(rz[["H", "modelo", "esquema", "tormentas_temporada_N100", "tormentas_azar_temporada_N100", "tormentas_temporada_N50", "tormentas_azar_temporada_N50"]].to_string(index=False))

    q = tabla_riesgo(o, torm)
    rr = eval_riesgo(q)
    rr.to_csv(SALIDA / "riesgo_por_H.csv", index=False)
    print("\n3. RIESGO POR QUEBRADA (bloques detectados; azar con el mismo reparto)")
    print(rr.round(2).to_string(index=False))

    # 4. tabla resumen: actual vs dos piezas (semilla 0 y media de 3 semillas), por H
    filas = []
    for H in HORIZONTES:
        r = rr[rr.H == H].set_index("puntaje")
        fila = {"H": H, "bloques": int(r.bloques_total.iloc[0])}
        for corte in ("fijo", "temporada"):
            fila[f"actual_{corte}"] = f"{r.loc['actual', f'det_{corte}_N100']} (azar {r.loc['actual', f'azar_{corte}_N100']:.1f})"
            for esq in ("loso", "losto"):
                v = [r.loc[f"xgb{s}_{esq}", f"det_{corte}_N100"] for s in SEMILLAS]
                a = r.loc[f"xgb0_{esq}", f"azar_{corte}_N100"]
                fila[f"dos_piezas_{esq}_{corte}"] = f"{v[0]} [{min(v)}-{max(v)}] (azar {a:.1f})"
        fila["lift_actual"] = round(r.loc["actual", "lift_medio_temporadas"], 1)
        fila["lift_dos_piezas_loso"] = round(r.loc["xgb0_loso", "lift_medio_temporadas"], 1)
        filas.append(fila)
    res = pd.DataFrame(filas)
    res.to_csv(SALIDA / "resumen_R1.csv", index=False)
    print("\n4. RESUMEN (N=100; semilla 0 [rango 3 semillas]; azar con el mismo reparto)\n" + res.to_string(index=False))
    figura(rr)


if __name__ == "__main__":
    main()

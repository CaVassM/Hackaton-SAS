"""Probabilidad calibrada por quebrada: calibración de Platt de P1 por horizonte + P2. El modelo v3 NO cambia (P1, P2 y umbrales iguales).

  P(quebrada q se activa en (t, t+H]) = p_cal(t, H) * kappa_H * P2(q)
    p_cal(t, H) = sigmoid(a_H + b_H * logit(p_zona(t, H)))       P(huaico en alguna de las 17 quebradas en (t, t+H]), calibrada
    kappa_H     = n_medio_H / suma_q P2(q)                         n_medio_H = promedio de quebradas activadas en las ventanas con huaico
Supuestos:
  - Platt corrige el PESO de los positivos (scale_pos_weight = raíz(neg/pos) infla p_zona) con 2 parámetros por H; no cambia el orden.
  - kappa lleva P2 (probabilidad de activarse en una TORMENTA, k = 4) a la VENTANA (t, t+H]: suma_q kappa P2(q) = quebradas esperadas dado un huaico en la zona.
  - Dado un huaico en la zona, QUÉ quebradas se activan no depende de la lluvia de la hora (solo de P2): las dos piezas se multiplican.
Ajuste: predicciones FUERA DE MUESTRA de P1 (modelo/v3/_cache/oof_b1.parquet, B1_estado_5d) y etiqueta de zona v2 (filas con etiqueta, dic-abr);
  LogisticRegression(C = 1e6) sobre logit(p_zona) recortado a [1e-6, 1 - 1e-6].
Modelo final (p1_b1.json): puntúa en otra escala que los modelos LOSO (igual que para los umbrales), así que antes de Platt su p_zona se traslada a la
  escala LOSO POR CUANTIL (misma fracción de horas por debajo; rejilla en calibracion_escala_final.csv). Para un modelo de pliegue (la demo fuera de
  muestra) no hace falta: su p_zona ya está en la escala LOSO.
Orden en H: Platt y kappa se ajustan por separado en cada H; para que p(3 h) <= p(6 h) <= p(12 h) <= p(24 h) se toma el máximo acumulado en H.
Validación: calibrador ajustado SIN la temporada s y aplicado a s (por cuantiles de p_zona y suma de p_cal vs. positivos), y por quebrada
  (suma de p_cal * kappa * P2(q) vs. horas con y_q = 1).
Salidas: calibracion.json, calibracion_escala_final.csv, calibracion_validacion.csv, calibracion_por_quebrada.csv
Uso: python modelo/v3/final/calibracion.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import modelo_final as mf  # noqa: E402
from modelo_final import HS, base  # noqa: E402
from comun_v3 import CACHE  # noqa: E402  (modelo_final pone modelo/v3 en sys.path)

EPS = 1e-6
CORTES = (0.50, 0.80, 0.90, 0.95, 0.99)
N_ESCALA = 2001  # puntos de la rejilla de cuantiles para trasladar el modelo final a la escala LOSO


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def datos():
    """Filas de zona con etiqueta (dic-abr): hora, H, y, n_y1 (quebradas con y = 1), temporada, p (OOF de P1) y las variables de P1."""
    z = mf.tabla_zona()
    ez = base.etiquetas_zona()
    o = pd.read_parquet(CACHE / "oof_b1.parquet")
    assert (z.hora.values == ez.hora.values).all() and (z.H.values == ez.H.values).all()
    assert (z.hora.values == o.hora.values).all() and (z.H.values == o.H.values).all()
    z["n_y1"], z["p"] = ez.n_y1.to_numpy(), o.B1_estado_5d.to_numpy()
    return z[z.y.notna()].reset_index(drop=True)


def ajustar(d, p2, excluir=None):
    """Por H: a, b (Platt), kappa, tasa base (media de y) y conteos; sin la temporada `excluir` si se indica (p2 debe ser el de ese mismo pliegue)."""
    if excluir:
        d = d[d.temporada != excluir]
    out = {}
    for H in HS:
        g = d[d.H == H]
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit(g.p)[:, None], g.y.to_numpy())
        n_medio = float(g.loc[g.y == 1, "n_y1"].mean())
        out[H] = dict(a=float(lr.intercept_[0]), b=float(lr.coef_[0, 0]), kappa=n_medio / float(p2.sum()), tasa_base=float(g.y.mean()),
                      n_quebradas_medio=n_medio, suma_p2=float(p2.sum()), filas=len(g), positivos=int(g.y.sum()))
    return out


def p_calibrada(cal, pz):
    """pz: {H: p_zona en la escala LOSO} -> {H: p_cal}, con máximo acumulado en H (p(3 h) <= ... <= p(24 h))."""
    pc = np.maximum.accumulate(np.vstack([sigmoid(cal[H]["a"] + cal[H]["b"] * logit(pz[H])) for H in HS]), axis=0)
    return {H: pc[i] for i, H in enumerate(HS)}


def p_zona_kappa(cal, pc):
    """{H: p_cal} -> {H: p_cal * kappa_H} con máximo acumulado en H. La probabilidad de la quebrada q es este valor * P2(q)."""
    zk = np.maximum.accumulate(np.vstack([pc[H] * cal[H]["kappa"] for H in HS]), axis=0)
    return {H: zk[i] for i, H in enumerate(HS)}


def escala_final(m, z_todas):
    """Rejilla de cuantiles por H: p_zona del modelo final (filas con etiqueta) -> p_zona OOF (misma fracción de horas)."""
    q = np.linspace(0, 1, N_ESCALA)
    filas = []
    for H in HS:
        g = z_todas[z_todas.H == H]
        s_fin = m.predict_proba(g[mf.VARIABLES])[:, 1]
        filas.append(pd.DataFrame({"H": H, "cuantil": q, "p_final": np.quantile(s_fin, q), "p_loso": np.quantile(g.p, q)}))
    return pd.concat(filas, ignore_index=True)


def a_escala_loso(esc, pz_final):
    """{H: p_zona del modelo final} -> {H: p_zona equivalente en la escala LOSO} (interpolación en la rejilla de cuantiles)."""
    out = {}
    for H in HS:
        g = esc[esc.H == H]
        x, i = np.unique(g.p_final.to_numpy(), return_index=True)
        out[H] = np.interp(pz_final[H], x, g.p_loso.to_numpy()[i])
    return out


def validar(d, p2):
    """Calibrador sin la temporada s aplicado a s. Por H: tramos de p_zona (cortes por cuantil de toda la serie) y suma de p_cal vs. positivos."""
    d = d.copy()
    d["p_cal"] = np.nan
    for s in sorted(d.temporada.unique()):
        cal = ajustar(d, p2, excluir=s)
        for H in HS:
            m = ((d.temporada == s) & (d.H == H)).to_numpy()
            d.loc[m, "p_cal"] = sigmoid(cal[H]["a"] + cal[H]["b"] * logit(d.p[m]))
    filas = []
    for H in HS:
        g = d[d.H == H]
        cortes = np.quantile(g.p, CORTES)
        tramo = np.searchsorted(cortes, g.p, side="right")
        nombres = [f"{int(100 * a)}-{int(100 * b)} %" for a, b in zip((0,) + CORTES, CORTES + (1,))]
        for k, nombre in enumerate(nombres):
            t = g[tramo == k]
            filas.append(dict(H=H, tramo_p_zona=nombre, horas=len(t), positivos=int(t.y.sum()), p_zona_media=round(float(t.p.mean()), 5),
                              p_cal_media=round(float(t.p_cal.mean()), 5), frecuencia_observada=round(float(t.y.mean()), 5)))
        filas.append(dict(H=H, tramo_p_zona="total", horas=len(g), positivos=int(g.y.sum()), p_zona_media=round(float(g.p.mean()), 5),
                          p_cal_media=round(float(g.p_cal.mean()), 5), frecuencia_observada=round(float(g.y.mean()), 5),
                          suma_p_cal=round(float(g.p_cal.sum()), 1)))
    return pd.DataFrame(filas), d


def por_quebrada(dv, cal, p2, hs=(3, 24)):
    """Suma en las horas con etiqueta de zona de p_cal (validación cruzada) * kappa_H * P2(q) vs. horas con y_q = 1 (etiquetas v2)."""
    filas = []
    for H in hs:
        g = dv[dv.H == H].set_index("hora")
        e = base.cargar_etiquetas(H)
        e = e[e.hora.dt.month.isin([12, 1, 2, 3, 4])]
        e, _ = base.poner_nan_dias_fuera_del_piloto(e)
        e = e[e.hora.isin(g.index)]
        for q in p2.index:
            filas.append(dict(H=H, quebrada_id=q, P2=round(float(p2[q]), 4),
                              esperado=round(float(g.p_cal.sum() * cal[H]["kappa"] * p2[q]), 1),
                              observado=int((e[e.quebrada_id == q].y == 1).sum())))
    T = pd.DataFrame(filas)
    tot = T.groupby("H")[["esperado", "observado"]].sum().reset_index().assign(quebrada_id="TOTAL")
    return pd.concat([T, tot], ignore_index=True)


def main():
    pd.set_option("display.width", 200)
    d = datos()
    p2 = pd.read_csv(AQUI / "p2_final.csv", index_col=0).iloc[:, 0]
    cal = ajustar(d, p2)
    m = xgb.XGBClassifier()
    m.load_model(AQUI / "p1_b1.json")
    esc = escala_final(m, d)
    esc.to_csv(AQUI / "calibracion_escala_final.csv", index=False)
    meta = dict(formula="P(q, t, H) = p_cal(t, H) * kappa_H * P2(q); p_cal = sigmoid(a_H + b_H * logit(p_zona)); kappa_H = n_quebradas_medio_H / suma(P2)",
                ajuste="Platt con LogisticRegression(C=1e6) sobre logit(p_zona OOF) recortado a [1e-6, 1-1e-6]; filas de zona con etiqueta v2, dic-abr",
                modelo_final="p_zona de p1_b1.json se traslada antes a la escala LOSO por cuantil (calibracion_escala_final.csv)",
                orden_en_H="máximo acumulado en H de p_cal y de p_cal * kappa_H",
                por_H={int(H): v for H, v in cal.items()})
    (AQUI / "calibracion.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    V, dv = validar(d, p2)
    V.to_csv(AQUI / "calibracion_validacion.csv", index=False)
    Q = por_quebrada(dv, cal, p2)
    Q.to_csv(AQUI / "calibracion_por_quebrada.csv", index=False)
    print(pd.DataFrame(cal).T.round(5).to_string())
    print(V.to_string(index=False))
    print(Q.pivot(index="quebrada_id", columns="H", values=["esperado", "observado"]).to_string())


if __name__ == "__main__":
    main()

"""Puntos de referencia para interpretar la línea base (NO es selección de variables): el mismo LOSO y las mismas alertas (1 cada N horas),
pero con el puntaje = una sola variable cruda, sin entrenar nada. Sirve para ver si la regresión logística aporta algo sobre lo trivial.
También comprueba la detección de bloques con un cálculo alternativo (recall por filas).
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from comun import SALIDA
from baseline_logistica import N_PROPUESTO, evaluar, episodios_falsos
from tabla3 import HORIZONTES, RUTA, bloques

REFERENCIAS = ["lluvia_24h", "lluvia_14d", "lluvia_efectiva", "log10_area_km2"]


def detectados(ev, score, N):
    """Bloques detectados con alertas = top 1/N de `score` en cada temporada. Devuelve (detectados, bloques, recall_por_filas)."""
    b = bloques(ev)
    det = tot = 0
    hits = pos = 0
    for s, e in ev.groupby("temporada"):
        sc = score.loc[e.index]
        alerta = sc >= np.quantile(sc, 1 - 1 / N)
        bs = b[b.temporada == s]
        d = bs.assign(al=alerta.loc[bs.index]).groupby("bloque").al.max()
        det, tot = det + int(d.sum()), tot + len(d)
        hits, pos = hits + int(alerta[e.y == 1].sum()), pos + int((e.y == 1).sum())
    return det, tot, hits / pos


def main():
    t = pd.read_parquet(RUTA)
    filas = []
    for H in HORIZONTES:
        r = evaluar(t, H)
        ev = r["ev"].copy()
        base = ev.y.mean()
        det, tot, rec = detectados(ev, ev.p, N_PROPUESTO)
        filas.append(dict(H=H, score="regresión logística", AUPRC=average_precision_score(ev.y, ev.p), veces_base=average_precision_score(ev.y, ev.p) / base,
                          bloques_detectados=f"{det}/{tot}", recall_filas_pct=100 * rec))
        for c in REFERENCIAS:
            sc = ev[c].fillna(ev[c].min())
            det, tot, rec = detectados(ev, sc, N_PROPUESTO)
            filas.append(dict(H=H, score=c + " (cruda)", AUPRC=average_precision_score(ev.y, sc), veces_base=average_precision_score(ev.y, sc) / base,
                              bloques_detectados=f"{det}/{tot}", recall_filas_pct=100 * rec))
    res = pd.DataFrame(filas).round({"AUPRC": 4, "veces_base": 1, "recall_filas_pct": 2})
    res.to_csv(SALIDA / "baseline_referencias_simples.csv", index=False)
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()

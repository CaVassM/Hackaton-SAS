"""Métricas de alerta compartidas por todos los modelos (regresión logística, XGBoost, Random Forest), para medirlos con el mismo código.

  - Alertas: en cada temporada evaluada se marca el top 1/N de los puntajes (presupuesto de 1 alerta por cada N horas de cada quebrada).
  - Bloque de huaico = racha de horas consecutivas con y=1 en una quebrada. Detectado = al menos una alerta dentro del bloque.
  - Falsa alarma: hora de alerta con y=0; episodio = alertas de una quebrada separadas por <= 6 h. y=0 es "sin noticia", no un cero seguro.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from tabla3 import bloques

N_PROPUESTO = 100
N_LISTA = (50, 100, 200, 500)
GAP_EPISODIO_H = 6


def episodios_falsos(ev, alerta):
    """(episodios de alerta sin ningún y=1, horas de alerta con y=0)."""
    a = ev.loc[alerta, ["quebrada_id", "hora", "y"]].sort_values(["quebrada_id", "hora"])
    if a.empty:
        return 0, 0
    dif = a.groupby("quebrada_id").hora.diff()
    a["ep"] = (dif.isna() | (dif > pd.Timedelta(hours=GAP_EPISODIO_H))).cumsum()
    return int((a.groupby("ep").y.max() == 0).sum()), int((a.y == 0).sum())


def metricas_por_temporada(ev, con_evento, H):
    """ev: filas evaluadas de un horizonte (columnas temporada, quebrada_id, hora, y, p). Devuelve (tabla por temporada y N, (y, p))."""
    b = bloques(ev)  # índice conservado: sirve para cruzar con las alertas
    filas = []
    for s in con_evento:
        e = ev[ev.temporada == s]
        bs = b[b.temporada == s]
        ap_s = average_precision_score(e.y, e.p)
        for N in N_LISTA:
            alerta = e.p >= np.quantile(e.p, 1 - 1 / N)
            det = bs.assign(al=alerta.loc[bs.index]).groupby("bloque").al.max()
            largo = bs.groupby("bloque").size()
            aleatorio = float((1 - (1 - 1 / N) ** largo).mean())
            ep, horas = episodios_falsos(e, alerta)
            filas.append(dict(H=H, temporada=s, N=N, bloques=len(det), detectados=int(det.sum()), aleatorio_esperado=aleatorio * len(det),
                              alertas_horas=int(alerta.sum()), falsas_horas=horas, falsos_episodios=ep, AUPRC=ap_s, base=e.y.mean()))
    return pd.DataFrame(filas), (ev.y.to_numpy(), ev.p.to_numpy())


def resumen_y_sensibilidad(res):
    """res: {H: dict(n=..., pr=..., con_evento=...)}. Devuelve (resumen con N propuesto, sensibilidad a N)."""
    resumen, sens_N = [], []
    for H, r in res.items():
        y, p = r["pr"]
        auprc, base = average_precision_score(y, p), y.mean()
        macro = r["n"].drop_duplicates("temporada").AUPRC.mean()
        for N, g in r["n"].groupby("N"):
            fila = dict(H=H, N=N, temporadas=g.temporada.nunique(), bloques=int(g.bloques.sum()), detectados=int(g.detectados.sum()),
                        pct_detectados=round(100 * g.detectados.sum() / g.bloques.sum(), 1), pct_aleatorio=round(100 * g.aleatorio_esperado.sum() / g.bloques.sum(), 1),
                        falsos_episodios_por_temporada=round(g.falsos_episodios.mean(), 1), falsas_horas_por_temporada=round(g.falsas_horas.mean()))
            sens_N.append(fila)
            if N == N_PROPUESTO:
                resumen.append(dict(H=H, temporadas_evaluadas=len(r["con_evento"]), filas_evaluadas=len(y), positivos=int(y.sum()), AUPRC=round(auprc, 4),
                                    base=round(base, 4), veces_la_base=round(auprc / base, 1), AUPRC_media_por_temporada=round(macro, 4),
                                    **{k: fila[k] for k in ("bloques", "detectados", "pct_detectados", "pct_aleatorio", "falsos_episodios_por_temporada", "falsas_horas_por_temporada")}))
    return pd.DataFrame(resumen), pd.DataFrame(sens_N)

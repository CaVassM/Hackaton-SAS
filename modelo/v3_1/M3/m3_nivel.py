"""M3 (pre-registrada): nivel operativo con menos horas en rojo, SIN reentrenar. Puntajes = v3 B1 fuera de muestra (oof_b1), umbral rojo = el de cada pliegue LOSO.

  Rojo M3     = p_zona >= umbral rojo  Y  lluvia IMERG > 0.1 mm en las últimas 6 h disponibles (i6h: máximo entre celdas de la lluvia de 6 h con etiqueta
                <= t-5, la misma que usa el modelo).
  Amarillo M3 = p_zona >= umbral rojo sin lluvia reciente ("condiciones favorables").
Reporta: TSS/POD/POFD por evento del ROJO (v3 vs M3), horas en rojo por temporada (H = 3), anticipación de los aciertos (primera hora roja hasta el huaico).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
V3 = AQUI.parents[1] / "v3"
sys.path.insert(0, str(V3 / "A"))
sys.path.insert(0, str(V3))
from comun_v3 import CACHE, bootstrap, etiquetar, evaluar_loso, eventos_lluvia, huaicos_v2, lluvia_zona  # noqa: E402
from fase_a import features_intensidad, score_model_safe  # noqa: E402

LLUVIA_MIN = 0.1


def anticipacion(r_eval, serie, taus, hu):
    filas = []
    for r in r_eval[(r_eval.disparador == 1) & r_eval.alerta].itertuples():
        tau = taus[r.temporada]
        b = (r.huaico_fin - pd.Timedelta(minutes=1)).floor("h")
        s = serie.loc[r.inicio:b]
        t1 = s.index[s.to_numpy() >= tau][0]
        m = (hu.ini < r.fin + pd.Timedelta(hours=4)) & (hu.fin >= r.inicio)
        ini = hu.loc[m, "ini"].min()
        filas.append(dict(inicio_evento=r.inicio, primera_alerta=t1, vs_inicio_h=(ini - t1) / pd.Timedelta(hours=1), vs_fin_h=(r.huaico_fin - t1) / pd.Timedelta(hours=1)))
    return pd.DataFrame(filas)


def main():
    pd.set_option("display.width", 230)
    o = pd.read_parquet(CACHE / "oof_b1.parquet")
    o = o[o.H == 3].set_index("hora").B1_estado_5d
    i6 = features_intensidad().i6h.reindex(o.index)
    m3 = o.where(i6 > LLUVIA_MIN, -np.inf)          # el puntaje solo cuenta para rojo si hay lluvia reciente
    ev = pd.read_parquet(V3 / "B" / "fase_b1_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    hu = huaicos_v2()
    ev["v3"] = [score_model_safe(o, r) for r in ev.itertuples()]
    ev["m3"] = [score_model_safe(m3, r) for r in ev.itertuples()]
    r3, taus, res3 = evaluar_loso(ev, ciegos, "v3")
    # M3 con los MISMOS umbrales de v3 (sin recalibrar)
    rm = ev.copy()
    rm["alerta"] = [np.nan_to_num(s, nan=-np.inf, neginf=-np.inf) >= taus[t] for s, t in zip(rm.m3, rm.temporada)]
    from comun_v3 import tss
    resm = tss(np.r_[rm.disparador, np.ones(len(ciegos))], np.r_[rm.alerta, np.zeros(len(ciegos), bool)])
    filas = []
    for nombre, r, res in (("v3 rojo actual", r3, res3), ("M3 rojo (umbral + lluvia > 0.1 mm en 6 h)", rm, resm)):
        t, pod, pofd, tp, fn, fp, tn = res
        ic = bootstrap(r, ciegos)
        filas.append(dict(nivel=nombre, TSS=round(t, 2), TSS_ic90=ic["TSS"], POD=round(pod, 2), POD_ic90=ic["POD"], POFD=round(pofd, 3), aciertos=tp, fallos=fn, falsas=fp))
    res = pd.DataFrame(filas)
    # horas en rojo por temporada (H = 3), umbral del pliegue de cada temporada
    temp = pd.Series(o.index, index=o.index).map(lambda h: f"{h.year if h.month >= 6 else h.year - 1}-{str((h.year if h.month >= 6 else h.year - 1) + 1)[2:]}")
    tau_h = temp.map(taus)
    rojo_v3 = o >= tau_h
    rojo_m3 = rojo_v3 & (i6 > LLUVIA_MIN)
    hrs = pd.DataFrame({"horas_v3_rojo": rojo_v3.groupby(temp).sum(), "horas_M3_rojo": rojo_m3.groupby(temp).sum(),
                        "horas_M3_amarillo_condiciones": (rojo_v3 & ~rojo_m3).groupby(temp).sum(), "horas_totales": temp.groupby(temp).size()})
    hrs["pct_v3_rojo"] = (100 * hrs.horas_v3_rojo / hrs.horas_totales).round(1)
    hrs["pct_M3_rojo"] = (100 * hrs.horas_M3_rojo / hrs.horas_totales).round(1)
    a3, am = anticipacion(r3, o, taus, hu), anticipacion(rm, m3, taus, hu)
    resumen_ant = []
    for nombre, a in (("v3", a3), ("M3", am)):
        x = a.vs_inicio_h
        resumen_ant.append(dict(nivel=nombre, aciertos=len(a), mediana_h=round(x.median(), 1), min_h=round(x.min(), 1), max_h=round(x.max(), 1),
                                ge1h=int((x >= 1).sum()), ge3h=int((x >= 3).sum()), ge6h=int((x >= 6).sum())))
    res.to_csv(AQUI / "m3_resultados.csv", index=False)
    hrs.to_csv(AQUI / "m3_horas_por_temporada.csv")
    pd.DataFrame(resumen_ant).to_csv(AQUI / "m3_anticipacion.csv", index=False)
    print(res.to_string(index=False))
    print("\nHoras en rojo por temporada (H=3):\n" + hrs.to_string())
    print(f"Total: v3 {int(hrs.horas_v3_rojo.sum())} h ({100 * hrs.horas_v3_rojo.sum() / hrs.horas_totales.sum():.1f} %) -> M3 {int(hrs.horas_M3_rojo.sum())} h "
          f"({100 * hrs.horas_M3_rojo.sum() / hrs.horas_totales.sum():.1f} %)")
    print("\nAnticipación (vs inicio del huaico):\n" + pd.DataFrame(resumen_ant).to_string(index=False))


if __name__ == "__main__":
    main()

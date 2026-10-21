"""Fase F: respuestas a los mentores (reunión 19/10). Fijado ANTES de correr; el modelo v3 (B1) no cambia salvo que (2) lo justifique.

(1) WALK-FORWARD (backtesting solo con el pasado): para cada temporada de prueba s >= 2016-17, P1 (B1, mismos parámetros y monotonía) se entrena
    SOLO con las temporadas anteriores a s. El umbral también sale solo del pasado: LOSO interno dentro de las temporadas anteriores (puntajes fuera
    de muestra del pasado) y mejor_umbral (máx. TSS). Se compara con LOSO restringido a las MISMAS temporadas de prueba.
(2) TENDENCIA DE LA LLUVIA (sugerencia del mentor): B1 + 3 variables, sin restricción de monotonía, todas con lluvia <= t-5:
      d1h  = i1h(t) - i1h(t-1)        (¿la última hora llovió más o menos que la anterior?)
      d3h  = i3h(t) - i3h(t-3)        (últimas 3 h vs las 3 h previas)
      f3_24 = i3h / max(p24h, 0.1)    (fracción de la lluvia de 24 h que cayó en las últimas 3 h: ¿se está concentrando?)
    Regla fijada: se adopta solo si el TSS LOSO sube >= 0.03 Y el límite inferior del IC 90 % no baja.
(3) FALSAS ALARMAS Y UMBRALES (para el dashboard): con los puntajes LOSO de B1 (H = 3), para una rejilla de umbrales: POD, POFD y TSS por evento
    y % de horas dic-abr en alerta, por temporada y total.
Salidas: modelo/v3/F/f1_walkforward.csv, f2_tendencia.csv, f3_umbrales.csv, f3_alertas_por_temporada.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent, AQUI.parent / "A", AQUI.parent / "B"):
    sys.path.insert(0, str(p))
from comun_v3 import CACHE, MODELO, bootstrap, etiquetar, evaluar_loso, eventos_lluvia, lluvia_zona, mejor_umbral, tss  # noqa: E402
from fase_a import A2, H_EV, base, features_intensidad, score_model_safe  # noqa: E402
from fase_b1 import CHICO, PARAMS_XGB, estado_horario, fila  # noqa: E402

B1 = A2["A2_mas_72h"] + ["hum_suelo_5d", "dias_activ", "icen"]
TEND = ["d1h", "d3h", "f3_24"]
TEMPS = [f"{a}-{str(a + 1)[2:]}" for a in range(2014, 2026)]
PRIMERA_WF = sys.argv[1] if len(sys.argv) > 1 else "2016-17"  # 2016-17: su LOSO interno no tiene positivos en entrenamiento -> umbral degenerado (-inf, alerta todo); por eso se reporta también desde 2017-18


def tabla():
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    F = features_intensidad()
    F["d1h"] = F.i1h - F.i1h.shift(1)
    F["d3h"] = F.i3h - F.i3h.shift(3)
    F["f3_24"] = F.i3h / np.maximum(F.p24h, 0.1)
    z = base.etiquetas_zona().merge(F, left_on="hora", right_index=True, how="left").merge(estado_horario(), left_on="hora", right_index=True, how="left")
    z["temporada"] = base.temporada_de(z.hora)
    return z.reset_index(drop=True)


def ajustar_predecir(z, cols, tr, te):
    usar = cols + ["H"]
    mono = tuple(1 if c in B1 and c != "dias_activ" or c == "H" else 0 for c in usar)
    y = z.y.to_numpy()
    tr = tr & ~np.isnan(y)
    npos = (y[tr] == 1).sum()
    if npos == 0:
        return np.full(te.sum(), np.nan)
    spw = float(np.sqrt((y[tr] == 0).sum() / npos))
    m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=0)
    return m.fit(z.loc[tr, usar], y[tr]).predict_proba(z.loc[te, usar])[:, 1]


def puntajes_evento(z, p, ev):
    s = pd.Series(p, index=z.hora)[(z.H == H_EV).to_numpy()]
    s = s[~s.index.duplicated()]
    return np.array([score_model_safe(s, r) for r in ev.itertuples()])


def loso(z, cols, temps=TEMPS):
    t = z.temporada.to_numpy()
    p = np.full(len(z), np.nan)
    for s in temps:
        te = t == s
        p[te] = ajustar_predecir(z, cols, t != s, te)
    return p


def main():
    pd.set_option("display.width", 230)
    z = tabla()
    ev0 = pd.read_parquet(AQUI.parent / "A" / "fase_a_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    t = z.temporada.to_numpy()
    print("tabla", z.shape, flush=True)

    # ---- (2) LOSO: B1 (control) y B1 + tendencia
    filas2 = []
    p_b1 = loso(z, B1)
    ev = ev0.copy()
    ev["B1"] = puntajes_evento(z, p_b1, ev)
    for nombre, cols in (("B1 (v3, control)", None), ("B1 + tendencia", B1 + TEND)):
        if cols is not None:
            ev["B1_tend"] = puntajes_evento(z, loso(z, cols), ev)
        col = "B1" if cols is None else "B1_tend"
        r, _, res = evaluar_loso(ev, ciegos, col)
        filas2.append(fila(nombre, r, res, ciegos))
        print(filas2[-1], flush=True)
    pd.DataFrame(filas2).to_csv(AQUI / "f2_tendencia.csv", index=False)

    # ---- (3) umbrales y falsas alarmas con los puntajes LOSO de B1
    h3 = (z.H == H_EV).to_numpy()
    sh = pd.DataFrame({"hora": z.hora[h3], "temporada": t[h3], "p": p_b1[h3]}).drop_duplicates("hora")
    se = ev.B1.to_numpy(float)
    y = np.r_[ev.disparador.to_numpy(), np.ones(len(ciegos))]
    filas3 = []
    for q in [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.98]:
        u = float(np.nanquantile(sh.p, q))
        a = np.r_[np.nan_to_num(se, nan=-np.inf) >= u, np.zeros(len(ciegos), bool)]
        tv, pod, pofd, tp, fn, fp, tn = tss(y, a)
        filas3.append(dict(umbral=round(u, 5), pct_horas_alerta=round(100 * (sh.p >= u).mean(), 1), POD=round(pod, 2), POFD=round(pofd, 3),
                           TSS=round(tv, 2), aciertos=tp, fallos=fn, falsas_alarmas=fp))
    pd.DataFrame(filas3).to_csv(AQUI / "f3_umbrales.csv", index=False)
    r, taus, _ = evaluar_loso(ev, ciegos, "B1")
    pt = []
    for s in TEMPS:
        g = sh[sh.temporada == s]
        tau = taus.get(s, np.nan)
        e = r[r.temporada == s]
        pt.append(dict(temporada=s, umbral_loso=round(float(tau), 5) if np.isfinite(tau) else np.nan, pct_horas_alerta=round(100 * (g.p >= tau).mean(), 1),
                       eventos=len(e), con_huaico=int(e.disparador.sum()), detectados=int((e.alerta & (e.disparador == 1)).sum()),
                       falsas_alarmas=int((e.alerta & (e.disparador == 0)).sum())))
    pd.DataFrame(pt).to_csv(AQUI / "f3_alertas_por_temporada.csv", index=False)
    print(pd.DataFrame(filas3).to_string(index=False), "\n", pd.DataFrame(pt).to_string(index=False), flush=True)

    # ---- (1) walk-forward
    ev["WF"] = np.nan
    ev["alerta_wf"] = False
    ok = []
    for i, s in enumerate(TEMPS):
        if s < PRIMERA_WF:
            continue
        pas = TEMPS[:i]
        # umbral: LOSO interno dentro del pasado
        pin = np.full(len(z), np.nan)
        for q in pas:
            te = t == q
            pin[te] = ajustar_predecir(z, B1, np.isin(t, pas) & (t != q), te)
        evp = ev[ev.temporada.isin(pas)]
        sp = puntajes_evento(z, pin, evp)
        tau = mejor_umbral(np.nan_to_num(sp, nan=-np.inf), evp.disparador.to_numpy())
        te = t == s
        pout = np.full(len(z), np.nan)
        pout[te] = ajustar_predecir(z, B1, np.isin(t, pas), te)
        m = ev.temporada == s
        ev.loc[m, "WF"] = puntajes_evento(z, pout, ev[m])
        ev.loc[m, "alerta_wf"] = np.nan_to_num(ev.loc[m, "WF"].to_numpy(float), nan=-np.inf) >= tau
        ok.append(s)
        print(f"  WF {s}: entrena {pas[0]}..{pas[-1]}, umbral {tau:.4f}", flush=True)
    sub = ev[ev.temporada.isin(ok)]
    cg = ciegos[ciegos.temporada.isin(ok)]
    filas1 = []
    rw = sub.assign(alerta=sub.alerta_wf)
    res = tss(np.r_[rw.disparador, np.ones(len(cg))], np.r_[rw.alerta, np.zeros(len(cg), bool)])
    filas1.append(fila(f"Walk-forward (prueba {ok[0]}..{ok[-1]})", rw, res, cg))
    rl = r[r.temporada.isin(ok)]
    res = tss(np.r_[rl.disparador, np.ones(len(cg))], np.r_[rl.alerta, np.zeros(len(cg), bool)])
    filas1.append(fila(f"LOSO en las mismas temporadas", rl, res, cg))
    res = tss(np.r_[r.disparador, np.ones(len(ciegos))], np.r_[r.alerta, np.zeros(len(ciegos), bool)])
    filas1.append(fila("LOSO, todas (referencia v3)", r, res, ciegos))
    out = pd.DataFrame(filas1)
    out.to_csv(AQUI / ("f1_walkforward.csv" if PRIMERA_WF == "2016-17" else f"f1_walkforward_desde_{PRIMERA_WF.replace('-', '_')}.csv"), index=False)
    print(out.to_string(index=False), flush=True)
    print("FIN", flush=True)


if __name__ == "__main__":
    main()

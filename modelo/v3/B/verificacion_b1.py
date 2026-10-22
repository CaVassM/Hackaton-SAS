"""Verificaciones de B1(a) antes de congelarlo (punto 1). Misma evaluación por evento que fase_b1 (TSS, LOSO, IC 90 % bootstrap por tormenta).

  a) B1 SIN "días desde la última activación" (intensidad + humedad 5 d + ICEN), semillas 0-2.
  b) B1 evaluado solo en PRIMEROS huaicos: se excluyen los disparadores (y días ciegos) con otra activación catalogada en las 17 quebradas en los 7 días
     PREVIOS (fechas d-7..d-1, d = día del huaico); las alertas son las mismas de B1 (no se reentrena), los negativos son todos.
  c) Persistencia trivial: alerta si hubo activación catalogada en los 2 días previos al evento (fechas [inicio-2 d, último día útil - 1 d]) Y la lluvia del
     evento (misma ventana útil que B1: en disparadores hasta el huaico con 4 h de latencia) supera la MEDIANA de la lluvia de los eventos de entrenamiento.
  d) Anticipación: en cada huaico acertado por B1, primera hora del evento (con puntaje horario >= umbral de su pliegue; la latencia de 4 h ya está en las
     variables) y horas hasta el huaico: contra el INICIO del rango del huaico (cota conservadora) y contra el FIN. También el inicio de la racha continua de
     alerta (puede empezar antes del evento).
Salidas: modelo/v3/B/verificacion_b1.csv, anticipacion_b1.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent / "A"))
from fase_b1 import A2, CHICO, H_EV, MODELO, PARAMS_XGB, RAIZ, base, estado_horario, features_intensidad, score_model_safe  # noqa: E402
from comun_v3 import CACHE, bootstrap, etiquetar, evaluar_loso, eventos_lluvia, huaicos_v2, lluvia_zona, tss  # noqa: E402
from fase_a import ventana  # noqa: E402


def activaciones():
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    q = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    return np.array(sorted(set(pd.to_datetime(c.fecha[c.en_piloto.eq("True") & q.ne("")]))), dtype="datetime64[ns]")


def hay_activacion(fechas, a, b):
    """¿Alguna activación con fecha en [a, b]?"""
    i = np.searchsorted(fechas, np.datetime64(a), "left")
    return i < len(fechas) and fechas[i] <= np.datetime64(b)


def resultado(nombre, r, ciegos, res=None):
    yy = np.r_[r.disparador.to_numpy(), np.ones(len(ciegos))]
    aa = np.r_[r.alerta.to_numpy(), np.zeros(len(ciegos), bool)]
    t, pod, pofd, tp, fn, fp, tn = res if res is not None else tss(yy, aa)
    ic = bootstrap(r, ciegos)
    return dict(verificacion=nombre, positivos=tp + fn, TSS=round(t, 2), TSS_ic90=ic["TSS"], POD=round(pod, 2), POD_ic90=ic["POD"], POFD=round(pofd, 3),
                aciertos=tp, fallos=fn, falsas=fp)


def main():
    pd.set_option("display.width", 230)
    ev = pd.read_parquet(AQUI / "fase_b1_eventos.parquet")
    z = lluvia_zona()
    _, ciegos = etiquetar(eventos_lluvia(z))
    act = activaciones()
    filas = []
    # referencia: B1(a)
    r_b1, taus, res = evaluar_loso(ev, ciegos, "B1_estado_5d")
    filas.append(resultado("B1(a) completo (referencia)", r_b1, ciegos, res))

    # a) sin días desde la activación
    E = estado_horario()
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    zz = base.etiquetas_zona().merge(features_intensidad(), left_on="hora", right_index=True, how="left").merge(E, left_on="hora", right_index=True, how="left")
    zz["temporada"] = base.temporada_de(zz.hora)
    y, temp = zz.y.to_numpy(), zz.temporada.to_numpy()
    lab = ~np.isnan(y)
    usar = A2["A2_mas_72h"] + ["hum_suelo_5d", "icen", "H"]
    for sem in (0, 1, 2):
        p = np.full(len(zz), np.nan)
        for s in np.unique(temp):
            te, tr = temp == s, (temp != s) & lab
            spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
            m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=tuple([1] * len(usar)), random_state=sem)
            p[te] = m.fit(zz.loc[tr, usar], y[tr]).predict_proba(zz.loc[te, usar])[:, 1]
        serie = pd.Series(p[zz.H.to_numpy() == H_EV], index=zz.hora[zz.H == H_EV])
        ev["sin_dias"] = [score_model_safe(serie, r) for r in ev.itertuples()]
        r, _, res = evaluar_loso(ev, ciegos, "sin_dias")
        filas.append(resultado(f"a) B1 SIN días desde activación, semilla {sem}", r, ciegos, res))

    # b) primeros huaicos
    hu = huaicos_v2()
    def previa(d):
        d = pd.Timestamp(d).normalize()
        return hay_activacion(act, d - pd.Timedelta(days=7), d - pd.Timedelta(days=1))
    d_huaico = r_b1.huaico_fin.dt.normalize()
    excluir = (r_b1.disparador == 1) & d_huaico.apply(lambda d: previa(d) if pd.notna(d) else False)
    rb = r_b1[~excluir]
    cb = ciegos[~ciegos.fecha.apply(previa)]
    f = resultado("b) B1 solo en primeros huaicos (sin activación en los 7 días previos)", rb, cb)
    f["excluidos"] = int(excluir.sum()) + (len(ciegos) - len(cb))
    filas.append(f)

    # c) persistencia trivial
    def lluvia_util(r):
        return float(z.loc[r.inicio: ventana(r, 4)].fillna(0).sum())
    ev["lluvia_util"] = [lluvia_util(r) for r in ev.itertuples()]
    ev["activ_2d"] = [hay_activacion(act, (r.inicio - pd.Timedelta(days=2)).normalize(), (ventana(r, 4) - pd.Timedelta(days=1)).normalize())
                      for r in ev.itertuples()]
    pc = ev.copy()
    pc["alerta"] = False
    for t in sorted(pc.temporada.unique()):
        med = pc.loc[pc.temporada != t, "lluvia_util"].median()
        te = pc.temporada == t
        pc.loc[te, "alerta"] = pc.loc[te, "activ_2d"] & (pc.loc[te, "lluvia_util"] > med)
    filas.append(resultado("c) persistencia: activación en 2 días previos Y lluvia > mediana", pc, ciegos))
    res_tab = pd.DataFrame(filas)
    res_tab.to_csv(AQUI / "verificacion_b1.csv", index=False)
    print(res_tab.to_string(index=False))

    # d) anticipación
    o = pd.read_parquet(CACHE / "oof_b1.parquet")
    o = o[o.H == H_EV].set_index("hora").B1_estado_5d
    filas = []
    for r in r_b1[(r_b1.disparador == 1) & r_b1.alerta].itertuples():
        tau = taus[r.temporada]
        b = (r.huaico_fin - pd.Timedelta(minutes=1)).floor("h")
        s = o.loc[r.inicio:b]
        t1 = s.index[s.to_numpy() >= tau][0]
        k = t1
        while (k - pd.Timedelta(hours=1)) in o.index and o.loc[k - pd.Timedelta(hours=1)] >= tau:   # inicio de la racha continua
            k -= pd.Timedelta(hours=1)
        m = (hu.ini < r.fin + pd.Timedelta(hours=4)) & (hu.fin >= r.inicio)
        ini = hu.loc[m, "ini"].min()
        filas.append(dict(temporada=r.temporada, evento_inicio=r.inicio, huaico_ini=ini, huaico_fin=r.huaico_fin, primera_alerta=t1,
                          anticip_vs_inicio_h=(ini - t1) / pd.Timedelta(hours=1), anticip_vs_fin_h=(r.huaico_fin - t1) / pd.Timedelta(hours=1),
                          inicio_racha=k, racha_vs_inicio_h=(ini - k) / pd.Timedelta(hours=1)))
    a = pd.DataFrame(filas)
    a.to_csv(AQUI / "anticipacion_b1.csv", index=False)
    print("\nAnticipación (aciertos de B1):\n" + a.round(1).to_string(index=False))
    for col in ("anticip_vs_inicio_h", "anticip_vs_fin_h", "racha_vs_inicio_h"):
        x = a[col]
        print(f"{col}: mediana {x.median():.1f} h, rango {x.min():.1f} a {x.max():.1f}; >= 1 h: {(x >= 1).sum()}, >= 3 h: {(x >= 3).sum()}, >= 6 h: {(x >= 6).sum()} de {len(x)}")


if __name__ == "__main__":
    main()

"""Modelo final v3 = dos piezas. P1 = B1(a) en la ZONA (intensidad IMERG + estado), P2 = historia + terreno por quebrada (dos_piezas/pieza2.py).

ENTRENAR (python modelo/v3/final/modelo_final.py entrenar):
  - P1: XGBoost restringido (PARAMS_XGB + CHICO; monotonía +1 salvo dias_activ), semilla 0, con TODAS las temporadas (dic-abr 2014-15..2025-26),
    etiquetas de zona v2 para H = 3, 6, 12, 24 (H es una columna monótona: p(H=3) <= p(H=6) <= ...). -> p1_b1.json
  - Umbrales por H, calibrados con los puntajes FUERA DE MUESTRA (LOSO) por EVENTO de lluvia, como en la validación:
      rojo     = umbral que maximiza el TSS;
      amarillo = umbral más alto con POD >= 0.9; como es inalcanzable (máx. 11/13 = 0.85: un día ciego y un huaico sin horas útiles), el umbral
                 del MÁXIMO POD posible. En el ejemplo 2022-23 (calibrado sin esa temporada) coincide con el rojo: no hay banda amarilla.
    El modelo final (entrenado con todo) puntúa en otra escala que los modelos LOSO: cada umbral se traslada POR CUANTIL (misma fracción de horas
    de dic-abr por encima del umbral). -> metadatos_final.json
  - P2: mezcla historia + terreno con las 10 tormentas: P2 = (n_activaciones + 4 p_terreno) / (10 + 4). -> p2_final.csv
CÓMO SE TRADUCE P1 A CADA H: P1 estima p_zona(t, H) = P(huaico en alguna de las 17 quebradas en (t, t+H] | lo que se sabe en t). Para cada H el umbral se
  calibra con el MISMO esquema por evento (puntaje del evento = máximo de p_zona(t, H) en las horas útiles antes del huaico). La anticipación medida
  (mediana 2 h contra el inicio del huaico) solo respalda H = 3 como promesa; H = 6/12/24 describen la condición de la zona.
PREDECIR (función tabla_operativa): para cada hora t y H -> quebrada_id, hora, H, p_zona, p2_quebrada, score = p_zona * p2, indice_0_100, nivel.
  nivel (de la ZONA, que es lo validado): rojo si p_zona >= umbral rojo(H); amarillo si >= umbral amarillo(H); si no verde.
  indice_0_100 = 100 * min(1, p_zona / umbral_rojo(H)) * p2 / max(p2): 100 = zona en umbral rojo y la quebrada más propensa. P2 ORDENA las quebradas;
  no hay umbral validado por quebrada.
EJEMPLO 2022-23 (python modelo/v3/final/modelo_final.py ejemplo): con el modelo del pliegue que NO vio 2022-23 (y P2 y umbrales calibrados sin 2022-23),
  para que el ejemplo sea fuera de muestra. -> ejemplo_2022_23.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
V3 = AQUI.parent
sys.path.insert(0, str(V3 / "B"))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3 / "A"))
from fase_b1 import A2, CHICO, MODELO, PARAMS_XGB, base, estado_horario, features_intensidad, score_model_safe  # noqa: E402
from comun_v3 import CACHE, etiquetar, eventos_lluvia, lluvia_zona, mejor_umbral, tss  # noqa: E402

sys.path.insert(0, str(MODELO / "dos_piezas"))
import pieza2  # noqa: E402

HS = (3, 6, 12, 24)
VARIABLES = A2["A2_mas_72h"] + ["hum_suelo_5d", "dias_activ", "icen", "H"]
FUENTES = {
    "i1h, i3h, i6h": "IMERG Early (GPM_3IMERGHHE V07, 30 min), máximo entre las 5 celdas de las quebradas de la lluvia de 1/3/6 h con etiqueta <= t-5 (latencia 4 h)",
    "i1h_max6, i3h_max6, i6h_max6": "máximo de i1h/i3h/i6h en las últimas 6 horas disponibles (IMERG Early, latencia 4 h)",
    "p24h, p48h, p72h": "IMERG Early: máximo entre celdas de la lluvia de 24/48/72 h (latencia 4 h)",
    "hum_suelo_5d": "ERA5-Land soil_moisture_0_to_7cm (Open-Meteo archive API, sin credenciales), media de las 5 celdas, valor de t - 5 días (retraso real de ERA5-Land)",
    "dias_activ": "catálogo de activaciones (17 quebradas; fechas < día de t; en operación: registro en tiempo real de INDECI/municipio), tope 3650",
    "icen": "ICEN oficial (IGP/ENFEN, met.igp.gob.pe/datos/ICEN.txt): mes M-2 desde el día 10 del mes M, M-3 antes",
    "H": "horizonte en horas (3, 6, 12, 24)",
}


def tabla_zona(idx_extra=None):
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    z = base.etiquetas_zona()
    return z.merge(features_intensidad(), left_on="hora", right_index=True, how="left").merge(estado_horario(), left_on="hora", right_index=True, how="left").assign(
        temporada=lambda d: base.temporada_de(d.hora))


def ajustar(z, semilla=0):
    tr = z.y.notna().to_numpy()
    y = z.y.to_numpy()[tr]
    spw = float(np.sqrt((y == 0).sum() / (y == 1).sum()))
    mono = tuple(0 if c == "dias_activ" else 1 for c in VARIABLES)
    return xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=semilla).fit(z.loc[tr, VARIABLES], y)


def umbrales_oof(excluir=None):
    """Por H: (rojo, amarillo) con los puntajes fuera de muestra por evento (oof_b1, B1_estado_5d), opcionalmente sin una temporada."""
    ev = pd.read_parquet(V3 / "B" / "fase_b1_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    if excluir:
        ev, ciegos = ev[ev.temporada != excluir], ciegos[ciegos.temporada != excluir]
    o = pd.read_parquet(CACHE / "oof_b1.parquet")
    out = {}
    for H in HS:
        s = o[o.H == H].set_index("hora").B1_estado_5d
        sc = np.array([score_model_safe(s, r) for r in ev.itertuples()])
        sc = np.nan_to_num(sc, nan=-np.inf)
        y = ev.disparador.to_numpy()
        rojo = mejor_umbral(sc, y)
        # amarillo: umbral más alto con POD >= 0.9 (los días ciegos cuentan como fallo). Si es inalcanzable (lo es: hay un día ciego y un huaico sin
        # horas útiles; máx. POD 11/13 = 0.85), el umbral que logra el MÁXIMO POD posible (= el menor puntaje de un disparador).
        # (Probado y descartado: "POD >= 0.9 entre los huaicos puntuables" coincide con el rojo, que ya acierta 10 de 11.)
        n_pos = int(y.sum()) + len(ciegos)
        puntuables = (y == 1) & np.isfinite(sc)
        amar = np.min(sc[puntuables])
        for c in np.unique(sc[np.isfinite(sc)])[::-1]:
            if ((sc >= c) & (y == 1)).sum() / n_pos >= 0.9:
                amar = c
                break
        t_r, pod_r, pofd_r = tss(np.r_[y, np.ones(len(ciegos))], np.r_[sc >= rojo, np.zeros(len(ciegos), bool)])[:3]
        t_a, pod_a, pofd_a = tss(np.r_[y, np.ones(len(ciegos))], np.r_[sc >= amar, np.zeros(len(ciegos), bool)])[:3]
        q_r = float((s.dropna() < rojo).mean())
        q_a = float((s.dropna() < amar).mean())
        out[H] = dict(rojo_oof=float(rojo), amarillo_oof=float(min(amar, rojo)), cuantil_rojo=q_r, cuantil_amarillo=q_a,
                      rojo_TSS=round(t_r, 2), rojo_POD=round(pod_r, 2), rojo_POFD=round(pofd_r, 3),
                      amarillo_TSS=round(t_a, 2), amarillo_POD=round(pod_a, 2), amarillo_POFD=round(pofd_a, 3))
    return out


def p2_tabla(entrenar=None):
    torm = pieza2.tormentas()
    A = pieza2.matriz_activacion(torm)
    ent = torm.tormenta if entrenar is None else entrenar(torm)
    return pieza2.p2(A, ent)["mezcla"]


def tabla_operativa(modelo, umbrales, p2, X):
    """X: variables por hora (índice = hora, columnas = VARIABLES sin H). Devuelve la tabla operativa para los 4 H y las 17 quebradas."""
    filas = []
    for H in HS:
        Xh = X.assign(H=H)[VARIABLES]
        pz = modelo.predict_proba(Xh)[:, 1]
        r, a = umbrales[H]["rojo"], umbrales[H]["amarillo"]
        nivel = np.where(pz >= r, "rojo", np.where(pz >= a, "amarillo", "verde"))
        for q, v in p2.items():
            filas.append(pd.DataFrame({"quebrada_id": q, "hora": X.index, "H": H, "p_zona": pz, "p2_quebrada": v, "score": pz * v,
                                       "indice_0_100": np.round(100 * np.minimum(1, pz / r) * v / p2.max(), 1), "nivel": nivel}))
    return pd.concat(filas, ignore_index=True)


def variables_horarias(horas):
    F = features_intensidad()
    E = estado_horario(idx=horas)
    return F.reindex(horas).join(E)[[c for c in VARIABLES if c != "H"]]


def entrenar():
    z = tabla_zona()
    m = ajustar(z)
    m.save_model(AQUI / "p1_b1.json")
    u = umbrales_oof()
    todas = z[z.y.notna()]
    for H in HS:
        s_fin = m.predict_proba(todas[todas.H == H][VARIABLES])[:, 1]
        u[H]["rojo"] = float(np.quantile(s_fin, u[H]["cuantil_rojo"]))
        u[H]["amarillo"] = float(min(np.quantile(s_fin, u[H]["cuantil_amarillo"]), u[H]["rojo"]))
    p2 = p2_tabla()
    p2.rename("p2_mezcla").to_csv(AQUI / "p2_final.csv")
    meta = dict(modelo="P1 = B1(a): XGBoost restringido en la zona (intensidad IMERG + estado); P2 = historia + terreno (k = 4)",
                entrenado_con="dic-abr 2014-15..2025-26 (filas de zona con etiqueta v2), semilla 0", filas_entrenamiento=int(z.y.notna().sum()),
                positivos_por_H={int(H): int(z[(z.H == H)].y.sum()) for H in HS}, variables_en_orden=VARIABLES, fuentes_operativas=FUENTES,
                parametros={**{k: v for k, v in PARAMS_XGB.items() if k != "n_jobs"}, **CHICO},
                umbrales={int(H): u[H] for H in HS},
                nota_umbrales="rojo = max TSS por evento (puntajes LOSO); amarillo = umbral más alto con POD >= 0.9; trasladados al modelo final por cuantil "
                              "de las horas de dic-abr. TSS/POD/POFD reportados = los de los puntajes LOSO (fuera de muestra).",
                nivel="de la ZONA (validado); P2 ordena quebradas; indice_0_100 = 100 * min(1, p_zona/umbral_rojo) * p2/max(p2)",
                horizonte_prometible="H = 3 h (anticipación mediana 2 h contra el inicio del huaico); H = 6/12/24 = condición de la zona")
    (AQUI / "metadatos_final.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta["umbrales"], indent=1))


def ejemplo(temporada="2022-23"):
    z = tabla_zona()
    m = ajustar(z[z.temporada != temporada])
    u = umbrales_oof(excluir=temporada)
    for H in HS:
        u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
    p2 = p2_tabla(lambda torm: torm.loc[torm.temporada != temporada, "tormenta"])
    a0 = int(temporada[:4])
    horas = pd.date_range(f"{a0}-12-01", f"{a0 + 1}-04-30 23:00", freq="h")
    T = tabla_operativa(m, u, p2, variables_horarias(horas))
    T["p_zona"], T["score"] = T.p_zona.round(5), T.score.round(5)
    T["p2_quebrada"] = T.p2_quebrada.round(4)
    T.to_csv(AQUI / f"ejemplo_{temporada.replace('-', '_')}.csv", index=False)
    print(f"{len(T):,} filas; horas en nivel por H:\n" + T[T.quebrada_id == T.quebrada_id.iloc[0]].groupby(["H", "nivel"]).size().unstack(fill_value=0).to_string())
    return T


if __name__ == "__main__":
    {"entrenar": entrenar, "ejemplo": ejemplo}[sys.argv[1]]()

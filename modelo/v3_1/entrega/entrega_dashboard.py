"""Entrega al dashboard: modelo v3 (SIN cambios: modelo/v3/final/p1_b1.json, metadatos_final.json, p2_final.csv) con dos columnas de nivel de la ZONA.

Nivel por defecto (OFICIAL, el validado; columna `nivel`), por zona y horizonte H:
  rojo     = p_zona >= umbral rojo(H)            (como en la validación)
  amarillo = umbral amarillo(H) <= p_zona < umbral rojo(H)
  verde    = el resto
Variante opcional (columna `nivel_con_lluvia`, antes "M3"): igual, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h disponibles
  (lluvia_6h_mm = i6h: máximo entre celdas, etiqueta <= t-5); si no la hay, amarillo ("condiciones favorables").
Validación (por evento, LOSO, 13 positivos; modelo/v3_1/RESUMEN.md): rojo de `nivel` TSS 0.49, POD 0.69, POFD 0.20, 15 % de horas en rojo;
  rojo de `nivel_con_lluvia` TSS 0.44, POD 0.62, POFD 0.17, 11 % de horas en rojo; su "rojo o amarillo" alerta los mismos huaicos que el rojo de `nivel`.

Uso:
  python modelo/v3_1/entrega/entrega_dashboard.py hora "2023-03-14 13:00" [--csv salida.csv]   # tabla operativa de una hora (17 x 4 filas)
  python modelo/v3_1/entrega/entrega_dashboard.py ejemplo                                       # temporada 2022-23 FUERA DE MUESTRA -> ejemplo_2022_23_m3.csv
Columnas: quebrada_id, hora, H, p_zona, p2_quebrada, score, indice_0_100, lluvia_6h_mm, nivel (oficial, por defecto), nivel_con_lluvia (variante),
  p_zona_calibrada, veces_lo_normal, prob_quebrada, prob_quebrada_min, prob_quebrada_max
Probabilidades calibradas (modelo/v3/final/calibracion.py; misma lógica que entrega_modelo, archivos A, B y E):
  p_zona_calibrada  = p_cal(t, H) = sigmoid(a_H + b_H logit(p_zona)): probabilidad de huaico en alguna de las 17 quebradas en (t, t+H]
  veces_lo_normal   = p_zona_calibrada / tasa base del H
  prob_quebrada     = p_cal x kappa_H x P2(q) (= prob_ml_Hh de entrega_modelo); prob_quebrada_min / _max = con kappa_min_H / kappa_max_H
  Modo hora (modelo final): p_zona se lleva antes a la escala LOSO por cuantil (calibracion_escala_final.csv); calibración de calibracion.json.
  Modo ejemplo (fuera de muestra): Platt, kappa, su rango y la tasa base se ajustan SIN la temporada.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
FINAL = AQUI.parents[1] / "v3" / "final"
sys.path.insert(0, str(FINAL))
import modelo_final as mf  # noqa: E402
from predecir import cargar  # noqa: E402
import calibracion as cb  # noqa: E402

LLUVIA_MIN = 0.1
COLUMNAS = ["quebrada_id", "hora", "H", "p_zona", "p2_quebrada", "score", "indice_0_100", "lluvia_6h_mm", "nivel", "nivel_con_lluvia",
            "p_zona_calibrada", "veces_lo_normal", "prob_quebrada", "prob_quebrada_min", "prob_quebrada_max"]


def con_niveles(T, X, umbrales):
    """T: tabla operativa de v3 (su columna nivel = oficial, se conserva). X: variables por hora (incluye i6h). Agrega lluvia_6h_mm y la variante nivel_con_lluvia."""
    T = T.copy()
    T["lluvia_6h_mm"] = T.hora.map(X.i6h).round(2)
    rojo_u = T.H.map({H: v["rojo"] for H, v in umbrales.items()})
    amar_u = T.H.map({H: v["amarillo"] for H, v in umbrales.items()})
    supera = T.p_zona >= rojo_u
    llueve = T.lluvia_6h_mm > LLUVIA_MIN
    T["nivel_con_lluvia"] = np.where(supera & llueve, "rojo", np.where(supera | (T.p_zona >= amar_u), "amarillo", "verde"))
    return T


def con_probabilidades(T, cal, esc=None):
    """Agrega p_zona_calibrada, veces_lo_normal y prob_quebrada (con su rango min / max). esc = rejilla del modelo final (None si p_zona ya está
    en la escala LOSO, como en un modelo de pliegue). cal debe traer kappa_min / kappa_max (calibracion.con_rango)."""
    W = T.drop_duplicates(["hora", "H"]).pivot(index="hora", columns="H", values="p_zona")
    pz = {H: W[H].to_numpy() for H in mf.HS}
    pc = cb.p_calibrada(cal, pz if esc is None else cb.a_escala_loso(esc, pz))
    zk = {k: cb.p_zona_kappa(cal, pc, k) for k in ("kappa", "kappa_min", "kappa_max")}
    Z = pd.concat([pd.DataFrame({"hora": W.index, "H": H, "p_zona_calibrada": pc[H], "veces_lo_normal": pc[H] / cal[H]["tasa_base"],
                                 "_zk": zk["kappa"][H], "_zk_min": zk["kappa_min"][H], "_zk_max": zk["kappa_max"][H]}) for H in mf.HS])
    T = T.merge(Z, on=["hora", "H"], how="left")
    for c, k in (("prob_quebrada", "_zk"), ("prob_quebrada_min", "_zk_min"), ("prob_quebrada_max", "_zk_max")):
        T[c] = T[k] * T.p2_quebrada
    return T[COLUMNAS]


def hora(t, csv=None):
    m, u, p2 = cargar()
    cal = {int(H): v for H, v in json.loads((FINAL / "calibracion.json").read_text(encoding="utf-8"))["por_H"].items()}
    esc = pd.read_csv(FINAL / "calibracion_escala_final.csv")
    horas = pd.DatetimeIndex([pd.Timestamp(t).floor("h")])
    X = mf.variables_horarias(horas)
    T = con_probabilidades(con_niveles(mf.tabla_operativa(m, u, p2, X), X, u), cal, esc).sort_values(["H", "score"], ascending=[True, False])
    if csv:
        T.to_csv(csv, index=False)
    return T


def ejemplo(temporada="2022-23"):
    """Igual que modelo_final.ejemplo (modelo, P2 y umbrales calibrados SIN la temporada), con nivel (oficial) y nivel_con_lluvia (variante)."""
    z = mf.tabla_zona()
    m = mf.ajustar(z[z.temporada != temporada])
    u = mf.umbrales_oof(excluir=temporada)
    for H in mf.HS:
        u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
    p2 = mf.p2_tabla(lambda torm: torm.loc[torm.temporada != temporada, "tormenta"])
    d = cb.datos()
    cal = cb.con_rango(cb.ajustar(d, p2, excluir=temporada), d, excluir=temporada)
    a0 = int(temporada[:4])
    horas = pd.date_range(f"{a0}-12-01", f"{a0 + 1}-04-30 23:00", freq="h")
    X = mf.variables_horarias(horas)
    T = con_probabilidades(con_niveles(mf.tabla_operativa(m, u, p2, X), X, u), cal)
    T["p_zona"], T["score"], T["p2_quebrada"] = T.p_zona.round(5), T.score.round(5), T.p2_quebrada.round(4)
    T["p_zona_calibrada"], T["veces_lo_normal"] = T.p_zona_calibrada.round(5), T.veces_lo_normal.round(2)
    for c in ("prob_quebrada", "prob_quebrada_min", "prob_quebrada_max"):
        T[c] = T[c].round(5)
    T.to_csv(AQUI / f"ejemplo_{temporada.replace('-', '_')}_m3.csv", index=False)
    una = T[T.quebrada_id == T.quebrada_id.iloc[0]]
    print(f"{len(T):,} filas. Horas por nivel (nivel oficial | nivel_con_lluvia):")
    print(pd.concat([una.groupby(["H", "nivel"]).size().unstack(fill_value=0).add_prefix("oficial_"),
                     una.groupby(["H", "nivel_con_lluvia"]).size().unstack(fill_value=0).add_prefix("con_lluvia_")], axis=1).to_string())
    return T


if __name__ == "__main__":
    if sys.argv[1] == "ejemplo":
        ejemplo()
    else:
        csv = sys.argv[sys.argv.index("--csv") + 1] if "--csv" in sys.argv else None
        pd.set_option("display.width", 220)
        print(hora(sys.argv[2], csv)[lambda d: d.H == 3].round(4).to_string(index=False))

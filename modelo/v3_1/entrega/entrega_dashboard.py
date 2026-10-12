"""Entrega al dashboard: modelo v3 (SIN cambios: modelo/v3/final/p1_b1.json, metadatos_final.json, p2_final.csv) con el nivel M3 POR DEFECTO.

Nivel por defecto (M3, columna `nivel`), por zona y horizonte H:
  rojo     = p_zona >= umbral rojo(H)  Y  lluvia IMERG > 0.1 mm en las últimas 6 h disponibles (lluvia_6h_mm = i6h: máximo entre celdas, etiqueta <= t-5)
  amarillo = p_zona >= umbral rojo(H) sin lluvia reciente ("condiciones favorables"),  o  umbral amarillo(H) <= p_zona < umbral rojo(H)
  verde    = el resto
Nivel original v3 (columna `nivel_v3`): rojo = p_zona >= umbral rojo; amarillo = p_zona >= umbral amarillo; verde = el resto.
Validación (por evento, LOSO, 13 positivos; modelo/v3_1/RESUMEN.md): rojo v3 TSS 0.49, POD 0.69, POFD 0.20, 15 % de horas en rojo;
  rojo M3 TSS 0.44, POD 0.62, POFD 0.17, 11 % de horas en rojo; "rojo o amarillo" alerta los mismos huaicos que el rojo de v3.

Uso:
  python modelo/v3_1/entrega/entrega_dashboard.py hora "2023-03-14 13:00" [--csv salida.csv]   # tabla operativa de una hora (17 x 4 filas)
  python modelo/v3_1/entrega/entrega_dashboard.py ejemplo                                       # temporada 2022-23 FUERA DE MUESTRA -> ejemplo_2022_23_m3.csv
Columnas: quebrada_id, hora, H, p_zona, p2_quebrada, score, indice_0_100, lluvia_6h_mm, nivel (M3, por defecto), nivel_v3
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
FINAL = AQUI.parents[1] / "v3" / "final"
sys.path.insert(0, str(FINAL))
import modelo_final as mf  # noqa: E402
from predecir import cargar  # noqa: E402

LLUVIA_MIN = 0.1
COLUMNAS = ["quebrada_id", "hora", "H", "p_zona", "p2_quebrada", "score", "indice_0_100", "lluvia_6h_mm", "nivel", "nivel_v3"]


def con_nivel_m3(T, X, umbrales):
    """T: tabla operativa de v3 (columna nivel = v3). X: variables por hora (incluye i6h). Agrega lluvia_6h_mm y el nivel M3 por defecto."""
    T = T.rename(columns={"nivel": "nivel_v3"})
    T["lluvia_6h_mm"] = T.hora.map(X.i6h).round(2)
    rojo_u = T.H.map({H: v["rojo"] for H, v in umbrales.items()})
    amar_u = T.H.map({H: v["amarillo"] for H, v in umbrales.items()})
    supera = T.p_zona >= rojo_u
    llueve = T.lluvia_6h_mm > LLUVIA_MIN
    T["nivel"] = np.where(supera & llueve, "rojo", np.where(supera | (T.p_zona >= amar_u), "amarillo", "verde"))
    return T[COLUMNAS]


def hora(t, csv=None):
    m, u, p2 = cargar()
    horas = pd.DatetimeIndex([pd.Timestamp(t).floor("h")])
    X = mf.variables_horarias(horas)
    T = con_nivel_m3(mf.tabla_operativa(m, u, p2, X), X, u).sort_values(["H", "score"], ascending=[True, False])
    if csv:
        T.to_csv(csv, index=False)
    return T


def ejemplo(temporada="2022-23"):
    """Igual que modelo_final.ejemplo (modelo, P2 y umbrales calibrados SIN la temporada), con el nivel M3 por defecto."""
    z = mf.tabla_zona()
    m = mf.ajustar(z[z.temporada != temporada])
    u = mf.umbrales_oof(excluir=temporada)
    for H in mf.HS:
        u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
    p2 = mf.p2_tabla(lambda torm: torm.loc[torm.temporada != temporada, "tormenta"])
    a0 = int(temporada[:4])
    horas = pd.date_range(f"{a0}-12-01", f"{a0 + 1}-04-30 23:00", freq="h")
    X = mf.variables_horarias(horas)
    T = con_nivel_m3(mf.tabla_operativa(m, u, p2, X), X, u)
    T["p_zona"], T["score"], T["p2_quebrada"] = T.p_zona.round(5), T.score.round(5), T.p2_quebrada.round(4)
    T.to_csv(AQUI / f"ejemplo_{temporada.replace('-', '_')}_m3.csv", index=False)
    una = T[T.quebrada_id == T.quebrada_id.iloc[0]]
    print(f"{len(T):,} filas. Horas por nivel (M3 por defecto | v3):")
    print(pd.concat([una.groupby(["H", "nivel"]).size().unstack(fill_value=0).add_prefix("M3_"),
                     una.groupby(["H", "nivel_v3"]).size().unstack(fill_value=0).add_prefix("v3_")], axis=1).to_string())
    return T


if __name__ == "__main__":
    if sys.argv[1] == "ejemplo":
        ejemplo()
    else:
        csv = sys.argv[sys.argv.index("--csv") + 1] if "--csv" in sys.argv else None
        pd.set_option("display.width", 220)
        print(hora(sys.argv[2], csv)[lambda d: d.H == 3].round(4).to_string(index=False))

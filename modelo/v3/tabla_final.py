"""Tabla final v3: TSS, acierto, falsas alarmas y % de alertas en 2024-25 (con IC 90 % por bootstrap de tormentas) de A1, A2, B1, B2 y E y las referencias.
Unidad: EVENTO de lluvia (A, B) o ZONA-DÍA (E; modelo del mismo día). Lee los CSV de cada fase.
"""
from pathlib import Path

import pandas as pd

V3 = Path(__file__).resolve().parent
FUENTES = [("A", V3 / "A" / "fase_a_resumen.csv", "evento"), ("B1", V3 / "B" / "fase_b1_resumen.csv", "evento"),
           ("B2", V3 / "B" / "fase_b2_resumen.csv", "evento"), ("E", V3 / "E" / "fase_e_resumen.csv", "zona-día (mismo día)")]


def main():
    filas = []
    for fase, ruta, unidad in FUENTES:
        if not ruta.exists():
            filas.append(dict(fase=fase, metodo="(no completada)", unidad=unidad))
            continue
        d = pd.read_csv(ruta)
        d = d.rename(columns={"acierto_POD": "POD", "falsas_POFD": "POFD"})
        for r in d.itertuples():
            filas.append(dict(fase=fase, metodo=r.metodo, unidad=unidad, TSS=r.TSS, TSS_ic90=r.TSS_ic90, acierto_POD=r.POD, falsas_POFD=r.POFD,
                              pct_alertas_2024_25=r.pct_alertas_2024_25))
    t = pd.DataFrame(filas)
    t.to_csv(V3 / "tabla_final.csv", index=False)
    pd.set_option("display.width", 220)
    print(t.to_string(index=False))
    return t


if __name__ == "__main__":
    main()

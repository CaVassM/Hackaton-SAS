"""Tabla de pesos IMERG -> quebrada (`lluvia/pesos_imerg.csv`).

Cada fila: fracción del área de una quebrada que cae en una celda de IMERG (0.1°).
Los pesos de cada quebrada suman 1. Lluvia de la quebrada = Σ peso × lluvia de la celda.

Uso:  python lluvia/pesos_imerg.py
"""
from pathlib import Path

from imerg_utils import bbox_quebradas, calcular_pesos, centros_imerg, leer_quebradas

SALIDA = Path(__file__).resolve().parent / "pesos_imerg.csv"


def main():
    gdf = leer_quebradas()
    lon0, lat0, lon1, lat1 = bbox_quebradas(margen=0)
    lon_c, lat_c = centros_imerg(lon0, lon1, lat0, lat1)
    pesos = calcular_pesos(gdf, lon_c, lat_c)
    pesos.drop(columns=["i_lat", "i_lon"]).round(6).to_csv(SALIDA, index=False)

    suma = pesos.groupby("quebrada_id")["peso"].sum()
    assert ((suma - 1).abs() < 1e-9).all(), "los pesos de cada quebrada deben sumar 1"
    celdas = pesos[["lat_centro", "lon_centro"]].drop_duplicates()
    por_q = pesos.groupby("quebrada_id").size()
    # Quebradas con exactamente el mismo conjunto de celdas y pesos casi iguales comparten la serie de lluvia
    firma = pesos.assign(c=list(zip(pesos.lat_centro, pesos.lon_centro))).groupby("quebrada_id")["c"].apply(tuple)
    grupos = firma.groupby(firma).apply(lambda s: sorted(s.index)).tolist()

    print(f"Guardado: {SALIDA}  ({len(pesos)} filas)")
    print(f"Celdas IMERG distintas que tocan las 17 quebradas: {len(celdas)}")
    print(f"Celdas por quebrada: min {por_q.min()}, máx {por_q.max()}")
    print("Grupos de quebradas con el mismo conjunto de celdas:")
    for g in grupos:
        print("  -", ", ".join(g))


if __name__ == "__main__":
    main()

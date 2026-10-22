"""01 - Variables del modelo. Lee inputs/ y arma la tabla de ZONA: una fila = la zona (17 quebradas) en una hora y un horizonte H, con su etiqueta.

Variables (todas conocidas en la hora t; ver _lib.py):
  intensidad (IMERG Early, máximo entre las 5 celdas, solo lluvia con etiqueta <= t-5 por la latencia de 4 h):
    i1h, i3h, i6h (lluvia de 1/3/6 h), i1h_max6, i3h_max6, i6h_max6 (su máximo en las últimas 6 h disponibles), p24h, p48h, p72h
  estado: hum_suelo_5d (humedad del suelo de hace 5 días), dias_activ (días desde la última activación catalogada), icen (último ICEN publicado)
  H (3, 6, 12, 24)
Equivale a modelo/v3/final/modelo_final.py tabla_zona (repo).
Salida: salidas/trabajo/tabla_zona.parquet     Uso: python entrega_modelo/scripts/01_features.py
"""
import _lib as L


def main():
    z = L.tabla_zona()
    L.TRABAJO.mkdir(parents=True, exist_ok=True)
    z.to_parquet(L.TRABAJO / "tabla_zona.parquet", index=False)
    print(f"Tabla de zona: {len(z):,} filas ({z.hora.nunique():,} horas x {z.H.nunique()} H), {z.temporada.nunique()} temporadas")
    print("Horas con huaico (y = 1) por H:", z.groupby("H").y.sum().astype(int).to_dict(), "| sin etiqueta (NaN):", int(z.y.isna().sum()))
    print("% de valores faltantes por variable:", {c: round(100 * z[c].isna().mean(), 1) for c in L.VARIABLES if c != "H"})


if __name__ == "__main__":
    main()

"""
Catálogo de huaicos de Lurigancho-Chosica -> etiquetas para el modelo.

Paso 1. Unir las partes del catálogo y normalizar nombres.
Paso 2. Clasificar qué representa cada hora (huaico, lluvia o publicación).
Paso 3. Construir etiquetas horarias (horizonte H) y diarias por quebrada.
Paso 4. Resumen: cuántos eventos sirven para cada tipo de modelo.

Uso:
    python construir_catalogo.py            # H = 6 horas por defecto
    python construir_catalogo.py --H 12
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CARPETA = Path(__file__).parent
PARTES = ["parte_2015_2017.csv", "parte_2018_2021.csv", "parte_2022_2026.csv"]
DISTRITO_PILOTO = "Lurigancho-Chosica"

# Mismo cauce escrito de formas distintas en las fuentes
NOMBRES = {
    "Carosio": "Carossio",
    "La Libertad": "Libertad",
    "El Pedregal": "Pedregal",
    "San Antonio": "San Antonio de Pedregal",
    "San Antonio (de Pedregal)": "San Antonio de Pedregal",
    "Vallecito (Vizcachera-Vallecito)": "El Vallecito",
    "Alto Perú (tres quebradas sin nombre)": "Alto Perú",
    "Huaycoloro 1": "Huaycoloro",
    "Huaycoloro 2": "Huaycoloro",
    "Río Seco 2": "Rioseco",
    "Inca Kola (paradero)": "Inca Kola",
}

# Días en que una fuente oficial puso en duda que fuera huaico
DUDOSOS = {
    "2019-02-25": "INDECI: 'Esto no es huaico, es agua que está bajando de las quebradas'",
}


# ---------------------------------------------------------------- Paso 1
def cargar_catalogo() -> pd.DataFrame:
    cat = pd.concat([pd.read_csv(CARPETA / p, dtype=str) for p in PARTES], ignore_index=True)
    cat = cat.fillna("")
    cat["quebrada"] = cat["quebrada"].str.strip().replace(NOMBRES)
    cat["en_piloto"] = cat["distrito"].eq(DISTRITO_PILOTO)
    cat = cat.sort_values(["fecha", "hora_inicio", "quebrada"]).reset_index(drop=True)
    cat.insert(0, "id", [f"EV{i+1:03d}" for i in range(len(cat))])
    return cat


# ---------------------------------------------------------------- Paso 2
def referencia_hora(texto: str) -> str:
    """¿La hora registrada es la del huaico, la de la lluvia o la de una publicación?"""
    t = texto.lower()
    if not t:
        return "sin_hora"
    if any(k in t for k in ["lluvia", "llovido", "lluvias intensas que caus"]):
        return "lluvia"
    if any(k in t for k in ["hora del reporte", "nota ", "entrada", "alertó", "minutos después"]):
        return "publicacion"
    return "huaico"


def agregar_tiempos(cat: pd.DataFrame) -> pd.DataFrame:
    cat["referencia_hora"] = cat["hora_texto"].map(referencia_hora)
    cat.loc[cat["hora_inicio"].eq(""), "referencia_hora"] = "sin_hora"

    # Formato explícito: si pandas lo adivina desde una fila sin hora, todas las demás fallan en silencio
    fmt = "%Y-%m-%d %H:%M"
    ini = pd.to_datetime(cat["fecha"] + " " + cat["hora_inicio"], format=fmt, errors="coerce")
    fin = pd.to_datetime(cat["fecha"] + " " + cat["hora_fin"], format=fmt, errors="coerce")
    fin = fin.where(fin >= ini, fin + pd.Timedelta(days=1))  # ventanas que cruzan la medianoche
    cat["dt_inicio"], cat["dt_fin"] = ini, fin

    cat["dudoso"] = cat["fecha"].map(DUDOSOS).fillna("")
    # Sirve para el modelo HORARIO si sabemos la quebrada y la hora apunta al huaico
    cat["usable_horario"] = (
        cat["en_piloto"]
        & cat["quebrada"].ne("")
        & cat["conf_temporal"].isin(["A", "B"])
        & cat["referencia_hora"].isin(["huaico", "publicacion"])
    )
    return cat


# ---------------------------------------------------------------- Paso 3
def etiquetas_horarias(cat, quebradas, desde, hasta, H=6, horas_post=24):
    """
    Tabla quebrada x hora con:
      y = 1   el huaico ocurre en las próximas H horas
      y = 0   no hay evento conocido (OJO: 'sin noticia', no 'cero seguro')
      y = NaN excluir: hora ambigua, posterior al evento o día sin detalle
    """
    horas = pd.date_range(desde, hasta, freq="h")
    y = pd.DataFrame(0.0, index=horas, columns=quebradas)
    pos = pd.DataFrame(False, index=horas, columns=quebradas)

    def marcar(df, a, b, cols, valor):
        a, b = max(a, horas[0]), min(b, horas[-1])
        if a <= b:
            df.loc[a:b, cols] = valor

    eventos = cat[cat["en_piloto"]]
    for _, ev in eventos.iterrows():
        dia = pd.Timestamp(ev["fecha"])
        cols = [ev["quebrada"]] if ev["quebrada"] in quebradas else quebradas  # sin quebrada -> todas

        if ev["usable_horario"] and ev["quebrada"] in quebradas:
            ini, fin = ev["dt_inicio"], ev["dt_fin"]
            # 1 si el huaico cae dentro de (t, t+H]. Ej.: huaico 15:10, H=6 -> horas 10:00 a 15:00
            primera = (ini - pd.Timedelta(hours=H)).ceil("h")
            ultima = (ini - pd.Timedelta(minutes=1)).floor("h")
            marcar(pos, primera, ultima, cols, True)
            # dentro de la ventana de incertidumbre y después del evento: excluir
            marcar(y, ini.ceil("h"), fin + pd.Timedelta(hours=horas_post), cols, np.nan)
        else:
            # sin hora útil o sin quebrada: no sabemos qué horas fueron, se excluye el día
            marcar(y, dia - pd.Timedelta(hours=H), dia + pd.Timedelta(hours=24 + horas_post), cols, np.nan)

    y[pos] = 1.0
    largo = y.stack(future_stack=True).rename("y").reset_index()
    largo.columns = ["hora", "quebrada", "y"]
    return largo


def etiquetas_diarias(cat, quebradas, desde, hasta):
    """Tabla quebrada x día: 1 si se activó ese día; NaN si hubo evento sin quebrada identificada."""
    dias = pd.date_range(desde, hasta, freq="D")
    y = pd.DataFrame(0.0, index=dias, columns=quebradas)
    ev = cat[cat["en_piloto"]]
    for _, e in ev[ev["quebrada"].eq("")].iterrows():
        y.loc[pd.Timestamp(e["fecha"]), :] = np.nan
    for _, e in ev[ev["quebrada"].isin(quebradas)].iterrows():
        y.loc[pd.Timestamp(e["fecha"]), e["quebrada"]] = 1.0
    largo = y.stack(future_stack=True).rename("y").reset_index()
    largo.columns = ["dia", "quebrada", "y"]
    return largo


# ---------------------------------------------------------------- Paso 4
def resumen(cat):
    p = cat[cat["en_piloto"]]
    print("=== Catálogo ===")
    print(f"Filas totales: {len(cat)}  |  Lurigancho-Chosica: {len(p)}  |  distritos vecinos: {(~cat['en_piloto']).sum()}")
    print(f"Días con evento en el piloto: {p['fecha'].nunique()}")
    print(f"Quebradas distintas en el piloto: {p.loc[p['quebrada'].ne(''), 'quebrada'].nunique()}")

    print("\n=== Por año (piloto) ===")
    por_anio = p.assign(anio=p["fecha"].str[:4]).groupby("anio").agg(
        dias=("fecha", "nunique"), activaciones=("id", "count"), usables_horario=("usable_horario", "sum")
    )
    print(por_anio.to_string())

    print("\n=== ¿Qué representa la hora registrada? (piloto) ===")
    print(p["referencia_hora"].value_counts().to_string())

    print("\n=== Confianza temporal x espacial (piloto) ===")
    print(pd.crosstab(p["conf_temporal"], p["conf_espacial"]).to_string())

    u = p[p["usable_horario"]]
    print("\n=== Usables para el modelo horario ===")
    print(f"Activaciones: {len(u)}  |  días: {u['fecha'].nunique()}")
    print(f"  2015-2020 (ventana PISCOp_h): {u[u['fecha'] < '2021'].shape[0]} activaciones, "
          f"{u.loc[u['fecha'] < '2021', 'fecha'].nunique()} días")
    print(f"  2021-2026 (estación horaria Chosica): {u[u['fecha'] >= '2021'].shape[0]} activaciones, "
          f"{u.loc[u['fecha'] >= '2021', 'fecha'].nunique()} días")
    print(f"  De ellas en días dudosos: {u['dudoso'].ne('').sum()}")

    print("\n=== Quebradas con más activaciones (piloto) ===")
    print(p.loc[p["quebrada"].ne(""), "quebrada"].value_counts().head(12).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--H", type=int, default=6, help="horizonte de predicción en horas")
    args = ap.parse_args()

    cat = agregar_tiempos(cargar_catalogo())
    columnas = ["id", "fecha", "hora_texto", "hora_inicio", "hora_fin", "referencia_hora", "quebrada",
                "sector", "distrito", "en_piloto", "conf_temporal", "conf_espacial", "usable_horario",
                "dudoso", "fuente", "url", "notas"]
    cat[columnas].to_csv(CARPETA / "catalogo_huaicos_chosica.csv", index=False)
    resumen(cat)

    quebradas = sorted(cat.loc[cat["en_piloto"] & cat["quebrada"].ne(""), "quebrada"].unique())
    horarias = etiquetas_horarias(cat, quebradas, "2015-01-01", "2026-06-30 23:00", H=args.H)
    diarias = etiquetas_diarias(cat, quebradas, "2015-01-01", "2026-06-30")

    print(f"\n=== Etiquetas horarias 2015-2026, H = {args.H} h ===")
    print(horarias["y"].value_counts(dropna=False).rename({1.0: "y=1", 0.0: "y=0"}).to_string())
    pos = horarias[horarias["y"].eq(1)]
    print(f"Horas positivas: {len(pos)}  |  activaciones que las generan: "
          f"{pos.groupby('quebrada')['hora'].apply(lambda s: (s.diff() != pd.Timedelta(hours=1)).sum()).sum()}")
    print("\n=== Etiquetas diarias 2015-2026 ===")
    print(diarias["y"].value_counts(dropna=False).rename({1.0: "y=1", 0.0: "y=0"}).to_string())

    horarias.to_parquet(CARPETA / f"etiquetas_horarias_H{args.H}.parquet", index=False)
    diarias.to_parquet(CARPETA / "etiquetas_diarias.parquet", index=False)

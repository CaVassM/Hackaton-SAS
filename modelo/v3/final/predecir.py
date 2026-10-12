"""Predicción operativa con el modelo final v3 (p1_b1.json + metadatos_final.json + p2_final.csv).

Uso: python modelo/v3/final/predecir.py "2023-03-14 13:00" [--csv salida.csv]
Devuelve la tabla operativa de la hora t (hora local de inicio): quebrada_id, hora, H, p_zona, p2_quebrada, score, indice_0_100, nivel (17 x 4 filas).

Datos que necesita en t (ver metadatos_final.json, "fuentes_operativas"):
  - IMERG Early de las 5 celdas hasta la hora con etiqueta t-5 (latencia 4 h) y 72 h hacia atrás: aquí se leen de lluvia/datos/early (lluvia_celdas);
    en operación hay que bajar los gránulos recientes (lluvia/descargar_imerg.py).
  - Humedad del suelo ERA5-Land de t - 5 días (Open-Meteo archive API; aquí datos/raw/openmeteo/era5_land.parquet).
  - ICEN publicado (met.igp.gob.pe/datos/ICEN.txt; aquí datos/raw/icen/ICEN.txt).
  - Catálogo de activaciones hasta el día anterior (aquí catalogo_huaicos_chosica.csv; en operación: registro de INDECI/municipio).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from modelo_final import HS, tabla_operativa, variables_horarias  # noqa: E402


def cargar():
    m = xgb.XGBClassifier()
    m.load_model(AQUI / "p1_b1.json")
    meta = json.loads((AQUI / "metadatos_final.json").read_text(encoding="utf-8"))
    u = {int(H): v for H, v in meta["umbrales"].items()}
    p2 = pd.read_csv(AQUI / "p2_final.csv", index_col=0).iloc[:, 0]
    return m, u, p2


def predecir(t):
    m, u, p2 = cargar()
    horas = pd.DatetimeIndex([pd.Timestamp(t).floor("h")])
    X = variables_horarias(horas)
    if X.drop(columns=["dias_activ"]).isna().any(axis=None):
        print("AVISO: faltan datos en t para algunas variables (NaN): " + ", ".join(X.columns[X.isna().any()]), file=sys.stderr)
    return tabla_operativa(m, u, p2, X).sort_values(["H", "score"], ascending=[True, False])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("t")
    ap.add_argument("--csv")
    a = ap.parse_args()
    T = predecir(a.t)
    if a.csv:
        T.to_csv(a.csv, index=False)
    pd.set_option("display.width", 200)
    print(T[T.H == HS[0]].round(4).to_string(index=False))

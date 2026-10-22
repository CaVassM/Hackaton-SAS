"""ERA5 y ERA5-Land horarios desde la API histórica de Open-Meteo (sin credenciales; los datos son los de Copernicus re-servidos).

  - era5_land: soil_moisture_0_to_7cm, soil_moisture_7_to_28cm, precipitation en las 5 celdas IMERG de las quebradas, 2014-11-01 a 2026-04-30 (B1).
  - era5     : precipitation, showers (~ precipitación convectiva), total_column_integrated_water_vapour en la grilla 0.25° de
               lat -12.5..-11.25 x lon -77.25..-75.75 (42 puntos), 25-nov a 30-abr de cada temporada 2014-15..2025-26 (B2).
               CAPE, K index y Total Totals NO están en Open-Meteo (dan "undefined"): requieren CDS (credenciales del usuario).
Convención: Open-Meteo marca cada hora al FINAL del intervalo (lluvia de la hora previa) en hora de Lima. Aquí se re-etiqueta al INICIO de la hora
local (hora = timestamp - 1 h), como el resto del proyecto. Las variables instantáneas (humedad, TCWV) también se corren 1 h (quedan como el valor
al final de la hora etiquetada: conocido en t+1 h; las features deben usarlas con retraso >= 1 h).
Salida: datos/raw/openmeteo/{era5_land,era5}.parquet (hora, lat, lon, variables). Reanuda por (punto, periodo).
Uso: python modelo/v3/datos/descargar_openmeteo.py [--solo era5_land | --solo era5]
(La copia de era5_land.parquet usada para entrenar el modelo v3 está versionada en git.)
"""
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
DEST = AQUI / "raw" / "openmeteo"
URL = "https://archive-api.open-meteo.com/v1/archive"
CELDAS = [(-11.95, -76.85), (-11.95, -76.75), (-11.95, -76.65), (-11.85, -76.75), (-11.85, -76.65)]
GRILLA = [(round(la, 2), round(lo, 2)) for la in np.arange(-12.5, -11.24, 0.25) for lo in np.arange(-77.25, -75.74, 0.25)]
V_LAND = "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,precipitation"
V_ERA5 = "precipitation,showers,total_column_integrated_water_vapour"


def pedir(lat, lon, ini, fin, variables, modelo, reintentos=6):
    q = f"{URL}?latitude={lat}&longitude={lon}&start_date={ini}&end_date={fin}&hourly={variables}&models={modelo}&timezone=America%2FLima"
    for k in range(reintentos):
        try:
            with urllib.request.urlopen(q, timeout=180) as r:
                d = json.loads(r.read())
            h = pd.DataFrame(d["hourly"])
            h["hora"] = pd.to_datetime(h.pop("time")) - pd.Timedelta(hours=1)
            return h.assign(lat=lat, lon=lon, lat_om=d["latitude"], lon_om=d["longitude"])
        except Exception as e:  # noqa: BLE001
            print(f"  reintento {k + 1} {lat},{lon} {ini}: {repr(e)[:100]}", flush=True)
            time.sleep(20 * (k + 1))
    raise RuntimeError(f"falló {lat},{lon} {ini}")


def bajar(nombre, puntos, periodos, variables, modelo):
    cache = DEST / f"_{nombre}"
    cache.mkdir(parents=True, exist_ok=True)
    for la, lo in puntos:
        for ini, fin in periodos:
            f = cache / f"{la}_{lo}_{ini}.parquet"
            if not f.exists():
                pedir(la, lo, ini, fin, variables, modelo).to_parquet(f, index=False)
                time.sleep(1.5)
        print(f"{nombre}: punto {la},{lo} listo", flush=True)
    pd.concat([pd.read_parquet(x) for x in sorted(cache.glob("*.parquet"))]).to_parquet(DEST / f"{nombre}.parquet", index=False)


def main():
    import sys

    solo = sys.argv[sys.argv.index("--solo") + 1] if "--solo" in sys.argv else None   # --solo era5_land: lo único que usa el modelo final v3
    land = [(f"{a}-01-01" if a > 2014 else "2014-11-01", f"{a}-12-31" if a < 2026 else "2026-04-30") for a in range(2014, 2027)]
    era5 = [(f"{a}-11-25", f"{a + 1}-04-30") for a in range(2014, 2026)]
    if solo in (None, "era5_land"):
        bajar("era5_land", CELDAS, land, V_LAND, "era5_land")
    if solo in (None, "era5"):
        bajar("era5", GRILLA, era5, V_ERA5, "era5")
    print("TERMINADO", flush=True)


if __name__ == "__main__":
    main()

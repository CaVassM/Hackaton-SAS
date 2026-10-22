"""Verifica que la descarga AMPLIADA de IMERG Early (lluvia/datos/early_ampliado, lat -12.3..-11.5, lon -77.0..-76.0) da EXACTAMENTE
los mismos valores que la descarga original (lluvia/datos/early) en las 12 celdas que ambas comparten (incluidas las 5 de las quebradas).

Uso: python lluvia/verificar_ampliado.py
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

AQUI = Path(__file__).resolve().parent
ORIG, AMPL = AQUI / "datos" / "early", AQUI / "datos" / "early_ampliado"


def main():
    pesos = pd.read_csv(AQUI / "pesos_imerg.csv")
    celdas_q = set(zip(pesos.lat_centro.round(2), pesos.lon_centro.round(2)))
    meses = sorted(Path(f).name for f in glob.glob(str(ORIG / "imerg_early_????-??.nc")))
    faltan = [m for m in meses if not (AMPL / m).exists()]
    print(f"Meses originales: {len(meses)} | faltan en la ampliada: {len(faltan)} {faltan[:5]}")
    peor, n_val, n_nan_dif, tam = 0.0, 0, 0, None
    for m in meses:
        if m in faltan:
            continue
        with xr.open_dataset(ORIG / m) as a, xr.open_dataset(AMPL / m) as b:
            tam = dict(b.sizes)
            bb = b["mm_h"].sel(lat=a.lat, lon=a.lon, method="nearest", tolerance=0.011)
            assert (a.time.values == bb.time.values).all(), f"{m}: tiempos distintos"
            x, y = a["mm_h"].values, bb.values
            n_nan_dif += int((np.isnan(x) != np.isnan(y)).sum())
            ok = ~np.isnan(x) & ~np.isnan(y)
            n_val += int(ok.sum())
            peor = max(peor, float(np.abs(x[ok] - y[ok]).max()) if ok.any() else 0.0)
    print(f"Recuadro ampliado: {tam} | celdas de las quebradas: {sorted(celdas_q)}")
    print(f"Comparados {n_val:,} valores (12 celdas x 30 min) | diferencia máxima {peor:.2e} mm/h | NaN en uno y no en el otro: {n_nan_dif}")
    print("IDÉNTICAS" if peor == 0 and n_nan_dif == 0 and not faltan else "HAY DIFERENCIAS: revisar antes de usar la descarga ampliada")


if __name__ == "__main__":
    main()

"""Paso 8.3: ¿IMERG Early deriva entre temporadas? Compara, mes por mes, IMERG Early, IMERG Final (calibrado con pluviómetros) y ERA5.

Final solo se descarga para unos meses (lluvia/datos/final/, ver comandos abajo). Para cada mes con Final (media de las 17 quebradas, hora local):
total del mes en cada fuente, razones Early/Final, Final/ERA5 y Early/ERA5, y correlación diaria Early-Final.
Si Early/Final es estable (~constante) y lo que cambia es ERA5, el problema es ERA5; si Early/Final cambia con los años, Early deriva.

Descarga (PowerShell, desde la raíz del proyecto; un mes de Final tarda lo mismo que uno de Early; ya reanuda por caché):
  foreach ($m in "2015-03","2017-03","2019-02","2021-02","2022-02","2023-03","2024-02","2025-02","2026-02") {
    & C:\\Users\\Camil\\anaconda3\\python.exe lluvia\\descargar_masivo.py --producto final --solo $m --procesos 24 --url-directa }
Uso:  python lluvia/comparar_early_final.py   (salida: lluvia/salida/comparar_early_final.csv)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent / "modelo"))
import features_lluvia as fl  # noqa: E402


def main(carpeta_early=AQUI / "datos" / "early", carpeta_final=AQUI / "datos" / "final"):
    from diagnostico_era5_ciegos import era5_por_quebrada

    pesos = pd.read_csv(AQUI / "pesos_imerg.csv")
    if not list(Path(carpeta_final).glob("imerg_final_*.nc")):
        raise SystemExit(f"No hay meses de Final en {carpeta_final}: corre primero los comandos de descarga (ver el encabezado).")
    F = fl.lluvia_horaria(carpeta_final, pesos).mean(axis=1)
    E = fl.lluvia_horaria(carpeta_early, pesos).mean(axis=1)
    A = era5_por_quebrada().mean(axis=1)
    ok = F.dropna().index
    d = pd.DataFrame({"final": F.loc[ok], "early": E.reindex(ok), "era5": A.reindex(ok)}).dropna()
    filas = []
    for (a, m), g in d.groupby([d.index.year, d.index.month]):
        if len(g) < 300:  # bordes de mes que quedan con pocas horas por el cambio de huso
            continue
        dia = g.resample("D").sum()
        filas.append(dict(mes=f"{a}-{m:02d}", horas=len(g), early_mm=g.early.sum(), final_mm=g.final.sum(), era5_mm=g.era5.sum(),
                          early_sobre_final=g.early.sum() / g.final.sum(), final_sobre_era5=g.final.sum() / g.era5.sum(), early_sobre_era5=g.early.sum() / g.era5.sum(),
                          corr_dia_early_final=dia.early.corr(dia.final, method="spearman"), corr_dia_final_era5=dia.final.corr(dia.era5, method="spearman")))
    t = pd.DataFrame(filas).round(2)
    (AQUI / "salida").mkdir(exist_ok=True)
    t.to_csv(AQUI / "salida" / "comparar_early_final.csv", index=False)
    pd.set_option("display.width", 220)
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()

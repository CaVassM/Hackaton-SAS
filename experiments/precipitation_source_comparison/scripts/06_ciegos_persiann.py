"""¿PERSIANN-CCS ve lluvia en los huaicos que IMERG Early no vio? (DIAGNÓSTICO sin retraso, como el paso 8.2 con ERA5; PERSIANN-CCS NO entra al modelo.)

Para cada uno de los 51 bloques de huaico de H=6 (quebrada, hora local del huaico = última hora con y=1; tabla de modelo/salida/diagnostico_era5_ciegos.csv) mide, con los pesos por cuenca de cada producto:
  - lluvia de las 6 y de las 24 horas hasta la hora del huaico (incluida), IMERG Early (ya calculada) y PERSIANN-CCS (días descargados con --eventos);
  - cuántos bloques superan 0.1 y 1 mm, y cuántos de los bloques «ciegos» de IMERG (< 0.1 mm en 6 h) ve PERSIANN-CCS;
  - si la ventana del huaico es más lluviosa que la MISMA hora del día anterior y del día siguiente (contraste dentro de la misma tormenta; no usa un percentil sobre toda la temporada
    porque solo hay descargados los días de los eventos).
PERSIANN-CCS está en UTC (verificado con 05_verificar_prueba_persiann.py): hora local t = UTC t + 5 h.
Salida: salida/ciegos_persiann.csv y salida/ciegos_persiann.txt
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(AQUI / "scripts"))
from importlib import import_module  # noqa: E402

v = import_module("05_verificar_prueba_persiann")


def main():
    fs = sorted(glob.glob(str(AQUI / "datos" / "persiann_ccs" / "persiann_ccs_????-??.nc")))
    PE = xr.concat([xr.open_dataset(f)["mm_h"].load() for f in fs], dim="time").sortby("time")
    celdas = pd.read_csv(AQUI / "salida" / "celdas_por_cuenca.csv")
    P = v.por_cuenca(PE, celdas[celdas["producto"] == "PERSIANN-CCS"]).asfreq("h")
    b = pd.read_csv(RAIZ / "modelo" / "salida" / "diagnostico_era5_ciegos.csv", parse_dates=["t_huaico"])
    h = pd.Timedelta(hours=1)
    filas = []
    for r in b.itertuples():
        u = r.t_huaico + 5 * h                                  # hora UTC del huaico
        s = P[r.quebrada]
        f = dict(quebrada=r.quebrada, t_huaico_local=r.t_huaico, IMERG_6h=r.imerg_6h, IMERG_24h=r.imerg_24h, ERA5_6h=r.era5_6h)
        f["PERSIANN_6h"] = s.loc[u - 5 * h:u].sum(min_count=6)
        f["PERSIANN_24h"] = s.loc[u - 23 * h:u].sum(min_count=24)
        for nom, serie in (("PERSIANN", s),):
            a, c = serie.loc[u - 29 * h:u - 24 * h].sum(min_count=6), serie.loc[u + 19 * h:u + 24 * h].sum(min_count=6)   # misma hora ±1 día
            f[f"{nom}_6h_dia_antes"], f[f"{nom}_6h_dia_despues"] = a, c
        filas.append(f)
    t = pd.DataFrame(filas)
    # IMERG: misma ventana de ±1 día desde su serie horaria del proyecto
    I = pd.read_parquet(RAIZ / "lluvia" / "lluvia_horaria_quebradas.parquet").pivot(index="hora", columns="quebrada_id", values="mm").asfreq("h")
    for k, r in enumerate(t.itertuples()):
        tl = r.t_huaico_local
        t.loc[k, "IMERG_6h_dia_antes"] = I[r.quebrada].loc[tl - 24 * h - 5 * h:tl - 24 * h].sum(min_count=6)
        t.loc[k, "IMERG_6h_dia_despues"] = I[r.quebrada].loc[tl + 24 * h - 5 * h:tl + 24 * h].sum(min_count=6)
    t.to_csv(AQUI / "salida" / "ciegos_persiann.csv", index=False, float_format="%.3f")
    n = len(t)
    ciego = t.IMERG_6h < 0.1
    log = []
    say = lambda s: (print(s), log.append(s))
    say(f"Bloques: {n} (tormentas: {t.t_huaico_local.dt.date.nunique()} fechas) | ciegos para IMERG (<0.1 mm en 6 h): {int(ciego.sum())} | sin dato PERSIANN: {int(t.PERSIANN_6h.isna().sum())}")
    for nom, c6, c24 in (("IMERG Early", "IMERG_6h", "IMERG_24h"), ("PERSIANN-CCS", "PERSIANN_6h", "PERSIANN_24h")):
        say(f"{nom:13s} 6h >= 0.1 mm: {int((t[c6] >= 0.1).sum()):>2}/{n} | 6h >= 1 mm: {int((t[c6] >= 1).sum()):>2}/{n} | 24h >= 1 mm: {int((t[c24] >= 1).sum()):>2}/{n} | 24h >= 5 mm: {int((t[c24] >= 5).sum()):>2}/{n} | mediana 6h {t[c6].median():.2f} mm, 24h {t[c24].median():.2f} mm")
    say(f"En los {int(ciego.sum())} bloques ciegos de IMERG: PERSIANN-CCS 6h >= 0.1 mm en {int((t.PERSIANN_6h[ciego] >= 0.1).sum())}, >= 1 mm en {int((t.PERSIANN_6h[ciego] >= 1).sum())}; 24h >= 1 mm en {int((t.PERSIANN_24h[ciego] >= 1).sum())}; mediana 6h {t.PERSIANN_6h[ciego].median():.2f} mm")
    say(f"En los {int((~ciego).sum())} no ciegos: PERSIANN-CCS 6h >= 0.1 mm en {int((t.PERSIANN_6h[~ciego] >= 0.1).sum())}, >= 1 mm en {int((t.PERSIANN_6h[~ciego] >= 1).sum())}")
    u6 = (t.IMERG_6h >= 0.1) | (t.PERSIANN_6h >= 0.1); u1 = (t.IMERG_6h >= 1) | (t.PERSIANN_6h >= 1)
    say(f"Cualquiera de los dos productos (6 h): >= 0.1 mm en {int(u6.sum())}/{n} bloques (IMERG solo: {int((t.IMERG_6h >= 0.1).sum())}); >= 1 mm en {int(u1.sum())}/{n} (IMERG solo: {int((t.IMERG_6h >= 1).sum())})")
    solo_p = t[(t.PERSIANN_6h >= 1) & (t.IMERG_6h < 0.5)]
    say(f"Bloques donde PERSIANN-CCS marca >= 1 mm en 6 h e IMERG < 0.5 mm: {len(solo_p)} ({', '.join(f'{r.quebrada} {pd.Timestamp(r.t_huaico_local):%Y-%m-%d}' for r in solo_p.itertuples())})")
    solo_i = t[(t.IMERG_6h >= 1) & (t.PERSIANN_6h < 0.5)]
    say(f"Bloques donde IMERG marca >= 1 mm en 6 h y PERSIANN-CCS < 0.5 mm: {len(solo_i)} ({', '.join(f'{r.quebrada} {pd.Timestamp(r.t_huaico_local):%Y-%m-%d}' for r in solo_i.itertuples())})")
    for nom in ("IMERG", "PERSIANN"):
        mas = ((t[f"{nom}_6h"] > t[f"{nom}_6h_dia_antes"].fillna(-1)) & (t[f"{nom}_6h"] > t[f"{nom}_6h_dia_despues"].fillna(-1)) & t[f"{nom}_6h"].notna())
        say(f"{nom}: la ventana de 6 h del huaico es más lluviosa que la misma hora del día anterior Y del siguiente en {int(mas.sum())}/{n} bloques")
    say(f"Correlación (Spearman) entre IMERG y PERSIANN-CCS en la lluvia de 24 h hasta el huaico: {t.IMERG_24h.corr(t.PERSIANN_24h, method='spearman'):.2f}; en la de 6 h: {t.IMERG_6h.corr(t.PERSIANN_6h, method='spearman'):.2f}")
    (AQUI / "salida" / "ciegos_persiann.txt").write_text("\n".join(log) + "\n")


if __name__ == "__main__":
    main()

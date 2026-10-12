"""Verificación de la PRUEBA real de PERSIANN-CCS (02_descargar_persiann_ccs.py --prueba): control de calidad, zona horaria y comparación puntual con IMERG Early.

Lee datos/persiann_ccs/persiann_ccs_*.nc (los 4 meses de la prueba: 2015-03, 2024-12, 2025-02, 2026-10) y IMERG Early (lluvia/datos/early). TODO en UTC y con la etiqueta = INICIO de la hora
(README de PERSIANN-CCS: HH:00 a HH:59; la zona horaria no está declarada: aquí se verifica).
  1. QC: rango, % de NaN, múltiplos de 0.01 (escala x100), horas con lluvia.
  2. ZONA HORARIA: correlación horaria PERSIANN vs IMERG (promedio de las 17 cuencas) con desfases de -6 a +6 h en cada ventana. Si PERSIANN está en UTC y ambos ven la misma
     tormenta, el mejor desfase debe ser 0. Con solo 24-48 h por ventana es una verificación burda, no una calibración; las ventanas sin lluvia no sirven.
  3. Quirio, 23/03/2015: lluvia horaria de ambos productos a lo largo de las horas UTC 12-24 (hora local = UTC - 5); el huaico fue a las 15:10 locales (20:10 UTC).
Salida: salida/verificacion_prueba_persiann.txt y .csv
"""
import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "lluvia"))
import features_lluvia as fl  # noqa: E402

LAGS = range(-6, 7)


def por_cuenca(da, pesos):
    out = {}
    for q, g in pesos.groupby("quebrada_id"):
        s = 0
        for r in g.itertuples():
            s = s + r.peso_cuenca_en_celda * da.sel(lat=r.lat_centro, lon=r.lon_centro, method="nearest", tolerance=0.011).to_series()
        out[q] = s
    return pd.DataFrame(out).astype("float64")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos-persiann", default=str(AQUI / "datos" / "persiann_ccs"))
    ap.add_argument("--salida", default=str(AQUI / "salida"))
    a = ap.parse_args()
    log = []
    say = lambda s="": (print(s), log.append(s))
    fs = sorted(glob.glob(str(Path(a.datos_persiann) / "persiann_ccs_????-??.nc")))
    if not fs:
        raise SystemExit(f"No hay archivos persiann_ccs_*.nc en {a.datos_persiann}")
    PE = xr.concat([xr.open_dataset(f)["mm_h"].load() for f in fs], dim="time").sortby("time")
    celdas = pd.read_csv(AQUI / "salida" / "celdas_por_cuenca.csv")
    P = por_cuenca(PE, celdas[celdas["producto"] == "PERSIANN-CCS"])
    IM = fl._horario(RAIZ / "lluvia" / "datos" / "early")                  # hora LOCAL (UTC-5); se devuelve a UTC
    IM = IM.assign_coords(time=IM.time.values + np.timedelta64(5, "h"))
    I = por_cuenca(IM, celdas[celdas["producto"] == "IMERG"])
    say(f"Archivos: {[Path(f).name for f in fs]} | horas PERSIANN: {len(P)} | rango UTC {P.index.min()} -> {P.index.max()}")
    v = PE.values
    say(f"QC: mínimo {np.nanmin(v):.2f}, máximo {np.nanmax(v):.2f} mm/h | NaN {100 * np.isnan(v).mean():.1f} % | múltiplos de 0.01: {bool(np.allclose(np.round(v[~np.isnan(v)] * 100), v[~np.isnan(v)] * 100, atol=1e-3))} | horas-píxel con >= 0.1 mm/h: {100 * np.nanmean(v >= 0.1):.1f} %")
    # --- ventanas = días consecutivos presentes
    dias = sorted(set(P.index.normalize()))
    ventanas, cur = [], [dias[0]]
    for d in dias[1:]:
        (cur.append(d) if (d - cur[-1]).days == 1 else (ventanas.append(cur), cur := [d]))
    ventanas.append(cur)
    filas = []
    say("\nZONA HORARIA: correlación PERSIANN(t+lag) vs IMERG(t), promedio de las 17 cuencas; lag > 0 = PERSIANN está atrasado respecto a IMERG")
    for w in ventanas:
        t0, t1 = w[0], w[-1] + pd.Timedelta(hours=23)
        ix = P.loc[t0:t1].index.intersection(I.index)
        if len(ix) == 0:
            say(f"  {t0.date()} a {t1.date()}: IMERG Early no cubre esas fechas (se omite)"); continue
        p, i = P.mean(axis=1), I.mean(axis=1)
        res = {}
        for lag in LAGS:
            x, y = p.shift(-lag).reindex(ix), i.reindex(ix)
            m = x.notna() & y.notna()
            res[lag] = x[m].corr(y[m]) if m.sum() > 6 and x[m].std() > 0 and y[m].std() > 0 else np.nan
        tot_p, tot_i = p.reindex(ix).sum(), i.reindex(ix).sum()
        mejor = max((l for l in res if pd.notna(res[l])), key=lambda l: res[l], default=None)
        say(f"  {t0.date()} a {t1.date()} ({len(ix)} h): lluvia total media PERSIANN {tot_p:.1f} mm, IMERG {tot_i:.1f} mm | mejor desfase {mejor} h (r={res.get(mejor, np.nan):.2f}; r a 0 h = {res[0]:.2f}) | " + ("SIN lluvia suficiente: no concluyente" if min(tot_p, tot_i) < 2 else "con lluvia"))
        filas.append(dict(ventana=f"{t0.date()}..{t1.date()}", horas=len(ix), total_PERSIANN_mm=tot_p, total_IMERG_mm=tot_i, mejor_desfase_h=mejor, **{f"r_lag{l}": res[l] for l in LAGS}))
    pd.DataFrame(filas).to_csv(Path(a.salida) / "verificacion_prueba_persiann.csv", index=False)
    # --- Quirio 23/03/2015
    t = pd.date_range("2015-03-23 12:00", "2015-03-24 00:00", freq="h")
    if "quirio" in P.columns and t[0] in P.index:
        q = pd.DataFrame({"UTC": t.strftime("%H:%M"), "local": (t - pd.Timedelta(hours=5)).strftime("%H:%M"), "PERSIANN_mm": P["quirio"].reindex(t).round(2).values,
                          "IMERG_Early_mm": I["quirio"].reindex(t).round(2).values})
        say("\nQuirio 23/03/2015 (huaico a las 15:10 locales = 20:10 UTC):\n" + q.to_string(index=False))
    (Path(a.salida) / "verificacion_prueba_persiann.txt").write_text("\n".join(log) + "\n")


if __name__ == "__main__":
    main()

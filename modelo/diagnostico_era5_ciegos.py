"""Paso 8.2: los huaicos "ciegos" de IMERG, ¿los ve ERA5? (SOLO validación: ERA5 no entra al modelo.)

Para cada bloque de H=6 (quebrada, hora del huaico = última hora con y=1) compara IMERG Early y ERA5 en la ventana de 6 h hasta el huaico,
en las 24 h previas y en el día del huaico, y cuándo cae el máximo horario de cada fuente respecto al huaico.
ERA5: 2 puntos de 0.25° (tp en m, `valid_time` UTC = FIN de la hora) -> mm, inicio de hora local = valid_time - 6 h; pesos por quebrada (calcular_pesos).
Como contexto: en las mismas temporadas, fracción de ventanas de 6 h cualquiera (diciembre-abril, misma quebrada) con lluvia > 0.1 mm en cada fuente.
Salida: modelo/salida/diagnostico_era5_ciegos.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lluvia"))
from imerg_utils import calcular_pesos, leer_quebradas  # noqa: E402

from comun import RAIZ, SALIDA, cargar_lluvia_horaria  # noqa: E402

UMBRAL = 0.1


def era5_por_quebrada():
    e = pd.concat([pd.read_csv(f, parse_dates=["valid_time"]) for f in sorted((RAIZ / "era5_data").glob("era5_lluvia_chosica_201[4-9].csv")) +
                   sorted((RAIZ / "era5_data").glob("era5_lluvia_chosica_202*.csv"))])
    e["hora"] = e.valid_time - pd.Timedelta(hours=6)
    e["mm"] = e.tp * 1000
    lat, lon = sorted(e.latitude.unique()), sorted(e.longitude.unique())
    pesos = calcular_pesos(leer_quebradas(), np.array(lon), np.array(lat), res=0.25)
    ancho = e.pivot(index="hora", columns=["latitude", "longitude"], values="mm")
    out = {}
    for q, g in pesos.groupby("quebrada_id"):
        out[q] = sum(r.peso * ancho[(r.lat_centro, r.lon_centro)] for r in g.itertuples())
    return pd.DataFrame(out)


def main():
    E = era5_por_quebrada()
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm")
    b = pd.read_csv(SALIDA / "diagnostico_eventos_H6.csv", parse_dates=["fecha"])
    from oof import oof_restringido
    o = oof_restringido(); o = o[(o.H == 6) & (o.y == 1)].sort_values(["quebrada_id", "hora"])
    o = o.assign(bloque=o.groupby("quebrada_id").hora.diff().ne(pd.Timedelta(hours=1)).cumsum())
    ult = o.groupby("bloque").agg(quebrada=("quebrada_id", "first"), t=("hora", "max")).reset_index(drop=True)
    assert len(ult) == len(b)
    filas = []
    h = pd.Timedelta(hours=1)
    for r in ult.itertuples():
        w6, w24 = slice(r.t - 5 * h, r.t), slice(r.t - 23 * h, r.t)
        dia = slice(r.t.normalize(), r.t.normalize() + 23 * h)
        fila = dict(quebrada=r.quebrada, t_huaico=r.t)
        for nom, S in (("imerg", R[r.quebrada]), ("era5", E[r.quebrada])):
            d = S.loc[dia]
            fila |= {f"{nom}_6h": S.loc[w6].sum(), f"{nom}_24h": S.loc[w24].sum(), f"{nom}_dia": d.sum(),
                     f"{nom}_hora_pico_dia": int(d.idxmax().hour) if d.max() > 0 else np.nan}
        filas.append(fila)
    t = pd.DataFrame(filas)
    t.to_csv(SALIDA / "diagnostico_era5_ciegos.csv", index=False)
    n = len(t)
    ciego = t.imerg_6h < UMBRAL
    print(f"Bloques: {n} | ciegos para IMERG (<{UMBRAL} mm en las 6 h hasta el huaico): {int(ciego.sum())}")
    print(f"ERA5 > {UMBRAL} mm en esas 6 h: en los ciegos {int((t.era5_6h[ciego] > UMBRAL).sum())}/{int(ciego.sum())}; en los no ciegos {int((t.era5_6h[~ciego] > UMBRAL).sum())}/{int((~ciego).sum())}")
    print("Medianas (mm) en los ciegos -> IMERG 6h/24h/día:", [round(float(t.loc[ciego, c].median()), 2) for c in ("imerg_6h", "imerg_24h", "imerg_dia")],
          "| ERA5 6h/24h/día:", [round(float(t.loc[ciego, c].median()), 2) for c in ("era5_6h", "era5_24h", "era5_dia")])
    print("Día del huaico con lluvia > 1 mm: IMERG", int((t.imerg_dia > 1).sum()), "/", n, "| ERA5", int((t.era5_dia > 1).sum()), "/", n,
          "| ciegos con IMERG_día > 1 mm:", int((t.imerg_dia[ciego] > 1).sum()), "/", int(ciego.sum()))
    print("Correlación (Spearman) entre fuentes en las 24 h previas, por bloque:", round(t.imerg_24h.corr(t.era5_24h, method="spearman"), 2))
    # contexto: ventanas de 6 h cualquiera en temporadas con eventos, mismas quebradas
    ix = R.index.intersection(E.index)
    cols = [c for c in R.columns if c in E.columns]
    sel = ix[ix.month.isin([12, 1, 2, 3, 4])]
    r6 = R.loc[sel, cols].rolling(6).sum().stack(); e6 = E.loc[sel, cols].rolling(6).sum().stack()
    print(f"Contexto, ventanas de 6 h cualquiera (dic-abr): IMERG > {UMBRAL} mm en {100 * (r6 > UMBRAL).mean():.0f} % | ERA5 en {100 * (e6 > UMBRAL).mean():.0f} %")
    # percentil de la lluvia del huaico frente a TODAS las ventanas de dic-abr de esa quebrada (ERA5 llovizna siempre: el umbral de 0.1 mm no distingue)
    pct = {}
    for nom, S, w in (("imerg", R, 6), ("era5", E, 6), ("imerg", R, 24), ("era5", E, 24)):
        suma = S.loc[sel, cols].rolling(w).sum()
        pct[(nom, w)] = [float((suma[r.quebrada].dropna() <= suma.at[r.t_huaico, r.quebrada]).mean() * 100) if r.t_huaico in suma.index and pd.notna(suma.at[r.t_huaico, r.quebrada]) else np.nan
                         for r in t.itertuples()]
    for (nom, w), v in pct.items():
        t[f"pct_{nom}_{w}h"] = v
    # control del ciclo diario: percentil solo frente a ventanas que terminan a la MISMA hora del día (la lluvia de la tarde no se compara con la de la noche)
    for nom, S, w in (("imerg", R, 6), ("era5", E, 6), ("imerg", R, 24), ("era5", E, 24)):
        suma = S.loc[sel, cols].rolling(w).sum()
        t[f"pcth_{nom}_{w}h"] = [float((suma.loc[suma.index.hour == r.t_huaico.hour, r.quebrada].dropna() <= suma.at[r.t_huaico, r.quebrada]).mean() * 100)
                                 if r.t_huaico in suma.index and pd.notna(suma.at[r.t_huaico, r.quebrada]) else np.nan for r in t.itertuples()]
    t.to_csv(SALIDA / "diagnostico_era5_ciegos.csv", index=False)
    print("Percentil mediano de la lluvia del huaico frente a todas las ventanas dic-abr (50 = lluvia típica; 99 = excepcional):")
    for w in (6, 24):
        print(f"  {w:>2} h: IMERG todos {t[f'pct_imerg_{w}h'].median():.0f} | IMERG ciegos {t.loc[ciego, f'pct_imerg_{w}h'].median():.0f} | ERA5 todos {t[f'pct_era5_{w}h'].median():.0f} | ERA5 ciegos {t.loc[ciego, f'pct_era5_{w}h'].median():.0f}"
              f" | ERA5 >= p90 en {int((t[f'pct_era5_{w}h'] >= 90).sum())}/{n}, IMERG >= p90 en {int((t[f'pct_imerg_{w}h'] >= 90).sum())}/{n}")
    print("Igual, pero frente a ventanas que terminan a la MISMA hora del día (control del ciclo diario):")
    for w in (6, 24):
        print(f"  {w:>2} h: IMERG todos {t[f'pcth_imerg_{w}h'].median():.0f} | ERA5 todos {t[f'pcth_era5_{w}h'].median():.0f} | ERA5 >= p90 en {int((t[f'pcth_era5_{w}h'] >= 90).sum())}/{n}, "
              f"IMERG >= p90 en {int((t[f'pcth_imerg_{w}h'] >= 90).sum())}/{n} (azar: ~{0.1 * n:.0f})")
    print("Totales dic-abr por temporada (media de quebradas, mm) IMERG vs ERA5:")
    tot = pd.DataFrame({"imerg": R.loc[R.index.isin(sel)].mean(axis=1), "era5": E.loc[E.index.isin(sel)].mean(axis=1)})
    tot["temp"] = np.where(tot.index.month >= 6, tot.index.year, tot.index.year - 1)
    print(tot.groupby("temp").sum().round(0).T.to_string())


if __name__ == "__main__":
    main()

"""Paso 9.1: auditoría de etiquetas. y=0 significa "sin noticia", no "seguro sin huaico". Dos revisiones:
  A. Cómo quedó cada fecha del catálogo en las etiquetas (positivos, NaN, ceros) en las 17 quebradas del piloto.
     Fechas con huaico SOLO en distritos vecinos (Chaclacayo, Santa Eulalia...) dejan y=0 en las 17 aunque llovió fuerte a pocos km.
  B. Días de mucha lluvia sin evento en el catálogo (±1 día): top 1.5 % en ERA5 o IMERG (solo para priorizar qué revisar en prensa/INDECI; ERA5 no es etiqueta).
Salidas: modelo/salida/auditoria_etiquetas_fechas_catalogo.csv y auditoria_etiquetas_candidatos.csv
"""
import numpy as np
import pandas as pd

from comun import RAIZ, SALIDA, cargar_lluvia_horaria
from diagnostico_era5_ciegos import era5_por_quebrada


def fechas_catalogo():
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", parse_dates=["fecha"])
    e = pd.read_parquet(RAIZ / "catalogo_huaicos_chosica" / "etiquetas_horarias_H24.parquet")
    g = e.groupby(e.hora.dt.normalize()).y.agg(horas_y1=lambda s: int((s == 1).sum()), horas_nan=lambda s: int(s.isna().sum()), horas=("size"))
    filas = []
    for f, x in c.groupby("fecha"):
        r = g.loc[f]
        filas.append(dict(fecha=f.date(), eventos=len(x), en_piloto=int(x.en_piloto.sum()), usables_hora=int(x.usable_horario.fillna(False).sum()),
                          horas_y1_H24=r.horas_y1, horas_nan=r.horas_nan, horas_total=r.horas,
                          solo_vecino=bool(x.en_piloto.sum() == 0), distritos="; ".join(sorted(set(x.distrito.str.replace(r" \(.*", "", regex=True))))))
    t = pd.DataFrame(filas)
    t.to_csv(SALIDA / "auditoria_etiquetas_fechas_catalogo.csv", index=False)
    return c, t


def candidatos(c):
    E = era5_por_quebrada().mean(axis=1)
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm").mean(axis=1)
    ix = R.index.intersection(E.index)
    ix = ix[ix.month.isin([12, 1, 2, 3, 4])]
    d = pd.DataFrame({"imerg": R.loc[ix], "era5": E.loc[ix]}).resample("D").sum()
    d = d[d.index.month.isin([12, 1, 2, 3, 4])]
    d["r_imerg"], d["r_era5"] = d.imerg.rank(pct=True), d.era5.rank(pct=True)
    ev = set(c.fecha.dt.normalize())
    d["evento_pm1"] = [any(abs((t - e).days) <= 1 for e in ev) for t in d.index]
    cand = d[(~d.evento_pm1) & ((d.r_era5 >= .985) | (d.r_imerg >= .985))].round(3)
    cand.to_csv(SALIDA / "auditoria_etiquetas_candidatos.csv")
    return d, cand


def main():
    c, t = fechas_catalogo()
    pd.set_option("display.width", 220)
    print(t.to_string(index=False))
    print(f"\nFechas del catálogo: {len(t)} | solo en distritos vecinos (y=0 en las 17 quebradas): {int(t.solo_vecino.sum())}: {', '.join(map(str, t[t.solo_vecino].fecha))}")
    d, cand = candidatos(c)
    print(f"Días dic-abr: {len(d)} | con evento en catálogo: {int(d.index.isin(c.fecha.dt.normalize()).sum())} | candidatos de mucha lluvia sin evento (±1 día): {len(cand)}")
    for nom in ("era5", "imerg"):
        top = d.nlargest(30, nom)
        print(f"  top 30 días por {nom}: {int(top.index.isin(c.fecha.dt.normalize()).sum())} con evento en catálogo (base {100 * d.index.isin(c.fecha.dt.normalize()).mean():.1f} %)")


if __name__ == "__main__":
    main()

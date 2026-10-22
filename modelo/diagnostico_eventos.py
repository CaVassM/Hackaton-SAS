"""Paso 7.1: ¿por qué algunas temporadas (sobre todo 2014-15) casi no mejoran? Mira cada tormenta (fecha) con el modelo restringido fuera de muestra, H = 6.
Para cada bloque de huaico (quebrada, racha de horas con y=1): su mejor puntaje, el percentil de ese puntaje dentro de la temporada, si cruza el umbral de 1 alerta cada 100 h,
la lluvia que el modelo PUDO ver (con el retraso de 4 h) y la que ya había caído en las 6 h previas al huaico (sin retraso).
"""
import numpy as np
import pandas as pd

from comun import SALIDA, cargar_lluvia_horaria
from oof import oof_restringido

H_VER, N = 6, 100
o = oof_restringido()
R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm")
d = o[o.H == H_VER].copy()
umbral = d.groupby("temporada").p.transform(lambda s: s.quantile(1 - 1 / N))
d["alerta"] = d.p >= umbral
d["pct"] = d.groupby("temporada").p.rank(pct=True) * 100

y1 = d[d.y == 1].sort_values(["quebrada_id", "hora"])
nuevo = y1.groupby("quebrada_id").hora.diff().ne(pd.Timedelta(hours=1))
y1 = y1.assign(bloque=nuevo.cumsum())
filas = []
for b, g in y1.groupby("bloque"):
    q, t_last = g.quebrada_id.iloc[0], g.hora.max()
    mejor = g.loc[g.p.idxmax()]
    sin_lat = float(R[q].loc[t_last - pd.Timedelta(hours=5): t_last].sum())  # 6 h de lluvia que ya habían caído hasta la hora del huaico
    filas.append(dict(temporada=g.temporada.iloc[0], fecha=t_last.normalize(), quebrada=q, horas_y1=len(g), pct_mejor=mejor.pct, detectado=bool(g.alerta.any()),
                      lluvia_6h_vista=float(g.loc[g.hora == t_last, "lluvia_6h"].iloc[0]), mm_6h_real=sin_lat,
                      reg_max_24h=float(g.loc[g.hora == t_last, "reg_max_24h"].iloc[0]), lluvia_14d=float(g.loc[g.hora == t_last, "lluvia_14d"].iloc[0])))
b = pd.DataFrame(filas)
b.to_csv(SALIDA / "diagnostico_eventos_H6.csv", index=False)
pd.set_option("display.width", 220)
res = b.groupby(["temporada", "fecha"]).agg(bloques=("quebrada", "size"), detectados=("detectado", "sum"), pct_mediano=("pct_mejor", "median"),
                                           lluvia_6h_vista=("lluvia_6h_vista", "median"), mm_6h_real=("mm_6h_real", "median"),
                                           reg_max_24h=("reg_max_24h", "median"), lluvia_14d=("lluvia_14d", "median")).round(1)
print("POR TORMENTA (H=6; percentil = qué tan arriba quedó su mejor hora dentro de la temporada; umbral de alerta = percentil 99)\n" + res.to_string())
print("\nResumen: bloques", len(b), "| detectados", int(b.detectado.sum()), "| tormentas (fechas)", b.fecha.nunique())
print("Percentil mediano del mejor puntaje por bloque, por temporada:", b.groupby("temporada").pct_mejor.median().round(1).to_dict())
v = b[b.mm_6h_real > 0]
print(f"Huaicos con lluvia real en las 6 h previas: {len(v)}/{len(b)}; de ellos, el modelo vio (lluvia_6h_vista > 0.1 mm) en {int((v.lluvia_6h_vista > 0.1).sum())}")

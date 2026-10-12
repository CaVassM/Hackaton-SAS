"""R0: los 10 días de 2024-25 con más horas de alerta (umbral FIJO, 1 alerta cada 100 h), para revisarlos en prensa. NO modifica etiquetas.

Puntaje: pieza 1 del modelo en dos piezas (XGBoost restringido, semilla 0, LOSTO), H = 6; umbral = cuantil 0.99 de las 12 temporadas.
Quebradas: riesgo P1 x P2 (mezcla) con su propio umbral fijo 1/100 por quebrada (H = 6).
Salida: modelo/mejoras/R0/dias_alerta_2024_25.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1] / "dos_piezas"))
from base import tormentas  # noqa: E402
from comun import cargar_lluvia_horaria  # noqa: E402
from evaluar import tabla_riesgo  # noqa: E402
from pieza1 import RUTA_OOF  # noqa: E402

H, N = 6, 100


def main():
    o = pd.read_parquet(RUTA_OOF)
    z = o[(o.H == H) & o.y.notna()]
    tau = np.quantile(z.p_xgb0_losto, 1 - 1 / N)
    a = z[(z.temporada == "2024-25")].assign(alerta=lambda d: d.p_xgb0_losto >= tau, dia=lambda d: d.hora.dt.normalize())
    dias = a.groupby("dia").agg(horas_alerta=("alerta", "sum"), p1_max=("p_xgb0_losto", "max"),
                                primera_alerta=("hora", lambda s: s[a.loc[s.index, "alerta"]].min()))
    dias = dias[dias.horas_alerta > 0].sort_values(["horas_alerta", "p1_max"], ascending=False).head(10)

    q = tabla_riesgo(o, tormentas())
    q = q[q.H == H]
    tau_q = np.quantile(q.r_xgb0_losto, 1 - 1 / N)
    q = q[q.temporada == "2024-25"].assign(dia=lambda d: d.hora.dt.normalize())
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm")
    filas = []
    for d, r in dias.iterrows():
        g = q[(q.dia == d) & (q.r_xgb0_losto >= tau_q)]
        top = g.groupby("quebrada_id").r_xgb0_losto.max().sort_values(ascending=False)
        lluvia = R.loc[d - pd.Timedelta(hours=12): d + pd.Timedelta(hours=23)]
        filas.append(dict(fecha=d.date(), horas_alerta_zona=int(r.horas_alerta), primera_alerta=r.primera_alerta, p1_max=round(r.p1_max, 3),
                          quebradas_en_alerta=",".join(top.index), riesgo_max=round(top.max(), 4) if len(top) else np.nan,
                          imerg_dia_media_mm=round(float(R.loc[d: d + pd.Timedelta(hours=23)].mean(axis=1).sum()), 1),
                          imerg_max_mmh=round(float(lluvia.max().max()), 1)))
    out = pd.DataFrame(filas)
    out.to_csv(AQUI / "dias_alerta_2024_25.csv", index=False)
    pd.set_option("display.width", 250)
    print(f"Umbral fijo zona (H={H}, 1/{N}): {tau:.4f} | horas de alerta 2024-25: {int(a.alerta.sum())} de {int((z.p_xgb0_losto >= tau).sum())}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()

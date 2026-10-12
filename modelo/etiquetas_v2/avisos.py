"""Paso 3: encuadre operativo. ¿Cuántos bloques detecta el ranking de V0 + P2 si solo se alerta en días con AVISO de lluvia de Senamhi?

Avisos: listado público de senamhi.gob.pe (avisos_senamhi_2021_2026.csv; 2 080 avisos, ene-2021 a oct-2026; NO hay avisos anteriores en esa página).
El listado no dice qué departamentos cubre cada aviso (está en un mapa de la ficha). PROXY: avisos de "precipitaciones/lluvia" cuyo título
nombra la SIERRA sin limitarla a la sierra norte o sur. Día con aviso = día entre inicio y fin del aviso (inclusive).
Temporadas evaluadas: 2021-22 a 2025-26 (cubiertas por el listado; con eventos: 2022-23 y 2025-26).
Puntaje: riesgo = P1 (zona, semilla 0) x P2 mezcla, LOSTO y LOSO, etiquetas v1 y v2 (salidas de correr.py). N = 100.
  cobertura : % de bloques cuya última hora cae en día con aviso; % de horas que son días con aviso.
  A aviso y umbral fijo : alerta si día con aviso Y riesgo >= umbral fijo 1/100 (calculado en las 12 temporadas, como antes).
  B solo días con aviso : mismo presupuesto (1/100 de todas las filas de las 5 temporadas) concentrado en días con aviso: umbral = cuantil de los
                          puntajes en filas con aviso (solo puntajes, sin etiquetas). Azar: mismas alertas por temporada al azar dentro de días con aviso.
  C sin aviso           : mismo presupuesto, umbral fijo calculado en estas 5 temporadas (referencia).
Salida: modelo/etiquetas_v2/avisos_resultado.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "dos_piezas"))
sys.path.insert(0, str(AQUI.parent))
from base import SALIDA  # noqa: E402
from tabla3 import bloques  # noqa: E402

TEMPORADAS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
N = 100
HS = (3, 6, 12, 24)


def dias_aviso():
    a = pd.read_csv(AQUI / "avisos_senamhi_2021_2026.csv", parse_dates=["inicio", "fin"])
    t = a.titulo
    lluvia = t.str.contains("PRECIPITAC|LLUVIA", regex=True) & t.str.contains("SIERRA")
    solo_norte_sur = t.str.contains(r"SIERRA (NORTE|SUR)", regex=True) & ~t.str.contains("CENTRO") & ~t.str.contains(r"SIERRA(?! NORTE| SUR)", regex=True)
    a = a[lluvia & ~solo_norte_sur]
    dias = set()
    for r in a.itertuples():
        dias.update(pd.date_range(r.inicio, r.fin, freq="D"))
    return a, dias


def esperado(grupos, temp_rows, n_s, k_s):
    """Bloques detectados al azar: alertas k_s repartidas al azar entre las n_s filas con aviso de la temporada; un bloque solo puede
    detectarse por sus filas en días con aviso (L_aviso)."""
    tot = 0.0
    for s, L in grupos:
        n, k = n_s.get(s, 0), k_s.get(s, 0)
        if L == 0 or n == 0:
            continue
        i = np.arange(L)
        tot += 1 - np.prod(np.clip((n - k - i) / (n - i), 0, 1))
    return tot


def main():
    pd.set_option("display.width", 220)
    av, dias = dias_aviso()
    P2 = pd.read_csv(SALIDA / "p2_por_pliegue.csv")
    filas = []
    for v in ("v1", "v2"):
        t = pd.read_parquet(AQUI / f"tabla3_{v}.parquet", columns=["hora", "quebrada_id", "H", "y", "temporada"])
        oz = pd.read_parquet(AQUI / f"oof_zona_{v}.parquet")
        for esq, clave in (("losto", "pliegue_losto"), ("loso", "temporada")):
            p2 = P2[P2.esquema == esq].rename(columns={"pliegue": clave})[[clave, "quebrada_id", "mezcla"]]
            q = t.merge(oz[["hora", "H", "pliegue_losto", f"p_xgb0_{esq}"]], on=["hora", "H"]).merge(p2, on=[clave, "quebrada_id"])
            q["r"] = q[f"p_xgb0_{esq}"] * q.mezcla
            for H in HS:
                todo = q[q.H == H]
                tau_fijo = np.quantile(todo.r, 1 - 1 / N)
                e = todo[todo.temporada.isin(TEMPORADAS)].reset_index(drop=True)
                e["aviso"] = e.hora.dt.normalize().isin(dias)
                b = bloques(e)
                gb = pd.Series(np.nan, index=e.index)
                gb.loc[b.index] = b.bloque.to_numpy()
                presupuesto = int(round(len(e) / N))
                ra = e.r.where(e.aviso)
                tau_b = np.sort(ra.dropna().to_numpy())[::-1][min(presupuesto, int(e.aviso.sum())) - 1]
                modos = {"A aviso y umbral fijo": e.aviso & (e.r >= tau_fijo), "B solo días con aviso": e.aviso & (e.r >= tau_b),
                         "C sin aviso (mismo presupuesto)": e.r >= np.quantile(e.r, 1 - 1 / N)}
                ult = b.groupby("bloque").hora.max()
                cubiertos = int(ult.dt.normalize().isin(dias).sum())
                for nombre, al in modos.items():
                    det = int(pd.DataFrame({"g": gb, "a": al}).dropna().groupby("g").a.max().sum())
                    # azar dentro de las filas elegibles (con aviso para A y B; todas para C)
                    eleg = e.aviso if nombre != "C sin aviso (mismo presupuesto)" else pd.Series(True, index=e.index)
                    n_s = e[eleg].groupby("temporada").size().to_dict()
                    k_s = e[al].groupby("temporada").size().to_dict()
                    grupos = [(g.temporada.iloc[0], int(eleg.loc[g.index].sum())) for _, g in b.groupby("bloque")]
                    filas.append(dict(etiquetas=v, esquema=esq, H=H, modo=nombre, bloques=len(ult), bloques_en_dias_aviso=cubiertos,
                                      pct_horas_con_aviso=round(100 * e.aviso.mean(), 1), alertas=int(al.sum()), presupuesto_1_100=presupuesto,
                                      detectados=det, azar=round(esperado(grupos, None, n_s, k_s), 1)))
    r = pd.DataFrame(filas)
    r.to_csv(AQUI / "avisos_resultado.csv", index=False)
    print(f"Avisos usados (proxy sierra/sierra centro): {len(av)} | días con aviso en dic-abr de 2021-22..2025-26: "
          f"{sum(1 for d in dias if d.month in (12, 1, 2, 3, 4) and d >= pd.Timestamp('2021-12-01'))}")
    print(r.to_string(index=False))
    s = r.groupby(["etiquetas", "esquema", "modo"])[["bloques", "bloques_en_dias_aviso", "alertas", "presupuesto_1_100", "detectados", "azar"]].sum()
    print("\nSuma de los 4 H\n" + s.to_string())


if __name__ == "__main__":
    main()

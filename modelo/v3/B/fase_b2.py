"""Fase B2: ambiente atmosférico ERA5 (Open-Meteo, sin credenciales): precipitation, showers (~ precipitación convectiva), total_column_integrated_water_vapour
en 42 puntos 0.25° (lat -12.5..-11.25, lon -77.25..-75.75). CAPE, K index y Total Totals NO están en Open-Meteo: requieren CDS (pendiente del usuario).

Variables de zona por hora (máximo entre los 42 puntos): lluvia 3/6/24 h, convectiva 3/6 h, TCWV.
  PASADO (<= t, 1 h de retraso; ojo: ERA5 real llega con ~5 días, tampoco es operativo): agregadas al mejor modelo de B1 (A2 + estado).
  TECHO "pronóstico perfecto" (valores en (t, t+3 h]): lluvia, convectiva y TCWV máximas futuras, agregadas al mismo modelo. NO desplegable.
Ceguera ERA5 en los bloques v2 (H=6): lluvia ERA5 < 0.1 mm en las 6 h hasta la última hora del bloque, en el punto más cercano y en el máximo de 9 puntos
  (lat -12.25..-11.75, lon -77..-76.5), frente a IMERG (24 de 43).
Evaluación por evento (TSS, LOSO), igual que A y B1.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent / "A"))
from fase_b1 import A2, CHICO, H_EV, MODELO, PARAMS_XGB, base, estado_horario, features_intensidad, fila, score_model_safe  # noqa: E402
from comun_v3 import CACHE, etiquetar, evaluar_loso, eventos_lluvia, lluvia_zona  # noqa: E402

OM = AQUI.parent / "datos" / "raw" / "openmeteo" / "era5.parquet"


def era5_zona():
    e = pd.read_parquet(OM)
    P = e.pivot_table(index="hora", columns=["lat", "lon"], values="precipitation")
    C = e.pivot_table(index="hora", columns=["lat", "lon"], values="showers")
    W = e.pivot_table(index="hora", columns=["lat", "lon"], values="total_column_integrated_water_vapour")
    idx = pd.date_range(P.index.min(), P.index.max(), freq="h")
    P, C, W = P.reindex(idx), C.reindex(idx), W.reindex(idx)
    Z = pd.DataFrame(index=idx)
    for k in (3, 6, 24):
        Z[f"e5_p{k}h"] = P.rolling(k, min_periods=k).sum().max(axis=1)
    for k in (3, 6):
        Z[f"e5_c{k}h"] = C.rolling(k, min_periods=k).sum().max(axis=1)
    Z["e5_tcwv"] = W.max(axis=1)
    pasado = Z.shift(1).add_suffix("_pas")                                  # hora etiquetada t-1 -> conocida en t
    fut = pd.DataFrame({"e5_pfut3h": P.rolling(3).sum().shift(-3).max(axis=1), "e5_cfut3h": C.rolling(3).sum().shift(-3).max(axis=1),
                        "e5_tcwv_fut3h": W.rolling(3).max().shift(-3).max(axis=1)}, index=idx)   # horas t+1..t+3 = (t, t+3 h]
    out = pd.concat([pasado, fut], axis=1)
    out.index.name = "hora"
    return out, P


def oof(E, X5):
    ruta = CACHE / "oof_b2.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    z = (base.etiquetas_zona().merge(features_intensidad(), left_on="hora", right_index=True, how="left")
         .merge(E, left_on="hora", right_index=True, how="left").merge(X5, left_on="hora", right_index=True, how="left"))
    z["temporada"] = base.temporada_de(z.hora)
    y, temp = z.y.to_numpy(), z.temporada.to_numpy()
    lab = ~np.isnan(y)
    b1 = A2["A2_mas_72h"] + ["hum_suelo_5d", "dias_activ", "icen"]
    pas = [c for c in X5.columns if c.endswith("_pas")]
    fut = ["e5_pfut3h", "e5_cfut3h", "e5_tcwv_fut3h"]
    variantes = {"B1 (referencia, misma corrida)": b1, "B2 pasado": b1 + pas, "B2 techo (futuro)": b1 + fut}
    out = z[["hora", "H"]].copy()
    for nombre, cols in variantes.items():
        usar = cols + ["H"]
        mono = tuple(0 if c == "dias_activ" else 1 for c in usar)
        p = np.full(len(z), np.nan)
        for s in np.unique(temp):
            te, tr = temp == s, (temp != s) & lab
            spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
            m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=0)
            p[te] = m.fit(z.loc[tr, usar], y[tr]).predict_proba(z.loc[te, usar])[:, 1]
        out[nombre] = p
        print(f"  {nombre} listo", flush=True)
    out.to_parquet(ruta, index=False)
    return out


def ceguera(P):
    t = pd.read_parquet(MODELO / "etiquetas_v2" / "tabla3_v2.parquet", columns=["hora", "quebrada_id", "H", "y"])
    t = t[(t.H == 6) & (t.y == 1)].sort_values(["quebrada_id", "hora"])
    nb = t.groupby("quebrada_id").hora.diff().ne(pd.Timedelta(hours=1)).cumsum()
    ult = t.groupby(nb).agg(q=("quebrada_id", "first"), tl=("hora", "max"))
    cerca = P[(-12.0, -76.75)]
    zona = P.loc[:, [(la, lo) for la, lo in P.columns if -12.25 <= la <= -11.75 and -77.0 <= lo <= -76.5]].max(axis=1)
    # ERA5 en Open-Meteo: hora etiquetada h = lluvia de [h, h+1): 6 h hasta la última hora del bloque = h en [tl-5, tl]
    r = pd.DataFrame({"cercano": [cerca.loc[x - pd.Timedelta(hours=5): x].sum() for x in ult.tl],
                      "max9": [zona.loc[x - pd.Timedelta(hours=5): x].sum() for x in ult.tl]})
    return {k: f"{int((r[k] < 0.1).sum())}/{len(r)}" for k in r}


def main():
    pd.set_option("display.width", 230)
    X5, P = era5_zona()
    E = estado_horario()
    ev = pd.read_parquet(AQUI / "fase_b1_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    o = oof(E, X5)
    o = o[o.H == H_EV].set_index("hora")
    filas = []
    for k in [c for c in o.columns if c != "H"]:
        ev["x"] = [score_model_safe(o[k], r) for r in ev.itertuples()]
        r, _, res = evaluar_loso(ev, ciegos, "x")
        filas.append(fila(k, r, res, ciegos))
    res = pd.DataFrame(filas)
    res.to_csv(AQUI / "fase_b2_resumen.csv", index=False)
    print(res.to_string(index=False))
    print("Ceguera ERA5 (bloques v2 H=6 con < 0.1 mm en 6 h):", ceguera(P), "| IMERG: 24/43")


if __name__ == "__main__":
    main()

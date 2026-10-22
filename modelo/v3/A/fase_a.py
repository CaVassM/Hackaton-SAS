"""Fase A: medir como la literatura (por EVENTO de lluvia, TSS) y modelo solo-intensidad. Etiquetas v2. Ver comun_v3.py para las definiciones.

Puntaje de cada evento (solo con lluvia/puntajes ANTERIORES al huaico en los eventos disparadores: horas h con h + 1 h + latencia <= fin del huaico;
en los no disparadores, todo el evento + 3 h):
  ISAAC_fijo      : umbral SENAMHI/ISAAC (Millán-Arancibia et al. 2026, Cusipata) I = 1.57 D^-0.047 mm/h aplicado a IMERG tal cual:
                    alerta si para alguna duración D (1..duración) la intensidad media máxima en D horas >= 1.57 D^-0.047. Sin latencia y con 4 h.
  ID_calibrado    : misma forma (exponente -0.047), escala alfa calibrada maximizando el TSS en las temporadas de entrenamiento. Sin latencia y con 4 h.
  actual          : modelo actual por quebrada (XGBoost restringido V1+D, LOSO, etiquetas v2; modelo/etiquetas_v2/oof_actual_v2.parquet), H = 3,
                    máximo entre quebradas y horas del evento. Umbral TSS en entrenamiento.
  dos_piezas      : pieza 1 (zona, semilla 0, LOSO, v2; oof_zona_v2.parquet), H = 3.
  A2_intensidad   : XGBoost restringido (mismos parámetros) en la zona con SOLO intensidad: máximo entre celdas de la lluvia de 1, 3 y 6 h, y su máximo
                    en las últimas 6 h disponibles (latencia 4 h). A2_mas_72h: además lluvia de 24, 48 y 72 h. Sin 14 d ni lluvia efectiva. LOSO, H como columna.
Umbral de cada temporada = el que maximiza el TSS en las otras (por evento). IC 90 %: bootstrap de tormentas.
% alertas 2024-25: de los eventos con alerta (fuera de muestra), qué % es de 2024-25 (temporada sin huaicos catalogados).
Salidas: modelo/v3/A/fase_a_resumen.csv (o fase_a_resumen_sin_referencias.csv si faltan las referencias de modelos anteriores), fase_a_eventos.parquet
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from comun_v3 import (CACHE, MODELO, bootstrap, etiquetar, evaluar_loso, eventos_lluvia, lluvia_celdas, lluvia_zona)  # noqa: E402

sys.path.insert(0, str(MODELO / "dos_piezas"))
import base  # noqa: E402
from arboles import PARAMS_XGB  # noqa: E402
from restringido import CHICO  # noqa: E402

ISAAC_A, ISAAC_B = 1.57, -0.047
LAT = 4
H_EV = 3
ETQ = MODELO / "etiquetas_v2"


# --------------------------------------------------------------------------- puntajes de lluvia por evento
def ventana(r, lat):
    """Última hora de lluvia utilizable: si disparador, h + 1 + lat <= huaico_fin; si no, fin del evento."""
    if r.disparador == 1:
        return (r.huaico_fin - pd.Timedelta(hours=1 + lat)).floor("h")
    return r.fin


def score_id(z, a, b, beta=ISAAC_B):
    """max_D (intensidad media máxima en D horas) / D^beta, con la lluvia de la zona entre a y b."""
    x = z.loc[a:b].fillna(0).to_numpy()
    if len(x) == 0:
        return 0.0
    best = 0.0
    for D in range(1, len(x) + 1):
        m = pd.Series(x).rolling(D).sum().max() / D
        best = max(best, m / D ** beta)
    return best


# --------------------------------------------------------------------------- A2: modelo solo-intensidad en la zona
def features_intensidad():
    R = lluvia_celdas()
    L = R.shift(LAT + 1)
    f = {}
    for k in (1, 3, 6):
        s = L.rolling(k, min_periods=k).sum().max(axis=1, skipna=False)
        f[f"i{k}h"] = s
        f[f"i{k}h_max6"] = s.rolling(6, min_periods=6).max()
    for k in (24, 48, 72):
        f[f"p{k}h"] = L.rolling(k, min_periods=k).sum().max(axis=1, skipna=False)
    F = pd.DataFrame(f)
    F.index.name = "hora"
    return F


A2 = {"A2_intensidad": ["i1h", "i3h", "i6h", "i1h_max6", "i3h_max6", "i6h_max6"]}
A2["A2_mas_72h"] = A2["A2_intensidad"] + ["p24h", "p48h", "p72h"]


def oof_a2():
    ruta = CACHE / "oof_a2.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    z = base.etiquetas_zona().merge(features_intensidad(), left_on="hora", right_index=True, how="left")
    z["temporada"] = base.temporada_de(z.hora)
    y, temp = z.y.to_numpy(), z.temporada.to_numpy()
    lab = ~np.isnan(y)
    out = z[["hora", "H", "y", "temporada"]].copy()
    for nombre, cols in A2.items():
        usar = cols + ["H"]
        p = np.full(len(z), np.nan)
        for s in np.unique(temp):
            te = temp == s
            tr = ~te & lab
            spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
            m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=tuple([1] * len(usar)), random_state=0)
            p[te] = m.fit(z.loc[tr, usar], y[tr]).predict_proba(z.loc[te, usar])[:, 1]
        out[nombre] = p
        print(f"  {nombre} listo", flush=True)
    out.to_parquet(ruta, index=False)
    return out


def score_modelo(serie, r):
    """Máximo del puntaje horario en [inicio, última hora útil] (disparador: t < fin del huaico; no disparador: hasta fin + 3 h)."""
    b = (r.huaico_fin - pd.Timedelta(minutes=1)).floor("h") if r.disparador == 1 else r.fin + pd.Timedelta(hours=3)
    x = serie.loc[r.inicio:b]
    return float(x.max()) if len(x) else np.nan


def main():
    pd.set_option("display.width", 220)
    z = lluvia_zona()
    e, ciegos = etiquetar(eventos_lluvia(z))
    ev = e[~e.desconocido].reset_index(drop=True)
    print(f"Eventos evaluados {len(ev)} (disparadores {int(ev.disparador.sum())}) + días ciegos {len(ciegos)}", flush=True)
    for lat, suf in ((0, "sin_lat"), (LAT, "lat4")):
        ev[f"id_{suf}"] = [score_id(z, r.inicio, ventana(r, lat)) for r in ev.itertuples()]
    # modelos (puntaje horario de la zona, H = 3)
    # Referencias de modelos ANTERIORES (solo para la tabla comparativa; el modelo final no las usa). Son regenerables y no van a git
    # (modelo/etiquetas_v2/correr.py, ~40 min). Si faltan, se omiten esas dos filas y el resumen va a fase_a_resumen_sin_referencias.csv.
    con_ref = (ETQ / "oof_actual_v2.parquet").exists() and (ETQ / "oof_zona_v2.parquet").exists()
    series = {}
    if con_ref:
        act = pd.read_parquet(ETQ / "oof_actual_v2.parquet")
        series["actual"] = act[act.H == H_EV].groupby("hora").p.max()
        zo = pd.read_parquet(ETQ / "oof_zona_v2.parquet")
        series["dos_piezas"] = zo[zo.H == H_EV].set_index("hora").p_xgb0_loso
    else:
        print("AVISO: faltan modelo/etiquetas_v2/oof_{actual,zona}_v2.parquet (modelos anteriores): se omiten esas dos referencias.", flush=True)
    a2 = oof_a2()
    a2 = a2[a2.H == H_EV].set_index("hora")
    series.update({"A2_intensidad": a2.A2_intensidad, "A2_mas_72h": a2.A2_mas_72h})
    for k, s in series.items():
        ev[k] = [score_model_safe(s, r) for r in ev.itertuples()]
    ev.to_parquet(AQUI / "fase_a_eventos.parquet", index=False)

    metodos = {"ISAAC fijo, sin latencia": ("id_sin_lat", ISAAC_A), "ISAAC fijo, latencia 4 h": ("id_lat4", ISAAC_A),
               "I-D calibrado, sin latencia": ("id_sin_lat", None), "I-D calibrado, latencia 4 h": ("id_lat4", None),
               "modelo actual (por quebrada)": ("actual", None), "dos piezas (P1)": ("dos_piezas", None),
               "A2 solo intensidad": ("A2_intensidad", None), "A2 + 24-72 h": ("A2_mas_72h", None)}
    metodos = {k: v for k, v in metodos.items() if v[0] in ev.columns}
    filas = []
    for nombre, (col, fijo) in metodos.items():
        r, taus, (t, pod, pofd, tp, fn, fp, tn) = evaluar_loso(ev, ciegos, col, fijo)
        ic = bootstrap(r, ciegos)
        al = r[r.alerta]
        filas.append(dict(metodo=nombre, TSS=round(t, 2), TSS_ic90=ic["TSS"], acierto_POD=round(pod, 2), POD_ic90=ic["POD"], falsas_POFD=round(pofd, 3),
                          aciertos=tp, fallos=fn, falsas_alarmas=fp, eventos_alerta=int(len(al)),
                          pct_alertas_2024_25=round(100 * (al.temporada == "2024-25").mean(), 0) if len(al) else np.nan,
                          umbral_mediano=float(np.median(list(taus.values())))))
    res = pd.DataFrame(filas)
    res.to_csv(AQUI / ("fase_a_resumen.csv" if con_ref else "fase_a_resumen_sin_referencias.csv"), index=False)
    print(res.to_string(index=False))
    d = ev[ev.disparador == 1][[c for c in ["inicio", "huaico_fin", "tormenta", "id_sin_lat", "id_lat4", "actual", "dos_piezas", "A2_intensidad"] if c in ev.columns]]
    print("\nEventos disparadores (puntajes)\n" + d.round(3).to_string(index=False))
    print("\nPercentiles 50/90/99 de los NO disparadores:\n" + ev[ev.disparador == 0][list(series) + ["id_sin_lat", "id_lat4"]].quantile([.5, .9, .99]).round(3).to_string())


def score_model_safe(s, r):
    try:
        return score_modelo(s, r)
    except KeyError:
        return np.nan


if __name__ == "__main__":
    main()

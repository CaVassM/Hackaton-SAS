"""Fase B1: variables de ESTADO (conocidas en t) como entradas del mejor modelo de A y como UMBRAL VARIABLE. Etiquetas v2, evaluación por evento (TSS, LOSO).

Estado (todas con el retraso real de publicación):
  - hum_suelo_5d : humedad del suelo 0-7 cm ERA5-Land (Open-Meteo), media de las 5 celdas, valor de t - 5 días (ERA5-Land llega con ~5 días).
                   Variante IDEAL hum_suelo_1h (t - 1 h): no desplegable con ERA5-Land, solo dice cuánto valdría tener humedad en tiempo real.
  - dias_activ   : días desde la última activación catalogada en las 17 quebradas (fechas < día de t; con o sin hora). Tope 3650.
  - icen         : ICEN mensual (IGP/ENFEN, versión oficial). ICEN(m) usa m-1..m+1: en el mes M se usa ICEN(M-2) desde el día 10 y ICEN(M-3) antes.
(a) ENTRADAS: A2 + 24-72 h (mejor modelo de A) + estado (hum_suelo_5d, dias_activ, icen); variante con hum_suelo_1h. XGBoost restringido, monotonía +1 en
    lluvia, humedad e ICEN; sin restricción en dias_activ. LOSO.
(b) UMBRAL VARIABLE: alerta si puntaje >= tau[régimen]; régimen = ICEN >= 0.4 (Niño costero cálido) o humedad 5 d >= mediana de entrenamiento.
    Los dos umbrales se calibran maximizando el TSS en las temporadas de entrenamiento (búsqueda en rejilla de cuantiles). Puntajes: A2 + 24-72 h y I-D (lat 4 h).
Sensibilidad: TSS evaluando SIN 2016-17 y 2022-23 (Niño costero 2017 y 2023; 7 de las 13 unidades positivas).
Salida: modelo/v3/B/fase_b1_resumen.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent / "A"))
from comun_v3 import CACHE, MODELO, RAIZ, bootstrap, etiquetar, evaluar_loso, eventos_lluvia, lluvia_zona, tss  # noqa: E402
from fase_a import A2, H_EV, base, features_intensidad, score_model_safe  # noqa: E402
from arboles import PARAMS_XGB  # noqa: E402
from restringido import CHICO  # noqa: E402

DATOS = AQUI.parent / "datos" / "raw"
NINO = {"2016-17", "2022-23"}


def estado_horario():
    sm = pd.read_parquet(DATOS / "openmeteo" / "era5_land.parquet").groupby("hora").soil_moisture_0_to_7cm.mean().asfreq("h")
    idx = pd.date_range("2014-12-01", "2026-04-30 23:00", freq="h")
    E = pd.DataFrame(index=idx)
    E["hum_suelo_1h"] = sm.reindex(idx - pd.Timedelta(hours=1)).to_numpy()
    E["hum_suelo_5d"] = sm.reindex(idx - pd.Timedelta(days=5)).to_numpy()
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    q = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    fechas = np.array(sorted(set(pd.to_datetime(c.fecha[c.en_piloto.eq("True") & q.ne("")]))), dtype="datetime64[ns]")
    dia = idx.normalize().to_numpy()
    k = np.searchsorted(fechas, dia, side="left") - 1          # última fecha estrictamente anterior al día de t
    ult = np.where(k >= 0, fechas[np.clip(k, 0, None)], np.datetime64("NaT"))
    d = (dia - ult) / np.timedelta64(1, "D")
    E["dias_activ"] = np.where(np.isnan(d), 3650, np.minimum(d, 3650))
    ic = pd.read_csv(DATOS / "icen" / "ICEN.txt", comment="%", sep=r"\s+", names=["a", "m", "icen"])
    ic = dict(zip(zip(ic.a, ic.m), ic.icen))
    atras = np.where(idx.day >= 10, 2, 3)
    per = (idx.to_period("M") - atras)
    E["icen"] = [ic.get((p.year, p.month), np.nan) for p in per]
    E.index.name = "hora"
    return E


def oof_estado(E):
    ruta = CACHE / "oof_b1.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    z = base.etiquetas_zona().merge(features_intensidad(), left_on="hora", right_index=True, how="left").merge(E, left_on="hora", right_index=True, how="left")
    z["temporada"] = base.temporada_de(z.hora)
    y, temp = z.y.to_numpy(), z.temporada.to_numpy()
    lab = ~np.isnan(y)
    out = z[["hora", "H"]].copy()
    variantes = {"B1_estado_5d": A2["A2_mas_72h"] + ["hum_suelo_5d", "dias_activ", "icen"],
                 "B1_estado_ideal": A2["A2_mas_72h"] + ["hum_suelo_1h", "dias_activ", "icen"]}
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


def umbral_regimen(ev, ciegos, col, reg_col):
    """LOSO con dos umbrales (régimen 0/1) calibrados juntos maximizando el TSS en entrenamiento."""
    ev = ev.copy()
    ev["alerta"] = False
    for t in sorted(ev.temporada.unique()):
        tr, te = ev[ev.temporada != t], ev.temporada == t
        reg_tr = tr[reg_col].to_numpy()
        s = np.nan_to_num(tr[col].to_numpy(float), nan=-np.inf)
        y = tr.disparador.to_numpy()
        cand = {r: np.unique(np.r_[np.quantile(s[reg_tr == r][np.isfinite(s[reg_tr == r])], np.linspace(0, 1, 41)), np.inf]) if (reg_tr == r).any() else np.array([np.inf])
                for r in (0, 1)}
        best, tau = -np.inf, (np.inf, np.inf)
        for a in cand[0]:
            for b in cand[1]:
                al = np.where(reg_tr == 1, s >= b, s >= a)
                v = tss(y, al)[0]
                if v > best + 1e-12:
                    best, tau = v, (a, b)
        st = np.nan_to_num(ev.loc[te, col].to_numpy(float), nan=-np.inf)
        rt = ev.loc[te, reg_col].to_numpy()
        ev.loc[te, "alerta"] = np.where(rt == 1, st >= tau[1], st >= tau[0])
    yy = np.r_[ev.disparador.to_numpy(), np.ones(len(ciegos))]
    aa = np.r_[ev.alerta.to_numpy(), np.zeros(len(ciegos), bool)]
    return ev, tss(yy, aa)


def fila(nombre, r, res, ciegos):
    t, pod, pofd, tp, fn, fp, tn = res
    ic = bootstrap(r, ciegos)
    al = r[r.alerta]
    sin = r[~r.temporada.isin(NINO)]
    cs = ciegos[~ciegos.temporada.isin(NINO)]
    t2 = tss(np.r_[sin.disparador, np.ones(len(cs))], np.r_[sin.alerta, np.zeros(len(cs), bool)])
    return dict(metodo=nombre, TSS=round(t, 2), TSS_ic90=ic["TSS"], POD=round(pod, 2), POFD=round(pofd, 3), aciertos=tp, fallos=fn, falsas=fp,
                pct_alertas_2024_25=round(100 * (al.temporada == "2024-25").mean()) if len(al) else np.nan,
                TSS_sin_2017_2023=round(t2[0], 2), positivos_sin_2017_2023=t2[3] + t2[4])


def main():
    pd.set_option("display.width", 230)
    E = estado_horario()
    print("Estado: % NaN", E.isna().mean().round(3).to_dict(), "| ICEN >= 0.4 en", round(100 * (E.icen >= 0.4).mean()), "% de las horas", flush=True)
    ev = pd.read_parquet(AQUI.parent / "A" / "fase_a_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    o = oof_estado(E)
    o = o[o.H == H_EV].set_index("hora")
    for k in ("B1_estado_5d", "B1_estado_ideal"):
        ev[k] = [score_model_safe(o[k], r) for r in ev.itertuples()]
    st = E.reindex(ev.inicio)
    ev["nino"] = (st.icen.to_numpy() >= 0.4).astype(int)
    ev["hum5d"] = st.hum_suelo_5d.to_numpy()
    filas = []
    for nombre, col in (("A2 + 24-72 h (base)", "A2_mas_72h"), ("(a) A2 + estado (humedad 5 d)", "B1_estado_5d"),
                        ("(a) A2 + estado (humedad ideal 1 h)", "B1_estado_ideal"), ("I-D calibrado lat 4 h (base)", "id_lat4")):
        r, _, res = evaluar_loso(ev, ciegos, col)
        filas.append(fila(nombre, r, res, ciegos))
    for col, et in (("A2_mas_72h", "A2 + 24-72 h"), ("id_lat4", "I-D lat 4 h")):
        r, res = umbral_regimen(ev, ciegos, col, "nino")
        filas.append(fila(f"(b) {et}, umbral por ICEN >= 0.4", r, res, ciegos))
        # humedad: régimen = humedad 5 d >= mediana de las horas de entrenamiento (se recalcula por temporada dentro de umbral_regimen vía columna fija:
        # la mediana se toma de TODAS las horas de dic-abr de las otras temporadas -> aproximación: mediana de los eventos de entrenamiento)
        evh = ev.copy()
        r2 = []
        for t in sorted(evh.temporada.unique()):
            med = evh.loc[evh.temporada != t, "hum5d"].median()
            r2.append(evh.loc[evh.temporada == t].assign(humedo=(evh.loc[evh.temporada == t, "hum5d"] >= med).astype(int)))
        evh = pd.concat(r2)
        r, res = umbral_regimen(evh, ciegos, col, "humedo")
        filas.append(fila(f"(b) {et}, umbral por humedad 5 d", r, res, ciegos))
    res = pd.DataFrame(filas)
    res.to_csv(AQUI / "fase_b1_resumen.csv", index=False)
    print(res.to_string(index=False))
    print("\nDisparadores por régimen ICEN:", ev[ev.disparador == 1].groupby("nino").size().to_dict(), "| eventos por régimen:", ev.groupby("nino").size().to_dict())
    ev.to_parquet(AQUI / "fase_b1_eventos.parquet", index=False)


if __name__ == "__main__":
    main()

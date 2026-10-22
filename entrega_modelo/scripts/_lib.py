"""Funciones comunes del paquete (AUTÓNOMO: solo lee entrega_modelo/inputs/; no importa el repo).
Cada función reproduce, con la misma lógica, una del repo (indicada entre corchetes). 03_validar.py comprueba que el resultado es el mismo.
"""
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTREGA = AQUI.parent
IN = ENTREGA / "inputs"
SALIDAS = ENTREGA / "salidas"
TRABAJO = SALIDAS / "trabajo"
MODELO = SALIDAS / "modelo"
REFERENCIA = SALIDAS / "referencia"

HS = (3, 6, 12, 24)
LATENCIA_H = 4                       # IMERG Early llega ~4 h tarde: en la hora t solo hay lluvia con etiqueta <= t-5
INTENSIDAD = ["i1h", "i3h", "i6h", "i1h_max6", "i3h_max6", "i6h_max6", "p24h", "p48h", "p72h"]
ESTADO = ["hum_suelo_5d", "dias_activ", "icen"]
VARIABLES = INTENSIDAD + ESTADO + ["H"]   # orden EXACTO de las columnas del modelo
# [modelo/arboles.py PARAMS_XGB + modelo/restringido.py CHICO]: fijados antes de entrenar
PARAMS = dict(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, min_child_weight=50, reg_lambda=10.0,
              tree_method="hist", n_jobs=4, verbosity=0)
MONOTONIA = tuple(0 if c == "dias_activ" else 1 for c in VARIABLES)
K_P2 = 4
TRAS_EVENTO_H = 3
NIVEL_LLUVIA_MIN = 0.1
EXACTO = "round_trip"            # lectura EXACTA de los floats del CSV (el parser rápido por defecto cambia la última cifra y, con ella, los cortes de XGBoost)


def temporada_de(hora):
    """'2014-15' = dic 2014 - abr 2015.  [modelo/comun.py temporada_de]"""
    h = pd.DatetimeIndex(hora)
    a = np.where(h.month >= 6, h.year, h.year - 1)
    return np.array([f"{x}-{str(x + 1)[2:]}" for x in a])


# --------------------------------------------------------------------------- insumos
def lluvia_celdas():
    R = pd.read_csv(IN / "lluvia_horaria_celdas.csv", index_col="hora", parse_dates=["hora"], float_precision=EXACTO)
    return R.astype("float64").asfreq("h")


def humedad():
    s = pd.read_csv(IN / "humedad_suelo_horaria.csv", index_col="hora", parse_dates=["hora"], float_precision=EXACTO).hum_suelo_0_7cm
    return s.asfreq("h")


def activaciones():
    return pd.read_csv(IN / "activaciones.csv", parse_dates=["fecha"], keep_default_na=False)


def terreno():
    return pd.read_csv(IN / "quebradas_terreno.csv", float_precision=EXACTO).set_index("quebrada_id").sort_index()


def eventos():
    """(eventos evaluados, días ciegos).  [modelo/v3/comun_v3.py eventos_lluvia + etiquetar; definiciones en ese archivo]"""
    e = pd.read_csv(IN / "eventos_lluvia.csv", parse_dates=["inicio", "fin", "huaico_fin"], float_precision=EXACTO)
    e["tormenta"] = e.tormenta.fillna("")
    ev = e[e.tipo == "evento"].drop(columns="tipo").reset_index(drop=True)
    ev["disparador"] = ev.disparador.astype(int)
    ciegos = e[e.tipo == "dia_ciego"].rename(columns={"inicio": "fecha"})[["tormenta", "fecha", "temporada"]].reset_index(drop=True)
    return ev, ciegos


# --------------------------------------------------------------------------- variables
def variables_intensidad():
    """[modelo/v3/A/fase_a.py features_intensidad]: máximo entre las 5 celdas de la lluvia de 1/3/6 h (y su máximo en 6 h) y de 24/48/72 h, con latencia."""
    L = lluvia_celdas().shift(LATENCIA_H + 1)
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


def variables_estado(idx):
    """[modelo/v3/B/fase_b1.py estado_horario] humedad de t-5 días; días desde la última activación (fechas < día de t, tope 3650); ICEN publicado."""
    idx = pd.DatetimeIndex(idx)
    sm = humedad()
    E = pd.DataFrame(index=idx)
    E["hum_suelo_5d"] = sm.reindex(idx - pd.Timedelta(days=5)).to_numpy()
    fechas = np.array(sorted(set(activaciones().fecha)), dtype="datetime64[ns]")
    dia = idx.normalize().to_numpy()
    k = np.searchsorted(fechas, dia, side="left") - 1
    ult = np.where(k >= 0, fechas[np.clip(k, 0, None)], np.datetime64("NaT"))
    d = (dia - ult) / np.timedelta64(1, "D")
    E["dias_activ"] = np.where(np.isnan(d), 3650, np.minimum(d, 3650))
    ic = pd.read_csv(IN / "icen.csv", float_precision=EXACTO)
    ic = dict(zip(zip(ic.anio, ic.mes), ic.icen))
    atras = np.where(idx.day >= 10, 2, 3)
    per = idx.to_period("M") - atras
    E["icen"] = [ic.get((p.year, p.month), np.nan) for p in per]
    E.index.name = "hora"
    return E


def variables_horarias(horas):
    horas = pd.DatetimeIndex(horas)
    return variables_intensidad().reindex(horas).join(variables_estado(horas))[[c for c in VARIABLES if c != "H"]]


def tabla_zona():
    """[modelo/v3/final/modelo_final.py tabla_zona] una fila = zona x hora x H, con etiqueta y variables (mismo orden de filas que en el repo)."""
    z = pd.read_csv(IN / "etiquetas_zona.csv", parse_dates=["hora"])
    z = z.merge(variables_intensidad(), left_on="hora", right_index=True, how="left")
    z = z.merge(variables_estado(pd.date_range("2014-12-01", "2026-04-30 23:00", freq="h")), left_on="hora", right_index=True, how="left")
    z["temporada"] = temporada_de(z.hora)
    return z


# --------------------------------------------------------------------------- modelo P1
def ajustar(z, semilla=0):
    """[modelo/v3/final/modelo_final.py ajustar]"""
    import xgboost as xgb

    tr = z.y.notna().to_numpy()
    y = z.y.to_numpy()[tr]
    spw = float(np.sqrt((y == 0).sum() / (y == 1).sum()))
    return xgb.XGBClassifier(**PARAMS, scale_pos_weight=spw, monotone_constraints=MONOTONIA, random_state=semilla).fit(z.loc[tr, VARIABLES], y)


def oof_loso(z):
    """[modelo/v3/B/fase_b1.py oof_estado] cada temporada predicha por un modelo entrenado con las otras 11."""
    import xgboost as xgb

    y, temp = z.y.to_numpy(), z.temporada.to_numpy()
    lab = ~np.isnan(y)
    p = np.full(len(z), np.nan)
    for s in np.unique(temp):
        te, tr = temp == s, (temp != s) & lab
        spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
        m = xgb.XGBClassifier(**PARAMS, scale_pos_weight=spw, monotone_constraints=MONOTONIA, random_state=0)
        p[te] = m.fit(z.loc[tr, VARIABLES], y[tr]).predict_proba(z.loc[te, VARIABLES])[:, 1]
    return p


# --------------------------------------------------------------------------- evaluación por evento  [modelo/v3/comun_v3.py y A/fase_a.py]
def puntaje_evento(serie, r):
    """Máximo del puntaje horario en [inicio, última hora útil]: disparador -> t < fin del huaico; no disparador -> hasta fin + 3 h."""
    b = (r.huaico_fin - pd.Timedelta(minutes=1)).floor("h") if r.disparador == 1 else r.fin + pd.Timedelta(hours=TRAS_EVENTO_H)
    x = serie.loc[r.inicio:b]
    return float(x.max()) if len(x) else np.nan


def tss(y, a):
    y, a = np.asarray(y, bool), np.asarray(a, bool)
    tp, fn, fp, tn = (y & a).sum(), (y & ~a).sum(), (~y & a).sum(), (~y & ~a).sum()
    pod = tp / (tp + fn) if tp + fn else np.nan
    pofd = fp / (fp + tn) if fp + tn else np.nan
    return pod - pofd, pod, pofd, int(tp), int(fn), int(fp), int(tn)


def mejor_umbral(s, y):
    cand = np.unique(s[~np.isnan(s)])
    if len(cand) == 0:
        return np.inf
    mejor, tau = -np.inf, cand[-1]
    for c in cand[::-1]:
        t = tss(y, s >= c)[0]
        if t > mejor + 1e-12:
            mejor, tau = t, c
    return tau


def evaluar_loso(ev, ciegos, col):
    ev = ev.copy()
    ev["alerta"] = False
    taus = {}
    for t in sorted(ev.temporada.unique()):
        tr = ev.temporada != t
        taus[t] = mejor_umbral(np.nan_to_num(ev.loc[tr, col].to_numpy(dtype=float), nan=-np.inf), ev.loc[tr, "disparador"].to_numpy())
        te = ev.temporada == t
        ev.loc[te, "alerta"] = np.nan_to_num(ev.loc[te, col].to_numpy(dtype=float), nan=-np.inf) >= taus[t]
    y = np.r_[ev.disparador.to_numpy(), np.ones(len(ciegos))]
    a = np.r_[ev.alerta.to_numpy(), np.zeros(len(ciegos), bool)]
    return ev, taus, tss(y, a)


def bootstrap(ev, ciegos, n=2000, semilla=0):
    rng = np.random.default_rng(semilla)
    pos = ev[ev.disparador == 1]
    tor = sorted(set(pos.tormenta) | set(ciegos.tormenta))
    por_tor = {t: (pos.alerta[pos.tormenta == t].to_numpy(), int(ciegos.loc[ciegos.tormenta == t].shape[0])) for t in tor}
    neg = ev[ev.disparador == 0]
    grupos = [g.alerta.to_numpy() for _, g in neg.groupby("temporada")]
    out = []
    for _ in range(n):
        tp = fn = 0
        for t in rng.choice(tor, len(tor), replace=True):
            al, nc = por_tor[t]
            tp += int(al.sum())
            fn += int((~al).sum()) + nc
        fa = sum(int(rng.choice(g, len(g), replace=True).sum()) for g in grupos)
        nn = sum(len(g) for g in grupos)
        pod, pofd = tp / max(tp + fn, 1), fa / max(nn, 1)
        out.append((pod - pofd, pod, pofd))
    o = np.array(out)
    return {k: (round(float(np.quantile(o[:, i], .05)), 2), round(float(np.quantile(o[:, i], .95)), 2)) for i, k in enumerate(("TSS", "POD", "POFD"))}


def umbrales_oof(oof, ev, ciegos, excluir=None):
    """[modelo/v3/final/modelo_final.py umbrales_oof] rojo = máx. TSS por evento; amarillo = POD >= 0.9 o, si es inalcanzable, el máximo POD posible."""
    if excluir:
        ev, ciegos = ev[ev.temporada != excluir], ciegos[ciegos.temporada != excluir]
    out = {}
    for H in HS:
        s = oof[oof.H == H].set_index("hora").p
        sc = np.nan_to_num(np.array([puntaje_evento(s, r) for r in ev.itertuples()]), nan=-np.inf)
        y = ev.disparador.to_numpy()
        rojo = mejor_umbral(sc, y)
        n_pos = int(y.sum()) + len(ciegos)
        amar = np.min(sc[(y == 1) & np.isfinite(sc)])
        for c in np.unique(sc[np.isfinite(sc)])[::-1]:
            if ((sc >= c) & (y == 1)).sum() / n_pos >= 0.9:
                amar = c
                break
        amar = min(amar, rojo)
        yy = np.r_[y, np.ones(len(ciegos))]
        t_r, pod_r, pofd_r = tss(yy, np.r_[sc >= rojo, np.zeros(len(ciegos), bool)])[:3]
        t_a, pod_a, pofd_a = tss(yy, np.r_[sc >= amar, np.zeros(len(ciegos), bool)])[:3]
        out[H] = dict(rojo_oof=float(rojo), amarillo_oof=float(amar), cuantil_rojo=float((s.dropna() < rojo).mean()), cuantil_amarillo=float((s.dropna() < amar).mean()),
                      rojo_TSS=round(t_r, 2), rojo_POD=round(pod_r, 2), rojo_POFD=round(pofd_r, 3), amarillo_TSS=round(t_a, 2), amarillo_POD=round(pod_a, 2),
                      amarillo_POFD=round(pofd_a, 3))
    return out


# --------------------------------------------------------------------------- P2  [modelo/dos_piezas/base.py tormentas, pieza2.py matriz_activacion y p2]
def tormentas():
    a = activaciones()[["fecha", "quebrada_id"]].drop_duplicates()
    f = pd.Series(sorted(a.fecha.unique()))
    grupo = (f.diff() > pd.Timedelta(days=2)).cumsum()
    filas = []
    for k, fs in f.groupby(grupo):
        q = sorted(a[a.fecha.isin(fs)].quebrada_id.unique())
        filas.append(dict(tormenta=f"T{k + 1:02d}", temporada=temporada_de(fs.iloc[:1])[0], inicio=fs.min(), fin=fs.max(), activadas=",".join(q)))
    return pd.DataFrame(filas)


def p2(entrenar=None):
    """P2 = (n_activaciones + 4 p_terreno) / (n_tormentas + 4); p_terreno = logística (C = 1) con log10(área) y pendiente, solo con las tormentas `entrenar`."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    torm = tormentas()
    T = terreno()
    A = pd.DataFrame(0, index=torm.tormenta, columns=T.index)
    for r in torm.itertuples():
        A.loc[r.tormenta, r.activadas.split(",")] = 1
    S = A.loc[list(torm.tormenta if entrenar is None else entrenar(torm))]
    n, n_act = len(S), S.sum(axis=0)
    cols = ["log10_area_km2", "pendiente_media"]
    X = np.tile(T[cols].to_numpy(), (n, 1))
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=1.0, max_iter=2000).fit(sc.transform(X), S.to_numpy().ravel())
    pt = lr.predict_proba(sc.transform(T[cols].to_numpy()))[:, 1]
    return ((n_act + K_P2 * pt) / (n + K_P2)).rename("p2")


# --------------------------------------------------------------------------- salidas  [entrega_modelo/scripts/predecir_demo.py]
QUEBRADAS = {"carossio": "Carossio", "corrales": "Corrales", "pedregal": "Pedregal", "california": "California", "la_ronda": "La Ronda",
             "quirio": "Quirio", "santa_maria": "Santa María", "chacrasana": "Chacrasana", "libertad": "Libertad",
             "mariscal_castilla": "Mariscal Castilla", "rosario": "Rosario", "el_vallecito": "El Vallecito", "la_cantuta": "La Cantuta",
             "santo_domingo": "Santo Domingo", "alto_peru": "Alto Perú", "huampani": "Huampaní", "buenos_aires": "Buenos Aires"}


def tiempo(h):
    return [f"{t.day}/{t.month:02d}/{t.year} {t:%H:%M}" for t in pd.DatetimeIndex(h)]


def archivo_a(horas, pz, p2s, paso=60):
    filas = [[h, q, nombre] + [round(float(pz[H][i] * p2s[q]), 5) for H in HS] for i, h in enumerate(horas) for q, nombre in QUEBRADAS.items()]
    A = pd.DataFrame(filas, columns=["hora", "quebrada_id", "quebrada"] + [f"prob_ml_{H}h" for H in HS])
    if paso == 30:
        A = pd.concat([A, A.assign(hora=A.hora + pd.Timedelta(minutes=30))]).sort_values("hora", kind="stable").reset_index(drop=True)
    A.insert(0, "Tiempo", tiempo(A.hora))
    return A.drop(columns="hora")


def archivo_b(horas, X, pz, u):
    filas = []
    for H in HS:
        r, a, p, lluvia = u[H]["rojo"], u[H]["amarillo"], pz[H], X.i6h.to_numpy()
        supera = p >= r
        oficial = np.where(supera, "rojo", np.where(p >= a, "amarillo", "verde"))                                   # nivel (validado)
        con_lluvia = np.where(supera & (lluvia > NIVEL_LLUVIA_MIN), "rojo", np.where(supera | (p >= a), "amarillo", "verde"))  # variante
        filas.append(pd.DataFrame({"hora": horas, "H": H, "p_zona": np.round(p, 5), "umbral_rojo": round(r, 5), "umbral_amarillo": round(a, 5),
                                   "nivel": oficial, "nivel_con_lluvia": con_lluvia, "lluvia_6h_mm": np.round(lluvia, 2)}))
    B = pd.concat(filas).sort_values(["hora", "H"], kind="stable").reset_index(drop=True)
    B.insert(0, "Tiempo", tiempo(B.hora))
    return B.drop(columns="hora")

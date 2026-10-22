"""v3: piezas comunes. Eventos de lluvia IMERG en la zona, huaicos con hora (etiquetas v2), evaluación por EVENTO (TSS) con validación por temporada.

Definiciones (fijadas antes de correr; ver modelo/v3/RESUMEN.md):
  - Lluvia de la zona: máximo horario entre las 5 celdas IMERG Early de las quebradas (mm/h, hora local de inicio). Hora lluviosa: >= 0.1 mm.
  - Evento de lluvia: racha de horas lluviosas separada de la siguiente por >= 6 h secas. Solo dic-abr (temporadas 2014-15..2025-26).
  - Huaico con hora: activación del catálogo en las 17 quebradas con hora usable; rango [ini, fin] de v2 (B: horas_B_v2.csv; A: hora_inicio..hora_fin).
  - Evento DISPARADOR: algún huaico con hora cuyo rango toca [inicio del evento, fin del evento + 3 h].
  - Evento DESCONOCIDO (se excluye): no disparador y toca un día con huaico sin hora/sin quebrada (17) o con huaico solo en distritos vecinos /
    quebradas excluidas (regla 9.2): ahí "sin huaico" no es confiable.
  - Huaico CIEGO: grupo de huaicos con hora (misma tormenta: fechas a <= 2 días) que no toca ningún evento de lluvia -> FALLO obligatorio.
  - Unidad de bootstrap: la tormenta (eventos disparadores y ciegos de la misma tormenta van juntos); los no disparadores se remuestrean por temporada.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V3 = Path(__file__).resolve().parent
MODELO = V3.parent
RAIZ = MODELO.parent
sys.path.insert(0, str(MODELO))
sys.path.insert(0, str(RAIZ / "lluvia"))
from comun import dias_evento_fuera_del_piloto, temporada_de  # noqa: E402

UMBRAL_HUMEDO = 0.1
SECAS = 6
TRAS = 3
CACHE = V3 / "_cache"
CACHE.mkdir(exist_ok=True)


def lluvia_celdas():
    ruta = CACHE / "lluvia_celdas.parquet"
    if not ruta.exists():
        import features_lluvia as fl

        R = fl.lluvia_celdas(RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv"))
        R.columns = [str(c) for c in R.columns]
        R.to_parquet(ruta)
    return pd.read_parquet(ruta)


def lluvia_zona():
    """Serie horaria de la zona: máximo entre celdas (NaN si falta alguna)."""
    R = lluvia_celdas()
    z = R.max(axis=1, skipna=False)
    return z[z.index.month.isin([12, 1, 2, 3, 4])]


def huaicos_v2():
    """Huaicos con hora usable en las 17 quebradas: id, fecha, quebrada_id, ini, fin (rango v2)."""
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    hb = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "horas_B_v2.csv", dtype=str, keep_default_na=False).set_index("id")
    u = c[c.en_piloto.eq("True") & c.usable_horario.eq("True") & c.quebrada_id.ne("")].copy()
    ini = u.apply(lambda r: hb.loc[r.id, "hora_inicio_v2"] if r.id in hb.index else r.hora_inicio, axis=1)
    fin = u.apply(lambda r: hb.loc[r.id, "hora_fin_v2"] if r.id in hb.index else r.hora_fin, axis=1)
    u["ini"] = pd.to_datetime(u.fecha + " " + ini)
    u["fin"] = pd.to_datetime(u.fecha + " " + fin)
    u.loc[u.fin < u.ini, "fin"] += pd.Timedelta(days=1)
    return u[["id", "fecha", "quebrada_id", "ini", "fin", "conf_temporal"]].reset_index(drop=True)


def dias_desconocidos():
    """Días donde 'sin huaico' no es confiable: huaicos sin hora/sin quebrada del piloto, y días con huaico solo fuera de las 17 (regla 9.2)."""
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    fuera = set(al.loc[al.motivo.str.contains("en_piloto = False"), "nombre_catalogo"])
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    p = c[c.en_piloto.eq("True") & ~c.quebrada.isin(fuera)]
    sin = p[~(p.usable_horario.eq("True") & p.quebrada_id.ne(""))]
    return set(pd.to_datetime(sin.fecha)) | set(pd.to_datetime(dias_evento_fuera_del_piloto()))


def eventos_lluvia(z=None):
    """Tabla de eventos: inicio, fin (hora de la última hora lluviosa), duración (h), total, máximos de 1/3/6 h."""
    z = lluvia_zona() if z is None else z
    z = z.asfreq("h")
    hum = (z >= UMBRAL_HUMEDO).to_numpy()
    idx = z.index
    filas, i, n = [], 0, len(z)
    while i < n:
        if not hum[i]:
            i += 1
            continue
        j, ultimo = i, i
        while j < n:
            if hum[j]:
                ultimo = j
            elif j - ultimo >= SECAS or np.isnan(z.iloc[j]):
                break
            j += 1
        x = z.iloc[i: ultimo + 1].fillna(0).to_numpy()
        filas.append(dict(inicio=idx[i], fin=idx[ultimo], duracion_h=ultimo - i + 1, total_mm=float(x.sum()),
                          max1=float(x.max()), max3=float(pd.Series(x).rolling(3, min_periods=1).sum().max()),
                          max6=float(pd.Series(x).rolling(6, min_periods=1).sum().max())))
        i = ultimo + 1
    e = pd.DataFrame(filas)
    e["temporada"] = temporada_de(e.inicio)
    return e


def tormenta_id(fechas):
    f = pd.Series(sorted(set(pd.to_datetime(fechas))))
    g = (f.diff() > pd.Timedelta(days=2)).cumsum()
    return {d: f"S{k:02d}" for d, k in zip(f, g)}


def etiquetar(e, hu=None, desconocidos=None):
    """Agrega a los eventos: disparador (0/1), huaico_fin (fin más temprano de los huaicos que toca), tormenta, desconocido.
    Devuelve (eventos, ciegos) donde ciegos = tormentas con huaicos con hora que no tocan ningún evento (FALLOS obligatorios)."""
    hu = huaicos_v2() if hu is None else hu
    desconocidos = dias_desconocidos() if desconocidos is None else desconocidos
    tor = tormenta_id(hu.fecha)
    hu = hu.assign(tormenta=pd.to_datetime(hu.fecha).map(tor))
    e = e.copy()
    e["disparador"], e["huaico_fin"], e["tormenta"] = 0, pd.NaT, ""
    usados = set()
    for k, r in e.iterrows():
        a, b = r.inicio, r.fin + pd.Timedelta(hours=TRAS + 1)
        m = (hu.ini < b) & (hu.fin >= a)
        if m.any():
            e.loc[k, ["disparador", "huaico_fin", "tormenta"]] = [1, hu.loc[m, "fin"].min(), hu.loc[m, "tormenta"].iloc[0]]
            usados |= set(hu.index[m])
    dias = e.apply(lambda r: set(pd.date_range(r.inicio.normalize(), (r.fin + pd.Timedelta(hours=TRAS)).normalize())), axis=1)
    e["desconocido"] = (e.disparador == 0) & dias.apply(lambda s: bool(s & desconocidos))
    # ciego = DÍA con huaicos con hora en el que ninguno toca un evento de lluvia (si otro huaico del mismo día sí lo toca, el día no es ciego)
    vistos = set(hu.loc[list(usados), "fecha"])
    ciegos = hu.drop(index=list(usados))
    ciegos = ciegos[~ciegos.fecha.isin(vistos)]
    resto = ciegos.groupby(["tormenta", "fecha"]).agg(huaicos=("id", "size")).reset_index()
    resto["temporada"] = temporada_de(pd.to_datetime(resto.fecha))
    return e, resto


# --------------------------------------------------------------------------- evaluación por evento
def tss(y, a):
    y, a = np.asarray(y, bool), np.asarray(a, bool)
    tp, fn = (y & a).sum(), (y & ~a).sum()
    fp, tn = (~y & a).sum(), (~y & ~a).sum()
    pod = tp / (tp + fn) if tp + fn else np.nan
    pofd = fp / (fp + tn) if fp + tn else np.nan
    return pod - pofd, pod, pofd, int(tp), int(fn), int(fp), int(tn)


def mejor_umbral(s, y):
    """Umbral que maximiza el TSS (alerta si s >= umbral) con los datos de entrenamiento. En empate, el más alto (menos alertas)."""
    cand = np.unique(s[~np.isnan(s)])
    if len(cand) == 0:
        return np.inf
    mejor, tau = -np.inf, cand[-1]
    for c in cand[::-1]:
        t = tss(y, s >= c)[0]
        if t > mejor + 1e-12:
            mejor, tau = t, c
    return tau


def evaluar_loso(ev, ciegos, col, umbral_fijo=None):
    """ev: eventos NO desconocidos con columna de puntaje `col` (NaN = sin dato -> no alerta). ciegos: tormentas sin evento (fallos).
    Umbral por temporada: maximiza el TSS en las otras temporadas (incluye sus ciegos como fallos, que no dependen del umbral).
    Devuelve tabla por evento con 'alerta' fuera de muestra, y el resumen."""
    ev = ev.copy()
    ev["alerta"] = False
    temps = sorted(ev.temporada.unique())
    taus = {}
    for t in temps:
        tr = ev.temporada != t
        s = ev.loc[tr, col].to_numpy(dtype=float)
        taus[t] = umbral_fijo if umbral_fijo is not None else mejor_umbral(np.nan_to_num(s, nan=-np.inf), ev.loc[tr, "disparador"].to_numpy())
        te = ev.temporada == t
        ev.loc[te, "alerta"] = np.nan_to_num(ev.loc[te, col].to_numpy(dtype=float), nan=-np.inf) >= taus[t]
    y = np.r_[ev.disparador.to_numpy(), np.ones(len(ciegos))]
    a = np.r_[ev.alerta.to_numpy(), np.zeros(len(ciegos), bool)]
    return ev, taus, tss(y, a)


def bootstrap(ev, ciegos, n=2000, semilla=0):
    """IC 90 % del TSS, POD y POFD: remuestrea tormentas (disparadores + ciegos juntos) y eventos no disparadores dentro de cada temporada."""
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

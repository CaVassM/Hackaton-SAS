"""M1 (pre-registrada): más positivos de la ZONA para P1. Zona = área de las 5 celdas IMERG de las quebradas (lat -12.0..-11.8, lon -76.9..-76.6).

Casos nuevos (CSV para revisión del usuario: casos_nuevos_zona.csv):
  - Catálogo de prensa: activaciones fuera de las 17 quebradas pero dentro de la zona: Chaclacayo (Girasoles, La Floresta, Los Cóndores, Los Laureles,
    Cusipata, Huascarán, El Cuadro, Av. Los Álamos), Santa Eulalia baja (Cashahuacra, Lúcuma Seca, Buenos Aires, Huayaringa, Palle Viejo, Cuculí,
    Lucumaseca) y Lurigancho sin quebrada ubicada (La Trinchera, Lechuceros, Los Molles, sectores Tarazona, Moyopampa, Puente Caracol, Nicolás de Piérola).
    FUERA de la zona (siguen como días "desconocidos", regla 9.2): Huaycoloro y Río Seco (cuencas grandes fuera del recorte), Jicamarca (SJL),
    Huaycán (Ate), San Antonio (Huarochirí).
  - INDECI/SINPAD (HUAYCO, dic-abr 2015-2026) en Lurigancho, Chaclacayo, Ricardo Palma y Santa Eulalia: sin hora, ubicación de distrito, la fecha puede
    ser de registro -> confianza BAJA. NASA COOLR Santa Eulalia 2015-03-24 (sin hora).
  Con hora (catálogo, conf A/B, referencia huaico/publicación): rango [hora_inicio, hora_fin] tal como está en el catálogo (sin releer fuentes: pendiente
    de revisión). Sin hora: rango = día completo [00:00, 23:00] -> regla v2: solo puede ser positivo con H = 24; NaN en ventanas que lo tocan a medias.
Etiqueta de zona M1 (por H): 1 si alguna fuente (17 quebradas v2 o caso nuevo) da 1; NaN si alguna da NaN y ninguna 1; si no 0. Además NaN (como en 9.2)
  los días con huaico SOLO fuera de la zona.
B1 reentrenado con estas etiquetas (mismas variables y parámetros, LOSO, semillas 0-2). P2 no cambia.
Evaluación: (a) los 13 positivos originales por evento (mismos eventos y reglas que v3); (b1) por evento con TODOS los positivos con hora de la zona
  (17 + vecinas); (b2) por DÍA local con todos los positivos de la zona (con y sin hora; modelo del mismo día: máximo horario del día).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
V3 = AQUI.parents[1] / "v3"
sys.path.insert(0, str(V3 / "B"))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3 / "A"))
from fase_b1 import A2, CHICO, MODELO, PARAMS_XGB, RAIZ, base, estado_horario, features_intensidad, score_model_safe  # noqa: E402
from comun_v3 import (CACHE, bootstrap, dias_desconocidos, etiquetar, evaluar_loso, eventos_lluvia, huaicos_v2, lluvia_zona, mejor_umbral,  # noqa: E402
                      tormenta_id, tss)
from comun import dias_evento_fuera_del_piloto, temporada_de  # noqa: E402

HS = (3, 6, 12, 24)
VARS = A2["A2_mas_72h"] + ["hum_suelo_5d", "dias_activ", "icen", "H"]
FUERA_ZONA = {"Huaycoloro", "Rioseco", "Jicamarca", "Huaycán"}
DISTRITOS_FUERA = ("San Juan de Lurigancho", "SJL", "Ate", "San Antonio, Huarochirí")
INDECI_ZONA = {"LURIGANCHO", "CHACLACAYO", "RICARDO PALMA", "SANTA EULALIA"}


def casos_nuevos():
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    x = c[c.quebrada_id.eq("") & ~c.quebrada.isin(FUERA_ZONA) & ~c.distrito.str.startswith(DISTRITOS_FUERA)].copy()
    con_hora = x.hora_inicio.ne("") & x.conf_temporal.isin(["A", "B"]) & x.referencia_hora.isin(["huaico", "publicacion"])
    filas = [dict(fuente="catálogo prensa", id=r.id, fecha=r.fecha, hora_inicio=r.hora_inicio if h else "", hora_fin=r.hora_fin if h else "",
                  nombre=r.quebrada or r.sector, distrito=r.distrito, url=r.url, con_hora=bool(h), confianza=f"temporal {r.conf_temporal}",
                  dudoso=r.dudoso, texto=r.hora_texto) for r, h in zip(x.itertuples(), con_hora)]
    m = pd.read_csv(V3 / "D" / "catalogo_multizona.csv", parse_dates=["fecha"])
    m = m[m.fecha.dt.month.isin([12, 1, 2, 3, 4]) & (m.fecha >= "2015-01-01")]
    ind = m[m.fuente.eq("INDECI SINPAD") & m.distrito.str.upper().isin(INDECI_ZONA)]
    gl = m[m.fuente.eq("NASA GLC (COOLR)") & m.distrito.str.contains("Santa Eulalia", na=False)]
    for r in pd.concat([ind, gl]).itertuples():
        filas.append(dict(fuente=r.fuente, id=r.texto.split("|")[0].strip() if r.fuente.startswith("INDECI") else "COOLR", fecha=r.fecha.strftime("%Y-%m-%d"),
                          hora_inicio="", hora_fin="", nombre=r.distrito, distrito=r.distrito, url=r.url, con_hora=False,
                          confianza="BAJA (distrito; fecha puede ser de registro)" if r.fuente.startswith("INDECI") else "media (5 km)", dudoso="",
                          texto=str(r.texto)[:200]))
    d = pd.DataFrame(filas)
    hu17 = huaicos_v2()
    fechas17 = set(pd.to_datetime(c.fecha[c.en_piloto.eq("True") & c.quebrada_id.ne("")]).dt.strftime("%Y-%m-%d"))
    d["fecha_ya_tiene_activacion_de_las_17"] = d.fecha.isin(fechas17)
    d["temporada"] = temporada_de(pd.to_datetime(d.fecha))
    d = d[pd.to_datetime(d.fecha).dt.month.isin([12, 1, 2, 3, 4])]
    return d.sort_values(["fecha", "fuente"]).reset_index(drop=True)


def rangos(d):
    ini = pd.to_datetime(d.fecha + " " + np.where(d.con_hora, d.hora_inicio, "00:00"))
    fin = pd.to_datetime(d.fecha + " " + np.where(d.con_hora, d.hora_fin, "23:00"))
    fin = fin.where(fin >= ini, fin + pd.Timedelta(days=1))
    return ini, fin


def etiquetas_zona_m1(d):
    """(hora, H, y) de la zona con las fuentes combinadas."""
    ini, fin = rangos(d)
    out = []
    horas = pd.date_range("2015-01-01", "2026-06-30 23:00", freq="h")
    for H in HS:
        e = pd.read_parquet(RAIZ / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
        g = e.groupby("hora").y
        uno, nan = (g.max() == 1).reindex(horas, fill_value=False).to_numpy(), g.apply(lambda s: s.isna().any()).reindex(horas, fill_value=False).to_numpy()
        t = horas.to_numpy("datetime64[ns]")
        Hd = np.timedelta64(H, "h")
        for a, b in zip(ini.to_numpy("datetime64[ns]"), fin.to_numpy("datetime64[ns]")):
            toca = (t < b) & (t + Hd >= a)
            cont = (t < a) & (t + Hd >= b)
            post = (t >= a) & (t <= b + np.timedelta64(24, "h"))
            uno |= cont
            nan |= (toca & ~cont) | post
        # 9.2: días con huaico SOLO fuera de la zona
        dz = set(pd.to_datetime(d.fecha)) | set(pd.to_datetime(e.loc[e.y == 1, "hora"]).dt.normalize())
        for dia in dias_evento_fuera_del_piloto():
            dia = pd.Timestamp(dia)
            if dia in set(pd.to_datetime(d.fecha)):
                continue
            nan |= (t < np.datetime64(dia + pd.Timedelta(hours=24))) & (t + Hd > np.datetime64(dia))
        y = np.where(uno, 1.0, np.where(nan, np.nan, 0.0))
        out.append(pd.DataFrame({"hora": horas, "H": H, "y": y}))
    z = pd.concat(out, ignore_index=True)
    return z[z.hora.dt.month.isin([12, 1, 2, 3, 4])].reset_index(drop=True)


def oof_m1(z):
    ruta = AQUI / "oof_m1.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    z = z.merge(features_intensidad(), left_on="hora", right_index=True, how="left").merge(estado_horario(), left_on="hora", right_index=True, how="left")
    z["temporada"] = temporada_de(z.hora)
    y, temp = z.y.to_numpy(), z.temporada.to_numpy()
    lab = ~np.isnan(y)
    mono = tuple(0 if c == "dias_activ" else 1 for c in VARS)
    out = z[["hora", "H"]].copy()
    for sem in (0, 1, 2):
        p = np.full(len(z), np.nan)
        for s in np.unique(temp):
            te, tr = temp == s, (temp != s) & lab
            spw = float(np.sqrt((y[tr] == 0).sum() / (y[tr] == 1).sum()))
            m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=sem)
            p[te] = m.fit(z.loc[tr, VARS], y[tr]).predict_proba(z.loc[te, VARS])[:, 1]
        out[f"M1_s{sem}"] = p
    out.to_parquet(ruta, index=False)
    return out


def fila(nombre, r, ciegos, res):
    t, pod, pofd, tp, fn, fp, tn = res
    ic = bootstrap(r, ciegos)
    return dict(metodo=nombre, positivos=tp + fn, TSS=round(t, 2), TSS_ic90=ic["TSS"], POD=round(pod, 2), POFD=round(pofd, 3), aciertos=tp, fallos=fn, falsas=fp)


def eval_dia(serie_h, dias_pos, dias_desc, temps_rango):
    """Zona-día (día local): puntaje = máximo horario del día (H=3); y = 1 si hay activación de la zona ese día. LOSO por temporada."""
    s = serie_h.groupby(serie_h.index.normalize()).max()
    Z = pd.DataFrame({"fecha": s.index, "s": s.to_numpy()})
    Z = Z[Z.fecha.dt.month.isin([12, 1, 2, 3, 4]) & (Z.fecha >= "2015-01-01")]
    Z["y"] = Z.fecha.isin(dias_pos).astype(int)
    Z = Z[~Z.fecha.isin(dias_desc) | (Z.y == 1)]
    Z["temporada"] = temporada_de(Z.fecha)
    al = np.zeros(len(Z), bool)
    for t in Z.temporada.unique():
        tr, te = (Z.temporada != t).to_numpy(), (Z.temporada == t).to_numpy()
        sc = np.nan_to_num(Z.s.to_numpy(float), nan=-np.inf)
        al[te] = sc[te] >= mejor_umbral(sc[tr], Z.y.to_numpy()[tr])
    Z["a"] = al
    fp = sorted(Z.fecha[Z.y == 1])
    tor = dict(zip(fp, (pd.Series(fp).diff() > pd.Timedelta(days=2)).cumsum()))
    rng = np.random.default_rng(0)
    pos = Z[Z.y == 1].assign(tor=lambda d: d.fecha.map(tor))
    negs = [g.a.to_numpy() for _, g in Z[Z.y == 0].groupby("temporada")]
    bs = []
    for _ in range(1000):
        sel = pd.concat([pos[pos.tor == k] for k in rng.choice(pos.tor.unique(), pos.tor.nunique())])
        bs.append(sel.a.mean() - sum(rng.choice(g, len(g)).sum() for g in negs) / sum(len(g) for g in negs))
    t, pod, pofd, tp, fn, fp_, tn = tss(Z.y, Z.a)
    return dict(TSS=round(t, 2), TSS_ic90=(round(float(np.quantile(bs, .05)), 2), round(float(np.quantile(bs, .95)), 2)), POD=round(pod, 2), POFD=round(pofd, 3),
                aciertos=tp, fallos=fn, falsas=fp_, positivos=tp + fn)


def main():
    pd.set_option("display.width", 240)
    d = casos_nuevos()
    d.to_csv(AQUI / "casos_nuevos_zona.csv", index=False, encoding="utf-8")
    print(f"Casos nuevos de la zona: {len(d)} (con hora {int(d.con_hora.sum())}; en fechas SIN activación de las 17: "
          f"{int((~d.fecha_ya_tiene_activacion_de_las_17).sum())}); por fuente: {d.fuente.value_counts().to_dict()}", flush=True)
    z = etiquetas_zona_m1(d)
    base.cargar_etiquetas = lambda H: pd.read_parquet(MODELO.parent / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    z3 = base.etiquetas_zona()
    comp = pd.DataFrame({"v3_positivos": z3.groupby("H").y.sum(), "M1_positivos": z.groupby("H").y.sum(),
                         "v3_NaN": z3.groupby("H").y.apply(lambda s: s.isna().sum()), "M1_NaN": z.groupby("H").y.apply(lambda s: s.isna().sum())})
    print("Horas positivas de zona por H:\n" + comp.to_string(), flush=True)
    o = oof_m1(z)
    o3 = pd.read_parquet(CACHE / "oof_b1.parquet")
    ev = pd.read_parquet(V3 / "B" / "fase_b1_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    filas = []
    serie = {"v3 (B1)": o3[o3.H == 3].set_index("hora").B1_estado_5d}
    for sem in (0, 1, 2):
        serie[f"M1 semilla {sem}"] = o[o.H == 3].set_index("hora")[f"M1_s{sem}"]
    # (a) 13 positivos originales
    for k, s in serie.items():
        ev["x"] = [score_model_safe(s, r) for r in ev.itertuples()]
        r, _, res = evaluar_loso(ev, ciegos, "x")
        filas.append({"evaluacion": "(a) 13 positivos originales, por evento", **fila(k, r, ciegos, res)})
    # (b1) todos los positivos CON hora de la zona, por evento
    hu = huaicos_v2()
    ini, fin = rangos(d[d.con_hora])
    hz = pd.concat([hu, pd.DataFrame({"id": d[d.con_hora].id, "fecha": d[d.con_hora].fecha, "quebrada_id": "zona:" + d[d.con_hora].nombre, "ini": ini, "fin": fin,
                                      "conf_temporal": ""})], ignore_index=True)
    desc = (dias_desconocidos() - set(pd.to_datetime(d.fecha))) | set(pd.to_datetime(d.fecha[~d.con_hora]))
    eb, cb = etiquetar(eventos_lluvia(lluvia_zona()), hu=hz, desconocidos=desc)
    eb = eb[~eb.desconocido].reset_index(drop=True)
    for k, s in serie.items():
        eb["x"] = [score_model_safe(s, r) for r in eb.itertuples()]
        r, _, res = evaluar_loso(eb, cb, "x")
        filas.append({"evaluacion": "(b1) todos los positivos con hora de la zona, por evento", **fila(k, r, cb, res)})
    # (b2) todos los positivos de la zona, por día local (mismo día)
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    q = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    dias_pos = set(pd.to_datetime(c.fecha[c.en_piloto.eq("True") & q.ne("")])) | set(pd.to_datetime(d.fecha))
    dias_desc = set(pd.to_datetime(dias_evento_fuera_del_piloto())) - dias_pos
    for k, s in serie.items():
        filas.append({"evaluacion": "(b2) todos los positivos de la zona, por día", "metodo": k, **eval_dia(s, dias_pos, dias_desc, None)})
    r = pd.DataFrame(filas)
    r.to_csv(AQUI / "m1_resultados.csv", index=False)
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()

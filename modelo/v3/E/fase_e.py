"""Fase E: modelo DIARIO multizona (celda IMERG 0.1° x día), entrenado con donantes (Fase C) + temporadas de entrenamiento de Chosica; validado SOLO en
Chosica, dejando una temporada fuera (LOSO). Mismo producto en todas las zonas: IMERG Early DIARIO (GPM_3IMERGDE, día UTC).

Fijado ANTES de correr:
  Etiquetas: Chosica = huaicos del catálogo en las 17 quebradas (con o sin hora), asignados a la celda dominante de la quebrada; fecha = día UTC del fin del
    rango v2 si hay hora, si no la fecha local. Días desconocidos (huaico sin quebrada / solo en vecinos o excluidas, regla 9.2) -> fuera.
    Donantes = eventos del catálogo multizona en su celda y fecha; negativos = días dic-abr sin evento, solo dentro del periodo cubierto por las fuentes
    con eventos en esa celda (INDECI 2003-2025, GLC 2007-2016, INGEMMET 2003-2025). y = 0 es "sin noticia" (PU).
  Variables (SOLO IMERG diario): lluvia del día (p0), de los 3 días previos (p1, p2, p3) y su suma (s3). Variante RELATIVA (principal): divididas por el
    percentil 99 diario de la celda en 2001-2014 (años anteriores a toda temporada de prueba). Variante CRUDA (mm). Modelo del MISMO día: usa la lluvia del día.
  Modelo: XGBoost restringido (PARAMS_XGB + CHICO, monotonía +1 en todo), scale_pos_weight = sqrt(neg/pos).
  Variantes: solo_chosica (sin donantes); donantes (corte principal Mahalanobis <= 3 y MESS >= -25); donantes ponderados (peso 1/(1+Mahalanobis));
    sensibilidad de corte (M <= 2 y MESS >= 0; M <= 4; todos). En cada pliegue se quitan las filas de donantes de la MISMA temporada que la de prueba.
  Chosica zona-día: puntaje = máximo de las 5 celdas; y = 1 si hubo huaico ese día en alguna quebrada. Umbral = máximo TSS en las otras temporadas.
  Referencias a nivel día (mismas filas): ISAAC (I = 1.57 D^-0.047 sobre la lluvia horaria IMERG del día local), A2 + estado (B1, máximo horario del día),
    modelo actual por quebrada (máximo del día), I-D calibrado diario. IC 90 %: bootstrap de tormentas (días positivos a <= 2 días = una tormenta).
Salidas: modelo/v3/E/fase_e_resumen.csv, fase_e_dias.parquet
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
V3 = AQUI.parent
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3 / "A"))
from comun_v3 import CACHE, MODELO, RAIZ, dias_desconocidos, huaicos_v2, lluvia_zona, mejor_umbral, tss  # noqa: E402
from fase_a import ISAAC_A, ISAAC_B  # noqa: E402

sys.path.insert(0, str(MODELO))
from arboles import PARAMS_XGB  # noqa: E402
from restringido import CHICO  # noqa: E402

RAW = V3 / "datos" / "raw" / "imerg_diario"
CEL_Q = [(-11.95, -76.85), (-11.95, -76.75), (-11.95, -76.65), (-11.85, -76.75), (-11.85, -76.65)]
COBERTURA = {"INDECI SINPAD": (2003, 2025), "NASA GLC (COOLR)": (2007, 2016), "INGEMMET PERU_ALERTA": (2003, 2025)}
FEAT = ["p0", "p1", "p2", "p3", "s3"]
CORTES = {"principal (M<=3, MESS>=-25)": (3, -25), "estricto (M<=2, MESS>=0)": (2, 0), "amplio (M<=4)": (4, -np.inf), "todos": (np.inf, -np.inf)}


def temporada(d):
    d = pd.DatetimeIndex(d)
    a = np.where(d.month >= 6, d.year, d.year - 1)
    return np.array([f"{x}-{str(x + 1)[2:]}" for x in a])


def cubo(celdas):
    ruta = CACHE / "imerg_diario_celdas.parquet"
    if ruta.exists():
        S = pd.read_parquet(ruta)
        if all(f"{a}_{b}" in S.columns for a, b in celdas):
            return S
    g = np.load(RAW / "grilla.npz")
    ii = {round(float(v), 2): i for i, v in enumerate(g["lat"])}
    jj = {round(float(v), 2): j for j, v in enumerate(g["lon"])}
    idx = [(ii[a], jj[b]) for a, b in celdas]
    filas = {}
    for f in sorted(RAW.glob("_cache/*/*.npy")):
        x = np.load(f)
        filas[pd.Timestamp(f.stem)] = [x[i, j] for i, j in idx]
    S = pd.DataFrame.from_dict(filas, orient="index").sort_index()
    S.columns = [f"{a}_{b}" for a, b in celdas]
    S = S.asfreq("D")
    S.to_parquet(ruta)
    return S


def features(S, p99):
    out = []
    for c in S.columns:
        x = S[c]
        d = pd.DataFrame({"p0": x, "p1": x.shift(1), "p2": x.shift(2), "p3": x.shift(3)})
        d["s3"] = d.p1 + d.p2 + d.p3
        r = d / p99[c]
        r.columns = [f + "_rel" for f in FEAT]
        out.append(pd.concat([d, r], axis=1).assign(celda=c, fecha=d.index))
    return pd.concat(out, ignore_index=True)


def etiquetas_chosica():
    """Por celda y día (UTC) de Chosica: y, y días desconocidos."""
    pes = pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
    dom = pes.loc[pes.groupby("quebrada_id").peso.idxmax()].set_index("quebrada_id")
    dom = {q: f"{r.lat_centro}_{r.lon_centro}" for q, r in dom.iterrows()}
    hu = huaicos_v2()
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    sin_hora = c[c.en_piloto.eq("True") & c.quebrada_id.ne("") & ~c.id.isin(hu.id)]
    pos = [(dom[r.quebrada_id], (r.fin + pd.Timedelta(hours=5)).normalize()) for r in hu.itertuples()]
    pos += [(dom[r.quebrada_id], pd.Timestamp(r.fecha)) for r in sin_hora.itertuples()]
    return set(pos), dias_desconocidos()


def main():
    pd.set_option("display.width", 240)
    f = pd.read_csv(V3 / "C" / "ficha_celdas.csv")
    cat = pd.read_csv(V3 / "C" / "catalogo_con_ficha.csv", parse_dates=["fecha"])
    p99 = f.set_index(f.clat.round(2).astype(str) + "_" + f.clon.round(2).astype(str)).p99_2001_2014
    don = f[~f.es_chosica]
    celdas = [(a, b) for a, b in CEL_Q] + list(zip(don.clat.round(2), don.clon.round(2)))
    S = cubo(celdas)
    S = S.loc["2002-11-01":]
    F = features(S, p99)
    F["temporada"] = temporada(F.fecha)
    F = F[F.fecha.dt.month.isin([12, 1, 2, 3, 4])]
    # --- Chosica
    pos_q, desc = etiquetas_chosica()
    cq = [f"{a}_{b}" for a, b in CEL_Q]
    ch = F[F.celda.isin(cq) & (F.fecha >= "2015-01-01") & (F.fecha <= "2026-04-30")].copy()
    ch["y"] = [int((c, d) in pos_q) for c, d in zip(ch.celda, ch.fecha)]
    ch = ch[~ch.fecha.isin(desc) | (ch.y == 1)]
    ch["donante"], ch["peso_sim"], ch["M"], ch["MESS"] = False, 1.0, 0.0, 100.0
    # --- donantes
    cat["celda"] = cat.clat.round(2).astype(str) + "_" + cat.clon.round(2).astype(str)
    cat = cat[cat.celda.isin(set(F.celda) - set(cq))]
    ev = set(zip(cat.celda, cat.fecha.dt.normalize()))
    cob = cat.groupby("celda").fuente.agg(lambda s: (min(COBERTURA[x][0] for x in set(s)), max(COBERTURA[x][1] for x in set(s))))
    dn = F[F.celda.isin(cob.index)].copy()
    ini = dn.celda.map(lambda c: cob[c][0])
    fin = dn.celda.map(lambda c: cob[c][1])
    dn = dn[(dn.fecha.dt.year >= ini) & (dn.fecha.dt.year <= fin)]
    dn["y"] = [int((c, d) in ev) for c, d in zip(dn.celda, dn.fecha)]
    fi = f.assign(celda=f.clat.round(2).astype(str) + "_" + f.clon.round(2).astype(str)).set_index("celda")
    dn["M"], dn["MESS"] = dn.celda.map(fi.mahalanobis), dn.celda.map(fi.mess)
    dn["donante"], dn["peso_sim"] = True, 1 / (1 + dn.M)
    T = pd.concat([ch, dn], ignore_index=True)
    print(f"Chosica: {len(ch):,} celda-días ({int(ch.y.sum())} positivos); donantes (todos): {len(dn):,} celda-días ({int(dn.y.sum())} positivos) en {dn.celda.nunique()} celdas", flush=True)

    temps = sorted(ch.temporada.unique())
    variantes = {}
    for corte, (m, s) in CORTES.items():
        variantes[f"donantes {corte}, relativa"] = (dict(M=m, MESS=s), True, False)
    variantes["donantes principal, cruda"] = (dict(M=3, MESS=-25), False, False)
    variantes["donantes principal ponderados, relativa"] = (dict(M=3, MESS=-25), True, True)
    variantes["solo Chosica, relativa"] = (None, True, False)
    variantes["solo Chosica, cruda"] = (None, False, False)
    Z = ch.groupby(["fecha", "temporada"]).y.max().reset_index()
    for nombre, (cut, rel, pond) in variantes.items():
        cols = [x + "_rel" for x in FEAT] if rel else FEAT
        base_ = T[~T.donante] if cut is None else T[~T.donante | ((T.M <= cut["M"]) & (T.MESS >= cut["MESS"]))]
        sc = pd.Series(np.nan, index=ch.index)
        for t in temps:
            tr = base_[(base_.temporada != t)]
            y = tr.y.to_numpy()
            spw = float(np.sqrt((y == 0).sum() / max((y == 1).sum(), 1)))
            mdl = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=tuple([1] * len(cols)), random_state=0)
            mdl.fit(tr[cols], y, sample_weight=tr.peso_sim.to_numpy() if pond else None)
            te = ch.temporada == t
            sc[te] = mdl.predict_proba(ch.loc[te, cols])[:, 1]
        Z[nombre] = ch.assign(s=sc).groupby("fecha").s.max().reindex(Z.fecha).to_numpy()
        n_don = int((base_.donante & (base_.y == 1)).sum())
        print(f"  {nombre}: donantes positivos {n_don}", flush=True)
    # --- referencias a nivel día (día UTC para alinear con IMERG diario: horas locales 19:00 del día anterior a 18:59)
    zh = lluvia_zona()
    dia_utc = (zh.index + pd.Timedelta(hours=5)).normalize()

    def isaac(x):
        x = np.nan_to_num(x.to_numpy())
        return max((pd.Series(x).rolling(D).sum().max() / D) / D ** ISAAC_B for D in range(1, len(x) + 1)) if len(x) else 0.0

    Z["ISAAC_dia"] = zh.groupby(dia_utc).apply(isaac).reindex(Z.fecha).to_numpy()
    o = pd.read_parquet(CACHE / "oof_b1.parquet")
    o = o[o.H == 3]
    Z["A2_estado_B1"] = o.groupby((o.hora + pd.Timedelta(hours=5)).dt.normalize()).B1_estado_5d.max().reindex(Z.fecha).to_numpy()
    a = pd.read_parquet(MODELO / "etiquetas_v2" / "oof_actual_v2.parquet")
    a = a[a.H == 3]
    Z["actual"] = a.groupby((a.hora + pd.Timedelta(hours=5)).dt.normalize()).p.max().reindex(Z.fecha).to_numpy()
    Z.to_parquet(AQUI / "fase_e_dias.parquet", index=False)
    # --- evaluación por día, LOSO
    fechas_pos = sorted(Z.fecha[Z.y == 1])
    g = (pd.Series(fechas_pos).diff() > pd.Timedelta(days=2)).cumsum()
    torm = dict(zip(fechas_pos, g))
    rng = np.random.default_rng(0)
    filas = []
    metodos = [c for c in Z.columns if c not in ("fecha", "temporada", "y")]
    for mtd in metodos:
        al = np.zeros(len(Z), bool)
        fijo = ISAAC_A if mtd == "ISAAC_dia" else None
        for t in temps:
            tr, te = (Z.temporada != t).to_numpy(), (Z.temporada == t).to_numpy()
            s = np.nan_to_num(Z[mtd].to_numpy(float), nan=-np.inf)
            tau = fijo if fijo is not None else mejor_umbral(s[tr], Z.y.to_numpy()[tr])
            al[te] = s[te] >= tau
        t_, pod, pofd, tp, fn, fp, tn = tss(Z.y, al)
        # bootstrap de tormentas (positivos) y días negativos por temporada
        P = Z.assign(a=al)
        pos = P[P.y == 1].assign(tor=lambda d: d.fecha.map(torm))
        tors = pos.tor.unique()
        negs = [x.a.to_numpy() for _, x in P[P.y == 0].groupby("temporada")]
        bs = []
        for _ in range(1000):
            sel = pd.concat([pos[pos.tor == k] for k in rng.choice(tors, len(tors))])
            fa = sum(rng.choice(x, len(x)).sum() for x in negs) / sum(len(x) for x in negs)
            bs.append(sel.a.mean() - fa)
        alr = P[P.a]
        filas.append(dict(metodo=mtd, TSS=round(t_, 2), TSS_ic90=(round(float(np.quantile(bs, .05)), 2), round(float(np.quantile(bs, .95)), 2)), POD=round(pod, 2),
                          POFD=round(pofd, 3), aciertos=tp, fallos=fn, falsas=fp, pct_alertas_2024_25=round(100 * (alr.temporada == "2024-25").mean()) if len(alr) else np.nan))
    r = pd.DataFrame(filas)
    r.to_csv(AQUI / "fase_e_resumen.csv", index=False)
    print(f"\nChosica zona-día: {len(Z):,} días, {int(Z.y.sum())} con huaico ({len(set(torm.values()))} tormentas)")
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()

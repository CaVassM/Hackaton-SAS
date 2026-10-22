"""Re-corrida con etiquetas v2 (horas vagas B como rango; catalogo_huaicos_chosica/etiquetas_v2.py) frente a v1, con el MISMO código para ambas.

Modelos (hiperparámetros sin cambios):
  - actual   : XGBoost restringido por quebrada (V1 + D, AMBAS, semilla 0), LOSO en las 12 temporadas (= oof.oof_todas).
  - dos piezas: pieza 1 de R1 (V0, zona, 3 semillas, LOSTO y LOSO) x P2 "mezcla" (P2 no cambia: usa fechas y quebradas, no horas).
Umbrales (N = 100 por quebrada): FIJO (12 temporadas), ENTRENAMIENTO (cuantil de los puntajes del modelo en sus filas/horas de entrenamiento)
y DENTRO de la temporada (secundario). Azar con el mismo reparto de alertas por temporada (esperanza hipergeométrica).
Ceguera: bloques de H = 6 con IMERG < 0.1 mm en las 6 h hasta la última hora del bloque (como modelo/diagnostico_eventos.py, sin retraso).
Uso: python modelo/etiquetas_v2/correr.py     (reanuda: guarda parquets intermedios en esta carpeta; no van a git)
Salidas: v1_vs_v2.csv, v1_vs_v2_detalle.csv, alertas_por_temporada.csv, ceguera.csv
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
MODELO = AQUI.parent
sys.path.insert(0, str(MODELO / "mejoras" / "R3"))
sys.path.insert(0, str(MODELO / "dos_piezas"))
sys.path.insert(0, str(MODELO))
import base  # noqa: E402
import tabla3  # noqa: E402
from arboles import PARAMS_XGB  # noqa: E402
from comun import RAIZ, cargar_lluvia_horaria  # noqa: E402
from escala import oof as oof_zona  # noqa: E402
from evaluar_r3 import alertas, contar  # noqa: E402
from restringido import CHICO, COLS, MONO  # noqa: E402

CAT = RAIZ / "catalogo_huaicos_chosica"
VERSIONES = {"v1": "etiquetas_horarias_H{H}.parquet", "v2": "etiquetas_horarias_v2_H{H}.parquet"}
HS = (3, 6, 12, 24)
SEMILLAS = (0, 1, 2)
N = 100


def usar_version(v):
    f = lambda H: pd.read_parquet(CAT / VERSIONES[v].format(H=H))  # noqa: E731
    tabla3.cargar_etiquetas = f
    base.cargar_etiquetas = f


def tabla(v):
    ruta = AQUI / f"tabla3_{v}.parquet"
    if not ruta.exists():
        usar_version(v)
        t, _ = tabla3.construir()
        t.to_parquet(ruta, index=False)
    return pd.read_parquet(ruta)


def oof_actual(t, v):
    ruta, ru = AQUI / f"oof_actual_{v}.parquet", AQUI / f"umbrales_actual_{v}.csv"
    if ruta.exists():
        return pd.read_parquet(ruta), pd.read_csv(ru)
    t = t.reset_index(drop=True)
    usar = COLS + ["H"]
    mono = tuple(1 if c == "H" else MONO.get(c, 0) for c in usar)
    y, temp, H = t.y.to_numpy(), t.temporada.to_numpy(), t.H.to_numpy()
    p, um = np.full(len(t), np.nan), []
    for s in sorted(t.temporada.unique()):
        te = temp == s
        spw = float(np.sqrt((y[~te] == 0).sum() / (y[~te] == 1).sum()))
        m = xgb.XGBClassifier(**{**PARAMS_XGB, **CHICO}, scale_pos_weight=spw, monotone_constraints=mono, random_state=0).fit(t.loc[~te, usar], y[~te])
        p[te] = m.predict_proba(t.loc[te, usar])[:, 1]
        ptr = m.predict_proba(t.loc[~te, usar])[:, 1]
        for h in HS:
            um.append(dict(pliegue=s, H=h, tau=float(np.quantile(ptr[H[~te] == h], 1 - 1 / N))))
        print(f"  actual {v} {s}", flush=True)
    o = t[["hora", "quebrada_id", "H", "y", "temporada"]].assign(p=p)
    o.to_parquet(ruta, index=False)
    pd.DataFrame(um).to_csv(ru, index=False)
    return o, pd.DataFrame(um)


def oof_dos_piezas(v):
    ruta, ru = AQUI / f"oof_zona_{v}.parquet", AQUI / f"umbrales_zona_{v}.csv"
    if ruta.exists():
        return pd.read_parquet(ruta), pd.read_csv(ru)
    usar_version(v)
    z = base.etiquetas_zona().merge(base._features_zona(), on="hora", how="left")
    z["temporada"] = base.temporada_de(z.hora)
    z = z.sort_values(["H", "hora"]).reset_index(drop=True)
    z["pliegue_losto"] = base.pliegue_losto(z.hora, z.temporada, base.tormentas())
    P2 = pd.read_csv(base.SALIDA / "p2_por_pliegue.csv")
    out, ums = z[["hora", "H", "y", "temporada", "pliegue_losto"]].copy(), []
    for esq, grupo in (("losto", z.pliegue_losto.to_numpy()), ("loso", z.temporada.to_numpy())):
        P, u = oof_zona(z, base.FEATURES_ZONA, grupo, esq, None, P2)
        for s in SEMILLAS:
            out[f"p_xgb{s}_{esq}"] = P[s]
        ums.append(u[u.N == N])
        print(f"  dos piezas {v} {esq} listo", flush=True)
    out.to_parquet(ruta, index=False)
    pd.concat(ums).to_csv(ru, index=False)
    return out, pd.concat(ums)


def evaluar(v, t, oa, ua, oz, uz):
    P2 = pd.read_csv(base.SALIDA / "p2_por_pliegue.csv")
    filas, por_t = [], []
    q0 = t[["hora", "quebrada_id", "H", "y", "temporada"]]
    puntajes = [("actual", "temporada", 0, oa.rename(columns={"p": "r"}), ua.rename(columns={"tau": "tau_r"}))]
    for esq, clave in (("losto", "pliegue_losto"), ("loso", "temporada")):
        p2 = P2[P2.esquema == esq].rename(columns={"pliegue": clave})[[clave, "quebrada_id", "mezcla"]]
        for s in SEMILLAS:
            q = q0.merge(oz[["hora", "H", "pliegue_losto", f"p_xgb{s}_{esq}"]], on=["hora", "H"]).merge(p2, on=[clave, "quebrada_id"])
            q["r"] = q[f"p_xgb{s}_{esq}"] * q.mezcla
            u = uz[(uz.esquema == esq) & (uz.semilla == s)].rename(columns={"tau_riesgo": "tau_r"})
            puntajes.append((f"dos_piezas_{esq}", clave, s, q, u))
    for nombre, clave, s, q, u in puntajes:
        assert len(q) == len(q0), nombre
        for H in HS:
            e = q[q.H == H].reset_index(drop=True)
            b = tabla3.bloques(e)
            gb = np.full(len(e), np.nan)
            gb[b.index.to_numpy()] = b.bloque.to_numpy()
            tau = u[u.H == H].set_index("pliegue").tau_r.to_dict()
            for modo in ("fijo", "entrenamiento", "temporada"):
                ee = e if modo != "temporada" else e[e.temporada.isin(e.temporada[e.y == 1].unique())]
                a = alertas(ee.r.to_numpy(), ee.temporada.to_numpy(), ee[clave].to_numpy(), tau, modo)
                det, tot, az, _, _ = contar(gb[ee.index.to_numpy()], a, ee.temporada.to_numpy())
                filas.append(dict(etiquetas=v, modelo=nombre, semilla=s, H=H, umbral=modo, detectados=det, bloques=tot, azar=az,
                                  alertas_vs_1_100=round(a.sum() / (len(ee) / N), 2)))
                if H == 6 and s == 0 and modo != "temporada":
                    for temp, k in pd.Series(a).groupby(ee.temporada.to_numpy()).sum().items():
                        por_t.append(dict(etiquetas=v, modelo=nombre, umbral=modo, temporada=temp, filas_alerta_H6=int(k)))
    return pd.DataFrame(filas), pd.DataFrame(por_t)


def ceguera(t, v):
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm")
    b = tabla3.bloques(t[t.H == 6])
    filas = []
    for _, g in b.groupby("bloque"):
        q, tl = g.quebrada_id.iloc[0], g.hora.max()
        filas.append(dict(etiquetas=v, quebrada=q, ultima_hora=tl, mm_6h=float(R[q].loc[tl - pd.Timedelta(hours=5): tl].sum())))
    return pd.DataFrame(filas)


def main():
    pd.set_option("display.width", 250)
    res, pt, cg = [], [], []
    for v in VERSIONES:
        t0 = time.time()
        t = tabla(v)
        if v == "v1":
            ref = pd.read_parquet(tabla3.RUTA)
            assert len(ref) == len(t) and (ref.y.to_numpy() == t.y.to_numpy()).all(), "la tabla v1 no coincide con tabla3_modelo.parquet"
        print(f"{v}: tabla {len(t):,} filas, positivos por H {t.groupby('H').y.sum().to_dict()}", flush=True)
        oa, ua = oof_actual(t, v)
        oz, uz = oof_dos_piezas(v)
        r, p = evaluar(v, t, oa, ua, oz, uz)
        res.append(r), pt.append(p), cg.append(ceguera(t, v))
        print(f"{v} listo en {(time.time() - t0) / 60:.1f} min", flush=True)
    r = pd.concat(res)
    r.to_csv(AQUI / "v1_vs_v2_detalle.csv", index=False)
    pd.concat(pt).to_csv(AQUI / "alertas_por_temporada.csv", index=False)
    c = pd.concat(cg)
    c.to_csv(AQUI / "ceguera.csv", index=False)
    g = r.groupby(["etiquetas", "modelo", "umbral", "semilla"]).agg(det=("detectados", "sum"), bl=("bloques", "sum"), az=("azar", "sum"),
                                                                    vol=("alertas_vs_1_100", "mean")).reset_index()
    s = g.groupby(["modelo", "umbral", "etiquetas"]).agg(detectados=("det", "mean"), bloques=("bl", "first"), azar=("az", "mean"), volumen=("vol", "mean")).reset_index()
    s["pct"] = (100 * s.detectados / s.bloques).round(1)
    s["veces_azar"] = (s.detectados / s.azar).round(2)
    s = s.round(1)
    s.to_csv(AQUI / "v1_vs_v2.csv", index=False)
    print("\nRESUMEN (N=100, bloques sumados en los 4 H; dos piezas = media de 3 semillas)\n" + s.to_string(index=False))
    print("\nPor H (semilla 0)\n" + r[r.semilla == 0].pivot_table(index=["modelo", "umbral", "etiquetas"], columns="H", values="detectados").to_string())
    print("\nCEGUERA (H=6): bloques con IMERG < 0.1 mm en las 6 h hasta el bloque")
    print(c.groupby("etiquetas").agg(bloques=("mm_6h", "size"), ciegos=("mm_6h", lambda x: int((x < 0.1).sum())), mediana_mm=("mm_6h", "median")).to_string())


if __name__ == "__main__":
    main()

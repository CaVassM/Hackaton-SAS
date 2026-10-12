"""Pieza 2: si hay tormenta, ¿qué tan propensa es cada quebrada? Se calcula SOLO con las tormentas de ENTRENAMIENTO de cada pliegue.

Fijado ANTES de correr:
  - Filas = (tormenta de entrenamiento, quebrada); y = 1 si la quebrada se activó en esa tormenta (base.activaciones).
  - p_terreno: regresión logística L2 con log10(área) y pendiente media, estandarizadas, C = 1.0 (sin class_weight: queremos la probabilidad por tormenta).
  - P2 = (n_activaciones + K * p_terreno) / (n_tormentas + K), K = 4 (suavizado bayesiano: con pocas tormentas manda el terreno).
  - Variantes que se reportan (todas, ninguna se elige mirando la prueba): historia (n_act/n), terreno, mezcla (la PRINCIPAL),
    y el experimento con img_media (INGEMMET nacional) en p_terreno: terreno_img y mezcla_img (3 variables).
  - Evaluación (pieza 2 sola): en cada tormenta de prueba, % de quebradas activadas dentro del top 5 (empates repartidos) y AUC del ranking.
    Azar: 5/17 = 29.4 % y AUC 0.5.
Salidas: modelo/dos_piezas/salida/p2_por_pliegue.csv, pieza2_por_tormenta.csv, pieza2_resumen.csv
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from base import SALIDA, activaciones, p2_tabla, tormentas

K = 4
C_TERRENO = 1.0
TOP = 5
VARS = {"": ["log10_area_km2", "pendiente_media"], "_img": ["log10_area_km2", "pendiente_media", "img_media"]}
VARIANTES = ["historia", "terreno", "mezcla", "terreno_img", "mezcla_img"]
PRINCIPAL = "mezcla"


def matriz_activacion(torm):
    a = activaciones()
    q = p2_tabla().index
    A = pd.DataFrame(0, index=torm.tormenta, columns=q)
    for r in torm.itertuples():
        A.loc[r.tormenta, r.activadas.split(",")] = 1
    assert int(A.to_numpy().sum()) == int(sum(torm.n_activadas)) and set(a.quebrada_id) <= set(q)
    return A


def p2(A, entrenar):
    """P2 por quebrada (todas las variantes) usando solo las tormentas `entrenar`."""
    T = p2_tabla()
    S = A.loc[list(entrenar)]
    n, n_act = len(S), S.sum(axis=0)
    out = pd.DataFrame({"n_tormentas": n, "n_activaciones": n_act, "historia": n_act / n}, index=T.index)
    for suf, cols in VARS.items():
        X = np.tile(T[cols].to_numpy(), (n, 1))          # filas (tormenta, quebrada), en el orden de S
        y = S.to_numpy().ravel()
        sc = StandardScaler().fit(X)
        lr = LogisticRegression(C=C_TERRENO, max_iter=2000).fit(sc.transform(X), y)
        pt = lr.predict_proba(sc.transform(T[cols].to_numpy()))[:, 1]
        out[f"terreno{suf}"] = pt
        out[f"mezcla{suf}"] = (n_act + K * pt) / (n + K)
    return out


def tabla_p2(torm, A):
    """P2 para cada pliegue de los dos esquemas. Pliegues = los de base.pliegue_losto (tormentas y 'S:<temporada>') y las temporadas (LOSO)."""
    filas = []
    temporadas = [f"{a}-{str(a + 1)[2:]}" for a in range(2014, 2026)]
    for g in list(torm.tormenta) + ["S:" + s for s in temporadas if s not in set(torm.temporada)]:
        filas.append(p2(A, [x for x in torm.tormenta if x != g]).assign(esquema="losto", pliegue=g))
    for s in temporadas:
        filas.append(p2(A, torm.loc[torm.temporada != s, "tormenta"]).assign(esquema="loso", pliegue=s))
    return pd.concat(filas).reset_index()


def top_k_esperado(score, act, k=TOP):
    """Nº esperado de activadas dentro del top k, repartiendo los empates al azar."""
    s = pd.Series(score)
    hits, quedan = 0.0, k
    for v in sorted(s.unique(), reverse=True):
        grupo = (s == v).to_numpy()
        tomar = min(quedan, grupo.sum())
        hits += tomar / grupo.sum() * act[grupo].sum()
        quedan -= tomar
        if quedan == 0:
            break
    return hits


def evaluar(torm, A, P):
    filas = []
    for esquema in ("losto", "loso"):
        for r in torm.itertuples():
            pl = r.tormenta if esquema == "losto" else r.temporada
            p = P[(P.esquema == esquema) & (P.pliegue == pl)].set_index("quebrada_id").loc[A.columns]
            act = A.loc[r.tormenta].to_numpy()
            for v in VARIANTES:
                auc = roc_auc_score(act, p[v]) if 0 < act.sum() < len(act) else np.nan
                filas.append(dict(esquema=esquema, tormenta=r.tormenta, temporada=r.temporada, n_activadas=int(act.sum()), variante=v,
                                  en_top5=top_k_esperado(p[v].to_numpy(), act), auc=auc, tormentas_entrenamiento=int(p.n_tormentas.iloc[0])))
    d = pd.DataFrame(filas)
    res = d.groupby(["esquema", "variante"]).agg(tormentas=("tormenta", "size"), activaciones=("n_activadas", "sum"), en_top5=("en_top5", "sum"),
                                                 auc_media=("auc", "mean"), auc_mediana=("auc", "median"), tormentas_con_auc=("auc", "count")).reset_index()
    res["pct_en_top5"] = (100 * res.en_top5 / res.activaciones).round(1)
    res["azar_pct_top5"] = round(100 * TOP / A.shape[1], 1)
    return d, res


def main():
    pd.set_option("display.width", 220)
    torm = tormentas()
    A = matriz_activacion(torm)
    P = tabla_p2(torm, A)
    P.to_csv(SALIDA / "p2_por_pliegue.csv", index=False)
    d, res = evaluar(torm, A, P)
    d.to_csv(SALIDA / "pieza2_por_tormenta.csv", index=False)
    res.to_csv(SALIDA / "pieza2_resumen.csv", index=False)
    print("PIEZA 2 SOLA (ranking de quebradas en cada tormenta de prueba; azar: 29.4 % en top 5, AUC 0.5)")
    print(res[["esquema", "variante", "tormentas", "activaciones", "pct_en_top5", "azar_pct_top5", "auc_media", "auc_mediana", "tormentas_con_auc"]].round(3).to_string(index=False))
    print("\nPor tormenta (LOSTO, mezcla):")
    print(d[(d.esquema == "losto") & (d.variante == PRINCIPAL)][["tormenta", "temporada", "n_activadas", "en_top5", "auc"]].round(2).to_string(index=False))
    full = p2(A, torm.tormenta)
    print("\nP2 con las 10 tormentas (solo descriptivo):\n" + full[["n_activaciones", "historia", "terreno", "mezcla", "mezcla_img"]].sort_values("mezcla", ascending=False).round(3).to_string())


if __name__ == "__main__":
    main()

"""Verificación independiente del paso 7.2 (integridad del OOF, bloques/detección recalculados con otro código, azar con el mismo reparto de alertas por temporada)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from umbrales import calibrar, monotona_en_H, NIVELES, HORIZONTES
from oof import RUTA_OOF_TODAS
d = pd.read_parquet(RUTA_OOF_TODAS)
t = pd.read_parquet(str(Path(__file__).resolve().parent / "tabla3_modelo.parquet"), columns=["hora","quebrada_id","H","y","temporada"])
# A. integridad
print("A. filas", len(d), len(t), "| p NaN:", int(d.p.isna().sum()), "| p fuera de [0,1]:", int(((d.p<0)|(d.p>1)).sum()))
m = d.merge(t, on=["hora","quebrada_id","H"], suffixes=("","_t"))
print("   claves únicas:", not d.duplicated(["hora","quebrada_id","H"]).any(), "| y igual a tabla3:", bool((m.y==m.y_t).all()), "| temporada igual:", bool((m.temporada==m.temporada_t).all()), "| filas cruzadas:", len(m))
d["pc"] = monotona_en_H(d.assign(pc=calibrar(d)), "pc")
print("   pc NaN:", int(d.pc.isna().sum()), "| orden p vs pc (Spearman) por H:", {h: round(d[d.H==h].p.corr(d[d.H==h].pc, method="spearman"),4) for h in HORIZONTES})
print("   viola p(H3)<=p(H6)<=p(H12)<=p(H24):", int((d.pivot(index=["quebrada_id","hora"],columns="H",values="pc").diff(axis=1).iloc[:,1:]< -1e-12).sum().sum()))
# B. recomputo independiente de bloques (huecos > 1 h) y detección
def bloques_ind(g):
    g = g[g.y==1].sort_values(["quebrada_id","hora"]).copy()
    g["gap"] = g.groupby("quebrada_id").hora.diff().fillna(pd.Timedelta(hours=99)) > pd.Timedelta(hours=1)
    g["b"] = g.gap.cumsum(); return g
res = pd.read_csv(str(Path(__file__).resolve().parent / "salida" / "umbrales_niveles.csv"))
print("B. detección recalculada vs CSV (H, nivel: recalculado / csv; anticipación mediana)")
rng = np.random.default_rng(0)
for h in HORIZONTES:
    g = d[d.H==h]; b = bloques_ind(g)
    for nivel,N in NIVELES.items():
        tau = np.quantile(g.pc, 1-1/N)
        det = (b.assign(a=b.pc>=tau).groupby("b").a.max())
        lead = b[b.pc>=tau].groupby("b").hora.min()
        ult = b.groupby("b").hora.max()
        L = ((ult.loc[lead.index]-lead)/pd.Timedelta(hours=1)+0.5)
        csv = res[(res.H==h)&(res.nivel==nivel)].iloc[0]
        # azar con el MISMO reparto de horas de alerta por temporada (se baraja dentro de la temporada)
        alerta = (g.pc>=tau).to_numpy(); sims=[]
        idx = {s: np.where((g.temporada==s).to_numpy())[0] for s in g.temporada.unique()}
        pos = pd.Series(np.arange(len(g)), index=g.index)
        bb = b.assign(pos=pos.loc[b.index].to_numpy())
        for _ in range(100):
            fl = np.zeros(len(g), bool)
            for s,ix in idx.items():
                k = int(alerta[ix].sum())
                if k: fl[rng.choice(ix, k, replace=False)] = True
            sims.append(bb.assign(a=fl[bb.pos.to_numpy()]).groupby("b").a.max().sum())
        print(f"  H={h:>2} {nivel:8s}: {int(det.sum()):>2}/{len(det)} vs {csv.detectados}/{csv.bloques} | anticip. mediana {L.median():.1f} vs {csv.anticipacion_mediana_h} | AZAR mismo reparto: {np.mean(sims):.1f} ± {np.std(sims):.1f}")
# C. totales de horas de alerta por temporada (H=6)
g = d[d.H==6]; tot = {n:int((g.pc>=np.quantile(g.pc,1-1/N)).sum()) for n,N in NIVELES.items()}
print("C. horas de alerta totales H=6:", tot)
for n,N in NIVELES.items():
    a = (g.pc>=np.quantile(g.pc,1-1/N)).groupby(g.temporada).sum()
    print(f"   {n}: 2024-25 = {a['2024-25']} de {a.sum()} ({100*a['2024-25']/a.sum():.0f} %)")
# D. por temporada normalizado (estilo 7.1) con esta misma tabla
ev = ["2014-15","2016-17","2018-19","2019-20","2022-23","2025-26"]
print("D. detección con corte DENTRO de cada temporada (estilo 7.1), 6 temporadas con eventos:")
for h in HORIZONTES:
    g = d[d.H==h]; b = bloques_ind(g); out=[]
    for N in (20,50,100):
        det=0
        for s in ev:
            tau = np.quantile(g[g.temporada==s].pc, 1-1/N); bs=b[b.temporada==s]
            det += int((bs.assign(a=bs.pc>=tau).groupby("b").a.max()).sum())
        out.append(f"1/{N}: {det}/{b.b.nunique()}")
    print(f"   H={h}:", " | ".join(out))

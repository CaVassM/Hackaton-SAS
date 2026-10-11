"""Informe del paso 5: lee las corridas de modelo/salida/ingenieria/ y resume piso de ruido, aporte de grupos, permutación y selección interna."""
import glob
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from comun import SALIDA
from tabla3 import GRUPOS_NUEVOS

runs = {json.load(open(f))["nombre"]: json.load(open(f)) for f in glob.glob(str(SALIDA / "ingenieria" / "run_*.json"))}
L = lambda n: runs[n]["lift_medio"]
D = lambda n: runs[n]["detectados_N100"]
v1 = [L(f"V1_semilla{s}") for s in range(3)]; v2 = [L(f"V2_semilla{s}") for s in range(3)]
d1 = [D(f"V1_semilla{s}") for s in range(3)]; d2 = [D(f"V2_semilla{s}") for s in range(3)]
ruido = float(np.sqrt((np.var(v1, ddof=1) + np.var(v2, ddof=1)) / 2))
m1, m2 = np.mean(v1), np.mean(v2)
print(f"PISO DE RUIDO (3 semillas): V1 lift {m1:.2f} ± {np.std(v1, ddof=1):.2f} (detectados {d1}) | V2 lift {m2:.2f} ± {np.std(v2, ddof=1):.2f} (detectados {d2}) | ruido típico ±{ruido:.2f}")

filas = []
for g in GRUPOS_NUEVOS:
    k = g[0]
    quitar, agregar = L(f"V2_sin_{k}") - m2, L(f"V1_mas_{k}") - m1
    filas.append(dict(grupo=g, variables=len(GRUPOS_NUEVOS[g]), efecto_al_AGREGAR_a_V1=round(agregar, 2), efecto_al_QUITAR_de_V2=round(-quitar, 2),
                      detectados_V1_mas=D(f"V1_mas_{k}"), detectados_V2_sin=D(f"V2_sin_{k}"),
                      coinciden=("sí: ayuda" if agregar > 0 and quitar < 0 else "sí: perjudica" if agregar < 0 and quitar > 0 else "no coinciden"),
                      supera_2x_ruido=bool(abs(agregar) > 2 * ruido and abs(quitar) > 2 * ruido)))
ab = pd.DataFrame(filas)
ab.to_csv(SALIDA / "ingenieria_aporte_grupos.csv", index=False)
pd.set_option("display.width", 250)
print("\nAPORTE POR GRUPO (cambio en lift medio; positivo = mejora). Un efecto creíble debe ir en el mismo sentido al agregar y al quitar y superar 2× el ruido\n" + ab.to_string(index=False))

perm = pd.DataFrame(runs["V2_semilla0"]["permutacion"])
imp = perm.groupby(["nombre", "es_grupo"]).caida.agg(media="mean", sd="std", folds_positivos=lambda s: int((s > 0).sum())).reset_index().sort_values("media", ascending=False)
imp.to_csv(SALIDA / "ingenieria_permutacion.csv", index=False)
print("\nIMPORTANCIA POR PERMUTACIÓN, GRUPOS (caída del lift al barajar el grupo en la temporada de prueba; 6 temporadas)\n" + imp[imp.es_grupo].round(3).to_string(index=False))
print("\nIMPORTANCIA POR PERMUTACIÓN, TOP 12 VARIABLES\n" + imp[~imp.es_grupo].head(12).round(3).to_string(index=False))
print("\nVARIABLES CON IMPORTANCIA <= 0 (barajarlas no empeora nada):", ", ".join(imp[(~imp.es_grupo) & (imp.media <= 0)].nombre))

sel = pd.Series(runs["V2_seleccion_top10"]["seleccion"]).sort_values(ascending=False)
print(f"\nSELECCIÓN INTERNA top-10: lift {L('V2_seleccion_top10'):.2f}, detectados {D('V2_seleccion_top10')}/204 (V1 {m1:.2f}, V2 {m2:.2f})")
print("veces elegida (de 6 pliegues):", sel.to_dict())

fig, ejes = plt.subplots(1, 2, figsize=(13, 4.8), facecolor="#fcfcfb")
g = imp[imp.es_grupo].sort_values("media")
i = imp[~imp.es_grupo].head(10).sort_values("media")
for ax, d, tit in ((ejes[0], g, "Por grupo"), (ejes[1], i, "Las 10 variables con más efecto")):
    ax.barh(d.nombre, d.media, xerr=d.sd, color="#2a78d6", ecolor="#52514e", error_kw=dict(lw=1))
    ax.axvline(0, color="#52514e", lw=1)
    ax.set_title(tit, loc="left", fontsize=11, color="#0b0b0b"); ax.set_facecolor("#fcfcfb"); ax.grid(axis="x", color="#e4e3df", lw=.8)
    ax.set_xlabel("caída del lift al barajar (media de 6 temporadas ± desviación)", color="#52514e")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
fig.suptitle("Importancia por permutación (XGBoost, 30 variables). Barras que cruzan el cero = efecto no distinguible de cero", x=0.01, ha="left", fontsize=11)
fig.tight_layout(); fig.savefig(SALIDA / "ingenieria_importancia.png", dpi=150)

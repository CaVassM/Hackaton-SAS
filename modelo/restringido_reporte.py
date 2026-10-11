"""Resumen del paso 6 (modelo restringido) a partir de modelo/salida/ingenieria/."""
import glob
import json

import numpy as np
import pandas as pd

from comun import SALIDA

D = SALIDA / "ingenieria"
R = lambda n: json.load(open(D / f"run_{n}.json"))
filas = []
for nombre, pref in (("V1 originales (13)", "V1_semilla"), ("V1 + D sin restricciones", "V1_mas_D_semilla"), ("solo monotonía", "R_MONO_semilla"),
                     ("solo árboles pequeños", "R_CHICO_semilla"), ("AMBAS (modelo restringido)", "R_AMBAS_semilla")):
    rs = [R(f"{pref}{s}") if pref != "V1_mas_D_semilla" or s else R("V1_mas_D") for s in range(3)]
    l = [r["lift_medio"] for r in rs]; d = [r["detectados_N100"] for r in rs]; d50 = [r["detectados_N50"] for r in rs]
    filas.append(dict(modelo=nombre, lift_medio=f"{np.mean(l):.1f} ± {np.std(l, ddof=1):.1f}", detectados_N100=f"{np.mean(d):.0f}/204 ({100 * np.mean(d) / 204:.0f} %)",
                      rango_N100=f"{min(d)}-{max(d)}", detectados_N50=f"{np.mean(d50):.0f}/204"))
pd.set_option("display.width", 220)
print(pd.DataFrame(filas).to_string(index=False))
azar = {3: 0.030, 6: 0.060, 12: 0.117, 24: 0.217}
rs = [R(f"R_AMBAS_semilla{s}") for s in range(3)]
print("\nMODELO RESTRINGIDO (AMBAS), bloques detectados por horizonte con 1 alerta cada 100 h (media de 3 semillas) frente al azar esperado")
for H in ("3", "6", "12", "24"):
    det = np.mean([r["det_por_H"][H][0] for r in rs]); bl = rs[0]["det_por_H"][H][1]
    print(f"  H={H:>2}: {det:4.1f} de {bl}  ({100 * det / bl:4.1f} %)   azar esperado {100 * azar[int(H)]:.0f} %   lift {np.mean([r['lift_por_H'][H] for r in rs]):.1f}")
print("\nLift por temporada (media de 3 semillas):")
for nombre, pref in (("V1", "V1_semilla"), ("AMBAS", "R_AMBAS_semilla")):
    rr = [R(f"{pref}{s}") for s in range(3)]
    print(f"  {nombre:6s}", {k: round(float(np.mean([r['lift_por_temporada'][k] for r in rr])), 1) for k in rr[0]["lift_por_temporada"]})
b = json.load(open(D / "brecha_restringido.json"))
print("\nBRECHA DE SOBREAJUSTE (lift en entrenamiento -> lift en prueba, semilla 0):")
for k, (a, c) in b.items():
    print(f"  {k:25s} {a:8.0f} -> {c:5.1f}")

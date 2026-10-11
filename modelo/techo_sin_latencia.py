"""Diagnóstico (NO es un modelo usable): ¿cuánto mejora el modelo restringido si la lluvia llegara con menos retraso?

IMERG Early llega con ~4 h de latencia (REZAGO = 5: la fila t usa lluvia con etiqueta <= t-5). Aquí se repite TODO igual
(mismas variables V1 + D, mismos parámetros, monotonía + árboles pequeños, LOSO, 3 semillas) cambiando solo el retraso:
  4 h (actual) | 2 h | 1 h | 0 h (la hora t-1 ya está completa en t).
Es un techo optimista para cualquier fuente más rápida (GOES, pluviómetros, nowcasting): usa los MISMOS valores de IMERG, solo antes.
Las variables sin retraso no se pueden usar en producción; esto solo mide cuánto pesa la latencia.
Salida: modelo/salida/techo_sin_latencia.csv (+ caché en modelo/salida/ingenieria/run_TECHO_*.json).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lluvia"))
import features_lluvia as fl  # noqa: E402

import tabla3  # noqa: E402
from comun import RAIZ, SALIDA  # noqa: E402
from ingenieria import DIR, correr  # noqa: E402
from restringido import CHICO, COLS, MONO  # noqa: E402

ESCENARIOS = {4: 5, 2: 3, 1: 2, 0: 1}   # latencia en horas -> REZAGO
ACTUAL = 4


def features_con_rezago(rez):
    ruta = RAIZ / "modelo" / f"techo_features_rez{rez}.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    fl.REZAGO = rez
    R = fl.lluvia_horaria(RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv"))
    Rcel = fl.lluvia_celdas(RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv"))
    f = fl.a_largo(fl.features(R, Rcel), R)
    f.to_parquet(ruta, index=False)
    return f


def main():
    filas = []
    for lat, rez in ESCENARIOS.items():
        tabla3.cargar_features = lambda rez=rez: features_con_rezago(rez)
        t = tabla3.construir()[0].reset_index(drop=True)
        rs = []
        for s in (0, 1, 2):
            nombre = f"R_AMBAS_semilla{s}" if lat == ACTUAL else f"TECHO_lat{lat}h_semilla{s}"
            if lat == ACTUAL and not (DIR / f"run_{nombre}.json").exists():
                nombre = f"TECHO_lat{lat}h_semilla{s}"
            rs.append(json.loads(json.dumps(correr(t, COLS, nombre, s, mono_extra=MONO, params=CHICO))))  # claves siempre como texto
        d = [r["detectados_N100"] for r in rs]
        porH = {H: np.mean([r["det_por_H"][str(H)][0] for r in rs]) for H in (3, 6, 12, 24)}
        filas.append(dict(latencia_h=lat, lift=f"{np.mean([r['lift_medio'] for r in rs]):.1f} ± {np.std([r['lift_medio'] for r in rs], ddof=1):.1f}",
                          detectados_N100=f"{np.mean(d):.0f}/204 ({100 * np.mean(d) / 204:.0f} %)", rango=f"{min(d)}-{max(d)}",
                          **{f"det_H{H}": round(v, 1) for H, v in porH.items()},
                          **{f"lift_{k}": round(float(np.mean([r['lift_por_temporada'][k] for r in rs])), 1) for k in rs[0]["lift_por_temporada"]}))
        print(pd.DataFrame(filas).tail(1).to_string(index=False), flush=True)
    out = pd.DataFrame(filas)
    out.to_csv(SALIDA / "techo_sin_latencia.csv", index=False)
    pd.set_option("display.width", 250)
    print("\n" + out.to_string(index=False))


if __name__ == "__main__":
    main()

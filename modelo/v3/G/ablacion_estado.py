"""Ablación del ESTADO de la pieza 1 (INFORMATIVO: el modelo v3 no cambia). ¿Cuánto pesan icen y hum_suelo_5d, y explican la alerta casi continua de 2017?

Mismo protocolo que fase_f / fase_g: mismas etiquetas v2, XGBoost v3 (PARAMS_XGB + CHICO, monotonía +1 salvo dias_activ), LOSO por temporada
(fase_f.loso), puntaje por evento = máx. p_zona H = 3 antes del huaico (fase_f.puntajes_evento), umbral de máx. TSS con las otras temporadas
(comun_v3.evaluar_loso) y bootstrap por tormenta (fase_b1.fila).
Variantes fijadas antes de correr: control (B1), sin icen, sin hum_suelo_5d, sin las dos.
Por variante: TSS, IC 90 %, POD, POFD; detectados y falsas alarmas en 2016-17; % de horas de marzo 2017 y marzo 2023 con p_zona (H = 3, LOSO)
>= el umbral LOSO de su temporada.
Salida: modelo/v3/G/ablacion_estado.csv      Uso: python ablacion_estado.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent, AQUI.parent / "A", AQUI.parent / "B", AQUI.parent / "F"):
    sys.path.insert(0, str(p))
from comun_v3 import etiquetar, evaluar_loso, eventos_lluvia, lluvia_zona  # noqa: E402
from fase_a import H_EV  # noqa: E402
from fase_b1 import fila  # noqa: E402
import fase_f  # noqa: E402

VARIANTES = {
    "B1 (v3, control)": fase_f.B1,
    "sin icen": [c for c in fase_f.B1 if c != "icen"],
    "sin hum_suelo_5d": [c for c in fase_f.B1 if c != "hum_suelo_5d"],
    "sin icen ni hum_suelo_5d": [c for c in fase_f.B1 if c not in ("icen", "hum_suelo_5d")],
}
MESES = {"2017-03": "2016-17", "2023-03": "2022-23"}


def main():
    pd.set_option("display.width", 250)
    z = fase_f.tabla()
    ev0 = pd.read_parquet(AQUI.parent / "A" / "fase_a_eventos.parquet")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    h3 = (z.H == H_EV).to_numpy()
    filas = []
    for nombre, cols in VARIANTES.items():
        p = fase_f.loso(z, cols)
        ev = ev0.copy()
        ev["s"] = fase_f.puntajes_evento(z, p, ev)
        r, taus, res = evaluar_loso(ev, ciegos, "s")
        f = fila(nombre, r, res, ciegos)
        e16 = r[r.temporada == "2016-17"]
        sh = pd.Series(p[h3], index=z.hora[h3])
        sh = sh[~sh.index.duplicated()]
        out = dict(variante=nombre, variables=len(cols) + 1, TSS=f["TSS"], TSS_ic90=f["TSS_ic90"], POD=f["POD"], POFD=f["POFD"],
                   aciertos=f["aciertos"], fallos=f["fallos"], falsas=f["falsas"],
                   huaicos_2016_17=int(e16.disparador.sum()), detectados_2016_17=int((e16.alerta & (e16.disparador == 1)).sum()),
                   falsas_2016_17=int((e16.alerta & (e16.disparador == 0)).sum()), eventos_2016_17=len(e16))
        for mes, temp in MESES.items():
            m = sh[sh.index.strftime("%Y-%m") == mes]
            out[f"umbral_{temp.replace('-', '_')}"] = round(float(taus[temp]), 5)
            out[f"pct_horas_alerta_{mes.replace('-', '_')}"] = round(100 * float((m >= taus[temp]).mean()), 1)
        filas.append(out)
        print(out, flush=True)
    T = pd.DataFrame(filas)
    T.to_csv(AQUI / "ablacion_estado.csv", index=False)
    print(T.to_string(index=False))
    print("FIN", flush=True)


if __name__ == "__main__":
    main()

"""03 - Validación por EVENTO de lluvia (como la literatura de umbrales) y comparación con la referencia del repo. Requiere 02_entrenar.py.

  - Unidad: evento de lluvia IMERG en la zona (horas con >= 0.1 mm separadas por >= 6 h secas); disparador = hubo huaico durante el evento o hasta 3 h
    después; el puntaje del evento es el máximo puntaje horario (H = 3) ANTES del huaico. 1 602 eventos, 12 disparadores + 1 día ciego (fallo seguro).
  - Umbral de cada temporada = el que maximiza el TSS en las otras 11 (LOSO). TSS = acierto (POD) - falsas alarmas (POFD); 0 = azar.
  - IC 90 % por bootstrap de tormentas (2 000 repeticiones, semilla 0).
Equivale a modelo/v3/comun_v3.py evaluar_loso y bootstrap (repo).
Salida: salidas/metricas_validacion.csv      Uso: python entrega_modelo/scripts/03_validar.py
Resultado esperado: TSS 0.49 (IC 90 % 0.15-0.70), 9 de 13 huaicos, POFD 0.199.
"""
import json

import numpy as np
import pandas as pd

import _lib as L


def main():
    oof = pd.read_parquet(L.TRABAJO / "oof.parquet")
    s3 = oof[oof.H == 3].set_index("hora").p
    ev, ciegos = L.eventos()
    ev["p1"] = [L.puntaje_evento(s3, r) for r in ev.itertuples()]
    r, taus, (t, pod, pofd, tp, fn, fp, tn) = L.evaluar_loso(ev, ciegos, "p1")
    ic = L.bootstrap(r, ciegos)
    met = pd.DataFrame([dict(metodo="B1 (P1 del modelo final), LOSO por evento", TSS=round(t, 2), TSS_ic90=ic["TSS"], POD=round(pod, 2), POFD=round(pofd, 3),
                             aciertos=tp, fallos=fn, falsas=fp, positivos=tp + fn, eventos=len(ev))])
    met.to_csv(L.SALIDAS / "metricas_validacion.csv", index=False)
    print(met.to_string(index=False))

    # comparación con la referencia (modelo final del repo)
    fallas = []
    ref_m = pd.read_csv(L.REFERENCIA / "metricas_validacion.csv").iloc[0]
    for k in ("TSS", "aciertos", "fallos", "falsas"):
        if not np.isclose(float(met.iloc[0][k]), float(ref_m[k])):
            fallas.append(f"métrica {k}: {met.iloc[0][k]} vs referencia {ref_m[k]}")
    if str(ic["TSS"]) != str(ref_m.TSS_ic90).replace(" ", "").replace(",", ", "):
        fallas.append(f"IC 90 % del TSS: {ic['TSS']} vs referencia {ref_m.TSS_ic90}")
    U, Ur = pd.read_csv(L.MODELO / "umbrales.csv"), pd.read_csv(L.REFERENCIA / "umbrales.csv")
    for c in ("rojo", "amarillo", "rojo_oof", "amarillo_oof"):
        if not np.allclose(U[c], Ur[c], rtol=1e-9, atol=0):
            fallas.append(f"umbral {c}: {U[c].round(6).tolist()} vs referencia {Ur[c].round(6).tolist()}")
    p2, p2r = pd.read_csv(L.MODELO / "p2.csv").set_index("quebrada_id").p2, pd.read_csv(L.REFERENCIA / "p2.csv").set_index("quebrada_id").p2
    if not np.allclose(p2.sort_index(), p2r.sort_index(), rtol=1e-9, atol=0):
        fallas.append("P2 distinto de la referencia")
    cal = json.loads((L.MODELO / "calibracion.json").read_text(encoding="utf-8"))["por_H"]
    cal_r = json.loads((L.REFERENCIA / "calibracion.json").read_text(encoding="utf-8"))["por_H"]
    for H in cal_r:
        for k in ("a", "b", "kappa", "tasa_base"):
            if not np.isclose(cal[H][k], cal_r[H][k], rtol=1e-9, atol=0):
                fallas.append(f"calibración H={H} {k}: {cal[H][k]} vs referencia {cal_r[H][k]}")
    E, Er = pd.read_csv(L.MODELO / "calibracion_escala_final.csv"), pd.read_csv(L.REFERENCIA / "calibracion_escala_final.csv")
    if not np.allclose(E[["p_final", "p_loso"]], Er[["p_final", "p_loso"]], rtol=1e-9, atol=0):
        fallas.append("rejilla de escala del modelo final distinta de la referencia")
    print("\nComparación con salidas/referencia/ (modelo final del repo): " + ("IGUAL (métricas, IC, umbrales, P2 y calibración)" if not fallas else "DIFERENCIAS:"))
    for f in fallas:
        print("  - " + f)


if __name__ == "__main__":
    main()

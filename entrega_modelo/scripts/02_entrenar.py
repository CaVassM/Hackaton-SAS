"""02 - Entrenamiento. Requiere salidas/trabajo/tabla_zona.parquet (01_features.py).

  1. Predicciones FUERA DE MUESTRA (LOSO): cada temporada predicha por un XGBoost entrenado con las otras 11 -> salidas/trabajo/oof.parquet
     (sirven para calibrar los umbrales y para validar en 03_validar.py).
  2. P1 final: XGBoost restringido (monotonía +1 en lluvia, humedad, ICEN y H; profundidad 2, 150 árboles; semilla 0) con TODAS las temporadas
     -> salidas/modelo/p1.json
  3. Umbrales por H: rojo = máximo TSS por evento de lluvia (puntajes fuera de muestra); amarillo = POD >= 0.9 o, si es inalcanzable, el máximo POD
     posible; trasladados al modelo final por cuantil de las horas -> salidas/modelo/umbrales.csv
  4. P2 por quebrada con las 10 tormentas: (n_activaciones + 4 p_terreno) / (10 + 4) -> salidas/modelo/p2.csv
  5. Calibración (no cambia P1, P2 ni umbrales): Platt por H sobre las predicciones LOSO, kappa_H y tasa base -> salidas/modelo/calibracion.json;
     rejilla de cuantiles para llevar p_zona del modelo final a la escala LOSO -> salidas/modelo/calibracion_escala_final.csv
Equivale a modelo/v3/B/fase_b1.py (oof), modelo/v3/final/modelo_final.py entrenar y modelo/v3/final/calibracion.py (repo).
Uso: python entrega_modelo/scripts/02_entrenar.py
"""
import json

import numpy as np
import pandas as pd

import _lib as L


def main():
    z = pd.read_parquet(L.TRABAJO / "tabla_zona.parquet")
    oof = z[["hora", "H", "y", "temporada"]].assign(p=L.oof_loso(z))
    oof.to_parquet(L.TRABAJO / "oof.parquet", index=False)
    print("Predicciones fuera de muestra (LOSO, 12 temporadas): listas", flush=True)
    m = L.ajustar(z)
    L.MODELO.mkdir(parents=True, exist_ok=True)
    m.save_model(L.MODELO / "p1.json")
    ev, ciegos = L.eventos()
    u = L.umbrales_oof(oof, ev, ciegos)
    todas = z[z.y.notna()]
    for H in L.HS:
        s_fin = m.predict_proba(todas[todas.H == H][L.VARIABLES])[:, 1]
        u[H]["rojo"] = float(np.quantile(s_fin, u[H]["cuantil_rojo"]))
        u[H]["amarillo"] = float(min(np.quantile(s_fin, u[H]["cuantil_amarillo"]), u[H]["rojo"]))
    U = pd.DataFrame([{"H": H, **v} for H, v in u.items()])
    U.to_csv(L.MODELO / "umbrales.csv", index=False)
    p2 = L.p2()
    p2.rename_axis("quebrada_id").reset_index().to_csv(L.MODELO / "p2.csv", index=False)
    cal = L.calibrar(oof, p2)
    (L.MODELO / "calibracion.json").write_text(json.dumps({"por_H": {int(H): v for H, v in cal.items()}}, indent=1), encoding="utf-8")
    L.escala_final(m, z, oof).to_csv(L.MODELO / "calibracion_escala_final.csv", index=False)
    (L.MODELO / "modelo.json").write_text(json.dumps(dict(variables_en_orden=L.VARIABLES, parametros=L.PARAMS, monotonia=L.MONOTONIA,
                                                           filas_entrenamiento=int(z.y.notna().sum()), semilla=0), indent=1), encoding="utf-8")
    print(U[["H", "rojo", "amarillo", "rojo_TSS", "rojo_POD", "rojo_POFD", "amarillo_POD"]].round(5).to_string(index=False))
    print("P2:", p2.round(3).to_dict())
    print("Calibración:", {H: {k: round(v[k], 4) for k in ("a", "b", "kappa", "tasa_base")} for H, v in cal.items()})


if __name__ == "__main__":
    main()

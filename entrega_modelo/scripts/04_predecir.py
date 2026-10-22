"""04 - Predicción para un periodo, en el formato del dashboard (archivos A, B y D; ver predecir_demo.py).

Modos:
  - por defecto: modelo final (salidas/modelo/: p1.json, umbrales.csv, p2.csv, calibracion.json, calibracion_escala_final.csv; requiere
    02_entrenar.py). Para fechas del histórico es DENTRO de muestra. Su p_zona se lleva a la escala LOSO por cuantil antes de la calibración.
  - --excluir-temporada AAAA-AA: FUERA DE MUESTRA, como predecir_demo.py: P1 entrenado sin esa temporada, umbrales y calibración (Platt, kappa,
    tasa base) ajustados sin ella con los puntajes LOSO, y P2 con las otras tormentas. Requiere salidas/trabajo/oof.parquet (02_entrenar.py).
Uso: python entrega_modelo/scripts/04_predecir.py --mes 2023-03 [--excluir-temporada 2022-23] [--paso 30]
     python entrega_modelo/scripts/04_predecir.py --desde "2023-03-12 00:00" --hasta "2023-03-12 23:00"
Salidas en salidas/predicciones/: probabilidad_huayco_por_quebrada_con_tiempo_<etiqueta>[_30min].csv (A), detalle_zona_<etiqueta>.csv (B) y
  probabilidad_si_hay_evento[_sin_<temporada>].csv (D: P2 = probabilidad de que la quebrada se active si hay un temporal en la zona)
  A: prob_ml_Hh = p_cal(t, H) * kappa_H * P2(q): probabilidad calibrada de que la quebrada se active en (t, t+H] (ver modelo/v3/final/calibracion.py).
  B: p_zona (P1 sin calibrar, el que se compara con los umbrales), p_zona_calibrada y veces_lo_normal (= p_zona_calibrada / tasa base del H).
  detalle_zona: nivel (OFICIAL, el validado) = rojo si p_zona >= umbral_rojo, amarillo si umbral_amarillo <= p_zona < umbral_rojo, si no verde;
                nivel_con_lluvia (variante) = igual, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h (lluvia_6h_mm); si no, amarillo.
"""
import argparse
import json

import pandas as pd
import xgboost as xgb

import _lib as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes")
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    ap.add_argument("--excluir-temporada")
    ap.add_argument("--paso", type=int, choices=(60, 30), default=60)
    a = ap.parse_args()
    if a.mes:
        ini = pd.Timestamp(f"{a.mes}-01")
        horas = pd.date_range(ini, ini + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23), freq="h")
        etiqueta = a.mes.replace("-", "_")
    else:
        horas = pd.date_range(pd.Timestamp(a.desde).floor("h"), pd.Timestamp(a.hasta).floor("h"), freq="h")
        etiqueta = f"{horas[0]:%Y%m%d_%H}_{horas[-1]:%Y%m%d_%H}"
    if a.excluir_temporada:
        s = a.excluir_temporada
        z = pd.read_parquet(L.TRABAJO / "tabla_zona.parquet")
        m = L.ajustar(z[z.temporada != s])
        ev, ciegos = L.eventos()
        u = L.umbrales_oof(pd.read_parquet(L.TRABAJO / "oof.parquet"), ev, ciegos, excluir=s)
        for H in L.HS:
            u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
        p2 = L.p2(lambda torm: torm.loc[torm.temporada != s, "tormenta"])
        cal = L.calibrar(pd.read_parquet(L.TRABAJO / "oof.parquet"), p2, excluir=s)
        etiqueta += f"_sin_{s.replace('-', '_')}"
    else:
        m = xgb.XGBClassifier()
        m.load_model(L.MODELO / "p1.json")
        u = {int(r.H): dict(rojo=r.rojo, amarillo=r.amarillo) for r in pd.read_csv(L.MODELO / "umbrales.csv").itertuples()}
        p2 = pd.read_csv(L.MODELO / "p2.csv").set_index("quebrada_id").p2
        cal = {int(H): v for H, v in json.loads((L.MODELO / "calibracion.json").read_text(encoding="utf-8"))["por_H"].items()}
        esc = pd.read_csv(L.MODELO / "calibracion_escala_final.csv")
    X = L.variables_horarias(horas)
    faltan = [c for c in X.columns if X[c].isna().any()]
    if faltan:
        print(f"AVISO: faltan datos en inputs/ para {faltan} en parte del periodo (el modelo los trata como faltantes).")
    pz = {H: m.predict_proba(X.assign(H=H)[L.VARIABLES])[:, 1] for H in L.HS}
    pc = L.p_calibrada(cal, pz if a.excluir_temporada else L.a_escala_loso(esc, pz))
    zk = L.p_zona_kappa(cal, pc)
    out = L.SALIDAS / "predicciones"
    out.mkdir(parents=True, exist_ok=True)
    rutas = [out / f"probabilidad_huayco_por_quebrada_con_tiempo_{etiqueta}.csv"]
    L.archivo_a(horas, zk, p2).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    if a.paso == 30:
        rutas.append(out / f"probabilidad_huayco_por_quebrada_con_tiempo_{etiqueta}_30min.csv")
        L.archivo_a(horas, zk, p2, 30).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    rutas.append(out / f"detalle_zona_{etiqueta}.csv")
    L.archivo_b(horas, X, pz, u, pc, cal).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    rutas.append(out / ("probabilidad_si_hay_evento" + (f"_sin_{a.excluir_temporada.replace('-', '_')}" if a.excluir_temporada else "") + ".csv"))
    L.archivo_d(p2).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    for r in rutas:
        print(f"  {r.relative_to(L.ENTREGA)}: {sum(1 for _ in open(r, encoding='utf-8-sig')) - 1} filas")


if __name__ == "__main__":
    main()

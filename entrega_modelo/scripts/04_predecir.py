"""04 - Predicción para un periodo, en el formato del dashboard (archivos A y B; ver predecir_demo.py).

Modos:
  - por defecto: modelo final (salidas/modelo/: p1.json, umbrales.csv, p2.csv; requiere 02_entrenar.py). Para fechas del histórico es DENTRO de muestra.
  - --excluir-temporada AAAA-AA: FUERA DE MUESTRA, como predecir_demo.py: P1 entrenado sin esa temporada, umbrales calibrados sin ella (puntajes
    LOSO) y P2 con las otras tormentas. Requiere salidas/trabajo/oof.parquet (02_entrenar.py).
Uso: python entrega_modelo/scripts/04_predecir.py --mes 2023-03 [--excluir-temporada 2022-23] [--paso 30]
     python entrega_modelo/scripts/04_predecir.py --desde "2023-03-12 00:00" --hasta "2023-03-12 23:00"
Salidas en salidas/predicciones/: probabilidad_huayco_por_quebrada_con_tiempo_<etiqueta>[_30min].csv y detalle_zona_<etiqueta>.csv
  prob_ml_Hh = p_zona x P2 es un PUNTAJE de riesgo por quebrada, no una probabilidad calibrada; el nivel de alerta es de la ZONA (detalle_zona).
  detalle_zona: nivel (OFICIAL, el validado) = rojo si p_zona >= umbral_rojo, amarillo si umbral_amarillo <= p_zona < umbral_rojo, si no verde;
                nivel_con_lluvia (variante) = igual, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h (lluvia_6h_mm); si no, amarillo.
"""
import argparse

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
        etiqueta += f"_sin_{s.replace('-', '_')}"
    else:
        m = xgb.XGBClassifier()
        m.load_model(L.MODELO / "p1.json")
        u = {int(r.H): dict(rojo=r.rojo, amarillo=r.amarillo) for r in pd.read_csv(L.MODELO / "umbrales.csv").itertuples()}
        p2 = pd.read_csv(L.MODELO / "p2.csv").set_index("quebrada_id").p2
    X = L.variables_horarias(horas)
    faltan = [c for c in X.columns if X[c].isna().any()]
    if faltan:
        print(f"AVISO: faltan datos en inputs/ para {faltan} en parte del periodo (el modelo los trata como faltantes).")
    pz = {H: m.predict_proba(X.assign(H=H)[L.VARIABLES])[:, 1] for H in L.HS}
    out = L.SALIDAS / "predicciones"
    out.mkdir(parents=True, exist_ok=True)
    rutas = [out / f"probabilidad_huayco_por_quebrada_con_tiempo_{etiqueta}.csv"]
    L.archivo_a(horas, pz, p2).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    if a.paso == 30:
        rutas.append(out / f"probabilidad_huayco_por_quebrada_con_tiempo_{etiqueta}_30min.csv")
        L.archivo_a(horas, pz, p2, 30).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    rutas.append(out / f"detalle_zona_{etiqueta}.csv")
    L.archivo_b(horas, X, pz, u).to_csv(rutas[-1], index=False, encoding="utf-8-sig")
    for r in rutas:
        print(f"  {r.relative_to(L.ENTREGA)}: {sum(1 for _ in open(r, encoding='utf-8-sig')) - 1} filas")


if __name__ == "__main__":
    main()

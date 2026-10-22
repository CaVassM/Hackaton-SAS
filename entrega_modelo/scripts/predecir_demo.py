"""Predicciones de demo FUERA DE MUESTRA para un mes: P1, P2, umbrales y calibración calculados SIN la temporada del mes (como modelo_final.ejemplo()).

Uso (desde la raíz del repo):
  python entrega_modelo/scripts/predecir_demo.py --temporada 2022-23 --mes 2023-03            # paso horario
  python entrega_modelo/scripts/predecir_demo.py --temporada 2022-23 --mes 2023-03 --paso 30  # además la versión cada 30 min (repite el valor de su hora)
Usa del repo: modelo/v3/final/modelo_final.py (tabla_zona, ajustar, umbrales_oof, p2_tabla, variables_horarias), modelo/v3/final/calibracion.py
  (datos, ajustar, con_rango, p_calibrada, p_zona_kappa) y modelo/v3/comun_v3.py (huaicos_v2); el formato de los archivos A, B, D y E sale de _lib.py.
Requiere los cachés de la cadena v3 (modelo/v3/_cache/oof_b1.parquet, modelo/v3/B/fase_b1_eventos.parquet): si faltan, correr antes `python replicar.py`.

Salidas en entrega_modelo/salidas/demo/ (UTF-8 con BOM, coma, punto decimal; Tiempo = d/mm/yyyy HH:MM, hora de Lima, inicio de la hora):
  A probabilidad_huayco_por_quebrada_con_tiempo_<AAAA_MM>[_30min].csv : Tiempo, quebrada_id, quebrada, prob_ml_3h, prob_ml_6h, prob_ml_12h, prob_ml_24h
      prob_ml_Hh = p_cal(t, H) x kappa_H x P2(quebrada), 5 decimales: probabilidad calibrada de que la quebrada se active en (t, t+H]
      (Platt y kappa ajustados SIN la temporada; ver modelo/v3/final/calibracion.py).
  B detalle_zona_<AAAA_MM>.csv : Tiempo, H, p_zona, umbral_rojo, umbral_amarillo, nivel, nivel_con_lluvia, lluvia_6h_mm, p_zona_calibrada, veces_lo_normal
      p_zona = P1 sin calibrar (el que se compara con los umbrales); p_zona_calibrada = p_cal; veces_lo_normal = p_cal / tasa base del H.
      nivel (OFICIAL, el validado): rojo si p_zona >= umbral_rojo (como en la validación); amarillo si umbral_amarillo <= p_zona < umbral_rojo; si no, verde.
      nivel_con_lluvia (variante): igual, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h disponibles (lluvia_6h_mm); si no la hay, amarillo.
      El nivel de alerta es de la ZONA (lo validado), no de cada quebrada.
  C huaicos_registrados_<AAAA_MM>.csv : fecha, hora_inicio, hora_fin, quebrada_id (catálogo, 17 quebradas; horas = rango v2; vacías si no hay hora)
  D probabilidad_si_hay_evento.csv (temporada 2022-23; otras: probabilidad_si_hay_evento_sin_<temporada>.csv):
      quebrada_id, quebrada, P2, prob_min_Hh, prob_max_Hh (H = 3, 6, 12, 24), descripcion
      P2 del pliegue (sin la temporada) = probabilidad de que la quebrada se active si hay un temporal en la zona; prob_min/max_Hh = kappa_min/max_H x P2 =
      rango de la probabilidad de que se active en una ventana de H horas con huaico en la zona.
  E rango_por_quebrada_<AAAA_MM>.csv : Tiempo, quebrada_id, quebrada, H, prob, prob_min, prob_max
      prob = prob_ml_Hh del archivo A; prob_min / prob_max = p_cal x kappa_min_H / kappa_max_H x P2 (kappa de los pliegues que dejan fuera, además de la
      temporada de la demo, una temporada más).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTREGA = AQUI.parent
RAIZ = ENTREGA.parent
SALIDAS = ENTREGA / "salidas" / "demo"
sys.path.insert(0, str(RAIZ / "modelo" / "v3" / "final"))
import modelo_final as mf  # noqa: E402
import calibracion as cb  # noqa: E402
from comun_v3 import huaicos_v2  # noqa: E402  (modelo_final ya puso modelo/v3 en sys.path)
import _lib as L  # noqa: E402  (mismo formato de salida que 04_predecir.py)

def modelo_sin_temporada(temporada):
    """Lo de modelo_final.ejemplo() (P1 sin la temporada, umbrales LOSO sin ella, P2 con sus otras tormentas) + calibración sin la temporada."""
    z = mf.tabla_zona()
    m = mf.ajustar(z[z.temporada != temporada])
    u = mf.umbrales_oof(excluir=temporada)
    for H in mf.HS:
        u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
    p2 = mf.p2_tabla(lambda torm: torm.loc[torm.temporada != temporada, "tormenta"])
    d = cb.datos()
    cal = cb.con_rango(cb.ajustar(d, p2, excluir=temporada), d, excluir=temporada)
    return m, u, p2, cal


def predecir_mes(m, u, p2, mes):
    ini = pd.Timestamp(f"{mes}-01")
    horas = pd.date_range(ini, ini + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23), freq="h")
    X = mf.variables_horarias(horas)
    pz = {H: m.predict_proba(X.assign(H=H)[mf.VARIABLES])[:, 1] for H in mf.HS}
    return horas, X, pz


def archivo_c(mes):
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    c = c[c.en_piloto.eq("True") & c.quebrada_id.ne("") & c.fecha.str.startswith(mes)]
    hu = huaicos_v2().set_index("id")
    filas = []
    for r in c.itertuples():
        if r.id in hu.index:
            filas.append(dict(fecha=r.fecha, hora_inicio=hu.loc[r.id, "ini"].strftime("%H:%M"), hora_fin=hu.loc[r.id, "fin"].strftime("%H:%M"), quebrada_id=r.quebrada_id))
        else:
            filas.append(dict(fecha=r.fecha, hora_inicio="", hora_fin="", quebrada_id=r.quebrada_id))
    return pd.DataFrame(filas, columns=["fecha", "hora_inicio", "hora_fin", "quebrada_id"]).drop_duplicates().sort_values(["fecha", "hora_inicio", "quebrada_id"])


def guardar(df, nombre):
    SALIDAS.mkdir(parents=True, exist_ok=True)
    df.to_csv(SALIDAS / nombre, index=False, encoding="utf-8-sig")
    return SALIDAS / nombre


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--temporada", required=True, help="temporada que se deja fuera, p. ej. 2022-23")
    ap.add_argument("--mes", required=True, help="mes a predecir, AAAA-MM (debe pertenecer a la temporada)")
    ap.add_argument("--paso", type=int, choices=(60, 30), default=60)
    a = ap.parse_args()
    suf = a.mes.replace("-", "_")
    m, u, p2, cal = modelo_sin_temporada(a.temporada)
    horas, X, pz = predecir_mes(m, u, p2, a.mes)
    pc = cb.p_calibrada(cal, pz)  # modelo del pliegue: p_zona ya está en la escala LOSO
    zk, zk_min, zk_max = (cb.p_zona_kappa(cal, pc, k) for k in ("kappa", "kappa_min", "kappa_max"))
    rutas = [guardar(L.archivo_a(horas, zk, p2, 60), f"probabilidad_huayco_por_quebrada_con_tiempo_{suf}.csv")]
    if a.paso == 30:
        rutas.append(guardar(L.archivo_a(horas, zk, p2, 30), f"probabilidad_huayco_por_quebrada_con_tiempo_{suf}_30min.csv"))
    rutas.append(guardar(L.archivo_b(horas, X, pz, u, pc, cal), f"detalle_zona_{suf}.csv"))
    rutas.append(guardar(archivo_c(a.mes), f"huaicos_registrados_{suf}.csv"))
    nombre_d = "probabilidad_si_hay_evento.csv" if a.temporada == "2022-23" else f"probabilidad_si_hay_evento_sin_{a.temporada.replace('-', '_')}.csv"
    rutas.append(guardar(L.archivo_d(p2, cal), nombre_d))
    rutas.append(guardar(L.archivo_e(horas, zk, zk_min, zk_max, p2), f"rango_por_quebrada_{suf}.csv"))
    print("kappa (sin la temporada) por H: " + ", ".join(f"H={H}: {cal[H]['kappa']:.3f} [{cal[H]['kappa_min']:.3f}, {cal[H]['kappa_max']:.3f}]" for H in mf.HS))
    print(f"Temporada fuera: {a.temporada} | umbral rojo por H: " + ", ".join(f"H={H}: {u[H]['rojo']:.5f}" for H in mf.HS))
    for r in rutas:
        print(f"  {r.relative_to(RAIZ)}: {sum(1 for _ in open(r, encoding='utf-8-sig')) - 1} filas")


if __name__ == "__main__":
    main()

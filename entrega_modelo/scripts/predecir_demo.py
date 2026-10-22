"""Predicciones de demo FUERA DE MUESTRA para un mes: P1, P2 y umbrales calculados SIN la temporada del mes (igual que modelo_final.ejemplo()).

Uso (desde la raíz del repo):
  python entrega_modelo/scripts/predecir_demo.py --temporada 2022-23 --mes 2023-03            # paso horario
  python entrega_modelo/scripts/predecir_demo.py --temporada 2022-23 --mes 2023-03 --paso 30  # además la versión cada 30 min (repite el valor de su hora)
Usa del repo: modelo/v3/final/modelo_final.py (tabla_zona, ajustar, umbrales_oof, p2_tabla, variables_horarias) y modelo/v3/comun_v3.py (huaicos_v2).
Requiere los cachés de la cadena v3 (modelo/v3/_cache/oof_b1.parquet, modelo/v3/B/fase_b1_eventos.parquet): si faltan, correr antes `python replicar.py`.

Salidas en entrega_modelo/salidas/demo/ (UTF-8 con BOM, coma, punto decimal; Tiempo = d/mm/yyyy HH:MM, hora de Lima, inicio de la hora):
  A probabilidad_huayco_por_quebrada_con_tiempo_<AAAA_MM>[_30min].csv : Tiempo, quebrada_id, quebrada, prob_ml_3h, prob_ml_6h, prob_ml_12h, prob_ml_24h
      prob_ml_Hh = p_zona(H) x P2(quebrada), 5 decimales: PUNTAJE de riesgo por quebrada, no una probabilidad calibrada.
  B detalle_zona_<AAAA_MM>.csv : Tiempo, H, p_zona, umbral_rojo, umbral_amarillo, nivel, nivel_con_lluvia, lluvia_6h_mm
      nivel (OFICIAL, el validado): rojo si p_zona >= umbral_rojo (como en la validación); amarillo si umbral_amarillo <= p_zona < umbral_rojo; si no, verde.
      nivel_con_lluvia (variante): igual, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h disponibles (lluvia_6h_mm); si no la hay, amarillo.
      El nivel de alerta es de la ZONA (lo validado), no de cada quebrada.
  C huaicos_registrados_<AAAA_MM>.csv : fecha, hora_inicio, hora_fin, quebrada_id (catálogo, 17 quebradas; horas = rango v2; vacías si no hay hora)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTREGA = AQUI.parent
RAIZ = ENTREGA.parent
SALIDAS = ENTREGA / "salidas" / "demo"
sys.path.insert(0, str(RAIZ / "modelo" / "v3" / "final"))
import modelo_final as mf  # noqa: E402
from comun_v3 import huaicos_v2  # noqa: E402  (modelo_final ya puso modelo/v3 en sys.path)

QUEBRADAS = {"carossio": "Carossio", "corrales": "Corrales", "pedregal": "Pedregal", "california": "California", "la_ronda": "La Ronda",
             "quirio": "Quirio", "santa_maria": "Santa María", "chacrasana": "Chacrasana", "libertad": "Libertad",
             "mariscal_castilla": "Mariscal Castilla", "rosario": "Rosario", "el_vallecito": "El Vallecito", "la_cantuta": "La Cantuta",
             "santo_domingo": "Santo Domingo", "alto_peru": "Alto Perú", "huampani": "Huampaní", "buenos_aires": "Buenos Aires"}
LLUVIA_MIN = 0.1


def tiempo(h):
    h = pd.DatetimeIndex(h)
    return [f"{t.day}/{t.month:02d}/{t.year} {t:%H:%M}" for t in h]


def modelo_sin_temporada(temporada):
    """Exactamente lo de modelo_final.ejemplo(): P1 entrenado sin la temporada, umbrales LOSO calibrados sin ella y P2 con sus otras tormentas."""
    z = mf.tabla_zona()
    m = mf.ajustar(z[z.temporada != temporada])
    u = mf.umbrales_oof(excluir=temporada)
    for H in mf.HS:
        u[H]["rojo"], u[H]["amarillo"] = u[H]["rojo_oof"], u[H]["amarillo_oof"]
    p2 = mf.p2_tabla(lambda torm: torm.loc[torm.temporada != temporada, "tormenta"])
    return m, u, p2


def predecir_mes(m, u, p2, mes):
    ini = pd.Timestamp(f"{mes}-01")
    horas = pd.date_range(ini, ini + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23), freq="h")
    X = mf.variables_horarias(horas)
    pz = {H: m.predict_proba(X.assign(H=H)[mf.VARIABLES])[:, 1] for H in mf.HS}
    return horas, X, pz


def archivo_a(horas, pz, p2, paso):
    filas = []
    for i, h in enumerate(horas):
        for q, nombre in QUEBRADAS.items():
            filas.append([h, q, nombre] + [round(float(pz[H][i] * p2[q]), 5) for H in mf.HS])
    A = pd.DataFrame(filas, columns=["hora", "quebrada_id", "quebrada"] + [f"prob_ml_{H}h" for H in mf.HS])
    if paso == 30:
        B = A.assign(hora=A.hora + pd.Timedelta(minutes=30))
        A = pd.concat([A, B]).sort_values("hora", kind="stable").reset_index(drop=True)
    A.insert(0, "Tiempo", tiempo(A.hora))
    return A.drop(columns="hora")


def archivo_b(horas, X, pz, u):
    filas = []
    for H in mf.HS:
        r, a = u[H]["rojo"], u[H]["amarillo"]
        p = pz[H]
        lluvia = X.i6h.to_numpy()
        supera = p >= r
        oficial = np.where(supera, "rojo", np.where(p >= a, "amarillo", "verde"))
        con_lluvia = np.where(supera & (lluvia > LLUVIA_MIN), "rojo", np.where(supera | (p >= a), "amarillo", "verde"))
        filas.append(pd.DataFrame({"hora": horas, "H": H, "p_zona": np.round(p, 5), "umbral_rojo": round(r, 5), "umbral_amarillo": round(a, 5),
                                   "nivel": oficial, "nivel_con_lluvia": con_lluvia, "lluvia_6h_mm": np.round(lluvia, 2)}))
    B = pd.concat(filas).sort_values(["hora", "H"], kind="stable").reset_index(drop=True)
    B.insert(0, "Tiempo", tiempo(B.hora))
    return B.drop(columns="hora")


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
    m, u, p2 = modelo_sin_temporada(a.temporada)
    horas, X, pz = predecir_mes(m, u, p2, a.mes)
    rutas = [guardar(archivo_a(horas, pz, p2, 60), f"probabilidad_huayco_por_quebrada_con_tiempo_{suf}.csv")]
    if a.paso == 30:
        rutas.append(guardar(archivo_a(horas, pz, p2, 30), f"probabilidad_huayco_por_quebrada_con_tiempo_{suf}_30min.csv"))
    rutas.append(guardar(archivo_b(horas, X, pz, u), f"detalle_zona_{suf}.csv"))
    rutas.append(guardar(archivo_c(a.mes), f"huaicos_registrados_{suf}.csv"))
    print(f"Temporada fuera: {a.temporada} | umbral rojo por H: " + ", ".join(f"H={H}: {u[H]['rojo']:.5f}" for H in mf.HS))
    for r in rutas:
        print(f"  {r.relative_to(RAIZ)}: {sum(1 for _ in open(r, encoding='utf-8-sig')) - 1} filas")


if __name__ == "__main__":
    main()

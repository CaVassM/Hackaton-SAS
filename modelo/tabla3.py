"""Paso 2: tabla del modelo (tabla 3). Una fila = una quebrada, una hora y un horizonte H.

Une etiquetas (hora, quebrada_id, H, y) + features de lluvia (hora, quebrada_id) + terreno (quebrada_id).
  - Solo diciembre–abril. Se excluyen las filas con y = NaN.
  - `anomalia_14d` queda como columna pero NO es feature de la v1 (ver FEATURES_V1).
  - `dia` y `temporada` ("2014-15") sirven para agrupar en la validación.
Salida: modelo/tabla3_modelo.parquet (no va a git; se regenera con: python modelo/tabla3.py)
"""
import numpy as np
import pandas as pd

from comun import RAIZ, SALIDA, cargar_etiquetas, cargar_features, temporada_de

HORIZONTES = (3, 6, 12, 24)
FEATURES_LLUVIA = ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "tendencia_3h", "horas_lluvia_24h", "lluvia_7d", "lluvia_14d",
                   "lluvia_efectiva", "horas_desde_lluvia", "lluvia_temporada", "anomalia_14d"]
FEATURES_TERRENO = ["log10_area_km2", "pendiente_media"]
FEATURES_V1 = [f for f in FEATURES_LLUVIA if f != "anomalia_14d"] + FEATURES_TERRENO
# --- ingeniería de variables (v2): grupos definidos a priori desde la hidrología (ver lluvia/features_lluvia.py)
FEATURES_A = ["max_3h_24h", "max_3h_72h", "horas_desde_lluvia_fuerte"]                          # intensidad
FEATURES_B = ["lluvia_48h", "lluvia_72h", "api_k70", "api_k92", "dias_lluviosos_7d"]            # humedad previa
FEATURES_C = ["tendencia_24h", "frac_24h_en_7d", "lluvia_24h_sobre_api"]                        # contraste con lo anterior
FEATURES_D = ["reg_max_24h", "reg_max_3h_24h"]                                                  # regional (5 celdas)
FEATURES_E = ["hora_sen", "hora_cos"]                                                           # ciclo diario (única NO basada en lluvia: pendiente de confirmar)
FEATURES_F = ["lluvia_24h_x_log10area", "int3h_x_pendiente"]                                    # interacciones lluvia × terreno
GRUPOS_NUEVOS = {"A intensidad": FEATURES_A, "B humedad previa": FEATURES_B, "C contraste": FEATURES_C, "D regional": FEATURES_D,
                 "E ciclo diario": FEATURES_E, "F lluvia x terreno": FEATURES_F}
FEATURES_V2 = FEATURES_V1 + [f for g in GRUPOS_NUEVOS.values() for f in g]
RUTA = RAIZ / "modelo" / "tabla3_modelo.parquet"


def terreno():
    q = pd.read_csv(RAIZ / "terreno" / "quebradas.csv")[["quebrada_id", "area_km2", "pendiente_media"]]
    q["log10_area_km2"] = np.log10(q["area_km2"])
    return q[["quebrada_id", "log10_area_km2", "pendiente_media"]]


def construir():
    lab = pd.concat([cargar_etiquetas(H) for H in HORIZONTES], ignore_index=True)
    n0 = len(lab)
    lab = lab[lab.hora.dt.month.isin([12, 1, 2, 3, 4])]
    n_temp = len(lab)
    lab = lab.dropna(subset=["y"])
    info = dict(filas_etiquetas=n0, filas_dic_abr=n_temp, filas_y_nan_excluidas=n_temp - len(lab))
    t = lab.merge(cargar_features(), on=["hora", "quebrada_id"], how="left").merge(terreno(), on="quebrada_id", how="left")
    t["dia"] = t.hora.dt.normalize()
    t["temporada"] = temporada_de(t.hora)
    t["H"], t["y"] = t["H"].astype("int8"), t["y"].astype("int8")
    ang = 2 * np.pi * t.hora.dt.hour / 24                      # ciclo diario: la hora del día es conocida al predecir
    t["hora_sen"], t["hora_cos"] = np.sin(ang), np.cos(ang)
    t["lluvia_24h_x_log10area"] = t["lluvia_24h"] * t["log10_area_km2"]
    t["int3h_x_pendiente"] = t["max_3h_24h"] * t["pendiente_media"]
    for c in FEATURES_V2 + ["anomalia_14d"]:
        t[c] = t[c].astype("float32")
    cols = ["hora", "dia", "temporada", "quebrada_id", "H", "y", "anomalia_14d"] + FEATURES_V2
    return t[cols].sort_values(["H", "quebrada_id", "hora"]).reset_index(drop=True), info


def bloques(d):
    """Bloques de huaico: rachas consecutivas de horas con y = 1 dentro de cada (quebrada, H)."""
    d = d[d.y == 1].sort_values(["H", "quebrada_id", "hora"])
    nuevo = (d.groupby(["H", "quebrada_id"]).hora.diff() != pd.Timedelta(hours=1))
    return d.assign(bloque=nuevo.cumsum())


def main():
    t, info = construir()
    t.to_parquet(RUTA, index=False, compression="zstd")
    print(f"Filas en etiquetas (4 H): {info['filas_etiquetas']:,} | solo dic–abr: {info['filas_dic_abr']:,} | excluidas por y=NaN: {info['filas_y_nan_excluidas']:,}")
    print(f"TABLA 3: {len(t):,} filas × {t.shape[1]} columnas | {t.quebrada_id.nunique()} quebradas | {t.dia.nunique():,} días | "
          f"{t.hora.min():%Y-%m-%d} -> {t.hora.max():%Y-%m-%d} | guardada en {RUTA.name} ({RUTA.stat().st_size / 1e6:.0f} MB)")
    assert not t.duplicated(["hora", "quebrada_id", "H"]).any() and set(t.y.unique()) <= {0, 1}
    b = bloques(t)
    res = pd.DataFrame({"filas": t.groupby("H").size(), "positivos": t.groupby("H").y.sum(), "bloques": b.groupby("H").bloque.nunique()})
    res["tasa_positivos_%"] = (100 * res.positivos / res.filas).round(3)
    print("\nPOR HORIZONTE\n" + res.to_string())
    # ¿se perdió algún positivo al filtrar dic–abr? (el contexto dice que todos los eventos caen entre enero y abril)
    for H in HORIZONTES:
        e = cargar_etiquetas(H)
        assert int((e.y == 1).sum()) == int(res.positivos[H]), f"H={H}: se perdieron positivos al filtrar a dic–abr"
    print("Positivos conservados al 100 % tras el filtro dic–abr.")
    seas = pd.DataFrame({"filas_H6": t[t.H == 6].groupby("temporada").size(), "positivos_H6": t[t.H == 6].groupby("temporada").y.sum(),
                         "bloques_H6": b[b.H == 6].groupby("temporada").bloque.nunique() if "temporada" in b else None}).fillna(0).astype(int)
    print("\nTEMPORADAS (H=6)\n" + seas.to_string())
    con = seas[seas.positivos_H6 > 0].index.tolist()
    print(f"\nTemporadas con al menos un evento: {len(con)} de {len(seas)} -> {con}")
    pos_h = b.groupby(["temporada", "H"]).bloque.nunique().unstack("H").fillna(0).astype(int)
    print("\nBLOQUES POR TEMPORADA Y H\n" + pos_h.to_string())
    print("\n% NaN por columna (features):", {c: round(100 * t[c].isna().mean(), 1) for c in FEATURES_V2 + ["anomalia_14d"] if t[c].isna().any()})
    res.to_csv(SALIDA / "tabla3_resumen_por_H.csv"); seas.to_csv(SALIDA / "tabla3_temporadas_H6.csv"); pos_h.to_csv(SALIDA / "tabla3_bloques_por_temporada_H.csv")


if __name__ == "__main__":
    main()

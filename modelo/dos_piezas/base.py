"""Modelo en DOS PIEZAS (fase R1): datos compartidos. Riesgo(quebrada, t, H) = P1(zona, t, H) x P2(quebrada).

  - Tabla de ZONA (pieza 1): una fila = una hora y un H (dic-abr). y = 1 si alguna de las 17 quebradas tiene y=1 en (t, t+H];
    NaN si alguna tiene NaN y ninguna tiene 1 (mismas etiquetas que tabla3, incluida la corrección del paso 9.2); si no, 0.
  - Variables de zona (fijadas antes de correr): las 11 variables de lluvia de la v1 calculadas POR CELDA IMERG (5 celdas, latencia 4 h,
    mismo código que lluvia/features_lluvia.py) y agregadas entre celdas con máximo y promedio. En horas_desde_lluvia se usa el MÍNIMO
    (= la celda más lluviosa, el análogo del máximo). Más reg_max_3h_24h. reg_max_24h NO se agrega: es idéntica a lluvia_24h_max.
  - Tormenta: fechas con activación en las 17 quebradas (catálogo, mismo criterio que las etiquetas: en_piloto, quebrada con quebrada_id,
    incluye el 25/02/2019 que las etiquetas cuentan como positivo) separadas por <= 2 días.
  - Pliegues "dejar una tormenta fuera" (LOSTO): cada temporada con tormentas se parte en tramos, uno por tormenta, cortando a mitad de camino
    entre una tormenta y la siguiente; las horas sin tormenta quedan con la tormenta más cercana de su temporada. Cada temporada sin tormentas
    es un pliegue propio. Así toda hora recibe exactamente una predicción fuera de muestra.
  - Pliegues LOSO: una temporada por pliegue (12).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from comun import RAIZ, cargar_etiquetas, poner_nan_dias_fuera_del_piloto, temporada_de  # noqa: E402
from tabla3 import HORIZONTES, terreno  # noqa: E402

SALIDA = AQUI / "salida"
SALIDA.mkdir(exist_ok=True)
RUTA_ZONA = AQUI / "tabla_zona.parquet"
VARS_V1 = ["lluvia_3h", "lluvia_6h", "lluvia_24h", "int_max_24h", "tendencia_3h", "horas_lluvia_24h", "lluvia_7d", "lluvia_14d",
           "lluvia_efectiva", "horas_desde_lluvia", "lluvia_temporada"]
FEATURES_ZONA = ([f"{v}_{a}" for v in VARS_V1 for a in (("min", "media") if v == "horas_desde_lluvia" else ("max", "media"))]
                 + ["reg_max_3h_24h"])
# monotonía (+1: más lluvia nunca baja el riesgo); tendencia_3h sin restricción; horas desde lluvia -1
MONO_ZONA = {f: (0 if f.startswith("tendencia_3h") else -1 if f.startswith("horas_desde_lluvia") else 1) for f in FEATURES_ZONA}
DIAS_TORMENTA = 2


# --------------------------------------------------------------------------- tabla de zona
def _features_zona():
    import features_lluvia as fl

    datos, pesos = RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
    Rcel = fl.lluvia_celdas(datos, pesos)
    F = fl.features(Rcel, Rcel)   # cada "columna" es una celda: mismas reglas de latencia y de NaN que por quebrada
    out = {}
    for v in VARS_V1:
        if v == "horas_desde_lluvia":
            out[f"{v}_min"] = F[v].min(axis=1, skipna=False)
        else:
            out[f"{v}_max"] = F[v].max(axis=1, skipna=False)
        out[f"{v}_media"] = F[v].mean(axis=1, skipna=False)
    out["reg_max_3h_24h"] = F["reg_max_3h_24h"].iloc[:, 0]
    assert np.allclose(F["reg_max_24h"].iloc[:, 0], out["lluvia_24h_max"], equal_nan=True), "reg_max_24h debería ser lluvia_24h_max"
    z = pd.DataFrame(out)
    z.index.name = "hora"
    return z.reset_index()


def etiquetas_zona():
    """(hora, H, y_zona, n_quebradas_y1) con las mismas etiquetas que tabla3 (dic-abr, paso 9.2)."""
    lab = pd.concat([cargar_etiquetas(H) for H in HORIZONTES], ignore_index=True)
    lab = lab[lab.hora.dt.month.isin([12, 1, 2, 3, 4])]
    lab, _ = poner_nan_dias_fuera_del_piloto(lab)
    g = lab.groupby(["hora", "H"]).y
    z = pd.DataFrame({"uno": g.max(), "hay_nan": g.apply(lambda s: s.isna().any()), "n_q": g.size(), "n_y1": g.sum()}).reset_index()
    assert (z.n_q == 17).all()
    z["y"] = np.where(z.uno == 1, 1.0, np.where(z.hay_nan, np.nan, 0.0))
    return z[["hora", "H", "y", "n_y1"]]


def tabla_zona(forzar=False):
    if RUTA_ZONA.exists() and not forzar:
        return pd.read_parquet(RUTA_ZONA)
    z = etiquetas_zona().merge(_features_zona(), on="hora", how="left")
    z["temporada"] = temporada_de(z.hora)
    z["H"] = z.H.astype("int8")
    for c in FEATURES_ZONA:
        z[c] = z[c].astype("float32")
    z = z.sort_values(["H", "hora"]).reset_index(drop=True)
    z.to_parquet(RUTA_ZONA, index=False)
    return z


# --------------------------------------------------------------------------- tormentas y activaciones
def activaciones():
    """(fecha, quebrada_id) activadas según el catálogo, con el mismo criterio que etiquetas_por_quebrada.py."""
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", parse_dates=["fecha"])
    a = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv")
    m = c[c.en_piloto.astype(bool)].merge(a[["nombre_catalogo", "quebrada_id"]], left_on="quebrada", right_on="nombre_catalogo", how="left")
    return m[m.quebrada_id.notna()][["fecha", "quebrada_id"]].drop_duplicates().sort_values(["fecha", "quebrada_id"]).reset_index(drop=True)


def tormentas():
    """Una fila por tormenta: tormenta (T01...), temporada, inicio, fin (fechas), fechas, quebradas activadas."""
    a = activaciones()
    f = pd.Series(sorted(a.fecha.unique()))
    grupo = (f.diff() > pd.Timedelta(days=DIAS_TORMENTA)).cumsum()
    filas = []
    for k, fs in f.groupby(grupo):
        q = sorted(a[a.fecha.isin(fs)].quebrada_id.unique())
        filas.append(dict(tormenta=f"T{k + 1:02d}", temporada=temporada_de(pd.Series([fs.iloc[0]])).iloc[0], inicio=fs.min(), fin=fs.max(),
                          fechas=",".join(x.strftime("%Y-%m-%d") for x in fs), n_activadas=len(q), activadas=",".join(q)))
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- pliegues
def pliegue_losto(hora, temporada, torm):
    """Pliegue de cada hora: id de la tormenta de su tramo, o 'S:<temporada>' si la temporada no tiene tormentas."""
    hora, temporada = pd.Series(hora).reset_index(drop=True), pd.Series(temporada).reset_index(drop=True)
    out = np.array(["S:" + s for s in temporada], dtype=object)
    for s, g in torm.groupby("temporada"):
        g = g.sort_values("inicio")
        m = (temporada == s).to_numpy()
        # cortes a mitad de camino entre el fin de una tormenta (fin del día) y el inicio de la siguiente
        cortes = [(g.fin.iloc[i] + pd.Timedelta(days=1)) + ((g.inicio.iloc[i + 1]) - (g.fin.iloc[i] + pd.Timedelta(days=1))) / 2 for i in range(len(g) - 1)]
        idx = np.searchsorted(np.array(cortes, dtype="datetime64[ns]"), hora[m].to_numpy("datetime64[ns]"), side="right")
        out[m] = g.tormenta.to_numpy()[idx]
    return out


def tormenta_de_hora(hora, torm):
    """Tormenta a la que pertenece una hora positiva: la de su temporada cuyo rango [inicio-1 d, fin+2 d) la contiene; si no, ''."""
    hora = pd.Series(hora).reset_index(drop=True)
    out = np.array([""] * len(hora), dtype=object)
    for r in torm.itertuples():
        m = ((hora >= r.inicio - pd.Timedelta(days=1)) & (hora < r.fin + pd.Timedelta(days=2))).to_numpy()
        out[m] = r.tormenta
    return out


def p2_tabla():
    """Terreno de las 17 quebradas para la pieza 2: log10(área), pendiente e img_media (experimento)."""
    q = pd.read_csv(RAIZ / "terreno" / "quebradas.csv")[["quebrada_id", "img_media"]]
    return terreno().merge(q, on="quebrada_id").set_index("quebrada_id").sort_index()


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    t = tormentas()
    print(t.to_string(index=False))
    z = tabla_zona(forzar=True)
    print(f"\nTabla de zona: {len(z):,} filas ({z.hora.nunique():,} horas x 4 H) | {len(FEATURES_ZONA)} variables")
    r = z.groupby("H").agg(filas=("y", "size"), y_nan=("y", lambda s: int(s.isna().sum())), positivos=("y", "sum"), tasa=("y", "mean"))
    print(r.to_string())
    z["pliegue"] = pliegue_losto(z.hora, z.temporada, t)
    pos = z[z.y == 1]
    tor = tormenta_de_hora(pos.hora, t)
    assert (tor != "").all(), "hay horas positivas fuera de toda tormenta"
    assert (tor == pos.pliegue.to_numpy()).all(), "una hora positiva cae en el tramo de otra tormenta"
    print("Horas positivas por tormenta (H=6):", pd.Series(tor[pos.H.to_numpy() == 6]).value_counts().sort_index().to_dict())
    print("Pliegues LOSTO:", z.pliegue.nunique(), "| % NaN por variable:", {c: round(100 * z[c].isna().mean(), 1) for c in FEATURES_ZONA if z[c].isna().mean() > 0.01})

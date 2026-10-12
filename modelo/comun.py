"""Carga compartida para los scripts de modelo/: features de lluvia, etiquetas, eventos del catálogo y terreno."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "lluvia"))
SALIDA = Path(__file__).resolve().parent / "salida"
SALIDA.mkdir(exist_ok=True)


def cargar_features(forzar=False):
    """Features de lluvia (hora, quebrada_id, ...). Si no existe el parquet, lo calcula desde los 60 meses de IMERG Early."""
    ruta = RAIZ / "lluvia" / "features_lluvia.parquet"
    if forzar or not ruta.exists():
        import features_lluvia as fl

        datos, pesos = RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
        R = fl.lluvia_horaria(datos, pesos)
        # sin la lluvia por celda las variables regionales (reg_max_*) quedan 100 % NaN
        fl.a_largo(fl.features(R, fl.lluvia_celdas(datos, pesos)), R).to_parquet(ruta, index=False)
        R.stack(future_stack=True).dropna().rename("mm").astype("float32").reset_index().set_axis(
            ["hora", "quebrada_id", "mm"], axis=1).to_parquet(RAIZ / "lluvia" / "lluvia_horaria_quebradas.parquet", index=False)
    return pd.read_parquet(ruta)


def cargar_lluvia_horaria():
    cargar_features()
    return pd.read_parquet(RAIZ / "lluvia" / "lluvia_horaria_quebradas.parquet")


def cargar_etiquetas(H):
    return pd.read_parquet(RAIZ / "catalogo_huaicos_chosica" / f"etiquetas_horarias_H{H}.parquet")


def eventos_catalogo():
    """(fecha, quebrada_id, hora_evento) de las activaciones con quebrada del piloto y sin marca `dudoso`. Una fila por fecha-quebrada."""
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv")
    a = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv")[["nombre_catalogo", "quebrada_id"]]
    m = c.merge(a, left_on="quebrada", right_on="nombre_catalogo", how="left")
    m = m[m.quebrada_id.notna() & m.dudoso.isna()].copy()
    m["fecha"] = pd.to_datetime(m["fecha"])
    m["hora_evento"] = pd.to_datetime(m["hora_inicio"], format="%H:%M", errors="coerce").dt.hour
    return (m.sort_values("id").drop_duplicates(["fecha", "quebrada_id"])[["id", "fecha", "quebrada_id", "hora_evento", "usable_horario"]]
            .reset_index(drop=True))


FUERA_DEL_PILOTO = {"Huaycoloro", "Rioseco", "Los Laureles"}   # quebradas del catálogo que el piloto ignora (cuenca grande fuera del recorte / probable Chaclacayo)


def dias_evento_fuera_del_piloto(incluir_excluidas=True):
    """Fechas con huaico en el catálogo pero NINGUNO en las 17 quebradas del piloto: en esos días las 17 quedaron y=0 sin saberse si activaron.

    Son fechas con eventos solo en distritos vecinos (Chaclacayo, Santa Eulalia...) o solo en quebradas que el piloto ignora (Huaycoloro, Río Seco...).
    `incluir_excluidas=False` deja fuera estas últimas (solo distritos vecinos).
    """
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", parse_dates=["fecha"])
    en_pil = c.en_piloto.astype(bool)
    if incluir_excluidas:
        en_pil &= ~c.quebrada.isin(FUERA_DEL_PILOTO)
    con_piloto = set(c.loc[en_pil, "fecha"])
    return sorted(set(c.fecha) - con_piloto)


def poner_nan_dias_fuera_del_piloto(lab, incluir_excluidas=True):
    """y=0 -> NaN en filas cuya ventana (t, t+H] toca un día de `dias_evento_fuera_del_piloto`. Los y=1 se conservan. `lab`: hora, quebrada_id, H, y."""
    y = lab["y"].to_numpy(dtype="float64").copy()
    t = lab["hora"].to_numpy("datetime64[ns]")
    H = lab["H"].to_numpy().astype("timedelta64[h]").astype("timedelta64[ns]")
    marca = np.zeros(len(lab), bool)
    for d in dias_evento_fuera_del_piloto(incluir_excluidas):
        d0 = np.datetime64(d, "ns")
        marca |= (t < d0 + np.timedelta64(24, "h")) & (t + H > d0)
    n = int(((y == 0) & marca).sum())
    y[(y == 0) & marca] = np.nan
    return lab.assign(y=y), n


def temporada_de(hora):
    """'2014-15' para dic 2014–abr 2015."""
    y = np.where(hora.dt.month >= 6, hora.dt.year, hora.dt.year - 1)
    return pd.Series([f"{a}-{str(a + 1)[2:]}" for a in y], index=hora.index)

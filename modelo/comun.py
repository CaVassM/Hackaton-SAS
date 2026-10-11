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

        R = fl.lluvia_horaria(RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv"))
        fl.a_largo(fl.features(R), R).to_parquet(ruta, index=False)
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


def temporada_de(hora):
    """'2014-15' para dic 2014–abr 2015."""
    y = np.where(hora.dt.month >= 6, hora.dt.year, hora.dt.year - 1)
    return pd.Series([f"{a}-{str(a + 1)[2:]}" for a in y], index=hora.index)

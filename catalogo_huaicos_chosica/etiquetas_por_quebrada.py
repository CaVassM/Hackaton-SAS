"""
Etiquetas horarias por quebrada_id final (camino del terreno, fase 5).

Usa la misma lógica que construir_catalogo.py, pero cada evento se asigna a su quebrada_id
con terreno/alias_catalogo.csv (17 quebradas del piloto, terreno/quebradas.csv).

  y = 1   el huaico ocurre en (t, t+H]
  y = 0   no hay evento conocido ('sin noticia', no 'cero seguro')
  y = NaN excluir: desde el evento hasta 24 h después, o día sin hora útil

Eventos sin quebrada_id:
  - quebradas fuera del piloto (Huaycoloro, Río Seco, Los Laureles): se ignoran
  - sin nombre o sin ubicar (La Trinchera, Lechuceros, Los Molles): NaN ese día en las 17 quebradas

Uso:
    python etiquetas_por_quebrada.py                 # H = 3, 6, 12, 24
    python etiquetas_por_quebrada.py --H 6 12
"""
import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from construir_catalogo import CARPETA, agregar_tiempos, cargar_catalogo

TERRENO = CARPETA.parent / "terreno"
DESDE, HASTA = "2015-01-01", "2026-06-30 23:00"


def cargar_con_quebrada_id():
    alias = pd.read_csv(TERRENO / "alias_catalogo.csv", dtype=str).fillna("")
    quebradas = sorted(pd.read_csv(TERRENO / "quebradas.csv")["quebrada_id"])
    cat = agregar_tiempos(cargar_catalogo())
    p = cat[cat["en_piloto"]]
    faltan = set(p.loc[p["quebrada"].ne(""), "quebrada"]) - set(alias["nombre_catalogo"])
    assert not faltan, f"Nombres del catálogo sin fila en alias_catalogo.csv: {faltan}"
    cat["quebrada_id"] = cat["quebrada"].map(dict(zip(alias["nombre_catalogo"], alias["quebrada_id"]))).fillna("")
    assert set(cat["quebrada_id"]) - {""} <= set(quebradas), "quebrada_id que no está en quebradas.csv"
    fuera = set(alias.loc[alias["motivo"].str.contains("en_piloto = False"), "nombre_catalogo"])
    return cat, quebradas, fuera


def etiquetas_horarias(cat, quebradas, fuera, H, horas_post=24):
    horas = pd.date_range(DESDE, HASTA, freq="h")
    y = pd.DataFrame(0.0, index=horas, columns=quebradas)
    pos = pd.DataFrame(False, index=horas, columns=quebradas)

    def marcar(df, a, b, cols, valor):
        a, b = max(a, horas[0]), min(b, horas[-1])
        if a <= b:
            df.loc[a:b, cols] = valor

    for _, ev in cat[cat["en_piloto"]].iterrows():
        if ev["quebrada"] in fuera:
            continue                                   # quebrada fuera del piloto
        dia = pd.Timestamp(ev["fecha"])
        qid = ev["quebrada_id"]
        cols = [qid] if qid else quebradas             # sin quebrada o sin ubicar -> todas
        if ev["usable_horario"] and qid:
            ini, fin = ev["dt_inicio"], ev["dt_fin"]
            primera = (ini - pd.Timedelta(hours=H)).ceil("h")
            ultima = (ini - pd.Timedelta(minutes=1)).floor("h")
            marcar(pos, primera, ultima, cols, True)
            marcar(y, ini.ceil("h"), fin + pd.Timedelta(hours=horas_post), cols, np.nan)
        else:
            marcar(y, dia - pd.Timedelta(hours=H), dia + pd.Timedelta(hours=24 + horas_post), cols, np.nan)

    y[pos] = 1.0
    largo = y.stack(future_stack=True).rename("y").reset_index()
    largo.columns = ["hora", "quebrada_id", "y"]
    largo.insert(2, "H", H)
    return largo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--H", type=int, nargs="+", default=[3, 6, 12, 24])
    args = ap.parse_args()

    # Respaldo de la versión anterior (por nombre del catálogo), sin borrarla
    previa = CARPETA / "etiquetas_horarias_H6.parquet"
    respaldo = CARPETA / "v0_por_nombre" / previa.name
    if previa.exists() and not respaldo.exists() and "quebrada" in pd.read_parquet(previa).columns:
        respaldo.parent.mkdir(exist_ok=True)
        shutil.copy2(previa, respaldo)
        print(f"Respaldo: {respaldo}")

    cat, quebradas, fuera = cargar_con_quebrada_id()
    p = cat[cat["en_piloto"]]
    print(f"Quebradas: {len(quebradas)} | eventos del piloto: {len(p)} | con quebrada_id: {p['quebrada_id'].ne('').sum()} "
          f"| usables horario con quebrada_id: {(p['usable_horario'] & p['quebrada_id'].ne('')).sum()} | ignorados (fuera): {p['quebrada'].isin(fuera).sum()}")
    filas = []
    for H in args.H:
        et = etiquetas_horarias(cat, quebradas, fuera, H)
        et.to_parquet(CARPETA / f"etiquetas_horarias_H{H}.parquet", index=False)
        vc = et["y"].value_counts(dropna=False)
        pos = et[et["y"].eq(1)]
        n_ev = pos.groupby("quebrada_id")["hora"].apply(lambda s: (s.diff() != pd.Timedelta(hours=1)).sum()).sum()
        filas.append({"H": H, "y=1": int(vc.get(1.0, 0)), "y=0": int(vc.get(0.0, 0)), "NaN": int(et["y"].isna().sum()),
                      "filas": len(et), "eventos_con_y1": int(n_ev), "quebradas_con_y1": pos["quebrada_id"].nunique()})
    print(pd.DataFrame(filas).to_string(index=False))

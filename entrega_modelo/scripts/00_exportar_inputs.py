"""(Mantenedor) Exporta los insumos del paquete a entrega_modelo/inputs/ (CSV) y la referencia a entrega_modelo/salidas/referencia/, DESDE EL REPO.
El equipo NO necesita correrlo: los CSV ya vienen en inputs/. Usa del repo:
  modelo/v3/comun_v3.py (lluvia_celdas, etiquetar, eventos_lluvia, lluvia_zona, huaicos_v2), modelo/dos_piezas/base.py (etiquetas_zona, activaciones),
  modelo/v3/B/fase_b1_eventos.parquet y fase_b1_resumen.csv, modelo/v3/final/metadatos_final.json y p2_final.csv, modelo/v3/datos/raw/ (ERA5-Land, ICEN).
Uso (desde la raíz del repo): python entrega_modelo/scripts/00_exportar_inputs.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTREGA = AQUI.parent
RAIZ = ENTREGA.parent
V3 = RAIZ / "modelo" / "v3"
for p in (V3, V3 / "A", V3 / "B", RAIZ / "modelo" / "dos_piezas", RAIZ / "modelo"):
    sys.path.insert(0, str(p))
import base  # noqa: E402
from comun_v3 import etiquetar, eventos_lluvia, huaicos_v2, lluvia_celdas, lluvia_zona  # noqa: E402

IN = ENTREGA / "inputs"
REF = ENTREGA / "salidas" / "referencia"


def main():
    IN.mkdir(parents=True, exist_ok=True)
    REF.mkdir(parents=True, exist_ok=True)
    # 1. lluvia horaria por celda IMERG (mm en la hora; hora = inicio de la hora local)
    R = lluvia_celdas()
    R = R[R.notna().any(axis=1)]
    R.index.name = "hora"
    R.to_csv(IN / "lluvia_horaria_celdas.csv")
    # 2. humedad del suelo 0-7 cm (ERA5-Land, media de las 5 celdas; hora = inicio de la hora; valor al final de esa hora)
    sm = pd.read_parquet(V3 / "datos" / "raw" / "openmeteo" / "era5_land.parquet").groupby("hora").soil_moisture_0_to_7cm.mean()
    sm.rename("hum_suelo_0_7cm").to_csv(IN / "humedad_suelo_horaria.csv")
    # 3. ICEN
    ic = pd.read_csv(V3 / "datos" / "raw" / "icen" / "ICEN.txt", comment="%", sep=r"\s+", names=["anio", "mes", "icen"])
    ic.to_csv(IN / "icen.csv", index=False)
    # 4. activaciones del catálogo (17 quebradas; con hora v2 si la tiene)
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(al.nombre_catalogo, al.quebrada_id))).fillna("")
    c = c[c.en_piloto.eq("True") & c.quebrada_id.ne("")]
    hu = huaicos_v2().set_index("id")
    act = pd.DataFrame({"id": c.id, "fecha": c.fecha, "quebrada_id": c.quebrada_id,
                        "hora_inicio": [hu.loc[i, "ini"].strftime("%H:%M") if i in hu.index else "" for i in c.id],
                        "hora_fin": [hu.loc[i, "fin"].strftime("%Y-%m-%d %H:%M") if i in hu.index else "" for i in c.id],
                        "con_hora": c.id.isin(hu.index), "dudoso": c.dudoso.ne(""), "fuente": c.fuente, "url": c.url})
    assert set(zip(act.fecha, act.quebrada_id)) == set(zip(base.activaciones().fecha.dt.strftime("%Y-%m-%d"), base.activaciones().quebrada_id))
    act.to_csv(IN / "activaciones.csv", index=False)
    # 5. terreno
    q = pd.read_csv(RAIZ / "terreno" / "quebradas.csv")
    q["log10_area_km2"] = np.log10(q.area_km2)
    q[["quebrada_id", "nombre", "area_km2", "log10_area_km2", "pendiente_media", "salida_tipo", "salida_lat", "salida_lon"]].to_csv(IN / "quebradas_terreno.csv", index=False)
    # 6. etiquetas de zona v2 (hora, H, y): y = 1 si alguna de las 17 quebradas tiene huaico en (t, t+H]
    base.cargar_etiquetas = lambda H: pd.read_parquet(RAIZ / "catalogo_huaicos_chosica" / f"etiquetas_horarias_v2_H{H}.parquet")
    base.etiquetas_zona()[["hora", "H", "y"]].to_csv(IN / "etiquetas_zona.csv", index=False)
    # 7. eventos de lluvia (los evaluados: sin los "desconocidos") + días ciegos
    ev = pd.read_parquet(V3 / "B" / "fase_b1_eventos.parquet")
    cols = ["inicio", "fin", "duracion_h", "total_mm", "max1", "max3", "max6", "temporada", "disparador", "huaico_fin", "tormenta"]
    e = ev[cols].assign(tipo="evento")
    _, ciegos = etiquetar(eventos_lluvia(lluvia_zona()))
    cg = pd.DataFrame({"inicio": pd.to_datetime(ciegos.fecha), "temporada": ciegos.temporada, "disparador": 1, "tormenta": ciegos.tormenta, "tipo": "dia_ciego"})
    pd.concat([e, cg], ignore_index=True)[["tipo"] + cols].to_csv(IN / "eventos_lluvia.csv", index=False)
    # referencia (modelo final del repo)
    meta = json.loads((V3 / "final" / "metadatos_final.json").read_text(encoding="utf-8"))
    pd.DataFrame([{"H": int(H), **u} for H, u in meta["umbrales"].items()]).to_csv(REF / "umbrales.csv", index=False)
    pd.read_csv(V3 / "final" / "p2_final.csv").rename(columns={"Unnamed: 0": "quebrada_id", "p2_mezcla": "p2"}).to_csv(REF / "p2.csv", index=False)
    b1 = pd.read_csv(V3 / "B" / "fase_b1_resumen.csv")
    b1[b1.metodo.str.startswith("(a) A2 + estado (humedad 5 d)")].assign(metodo="B1 (P1 del modelo final), LOSO por evento").to_csv(REF / "metricas_validacion.csv", index=False)
    for f in sorted(IN.glob("*.csv")):
        print(f"  {f.relative_to(RAIZ)}: {sum(1 for _ in open(f, encoding='utf-8')) - 1} filas")


if __name__ == "__main__":
    main()

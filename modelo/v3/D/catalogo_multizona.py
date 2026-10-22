"""Fase D: catálogo multizona de flujos (huaicos / flujos de detritos / aluviones) en zonas áridas del Pacífico (Perú y norte de Chile).

Campos unificados: fuente, url, fecha, hora, lat, lon, precision_km, tipo, pais, region, distrito, texto.
Fuentes (si una no responde, se documenta y se sigue):
  D1a INGEMMET SERV_PERU_ALERTA capa 4 "Zonas críticas por activación de quebradas" (geocatmin.ingemmet.gob.pe; el servicio citado en
      geocatminapp ya no existe): puntos con F_EVENTO y F_REACTIVACION (cada fecha es un evento). Precisión: punto (~1 km).
  D1b INDECI/SINPAD: BD_2003-2025_EMERGENCIAS.csv (carpeta del proyecto), PELIGRO = HUAYCO en Lima Metropolitana, Lima Provincias, Ica, Arequipa,
      Moquegua y Tacna. Ubicación = centroide del distrito (ubigeo); precisión = radio equivalente del distrito. Fechas dd/mm/aaaa (y mm/dd/aa en 2025).
  D2  SERNAGEOMIN (Remociones en masa Chile, REST) y Matus et al. (Zenodo 10.5281/zenodo.14342936): se intentan; ver estado en la salida.
  D3  NASA Global Landslide Catalog (COOLR), Perú y Chile.
Salidas: modelo/v3/D/catalogo_multizona.csv, catalogo_estado_fuentes.csv
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAW = AQUI.parent / "datos" / "raw" / "catalogos"
RAW.mkdir(parents=True, exist_ok=True)
RAIZ_PADRE = AQUI.parents[4]   # carpeta 'Hackaton SAS' (fuera del repo)
UA = {"User-Agent": "Mozilla/5.0"}
INGEMMET = "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_PERU_ALERTA/MapServer/4/query"
SERNA = "https://sdngsig.sernageomin.cl/gissdng/rest/services/Remociones_en_masa_Chile/Remociones_en_Masa_Chile/MapServer"
GLC = "https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv"
DEP_ARIDOS = ["LIMA METROPOLITANA", "LIMA PROVINCIAS", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"]
COLS = ["fuente", "url", "fecha", "hora", "lat", "lon", "precision_km", "tipo", "pais", "region", "distrito", "texto"]


def get(url, timeout=120, reintentos=4):
    for k in range(reintentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:150]
            time.sleep(5 * (k + 1))
    raise RuntimeError(err)


def ingemmet():
    feats, off = [], 0
    while True:
        q = urllib.parse.urlencode(dict(where="1=1", outFields="*", returnGeometry="false", resultOffset=off, resultRecordCount=1000, f="json"))
        d = json.loads(get(f"{INGEMMET}?{q}"))
        f = d.get("features", [])
        feats += [x["attributes"] for x in f]
        if len(f) < 1000:
            break
        off += 1000
    a = pd.DataFrame(feats)
    a.to_csv(RAW / "ingemmet_peru_alerta_capa4.csv", index=False)
    filas = []
    for r in a.itertuples():
        for campo in ("F_EVENTO", "F_REACTIVACION"):
            v = getattr(r, campo)
            if v is None or pd.isna(v):
                continue
            fecha = pd.to_datetime(v, unit="ms")
            filas.append(dict(fuente="INGEMMET PERU_ALERTA", url=getattr(r, "URL_BOLETIN") or INGEMMET, fecha=fecha.date(), hora=None, lat=r.LATITUD, lon=r.LONGITUD,
                              precision_km=1.0, tipo=f"{r.PELIGROS_G} | {r.PELIGRO_ESPECIFICO_ISO or ''}".strip(" |"), pais="Perú", region=r.NM_DEPA or r.REGION,
                              distrito=r.NM_DIST or r.DISTRITO, texto=f"{campo}: {r.PARAJE} | {r.DESCRIPCION or ''} | {r.COMENT_GEODINAMICO or ''}"[:500]))
    return pd.DataFrame(filas), len(a)


def indeci():
    import geopandas as gpd

    d = pd.read_csv(RAIZ_PADRE / "BD_2003-2025_EMERGENCIAS.csv", sep=";", encoding="latin-1", dtype=str)
    h = d[d.PELIGRO.eq("HUAYCO") & d["DPTO."].isin(DEP_ARIDOS)].copy()
    f = h["FECHA  DE LA EMER"].str.strip()
    fecha = pd.to_datetime(f, format="%d/%m/%Y", errors="coerce")
    fecha = fecha.fillna(pd.to_datetime(f, format="%m/%d/%y", errors="coerce"))
    g = gpd.read_file(RAW / "peru_distritos.geojson")[["IDDIST", "geometry"]]
    gu = g.to_crs(32718)
    cen = gu.geometry.centroid.to_crs(4326)
    info = pd.DataFrame({"IDDIST": g.IDDIST, "lat": cen.y, "lon": cen.x, "precision_km": np.sqrt(gu.area / np.pi) / 1000})
    h["fecha"] = fecha
    h = h.merge(info, left_on="COD. DISTRITO", right_on="IDDIST", how="left")
    out = pd.DataFrame(dict(fuente="INDECI SINPAD", url="BD_2003-2025_EMERGENCIAS.csv (INDECI)", fecha=h.fecha.dt.date, hora=None, lat=h.lat, lon=h.lon,
                            precision_km=h.precision_km.round(1), tipo="huayco", pais="Perú", region=h["DPTO."], distrito=h["DIST."],
                            texto="SINPAD " + h["CODIGO DE EMERGENCIA-SINPAD"].astype(str) + " | " + h["PROV."]))
    return out, len(h)


def glc():
    ruta = RAW / "glc_nasa.csv"
    if not ruta.exists() or ruta.stat().st_size == 0:
        ruta.write_bytes(get(GLC, timeout=600))
    g = pd.read_csv(ruta)
    g = g[g.country_name.isin(["Peru", "Chile"])]
    acc = {"exact": 0.5, "1km": 1, "5km": 5, "10km": 10, "25km": 25, "50km": 50, "100km": 100, "250km": 250, "unknown": np.nan}
    g = g[g.landslide_category.isin(["mudslide", "debris_flow", "landslide", "complex", "lahar"]) & ~g.landslide_trigger.isin(["earthquake", "snowfall_snowmelt"])]
    fecha = pd.to_datetime(g.event_date, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    tiene_hora = g.event_time.notna() & g.event_time.astype(str).str.strip().ne("")
    out = pd.DataFrame(dict(fuente="NASA GLC (COOLR)", url=g.source_link, fecha=fecha.dt.date, hora=np.where(tiene_hora, g.event_time.astype(str), None),
                            lat=g.latitude, lon=g.longitude, precision_km=g.location_accuracy.map(acc), tipo=g.landslide_category.astype(str) + " | " + g.landslide_trigger.astype(str),
                            pais=g.country_name.map({"Peru": "Perú", "Chile": "Chile"}), region=g.admin_division_name, distrito=g.gazeteer_closest_point,
                            texto=g.event_title.astype(str) + " | " + g.event_description.astype(str).str[:300]))
    return out, len(g)


def sernageomin():
    d = json.loads(get(f"{SERNA}?f=json", timeout=60))
    return d


def main():
    estado, partes = [], []
    for nombre, fn in (("D1a INGEMMET PERU_ALERTA", ingemmet), ("D1b INDECI SINPAD", indeci), ("D3 NASA GLC", glc)):
        try:
            df, n = fn()
            partes.append(df)
            estado.append(dict(fuente=nombre, estado="ok", registros_crudos=n, eventos=len(df)))
        except Exception as e:  # noqa: BLE001
            estado.append(dict(fuente=nombre, estado=f"FALLÓ: {repr(e)[:150]}", registros_crudos=0, eventos=0))
        print(estado[-1], flush=True)
    try:
        sernageomin()
        estado.append(dict(fuente="D2 SERNAGEOMIN", estado="responde (falta implementar la consulta de capas)", registros_crudos=0, eventos=0))
    except Exception as e:  # noqa: BLE001
        estado.append(dict(fuente="D2 SERNAGEOMIN", estado=f"NO RESPONDE desde esta red: {repr(e)[:120]}", registros_crudos=0, eventos=0))
    try:
        get("https://zenodo.org/api/records/14342936", timeout=60)
        estado.append(dict(fuente="D2 Matus et al. (Zenodo)", estado="responde", registros_crudos=0, eventos=0))
    except Exception as e:  # noqa: BLE001
        estado.append(dict(fuente="D2 Matus et al. (Zenodo)", estado=f"NO RESPONDE: {repr(e)[:120]}", registros_crudos=0, eventos=0))
    print(estado[-2:], flush=True)
    c = pd.concat(partes, ignore_index=True)[COLS]
    c["fecha"] = pd.to_datetime(c.fecha)
    c = c.dropna(subset=["fecha"]).sort_values(["fecha", "fuente"]).reset_index(drop=True)
    c.to_csv(AQUI / "catalogo_multizona.csv", index=False, encoding="utf-8")
    pd.DataFrame(estado).to_csv(AQUI / "catalogo_estado_fuentes.csv", index=False)
    pd.set_option("display.width", 220)
    r = c.groupby("fuente").agg(eventos=("fecha", "size"), con_hora=("hora", lambda s: round(100 * s.notna().mean(), 1)),
                                precision_menor_5km=("precision_km", lambda s: round(100 * (s < 5).mean(), 1)),
                                con_coordenadas=("lat", lambda s: round(100 * s.notna().mean(), 1)), desde=("fecha", "min"), hasta=("fecha", "max"))
    print(r.to_string())
    print(c.groupby([c.fecha.dt.year, "fuente"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()

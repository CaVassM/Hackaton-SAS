"""Fase C: ficha de similitud y selección de donantes. NIVEL USADO: celda IMERG de 0.1° (para Chosica y para los donantes, con el MISMO método;
los donantes no tienen cuenca delimitada y la precisión de INDECI es de distrito). La forma de cuenca de las 17 quebradas (área, Melton, pendiente,
relieve; terreno/quebradas.csv, FABDEM) se documenta pero no entra a la comparación (otro nivel). Superficie (Sentinel-2, AlphaEarth): requiere
Earth Engine autenticado -> pendiente.

Variables de la ficha (fijadas antes de mirar donantes):
  clima  : lluvia anual media (mm), % en dic-abr, percentil 99 de la lluvia diaria (IMERG Early diario, día UTC). Para SELECCIONAR se usa 2001-2014
           (antes de toda temporada de prueba: sin información futura); 2001-2025 queda como columna descriptiva (sufijo _2001_2025).
  relieve: cota media, relieve (máx - mín) y pendiente media (grados) en la celda, con 6 x 6 puntos del DEM SRTM 90 m (OpenTopoData)
Referencia "Chosica": las 12 celdas del recorte IMERG original (lat -12.05..-11.85, lon -76.85..-76.55); centro = media de las 5 celdas de las quebradas.
Selección: distancia de Mahalanobis al centro de Chosica (covarianza de todas las celdas) y MESS (Elith et al. 2010) con la referencia de 12 celdas.
Se excluyen como donantes las celdas a < 0.15° de las 5 celdas de las quebradas (Lurigancho/Chaclacayo: serían las etiquetas de prueba).
Uso: python modelo/v3/C/ficha.py relieve   (solo DEM)  |  python modelo/v3/C/ficha.py   (todo; requiere el IMERG diario)
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
V3 = AQUI.parent
RAW = V3 / "datos" / "raw"
CEL_Q = [(-11.95, -76.85), (-11.95, -76.75), (-11.95, -76.65), (-11.85, -76.75), (-11.85, -76.65)]
REF = [(round(la, 2), round(lo, 2)) for la in (-12.05, -11.95, -11.85) for lo in (-76.85, -76.75, -76.65, -76.55)]
VARS = ["lluvia_anual", "pct_dic_abr", "p99_diario", "cota_media", "relieve", "pendiente"]


def celda(x):
    return np.round(np.floor(np.asarray(x) * 10) / 10 + 0.05, 2)


def celdas_candidatas():
    c = pd.read_csv(V3 / "D" / "catalogo_multizona.csv", parse_dates=["fecha"])
    c = c[c.lat.between(-30, -8) & c.lon.between(-81, -67)]
    c["clat"], c["clon"] = celda(c.lat), celda(c.lon)
    cel = pd.concat([c[["clat", "clon"]], pd.DataFrame(REF, columns=["clat", "clon"])]).drop_duplicates().reset_index(drop=True)
    return cel, c


def elevaciones(puntos):
    """DEM SRTM 90 m vía OpenTopoData (100 puntos por consulta, 1 consulta/s). Se usó en vez de la API de elevación de Open-Meteo porque esta
    agotó su límite horario (la descarga de ERA5 usó el cupo); TODAS las celdas usan el mismo DEM."""
    out = []
    for i in range(0, len(puntos), 100):
        lote = puntos[i:i + 100]
        url = "https://api.opentopodata.org/v1/srtm90m?locations=" + "|".join(f"{a:.4f},{b:.4f}" for a, b in lote)
        for k in range(10):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    out += [x["elevation"] if x["elevation"] is not None else 0.0 for x in json.loads(r.read())["results"]]
                break
            except Exception:  # noqa: BLE001
                time.sleep(10 * (k + 1))
        else:
            raise RuntimeError("elevación falló")
        time.sleep(1.1)
    return np.array(out, dtype=float)


def relieve(cel):
    ruta = AQUI / "relieve_celdas_srtm.csv"
    hechas = pd.read_csv(ruta) if ruta.exists() else pd.DataFrame(columns=["clat", "clon"])
    falta = cel.merge(hechas[["clat", "clon"]], how="left", indicator=True).query("_merge == 'left_only'")[["clat", "clon"]]
    paso = 0.1 / 6
    off = -0.05 + paso / 2 + paso * np.arange(6)
    filas = []
    for r in falta.itertuples():
        pts = [(r.clat + a, r.clon + b) for a in off for b in off]
        z = elevaciones(pts).reshape(6, 6)
        dy = paso * 111_000
        dx = paso * 111_000 * np.cos(np.radians(r.clat))
        gy, gx = np.gradient(z, dy, dx)
        filas.append(dict(clat=r.clat, clon=r.clon, cota_media=float(z.mean()), relieve=float(z.max() - z.min()),
                          pendiente=float(np.degrees(np.arctan(np.hypot(gx, gy))).mean()), frac_mar=float((z <= 0).mean())))
        if len(filas) % 25 == 0:
            pd.concat([hechas, pd.DataFrame(filas)]).to_csv(ruta, index=False)
            print(f"  relieve: {len(filas)}/{len(falta)}", flush=True)
    out = pd.concat([hechas, pd.DataFrame(filas)])
    out.to_csv(ruta, index=False)
    return out


def clima(cel):
    g = np.load(RAW / "imerg_diario" / "grilla.npz")
    lat, lon = np.round(g["lat"], 2), np.round(g["lon"], 2)
    ii = {v: i for i, v in enumerate(lat)}
    jj = {v: j for j, v in enumerate(lon)}
    idx = [(ii[a], jj[b]) for a, b in zip(cel.clat, cel.clon)]
    filas = {}
    for f in sorted((RAW / "imerg_diario" / "_cache").glob("*/*.npy")):
        d = pd.Timestamp(f.stem)
        if d.year < 2001 or d.year > 2025:
            continue
        x = np.load(f)
        filas[d] = [x[i, j] for i, j in idx]
    S = pd.DataFrame.from_dict(filas, orient="index").sort_index()
    S.columns = range(len(cel))
    out = cel.copy()
    for suf, (a, b) in (("", (2001, 2014)), ("_2001_2025", (2001, 2025))):   # sin sufijo = 2001-2014 (antes de toda temporada de prueba): es lo que se usa
        X = S[(S.index.year >= a) & (S.index.year <= b)]
        anual = X.groupby(X.index.year).sum(min_count=300).mean()
        w = X[X.index.month.isin([12, 1, 2, 3, 4])]
        wet = w.groupby(w.index.year).sum().mean()
        out["lluvia_anual" + suf] = anual.to_numpy()
        out["pct_dic_abr" + suf] = 100 * wet.to_numpy() / anual.to_numpy()
        out["p99_diario" + suf] = X.quantile(0.99).to_numpy()
    out["p99_2001_2014"] = out["p99_diario"]
    out["dias_imerg"] = len(S)
    return out


def mess(X, R):
    """MESS de Elith et al. (2010): para cada variable, similitud respecto a la distribución de referencia R; MESS = mínimo entre variables."""
    out = np.full(X.shape, np.nan)
    for k in range(X.shape[1]):
        r = np.sort(R[:, k])
        mn, mx = r.min(), r.max()
        rng_ = mx - mn if mx > mn else 1e-9
        for i, x in enumerate(X[:, k]):
            f = 100 * (r < x).mean()
            if f == 0:
                out[i, k] = 100 * (x - mn) / rng_
            elif f <= 50:
                out[i, k] = 2 * f
            elif f < 100:
                out[i, k] = 2 * (100 - f)
            else:
                out[i, k] = 100 * (mx - x) / rng_
    return out.min(axis=1), np.array(VARS)[np.argmin(out, axis=1)]


def main():
    cel, cat = celdas_candidatas()
    print(f"celdas candidatas: {len(cel)} (eventos del catálogo en el recuadro: {len(cat)})", flush=True)
    rel = relieve(cel)
    if len(sys.argv) > 1 and sys.argv[1] == "relieve":
        return
    f = clima(cel).merge(rel, on=["clat", "clon"])
    f = f[f.frac_mar < 0.5].reset_index(drop=True)      # celdas casi todo mar: fuera
    X = f[VARS].to_numpy(float)
    par = list(zip(f.clat.round(2), f.clon.round(2)))
    q = np.array([x in set(CEL_Q) for x in par])        # comparar PARES (lat, lon), no cada coordenada por separado
    ref = np.array([x in set(REF) for x in par])
    mu = X[q].mean(axis=0)
    Si = np.linalg.pinv(np.cov(X, rowvar=False))
    f["mahalanobis"] = np.sqrt(np.einsum("ij,jk,ik->i", X - mu, Si, X - mu))
    f["mess"], f["mess_var_limitante"] = mess(X, X[ref])
    dq = np.min([np.hypot(f.clat - a, f.clon - b) for a, b in CEL_Q], axis=0)
    f["es_chosica"] = dq < 0.15
    f.to_csv(AQUI / "ficha_celdas.csv", index=False)
    cat = cat.merge(f[["clat", "clon", "mahalanobis", "mess", "es_chosica"]], on=["clat", "clon"], how="left")
    cat.to_csv(AQUI / "catalogo_con_ficha.csv", index=False)
    d = cat[~cat.es_chosica.fillna(False) & cat.mahalanobis.notna()]
    filas = []
    for m in (1.5, 2, 3, 4, np.inf):
        for s in (0, -10, -25, -np.inf):
            x = d[(d.mahalanobis <= m) & (d.mess >= s)]
            filas.append(dict(mahalanobis_max=m, mess_min=s, eventos=len(x), celdas=x[["clat", "clon"]].drop_duplicates().shape[0],
                              dias_celda=x[["clat", "clon", "fecha"]].drop_duplicates().shape[0], fuentes=x.fuente.value_counts().to_dict()))
    r = pd.DataFrame(filas)
    r.to_csv(AQUI / "donantes_por_corte.csv", index=False)
    pd.set_option("display.width", 250)
    print("Chosica (5 celdas):\n" + f[q][["clat", "clon"] + VARS].round(1).to_string(index=False))
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()

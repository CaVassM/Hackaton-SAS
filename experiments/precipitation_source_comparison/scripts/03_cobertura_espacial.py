"""Cobertura espacial: ¿cuántas series de lluvia espacialmente distintas aporta cada producto para las 17 quebradas?

Usa los polígonos reales (terreno/quebradas.geojson, EPSG:4326) y la misma función de pesos del proyecto (lluvia/imerg_utils.calcular_pesos: intersección en UTM 18S).
Productos (todos con geometría de grilla, SIN descargar lluvia):
  IMERG Early   0.1°, centros en x.x5 (la grilla real ya usada, lluvia/pesos_imerg.csv)
  PERSIANN-CCS  0.04°, 3000 x 9000, 60N-60S, 0-360E; primer píxel (NW) centrado en 0.02E y 59.98N  [readmes diario y 6-horario de CHRS; el README horario no pudo consultarse: CONFIRMAR]
  PISCOp_h      0.1° (grilla del archivo local PISCOp_h_2015.nc, centros en x.x5), solo como contexto
  ERA5          0.25° (2 puntos del CSV local: -11.75/-76.75 y -12.0/-76.75), solo como contexto
Una celda más fina NO es información nueva por sí sola: el píxel nativo de PERSIANN-CCS (0.04°) viene del infrarrojo de satélites geoestacionarios y su resolución
efectiva depende de eso, no del tamaño del píxel. Aquí solo se cuenta cómo se reparten los polígonos sobre cada grilla.

Salidas en salida/: cobertura_espacial.csv, celdas_por_cuenca.csv, resumen_series.csv, mapa_cobertura.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lluvia"))
from imerg_utils import calcular_pesos, leer_quebradas  # noqa: E402

UMBRAL_EFECTIVO = 0.10   # una celda con menos del 10 % del área de la cuenca casi no mueve su serie: no cuenta como celda efectiva
SALIDA = AQUI / "salida"
SALIDA.mkdir(exist_ok=True)


def centros(res, ref, lo, hi):
    """Centros de celda de una grilla de paso `res` cuyos centros son ref + k*res, dentro de [lo - res, hi + res]."""
    k0, k1 = int(np.floor((lo - res - ref) / res)), int(np.ceil((hi + res - ref) / res))
    return np.round(ref + res * np.arange(k0, k1 + 1), 4)


def grillas(bbox):
    x0, y0, x1, y1 = bbox
    return {
        "IMERG": dict(res=0.1, lon=centros(0.1, 0.05, x0, x1), lat=centros(0.1, 0.05, y0, y1)),
        # PERSIANN-CCS: centros lon = 0.02 + 0.04 j (0-360E) = (… - 360) en lon negativa; lat = 59.98 - 0.04 i
        "PERSIANN-CCS": dict(res=0.04, lon=centros(0.04, 0.02 - 360, x0, x1), lat=centros(0.04, 59.98, y0, y1)),
        "PISCOp_h": dict(res=0.1, lon=centros(0.1, 0.05, x0, x1), lat=centros(0.1, 0.05, y0, y1)),
        "ERA5": dict(res=0.25, lon=np.array([-76.75]), lat=np.array([-12.0, -11.75])),
    }


def pesos_producto(q, g):
    p = calcular_pesos(q, g["lon"], g["lat"], res=g["res"])
    p["celda"] = p.lat_centro.round(4).astype(str) + "|" + p.lon_centro.round(4).astype(str)
    return p


def series_distintas(p):
    """Clave de la serie de cada quebrada = (celdas, pesos redondeados). Dos quebradas con la misma clave tienen EXACTAMENTE la misma lluvia estimada.
    `misma_celda_unica` = comparten una única celda con peso 1 (caso más fuerte); `mismas_celdas` = mismo conjunto de celdas aunque con pesos distintos."""
    claves, conj = {}, {}
    for q, g in p.groupby("quebrada_id"):
        g = g.sort_values("celda")
        claves[q] = tuple(zip(g.celda, g.peso.round(3)))
        conj[q] = tuple(g.celda)
    return claves, conj


def main():
    q = leer_quebradas()
    area = pd.read_csv(RAIZ / "terreno" / "quebradas.csv").set_index("quebrada_id").area_km2
    bbox = tuple(q.total_bounds)
    G = grillas(bbox)
    P = {k: pesos_producto(q, g) for k, g in G.items()}
    # chequeo contra el archivo de pesos del proyecto (IMERG)
    ref = pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
    m = P["IMERG"].merge(ref, on=["quebrada_id", "lat_centro", "lon_centro"], suffixes=("", "_ref"))
    assert len(m) == len(ref) == len(P["IMERG"]) and np.allclose(m.peso, m.peso_ref, atol=1e-6), "los pesos de IMERG no coinciden con lluvia/pesos_imerg.csv"

    filas, resumen, celdas = [], [], []
    clave, conj = {}, {}
    for k, p in P.items():
        clave[k], conj[k] = series_distintas(p)
        res_deg = G[k]["res"]
        lat0 = float(np.mean(bbox[1::2]))
        celda_km2 = (res_deg * 111.32 * np.cos(np.radians(lat0))) * (res_deg * 110.57)   # km², aprox. a la latitud de la zona
        cnt_clave = pd.Series(clave[k]).map(lambda t: hash(t)).value_counts()
        cnt_conj = pd.Series(conj[k]).map(lambda t: hash(t)).value_counts()
        resumen.append(dict(producto=k, resolucion_grados=res_deg, celda_km2=round(celda_km2, 1), celdas_que_tocan_alguna_cuenca=p.celda.nunique(),
                            series_distintas_exactas=len(cnt_clave), conjuntos_de_celdas_distintos=len(cnt_conj),
                            quebradas_con_celda_unica=int((p.groupby("quebrada_id").celda.nunique() == 1).sum()),
                            celdas_dominantes_distintas=int(p.loc[p.groupby("quebrada_id").peso.idxmax()].celda.nunique()),
                            quebradas_con_una_sola_celda_efectiva=int((p[p.peso >= UMBRAL_EFECTIVO].groupby("quebrada_id").celda.nunique() == 1).sum()),
                            area_cuenca_max_km2=round(float(area.max()), 2), cuencas_mas_chicas_que_una_celda=int((area < celda_km2).sum())))
        for r in p.itertuples():
            celdas.append(dict(producto=k, quebrada_id=r.quebrada_id, lat_centro=r.lat_centro, lon_centro=r.lon_centro,
                               area_km2_en_celda=round(r.area_km2_en_celda, 4), peso_cuenca_en_celda=round(r.peso, 4)))
    # tabla pedida: quebrada | área | celdas_IMERG | series_IMERG_compartidas | celdas_PERSIANN | series_PERSIANN_compartidas
    def comparte(k, qid, tipo):
        d = clave[k] if tipo == "exacta" else conj[k]
        return sorted(o for o in d if o != qid and d[o] == d[qid])
    for qid in q.quebrada_id:
        f = dict(quebrada=qid, area_km2=round(float(area[qid]), 3))
        for k, tag in (("IMERG", "IMERG"), ("PERSIANN-CCS", "PERSIANN")):
            f[f"celdas_{tag}"] = len(conj[k][qid])
            ex, mc = comparte(k, qid, "exacta"), comparte(k, qid, "conjunto")
            f[f"series_{tag}_compartidas"] = len(ex)
            f[f"series_{tag}_compartidas_con"] = "; ".join(ex)
            f[f"mismas_celdas_pesos_distintos_{tag}"] = "; ".join(o for o in mc if o not in ex)
            f[f"mayor_peso_{tag}"] = round(max(w for _, w in clave[k][qid]), 3)
            f[f"celdas_efectivas_{tag}"] = sum(w >= UMBRAL_EFECTIVO for _, w in clave[k][qid])
            dom = {o: max(clave[k][o], key=lambda t: t[1])[0] for o in clave[k]}
            f[f"celda_dominante_{tag}"] = dom[qid]
            f[f"comparten_celda_dominante_{tag}"] = sum(1 for o in dom if o != qid and dom[o] == dom[qid])
        f["cuenca_menor_que_celda_IMERG"] = bool(area[qid] < resumen[0]["celda_km2"])
        f["cuenca_menor_que_celda_PERSIANN"] = bool(area[qid] < resumen[1]["celda_km2"])
        filas.append(f)
    t = pd.DataFrame(filas).sort_values("area_km2")
    t.to_csv(SALIDA / "cobertura_espacial.csv", index=False)
    pd.DataFrame(celdas).to_csv(SALIDA / "celdas_por_cuenca.csv", index=False)
    r = pd.DataFrame(resumen)
    r.to_csv(SALIDA / "resumen_series.csv", index=False)
    pd.set_option("display.width", 250)
    print(r.to_string(index=False))
    print()
    print(t[["quebrada", "area_km2", "celdas_IMERG", "series_IMERG_compartidas", "comparten_celda_dominante_IMERG", "celdas_PERSIANN", "celdas_efectivas_PERSIANN", "series_PERSIANN_compartidas", "comparten_celda_dominante_PERSIANN", "mayor_peso_PERSIANN"]].to_string(index=False))
    mapa(q, G, bbox)


def mapa(q, G, bbox):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.5, 8), facecolor="#fcfcfb")
    x0, y0, x1, y1 = bbox
    pad = 0.06
    for k, col, lw in (("IMERG", "#2a78d6", 2.2), ("PERSIANN-CCS", "#eb6834", 0.7)):
        g = G[k]; h = g["res"] / 2
        for lo in g["lon"]:
            ax.plot([lo - h, lo - h], [y0 - pad, y1 + pad], color=col, lw=lw, alpha=.8)
        for la in g["lat"]:
            ax.plot([x0 - pad, x1 + pad], [la - h, la - h], color=col, lw=lw, alpha=.8)
    q.boundary.plot(ax=ax, color="#0b0b0b", lw=1.2)
    for _, r in q.iterrows():
        c = r.geometry.representative_point(); ax.annotate(r.quebrada_id, (c.x, c.y), fontsize=6, ha="center", color="#0b0b0b")
    ax.set_xlim(x0 - pad / 2, x1 + pad / 2); ax.set_ylim(y0 - pad / 2, y1 + pad / 2)
    ax.set_title("17 cuencas sobre la grilla de IMERG (azul, 0.1°) y de PERSIANN-CCS (naranja, 0.04°)", fontsize=10, loc="left")
    ax.set_xlabel("longitud"); ax.set_ylabel("latitud")
    fig.tight_layout(); fig.savefig(SALIDA / "mapa_cobertura.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()

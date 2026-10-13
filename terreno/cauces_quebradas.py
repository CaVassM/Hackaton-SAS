"""Cauce principal de cada una de las 17 quebradas: desde la cabecera de su cuenca hasta el río (Rímac o Santa Eulalia), siguiendo la dirección de flujo D8
de FABDEM (convención Whitebox). Si la salida es "apice", el trazo sigue más allá del punto de salida (cono de deyección) hasta el río.

  - Cabecera = celda de la cuenca con el MAYOR recorrido D8 hasta la salida (longest flow path, *longest flowpath*).
  - Trazo = desde la cabecera, celda a celda por D8, hasta la primera celda del cauce principal (Rímac + Santa Eulalia).
  - Río de llegada: se recalcula desde las dos cabeceras del cauce principal (la del este = Rímac, la del norte = Santa Eulalia): las celdas que solo
    se alcanzan desde la cabecera del Santa Eulalia son "Santa Eulalia"; las que se alcanzan desde la del Rímac (incluida la parte aguas abajo de la
    confluencia) son "Rímac". No se usa la codificación 1/2 de cauce_principal.tif tal cual.
  - largo_km = suma de pasos D8 (30 m ortogonal, 30·√2 m diagonal), cabecera -> río.
Entradas (carpeta del proyecto, fuera del repo): flow_direction_d8.tif, flow_accumulation_d8.tif, terreno/cauce_principal.tif (EPSG:32718, 30 m).
Salidas (terreno/ del repo): cauces_quebradas.geojson (EPSG:4326), cuencas_y_cauces.kml (Google Earth), cauces_quebradas.png (verificación).
"""
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from shapely.geometry import LineString, Point

AQUI = Path(__file__).resolve().parent
PROYECTO = AQUI.parents[2]                     # carpeta "Hackaton SAS" (rasters del terreno)
FDIR, FACC, CAUCE = PROYECTO / "flow_direction_d8.tif", PROYECTO / "flow_accumulation_d8.tif", PROYECTO / "terreno" / "cauce_principal.tif"
D8 = {1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0), 16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0)}   # Whitebox
MAX_PASOS = 20000


def red_d8():
    with rasterio.open(FDIR) as s:
        fdir, T, crs = s.read(1), s.transform, s.crs
    with rasterio.open(FACC) as s:
        acc = s.read(1)
        valido = acc != s.nodata
    with rasterio.open(CAUCE) as s:
        rio = s.read(1)
    R, C = fdir.shape
    abajo = np.full((R, C, 2), -1, dtype=np.int32)
    paso = np.zeros((R, C))
    for d, (dr, dc) in D8.items():
        rr, cc = np.where((fdir == d) & valido)
        r2, c2 = rr + dr, cc + dc
        ok = (r2 >= 0) & (r2 < R) & (c2 >= 0) & (c2 < C)
        ok[ok] &= valido[r2[ok], c2[ok]]
        abajo[rr[ok], cc[ok]] = np.stack([r2[ok], c2[ok]], axis=1)
        paso[rr[ok], cc[ok]] = 30 * np.sqrt(2) if dr and dc else 30.0
    return fdir, acc, valido, rio, abajo, paso, T, crs


def etiquetar_rios(rio, abajo):
    """Rímac / Santa Eulalia desde las cabeceras del cauce principal (celdas del cauce sin otra celda del cauce aguas arriba)."""
    principal = rio > 0
    tiene_arriba = np.zeros_like(principal)
    for r, c in zip(*np.where(principal)):
        r2, c2 = abajo[r, c]
        if r2 >= 0 and principal[r2, c2]:
            tiene_arriba[r2, c2] = True
    cabezas = list(zip(*np.where(principal & ~tiene_arriba)))
    assert len(cabezas) == 2, f"se esperaban 2 cabeceras del cauce principal, hay {len(cabezas)}"
    def traza(p):
        out = []
        while p[0] >= 0 and principal[p]:
            out.append(p)
            p = tuple(abajo[p])
        return out
    # cabecera del este = Rímac; del norte = Santa Eulalia
    cab_rimac = max(cabezas, key=lambda p: p[1])
    cab_se = [p for p in cabezas if p != cab_rimac][0]
    t_r, t_se = traza(cab_rimac), traza(cab_se)
    etiqueta = np.zeros(rio.shape, np.uint8)
    for p in t_se:
        etiqueta[p] = 2
    for p in t_r:
        etiqueta[p] = 1                    # el tramo compartido (aguas abajo de la confluencia) es Rímac
    confluencia = next(p for p in t_se if p in set(t_r))
    return etiqueta, confluencia, len(t_r), len(t_se)


def main():
    fdir, acc, valido, rio, abajo, paso, T, crs = red_d8()
    etiqueta, confl, n_r, n_se = etiquetar_rios(rio, abajo)
    reetiquetadas = int(((rio == 2) & (etiqueta == 1)).sum())
    print(f"Cauce principal: Rímac {n_r} celdas, Santa Eulalia {n_se}; confluencia en la fila/col {confl}; "
          f"celdas marcadas 2 en cauce_principal.tif que en realidad son Rímac (aguas abajo de la confluencia): {reetiquetadas}")
    q = gpd.read_file(AQUI / "quebradas.geojson").to_crs(crs)
    filas, lineas = [], []
    for r in q.itertuples():
        cuenca = rasterize([(r.geometry, 1)], out_shape=fdir.shape, transform=T, fill=0, dtype="uint8").astype(bool) & valido
        # recorrido D8 de cada celda hasta salir de la cuenca (memorizado)
        dist = np.full(fdir.shape, np.nan)
        for c0 in zip(*np.where(cuenca)):
            camino, p = [], c0
            while cuenca[p] and np.isnan(dist[p]):
                camino.append(p)
                n = tuple(abajo[p])
                if n[0] < 0:
                    break
                p = n
            base = 0.0 if (not cuenca[p] or n[0] < 0) else dist[p]
            if cuenca[p] and not np.isnan(dist[p]):
                base = dist[p]
            for c in reversed(camino):
                base = base + paso[c]
                dist[c] = base
        cab = np.unravel_index(np.nanargmax(dist), dist.shape)
        # trazo hasta el cauce principal
        pts, p, largo, largo_cuenca, k = [cab], cab, 0.0, 0.0, 0
        while etiqueta[p] == 0 and k < MAX_PASOS:
            n = tuple(abajo[p])
            if n[0] < 0:
                break
            largo += paso[p]
            if cuenca[p]:
                largo_cuenca += paso[p]
            p = n
            pts.append(p)
            k += 1
        llega = bool(etiqueta[p] > 0)
        xy = [rasterio.transform.xy(T, a, b) for a, b in pts]
        lineas.append(LineString(xy))
        filas.append(dict(quebrada_id=r.quebrada_id, nombre=r.nombre, largo_km=round(largo / 1000, 3), largo_en_cuenca_km=round(largo_cuenca / 1000, 3),
                          largo_tras_salida_km=round((largo - largo_cuenca) / 1000, 3), salida_tipo=r.salida_tipo,
                          rio_destino={1: "Rímac", 2: "Santa Eulalia"}.get(int(etiqueta[p]), "NO LLEGA"), llega_al_rio=llega,
                          cota_cabecera_acc=int(acc[cab]), acc_llegada=int(acc[pts[-2]]) if len(pts) > 1 else int(acc[cab])))
    g = gpd.GeoDataFrame(pd.DataFrame(filas), geometry=lineas, crs=crs)
    g = g.drop(columns=["cota_cabecera_acc"])
    g.to_crs(4326).to_file(AQUI / "cauces_quebradas.geojson", driver="GeoJSON")
    pd.set_option("display.width", 200)
    print(g.drop(columns="geometry").to_string(index=False))
    kml(q.to_crs(4326), g.to_crs(4326))
    mapa(q, g, etiqueta, T)


def kml(cuencas, cauces):
    def coords(geom):
        return " ".join(f"{x:.6f},{y:.6f},0" for x, y in geom.coords)
    def poligonos(geom):
        partes = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        out = []
        for pg in partes:
            inner = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{coords(i)}</coordinates></LinearRing></innerBoundaryIs>" for i in pg.interiors)
            out.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(pg.exterior)}</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>")
        return f"<MultiGeometry>{''.join(out)}</MultiGeometry>" if len(out) > 1 else out[0]
    pm_c = "".join(f"<Placemark><name>{escape(r.nombre)}</name><description>{escape(r.quebrada_id)} | área {r.area_km2:.2f} km² | salida: {escape(r.salida_tipo)}</description>"
                   f"<styleUrl>#cuenca</styleUrl>{poligonos(r.geometry)}</Placemark>" for r in cuencas.itertuples())
    pm_l = "".join(f"<Placemark><name>{escape(r.nombre)} (cauce)</name><description>{escape(r.quebrada_id)} | {r.largo_km:.2f} km hasta el {escape(r.rio_destino)}</description>"
                   f"<styleUrl>#cauce</styleUrl><LineString><tessellate>1</tessellate><coordinates>{coords(r.geometry)}</coordinates></LineString></Placemark>"
                   for r in cauces.itertuples())
    doc = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Quebradas piloto Chosica: cuencas y cauces</name>'
           '<Style id="cuenca"><LineStyle><color>ff00a5ff</color><width>2</width></LineStyle><PolyStyle><color>3300a5ff</color></PolyStyle></Style>'
           '<Style id="cauce"><LineStyle><color>ffff3300</color><width>3</width></LineStyle></Style>'
           f'<Folder><name>Cuencas (17)</name>{pm_c}</Folder><Folder><name>Cauces principales (17)</name>{pm_l}</Folder></Document></kml>')
    (AQUI / "cuencas_y_cauces.kml").write_text(doc, encoding="utf-8")


def mapa(q, g, etiqueta, T):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 7.5), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for val, col, et in ((1, "#2a78d6", "río Rímac"), (2, "#1baf7a", "río Santa Eulalia")):
        rr, cc = np.where(etiqueta == val)
        x, y = rasterio.transform.xy(T, rr, cc)
        ax.scatter(x, y, s=1.5, color=col, label=et, zorder=1)
    q.boundary.plot(ax=ax, color="#8f8d87", lw=0.8, zorder=2)
    g.plot(ax=ax, color="#eb6834", lw=1.6, zorder=3)
    fin = [Point(l.coords[-1]) for l in g.geometry]
    ax.scatter([p.x for p in fin], [p.y for p in fin], s=22, color="#0b0b0b", zorder=4, label="llegada al río")
    for r, l in zip(g.itertuples(), g.geometry):
        x0, y0 = l.coords[0]
        ax.annotate(r.quebrada_id, (x0, y0), fontsize=6.5, color="#52514e", xytext=(2, 2), textcoords="offset points")
    xmin, ymin, xmax, ymax = q.total_bounds
    ax.set_xlim(xmin - 1500, xmax + 1500)
    ax.set_ylim(ymin - 1500, ymax + 1500)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    ax.plot([], [], color="#eb6834", lw=1.6, label="cauce principal de la quebrada")
    ax.plot([], [], color="#8f8d87", lw=0.8, label="cuenca")
    ax.legend(frameon=False, fontsize=8.5, loc="lower left", markerscale=4)
    ax.set_title("Cauce principal de las 17 quebradas (D8 FABDEM) desde la cabecera hasta el río", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(AQUI / "cauces_quebradas.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()

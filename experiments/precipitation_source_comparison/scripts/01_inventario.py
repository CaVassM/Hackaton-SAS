"""Inventario de los archivos del proyecto relevantes para este experimento (solo lectura). Salida: inventario/inventario_archivos.csv"""
import subprocess
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
AQUI = Path(__file__).resolve().parents[1]
ITEMS = [
    # (ruta relativa o patrón, qué es, formato/proyección, nota)
    ("terreno/quebradas.geojson", "Polígonos de las 17 cuencas/quebradas (nombres en quebrada_id, nombre, alias)", "GeoJSON, EPSG:4326", "Los pesos se miden en UTM 18S (EPSG:32718); la lista de quebradas está en CLAUDE.md"),
    ("terreno/quebradas.csv", "Atributos de las 17 quebradas (área, pendiente, salida, etc.)", "CSV", ""),
    ("terreno/alias_catalogo.csv", "Nombre del catálogo -> quebrada_id", "CSV", ""),
    ("catalogo_huaicos_chosica/catalogo_huaicos_chosica.csv", "Inventario de huaicos (130 filas, 26 fechas, 2015-02 a 2026-02)", "CSV", ""),
    ("catalogo_huaicos_chosica/etiquetas_horarias_H*.parquet", "Etiquetas horarias por quebrada y horizonte", "Parquet", ""),
    ("lluvia/datos/early/imerg_early_*.nc", "IMERG Early V07 recortado (60 meses dic-abr, dic 2014 a abr 2026): tasa mm/h por 30 min, UTC", "NetCDF (var mm_h; time, lat, lon)", "Recorte = polígonos + 0.1° (12 celdas); ya descargado, no repetir"),
    ("lluvia/imerg_utils.py", "Lectura de gránulos, pesos por celda, conversión a mm/hora local", "Python", "calcular_pesos(), a_horario_local(), lluvia_por_quebrada()"),
    ("lluvia/descargar_masivo.py", "Descarga masiva y robusta de IMERG (Early o Final) con caché y reintentos", "Python", "--producto early|final"),
    ("lluvia/pesos_imerg.csv", "Pesos de las 17 quebradas sobre las 5 celdas IMERG que las tocan", "CSV", "Este experimento los reproduce y coinciden"),
    ("lluvia/features_lluvia.py", "Variables de lluvia del modelo (25) a partir de IMERG Early", "Python", "NO se modifica"),
    ("lluvia/lluvia_horaria_quebradas.parquet", "Lluvia horaria por quebrada (mm, hora local)", "Parquet", "Generado; no va a git"),
    ("imerg_data/*.HDF5", "IMERG Final V07B: 7 gránulos del 23/03/2015 (19:00-22:30 UTC)", "HDF5 (grupo Grid)", "Solo la prueba de Quirio"),
    ("lluvia/salida/comparar_early_final.csv", "Comparación mensual Early/Final/ERA5 (4 meses: 2019-02, 2021-02, 2023-03, 2024-02)", "CSV", "Los meses de Final no están en el repositorio (los bajó el usuario)"),
    ("PISCOp_h/PISCOp_h_2015.nc", "PISCOp_h (SENAMHI) horario, solo 2015", "NetCDF (var p: time 8760, lat 198, lon 133; 0.1°, centros x.x5)", "Desfase horario sin confirmar (+7 h probable)"),
    ("era5_data/era5_lluvia_chosica_*.csv", "ERA5 horario de 2 puntos (-11.75,-76.75) y (-12.0,-76.75); 2010-2012 y 2014-2026 (falta 2013)", "CSV (valid_time UTC = fin de hora, tp en m)", "Solo validación"),
    ("modelo/", "Modelo y resultados", "Python/CSV", "NO se modifica"),
]


def git_tracked(p):
    r = subprocess.run(["git", "ls-files", "--error-unmatch", p], cwd=RAIZ, capture_output=True)
    return r.returncode == 0


def main():
    filas = []
    for patron, que, fmt, nota in ITEMS:
        fs = sorted(RAIZ.glob(patron)) if any(c in patron for c in "*?") else [RAIZ / patron]
        fs = [f for f in fs if f.exists()]
        if f"{patron}".endswith("/"):
            fs = [RAIZ / patron]
        tam = sum(f.stat().st_size for f in fs if f.is_file()) if fs and fs[0].is_file() else sum(x.stat().st_size for f in fs for x in f.rglob("*") if x.is_file())
        filas.append(dict(ruta=patron, archivos=len(fs), tamano_mb=round(tam / 1e6, 1), que_es=que, formato=fmt, en_git=bool(fs) and git_tracked(str(fs[0].relative_to(RAIZ))), nota=nota))
    t = pd.DataFrame(filas)
    (AQUI / "inventario").mkdir(exist_ok=True)
    t.to_csv(AQUI / "inventario" / "inventario_archivos.csv", index=False)
    pd.set_option("display.width", 220, "display.max_colwidth", 70)
    print(t[["ruta", "archivos", "tamano_mb", "en_git"]].to_string(index=False))


if __name__ == "__main__":
    main()

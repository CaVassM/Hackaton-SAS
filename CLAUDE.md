# Proyecto: alerta temprana de huaicos — Lurigancho-Chosica (SAS Hackathon 2026)

## Contexto
- Equipo de Gerardo Salazar. Hackatón 1–31 oct 2026 (entornos SAS cierran a fin de octubre; video 2 nov).
- Camilo (yo) hace el **modelo predictivo**: probabilidad de huaico por quebrada, por hora y horizonte H (3, 6, 12, 24 h).
  Riesgo/exposición, dashboard, Telegram y RAG los hacen otros.
- Una fila del modelo = una quebrada en una hora. Etiqueta y_H = 1 si hay huaico en (t, t+H].
- Lluvia de entrada: IMERG Early (0.1°, 30 min, ~4 h de latencia). PISCOp_h y ERA5 solo para validar (no entran al modelo).

## Cómo trabajar conmigo
- Explica paso a paso, en español, con viñetas cortas. Define los términos técnicos antes de usarlos, pero usa su nombre formal (p. ej. *flow accumulation*, *pour point*).
- Nada de ejercicios de práctica: estamos resolviendo el problema.
- Ve de a una tarea; muestra resultados con pocos números clave y como mucho una imagen.

## Entorno
- Windows, VS Code. Python: entorno conda `base` (tiene whitebox, rasterio, geopandas, pypdf). `conda` no está en el PATH de la terminal: usa `C:\Users\Camil\anaconda3\python.exe` o el kernel `python3` (base) del notebook.
- WhiteboxTools: llama siempre `wbt.set_verbose_mode(False)` (los logs "Progress: x%" son enormes).
- No imprimas arrays ni rasters completos.
- Guarda las salidas nuevas del camino del terreno en la subcarpeta `terreno/`. No borres archivos existentes.

## Archivos existentes
- `fabdem_chosica.tif`: FABDEM original (EPSG:4326).
- `fabdem_chosica_utm18s.tif`: reproyectado a EPSG:32718, 30 m, NoData = -9999, 1097 x 930 px. Elevación 472–3874 m.
- `fabdem_chosica_hydro.tif`: el anterior con `breach_depressions`.
- `flow_direction_d8.tif` (D8 pointer, convención Whitebox) y `flow_accumulation_d8.tif` (en celdas; 1 celda = 900 m²).
- `streams_{100,500,1000,2500,5000,10000}.tif`: redes por umbral. 1000 celdas = 0.9 km².
- `revision_fabdem_chosica.ipynb`: notebook donde se hizo todo lo anterior.
- `catalogo_huaicos_chosica/`: catálogo de eventos (`catalogo_huaicos_chosica.csv`, 130 filas; 99 en Chosica, 30 nombres).
  La columna `quebrada` mezcla quebradas con barrios/sectores: **usa siempre `terreno/alias_catalogo.csv`** (nombre del catálogo → `quebrada_id`).
  - Etiquetas finales: `etiquetas_horarias_H{3,6,12,24}.parquet` (columnas hora, quebrada_id, H, y), generadas con `etiquetas_por_quebrada.py`.
  - `v0_por_nombre/etiquetas_horarias_H6.parquet` y `etiquetas_diarias.parquet` son la versión anterior por nombre (no usar).

## Decisiones tomadas
- DEM: FABDEM (sin edificios ni árboles), no Copernicus DSM. 30 m es suficiente.
- Preparación hidrológica: `breach_depressions` (no `fill`), D8.
- **El umbral de acumulación NO define las cuencas**: la cuenca depende solo de la dirección de flujo + el punto de salida (*pour point*). El umbral sirve para ver cauces candidatos y para ajustar (*snap*) los puntos de salida.
- La red de ANA y la lámina de SIGRID son **referencias**, no verdad absoluta. La lámina de SIGRID (PDF) se usa solo visualmente; no georreferenciar.
- Capa de ANA correcta: ALA **Chillón-Rímac-Lurín** (no Huallaga Central).

## Problemas conocidos
- Ríos grandes (Rímac, Santa Eulalia) vienen de fuera del recorte: su acumulación está truncada. No importa, pero **ninguna cuenca de quebrada debe tocar el borde del raster** (si toca, está incompleta: agrandar el recorte).
- Esquina inferior izquierda: líneas paralelas densas = zona plana/urbana, cauces poco confiables.

## Camino del terreno: TERMINADO (oct 2026)
Notebooks: `terreno/cuencas.ipynb` (fase 1), `terreno/referencia_validacion.ipynb` (fases 2–3), `terreno/quebradas_finales.ipynb` (fases 4–5 y cierre).

- **Red y cuencas:** `UMBRAL_CAUCE = 500` celdas (0.45 km²; mayor F1 contra ANA Estudios con buffer de 90 m). Cauce principal = Rímac + Santa Eulalia
  (corte 50 000 celdas + "drena a la salida del Rímac" + trazo D8 desde las entradas). 89 cuencas candidatas (`terreno/cuencas_candidatas.*`).
- **17 quebradas finales del piloto** → `terreno/quebradas.csv` / `.geojson` / `.kml`:
  quirio, santa_maria (incluye Yanacoto), california, la_cantuta, la_ronda, pedregal, carossio, corrales, chacrasana, santo_domingo,
  libertad, mariscal_castilla, rosario, el_vallecito, alto_peru, buenos_aires, huampani.
  - Ubicación: ANA (5), Cuadro Nº 04 de SIGRID 123 por km/margen/área/cota (Pedregal, Carossio, Corrales) y puntos a mano (`pendientes_ubicar.csv`).
  - Alias en `alias_catalogo.csv`: Inca Kola y Moyopampa → carossio; Tarazona y Nicolás de Piérola → quirio; Yanacoto → santa_maria;
    San Antonio de Pedregal → pedregal; Rayos de Sol → corrales.
  - `salida_tipo`: "confluencia" (10) o "apice" (7, punto a mano; la cuenca excluye el cono). Chacrasana y Santo Domingo usan la candidata
    (25, 36); sus cuencas de ápice están en `cuencas_apice_alternativas.geojson`.
  - `confianza_cuenca = "baja"` solo en huampani (snap de 206 m > 150 m). `cuenca_pequena` (< 0.3 km²): rosario, alto_peru, buenos_aires.
- **Excluidas:** Huaycoloro y Río Seco (cuenca grande fuera del recorte; trabajo futuro), Los Laureles (probable Chaclacayo),
  La Trinchera, Lechuceros y Los Molles (sin ubicación). En las etiquetas: Huaycoloro, Río Seco y Los Laureles se ignoran;
  las sin ubicar y los eventos sin nombre ponen NaN ese día en las 17 quebradas.
- **Variables de terreno de la v1:** `log10(area_km2)` (tamaño) y `pendiente_media` (grados).
  Correlación entre ambas: Pearson −0.69, Spearman −0.62 (criterio |r| ≤ 0.7). Melton queda fuera: r = −0.92 con log10(área) y depende de
  `salida_tipo` (ápice vs confluencia), lo que es un artefacto de la delimitación. `largo_cauce_km` es redundante con el área (r = 0.95).
- **Susceptibilidad INGEMMET: FUERA de la v1.** La capa vectorial regional satura (87–100 % de clase ≥ 4 en todas las cuencas); la imagen nacional
  de 200 m varía más pero tiene 3–30 píxeles en las cuencas pequeñas, y las dos capas casi no se correlacionan (r ≈ 0.1–0.3).
  Las columnas `vec_*` e `img_*` quedan en `quebradas.csv` para un experimento posterior.
- `dias_con_evento` / conteos de eventos: NUNCA como feature ni para elegir variables.
- Fuentes de referencia descargadas en `terreno/fuentes/` (ANA, INGEMMET, SIGRID 123, 1610, 19950, 6441, 14474); ver `fuentes.csv`.

## Fuentes útiles (SIGRID / CENEPRED)
- Mapa de Peligros Ciudad de Chosica (lámina de hidrografía): sigrid.cenepred.gob.pe/sigridv3/documento/123
- ANA, 7 puntos críticos Lurigancho-Chosica: sigrid.cenepred.gob.pe/sigridv3/documento/14474
- Evaluación de riesgo por flujo de detritos, CP Lurigancho: sigrid.cenepred.gob.pe/sigridv3/documento/6441
- Evaluación de riesgos, quebradas Carossio y Libertad: sigrid.cenepred.gob.pe/sigridv3/documento/1610
- Faja marginal de la quebrada Santo Domingo (R.D. ANA): sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca/19950_resolucion_directoral.pdf
- FABDEM: data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn (CC BY-NC-SA 4.0, citar)

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

## Camino de la lluvia (en curso, oct 2026)
- Scripts en `lluvia/`: `pesos_imerg.py` (-> `pesos_imerg.csv`), `imerg_utils.py`, `descargar_imerg.py` (prueba y `--inspect`),
  `prueba_23mar2015.py` (Early vs Final vs PISCOp_h vs ERA5), `descargar_masivo.py` (dic 2014 – abr 2026, un .nc por mes en `lluvia/datos/early/`, no va a git; caché por día en `_cache/`, reintentos, rondas y bitácora `descarga.log`; `--verificar` revisa los meses; un vigilante mata procesos sin avance en 20 min y aparta días que se cuelgan 3 veces).
- Las 17 quebradas tocan solo **5 celdas** IMERG (0.1°): quebradas con las mismas celdas comparten la serie de lluvia (el modelo las distingue por terreno).
- Recorte de descarga = polígonos + 0.1° (12 celdas). IMERG: tasa mm/h por media hora -> mm = valor x 0.5; hora etiquetada = inicio de la hora local (UTC-5).
- **Lectura remota:** con el bloque por defecto de fsspec (5 MB) se baja el gránulo ENTERO (7.5 MB; ~650 GB en total). Con `block_size=64 KB, cache_type="blockcache"` baja ~5 % (medido con gránulos reales). No quitar esa configuración.
- PISCOp_h: desfase de +7 h respecto a hora local (coherente con el ciclo diurno, no probado); su hora exacta es poco confiable (referencia gruesa). ERA5: solo validación (en 2015 sus 2 puntos dan 500–1400 mm/año vs 70 mm de PISCOp_h en la celda de Quirio: una celda y un año, escalas distintas; indicio, no conclusión).
- Prueba 23/03/2015: Early marca 0 mm a las 15:00 y 1.62 mm a las 16:00; el huaico fue 15:10. Comparado con Final solo en 3 h (Final: 0 / 0.79 / 1.96 mm a las 14/15/16 h): indicio de que Early llega ~1 h tarde y más débil, no concluyente. Con la latencia de 4 h, eventos así no se anticipan con lluvia reciente.
- Entorno Windows: el `dask` de `base` está dañado (`Invalid version: 'unknown'`): no usar `print(ds)` de xarray; si molesta, `python -m pip install --upgrade dask`.

## Camino del modelo (en curso, oct 2026)
- Decisiones: `lluvia_efectiva` con k = 0.84 por DÍA aplicado por hora (0.84**(1/24)); `anomalia_14d` queda FUERA de la v1 (columna en la tabla, no es feature; ver `FEATURES_V1` en `modelo/tabla3.py`).
- `lluvia/features_lluvia.py`: fila t usa lluvia con etiqueta <= t-5 (latencia 4 h). Ventanas incompletas = NaN. Prueba anti-futuro con `--prueba`.
- `modelo/diagnostico_senal.py`: QC (no selección de variables): a las 12:00 locales, con huaico vs sin huaico; medianas lluvia_24h 1.9 vs 0.24 mm, lluvia_14d 38 vs 17 mm; solo 15 fechas con huaico. Señal modesta y ruidosa.
- `modelo/tabla3.py` -> `modelo/tabla3_modelo.parquet` (no va a git): 2 882 561 filas; positivos H3/6/12/24 = 160/316/619/1219; 6 de 12 temporadas con eventos (2014-15 aporta 22 de 51 bloques de H=6).
- `modelo/auditoria.py`: 12 chequeos independientes (pesos, unidades y huso, features contra sumas directas, convención de etiquetas contra el catálogo, integridad de la tabla). Correr tras cualquier cambio en lluvia/ o modelo/.
- Aviso de diseño: log10(area) y pendiente identifican la quebrada (hay 17); con validación por temporada el modelo puede aprender la frecuencia histórica de cada quebrada. Es un a priori legítimo, no un conteo explícito, pero hay que tenerlo presente al interpretar.
- Resultados LOSO (6 temporadas con eventos; alertas 1 cada 100 h por quebrada; bloques detectados H=3/6/12/24 de 53/51/50/50): logística 2/2/4/5; logística+log1p (C=0.1) 3/3/4/10;
  XGBoost (H como columna, monótono en H) 2/2/3/4; Random Forest 1/3/3/5; `lluvia_efectiva` cruda sin modelo 4/4/4/7. Al azar se esperarían ~3/6/12/22 (optimista: las alertas reales se agrupan en tormentas).
  Ningún modelo supera con claridad al azar; con 2-10 bloques detectados las diferencias entre modelos son ruido. Hiperparámetros fijados de antemano, sin ajustar.
- AVISO DE METODOLOGÍA: `lluvia_efectiva` cruda tuvo AUPRC medio por temporada 3-6 veces mayor que cualquier modelo entrenado (0.006/0.014/0.021/0.027 vs 0.001-0.017). Era una de 4 referencias elegidas de antemano,
  pero es la mejor mirando los resultados: NO se puede declarar "la mejor variable" ni construir un modelo sobre ella sin validarla en datos nuevos o con selección DENTRO de cada pliegue (regla: no elegir variables mirando eventos).
  Los modelos entrenados (13 variables, ~15 fechas con huaico) probablemente sobreajustan; el límite de los datos y el sobreajuste no se pueden separar con la evidencia actual.
- `modelo/metricas.py` (métricas comunes), `modelo/baseline_logistica.py [base|log1p]`, `modelo/arboles.py xgb|rf`, `modelo/referencias_simples.py`, `modelo/comparar_modelos.py` (tabla y figura finales).
- Paso 5, ingeniería de variables (`lluvia/features_lluvia.py` TODAS = 25 de lluvia, `modelo/tabla3.py` FEATURES_V2 = 30; auditoría 14/14; `modelo/ingenieria*.py`, XGBoost con PARAMS_XGB fijos, LOSO):
  piso de ruido entre semillas ±0.3 de lift (V1 3.43, V2 3.45): AGREGAR las 17 variables nuevas NO mejora. Por grupo (agregar a V1 / quitar de V2, en lift): D regional (reg_max_24h, reg_max_3h_24h) +2.9 / -0.9, CONFIRMADO con 3 semillas
  (V1 3.4 -> V1+D 6.1; bloques 9 -> 26 de 204) y en logística (4.4 -> 5.1) y Random Forest (2.8 -> 3.6), pero la detección de bloques solo sube en XGBoost y sigue cerca del azar (~11 %); B humedad previa PERJUDICA (-1.0 / +2.3; el modelo se apoya
  en ella, permutación alta, y no generaliza entre temporadas: confiar en importancia != utilidad); E ciclo diario +0.5..0.8 dentro del ruido; A, C, F sin efecto claro. Selección interna top-10: 3.76, sin ganancia.
  CUIDADO: D y B se destacaron entre 6 grupos mirando las MISMAS 6 temporadas de prueba; la confirmación descarta suerte de semilla/modelo, no el efecto de selección. Validar con una temporada nueva o contra SILVIA.
  Variables sin efecto (permutación <= 0): lluvia_3h, lluvia_6h, int_max_24h, tendencia_3h, tendencia_24h, lluvia_14d, horas_desde_lluvia_fuerte (coherente con la latencia de 4 h). El ciclo diario (hora) es la única variable no basada en lluvia: pendiente de confirmar con Camilo.
- Paso 6, modelo restringido (`modelo/restringido.py`, `restringido_reporte.py`; XGBoost, variables V1 + D, 3 semillas por variante, parámetros fijados antes de correr): restricciones físicas de monotonía en la lluvia (+1; horas_desde_lluvia -1; H +1; sin restricción tendencia_3h y terreno)
  y árboles pequeños (profundidad 2, 150 árboles, min_child_weight 50). Lift medio / bloques detectados (N=100, de 204): V1 3.4 / 9; V1+D sin restricciones 6.1 / 26; solo monotonía 9.6 / 33; solo árboles pequeños 7.4 / 14; AMBAS (el pre-especificado) 10.0 ± 2.8 / 31.
  La MONOTONÍA es lo que pesa; los árboles pequeños no aportan de forma medible (AMBAS no se distingue de MONO). Brecha de sobreajuste: lift entrenamiento/prueba 1120/6.4 sin restricciones -> 56/13.2 con AMBAS (semilla 0).
  Por horizonte (AMBAS): detecta 14.5/13.7/14.7/18 % de los bloques (H=3/6/12/24) frente a un azar esperado de 3/6/12/22 %: mejora clara en H=3 y 6, ninguna en H=24. Muy desigual por temporada: lift 27 (2016-17), 12 (2018-19), 11 (2022-23), pero ~3 en 2014-15 (la de más eventos), 2019-20 y 2025-26.
  Salvedad vigente: el grupo D se eligió mirando las mismas 6 temporadas; falta validar con una temporada nueva o contra SILVIA.

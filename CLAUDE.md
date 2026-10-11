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
- Paso 7.1, diagnóstico por tormenta (`modelo/oof.py` -> `modelo/oof_restringido.parquet`, no va a git; `modelo/diagnostico_eventos.py`; modelo restringido AMBAS semilla 0, H=6): los 51 bloques son 14 tormentas (2014-15: 22 bloques pero solo 3 tormentas, varias quebradas por tormenta).
  El modelo SÍ pone las horas de huaico arriba (percentil mediano ~88 de la temporada) pero 1 alerta/100 h (top 1 %) solo cubre ~12 % de los bloques; 1/50 h 16 %, 1/20 h 33 %, 1/10 h 39 %, 1/5 h 67 % (20 % de las horas en alerta).
  CAUSAS: (a) IMERG no ve lluvia en la quebrada en las 6 h previas al huaico (<0.1 mm, incluso SIN retraso) en 32 de 51 bloques, y en 17 de 51 hay <1 mm en las 24 h previas: límite de la fuente; (b) de los 19 bloques con lluvia real en las 6 h previas, el modelo (retraso de 4 h) la veía en solo 4: efecto de la latencia.
- Paso 7.2, calibración, niveles y anticipación (`modelo/oof.py oof_todas()` -> `oof_restringido_todas.parquet`, 12 temporadas fuera de muestra; `modelo/umbrales.py`; salidas `modelo/salida/umbrales_*`):
  Calibración Platt por H con UNA recta global (2 parámetros): la versión anidada por temporada es inestable (al dejar fuera 2014-15 la pendiente sale 2.2 en vez de ~0.3) y mezclar rectas rompe el orden entre temporadas. Se impone p(H=3)<=p(H=6)<=p(H=12)<=p(H=24).
  Las probabilidades calibradas son MUY bajas (percentil 99: 0.1–0.5 %); el tramo alto del puntaje casi no discrimina (frecuencia observada plana entre tramos). Sirven para ordenar, no como probabilidad operativa.
  Niveles con UMBRAL FIJO entre temporadas (sin mirar etiquetas): amarillo 1 alerta/20 h, naranja 1/50 h, rojo 1/100 h por quebrada. Bloques detectados (de 53/51/50/50 en H=3/6/12/24): amarillo 6/9/6/8 (11–18 %), naranja 5/5/5/5 (~10 %), rojo 1/1/2/2 (2–4 %).
  Es MUCHO peor que el 12 % del paso 7.1, porque allá el 1/100 se aplicaba dentro de cada temporada (impracticable: exige conocer la temporada). Con umbral fijo el puntaje depende de la temporada: 2024-25 (sin eventos en el catálogo) concentra en H=6 el 51 % de las horas amarillas (18 367 de 36 098), el 83 % de las naranjas y el 88 % de las rojas (6 598 de 7 457);
  2014-15 (22 bloques) y 2018-19 no generan ninguna alerta. IMERG Early en 2024-25: 433 mm dic–abr (otras 106–299) y máx. 15 mm/h (otras ≤ 9): temporada muy lluviosa según el satélite sin huaicos catalogados (posible sobreestimación de IMERG o eventos sin registrar; sin verificar).
  Anticipación (tope = H por construcción): mediana 2.5 / 5.5 / 11.5 / 22 h al nivel amarillo (H=3/6/12/24), pero con 6–9 bloques por celda es indicativa, no una estimación.
  Falsos episodios por temporada: amarillo ~75–80, naranja ~30, rojo ~18 (cota pesimista: y=0 es "sin noticia"). Conclusión: no hay umbrales operativos defendibles con estos datos; los niveles solo valen como regla de priorización relativa DENTRO de una temporada/tormenta.
  VERIFICADO (`modelo/verificar_umbrales.py`): OOF íntegro (claves, y y temporada iguales a la tabla; una temporada re-entrenada da p idéntico, sin fuga); detección/anticipación recalculadas con otro código coinciden con el CSV. AZAR con el mismo reparto de horas de alerta por temporada (baraja dentro de cada temporada, 100 repeticiones), H=3/6/12/24: amarillo 2.7/6.0/8.6/16.3 detectados vs modelo 6/9/6/8 (≈ azar o peor); naranja 0.6/1.2/2.6/4.6 vs 5/5/5/5 (mejor en H=3-12, no en 24); rojo 0.2/0.4/0.8/1.5 vs 1/1/2/2 (ruido).
  El amarillo NO supera al azar con umbral fijo. La calibración Platt global usa las etiquetas de todas las temporadas (2 parámetros; no cambia el orden ni los cortes por cuantil). Con corte dentro de cada temporada esta misma tabla da 7–8 de ~51 bloques al 1/100 (~15 %), coherente con el 12 % del paso 7.1.
- Paso 8.1, techo sin latencia (`modelo/techo_sin_latencia.py` -> `modelo/salida/techo_sin_latencia.csv`; DIAGNÓSTICO, no modelo usable): mismo modelo restringido (V1+D, AMBAS, LOSO, 3 semillas) cambiando solo el retraso de la lluvia IMERG. Latencia 4 h (actual) / 2 h / 1 h / 0 h:
  bloques detectados N=100 de 204: 31 (15 %) / 33 / 37 / 38 (19 %); lift 10.0±2.8 / 8.8±1.9 / 7.6±0.4 / 7.7±0.1 (el lift BAJA porque 2016-17 cae de 27 a 11; las demás temporadas casi no cambian).
  CONCLUSIÓN: quitar TODA la latencia sube solo ~7 bloques (+4 pp). La latencia no es el cuello de botella con IMERG; lo es que IMERG no ve la lluvia en la quebrada en muchos huaicos (32/51 bloques sin lluvia <0.1 mm en las 6 h previas, incluso sin retraso).
  Una fuente más rápida con la MISMA información no ayudaría mucho; solo ayudaría una fuente que vea lluvia que IMERG no ve (pluviómetros, GOES, radar). Esto NO prueba que otra fuente la vea.
- Paso 8.2, ¿ERA5 ve los huaicos que IMERG no ve? (`modelo/diagnostico_era5_ciegos.py` -> `modelo/salida/diagnostico_era5_ciegos.csv`; ERA5 SOLO validación, no entra al modelo; 51 bloques de H=6 = 14 tormentas, no independientes):
  En las 6 h hasta el huaico, mediana del percentil de la lluvia frente a ventanas que terminan a la MISMA hora del día (control del ciclo diario): ERA5 92, IMERG 80; ERA5 >= p90 en 26/51 bloques, IMERG en 10/51 (azar ~5). A 24 h: ERA5 30/51, IMERG 13/51.
  El umbral de 0.1 mm NO sirve para comparar (ERA5 supera 0.1 mm en el 51 % de las ventanas de 6 h, IMERG en el 26 %). Correlación Spearman entre ambas fuentes en las 24 h previas por bloque: ~0.
  LECTURA: sí hay señal de lluvia en la fecha del huaico que IMERG Early pierde o subestima y ERA5 (reanálisis, 0.25°, solo 2 puntos, tiende a sobreestimar en la sierra) recoge mejor. ERA5 NO es usable (retraso de días). No prueba que ERA5 esté "bien": falta un pluviómetro.
  ALERTA de deriva: total dic-abr medio IMERG/ERA5 por temporada: 0.29 0.34 0.37 0.39 0.28 0.38 0.37 0.55 0.86 1.54 1.34 0.97 (2014-15 ... 2025-26). La razón sube de ~0.35 a ~1-1.5 desde 2021-22 (ERA5 baja a 158-344 mm y IMERG sube a 244-433 mm). Una de las dos fuentes no es estacionaria. RESUELTO en el paso 8.3: la deriva viene de ERA5, no de IMERG Early (4 meses de Final).
- Paso 9.1, auditoría de etiquetas (`modelo/auditoria_etiquetas.py` -> `modelo/salida/auditoria_etiquetas_fechas_catalogo.csv` y `auditoria_etiquetas_candidatos.csv`). DECISIÓN del usuario: seguir a nivel QUEBRADA (no "huaico en Chosica"); la comparación IMERG Final se descartó (no se descarga).
  (a) El catálogo tiene 26 fechas en 12 temporadas, sin ninguna en 2015-16, 2017-18, 2021-22 ni 2024-25; la cobertura es por prensa y muy desigual (2015, 2017 y 2023 concentran 19 de 26). Eso, más que una temporada "sin huaicos", puede ser temporada sin buscar.
  (b) 7 fechas tienen huaico SOLO en distritos vecinos (2017-01-15, 2017-01-21, 2020-01-29, 2021-03-07, 2023-02-17, 2023-03-17, 2024-02-08): en las 17 quebradas esos días quedan y=0 (0 positivos, 0 NaN) aunque llovió fuerte a pocos km (las mismas celdas IMERG). Son negativos dudosos; 2020-21 y 2023-24 quedan como temporadas "sin evento" por eso.
      PROPUESTA (no aplicada): poner y=NaN esos días en las 17 quebradas, igual que la regla de eventos sin ubicar. Pendiente de aprobación; cambia entrenamiento y evaluación (hay que re-correr tabla3, OOF y métricas).
  (c) 44 días con lluvia extrema en ERA5/IMERG (top 1.5 %) sin evento a ±1 día: son candidatos a eventos no registrados. Prensa (búsqueda web por fecha) NO confirmó ninguno: devuelve notas sin día claro. Pistas sin confirmar: 2025-02-11/14 (alerta roja del Rímac a 120.54 m3/s, 21 quebradas "en riesgo", IMERG 30.6 mm el 12/02, sin activación confirmada), marzo 2017 (varios huaicos; el catálogo solo tiene el 15/03),
      2019-02-27 (nota de Exitosa con maquinaria tras huaico en Chosica/Chaclacayo; el catálogo tiene el 25/02).
  (d) La lluvia sí ordena los días del catálogo: 3 de los 30 días más lluviosos de ERA5 tienen evento (10 %, base 1.4 %); 2 de 30 en IMERG.
  PRÓXIMO PASO para etiquetas: registro oficial por fecha (INDECI/COEN SINPAD, informes diarios COEN, alertas SENAMHI); no encontré descarga pública (CSV); hay que pedirlo a INDECI (oet@indeci.gob.pe) o revisar los resúmenes de emergencias del Congreso (PDF).
- Paso 8.3, ¿deriva IMERG Early? (`lluvia/comparar_early_final.py` -> `lluvia/salida/comparar_early_final.csv`; 4 meses de IMERG Final descargados por el usuario: 2019-02, 2021-02, 2023-03, 2024-02; los datos no van a git; tabla pegada por el usuario):
  Early/Final (total del mes, media de las 17 quebradas) = 2.29 / 0.76 / 2.22 / 2.34; en los 3 meses lluviosos Early da ~2.3 veces lo de Final y la razón NO crece con los años (2019 2.29, 2024 2.34). En 2021-02 (mes seco, ~20 mm) Early/Final = 0.76.
  Final/ERA5 = 0.14 / 0.27 / 0.37 / 0.65: sube porque ERA5 cae (235 -> 82 -> 141 -> 51 mm) mientras Final se mantiene (33 / 22 / 53 / 33 mm). Correlación diaria Early-Final 0.81-0.97 (mismo satélite); Final-ERA5 0.15-0.55.
  LECTURA: con 4 meses NO hay evidencia de deriva de Early respecto a Final; Early sobrestima de forma consistente (~2.3x en meses lluviosos), lo que un factor constante no rompe entre temporadas. La deriva de la razón IMERG/ERA5 se debe a ERA5 (o a clima que Final no ve): ERA5 no sirve como referencia de NIVEL; sus percentiles dentro de la misma hora (paso 8.2) no dependen de la escala.
  LÍMITES: solo meses de feb-mar, uno por temporada, y NO se revisó febrero 2025 (temporada 2024-25, la más lluviosa en Early: 433 mm, sin huaicos catalogados): sigue sin explicarse. Final tampoco es un pluviómetro (calibra con GPCC mensual, pocos pluviómetros en la sierra).
- Paso 9.2, etiquetas corregidas y re-corrida (`comun.py: poner_nan_dias_fuera_del_piloto`, aplicado en `tabla3.py`; `modelo/correr_rapido.sh`; resultados en `modelo/salida/ingenieria_nan/`; los anteriores quedan en `modelo/salida/ingenieria/` y `modelo/salida_antes_nan/`):
  REGLA: los y=0 cuya ventana (t, t+H] toca una de 10 fechas con huaico solo FUERA de las 17 quebradas (distritos vecinos o Huaycoloro/Río Seco: 2015-02-20, 2017-01-15, 2017-01-21, 2017-02-01, 2020-01-29, 2021-03-07, 2023-02-17, 2023-03-15, 2023-03-17, 2024-02-08) pasan a NaN; los y=1 se conservan. Tabla 3: 2 882 561 -> 2 861 040 filas; positivos y bloques sin cambio (160/316/619/1219; 53/51/50/50). Auditoría 14/14.
  Se re-corrió solo la versión rápida (V1, V1+D, restringido, OOF, niveles, diagnósticos). NO se re-corrieron las ablaciones de ingeniería (V2, grupos A-F), la confirmación con logística/RF, las referencias simples de los pasos 3-4 ni el techo sin latencia (8.1); sus cifras en este archivo son con las etiquetas anteriores. `bash modelo/correr_todo.sh` las repite (~2 h).
  RESULTADOS NUEVOS (LOSO, 6 temporadas con eventos, 3 semillas, N=100, de 204 bloques), lift medio / bloques detectados (antes -> ahora): V1 3.4/9 -> 8.9±3.0/21; V1+D 6.1/26 -> 10.9±2.3/26; solo monotonía 9.6/33 -> 19.6±1.7/39; solo árboles pequeños 7.4/14 -> 12.3±1.9/21; AMBAS 10.0±2.8/31 -> 18.7±0.5/39 (19 %).
  CUIDADO AL COMPARAR: el lift NO es comparable con el de antes. Quitar los negativos dudosos sube el AUPRC de forma mecánica: los días de huaico vecino eran de los negativos mejor puntuados (2016-17 pasa de lift 27 a 76 solo por eso). La mejora es de MEDICIÓN (etiquetas menos ruidosas), no del modelo. Lo más comparable son los bloques detectados.
  AMBAS por horizonte: 18.2 / 18.3 / 18.7 / 22.0 % de los bloques (H=3/6/12/24) frente a un azar esperado de 3 / 6 / 12 / 22 %: mejora clara en H=3 y 6, leve en H=12, ninguna en H=24. Brecha de sobreajuste (lift entrenamiento -> prueba): sin restricciones 1056 -> 8.7; AMBAS 55 -> 18.4. La monotonía sigue siendo lo que pesa; los árboles pequeños no aportan.
  NIVELES con umbral fijo (amarillo 1/20 h, naranja 1/50 h, rojo 1/100 h), detectados de 53/51/50/50 (H=3/6/12/24) y azar con el mismo reparto de alertas por temporada: amarillo 8/8/9/9 (azar 2.4/4.8/9.1/13.5: mejor en H=3-6, igual en H=12, PEOR en H=24); naranja 7/7/7/7 (azar 0.7/1.4/2.6/4.6: mejor en todos); rojo 2/2/4/3 (azar 0.1-0.6; pocos casos). Antes: amarillo 6/9/6/8, naranja 5/5/5/5, rojo 1/1/2/2.
  Sigue el problema de escala por temporada: 2024-25 (sin eventos catalogados) acapara el 49 % de las horas amarillas, el 74 % de las naranjas y el 87 % de las rojas (H=6). Con corte dentro de cada temporada: 10/9/9 bloques de 53/51/50 al 1/100 (~18 %). Anticipación mediana (amarillo) 2.5 / 5.5 / 11.5 / 23.5 h. Falsos episodios por temporada: amarillo ~75-79, naranja ~30, rojo ~16.
  Diagnóstico por tormenta (H=6): 9 de 51 bloques detectados al 1/100 en la temporada; percentil mediano del mejor puntaje por temporada 77-95; 23 de 51 huaicos con lluvia real en las 6 h previas (antes 19) y el modelo la vio en 7.
  Pendiente: re-correr correr_todo.sh completo, revisar la corrida `V2_sin_C` (lift 46, probable artefacto de una temporada con pocos eventos tras el cambio de etiquetas).

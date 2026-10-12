# v3 — Resumen por fase (alerta de huaicos, Lurigancho-Chosica)

Reglas: etiquetas v2; nada de información futura; estadísticas solo con datos de entrenamiento; ninguna credencial en código ni git.
Métrica común: **por evento de lluvia** (literatura), TSS = acierto (POD) − falsas alarmas (POFD), umbral que maximiza el TSS en las temporadas de
entrenamiento, validado dejando una temporada fuera (LOSO); IC 90 % por bootstrap de tormentas. Definiciones en `comun_v3.py`.

## Fase A — Medir como la literatura (`A/fase_a.py`)
- Eventos de lluvia IMERG Early en la zona (máximo de las 5 celdas; hora con >= 0.1 mm; separados por >= 6 h secas), dic-abr 2014-15..2025-26:
  **1 626 eventos**, **12 disparadores** (huaico de las 17 quebradas durante el evento o hasta 3 h después), 24 desconocidos (días con huaico sin hora
  o solo en vecinos), **1 día ciego** (23/01/2020: el huaico no toca ningún evento IMERG; cuenta como fallo).
- En los disparadores solo se usa lluvia/puntaje ANTERIOR al huaico (fin del rango v2; es una cota generosa).

| Método | TSS | IC 90 % | Acierto (POD) | Falsas alarmas (POFD) | % alertas en 2024-25 |
|---|---|---|---|---|---|
| ISAAC fijo (I = 1.57 D^-0.047), sin latencia | −0.13 | (−0.22, −0.05) | 0.08 (1/13) | 0.20 | 11 % |
| ISAAC fijo, latencia 4 h | −0.13 | (−0.22, −0.05) | 0.08 | 0.20 | 11 % |
| I-D calibrado (misma forma), sin latencia | 0.00 | (−0.26, 0.18) | 0.46 | 0.46 | 11 % |
| I-D calibrado, latencia 4 h | 0.25 | (−0.13, 0.54) | 0.38 | 0.13 | 5 % |
| Modelo actual (por quebrada, H=3) | 0.15 | (−0.23, 0.44) | 0.38 | 0.23 | 10 % |
| Dos piezas (P1, H=3) | 0.13 | (−0.23, 0.41) | 0.54 | 0.40 | 13 % |
| A2 solo intensidad (máx. 1/3/6 h) | 0.01 | (−0.30, 0.23) | 0.62 | 0.60 | 12 % |
| A2 + lluvia 24-72 h | 0.23 | (−0.14, 0.51) | 0.46 | 0.23 | 9 % |

- **Ningún método supera al azar con claridad** (todos los IC incluyen 0 salvo ISAAC, que es peor que el azar).
- Motivo: antes de los huaicos IMERG marca POCA lluvia. Puntaje I-D (máx. de I/D^-0.047) antes del huaico en los 12 disparadores: mediana ~0.75 mm/h,
  solo 2 superan 1.57; en los eventos SIN huaico la mediana es 0.54 y el percentil 90 es 2.8. El umbral de un pluviómetro (ISAAC) no se puede usar con
  IMERG: IMERG suaviza y no ve el golpe corto que dispara estos flujos (coherente con la ceguera de los pasos 7-8).
- Las diferencias entre métodos (12 disparadores, 13 unidades positivas) son ruido. "% alertas 2024-25" por evento es 5-13 % (2024-25 tiene 148 de
  1 626 eventos = 9 %): a nivel de evento 2024-25 NO domina (sí dominaba por horas, porque sus eventos son largos).

## Fase B1 — Estado y umbral variable (`B/fase_b1.py`, `B/ablacion_b1.py`)
Estado conocido en t: humedad del suelo 0-7 cm ERA5-Land (Open-Meteo, sin credenciales; con el retraso real de ~5 días, y variante ideal de 1 h),
días desde la última activación catalogada (fechas anteriores al día de t), ICEN (IGP/ENFEN; mes M-2 desde el día 10, M-3 antes).

| Método | TSS | IC 90 % | POD | POFD | % alertas 2024-25 | TSS sin 2016-17 y 2022-23 (6 positivos) |
|---|---|---|---|---|---|---|
| A2 + 24-72 h (base) | 0.23 | (−0.14, 0.51) | 0.46 | 0.23 | 9 % | 0.03 |
| **(a) A2 + estado (humedad 5 d, días desde activación, ICEN)** | **0.49** | **(0.15, 0.70)** | 0.69 | 0.20 | 14 % | **0.50** |
| (a) ídem con humedad ideal (1 h) | 0.49 | (0.24, 0.67) | 0.69 | 0.20 | 8 % | 0.66 |
| (b) A2 + 24-72 h, umbral por ICEN ≥ 0.4 | 0.06 | (−0.30, 0.34) | 0.46 | 0.40 | 17 % | −0.22 |
| (b) A2 + 24-72 h, umbral por humedad | 0.17 | (−0.19, 0.45) | 0.54 | 0.37 | 10 % | −0.02 |
| (b) I-D lat 4 h, umbral por ICEN | −0.24 | (−0.47, 0.04) | 0.38 | 0.63 | 13 % | −0.16 |
| (b) I-D lat 4 h, umbral por humedad | 0.43 | (0.27, 0.52) | 0.92 | 0.49 | 7 % | 0.35 |

- **Primer resultado con IC que excluye 0: estado como ENTRADA del modelo de intensidad (TSS 0.49), y no depende de los años de Niño costero** (0.50 sin ellos).
  Robusto a la semilla (`B/semillas_b1.py`): 0.49 / 0.48 / 0.47 con semillas 0/1/2 (mismos 9 aciertos de 13).
- Ablación (diagnóstico, no selección): cada variable sola da TSS 0.17-0.26; juntas 0.49. "Días desde la última activación" capta las RACHAS
  (4 de 12 disparadores ocurren <= 2 días después de otra activación; solo 5 % de los no disparadores <= 7 días): es información real y conocida en t,
  pero en parte refleja que la prensa cubre los episodios en serie. Con 13 unidades positivas el IC es ancho.
- El umbral por régimen de ICEN NO funciona (solo 3 de 12 disparadores ocurren con ICEN >= 0.4 publicado; el ICEN llega con 2-3 meses de retraso).
- El umbral por humedad sobre I-D (0.43) lo logra alertando la mitad de los eventos (POFD 0.49): poco útil.

## Fase D — Catálogo multizona (`D/catalogo_multizona.py` -> `D/catalogo_multizona.csv`, `D/catalogo_estado_fuentes.csv`)
| Fuente | Estado | Eventos | Con hora | Precisión < 5 km | Años |
|---|---|---|---|---|---|
| INDECI/SINPAD (HUAYCO; Lima Met., Lima Prov., Ica, Arequipa, Moquegua, Tacna) | ok (CSV local) | 911 | 0 % | 10 % (centroide del distrito) | 2003-2025 (433 en 2017) |
| INGEMMET PERU_ALERTA capa 4 (geocatmin; el servicio citado en geocatminapp ya no existe) | ok | 27 fechas (de 1 585 puntos, casi sin fecha de evento) | 0 % | 100 % | 1977-2025 |
| NASA GLC/COOLR (Perú y Chile; lluvia; sin sismo/nieve) | ok | 65 | 0 % (campo de hora vacío) | 11 % | 2007-2016 |
| SERNAGEOMIN (Remociones en masa Chile, REST) | NO responde desde esta red (timeout) | 0 | | | |
| Matus et al. 2026 (Zenodo) | 403 "tráfico inusual" | 0 | | | |
- Total 1 003 eventos (972 en el recuadro de IMERG diario lat -30..-8, lon -81..-67). Ninguno con hora: el modelo multizona tiene que ser DIARIO.
- El norte de Chile entra solo por COOLR. INDECI incluye eventos de Lurigancho/Chaclacayo: se excluyen como donantes (celdas a < 0.15° de las quebradas).

## Fase B2 — Ambiente atmosférico ERA5 (`B/fase_b2.py`)
- Open-Meteo (sin credenciales) da precipitación total, *showers* (≈ convectiva) y agua precipitable (TCWV) de ERA5 en 42 puntos 0.25°.
  **CAPE, índice K y Total Totals NO están en Open-Meteo**: requieren CDS (`.cdsapirc` del usuario) -> esa parte NO se hizo.
| Método | TSS | IC 90 % | POD | POFD | % alertas 2024-25 | TSS sin 2016-17/2022-23 |
|---|---|---|---|---|---|---|
| B1 (A2 + estado), misma corrida | 0.49 | (0.15, 0.70) | 0.69 | 0.20 | 14 % | 0.50 |
| B2 PASADO (≤ t; ERA5 real llega con ~5 días: tampoco operativo) | 0.49 | (0.15, 0.70) | 0.69 | 0.20 | 14 % | 0.49 |
| B2 TECHO "pronóstico perfecto" ((t, t+3 h]; NO desplegable) | 0.51 | (0.26, 0.69) | 0.69 | 0.19 | 13 % | 0.67 |
- ERA5 pasado no agrega nada; ni un pronóstico PERFECTO de ERA5 (0.25°) mejora con claridad -> no se cumplió la condición para comparar con
  Open-Meteo Historical Forecast (ECMWF IFS / GFS); no se hizo.
- Ceguera ERA5 en los 43 bloques v2 (H=6): 0/43 con < 0.1 mm en 6 h (IMERG 24/43). No es comparable: ERA5 supera 0.1 mm en ~51 % de las ventanas de
  6 h de dic-abr (llovizna permanente del modelo), así que "ver lluvia" en ERA5 casi no informa.

## Fase C — Ficha de similitud (`C/ficha.py` -> `C/ficha_celdas.csv`, `C/donantes_por_corte.csv`)
- NIVEL USADO: celda IMERG 0.1° (Chosica y donantes con el MISMO método; los donantes no tienen cuenca y INDECI es por distrito). Variables:
  lluvia anual, % dic-abr y percentil 99 diario (IMERG Early diario **2001-2014**, años previos a toda temporada de prueba; 2001-2025 solo descriptivo),
  cota media, relieve y pendiente media (DEM SRTM 90 m, OpenTopoData, 6 x 6 puntos por celda; la API de Open-Meteo agotó su cupo horario).
- NO HECHO: % suelo desnudo (Sentinel-2) y AlphaEarth (requieren Earth Engine autenticado: acción del usuario pendiente). La ficha de las 17 cuencas
  (área, Melton, pendiente, relieve con FABDEM) existe en `terreno/quebradas.csv` pero no se usa en la comparación (otro nivel).
- Chosica (5 celdas): lluvia anual 134-284 mm, 76-78 % en dic-abr, p99 diario 6-9 mm, cota 800-2 100 m, relieve 1 000-1 800 m.
- Donantes por corte (excluidas las celdas a < 0.15° de Chosica): MESS >= 0 -> 13 eventos (6 celdas); **principal Mahalanobis <= 3 y MESS >= -25 -> 96
  eventos, 23 celdas, 82 celda-días (todos INDECI: Lima Provincias 75, Arequipa 13, Lima Metropolitana 8; 62 de ellos en 2017)**; sin corte de MESS: 682-864.

## Fase E — Modelo DIARIO multizona (`E/fase_e.py`)
- IMERG Early DIARIO (GPM_3IMERGDE, día UTC) en TODAS las zonas, Chosica incluida (descarga por rangos; 9 249 días 2001-2026, 0 fallos).
  Variables: lluvia del día y de 3 días previos (cruda y relativa al p99 2001-2014). XGBoost restringido. Validación SOLO en Chosica, LOSO, sin filas de
  donantes de la temporada de prueba. Unidad de evaluación: zona-día (1 774 días, **18 con huaico, 10 tormentas**). Todos son modelos del MISMO día.

| Método (zona-día) | TSS | IC 90 % | POD | POFD | % alertas 2024-25 |
|---|---|---|---|---|---|
| E donantes, corte principal, relativa | 0.32 | (0.02, 0.60) | 0.61 | 0.29 | 17 % |
| E donantes, corte estricto (MESS ≥ 0) | 0.48 | (0.19, 0.74) | 0.61 | 0.14 | 24 % |
| E donantes, amplio (M ≤ 4) | 0.33 | (0.05, 0.56) | 0.67 | 0.34 | 17 % |
| E donantes, todos | 0.39 | (0.09, 0.63) | 0.61 | 0.22 | 16 % |
| E donantes, principal, cruda | 0.48 | (0.20, 0.71) | 0.61 | 0.13 | 25 % |
| E donantes, principal, ponderados por similitud | 0.48 | (0.18, 0.74) | 0.61 | 0.14 | 23 % |
| E solo Chosica, relativa | 0.44 | (0.12, 0.72) | 0.61 | 0.17 | 19 % |
| E solo Chosica, cruda | 0.42 | (0.11, 0.69) | 0.61 | 0.19 | 17 % |
| Ref.: ISAAC (lluvia horaria IMERG del día) | 0.23 | (0.04, 0.37) | 0.44 | 0.21 | 13 % |
| **Ref.: A2 + estado (B1), máximo horario del día** | **0.69** | **(0.53, 0.81)** | 0.89 | 0.20 | 14 % |
| Ref.: modelo actual por quebrada (máx. del día) | 0.22 | (−0.09, 0.53) | 0.50 | 0.28 | 20 % |
- **Los donantes NO mejoran con claridad** al modelo solo-Chosica (0.32-0.48 vs 0.42-0.44; todas aciertan los mismos 11 de 18 días y solo cambian las
  falsas alarmas). Los 96 donantes del corte principal son casi todos de 2017 y de la sierra de Lima Provincias (Sayán, Huamantanga), con hora desconocida
  y ubicación de distrito: aportan poco y con ruido. El corte estricto (13 eventos) da lo mismo que no tener donantes.
- A nivel día, el modelo horario con estado (B1) agregado al día es claramente el mejor (0.69). El modelo diario con solo IMERG diario pierde la intensidad.

## No completado (y por qué)
- B2: CAPE, índice K y Total Totals (no están en Open-Meteo; requieren `.cdsapirc` del CDS). Comparación con Open-Meteo Historical Forecast: no se cumplió
  la condición (el techo de ERA5 no supera con claridad).
- C1: % suelo desnudo (Sentinel-2) y AlphaEarth (requieren Earth Engine autenticado). Ficha a nivel celda, no cuenca, para los donantes.
- D2: SERNAGEOMIN no responde desde esta red; Zenodo (Matus et al.) responde 403. El norte de Chile entra solo por COOLR (y ninguno pasó el corte de similitud).
- F (opcional): no hecha. F1 requiere Earth Engine; F2 (datos USGS post-incendio) existe en ScienceBase pero quedó fuera por prioridad.

## Tabla final (`tabla_final.csv`; IC 90 % por bootstrap de tormentas)
Unidad EVENTO (A, B; 1 602 eventos, 13 unidades positivas) — alerta antes del huaico:
| Método | TSS (IC 90 %) | Acierto | Falsas alarmas | % alertas 2024-25 |
|---|---|---|---|---|
| Ref. ISAAC fijo (1.57 D^-0.047) sobre IMERG | −0.13 (−0.22, −0.05) | 0.08 | 0.20 | 11 % |
| Ref. modelo actual por quebrada | 0.15 (−0.23, 0.44) | 0.38 | 0.23 | 10 % |
| Ref. dos piezas (P1) | 0.13 (−0.23, 0.41) | 0.54 | 0.40 | 13 % |
| A1 I-D calibrado (lat 4 h) | 0.25 (−0.13, 0.54) | 0.38 | 0.13 | 5 % |
| A2 solo intensidad | 0.01 (−0.30, 0.23) | 0.62 | 0.60 | 12 % |
| A2 + 24-72 h | 0.23 (−0.14, 0.51) | 0.46 | 0.23 | 9 % |
| **B1 A2 + estado (humedad 5 d, días desde activación, ICEN)** | **0.49 (0.15, 0.70)** | 0.69 | 0.20 | 14 % |
| B1 umbral por humedad (I-D) | 0.43 (0.27, 0.52) | 0.92 | 0.49 | 7 % |
| B2 pasado (ERA5 precip., convectiva, TCWV) | 0.49 (0.15, 0.70) | 0.69 | 0.20 | 14 % |
| B2 techo, pronóstico perfecto (no desplegable) | 0.51 (0.26, 0.69) | 0.69 | 0.19 | 13 % |
Unidad ZONA-DÍA (E; 1 774 días, 18 con huaico, 10 tormentas) — modelos del mismo día:
| Método | TSS (IC 90 %) | Acierto | Falsas alarmas | % alertas 2024-25 |
|---|---|---|---|---|
| E diario con donantes (corte principal) | 0.32 (0.02, 0.60) | 0.61 | 0.29 | 17 % |
| E diario solo Chosica | 0.44 (0.12, 0.72) | 0.61 | 0.17 | 19 % |
| Ref. ISAAC diario | 0.23 (0.04, 0.37) | 0.44 | 0.21 | 13 % |
| Ref. modelo actual (máx. del día) | 0.22 (−0.09, 0.53) | 0.50 | 0.28 | 20 % |
| **B1 agregado al día** | **0.69 (0.53, 0.81)** | 0.89 | 0.20 | 14 % |

Donantes por fuente (corte principal): INDECI 96 (Lima Provincias 75, Arequipa 13, Lima Metropolitana 8); INGEMMET 0; COOLR 0; Chile 0.

## Recomendación (12/10/2026)
1. **Modelo final candidato: B1(a)** = XGBoost restringido en la ZONA con intensidad IMERG (máx. 1/3/6 h y sus máximos en 6 h, lluvia 24/48/72 h; latencia 4 h)
   + estado conocido en t (humedad del suelo ERA5-Land con 5 días de retraso, días desde la última activación catalogada, ICEN publicado).
   Es el único con IC que excluye 0 en ambas unidades (evento 0.49; día 0.69), estable entre semillas (0.47-0.49) y sin depender de los años de Niño
   costero (0.50 sin 2016-17/2022-23). El "dónde" lo sigue dando la pieza 2 (historia + terreno).
2. Cautelas: 13 unidades positivas (IC anchos); la ganancia viene de COMBINAR estado + intensidad, y "días desde la activación" capta rachas que en parte
   reflejan la cobertura de prensa. Operar requiere el catálogo de activaciones en tiempo real (INDECI/municipio) y ERA5-Land (o humedad equivalente).
3. NO usar: el umbral ISAAC sobre IMERG (peor que el azar: IMERG no ve el golpe corto), los umbrales por régimen de ICEN, ni los donantes actuales
   (no mejoran; catálogo sin hora y con precisión de distrito).
4. Lo que más podría cambiar el resultado sigue siendo la LLUVIA LOCAL: pluviómetros de SENAMHI/ISAAC (solicitud pendiente) para calibrar el umbral
   I-D con el dato correcto, y CAPE/K/TT del CDS para probar el ambiente convectivo.

## Verificaciones de B1(a) antes de congelar (`B/verificacion_b1.py` -> `verificacion_b1.csv`, `anticipacion_b1.csv`)
| Verificación | Positivos | TSS (IC 90 %) | POD (IC 90 %) | POFD |
|---|---|---|---|---|
| B1(a) completo (referencia) | 13 | 0.49 (0.15, 0.70) | 0.69 (0.33, 0.89) | 0.20 |
| a) SIN "días desde la última activación" (semillas 0/1/2) | 13 | 0.34 / 0.34 / 0.35 (≈0.00-0.01, 0.54) | 0.69 | 0.35 |
| b) solo PRIMEROS huaicos (sin activación en los 7 días previos; 5 excluidos) | 8 | 0.30 (0.04, 0.56) | 0.50 (0.25, 0.75) | 0.20 |
| c) persistencia trivial (activación en 2 días previos Y lluvia > mediana) | 13 | 0.07 (−0.01, 0.19) | 0.08 | 0.01 |
- B1 le gana con claridad a la persistencia trivial. Sin la variable de rachas el TSS baja a ~0.34 y el IC queda en el límite de 0 (LIMITACIÓN: la
  variable de rachas aporta ~0.15 de TSS bajando las falsas alarmas de 0.35 a 0.20). En primeros huaicos baja a 0.30 pero el IC sigue > 0.
- **Anticipación (9 aciertos)**, primera alerta del evento (latencia de 4 h incluida) hasta el huaico: contra el INICIO del rango del huaico mediana **2 h**
  (rango −4 a 29.5 h; >= 1 h: 6/9, >= 3 h: 3/9, >= 6 h: 1/9); contra el FIN del rango mediana 3 h (>= 1 h: 8/9, >= 3 h: 5/9, >= 6 h: 2/9).
  La racha continua de alerta empieza mucho antes (mediana 72 h): el estado mantiene la zona en alerta varios días (muchas horas de alerta).
- **Horizonte honesto para el dashboard: H = 3 h** ("riesgo en las próximas horas"); H = 6 solo como contexto; H = 12/24 = "condición de la zona"
  (estado), NO como anticipación de un huaico concreto.

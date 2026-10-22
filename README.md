# Alerta temprana de huaicos — Lurigancho-Chosica (SAS Hackathon 2026)

Modelo predictivo de riesgo de huaico, por quebrada y por hora, en las 17 quebradas piloto de Lurigancho-Chosica (Lima, Perú).
Este repositorio contiene el modelo predictivo. El dashboard, el bot de Telegram y el RAG los desarrolla otra parte del equipo.

## Modelo vigente: v3 (dos piezas)
- **P1, cuándo (zona):** probabilidad de que se active alguna de las 17 quebradas en las próximas H horas (H = 3, 6, 12 y 24 h).
  - Es un XGBoost con restricciones físicas de monotonía.
  - Variables:
    - intensidad de lluvia IMERG Early (máximos de 1, 3 y 6 h, y lluvia de 24 a 72 h), con 4 h de latencia;
    - humedad del suelo ERA5-Land de hace 5 días;
    - días desde la última activación catalogada;
    - último ICEN publicado.
- **P2, dónde (quebrada):** propensión de cada quebrada cuando hay tormenta. Combina su historia de activaciones con el terreno (área y pendiente).

**Validación:** fuera de muestra, por evento de lluvia y dejando una temporada fuera.

| Indicador | Valor |
|---|---|
| TSS | **0.49** (IC 90 % 0.15–0.70) |
| Acierto (POD) | 0.69 |
| Falsas alarmas (POFD) | 0.20 |
| Anticipación mediana | 2 h |

Con esa anticipación, **la única promesa honesta es H = 3 h**. Detalle completo en [modelo/v3/model_card_datos.md](modelo/v3/model_card_datos.md).

## Replicar el modelo
Todos los insumos de datos del modelo final están versionados en git, así que no hace falta descargar nada ni tener credenciales.
```bash
python -m pip install -r requirements.txt   # Python 3.13; versiones fijadas (xgboost==3.4.1 fija el resultado)
python replicar.py                          # ~2-5 min: etiquetas -> eventos -> B1 -> modelo final -> entrega; termina con "REPLICA OK"
```
Paso a paso, insumos, cómo volver a bajarlos y qué queda fuera: [REPLICAR.md](REPLICAR.md).

## Entrega al dashboard (nivel por defecto: el oficial, validado)
Script: `modelo/v3_1/entrega/entrega_dashboard.py`. Usa el modelo v3 **sin cambios** (`modelo/v3/final/`). Da el nivel oficial y, como opción, la variante `nivel_con_lluvia`.

```bash
# tabla operativa de una hora (17 quebradas x 4 horizontes)
python modelo/v3_1/entrega/entrega_dashboard.py hora "2023-03-14 13:00" --csv salida.csv
# temporada 2022-23 completa, FUERA DE MUESTRA (ejemplo para el dashboard)
python modelo/v3_1/entrega/entrega_dashboard.py ejemplo   # -> modelo/v3_1/entrega/ejemplo_2022_23_m3.csv
```

Columnas de salida:

| Columna | Qué es |
|---|---|
| `quebrada_id` | una de las 17 quebradas (`terreno/quebradas.csv`) |
| `hora` | hora local (UTC−5) de inicio en que se emite la predicción |
| `H` | horizonte en horas (3, 6, 12, 24) |
| `p_zona` | P1: probabilidad de huaico en la zona en (t, t+H] |
| `p2_quebrada` | P2: propensión de la quebrada (fija por quebrada) |
| `score` | `p_zona × p2_quebrada` (para ordenar) |
| `indice_0_100` | `100 × min(1, p_zona / umbral rojo) × p2 / max(p2)`; 100 = zona en umbral rojo y la quebrada más propensa |
| `lluvia_6h_mm` | lluvia IMERG de las últimas 6 h disponibles (máximo entre celdas) |
| `nivel` | **nivel por defecto (oficial, el validado)**: rojo si p_zona ≥ umbral rojo |
| `nivel_con_lluvia` | variante opcional: el rojo exige además lluvia en las últimas 6 h |

### Los dos niveles
El nivel se calcula para la **zona**, que es lo validado. Las quebradas comparten nivel y se ordenan por `score` o `indice_0_100`.

| | `nivel` (oficial, por defecto) | `nivel_con_lluvia` (variante opcional) |
|---|---|---|
| Rojo | p_zona ≥ umbral rojo | p_zona ≥ umbral rojo **y** lluvia IMERG > 0.1 mm en las últimas 6 h |
| Amarillo | umbral amarillo ≤ p_zona < umbral rojo | p_zona ≥ umbral rojo **sin** lluvia reciente ("condiciones favorables"), o umbral amarillo ≤ p_zona < umbral rojo |
| Verde | el resto | el resto |
| TSS del rojo (IC 90 %) | 0.49 (0.15–0.70) | 0.44 (0.16–0.63) |
| Acierto del rojo | 0.69 (9 de 13) | 0.62 (8 de 13) |
| Falsas alarmas del rojo | 0.20 | 0.17 |
| Horas en rojo (dic–abr) | 15.0 % | 11.4 % |

- **Por qué el oficial es el nivel por defecto:** es exactamente la regla validada (TSS 0.49). La condición de lluvia se agregó después (`modelo/v3_1/M3`).
- **Cuándo usar `nivel_con_lluvia`:** quita ~24 % de las horas en rojo a cambio de un acierto. El huaico que deja de estar en rojo pasa a amarillo, así que "rojo o amarillo" alerta los mismos huaicos en las dos columnas.
- **Umbrales:** están en `modelo/v3/final/metadatos_final.json`. El rojo maximiza el TSS por evento; el amarillo es el de máximo acierto alcanzable (0.85).
- **Cómo leer H = 6, 12 y 24:** describen la **condición de la zona**, no la anticipación de un huaico concreto.

## Paquete para el equipo y formato de simulación (entrega_modelo/)
`entrega_modelo/` es el modelo final v3 empaquetado para el equipo (detalle en [entrega_modelo/README.md](entrega_modelo/README.md)):

- **Insumos en CSV** (`inputs/`): lluvia IMERG por celda, humedad del suelo, ICEN, activaciones, terreno de las 17 quebradas, etiquetas de zona y eventos de lluvia.
- **Scripts `01`–`04`** (`scripts/`): características, entrenamiento, validación y predicción. **No dependen del repo**: solo leen `inputs/` y funcionan con la carpeta copiada sola.
- **Resultados de referencia** (`salidas/referencia/`): P2, umbrales y métricas del modelo final. `03_validar.py` los compara y debe terminar en `IGUAL (métricas, IC, umbrales y P2)`, con TSS 0.49 (IC 90 % 0.15–0.70).

Comandos, desde la raíz del repo (verificados; ~20 s en total):

```bash
python -m pip install -r entrega_modelo/requirements.txt
python entrega_modelo/scripts/01_features.py
python entrega_modelo/scripts/02_entrenar.py
python entrega_modelo/scripts/03_validar.py

# tabla de simulación de un mes FUERA DE MUESTRA (P1, umbrales y P2 sin esa temporada), por hora y por media hora
python entrega_modelo/scripts/04_predecir.py --mes 2023-03 --excluir-temporada 2022-23 --paso 30
# lo mismo con el modelo final (dentro de muestra para meses del histórico)
python entrega_modelo/scripts/04_predecir.py --mes 2026-03 --paso 30
```

- **Dónde quedan:** en `entrega_modelo/salidas/predicciones/`, por ejemplo:
  - `probabilidad_huayco_por_quebrada_con_tiempo_2023_03_sin_2022_23.csv` (por hora)
  - `..._30min.csv` (por media hora)
  - `detalle_zona_2023_03_sin_2022_23.csv`
- **Sin `--paso 30`** solo se genera la versión horaria.
- **En lugar de `--mes`** se puede pedir un rango: `--desde "2023-03-12 00:00" --hasta "2023-03-12 23:00"`.
- **Rutas largas en Windows:** la ruta completa de cada salida no debe pasar de 260 caracteres.

**Demo ya generada** (`entrega_modelo/salidas/demo/`): marzo 2017 y marzo 2023, fuera de muestra, con los archivos A, B y C. Se regenera con:

```bash
python entrega_modelo/scripts/predecir_demo.py --temporada 2022-23 --mes 2023-03 --paso 30
python entrega_modelo/scripts/predecir_demo.py --temporada 2016-17 --mes 2017-03 --paso 30
```

`predecir_demo.py` sí usa el repo (`modelo/v3/final/modelo_final.py`) y da los mismos archivos A y B que `04_predecir.py --excluir-temporada`, más el archivo C.

Los archivos son UTF-8 con BOM. `Tiempo` va en formato `d/mm/yyyy HH:MM`, en hora de Lima, y marca el inicio de la hora.

| Archivo | Columnas |
|---|---|
| **A** `probabilidad_huayco_por_quebrada_con_tiempo_<AAAA_MM>[_sin_<temporada>][_30min].csv` | `Tiempo, quebrada_id, quebrada, prob_ml_3h, prob_ml_6h, prob_ml_12h, prob_ml_24h`. Son 17 filas por hora, en orden fijo. La versión de 30 min repite el valor de su hora. |
| **B** `detalle_zona_<AAAA_MM>[_sin_<temporada>].csv` | `Tiempo, H, p_zona, umbral_rojo, umbral_amarillo, nivel, nivel_con_lluvia, lluvia_6h_mm`, con 4 filas por hora (una por H). `nivel` es el **oficial**: rojo si `p_zona ≥ umbral_rojo`, como en la validación. `nivel_con_lluvia` es la variante en la que el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h; si no la hay, queda en amarillo. |
| **C** `huaicos_registrados_<AAAA_MM>.csv` (solo la demo) | `fecha, hora_inicio, hora_fin, quebrada_id`: los huaicos del catálogo en las 17 quebradas. Las horas son el rango v2 y quedan vacías si la fuente no da hora. |

- **Qué es `prob_ml_Hh`:** `p_zona(H) × P2(quebrada)`, con 5 decimales.
  - Es un **puntaje de riesgo por quebrada, no una probabilidad calibrada**.
  - El nivel de alerta es de la **zona** y está en el archivo B.
- **Es el mismo dato que `entrega_dashboard.py`, en formato ancho:**
  - `prob_ml_Hh` = `score` de la fila (quebrada, hora, H).
  - `p_zona`, `nivel`, `nivel_con_lluvia` y `lluvia_6h_mm` del archivo B son los de cada (hora, H).
  - Comprobado con marzo 2023 de `ejemplo_2022_23_m3.csv`: los niveles y `p_zona` son idénticos. En el puntaje solo cambia el redondeo del quinto decimal, en 3 de 50 592 filas.

## Datos en operación (qué hay que actualizar cada hora)
| Variable | Fuente | Retraso |
|---|---|---|
| Lluvia (`i1h` … `p72h`, `lluvia_6h_mm`) | IMERG Early V07 (NASA GES DISC, cuenta Earthdata) | ~4 h |
| Humedad del suelo | ERA5-Land vía Open-Meteo archive API (sin credenciales) | ~5 días |
| ICEN | IGP/ENFEN, `met.igp.gob.pe/datos/ICEN.txt` | mensual (M−2 / M−3) |
| Días desde la última activación | registro de activaciones (catálogo; en operación, INDECI o municipio) | tiempo real (requerido) |

## Estructura
**Vigente (lo que forma el modelo final y la entrega):**

| Carpeta / archivo | Contenido |
|---|---|
| `replicar.py`, `REPLICAR.md`, `replicacion_referencia.json` | replicación del modelo final y su verificación |
| `terreno/` | cuencas de las 17 quebradas (FABDEM, D8): `quebradas.csv` / `.geojson` / `.kml`, cauces principales, alias del catálogo; `notebooks/` con la delimitación |
| `catalogo_huaicos_chosica/` | catálogo de huaicos (partes, constructor), etiquetas horarias v1 y v2 (horas vagas como rango) |
| `lluvia/` | descarga de IMERG Early (60 meses en `datos/early/`) y variables de lluvia |
| `modelo/v3/` | enfoque por evento: Fase A (eventos e intensidad), Fase B1 (estado), **modelo final** (`final/`), ficha del modelo, `RESUMEN.md` |
| `modelo/v3/datos/` | descargadores (Open-Meteo, ICEN, IMERG diario) e insumos versionados (`raw/openmeteo/era5_land.parquet`, `raw/icen/ICEN.txt`) |
| `modelo/v3_1/entrega/` | **entrega al dashboard** (nivel oficial por defecto; `nivel_con_lluvia` opcional) y ejemplo 2022-23 |
| `docs/` | diccionario de datos (.docx, generado con `docs/fuente_diccionario/gen.js`), informe de resultados |

**Histórico y exploratorio** (cada carpeta tiene su script y su resumen; no hace falta para replicar):

| Carpeta | Contenido |
|---|---|
| `modelo/` (raíz), `modelo/dos_piezas/`, `modelo/mejoras/`, `modelo/etiquetas_v2/` | modelos anteriores al v3: por quebrada (v1), dos piezas, mejoras R0–R3, re-corrida con etiquetas v2 |
| `modelo/v3/{B (B2), C, D, E, F}` | fases del v3 probadas y descartadas o diagnósticas: ERA5, ficha de similitud, catálogo multizona, modelo diario multizona, walk-forward |
| `modelo/v3_1/{M1, M3}` | mejoras pre-registradas (zona ampliada; nivel con lluvia reciente) |
| `experiments/` | comparación de fuentes de lluvia (PERSIANN-CCS) y solicitud de pluviómetros a SENAMHI (`precipitation_source_comparison/docs/`) |
| `imerg_data/`, `era5_data/`, `PISCOp_h/` | datos de las primeras pruebas de validación |

Los insumos que usa el modelo final están en git. Lo regenerable no se versiona: cachés y parquets intermedios (`modelo/v3/_cache/`, `lluvia/*.parquet`) y los datos de las fases exploratorias (`modelo/v3/datos/raw/`, salvo ERA5-Land e ICEN).
Las credenciales (`_netrc` de Earthdata, `.cdsapirc`) nunca van en el código ni en el repositorio.

## Limitaciones principales
- Solo hay **13 casos positivos** (10 tormentas): los intervalos de confianza son anchos.
- **IMERG no ve el golpe corto de lluvia** que dispara los huaicos en zona árida. El umbral de pluviómetro de ISAAC no funciona con IMERG (TSS −0.13).
- Parte de la señal viene de las **rachas**: días desde la última activación. Sin esa variable, el TSS baja a 0.34.
- La humedad del suelo es la variable que más aporta (sin ella, el TSS baja a 0.23), pero cuando el suelo pasa semanas saturado, como en El Niño costero 2017, el modelo queda en alerta casi continua (82 % de las horas de marzo de 2017).
- **Muchas horas en alerta.** Usarlo como **índice de prioridad**, no como alarma pública automática.
- **Lo que más lo mejoraría:** pluviómetros de SENAMHI/ISAAC (solicitud en `experiments/precipitation_source_comparison/docs/solicitud_senamhi.md`) y CAPE/K/TT de ERA5 (CDS).

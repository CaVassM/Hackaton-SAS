# Paquete del modelo final v3: alerta temprana de huaicos en Lurigancho-Chosica

Este paquete entrena, valida y usa el modelo final v3 para las 17 quebradas del piloto.

- **Es autónomo.** Los scripts `01` a `04` solo leen `inputs/` y no importan nada del repo.
- **Reproduce el repo bit a bit.** El OOF, el modelo, los umbrales, P2, la calibración, el TSS y su intervalo salen iguales a los de `modelo/v3/final/` (ver [Verificación](#verificación)).
- **Tarda unos 20 segundos** en total en un portátil, en Windows 11 con Python 3.13.9.

> **prob_ml_Hh = p_cal(t, H) × kappa_H × P2(q) es la probabilidad calibrada de que la quebrada se active en las próximas H horas. Es baja porque los huaicos son raros: para comunicar conviene usar `veces_lo_normal` y el nivel de alerta de la zona (archivo detalle_zona).**

## Modelo en una línea

Riesgo(quebrada, hora t, horizonte H) = **P1** × **P2**:

- **P1 = `p_zona(t, H)`**: un XGBoost estima si habrá un huaico en alguna de las 17 quebradas en (t, t+H]. Usa:
  - intensidad de lluvia IMERG Early;
  - el estado de la zona: humedad del suelo, días desde la última activación y El Niño costero (ICEN).
- **P2(quebrada)**: qué tan propensa es cada quebrada. Mezcla cuántas de las 10 tormentas la activaron con un a priori de terreno (área y pendiente).
- **El nivel (verde / amarillo / rojo) es de la ZONA.** Se compara `p_zona` con umbrales calibrados por evento de lluvia, que es lo validado.
  - P2 solo ordena las quebradas dentro de la zona.
  - No hay umbral validado por quebrada.
- **Probabilidad calibrada por quebrada** (sección 6): `p_zona` se calibra por H con Platt (`p_cal`) y se reparte entre las quebradas con `kappa_H × P2(q)`. P1, P2 y los umbrales no cambian.

## 1. Scripts, en orden

Todos se corren desde la raíz del repo: `python entrega_modelo/scripts/<script>.py`. Cada script indica en su encabezado qué función del repo reproduce.

| # | Script | Qué hace | Lee | Escribe | Tiempo |
|---|---|---|---|---|---|
| 1 | `01_features.py` | Arma la tabla de zona: una fila por hora × H (3, 6, 12, 24 h), con la etiqueta y las 12 variables + H. | `inputs/` | `salidas/trabajo/tabla_zona.parquet` | 1 s |
| 2 | `02_entrenar.py` | (a) Predicciones fuera de muestra LOSO (cada temporada la predice un modelo entrenado con las otras 11). (b) P1 final con las 12 temporadas. (c) Umbrales rojo y amarillo por H. (d) P2 por quebrada. (e) Calibración: Platt, `kappa` y tasa base por H. | `tabla_zona.parquet`, `inputs/` | `salidas/trabajo/oof.parquet`, `salidas/modelo/{p1.json, umbrales.csv, p2.csv, calibracion.json, calibracion_escala_final.csv, modelo.json}` | 12 s |
| 3 | `03_validar.py` | Validación por evento de lluvia (TSS, IC 90 %) y comparación con `salidas/referencia/`. | `oof.parquet`, `salidas/modelo/` | `salidas/metricas_validacion.csv` | 2 s |
| 4 | `04_predecir.py` | Predicción para un mes o un rango de horas en el formato del dashboard (archivos A, B y D). | `salidas/modelo/` (o `trabajo/` con `--excluir-temporada`) | `salidas/predicciones/` | 3 s |

Detalle de lo que hace cada paso:

- **Variables** (`01`): todas se conocen en la hora t.
  - **Intensidad**: `i1h, i3h, i6h` (lluvia de 1, 3 y 6 h) y `i1h_max6, i3h_max6, i6h_max6` (su máximo en las últimas 6 h).
    - `p24h, p48h, p72h` son la lluvia acumulada.
    - Se toma el máximo entre las 5 celdas IMERG que tocan las quebradas.
    - IMERG Early llega con ~4 h de retraso, así que en la hora t solo se usa lluvia con etiqueta ≤ t−5.
  - **Estado**:
    - `hum_suelo_5d`: humedad del suelo ERA5-Land de hace 5 días, que es su retraso real.
    - `dias_activ`: días desde la última activación catalogada, con tope 3650.
    - `icen`: último ICEN publicado (mes M−2 desde el día 10, M−3 antes).
- **P1** (`02`): XGBoost con hiperparámetros fijados antes de entrenar.
  - 150 árboles de profundidad 2, `learning_rate` 0.05, `subsample` y `colsample` 0.8, `min_child_weight` 50, `reg_lambda` 10, semilla 0.
  - `scale_pos_weight = √(negativos/positivos)`.
  - Monotonía +1 en todas las variables salvo `dias_activ`. Por eso p(3 h) ≤ p(6 h) ≤ p(12 h) ≤ p(24 h) siempre.
- **Umbrales** (`02`): se calibran por H con los puntajes fuera de muestra, evento por evento. El puntaje de un evento es el máximo de `p_zona` antes del huaico.
  - **Rojo** = umbral que maximiza el TSS.
  - **Amarillo** = umbral con POD ≥ 0.9. Es inalcanzable: hay un día ciego y un huaico sin horas útiles, así que el máximo es 11/13 = 0.85. Por eso se usa el umbral del **máximo POD posible**.
  - El modelo final puntúa en otra escala que los modelos LOSO, así que cada umbral se traslada **por cuantil**: queda la misma fracción de horas por encima.
- **P2** (`02`): P2 = (activaciones + 4 · p_terreno) / (10 tormentas + 4).
  - `p_terreno` es una logística (C = 1) con `log10(área)` y la pendiente media.
  - Una tormenta son las fechas con activación separadas por ≤ 2 días.
- **Calibración** (`02`, ver sección 6): Platt por H sobre las predicciones LOSO, `kappa_H` y tasa base. Para usarla con el modelo final, su `p_zona` se lleva antes a la escala LOSO por cuantil, igual que los umbrales.
- **Niveles de la zona** (`04`, archivo B). Hay dos columnas:
  - **`nivel` (oficial)**: es el que se validó (TSS 0.49).
    - **Rojo** si `p_zona ≥ umbral_rojo`, igual que en la validación.
    - **Amarillo** si `umbral_amarillo ≤ p_zona < umbral_rojo`.
    - **Verde** en el resto.
  - **`nivel_con_lluvia` (variante)**: igual que `nivel`, pero el rojo exige además lluvia IMERG > 0.1 mm en las últimas 6 h disponibles (`lluvia_6h_mm`). Si no la hay, queda en amarillo.
    - Tiene menos horas en rojo.
    - Cuesta un acierto: un huaico sin lluvia IMERG previa queda en amarillo (`modelo/v3_1/`).

### Funciones del repo

Los scripts `01`–`04` reproducen estas funciones del repo, pero no las importan:

| Script | Funciones reproducidas |
|---|---|
| `01` | `modelo/v3/final/modelo_final.py` `tabla_zona`, `modelo/v3/A/fase_a.py` `features_intensidad`, `modelo/v3/B/fase_b1.py` `estado_horario` |
| `02` | `fase_b1.py` `oof_estado`; `modelo_final.py` `ajustar`, `umbrales_oof` y `entrenar`; `modelo/dos_piezas/pieza2.py` `tormentas` y `p2`; `modelo/v3/final/calibracion.py` `ajustar` y `escala_final` |
| `03` | `modelo/v3/comun_v3.py` `mejor_umbral`, `tss`; `fase_a.py` y `fase_b1.py` evaluación LOSO y `bootstrap` |
| `04` | `modelo_final.py` `variables_horarias` y `tabla_operativa`; `calibracion.py` `p_calibrada`, `p_zona_kappa` y `a_escala_loso` |

Dos scripts **sí importan el repo** y necesitan el `requirements.txt` de la raíz:

- `00_exportar_inputs.py` (solo para quien mantiene el paquete): regenera `inputs/` y `salidas/referencia/` desde el repo. El equipo **no** necesita correrlo.
  - Usa `modelo/v3/comun_v3.py` (`lluvia_celdas`, `etiquetar`, `eventos_lluvia`, `lluvia_zona`, `huaicos_v2`) y `modelo/dos_piezas/base.py` (`etiquetas_zona`).
  - Lee también `modelo/v3/B/fase_b1_eventos.parquet`, `modelo/v3/final/{metadatos_final.json, p2_final.csv, calibracion.json, calibracion_escala_final.csv}` y `modelo/v3/datos/raw/` (ERA5-Land, ICEN).
- `predecir_demo.py`: la demo fuera de muestra (sección 4).
  - Usa `modelo/v3/final/modelo_final.py` (`tabla_zona`, `ajustar`, `umbrales_oof`, `p2_tabla`, `variables_horarias`), `modelo/v3/final/calibracion.py` (calibrador ajustado sin la temporada) y `modelo/v3/comun_v3.py` (`huaicos_v2`).
  - El formato de los archivos A, B y D lo toma de `_lib.py`.
  - Requiere los cachés `modelo/v3/_cache/oof_b1.parquet` y `modelo/v3/B/fase_b1_eventos.parquet`. Si faltan, primero `python replicar.py`.
  - Sus salidas son idénticas a `04_predecir.py --excluir-temporada`.

`_lib.py` contiene las funciones comunes de `01`–`04`.

## 2. Insumos (`inputs/`)

Todas las horas están en hora local de Lima (UTC−5) y marcan el **inicio** de la hora.

| Archivo | Filas | Contenido |
|---|---|---|
| `lluvia_horaria_celdas.csv` | 43 560 | Lluvia IMERG Early V07 (GPM_3IMERGHHE) en mm por hora para las 5 celdas de 0.1° que tocan las 17 cuencas (columnas `lat_lon` del centro). Solo dic–abr, de 30/11/2014 19:00 a 30/04/2026. |
| `humedad_suelo_horaria.csv` | 100 776 | Humedad del suelo 0–7 cm de ERA5-Land (m³/m³), media de las 5 celdas, de la API de archivo de Open-Meteo. 31/10/2014 → 30/04/2026. |
| `icen.csv` | 919 | ICEN mensual oficial (IGP/ENFEN, `met.igp.gob.pe/datos/ICEN.txt`): `anio, mes, icen`. 1950 → jul 2026. |
| `activaciones.csv` | 80 | Activaciones del catálogo en las 17 quebradas: `id, fecha, quebrada_id, hora_inicio, hora_fin` (rango horario v2), `con_hora, dudoso, fuente, url`. 16 fechas. Alimentan `dias_activ` y P2. |
| `quebradas_terreno.csv` | 17 | `quebrada_id, nombre, area_km2, log10_area_km2, pendiente_media` (grados), `salida_tipo, salida_lat, salida_lon`. Cuencas de FABDEM 30 m. Alimentan P2. |
| `etiquetas_zona.csv` | 171 264 | Etiqueta de zona `hora, H, y`: y = 1 si hay huaico en alguna quebrada en (t, t+H]; NaN si la hora es dudosa (rango vago que la ventana corta, o huaico solo en distritos vecinos). Etiquetas v2. |
| `eventos_lluvia.csv` | 1 603 | Unidad de la validación. Ver detalle abajo. |
| `quebradas_activadas_por_ventana.csv` | 584 | `hora, H, n_quebradas`: cuántas de las 17 quebradas se activaron en cada ventana (t, t+H] con huaico en la zona. Da `kappa` en la calibración. |

Detalle de `eventos_lluvia.csv`:

- **1 602 filas `evento`**: un evento es una racha de horas con ≥ 0.1 mm en la zona, separadas por ≥ 6 h secas.
  - Columnas: `inicio, fin, duracion_h, total_mm, max1/3/6`.
  - Un evento es disparador (`disparador`) si hubo huaico durante el evento o hasta 3 h después. `huaico_fin` y `tormenta` lo describen.
  - Hay 12 disparadores.
- **1 fila `dia_ciego`**: un huaico sin lluvia IMERG. Cuenta siempre como fallo.

Hay 3 575 filas con NaN en `etiquetas_zona.csv`; no entran al entrenamiento. Las variables tienen menos de 2 % de faltantes, y XGBoost los trata como faltantes.

## 3. Cómo correrlo

```bash
python -m pip install -r entrega_modelo/requirements.txt      # versiones exactas (xgboost 3.4.1 fija los resultados)
python entrega_modelo/scripts/01_features.py
python entrega_modelo/scripts/02_entrenar.py
python entrega_modelo/scripts/03_validar.py                   # debe terminar en "IGUAL (métricas, IC, umbrales, P2 y calibración)"

# predicción con el modelo final (archivos A, B y D en salidas/predicciones/)
python entrega_modelo/scripts/04_predecir.py --mes 2026-03
python entrega_modelo/scripts/04_predecir.py --desde "2026-03-01 00:00" --hasta "2026-03-02 23:00"
python entrega_modelo/scripts/04_predecir.py --mes 2026-03 --paso 30            # además la versión cada 30 min

# predicción FUERA DE MUESTRA (P1, umbrales, P2 y calibración sin esa temporada), como la demo
python entrega_modelo/scripts/04_predecir.py --mes 2023-03 --excluir-temporada 2022-23
```

Notas sobre la predicción:

- **Fechas del histórico con el modelo final:** quedan **dentro de muestra**, porque el modelo las vio al entrenar. Para mostrar cómo se comportaría el modelo, usa `--excluir-temporada`.
- **Fechas nuevas:** primero hay que agregar sus filas a `lluvia_horaria_celdas.csv` y `humedad_suelo_horaria.csv`, y a `icen.csv` si cae en un mes nuevo. Las activaciones también si hubo huaicos.
- **Datos faltantes:** si faltan datos para el periodo, `04` lo avisa.

## 4. Salidas para el dashboard

Formato de los archivos:

- UTF-8 con BOM, coma como separador y punto decimal.
- `Tiempo` = `d/mm/yyyy HH:MM`, hora de Lima, inicio de la hora.

| Archivo | Columnas |
|---|---|
| **A** `probabilidad_huayco_por_quebrada_con_tiempo_<AAAA_MM>.csv` | `Tiempo, quebrada_id, quebrada, prob_ml_3h, prob_ml_6h, prob_ml_12h, prob_ml_24h`. `prob_ml_Hh = p_cal(t, H) × kappa_H × P2(q)`, 5 decimales: probabilidad calibrada de que la quebrada se active en (t, t+H] (sección 6). 17 filas por hora, siempre en el mismo orden. La versión `_30min` repite el valor de su hora en :00 y :30. |
| **B** `detalle_zona_<AAAA_MM>.csv` | `Tiempo, H, p_zona, umbral_rojo, umbral_amarillo, nivel, nivel_con_lluvia, lluvia_6h_mm, p_zona_calibrada, veces_lo_normal`. 4 filas por hora (una por H). <br>`p_zona` es P1 sin calibrar, el que se compara con los umbrales. <br>`nivel` es el oficial (rojo si `p_zona ≥ umbral_rojo`) y `nivel_con_lluvia` la variante que exige lluvia en las últimas 6 h para el rojo (ver sección 1). <br>`p_zona_calibrada` = `p_cal`: probabilidad de un huaico en alguna de las 17 quebradas en (t, t+H]. <br>`veces_lo_normal` = `p_zona_calibrada` / tasa base del H. |
| **C** `huaicos_registrados_<AAAA_MM>.csv` (solo en la demo) | `fecha, hora_inicio, hora_fin, quebrada_id`. Catálogo con el rango horario v2; las horas quedan vacías si la fuente no da hora. Una quebrada puede aparecer dos veces el mismo día si el catálogo tiene dos registros (con y sin hora). |
| **D** `probabilidad_si_hay_evento.csv` | `quebrada_id, quebrada, P2, descripcion`: **probabilidad de que la quebrada se active si hay un temporal en la zona**. <br>En la demo es el P2 calculado sin 2022-23; el de la corrida sin 2016-17 es `probabilidad_si_hay_evento_sin_2016_17.csv`. <br>`04_predecir.py` escribe `probabilidad_si_hay_evento[_sin_<temporada>].csv`. |

Orden de las quebradas en el archivo A: Carossio, Corrales, Pedregal, California, La Ronda, Quirio, Santa María, Chacrasana, Libertad, Mariscal Castilla, Rosario, El Vallecito, La Cantuta, Santo Domingo, Alto Perú, Huampaní, Buenos Aires.

**Demo** (`salidas/demo/`, generada con `predecir_demo.py`): marzo 2017 (sin 2016-17) y marzo 2023 (sin 2022-23), fuera de muestra, con los archivos A (horario y 30 min), B, C y D.

Horas de cada color con H = 3 (744 h por mes):

| Mes | Columna | Rojo | Amarillo | Verde |
|---|---|---|---|---|
| Marzo 2017 | `nivel` (oficial) | 608 | 134 | 2 |
| Marzo 2017 | `nivel_con_lluvia` | 484 | 258 | 2 |
| Marzo 2023 | `nivel` (oficial) | 216 | 0 | 528 |
| Marzo 2023 | `nivel_con_lluvia` | 178 | 38 | 528 |

- **Marzo 2023 discrimina bien.** Con `nivel` no hay banda amarilla: calibrado sin 2022-23, el umbral amarillo coincide con el rojo (ver `modelo/v3/final/modelo_final.py`).
- **Marzo 2017 queda casi todo en alerta.** De los 12 marzos, es el de mayor lluvia de 72 h (mediana 11 mm) y suelo más húmedo (0.441), con una activación 16 días antes. Por eso el modelo que no vio 2016-17 lo puntúa alto casi todo el mes. Sirve para mostrar el caso, no como ejemplo de discriminación.

## 5. Resultados esperados

`03_validar.py` debe dar exactamente lo siguiente:

| | Valor |
|---|---|
| TSS por evento (LOSO, 12 temporadas) | **0.49**, IC 90 % **0.15–0.70** (bootstrap de tormentas, 2 000 repeticiones) |
| Huaicos anticipados | **9 de 13** (12 disparadores + 1 día ciego) |
| POD / POFD | 0.69 / **0.199** (316 falsas alarmas de 1 590 eventos sin huaico) |
| Umbrales del modelo final, rojo (H = 3 / 6 / 12 / 24) | 0.03180 / 0.03281 / 0.06622 / 0.10740 |
| Umbrales del modelo final, amarillo (H = 3 / 6 / 12 / 24) | 0.00554 / 0.00523 / 0.00915 / 0.01136 |
| Rojo sobre los puntajes fuera de muestra | TSS 0.56–0.57, POD 0.77, POFD 0.20 |
| P2 (máx. → mín.) | quirio 0.625, pedregal 0.554, santa_maria 0.539 … alto_peru 0.133, buenos_aires 0.130 |

| Calibración: `a` (H = 3 / 6 / 12 / 24) | −3.082 / −2.600 / −2.514 / −2.216 |
| Calibración: `b` (H = 3 / 6 / 12 / 24) | 1.058 / 1.006 / 0.912 / 0.879 |
| Calibración: `kappa` (H = 3 / 6 / 12 / 24) | 0.592 / 0.611 / 0.597 / 0.612 |
| Calibración: tasa base (H = 3 / 6 / 12 / 24) | 0.00076 / 0.00162 / 0.00377 / 0.00779 |

`salidas/referencia/` contiene las cifras del modelo final del repo (`p2.csv`, `umbrales.csv`, `metricas_validacion.csv`, `calibracion.json`, `calibracion_escala_final.csv`), y `03` las compara una por una.

Qué significan estas cifras:

- **TSS = POD − POFD**: acierto menos falsas alarmas; 0 es lo que da el azar.
- **El intervalo es ancho** porque hay solo 13 huaicos (12 disparadores + 1 día ciego) en 9 tormentas.
- **La anticipación mediana es de ~2 h** contra el inicio del huaico. Solo H = 3 es una promesa de anticipación; H = 6, 12 y 24 describen la condición de la zona.

## 6. Probabilidad calibrada por quebrada

**Fórmula** (`modelo/v3/final/calibracion.py`; P1, P2 y los umbrales no cambian):

> P(quebrada q se activa en (t, t+H]) = `p_cal(t, H) × kappa_H × P2(q)`

- **`p_cal(t, H)`** = `sigmoid(a_H + b_H · logit(p_zona))`: es la calibración de Platt.
  - Se ajusta por H con una logística (C = 1e6) sobre `logit(p_zona)` de las predicciones **fuera de muestra** y la etiqueta de zona (dic–abr). `p_zona` se recorta a [1e-6, 1 − 1e-6] antes del logit.
  - Es la probabilidad de un huaico en alguna de las 17 quebradas en (t, t+H].
- **`kappa_H`** = (quebradas activadas en promedio en las ventanas con huaico) / suma de P2.
  - Ese promedio es 3.4–3.5 quebradas y la suma de P2 es 5.70, así que `kappa` ≈ 0.6.

**Supuestos:**

- **La calibración de Platt corrige el peso de los positivos.** El modelo se entrena con `scale_pos_weight = √(neg/pos)`, que infla `p_zona`. Platt lo corrige con dos parámetros por H sin cambiar el orden de las horas.
- **`kappa` lleva P2 de la tormenta a la ventana.** P2 es la probabilidad de activarse en una tormenta, y `kappa` la escala para que la suma sobre las quebradas dé las quebradas esperadas dado un huaico en la zona.
- **Dado un huaico en la zona, qué quebradas se activan no depende de la lluvia de la hora.** Solo depende de P2. Por eso las dos piezas se multiplican.

**Cómo se aplica en cada caso:**

- **Demo y `--excluir-temporada`:** Platt, `kappa` y la tasa base se ajustan **sin** la temporada, igual que P1, P2 y los umbrales.
- **Modelo final:** su `p_zona` se lleva antes a la escala LOSO por cuantil, igual que los umbrales.
  - Hace falta porque, aplicado tal cual, sobrestima: suma 379 contra 326 positivos en H = 24.
- **Orden en H:** se toma el máximo acumulado en H para garantizar `p(3 h) ≤ … ≤ p(24 h)`. En 2016-17 y 2022-23 no corrigió ninguna hora.

**Validación** (`modelo/v3/final/calibracion_validacion.csv`): el calibrador se ajusta sin la temporada s y se aplica a s. Los tramos son cuantiles de `p_zona`. Para H = 3:

| Tramo de `p_zona` | Horas | Huaicos | `p_zona` media | `p_cal` media | Frecuencia observada |
|---|---|---|---|---|---|
| 0–50 % | 20 982 | 0 | 0.00085 | 0.00003 | 0.00000 |
| 50–80 % | 12 569 | 3 | 0.00686 | 0.00024 | 0.00024 |
| 80–90 % | 4 176 | 9 | 0.02860 | 0.00109 | 0.00216 |
| 90–95 % | 2 125 | 1 | 0.06718 | 0.00289 | 0.00047 |
| 95–99 % | 1 663 | 5 | 0.10458 | 0.00545 | 0.00301 |
| 99–100 % | 453 | 14 | 0.32289 | **0.03409** | **0.03091** |

| H | `p_cal` media en el 1 % más alto | Observado en el 1 % más alto | Suma de `p_cal` | Positivos |
|---|---|---|---|---|
| 3 | 0.034 | 0.031 | 38.7 | 32 |
| 6 | 0.059 | 0.051 | 78.6 | 68 |
| 12 | 0.113 | 0.110 | 175.3 | 158 |
| 24 | 0.183 | 0.216 | 342.7 | 326 |

- **Funciona donde importa, en el tramo alto.** Las sumas sobrestiman 5–21 %.
- **Por quebrada** (`calibracion_por_quebrada.csv`): la suma de `p_cal · kappa · P2(q)` da 131 frente a 108 horas con y_q = 1 en H = 3, y 1 197 frente a 1 138 en H = 24.
  - Quirio y Chacrasana quedan por debajo de lo observado.
  - Santa María, La Ronda y Alto Perú quedan por encima. Las dos últimas no tienen huaicos registrados; su P2 viene del a priori de terreno.

**Cómo comunicarlo.** Las probabilidades son **bajas porque los huaicos son raros**: hay un huaico en las 17 quebradas en 0.08 % de las ventanas de 3 h.

- El 14/03/2023 a las 12:00 (demo, H = 3), Quirio tiene 1.8 % de activarse en las próximas 3 h.
- Ese mismo valor es **63 veces lo normal** para la zona, y el nivel está en **rojo**.
- Para comunicar conviene usar `veces_lo_normal` y el nivel. `prob_ml_Hh` sirve para comparar quebradas y para cálculos de riesgo esperado.

## Verificación

Comprobado en este equipo (Windows 11, Python 3.13.9, xgboost 3.4.1), con corrida limpia:

- La tabla de zona del paquete es igual a `modelo_final.tabla_zona()` del repo: mismo orden, etiquetas y variables.
- Las predicciones LOSO son iguales a `modelo/v3/_cache/oof_b1.parquet` (diferencia máxima 0.0).
- `p1.json` predice igual que `modelo/v3/final/p1_b1.json` en las 171 264 filas (diferencia 0.0).
- Umbrales, P2, calibración (`a`, `b`, `kappa`, tasa base, rejilla del modelo final), TSS, IC y conteos coinciden con `salidas/referencia/`.
- `04_predecir.py --excluir-temporada` produce archivos A, B y D idénticos byte a byte a los de `predecir_demo.py`.
- La demo de marzo 2023 coincide con `modelo/v3/final/ejemplo_2022_23.csv`: 2 976 filas, diferencia 0. Por ejemplo, 12/03/2023 18:00, H = 3: `p_zona` = 0.02969.
- Cada archivo A horario tiene 12 648 filas (744 h × 17). En todas las filas, `prob_ml_3h ≤ 6h ≤ 12h ≤ 24h`, y en el archivo B `p_zona_calibrada` también crece con H.

Si se cambian los insumos, hay que leer los CSV con `float_precision="round_trip"`, como hace `_lib.py`. El lector rápido por defecto de pandas cambia la última cifra de algunos números, y eso basta para que XGBoost elija otros cortes: el TSS seguía en 0.49, pero los umbrales y una falsa alarma cambiaban.

## Límites

- **Pocos datos:** 13 huaicos evaluables en 9 tormentas y 12 temporadas.
- **Probabilidades calibradas con pocos casos:** `p_zona` no es una probabilidad; `p_zona_calibrada` y `prob_ml_Hh` sí, pero calibradas con 32–326 ventanas positivas por H y con el reparto por quebrada que da P2.
- **Escala por temporada:** el modelo pone mucha alerta en temporadas muy lluviosas según IMERG. 2024-25 no tiene huaicos catalogados.
- **El catálogo viene de prensa:** puede faltar algún huaico y las horas pueden ser vagas.
- Más detalle en `modelo/v3/model_card_datos.md` y `modelo/v3/RESUMEN.md` del repo.

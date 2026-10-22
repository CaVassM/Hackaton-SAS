# Informe de resultados — Modelo de alerta temprana de huaicos, Lurigancho-Chosica (12/10/2026)

## 1. Resumen ejecutivo
- **Qué hace el modelo:** probabilidad de huaico por quebrada, hora y horizonte H (3, 6, 12, 24 h). Una fila = una quebrada en una hora; y_H = 1 si hay huaico en (t, t+H]. Piloto: **17 quebradas**, solo diciembre–abril, 12 temporadas (dic 2014 – abr 2026).
- **Entrada de lluvia:** IMERG Early V07 (0.1°, 30 min, ~4 h de retraso). PISCOp_h, ERA5, IMERG Final y PERSIANN-CCS solo se usaron para validar.
- **Modelo final:** XGBoost con restricciones físicas de monotonía (más lluvia nunca baja el riesgo) y árboles pequeños; 15 variables (13 de lluvia + 2 de terreno) + H.
- **Veredicto:** sirve como **prioridad relativa** dentro de una tormenta o temporada (detecta ~19 % de los huaicos con 1 alerta cada 100 h, frente a ~10 % del azar; clara mejora en H=3 y 6 h, ninguna en 24 h). **No sirve todavía como alerta automática con niveles fijos** (amarillo/naranja/rojo): el amarillo no supera al azar de forma sostenida, hay muchos falsos episodios y las probabilidades calibradas salen muy bajas.
- **Cuello de botella = el dato, no el algoritmo:** solo ~15 fechas con huaico; IMERG marcó < 0.1 mm en la quebrada en las 6 h previas en **32 de 51** huaicos (incluso sin retraso). Quitar toda la latencia sube la detección solo ~4 puntos. PERSIANN-CCS tampoco recupera esa lluvia.
- **Lo que sí podría cambiar el resultado:** pluviómetros de SENAMHI (solicitud preparada, pendiente), para corrección de sesgo / fusión satélite–estación.

## 2. Datos
| Dato | Detalle |
|---|---|
| Quebradas | 17 (FABDEM 30 m, `breach_depressions`, D8); variables de terreno de la v1: log10(área) y pendiente media. Susceptibilidad INGEMMET, Melton y AlphaEarth fuera de la v1 (saturación / artefactos) |
| Catálogo de huaicos | 130 filas, **26 fechas** (feb 2015 – feb 2026); 99 filas de Chosica (19 fechas); 70 usables por hora en 16 fechas; 13 marcadas dudosas (25/02/2019). Cobertura muy despareja: 2015, 2017 y 2023 concentran 19 de 26 fechas; ninguna en 2015-16, 2017-18, 2021-22, 2024-25 |
| Etiquetas | 1 713 192 filas por H; horas con y=1: 160 / 316 / 619 / 1 219 (H=3/6/12/24); bloques (huaicos): 53 / 51 / 50 / 50. y=0 significa «sin noticia», no cero seguro. Solo **6 de 12 temporadas** tienen eventos (2014-15, 2016-17, 2018-19, 2019-20, 2022-23, 2025-26) |
| IMERG Early | 60 meses recortados; las 17 quebradas tocan solo **5 celdas** (quebradas con la misma celda comparten la lluvia). Fila t usa lluvia con etiqueta ≤ t−5. Prueba anti-futuro: 30 instantes × 25 variables, 0 fugas |
| Variables de lluvia | 25 calculadas; **13 entran al modelo** (lluvia 3/6/24 h, 7 y 14 d, intensidad máx. 24 h, tendencia 3 h, horas con lluvia, lluvia efectiva k=0.84/día, horas desde lluvia, lluvia de temporada, y 2 regionales); 12 probadas y descartadas |
| Tabla del modelo | **2 861 040 filas** (tras la corrección de etiquetas del paso 9.2; antes 2 882 561) |
| Otras fuentes (solo validación) | IMERG Final: 7 gránulos del 23/03/2015 + 4 meses (2019-02, 2021-02, 2023-03, 2024-02); PISCOp_h solo 2015; ERA5 2 puntos 0.25° (2010-2012, 2014-2026); PERSIANN-CCS: 63 días alrededor de los huaicos + 3 ventanas |
| Auditorías | `auditoria.py`: **14/14 chequeos** independientes (pesos, unidades, huso, variables contra sumas directas, etiquetas contra catálogo, integridad) |

## 3. Cómo se mide (todo con validación por temporada, nunca por filas)
- **LOSO:** entrenar con 11 temporadas y probar en la que queda fuera; se evalúa en las 6 con eventos.
- **Bloque detectado** = hubo al menos una alerta dentro de la racha de H horas con y=1. **Presupuesto de alertas:** «1 alerta cada N horas por quebrada».
- **Lift** = AUPRC ÷ lo que sacaría el azar. **Azar** esperado ~3 / 6 / 12 / 22 % (H=3/6/12/24), optimista porque las alertas reales se agrupan en tormentas.
- Ojo: con 2–40 bloques detectados, diferencias pequeñas entre modelos son ruido.

## 4. Resultados del modelo (cronológico)
**4.1 Modelos de referencia (etiquetas anteriores a 9.2; bloques detectados H=3/6/12/24 con 1 alerta/100 h):** logística 2/2/4/5; logística log1p 3/3/4/10; XGBoost 2/2/3/4; Random Forest 1/3/3/5; `lluvia_efectiva` cruda sin modelo 4/4/4/7. Ninguno supera claramente al azar (3/6/12/22). Aviso: `lluvia_efectiva` cruda tuvo el mejor AUPRC, pero se eligió mirando resultados: no se declara «la mejor variable».

**4.2 Ingeniería de variables (17 variables nuevas, 6 grupos):** agregar todas NO mejora (piso de ruido ±0.3 de lift). El grupo **regional (D)** ayudó (lift 3.4 → 6.1; bloques 9 → 26 de 204; confirmado con 3 semillas y en logística y RF); la **humedad previa (B) perjudicó**; ciclo diario y otros, sin efecto claro. Salvedad: D y B se destacaron mirando las mismas 6 temporadas de prueba.

**4.3 Modelo restringido (lift / bloques de 204):** V1 3.4/9; V1+D 6.1/26; solo monotonía 9.6/33; solo árboles pequeños 7.4/14; **ambas 10.0±2.8/31**. La **monotonía** es lo que pesa; reduce el sobreajuste (lift entrenamiento→prueba 1120/6.4 → 56/13.2).

**4.4 Diagnóstico por tormenta:** los 51 bloques son 14 tormentas (2014-15: 22 bloques pero 3 tormentas). El modelo pone las horas de huaico arriba (percentil mediano ~88 de la temporada). Causas del límite: (a) IMERG < 0.1 mm en 6 h en 32 de 51 bloques y < 1 mm en 24 h en 17 de 51; (b) de los 19 con lluvia real en las 6 h previas, el modelo (con retraso de 4 h) la veía en 4.

**4.5 Calibración y niveles de alerta:** Platt global por H (la versión anidada por temporada es inestable); probabilidades **muy bajas** (percentil 99: 0.1–0.5 %), sirven para ordenar, no como probabilidad operativa. Niveles con umbral fijo entre temporadas: amarillo 1 alerta/20 h, naranja 1/50 h, rojo 1/100 h.

**4.6 Techo sin latencia (diagnóstico):** retraso 4/2/1/0 h → bloques detectados 31/33/37/38 de 204 (15 → 19 %). La latencia no es el cuello de botella.

**4.7 ¿Ve ERA5 lo que IMERG no ve? (validación):** frente a ventanas de la misma hora del día, ERA5 pone la lluvia del huaico en el percentil 92 (IMERG 80); ERA5 ≥ p90 en 26/51 bloques (IMERG 10/51; azar ~5). ERA5 no es usable (llega con días de retraso, sobreestima en la sierra).

**4.8 Deriva entre fuentes:** la razón IMERG/ERA5 sube de ~0.35 a ~1–1.5 desde 2021-22. Con 4 meses de IMERG Final: Early/Final = 2.29 / 0.76 / 2.22 / 2.34 (estable, Early da ~2.3 veces lo de Final en meses lluviosos); Final/ERA5 = 0.14 / 0.27 / 0.37 / 0.65. **La deriva viene de ERA5, no de IMERG Early.** No se revisó feb 2025 (temporada 2024-25, muy lluviosa en Early y sin huaicos catalogados: sin explicar).

**4.9 Auditoría y corrección de etiquetas (paso 9):** 10 fechas con huaico solo fuera de las 17 quebradas (distritos vecinos o Huaycoloro) dejaban `y=0` dudosos en las 17 → pasan a «desconocido» (21 521 filas; positivos y bloques intactos). Además, 44 días de lluvia extrema sin evento registrado (candidatos; la búsqueda en prensa no confirmó ninguno).

## 5. Resultados vigentes (con las etiquetas corregidas; versión rápida, 3 semillas)
| Modelo | Lift | Bloques detectados (de 204) |
|---|---|---|
| Variables originales | 8.9 ± 3.0 | 21 |
| Originales + regional | 10.9 ± 2.3 | 26 |
| Solo monotonía | 19.6 ± 1.7 | 39 |
| Solo árboles pequeños | 12.3 ± 1.9 | 21 |
| **Modelo restringido (final)** | **18.7 ± 0.5** | **39 (19 %)** |

- **El lift NO es comparable con el anterior** (3.4 → 8.9 etc.): quitar los negativos dudosos sube el AUPRC mecánicamente (2016-17 pasó de 27 a 76 solo por eso). La mejora es de **medición**, no del modelo. Lo comparable son los bloques detectados (31 → 39).
- **Por horizonte (modelo final):** detecta 18.2 / 18.3 / 18.7 / 22.0 % frente a un azar de 3 / 6 / 12 / 22 %: mejora clara en H=3 y 6, leve en 12, **ninguna en 24**.
- **Niveles con umbral fijo** (detectados de 53/51/50/50 y azar con el mismo reparto de alertas por temporada): amarillo 8/8/9/9 (azar 2.4/4.8/9.1/13.5: mejor en 3–6 h, igual en 12, **peor en 24**); naranja 7/7/7/7 (azar 0.7/1.4/2.6/4.6: mejor en todos); rojo 2/2/4/3 (azar 0.1–0.6, pocos casos).
- **Problema de escala por temporada:** 2024-25 (sin eventos catalogados) acapara el 49 % de las horas amarillas, el 74 % de las naranjas y el 87 % de las rojas. Con corte dentro de cada temporada: 10/9/9 bloques de 53/51/50 al 1/100 (~18 %), pero eso exige conocer la temporada.
- **Anticipación mediana (amarillo):** 2.5 / 5.5 / 11.5 / 23.5 h (tope = H por construcción; indicativa, pocos casos). **Falsos episodios por temporada:** amarillo ~75–79, naranja ~30, rojo ~16 (cota pesimista: «sin huaico» = «sin noticia»).
- Pendiente: re-correr la cadena completa (ablaciones, logística/RF y techo sin latencia siguen con las etiquetas anteriores) y revisar una corrida con lift 46 (probable artefacto de una temporada con pocos eventos).

## 6. Experimento de fuentes de precipitación (sin tocar el modelo)
**Cobertura espacial (polígonos reales):**
| | IMERG Early (0.1°) | PERSIANN-CCS (0.04°) |
|---|---|---|
| Celdas que tocan alguna cuenca | 5 | 11 |
| Series exactamente distintas (de 17 quebradas) | 7 | 17 |
| Celdas dominantes distintas | 3 | 8 |
- IMERG: tres grupos con la misma serie exacta: 7 quebradas (rosario, buenos_aires, libertad, carossio, mariscal_castilla, corrales, la_ronda), 4 (santa_maria, chacrasana, el_vallecito, quirio) y 2 (alto_peru, huampani).
- Las 17 cuencas son menores que un píxel de ambos productos; 7 miden < 5 % de un píxel de PERSIANN-CCS. **Más series distintas no prueba más precisión.**

**PERSIANN-CCS horario (README leído y datos reales descargados en el PC del usuario):** int16 mm/h×100, subcarpetas por año, ~40 min de latencia observada, datos «realtime» reprocesados tras 2 días; ~1.94 MB por archivo (**84 GB** para dic–abr de 12 temporadas; no se descargaron). Zona horaria verificada: **UTC, inicio de hora**.
**¿Recupera los huaicos «ciegos» de IMERG?** No: de los 32 bloques ciegos, PERSIANN-CCS ve ≥ 0.1 mm en 6 h solo en **1** (ve ≥ 1 mm en 24 h en 13). En 6 h ≥ 0.1 mm: PERSIANN 10/51 vs IMERG 19/51; combinados 20/51. Correlación 24 h entre productos 0.78. Quirio 23/03/2015: ambos marcan 0 mm a las 20 UTC (huaico a las 20:10 UTC) y ven lluvia una hora después. Límites: 14 tormentas, sin pluviómetros, sin temporada completa.

**SENAMHI / pluviómetros (fuentes públicas; el entorno bloqueaba senamhi.gob.pe, nada verificado en las páginas oficiales):** ISAAC = «Plataforma Espacial de Monitoreo de Lluvias Intensas en la Región Lima frente a la Activación de Quebradas» (14 pluviómetros en tiempo real según una nota del MINAM). Ninguna de las 9 estaciones nombradas (Carosio, Castilla, Libertad, Pedregal Koica, La Cantuta, Río Seco, Quebrada Molle, Los Cóndores, Vizcachera) apareció por nombre en fuentes públicas. El portal público da series **diarias**; lo horario de estaciones automáticas es por solicitud (TUSNE S/ 348.45 por año/variable/estación en 2021 y un extracto de 2024; vía gratuita para estudiantes/investigadores según una directiva, ~15 días hábiles; ambos sin confirmar vigencia). Solicitud lista en `docs/solicitud_senamhi.md`.

## 7. Verificaciones y pruebas realizadas
- Auditoría 14/14; prueba anti-futuro sin fugas; OOF íntegro (una temporada re-entrenada da predicciones idénticas); detecciones recalculadas con otro código coinciden; comparación contra azar con el mismo reparto de alertas por temporada (100 repeticiones).
- Pruebas **sintéticas** (validan código, no datos): decodificador y recorte de PERSIANN-CCS en 3 formatos (9/9 píxeles correctos, incluida la estructura real con prefijo distinto en el año 2000), lectura del README real, índice no reconocido → diagnóstico.
- Descargas **reales**: IMERG Early 60 meses; IMERG Final 4 meses; PERSIANN-CCS (en el PC del usuario).
- Literatura consultada: IMERG Early en los Andes peruanos tiene correlación media 0.34 a escala diaria contra 35 pluviómetros (Mantas & Caro, EGU 2023); NASA LHASA usa IMERG para deslizamientos y mejora modelando el error de la lluvia satelital; GOES-16 + IMERG con random forest mejora en Ecuador. No se encontró ningún trabajo con IMERG para huaicos en Chosica.

## 8. Limitaciones y advertencias metodológicas
- ~15 fechas con huaico, 14 tormentas, 6 temporadas de prueba: los intervalos son anchos y los bloques no son independientes.
- El grupo regional y la monotonía se identificaron mirando las **mismas** 6 temporadas de prueba: falta validar con una temporada nueva (2026-27) o contra SILVIA.
- log10(área) y pendiente identifican cada quebrada: el modelo puede aprender la frecuencia histórica de cada una (a priori legítimo, hay que tenerlo presente).
- `y = 0` es «sin noticia»: falsas alarmas y precisión son cotas pesimistas. El catálogo es por prensa y está incompleto.
- Early sobrestima ~2.3 veces respecto a Final (constante entre años, no rompe el modelo) y no ve la lluvia local de muchos huaicos.
- Pasar de archivo reprocesado a «tiempo real» (IMERG y PERSIANN-CCS) puede cambiar los valores: antes de entrenar con uno hay que compararlos.

## 9. Pendientes y recomendaciones
1. **Enviar la solicitud de pluviómetros a SENAMHI**; si llegan, corrección de sesgo o fusión satélite–estación (única vía que ataca el problema de fondo).
2. Pedir a INDECI/COEN el registro de emergencias con fecha para completar el catálogo y revisar los 44 días candidatos.
3. Re-correr la cadena completa con las etiquetas corregidas (~2 h).
4. Validar con una temporada nueva o contra SILVIA; presentar el modelo como **índice de prioridad relativa**, no como alerta absoluta.
5. Decidir si el ciclo diario (hora del día) entra al modelo. Pasar entrenamiento y tabla a SAS Viya antes del cierre (fin de octubre).
6. No sustituir IMERG Early por PERSIANN-CCS; no descargar las 84 GB salvo para evaluarlo como variable complementaria o revisar 2024-25.
7. Experimentos de bajo retorno esperado (TabPFN, redes profundas, aumento de datos): dejarlos para el final.

## 10. Archivos clave
`CLAUDE.md` (bitácora completa de pasos), `docs/Diccionario_de_datos_*.docx` (diccionario v2), `modelo/` (tabla, modelos, umbrales, verificaciones, `salida/`), `lluvia/` (descarga y variables de IMERG), `experiments/precipitation_source_comparison/` (`informe_final.md`, scripts 01–06, `docs/`, `salida/`), `docs/solicitud_senamhi.md`.

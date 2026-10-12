# Informe final: fuentes de precipitación para las 17 quebradas de Chosica (12/10/2026)

**No se tocó el modelo, las variables, el terreno ni los resultados previos. No se reemplazó IMERG Early. No se entrenó ningún modelo.**

## Qué se logró y qué no (leer primero)
| | Estado |
|---|---|
| **Descargado y procesado** | **PERSIANN-CCS horario REAL** (bajado en el PC del usuario, el entorno de nube sigue sin alcanzar el servidor): los 63 días alrededor de las 26 fechas del catálogo de huaicos (el día anterior, el día y el siguiente; 1 512 archivos de ~1.9 MB, recortados a 5 × 7 píxeles) más 2024-12-02, 2025-02-12 y 2026-10-10/11; README horario leído; zona horaria verificada. Además la geometría de grillas contra los 17 polígonos reales. **Pluviómetros: nada.** |
| **Visible en una plataforma (sin descargar)** | El índice de PERSIANN-CCS (2000-02-07 a hoy, ~40 min de retraso). De SENAMHI/ISAAC solo hay notas de prensa y resúmenes: este entorno bloquea `www.senamhi.gob.pe` y `www.datosabiertos.gob.pe`. |
| **Pendiente de autorización o de decisión** | Todo lo horario de pluviómetros (solicitud a SENAMHI). Las 12 temporadas de PERSIANN-CCS (84 GB) **no se descargaron**: se decidió esperar a ver si lo de los huaicos lo justificaba (ver abajo: no). |

La prioridad que pediste («primero demostrar que podemos obtener y procesar PERSIANN-CCS y los pluviómetros») se cumplió **para PERSIANN-CCS** y **no para los pluviómetros**.

## Resultados con datos reales de PERSIANN-CCS (12/10/2026)
**Formato y calidad (`scripts/05_verificar_prueba_persiann.py`, `salida/verificacion_prueba_persiann.txt`):** int16 big-endian en mm/h × 100; sin datos faltantes; máximo 38.4 mm/h en un píxel; todos los valores múltiplos de 0.01. **Zona horaria: UTC, inicio de la hora**: en las 15 ventanas con lluvia suficiente el mejor desfase contra IMERG (que está en UTC) fue 0 h en 6, +1 h en 4, −1 h en 2, +2 h en 1 y −3 h en 2; nunca ±5 o ±6 h (lo que daría una hora local). Esto es una verificación burda (ventanas de 1 a 9 días), no una calibración al minuto: puede haber ±1 h de diferencia entre productos.

**¿PERSIANN-CCS ve lluvia en los huaicos que IMERG no ve? (`scripts/06_ciegos_persiann.py`, `salida/ciegos_persiann.txt`; diagnóstico sin retraso, 51 bloques = 14 tormentas, no independientes):**
| | IMERG Early | PERSIANN-CCS |
|---|---|---|
| Bloques con ≥ 0.1 mm en las 6 h hasta el huaico | 19 / 51 | 10 / 51 |
| Bloques con ≥ 1 mm en 6 h | 9 / 51 | 8 / 51 |
| Bloques con ≥ 1 mm en 24 h | 34 / 51 | 25 / 51 |
| Bloques con ≥ 5 mm en 24 h | 13 / 51 | 16 / 51 |
| Mediana de la lluvia de 24 h | 1.86 mm | 0.78 mm |

- **De los 32 bloques «ciegos» de IMERG (< 0.1 mm en 6 h), PERSIANN-CCS ve ≥ 0.1 mm solo en 1.** En 24 h, ≥ 1 mm en 13 de 32.
- Cualquiera de los dos productos marca ≥ 0.1 mm en 20 de 51 bloques (IMERG solo, 19) y ≥ 1 mm en 12 (IMERG solo, 9): **la ganancia al combinarlos es de 1 y 3 bloques**.
- Los productos **coinciden bastante**: correlación (Spearman) de 0.78 en la lluvia de 24 h y 0.67 en la de 6 h hasta el huaico. Hay discrepancias por tormenta en ambos sentidos (PERSIANN-CCS ve más en 2023-03-14, 2026-02-24 y 2026-02-25; IMERG ve más en 2015-03-21 y 2023-03-18).
- La ventana del huaico es más lluviosa que la misma hora del día anterior y del siguiente en 16/51 bloques con IMERG y en 7/51 con PERSIANN-CCS.
- **Quirio, 23/03/2015** (huaico a las 15:10 locales = 20:10 UTC): ambos productos marcan 0 mm a las 20:00 UTC y empiezan a ver lluvia una hora después (21:00 UTC: PERSIANN-CCS 1.02 mm, IMERG Early 1.62 mm). PERSIANN-CCS no se adelanta a IMERG.

**Lectura:** con estos 14 episodios, **PERSIANN-CCS no recupera la lluvia que IMERG pierde en los huaicos** y por sí solo detecta menos horas con lluvia que IMERG. La lluvia de los huaicos «ciegos» parece ser local (celdas pequeñas de la cuenca alta) y escapa a **ambos** satélites (ERA5, un reanálisis, sí la ordena mejor, pero no está disponible en tiempo real). Su ventaja práctica sería la latencia (~40 min frente a ~4 h), pero el análisis del paso 8.1 mostró que quitar toda la latencia de IMERG sube la detección solo ~4 puntos. **Límites:** 14 tormentas; sin pluviómetros no se puede decir cuál de los dos se acerca más a la lluvia real; solo se descargaron los días de los eventos (no hay estadísticas de toda la temporada ni percentil del ciclo diario); se comparó sin retraso, no con la disponibilidad operativa.

## Respuestas a las 7 preguntas
**1. ¿Es posible obtener lluvia horaria de SENAMHI y para qué periodos?**
No verificado. Según fuentes públicas (resúmenes, no las páginas oficiales): el portal de descarga entrega series **diarias** (texto, con registro de usuario); lo **horario** de estaciones automáticas se obtiene por solicitud formal (TUSNE: S/ 348.45 por año, variable y estación en el tarifario 2021 y en un extracto 2024, sin confirmar como vigente) o, para estudiantes e investigadores, por una vía que la directiva interna describe como gratuita, electrónica y de hasta 15 días hábiles. El periodo disponible de cada estación es **desconocido**. ISAAC (14 pluviómetros en la región Lima, tiempo real, según una nota del MINAM) y los 9 pluviómetros municipales que el alcalde mencionó tras el ciclón Yaku (2023) sugieren historiales recientes, pero no hay fecha de instalación confirmada.

**2. ¿Qué estaciones son útiles para nuestras 17 quebradas?**
No puedo confirmarlo con códigos ni coordenadas. Por nombre, las nueve pedidas se relacionan así: Carosio → carossio; Libertad → libertad; Pedregal Koica → pedregal; La Cantuta → la_cantuta; Castilla → probablemente mariscal_castilla; Río Seco, Quebrada Molle, Los Cóndores y Vizcachera → ninguna segura (Río Seco está excluida del piloto y «Los Molles» está sin ubicar en el catálogo). Además aparecen citadas Quirio (SENAMHI, marzo 2023), Chosica, Ñaña y Santa Eulalia. Ver `inventario/estaciones_objetivo.csv`.

**3. ¿PERSIANN-CCS aporta más series espaciales distintas que IMERG Early?**
Sí **en geometría** (y la geometría se confirmó con el README horario real): el píxel de PERSIANN-CCS (0.04°, ~19 km²) es ~6 veces menor que el de IMERG (0.1°, ~120 km²).

| | IMERG Early | PERSIANN-CCS |
|---|---|---|
| Celdas que tocan alguna cuenca | 5 | 11 |
| Series exactamente distintas (de 17 quebradas) | **7** | **17** |
| Celdas dominantes distintas (celda con más área de la cuenca) | 3 | 8 |
| Quebradas con una sola celda efectiva (≥10 % del área) | 15 | 10 |
| Cuencas más chicas que una celda | 17 de 17 | 17 de 17 |

**Esto NO demuestra mayor precisión.** La resolución efectiva de PERSIANN-CCS la fija el infrarrojo de los satélites geoestacionarios, no el tamaño de su píxel; las 17 cuencas (la mayor mide 13.9 km²) siguen siendo menores que un píxel de cualquiera de los dos. Que dos quebradas caigan en celdas distintas solo significa que la serie puede diferir, no que la diferencia sea real. Hace falta compararlas con pluviómetros.

**4. ¿Cuáles siguen compartiendo exactamente la misma lluvia estimada?**
- **IMERG Early (3 grupos con la misma serie exacta, 13 de las 17 quebradas):** (a) rosario, buenos_aires, libertad, carossio, mariscal_castilla, corrales y la_ronda (7, todas con peso 1.0 en la misma celda); (b) santa_maria, chacrasana, el_vallecito y quirio (4); (c) alto_peru y huampani (2). Series propias: santo_domingo, california, pedregal y la_cantuta (varias celdas).
- **PERSIANN-CCS: ninguna pareja comparte la serie exacta** (las 17 tienen una mezcla de pesos distinta). Pero seis quebradas tienen la **misma celda dominante** con pesos distintos: rosario (1.00), buenos_aires (0.97), libertad (0.98), mariscal_castilla (0.91), carossio (0.52) y santo_domingo (0.60); sus series serán muy parecidas, aunque no idénticas.
- **Demasiado pequeñas para resolverse** (menos del 5 % de un píxel de PERSIANN, ~1 km²): rosario (0.14 km²), buenos_aires (0.15), alto_peru (0.21), libertad (0.41), carossio (0.53), mariscal_castilla (0.77) y el_vallecito (0.94). Con ninguna de las dos fuentes se puede asegurar que su lluvia propia se esté midiendo.

**5. ¿PERSIANN-CCS mejora realmente la estimación frente a las observaciones terrestres?**
**Contra pluviómetros, no se puede responder**: no hay series de pluviómetros. Contra IMERG, con datos reales y sin pluviómetros: **no hay evidencia de mejora** en los huaicos (ver resultados arriba: ve lluvia en solo 1 de los 32 huaicos que IMERG no vio; detecta menos horas con lluvia que IMERG; coinciden en lo demás, Spearman 0.78 a 24 h). `04_comparar_temporal.py` queda listo para el resto de la comparación (acumulados de 1, 3, 6 y 24 h, horas con lluvia e intensas, y pluviómetros con sesgo, MAE, correlación, POD/FAR y `concluyente` solo con ≥ 300 horas válidas y ≥ 10 con lluvia) cuando haya temporadas completas y estaciones.

**6. ¿Qué datos necesitamos solicitar formalmente a SENAMHI?**
Precipitación horaria (o del intervalo original) de las 9 estaciones nombradas, más Quirio, Chosica, Ñaña, Santa Eulalia y las demás de ISAAC en el Rímac medio y bajo, **del historial completo**, con códigos, coordenadas, altitud, sensor, marcas de calidad y convención de la marca de tiempo; y preguntar por el acceso en tiempo real a ISAAC y por el historial de SILVIA. Detalle y borrador en `docs/solicitud_senamhi.md`.

**7. ¿Mantener IMERG, sustituirlo o desarrollar una fusión satélite–estación?**
**Mantener IMERG Early como entrada del modelo** y **no sustituirlo por PERSIANN-CCS**: con los datos reales, PERSIANN-CCS no ve la lluvia que IMERG pierde en los huaicos, detecta menos horas con lluvia y sus series coinciden bastante con las de IMERG. Además es una de las tres entradas del SAT de PISCOp_h, así que no es independiente. **No recomiendo bajar las 12 temporadas (84 GB) por ahora**: solo valdría la pena para evaluarlo como variable complementaria por su latencia (~40 min) o para ver la temporada 2024-25. Lo que sí puede cambiar el resultado es **conseguir pluviómetros de SENAMHI** y, si llegan, desarrollar una **corrección de sesgo o fusión satélite–estación**; es la única vía que corrige el problema de fondo (ningún satélite ve la lluvia local de los huaicos «ciegos»).

## Tabla de cobertura espacial (polígonos reales; `salida/cobertura_espacial.csv`)
| quebrada | área_km2 | celdas_IMERG | series_IMERG_compartidas | celdas_PERSIANN | series_PERSIANN_compartidas | peso de la celda dominante (PERSIANN) |
|---|---|---|---|---|---|---|
| rosario | 0.14 | 1 | 6 | 1 | 0 | 1.00 |
| buenos_aires | 0.15 | 1 | 6 | 2 | 0 | 0.97 |
| alto_peru | 0.21 | 1 | 1 | 1 | 0 | 1.00 |
| libertad | 0.41 | 1 | 6 | 2 | 0 | 0.98 |
| carossio | 0.53 | 1 | 6 | 2 | 0 | 0.52 |
| mariscal_castilla | 0.77 | 1 | 6 | 2 | 0 | 0.91 |
| el_vallecito | 0.94 | 1 | 3 | 1 | 0 | 1.00 |
| corrales | 1.26 | 1 | 6 | 3 | 0 | 0.93 |
| huampani | 3.48 | 1 | 1 | 2 | 0 | 0.54 |
| santo_domingo | 3.79 | 2 | 0 | 2 | 0 | 0.60 |
| santa_maria | 4.20 | 1 | 3 | 1 | 0 | 1.00 |
| chacrasana | 4.99 | 1 | 3 | 3 | 0 | 0.95 |
| california | 8.43 | 2 | 0 | 4 | 0 | 0.83 |
| la_ronda | 8.82 | 1 | 6 | 3 | 0 | 0.81 |
| quirio | 9.82 | 1 | 3 | 4 | 0 | 0.44 |
| pedregal | 9.98 | 4 | 0 | 3 | 0 | 0.77 |
| la_cantuta | 13.89 | 2 | 0 | 4 | 0 | 0.50 |

`series_*_compartidas` = cuántas otras quebradas tienen exactamente la misma serie (mismas celdas y mismos pesos). Mapa: `salida/mapa_cobertura.png`. La grilla de PERSIANN-CCS (0.04°, centros 59.98 − 0.04 i y 0.02 + 0.04 j) viene de los READMEs diario y 6-horario y **debe confirmarse con el README horario**; la de IMERG es la ya usada por el proyecto (los pesos reproducidos coinciden con `lluvia/pesos_imerg.csv`).

## Limitaciones y archivos que no pudieron obtenerse
- Sin acceso a `persiann.eng.uci.edu`, `chrsdata.eng.uci.edu`, `www.senamhi.gob.pe`, `www.datosabiertos.gob.pe`: el entorno los bloquea. Para destrabarlo hay que añadir esos hosts en *Network access* del entorno (o correr los scripts en otra máquina).
- **No se obtuvieron:** cualquier serie de pluviómetro; la lista oficial de estaciones de ISAAC; PERSIANN-CCS de las temporadas completas (solo los días de los huaicos y 3 ventanas de prueba). El README horario, el índice y los archivos de prueba SÍ se obtuvieron (en el PC del usuario).
- **Sin confirmar:** la latencia *declarada* de PERSIANN-CCS (observada ~40 min; el README no la da); el comportamiento de la versión «en tiempo real» frente a la reprocesada tras 2 días; la vigencia del tarifario TUSNE y de la gratuidad para investigación. Medido: ~1.9 MB por archivo, 43 488 archivos = ~84 GB para dic–abr de 12 temporadas (no recortables por red).
- Comparación justa en el tiempo: el script solo usa lluvia con etiqueta ≤ t − latencia − 1 para la comparación «operativa» y exige declarar la latencia de PERSIANN-CCS; la comparación sin retraso se marca como diagnóstica.

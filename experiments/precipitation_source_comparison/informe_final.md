# Informe final: fuentes de precipitación para las 17 quebradas de Chosica (12/10/2026)

**No se tocó el modelo, las variables, el terreno ni los resultados previos. No se reemplazó IMERG Early. No se entrenó ningún modelo.**

## Qué se logró y qué no (leer primero)
| | Estado |
|---|---|
| **Descargado y procesado** | Nada de PERSIANN-CCS real ni de pluviómetros. Sí: geometría de grillas contra los 17 polígonos reales, y un decodificador de PERSIANN-CCS **probado con archivos sintéticos** (valida el código, no los datos). |
| **Visible en una plataforma (sin descargar)** | Nada pudo verificarse: este entorno bloquea `persiann.eng.uci.edu`, `chrsdata.eng.uci.edu`, `www.senamhi.gob.pe` y `www.datosabiertos.gob.pe` (403 de la política de red). La información sobre ISAAC y las estaciones viene de notas de prensa y de resúmenes de búsqueda. |
| **Pendiente de autorización o de acceso de red** | Todo lo horario de pluviómetros (SENAMHI) y la descarga de PERSIANN-CCS (permitir los hosts en el entorno o correr los scripts en una máquina con internet). |

La prioridad que pediste («primero demostrar que podemos obtener y procesar PERSIANN-CCS y los pluviómetros») **no se pudo cumplir desde este entorno**; lo que sigue es lo que sí se puede afirmar y lo que quedó listo para correr.

## Respuestas a las 7 preguntas
**1. ¿Es posible obtener lluvia horaria de SENAMHI y para qué periodos?**
No verificado. Según fuentes públicas (resúmenes, no las páginas oficiales): el portal de descarga entrega series **diarias** (texto, con registro de usuario); lo **horario** de estaciones automáticas se obtiene por solicitud formal (TUSNE: S/ 348.45 por año, variable y estación en el tarifario 2021 y en un extracto 2024, sin confirmar como vigente) o, para estudiantes e investigadores, por una vía que la directiva interna describe como gratuita, electrónica y de hasta 15 días hábiles. El periodo disponible de cada estación es **desconocido**. ISAAC (14 pluviómetros en la región Lima, tiempo real, según una nota del MINAM) y los 9 pluviómetros municipales que el alcalde mencionó tras el ciclón Yaku (2023) sugieren historiales recientes, pero no hay fecha de instalación confirmada.

**2. ¿Qué estaciones son útiles para nuestras 17 quebradas?**
No puedo confirmarlo con códigos ni coordenadas. Por nombre, las nueve pedidas se relacionan así: Carosio → carossio; Libertad → libertad; Pedregal Koica → pedregal; La Cantuta → la_cantuta; Castilla → probablemente mariscal_castilla; Río Seco, Quebrada Molle, Los Cóndores y Vizcachera → ninguna segura (Río Seco está excluida del piloto y «Los Molles» está sin ubicar en el catálogo). Además aparecen citadas Quirio (SENAMHI, marzo 2023), Chosica, Ñaña y Santa Eulalia. Ver `inventario/estaciones_objetivo.csv`.

**3. ¿PERSIANN-CCS aporta más series espaciales distintas que IMERG Early?**
Sí **en geometría**: el píxel de PERSIANN-CCS (0.04°, ~19 km²) es ~6 veces menor que el de IMERG (0.1°, ~120 km²).

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
**No se puede responder todavía**: no hay datos de PERSIANN-CCS ni de pluviómetros en el repositorio. El script `04_comparar_temporal.py` calcula sesgo, MAE, correlación, POD/FAR de horas lluviosas e intensas, observaciones válidas y faltantes, y marca `concluyente` solo con ≥ 300 horas válidas y ≥ 10 horas con lluvia. Se probó solo con un producto sintético (para ver que corra), sin guardar resultados.

**6. ¿Qué datos necesitamos solicitar formalmente a SENAMHI?**
Precipitación horaria (o del intervalo original) de las 9 estaciones nombradas, más Quirio, Chosica, Ñaña, Santa Eulalia y las demás de ISAAC en el Rímac medio y bajo, **del historial completo**, con códigos, coordenadas, altitud, sensor, marcas de calidad y convención de la marca de tiempo; y preguntar por el acceso en tiempo real a ISAAC y por el historial de SILVIA. Detalle y borrador en `docs/solicitud_senamhi.md`.

**7. ¿Mantener IMERG, sustituirlo o desarrollar una fusión satélite–estación?**
**Mantener IMERG Early como entrada del modelo por ahora** (no hay evidencia para sustituirlo). Mi recomendación, condicionada a lo que falta verificar: (1) pedir los pluviómetros a SENAMHI ya; (2) correr la prueba de PERSIANN-CCS en una máquina con acceso y confirmar formato, latencia y cobertura; (3) **si se consiguen pluviómetros, desarrollar una fusión o corrección de sesgo satélite–estación** en lugar de cambiar un satélite por otro: ambos productos son estimaciones con el mismo problema de fondo (en 32 de 51 huaicos IMERG marcó menos de 0.1 mm en las 6 h previas y ERA5 ordena mejor los días de huaico), y una fuente adicional de estimación satelital no resuelve eso por sí sola. Además PERSIANN-CCS es una de las tres entradas del SAT de PISCOp_h, así que no es independiente de IMERG Early.

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
- **No se obtuvieron:** el README horario de PERSIANN-CCS; los archivos horarios de las tres ventanas de prueba (Quirio 2015-03-23, 2024-25, reciente); el índice (cobertura histórica y si sigue actualizándose); cualquier serie de pluviómetro; la lista oficial de estaciones de ISAAC.
- **Sin confirmar:** tipo de dato/escala y convención de la hora del producto horario; latencia declarada de PERSIANN-CCS; el peso de cada archivo (los archivos son globales y gzip, no se pueden recortar por red: dic–abr de 12 temporadas son 43 512 archivos); la vigencia del tarifario TUSNE y de la gratuidad para investigación.
- Comparación justa en el tiempo: el script solo usa lluvia con etiqueta ≤ t − latencia − 1 para la comparación «operativa» y exige declarar la latencia de PERSIANN-CCS; la comparación sin retraso se marca como diagnóstica.

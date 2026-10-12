# PERSIANN-CCS horario: procedencia, lo confirmado y lo pendiente

**Estado de acceso (12/10/2026): el entorno de nube sigue sin alcanzar el servidor (no se descargó nada desde allí), pero el usuario SÍ lo alcanza desde su PC y pegó el README horario y el índice (abajo).** El entorno donde se hizo este trabajo bloquea `persiann.eng.uci.edu` y `chrsdata.eng.uci.edu` (el proxy responde 403 a la conexión: política de red del entorno, no un fallo del servidor). La sección «Lo que dicen los READMEs hermanos» es solo contexto histórico: el formato vigente es el del README horario.

## Fuentes oficiales
| Qué | URL | Estado |
|---|---|---|
| Portal CHRS | https://chrsdata.eng.uci.edu/ | no accesible desde este entorno |
| Índice horario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/hrly/ | no accesible desde este entorno |
| README diario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/daily/readme.daily | leído vía buscador (resumen) |
| README 6-horario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/6hrly/readme.6hrly | leído vía buscador (resumen) |
| README horario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/hrly/readme.hrly | **leído** (pegado por el usuario) |
| Catálogo UCAR/GDEX (acumulado horario) | https://gdex.ucar.edu/datasets/d652000/ (DOI 10.5065/N81D-3E26) | aparece en búsquedas; no abierto |
| Tutorial de descarga con Python (CHRS) | https://towardsdatascience.com/download-rainfall-satellite-data-from-chrs-data-portal-using-python-1055d55bef0d | no leído |

## Lo que dicen los READMEs hermanos (misma grilla)
- Grilla de 0.04°, 3000 filas × 9000 columnas, de 60°N a 60°S, longitud 0–360°E. El primer valor es el píxel noroeste, centrado en 0.02°E y 59.98°N; las filas bajan hacia el sur y las columnas van hacia el este.
- Diario (`rgccs1d` + `YYDDD`): float32 *big-endian*, mm/día, NODATA −9999. 6-horario (`YYDDDHH`): int16 *big-endian*, mm/6 h × 100, NODATA −9999.
- «Tiempo real» cerca del presente; el dato en tiempo real se **reprocesa** con entradas más consistentes pasados ~2 días.

## README HORARIO (leído el 12/10/2026: el usuario corrió `--readme` y `--indice` en su PC y pegó la salida)
| Punto | Lo que dice el README / el índice | Estado |
|---|---|---|
| Nombre | `rgccs1h` + `YYDDDHH` + `.bin.gz` (ej. `rgccs1h0934923.bin.gz`); **el prefijo cambia entre años** (el primer archivo del índice, 2000-02-07 20 UTC, es `rgccs0003820.bin.gz`) | **confirmado** |
| Carpetas | subcarpetas por año `YYYY/` (2000 a 2026) | **confirmado** |
| Tipo y escala | entero corto (*short*) *big-endian*, **mm/h × 100** | **confirmado** |
| Grilla | 3000 filas × 9000 columnas, 60N a 60S, 0 a 360E; primer valor = píxel noroeste centrado en 0.02E y 59.98N | **confirmado** |
| Hora | HH = **inicio** del periodo horario (HH:00 a HH:59). El README **no dice la zona horaria**: se asume UTC y debe verificarse con el ciclo diario (la lluvia de la tarde local cae a las ~18–23 UTC) | inicio confirmado; **zona horaria sin confirmar** |
| Latencia | el último archivo del índice (a las 03:38 UTC del 12/10/2026) era el de las **02:00** UTC, es decir, ~40 minutos después de terminar esa hora | observada, no declarada |
| Tiempo real y reprocesado | los datos «realtime» se reprocesan tras 2 días (hasta 24 h de proceso); el README avisa que pueden quedar datos «realtime» sin reprocesar en el archivo | **riesgo** (ver abajo) |
| Cobertura | índice desde 2000-02-07 hasta 2026-10-12; el 2026 tiene 6 819 archivos (de ~6 843 posibles: faltan unas 24 horas) | observada |
| Fecha del README | 17/12/2009 (D. Braithwaite, CHRS) | — |
| Peso por archivo | no medido todavía | `--medir` |

## Riesgos a tener presentes
1. **Los archivos son globales y comprimidos con gzip: no se puede pedir solo un recorte por red.** Cada hora exige bajar el archivo completo y recortarlo al llegar. Dic–abr de 2014-15 a 2025-26 son 43 512 archivos; el peso total depende del tamaño de cada uno (usa `--medir` antes). Si es demasiado, la alternativa a evaluar es la extracción por región del propio portal CHRS (no verificada).
2. **Reprocesamiento:** el archivo histórico es (en su mayor parte) la versión reprocesada con entradas más consistentes, y la operación usaría la versión «en tiempo real» (~40 minutos de latencia). Es la misma trampa de IMERG Early frente a Final: antes de entrenar con el archivo hay que comparar versión en tiempo real y reprocesada. Los días más recientes del índice (últimas ~48 h) todavía son de tiempo real.
3. Según el diccionario del proyecto, PERSIANN-CCS es una de las tres entradas que PISCOp_h promedia en su producto SAT (junto con IMERG Early y GSMaP): no es independiente de las fuentes que ya usamos.
4. El píxel de 0.04° es el tamaño de la grilla; la resolución efectiva de la lluvia estimada la fija el infrarrojo de los satélites geoestacionarios. Una grilla más fina **no** es evidencia de mayor precisión.

## Procedimiento (en una máquina con acceso)
```
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --readme
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --indice
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --medir 6
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --prueba
# solo si la prueba es utilizable y el peso es razonable:
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --temporadas 2014 2025
```
`--prueba` baja 3 ventanas: Quirio 23/03/2015, dos días de 2024-25 (2024-12-02 y 2025-02-12, anómalos en IMERG) y los 2 últimos días del índice. Con la salida, `04_comparar_temporal.py` hace la comparación; pásale `--lat-persiann` con la latencia del README.

**Verificado:** el decodificador, el recorte (fila/columna → latitud/longitud) y el ensamblado mensual se probaron con archivos sintéticos locales en ambos formatos posibles (`salida/prueba_sintetica_decodificador.txt`, 9 de 9 píxeles correctos). Eso valida el código, **no** los datos reales.

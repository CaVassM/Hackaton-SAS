# PERSIANN-CCS horario: procedencia, lo confirmado y lo pendiente

**Estado de acceso (12/10/2026): NO se pudo descargar ni leer nada del servidor.** El entorno donde se hizo este trabajo bloquea `persiann.eng.uci.edu` y `chrsdata.eng.uci.edu` (el proxy responde 403 a la conexión: política de red del entorno, no un fallo del servidor). Todo lo que sigue sobre el formato viene de documentos hermanos (diario y 6-horario) encontrados por búsqueda, **no del README horario**.

## Fuentes oficiales
| Qué | URL | Estado |
|---|---|---|
| Portal CHRS | https://chrsdata.eng.uci.edu/ | no accesible desde este entorno |
| Índice horario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/hrly/ | no accesible desde este entorno |
| README diario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/daily/readme.daily | leído vía buscador (resumen) |
| README 6-horario | https://persiann.eng.uci.edu/CHRSdata/PERSIANN-CCS/6hrly/readme.6hrly | leído vía buscador (resumen) |
| README horario | …/PERSIANN-CCS/hrly/readme.hrly | **no encontrado por el buscador; no leído** |
| Catálogo UCAR/GDEX (acumulado horario) | https://gdex.ucar.edu/datasets/d652000/ (DOI 10.5065/N81D-3E26) | aparece en búsquedas; no abierto |
| Tutorial de descarga con Python (CHRS) | https://towardsdatascience.com/download-rainfall-satellite-data-from-chrs-data-portal-using-python-1055d55bef0d | no leído |

## Lo que dicen los READMEs hermanos (misma grilla)
- Grilla de 0.04°, 3000 filas × 9000 columnas, de 60°N a 60°S, longitud 0–360°E. El primer valor es el píxel noroeste, centrado en 0.02°E y 59.98°N; las filas bajan hacia el sur y las columnas van hacia el este.
- Diario (`rgccs1d` + `YYDDD`): float32 *big-endian*, mm/día, NODATA −9999. 6-horario (`YYDDDHH`): int16 *big-endian*, mm/6 h × 100, NODATA −9999.
- «Tiempo real» cerca del presente; el dato en tiempo real se **reprocesa** con entradas más consistentes pasados ~2 días.

## Lo que falta confirmar con el README horario  (cada punto está marcado [CONFIRMAR] en el script)
| Pregunta | Supuesto del script | Cómo resolverlo |
|---|---|---|
| Tipo de dato y escala del horario | se infiere del README; si no se puede, `--dtype` y `--escala` | `--readme` |
| Patrón del nombre | `rgccs1h` + `YYDDDHH` + `.bin.gz` | `--indice` |
| La hora del nombre, ¿inicio o fin del acumulado? | `inicio` (`--convencion`) | README |
| Latencia declarada | desconocida | README + `--indice` (antigüedad del último archivo) |
| Cobertura histórica | desconocida (se espera 2003 en adelante: **confirmar**) | `--indice` |
| Peso por archivo | desconocido | `--medir` |

## Riesgos a tener presentes
1. **Los archivos son globales y comprimidos con gzip: no se puede pedir solo un recorte por red.** Cada hora exige bajar el archivo completo y recortarlo al llegar. Dic–abr de 2014-15 a 2025-26 son 43 512 archivos; el peso total depende del tamaño de cada uno (usa `--medir` antes). Si es demasiado, la alternativa a evaluar es la extracción por región del propio portal CHRS (no verificada).
2. **Reprocesamiento:** el archivo histórico puede ser la versión reprocesada y la operación usaría la versión «en tiempo real». Es la misma trampa de IMERG Early frente a Final: hay que comparar ambas versiones antes de entrenar con una.
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

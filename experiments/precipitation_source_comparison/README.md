# Experimento: fuentes de precipitación para las 17 quebradas de Chosica

Pregunta: ¿se puede mejorar la resolución espacial (y la calidad) de la lluvia del proyecto, hoy IMERG Early V07 (0.1°), con PERSIANN-CCS horario (0.04°) y con pluviómetros de SENAMHI?
**No toca el modelo, las variables, el terreno ni los resultados previos; no reemplaza IMERG Early; no entrena ningún modelo.**

**Lee primero `informe_final.md`** (conclusión ejecutiva, con lo descargado / visible / pendiente por separado).

| Carpeta | Contenido |
|---|---|
| `informe_final.md` | Respuestas a las 7 preguntas, limitaciones y archivos que no pudieron obtenerse |
| `docs/persiann_ccs.md` | Procedencia, formato (confirmado vs. supuesto) y procedimiento de PERSIANN-CCS |
| `docs/senamhi_estaciones.md` | ISAAC, las 9 estaciones pedidas, vías oficiales de acceso y costos |
| `docs/solicitud_senamhi.md` | Qué estaciones y periodos solicitar y borrador de la solicitud |
| `inventario/` | Archivos del proyecto relevantes y estaciones ya investigadas |
| `scripts/` | `01_inventario.py`, `02_descargar_persiann_ccs.py`, `03_cobertura_espacial.py`, `04_comparar_temporal.py`, `05_verificar_prueba_persiann.py`, `06_ciegos_persiann.py`, `test_sintetico_decodificador.py` |
| `salida/` | Tablas de cobertura espacial, celdas por cuenca, mapa y la prueba sintética del decodificador |
| `datos/` | (no va a git) PERSIANN-CCS recortado y series de pluviómetros cuando existan |

## Estado por tarea
| Tarea | Estado |
|---|---|
| 1. Inventario del proyecto | **Hecho** |
| 2. Pluviómetros SENAMHI | Investigado en fuentes públicas; **sin datos descargados** (el entorno bloquea senamhi.gob.pe); solicitud preparada |
| 3. PERSIANN-CCS horario | **Descargado y verificado con datos reales** (en el PC del usuario): README leído, 63 días de los huaicos + 3 ventanas, zona horaria UTC verificada. Las 12 temporadas (84 GB) NO se bajaron |
| 4. Cobertura espacial | **Hecho** (geometría de grillas con los polígonos reales) |
| 5. Comparación temporal | Hecho para los huaicos (`06_ciegos_persiann.py`): PERSIANN-CCS ve lluvia en 1 de los 32 huaicos «ciegos» de IMERG. Con pluviómetros: pendiente |
| 6/7. Informe | **Hecho**, con las conclusiones que sí se sostienen |

## Cómo continuar (en una máquina con acceso a internet)
```
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --readme
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --indice
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --medir 6
python experiments/precipitation_source_comparison/scripts/02_descargar_persiann_ccs.py --prueba
python experiments/precipitation_source_comparison/scripts/04_comparar_temporal.py --lat-persiann <horas del README>
```
Si el entorno de nube es el que se usa, hay que permitir los hosts `persiann.eng.uci.edu` y `chrsdata.eng.uci.edu` (y `www.senamhi.gob.pe` para la plataforma) en *Network access* del entorno.

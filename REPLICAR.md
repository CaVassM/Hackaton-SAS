# Cómo replicar el modelo

Esta guía reproduce el **modelo final v3** desde el repositorio y verifica que el resultado coincide con el entregado.
Cubre las dos piezas (P1 = zona; P2 = quebrada) y la entrega al dashboard con el nivel M3.
Todos los insumos de datos que usa el modelo ya están versionados en git, así que la replicación básica **no necesita descargas ni credenciales**.

## 1. Replicación en 3 comandos (~15 min)
```bash
git clone <url-del-repo> Hackaton-SAS && cd Hackaton-SAS
python -m pip install -r requirements.txt        # Python 3.13; las versiones fijadas importan (ver §4)
python replicar.py
```
Al final debe aparecer:
```
B1 (validación LOSO por evento): TSS 0.49 (ref. 0.49), aciertos 9 de 13, falsas alarmas 316
Modelo P1 y ejemplo idénticos byte a byte (salvo saltos de línea): SÍ
RESULTADO: REPLICA OK
```

**Variantes de `replicar.py`:**

| Opción | Qué hace |
|---|---|
| `--recalcular` | Recalcula todo desde los insumos. Los cachés de una corrida anterior se mueven a un respaldo; no se borran. |
| `--desde-partes` | Reconstruye también el catálogo y las etiquetas v1 desde las partes del catálogo. |
| `--descargar` | Vuelve a bajar los insumos (§3). |
| `--solo-verificar` | Solo compara las salidas actuales con `replicacion_referencia.json`. |

## 2. Qué hace cada paso
`replicar.py` corre estos scripts en orden; cada uno se puede correr solo.

| Paso | Script | Entradas | Salidas |
|---|---|---|---|
| 1 (opcional) | `catalogo_huaicos_chosica/construir_catalogo.py`, luego `etiquetas_por_quebrada.py` (**siempre en ese orden**: el primero deja un `etiquetas_horarias_H6` por nombre que el segundo reemplaza) | `parte_*.csv`, `terreno/alias_catalogo.csv`, `terreno/quebradas.csv` | `catalogo_huaicos_chosica.csv`, `etiquetas_horarias_H{3,6,12,24}.parquet` (v1) |
| 2 | `catalogo_huaicos_chosica/etiquetas_v2.py` | catálogo, `horas_B_v2.csv` (horas vagas releídas en las fuentes, con url y cita) | `etiquetas_horarias_v2_H*.parquet`; comprueba que reproduce v1 bit a bit |
| 3 | `modelo/v3/A/fase_a.py` | IMERG Early (`lluvia/datos/early/`), pesos IMERG, etiquetas v2 | eventos de lluvia (`A/fase_a_eventos.parquet`), `A/fase_a_resumen.csv` |
| 4 | `modelo/v3/B/fase_b1.py` | lo anterior + ERA5-Land, ICEN, catálogo | predicciones fuera de muestra de B1 (`_cache/oof_b1.parquet`), `B/fase_b1_resumen.csv` (**TSS 0.49**) |
| 5 | `modelo/v3/final/modelo_final.py entrenar` | lo anterior | **`p1_b1.json`** (modelo P1), **`metadatos_final.json`** (variables, fuentes, umbrales por H), **`p2_final.csv`** |
| 6 | `modelo/v3_1/entrega/entrega_dashboard.py ejemplo` | modelo final | `ejemplo_2022_23_m3.csv` (temporada 2022-23 fuera de muestra, nivel M3 por defecto) |
| 7 | verificación | `replicacion_referencia.json` | REPLICA OK / NO REPLICA |

Una vez replicado, el modelo se usa así:
```bash
python modelo/v3_1/entrega/entrega_dashboard.py hora "2023-03-14 13:00" --csv salida.csv   # 17 quebradas x 4 horizontes
```

## 3. Insumos (versionados en git) y cómo volver a bajarlos
| Insumo | Archivo en el repo | Cómo se bajó | Notas |
|---|---|---|---|
| IMERG Early V07, 30 min, 12 celdas, dic–abr 2014-15 a 2025-26 | `lluvia/datos/early/imerg_early_AAAA-MM.nc` (60 meses) | `python lluvia/descargar_masivo.py --procesos 24 --url-directa` (~8 h) | Requiere cuenta Earthdata en `~/.netrc` (Windows: `%USERPROFILE%\_netrc`). Nunca poner credenciales en el código |
| Humedad del suelo ERA5-Land (5 celdas) | `modelo/v3/datos/raw/openmeteo/era5_land.parquet` | `python modelo/v3/datos/descargar_openmeteo.py --solo era5_land` | Open-Meteo, sin credenciales |
| ICEN (IGP/ENFEN) | `modelo/v3/datos/raw/icen/ICEN.txt` | `python modelo/v3/datos/descargar_icen.py --forzar` | Bajado el 12/10/2026 (último dato: jul-2026) |
| Catálogo de huaicos | `catalogo_huaicos_chosica/` | Prensa e INDECI, revisado a mano | Fuente y URL de cada fila en el CSV |
| Cuencas de las 17 quebradas | `terreno/quebradas.geojson`, `quebradas.csv` | Notebooks de `terreno/notebooks/` (FABDEM, D8) | Ver §5 |

Si se vuelven a bajar los insumos, los valores pueden cambiar: NASA reprocesa IMERG, IGP revisa el ICEN y Open-Meteo actualiza ERA5. En ese caso `replicar.py` lo informa como NO REPLICA, con el detalle de las diferencias.

## 4. Determinismo y versiones
- Con las versiones de `requirements.txt`, la corrida es **idéntica byte a byte**: el modelo `p1_b1.json` y el CSV de ejemplo. Se comprobó en un clon limpio.
- **xgboost es la versión que más importa.** Con otra versión el modelo cambia; por ejemplo, el TSS de control de B1 sale 0.45 en lugar de 0.49.
- Los hiperparámetros están fijos en el código: `modelo/arboles.py` (`PARAMS_XGB`) y `modelo/restringido.py` (`CHICO`). Usa semilla 0 y `n_jobs=4`.

## 5. Qué no reproduce `replicar.py`
- **El camino del terreno** (delimitación de cuencas). Se hizo una sola vez con FABDEM 30 m y WhiteboxTools, en los notebooks de `terreno/notebooks/`:
  - `0_revision_fabdem_chosica` prepara el DEM;
  - `1_cuencas` define la red y las cuencas candidatas;
  - `2_referencia_validacion` valida contra ANA y SIGRID;
  - `3_quebradas_finales` deja las 17 quebradas.

  Se ejecutaron en la carpeta del proyecto, con los rasters de FABDEM fuera del repo: FABDEM se descarga de data.bris.ac.uk (CC BY-NC-SA 4.0). Sus salidas (`terreno/quebradas.*`, tablas intermedias) están versionadas.
- **Las fases exploratorias y los modelos descartados:**
  - modelos anteriores: `modelo/` (v1 por quebrada), `modelo/dos_piezas/`, `modelo/mejoras/`, `modelo/etiquetas_v2/`;
  - fases experimentales del v3: `modelo/v3/{C,D,E,B2,F}`;
  - mejoras pre-registradas: `modelo/v3_1/M1`, `M3`;
  - comparación de fuentes: `experiments/`.

  Cada una tiene su script y su resumen (`RESUMEN.md`), pero algunas usan datos que no están en el repo: la base de emergencias de INDECI, IMERG diario multizona, `terreno/fuentes`.

## 6. Dónde está cada cosa
- **Modelo final:** `modelo/v3/final/`. Su ficha está en `modelo/v3/model_card_datos.md`.
- **Entrega al dashboard:** `modelo/v3_1/entrega/`.
- **Resultados y decisiones de cada fase:** `modelo/v3/RESUMEN.md`, `modelo/v3_1/RESUMEN.md` y `CLAUDE.md` (bitácora completa del proyecto).
- **Diccionario de datos:** `docs/Diccionario_de_datos_Modelo_de_alerta_de_huaicos_Chosica.docx`.

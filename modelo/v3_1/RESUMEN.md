# v3.1 — Mejoras finales pre-registradas (se reportan todas). Validación igual que v3 (por evento, TSS, LOSO, IC 90 % bootstrap de tormentas).

## M1 — Más positivos de la zona (`M1/m1_zona_ampliada.py`; casos para revisar: `M1/casos_nuevos_zona.csv`)
- Zona = 5 celdas IMERG (lat -12.0..-11.8, lon -76.9..-76.6). Casos nuevos: **67** (catálogo de prensa 34: Chaclacayo, Santa Eulalia baja y quebradas sin
  ubicar de Lurigancho; INDECI 32 sin hora y confianza BAJA; COOLR 1); 24 con hora; 34 en fechas sin activación de las 17. Fuera de la zona (siguen
  "desconocidos"): Huaycoloro, Río Seco, Jicamarca, Huaycán, San Antonio. Sin hora -> rango = día completo (solo cuenta para H = 24).
- Horas positivas de zona v3 -> M1 (H = 3/6/12/24): 32/68/158/326 -> 48/104/230/470.

| Evaluación | v3 (B1) | M1 semilla 0 / 1 / 2 |
|---|---|---|
| (a) 13 positivos originales, evento | 0.49 (0.15, 0.70) | 0.44 (0.16, 0.63) / 0.53 (0.18, 0.73) / 0.53 (0.19, 0.73) |
| (b1) 18 positivos con hora de la zona, evento | 0.40 (0.12, 0.58) | 0.33 (0.06, 0.51) / 0.38 (0.05, 0.59) / 0.40 (0.08, 0.62) |
| (b2) 35 días con activación en la zona, día | **0.69 (0.59, 0.78)**, 31/35 | 0.47 (0.28, 0.61) / 0.65 (0.52, 0.74) / 0.62 (0.48, 0.72) |
- **M1 NO mejora de forma consistente** (en (a) depende de la semilla: 0.44-0.53 vs 0.47-0.49 de v3; en (b1) y (b2) igual o peor). Los positivos nuevos
  son mayormente sin hora (solo aportan a H = 24) y de confianza baja (INDECI).
- **Hallazgo útil: v3, entrenado SIN las vecinas, detecta 31 de 35 días con activación en la zona** (incluidas Chaclacayo y Santa Eulalia): validación con
  positivos que el modelo nunca vio.

## M2 — CAPE / K / Total Totals: NO HECHA
- `~/.cdsapirc` no existe (verificado al inicio): sin credenciales del CDS no se puede bajar ERA5 single levels (cape, k_index, total_totals_index).

## M3 — Nivel operativo con menos horas en rojo, sin reentrenar (`M3/m3_nivel.py`)
Rojo = p_zona ≥ umbral rojo **y** IMERG > 0.1 mm en las últimas 6 h disponibles; si no hay lluvia reciente baja a amarillo ("condiciones favorables").
| Nivel | TSS (IC 90 %) | POD (IC 90 %) | POFD | Horas en rojo dic-abr (H=3) | Anticipación mediana (≥1 h / ≥3 h / ≥6 h) |
|---|---|---|---|---|---|
| v3 rojo actual | 0.49 (0.15, 0.70) | 0.69 (0.33, 0.89) | 0.20 | 6 436 h (15.0 %) | 2.0 h (6 / 3 / 1 de 9) |
| M3 rojo | 0.44 (0.16, 0.63) | 0.62 (0.33, 0.80) | 0.17 | 4 868 h (11.4 %) | 2.1 h (5 / 2 / 1 de 8) |
- M3 quita ~24 % de las horas rojas (2024-25: 24 % -> 20 %; 2016-17: 48 % -> 37 %) a cambio de 1 acierto (un huaico sin lluvia IMERG en las 6 h previas,
  que queda en AMARILLO). Ni más ni menos anticipación.

## Tabla v3 vs mejoras (por evento, 13 positivos originales; IC 90 % bootstrap de tormentas)
| Versión | TSS (IC 90 %) | POD | POFD | Horas en rojo | Comentario |
|---|---|---|---|---|---|
| **v3 (B1)** | **0.49 (0.15, 0.70)** | 0.69 | 0.20 | 15.0 % | semillas 0.47-0.49 |
| M1 (zona ampliada) | 0.44 / 0.53 / 0.53 (≈0.16-0.19, 0.63-0.73) | 0.62-0.69 | 0.16-0.18 | — | depende de la semilla; por día peor (0.47-0.65 vs 0.69) |
| M2 (CAPE, K, TT) | no hecha | | | | falta `.cdsapirc` |
| M3 (rojo con lluvia reciente) | 0.44 (0.16, 0.63) | 0.62 | 0.17 | 11.4 % | pierde 1 acierto, que queda en amarillo |
| Combinación | no aplica | | | | ninguna mejora el TSS |

## Recomendación
- **Quedarse con el MODELO v3** (`modelo/v3/final/`): ninguna mejora pre-registrada sube el TSS más allá del ruido entre semillas. M1 no ayuda y además
  depende de casos de confianza baja (INDECI sin hora); su lista queda para revisión (`M1/casos_nuevos_zona.csv`).
- **M3 como capa de PRESENTACIÓN (opcional, no cambia el modelo)**: si el dashboard necesita menos horas en rojo, mostrar en rojo solo con lluvia reciente
  (11 % de las horas en vez de 15 %) y el resto como "amarillo: condiciones favorables". El POD de "rojo o amarillo" no cambia (0.69); el del rojo baja a
  0.62. Es decisión de comunicación del equipo.
- Validación extra a favor de v3 (M1-b2): detecta 31 de 35 días con activación en la zona, incluidas quebradas vecinas que nunca vio.

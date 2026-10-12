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

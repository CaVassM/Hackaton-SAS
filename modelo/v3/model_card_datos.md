# Ficha del modelo v3 — Alerta de huaicos en Lurigancho-Chosica

Versión: v3 (octubre 2026). Código: `modelo/v3/` (detalle de cada fase en `RESUMEN.md`).

## 1. Qué hace
Estima, cada hora, el riesgo de huaico en las 17 quebradas piloto de Lurigancho-Chosica, para horizontes de 3, 6, 12 y 24 horas.
Tiene dos piezas:

- **P1, cuándo (zona):** probabilidad de que se active alguna de las 17 quebradas en las próximas H horas. Usa la intensidad de lluvia satelital y el estado de la zona.
- **P2, dónde (quebrada):** qué tan propensa es cada quebrada cuando hay tormenta. Combina su historia de activaciones con el terreno (área y pendiente).

Salida por hora y quebrada: `p_zona`, `p2_quebrada`, `score = p_zona × p2`, `indice_0_100` y `nivel` (verde, amarillo o rojo).
El nivel es de la **zona**, que es lo que se validó. P2 solo ordena las quebradas dentro de la alerta.

## 2. Datos
| Dato | Fuente | Periodo | Uso |
|---|---|---|---|
| Lluvia | IMERG Early V07 (NASA), 30 min, 0.1°, 5 celdas sobre las quebradas | dic–abr, 2014-15 a 2025-26 | intensidad (con 4 h de latencia) |
| Humedad del suelo 0–7 cm | ERA5-Land (vía Open-Meteo) | 2014–2026 | estado (valor de hace 5 días: retraso real de ERA5-Land) |
| El Niño costero | ICEN oficial (IGP/ENFEN) | mensual | estado (último valor ya publicado: mes M−2 o M−3) |
| Activaciones | catálogo de prensa e INDECI (130 registros, 26 fechas; etiquetas v2) | feb-2015 a feb-2026 | etiquetas y "días desde la última activación" |
| Terreno | FABDEM 30 m (cuencas delimitadas) | — | P2 (área, pendiente) |

Etiquetas v2: las horas vagas del catálogo ("la tarde") se tratan como un rango. Una hora es positiva solo si la ventana (t, t+H] contiene todo el rango; si lo toca a medias, la hora queda excluida.

## 3. Variables de P1 (en orden)
1. `i1h`, `i3h`, `i6h`: lluvia máxima entre celdas en 1, 3 y 6 h.
2. `i1h_max6`, `i3h_max6`, `i6h_max6`: el máximo de esas tres en las últimas 6 h disponibles.
3. `p24h`, `p48h`, `p72h`: lluvia de 24, 48 y 72 h.
4. `hum_suelo_5d`: humedad del suelo de hace 5 días.
5. `dias_activ`: días desde la última activación catalogada (solo fechas anteriores).
6. `icen`: último ICEN publicado.
7. `H`: horizonte.

Toda la lluvia usa una latencia de 4 h: en la hora t solo entra la lluvia con etiqueta ≤ t−5.

Modelo: XGBoost con restricciones físicas de monotonía (más lluvia, humedad o ICEN nunca bajan el riesgo) y árboles pequeños (profundidad 2, 150 árboles). Los hiperparámetros se fijaron de antemano.

## 4. Cómo se validó
- **Unidad:** el **evento de lluvia** IMERG (horas con ≥ 0.1 mm, separadas por ≥ 6 h secas). Es **disparador** si hubo un huaico durante el evento o hasta 3 h después.
- **Evaluación de 1 602 eventos:**
  - Hay **13 unidades positivas:** 12 eventos disparadores y 1 día "ciego", en el que IMERG no registró lluvia y que cuenta como fallo.
  - En cada disparador solo cuenta lo que se sabía **antes** del huaico.
- **Métrica:** TSS = tasa de acierto (POD) − tasa de falsas alarmas (POFD). 0 es el azar y 1 es perfecto.
- **Umbral y validación:** el umbral maximiza el TSS en las temporadas de entrenamiento y se valida dejando una temporada fuera (LOSO, 12 temporadas).
- **Intervalo de confianza:** IC 90 % por *bootstrap* de tormentas.

## 5. Resultados (fuera de muestra)
| Método | TSS (IC 90 %) | Acierto | Falsas alarmas |
|---|---|---|---|
| Azar | 0 | — | — |
| Umbral ISAAC/SENAMHI (I = 1.57·D^−0.047) aplicado a IMERG | −0.13 (−0.22, −0.05) | 0.08 | 0.20 |
| Modelo anterior (por quebrada, solo lluvia) | 0.15 (−0.23, 0.44) | 0.38 | 0.23 |
| Persistencia trivial (activación en los 2 días previos y lluvia > mediana) | 0.07 (−0.01, 0.19) | 0.08 | 0.01 |
| **v3: P1 = B1** | **0.49 (0.15, 0.70)** | **0.69** | **0.20** |
| v3 sin "días desde activación" | 0.34 (≈0.00, 0.54) | 0.69 | 0.35 |
| v3 solo en primeros huaicos (8) | 0.30 (0.04, 0.56) | 0.50 | 0.20 |
| v3 agregado por día (18 días con huaico) | 0.69 (0.53, 0.81) | 0.89 | 0.20 |

- **Estabilidad:** da lo mismo con 3 semillas (0.47–0.49) y sin las temporadas del Niño costero (0.50).
- **Anticipación:** de los 9 aciertos, la primera alerta llega con una mediana de **2 h** antes del inicio del huaico (rango −4 a 29 h). 6 de 9 llegan con ≥ 1 h de anticipación y 3 de 9 con ≥ 3 h. **Solo H = 3 h es una promesa honesta.**
- **Umbrales operativos:**
  - **Rojo**, máximo TSS: POD 0.77, POFD 0.20.
  - **Amarillo**, máximo POD alcanzable (0.85): POFD ~0.45.
  - **Costo:** la zona queda en rojo ~15 % de las horas de diciembre a abril y en amarillo ~35 %.

## 6. Limitaciones
- **Muy pocos casos.** Hay 13 unidades positivas en 10 tormentas, y la cobertura del catálogo de prensa es desigual. Los intervalos son anchos.
- **IMERG no ve el golpe corto de lluvia** que dispara estos flujos en zona árida:
  - antes de los huaicos marca menos lluvia que en un evento cualquiera;
  - el umbral de pluviómetro de ISAAC no sirve sobre IMERG.
  La señal de B1 viene sobre todo del **estado** combinado con la intensidad.
- **Rachas.** "Días desde la última activación" aporta ~0.15 de TSS, porque los huaicos llegan en rachas de varios días. En parte refleja cómo cubre la prensa esos episodios. Sin esa variable, el IC queda en el límite de 0.
- **Depende de datos en tiempo real que hoy no existen como flujo:**
  - el registro de activaciones (INDECI o municipio);
  - IMERG Early, que llega con ~4 h de retraso;
  - ERA5-Land, que llega con ~5 días.
- **Muchas horas en alerta.** Sirve como **índice de prioridad**, no como alarma pública automática.
- **Escala entre temporadas.** IMERG Early sobrestima ~2.3 veces frente a IMERG Final. La temporada 2024-25 fue muy lluviosa según el satélite y no tiene huaicos catalogados (revisado en prensa: solo hubo alertas).

## 7. Qué datos lo mejorarían
1. **Pluviómetros de SENAMHI/ISAAC** (Lima Este, horarios o subhorarios). Son la única vía para ver el golpe corto de lluvia y calibrar un umbral I–D local. La solicitud está en `docs/solicitud_senamhi.md`.
2. **CAPE, índice K y Total Totals de ERA5** (CDS), o de pronóstico, para el ambiente convectivo. Con Open-Meteo, un pronóstico perfecto de la lluvia de ERA5 solo sube el TSS a 0.51.
3. **Registro oficial de emergencias con hora** (INDECI/COEN) y avisos de SENAMHI por provincia, para completar el catálogo y la variable de rachas.
4. **Earth Engine** (AlphaEarth, Sentinel-2), para describir el material suelto de los cauces.

## 8. Archivos
- `final/p1_b1.json`: modelo P1.
- `final/metadatos_final.json`: variables, fuentes, umbrales y parámetros.
- `final/p2_final.csv`: P2.
- `final/predecir.py`: predicción para una hora.
- `final/ejemplo_2022_23.csv`: ejemplo fuera de muestra.
- `RESUMEN.md`, `tabla_final.csv`: detalle y comparaciones.

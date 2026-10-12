# Qué solicitar formalmente a SENAMHI

## Resumen para decidir
Lo que más valor tendría: **lluvia horaria (o de 10 minutos) de los pluviómetros automáticos ubicados dentro o junto a las 17 quebradas**, con su historial completo. Hoy el proyecto no tiene ninguna medición de lluvia por pluviómetro en la zona de las quebradas: todo lo que entra al modelo es estimación satelital (IMERG Early), que en 32 de 51 huaicos marcó menos de 0.1 mm en las 6 h previas. Un pluviómetro es una medición puntual, no la lluvia media de una cuenca, pero sirve para:
1. saber cuál fuente (IMERG, PERSIANN-CCS, ERA5) se acerca más a la lluvia real;
2. corregir el sesgo (IMERG Early da ~2.3 veces lo de IMERG Final en meses lluviosos) y entrenar una fusión satélite–estación;
3. si hubiera acceso en tiempo real (ISAAC), usar los pluviómetros de las cuencas altas como variable del modelo.

## Lista de estaciones
**Prioridad A (9 estaciones que nos indicaron):** Carosio, Castilla, Libertad, Pedregal Koica, La Cantuta, Río Seco, Quebrada Molle, Los Cóndores y Vizcachera.
**Prioridad B:** Quirio (SENAMHI la citó en 2023), Chosica (meteorológica), Ñaña, Santa Eulalia y las demás de las **14 de ISAAC** que estén en las cuencas media y baja del Rímac.
**Para cada una pedir:** nombre, código, coordenadas, altitud, tipo de sensor y resolución del pluviómetro, y fecha de instalación.

## Qué periodos
- Variable: **precipitación**; escala **horaria** (o el intervalo original si es más fino, indicando cuál es).
- Periodo: **todo el historial disponible hasta hoy**. Si hay que acotar por costo, lo mínimo útil son las temporadas **diciembre–abril** desde la instalación de cada estación; no sabemos cuándo se instalaron los pluviómetros de las quebradas (el alcalde habló de 9 en 9 quebradas después del ciclón Yaku, 2023, sin fecha de instalación); si son de 2023 en adelante, se esperan sobre todo las temporadas 2022-23 a 2025-26. Las temporadas 2024-25 (anómala en IMERG) y 2022-23 (la de más huaicos recientes) son las más valiosas.
- Pedir también: **marcas de calidad (QC)**, convención de datos faltantes y **zona horaria/convención de la marca de tiempo** (UTC o local; inicio o fin del intervalo).

## Preguntas adicionales para SENAMHI
1. ¿Se pueden recibir los datos de ISAAC **en tiempo real** (servicio o convenio) y con qué retraso?
2. ¿Cómo se puede acceder al historial de **SILVIA** (alertas por quebrada) para comparar el modelo?
3. ¿La base **PISCO horario** reciente está publicada y con qué licencia?

## Borrador de solicitud (editar y enviar por el canal que corresponda)
> **Asunto:** Solicitud de datos de precipitación horaria de estaciones de las quebradas de Lurigancho-Chosica (fines de investigación)
>
> Soy estudiante de la PUCP (@Camilo, correo) y participo en un proyecto de alerta temprana de huaicos para Lurigancho-Chosica (SAS Hackathon 2026). Solicito, para fines de investigación y sin fines de lucro, la serie de **precipitación horaria (o del intervalo original)** de las estaciones: Carosio, Castilla, Libertad, Pedregal Koica, La Cantuta, Río Seco, Quebrada Molle, Los Cóndores, Vizcachera, Quirio, Chosica, Ñaña, Santa Eulalia y las demás de la plataforma ISAAC ubicadas en las cuencas media y baja del Rímac, **desde su fecha de instalación hasta la fecha**, con sus marcas de calidad, metadatos (código, coordenadas, altitud, sensor, resolución) y convención de la marca de tiempo. Pido que me indiquen si corresponde trámite gratuito para investigadores/estudiantes o el costo según el TUSNE vigente.
>
> Adjunto: carta de la universidad / constancia de estudiante y descripción del proyecto.

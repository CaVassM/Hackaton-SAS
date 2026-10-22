const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, HeadingLevel, AlignmentType, ImageRun, LevelFormat } = require('docx');

// ---------- helpers
function runs(text, base = {}) {
  const out = [];
  for (const part of text.split(/(\*\*.+?\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g)) {
    if (!part) continue;
    if (part.startsWith('**')) out.push(...runs(part.slice(2, -2), { ...base, bold: true }));
    else if (part.startsWith('`')) out.push(new TextRun({ ...base, text: part.slice(1, -1), font: 'Consolas', size: (base.size || 22) - 2 }));
    else if (part.startsWith('*') && part.endsWith('*') && part.length > 2) out.push(...runs(part.slice(1, -1), { ...base, italics: true }));
    else out.push(new TextRun({ ...base, text: part }));
  }
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), ...o });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = t => new Paragraph({ numbering: { reference: 'bul', level: 0 }, children: runs(t) });
const N = (t, ref) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t) });
const CHK = (t, done) => new Paragraph({ spacing: { after: 80 }, indent: { left: 360, hanging: 360 }, children: [new TextRun({ text: done ? '☑  ' : '☐  ' }), ...runs(t)] });

const thin = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: thin, bottom: thin, left: thin, right: thin };
function table(widths, header, rows, o = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (t, i, head) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA }, borders,
    shading: head ? { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({ spacing: { after: 0 }, children: runs(String(t), { size: o.size || 19, bold: head ? true : undefined }) })],
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map(r => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, i, false)) }))],
  });
}
const gap = () => new Paragraph({ spacing: { after: 60 }, children: [] });

// ---------- contenido
const c = [];
c.push(H1('Diccionario de datos — Modelo de alerta de huaicos (Chosica)'));
c.push(P('Oct 12, 2026 · @Camilo · versión 3 (modelo v3 y entrega al dashboard; la versión 2 es del 12 de octubre y la primera del 5 de octubre)'));

c.push(H2('De qué va esto'));
c.push(P('El modelo responde una sola pregunta: **¿habrá huaico en esta quebrada en las próximas H horas?** Devuelve una probabilidad por quebrada, por hora y por horizonte (3, 6, 12 o 24 h). El riesgo y la exposición los calcula otra parte del equipo; aquí solo predecimos el peligro.'));
c.push(P('**Modelo vigente: v3, en dos piezas.** P1 (*cuándo*) estima el riesgo de la **zona** con la intensidad de lluvia IMERG y el **estado** de la zona (humedad del suelo, días desde la última activación, El Niño costero). P2 (*dónde*) ordena las 17 quebradas por su historia y su terreno. Las tablas 0 a 3 siguen vigentes como base; las tablas 4 a 6 son las del modelo v3 y de la entrega al dashboard.'));
c.push(P('**Todas las tablas están hechas.**'));
c.push(table([1900, 2300, 1500, 1500, 2160], ['Tabla', 'Una fila es…', '¿Cambia en el tiempo?', 'Estado', 'Para qué sirve'], [
  ['0. Catálogo de eventos', 'Una quebrada que se activó en un evento', 'No (se le agregan filas)', 'Hecha, versión 1 (130 filas)', 'Fuente de verdad: de aquí salen las etiquetas'],
  ['1. Quebradas', 'Una quebrada', 'No', 'Hecha (17 quebradas)', 'Terreno de cada quebrada'],
  ['Auxiliar: pesos IMERG', 'Una quebrada × una celda de IMERG', 'No', 'Hecha (23 filas, 5 celdas)', 'Promediar la lluvia sobre la quebrada'],
  ['2. Lluvia horaria', 'Una quebrada en una hora', 'Sí, cada hora', 'Hecha (740 mil filas)', 'Lluvia reciente, suelo mojado y contexto de la temporada'],
  ['3. Tabla del modelo anterior', 'Una quebrada, una hora y un horizonte', 'Sí', 'Hecha (2.86 millones de filas)', 'Modelo por quebrada (v1/v2); queda como referencia'],
  ['4. Eventos de lluvia (v3)', 'Un evento de lluvia IMERG en la zona', 'Sí (cada evento)', 'Hecha (1 626 eventos)', 'Unidad de evaluación del v3 (TSS por evento)'],
  ['5. Zona horaria (v3, P1)', 'La zona en una hora y un horizonte', 'Sí, cada hora', 'Hecha (171 mil filas)', 'Lo que entra a P1: intensidad + estado + etiqueta de zona'],
  ['6. Salida al dashboard (v3)', 'Una quebrada, una hora y un horizonte', 'Sí, cada hora', 'Hecha (script y ejemplo 2022-23)', 'Lo que recibe el dashboard: probabilidad, índice y nivel'],
]));
c.push(gap());

c.push(H2('Qué cambió en la versión 3 (modelo v3)'));
for (const t of [
  '**Nuevo modelo en dos piezas.** P1 = la ZONA (no cada quebrada), con la intensidad de lluvia IMERG (máximos de 1/3/6 h y lluvia de 24–72 h) más tres variables de **estado** conocidas en *t*: humedad del suelo ERA5-Land (con 5 días de retraso), días desde la última activación catalogada y el último ICEN publicado. P2 = historia + terreno de cada quebrada.',
  '**Se mide como la literatura: por EVENTO de lluvia** (tabla 4), con el TSS (aciertos − falsas alarmas). Resultado fuera de muestra: TSS 0.49 (IC 90 % 0.15–0.70); el umbral ISAAC de SENAMHI aplicado a IMERG da −0.13 y el modelo anterior 0.15.',
  '**Etiquetas v2:** las horas vagas del catálogo («la tarde») se tratan como un rango; archivos `etiquetas_horarias_v2_H*.parquet` (las v1 no se tocan).',
  '**Salida al dashboard (tabla 6)** con dos niveles: **M3 por defecto** (rojo solo si además hubo lluvia IMERG reciente) y el nivel original de v3 como referencia.',
  '**Datos nuevos:** ERA5-Land y ERA5 vía Open-Meteo (sin credenciales), ICEN (IGP/ENFEN), IMERG Early diario 2001–2026 (Perú y norte de Chile), catálogo multizona (INDECI, INGEMMET, NASA COOLR).',
  '**Probado y descartado:** umbral por régimen de El Niño, ERA5 como variable, modelo diario con eventos de otras zonas (donantes), más positivos de quebradas vecinas (M1). Detalle en `modelo/v3/RESUMEN.md` y `modelo/v3_1/RESUMEN.md`.',
]) c.push(B(t));

c.push(H2('Qué cambió en la versión 2'));
for (const t of [
  '**Todas las tablas están hechas.** Antes las tablas 1, 2, 3 y la de pesos figuraban como «por hacer».',
  '**17 quebradas finales** (antes «unas 20»). Quedaron fuera Huaycoloro y Río Seco (cuenca grande fuera del recorte), Los Laureles (probable Chaclacayo) y tres sin ubicación.',
  '**DEM: FABDEM** en lugar de Copernicus DEM (FABDEM quita edificios y árboles).',
  '**Variables de terreno de la v1: solo `area_km2` (en log10) y `pendiente_media`.** La susceptibilidad de INGEMMET, Melton y AlphaEarth quedaron fuera de la v1 (motivos en la tabla 1).',
  '**Retraso de la lluvia:** la fila de la hora *t* usa solo lluvia con etiqueta hasta *t* − 5 h (4 h de latencia + la hora que debe estar completa). Antes decía *t* − 4 h.',
  '**25 variables de lluvia calculadas; 13 entran al modelo final** (más 2 de terreno y el horizonte H).',
  '**Etiquetas:** regla nueva (paso 9.2) para no tratar como «cero seguro» los días con huaico solo fuera de las 17 quebradas.',
  '**Fuentes:** IMERG Final y ERA5 se usaron para validar; hallazgos en la sección de fuentes.',
]) c.push(B(t));

c.push(H2('El flujo completo, contado como historia'));
c.push(P('Hay tres caminos que corren por separado y al final se juntan en una sola tabla: los **eventos** (cuándo hubo huaico), el **terreno** (cómo es cada quebrada) y la **lluvia** (cuánto llovió cada hora).'));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new ImageRun({ type: 'png', data: fs.readFileSync('flujo.png'), transformation: { width: 576, height: 443 }, altText: { title: 'Flujo de datos', description: 'Tres caminos (terreno, lluvia, eventos) que se juntan en la tabla 3', name: 'flujo' } })] }));
c.push(P('Los polígonos alimentan dos cosas: el terreno de la tabla 1 y los pesos con que se promedia la lluvia. Abajo, el mismo flujo paso a paso.'));
c.push(P('**Camino A — los eventos (hecho, versión 1)**'));
for (const t of [
  'Buscamos en reportes de INDECI y en la prensa cada vez que se activó una quebrada en Chosica. Anotamos el día, la hora, la quebrada y de dónde salió el dato. Eso es el **catálogo** (tabla 0).',
  'Un script lee el catálogo y marca, para cada quebrada y cada hora, si en las próximas H horas hubo huaico (1), si no sabemos de ninguno (0) o si esa hora es dudosa y no se usa (vacío). Esas son las **etiquetas**.',
]) c.push(N(t, 'pasosA'));
c.push(P('**Camino B — el terreno (hecho, una sola vez)**'));
for (const t of [
  'Bajamos el **DEM** (FABDEM), un mapa donde cada cuadradito de 30 × 30 m guarda la altura del suelo.',
  'Con esas alturas la computadora sigue el camino que haría una gota de agua cuesta abajo (dirección de flujo D8) y encuentra los cauces. Marcamos el punto de salida (*pour point*) de cada quebrada y obtenemos su **polígono**: el contorno de toda la zona que drena hacia ahí (*watershed delineation*, delimitación de cuencas).',
  'Usamos cada polígono como un molde de galletas: lo ponemos encima del DEM y calculamos lo que queda adentro (área, pendiente promedio, cotas). Eso es la **tabla 1**.',
  'También ponemos el polígono encima de la grilla de IMERG y anotamos qué parte de la quebrada cae en cada celda. Eso es la **tabla de pesos**.',
]) c.push(N(t, 'pasosB'));
c.push(P('**Camino C — la lluvia (cambia cada hora)**'));
for (const t of [
  'Bajamos IMERG Early para la zona, de diciembre de 2014 a abril de 2026 (solo los meses diciembre–abril). Viene cada 30 minutos; juntamos cada par de medias horas para tener lluvia por hora, en hora local.',
  'Para cada quebrada y cada hora, promediamos la lluvia de las celdas que la tocan usando los pesos.',
  'Con esa lluvia por hora calculamos los resúmenes: cuánto llovió en las últimas 3 h, 24 h, 14 días, etc. Como IMERG Early llega con ~4 h de retraso, en la hora *t* solo usamos lluvia con etiqueta hasta *t* − 5 h, igual que pasará en la vida real. Hay una prueba automática que cambia toda la lluvia posterior y exige que las variables no se muevan.',
  'Las etiquetas del paso 2 se pegan en la tabla 3.',
]) c.push(N(t, 'pasosC'));
c.push(P('**Se juntan los tres caminos**'));
for (const t of [
  'Unimos la tabla 2 con la tabla 1 por el código de la quebrada: cada fila de una hora «hereda» el terreno de su quebrada.',
  'Repetimos cada fila 4 veces, una por horizonte (3, 6, 12 y 24 h), con su etiqueta correspondiente. Quedan solo diciembre–abril y se descartan las filas con etiqueta vacía. Eso es la **tabla 3**, la que entra al modelo.',
]) c.push(N(t, 'pasosD'));

// ---- Tabla 0
c.push(H2('Tabla 0 — Catálogo de eventos (catalogo_huaicos_chosica.csv)'));
c.push(P('**Estado: hecha, versión 1.** Tiene 130 filas entre febrero de 2015 y febrero de 2026, en **26 fechas distintas**: 99 filas de Lurigancho-Chosica (19 fechas) y 31 de distritos vecinos. **Una fila = una quebrada que se activó en un evento**: si en un aguacero se activaron 10 quebradas, son 10 filas.'));
c.push(P('Ojo con la columna `quebrada`: guarda el nombre tal como lo escribió la fuente. A veces es la quebrada («Quirio») y a veces el barrio donde llegó el huaico («Santa María»). Por eso hay 30 nombres distintos en Chosica. **Usa siempre `terreno/alias_catalogo.csv`** (nombre del catálogo → `quebrada_id`): ahí se resuelve, por ejemplo, Inca Kola y Moyopampa → carossio; Tarazona y Nicolás de Piérola → quirio; Yanacoto → santa_maria; San Antonio de Pedregal → pedregal; Rayos de Sol → corrales.'));
c.push(table([1700, 3200, 2160, 2300], ['Columna', 'Qué guarda', 'Ejemplo', 'De dónde sale'], [
  ['id', 'Código del registro', 'EV036', 'Lo pone el script'],
  ['fecha', 'Día del huaico', '2015-03-23', 'La fuente'],
  ['hora_texto', 'Lo que dice la fuente sobre la hora, copiado tal cual', '«a las 15:30 horas aproximadamente»', 'La fuente'],
  ['hora_inicio, hora_fin', 'Ventana donde creemos que ocurrió (hora local)', '15:10 / 15:55', 'Lectura de hora_texto'],
  ['referencia_hora', 'Qué representa esa hora: el huaico, la lluvia, la publicación de la noticia o no hay hora', 'huaico', 'El script, por palabras clave'],
  ['quebrada', 'Nombre normalizado (se unifican escrituras: «Carosio» → «Carossio»)', 'Quirio', 'La fuente + limpieza'],
  ['sector', 'Barrio, kilómetro o referencia del lugar', 'Carretera Central km 25', 'La fuente'],
  ['distrito', 'Distrito', 'Lurigancho-Chosica', 'La fuente'],
  ['en_piloto', '¿Es de Lurigancho-Chosica? (99 filas son True; ojo: Huaycoloro, Río Seco y Los Laureles están marcadas True pero el piloto las ignora)', 'True', 'El script'],
  ['conf_temporal', 'Qué tan segura es la hora. **A** = hora exacta escrita; **B** = aproximada o parte del día; **C** = solo la fecha', 'A', 'Revisión'],
  ['conf_espacial', 'Qué tan seguro es el lugar. **A** = nombran la quebrada; **B** = nombran un barrio que se puede asociar a una quebrada; **C** = solo el distrito', 'A', 'Revisión'],
  ['usable_horario', '¿Sirve para el modelo hora por hora? Sí, si es de Chosica, tiene quebrada, confianza A o B y la hora apunta al huaico (70 filas, 16 fechas)', 'True', 'El script'],
  ['dudoso', 'Si una fuente oficial puso en duda que fuera huaico (13 filas, todas del 25/02/2019)', '«INDECI: no es huaico, es agua»', 'Revisión'],
  ['fuente, url', 'De dónde salió y el link', 'INDECI N° 339', 'La fuente'],
  ['notas', 'Comentarios y contradicciones entre fuentes', '—', 'Revisión'],
]));
c.push(gap());
c.push(P('**Cobertura despareja.** 2015, 2017 y 2023 concentran 19 de las 26 fechas, y no hay ninguna en las temporadas 2015-16, 2017-18, 2021-22 ni 2024-25. Es probable que sea vacío de búsqueda y no ausencia de huaicos (auditoría de etiquetas, paso 9.1).'));

c.push(H3('Etiquetas (etiquetas_horarias_H3 / H6 / H12 / H24.parquet)'));
c.push(P('De aquí salen las **etiquetas**: una fila por quebrada y hora (1 713 192 filas por horizonte, 17 quebradas, solo diciembre–abril). Columnas: `hora`, `quebrada_id`, `H`, `y`. La ventana es (t, t + H], con la hora en hora local y t = inicio de la hora.'));
c.push(table([1500, 7860], ['Valor de y', 'Qué significa'], [
  ['1', 'Hay un huaico registrado en esa quebrada dentro de la ventana (t, t + H].'],
  ['0', '«Sin noticia»: no sabemos de ningún huaico. **No es un cero seguro** (*PU learning*): puede haber habido uno que nadie reportó.'],
  ['vacío (NaN)', 'La hora no se usa: evento sin hora clara, sin nombre o sin ubicar (ese día queda vacío en las 17 quebradas), o la regla del paso 9.2 (abajo).'],
]));
c.push(gap());
c.push(P('**Ejemplo real: Quirio, 23/03/2015, huaico a las 15:10, H = 6.** La fila de la hora *t* mira la ventana (t, t + 6 h]. Las filas de las 10:00 a las 15:00 incluyen las 15:10, así que valen 1 (6 filas). Las filas de las 16:00 en adelante quedan vacías porque el huaico ya pasó. Con H = 3 son 3 filas con y = 1 (13:00 a 15:00) y con H = 24 son 24 (desde las 16:00 del día anterior). Ese día además hubo otros eventos sin quebrada ubicada, por eso las filas de las 07:00 a las 09:00 también salen vacías.'));
c.push(P('**El target se arma hora por hora, no por bloques.** Las filas con y = 1 de un mismo huaico quedan seguidas y forman un *bloque* de H horas; el modelo nunca ve el bloque, solo filas sueltas. El bloque se usa después para medir: un huaico cuenta como *detectado* si hubo al menos una alerta dentro de su bloque.'));
c.push(P('**Regla del paso 9.2.** Hay 10 fechas con huaico en el catálogo pero **ninguno en las 17 quebradas** (solo en Chaclacayo, Santa Eulalia, Huaycoloro…): 2015-02-20, 2017-01-15, 2017-01-21, 2017-02-01, 2020-01-29, 2021-03-07, 2023-02-17, 2023-03-15, 2023-03-17 y 2024-02-08. Esos días llovió fuerte a pocos kilómetros y sobre las mismas celdas de IMERG, así que un `y = 0` en las 17 quebradas sería dudoso. Al armar la tabla 3 los `y = 0` cuya ventana toca uno de esos días pasan a vacío; los `y = 1` se conservan. No se tocan los archivos de etiquetas originales (`comun.py`, función `poner_nan_dias_fuera_del_piloto`).'));
c.push(table([2340, 3510, 3510], ["Horizonte H", "Horas con y = 1", "Bloques de huaico"], [["3 h", "160", "53"], ["6 h", "316", "51"], ["12 h", "619", "50"], ["24 h", "1 219", "50"]]));
c.push(gap());
c.push(P('Un **bloque** es una racha de horas seguidas con y = 1 en una quebrada: equivale a un huaico. Solo **6 de las 12 temporadas** tienen al menos un evento (2014-15, 2016-17, 2018-19, 2019-20, 2022-23, 2025-26); 2014-15 aporta 22 de los 51 bloques de H = 6. Los 51 bloques son unas 14 tormentas, así que no son independientes.'));
c.push(H3('Etiquetas v2 (etiquetas_horarias_v2_H3 / H6 / H12 / H24.parquet) — las que usa el v3'));
c.push(P('Mismo formato que las anteriores (`hora`, `quebrada_id`, `H`, `y`). Cambia solo el trato de los **27 eventos con hora vaga** (`conf_temporal` = B) que generan positivos: se releyó cada fuente y se guardó un **rango** [hora_inicio, hora_fin] en `catalogo_huaicos_chosica/horas_B_v2.csv` (con url y cita). Reglas del rango: la hora concreta de la fuente se mantiene; si es vaga, mañana 06:00–11:59, tarde 12:00–18:59, noche 19:00–23:59, primeras horas 00:00–05:59, recortado en la hora de publicación de la nota; «reporte a las X» = [X − 1 h, X]. Nunca se usó lluvia satelital para decidir horas.'));
c.push(table([1700, 7660], ['Valor de y (v2)', 'Regla para un evento con rango [inicio, fin]'], [
  ['1', 'La ventana (t, t + H] contiene **todo** el rango'],
  ['vacío (NaN)', 'La ventana toca el rango solo en parte, o la hora está entre el inicio del rango y 24 h después del fin'],
  ['0', 'La ventana no toca el rango'],
]));
c.push(gap());
c.push(P('Para eventos con hora exacta, v2 da lo mismo que v1 (el script `etiquetas_v2.py` reproduce v1 bit a bit). Bloques de huaico (H = 3/6/12/24): v1 53/51/50/50 → v2 41/43/50/50: un rango vago de 7 h no cabe en una ventana de 3 o 6 h y esas horas pasan a vacío.'));

// ---- Tabla 1
c.push(H2('Tabla 1 — Quebradas (terreno, fija)'));
c.push(P('**Estado: hecha** (`terreno/quebradas.csv`, `.geojson` y `.kml`). **Una fila = una quebrada**: 17. Se calcula una sola vez, porque el terreno no cambia de una hora a otra. Todo sale de poner el polígono de la quebrada encima de un mapa y mirar lo que queda adentro.'));
c.push(table([1700, 3260, 2700, 1700], ['Columna', 'Qué es, en simple', 'Cómo se obtiene', '¿Entra al modelo?'], [
  ['quebrada_id', 'Código en minúsculas: quirio, carossio, pedregal…', 'Lo asignamos nosotros', 'Solo para unir tablas'],
  ['nombre, alias', 'Nombre y otros nombres con que aparece en el catálogo', 'Revisión a mano (`alias_catalogo.csv`)', 'No'],
  ['origen', '`candidata` (8): la cuenca salió de las 89 cuencas candidatas. `ubicada` (9): punto de salida puesto a mano', 'Notebooks de `terreno/`', 'No'],
  ['cuenca_id, salida_tipo', '`salida_tipo`: «confluencia» (10) o «apice» (7, la cuenca excluye el cono de deyección)', 'Delimitación con el DEM', 'No'],
  ['confianza_cuenca', '«alta» (16) o «baja» (1: huampani, su punto de salida se tuvo que mover 206 m)', 'Revisión', 'No'],
  ['salida_lat, salida_lon', 'Punto donde la quebrada llega al pueblo o al Rímac', 'Lo marcamos en el mapa', 'No'],
  ['area_km2', 'Qué tan grande es la cuenca', 'Se cuentan los cuadraditos del DEM dentro del polígono × 900 m² (30 × 30 m)', '**Sí**, como log10(area_km2)'],
  ['cuenca_pequena', '`True` si el área es menor de 0.3 km² (rosario, alto_peru, buenos_aires)', 'Regla sobre area_km2', 'No'],
  ['pendiente_media', 'Qué tan empinada es, en grados', 'Para cada cuadradito se compara su altura con la de sus vecinos; se promedia dentro del polígono', '**Sí**'],
  ['cota_max_m, cota_min_m', 'Altura máxima y mínima de la cuenca', 'Del DEM', 'No'],
  ['melton', 'Indicador clásico: (altura máx − mín) ÷ √área', 'Del DEM', '**No**: r = −0.92 con log10(área) y depende de si la salida es ápice o confluencia (un artefacto de la delimitación)'],
  ['largo_cauce_km', 'Largo del cauce principal', 'Del DEM', 'No: redundante con el área (r = 0.95)'],
  ['toca_borde', '¿La cuenca toca el borde del raster? Si sí, está incompleta', 'Control de calidad', 'No (hoy ninguna lo toca)'],
  ['columnas vec_ e img_', 'Susceptibilidad de INGEMMET: capa vectorial regional (`vec_`) e imagen nacional de 200 m (`img_`); porcentajes de clase ≥ 4 y 5, media y cobertura', 'Se pone el polígono sobre cada mapa', '**No (fuera de la v1)**. La capa vectorial satura (87–100 % en clase ≥ 4 en todas las cuencas); la imagen tiene 3–30 píxeles en las cuencas pequeñas; las dos casi no se correlacionan (r ≈ 0.1–0.3). Quedan para un experimento'],
]));
c.push(gap());
c.push(P('`log10(area_km2)` y `pendiente_media` tienen correlación −0.69 (Pearson) y −0.62 (Spearman), por debajo del criterio de 0.7. **Nunca** se usa como variable el número de días con huaico de cada quebrada (*data leakage*). **Aviso de diseño:** con solo 17 quebradas, estas dos variables identifican a cada quebrada, y con validación por temporada el modelo puede aprender su frecuencia histórica. Es un a priori legítimo, pero hay que tenerlo presente al interpretar.'));
c.push(P('**Las 17 quebradas:** quirio, santa_maria (incluye Yanacoto), california, la_cantuta, la_ronda, pedregal, carossio, corrales, chacrasana, santo_domingo, libertad, mariscal_castilla, rosario, el_vallecito, alto_peru, buenos_aires y huampani. Áreas de 0.14 km² (rosario) a 13.9 km² (la_cantuta); pendiente media de 27° a 36°.'));

// ---- pesos
c.push(H2('Tabla auxiliar — Pesos IMERG (fija)'));
c.push(P('**Estado: hecha** (`lluvia/pesos_imerg.csv`, 23 filas). Una celda de IMERG mide ~11 × 11 km y una quebrada mide entre 0.1 y 14 km², así que una quebrada puede caer en una celda o repartida entre varias. Las 17 quebradas tocan solo **5 celdas**: quebradas con las mismas celdas comparten la misma lluvia, y el modelo las distingue por el terreno. Esta tabla guarda **qué parte de cada quebrada cae en cada celda**. No entra al modelo; sirve para calcular la lluvia de la tabla 2.'));
c.push(table([2340, 4680, 2340], ['Columna', 'Qué es', 'Ejemplo'], [
  ['quebrada_id', 'La quebrada', 'quirio'],
  ['lat_centro, lon_centro', 'Centro de la celda de IMERG', '−11.95, −76.65'],
  ['area_km2_en_celda', 'Cuántos km² de la quebrada caen en esa celda (se mide en UTM 18S, no en grados)', '7.4'],
  ['peso', 'Fracción **de la quebrada** que cae en esa celda. Los pesos de una quebrada suman 1', '0.75'],
]));
c.push(gap());
c.push(P('**Cómo se usa: promedio ponderado por área.** Si una quebrada de 20 km² tiene 15 km² en una celda donde llovió 30 mm y 5 km² en otra donde llovió 10 mm, su lluvia es 0.75 × 30 + 0.25 × 10 = 25 mm. En fórmula: `lluvia_quebrada(t) = Σ peso_i × lluvia_celda_i(t)`.'));
c.push(P('El peso es «qué % de la quebrada está en la celda», no «qué % de la celda cubre la quebrada».'));

// ---- Tabla 2
c.push(H2('Tabla 2 — Lluvia horaria (cambia cada hora)'));
c.push(P('**Estado: hecha** (`lluvia/lluvia_horaria_quebradas.parquet` con la lluvia por hora, y `lluvia/features_lluvia.parquet` con las variables). **Una fila = una quebrada en una hora**, solo diciembre–abril, de diciembre de 2014 a abril de 2026 (740 mil filas). No van a git; se regeneran con `python lluvia/features_lluvia.py`.'));
c.push(P('De dónde sale la lluvia: IMERG Early da una *tasa* en mm/h cada 30 minutos. Para tener la lluvia de una hora se multiplica cada media hora por 0.5 (lo que cayó en esos 30 min) y se suman las dos. La etiqueta de tiempo es el **inicio de la hora local** (UTC−5). Luego se promedia sobre la quebrada con los pesos.'));
c.push(P('**El retraso.** IMERG Early llega ~4 h tarde. Una variable de la fila *t* usa solo lluvia con etiqueta hasta *t* − 5 h. Ejemplo real: Quirio, 23/03/2015 a las 13:00, dos horas antes del huaico de las 15:10: el modelo ve `lluvia_3h = 0.0` porque la lluvia de las últimas horas todavía no llegó. Las ventanas incompletas quedan vacías.'));
c.push(table([1300, 1750, 2150, 2760, 1400], ['Grupo', 'Columna', 'Qué es, en simple', 'Cómo se calcula', '¿Entra al modelo?'], [
  ['Claves', 'quebrada_id, hora', 'La quebrada y la hora local de Perú (UTC−5)', 'Para unir con la tabla 1', 'No (identifican la fila)'],
  ['Lluvia reciente', 'lluvia_3h, lluvia_6h, lluvia_24h', 'Cuánto llovió últimamente, en mm', 'Suma de las últimas 3, 6 o 24 horas disponibles', 'Sí'],
  ['', 'int_max_24h', 'El golpe más fuerte del último día, en mm/h', 'La hora más lluviosa de las últimas 24', 'Sí'],
  ['', 'tendencia_3h', '¿Está arreciando o calmando?', 'Lluvia de las últimas 3 h menos la de las 3 h anteriores', 'Sí'],
  ['', 'horas_lluvia_24h', 'Si fue un chaparrón o lluvia de todo el día', 'Cuántas de las últimas 24 horas tuvieron al menos 0.1 mm', 'Sí'],
  ['Suelo mojado', 'lluvia_7d, lluvia_14d', 'Cuánto llovió los días anteriores', 'Suma de los últimos 7 o 14 días', 'Sí'],
  ['', 'lluvia_efectiva', 'Agua que «queda» en el suelo: la lluvia vieja cuenta menos que la nueva', 'Cada hora: lo de esa hora + 0.84^(1/24) × lo acumulado (olvido de 0.84 por día)', 'Sí'],
  ['', 'horas_desde_lluvia', 'Cuánto tiempo seco lleva', 'Horas desde la última hora con al menos 0.1 mm (tope 336 h)', 'Sí'],
  ['Contexto', 'lluvia_temporada', '¿La temporada viene fuerte o floja?', 'Suma desde el 1 de diciembre (la lluvia anterior no cuenta)', 'Sí'],
  ['', 'anomalia_14d', '¿Está lloviendo más de lo normal para esta fecha?', 'Percentil de lluvia_14d frente a la misma fecha (±7 días) de las temporadas anteriores; vacío en las 3 primeras temporadas', '**No** (decisión: fuera de la v1; queda la columna)'],
  ['Regional (D)', 'reg_max_24h', 'La mayor lluvia de 24 h entre las 5 celdas de la zona', 'Máximo de la suma de 24 h sobre las celdas IMERG', 'Sí'],
  ['', 'reg_max_3h_24h', 'El mayor golpe de 3 h del último día entre las 5 celdas', 'Máximo de las sumas móviles de 3 h en 24 h, sobre las celdas', 'Sí'],
  ['Intensidad (A)', 'max_3h_24h, max_3h_72h', 'El mayor golpe de 3 h en el último día o en 3 días', 'Máximo de las sumas móviles de 3 h', 'No (sin efecto claro)'],
  ['', 'horas_desde_lluvia_fuerte', 'Cuánto hace desde una hora fuerte', 'Horas desde la última hora con al menos 2 mm', 'No'],
  ['Humedad previa (B)', 'lluvia_48h, lluvia_72h', 'Lluvia de los últimos 2 y 3 días', 'Suma de 48 o 72 horas', 'No (**perjudicó**)'],
  ['', 'api_k70, api_k92', 'Humedad del suelo con olvido rápido (0.70 por día) y lento (0.92)', 'Igual que lluvia_efectiva con otro olvido', 'No (**perjudicó**)'],
  ['', 'dias_lluviosos_7d', 'Cuántos de los últimos 7 días fueron lluviosos', 'Bloques de 24 h con al menos 1 mm (de 7)', 'No (**perjudicó**)'],
  ['Contraste (C)', 'tendencia_24h, frac_24h_en_7d, lluvia_24h_sobre_api', 'Si el último día fue mucho o poco comparado con lo anterior', 'Lluvia 24 h menos la de las 24 h previas; lluvia 24 h ÷ (lluvia 7 d + 1); lluvia 24 h ÷ (lluvia efectiva + 1)', 'No (sin efecto claro)'],
]));
c.push(gap());
c.push(P('**Qué dijo la evidencia (pasos 5 y 6, con las etiquetas anteriores al paso 9.2):** el grupo regional ayudó (de ~3.4 a ~6.1 de *lift*, confirmado con 3 semillas y 3 tipos de modelo); la humedad previa perjudicó (el modelo se apoya en ella pero no generaliza entre temporadas); las demás no mostraron efecto claro. Con las etiquetas corregidas solo se repitió el modelo final: agregar el grupo regional a las variables originales sigue sumando (lift 8.9 → 10.9) y lo que más pesa son las restricciones físicas (lift 19.6). Las ablaciones por grupo no se han repetido todavía. Ojo: el grupo regional se identificó mirando las mismas 6 temporadas de prueba; falta validarlo con una temporada nueva.'));
c.push(P('El contexto se saca de la propia lluvia a propósito: el mes del año o el índice ONI no entran en el modelo base, porque la lluvia ya cuenta si es temporada fuerte. El índice de El Niño costero (ICEN) queda como experimento.'));

// ---- Tabla 3
c.push(H2('Tabla 3 — La tabla del modelo'));
c.push(P('**Estado: hecha** (`modelo/tabla3_modelo.parquet`, no va a git; se regenera con `python modelo/tabla3.py`). Se arma en dos pasos:'));
c.push(N('**Unir** la tabla 2 con la tabla 1 por `quebrada_id` y pegar las etiquetas. Cada fila horaria hereda el terreno de su quebrada.', 'pasosT3'));
c.push(N('**Repetir cada fila 4 veces**, una por horizonte, con una columna `H` (3, 6, 12, 24) y una sola columna `y`. Así se entrena **un solo modelo** para todos los horizontes, con una regla que obliga a que la probabilidad no baje cuando H sube (*monotone constraint* en XGBoost).', 'pasosT3'));
c.push(P('Ejemplo con valores reales: Quirio, 23/03/2015 a las 13:00 (el huaico fue a las 15:10). `anomalia_14d` está vacía porque es la primera temporada.'));
c.push(table([900, 700, 1050, 1150, 1150, 1100, 1100, 1110, 1100], ['H', 'y', 'lluvia_3h', 'lluvia_24h', 'lluvia_14d', 'lluvia_efectiva', 'reg_max_24h', 'log10_area_km2', 'pendiente_media'], [
  ['3', '1', '0.0', '0.435', '12.07', '6.99', '1.04', '0.992', '29.5°'],
  ['6', '1', '0.0', '0.435', '12.07', '6.99', '1.04', '0.992', '29.5°'],
  ['12', '1', '0.0', '0.435', '12.07', '6.99', '1.04', '0.992', '29.5°'],
  ['24', '1', '0.0', '0.435', '12.07', '6.99', '1.04', '0.992', '29.5°'],
], { size: 17 }));
c.push(gap());
c.push(P('**Tamaño: 2 861 040 filas** (12 temporadas, diciembre–abril, 17 quebradas, 4 horizontes; 717 189 / 716 483 / 715 071 / 712 297 por horizonte). Con todo el año serían ~8 millones, casi todas de temporada seca; todos los huaicos del catálogo caen entre enero y abril y se conservan al 100 %.'));
c.push(table([2300, 3200, 3860], ['Columnas', 'Cuáles', 'Para qué'], [
  ['Identifican la fila', '`hora`, `dia`, `temporada` («2014-15» = dic 2014–abr 2015), `quebrada_id`', 'No son variables. Sirven para identificar la fila y para separar entrenamiento y prueba **por temporada, nunca por filas**'],
  ['Horizonte y respuesta', '`H` (3, 6, 12, 24) y `y`', '`H` sí entra al modelo; `y` es lo que se predice'],
  ['**Variables del modelo final (15 + H)**', 'Lluvia (13): lluvia_3h, lluvia_6h, lluvia_24h, int_max_24h, tendencia_3h, horas_lluvia_24h, lluvia_7d, lluvia_14d, lluvia_efectiva, horas_desde_lluvia, lluvia_temporada, reg_max_24h, reg_max_3h_24h. Terreno (2): log10_area_km2, pendiente_media', 'Entran con **restricciones físicas**: más lluvia nunca baja el riesgo (más horas desde la lluvia, nunca sube); `tendencia_3h` y el terreno sin restricción'],
  ['Probadas, fuera del modelo', '`anomalia_14d`; grupos A, B, C (ver tabla 2); `hora_sen`, `hora_cos` (ciclo diario: la hora del día es conocida al predecir, pero es la única variable que no es de lluvia, pendiente de decidir); `lluvia_24h_x_log10area`, `int3h_x_pendiente` (interacciones lluvia × terreno)', 'Sin mejora clara o en pendiente'],
]));
c.push(gap());
c.push(P('**Cómo se evalúa:** *validación dejando una temporada afuera* (LOSO): se entrena con 11 temporadas y se prueba en la que quedó fuera, solo en las 6 con eventos (las tranquilas entran siempre al entrenamiento). El modelo es XGBoost con árboles pequeños (profundidad 2, 150 árboles) y pesos para compensar que los huaicos son muy raros.'));

// ---- Tabla 4 (v3)
c.push(H2('Tabla 4 — Eventos de lluvia (modelo v3)'));
c.push(P('**Estado: hecha** (`modelo/v3/A/fase_a_eventos.parquet`; se arma con `modelo/v3/comun_v3.py`). **Una fila = un evento de lluvia en la zona.** Es la unidad con que se evalúa el v3, como en la literatura de umbrales de lluvia. 1 626 eventos (diciembre–abril, 2014-15 a 2025-26), **12 disparadores**, 24 desconocidos y 1 día «ciego».'));
c.push(table([1900, 4200, 3260], ['Columna', 'Qué es', 'Cómo se calcula'], [
  ['inicio, fin', 'Primera y última hora lluviosa del evento (hora local)', 'Lluvia de la zona = máximo horario entre las 5 celdas IMERG; hora lluviosa = al menos 0.1 mm; un evento termina tras 6 h secas'],
  ['duracion_h, total_mm', 'Cuánto duró y cuánto llovió', 'Del evento'],
  ['max1, max3, max6', 'El golpe más fuerte en 1, 3 y 6 h', 'Máximo de las sumas móviles'],
  ['temporada', '«2022-23» = diciembre 2022 a abril 2023', '—'],
  ['disparador', '1 si hubo huaico de las 17 quebradas durante el evento o hasta 3 h después', 'Cruce con las etiquetas v2 (rangos)'],
  ['huaico_fin', 'Fin del rango del huaico (en disparadores)', 'La alerta solo puede usar lo anterior a esta hora'],
  ['tormenta', 'Agrupa huaicos de fechas a ≤ 2 días', 'Unidad del *bootstrap* para los intervalos'],
  ['desconocido', 'Evento sin huaico que toca un día con huaico sin hora o solo en vecinos: «sin huaico» no es confiable', 'Se excluye de la evaluación'],
]));
c.push(gap());
c.push(P('**Día ciego:** un día con huaico en el que IMERG no registró ningún evento de lluvia (23/01/2020). Cuenta como fallo obligatorio para cualquier método.'));

// ---- Tabla 5 (v3)
c.push(H2('Tabla 5 — Zona horaria (P1 del modelo v3)'));
c.push(P('**Estado: hecha** (se arma en `modelo/v3/final/modelo_final.py`, función `tabla_zona`). **Una fila = la zona en una hora y un horizonte H** (diciembre–abril; 42 816 horas × 4 H). La etiqueta de zona vale 1 si **alguna** de las 17 quebradas tiene y = 1 (v2), vacío si alguna está vacía y ninguna vale 1, y 0 si no.'));
c.push(table([1800, 3700, 2560, 1300], ['Columna', 'Qué es, en simple', 'Fuente y retraso', 'Monotonía'], [
  ['i1h, i3h, i6h', 'Lluvia de la última 1, 3 y 6 h disponible (máximo entre las 5 celdas)', 'IMERG Early; latencia 4 h (etiqueta ≤ t − 5)', '+'],
  ['i1h_max6, i3h_max6, i6h_max6', 'El máximo de las anteriores en las últimas 6 h disponibles', 'IMERG Early; latencia 4 h', '+'],
  ['p24h, p48h, p72h', 'Lluvia de 24, 48 y 72 h (máximo entre celdas)', 'IMERG Early; latencia 4 h', '+'],
  ['hum_suelo_5d', 'Humedad del suelo superficial (0–7 cm, m³/m³), media de las 5 celdas', 'ERA5-Land vía Open-Meteo; valor de t − 5 días (retraso real)', '+'],
  ['dias_activ', 'Días desde la última activación catalogada en las 17 quebradas (tope 3650)', 'Catálogo; solo fechas anteriores al día de t', 'sin restricción'],
  ['icen', 'Índice Costero El Niño (último publicado)', 'IGP/ENFEN; mes M − 2 desde el día 10, M − 3 antes', '+'],
  ['H', 'Horizonte (3, 6, 12, 24)', '—', '+'],
  ['y', 'Huaico en la zona en (t, t + H]', 'Etiquetas v2 de las 17 quebradas', '—'],
]));
c.push(gap());
c.push(P('**Por qué estas variables:** con IMERG, la intensidad sola no supera al azar (TSS 0.01–0.23); la combinación con el **estado** sí (TSS 0.49). Sin `dias_activ` el TSS baja a 0.34: parte de la señal son las **rachas** de huaicos. Hiperparámetros fijados de antemano (profundidad 2, 150 árboles).'));

// ---- Tabla 6 (v3)
c.push(H2('Tabla 6 — Salida al dashboard (modelo v3, nivel M3 por defecto)'));
c.push(P('**Estado: hecha.** Script: `modelo/v3_1/entrega/entrega_dashboard.py` (usa el modelo v3 sin cambios de `modelo/v3/final/`). Ejemplo fuera de muestra: `modelo/v3_1/entrega/ejemplo_2022_23_m3.csv` (temporada 2022-23 completa, 246 432 filas). **Una fila = una quebrada en una hora y un horizonte.**'));
c.push(table([1800, 4600, 2960], ['Columna', 'Qué es', 'Ejemplo'], [
  ['quebrada_id', 'Una de las 17 quebradas', 'quirio'],
  ['hora', 'Hora local (UTC−5) de inicio en que se emite la predicción', '2023-03-14 13:00'],
  ['H', 'Horizonte en horas', '3'],
  ['p_zona', 'P1: probabilidad de huaico en la zona en (t, t + H]', '0.7047'],
  ['p2_quebrada', 'P2: propensión de la quebrada (fija): (activaciones + 4 × p_terreno) ÷ (tormentas + 4)', '0.6250'],
  ['score', 'p_zona × p2_quebrada (para ordenar quebradas)', '0.4404'],
  ['indice_0_100', '100 × min(1, p_zona ÷ umbral rojo) × p2 ÷ máx(p2)', '100'],
  ['lluvia_6h_mm', 'Lluvia IMERG de las últimas 6 h disponibles (máximo entre celdas)', '0.53'],
  ['nivel', '**Nivel por defecto (M3)**: verde / amarillo / rojo', 'rojo'],
  ['nivel_v3', 'Nivel original del v3 (referencia)', 'rojo'],
]));
c.push(gap());
c.push(P('**Los dos niveles** (de la zona; las quebradas se ordenan por `score`):'));
c.push(table([1700, 4030, 3630], ['', '`nivel` = M3 (por defecto)', '`nivel_v3` (original)'], [
  ['Rojo', 'p_zona ≥ umbral rojo **y** lluvia_6h_mm > 0.1', 'p_zona ≥ umbral rojo'],
  ['Amarillo', 'p_zona ≥ umbral rojo sin lluvia reciente («condiciones favorables»), o umbral amarillo ≤ p_zona < umbral rojo', 'umbral amarillo ≤ p_zona < umbral rojo'],
  ['Verde', 'El resto', 'El resto'],
  ['Acierto del rojo (por evento)', '0.62 (8 de 13); TSS 0.44', '0.69 (9 de 13); TSS 0.49'],
  ['Horas en rojo (dic–abr)', '11.4 %', '15.0 %'],
]));
c.push(gap());
c.push(P('Umbrales por H en `modelo/v3/final/metadatos_final.json`: el rojo maximiza el TSS por evento; el amarillo es el de máximo acierto alcanzable (0.85; 0.9 es imposible porque un huaico no tuvo lluvia IMERG y otro no tuvo horas útiles). **Solo H = 3 h es una promesa de anticipación** (mediana 2 h antes del huaico); H = 6/12/24 describen la condición de la zona.'));

// ---- archivos derivados
c.push(H2('Archivos que genera el modelo'));
c.push(table([3300, 4560, 1500], ['Archivo', 'Qué contiene', '¿Va a git?'], [
  ['lluvia/datos/early/imerg_early_AAAA-MM.nc', 'IMERG Early recortado a la zona: un archivo por mes (tasa mm/h cada 30 min, UTC)', 'Sí (forzado, ~6 MB c/u)'],
  ['modelo/oof_restringido_todas.parquet', 'Probabilidad `p` «fuera de muestra» para las 2.88 millones de filas: cada temporada predicha por un modelo que no la vio. Columnas: hora, quebrada_id, H, y, temporada, p', 'No'],
  ['modelo/oof_restringido.parquet', 'Lo mismo solo para las 6 temporadas con eventos, con algunas variables extra', 'No'],
  ['modelo/salida/umbrales_niveles.csv', 'Por horizonte y nivel (amarillo, naranja, rojo): umbral, bloques detectados, anticipación, horas de alerta y falsos episodios por temporada', 'Sí'],
  ['modelo/salida/umbrales_calibracion.csv, umbrales_anticipacion.csv', 'Calibración de las probabilidades (Platt) y anticipación por bloque', 'Sí'],
  ['modelo/salida/diagnostico_eventos_H6.csv', 'Por cada bloque de huaico: percentil de su mejor puntaje, si se detectó, lluvia que el modelo vio y la que había caído', 'Sí'],
  ['modelo/salida/diagnostico_era5_ciegos.csv', 'Por bloque: lluvia de IMERG y de ERA5 antes del huaico (solo validación)', 'Sí'],
  ['modelo/salida/auditoria_etiquetas_*.csv', 'Cómo quedó cada fecha del catálogo en las etiquetas y los 44 días de lluvia extrema sin evento registrado', 'Sí'],
  ['modelo/salida/ingenieria_nan/', 'Resultados de cada corrida con las etiquetas corregidas (los anteriores quedan en `ingenieria/` y `salida_antes_nan/`)', 'Sí'],
  ['lluvia/salida/comparar_early_final.csv', 'Comparación mensual de IMERG Early, IMERG Final y ERA5 (4 meses)', 'Sí'],
  ['catalogo_huaicos_chosica/horas_B_v2.csv y etiquetas_horarias_v2_H*.parquet', 'Rangos de las horas vagas (con url y cita) y etiquetas v2', 'Sí'],
  ['modelo/v3/final/p1_b1.json, metadatos_final.json, p2_final.csv', '**Modelo v3 final**: P1 (XGBoost), variables en orden, fuentes, umbrales por H; P2 por quebrada', 'Sí'],
  ['modelo/v3_1/entrega/ejemplo_2022_23_m3.csv', 'Ejemplo para el dashboard (tabla 6), fuera de muestra', 'Sí'],
  ['modelo/v3/tabla_final.csv, RESUMEN.md, model_card_datos.md', 'Comparación de todos los métodos con IC 90 %, resumen por fase y ficha del modelo', 'Sí'],
  ['modelo/v3/D/catalogo_multizona.csv', 'Catálogo de flujos en Perú y Chile (INDECI 911, INGEMMET 27, NASA COOLR 65)', 'Sí'],
  ['modelo/v3_1/M1/casos_nuevos_zona.csv', '67 activaciones de quebradas vecinas e INDECI en la zona, para revisión', 'Sí'],
  ['modelo/v3/datos/raw/', 'IMERG Early diario 2001–2026 (Perú y norte de Chile), ERA5/ERA5-Land (Open-Meteo), ICEN, catálogos crudos', 'No (se regenera)'],
]));
c.push(gap());

// ---- Fuentes
c.push(H2('Fuentes consultadas'));
c.push(P('**La lluvia del modelo sale de IMERG Early; el resto de fuentes de lluvia sirven para validar.** Cada fuente mide la lluvia de forma distinta, así que antes de compararlas hay que llevarlas todas a **mm acumulados en una hora, en hora local**.'));
c.push(H3('Fuentes de lluvia'));
c.push(table([1500, 1650, 2050, 3000, 1160], ['Fuente', 'Quién · grilla · cada cuánto', 'Unidad y cómo pasarla a mm por hora', 'Lo que encontramos / limitaciones', 'Uso'], [
  ['**IMERG V07 Early**', 'NASA + JAXA (misión GPM), con satélites · 0.1° ≈ 11 × 11 km · 30 min', '**Tasa** en mm/h. Lo que cayó = valor × 0.5; se suman las dos medias horas. Llega ~4 h tarde', 'Menos certera en montaña. En 32 de 51 huaicos marcó menos de 0.1 mm en la quebrada en las 6 h previas, incluso sin retraso. Da ~2.3 veces lo de IMERG Final en los meses lluviosos, de forma estable entre años (4 meses). Una celda es mucho más grande que una quebrada. 23/03/2015: no vio lluvia fuerte cerca de las 14:30', '**Entrada principal del modelo**'],
  ['**IMERG V07 Final**', 'NASA + JAXA · igual que Early', 'Igual que Early. Corregida con pluviómetros; llega con meses de retraso', 'Tenemos 7 gránulos del 23/03/2015 y 4 meses completos (2019-02, 2021-02, 2023-03, 2024-02). Sirvió para descartar que Early derive en el tiempo. No sirve para alertar', 'Validar. **No entra al modelo**'],
  ['**ERA5** (reanálisis)', 'ECMWF (un modelo físico que reconstruye el clima pasado) · 0.25° ≈ 28 km · 1 hora', 'Variable `tp` en **metros** acumulados en la hora que **termina** en `valid_time` (UTC): × 1000 y hora local = valid_time − 6 h (inicio de hora)', 'Solo 2 puntos (CSV 2010–2012 y 2014–2026; falta 2013). Con días de retraso. Da mucha más lluvia que IMERG en 2014–2021 y menos desde 2022: su escala cambia entre años, no sirve como referencia de cantidad. Sus percentiles dentro de la misma hora sí ordenan los días de huaico mejor que IMERG', 'Validación. **No entra al modelo**'],
  ['**PISCOp_h**', 'SENAMHI · ~0.1° ≈ 10 × 10 km · 1 hora', '**mm acumulados en esa hora** (no es tasa). Desfase de +7 h respecto a la hora local (coherente con el ciclo diurno, sin probar)', 'Reparte el total diario de PISCO según el patrón horario de SATc. Solo tenemos 2015 y la celda de Quirio; su hora exacta es poco confiable. No se publica en tiempo real', 'Validar. **No entra al modelo**'],
  ['**SAT / SATc** (piezas de PISCOp_h)', 'SENAMHI · ~10 km · 1 hora', 'mm por hora', 'SAT = promedio de 3 productos satelitales (IMERG Early, PERSIANN-CCS, GSMaP), sin corregir. SATc = SAT corregido con 309 estaciones automáticas', 'Entender cómo se armó PISCOp_h'],
  ['**PISCO diario**', 'SENAMHI · ~10 km · 1 día', 'mm por día', '1981–2016. No dice a qué hora cayó la lluvia, y para un huaico eso importa mucho', 'Contexto histórico'],
  ['**Estación SENAMHI Chosica**', 'SENAMHI (MET PLU y HID EHMA; la HID HLG solo mide nivel del río) · un punto · 1 día', 'mm por día', 'Desde 1989. La columna horaria existe pero está vacía. **Pendiente pedir datos horarios de pluviómetros de la cuenca del Rímac**: es lo que más ayudaría a corregir IMERG', 'Validar IMERG día por día'],
  ['**Estaciones automáticas (CSV público)**', 'SENAMHI · puntos · 1 hora', 'mm por hora', 'No incluye Chosica; la más cercana es Matucana', 'Referencia; poco útil'],
  ['**CHIRPS**', 'UCSB / USGS · 0.05° ≈ 5 km · 1 día', 'mm por día', 'Grilla más fina, pero solo diaria. No se usó', 'Posible validación'],
  ['**ERA5 / ERA5-Land vía Open-Meteo** (v3)', 'ECMWF re-servido por Open-Meteo, sin credenciales · 0.25° / 0.1° · 1 hora', 'mm en la hora previa al *timestamp* (se re-etiqueta al inicio de la hora); humedad en m³/m³', 'Humedad del suelo 0–7 cm: **entra al v3** con 5 días de retraso. Precipitación, convectiva y agua precipitable: no mejoran ni como pronóstico perfecto (TSS 0.51). CAPE, índice K y Total Totals no están en Open-Meteo: requieren CDS', '**Humedad: entra al modelo**'],
  ['**IMERG V07 Early diario** (v3)', 'NASA · 0.1° · 1 día UTC', 'mm por día', '2001–2026 en Perú y norte de Chile, leído por rangos (9 249 días). Para la ficha de similitud y el modelo diario multizona (descartado)', 'Experimento'],
  ['**Open-Meteo pronóstico (IFS)**', 'ECMWF vía Open-Meteo · ~9 km · 1 hora', 'mm por hora', 'Es pronóstico, con su propio error; no hay archivo histórico para entrenar', 'Posible variable futura'],
  ['**GOES-16** (idea)', 'NOAA · ~2 km · 10 min', 'Temperatura de la nube (infrarrojo), no lluvia directa', 'No se usó. Veríamos tormentas que IMERG pierde y llega en minutos, pero solo existe desde 2017 (se perdería 2014-15)', 'Idea para después'],
]));
c.push(gap());
c.push(H3('Fuentes de eventos y terreno'));
c.push(table([1800, 1800, 3660, 2100], ['Fuente', 'Qué da', 'Lo que encontramos / limitaciones', 'Uso'], [
  ['**SINPAD / COEN** (INDECI)', 'Emergencias registradas', 'Solo 14 eventos clasificados como huayco en la zona entre 2012 y 2023, sin hora. No encontramos descarga pública en CSV: hay que pedirla a INDECI. Es la mejor vía para completar el catálogo', 'Cruzar con el catálogo (pendiente)'],
  ['**INDECI-COEN, reportes complementarios y prensa**', 'Eventos con hora y quebrada', 'Base del catálogo (2015–2026). Las horas a veces son de la lluvia o de la publicación, no del huaico', '**Tabla 0 (catálogo)**'],
  ['**INGEMMET, inventario de peligros geológicos**', 'Puntos con peligros geológicos', '286 registros en la zona, de distintos tipos (no son 286 huaicos). La fecha es la del estudio, no la del evento', 'Ubicar quebradas activas'],
  ['**INGEMMET, mapa de susceptibilidad**', 'Qué tan propenso es cada lugar, en 5 niveles', 'Regional; satura. Fuera de la v1 (ver tabla 1)', 'Columnas `vec_*` e `img_*`'],
  ['**FABDEM**', 'Altura del suelo sin edificios ni árboles', '30 × 30 m. Licencia CC BY-NC-SA 4.0: hay que citarlo. Reemplazó a Copernicus DEM GLO-30', 'Polígonos, área, pendiente (tabla 1)'],
  ['**ANA** (red hidrográfica) y láminas de **SIGRID/CENEPRED**', 'Cauces y mapas de peligros de referencia', 'Son referencias, no verdad absoluta. La capa correcta de ANA es la ALA Chillón-Rímac-Lurín. Documentos SIGRID 123, 14474, 6441, 1610 y 19950 (ubican Pedregal, Carossio, Corrales)', 'Ubicar y validar las quebradas'],
  ['**AlphaEarth** (Google)', '64 números que resumen cómo se ve cada lugar desde el satélite', 'No se usó: requiere Earth Engine autenticado (pendiente)', 'Experimento (no hecho)'],
  ['**ICEN** (IGP/ENFEN)', 'Índice de El Niño costero, mensual', 'Archivo oficial `met.igp.gob.pe/datos/ICEN.txt`. Llega con 2–3 meses de retraso. Como umbral por régimen no sirve; como variable de estado sí suma', '**Entra al v3**'],
  ['**SINPAD / INDECI (base 2003–2025)**', 'Emergencias por distrito y fecha', 'CSV local `BD_2003-2025_EMERGENCIAS.csv`: 911 huaicos en la vertiente árida, sin hora y con ubicación de distrito; las fechas pueden ser de registro', 'Catálogo multizona y M1 (descartados)'],
  ['**INGEMMET PERU_ALERTA**', 'Zonas críticas por activación de quebradas', 'Servicio en geocatmin.ingemmet.gob.pe (el de geocatminapp ya no existe); 1 585 puntos, solo 27 con fecha de evento', 'Catálogo multizona'],
  ['**NASA COOLR** (Global Landslide Catalog)', 'Deslizamientos con fecha y punto', '65 en Perú y Chile (2007–2016), sin hora', 'Catálogo multizona'],
  ['**SRTM 90 m** (OpenTopoData)', 'Altura del suelo', 'Relieve y pendiente por celda de 0.1° para la ficha de similitud', 'Experimento'],
  ['**GPM_MERGIR** (temperatura de nubes)', 'Infrarrojo 4 km cada 30 min', 'Prueba por OPeNDAP: antes de los huaicos «ciegos» no hay nubes frías; sí después de horas del catálogo que estaban mal asignadas. Llega con ~24 h de retraso', 'Prueba (no entra)'],
]));
c.push(gap());

// ---- Glosario
c.push(H2('Glosario'));
c.push(table([2400, 6960], ['Término', 'En simple'], [
  ['Quebrada / cuenca', 'La quebrada es el cauce seco por donde baja el huaico. Su cuenca es toda la zona del cerro cuya lluvia termina bajando por ese cauce, como un embudo'],
  ['Polígono', 'El contorno de la cuenca dibujado en el mapa: una lista de coordenadas'],
  ['DEM / FABDEM', 'Mapa de alturas: cada cuadradito guarda la altura del suelo en metros. FABDEM le quita edificios y árboles'],
  ['*Watershed delineation*', 'Delimitar cuencas: con el DEM se sigue el camino que haría una gota cuesta abajo y se juntan todos los cuadraditos que drenan al mismo punto de salida'],
  ['*Pour point*', 'El punto de salida de una cuenca. La cuenca depende de la dirección de flujo y de este punto, no del umbral de acumulación'],
  ['Grilla / celda', 'Las fuentes satelitales dividen el mapa en cuadrados y dan un solo valor de lluvia por cuadrado'],
  ['Promedio ponderado por área', 'Lluvia de la quebrada = suma de la lluvia de cada celda × qué parte de la quebrada cae en ella'],
  ['Susceptibilidad', 'Qué tan propenso es un lugar a tener huaicos solo por su terreno, sin contar la lluvia'],
  ['Peligro / riesgo', 'Peligro = susceptibilidad + lluvia (lo que predice el modelo). Riesgo = peligro + gente y casas expuestas (lo calcula el score)'],
  ['Latencia / retraso', 'Cuánto tarda un dato en estar disponible después de medido. IMERG Early: ~4 h. En el modelo, la fila *t* solo usa lluvia hasta *t* − 5 h'],
  ['Reanálisis', 'Un modelo físico que reconstruye el clima del pasado (ERA5). No es una medición directa'],
  ['Horizonte (H)', 'Cuántas horas hacia adelante mira la predicción: 3, 6, 12 o 24'],
  ['Etiqueta (y)', 'La respuesta que el modelo aprende: 1 si hubo huaico en las próximas H horas'],
  ['Bloque', 'Racha de horas seguidas con y = 1 en una quebrada: equivale a un huaico'],
  ['*PU learning*', 'Aprender cuando los «0» no son seguros: que nadie reportó un huaico no significa que no hubo'],
  ['Presupuesto de alertas', 'Cuántas horas de alerta se permite el modelo: «1 alerta cada 100 h» = marcar el 1 % de puntajes más altos. Sirve para comparar modelos con la misma vara'],
  ['Detectado', 'Un bloque está detectado si hubo al menos una alerta dentro de él, es decir, antes del huaico'],
  ['AUPRC y *lift*', 'AUPRC: nota global (0 a 1) de qué tan arriba pone el modelo las horas de huaico. *Lift* = AUPRC ÷ la nota que sacaría el azar; «lift 10» = 10 veces mejor que el azar'],
  ['LOSO (validación por temporada)', 'Entrenar con 11 temporadas y probar en la que quedó fuera, repitiendo con cada una. Nunca se valida por filas sueltas: horas vecinas se parecen demasiado'],
  ['Monotonía', 'Regla que obliga al modelo a que más lluvia nunca baje el riesgo (y que el riesgo no baje al subir H)'],
  ['Fuera de muestra (OOF)', 'Predicción de una temporada hecha por un modelo que no la vio al entrenar'],
  ['Calibración', 'Ajustar las probabilidades para que «5 %» ocurra el 5 % de las veces. Aquí salen muy bajas y solo sirven para ordenar'],
  ['*Train/serve skew*', 'Entrenar con un dato que no existirá al momento de predecir. Por eso PISCOp_h, ERA5 e IMERG Final no entran al modelo'],
  ['*Data leakage*', 'Darle al modelo una pista que ya contiene la respuesta, como el número de huaicos de cada quebrada'],
  ['Pre-entrenamiento', 'Enseñarle primero al modelo con huaicos de lugares parecidos y después ajustarlo con Chosica'],
  ['Evento de lluvia', 'Racha de horas con lluvia (al menos 0.1 mm) en la zona, separada de la siguiente por 6 h secas'],
  ['Evento disparador', 'Evento de lluvia con un huaico durante el evento o hasta 3 h después'],
  ['TSS', 'Aciertos menos falsas alarmas (POD − POFD): 0 = azar, 1 = perfecto. Es la métrica de la literatura de umbrales de lluvia'],
  ['POD / POFD', 'POD: % de huaicos con alerta (acierto). POFD: % de eventos sin huaico con alerta (falsas alarmas)'],
  ['Variables de estado', 'Lo que describe cómo está la zona antes de la lluvia: humedad del suelo, días desde la última activación, El Niño costero'],
  ['Umbral rojo / amarillo', 'Rojo: el que maximiza el TSS. Amarillo: el que logra el máximo acierto posible'],
  ['Nivel M3', 'Nivel por defecto del dashboard: el rojo exige además lluvia IMERG reciente; si no hay, se muestra amarillo («condiciones favorables»)'],
  ['Umbral ISAAC', 'Curva intensidad–duración de SENAMHI para Cusipata (I = 1.57 D^−0.047 mm/h), calibrada con pluviómetro; con IMERG no funciona'],
  ['Donantes / MESS', 'Donantes: eventos de otras zonas parecidas usados para entrenar. MESS: índice que dice si una zona cae dentro del rango de condiciones de Chosica'],
]));
c.push(gap());

// ---- Pendientes
c.push(H2('Pendientes y decisiones abiertas'));
for (const [t, d] of [
  ['Delimitar las cuencas con el DEM y cruzar los cauces con los nombres del catálogo', true],
  ['Decidir qué nombres son quebradas y cuáles barrios (resuelto en `alias_catalogo.csv`)', true],
  ['Confirmar el distrito de California (Chosica, incluida) y Los Laureles (probable Chaclacayo, excluida)', true],
  ['Elegir las quebradas finales: 17 del piloto', true],
  ['Descargar IMERG Early 2014–2026 para la zona', true],
  ['Generar etiquetas para 3, 6, 12 y 24 h', true],
  ['Filtrar a diciembre–abril', true],
  ['Re-correr el modelo restringido con las etiquetas corregidas del paso 9.2 (versión rápida)', true],
  ['Re-correr la cadena completa del modelo anterior con las etiquetas corregidas (reemplazado por el v3)', false],
  ['Modelo v3 por evento con estado (humedad, días desde activación, ICEN); verificaciones; modelo final y entrega al dashboard con nivel M3', true],
  ['Etiquetas v2 (horas vagas como rango)', true],
  ['Probar ICEN, ERA5 y eventos de otras zonas (donantes)', true],
  ['Revisar los 67 casos de quebradas vecinas e INDECI (`modelo/v3_1/M1/casos_nuevos_zona.csv`)', false],
  ['Credenciales del CDS (`.cdsapirc`) para probar CAPE, índice K y Total Totals', false],
  ['Earth Engine para AlphaEarth y suelo desnudo (Sentinel-2)', false],
  ['Flujo en tiempo real de activaciones (INDECI o municipio): lo necesita la variable `dias_activ` en operación', false],
  ['Pedir a INDECI/COEN el registro de emergencias con fecha y revisar los 44 días de lluvia extrema sin evento; cruzar con los 14 eventos de SINPAD', false],
  ['Buscar eventos de 2016, 2018, 2021, 2022, 2024 y 2025 (probable vacío de búsqueda)', false],
  ['Conseguir datos horarios de pluviómetros de SENAMHI en la cuenca del Rímac; confirmar si la estación HID EHMA de Chosica tiene datos horarios desde 2021', false],
  ['Confirmar el desplazamiento horario de PISCOp_h (+7 u +8 h)', false],
  ['Revisar febrero de 2025 en IMERG Final (temporada 2024-25: muy lluviosa en Early y sin huaicos catalogados)', false],
  ['Decidir si el ciclo diario (hora del día) entra al modelo', false],
  ['Validar con una temporada nueva (2026-27) o contra SILVIA', false],
  ['Pasar el entrenamiento y la tabla a SAS Viya (los entornos cierran a fin de octubre)', false],
  ['Armar el catálogo regional para el pre-entrenamiento (hecho en v3: no mejora con los datos disponibles)', true],
]) c.push(CHK(t, d));

const doc = new Document({
  creator: 'Camilo', title: 'Diccionario de datos — Modelo de alerta de huaicos (Chosica)',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 22 }, paragraph: { spacing: { after: 160, line: 259, lineRule: 'auto' } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { bold: true, size: 32 }, paragraph: { keepNext: true, spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { bold: true, size: 26 }, paragraph: { keepNext: true, spacing: { before: 280, after: 100 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { bold: true, size: 24 }, paragraph: { keepNext: true, spacing: { before: 240, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ...['pasosA', 'pasosB', 'pasosC', 'pasosD', 'pasosT3'].map(r => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] })),
  ] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } }, children: c }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync('nuevo.docx', b); console.log('ok', b.length); });

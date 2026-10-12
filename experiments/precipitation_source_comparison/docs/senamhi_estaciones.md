# Pluviómetros de SENAMHI y de las quebradas: qué se sabe y qué no

**Estado (12/10/2026): no se descargó ninguna serie de pluviómetros.** El entorno bloquea `www.senamhi.gob.pe` y `www.datosabiertos.gob.pe` (403 de la política de red), así que no pude abrir la plataforma, el portal de descarga ni el catálogo de datos abiertos. Lo de abajo sale de resúmenes de búsqueda y **no está verificado en las páginas oficiales**. No se simuló ninguna descarga.

## Qué es ISAAC (según lo único que apareció)
Una nota del MINAM describe a **ISAAC como la «Plataforma Espacial de Monitoreo de Lluvias Intensas en la Región Lima frente a la Activación de Quebradas»**, gestionada por SENAMHI, con **14 pluviómetros** en la región Lima que dan información **en tiempo real** de las partes bajas de las cuencas de los ríos Rímac y Lurín; SENAMHI tiene además **SILVIA** (movimientos en masa por lluvias intensas). Fuente: https://www.gob.pe/institucion/minam/noticias/917648-ministro-del-ambiente-plataformas-tecnologicas-del-sector-contribuyen-a-prevenir-los-impactos-del-fenomeno-el-nino (una sola fuente; una segunda búsqueda no la volvió a confirmar; **no encontré la URL oficial de ISAAC**).

## Estaciones pedidas
| Estación (nombre dado) | Quebrada del proyecto (inferida solo por el nombre) | Código / coordenadas / altitud | Variable y frecuencia | Periodo | Descarga | ¿Qué se necesita? |
|---|---|---|---|---|---|---|
| Carosio | carossio | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Castilla | mariscal_castilla (?) | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Libertad | libertad | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Pedregal Koica | pedregal | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| La Cantuta | la_cantuta | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Río Seco | (Río Seco está excluida del piloto: cuenca grande fuera del recorte) | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Quebrada Molle | ninguna segura (en el catálogo «Los Molles» está sin ubicar) | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Los Cóndores | sin asignar | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |
| Vizcachera | sin asignar | sin confirmar | sin confirmar | sin confirmar | sin confirmar | sin confirmar |

**Ninguna de las nueve apareció por nombre en fuentes públicas.** Lo más cercano, y lo que da pistas de que existen pluviómetros en las quebradas:
- Una nota de prensa de marzo de 2023 cita a un meteorólogo de SENAMHI: «las estaciones de Quirio y Carosio» tuvieron los mayores acumulados, 16 mm y 12 mm. La fuente exacta no quedó clara en la búsqueda; entre los resultados estaba https://andina.pe/agencia/noticia-lluvias-moderada-intensidad-activaron-quebradas-chosica-932430.aspx (**confirmar**).
- El alcalde de Lurigancho-Chosica dijo que, tras el ciclón Yaku (2023), cuentan **solo con 9 pluviómetros en 9 quebradas** (dato municipal; no se sabe si son los mismos de ISAAC).
- Un boletín de SENAMHI para las cuencas Chillón, Rímac y Lurín menciona las estaciones de lluvia **Ñaña, Chosica y Santa Eulalia**.
- SENAMHI tiene una estación meteorológica e hidrológica en Chosica (ya investigada antes por el proyecto: datos **diarios** desde 1989, columna horaria vacía) y, aparte, el nivel del Rímac en Chosica lo mide también la Dirección de Hidrografía de la Marina.
- El conjunto público de estaciones automáticas que ya revisó el proyecto no incluye Chosica; la más cercana es Matucana.

## Cómo se obtendrían los datos (lo que dicen las fuentes oficiales encontradas)
| Vía | Qué da | Condiciones (según resúmenes; **verificar vigencia**) | Fuente |
|---|---|---|---|
| Portal de descarga de datos (menú *Datos* de senamhi.gob.pe) | Series **diarias** por estación en archivo de texto (−99.9 = sin dato) | Requiere registrarse/iniciar sesión y aceptar términos | Tutorial: https://www.senamhi.gob.pe/mapas/descarga-datos/pdf/tutorial-para-la-descarga-de-datos.pdf |
| Solicitud formal de información hidrometeorológica (TUSNE) | Series por variable, estación, año y **escala horaria**, diaria o mensual | Pago: estación automática, horaria, 1 año/1 variable/1 estación = **S/ 348.45 (IGV incl.)** en el TUSNE 2021 y en un extracto del 2024 (no confirmado como vigente). Se pide por formato 1 (Gerente General) o formato 2 (director zonal) con constancia de pago | https://www.senamhi.gob.pe/pdf/trans/tusne_senamhi_2024.pdf |
| Solicitud para **estudiantes e investigadores** | La Dirección de línea define qué entregar | Según la directiva interna: **gratuita**, por vía electrónica, plazo máximo de **15 días hábiles** | https://web2.senamhi.gob.pe/load/file/00706SENA-62.pdf |
| Acceso a la información pública (Ley de Transparencia) | Lo que SENAMHI posee | Portal de Transparencia o mesa de partes; el costo de reproducción se liquida desde el 6.º día hábil | TUPA: https://www.senamhi.gob.pe/pdf/trans/tupa/tupa-senamhi.pdf |
| Catálogo nacional de datos abiertos | — | No encontré un conjunto de SENAMHI con precipitación horaria de estaciones | https://www.datosabiertos.gob.pe |

**Consecuencia:** lo que sí es público y descargable es la serie **diaria**; lo **horario** de estaciones automáticas parece requerir solicitud (gratuita para investigación según la directiva, o de pago según el TUSNE). Si hubiera que pagar, 9 estaciones × 12 años a S/ 348.45 serían unos S/ 37 600; por eso conviene la vía gratuita y acotar estaciones y años (ver `solicitud_senamhi.md`).

## Lo que SENAMHI ya ofrece sin pagar y no hemos evaluado
La memoria 2025 de SENAMHI dice que se generó la base grillada **PISCO horario**; el proyecto ya tiene PISCOp_h 2015 (solo 2015). No verifiqué licencia ni dónde se publica la versión más reciente.

# Sistema Inteligente de Verificacion de Licitaciones para Equipos Maritimos

## 1. Introduccion

### El problema

Las empresas fabricantes de equipos de tratamiento de liquidos para el sector maritimo (separadores de sentinas, plantas de aguas grises, sistemas de refuelling, etc.) se enfrentan a un proceso manual, lento y propenso a errores cada vez que participan en una licitacion.

Cuando un astillero o una petrolera publica una licitacion para un buque o plataforma offshore, el documento de requisitos tecnicos puede superar las 100 paginas y estar acompanado de mas de 15 apendices con especificaciones de materiales, electricidad, instrumentacion, pintura, calidad, certificaciones y normativa aplicable.

Por otro lado, las especificaciones del producto del fabricante estan repartidas en multiples documentos: hojas de datos de cada componente (bombas, calentadores, sensores, valvulas), planos dimensionales, listas de materiales y manuales.

El ingeniero que prepara la oferta debe comparar manualmente cada requisito de la licitacion contra las caracteristicas de su producto, identificar donde cumple, donde no cumple, y que modificaciones serian necesarias para cubrir los requisitos. Este proceso puede llevar dias o semanas, y un error u omision puede suponer la descalificacion de la oferta o un sobrecoste imprevisto durante la fabricacion.

### La solucion propuesta

Desarrollar un sistema basado en inteligencia artificial que automatice este proceso de verificacion. El sistema es capaz de:

1. **Leer y comprender** los documentos tecnicos del producto y de la licitacion, extrayendo la informacion relevante de forma estructurada.
2. **Comparar automaticamente** las caracteristicas del producto con los requisitos de la licitacion.
3. **Identificar gaps** (puntos donde el producto no cumple) y sugerir las modificaciones necesarias.
4. **Estimar el impacto economico** de cada modificacion para facilitar la elaboracion de la oferta.
5. **Generar un informe de cumplimiento** que el equipo de ingenieria puede revisar, ajustar y presentar al cliente.

---

## 2. Como funciona el sistema

### Paso 1: Ingestion de documentos

El usuario sube al sistema los documentos del producto (hojas de datos, especificaciones tecnicas) y los documentos de la licitacion (requisicion de materiales, especificaciones del paquete, hojas de datos del cliente, apendices).

El sistema acepta documentos en formato PDF y hojas de calculo (Excel), que son los formatos habituales en el sector.

### Paso 2: Extraccion inteligente de informacion

El sistema utiliza tecnologia de procesamiento de documentos para leer cada archivo y extraer la informacion tecnica relevante: caudales, presiones, temperaturas, materiales de cada componente, certificaciones, requisitos electricos, normas aplicables, etc.

Esta informacion se organiza en un formato estructurado y estandarizado que permite la comparacion automatica. Donde los documentos ya estan en formato tabular (como las hojas de evaluacion de ofertas o los checklists de cumplimiento), la informacion se extrae directamente sin necesidad de interpretacion.

Para los documentos mas complejos (especificaciones tecnicas en prosa, requisitos con multiples clausulas), el sistema utiliza modelos de inteligencia artificial de ultima generacion para interpretar el texto y extraer los requisitos individuales con su nivel de obligatoriedad (requisito obligatorio vs recomendacion).

### Paso 3: Comparacion y analisis de cumplimiento

Una vez extraida la informacion de ambos lados (producto y licitacion), el sistema ejecuta una comparacion automatica en tres niveles:

- **Comparacion directa**: Para parametros cuantificables (caudal, presion, temperatura, voltaje, grado de proteccion IP), el sistema verifica directamente si el valor del producto cumple o supera el requisito.

- **Comparacion de materiales y certificaciones**: El sistema conoce las jerarquias de materiales (por ejemplo, que el acero inoxidable 316L es superior al acero al carbono) y las equivalencias entre certificaciones, permitiendo evaluar automaticamente si un material o certificacion cubre el requisito.

- **Evaluacion asistida por IA**: Para requisitos complejos que requieren interpretacion tecnica (como "el equipo debe tener experiencia probada en al menos 3 instalaciones offshore"), el sistema utiliza inteligencia artificial para evaluar el cumplimiento basandose en el contexto completo de la documentacion.

### Paso 4: Identificacion de gaps y estimacion de costes

Para cada requisito donde el producto no cumple, el sistema genera:

- Una descripcion clara del gap (diferencia entre lo que se tiene y lo que se pide).
- Una propuesta de modificacion necesaria.
- Una estimacion del coste adicional que supondria esa modificacion.
- Un nivel de riesgo (bajo, medio, alto, o descalificante).

Las estimaciones de coste se basan en tablas de referencia configurables por el fabricante, que se van refinando con la experiencia de proyectos anteriores.

### Paso 5: Generacion de informes

El sistema produce un informe de cumplimiento que incluye:

- Una puntuacion global de cumplimiento (porcentaje).
- Un resumen ejecutivo con los gaps criticos.
- Una tabla detallada item por item, compatible con los formatos habituales de evaluacion de ofertas del sector.
- Un resumen economico del coste estimado de todas las modificaciones.

Este informe se puede descargar en formato Excel (compatible con las tablas de evaluacion de ofertas) y se puede revisar y ajustar antes de su inclusion en la propuesta.

---

## 3. Tecnologia utilizada

El sistema se apoya en las siguientes tecnologias:

- **Modelos de lenguaje de inteligencia artificial** (tipo ChatGPT/Claude) para la comprension e interpretacion de documentos tecnicos complejos. Estos modelos se utilizan a traves de sus APIs, sin necesidad de infraestructura de IA propia.

- **Procesamiento avanzado de documentos** para la extraccion de texto y tablas de PDFs tecnicos, preservando la estructura y relaciones entre los datos.

- **Base de datos con capacidad de busqueda semantica** que permite encontrar informacion relevante del producto aunque la terminologia utilizada sea diferente entre el fabricante y el cliente.

- **Interfaz web** accesible desde cualquier navegador, sin necesidad de instalar software adicional.

---

## 4. Beneficios esperados

| Aspecto | Situacion actual | Con el sistema |
|---------|-----------------|----------------|
| Tiempo de analisis por licitacion | Dias o semanas | Horas (revision incluida) |
| Riesgo de omisiones | Alto (proceso manual) | Bajo (revision sistematica) |
| Coste por analisis | Horas de ingenieria senior | Menos de 6 euros en servicios de IA |
| Trazabilidad | Documentos dispersos | Todo centralizado y auditable |
| Reutilizacion | Limitada | Las specs del producto se extraen una vez y se reutilizan en todas las licitaciones |
| Historico | No sistematizado | Base de datos con todas las comparaciones anteriores |

---

## 5. Alcance del proyecto

### Fase inicial (MVP)

El desarrollo inicial se centra en un tipo de producto concreto: **separadores de sentinas** (Oily Water Separators), utilizando como caso de prueba una licitacion real para una plataforma FPSO.

Se dispone de documentacion completa tanto del producto como de la licitacion, incluyendo la respuesta real del fabricante a la evaluacion tecnica, lo que permite validar la precision del sistema comparando sus resultados con los de un analisis humano real.

### Escalabilidad

La arquitectura del sistema esta disenada para incorporar progresivamente otras familias de productos (plantas de aguas grises, sistemas de refuelling, etc.) sin cambios estructurales. Cada nuevo producto requiere unicamente la carga de su documentacion tecnica.

---

## 6. Costes operativos

El sistema tiene costes operativos muy reducidos:

- **Coste por licitacion analizada**: Aproximadamente 5-6 euros en servicios de inteligencia artificial (extraccion de documentos + comparacion).
- **Infraestructura mensual**: Entre 95 y 200 euros (base de datos, servidor de aplicacion, APIs de IA), para un volumen estimado de 10 licitaciones al mes.
- **Sin coste de licencias de software**: Todo el sistema se construye con tecnologias de codigo abierto, a excepcion de los servicios de IA que se consumen bajo demanda (pago por uso).

---

## 7. Resultado esperado

Al finalizar el proyecto, el fabricante dispondra de una herramienta que le permite, en cuestion de horas en lugar de dias:

1. Subir los documentos de una nueva licitacion.
2. Obtener un analisis automatico de cumplimiento de su producto.
3. Identificar exactamente que modificaciones necesita y cuanto costarian.
4. Generar la documentacion de respuesta tecnica en el formato requerido por el cliente.

Esto se traduce en una **mayor competitividad** (ofertas mas rapidas y precisas), **menor riesgo** (menos omisiones y errores), y **mejor toma de decisiones** (visibilidad clara del coste real de cada licitacion antes de comprometerse).

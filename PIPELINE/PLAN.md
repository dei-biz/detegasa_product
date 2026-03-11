# Plan: Sistema de Compliance de Licitaciones con IA para Equipos Maritimos

## Contexto

DETEGASA fabrica equipos de tratamiento de liquidos para el sector maritimo (separadores de sentinas OWS, aguas grises, refuelling). Cuando reciben licitaciones de astilleros (ej: Keppel/HHI para FPSOs de Petrobras), necesitan verificar manualmente si sus productos cumplen con las especificaciones tecnicas, identificar gaps y calcular el coste de modificaciones.

**Problema**: Las especificaciones del producto estan repartidas en multiples PDFs (data sheets de componentes, diagramas, listas de materiales) y las licitaciones llegan como documentos extensos (99 paginas + 16 apendices). La comparacion manual es lenta, propensa a errores, y no escalable.

**Solucion**: Sistema que extrae especificaciones de PDFs a JSON estructurado, las almacena en PostgreSQL+pgvector, y usa LLMs para comparar automaticamente producto vs licitacion, generando un informe de compliance con gaps y estimaciones de coste.

**Alcance MVP**: Solo separadores de sentinas (OWS). Arquitectura preparada para multi-producto.

---

## Arquitectura General

```
                    +-------------------+
                    |  Frontend basico  |
                    |  (Streamlit)      |
                    +--------+----------+
                             |
                    +--------v----------+
                    |    FastAPI         |
                    |    Backend         |
                    +--+----+----+------+
                       |    |    |
            +----------+  +v+   +----------+
            |              |               |
     +------v------+ +----v-------+ +-----v-------+
     | Doc Parser  | | LLM Engine | |  Embedding  |
     | Docling/    | | Instructor | |  Service    |
     | PyMuPDF/    | | +Claude/GPT| | (API/Local) |
     | openpyxl    | +-----+------+ +------+------+
     +------+------+       |               |
            |         +----v-----+   +-----v------+
            |         | Langfuse |   | PostgreSQL |
            +-------->| (observ) |   | + pgvector  |
                      +----------+   +------------+
```

### Stack tecnologico

| Capa | Herramienta | Proposito |
|------|-------------|-----------|
| PDF parsing | **Docling** (IBM) + PyMuPDF fallback | Extraccion de texto y tablas con estructura |
| XLS/XLSX parsing | **openpyxl** / **xlrd** | Parseo directo de datos tabulares |
| Extraccion LLM | **Instructor** + Claude/GPT | Output Pydantic validado automaticamente |
| Embeddings | **OpenAI API** / **sentence-transformers** | Busqueda semantica via adapter |
| Base de datos | **PostgreSQL 16 + pgvector** | Almacenamiento + busqueda vectorial |
| Observabilidad | **Langfuse** | Tracking de costes, latencia, calidad LLM |
| Cache | **PostgreSQL** (tabla llm_cache) | Evitar reprocesar documentos |
| Backend | **FastAPI** | API REST async |
| Frontend | **Streamlit** | Interfaz web basica |

---

## Estructura de Carpetas del Plan

Cada modulo tiene su propia carpeta en `PIPELINE/` con un markdown detallado:

| # | Carpeta | Contenido |
|---|---------|-----------|
| 01 | `01_fundamentos` | Setup proyecto, Docker, config |
| 02 | `02_extraccion_pdf` | **Docling** + PyMuPDF fallback + parseo XLS/XLSX directo |
| 03 | `03_llm_adapters` | **Instructor** + adapters Claude/GPT + **Langfuse** + cache |
| 04 | `04_schemas_json` | Schemas Pydantic de producto, licitacion y compliance |
| 05 | `05_base_datos` | PostgreSQL + pgvector, migraciones Alembic |
| 06 | `06_embeddings` | Embeddings API/local, busqueda semantica |
| 07 | `07_motor_compliance` | Matchers deterministicos + semanticos + LLM |
| 08 | `08_estimacion_costes` | Modelo de costes por modificacion |
| 09 | `09_api_backend` | Endpoints FastAPI |
| 10 | `10_frontend` | App Streamlit |

---

## Estimaciones Temporales (Claude como programador)

| Fase | Modulos | Sesiones estimadas | Notas |
|------|---------|-------------------|-------|
| **Fase 1: Fundamentos** | 01, 04, 05, 03 | 2-3 sesiones | Setup, schemas, DB, LLM adapters |
| **Fase 2: Extraccion** | 02 | 2-3 sesiones | Docling + parseo XLS + tuning con PDFs reales |
| **Fase 3: Embeddings** | 06 | 1-2 sesiones | Adapter sencillo, integracion pgvector |
| **Fase 4: Compliance** | 07, 08 | 3-4 sesiones | Matchers + LLM comparator + costes |
| **Fase 5: API + Frontend** | 09, 10 | 2-3 sesiones | FastAPI + Streamlit |
| **Fase 6: Validacion** | - | 2-3 sesiones | Testing contra TBT real. Calibracion. |
| **TOTAL** | | **12-18 sesiones** | |

**Bottlenecks**: No es escribir codigo sino iterar prompts de extraccion, validar contra documentos reales, y obtener datos de costes de DETEGASA.

---

## Costes

### Por licitacion analizada (~430 paginas)

| Concepto | Coste |
|----------|-------|
| Extraccion LLM (~720K tokens) | ~$3.55 |
| Comparacion LLM (~375K tokens) | ~$2.03 |
| Embeddings (~700K tokens) | ~$0.01 |
| **Total por licitacion** | **~$5.60** |

*Con cache activo, relicitaciones del mismo producto cuestan solo la comparacion (~$2)*

### Infraestructura mensual (10 licitaciones/mes)

| Concepto | EUR/mes |
|----------|---------|
| PostgreSQL + pgvector | 25-100 |
| Hosting aplicacion | 20-50 |
| APIs LLM | ~50 |
| Langfuse (self-hosted) | 0 |
| **Total** | **~95-200** |

---

## Dependencias

```
# Parsing
docling                          # IBM PDF->structured (principal)
PyMuPDF                          # Fallback PDF (ya instalado)
pdfplumber                       # Tablas PDF
openpyxl, xlrd                   # XLS/XLSX directo

# LLM
anthropic, openai                # APIs
instructor                       # Extraccion estructurada garantizada
langfuse                         # Observabilidad LLM
tenacity                         # Reintentos

# Embeddings
sentence-transformers            # Embeddings locales (opcional)
tiktoken                         # Conteo de tokens

# Base de datos
sqlalchemy, asyncpg, alembic     # ORM + migraciones
pgvector                         # Extension vectorial

# Web
fastapi, uvicorn, python-multipart
streamlit, httpx

# Datos
pydantic, pandas
python-dotenv

# Testing
pytest, pytest-asyncio
```

---

## Documentos Criticos

| Documento | Ruta | Uso | Formato |
|-----------|------|-----|---------|
| Data sheets producto (56pp) | `DOCUMENTACION/I-FD-...-DTG-302-C.pdf` | Specs componentes | PDF (Docling) |
| Data sheets E&I (23pp) | `DOCUMENTACION/I-FD-...-DTG-301-IAB.pdf` | Specs electrico/instr. | PDF (Docling) |
| Material Requisition (99pp) | `ESPECIFICACION DE CLIENTE/I-RM-...-KES-301_REVA.pdf` | Doc principal licitacion | PDF (Docling) |
| Package Spec (22pp) | `ESPECIFICACION DE CLIENTE/APPENDIX 2_/.../OWS PACKAGE.pdf` | Requisitos tecnicos | PDF (Docling) |
| Datasheet cliente (4pp) | `ESPECIFICACION DE CLIENTE/APPENDIX 1_/.../KES-303_REVA.pdf` | Condiciones operativas | PDF (Docling) |
| **TBT (ground truth)** | `ESPECIFICACION DE CLIENTE/APPENDIX 12_/.../TBT.xlsx` | **Validacion sistema** | **XLSX (directo)** |
| **E&I Compliance Sheet** | `ESPECIFICACION DE CLIENTE/APPENDIX 10_/.../DETEGASA.XLS` | **Segunda validacion** | **XLS (directo)** |
| **VDRL** | `ESPECIFICACION DE CLIENTE/APPENDIX 5_/.../VDRL.xls` | Lista documentos vendor | **XLS (directo)** |
| **Technical Clarification** | `ESPECIFICACION DE CLIENTE/APPENDIX 6_/.../TC_Detegasa.xlsx` | Clarificaciones tecnicas | **XLSX (directo)** |

---

## Validacion

- Usar la **Technical Bid Evaluation Table** (Appendix 12) como ground truth
- Usar el **E&I Technical Compliance Check Sheet** (Appendix 10) como segunda referencia
- **Langfuse** para trackear precision de extraccion y comparacion
- Objetivo: >85% acuerdo en items estructurados, >70% en items de juicio

## Riesgos y mitigaciones

| Riesgo | Mitigacion |
|--------|-----------|
| Paginas PDF con solo imagenes/diagramas | Docling detecta imagenes; marcar para revision manual |
| Archivos .xls legacy | xlrd para formato antiguo |
| Encoding Windows (cp1252) | Forzar UTF-8, normalizar en text_cleaner |
| Tablas multi-pagina en PDFs | Docling las maneja mejor que PyMuPDF |
| Estimaciones de coste imprecisas | Empezar con rangos conservadores, calibrar con datos DETEGASA |
| Variabilidad en formato de licitaciones | Prompts resilientes + deteccion de formato + fallbacks |
| Archivos DWG (CAD drawings) | Fuera de alcance, no procesables. Marcar para revision manual |

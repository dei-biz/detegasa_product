# Separador Sentinas

**Sistema inteligente de verificacion de licitaciones para equipos maritimos**

DETEGASA fabrica equipos de tratamiento de liquidos para el sector maritimo (separadores de sentinas OWS, plantas de aguas grises, sistemas de refuelling). Cuando reciben licitaciones de astilleros, necesitan verificar si sus productos cumplen con las especificaciones tecnicas, identificar gaps y calcular el coste de modificaciones.

Este sistema automatiza ese proceso: extrae especificaciones de PDFs y Excel a JSON estructurado, y usa una combinacion de reglas deterministicas e IA (LLMs) para comparar producto vs. licitacion, generando un informe de compliance detallado.

**Alcance MVP:** Separadores de sentinas (OWS). Arquitectura preparada para multi-producto.

---

## Arquitectura

```
  PDF / Excel                       Resultado
  (producto + tender)               (JSON compliance)
       |                                 ^
       v                                 |
  +-----------+    +----------+    +------------+    +---------+
  | Extraction|    | Schemas  |    | Compliance |    | Viewer  |
  | pdf_parser|--->| product  |--->| engine     |--->| HTML/JS |
  | xlsx_parse|    | tender   |    | matchers   |    | Chart.js|
  | chunker   |    | complianc|    | llm_compar.|    |         |
  +-----------+    +----------+    +-----+------+    +---------+
       |                                 |
       v                                 v
  +-----------+                    +-----------+
  | LLM       |                    | Langfuse  |
  | Claude/GPT|                    | (observ.) |
  | Instructor|                    +-----------+
  | Cache     |
  +-----------+
```

---

## Estructura del proyecto

```
separador_sentinas/
    src/
        extraction/          Parsing de PDF (PyMuPDF) y Excel (openpyxl)
        llm/                 Adaptadores Anthropic/OpenAI + cache + observabilidad
        llm_extraction/      Extraccion estructurada de specs via LLM
        compliance/          Motor de compliance: 3 matchers + fallback LLM
            matchers/        ProcessMatcher, MaterialMatcher, CertificationMatcher
        schemas/             Modelos Pydantic: producto, tender, compliance
        core/                Config, base de datos, modelos ORM
    tests/                   334 tests (pytest)
    scripts/                 Scripts E2E de extraccion y compliance
    viewer/                  Visor web estatico (HTML + CSS + JS + Chart.js)
    PIPELINE/                Documentacion de arquitectura y plan de fases
    DOCUMENTACION/           Data sheets del producto (PDFs)
    ESPECIFICACION DE CLIENTE/  Documentos de la licitacion (PDFs + Excel)
    alembic/                 Migraciones de base de datos
```

---

## Modulos principales

### `src/extraction/` — Parsing de documentos

Extrae texto y tablas de PDFs (PyMuPDF, pdfplumber) y Excel (openpyxl, xlrd). Incluye limpieza de texto, chunking para LLMs, y deteccion automatica del tipo de documento.

### `src/llm/` — Adaptadores LLM

Patron adapter con implementaciones para **Anthropic (Claude)** y **OpenAI (GPT)**. Usa **Instructor** para salida Pydantic validada. Incluye cache de respuestas y tracking via **Langfuse**.

### `src/compliance/` — Motor de compliance

Evalua cada requisito del tender contra las especificaciones del producto en dos fases:

1. **Matchers deterministicos** (sin coste API):
   - `ProcessMatcher` — Comparaciones numericas (capacidad >= requerida, ppm <= limite)
   - `MaterialMatcher` — Jerarquia de materiales (SS 316L > SS 304 > carbon steel)
   - `CertificationMatcher` — Equivalencias de certificaciones (IMO ↔ MARPOL, ATEX ↔ IECEx)

2. **Fallback LLM** — Para items que no pueden resolverse deterministicamente

Resultado: JSON con score global (0-100%), status por item (compliant, non_compliant, partial, clarification_needed), nivel de riesgo, y descripcion de gaps.

### `src/schemas/` — Modelos de datos

Modelos Pydantic para toda la cadena:
- `ProductSpec` — Especificaciones del producto (rendimiento, materiales, certificaciones)
- `TenderRequirement` — Requisitos individuales del tender
- `ComplianceResult` — Resultado de evaluacion con items, score, y resumen

### `viewer/` — Visor web

Aplicacion estatica (sin build) para revisar resultados de compliance:
- Dashboard con score, charts (Chart.js), y alertas de gaps criticos
- Filtros combinables por status, categoria, riesgo, y busqueda de texto
- Tabla sortable con detalle de cada item
- Exportacion a CSV

---

## Estado actual

### Implementado

| Fase | Modulo | Estado |
|------|--------|--------|
| 1 | Fundamentos (config, DB, ORM) | Completo |
| 2 | Extraccion PDF + Excel | Completo |
| 3 | Adaptadores LLM (Claude + OpenAI) | Completo |
| 4 | Schemas Pydantic | Completo |
| 5 | Base de datos PostgreSQL + pgvector | Completo |
| 7 | Motor de compliance (matchers + LLM) | Completo |
| - | Visor web de resultados | Completo |
| - | Tests (334 tests) | Completo |

### Pendiente

| Fase | Modulo | Estado |
|------|--------|--------|
| 6 | Embeddings y busqueda semantica | Pendiente |
| 8 | Estimacion de costes por modificacion | Pendiente |
| 9 | API REST (FastAPI) | Pendiente |
| 10 | Frontend Streamlit | Pendiente |
| - | Validacion contra TBT real | En progreso |

El plan detallado de todas las fases esta en `PIPELINE/PLAN.md`.

---

## Quick start

Ver [INSTALL.md](INSTALL.md) para instrucciones completas.

```bash
# 1. Instalar
pip install -e ".[dev]"
cp .env.example .env   # editar con API keys

# 2. Tests
pytest                  # 334 tests, sin API keys

# 3. Visor web (datos de demo)
python -m http.server 8080 --directory viewer
# Abrir http://localhost:8080

# 4. Compliance E2E (requiere API key + documentos)
python -m scripts.compliance_test --provider anthropic
```

---

## Stack tecnologico

| Capa | Tecnologia |
|------|------------|
| Lenguaje | Python 3.11+ |
| Parsing PDF | PyMuPDF, pdfplumber |
| Parsing Excel | openpyxl, xlrd |
| LLM | Anthropic (Claude), OpenAI (GPT) via Instructor |
| Observabilidad | Langfuse |
| Base de datos | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 (async) |
| Migraciones | Alembic |
| Modelos de datos | Pydantic v2 |
| Visor web | HTML + CSS + JavaScript + Chart.js |
| Tests | pytest |
| Linting | ruff |

---

## Coste por licitacion

| Concepto | Coste estimado |
|----------|---------------|
| Extraccion LLM (~720K tokens) | ~$3.55 |
| Comparacion LLM (~375K tokens) | ~$2.03 |
| Embeddings (~700K tokens) | ~$0.01 |
| **Total por licitacion** | **~$5.60** |

Con cache activo, relicitaciones del mismo producto cuestan solo la comparacion (~$2).

---

## Licencia

Proprietary. Uso interno DETEGASA.

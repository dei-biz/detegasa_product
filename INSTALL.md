# Guia de Instalacion

## Requisitos previos

| Requisito | Version minima | Notas |
|-----------|---------------|-------|
| Python | 3.11+ | Recomendado 3.12 |
| Docker + Docker Compose | 24+ | Para PostgreSQL + pgvector |
| Git | 2.x | |

Necesitaras una API key de al menos uno de estos proveedores LLM:

- **Anthropic** (Claude) — recomendado
- **OpenAI** (GPT-4)

Los tests unitarios no requieren API keys.

---

## 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd separador_sentinas
```

## 2. Crear entorno virtual

```bash
python -m venv .venv
```

Activar:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (Git Bash)
source .venv/Scripts/activate
```

## 3. Instalar dependencias

```bash
# Instalacion base + herramientas de desarrollo
pip install -e ".[dev]"
```

Extras opcionales:

```bash
# Embeddings locales (sentence-transformers, requiere ~2 GB)
pip install -e ".[local-embeddings]"

# Docling (IBM, extraccion avanzada de PDF)
pip install -e ".[docling]"
```

## 4. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` y rellenar como minimo:

```
ANTHROPIC_API_KEY=sk-ant-...      # o bien OPENAI_API_KEY
DEFAULT_LLM_PROVIDER=anthropic    # o "openai"
```

Las demas variables tienen valores por defecto validos para desarrollo local.

## 5. Levantar la base de datos

```bash
docker compose up -d
```

Esto arranca PostgreSQL 16 con la extension **pgvector** en el puerto **5433** (no el 5432 por defecto, para evitar conflictos con instalaciones locales).

Verificar que esta corriendo:

```bash
docker compose ps
# Debe mostrar el servicio "db" como "healthy"
```

## 6. Ejecutar migraciones

```bash
alembic upgrade head
```

## 7. Verificar instalacion

```bash
pytest
```

Deben pasar **334 tests**. Ningun test requiere API keys ni base de datos activa.

---

## Uso: Scripts principales

### Extraccion E2E (PDF + Excel → JSON)

Requiere: API key configurada + documentos en `DOCUMENTACION/` y `ESPECIFICACION DE CLIENTE/`.

```bash
python -m scripts.e2e_extraction_test --provider anthropic
```

Opciones:

| Flag | Descripcion |
|------|-------------|
| `--provider anthropic\|openai` | Proveedor LLM |
| `--model MODEL` | Modelo especifico (ej: `claude-sonnet-4-5-20250514`) |
| `--ocr` | Activar OCR para paginas escaneadas |

Salida: `product/<timestamp>_e2e_results.json`

### Evaluacion de Compliance (JSON producto + TBT Excel → informe)

Requiere: haber ejecutado la extraccion previamente.

```bash
python -m scripts.compliance_test --provider anthropic
```

Opciones:

| Flag | Descripcion |
|------|-------------|
| `--provider anthropic\|openai` | Proveedor LLM |
| `--model MODEL` | Modelo especifico |
| `--no-llm` | Solo matchers deterministicos (sin coste API) |

Salida: `product/<timestamp>_compliance_<provider>.json`

### Visor web de resultados

```bash
python -m http.server 8080 --directory viewer
```

Abrir http://localhost:8080 y cargar el JSON de compliance generado, o pulsar "Cargar datos de demo".

---

## Extras opcionales

### Langfuse (observabilidad LLM)

Descomentar el servicio `langfuse` en `docker-compose.yml` y ejecutar:

```bash
docker compose up -d
```

Dashboard disponible en http://localhost:3000. Configurar las claves en `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

---

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| `ModuleNotFoundError: src` | Asegurar `pip install -e .` (modo editable) |
| Puerto 5433 ocupado | Cambiar el mapeo en `docker-compose.yml` y en `DATABASE_URL` |
| `alembic upgrade` falla | Verificar que Docker esta corriendo y el servicio `db` es `healthy` |
| Tests de LLM fallan | Los tests unitarios no necesitan API keys; si ejecutas scripts E2E, configura `.env` |
| Viewer no carga demo | Usar servidor HTTP (`python -m http.server`), no abrir `file://` directamente |

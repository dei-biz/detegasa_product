# 01 - Fundamentos del Proyecto

## Objetivo

Establecer la estructura base del proyecto Python, la configuracion de entorno, Docker para PostgreSQL+pgvector, y la infraestructura de testing.

## Entregables

1. **Estructura de carpetas** del proyecto Python con `pyproject.toml`
2. **Docker Compose** con PostgreSQL 16 + pgvector
3. **Configuracion** de entorno (`.env`, settings con Pydantic)
4. **Infraestructura de tests** con pytest

## Como implementarlo

### 1. Proyecto Python

```
separador_sentinas/
  src/
    __init__.py
    core/
      __init__.py
      config.py          # BaseSettings de Pydantic, lee .env
      database.py        # Pool de conexiones asyncpg
  tests/
    __init__.py
    conftest.py          # Fixtures compartidas (db test, etc.)
  .env.example
  pyproject.toml
  docker-compose.yml
```

`pyproject.toml` usara `hatchling` o `setuptools` como build system. Todas las dependencias se declaran ahi.

### 2. Docker Compose

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: sentinas
      POSTGRES_USER: sentinas
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  # Langfuse (observabilidad LLM) - opcional, self-hosted
  langfuse:
    image: langfuse/langfuse:latest
    environment:
      DATABASE_URL: postgresql://sentinas:${DB_PASSWORD}@db:5432/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_SECRET}
      NEXTAUTH_URL: http://localhost:3000
    ports:
      - "3000:3000"
    depends_on:
      - db

volumes:
  pgdata:
```

La imagen `pgvector/pgvector:pg16` incluye la extension pgvector preinstalada.
Langfuse se puede desactivar si no se quiere observabilidad (el sistema funciona sin el).

### 3. Config con Pydantic

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://sentinas:pass@localhost/sentinas"

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_llm_provider: str = "anthropic"  # o "openai"

    # Embeddings
    embedding_provider: str = "openai"  # o "local"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Observabilidad (Langfuse)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"  # Self-hosted
    enable_llm_cache: bool = True

    # App
    debug: bool = False

    class Config:
        env_file = ".env"
```

### 4. Conexion a la base de datos

Usar `asyncpg` directamente con un pool de conexiones, o SQLAlchemy async. Decisiones:

- **SQLAlchemy async** si queremos ORM completo (mas facil de mantener, migraciones con Alembic)
- **asyncpg raw** si queremos maximo rendimiento y control

**Recomendacion**: SQLAlchemy async. El rendimiento no es critico (no es una app de alto trafico) y el ORM facilita mucho las migraciones y queries complejas con JSONB.

## Dependencias de otros modulos

Ninguna. Este es el punto de partida.

## Sesiones estimadas

1 sesion para tener todo funcional (proyecto creado, Docker levantado, config, test de conexion a DB).

# 05 - Base de Datos (PostgreSQL + pgvector)

## Objetivo

Disenar e implementar el esquema de base de datos en PostgreSQL con la extension pgvector para almacenar productos, licitaciones, resultados de compliance, documentos y embeddings vectoriales.

## Entregables

1. **models.py** - Modelos SQLAlchemy ORM
2. **database.py** - Conexion async y session management
3. **Migraciones Alembic** - Versionado del schema
4. **Indices** - GIN para JSONB, IVFFlat para vectores

## Como implementarlo

### 1. SQLAlchemy Async con asyncpg

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase

class Base(DeclarativeBase):
    pass

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session
```

### 2. Modelos ORM

```python
from sqlalchemy import Column, String, Integer, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from pgvector.sqlalchemy import Vector

class Product(Base):
    __tablename__ = "products"
    id = Column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    product_name = Column(String(255), nullable=False)
    product_family = Column(String(50), default="OWS")
    specs = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMPTZ, server_default=text("NOW()"))

class ProductComponent(Base):
    __tablename__ = "product_components"
    id = Column(UUID, primary_key=True)
    product_id = Column(UUID, ForeignKey("products.id", ondelete="CASCADE"))
    component_tag = Column(String(50))
    component_type = Column(String(50))
    specs = Column(JSONB, nullable=False)

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(UUID, primary_key=True)
    document_id = Column(UUID, ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    page_number = Column(Integer)
    section_title = Column(String(255))
    embedding = Column(Vector(1536), nullable=False)  # Dimension configurable
    metadata_ = Column("metadata", JSONB)
```

### 3. Migraciones con Alembic

```bash
alembic init alembic
# Configurar env.py para async
# Crear migracion inicial:
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

La migracion inicial incluye:
- `CREATE EXTENSION IF NOT EXISTS vector;`
- Todas las tablas del schema
- Indices GIN para JSONB
- Indices IVFFlat para vectores

### 4. Indices

```sql
-- Busqueda vectorial rapida
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Queries sobre specs JSON
CREATE INDEX idx_products_specs ON products USING gin(specs);
CREATE INDEX idx_tenders_reqs ON tenders USING gin(requirements);

-- Filtros frecuentes
CREATE INDEX idx_tender_reqs_category ON tender_requirements(category);
CREATE INDEX idx_compliance_items_status ON compliance_items(status);
CREATE INDEX idx_documents_status ON documents(processing_status);
```

### 5. Dimension del vector configurable

Para soportar tanto embeddings de API (1536d) como locales (384d):

```python
# En config.py
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 1536))

# En la migracion, usar variable
# O bien: crear la tabla con dimension 1536 y truncar/pad si se usa modelo local
# Alternativa: dos tablas, una para cada dimension
```

**Recomendacion**: Usar 1536 como default. Si se cambia a modelo local, regenerar embeddings (es rapido, ~minutos).

### 6. Tabla de cache LLM (nueva)

```python
class LLMCache(Base):
    __tablename__ = "llm_cache"
    id = Column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    cache_key = Column(String(64), unique=True, nullable=False)  # SHA-256
    input_hash = Column(String(64), nullable=False)  # Hash del input
    model = Column(String(100), nullable=False)
    schema_name = Column(String(100), nullable=False)
    result = Column(JSONB, nullable=False)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Numeric(8, 4))
    created_at = Column(TIMESTAMPTZ, server_default=text("NOW()"))
```

Indice:
```sql
CREATE UNIQUE INDEX idx_llm_cache_key ON llm_cache(cache_key);
```

Esto evita re-llamar al LLM para el mismo chunk+schema+modelo. Ahorra ~60% del coste en re-analisis.

## Consideraciones

- **JSONB vs columnas tipadas**: Los `specs` se guardan como JSONB para flexibilidad. Los campos que se filtran frecuentemente (status, category, tag) tienen columnas dedicadas.
- **Cascade deletes**: Si se borra un producto, se borran sus componentes y embeddings asociados.
- **Versionado**: Los productos y licitaciones tienen `updated_at` para tracking de cambios.
- **Cache LLM**: Reduce costes significativamente en re-analisis y durante desarrollo/testing de prompts.

## Dependencias

- Requiere: `01_fundamentos` (config, Docker), `04_schemas_json` (para validacion)
- Librerias: `sqlalchemy`, `asyncpg`, `alembic`, `pgvector`

## Sesiones estimadas

1 sesion. El schema esta bien definido. Las migraciones con Alembic son directas.

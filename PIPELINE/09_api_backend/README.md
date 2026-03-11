# 09 - API Backend (FastAPI)

## Objetivo

Exponer todas las funcionalidades del sistema como endpoints REST para ser consumidos por el frontend y potencialmente por otros sistemas de DETEGASA.

## Entregables

1. **main.py** - Aplicacion FastAPI con configuracion CORS, middleware
2. **routes/documents.py** - Upload y gestion de documentos PDF/XLS
3. **routes/products.py** - CRUD de productos y sus especificaciones
4. **routes/tenders.py** - CRUD de licitaciones y requisitos
5. **routes/compliance.py** - Lanzar comparaciones y obtener resultados
6. **routes/search.py** - Busqueda semantica sobre documentos

## Como implementarlo

### 1. Estructura FastAPI

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Sentinas Compliance API",
    description="AI-powered tender compliance checking for maritime equipment",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. Endpoints principales

#### Documents

```
POST   /api/documents/upload          # Upload PDF/XLS
GET    /api/documents/                # Listar documentos
GET    /api/documents/{id}            # Detalle de documento
POST   /api/documents/{id}/process    # Lanzar extraccion
GET    /api/documents/{id}/status     # Estado de procesamiento
DELETE /api/documents/{id}            # Eliminar documento
```

```python
@router.post("/upload")
async def upload_document(
    file: UploadFile,
    document_type: str,  # "product_datasheet", "material_requisition", etc.
    parent_entity_type: str,  # "product" o "tender"
    parent_entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    # Guardar archivo
    # Crear registro en DB
    # Devolver document_id
```

#### Products

```
POST   /api/products/                 # Crear producto (con JSON specs)
GET    /api/products/                 # Listar productos
GET    /api/products/{id}            # Detalle con componentes
PUT    /api/products/{id}            # Actualizar specs
POST   /api/products/{id}/extract    # Extraer specs de PDFs asociados con LLM
GET    /api/products/{id}/components # Listar componentes
```

#### Tenders

```
POST   /api/tenders/                  # Crear licitacion
GET    /api/tenders/                  # Listar licitaciones
GET    /api/tenders/{id}             # Detalle con requisitos
POST   /api/tenders/{id}/extract     # Extraer requisitos de PDFs con LLM
GET    /api/tenders/{id}/requirements # Listar requisitos extraidos
PUT    /api/tenders/{id}/requirements/{req_id}  # Editar un requisito manualmente
```

#### Compliance

```
POST   /api/compliance/compare        # Lanzar comparacion producto vs licitacion
GET    /api/compliance/{id}           # Resultado de comparacion
GET    /api/compliance/{id}/report    # Descargar informe (XLSX o JSON)
GET    /api/compliance/history        # Historico de comparaciones
```

```python
@router.post("/compare")
async def run_comparison(
    request: ComparisonRequest,  # product_id + tender_id
    db: AsyncSession = Depends(get_db),
    llm: LLMAdapter = Depends(get_llm),
    embeddings: EmbeddingAdapter = Depends(get_embeddings)
):
    # Cargar product y tender de DB
    # Ejecutar ComplianceEngine
    # Guardar resultado
    # Devolver comparison_id + resultado
```

#### Search

```
POST   /api/search/semantic           # Busqueda semantica sobre documentos
POST   /api/search/requirements       # Buscar requisitos similares entre licitaciones
```

### 3. Background tasks

Las extracciones LLM pueden tardar minutos. Usar FastAPI background tasks o Celery:

```python
from fastapi import BackgroundTasks

@router.post("/products/{id}/extract")
async def extract_product_specs(
    id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    background_tasks.add_task(run_extraction, id, "product", db)
    return {"status": "processing", "message": "Extraction started"}
```

Para MVP, `BackgroundTasks` de FastAPI es suficiente. Si se necesita escalabilidad, migrar a Celery + Redis.

### 4. Error handling

```python
from fastapi import HTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )
```

### 5. Endpoint de observabilidad

```
GET    /api/stats/costs              # Coste acumulado de API LLM
GET    /api/stats/extractions        # Metricas de extraccion
GET    /api/stats/cache              # Hit rate del cache LLM
```

Estos endpoints consultan la tabla `llm_cache` y Langfuse para dar visibilidad sobre costes y calidad.

### 6. Autenticacion (futuro)

Para MVP no se implementa auth. Para produccion:
- API key simple para empezar
- OAuth2/JWT si se necesita multi-usuario

## Dependencias

- Requiere: todos los modulos anteriores
- Librerias: `fastapi`, `uvicorn`, `python-multipart`

## Sesiones estimadas

2 sesiones:
- Sesion 1: Endpoints de documents, products, tenders + upload
- Sesion 2: Endpoints de compliance, search, stats + background tasks

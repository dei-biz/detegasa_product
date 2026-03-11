# 06 - Embeddings y Busqueda Semantica

## Objetivo

Generar embeddings vectoriales de los chunks de documentos y almacenarlos en pgvector para permitir busqueda semantica. Esto es clave para el matching entre requisitos de licitacion y especificaciones de producto cuando no hay correspondencia directa en el JSON estructurado.

## Entregables

1. **adapter.py** - Interfaz abstracta `EmbeddingAdapter`
2. **openai_embeddings.py** - Implementacion con text-embedding-3-small
3. **local_embeddings.py** - Implementacion con sentence-transformers
4. **semantic_search.py** - Queries de busqueda vectorial contra pgvector
5. **batch_processor.py** - Procesamiento en lotes para documentos completos

## Como implementarlo

### 1. Adapter para embeddings

```python
from abc import ABC, abstractmethod
import numpy as np

class EmbeddingAdapter(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass
```

### 2. OpenAI Embeddings

```python
from openai import AsyncOpenAI

class OpenAIEmbeddingAdapter(EmbeddingAdapter):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._dimension = 1536

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]
```

### 3. Embeddings locales

```python
from sentence_transformers import SentenceTransformer

class LocalEmbeddingAdapter(EmbeddingAdapter):
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model = SentenceTransformer(model_name)
        self._dimension = self.model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # sentence-transformers es sincrono, ejecutar en thread pool
        embeddings = await asyncio.to_thread(
            self.model.encode, texts, normalize_embeddings=True
        )
        return embeddings.tolist()
```

### 4. Busqueda semantica con pgvector

```python
async def semantic_search(
    session: AsyncSession,
    query_embedding: list[float],
    entity_type: str = "product",  # "product" o "tender"
    top_k: int = 10,
    min_similarity: float = 0.7
) -> list[dict]:
    """Busca los chunks mas similares al embedding de la query."""
    result = await session.execute(
        text("""
            SELECT
                dc.chunk_text,
                dc.section_title,
                dc.page_number,
                d.filename,
                1 - (dc.embedding <=> :query_embedding) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.parent_entity_type = :entity_type
            AND 1 - (dc.embedding <=> :query_embedding) > :min_similarity
            ORDER BY dc.embedding <=> :query_embedding
            LIMIT :top_k
        """),
        {
            "query_embedding": str(query_embedding),
            "entity_type": entity_type,
            "top_k": top_k,
            "min_similarity": min_similarity
        }
    )
    return [dict(row) for row in result.mappings()]
```

### 5. Caso de uso principal: encontrar info de producto para un requisito

```python
async def find_product_info_for_requirement(
    requirement_text: str,
    product_id: str,
    embedding_adapter: EmbeddingAdapter,
    session: AsyncSession
) -> list[dict]:
    """Dado un texto de requisito, encuentra las secciones del producto relevantes."""
    query_embedding = await embedding_adapter.embed_text(requirement_text)

    results = await session.execute(
        text("""
            SELECT
                dc.chunk_text,
                dc.section_title,
                pc.component_tag,
                1 - (dc.embedding <=> :qe) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            LEFT JOIN product_components pc ON pc.product_id = d.parent_entity_id
            WHERE d.parent_entity_id = :product_id
            ORDER BY dc.embedding <=> :qe
            LIMIT 5
        """),
        {"qe": str(query_embedding), "product_id": product_id}
    )
    return [dict(row) for row in result.mappings()]
```

## Estrategia de chunking para embeddings

- Chunks de 500-1500 tokens (sweet spot para embeddings)
- Overlap de 100 tokens entre chunks consecutivos
- Metadata por chunk: documento, pagina, seccion, tag de componente
- Los titles/headers se prependen al chunk para dar contexto

## Consideraciones

- **Coste embeddings API**: ~$0.02/M tokens. Un documento de 100 paginas ~ 150K tokens = $0.003. Negligible.
- **Modelo local**: Requiere ~1GB de RAM para cargar. Sin GPU funciona bien para batches pequenos.
- **Regeneracion**: Si se cambia de modelo, hay que regenerar todos los embeddings. Tener un script de reindexacion.
- **IVFFlat vs HNSW**: IVFFlat es mejor para datasets pequenos (<100K vectors). HNSW para mas grandes. Empezar con IVFFlat.

## Integracion con Docling

Cuando se usa Docling (modulo 02) para parsear PDFs, los chunks vienen con metadata mas rica (titulo de seccion, tipo de contenido, relaciones con tablas). Esto mejora la calidad de la busqueda semantica.

## Dependencias

- Requiere: `01_fundamentos`, `02_extraccion_pdf` (chunks de Docling/PyMuPDF), `05_base_datos` (pgvector)
- Librerias: `openai`, `sentence-transformers`, `pgvector`

## Sesiones estimadas

1 sesion. Los adapters son simples y la integracion con pgvector es directa. El testing con datos reales valida la calidad de los resultados de busqueda.

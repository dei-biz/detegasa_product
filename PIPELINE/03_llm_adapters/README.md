# 03 - LLM Adapters (Claude / OpenAI) + Instructor + Observabilidad

## Objetivo

Implementar un patron adapter que permita usar Claude (Anthropic) o GPT-4o (OpenAI) de forma intercambiable, con extraccion estructurada garantizada via **Instructor** y observabilidad de costes/calidad via **Langfuse**.

## Entregables

1. **adapter.py** - Interfaz abstracta `LLMAdapter`
2. **claude_adapter.py** - Implementacion para Anthropic API
3. **openai_adapter.py** - Implementacion para OpenAI API
4. **instructor_extractor.py** - Extraccion estructurada con Instructor (output Pydantic garantizado)
5. **observability.py** - Integracion con Langfuse para tracking
6. **cache.py** - Cache de resultados LLM para evitar reprocesamiento
7. **prompts/** - Templates de prompts por tarea

## Mejoras respecto al diseno original

### Instructor (nuevo)

**Por que**: En vez de esperar que el LLM devuelva JSON valido y parsearlo manualmente, **Instructor** garantiza output Pydantic valido con reintentos automaticos si la validacion falla. 3M+ descargas mensuales, soporta Claude y OpenAI.

```python
import instructor
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

# Claude con Instructor
client = instructor.from_anthropic(AsyncAnthropic())

component = await client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=4096,
    messages=[{"role": "user", "content": chunk_text}],
    response_model=ComponentSpec,  # Pydantic model -> output validado
)
# component ya es un ComponentSpec validado, no un string JSON

# OpenAI con Instructor
client = instructor.from_openai(AsyncOpenAI())

component = await client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    response_model=ComponentSpec,
)
```

**Ventajas**:
- Output siempre valido contra el Pydantic model
- Reintentos automaticos si la validacion falla (max_retries configurable)
- Funciona igual con Claude y OpenAI
- Soporta streaming para extracciones largas
- Validacion semantica (custom validators en Pydantic)

### Structured Outputs nativos (nuevo)

Tanto Claude como OpenAI ahora soportan structured outputs a nivel de API:

```python
# Claude - structured output nativo
response = await anthropic_client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=4096,
    messages=[...],
    # JSON schema enforcement durante la generacion de tokens
    response_format={"type": "json_schema", "schema": ComponentSpec.model_json_schema()}
)

# OpenAI - strict mode
response = await openai_client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "component", "schema": ComponentSpec.model_json_schema(), "strict": True}
    }
)
```

**Recomendacion**: Usar **Instructor** como capa de abstraccion sobre los structured outputs nativos. Instructor ya usa internamente los mecanismos nativos de cada proveedor.

### Langfuse - Observabilidad LLM (nuevo)

**Por que**: Necesitamos trackear costes, latencia, y calidad de extraccion por documento y por proveedor. Langfuse es open-source y se puede self-hostear.

```python
from langfuse import Langfuse
from langfuse.decorators import observe

langfuse = Langfuse()

@observe()  # Trackea automaticamente la llamada
async def extract_component(chunk_text: str, model: str) -> ComponentSpec:
    result = await instructor_client.messages.create(
        model=model,
        messages=[{"role": "user", "content": chunk_text}],
        response_model=ComponentSpec,
    )
    return result
```

**Metricas que trackeamos**:
- Coste por documento (tokens input + output)
- Latencia por extraccion
- Tasa de reintentos (cuando Instructor necesita re-pedir al LLM)
- Comparativa Claude vs GPT-4o por tipo de documento
- Coste acumulado mensual

### Cache de resultados (nuevo)

Evitar reprocesar el mismo documento si ya se extrajo:

```python
import hashlib

class LLMCache:
    async def get_or_extract(self, chunk_text: str, schema: type, llm_adapter):
        cache_key = hashlib.sha256(
            f"{chunk_text}:{schema.__name__}:{llm_adapter.model}".encode()
        ).hexdigest()

        # Buscar en DB
        cached = await self.db.execute(
            "SELECT result FROM llm_cache WHERE cache_key = :key",
            {"key": cache_key}
        )
        if cached:
            return schema.model_validate_json(cached)

        # Si no hay cache, extraer con LLM
        result = await llm_adapter.extract(chunk_text, schema)

        # Guardar en cache
        await self.db.execute(
            "INSERT INTO llm_cache (cache_key, result, model, cost) VALUES (:key, :result, :model, :cost)",
            {"key": cache_key, "result": result.model_dump_json(), ...}
        )
        return result
```

## Adapter pattern actualizado

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float

class LLMAdapter(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    async def extract_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str = "",
        max_retries: int = 3
    ) -> tuple[BaseModel, LLMResponse]:
        """Extraccion estructurada via Instructor."""
        pass
```

## Prompts

```
prompts/
  system_maritime_expert.txt    # System prompt comun: contexto dominio maritimo
  extract_component.txt         # Extraccion de specs de un componente
  extract_requirements.txt      # Extraccion de requisitos de licitacion
  compare_compliance.txt        # Evaluacion de compliance
  classify_requirement.txt      # Clasificacion de categoria de requisito
```

## Tabla de modelos actualizada (precios 2025-2026)

| Modelo | Input $/M | Output $/M | Uso recomendado |
|--------|-----------|------------|-----------------|
| claude-sonnet-4-5 | $3.00 | $15.00 | Extraccion + comparacion (default) |
| claude-haiku-4-5 | $0.80 | $4.00 | Clasificacion rapida |
| gpt-4o | $2.50 | $10.00 | Alternativa a Sonnet |
| gpt-4o-mini | $0.15 | $0.60 | Alternativa a Haiku |

## Dependencias

- Requiere: `01_fundamentos`
- Librerias: `anthropic`, `openai`, `instructor`, `langfuse`, `tenacity`

## Sesiones estimadas

1 sesion: Instructor simplifica mucho el codigo. Langfuse se integra con decoradores.

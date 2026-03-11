# 10 - Frontend (Streamlit)

## Objetivo

Proporcionar una interfaz web basica para que los ingenieros de DETEGASA puedan subir documentos, ver especificaciones extraidas, lanzar comparaciones de compliance, y revisar/descargar informes.

## Entregables

1. **app.py** - Aplicacion Streamlit principal
2. **pages/upload.py** - Pagina de upload de documentos
3. **pages/products.py** - Vista de productos y componentes
4. **pages/tenders.py** - Vista de licitaciones y requisitos
5. **pages/compliance.py** - Comparacion y resultados
6. **pages/search.py** - Busqueda semantica

## Como implementarlo

### 1. Estructura Streamlit multi-pagina

```
frontend/
  app.py                  # Entry point, sidebar navigation
  pages/
    1_Upload.py           # Subir PDFs y XLS
    2_Products.py         # Ver/editar productos
    3_Tenders.py          # Ver/editar licitaciones
    4_Compliance.py       # Lanzar y ver comparaciones
    5_Search.py           # Busqueda semantica
  utils/
    api_client.py         # Cliente HTTP para la API FastAPI
```

### 2. Pagina de Upload

```python
import streamlit as st
import httpx

st.title("Subir Documentos")

doc_type = st.selectbox("Tipo de documento", [
    "Data Sheet de Producto",
    "Material Requisition",
    "Package Specification",
    "Technical Bid Evaluation Table",
    "E&I Compliance Check Sheet",
    "Otro"
])

entity_type = st.radio("Asociar a:", ["Producto", "Licitacion"])

uploaded_file = st.file_uploader("Seleccionar archivo", type=["pdf", "xls", "xlsx"])

if uploaded_file and st.button("Subir y Procesar"):
    with st.spinner("Subiendo documento..."):
        response = api_client.upload_document(uploaded_file, doc_type, entity_type)
    st.success(f"Documento subido. ID: {response['id']}")

    if st.button("Extraer especificaciones con IA"):
        with st.spinner("Extrayendo... (puede tardar 1-2 minutos)"):
            result = api_client.extract_specs(response['id'])
        st.json(result)
```

### 3. Pagina de Compliance

```python
st.title("Comparacion de Compliance")

col1, col2 = st.columns(2)
with col1:
    product = st.selectbox("Producto", api_client.list_products())
with col2:
    tender = st.selectbox("Licitacion", api_client.list_tenders())

if st.button("Lanzar Comparacion"):
    with st.spinner("Analizando compliance..."):
        result = api_client.run_comparison(product.id, tender.id)

    # Score general
    st.metric("Score de Compliance", f"{result.overall_score}%")

    # Resumen por status
    col1, col2, col3 = st.columns(3)
    col1.metric("Cumple", result.summary.compliant_count, delta_color="normal")
    col2.metric("No cumple", result.summary.non_compliant_count, delta_color="inverse")
    col3.metric("Parcial", result.summary.partial_count)

    # Coste estimado
    st.metric("Coste estimado de modificaciones",
              f"{result.summary.estimated_total_delta_eur:,.0f} EUR")

    # Gaps criticos
    if result.summary.disqualifying_gaps:
        st.error("GAPS DESCALIFICANTES:")
        for gap in result.summary.disqualifying_gaps:
            st.write(f"- {gap}")

    # Tabla detallada
    st.dataframe(
        [{
            "Categoria": i.category,
            "Requisito": i.requirement_text[:80],
            "Producto": i.product_value,
            "Status": i.status.value,
            "Gap": i.gap_description or "-",
            "Coste": f"{i.cost_impact.estimated_delta_eur:,.0f} EUR" if i.cost_impact else "-",
            "Riesgo": i.risk_level.value
        } for i in result.items],
        use_container_width=True
    )

    # Descarga
    st.download_button(
        "Descargar informe XLSX",
        data=api_client.download_report(result.comparison_id, "xlsx"),
        file_name=f"compliance_{tender.project_name}.xlsx"
    )
```

### 4. Pagina de Busqueda Semantica

```python
st.title("Busqueda Semantica")

query = st.text_input("Buscar en documentos...",
    placeholder="Ej: material requirements for pump body")

search_in = st.multiselect("Buscar en:", ["Productos", "Licitaciones"], default=["Productos"])

if query:
    results = api_client.semantic_search(query, search_in)
    for r in results:
        with st.expander(f"{r.filename} - p.{r.page_number} ({r.similarity:.0%})"):
            st.write(r.chunk_text)
            st.caption(f"Seccion: {r.section_title}")
```

### 5. Cliente API

```python
class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=120.0)

    def upload_document(self, file, doc_type, entity_type):
        return self.client.post("/api/documents/upload",
            files={"file": (file.name, file.read())},
            data={"document_type": doc_type, "parent_entity_type": entity_type}
        ).json()

    def run_comparison(self, product_id, tender_id):
        return self.client.post("/api/compliance/compare",
            json={"product_id": product_id, "tender_id": tender_id}
        ).json()
```

### 6. Pagina de Costes y Observabilidad

```python
st.title("Costes y Metricas")

stats = api_client.get_stats()

col1, col2, col3 = st.columns(3)
col1.metric("Coste API este mes", f"${stats['monthly_cost']:.2f}")
col2.metric("Documentos procesados", stats['documents_processed'])
col3.metric("Cache hit rate", f"{stats['cache_hit_rate']:.0%}")

# Link a Langfuse para metricas detalladas
st.markdown("[Dashboard detallado en Langfuse](http://localhost:3000)")
```

## Consideraciones UX

- **Color coding**: Verde (cumple), Rojo (no cumple), Amarillo (parcial), Gris (requiere clarificacion)
- **Filtros**: Por categoria, por status, por nivel de riesgo
- **Edicion manual**: Permitir que el ingeniero corrija/anote items del resultado antes de exportar
- **Idioma**: Interfaz en espanol (el contenido tecnico esta en ingles)
- **Feedback loop**: Boton para marcar un item como "correcto" o "incorrecto" para calibrar el sistema

## Dependencias

- Requiere: `09_api_backend` (todos los endpoints)
- Librerias: `streamlit`, `httpx`, `pandas`

## Sesiones estimadas

1-2 sesiones:
- Sesion 1: Todas las paginas con funcionalidad basica
- Sesion 2: Mejoras UX, filtros, edicion manual (opcional para MVP)

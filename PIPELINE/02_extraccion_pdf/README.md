# 02 - Pipeline de Extraccion de Documentos

## Objetivo

Extraer texto y tablas estructuradas de los PDFs de producto y de licitacion, y datos tabulares de los XLS/XLSX de los apendices. Dividir en chunks semanticos listos para procesamiento con LLM y generacion de embeddings.

## Entregables

1. **docling_parser.py** - Extraccion principal con Docling (IBM): texto + tablas + estructura
2. **pymupdf_fallback.py** - Fallback con PyMuPDF para casos donde Docling falle
3. **xlsx_parser.py** - Parseo directo de XLS/XLSX (Appendices 5, 6, 10, 12)
4. **text_cleaner.py** - Limpieza de headers/footers repetidos Petrobras/KES
5. **chunker.py** - Estrategias de chunking por tipo de documento

## Como implementarlo

### 1. Extraccion principal con Docling (IBM)

**Por que Docling en vez de solo PyMuPDF**:
- Docling preserva la estructura de tablas (key-value pairs de data sheets) mucho mejor
- Detecta automaticamente layouts complejos (texto + tabla + diagrama en la misma pagina)
- Exporta a Markdown estructurado o JSON con metadata de posicion
- El modelo Granite-Docling (2026) esta optimizado para documentos tecnicos
- 37K+ stars en GitHub, mantenido activamente por IBM

```python
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat

def extract_with_docling(pdf_path: str) -> dict:
    converter = DocumentConverter()
    result = converter.convert(pdf_path)

    return {
        "markdown": result.document.export_to_markdown(),
        "tables": [
            {
                "page": table.prov[0].page_no if table.prov else None,
                "data": table.export_to_dataframe().to_dict()
            }
            for table in result.document.tables
        ],
        "sections": [
            {
                "title": section.text,
                "level": section.level,
                "content": section.export_to_markdown()
            }
            for section in result.document.sections
        ]
    }
```

### 2. Fallback con PyMuPDF

PyMuPDF (fitz) ya instalado (v1.27.1). Se usa como fallback si Docling falla o para extraccion rapida de texto plano:

```python
import fitz

def extract_with_pymupdf(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append({
            "page_number": i + 1,
            "text": text,
            "has_images": bool(page.get_images()),
        })
    return pages
```

### 3. Parseo directo de XLS/XLSX

Los apendices mas valiosos para la comparacion ya estan en formato tabular. Parsearlos directamente sin LLM:

```python
import openpyxl
import xlrd

def parse_tbt(xlsx_path: str) -> list[dict]:
    """Parsea Technical Bid Evaluation Table (Appendix 12)."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Detectar headers y filas de datos
    headers = [str(h).strip() for h in rows[0] if h]
    items = []
    for row in rows[1:]:
        if any(cell is not None for cell in row):
            items.append(dict(zip(headers, row)))
    return items

def parse_compliance_sheet(xls_path: str) -> list[dict]:
    """Parsea E&I Technical Compliance Check Sheet (Appendix 10)."""
    wb = xlrd.open_workbook(xls_path)
    ws = wb.sheet_by_index(0)
    # Similar logic for .xls format
```

**Archivos que se parsean directamente (sin LLM)**:
| Archivo | Tipo | Datos que contiene |
|---------|------|-------------------|
| Appendix 5 VDRL | .xls | Lista de documentos requeridos al vendor |
| Appendix 6 Technical Clarification | .xlsx | Preguntas/respuestas tecnicas |
| Appendix 10 E&I Compliance | .xls | Checklist de cumplimiento E&I |
| Appendix 12 TBT | .xlsx | Tabla de evaluacion de bid (ground truth) |

### 4. Limpieza de texto

Los PDFs tienen un header repetido de Petrobras en cada pagina:

```python
import re

def clean_petrobras_header(text: str) -> tuple[dict, str]:
    """Elimina el header/footer de Petrobras y extrae metadata."""
    sheet_match = re.search(r'SHEET\s+(\d+)\s+of\s+(\d+)', text)
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|$)', text)

    metadata = {
        "sheet": sheet_match.group(1) if sheet_match else None,
        "total_sheets": sheet_match.group(2) if sheet_match else None,
        "title": title_match.group(1).strip() if title_match else None
    }

    clean = re.sub(r'^.*?(?:SCP78|ESUP)\s*\n', '', text, flags=re.DOTALL)
    clean = re.sub(r'INFORMATION IN THIS DOCUMENT.*$', '', clean, flags=re.DOTALL)

    return metadata, clean.strip()
```

### 5. Chunking por tipo de documento

**Tipo A: Data sheets de componentes** (I-FD-3010.2G-5330-540-DTG-302)
- Split por header de componente: `1- PUMP -P1`, `2- ELECTRIC HEATER - RS1`
- Cada chunk = especificacion completa de un componente

**Tipo B: Especificaciones tecnicas** (Material Requisition, Package Spec)
- Split por seccion numerada: `1.0 INTRODUCTION`, `5.1 DESIGN LIFE`

**Tipo C: XLS/XLSX** - No necesita chunking, cada fila es un item

### 6. Pipeline completo

```
PDF/XLS -> Detectar tipo de documento
  |
  +--> PDF: Docling (estructura + tablas)
  |         |-> PyMuPDF fallback
  |         |-> Limpiar headers Petrobras
  |         |-> Chunking semantico
  |         |-> Cache resultado
  |
  +--> XLS/XLSX: openpyxl/xlrd
  |              |-> Parseo directo a dicts
  |              |-> Mapeo a schemas Pydantic
  |
  +--> Chunks listos para:
       - Extraccion LLM (-> JSON estructurado)
       - Embedding generation (-> pgvector)
```

## Retos conocidos

1. **Encoding Windows**: cp1252 por defecto. Forzar UTF-8
2. **Paginas con solo imagenes**: Dibujos dimensionales -> marcar como `image_only`, no procesar con LLM
3. **Archivos .xls legacy**: Appendices 5 y 10 son .xls (formato antiguo), requieren `xlrd`
4. **Tablas multi-pagina**: Algunas tablas de scope of work cruzan paginas -> Docling las maneja mejor que PyMuPDF

## Dependencias

- Requiere: `01_fundamentos`
- Nuevas librerias: `docling`, `pdfplumber`, `openpyxl`, `xlrd`
- Ya instalado: `PyMuPDF`

## Sesiones estimadas

2 sesiones:
- Sesion 1: Setup Docling + parseo de data sheets + parseo XLS/XLSX directo
- Sesion 2: Chunking + limpieza + testing con todos los documentos reales

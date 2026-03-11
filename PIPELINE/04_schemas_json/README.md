# 04 - Schemas JSON (Pydantic)

## Objetivo

Definir los schemas de datos que representan las especificaciones de producto, los requisitos de licitacion, y los resultados de compliance. Estos schemas sirven como contrato entre todos los modulos del sistema.

## Entregables

1. **product_schemas.py** - Modelos Pydantic para producto y componentes
2. **tender_schemas.py** - Modelos Pydantic para licitacion y requisitos
3. **compliance_schemas.py** - Modelos Pydantic para resultados de comparacion
4. **common.py** - Tipos compartidos (medidas con unidades, materiales, certificaciones)

## Como implementarlo

### 1. Tipos compartidos (common.py)

```python
from pydantic import BaseModel
from enum import Enum

class MeasuredValue(BaseModel):
    value: float
    unit: str  # "bar", "m3/h", "kW", "mm", "dB(A)", etc.

class MaterialSpec(BaseModel):
    designation: str     # "SS 316L", "AISI-316L", "Carbon Steel ASTM A516 Gr60"
    grade: str | None    # "316L", "420", etc.
    family: str | None   # "stainless_steel", "carbon_steel", "polymer"
    standard: str | None # "ASTM", "AISI", "DIN"

class ConnectionSpec(BaseModel):
    type: str           # "NPT", "Flanged", "Welded"
    size: str           # "2 inch", "DN50"
    rating: str | None  # "PN40", "Class 150", "ANSI 150"

class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    CLARIFICATION_NEEDED = "clarification_needed"
    NOT_APPLICABLE = "not_applicable"
    DEVIATION_ACCEPTABLE = "deviation_acceptable"

class RiskLevel(str, Enum):
    DISQUALIFYING = "disqualifying"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
```

### 2. Product Schema (product_schemas.py)

Basado en los datos reales extraidos del data sheet I-FD-3010.2G-5330-540-DTG-302-C:

```python
class ComponentSpec(BaseModel):
    tag: str                    # "P1", "RS1", "LS3", "PS1"
    type: str                   # "pump", "heater", "sensor", "valve"
    name: str                   # "Progressive cavity pump PCM 13c12s"
    materials: dict[str, MaterialSpec]  # {"body": ..., "rotor": ..., "stator": ...}
    mechanical: dict | None     # capacity, pressure, connections
    electrical: dict | None     # voltage, power, IP, insulation
    instrumentation: dict | None # range, accuracy, output signal
    dimensional: dict | None    # weight, dimensions

class ProductPerformance(BaseModel):
    service: str
    capacity: MeasuredValue
    oil_input_max_ppm: int
    oil_output_max_ppm: int
    design_pressure: MeasuredValue
    design_temperature: MeasuredValue
    operation_mode: str  # "continuous" | "intermittent"

class ProductSpec(BaseModel):
    product_id: str
    product_family: str         # "OWS", "GWT", etc.
    manufacturer: str
    model: str
    revision: str
    performance: ProductPerformance
    certifications: list[str]
    components: list[ComponentSpec]
    package_level: dict | None  # weight, dimensions, noise, electrical load
```

### 3. Tender Schema (tender_schemas.py)

Basado en la estructura del Material Requisition I-RM-3010.2G-5330-667-KES-301:

```python
class TenderMetadata(BaseModel):
    project_name: str           # "P-78 FPSO Buzios"
    project_code: str | None
    client: str                 # "Petrobras"
    contractor: str             # "Keppel/HHI"
    classification_society: str # "ABS"
    vessel_type: str | None     # "FPSO"
    location: str | None        # "Santos Basin, Brazil"

class ProcessRequirement(BaseModel):
    service: str
    flow_rate: MeasuredValue
    oil_input_max_ppm: int
    oil_output_max_ppm: int
    design_pressure: MeasuredValue
    design_temperature: MeasuredValue
    suction_pressure_min: MeasuredValue | None
    discharge_pressure_min: MeasuredValue | None
    operation_mode: str
    regulatory_compliance: list[str]

class TenderRequirementItem(BaseModel):
    id: str
    category: str               # "process", "material", "electrical", etc.
    requirement_text: str
    mandatory: bool             # SHALL=True, SHOULD=False
    source_document: str
    source_section: str
    extracted_values: dict | None

class TenderSpec(BaseModel):
    tender_id: str
    metadata: TenderMetadata
    general_requirements: dict  # design_life, field_proven, asbestos_free, etc.
    process_requirements: ProcessRequirement
    material_requirements: list[TenderRequirementItem]
    electrical_requirements: dict
    instrumentation_requirements: dict
    applicable_standards: list[dict]
    qa_qc_requirements: dict
    scope_line_items: list[dict]
```

### 4. Compliance Schema (compliance_schemas.py)

```python
class CostImpact(BaseModel):
    estimated_delta_eur: float
    confidence: str             # "high", "medium", "low"
    notes: str | None

class ComplianceItem(BaseModel):
    requirement_id: str
    category: str
    requirement_text: str
    product_value: str | None
    tender_value: str
    status: ComplianceStatus
    gap_description: str | None
    modification_needed: str | None
    cost_impact: CostImpact | None
    risk_level: RiskLevel
    source_document: str
    source_section: str | None

class ComplianceSummary(BaseModel):
    total_requirements: int
    compliant_count: int
    non_compliant_count: int
    partial_count: int
    clarification_count: int
    estimated_total_delta_eur: float
    disqualifying_gaps: list[str]
    key_deviations: list[str]

class ComplianceResult(BaseModel):
    comparison_id: str
    product_id: str
    tender_id: str
    overall_score: float        # 0-100
    items: list[ComplianceItem]
    summary: ComplianceSummary
```

## Principios de diseno

1. **Flexibilidad con JSONB**: Los campos `dict` genericos permiten capturar specs inesperadas sin romper el schema
2. **Materiales como objetos**: No strings planos sino `MaterialSpec` con designation, grade, family para comparaciones inteligentes
3. **Medidas con unidades**: `MeasuredValue` evita ambiguedades (3.5 bar vs 3.5 barg vs 50 psi)
4. **Trazabilidad**: Cada item de compliance referencia su fuente (documento, seccion, pagina)
5. **Compatibilidad con Instructor**: Todos los schemas son Pydantic BaseModel, lo que permite usarlos directamente como `response_model` en Instructor para extraccion LLM validada

## Validacion semantica con Instructor

Los schemas pueden incluir validadores custom que Instructor aplica automaticamente:

```python
from pydantic import field_validator

class ComponentSpec(BaseModel):
    tag: str
    type: str
    materials: dict[str, MaterialSpec]

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid_types = {"pump", "heater", "sensor", "valve", "gauge",
                       "display", "monitor", "strainer", "regulator"}
        if v.lower() not in valid_types:
            raise ValueError(f"Unknown component type: {v}")
        return v.lower()
```

Si el LLM produce un tipo invalido, Instructor re-intenta la llamada automaticamente.

## Dependencias

- Requiere: ninguna (es una definicion pura de modelos)
- Libreria: `pydantic`
- Usado por: `03_llm_adapters` (Instructor), `07_motor_compliance` (matchers)

## Sesiones estimadas

1 sesion. Los schemas estan bien definidos por el analisis de los documentos reales. Se iteraran segun surjan campos nuevos durante la extraccion.

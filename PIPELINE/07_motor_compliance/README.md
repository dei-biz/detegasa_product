# 07 - Motor de Compliance

## Objetivo

Implementar el motor central que compara las especificaciones de un producto contra los requisitos de una licitacion, identificando cumplimiento, gaps, y posibles modificaciones. Este es el modulo mas complejo y critico del sistema.

## Entregables

1. **compliance_engine.py** - Orquestador principal del pipeline de comparacion
2. **matchers/** - Modulos especializados por categoria
   - `process_matcher.py` - Caudal, presion, temperatura
   - `material_matcher.py` - Grados de material y equivalencias
   - `electrical_matcher.py` - Voltaje, IP rating, aislamiento
   - `certification_matcher.py` - Normas, certificaciones, standards
   - `dimensional_matcher.py` - Peso, dimensiones, CoG
   - `environmental_matcher.py` - Ruido, vibracion, vida util
3. **llm_comparator.py** - Comparacion asistida por LLM para requisitos complejos
4. **report_generator.py** - Generacion de informe de compliance

## Como implementarlo

### 1. Pipeline de comparacion (3 pasos)

```
Paso 1: Matching Deterministico
  - Comparacion directa de valores numericos y strings
  - Rapido, sin coste API
  - Cubre ~60% de los requisitos

Paso 2: Matching Semantico
  - Busqueda vectorial para encontrar info relevante del producto
  - Para requisitos sin correspondencia directa en el JSON
  - Cubre ~20% adicional

Paso 3: Evaluacion LLM
  - Para requisitos que requieren juicio tecnico
  - Equivalencias de normas, interpretacion de "field proven", etc.
  - Cubre el ~20% restante
```

### 2. Matchers deterministicos

#### Process Matcher

```python
class ProcessMatcher:
    def compare(self, product: ProductSpec, tender: TenderSpec) -> list[ComplianceItem]:
        items = []

        # Caudal
        items.append(self._compare_numeric(
            "Flow rate",
            product.performance.capacity,
            tender.process_requirements.flow_rate,
            operator=">=",  # producto debe cumplir o superar
            category="process"
        ))

        # Presion de diseno
        items.append(self._compare_numeric(
            "Design pressure",
            product_design_pressure,
            tender.process_requirements.design_pressure,
            operator=">=",
            category="process"
        ))

        # Contenido de aceite a la salida
        items.append(self._compare_numeric(
            "Oil output max ppm",
            MeasuredValue(value=product.performance.oil_output_max_ppm, unit="ppm"),
            MeasuredValue(value=tender.process_requirements.oil_output_max_ppm, unit="ppm"),
            operator="<=",  # producto debe ser igual o menor
            category="process"
        ))

        return items

    def _compare_numeric(self, name, product_val, tender_val, operator, category):
        # Convertir unidades si es necesario (bar vs psi, etc.)
        prod_normalized = self._normalize_unit(product_val)
        tend_normalized = self._normalize_unit(tender_val)

        if operator == ">=" and prod_normalized >= tend_normalized:
            status = ComplianceStatus.COMPLIANT
        elif operator == "<=" and prod_normalized <= tend_normalized:
            status = ComplianceStatus.COMPLIANT
        else:
            status = ComplianceStatus.NON_COMPLIANT

        return ComplianceItem(
            category=category,
            requirement_text=f"{name}: {tender_val}",
            product_value=str(product_val),
            tender_value=str(tender_val),
            status=status,
            gap_description=f"Product {prod_normalized} vs required {tend_normalized}" if status != ComplianceStatus.COMPLIANT else None,
            risk_level=RiskLevel.HIGH if status == ComplianceStatus.NON_COMPLIANT else RiskLevel.LOW
        )
```

#### Material Matcher

Este es el mas interesante porque requiere conocimiento de jerarquias de materiales:

```python
class MaterialMatcher:
    # Jerarquia de materiales (mayor numero = mayor resistencia/coste)
    MATERIAL_HIERARCHY = {
        "carbon_steel": 1,
        "galvanized_steel": 2,
        "duplex_stainless": 4,
        "ss_304": 3,
        "ss_316": 4,
        "ss_316l": 5,
        "super_duplex": 6,
        "titanium": 7,
        "inconel": 8,
    }

    # Mapeo de designaciones comunes
    MATERIAL_ALIASES = {
        "AISI-316L": "ss_316l",
        "SS 316L": "ss_316l",
        "Stainless Steel 316L": "ss_316l",
        "ASTM A516 Grade 60": "carbon_steel",
        "Carbon Steel": "carbon_steel",
        "SS 420": "ss_420",
        "NBR": "nitrile_rubber",
        "EPDM": "epdm_rubber",
        "Viton": "viton_rubber",
    }

    def compare_material(self, product_mat: MaterialSpec, required_mat: str) -> ComplianceItem:
        prod_family = self._normalize(product_mat.designation)
        req_family = self._normalize(required_mat)

        prod_rank = self.MATERIAL_HIERARCHY.get(prod_family, 0)
        req_rank = self.MATERIAL_HIERARCHY.get(req_family, 0)

        if prod_rank >= req_rank:
            return ComplianceItem(status=ComplianceStatus.COMPLIANT, ...)
        else:
            return ComplianceItem(
                status=ComplianceStatus.NON_COMPLIANT,
                gap_description=f"Product uses {product_mat.designation}, tender requires {required_mat}",
                modification_needed=f"Upgrade from {product_mat.designation} to {required_mat}",
                cost_impact=self._estimate_upgrade_cost(prod_family, req_family),
                risk_level=RiskLevel.MEDIUM
            )
```

#### Certification Matcher

```python
class CertificationMatcher:
    # Certificaciones equivalentes o que cubren otras
    CERT_COVERS = {
        "IMO MEPC 107(49)": ["MARPOL Annex I"],  # Si tienes MEPC 107(49), cubres MARPOL
        "ISO 9001:2015": ["ISO 9001"],
        "IEC 61892": ["IEC 60092"],  # Extension para offshore
    }

    def compare(self, product_certs: list[str], required_certs: list[str]) -> list[ComplianceItem]:
        items = []
        for req_cert in required_certs:
            found = False
            for prod_cert in product_certs:
                if self._cert_matches(prod_cert, req_cert):
                    found = True
                    break
            items.append(ComplianceItem(
                status=ComplianceStatus.COMPLIANT if found else ComplianceStatus.NON_COMPLIANT,
                requirement_text=f"Certification: {req_cert}",
                ...
            ))
        return items
```

### 3. Comparacion asistida por LLM (via Instructor)

Para requisitos que no se pueden resolver con logica determinista, se usa Instructor para obtener un `ComplianceItem` validado directamente:

```python
import instructor
from langfuse.decorators import observe

class LLMComparator:
    SYSTEM_PROMPT = """You are a maritime engineering compliance assessor.
    You are comparing a product specification against a tender requirement.
    You must determine if the product complies with the requirement.

    Consider:
    - Maritime and offshore engineering standards
    - Material equivalences and hierarchies
    - Whether a "SHOULD" requirement is advisory vs mandatory
    - Whether a partial compliance is acceptable with modifications"""

    @observe(name="compliance_assessment")  # Langfuse tracking
    async def assess(self, requirement: str, product_context: str) -> ComplianceItem:
        # Instructor garantiza que el output es un ComplianceItem valido
        result = await self.instructor_client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=2048,
            system=self.SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"REQUIREMENT:\n{requirement}\n\nPRODUCT SPECIFICATION:\n{product_context}"
            }],
            response_model=ComplianceItem,  # Output Pydantic garantizado
            max_retries=3,                  # Reintenta si la validacion falla
        )
        return result
```

Ventaja de usar Instructor aqui: si el LLM produce un `risk_level` invalido o un `status` que no esta en el enum, Instructor re-intenta automaticamente con feedback del error de validacion.

Casos donde se usa el LLM:
- "Field proven: 3 offshore installations, 24000 hours" (necesita verificar el historial del fabricante)
- "Equipment shall withstand 100-year return period environmental conditions" (requiere interpretar datos metoceanicos)
- "All non-current carrying metallic parts shall be earthed" (busqueda semantica + juicio)
- Equivalencias entre normas brasilenas (NR-12) e internacionales

### 4. Orquestador

```python
class ComplianceEngine:
    def __init__(self, matchers, llm_comparator, embedding_service, llm_adapter):
        self.matchers = matchers
        self.llm_comparator = llm_comparator
        self.embedding_service = embedding_service
        self.llm = llm_adapter

    async def run_comparison(self, product: ProductSpec, tender: TenderSpec) -> ComplianceResult:
        all_items = []

        # Paso 1: Matching deterministico
        for matcher in self.matchers:
            items = matcher.compare(product, tender)
            all_items.extend(items)

        # Paso 2: Requisitos pendientes -> busqueda semantica + LLM
        unmatched = self._get_unmatched_requirements(tender, all_items)
        for req in unmatched:
            context = await self.embedding_service.find_product_info(req.text, product.product_id)
            assessment = await self.llm_comparator.assess(req.text, context, self.llm)
            all_items.append(assessment)

        # Paso 3: Calcular score y generar resumen
        score = self._calculate_score(all_items)
        summary = self._generate_summary(all_items)

        return ComplianceResult(
            overall_score=score,
            items=all_items,
            summary=summary
        )
```

### 5. Generacion de informes

Formatos de salida:
- **JSON**: Para integracion con otros sistemas
- **XLSX**: Formato TBT (Technical Bid Evaluation Table) compatible con Appendix 12
- **HTML/PDF**: Informe legible para revision humana

```python
class ReportGenerator:
    def to_xlsx(self, result: ComplianceResult, template_path: str | None = None) -> bytes:
        """Genera Excel en formato TBT."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Compliance Report"

        # Headers
        headers = ["#", "Category", "Requirement", "Product Value",
                   "Status", "Gap", "Modification", "Cost Delta (EUR)", "Risk"]
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)

        # Data rows
        for i, item in enumerate(result.items, 2):
            ws.cell(row=i, column=1, value=i-1)
            ws.cell(row=i, column=2, value=item.category)
            # ... etc

        # Color coding por status
        # Compliant = verde, Non-compliant = rojo, Partial = amarillo

        return save_virtual_workbook(wb)
```

## Retos conocidos

1. **Requisitos ambiguos**: "Equipment shall be of proven design" - que significa exactamente? Necesita interpretacion LLM + datos del fabricante
2. **Requisitos cruzados**: Un requisito de material puede afectar al cumplimiento de presion
3. **Requisitos implicitos**: La clasificacion ABS implica una serie de requisitos que no estan explicitamente listados
4. **Coste de modificaciones**: Necesitamos datos reales de DETEGASA para ser precisos

## Dependencias

- Requiere: todos los modulos anteriores (01-06)
- El mas dependiente del tuning con datos reales

## Sesiones estimadas

3-4 sesiones:
- Sesion 1: Matchers deterministicos (process, material, electrical)
- Sesion 2: Certification matcher + LLM comparator
- Sesion 3: Orquestador + generacion de informes
- Sesion 4: Testing y tuning contra el TBT real (Appendix 12)

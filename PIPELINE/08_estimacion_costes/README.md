# 08 - Estimacion de Costes

## Objetivo

Proporcionar estimaciones de coste para las modificaciones necesarias cuando un producto no cumple un requisito de la licitacion. El objetivo es que DETEGASA pueda incluir estos deltas en su propuesta economica.

## Entregables

1. **cost_estimator.py** - Motor de estimacion basado en reglas y tablas de costes
2. **cost_tables.py** - Tablas de referencia de costes por tipo de modificacion
3. **cost_report.py** - Generacion de resumen economico de gaps

## Como implementarlo

### 1. Categorias de coste

```python
class CostCategory(str, Enum):
    MATERIAL_UPGRADE = "material_upgrade"      # Cambio de material
    CERTIFICATION = "certification"            # Obtener certificacion
    DESIGN_CHANGE = "design_change"            # Cambio de diseno
    ADDITIONAL_EQUIPMENT = "additional_equipment"  # Equipamiento extra
    DOCUMENTATION = "documentation"            # Documentacion adicional
    TESTING = "testing"                        # Testing adicional
    PAINTING = "painting"                      # Esquema de pintura especial
```

### 2. Tablas de costes de referencia

Estas tablas son **puntos de partida** que DETEGASA deberia refinar con sus datos internos:

```python
MATERIAL_UPGRADE_COSTS = {
    # (material_actual, material_requerido): coste_factor o coste_fijo
    ("carbon_steel", "ss_316l"): {
        "type": "factor",
        "value": 2.5,           # Factor sobre el coste del componente
        "unit": "per_component",
        "confidence": "medium",
        "notes": "Depende del tamano del componente"
    },
    ("neoprene", "viton"): {
        "type": "factor",
        "value": 1.8,
        "unit": "per_seal",
        "confidence": "high"
    },
    ("standard_paint", "offshore_epoxy"): {
        "type": "rate",
        "value": 45,             # EUR/m2
        "unit": "per_m2",
        "confidence": "medium"
    },
}

CERTIFICATION_COSTS = {
    "INMETRO": {
        "fixed_eur": 15000,
        "per_item_eur": 2000,
        "time_weeks": 12,
        "confidence": "medium"
    },
    "ABS_type_approval": {
        "fixed_eur": 25000,
        "time_weeks": 16,
        "confidence": "low"
    },
    "NR-12_compliance": {
        "fixed_eur": 8000,
        "time_weeks": 6,
        "confidence": "medium"
    },
    "NR-13_pressure_vessel": {
        "fixed_eur": 5000,
        "per_vessel_eur": 3000,
        "time_weeks": 8,
        "confidence": "medium"
    },
}

DESIGN_CHANGE_COSTS = {
    "ip_rating_upgrade": {
        "from": "IP55",
        "to": "IP66",
        "cost_eur": 500,
        "per": "component",
        "confidence": "medium"
    },
    "insulation_class_upgrade": {
        "from": "B",
        "to": "F",
        "cost_eur": 200,
        "per": "motor",
        "confidence": "high"
    },
    "noise_reduction": {
        "cost_eur": 3000,
        "per": "package",
        "notes": "Encapsulamiento acustico",
        "confidence": "low"
    },
}
```

### 3. Estimador

```python
class CostEstimator:
    def __init__(self, cost_tables: dict):
        self.tables = cost_tables

    def estimate_gap_cost(self, gap: ComplianceItem) -> CostImpact:
        """Estima el coste de resolver un gap de compliance."""

        if gap.category == "material":
            return self._estimate_material_cost(gap)
        elif gap.category == "certification":
            return self._estimate_certification_cost(gap)
        elif gap.category == "electrical":
            return self._estimate_electrical_cost(gap)
        else:
            return CostImpact(
                estimated_delta_eur=0,
                confidence="low",
                notes="Requiere evaluacion manual por ingenieria"
            )

    def _estimate_material_cost(self, gap):
        product_mat = self._normalize_material(gap.product_value)
        required_mat = self._normalize_material(gap.tender_value)
        key = (product_mat, required_mat)

        if key in self.tables["material_upgrades"]:
            cost_data = self.tables["material_upgrades"][key]
            return CostImpact(
                estimated_delta_eur=cost_data["value"],
                confidence=cost_data["confidence"],
                notes=cost_data.get("notes", "")
            )

        return CostImpact(
            estimated_delta_eur=0,
            confidence="low",
            notes=f"No hay datos de coste para upgrade {product_mat} -> {required_mat}"
        )

    def generate_cost_summary(self, items: list[ComplianceItem]) -> dict:
        """Genera resumen economico."""
        non_compliant = [i for i in items if i.status == ComplianceStatus.NON_COMPLIANT]
        total_cost = sum(i.cost_impact.estimated_delta_eur for i in non_compliant if i.cost_impact)
        high_confidence = sum(
            i.cost_impact.estimated_delta_eur for i in non_compliant
            if i.cost_impact and i.cost_impact.confidence == "high"
        )

        return {
            "total_estimated_delta_eur": total_cost,
            "high_confidence_delta_eur": high_confidence,
            "items_without_cost_data": len([
                i for i in non_compliant
                if not i.cost_impact or i.cost_impact.confidence == "low"
            ]),
            "breakdown_by_category": self._group_by_category(non_compliant),
            "recommendation": "Revisar items con confianza 'low' con ingenieria"
        }
```

### 4. Integracion con datos reales de DETEGASA

El sistema debe permitir que DETEGASA actualice las tablas de costes:

- **Via API**: Endpoint para actualizar tablas de costes
- **Via XLSX**: Importar una hoja de calculo con costes de referencia
- **Feedback loop**: Cuando DETEGASA gana una licitacion, registrar el coste real vs estimado para calibrar

## Datos necesarios de DETEGASA

Para que las estimaciones sean utiles, necesitamos que DETEGASA proporcione:

1. **Coste base por componente** del OWS estandar
2. **Deltas historicos** de modificaciones pasadas (ej: cuanto costo upgrader a SS316L en proyecto X)
3. **Costes de certificacion** reales (INMETRO, ABS, etc.)
4. **Costes de ingenieria** por hora para cambios de diseno
5. **Markup de modificaciones** (factor que aplican sobre el coste directo)

## Dependencias

- Requiere: `04_schemas_json` (modelos), `07_motor_compliance` (gaps)
- Datos externos: tablas de costes de DETEGASA

## Sesiones estimadas

1 sesion para la estructura + tablas de referencia. La calibracion con datos reales es un proceso continuo.

# Esquema de Producto DETEGASA

Descripcion completa de la estructura de datos `ProductSpec` — la representacion canonica de cualquier producto DETEGASA en el sistema.

---

## Vision general

```
ProductSpec
├── Identificacion (product_id, model, manufacturer, revision)
├── Familia de producto (product_family → OWS, GWT, ...)
├── Performance (union discriminada por familia)
│   ├── OWSPerformance  — Separador de aguas oleosas
│   └── GWTPerformance  — Tratamiento de aguas grises
├── Certificaciones (lista de CertificationSpec)
│   └── CertificationSpec
│       ├── standard_code, cert_type
│       ├── applicability (certified/pending/not_applicable/...)
│       ├── issuing_body, certificate_no
│       └── valid_from, valid_until, scope, notes
├── Componentes (lista de ComponentSpec)
│   └── ComponentSpec
│       ├── Materiales (dict de MaterialSpec)
│       ├── Mecanica
│       ├── Electrica
│       ├── Instrumentacion
│       └── Dimensional
└── Package-level (datos a nivel de paquete completo)
```

---

## 1. `ProductSpec` — Producto completo

El schema raiz que describe un producto DETEGASA en su totalidad.

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `product_id` | `str` | si | Identificador interno del producto. Ej: `"OWS-5330501"` |
| `product_family` | `str` | — | Familia de producto: `"OWS"`, `"GWT"`, `"REFUELLING"`, etc. Por defecto `"OWS"` |
| `manufacturer` | `str` | — | Fabricante. Por defecto `"DETEGASA"` |
| `model` | `str` | si | Designacion del modelo. Ej: `"OWS-5"`, `"GWT-10"` |
| `revision` | `str` | — | Letra de revision del documento. Ej: `"C"`, `"IAB"` |
| `performance` | `ProductPerformance` | si | Datos de rendimiento (ver seccion 2) |
| `certifications` | `list[CertificationSpec]` | — | Estandares, certificaciones y codigos de diseno con estado de aplicabilidad (ver seccion 3) |
| `components` | `list[ComponentSpec]` | — | Lista de componentes (ver seccion 4) |
| `package_level` | `dict` | — | Specs a nivel paquete: peso total, dimensiones, ruido, carga electrica |

### Ejemplo JSON

```json
{
  "product_id": "OWS-5330501",
  "product_family": "OWS",
  "manufacturer": "DETEGASA",
  "model": "OWS-5",
  "revision": "C",
  "performance": { "family": "OWS", "..." : "..." },
  "certifications": [
    {
      "standard_code": "IMO MEPC 107(49)",
      "cert_type": "regulatory",
      "applicability": "certified",
      "issuing_body": "ABS",
      "certificate_no": "TAC-2024-00123",
      "valid_until": "2029-03-14",
      "scope": "OWS 1-5 m3/h"
    },
    {
      "standard_code": "INMETRO",
      "cert_type": "country",
      "applicability": "pending",
      "notes": "Certification process started Q1 2025"
    }
  ],
  "components": [ "..." ],
  "package_level": {
    "total_weight_kg": 4500,
    "dimensions_mm": {"L": 3200, "W": 1800, "H": 2400},
    "max_noise_db": 82,
    "total_electrical_load_kw": 35
  }
}
```

---

## 2. Performance — Union discriminada por familia

El campo `performance` usa una **union discriminada** por el campo `family`. Esto permite que cada familia de producto tenga sus propios campos especificos, manteniendo una base comun.

### 2.1 `BasePerformance` — Campos comunes

Campos compartidos por todas las familias de producto.

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `service` | `str` | si | Descripcion del servicio. Ej: `"Bilge water separation"` |
| `capacity` | `MeasuredValue` | si | Capacidad de flujo. Ej: `{"value": 5.0, "unit": "m3/h"}` |
| `design_pressure` | `MeasuredValue` | si | Presion de diseno. Ej: `{"value": 6.7, "unit": "barg"}` |
| `design_temperature` | `MeasuredValue` | si | Temperatura de diseno. Ej: `{"value": 60, "unit": "C"}` |
| `operation_mode` | `str` | si | Modo de operacion: `"continuous"` o `"intermittent"` |

### 2.2 `OWSPerformance` — Separador de Aguas Oleosas

Familia: `"OWS"`. Hereda de `BasePerformance`.

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `family` | `Literal["OWS"]` | si | Discriminador. Siempre `"OWS"` |
| `oil_input_max_ppm` | `int` | si | Contenido maximo de aceite a la entrada (ppm). Tipico: `500` |
| `oil_output_max_ppm` | `int` | si | Contenido maximo de aceite a la salida (ppm). Regulacion: `<=15` |

```json
{
  "family": "OWS",
  "service": "Bilge water separation",
  "capacity": {"value": 5.0, "unit": "m3/h"},
  "design_pressure": {"value": 6.7, "unit": "barg"},
  "design_temperature": {"value": 60, "unit": "C"},
  "operation_mode": "intermittent",
  "oil_input_max_ppm": 500,
  "oil_output_max_ppm": 15
}
```

### 2.3 `GWTPerformance` — Tratamiento de Aguas Grises

Familia: `"GWT"`. Hereda de `BasePerformance`.

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `family` | `Literal["GWT"]` | si | Discriminador. Siempre `"GWT"` |
| `bod_input_mg_l` | `float \| None` | — | BOD (demanda biologica de oxigeno) a la entrada (mg/L) |
| `bod_output_mg_l` | `float \| None` | — | BOD a la salida (mg/L) |
| `tss_input_mg_l` | `float \| None` | — | TSS (solidos totales en suspension) a la entrada (mg/L) |
| `tss_output_mg_l` | `float \| None` | — | TSS a la salida (mg/L) |

```json
{
  "family": "GWT",
  "service": "Grey water treatment",
  "capacity": {"value": 10.0, "unit": "m3/h"},
  "design_pressure": {"value": 4.0, "unit": "barg"},
  "design_temperature": {"value": 45, "unit": "C"},
  "operation_mode": "continuous",
  "bod_input_mg_l": 250.0,
  "bod_output_mg_l": 25.0,
  "tss_input_mg_l": 100.0,
  "tss_output_mg_l": 10.0
}
```

### 2.4 Extensibilidad

Para anadir una nueva familia (ej. `REFUELLING`, `STP`):

1. Crear una clase que herede de `BasePerformance` con `family: Literal["REFUELLING"]`
2. Anadirla a la union `ProductPerformance`
3. El campo `family` en el JSON determina automaticamente que schema se usa

---

## 3. `CertificationSpec` — Estandares y certificaciones

Cada entrada en `certifications` es un `CertificationSpec` estructurado que captura no solo *que* estandar aplica, sino *como* aplica: si el producto esta certificado, si la certificacion esta pendiente, si el estandar no aplica, o si podria llegar a aplicar en funcion del proyecto.

### 3.1 Campos

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `standard_code` | `str` | si | Codigo del estandar o regulacion. Ej: `"IMO MEPC 107(49)"`, `"ATEX 2014/34/EU"`, `"ASME VIII Div.1"` |
| `standard_title` | `str` | — | Titulo completo del estandar (para claridad) |
| `cert_type` | `CertType` | si | Categoria del estandar (ver tabla abajo) |
| `applicability` | `ApplicabilityStatus` | si | Estado de aplicabilidad (ver tabla abajo) |
| `issuing_body` | `str` | — | Organismo emisor/evaluador: `"ABS"`, `"RINA"`, `"INMETRO"`, `"TUV"` |
| `certificate_no` | `str` | — | Numero de certificado o type-approval, si ha sido emitido |
| `valid_from` | `date \| None` | — | Fecha de emision/inicio de vigencia |
| `valid_until` | `date \| None` | — | Fecha de caducidad del certificado |
| `scope` | `str` | — | Alcance de la certificacion: `"OWS 1-5 m3/h bilge water separators"` |
| `notes` | `str` | — | Texto libre para contexto adicional, condiciones, o notas de evolucion |

### 3.2 `CertType` — Categorias de estandar

| Valor | Descripcion | Ejemplos |
|-------|-------------|----------|
| `regulatory` | Regulaciones internacionales maritimas | IMO MEPC 107(49), MARPOL Annex I, SOLAS, EU MED |
| `class_society` | Aprobaciones de sociedad clasificadora | ABS, DNV, Bureau Veritas, Lloyd's Register, RINA |
| `hazardous_area` | Certificaciones de zona peligrosa | ATEX 2014/34/EU, IECEx |
| `country` | Certificaciones nacionales | INMETRO (Brasil), UL (USA), CSA (Canada), CCS (China) |
| `quality` | Sistemas de calidad y directivas | ISO 9001, PED (Pressure Equipment Directive), CE marking |
| `design_code` | Codigos de diseno aplicados | ASME VIII, API 11AX, IEC 61892, NEMA, EN 12953 |

### 3.3 `ApplicabilityStatus` — Estados de aplicabilidad

| Valor | Significado | Caso tipico |
|-------|-------------|-------------|
| `certified` | Tiene certificado valido y vigente | IMO type-approval activo con numero y fecha |
| `compliant` | Cumple el estandar pero sin certificacion formal | Diseno conforme a ASME VIII sin stamp |
| `pending` | Proceso de certificacion en curso | INMETRO en tramite para proyecto Petrobras |
| `applicable` | Aplica y debe ser abordado | Requisito identificado, aun no evaluado |
| `potentially_applicable` | Podria aplicar segun el proyecto | IECEx si la zona se clasifica como peligrosa |
| `not_applicable` | Explicitamente no aplica | ATEX para equipo en sala de maquinas no clasificada |
| `non_compliant` | Evaluado y no cumple | Requisito que el producto no satisface |
| `expired` | Tuvo certificacion pero ha caducado | Certificado DNV vencido pendiente de renovacion |

### 3.4 Ejemplos por caso de uso

**Certificacion activa (IMO type-approval via ABS):**
```json
{
  "standard_code": "IMO MEPC 107(49)",
  "standard_title": "Guidelines for Oily Water Separating Equipment",
  "cert_type": "regulatory",
  "applicability": "certified",
  "issuing_body": "ABS",
  "certificate_no": "TAC-2024-00123",
  "valid_from": "2024-03-15",
  "valid_until": "2029-03-14",
  "scope": "OWS 1-5 m3/h bilge water separators"
}
```

**Certificacion pendiente (INMETRO para Petrobras):**
```json
{
  "standard_code": "INMETRO",
  "cert_type": "country",
  "applicability": "pending",
  "notes": "Certification process started Q1 2025. Required by Petrobras for all electrical equipment."
}
```

**Estandar que no aplica (ATEX en zona no peligrosa):**
```json
{
  "standard_code": "ATEX 2014/34/EU",
  "cert_type": "hazardous_area",
  "applicability": "not_applicable",
  "notes": "Equipment installed in non-hazardous engine room per area classification"
}
```

**Estandar que podria aplicar (IECEx):**
```json
{
  "standard_code": "IECEx",
  "cert_type": "hazardous_area",
  "applicability": "potentially_applicable",
  "notes": "Depends on area classification at installation site"
}
```

**Codigo de diseno seguido (ASME VIII):**
```json
{
  "standard_code": "ASME VIII Div.1",
  "cert_type": "design_code",
  "applicability": "compliant",
  "notes": "Pressure vessel designed per ASME VIII Div.1, no U-stamp required for this application"
}
```

**Certificado caducado (DNV):**
```json
{
  "standard_code": "DNV GL",
  "cert_type": "class_society",
  "applicability": "expired",
  "issuing_body": "DNV",
  "certificate_no": "TAP-2019-456",
  "valid_until": "2024-06-30",
  "notes": "Renewal pending"
}
```

### 3.5 Uso en comparacion con tender

Cuando el sistema compara un `ProductSpec` contra un `TenderSpec`, las certificaciones estructuradas permiten:

1. **Match automatico**: `tender.regulatory_compliance` vs `product.certifications` filtrado por `cert_type=regulatory` y `applicability=certified`
2. **Deteccion de gaps**: requisito del tender sin entrada correspondiente en producto, o con `applicability=non_compliant`
3. **Estimacion de coste**: certificaciones `pending` tienen coste estimable; `not_applicable` se pueden justificar
4. **Priorizacion de riesgo**: `certified` = riesgo bajo; `pending` = riesgo medio; `non_compliant` o sin entrada = riesgo alto

---

## 4. `ComponentSpec` — Componente individual

Cada producto se compone de multiples componentes (bombas, sensores, valvulas, etc.).

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `tag` | `str` | si | Tag del componente. Ej: `"P1"`, `"RS1"`, `"LS3"`, `"PS1"` |
| `type` | `str` | si | Tipo de componente (ver lista valida abajo). Se normaliza a minusculas |
| `name` | `str` | si | Nombre/modelo del componente. Ej: `"Progressive cavity pump PCM 13c12s"` |
| `materials` | `dict[str, MaterialSpec]` | — | Materiales por parte: `{"body": ..., "rotor": ..., "stator": ...}` |
| `mechanical` | `dict` | — | Specs mecanicas: capacidad, presion, conexiones |
| `electrical` | `dict` | — | Specs electricas: tension, potencia, IP, clase de aislamiento |
| `instrumentation` | `dict` | — | Specs de instrumentacion: rango, precision, senal de salida |
| `dimensional` | `dict` | — | Datos dimensionales: peso, dimensiones (L, W, H) |

### Tipos de componente validos

| Tipo | Descripcion | Ejemplo real |
|------|-------------|--------------|
| `pump` | Bombas | Progressive cavity pump PCM 13c12s |
| `separator` | Separadores | Oily water separator (coalescence) |
| `heater` | Calentadores | Electric immersion heater 24 kW |
| `filter` | Filtros | 2nd stage coalescence filter |
| `strainer` | Coladores | Y-type strainer DN50 |
| `tank` | Tanques/depositos | Sludge collection tank 200L |
| `valve` | Valvulas | 3-way solenoid valve DN25 |
| `sensor` | Sensores | Oil content sensor 0-50 ppm |
| `switch` | Interruptores | Level switch float type |
| `transmitter` | Transmisores | Pressure transmitter 4-20mA |
| `gauge` | Manometros/indicadores | Pressure gauge 0-10 bar |
| `indicator` | Indicadores | Flow indicator local mount |
| `display` | Displays | Touch panel 7" HMI |
| `monitor` | Monitores | Oil content monitor 15 ppm alarm |
| `controller` | Controladores | PLC Siemens S7-1200 |
| `panel` | Paneles electricos | MCC panel 440V/60Hz |
| `regulator` | Reguladores | Pressure regulator 0-6 bar |
| `flow_meter` | Caudalimetros | Electromagnetic flowmeter DN50 |
| `analyzer` | Analizadores | Oil-in-water analyzer IR |
| `alarm` | Alarmas | High level alarm audible+visual |

### Ejemplo completo de componente

```json
{
  "tag": "P1",
  "type": "pump",
  "name": "Progressive cavity pump PCM 13c12s",
  "materials": {
    "body": {
      "designation": "SS 316L",
      "grade": "316L",
      "family": "stainless_steel",
      "standard": "AISI"
    },
    "rotor": {
      "designation": "SS 420",
      "grade": "420",
      "family": "stainless_steel"
    },
    "stator": {
      "designation": "NBR",
      "family": "polymer"
    }
  },
  "mechanical": {
    "connections": "PN40 DN50 Class 150 NPS 2\"",
    "capacity_m3h": 5,
    "max_pressure_bar": 3.5
  },
  "electrical": {
    "voltage": "440V",
    "frequency_hz": 60,
    "phases": 3,
    "power_kw": 3,
    "ip_rating": "IP66",
    "insulation_class": "F",
    "speed_rpm": 600
  }
}
```

---

## 5. Tipos auxiliares

### 5.1 `MeasuredValue` — Valor con unidad

Cualquier magnitud fisica medible.

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `value` | `float` | si | Valor numerico. Puede ser negativo (ej. presion de vacio) |
| `unit` | `str` | si | Unidad de medida: `"bar"`, `"barg"`, `"m3/h"`, `"kW"`, `"mm"`, `"C"`, `"dB(A)"` |

Representacion string: `"5.0 m3/h"`, `"6.7 barg"`, `"-0.3 barg"`

### 5.2 `MaterialSpec` — Especificacion de material

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `designation` | `str` | si | Designacion completa. Ej: `"SS 316L"`, `"Carbon Steel ASTM A516 Gr60"` |
| `grade` | `str \| None` | — | Grado del material. Ej: `"316L"`, `"420"`, `"Gr60"` |
| `family` | `str \| None` | — | Familia: `"stainless_steel"`, `"carbon_steel"`, `"duplex"`, `"polymer"` |
| `standard` | `str \| None` | — | Norma de referencia: `"ASTM"`, `"AISI"`, `"DIN"`, `"EN"` |

### 5.3 `ConnectionSpec` — Conexion de tuberia

| Campo | Tipo | Obligatorio | Descripcion |
|-------|------|:-----------:|-------------|
| `type` | `str` | si | Tipo: `"NPT"`, `"Flanged"`, `"Welded"`, `"Threaded"` |
| `size` | `str` | si | Tamano: `"DN50"`, `"NPS 2"`, `"2 inch"` |
| `rating` | `str \| None` | — | Presion nominal: `"PN40"`, `"Class 150"`, `"ANSI 150"` |

---

## 6. Validaciones automaticas

| Regla | Aplicada en | Comportamiento |
|-------|-------------|----------------|
| Tipo de componente valido | `ComponentSpec.type` | Rechaza tipos no reconocidos con `ValidationError` |
| Normalizacion a minusculas | `ComponentSpec.type` | `"PUMP"` -> `"pump"`, `"Heater"` -> `"heater"` |
| Discriminacion por familia | `ProductSpec.performance` | El campo `family` determina que schema se aplica |
| Enums tipados | `CertType`, `ApplicabilityStatus` | Solo valores validos del enum, serializa a string en JSON |
| Score 0-100 | `ComplianceResult.overall_score` | Rechaza valores fuera de rango |

---

## 7. Flujo de datos

```
PDF/Excel del producto
        |
        v
   Extraccion (PyMuPDF / openpyxl)
        |
        v
   Limpieza (TextCleaner)
        |
        v
   Chunking (DocumentChunker)
        |
        v
   Extraccion LLM (Claude/GPT -> Instructor)
        |
        v
   ProductSpec (validado por Pydantic)
   ├── performance (OWSPerformance / GWTPerformance)
   ├── certifications (CertificationSpec con applicability)
   └── components (ComponentSpec con materials)
        |
        v
   Base de datos (PostgreSQL JSONB)
        |
        v
   Comparacion con TenderSpec -> ComplianceResult
```

Los documentos fuente de DETEGASA (data sheets I-FD-*, manuales MA-*) contienen toda la informacion necesaria para poblar un `ProductSpec` completo, incluyendo los datos de rendimiento, componentes con sus materiales, especificaciones electricas/mecanicas, y las certificaciones con sus numeros y alcances.

---

## 8. Modelos LLM recomendados

### 8.1 Estrategia de dos niveles

Para optimizar coste y calidad, se recomienda usar modelos diferentes segun la complejidad de la tarea de extraccion:

| Tarea | Modelo principal | Alternativa | Coste in/out (por M tokens) | Razon |
|-------|-----------------|-------------|:---------------------------:|-------|
| **Componentes** | `claude-sonnet-4-5` | `gpt-4o` | $3.00 / $15.00 | Extraccion compleja con campos nested (materiales, mecanica, electrica) |
| **Performance** | `claude-sonnet-4-5` | `gpt-4o` | $3.00 / $15.00 | Requiere entender contexto tecnico maritimo y mapear a familia correcta |
| **Certificaciones** | `claude-sonnet-4-5` | `gpt-4o` | $3.00 / $15.00 | Debe interpretar contexto regulatorio y determinar applicability status |
| **Metadata** | `claude-haiku-4-5` | `gpt-4o-mini` | $0.80 / $4.00 | Tarea simple: pocos campos, texto de portada |
| **Requirements** | `claude-sonnet-4-5` | `gpt-4o` | $3.00 / $15.00 | Debe distinguir SHALL/MUST (mandatory) vs SHOULD/MAY (optional) |
| **TBT -> Requirements** | *Sin LLM* | — | $0.00 | Conversion deterministica — los datos ya estan estructurados en el Excel |

### 8.2 Comparacion de modelos disponibles

| Modelo | Proveedor | Input ($/M) | Output ($/M) | Calidad extraccion | Velocidad | Uso recomendado |
|--------|-----------|:-----------:|:------------:|:------------------:|:---------:|-----------------|
| `claude-sonnet-4-5` | Anthropic | $3.00 | $15.00 | Excelente | Media | Extraccion principal (componentes, performance, certs) |
| `claude-haiku-4-5` | Anthropic | $0.80 | $4.00 | Buena | Rapida | Tareas simples (metadata, clasificacion) |
| `gpt-4o` | OpenAI | $2.50 | $10.00 | Excelente | Media | Alternativa al Sonnet, algo mas barato en output |
| `gpt-4o-mini` | OpenAI | $0.15 | $0.60 | Buena | Rapida | Alternativa ultra-barata para metadata/clasificacion |

### 8.3 Estimacion de coste por documento

Para un data sheet tipico de DETEGASA (~56 paginas, ~50K chars de texto limpio):

| Fase | Llamadas LLM | Tokens aprox. (in+out) | Coste estimado (Sonnet) |
|------|:------------:|:---------------------:|:-----------------------:|
| Componentes (17 chunks) | ~17 | ~60K in + ~10K out | ~$0.33 |
| Performance | 1 | ~5K in + ~1K out | ~$0.03 |
| Certificaciones | 1 | ~5K in + ~1K out | ~$0.03 |
| **Total producto** | **~19** | **~70K in + ~12K out** | **~$0.39** |

Para un Material Requisition del cliente (~100 paginas):

| Fase | Llamadas LLM | Tokens aprox. (in+out) | Coste estimado (Sonnet) |
|------|:------------:|:---------------------:|:-----------------------:|
| Metadata | 1 | ~3K in + ~0.5K out | ~$0.02 |
| Process requirements | 1 | ~5K in + ~1K out | ~$0.03 |
| Requirements (20 chunks) | ~20 | ~80K in + ~15K out | ~$0.47 |
| **Total tender** | **~22** | **~88K in + ~16.5K out** | **~$0.51** |

| Fase | Coste |
|------|:-----:|
| TBT (deterministic) | $0.00 |
| **Total por proyecto** | **~$0.90** |

> **Nota**: Los costes son estimaciones conservadoras. El coste real depende del largo del documento y la densidad de contenido tecnico. El script `scripts/e2e_extraction_test.py` reporta costes reales por llamada.

### 8.4 Recomendacion

1. **Empezar con Claude Sonnet 4.5 para todo** — consistencia y maxima calidad
2. **Optimizar gradualmente** bajando metadata y clasificacion a Haiku cuando se valide que funciona
3. **Considerar GPT-4o** como fallback si hay problemas de disponibilidad con Anthropic
4. **GPT-4o-mini** solo para tareas de clasificacion/triaje donde la precision no es critica

# CLAUDE.md — Furniture Cost Estimator
## Contexto del proyecto

Sistema basado en agentes de IA para estimación de costos de fabricación
e instalación de muebles a medida. Empresa mediana (5-50 personas).
Inputs: archivos .skp (SketchUp) y PDF con planos CAD.

## Arquitectura: 4 capas de agentes

### Capa 1 · Parseo y extracción
Agentes: SKP Parser, PDF Vision Agent, CAD Parser
Output: JSON canónico de componentes (ver schema en docs/schemas.md)
Tools clave: pyslapi (SketchUp C API), pdf2image, Claude Vision API
Clasificador: cascada Rules → ML → LLM para tipo de pieza

### Capa 2 · BOM y optimización
Agentes: Material Grouper, Cut Optimizer, Hardware Matcher
Output: BOM con plan de corte + herrajes asignados
Tools clave: rectpack (bin packing 2D), catálogo herrajes en PostgreSQL
Algoritmo corte: guillotine cut con kerf configurable

### Capa 3 · Motor de costos
Agentes: Labor, Install, Transport, Overhead (paralelos) + Consolidator
Output: cost breakdown JSON + precio sugerido
Patrón ML: cada agente tiene ToolBelt con Rules → MLTool → LLMTool
Modelo ML: GradientBoostingRegressor (XGBoost) por agente, target separado
Training: se re-entrena cada 5 proyectos cerrados (MLTrainingPipeline)

### Capa 4 · Presupuesto y entrega
Agentes: Cost Consolidator, Price Suggester, Quote Generator
Output: PDF cliente (resumido/detallado), Excel producción, push CRM
PDF lib: reportlab · Excel: openpyxl · CRM: REST API (Odoo/ERPNext)

## Patrones de código establecidos

EstimationResult — dataclass con value_usd, confidence, source, explanation
EstimatorTool  — ABC con estimate() e is_available()
ToolBelt       — orquesta tools en cascada, blending 70/30 ML+rules
MLEstimatorTool— tool ML genérica reutilizable por todos los agentes

## Stack tecnológico

Runtime:    Python 3.11+
API:        FastAPI + uvicorn
ML:         scikit-learn (GradientBoostingRegressor), joblib, pandas
SketchUp:   pyslapi (wrapper del SketchUp C API SDK)
PDF:        pdf2image, reportlab, anthropic vision
CAD:        ezdxf
Corte:      rectpack
DB:         PostgreSQL + SQLAlchemy (async)
Cache:      Redis
Tests:      pytest + pytest-asyncio
LLM:        anthropic SDK (claude-sonnet-4-6)

## Convenciones

- Todos los costos en USD internamente
- Dimensiones en mm siempre
- Confianza ML en rango 0.0–1.0
- JSON canónico definido en docs/schemas.md
- Cada agente vive en src/agents/{nombre}_agent.py
- Cada tool en src/agents/tools/{nombre}_tool.py
- Tests en tests/unit/test_{nombre}.py

## Orden de desarrollo sugerido

1. ✅ Schema BD + modelos SQLAlchemy  (src/models/)
2. ✅ SKP Parser Agent                (src/agents/skp_parser.py)
3. ✅ Clasificador de componentes     (src/agents/classifier.py)
4. ✅ BOM Builder completo            (src/layers/layer2_bom.py)
5. ✅ Motor de costos con ML          (src/layers/layer3_costs.py)
6. ✅ Quote Generator                 (src/agents/quote_generator.py)
7. ✅ API FastAPI endpoints           (src/api/)
8. ✅ Tests de integración end-to-end (tests/integration/)

## Estado de implementación

### ✅ Capa 1 — Parseo y extracción

**Archivos creados:**
- `src/models/database.py` — engine async, SessionLocal, Base, get_db
- `src/models/project.py` — 7 modelos SQLAlchemy 2.0 (Project, Component, BOMItem, CutPlan, CostBreakdown, Quote, MLTrainingData) + 5 enums
- `src/models/__init__.py`
- `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`
- `src/agents/tools/name_tool.py` — NameClassifierTool con FURNITURE_TAXONOMY
- `src/agents/tools/dimension_tool.py` — DimensionClassifierTool
- `src/agents/tools/llm_tool.py` — LLMClassifierTool (AsyncAnthropic)
- `src/agents/classifier.py` — CascadeClassifier (name → dim → llm → fallback)
- `src/agents/skp_parser.py` — SKPParserAgent
- `src/agents/pdf_vision_agent.py` — PDFVisionAgent
- `tests/unit/test_models.py`, `test_skp_parser.py`, `test_pdf_vision_agent.py`

**Decisiones no previstas en el diseño original:**
- `pyslapi` no está en PyPI (requiere SketchUp C SDK nativo). `_load_raw_components()` se diseñó como único punto de contacto con pyslapi, reemplazable via monkeypatch en tests.
- `pdf_to_images()` idem para poppler/pdf2image — tests inyectan PIL Images directamente.
- `_parse_json()` en PDFVisionAgent limpia fences de markdown ` ```json ``` ` con regex antes de `json.loads` — Claude a veces devuelve JSON envuelto en bloques de código.
- Separadores de palabras en NameClassifierTool: `\b` falla con guiones bajos (SketchUp nombra piezas como `Puerta_Derecha`). Se reemplazó con lookahead/lookbehind `_SEP`/`_END` que tratan `_`, `-`, `/`, `.` como separadores.
- Las dimensiones extraídas de Claude Vision y de pyslapi se ordenan siempre descendente (largo ≥ ancho ≥ espesor) para garantizar consistencia independientemente del orden que devuelva la API.
- `REVISION_THRESHOLD = 0.60` en SKPParserAgent: componentes con confianza < 0.60 van a `requiere_revision` en lugar del JSON canónico.

**TODOs / limitaciones conocidas:**
- CAD Parser (`src/agents/cad_parser.py`) no implementado aún (ezdxf).
- `pyslapi` sólo se puede testear con el SDK nativo de SketchUp instalado; los tests de integración del parser SKP están mockeados.
- El clasificador LLM (`llm_tool.py`) no tiene caché de respuestas — llamadas repetidas con el mismo componente hacen N requests a la API.

---

### ✅ Capa 2 — BOM y optimización

**Archivos creados:**
- `src/agents/material_grouper.py` — MaterialGrouper + MaterialSpec + MaterialGroup
- `src/agents/cut_optimizer.py` — CutOptimizer (rectpack bin packing 2D)
- `src/agents/hardware_matcher.py` — HardwareMatcher (bisagras, correderas, canto PVC)
- `src/layers/layer2_bom.py` — BOMBuilder (orquesta los tres agentes)
- `configs/defaults.yml` — catálogo materiales, herrajes, reglas, tarifas
- `tests/unit/test_bom_builder.py`

**Decisiones no previstas en el diseño original:**
- `rectpack` trabaja con enteros; todas las dimensiones se convierten a `int` antes de añadir al packer. La detección de rotación compara `rect.width != info["orig_w"]` (int comparison, confiable).
- `add_bin(..., count=float('inf'))` para tableros ilimitados — rectpack silenciosamente omite piezas que no caben en ningún tablero (no lanza excepción). Se logea un warning pero no se interrumpe el proceso.
- `resolve_material()` en MaterialGrouper usa tres niveles de fallback: (1) alias exacto case-insensitive, (2) espesor más cercano dentro de ±2 mm, (3) `material_default` del config. Esto no estaba detallado en el diseño.
- Canto PVC (`canto_pvc`) se acumula como una línea de herraje única con unidad `ml` en lugar de por pieza — simplifica el cálculo de costo total.

**TODOs / limitaciones conocidas:**
- `rectpack` usa algoritmo guillotine; no implementa nesting optimizado (e.g., OR-Tools). Para proyectos grandes (> 50 piezas) el desperdicio puede ser 5–10% mayor que el óptimo teórico.
- `desperdicio_pct` se calcula sobre área de piezas vs. área de tableros usados, ignorando el kerf acumulado. Subestima el desperdicio real en ~1–2%.
- No se verifica si una pieza individual supera el tamaño del tablero — sólo se logea un warning.

---

### ✅ Capa 3 — Motor de costos

**Archivos creados:**
- `src/agents/tools/base_tools.py` — EstimationResult, EstimatorTool (ABC sync), AsyncEstimatorTool (ABC async), ToolBelt
- `src/agents/tools/ml_tool.py` — MLEstimatorTool (joblib GBR, confianza escala con n_samples)
- `src/agents/tools/training_pipeline.py` — MLTrainingPipeline (registra proyectos, re-entrena cada N, logea MAPE)
- `src/agents/costs/__init__.py`
- `src/agents/costs/labor_agent.py` — LaborRulesTool + LaborLLMTool + LaborAgent
- `src/agents/costs/install_agent.py` — InstallRulesTool + InstallLLMTool + InstallAgent
- `src/agents/costs/transport_agent.py` — TransportRulesTool + TransportAgent (sin LLM)
- `src/agents/costs/overhead_agent.py` — OverheadRulesTool + OverheadAgent (sin LLM)
- `src/layers/layer3_costs.py` — CostEngine (4 agentes en paralelo, precio sugerido)
- `tests/unit/test_costs.py`

**Decisiones no previstas en el diseño original:**
- `OverheadAgent` y `TransportAgent` no tienen LLM tool — sus estimaciones son suficientemente estables con reglas y ML; agregar LLM añadiría latencia y costo sin beneficio real.
- `Overhead` depende de `costo_directo_usd` (que requiere los otros tres agentes). Se corre en serie después de `asyncio.gather(labor, install, transport)` en lugar de los cuatro en paralelo como mencionaba el diseño.
- La confianza del ML escala como `0.92 × (1 − exp(−n/30))`. El divisor 30 se eligió para que con 5 proyectos (mínimo para activar) la confianza sea ~0.41 (por debajo del blend threshold), forzando fallback a reglas hasta tener suficientes datos.
- `factor_complejidad` se deriva automáticamente de la cantidad de puertas y cajones del BOM en lugar de ser un parámetro de entrada — 1.0 base + 0.10/puerta + 0.15/cajón, cap 2.0.
- `n_puertas` y `n_cajones` en features se infieren contando líneas de herrajes del BOM (bisagras ÷ 2 = puertas aprox., correderas = cajones), no de los componentes directamente.
- El precio sugerido aplica margen e IVA en cascada: `costo_total × (1 + margen) × (1 + iva)` con defaults 32% y 21% desde `configs/defaults.yml`.
- `MLTrainingPipeline` guarda todos los datos históricos en memoria (`self._all_data`). En producción esto debería persistirse en la DB.

**TODOs / limitaciones conocidas:**
- Los modelos ML no existen en disco al arrancar por primera vez — todos los agentes operan en modo "rules only" hasta acumular 5 proyectos cerrados.
- `MLTrainingPipeline._all_data` es en memoria; se pierde al reiniciar el proceso. Pendiente: persistir en tabla `ml_training_data` (ya modelada en SQLAlchemy).
- ✅ Endpoints para registrar proyectos cerrados (`POST /close`) y disparar re-entrenamiento (`POST /ml/retrain`) implementados en la API.
- El intervalo de confianza del ML usa `std` de las predicciones de árboles individuales del GBR — es una aproximación, no un intervalo de predicción estadísticamente riguroso.
- `LaborLLMTool` y `InstallLLMTool` no tienen manejo de errores de rate-limit ni retry con backoff.
- Falta un test de integración end-to-end Layer 1 → 2 → 3 sin mocks.

---

### ✅ Capa 4 — Presupuesto y entrega

**Archivos creados:**
- `src/agents/quote_generator.py` — QuoteGenerator (PDF resumido + detallado, Excel 4 hojas, CRM push)
- `configs/defaults.yml` — secciones `empresa`, `precio` (escenarios), `crm` agregadas
- `tests/unit/test_quote_generator.py`

**Decisiones no previstas en el diseño original:**
- `_items_resumido()` y `_items_detallado()` son métodos públicos (no privados) para que los tests de contenido no necesiten parsear el PDF binario — testar los datos evita dependencia de la serialización de reportlab.
- El número de presupuesto `PRES-YYYYMM-XXXX` se persiste en un archivo `.quote_counter` dentro de `output_dir`; se incrementa en cada llamada a `generate()`. Reiniciable manualmente borrando el archivo.
- La sección de Totals del PDF muestra `costo_total_usd × (1 + IVA)` (costo real + impuesto), no `precio_sugerido`; los escenarios de precio son una sección aparte para no confundir costo con precio de venta.
- CRM push usa `httpx.AsyncClient` con timeout configurable; tanto `HTTPStatusError` como `RequestError` devuelven `{"success": False, ...}` sin propagar la excepción — la generación de archivos continúa siempre.
- La hoja "Costos" del Excel destaca `precio_sugerido` en navy bold y agrega una nota de confianza del modelo (porcentaje).
- Modo detallado del PDF expande cada línea de herraje individualmente (bisagras, correderas, canto PVC) en lugar de una única fila consolidada de herrajes.
- `generate()` siempre produce ambos PDFs (resumido y detallado) en la misma llamada; no hay parámetro de selección de modo.

**TODOs / limitaciones conocidas:**
- No hay Price Suggester separado — el precio sugerido lo calcula directamente `CostEngine` (Capa 3) con margen e IVA desde `configs/defaults.yml`. Si se requiere lógica de pricing más sofisticada (márgenes por cliente, descuentos por volumen), habría que extraerlo a un agente propio.
- El logo de empresa no está implementado en el PDF — reportlab admite `Image()` pero requiere que el archivo exista en disco.
- `MLTrainingPipeline._all_data` no se persiste; al reiniciar el proceso los modelos ML deben re-entrenarse desde cero si no hay artefactos joblib en disco.
- No hay Price Suggester separado — ver nota en Capa 4.
- Falta push de Excel/PDF al CRM — el CRM recibe solo JSON de metadata.
- ✅ Tests de integración end-to-end implementados en `tests/integration/test_pipeline_completo.py` (con mocks de pyslapi y Claude API).

---

### ✅ API FastAPI (módulo 7)

**Archivos creados:**
- `src/api/__init__.py`
- `src/api/main.py` — `create_app()` factory + lifespan (Redis, config, MLTrainingPipeline, CORS)
- `src/api/deps.py` — `get_redis`, `get_config`, `get_training_pipeline`, `get_upload_dir`, `get_quote_output_dir`
- `src/api/schemas.py` — 12 modelos Pydantic (request + response para todos los endpoints)
- `src/api/routers/__init__.py`
- `src/api/routers/pipeline.py` — `POST /api/v1/projects/analyze` + `run_pipeline()` background task
- `src/api/routers/projects.py` — `GET status/bom/costs/quote/files`, `POST close/quote/regenerate`
- `src/api/routers/ml.py` — `GET /api/v1/ml/status`, `POST /api/v1/ml/retrain`
- `tests/integration/__init__.py`
- `tests/integration/test_api.py` — 7 tests (4 requeridos + 3 extras)
- `pyproject.toml` — agregado `python-multipart>=0.0.9` (requerido por FastAPI para `Form` y `File`)

**Endpoints implementados:**

| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/projects/analyze` | Sube archivo, inicia pipeline, retorna `{project_id, status}` |
| `GET`  | `/api/v1/projects/{id}/status` | Estado actual + progreso por capa (0–100) |
| `GET`  | `/api/v1/projects/{id}/bom` | BOM completo de Capa 2 |
| `GET`  | `/api/v1/projects/{id}/costs` | Cost breakdown de Capa 3 con confianza ML |
| `GET`  | `/api/v1/projects/{id}/quote` | URLs de descarga PDF y Excel |
| `GET`  | `/api/v1/projects/{id}/files/{filename}` | Descarga real del archivo generado |
| `POST` | `/api/v1/projects/{id}/close` | Registra costos reales, dispara re-entrenamiento si corresponde |
| `POST` | `/api/v1/projects/{id}/quote/regenerate` | Regenera PDF/Excel con precio o modo de detalle diferente |
| `GET`  | `/api/v1/ml/status` | Estado de los 4 modelos ML (existe en disco, n_samples) |
| `POST` | `/api/v1/ml/retrain` | Dispara re-entrenamiento manual sobre todos los datos históricos |
| `GET`  | `/health` | Health check |

**Decisiones no previstas en el diseño original:**
- **`run_pipeline` como función importable** — no está atada al router; los tests la parchean con `patch("src.api.routers.pipeline.run_pipeline", ...)` sin necesidad de tocar FastAPI internals.
- **Lifespan no-fatal para Redis** — si Redis no responde al arrancar, `app.state.redis = None` y los endpoints retornan 503. El proceso no muere; ideal para entornos de desarrollo sin Redis levantado.
- **`create_app()` factory** — la app no se instancia a nivel de módulo sino dentro de una función, lo que permite tests limpios con `app.dependency_overrides` sin efectos colaterales entre tests.
- **URLs de descarga relativas** — `GET /quote` construye las URLs con `request.base_url` en lugar de hardcodear dominio; funciona detrás de cualquier proxy inverso.
- **Estado Redis como JSON plano** — se almacena todo el state (layer1, layer2, layer3, layer4) en un único key `project:{id}` serializado como JSON con TTL 24h. Evita transacciones multi-key pero requiere reescritura completa en cada update.
- **`FakeRedis` con acceso directo a `_store`** — en fixtures de `TestClient` (síncronas) se escribe estado inicial vía `fake_redis._store[key] = value` en lugar de `await fake_redis.set(...)`, evitando el error "no current event loop".
- **`TestClient` sobre `AsyncClient`** — los background tasks corren inline antes de que `TestClient` devuelva la respuesta al test, lo que permite `test_status_polling_reaches_done` sin polling ni `asyncio.sleep`.
- **`POST /close` deriva el overhead real** como `total_real − labor_real − install_real − transport_real`. El cliente no necesita calcularlo.

**TODOs / limitaciones conocidas:**
- No hay autenticación/autorización en ningún endpoint — todos son públicos.
- El pipeline llama `SKPParserAgent` que requiere `pyslapi`; en producción falla hasta instalar el SDK nativo de SketchUp.
- Estado del proyecto expira en Redis a las 24h; no hay persistencia en PostgreSQL para recuperación tras reinicio.
- `MLTrainingPipeline._all_data` en memoria se pierde al reiniciar — pendiente conectar con tabla `ml_training_data` en SQLAlchemy.
- No hay paginación ni listado de proyectos (`GET /api/v1/projects/`).
- No hay rate limiting ni control de tamaño máximo de archivo en el endpoint de upload.
- `CORS_ORIGINS=*` en desarrollo — debe restringirse en producción via variable de entorno.

---

### ✅ Tests de integración end-to-end (módulo 8)

**Archivos creados:**
- `tests/fixtures/__init__.py` — vacío (marca el directorio como package)
- `tests/fixtures/cocina_data.py` — datos de fixture para cocina de 3 módulos (MB1, MB2, MA1)
- `tests/integration/conftest.py` — fixtures compartidas para los tests de pipeline
- `tests/integration/test_pipeline_completo.py` — 4 tests de integración end-to-end

**Contenido de `tests/fixtures/cocina_data.py`:**
- `get_components()` — 30 `RawComponent` para 3 módulos: MB1 (8 piezas), MB2 (11 piezas), MA1 (11 piezas). Lazy import para evitar efectos colaterales en la colección de pytest.
- `build_layer2_10_modulos()` — Layer-2 pre-construido para 10 módulos estándar (80 piezas MDF + 10 HDF, herrajes con bisagras/correderas/canto). Usado en test 4 sin correr el pipeline completo.
- `create_cocina_pdf(path)` — genera `cocina_simple.pdf` con reportlab: alzado frontal A3 con cotas horizontales y verticales, rectángulos de módulos, leyenda de materiales.
- `create_cocina_skp_stub(path)` — escribe bytes stub; el contenido real es irrelevante porque `_load_raw_components` se monkeyparchea en los tests.

**Contenido de `tests/integration/conftest.py`:**
- `test_config` (session-scoped) — carga `configs/defaults.yml` como dict
- `test_db` (function-scoped) — aiosqlite in-memory + `Base.metadata.create_all`; yield `AsyncSession`; dispose engine
- `cocina_skp_path` (session-scoped) — genera `cocina_simple.skp` si no existe; retorna `Path`
- `cocina_pdf_path` (session-scoped) — genera `cocina_simple.pdf` si no existe; retorna `Path`

**Tests implementados:**

| Test | Qué verifica |
|------|-------------|
| `test_skp_to_quote_completo` | Pipeline completo SKP→L1→L2→L3→L4: schema JSON en cada capa, PDF > 1 KB, Excel con las 4 hojas exactas |
| `test_pdf_to_bom` | PDFVisionAgent extrae ≥ 5 piezas con confidence > 0.6 (Claude API y poppler monkeypatched) |
| `test_ml_feedback_loop` | 20 proyectos → retraining se dispara 4 veces (cada 5), modelos joblib creados en disco y cargables |
| `test_costos_dentro_de_rango_razonable` | $1 500 ≤ costo_total ≤ $8 000, labor < 60 % del total, precio_sugerido > costo_total, aritmética interna consistente |

**Decisiones no previstas en el diseño original:**
- **Todos los tests usan `use_llm=False` en `CostEngine`** — evita llamadas reales a la API de Claude en CI. El ToolBelt usa reglas puras, cuyos valores son predecibles y suficientes para las validaciones de rango.
- **`test_skp_to_quote_completo` monkeyparchea `_load_raw_components` en lugar de preparar un `.skp` real** — `agent._load_raw_components = lambda _path: get_components()`. El archivo stub sólo necesita existir en disco (el parser verifica existencia pero no el formato binario antes de llamar a pyslapi).
- **`test_pdf_to_bom` monkeyparchea dos puntos de contacto** — `agent.pdf_to_images` (evita poppler) y `agent._call_claude_vision` (evita la API). La respuesta simulada devuelve 8 componentes con confidence > 0.6, probando el pipeline de consolidación y el mapeo al JSON canónico sin dependencias externas.
- **`_call_claude_vision` se alterna por paridad de llamadas** — `call_count % 2 == 1` devuelve clasificación de página (`{"tipo": "alzado"}`), el par devuelve extracción de piezas. Esto refleja el orden real de invocaciones del agente (classify → extract) sin necesitar un mock más complejo.
- **`test_ml_feedback_loop` usa features que cubren los cuatro agentes simultáneamente** — un único dict de features por proyecto incluye todos los campos que necesitan labor, install, transport y overhead. Evita tener que construir cuatro conjuntos de datos distintos.
- **`test_costos_dentro_de_rango_razonable` usa `build_layer2_10_modulos()` pre-construido** — en lugar de correr `BOMBuilder`, lo que evita variabilidad en el bin packing y hace el test determinista: se validan los rangos de costo, no el algoritmo de corte.
- **Los fixtures `cocina_skp_path` y `cocina_pdf_path` son session-scoped** — los archivos se generan una sola vez por sesión de pytest y se reusan; se escriben en `tests/fixtures/` (commiteables) en lugar de en `tmp_path` (efímero), para que la revisión manual del PDF sea posible.
- **La verificación de schema en Layer 1 usa el nombre de campo `"name"` (no `"nombre"`)** — el SKP parser serializa `c.name` del `ClassifiedComponent`, mientras que el PDF Vision Agent usa `"nombre"`. La inconsistencia existe en el código fuente y se documenta aquí para no repetir el error en futuros tests.

**TODOs / limitaciones conocidas:**
- No hay test que corra el pipeline con un archivo `.skp` real (requeriría pyslapi + SketchUp C SDK instalados en el entorno CI).
- No hay test de `PDFVisionAgent` con un PDF real y Claude API real — agregar como test de smoke en entornos con `ANTHROPIC_API_KEY` configurada.
- `test_db` (fixture aiosqlite) se crea pero ningún test del pipeline escribe en ella aún — la persistencia SQLAlchemy está modelada pero no conectada al flujo de `run_pipeline`.
- El fixture `cocina_simple.pdf` generado con reportlab es minimalista (rectángulos y cotas simples); un test con Claude Vision real probablemente extrairía menos piezas que el mock y requeriría ajuste del umbral de 5 piezas.
- `build_layer2_10_modulos()` hardcodea `tableros_necesarios: 10` para MDF; en realidad `CutOptimizer` podría necesitar más o menos tableros según el bin packing. El test de costos asume este valor fijo.
- No hay test de regresión de rendimiento (latencia del pipeline, uso de memoria en BOM con > 200 piezas).

---

## Archivos de referencia

- docs/schemas.md     — JSON canónico completo de cada capa
- docs/architecture.md — decisiones de diseño y ADRs
- configs/defaults.yml — tarifas, catálogo materiales, overhead %
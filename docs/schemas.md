# Schemas JSON canónicos

## Salida Capa 1 → entrada Capa 2
```json
{
  "proyecto_id": "string",
  "origen": "skp | pdf | dxf",
  "componentes": [
    {
      "id": "string",
      "name": "string",
      "parent": "string | null",
      "tipo_inferido": "puerta | lateral | fondo | tapa | base | estante | cajon_caja | cajon_frente | zocalo | columna | otro",
      "subtype": "string | null",
      "dimensiones": { "largo": 0, "ancho": 0, "espesor": 0 },
      "material": "string",
      "cantidad": 1,
      "confidence": 0.0,
      "classification_method": "name_match | dimension_rule | ml | llm"
    }
  ],
  "advertencias": [],
  "requiere_revision": []
}
```

## Salida Capa 2 → entrada Capa 3
```json
{
  "proyecto_id": "string",
  "tableros": [
    {
      "material_id": "string",
      "tableros_necesarios": 0,
      "costo_tableros_usd": 0.0,
      "desperdicio_pct": 0.0,
      "plan_de_corte": []
    }
  ],
  "herrajes": {
    "lineas": [],
    "total_herrajes_usd": 0.0
  },
  "resumen": {
    "total_materiales_usd": 0.0,
    "piezas_procesadas": 0
  }
}
```

## Salida Capa 3 → entrada Capa 4
```json
{
  "proyecto_id": "string",
  "desglose": {
    "materiales_usd": 0.0,
    "labor_usd": 0.0,
    "instalacion_usd": 0.0,
    "transporte_usd": 0.0,
    "overhead_usd": 0.0,
    "impuestos_usd": 0.0
  },
  "costo_total_usd": 0.0,
  "precio_sugerido": 0.0,
  "confianza_ml": 0.0,
  "fuente_estimacion": "string",
  "alertas": []
}
```

export type PipelineStatus =
  | "processing"
  | "parsing"
  | "bom"
  | "costs"
  | "quoting"
  | "done"
  | "error";

export interface LayerProgress {
  parsing: number;
  bom: number;
  costs: number;
  quoting: number;
}

export interface ProjectStatus {
  project_id: string;
  status: PipelineStatus;
  progress: LayerProgress;
  created_at: string;
  updated_at: string;
  error?: string | null;
}

export interface CutPiece {
  pieza_id: string;
  nombre: string;
  tablero_num: number;
  x_mm: number;
  y_mm: number;
  largo_mm: number;
  ancho_mm: number;
  rotada: boolean;
}

export interface TableroResult {
  material_id: string;
  tableros_necesarios: number;
  costo_tableros_usd: number;
  desperdicio_pct: number;
  plan_de_corte: CutPiece[];
}

export interface HerrajeLinea {
  herraje_id: string;
  nombre: string;
  cantidad: number;
  precio_unitario_usd: number;
  precio_total_usd: number;
  unidad: string;
}

export interface BOMData {
  proyecto_id: string;
  tableros: TableroResult[];
  herrajes: {
    lineas: HerrajeLinea[];
    total_herrajes_usd: number;
  };
  resumen: {
    total_materiales_usd: number;
    piezas_procesadas: number;
  };
}

export interface CostsData {
  proyecto_id: string;
  costo_materiales_usd: number;
  costo_mano_obra_usd: number;
  costo_instalacion_usd: number;
  costo_transporte_usd: number;
  costo_indirecto_usd: number;
  costo_directo_usd: number;
  costo_total_usd: number;
  precio_sugerido_usd: number;
  confianza_global: number;
  fuentes: {
    materiales: string;
    mano_obra: string;
    instalacion: string;
    transporte: string;
    indirecto: string;
  };
  intervalos: {
    labor_low: number;
    labor_high: number;
    install_low: number;
    install_high: number;
    transport_low: number;
    transport_high: number;
    overhead_low: number;
    overhead_high: number;
  };
  escenarios_precio?: {
    conservador: number;
    agresivo: number;
  };
}

export interface QuoteFiles {
  project_id: string;
  quote_number: string;
  files: {
    pdf_resumido: string;
    pdf_detallado: string;
    excel: string;
  };
}

export interface AgentMLStatus {
  model_exists: boolean;
  n_samples: number;
  model_path: string;
}

export interface MLStatus {
  agents: Record<string, AgentMLStatus>;
}

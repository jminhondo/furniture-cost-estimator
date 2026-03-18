/**
 * API client for the FastAPI backend.
 *
 * In development, Next.js rewrites /api/* to http://localhost:8000/api/*
 * (see next.config.ts).  In production the same rewrite proxies to BACKEND_URL.
 * All calls therefore use relative paths — no CORS issues.
 */

import type {
  BOMData,
  CostsData,
  MLStatus,
  ProjectStatus,
  QuoteFiles,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body.detail ?? body.message ?? message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export interface AnalyzePayload {
  proyecto_nombre: string;
  cliente: {
    nombre: string;
    email: string;
    telefono: string;
    direccion_obra: string;
    cliente_id: string;
  };
  project_params: {
    distancia_obra_km: number;
    distancia_proveedor_km: number;
    n_instaladores: number;
    tipo_obra: number;
    duracion_proyecto_dias: number;
    tiene_lacado: boolean;
  };
}

export async function analyzeProject(
  file: File,
  metadata: AnalyzePayload
): Promise<{ project_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  return request("/api/v1/projects/analyze", { method: "POST", body: form });
}

// ---------------------------------------------------------------------------
// Project state
// ---------------------------------------------------------------------------

export function getProjectStatus(id: string): Promise<ProjectStatus> {
  return request(`/api/v1/projects/${id}/status`);
}

export function getBOM(id: string): Promise<{ project_id: string; bom: BOMData }> {
  return request(`/api/v1/projects/${id}/bom`);
}

export function getCosts(id: string): Promise<{ project_id: string; costs: CostsData }> {
  return request(`/api/v1/projects/${id}/costs`);
}

export function getQuote(id: string): Promise<QuoteFiles> {
  return request(`/api/v1/projects/${id}/quote`);
}

// ---------------------------------------------------------------------------
// Close project (ML feedback)
// ---------------------------------------------------------------------------

export interface ClosePayload {
  labor_real: number;
  install_real: number;
  transport_real: number;
  total_real: number;
}

export function closeProject(
  id: string,
  data: ClosePayload
): Promise<{ project_id: string; registered: boolean; retrained: boolean }> {
  return request(`/api/v1/projects/${id}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ---------------------------------------------------------------------------
// Regenerate quote
// ---------------------------------------------------------------------------

export function regenerateQuote(
  id: string,
  options: { mode?: string; precio_override?: number | null }
): Promise<QuoteFiles> {
  return request(`/api/v1/projects/${id}/quote/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
}

// ---------------------------------------------------------------------------
// ML status
// ---------------------------------------------------------------------------

export function getMLStatus(): Promise<MLStatus> {
  return request("/api/v1/ml/status");
}

// ---------------------------------------------------------------------------
// File download helper
// ---------------------------------------------------------------------------

export async function downloadBlob(url: string): Promise<Blob> {
  // URL is already absolute (built by FastAPI from request.base_url)
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: HTTP ${res.status}`);
  return res.blob();
}

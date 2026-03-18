"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import {
  closeProject,
  downloadBlob,
  getBOM,
  getCosts,
  getMLStatus,
  getProjectStatus,
  getQuote,
  regenerateQuote,
} from "@/lib/api";
import type { BOMData, CostsData, MLStatus, ProjectStatus, QuoteFiles } from "@/lib/types";

// ---------------------------------------------------------------------------
// Shared small components
// ---------------------------------------------------------------------------

function Badge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    processing: ["bg-yellow-100 text-yellow-800", "⏳ Procesando"],
    parsing:    ["bg-blue-100 text-blue-800",   "🔍 Parseando"],
    bom:        ["bg-blue-100 text-blue-800",   "📋 BOM"],
    costs:      ["bg-blue-100 text-blue-800",   "💰 Costos"],
    quoting:    ["bg-blue-100 text-blue-800",   "📄 Presupuesto"],
    done:       ["bg-green-100 text-green-800", "✅ Completo"],
    error:      ["bg-red-100 text-red-800",     "❌ Error"],
  };
  const [cls, label] = map[status] ?? ["bg-gray-100 text-gray-700", status];
  return (
    <span className={`inline-flex items-center px-3 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

function ProgressBar({ value, label }: { value: number; label: string }) {
  const color = value === 100 ? "bg-green-500" : "bg-blue-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="h-2 rounded-full bg-gray-200">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 rounded-full bg-gray-200">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">{pct}%</span>
    </div>
  );
}

function usd(n: number) {
  return `$${n.toLocaleString("es-AR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

// ---------------------------------------------------------------------------
// Tab: Estado
// ---------------------------------------------------------------------------

function StatusTab({ status }: { status: ProjectStatus }) {
  const prog = status.progress;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Badge status={status.status} />
        <span className="text-sm text-gray-500">
          Actualizado {new Date(status.updated_at).toLocaleTimeString("es-AR")}
        </span>
      </div>

      {status.error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <strong>Error:</strong> {status.error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <ProgressBar value={prog.parsing} label="🔍 Parseo de archivo" />
        <ProgressBar value={prog.bom} label="📋 BOM y optimización de corte" />
        <ProgressBar value={prog.costs} label="💰 Motor de costos (IA)" />
        <ProgressBar value={prog.quoting} label="📄 Generación de presupuesto" />
      </div>

      {status.status === "done" && (
        <p className="text-sm text-green-700 font-medium">
          ✅ Pipeline completado. Usá las pestañas de arriba para ver los resultados.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: BOM
// ---------------------------------------------------------------------------

function BOMTab({ projectId }: { projectId: string }) {
  const [bom, setBOM] = useState<BOMData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBOM(projectId)
      .then((r) => setBOM(r.bom))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (!bom) return null;

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Metric label="Piezas procesadas" value={String(bom.resumen.piezas_procesadas)} />
        <Metric label="Costo materiales" value={usd(bom.resumen.total_materiales_usd)} />
        <Metric label="Total herrajes" value={usd(bom.herrajes.total_herrajes_usd)} />
      </div>

      {/* Tableros */}
      <section>
        <h3 className="font-semibold text-gray-800 mb-3">Tableros</h3>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                {["Material", "Tableros", "Desperdicio", "Costo USD"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {bom.tableros.map((t, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{t.material_id}</td>
                  <td className="px-4 py-3">{t.tableros_necesarios}</td>
                  <td className="px-4 py-3">{(t.desperdicio_pct * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 font-medium">{usd(t.costo_tableros_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Herrajes */}
      <section>
        <h3 className="font-semibold text-gray-800 mb-3">Herrajes</h3>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                {["Herraje", "Cantidad", "P. Unit.", "Total"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {bom.herrajes.lineas.map((l, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{l.nombre}</td>
                  <td className="px-4 py-3">{l.cantidad} {l.unidad}</td>
                  <td className="px-4 py-3">${l.precio_unitario_usd.toFixed(2)}</td>
                  <td className="px-4 py-3 font-medium">{usd(l.precio_total_usd)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 font-semibold text-sm">
              <tr>
                <td className="px-4 py-3" colSpan={3}>Total herrajes</td>
                <td className="px-4 py-3">{usd(bom.herrajes.total_herrajes_usd)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Costos
// ---------------------------------------------------------------------------

function CostsTab({ projectId }: { projectId: string }) {
  const [costs, setCosts] = useState<CostsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCosts(projectId)
      .then((r) => setCosts(r.costs))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (!costs) return null;

  const laborRatio = (costs.costo_mano_obra_usd / costs.costo_total_usd) * 100;

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Metric label="Materiales"    value={usd(costs.costo_materiales_usd)} />
        <Metric label="Mano de obra"  value={usd(costs.costo_mano_obra_usd)}  sub={`${laborRatio.toFixed(0)}% del total`} />
        <Metric label="Instalación"   value={usd(costs.costo_instalacion_usd)} />
        <Metric label="Transporte"    value={usd(costs.costo_transporte_usd)} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Metric label="Overhead"      value={usd(costs.costo_indirecto_usd)} />
        <Metric label="Costo total"   value={usd(costs.costo_total_usd)} />
      </div>

      {/* Price highlight */}
      <div className="rounded-xl bg-blue-600 text-white p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <p className="text-sm text-blue-200">Precio sugerido al cliente</p>
          <p className="text-4xl font-bold mt-1">{usd(costs.precio_sugerido_usd)}</p>
          <p className="text-sm text-blue-200 mt-1">
            Margen: {usd(costs.precio_sugerido_usd - costs.costo_total_usd)} sobre costo
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-blue-200">Confianza del modelo</p>
          <div className="mt-2">
            <ConfidenceBar value={costs.confianza_global} />
          </div>
        </div>
      </div>

      {/* Price scenarios */}
      {costs.escenarios_precio && (
        <div className="grid grid-cols-3 gap-4">
          {[
            ["🔵 Conservador", costs.escenarios_precio.conservador, "text-blue-700"],
            ["🟢 Sugerido",    costs.precio_sugerido_usd,           "text-green-700"],
            ["🔴 Agresivo",    costs.escenarios_precio.agresivo,    "text-red-700"],
          ].map(([label, val, cls]) => (
            <div key={String(label)} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <p className={`text-sm font-medium ${cls}`}>{label as string}</p>
              <p className="text-xl font-bold text-gray-900 mt-1">{usd(val as number)}</p>
            </div>
          ))}
        </div>
      )}

      {/* Fuentes */}
      <section>
        <h3 className="font-semibold text-gray-800 mb-3">Fuentes de estimación</h3>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                {["Agente", "Fuente", "Valor", "Intervalo"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {(
                [
                  ["Labor",     costs.fuentes.mano_obra,  costs.costo_mano_obra_usd,  costs.intervalos.labor_low,    costs.intervalos.labor_high],
                  ["Instalación",costs.fuentes.instalacion,costs.costo_instalacion_usd,costs.intervalos.install_low,  costs.intervalos.install_high],
                  ["Transporte", costs.fuentes.transporte, costs.costo_transporte_usd, costs.intervalos.transport_low,costs.intervalos.transport_high],
                  ["Overhead",   costs.fuentes.indirecto,  costs.costo_indirecto_usd,  costs.intervalos.overhead_low, costs.intervalos.overhead_high],
                ] as const
              ).map(([name, source, value, low, high]) => (
                <tr key={name} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{name}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      source === "ml"    ? "bg-purple-100 text-purple-700" :
                      source === "blend" ? "bg-blue-100 text-blue-700" :
                      source === "llm"   ? "bg-orange-100 text-orange-700" :
                                          "bg-gray-100 text-gray-700"
                    }`}>{source}</span>
                  </td>
                  <td className="px-4 py-3">{usd(value as number)}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{usd(low as number)} – {usd(high as number)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Presupuesto
// ---------------------------------------------------------------------------

function QuoteTab({ projectId }: { projectId: string }) {
  const [quote, setQuote] = useState<QuoteFiles | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const [regen, setRegen] = useState(false);
  const [precioCustom, setPrecioCustom] = useState("");

  const loadQuote = useCallback(() => {
    setLoading(true);
    getQuote(projectId)
      .then(setQuote)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { loadQuote(); }, [loadQuote]);

  async function download(url: string, filename: string, mime: string) {
    setDlError(null);
    try {
      const blob = await downloadBlob(url);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([blob], { type: mime }));
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setDlError(e instanceof Error ? e.message : "Error al descargar.");
    }
  }

  async function handleRegen(e: React.FormEvent) {
    e.preventDefault();
    setRegen(true);
    try {
      const precio = precioCustom ? Number(precioCustom) : null;
      const result = await regenerateQuote(projectId, { mode: "both", precio_override: precio });
      setQuote(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al regenerar.");
    } finally {
      setRegen(false);
    }
  }

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (!quote) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h3 className="font-semibold text-gray-800 text-lg">{quote.quote_number}</h3>
      </div>

      {dlError && <ErrorBox msg={dlError} />}

      {/* Download buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { key: "pdf_resumido" as const,  label: "📄 PDF Resumido",     mime: "application/pdf",                                                                          ext: "pdf" },
          { key: "pdf_detallado" as const, label: "📑 PDF Detallado",    mime: "application/pdf",                                                                          ext: "pdf" },
          { key: "excel" as const,         label: "📊 Excel Producción", mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ext: "xlsx" },
        ].map(({ key, label, mime, ext }) => (
          <button
            key={key}
            onClick={() => download(
              quote.files[key],
              `${quote.quote_number}_${key}.${ext}`,
              mime
            )}
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-gray-200 bg-white p-5 hover:border-blue-400 hover:bg-blue-50 transition-colors text-sm font-medium text-gray-700 hover:text-blue-700"
          >
            <span className="text-3xl">{label.split(" ")[0]}</span>
            <span>{label.slice(label.indexOf(" ") + 1)}</span>
          </button>
        ))}
      </div>

      {/* Regenerate */}
      <section className="bg-gray-50 rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-4">Regenerar con precio distinto</h3>
        <form onSubmit={handleRegen} className="flex gap-3">
          <input
            type="number"
            min="0"
            step="50"
            placeholder="Precio override (USD) — vacío = usar sugerido"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={precioCustom}
            onChange={(e) => setPrecioCustom(e.target.value)}
          />
          <button
            type="submit"
            disabled={regen}
            className="rounded-lg bg-gray-800 hover:bg-gray-900 disabled:opacity-60 text-white px-4 py-2 text-sm font-medium transition-colors"
          >
            {regen ? "Generando…" : "🔄 Regenerar"}
          </button>
        </form>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Cerrar proyecto
// ---------------------------------------------------------------------------

function CloseTab({ projectId }: { projectId: string }) {
  const [costs, setCosts] = useState<CostsData | null>(null);
  const [labor, setLabor] = useState("");
  const [install, setInstall] = useState("");
  const [transport, setTransport] = useState("");
  const [total, setTotal] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ registered: boolean; retrained: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mlStatus, setMLStatus] = useState<MLStatus | null>(null);

  useEffect(() => {
    getCosts(projectId)
      .then((r) => {
        const c = r.costs;
        setCosts(c);
        setLabor(c.costo_mano_obra_usd.toFixed(0));
        setInstall(c.costo_instalacion_usd.toFixed(0));
        setTransport(c.costo_transporte_usd.toFixed(0));
        setTotal(c.precio_sugerido_usd.toFixed(0));
      })
      .catch(() => {});
    getMLStatus()
      .then(setMLStatus)
      .catch(() => {});
  }, [projectId]);

  async function handleClose(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await closeProject(projectId, {
        labor_real:     Number(labor),
        install_real:   Number(install),
        transport_real: Number(transport),
        total_real:     Number(total),
      });
      setResult(r);
      getMLStatus().then(setMLStatus).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cerrar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-600">
        Registrá los costos reales del proyecto para mejorar las estimaciones futuras.
        Cada <strong>5 proyectos cerrados</strong> el modelo ML se re-entrena automáticamente.
      </p>

      {/* ML status */}
      {mlStatus && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Estado del modelo ML</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(mlStatus.agents).map(([name, info]) => (
              <div key={name} className="text-center">
                <span className="text-lg">{info.model_exists ? "✅" : "⬜"}</span>
                <p className="text-xs font-medium text-gray-700 mt-1 capitalize">{name}</p>
                <p className="text-xs text-gray-400">{info.n_samples} proyectos</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reference row */}
      {costs && (
        <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
          <p className="text-xs font-medium text-blue-700 mb-1">Estimaciones del sistema (referencia)</p>
          <div className="flex flex-wrap gap-4 text-xs text-blue-800">
            <span>Labor: <strong>{usd(costs.costo_mano_obra_usd)}</strong></span>
            <span>Inst.: <strong>{usd(costs.costo_instalacion_usd)}</strong></span>
            <span>Transp.: <strong>{usd(costs.costo_transporte_usd)}</strong></span>
            <span>Total sugerido: <strong>{usd(costs.precio_sugerido_usd)}</strong></span>
          </div>
        </div>
      )}

      {result ? (
        <div className={`rounded-xl p-5 border ${result.retrained ? "bg-green-50 border-green-200" : "bg-gray-50 border-gray-200"}`}>
          <p className="font-semibold text-gray-800">
            {result.retrained ? "🎉 ¡Modelo re-entrenado!" : "✅ Datos registrados"}
          </p>
          <p className="text-sm text-gray-600 mt-1">
            {result.retrained
              ? "El modelo ML fue re-entrenado con los nuevos datos. Las próximas estimaciones serán más precisas."
              : "Los costos reales fueron registrados. El modelo se re-entrenará cuando haya 5 proyectos nuevos."}
          </p>
        </div>
      ) : (
        <form onSubmit={handleClose} className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {[
              ["Mano de obra real (USD)", labor, setLabor],
              ["Instalación real (USD)", install, setInstall],
              ["Transporte real (USD)", transport, setTransport],
              ["Total facturado al cliente (USD)", total, setTotal],
            ].map(([label, value, setter]) => (
              <label key={label as string} className="flex flex-col gap-1">
                <span className="text-sm font-medium text-gray-700">{label as string}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  required
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={value as string}
                  onChange={(e) => (setter as (v: string) => void)(e.target.value)}
                />
              </label>
            ))}
          </div>

          {error && <ErrorBox msg={error} />}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white font-semibold py-2.5 text-sm transition-colors"
          >
            {loading ? "Registrando…" : "✔️ Cerrar proyecto y registrar costos"}
          </button>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-8 w-8 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
      {msg}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const TABS = [
  { id: "estado",      label: "📊 Estado" },
  { id: "bom",         label: "📋 BOM" },
  { id: "costos",      label: "💰 Costos" },
  { id: "presupuesto", label: "📄 Presupuesto" },
  { id: "cerrar",      label: "✔️ Cerrar" },
];

const DONE_STATUSES = new Set(["done", "error"]);
const POLL_MS = 2000;

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [tab, setTab] = useState("estado");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(() => {
    getProjectStatus(id)
      .then((s) => {
        setStatus(s);
        if (DONE_STATUSES.has(s.status)) {
          clearInterval(intervalRef.current!);
          intervalRef.current = null;
        }
      })
      .catch((e) => setFetchError(e.message));
  }, [id]);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, POLL_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [poll]);

  const isDone = status?.status === "done";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <p className="text-xs text-gray-400 font-mono">{id}</p>
          <div className="flex items-center gap-3 mt-1">
            {status ? <Badge status={status.status} /> : <span className="text-sm text-gray-400">Cargando…</span>}
          </div>
        </div>
        {!isDone && status && !DONE_STATUSES.has(status.status) && (
          <span className="flex items-center gap-1.5 text-xs text-blue-600">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
            Actualizando automáticamente…
          </span>
        )}
      </div>

      {fetchError && <ErrorBox msg={`No se pudo obtener el estado: ${fetchError}`} />}

      {/* Tab nav */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1 -mb-px overflow-x-auto">
          {TABS.map(({ id: tabId, label }) => {
            const locked = !isDone && tabId !== "estado";
            return (
              <button
                key={tabId}
                onClick={() => !locked && setTab(tabId)}
                disabled={locked}
                className={`whitespace-nowrap px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  tab === tabId
                    ? "border-blue-600 text-blue-600"
                    : locked
                    ? "border-transparent text-gray-300 cursor-not-allowed"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                {label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {tab === "estado"      && status && <StatusTab status={status} />}
        {tab === "bom"         && isDone  && <BOMTab projectId={id} />}
        {tab === "costos"      && isDone  && <CostsTab projectId={id} />}
        {tab === "presupuesto" && isDone  && <QuoteTab projectId={id} />}
        {tab === "cerrar"      && isDone  && <CloseTab projectId={id} />}
      </div>
    </div>
  );
}

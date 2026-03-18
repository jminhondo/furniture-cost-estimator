"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { analyzeProject, type AnalyzePayload } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}

const inputCls =
  "rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white";

const selectCls = inputCls + " cursor-pointer";

// ---------------------------------------------------------------------------
// Upload dropzone
// ---------------------------------------------------------------------------

function Dropzone({
  file,
  onFile,
}: {
  file: File | null;
  onFile: (f: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith(".skp") || f.name.endsWith(".pdf"))) onFile(f);
  };

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
        dragging
          ? "border-blue-500 bg-blue-50"
          : file
          ? "border-green-400 bg-green-50"
          : "border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".skp,.pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <div className="text-3xl mb-2">{file ? "✅" : "📂"}</div>
      {file ? (
        <>
          <p className="font-medium text-green-700">{file.name}</p>
          <p className="text-xs text-gray-500 mt-1">
            {(file.size / 1024).toFixed(0)} KB · click para cambiar
          </p>
        </>
      ) : (
        <>
          <p className="font-medium text-gray-700">Arrastrá tu archivo aquí</p>
          <p className="text-sm text-gray-500 mt-1">o hacé click para seleccionar</p>
          <p className="text-xs text-gray-400 mt-2">Formatos: .skp (SketchUp) · .pdf (planos CAD)</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HomePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Client fields
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [telefono, setTelefono] = useState("");
  const [direccion, setDireccion] = useState("");
  const [proyectoNombre, setProyectoNombre] = useState("");

  // Project params
  const [distObra, setDistObra] = useState(15);
  const [distProv, setDistProv] = useState(30);
  const [nInstal, setNInstal] = useState(2);
  const [duracion, setDuracion] = useState(5);
  const [tipoObra, setTipoObra] = useState(0);
  const [lacado, setLacado] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Seleccioná un archivo .skp o .pdf."); return; }
    setError(null);
    setLoading(true);

    const metadata: AnalyzePayload = {
      proyecto_nombre: proyectoNombre || file.name,
      cliente: {
        nombre,
        email,
        telefono,
        direccion_obra: direccion,
        cliente_id: "",
      },
      project_params: {
        distancia_obra_km:      distObra,
        distancia_proveedor_km: distProv,
        n_instaladores:         nInstal,
        tipo_obra:              tipoObra,
        duracion_proyecto_dias: duracion,
        tiene_lacado:           lacado,
      },
    };

    try {
      const { project_id } = await analyzeProject(file, metadata);
      router.push(`/proyecto/${project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al conectar con el backend.");
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
      {/* ── Sidebar info ───────────────────────────────────────────── */}
      <aside className="lg:col-span-2 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Nueva estimación</h1>
          <p className="text-gray-500 mt-2 text-sm leading-relaxed">
            Cargá el archivo de planos y completá los datos del proyecto. El sistema
            estimará materiales, mano de obra, instalación y te generará un presupuesto
            listo para entregar.
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">¿Cómo funciona?</h2>
          {[
            ["🔍", "Parseo", "Extrae piezas y dimensiones del archivo"],
            ["📋", "BOM", "Calcula tableros, cortes y herrajes"],
            ["💰", "Costos", "Estima mano de obra e instalación con IA"],
            ["📄", "Presupuesto", "Genera PDF y Excel listos para el cliente"],
          ].map(([icon, title, desc]) => (
            <div key={title} className="flex gap-3">
              <span className="text-xl">{icon}</span>
              <div>
                <p className="text-sm font-medium text-gray-800">{title}</p>
                <p className="text-xs text-gray-500">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Form ───────────────────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className="lg:col-span-3 bg-white rounded-xl border border-gray-200 p-6 space-y-6"
      >
        {/* File */}
        <section>
          <h2 className="font-semibold text-gray-800 mb-3">Archivo de planos</h2>
          <Dropzone file={file} onFile={setFile} />
        </section>

        {/* Client */}
        <section>
          <h2 className="font-semibold text-gray-800 mb-3">Datos del cliente</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Nombre del proyecto">
              <input
                className={inputCls}
                placeholder="Cocina principal"
                value={proyectoNombre}
                onChange={(e) => setProyectoNombre(e.target.value)}
              />
            </Field>
            <Field label="Cliente">
              <input
                className={inputCls}
                placeholder="Juan García"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
              />
            </Field>
            <Field label="Email">
              <input
                type="email"
                className={inputCls}
                placeholder="juan@empresa.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Teléfono">
              <input
                className={inputCls}
                placeholder="+54 11 1234-5678"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
              />
            </Field>
            <Field label="Dirección de obra">
              <input
                className={inputCls + " sm:col-span-2"}
                placeholder="Av. Corrientes 1234, CABA"
                value={direccion}
                onChange={(e) => setDireccion(e.target.value)}
              />
            </Field>
          </div>
        </section>

        {/* Project params */}
        <section>
          <h2 className="font-semibold text-gray-800 mb-3">Parámetros de obra</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <Field label="Distancia a obra (km)">
              <input
                type="number" min={0} className={inputCls}
                value={distObra}
                onChange={(e) => setDistObra(Number(e.target.value))}
              />
            </Field>
            <Field label="Distancia a proveedor (km)">
              <input
                type="number" min={0} className={inputCls}
                value={distProv}
                onChange={(e) => setDistProv(Number(e.target.value))}
              />
            </Field>
            <Field label="Instaladores">
              <input
                type="number" min={1} max={10} className={inputCls}
                value={nInstal}
                onChange={(e) => setNInstal(Number(e.target.value))}
              />
            </Field>
            <Field label="Duración (días)">
              <input
                type="number" min={1} max={90} className={inputCls}
                value={duracion}
                onChange={(e) => setDuracion(Number(e.target.value))}
              />
            </Field>
            <Field label="Tipo de obra">
              <select
                className={selectCls}
                value={tipoObra}
                onChange={(e) => setTipoObra(Number(e.target.value))}
              >
                <option value={0}>Residencial</option>
                <option value={1}>Comercial</option>
                <option value={2}>Industrial</option>
              </select>
            </Field>
            <Field label="Incluye lacado">
              <div className="flex items-center h-[38px]">
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={lacado}
                    onChange={(e) => setLacado(e.target.checked)}
                  />
                  <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-5" />
                  <span className="ml-3 text-sm text-gray-700">{lacado ? "Sí" : "No"}</span>
                </label>
              </div>
            </Field>
          </div>
        </section>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold py-3 text-sm transition-colors"
        >
          {loading ? "Enviando…" : "🚀 Iniciar estimación"}
        </button>
      </form>
    </div>
  );
}

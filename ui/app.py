"""
Furniture Cost Estimator — Streamlit UI

Levantarlo:
    streamlit run ui/app.py

Requiere que el backend FastAPI esté corriendo:
    uvicorn src.api.main:app --reload       (otra terminal)

La URL del backend se puede cambiar en el sidebar.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Estimador de Costos",
    page_icon="🪑",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DEFAULT_API = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

if "api_base" not in st.session_state:
    st.session_state.api_base = _DEFAULT_API
if "project_id" not in st.session_state:
    st.session_state.project_id = ""
if "polling" not in st.session_state:
    st.session_state.polling = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api(path: str) -> str:
    return st.session_state.api_base.rstrip("/") + path


def _status_badge(status: str) -> str:
    colors = {
        "processing": "#f0ad4e",
        "parsing":    "#5bc0de",
        "bom":        "#5bc0de",
        "costs":      "#5bc0de",
        "quoting":    "#5bc0de",
        "done":       "#5cb85c",
        "error":      "#d9534f",
    }
    color = colors.get(status, "#aaa")
    label = {
        "processing": "⏳ Procesando",
        "parsing":    "🔍 Parseando",
        "bom":        "📋 BOM",
        "costs":      "💰 Costos",
        "quoting":    "📄 Presupuesto",
        "done":       "✅ Completo",
        "error":      "❌ Error",
    }.get(status, status)
    return (
        f'<span style="background:{color};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:0.85rem;font-weight:600">{label}</span>'
    )


def _confidence_bar(value: float) -> str:
    pct = int(value * 100)
    color = "#5cb85c" if pct >= 70 else "#f0ad4e" if pct >= 40 else "#d9534f"
    return (
        f'<div style="background:#eee;border-radius:4px;height:12px;width:120px;display:inline-block;vertical-align:middle">'
        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:4px"></div></div>'
        f' <span style="font-size:0.8rem;color:#555">{pct}%</span>'
    )


def get_project_state() -> dict | None:
    pid = st.session_state.project_id
    if not pid:
        return None
    try:
        r = requests.get(api(f"/api/v1/projects/{pid}/status"), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🪑 Estimador")
    st.caption("Sistema de estimación de costos de muebles a medida")
    st.divider()

    # API URL
    st.session_state.api_base = st.text_input(
        "Backend URL", value=st.session_state.api_base, help="URL base del servidor FastAPI"
    )

    # Health check
    try:
        h = requests.get(api("/health"), timeout=2)
        if h.status_code == 200:
            st.success("Backend conectado", icon="🟢")
        else:
            st.error(f"Backend error {h.status_code}", icon="🔴")
    except Exception:
        st.error("Backend no disponible", icon="🔴")

    st.divider()

    # Project ID
    st.subheader("Proyecto activo")
    pid_input = st.text_input("Project ID", value=st.session_state.project_id)
    if pid_input != st.session_state.project_id:
        st.session_state.project_id = pid_input
        st.rerun()

    if st.button("Limpiar proyecto", use_container_width=True):
        st.session_state.project_id = ""
        st.session_state.polling = False
        st.rerun()

    st.divider()

    # ML Status
    st.subheader("Estado ML")
    try:
        ml_resp = requests.get(api("/api/v1/ml/status"), timeout=3)
        if ml_resp.status_code == 200:
            agents = ml_resp.json().get("agents", {})
            for agent_name, info in agents.items():
                icon = "✅" if info["model_exists"] else "⬜"
                n = info["n_samples"]
                st.caption(f"{icon} **{agent_name}** — {n} proyectos")
        else:
            st.caption("Sin datos ML")
    except Exception:
        st.caption("N/A")


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------

tab_nueva, tab_estado, tab_resultados, tab_cerrar = st.tabs([
    "📤 Nueva Estimación",
    "📊 Estado",
    "📋 Resultados",
    "✔️ Cerrar Proyecto",
])


# ══════════════════════════════════════════════════════════════════════════
# Tab 1 — Nueva estimación
# ══════════════════════════════════════════════════════════════════════════

with tab_nueva:
    st.header("Nueva estimación")

    with st.form("nueva_estimacion"):
        col_file, col_client = st.columns([1, 1])

        with col_file:
            st.subheader("Archivo")
            uploaded = st.file_uploader(
                "Cargar archivo de planos",
                type=["skp", "pdf"],
                help="Formatos soportados: .skp (SketchUp) y .pdf (planos CAD)",
            )

        with col_client:
            st.subheader("Cliente")
            cliente_nombre   = st.text_input("Nombre", placeholder="Juan García")
            cliente_email    = st.text_input("Email", placeholder="juan@empresa.com")
            cliente_telefono = st.text_input("Teléfono", placeholder="+54 11 1234-5678")
            cliente_dir      = st.text_input("Dirección de obra", placeholder="Av. Corrientes 1234, CABA")
            proyecto_nombre  = st.text_input("Nombre del proyecto", placeholder="Cocina principal")

        st.subheader("Parámetros de obra")
        p_col1, p_col2, p_col3 = st.columns(3)

        with p_col1:
            dist_obra    = st.number_input("Distancia a obra (km)", min_value=0, value=15, step=5)
            dist_proveedor = st.number_input("Distancia a proveedor (km)", min_value=0, value=30, step=5)

        with p_col2:
            n_instaladores  = st.number_input("Instaladores", min_value=1, max_value=10, value=2)
            duracion_dias   = st.number_input("Duración estimada (días)", min_value=1, max_value=60, value=5)

        with p_col3:
            tipo_obra = st.selectbox(
                "Tipo de obra",
                options=[0, 1, 2],
                format_func=lambda x: {0: "Residencial", 1: "Comercial", 2: "Industrial"}[x],
            )
            tiene_lacado = st.toggle("Incluye lacado", value=False)

        submitted = st.form_submit_button("🚀 Iniciar estimación", use_container_width=True, type="primary")

    if submitted:
        if not uploaded:
            st.error("Seleccioná un archivo .skp o .pdf antes de continuar.")
        else:
            metadata = {
                "proyecto_nombre": proyecto_nombre or uploaded.name,
                "cliente": {
                    "nombre":         cliente_nombre,
                    "email":          cliente_email,
                    "telefono":       cliente_telefono,
                    "direccion_obra": cliente_dir,
                    "cliente_id":     "",
                },
                "project_params": {
                    "distancia_obra_km":      dist_obra,
                    "distancia_proveedor_km": dist_proveedor,
                    "n_instaladores":         n_instaladores,
                    "tipo_obra":              tipo_obra,
                    "duracion_proyecto_dias": duracion_dias,
                    "tiene_lacado":           tiene_lacado,
                },
            }

            with st.spinner("Enviando archivo al servidor…"):
                try:
                    import json as _json
                    resp = requests.post(
                        api("/api/v1/projects/analyze"),
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                        data={"metadata": _json.dumps(metadata)},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    st.session_state.project_id = data["project_id"]
                    st.session_state.polling = True
                    st.success(f"Estimación iniciada — Project ID: `{data['project_id']}`")
                    st.info("Pasá a la pestaña **Estado** para ver el progreso.")
                except requests.HTTPError as e:
                    st.error(f"Error del servidor: {e.response.status_code} — {e.response.text}")
                except Exception as e:
                    st.error(f"No se pudo conectar al backend: {e}")


# ══════════════════════════════════════════════════════════════════════════
# Tab 2 — Estado del pipeline
# ══════════════════════════════════════════════════════════════════════════

with tab_estado:
    st.header("Estado del pipeline")

    pid = st.session_state.project_id
    if not pid:
        st.info("No hay ningún proyecto activo. Iniciá una estimación en la primera pestaña.")
    else:
        st.caption(f"Project ID: `{pid}`")

        state = get_project_state()
        if state is None:
            st.error("No se pudo obtener el estado del proyecto.")
        else:
            status = state.get("status", "")
            progress = state.get("progress", {})

            # Status badge
            st.markdown(_status_badge(status), unsafe_allow_html=True)
            st.write("")

            if state.get("error"):
                st.error(f"**Error:** {state['error']}")

            # Progress bars
            cols = st.columns(4)
            stages = [
                ("parsing",  "🔍 Parseo"),
                ("bom",      "📋 BOM"),
                ("costs",    "💰 Costos"),
                ("quoting",  "📄 Presupuesto"),
            ]
            for col, (key, label) in zip(cols, stages):
                with col:
                    val = progress.get(key, 0) / 100.0
                    st.metric(label, f"{int(val*100)}%")
                    st.progress(val)

            st.caption(f"Actualizado: {state.get('updated_at', '—')}")

            # Auto-refresh while pipeline is running
            if status not in ("done", "error"):
                st.session_state.polling = True
                col_refresh, col_auto = st.columns([1, 2])
                with col_refresh:
                    if st.button("🔄 Actualizar ahora"):
                        st.rerun()
                with col_auto:
                    if st.toggle("Auto-refresh (2s)", value=True, key="auto_refresh"):
                        time.sleep(2)
                        st.rerun()
            else:
                st.session_state.polling = False
                if status == "done":
                    st.success("Pipeline completado. Pasá a la pestaña **Resultados**.")


# ══════════════════════════════════════════════════════════════════════════
# Tab 3 — Resultados
# ══════════════════════════════════════════════════════════════════════════

with tab_resultados:
    st.header("Resultados")

    pid = st.session_state.project_id
    if not pid:
        st.info("No hay ningún proyecto activo.")
    else:
        state = get_project_state()
        if not state or state.get("status") != "done":
            current = state.get("status", "desconocido") if state else "sin datos"
            st.warning(f"El pipeline aún no terminó (estado: **{current}**). Esperá en la pestaña **Estado**.")
        else:
            sub_bom, sub_costos, sub_presupuesto = st.tabs(["📋 BOM", "💰 Costos", "📄 Presupuesto"])

            # ── BOM ──────────────────────────────────────────────────────
            with sub_bom:
                try:
                    bom_resp = requests.get(api(f"/api/v1/projects/{pid}/bom"), timeout=5)
                    bom_resp.raise_for_status()
                    bom = bom_resp.json().get("bom", {})
                except Exception as e:
                    st.error(f"No se pudo obtener el BOM: {e}")
                    bom = {}

                if bom:
                    # Resumen
                    resumen = bom.get("resumen", {})
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("Piezas procesadas", resumen.get("piezas_procesadas", "—"))
                    with c2:
                        total_mat = resumen.get("total_materiales_usd", 0)
                        st.metric("Costo materiales", f"${total_mat:,.2f}")

                    # Tableros
                    st.subheader("Tableros")
                    import pandas as pd
                    tablero_rows = []
                    for t in bom.get("tableros", []):
                        tablero_rows.append({
                            "Material": t.get("material_id", ""),
                            "Tableros":  t.get("tableros_necesarios", 0),
                            "Desperdicio": f"{t.get('desperdicio_pct', 0)*100:.1f}%",
                            "Costo USD": f"${t.get('costo_tableros_usd', 0):,.2f}",
                        })
                    if tablero_rows:
                        st.dataframe(pd.DataFrame(tablero_rows), use_container_width=True, hide_index=True)

                    # Herrajes
                    st.subheader("Herrajes")
                    herrajes = bom.get("herrajes", {})
                    herr_rows = []
                    for linea in herrajes.get("lineas", []):
                        herr_rows.append({
                            "Herraje":   linea.get("nombre", ""),
                            "Cantidad":  f"{linea.get('cantidad', 0)} {linea.get('unidad', '')}",
                            "P. Unit.":  f"${linea.get('precio_unitario_usd', 0):.2f}",
                            "Total USD": f"${linea.get('precio_total_usd', 0):,.2f}",
                        })
                    if herr_rows:
                        st.dataframe(pd.DataFrame(herr_rows), use_container_width=True, hide_index=True)
                    total_herr = herrajes.get("total_herrajes_usd", 0)
                    st.caption(f"**Total herrajes: ${total_herr:,.2f}**")

            # ── Costos ───────────────────────────────────────────────────
            with sub_costos:
                try:
                    costs_resp = requests.get(api(f"/api/v1/projects/{pid}/costs"), timeout=5)
                    costs_resp.raise_for_status()
                    costs = costs_resp.json().get("costs", {})
                except Exception as e:
                    st.error(f"No se pudo obtener los costos: {e}")
                    costs = {}

                if costs:
                    # KPI row
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Materiales",    f"${costs.get('costo_materiales_usd', 0):,.0f}")
                    k2.metric("Mano de obra",  f"${costs.get('costo_mano_obra_usd',  0):,.0f}")
                    k3.metric("Instalación",   f"${costs.get('costo_instalacion_usd',0):,.0f}")
                    k4.metric("Transporte",    f"${costs.get('costo_transporte_usd', 0):,.0f}")

                    st.divider()
                    c_left, c_right = st.columns([1, 1])

                    with c_left:
                        costo_total = costs.get("costo_total_usd", 0)
                        overhead    = costs.get("costo_indirecto_usd", 0)
                        st.metric("Overhead",     f"${overhead:,.0f}")
                        st.metric("Costo total",  f"${costo_total:,.0f}", delta=None)

                    with c_right:
                        precio = costs.get("precio_sugerido_usd", 0)
                        confianza = costs.get("confianza_global", 0)
                        st.metric(
                            "💡 Precio sugerido",
                            f"${precio:,.0f}",
                            delta=f"+{precio-costo_total:,.0f} sobre costo",
                        )
                        st.markdown(
                            f"Confianza del modelo: {_confidence_bar(confianza)}",
                            unsafe_allow_html=True,
                        )

                    # Fuentes ML
                    st.subheader("Fuentes de estimación")
                    fuentes = costs.get("fuentes", {})
                    intervalos = costs.get("intervalos", {})
                    # (fuente_key, intervalo_prefix, label)
                    agent_map = [
                        ("mano_obra",  "labor",     "Labor"),
                        ("instalacion","install",   "Instalación"),
                        ("transporte", "transport", "Transporte"),
                        ("indirecto",  "overhead",  "Overhead"),
                    ]
                    src_rows = []
                    for fuente_key, intv_key, label in agent_map:
                        src = fuentes.get(fuente_key, "—")
                        low  = intervalos.get(f"{intv_key}_low",  0)
                        high = intervalos.get(f"{intv_key}_high", 0)
                        src_rows.append({
                            "Agente":  label,
                            "Fuente":  src,
                            "Rango":   f"${low:,.0f} – ${high:,.0f}",
                        })
                    import pandas as pd
                    st.dataframe(pd.DataFrame(src_rows), use_container_width=True, hide_index=True)

                    # Escenarios
                    escenarios = costs.get("escenarios_precio", {})
                    if escenarios:
                        st.subheader("Escenarios de precio")
                        e1, e2, e3 = st.columns(3)
                        e1.metric("🔵 Conservador", f"${escenarios.get('conservador', 0):,.0f}")
                        e2.metric("🟢 Sugerido",    f"${precio:,.0f}")
                        e3.metric("🔴 Agresivo",    f"${escenarios.get('agresivo', 0):,.0f}")

            # ── Presupuesto ───────────────────────────────────────────────
            with sub_presupuesto:
                try:
                    q_resp = requests.get(api(f"/api/v1/projects/{pid}/quote"), timeout=5)
                    q_resp.raise_for_status()
                    q_data = q_resp.json()
                except Exception as e:
                    st.error(f"No se pudo obtener los archivos: {e}")
                    q_data = {}

                if q_data:
                    st.subheader(f"Presupuesto {q_data.get('quote_number', '')}")
                    files = q_data.get("files", {})

                    def _download_btn(label: str, full_url: str, mime: str):
                        """Fetch from API and present a Streamlit download button."""
                        filename = full_url.split("/")[-1] or "archivo"
                        try:
                            r = requests.get(full_url, timeout=15)
                            r.raise_for_status()
                            st.download_button(
                                label=label,
                                data=r.content,
                                file_name=filename,
                                mime=mime,
                                use_container_width=True,
                            )
                        except Exception as exc:
                            st.error(f"Error al descargar {filename}: {exc}")

                    col_dl1, col_dl2, col_dl3 = st.columns(3)
                    with col_dl1:
                        if files.get("pdf_resumido"):
                            _download_btn("📄 PDF Resumido", files["pdf_resumido"], "application/pdf")

                    with col_dl2:
                        if files.get("pdf_detallado"):
                            _download_btn("📑 PDF Detallado", files["pdf_detallado"], "application/pdf")

                    with col_dl3:
                        if files.get("excel"):
                            _download_btn(
                                "📊 Excel Producción", files["excel"],
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                    # Regenerar con precio custom
                    st.divider()
                    st.subheader("Regenerar presupuesto")
                    with st.form("regenerar"):
                        precio_custom = st.number_input(
                            "Precio de venta override (USD)", min_value=0.0, value=0.0, step=50.0,
                            help="Dejá en 0 para usar el precio sugerido por el modelo",
                        )
                        if st.form_submit_button("🔄 Regenerar", use_container_width=True):
                            payload = {
                                "mode": "both",
                                "precio_override": precio_custom if precio_custom > 0 else None,
                            }
                            try:
                                r = requests.post(
                                    api(f"/api/v1/projects/{pid}/quote/regenerate"),
                                    json=payload,
                                    timeout=30,
                                )
                                r.raise_for_status()
                                st.success(f"Regenerado como {r.json().get('quote_number')}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al regenerar: {e}")


# ══════════════════════════════════════════════════════════════════════════
# Tab 4 — Cerrar proyecto
# ══════════════════════════════════════════════════════════════════════════

with tab_cerrar:
    st.header("Cerrar proyecto")
    st.write(
        "Registrá los costos reales del proyecto ejecutado. Esto alimenta el modelo ML "
        "para mejorar las estimaciones futuras. Tras **5 proyectos cerrados**, el sistema "
        "re-entrena automáticamente."
    )

    pid = st.session_state.project_id
    if not pid:
        st.info("No hay ningún proyecto activo.")
    else:
        state = get_project_state()
        if not state or state.get("status") != "done":
            st.warning("El proyecto debe estar completo antes de poder cerrarlo.")
        else:
            # Show estimated costs for reference
            try:
                costs_resp = requests.get(api(f"/api/v1/projects/{pid}/costs"), timeout=5)
                costs = costs_resp.json().get("costs", {}) if costs_resp.status_code == 200 else {}
            except Exception:
                costs = {}

            if costs:
                st.subheader("Estimación vs. real")
                ref_col1, ref_col2, ref_col3, ref_col4 = st.columns(4)
                ref_col1.metric("Labor estimado",     f"${costs.get('costo_mano_obra_usd', 0):,.0f}")
                ref_col2.metric("Inst. estimada",     f"${costs.get('costo_instalacion_usd', 0):,.0f}")
                ref_col3.metric("Transp. estimado",   f"${costs.get('costo_transporte_usd', 0):,.0f}")
                ref_col4.metric("Total estimado",     f"${costs.get('costo_total_usd', 0):,.0f}")
                st.divider()

            with st.form("cerrar_proyecto"):
                c1, c2 = st.columns(2)
                with c1:
                    labor_real     = st.number_input("Mano de obra real (USD)",  min_value=0.0, step=10.0,
                                                    value=float(costs.get("costo_mano_obra_usd",  0) or 0))
                    install_real   = st.number_input("Instalación real (USD)",    min_value=0.0, step=10.0,
                                                    value=float(costs.get("costo_instalacion_usd",0) or 0))
                with c2:
                    transport_real = st.number_input("Transporte real (USD)",     min_value=0.0, step=10.0,
                                                    value=float(costs.get("costo_transporte_usd", 0) or 0))
                    total_real     = st.number_input("Total facturado al cliente (USD)", min_value=0.0, step=10.0,
                                                    value=float(costs.get("precio_sugerido_usd",  0) or 0))

                cerrar_btn = st.form_submit_button("✔️ Cerrar proyecto y registrar costos", use_container_width=True, type="primary")

            if cerrar_btn:
                try:
                    payload = {
                        "labor_real":     labor_real,
                        "install_real":   install_real,
                        "transport_real": transport_real,
                        "total_real":     total_real,
                    }
                    r = requests.post(api(f"/api/v1/projects/{pid}/close"), json=payload, timeout=15)
                    r.raise_for_status()
                    result = r.json()
                    st.success("Proyecto cerrado correctamente.")
                    if result.get("retrained"):
                        st.balloons()
                        st.info("🎉 El modelo ML fue re-entrenado con los nuevos datos.")
                    else:
                        st.info("Datos registrados. El modelo se re-entrenará cuando haya 5 proyectos nuevos.")
                except Exception as e:
                    st.error(f"Error al cerrar el proyecto: {e}")

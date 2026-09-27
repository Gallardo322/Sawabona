import streamlit as st
import sqlite3
import json
import hashlib
import os
import io
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Comunidad Terapéutica Sawabona Shikoba A.C.",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE UTILIDAD ---
def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    for k, v in replacements.items():
        texto = str(texto).replace(k, v)
    return texto

def get_safe_index(options, value, default=0):
    if not value:
        return default
    val_clean = str(value).strip().lower()
    for idx, opt in enumerate(options):
        if str(opt).strip().lower() == val_clean:
            return idx
    return default

def calculate_age(born_str):
    if not born_str:
        return 0
    try:
        born = datetime.strptime(born_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except:
        return 0

def days_between(date_str):
    if not date_str:
        return 0
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except:
        return 0

# --- INICIALIZACIÓN DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Consejero',
            estado TEXT DEFAULT 'Activo'
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_ingreso TEXT,
            datos_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            numero_sesion INTEGER,
            fecha TEXT,
            etapa TEXT,
            consejero TEXT,
            datos_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            facilitador TEXT,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            stock INTEGER,
            indicaciones TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS entrega_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            fecha TEXT,
            dosis TEXT,
            responsable TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            carpeta TEXT,
            nombre_archivo TEXT,
            fecha TEXT,
            usuario TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS carpetas_custom (
            nombre TEXT PRIMARY KEY
        )
    """)

    # Crear admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        pass_h = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, ?)',
                  ('admin', pass_h, 'Administrador del Sistema', 'Administrador', 'Activo'))
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol, estado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

# --- HEADER REUTILIZABLE ---
def render_header():
    st.markdown("""
        <div style='background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%); padding: 18px 25px; border-radius: 12px; color: white; margin-bottom: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
            <div style='display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;'>
                <div>
                    <h1 style='color: #FFFFFF; margin: 0; font-size: 1.8em; font-weight: bold;'>🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>
                    <p style='color: #C8E6C9; margin: 4px 0 0 0; font-size: 1.05em; font-weight: 500;'>Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</p>
                </div>
                <div style='margin-top: 8px;'>
                    <span style='background-color: #4CAF50; color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold; margin-right: 8px;'>SISTEMA ACTIVO</span>
                    <span style='background-color: #81C784; color: #1B5E20; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold;'>NOM-028-SSA2-2009</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

# --- PDF EN HORIZONTAL PARA LISTA DE PACIENTES ---
class PDFListaPacientes(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "PADRON Y LISTADO GENERAL DE RESIDENTES ACTIVOS E INACTIVOS", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_lista_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()

    pdf = PDFListaPacientes(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [30, 65, 20, 18, 40, 35, 35, 25]
    headers = ["Folio / Exp.", "Nombre Completo", "Sexo", "Edad", "Etapa Actual", "Dias Proceso", "Dias Etapa", "Estado"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for row in rows:
        pid, d_json = row
        d = json.loads(d_json) if d_json else {}
        
        nombre = f"{d.get('nombre','')} {d.get('ap_paterno','')} {d.get('ap_materno','')}".strip() or d.get("nombre_completo", "Sin Nombre")
        exp = d.get("numero_expediente", pid)
        sexo = d.get("sexo", "N/R")
        fnac = d.get("fecha_nacimiento", "")
        edad = str(calculate_age(fnac)) if fnac else "N/R"
        etapa = d.get("etapa_actual", "Acogida")
        
        dias_proc = str(days_between(d.get("fecha_ingreso_institucion", d.get("fecha_ingreso", ""))))
        dias_etapa = str(days_between(d.get("fecha_inicio_etapa", "")))
        estado = d.get("estado_paciente", "Activo")
        
        pdf.cell(col_w[0], 6, clean_pdf_text(f"{pid} ({exp})"), border=1)
        pdf.cell(col_w[1], 6, clean_pdf_text(nombre[:35]), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(sexo), border=1, align="C")
        pdf.cell(col_w[3], 6, clean_pdf_text(edad), border=1, align="C")
        pdf.cell(col_w[4], 6, clean_pdf_text(etapa), border=1)
        pdf.cell(col_w[5], 6, clean_pdf_text(f"{dias_proc} dias"), border=1, align="C")
        pdf.cell(col_w[6], 6, clean_pdf_text(f"{dias_etapa} dias"), border=1, align="C")
        pdf.cell(col_w[7], 6, clean_pdf_text(estado), border=1, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf_file = "Reporte_General_Pacientes_Sawabona.pdf"
    pdf.output(pdf_file)
    return pdf_file

# --- APLICACIÓN PRINCIPAL ---
def main():
    init_db()

    # --- SESSION STATE ---
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "nombre_completo" not in st.session_state:
        st.session_state["nombre_completo"] = ""
    if "rol" not in st.session_state:
        st.session_state["rol"] = ""
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()

    # --- MENSAJES PERSISTENTES TRAS RERUN ---
    if "mensaje_exito" in st.session_state:
        st.success(st.session_state["mensaje_exito"])
        st.balloons()
        del st.session_state["mensaje_exito"]

    # --- CONTROL DE LOGIN ---
    if not st.session_state["logged_in"]:
        render_header()
        st.subheader("🔐 Inicio de Sesión de Personal")
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            with st.form("login_form"):
                u_in = st.text_input("Usuario")
                p_in = st.text_input("Contraseña", type="password")
                btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                
                if btn_login:
                    res = verificar_login(u_in, p_in)
                    if res:
                        u, n, r, est = res
                        if est == "Bloqueado":
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = u
                            st.session_state["nombre_completo"] = n
                            st.session_state["rol"] = r
                            st.session_state["ultima_actividad"] = datetime.now()
                            st.session_state["mensaje_exito"] = f"🎉 ¡Bienvenido al Sistema, {n}!"
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
            st.info("💡 Credencial por defecto: Usuario: `admin` | Contraseña: `admin123`")
        return

    # --- TIMEOUT INACTIVIDAD (10 MIN) ---
    inactivo_seg = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
    if inactivo_seg > 600:
        st.session_state["logged_in"] = False
        st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión nuevamente.")
        st.rerun()
    st.session_state["ultima_actividad"] = datetime.now()

    # --- NAVEGACIÓN PRINCIPAL ---
    st.sidebar.markdown("""
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica A.C.</p>
        </div>
    """, unsafe_allow_html=True)

    st.sidebar.write(f"👤 **{st.session_state['nombre_completo']}**")
    st.sidebar.write(f"🏷️ **Rol**: {st.session_state['rol']}")

    menu = st.sidebar.selectbox(
        "Seleccione Módulo",
        [
            "🏠 Inicio / Tablero General",
            "👤 Registro y Edición de Pacientes",
            "📄 Ficha de Ingreso y Admisión",
            "📝 Entrevista Inicial de Consejería",
            "📝 Consejerías Individuales",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "💊 Control de Medicamentos",
            "📁 Repositorio de Documentos",
            "🔍 Buscar y Listar Pacientes",
            "⚙️ Configuración y Seguridad",
            "📦 Respaldo y Restauración"
        ]
    )

    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    render_header()

    # ==========================================
    # 1. TABLERO GENERAL
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General y Control Clínico")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT datos_json FROM entrevistas')
        rows = c.fetchall()
        conn.close()

        activos = 0
        inactivos = 0
        etapas_count = {"Acogida": 0, "Identificación": 0, "Elaboración": 0, "Consolidación": 0, "Servicio Social": 0}
        pacientes_por_etapa = {"Acogida": [], "Identificación": [], "Elaboración": [], "Consolidación": [], "Servicio Social": []}

        for r in rows:
            if r[0]:
                d = json.loads(r[0])
                est = d.get("estado_paciente", "Activo")
                etapa = d.get("etapa_actual", "Acogida")
                if est == "Activo":
                    activos += 1
                    if etapa in etapas_count:
                        etapas_count[etapa] += 1
                        pacientes_por_etapa[etapa].append(d)
                else:
                    inactivos += 1

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("🟢 Residentes Activos", activos)
        m2.metric("🌱 Acogida", etapas_count["Acogida"])
        m3.metric("🔎 Identificación", etapas_count["Identificación"])
        m4.metric("⚙️ Elaboración", etapas_count["Elaboración"])
        m5.metric("🎯 Consolidación", etapas_count["Consolidación"])
        m6.metric("🤝 Servicio Social", etapas_count["Servicio Social"])

        st.divider()
        st.subheader("📋 Padrón por Etapas del Modelo de Tratamiento")
        
        t_ac, t_id, t_el, t_co, t_ss = st.tabs(["🌱 Acogida", "🔎 Identificación", "⚙️ Elaboración", "🎯 Consolidación", "🤝 Servicio Social"])
        
        tabs_map = [
            (t_ac, "Acogida"),
            (t_id, "Identificación"),
            (t_el, "Elaboración"),
            (t_co, "Consolidación"),
            (t_ss, "Servicio Social")
        ]

        for tab_obj, et_name in tabs_map:
            with tab_obj:
                plist = pacientes_por_etapa[et_name]
                if not plist:
                    st.info(f"No hay residentes actualmente registrados en la etapa de {et_name}.")
                else:
                    st.write(f"**Residentes en {et_name}: {len(plist)}**")
                    for p in plist:
                        nombre = f"{p.get('nombre','')} {p.get('ap_paterno','')} {p.get('ap_materno','')}".strip() or p.get("nombre_completo", "")
                        dias_proc = days_between(p.get("fecha_ingreso_institucion", p.get("fecha_ingreso","")))
                        dias_et = days_between(p.get("fecha_inicio_etapa",""))
                        st.write(f"• **{nombre}** | Folio: `{p.get('paciente_id','')}` | Exp: `{p.get('numero_expediente','')}` | Días en proceso: **{dias_proc}** | Días en etapa: **{dias_et}**")

    # ==========================================
    # 2. REGISTRO Y EDICIÓN DE PACIENTES
    # ==========================================
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        
        tab_alta, tab_edit, tab_block = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Estado y Bloqueo"])
        
        # --- ALTA NUEVO PACIENTE ---
        with tab_alta:
            st.subheader("Formulario de Alta de Residente")
            with st.form("form_alta_paciente", clear_on_submit=True):
                col_a1, col_a2, col_a3 = st.columns(3)
                with col_a1:
                    exp_in = st.text_input("Número de Expediente *", value="").strip()
                    nombre_in = st.text_input("Nombre(s) *", value="").strip()
                with col_a2:
                    ap_pat_in = st.text_input("Apellido Paterno *", value="").strip()
                    ap_mat_in = st.text_input("Apellido Materno", value="").strip()
                with col_a3:
                    sexo_in = st.selectbox("Sexo *", ["Masculino", "Femenino", "Otro"])
                    f_nac_in = st.date_input("Fecha de Nacimiento *", value=date(1995, 1, 1))

                st.divider()
                col_b1, col_b2, col_b3 = st.columns(3)
                with col_b1:
                    f_ing_in = st.date_input("Fecha de Ingreso a la Institución *", value=date.today())
                with col_b2:
                    f_etapa_in = st.date_input("Fecha de Inicio de Etapa *", value=date.today())
                with col_b3:
                    etapa_in = st.selectbox("Etapa Inicial *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])

                mod_in = st.selectbox("Modalidad de Internamiento", ["Voluntaria", "Involuntaria por solicitud familiar", "Obligatoria por medida judicial"])
                
                btn_alta = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                
                if btn_alta:
                    if not nombre_in or not ap_pat_in:
                        st.error("⚠️ El Nombre(s) y el Apellido Paterno son campos obligatorios.")
                    else:
                        full_name = f"{nombre_in} {ap_pat_in} {ap_mat_in}".strip()
                        
                        # Validar Duplicados
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT paciente_id, datos_json FROM entrevistas')
                        all_rows = c.fetchall()
                        conn.close()

                        dup_found = False
                        exp_dup = False
                        
                        for pid, djson in all_rows:
                            if djson:
                                dj = json.loads(djson)
                                ex_fn = f"{dj.get('nombre','')} {dj.get('ap_paterno','')} {dj.get('ap_materno','')}".strip()
                                if ex_fn.lower() == full_name.lower():
                                    dup_found = True
                                    st.error(f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{full_name}' (Folio: {pid}, Exp: {dj.get('numero_expediente','')}).")
                                    break
                                if exp_in and dj.get("numero_expediente") and str(dj.get("numero_expediente")).strip() == exp_in:
                                    exp_dup = True
                                    st.error(f"⛔ EXPEDIENTE DUPLICADO: El número de expediente '{exp_in}' ya está asignado a {ex_fn}.")
                                    break

                        if not dup_found and not exp_dup:
                            next_id = f"PAC-{(len(all_rows) + 1):03d}"
                            datos_paciente = {
                                "paciente_id": next_id,
                                "numero_expediente": exp_in or str(len(all_rows) + 1),
                                "nombre": nombre_in,
                                "ap_paterno": ap_pat_in,
                                "ap_materno": ap_mat_in,
                                "nombre_completo": full_name,
                                "sexo": sexo_in,
                                "fecha_nacimiento": str(f_nac_in),
                                "fecha_ingreso_institucion": str(f_ing_in),
                                "fecha_inicio_etapa": str(f_etapa_in),
                                "etapa_actual": etapa_in,
                                "modalidad_internamiento": mod_in,
                                "sustancia_impacto": "Sin registrar",
                                "estado_paciente": "Activo"
                            }
                            
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                                      (next_id, now_s, now_s, st.session_state["username"], json.dumps(datos_paciente, ensure_ascii=False)))
                            conn.commit()
                            conn.close()

                            st.session_state["mensaje_exito"] = f"🎉 ¡Residente {full_name} registrado exitosamente con Folio {next_id}!"
                            st.rerun()

        # --- EDITAR PACIENTE ---
        with tab_edit:
            st.subheader("Editar Paciente Existente")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT paciente_id, datos_json FROM entrevistas')
            p_rows = c.fetchall()
            conn.close()

            p_options = {}
            for pid, dj in p_rows:
                if dj:
                    d = json.loads(dj)
                    fn = f"{d.get('nombre','')} {d.get('ap_paterno','')} {d.get('ap_materno','')}".strip() or d.get("nombre_completo","")
                    p_options[f"{pid} - {fn} (Exp: {d.get('numero_expediente','')})"] = (pid, d)

            if not p_options:
                st.info("No hay pacientes registrados para editar.")
            else:
                selected_p = st.selectbox("Seleccione Paciente a Editar", list(p_options.keys()))
                sel_pid, dj = p_options[selected_p]

                with st.form("form_edit_paciente"):
                    c_e1, c_e2, c_e3 = st.columns(3)
                    with c_e1:
                        e_exp = st.text_input("Número de Expediente", value=dj.get("numero_expediente",""))
                        e_nom = st.text_input("Nombre(s)", value=dj.get("nombre",""))
                    with c_e2:
                        e_app = st.text_input("Apellido Paterno", value=dj.get("ap_paterno",""))
                        e_apm = st.text_input("Apellido Materno", value=dj.get("ap_materno",""))
                    with c_e3:
                        e_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=get_safe_index(["Masculino", "Femenino", "Otro"], dj.get("sexo","Masculino")))
                        try:
                            fn_val = datetime.strptime(dj.get("fecha_nacimiento","1995-01-01"), "%Y-%m-%d").date()
                        except:
                            fn_val = date(1995, 1, 1)
                        e_fnac = st.date_input("Fecha de Nacimiento", value=fn_val)

                    st.divider()
                    c_f1, c_f2, c_f3 = st.columns(3)
                    with c_f1:
                        try:
                            fi_val = datetime.strptime(dj.get("fecha_ingreso_institucion", dj.get("fecha_ingreso","2026-01-01"))[:10], "%Y-%m-%d").date()
                        except:
                            fi_val = date.today()
                        e_fing = st.date_input("Fecha Ingreso a la Institución", value=fi_val)
                    with c_f2:
                        try:
                            fe_val = datetime.strptime(dj.get("fecha_inicio_etapa","2026-01-01")[:10], "%Y-%m-%d").date()
                        except:
                            fe_val = date.today()
                        e_fetapa = st.date_input("Fecha Inicio de Etapa", value=fe_val)
                    with c_f3:
                        e_etapa = st.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=get_safe_index(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], dj.get("etapa_actual","Acogida")))

                    e_mod = st.selectbox("Modalidad Internamiento", ["Voluntaria", "Involuntaria por solicitud familiar", "Obligatoria por medida judicial"], index=get_safe_index(["Voluntaria", "Involuntaria por solicitud familiar", "Obligatoria por medida judicial"], dj.get("modalidad_internamiento","Voluntaria")))
                    
                    btn_update = st.form_submit_button("💾 Guardar Cambios del Paciente", use_container_width=True)
                    
                    if btn_update:
                        dj["numero_expediente"] = e_exp
                        dj["nombre"] = e_nom
                        dj["ap_paterno"] = e_app
                        dj["ap_materno"] = e_apm
                        dj["nombre_completo"] = f"{e_nom} {e_app} {e_apm}".strip()
                        dj["sexo"] = e_sexo
                        dj["fecha_nacimiento"] = str(e_fnac)
                        dj["fecha_ingreso_institucion"] = str(e_fing)
                        dj["fecha_inicio_etapa"] = str(e_fetapa)
                        dj["etapa_actual"] = e_etapa
                        dj["modalidad_internamiento"] = e_mod

                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?',
                                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(dj, ensure_ascii=False), sel_pid))
                        conn.commit()
                        conn.close()

                        st.session_state["mensaje_exito"] = f"✅ Paciente {dj['nombre_completo']} actualizado correctamente."
                        st.rerun()

        # --- BLOQUEO PACIENTES ---
        with tab_block:
            st.subheader("Gestión de Estado y Bloqueo de Residente")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT paciente_id, datos_json FROM entrevistas')
            b_rows = c.fetchall()
            conn.close()

            for pid, djson in b_rows:
                if djson:
                    dj = json.loads(djson)
                    fn = dj.get("nombre_completo", pid)
                    est = dj.get("estado_paciente", "Activo")
                    
                    cb1, cb2, cb3 = st.columns([3, 1, 1])
                    cb1.write(f"• **{fn}** (Folio: `{pid}`, Exp: `{dj.get('numero_expediente','')}`) - Estado actual: **{est}**")
                    if est == "Activo":
                        if cb2.button("🔴 Bloquear", key=f"blk_{pid}"):
                            dj["estado_paciente"] = "Bloqueado"
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE entrevistas SET datos_json = ? WHERE paciente_id = ?', (json.dumps(dj, ensure_ascii=False), pid))
                            conn.commit()
                            conn.close()
                            st.session_state["mensaje_exito"] = f"🔴 Residente {fn} cambiado a Bloqueado."
                            st.rerun()
                    else:
                        if cb3.button("🟢 Activar", key=f"act_{pid}"):
                            dj["estado_paciente"] = "Activo"
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE entrevistas SET datos_json = ? WHERE paciente_id = ?', (json.dumps(dj, ensure_ascii=False), pid))
                            conn.commit()
                            conn.close()
                            st.session_state["mensaje_exito"] = f"🟢 Residente {fn} reactivado."
                            st.rerun()

        st.divider()
        st.subheader("📋 Lista en Vivo de Residentes Activos")
        pdf_f = generar_pdf_lista_pacientes()
        with open(pdf_f, "rb") as f:
            st.download_button(
                label="🖨️ Imprimir / Descargar Reporte de Pacientes (PDF)",
                data=f,
                file_name=pdf_f,
                mime="application/pdf"
            )

    # ==========================================
    # 3. FICHA DE INGRESO Y ADMISIÓN
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (Formato Oficial Sawabona)")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, datos_json FROM entrevistas')
        p_rows = c.fetchall()
        conn.close()

        p_dict = {}
        for pid, djson in p_rows:
            if djson:
                dj = json.loads(djson)
                p_dict[f"{pid} - {dj.get('nombre_completo','')}"] = (pid, dj)

        if not p_dict:
            st.warning("Debe registrar al menos un paciente para llenar la Ficha de Ingreso.")
        else:
            sel_p = st.selectbox("Seleccione el Paciente para la Ficha de Ingreso", list(p_dict.keys()))
            sel_pid, dj_pac = p_dict[sel_p]

            with st.form("form_ficha_ingreso"):
                f_tab1, f_tab2, f_tab3, f_tab4, f_tab5 = st.tabs([
                    "1. Sucursal y Folios",
                    "2. Datos del Residente",
                    "3. Sustancias de Consumo",
                    "4. Responsables y Contacto",
                    "5. Términos y Cuotas"
                ])

                with f_tab1:
                    sucursal = st.text_input("Sucursal a Referir", value="Matriz Colima")
                    f_exp = st.text_input("No. de Expediente", value=dj_pac.get("numero_expediente",""))
                    f_fecha_hora = st.text_input("Fecha y Hora de Ingreso", value=datetime.now().strftime("%Y-%m-%d %H:%M"))

                with f_tab2:
                    f_nom = st.text_input("Nombre Completo del Residente", value=dj_pac.get("nombre_completo",""))
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        f_edad = st.text_input("Edad", value=str(calculate_age(dj_pac.get("fecha_nacimiento",""))))
                        f_ecivil = st.text_input("Estado Civil", value="Soltero")
                    with c2:
                        f_esc = st.text_input("Escolaridad", value="Secundaria")
                        f_rel = st.text_input("Religión", value="Católica")
                    with c3:
                        f_ocu = st.text_input("Ocupación", value="Empleado")
                        f_serv_med = st.text_input("Servicios Médicos", value="IMSS / Ninguno")

                    f_dom = st.text_area("Domicilio Particular Completo", value="Calle Principal No. 123, Col. Centro")

                with f_tab3:
                    st.write("**Sustancias que Consume al Ingresar:**")
                    sust_opts = ["Alcaloides", "Alcohol", "Anfetaminas", "Benzodiazepinas", "Cannabis", "Esteroides", "Fármacos", "LSD", "Meta-anfetaminas", "Opiáceos", "Psicoactivas", "Solventes", "Tabaco"]
                    selected_sust = []
                    col_s1, col_s2, col_s3 = st.columns(3)
                    for idx, s_name in enumerate(sust_opts):
                        target_col = [col_s1, col_s2, col_s3][idx % 3]
                        if target_col.checkbox(s_name, key=f"sust_{s_name}"):
                            selected_sust.append(s_name)

                with f_tab4:
                    st.subheader("Responsable Familiar / Legal")
                    f_resp_nom = st.text_input("Nombre Completo del Responsable Familiar")
                    f_resp_parentesco = st.text_input("Parentesco (Desea internar a su...)", value="Padre / Madre / Esposo(a)")
                    f_resp_tel = st.text_input("Teléfono(s) del Responsable")
                    f_resp_dom = st.text_area("Domicilio del Responsable")

                    st.subheader("Contacto de Emergencia Secundario")
                    f_emg_nom = st.text_input("Nombre Contacto Emergencia")
                    f_emg_tel = st.text_input("Teléfono Contacto Emergencia")

                with f_tab5:
                    st.write("**Cláusulas Financieras Oficiales:**")
                    st.info("• Costo de Ingreso: $4,500.00 | Cuota Mensual: $6,000.00 | Pagaré: $42,000.00")
                    st.write("• El tratamiento tiene una duración sugerida de 6 a 8 meses (mínimo obligatorio de 7 meses conforme a NOM-028-SSA2-2009).")

                btn_save_ficha = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)

                if btn_save_ficha:
                    ficha_datos = {
                        "sucursal": sucursal,
                        "expediente": f_exp,
                        "fecha_hora": f_fecha_hora,
                        "nombre_residente": f_nom,
                        "edad": f_edad,
                        "estado_civil": f_ecivil,
                        "escolaridad": f_esc,
                        "religion": f_rel,
                        "ocupacion": f_ocu,
                        "servicios_medicos": f_serv_med,
                        "domicilio": f_dom,
                        "sustancias": selected_sust,
                        "responsable_nombre": f_resp_nom,
                        "responsable_parentesco": f_resp_parentesco,
                        "responsable_tel": f_resp_tel,
                        "responsable_domicilio": f_resp_dom,
                        "emergencia_nombre": f_emg_nom,
                        "emergencia_tel": f_emg_tel
                    }

                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('INSERT OR REPLACE INTO ficha_ingreso (paciente_id, fecha_ingreso, datos_json) VALUES (?, ?, ?)',
                              (sel_pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(ficha_datos, ensure_ascii=False)))
                    conn.commit()
                    conn.close()

                    st.session_state["mensaje_exito"] = f"✅ Ficha de Ingreso guardada correctamente para {f_nom}."
                    st.rerun()

    # ==========================================
    # 4. ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería (Evaluación Basal)")
        st.info("Consulte y complete la entrevista clínica inicial de adicciones.")

    # ==========================================
    # 5. CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales por Etapa")

    # ==========================================
    # 6. GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Promoción de Proceso")

    # ==========================================
    # 7. GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")

    # ==========================================
    # 8. CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control e Inventario de Medicamentos")

    # ==========================================
    # 9. REPOSIRORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos y Expedientes")

    # ==========================================
    # 10. BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Pacientes")
        
        pdf_f = generar_pdf_lista_pacientes()
        with open(pdf_f, "rb") as f:
            st.download_button(
                label="🖨️ Descargar Padrón Completo en PDF",
                data=f,
                file_name=pdf_f,
                mime="application/pdf"
            )

    # ==========================================
    # 11. CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad de Usuarios")
        
        t_sec1, t_sec2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        
        with t_sec1:
            with st.form("form_change_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_neu = st.text_input("Nueva Contraseña", type="password")
                p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p = st.form_submit_button("Actualizar Contraseña")
                
                if btn_p:
                    if p_neu != p_cnf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        v = verificar_login(st.session_state["username"], p_act)
                        if v:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(p_neu), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.session_state["mensaje_exito"] = "✅ Contraseña actualizada correctamente."
                            st.rerun()
                        else:
                            st.error("Contraseña actual incorrecta.")

        with t_sec2:
            st.subheader("Gestión de Personal")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT username, nombre_completo, rol, estado FROM usuarios')
            u_rows = c.fetchall()
            conn.close()

            for u, n, r, est in u_rows:
                u_col1, u_col2, u_col3 = st.columns([3, 1, 1])
                u_col1.write(f"• **{n}** (`{u}`) - Rol: **{r}** | Estado: **{est}**")
                if u != "admin":
                    if est == "Activo":
                        if u_col2.button("🔴 Bloquear", key=f"ublk_{u}"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET estado = "Bloqueado" WHERE username = ?', (u,))
                            conn.commit()
                            conn.close()
                            st.session_state["mensaje_exito"] = f"🔴 Usuario {u} bloqueado."
                            st.rerun()
                    else:
                        if u_col3.button("🟢 Activar", key=f"uact_{u}"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET estado = "Activo" WHERE username = ?', (u,))
                            conn.commit()
                            conn.close()
                            st.session_state["mensaje_exito"] = f"🟢 Usuario {u} reactivado."
                            st.rerun()

    # ==========================================
    # 12. RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        tab_down, tab_up = st.tabs(["⬇️ Copia de Seguridad (Respaldo)", "⬆️ Restaurar Base de Datos"])
        
        with tab_down:
            st.subheader("Descargar Copia de Seguridad (.db)")
            st.info("Guarde una copia local del archivo SQLite `sistema_pacientes.db` con toda la información de la institución.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar Copia de Seguridad Actual",
                        data=f,
                        file_name=f"backup_sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )

        with tab_up:
            st.subheader("Restaurar Base de Datos desde Respaldo")
            st.warning("⚠️ ADVERTENCIA: Al restaurar un archivo de respaldo, se reemplazará completamente la base de datos actual.")
            
            uploaded_db = st.file_uploader("Seleccione el archivo de respaldo (.db / .sqlite)", type=["db", "sqlite"], key="uploader_restore_db")
            
            if uploaded_db is not None:
                st.write(f"📁 **Archivo seleccionado**: `{uploaded_db.name}` ({uploaded_db.size} bytes)")
                
                if st.button("🔄 Confirmar y Restaurar Base de Datos Ahora", type="primary", use_container_width=True):
                    try:
                        db_bytes = uploaded_db.getbuffer()
                        # Close open SQLite connections before replacing
                        sqlite3.connect(DB_FILE).close()
                        with open(DB_FILE, "wb") as f:
                            f.write(db_bytes)
                        
                        st.session_state["mensaje_exito"] = f"🎉 ¡Base de datos restaurada con éxito desde {uploaded_db.name}!"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al restaurar la base de datos: {e}")

if __name__ == "__main__":
    main()

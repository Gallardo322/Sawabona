import streamlit as st
import sqlite3
import json
import hashlib
import os
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

# --- UTILIDADES DE TEXTO Y BÚSQUEDA ---
def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    res = str(texto)
    for k, v in replacements.items():
        res = res.replace(k, v)
    return res

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

def calculate_days(date_str):
    if not date_str:
        return 0
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - dt).days
    except:
        return 0

def show_success_alert(msg):
    st.balloons()
    st.toast(msg, icon="🎉")
    st.markdown(f"""
        <div style='background-color: #D4EDDA; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #C3E6CB; text-align: center; margin: 15px 0;'>
            <h4 style='margin:0;'>{msg}</h4>
        </div>
    """, unsafe_allow_html=True)

# --- BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador',
            estado TEXT DEFAULT 'Activo'
        )
    ''')
    
    # Check default admin
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        pass_hash = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, ?)',
                  ('admin', pass_hash, 'Administrador del Sistema', 'Administrador', 'Activo'))

    # 2. Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombres TEXT,
            apellido_paterno TEXT,
            apellido_materno TEXT,
            nombre_completo TEXT,
            fecha_nacimiento TEXT,
            fecha_ingreso TEXT,
            fecha_inicio_etapa TEXT,
            etapa_actual TEXT DEFAULT 'Acogida',
            estado TEXT DEFAULT 'Activo',
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # 3. Ficha de Ingreso
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            sucursal TEXT,
            expediente TEXT,
            fecha_ingreso TEXT,
            hora_ingreso TEXT,
            costo_ingreso REAL,
            cuota_mensual REAL,
            importe_pagare REAL,
            nombres TEXT,
            apellido_paterno TEXT,
            apellido_materno TEXT,
            edad INTEGER,
            fecha_nacimiento TEXT,
            estado_civil TEXT,
            escolaridad TEXT,
            religion TEXT,
            ocupacion TEXT,
            servicio_medico_flag TEXT,
            servicio_medico_inst TEXT,
            calle TEXT,
            numero_ext_int TEXT,
            colonia TEXT,
            municipio TEXT,
            estado_dom TEXT,
            cp TEXT,
            sustancias_json TEXT,
            modalidad TEXT,
            familiar_nombre TEXT,
            familiar_parentesco TEXT,
            familiar_telefono TEXT,
            familiar_email TEXT,
            familiar_domicilio TEXT,
            emergencia_nombre TEXT,
            emergencia_parentesco TEXT,
            emergencia_telefono TEXT,
            fecha_registro TEXT
        )
    ''')

    # 4. Entrevistas Iniciales
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 5. Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            expediente TEXT,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # 6. Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            conductor TEXT,
            pacientes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')

    # 7. Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            stock INTEGER,
            dosis_default TEXT,
            indicaciones TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS entrega_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            horario TEXT,
            usuario TEXT
        )
    ''')

    # 8. Repositorio de Carpetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE
        )
    ''')

    for f in ["Expedientes Clínicos", "Identificaciones", "Estudios Médicos", "Documentos Legales", "Otros"]:
        c.execute('INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (f,))

    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT,
            paciente_id TEXT,
            nombre_archivo TEXT,
            ruta_archivo TEXT,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol, estado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    row = c.fetchone()
    conn.close()
    return row

# --- GENERACIÓN DE PDF: FICHA DE INGRESO ---
class PDF_FichaIngreso(FPDF):
    def header(self):
        self.set_fill_color(27, 94, 32)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, clean_pdf_text("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, clean_pdf_text("FICHA DE INGRESO Y CONTRATO DE ADMISIÓN (NOM-028-SSA2-2009)"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, clean_pdf_text(f"Página {self.page_no()} | Sawabona Shikoba A.C. - Confidencial"), align="C")

def generar_pdf_ficha_ingreso(datos):
    pdf = PDF_FichaIngreso()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"DATOS DE ADMISIÓN | Sucursal: {datos.get('sucursal', 'Matriz Colima')} | Expediente: {datos.get('expediente', '')} | Folio: {datos.get('paciente_id', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Fecha de Ingreso: {datos.get('fecha_ingreso', '')} | Hora: {datos.get('hora_ingreso', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Residente
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS DEL RESIDENTE"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    nom_comp = f"{datos.get('nombres', '')} {datos.get('apellido_paterno', '')} {datos.get('apellido_materno', '')}".strip()
    pdf.cell(0, 5, clean_pdf_text(f"Nombre Completo: {nom_comp}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Edad: {datos.get('edad', '')} años | Fecha Nacimiento: {datos.get('fecha_nacimiento', '')} | Estado Civil: {datos.get('estado_civil', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Escolaridad: {datos.get('escolaridad', '')} | Religión: {datos.get('religion', '')} | Ocupación: {datos.get('ocupacion', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Servicio Médico: {datos.get('servicio_medico_flag', 'NO')} ({datos.get('servicio_medico_inst', '')})"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio: {datos.get('calle', '')} {datos.get('numero_ext_int', '')}, Col. {datos.get('colonia', '')}, {datos.get('municipio', '')}, {datos.get('estado_dom', '')} C.P. {datos.get('cp', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Sustancias
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. SUSTANCIAS QUE CONSUME AL INGRESAR"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    susts = datos.get("sustancias", [])
    sust_str = ", ".join(susts) if susts else "Ninguna especificada"
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sustancias seleccionadas: {sust_str}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Modalidad de Internamiento: {datos.get('modalidad', 'Voluntaria')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Responsable
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. RESPONSABLE FAMILIAR Y EMERGENCIA"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Responsable Familiar: {datos.get('familiar_nombre', '')} ({datos.get('familiar_parentesco', '')})"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Teléfono: {datos.get('familiar_telefono', '')} | Email: {datos.get('familiar_email', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio Responsable: {datos.get('familiar_domicilio', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Contacto Emergencia: {datos.get('emergencia_nombre', '')} ({datos.get('emergencia_parentesco', '')}) - Tel: {datos.get('emergencia_telefono', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Acuerdo Financiero
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("4. ACUERDO FINANCIERO Y COMPROMISOS (NOM-028-SSA2-2009)"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, clean_pdf_text(f"Costo de Ingreso: ${datos.get('costo_ingreso', 4500):,.2f} | Cuota Mensual: ${datos.get('cuota_mensual', 6000):,.2f} | Pagaré: ${datos.get('importe_pagare', 42000):,.2f}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 4, clean_pdf_text("El tratamiento residencial tiene una duración sugerida de 6 a 8 meses (mínimo legal obligatorio de 7 meses según NOM-028-SSA2-2009). Se requiere el uso del uniforme oficial por etapas. La institución garantiza un trato digno, profesional y confidencial."), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    # Firmas
    pdf.set_font("Helvetica", "B", 9)
    col_w = (pdf.epw - 10) / 3
    y_curr = pdf.get_y()
    pdf.line(10, y_curr, 10 + col_w, y_curr)
    pdf.line(15 + col_w, y_curr, 15 + 2*col_w, y_curr)
    pdf.line(20 + 2*col_w, y_curr, 20 + 3*col_w, y_curr)
    
    pdf.cell(col_w, 4, clean_pdf_text("Firma del Responsable Familiar"), align="C")
    pdf.cell(5)
    pdf.cell(col_w, 4, clean_pdf_text("Firma del Residente"), align="C")
    pdf.cell(5)
    pdf.cell(col_w, 4, clean_pdf_text("Dirección del Establecimiento"), align="C")
    
    return bytes(pdf.output())

# --- GENERACIÓN DE PDF: CONSEJERÍA ---
def generar_pdf_consejeria(paciente_id, datos_cons):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, clean_pdf_text("HOJA DE CONSEJERÍA CLINICA INDIVIDUAL"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"Residente Folio: {paciente_id} | Consejería #{datos_cons.get('num_consejeria', 1)} | Etapa: {datos_cons.get('etapa', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, clean_pdf_text(f"Fecha: {datos_cons.get('fecha', '')} | Atendido por: {datos_cons.get('usuario', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("1. EXPOSICIÓN DEL PACIENTE"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(datos_cons.get("exposicion", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. AVANCE / RETROCESO OBSERVADO"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(datos_cons.get("avance", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. SUGERENCIAS Y RECOMENDACIONES"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(datos_cons.get("sugerencia", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"Aspectos para próxima sesión ({datos_cons.get('fecha_proxima', '')}):"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(datos_cons.get("aspectos_proxima", "")), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())

# --- PROGRAMA PRINCIPAL ---
def main():
    init_db()

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

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()

    if st.session_state["logged_in"]:
        inactivo = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
        if inactivo > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        st.session_state["ultima_actividad"] = datetime.now()

    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión de Personal")
        col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
        with col_l2:
            with st.form("login_form"):
                user = st.text_input("Usuario")
                pwd = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                if submit:
                    res = verificar_login(user, pwd)
                    if res:
                        if res[3] == 'Bloqueado':
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = res[0]
                            st.session_state["nombre_completo"] = res[1]
                            st.session_state["rol"] = res[2]
                            st.session_state["ultima_actividad"] = datetime.now()
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
            st.info("💡 **Credenciales Administrador**: Usuario: `admin` | Contraseña: `admin123`")
        return

    st.sidebar.markdown("""
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica</p>
        </div>
    """, unsafe_allow_html=True)

    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.write(f"🔑 **Rol**: {st.session_state.get('rol', 'Administrador')}")

    menu = st.sidebar.selectbox(
        "📌 Menú Principal",
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

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # MÓDULO 1: TABLERO GENERAL
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        c.execute("SELECT COUNT(*) FROM pacientes WHERE estado = 'Activo'")
        activos_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pacientes WHERE estado = 'Bloqueado'")
        bloq_cnt = c.fetchone()[0]

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("🟢 Residentes Activos", activos_cnt)
        col_m2.metric("🔴 Residentes Inactivos / Bloqueados", bloq_cnt)
        col_m3.metric("📊 Total de Expedientes", activos_cnt + bloq_cnt)

        st.divider()
        st.subheader("📊 Distribución por Etapas de Tratamiento")
        etapas_lista = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        tabs_e = st.tabs(etapas_lista)

        for i, et in enumerate(etapas_lista):
            with tabs_e[i]:
                c.execute("SELECT paciente_id, expediente, nombre_completo, fecha_ingreso, fecha_inicio_etapa FROM pacientes WHERE etapa_actual = ? AND estado = 'Activo'", (et,))
                pacs_et = c.fetchall()
                st.write(f"**Residentes en {et}:** `{len(pacs_et)}`")
                if pacs_et:
                    for p in pacs_et:
                        d_etapa = calculate_days(p[4])
                        st.info(f"👤 **{p[2]}** | Folio: `{p[0]}` | Exp: `{p[1]}` | Ingreso: `{p[3]}` | ⏳ **Días en Etapa {et}:** `{d_etapa} días`")
                else:
                    st.caption(f"No hay residentes actualmente en la etapa de {et}.")

    # MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Residentes")
        tab_p1, tab_p2, tab_p3 = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Bloqueo y Estado"])

        with tab_p1:
            st.subheader("Captura Basal de Nuevo Residentes")
            c.execute("SELECT COUNT(*) FROM pacientes")
            next_num = c.fetchone()[0] + 1
            auto_folio = f"PAC-{next_num:03d}"

            with st.form("form_nuevo_paciente"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    folio_in = st.text_input("Folio del Paciente", value=auto_folio, disabled=True)
                    expediente_in = st.text_input("Número de Expediente *", value=str(next_num))
                    nombres_in = st.text_input("Nombre(s) *").strip()
                with c2:
                    ap_paterno_in = st.text_input("Apellido Paterno *").strip()
                    ap_materno_in = st.text_input("Apellido Materno").strip()
                    fecha_nac_in = st.date_input("Fecha de Nacimiento", value=date(1995, 1, 1))
                with c3:
                    fecha_ing_in = st.date_input("Fecha de Ingreso a la Institución", value=date.today())
                    fecha_etapa_in = st.date_input("Fecha de Inicio de Etapa Actual", value=date.today())
                    etapa_in = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])

                btn_guardar_p = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                if btn_guardar_p:
                    if not nombres_in or not ap_paterno_in or not expediente_in:
                        st.error("⚠️ El Nombre, Apellido Paterno y Expediente son obligatorios.")
                    else:
                        nom_full = f"{nombres_in} {ap_paterno_in} {ap_materno_in}".strip()
                        c.execute("SELECT paciente_id, expediente FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = LOWER(TRIM(?))", (nom_full,))
                        dup_nom = c.fetchone()
                        c.execute("SELECT paciente_id, nombre_completo FROM pacientes WHERE expediente = ?", (expediente_in,))
                        dup_exp = c.fetchone()

                        if dup_nom:
                            st.error(f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{nom_full}' (Folio: {dup_nom[0]}, Exp: {dup_nom[1]}).")
                        elif dup_exp:
                            st.error(f"⛔ EXPEDIENTE EN USO: El expediente '{expediente_in}' ya pertenece al paciente '{dup_exp[1]}'.")
                        else:
                            f_nac_str = fecha_nac_in.strftime("%Y-%m-%d")
                            f_ing_str = fecha_ing_in.strftime("%Y-%m-%d")
                            f_eta_str = fecha_etapa_in.strftime("%Y-%m-%d")
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('''
                                INSERT INTO pacientes (paciente_id, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa_actual, estado, fecha_registro, usuario_registro)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Activo', ?, ?)
                            ''', (auto_folio, expediente_in, nombres_in, ap_paterno_in, ap_materno_in, nom_full, f_nac_str, f_ing_str, f_eta_str, etapa_in, now_str, st.session_state['username']))
                            conn.commit()
                            show_success_alert(f"✅ ¡Residente {nom_full} registrado exitosamente con Folio {auto_folio}!")
                            st.rerun()

        with tab_p2:
            st.subheader("Edición de Datos de Residentes")
            c.execute("SELECT paciente_id, nombre_completo, expediente FROM pacientes WHERE estado = 'Activo'")
            acts = c.fetchall()
            if not acts:
                st.info("No hay residentes activos para editar.")
            else:
                p_opts = [f"{p[0]} - {p[1]} (Exp: {p[2]})" for p in acts]
                sel_p = st.selectbox("Seleccione Residente a Editar", p_opts)
                p_id_edit = sel_p.split(" - ")[0]
                c.execute("SELECT expediente, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa_actual FROM pacientes WHERE paciente_id = ?", (p_id_edit,))
                p_curr = c.fetchone()
                if p_curr:
                    with st.form("form_edit_paciente"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            exp_ed = st.text_input("Expediente", value=p_curr[0])
                            nom_ed = st.text_input("Nombre(s)", value=p_curr[1])
                        with ce2:
                            app_ed = st.text_input("Apellido Paterno", value=p_curr[2])
                            apm_ed = st.text_input("Apellido Materno", value=p_curr[3])
                        with ce3:
                            fn_val = datetime.strptime(p_curr[4], "%Y-%m-%d").date() if p_curr[4] else date(1995, 1, 1)
                            fi_val = datetime.strptime(p_curr[5], "%Y-%m-%d").date() if p_curr[5] else date.today()
                            fe_val = datetime.strptime(p_curr[6], "%Y-%m-%d").date() if p_curr[6] else date.today()
                            fn_ed = st.date_input("Fecha de Nacimiento", value=fn_val)
                            fi_ed = st.date_input("Fecha de Ingreso", value=fi_val)
                            fe_ed = st.date_input("Fecha Inicio de Etapa", value=fe_val)
                        etapas_opts = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                        et_idx = get_safe_index(etapas_opts, p_curr[7])
                        et_ed = st.selectbox("Etapa Actual", etapas_opts, index=et_idx)
                        btn_update_p = st.form_submit_button("💾 Guardar Cambios de Residente", use_container_width=True)
                        if btn_update_p:
                            nom_full_ed = f"{nom_ed} {app_ed} {apm_ed}".strip()
                            c.execute('''
                                UPDATE pacientes
                                SET expediente = ?, nombres = ?, apellido_paterno = ?, apellido_materno = ?, nombre_completo = ?, fecha_nacimiento = ?, fecha_ingreso = ?, fecha_inicio_etapa = ?, etapa_actual = ?
                                WHERE paciente_id = ?
                            ''', (exp_ed, nom_ed, app_ed, apm_ed, nom_full_ed, fn_ed.strftime("%Y-%m-%d"), fi_ed.strftime("%Y-%m-%d"), fe_ed.strftime("%Y-%m-%d"), et_ed, p_id_edit))
                            conn.commit()
                            show_success_alert(f"✅ ¡Datos del residente {nom_full_ed} actualizados exitosamente!")
                            st.rerun()

        with tab_p3:
            st.subheader("Cambio de Estado y Bloqueo de Residentes")
            c.execute("SELECT paciente_id, nombre_completo, estado FROM pacientes")
            all_p = c.fetchall()
            if all_p:
                p_bloq_opts = [f"{p[0]} - {p[1]} (Estado: {p[2]})" for p in all_p]
                sel_b = st.selectbox("Seleccione Residente", p_bloq_opts)
                p_id_b = sel_b.split(" - ")[0]
                cb1, cb2 = st.columns(2)
                with cb1:
                    if st.button("🔴 Bloquear / Dar de Baja Residente", use_container_width=True):
                        c.execute("UPDATE pacientes SET estado = 'Bloqueado' WHERE paciente_id = ?", (p_id_b,))
                        conn.commit()
                        show_success_alert(f"✅ Residente {p_id_b} cambiado a estado BLOQUEADO/INACTIVO.")
                        st.rerun()
                with cb2:
                    if st.button("🟢 Reactivar Residente", use_container_width=True):
                        c.execute("UPDATE pacientes SET estado = 'Activo' WHERE paciente_id = ?", (p_id_b,))
                        conn.commit()
                        show_success_alert(f"✅ Residente {p_id_b} REACTIVADO exitosamente.")
                        st.rerun()

        st.divider()
        st.subheader("📋 Lista de Residentes Activos Registrados")
        c.execute("SELECT paciente_id, expediente, nombre_completo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa FROM pacientes WHERE estado = 'Activo' ORDER BY fecha_registro DESC")
        acts_list = c.fetchall()
        if acts_list:
            data_tab = []
            for r in acts_list:
                edad_calc = calculate_age(r[3])
                dias_et = calculate_days(r[6])
                data_tab.append({
                    "Folio": r[0], "Expediente": r[1], "Nombre Completo": r[2],
                    "Edad": f"{edad_calc} años", "Fecha Ingreso": r[4], "Etapa Actual": r[5], "Días en Etapa": f"{dias_et} días"
                })
            st.dataframe(data_tab, use_container_width=True)
        else:
            st.info("No hay residentes activos en el sistema.")

    # MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión")
        st.caption("Formato oficial de admisión según NOM-028-SSA2-2009 y Comunidad Terapéutica Sawabona Shikoba A.C.")
        c.execute("SELECT paciente_id, nombre_completo, expediente FROM pacientes WHERE estado = 'Activo'")
        p_activos = c.fetchall()
        if not p_activos:
            st.warning("⚠️ Primero debe registrar al menos un paciente activo.")
        else:
            opts_fi = [f"{p[0]} - {p[1]} (Exp: {p[2]})" for p in p_activos]
            sel_fi = st.selectbox("🔑 Seleccione Residente para Ficha de Ingreso *", opts_fi)
            p_id_fi = sel_fi.split(" - ")[0]
            c.execute("SELECT expediente, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, fecha_ingreso FROM pacientes WHERE paciente_id = ?", (p_id_fi,))
            p_base = c.fetchone()
            c.execute("SELECT * FROM ficha_ingreso WHERE paciente_id = ?", (p_id_fi,))
            f_exist = c.fetchone()

            with st.form("form_ficha_ingreso"):
                f_tab1, f_tab2, f_tab3, f_tab4, f_tab5 = st.tabs([
                    "1. Admisión y Sucursal", "2. Datos del Residente", "3. Sustancias de Consumo", "4. Responsables y Emergencia", "5. Acuerdo Financiero y NOM-028"
                ])
                with f_tab1:
                    st.subheader("Datos de Admisión Institucional")
                    cf1, cf2, cf3 = st.columns(3)
                    with cf1:
                        sucursal = st.selectbox("Sucursal a Referir", ["Matriz Colima", "Sucursal Guadalajara", "Sucursal Manzanillo"], index=0)
                        expediente_f = st.text_input("No. de Expediente", value=p_base[0] if p_base else "")
                    with cf2:
                        fecha_ing_f = st.date_input("Fecha de Ingreso", value=datetime.strptime(p_base[5], "%Y-%m-%d").date() if p_base and p_base[5] else date.today())
                        hora_ing_f = st.time_input("Hora de Ingreso", value=datetime.now().time())
                    with cf3:
                        costo_ingreso = st.number_input("Costo de Ingreso ($)", value=4500.0, step=100.0)
                        cuota_mensual = st.number_input("Cuota Mensual ($)", value=6000.0, step=100.0)
                        importe_pagare = st.number_input("Importe Pagaré ($)", value=42000.0, step=500.0)

                with f_tab2:
                    st.subheader("Datos Basales del Residente")
                    cr1, cr2, cr3 = st.columns(3)
                    with cr1:
                        nombres_f = st.text_input("Nombre(s)", value=p_base[1] if p_base else "")
                        ap_pat_f = st.text_input("Apellido Paterno", value=p_base[2] if p_base else "")
                        ap_mat_f = st.text_input("Apellido Materno", value=p_base[3] if p_base else "")
                    with cr2:
                        fn_val_f = datetime.strptime(p_base[4], "%Y-%m-%d").date() if p_base and p_base[4] else date(1995, 1, 1)
                        fn_f = st.date_input("Fecha de Nacimiento", value=fn_val_f)
                        edad_calc_f = calculate_age(fn_f.strftime("%Y-%m-%d"))
                        st.write(f"**Edad calculada:** `{edad_calc_f} años`")
                        estado_civil_f = st.selectbox("Estado Civil", ["Soltero/a", "Casado/a", "Unión Libre", "Divorciado/a", "Viudo/a"])
                    with cr3:
                        escolaridad_f = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria / Bachillerato", "Licenciatura", "Postgrado", "Ninguna"])
                        religion_f = st.text_input("Religión", value="Católica")
                        ocupacion_f = st.text_input("Ocupación", value="Empleado/a")
                    st.divider()
                    st.subheader("Servicios Médicos y Domicilio")
                    cm1, cm2 = st.columns(2)
                    with cm1:
                        serv_med_flag = st.selectbox("¿Cuenta con Servicio Médico?", ["NO", "SÍ"])
                        serv_med_inst = st.text_input("Institución (IMSS, ISSSTE, INSABI, Particular)", value="INSABI")
                    with cm2:
                        calle_f = st.text_input("Calle y Número Ext/Int")
                        colonia_f = st.text_input("Colonia / Población")
                    cd1, cd2, cd3 = st.columns(3)
                    with cd1:
                        municipio_f = st.text_input("Municipio", value="Colima")
                    with cd2:
                        estado_dom_f = st.text_input("Estado", value="Colima")
                    with cd3:
                        cp_f = st.text_input("Código Postal", value="28000")

                with f_tab3:
                    st.subheader("Sustancias que Consume al Ingresar")
                    cat_sust = ["Alcaloides", "Alcohol", "Anfetaminas", "Benzodiazepinas", "Cannabis / Marihuana", "Esteroides", "Fármacos", "LSD / Alucinógenos", "Meta-anfetaminas / Cristal", "Opiáceos", "Sustancias Psicoactivas", "Solventes e Inhalables", "Tabaco"]
                    selected_susts = []
                    cols_s = st.columns(3)
                    for idx_s, s_item in enumerate(cat_sust):
                        with cols_s[idx_s % 3]:
                            if st.checkbox(s_item, key=f"fi_s_{idx_s}"):
                                selected_susts.append(s_item)
                    st.divider()
                    modalidad_f = st.selectbox("Modalidad de Internamiento", ["Voluntaria (Por convicción del residente)", "Involuntaria (A solicitud del responsable familiar)"])

                with f_tab4:
                    st.subheader("Datos del Responsable Familiar")
                    crf1, crf2 = st.columns(2)
                    with crf1:
                        fam_nombre = st.text_input("Nombre Completo del Responsable Familiar *")
                        fam_parentesco = st.text_input("Parentesco (Desea internar a su...)", value="Padre / Madre / Cónyuge")
                    with crf2:
                        fam_tel = st.text_input("Teléfono(s) de Contacto *")
                        fam_email = st.text_input("Correo Electrónico")
                    fam_dom = st.text_area("Domicilio Completo del Responsable Familiar")
                    st.divider()
                    st.subheader("Contacto Secundario de Emergencia")
                    cre1, cre2, cre3 = st.columns(3)
                    with cre1:
                        emerg_nombre = st.text_input("Nombre de Emergencia")
                    with cre2:
                        emerg_parentesco = st.text_input("Parentesco Emergencia")
                    with cre3:
                        emerg_tel = st.text_input("Teléfono Emergencia")

                with f_tab5:
                    st.subheader("Acuerdo y Políticas NOM-028-SSA2-2009")
                    st.info("""
                        📌 **Puntos Clave del Contrato de Admisión:**
                        * **Tratamiento Sugerido**: De 6 a 8 meses. Tiempo mínimo obligatorio legal: 7 meses conforme a NOM-028-SSA2-2009.
                        * **Uniformes Obligatorios por Etapa**: Playeras correspondientes (Acogida - Roja, Identificación - Naranja, Elaboración - Morada, Consolidación - Azul Turquesa, Servicio Social - Verde).
                        * **Pagaré de Garantía**: Firma del pagaré por $42,000.00 M.N. como respaldo de la estancia.
                        * **Derechos y Dignidad**: Se garantiza la seguridad médica, psicológica y trato digno sin violencia.
                    """)

                btn_guardar_fi = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                if btn_guardar_fi:
                    if not fam_nombre or not fam_tel:
                        st.error("⚠️ El Nombre y Teléfono del Responsable Familiar son obligatorios.")
                    else:
                        sust_json = json.dumps(selected_susts, ensure_ascii=False)
                        f_ing_str_f = fecha_ing_f.strftime("%Y-%m-%d")
                        h_ing_str_f = hora_ing_f.strftime("%H:%M:%S")
                        now_f = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute('''
                            INSERT OR REPLACE INTO ficha_ingreso
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            p_id_fi, sucursal, expediente_f, f_ing_str_f, h_ing_str_f, costo_ingreso, cuota_mensual, importe_pagare,
                            nombres_f, ap_pat_f, ap_mat_f, edad_calc_f, fn_f.strftime("%Y-%m-%d"), estado_civil_f, escolaridad_f, religion_f, ocupacion_f,
                            serv_med_flag, serv_med_inst, calle_f, colonia_f, municipio_f, estado_dom_f, cp_f,
                            sust_json, modalidad_f, fam_nombre, fam_parentesco, fam_tel, fam_email, fam_dom,
                            emerg_nombre, emerg_parentesco, emerg_tel, now_f, calle_f + " " + colonia_f
                        ))
                        conn.commit()
                        show_success_alert(f"✅ ¡Ficha de Ingreso para {sel_fi} guardada exitosamente!")
                        st.rerun()
            if f_exist:
                st.divider()
                st.subheader("🖨️ Generación de Documento Impreso Oficial")
                datos_pdf_fi = {
                    "paciente_id": f_exist[0], "sucursal": f_exist[1], "expediente": f_exist[2], "fecha_ingreso": f_exist[3], "hora_ingreso": f_exist[4],
                    "costo_ingreso": f_exist[5], "cuota_mensual": f_exist[6], "importe_pagare": f_exist[7], "nombres": f_exist[8], "apellido_paterno": f_exist[9],
                    "apellido_materno": f_exist[10], "edad": f_exist[11], "fecha_nacimiento": f_exist[12], "estado_civil": f_exist[13], "escolaridad": f_exist[14],
                    "religion": f_exist[15], "ocupacion": f_exist[16], "servicio_medico_flag": f_exist[17], "servicio_medico_inst": f_exist[18], "calle": f_exist[19],
                    "numero_ext_int": "", "colonia": f_exist[20], "municipio": f_exist[21], "estado_dom": f_exist[22], "cp": f_exist[23],
                    "sustancias": json.loads(f_exist[24]) if f_exist[24] else [], "modalidad": f_exist[25], "familiar_nombre": f_exist[26], "familiar_parentesco": f_exist[27],
                    "familiar_telefono": f_exist[28], "familiar_email": f_exist[29], "familiar_domicilio": f_exist[30], "emergencia_nombre": f_exist[31],
                    "emergencia_parentesco": f_exist[32], "emergencia_telefono": f_exist[33]
                }
                pdf_bytes_fi = generar_pdf_ficha_ingreso(datos_pdf_fi)
                st.download_button(
                    label="📄 Descargar Ficha de Ingreso Oficial en PDF (Imprimible)",
                    data=pdf_bytes_fi,
                    file_name=f"Ficha_Ingreso_{p_id_fi}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    # MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Evaluación basal clínica de consumo de sustancias y disposición al cambio")
        c.execute("SELECT paciente_id, nombre_completo, expediente FROM pacientes WHERE estado = 'Activo'")
        p_activos_e = c.fetchall()
        if not p_activos_e:
            st.warning("⚠️ Primero debe registrar al menos un paciente activo.")
        else:
            opts_ei = [f"{p[0]} - {p[1]} (Exp: {p[2]})" for p in p_activos_e]
            sel_ei = st.selectbox("🔑 Seleccione Residente *", opts_ei)
            p_id_ei = sel_ei.split(" - ")[0]
            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (p_id_ei,))
            row_e = c.fetchone()
            d_ei = json.loads(row_e[0]) if row_e else {}
            with st.form("form_entrevista_inicial"):
                etab1, etab2, etab3, etab4, etab5 = st.tabs([
                    "1. Datos Generales", "2. Consumo de Sustancias", "3. Disposición al Cambio", "4. Entorno y Riesgos", "5. Observaciones y Firma"
                ])
                with etab1:
                    st.subheader("Datos Socio-Demográficos Basales")
                    c1, c2 = st.columns(2)
                    with c1:
                        dep_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], index=1 if d_ei.get("dependientes_flag") == "SÍ" else 0)
                        dep_quienes = st.text_input("¿Quiénes o quién?", value=d_ei.get("dependientes_quienes", ""))
                    with c2:
                        par_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if d_ei.get("pareja_flag") == "SÍ" else 0)
                        par_tiempo = st.text_input("Tiempo de relación", value=d_ei.get("pareja_tiempo", ""))
                with etab2:
                    st.subheader("Tabla de Consumo de Sustancias")
                    susts_list = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO"]
                    tabla_c_guardada = d_ei.get("tabla_consumo", {})
                    tabla_c_input = {}
                    for s_item in susts_list:
                        st.markdown(f"**{s_item}**")
                        s_d = tabla_c_guardada.get(s_item, {})
                        ca, cb, cc, cd, ce, cf = st.columns([1, 1.5, 1.5, 1.5, 1, 1.5])
                        with ca:
                            c_val = st.checkbox("Consume", value=s_d.get("consumo") == "SÍ", key=f"c_ei_{s_item}")
                        with cb:
                            forma_val = st.text_input("Forma", value=s_d.get("forma", ""), key=f"forma_ei_{s_item}")
                        with cc:
                            frec_val = st.text_input("Frecuencia", value=s_d.get("frecuencia", ""), key=f"frec_ei_{s_item}")
                        with cd:
                            cant_val = st.text_input("Cantidad", value=s_d.get("cantidad", ""), key=f"cant_ei_{s_item}")
                        with ce:
                            edad_val = st.text_input("Edad Inicio", value=s_d.get("edad_inicio", ""), key=f"edad_ei_{s_item}")
                        with cf:
                            lugar_val = st.text_input("Lugar", value=s_d.get("lugar", ""), key=f"lugar_ei_{s_item}")
                        tabla_c_input[s_item] = {
                            "consumo": "SÍ" if c_val else "NO", "forma": forma_val, "frecuencia": frec_val, "cantidad": cant_val, "edad_inicio": edad_val, "lugar": lugar_val
                        }
                        st.divider()
                    st.subheader("Sustancia de Impacto Principal")
                    ci1, ci2, ci3 = st.columns(3)
                    with ci1:
                        sust_imp = st.text_input("Sustancia de Impacto", value=d_ei.get("sustancia_impacto", ""))
                    with ci2:
                        t_excesivo = st.text_input("¿Tiempo de consumo excesivo?", value=d_ei.get("tiempo_excesivo", ""))
                    with ci3:
                        mod_cons_opts = ["Sin registrar", "SOLO", "ACOMPAÑADO", "AMBOS"]
                        mod_idx = get_safe_index(mod_cons_opts, d_ei.get("modo_consumo"))
                        modo_cons = st.selectbox("Normalmente consume", mod_cons_opts, index=mod_idx)
                with etab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor = st.text_area("Mayor periodo de abstinencia logrado", value=d_ei.get("abst_mayor_tiempo", ""))
                    abst_f = st.text_input("¿Cuándo ocurrió?", value=d_ei.get("abst_fecha", ""))
                    abst_mot = st.text_area("Motivo / Estrategia de abstinencia", value=d_ei.get("abst_motivo", ""))
                    abst_6m = st.text_area("Abstinencia en los últimos 6 meses", value=d_ei.get("abst_6meses", ""))
                    imp_opts = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_idx = get_safe_index(imp_opts, d_ei.get("importancia_cambio"), default=2)
                    importancia_c = st.select_slider("Importancia de dejar de consumir", options=imp_opts, value=imp_opts[imp_idx])
                with etab4:
                    st.subheader("Situación Social y Factores de Riesgo")
                    fam_integ = st.text_area("Integrantes de la familia con mayor contacto", value=d_ei.get("familia_integrantes", ""))
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        rel_post = st.selectbox("¿Relaciones sexuales tras consumir?", ["NO", "SÍ"], index=1 if d_ei.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_fl = st.selectbox("¿Involucrado en abuso físico/sexual?", ["NO", "SÍ"], index=1 if d_ei.get("abuso_flag") == "SÍ" else 0)
                with etab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    prob_sesion = st.text_area("Problemas durante la sesión", value=d_ei.get("problemas_sesion", ""))
                    obs_gen = st.text_area("Observaciones generales", value=d_ei.get("observaciones", ""))
                    cf1, cf2 = st.columns(2)
                    with cf1:
                        eval_nom = st.text_input("Nombre de quien aplica", value=d_ei.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with cf2:
                        eval_cargo = st.text_input("Cargo del evaluador", value=d_ei.get("evaluador_cargo", "Consejero Clínico"))
                btn_save_ei = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ei:
                    d_ei_completos = {
                        "dependientes_flag": dep_flag, "dependientes_quienes": dep_quienes, "pareja_flag": par_flag, "pareja_tiempo": par_tiempo,
                        "tabla_consumo": tabla_c_input, "sustancia_impacto": sust_imp, "tiempo_excesivo": t_excesivo, "modo_consumo": modo_cons,
                        "abst_mayor_tiempo": abst_mayor, "abst_fecha": abst_f, "abst_motivo": abst_mot, "abst_6meses": abst_6m,
                        "importancia_cambio": importancia_c, "familia_integrantes": fam_integ, "relaciones_post_consumo": rel_post,
                        "abuso_flag": abuso_fl, "problemas_sesion": prob_sesion, "observaciones": obs_gen, "evaluador_nombre": eval_nom, "evaluador_cargo": eval_cargo
                    }
                    now_ei = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    d_json_str = json.dumps(d_ei_completos, ensure_ascii=False)
                    c.execute("INSERT OR REPLACE INTO entrevistas VALUES (?, ?, ?, ?, ?)", (p_id_ei, now_ei, now_ei, st.session_state['username'], d_json_str))
                    conn.commit()
                    show_success_alert(f"✅ ¡Entrevista Inicial para {sel_ei} guardada exitosamente!")
                    st.rerun()
    # MÓDULO 5: CONSEJERÍAS INDIVIDUALES
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Hojas de Consejería Individual")
        c.execute("SELECT paciente_id, nombre_completo, etapa_actual, expediente FROM pacientes WHERE estado = 'Activo'")
        p_act_cons = c.fetchall()
        if not p_act_cons:
            st.warning("⚠️ No hay pacientes activos registrados.")
        else:
            opts_co = [f"{p[0]} - {p[1]} (Etapa: {p[2]})" for p in p_act_cons]
            sel_co = st.selectbox("🔑 Seleccione Residente", opts_co)
            p_id_co = sel_co.split(" - ")[0]
            c.execute("SELECT etapa_actual, expediente FROM pacientes WHERE paciente_id = ?", (p_id_co,))
            p_info_co = c.fetchone()
            etapa_curr = p_info_co[0]
            exp_curr = p_info_co[1]
            col_num, col_info = st.columns([1, 2])
            with col_num:
                num_cons = st.selectbox("Número de Consejería", list(range(1, 11)), index=0)
            with col_info:
                st.info(f"📍 **Etapa Actual:** `{etapa_curr}` | **Expediente:** `{exp_curr}`")
            c.execute("SELECT exposicion, avance, sugerencia, aspectos_proxima, fecha_proxima FROM consejerias WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?", (p_id_co, etapa_curr, num_cons))
            cons_saved = c.fetchone()
            exp_val = cons_saved[0] if cons_saved else ""
            ava_val = cons_saved[1] if cons_saved else ""
            sug_val = cons_saved[2] if cons_saved else ""
            asp_val = cons_saved[3] if cons_saved else ""
            f_prox_val = cons_saved[4] if cons_saved else (date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            with st.form("form_consejeria_ind"):
                exposicion_input = st.text_area("1. Exposición del Paciente (Temas planteados por el residente)", value=exp_val, height=120)
                avance_input = st.text_area("2. Avance / Retroceso Observado (Evaluación clínica de la sesión)", value=ava_val, height=120)
                sugerencia_input = st.text_area("3. Sugerencias y Recomendaciones Dadas", value=sug_val, height=120)
                cc1, cc2 = st.columns(2)
                with cc1:
                    aspectos_prox_input = st.text_area("Aspectos para próxima sesión", value=asp_val)
                with cc2:
                    fecha_prox_input = st.date_input("Fecha sugerida próxima sesión", value=datetime.strptime(f_prox_val[:10], "%Y-%m-%d").date() if f_prox_val else date.today())
                btn_save_co = st.form_submit_button("💾 Guardar Hoja de Consejería", use_container_width=True)
                if btn_save_co:
                    now_co = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f_prox_str = fecha_prox_input.strftime("%Y-%m-%d")
                    c.execute('''
                        INSERT INTO consejerias (paciente_id, etapa, num_consejeria, expediente, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p_id_co, etapa_curr, num_cons, exp_curr, "Consejería rutinaria", aspectos_prox_input, f_prox_str, exposicion_input, avance_input, sugerencia_input, now_co, st.session_state['username']))
                    conn.commit()
                    show_success_alert(f"✅ ¡Consejería #{num_cons} para {sel_co} guardada exitosamente!")
                    st.rerun()
            if cons_saved:
                st.divider()
                d_pdf_co = {
                    "num_consejeria": num_cons, "etapa": etapa_curr, "fecha": datetime.now().strftime("%Y-%m-%d"),
                    "usuario": st.session_state['nombre_completo'], "exposicion": exp_val, "avance": ava_val,
                    "sugerencia": sug_val, "aspectos_proxima": asp_val, "fecha_proxima": f_prox_val
                }
                pdf_co_bytes = generar_pdf_consejeria(p_id_co, d_pdf_co)
                st.download_button("🖨️ Descargar Hoja de Consejería en PDF", data=pdf_co_bytes, file_name=f"Consejeria_{p_id_co}_#_{num_cons}.pdf", mime="application/pdf")
    # MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Promoción Clínica")
        c.execute("SELECT paciente_id, nombre_completo, etapa_actual, fecha_inicio_etapa FROM pacientes WHERE estado = 'Activo'")
        p_etapas = c.fetchall()
        if not p_etapas:
            st.info("No hay residentes activos registrados.")
        else:
            opts_prom = [f"{p[0]} - {p[1]} (Etapa: {p[2]})" for p in p_etapas]
            sel_prom = st.selectbox("Seleccione Residente para Evaluar Promoción", opts_prom)
            p_id_prom = sel_prom.split(" - ")[0]
            c.execute("SELECT nombre_completo, etapa_actual, fecha_inicio_etapa, expediente FROM pacientes WHERE paciente_id = ?", (p_id_prom,))
            p_pr = c.fetchone()
            st.subheader(f"Residente: **{p_pr[0]}** | Expediente: `{p_pr[3]}`")
            dias_etapa_pr = calculate_days(p_pr[2])
            col_p1, col_p2 = st.columns(2)
            col_p1.metric("Etapa Actual", p_pr[1])
            col_p2.metric("Días en Etapa Actual", f"{dias_etapa_pr} días")
            if dias_etapa_pr > 90:
                st.warning("⚠️ **Alerta de Rezago Clínico**: El residente supera los 90 días en la etapa actual. Se sugiere revisión en equipo interdisciplinario.")
            st.divider()
            st.subheader("Promover de Etapa")
            etapas_orden = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
            curr_idx = etapas_orden.index(p_pr[1]) if p_pr[1] in etapas_orden else 0
            if curr_idx < len(etapas_orden) - 1:
                next_etapa = etapas_orden[curr_idx + 1]
                st.write(f"Siguiente etapa sugerida: **{next_etapa}**")
                if st.button(f"🚀 Promover Residente a '{next_etapa}'", use_container_width=True):
                    today_str = date.today().strftime("%Y-%m-%d")
                    c.execute("UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?", (next_etapa, today_str, p_id_prom))
                    conn.commit()
                    show_success_alert(f"🎉 ¡Residente {p_pr[0]} promovido con éxito a la etapa '{next_etapa}'!")
                    st.rerun()
            else:
                st.success("🎓 El residente se encuentra en la etapa final ('Servicio Social').")
    # MÓDULO 7: GRUPOS TERAPÉUTICOS
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Sesiones de Grupos Terapéuticos")
        with st.form("form_grupo_terapeutico"):
            cg1, cg2 = st.columns(2)
            with cg1:
                fecha_grupo = st.date_input("Fecha del Grupo", value=date.today())
                tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo Interpersonal", "Grupo Aquí y Ahora", "Feedback e Integración", "Prevención de Recaídas", "Estudio de Pasos"])
            with cg2:
                tema_grupo = st.text_input("Tema Tratar en la Sesión *")
                conductor_grupo = st.text_input("Conductor / Facilitador", value=st.session_state['nombre_completo'])
            c.execute("SELECT paciente_id, nombre_completo FROM pacientes WHERE estado = 'Activo'")
            acts_g = c.fetchall()
            pacs_asistentes = []
            st.subheader("Asistencia de Residentes")
            if acts_g:
                cols_g = st.columns(3)
                for idx_g, pg in enumerate(acts_g):
                    with cols_g[idx_g % 3]:
                        if st.checkbox(f"{pg[1]} ({pg[0]})", key=f"g_asist_{pg[0]}"):
                            pacs_asistentes.append(pg[0])
            obs_grupo = st.text_area("Observaciones y Dinámica del Grupo")
            btn_save_g = st.form_submit_button("💾 Guardar Sesión Grupal", use_container_width=True)
            if btn_save_g:
                if not tema_grupo:
                    st.error("⚠️ El tema de la sesión es obligatorio.")
                else:
                    now_g = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f_g_str = fecha_grupo.strftime("%Y-%m-%d")
                    p_json_g = json.dumps(pacs_asistentes, ensure_ascii=False)
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (fecha, tipo_grupo, tema, conductor, pacientes_json, observaciones, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (f_g_str, tipo_grupo, tema_grupo, conductor_grupo, p_json_g, obs_grupo, st.session_state['username']))
                    conn.commit()
                    show_success_alert("✅ ¡Sesión de Grupo Terapéutico registrada exitosamente!")
                    st.rerun()
    # MÓDULO 8: CONTROL DE MEDICAMENTOS
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Inventario y Suministro de Medicamentos")
        m_tab1, m_tab2 = st.tabs(["📦 Inventario de Medicamentos", "💊 Suministro a Residentes"])
        with m_tab1:
            st.subheader("Catálogo e Inventario de Fármacos")
            with st.form("form_med_inv"):
                cm1, cm2, cm3 = st.columns(3)
                with cm1:
                    nom_med = st.text_input("Nombre del Medicamento / Fármaco *")
                with cm2:
                    stock_med = st.number_input("Cantidad Inicial en Stock", min_value=0, value=50)
                with cm3:
                    dosis_med = st.text_input("Dosis Habitual (ej. 500mg, 1 tab)")
                indic_med = st.text_area("Indicaciones / Contraindicaciones")
                btn_save_med = st.form_submit_button("➕ Agregar al Inventario", use_container_width=True)
                if btn_save_med:
                    if not nom_med:
                        st.error("⚠️ El nombre del medicamento es obligatorio.")
                    else:
                        c.execute("INSERT OR REPLACE INTO medicamentos (nombre, stock, dosis_default, indicaciones) VALUES (?, ?, ?, ?)", (nom_med, stock_med, dosis_med, indic_med))
                        conn.commit()
                        show_success_alert(f"✅ Medicamento '{nom_med}' agregado al inventario.")
                        st.rerun()
            st.divider()
            c.execute("SELECT id, nombre, stock, dosis_default, indicaciones FROM medicamentos")
            meds = c.fetchall()
            if meds:
                st.subheader("Inventario Actual")
                med_data = [{"ID": m[0], "Medicamento": m[1], "Stock Disponible": m[2], "Dosis Sugerida": m[3], "Indicaciones": m[4]} for m in meds]
                st.dataframe(med_data, use_container_width=True)
        with m_tab2:
            st.subheader("Registro de Suministro de Medicamento")
            c.execute("SELECT id, nombre, stock FROM medicamentos WHERE stock > 0")
            meds_avail = c.fetchall()
            c.execute("SELECT paciente_id, nombre_completo FROM pacientes WHERE estado = 'Activo'")
            pacs_med = c.fetchall()
            if not meds_avail or not pacs_med:
                st.info("Asegúrese de tener medicamentos en stock y residentes activos.")
            else:
                with st.form("form_suministro_med"):
                    m_opts = [f"{m[0]} - {m[1]} (Stock: {m[2]})" for m in meds_avail]
                    p_opts_m = [f"{p[0]} - {p[1]}" for p in pacs_med]
                    sel_m = st.selectbox("Seleccione Medicamento", m_opts)
                    sel_pm = st.selectbox("Seleccione Residente", p_opts_m)
                    cant_med = st.number_input("Cantidad a Suministrar", min_value=1, value=1)
                    horario_med = st.text_input("Horario / Turno (ej. 08:00 AM - Mañana)", value="08:00 AM")
                    btn_sum_med = st.form_submit_button("💊 Registrar Suministro", use_container_width=True)
                    if btn_sum_med:
                        med_id = int(sel_m.split(" - ")[0])
                        p_id_m = sel_pm.split(" - ")[0]
                        c.execute("UPDATE medicamentos SET stock = stock - ? WHERE id = ?", (cant_med, med_id))
                        now_m = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute("INSERT INTO entrega_medicamentos (fecha, paciente_id, medicamento_id, cantidad, horario, usuario) VALUES (?, ?, ?, ?, ?, ?)", (now_m, p_id_m, med_id, cant_med, horario_med, st.session_state['username']))
                        conn.commit()
                        show_success_alert("✅ Suministro de medicamento registrado e inventario descontado.")
                        st.rerun()
    # MÓDULO 9: REPOSITORIO DE DOCUMENTOS
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital y Gestión de Carpetas")
        rep_tab1, rep_tab2 = st.tabs(["📄 Subir y Consultar Documentos", "⚙️ Gestión de Carpetas"])
        with rep_tab1:
            st.subheader("Subir Documento al Repositorio")
            c.execute("SELECT nombre_carpeta FROM repositorio_carpetas")
            carps = [r[0] for r in c.fetchall()]
            c.execute("SELECT paciente_id, nombre_completo FROM pacientes")
            pacs_rep = c.fetchall()
            with st.form("form_subir_doc"):
                cr_a, cr_b = st.columns(2)
                with cr_a:
                    sel_carp = st.selectbox("Carpeta Destino", carps)
                with cr_b:
                    opts_pr = ["General / Sin Residente"] + [f"{p[0]} - {p[1]}" for p in pacs_rep]
                    sel_pr = st.selectbox("Residente Asociado", opts_pr)
                up_file = st.file_uploader("Seleccione Archivo (PDF, PNG, JPG, DOCX)", type=["pdf", "png", "jpg", "jpeg", "docx"])
                btn_up = st.form_submit_button("📤 Subir Archivo", use_container_width=True)
                if btn_up and up_file:
                    os.makedirs("uploads", exist_ok=True)
                    f_path = os.path.join("uploads", up_file.name)
                    with open(f_path, "wb") as f_out:
                        f_out.write(up_file.getbuffer())
                    p_assoc = sel_pr.split(" - ")[0] if " - " in sel_pr else "GENERAL"
                    now_r = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO repositorio_archivos (carpeta, paciente_id, nombre_archivo, ruta_archivo, fecha, usuario) VALUES (?, ?, ?, ?, ?, ?)", (sel_carp, p_assoc, up_file.name, f_path, now_r, st.session_state['username']))
                    conn.commit()
                    show_success_alert(f"✅ Archivo '{up_file.name}' subido a la carpeta '{sel_carp}'.")
                    st.rerun()
            st.divider()
            st.subheader("Documentos Guardados")
            c.execute("SELECT id, carpeta, paciente_id, nombre_archivo, fecha FROM repositorio_archivos ORDER BY id DESC")
            docs_list = c.fetchall()
            if docs_list:
                d_tab = [{"ID": d[0], "Carpeta": d[1], "Residente": d[2], "Archivo": d[3], "Fecha Subida": d[4]} for d in docs_list]
                st.dataframe(d_tab, use_container_width=True)
        with rep_tab2:
            st.subheader("Administración de Carpetas")
            c1_c, c2_c = st.columns(2)
            with c1_c:
                st.markdown("**➕ Crear Nueva Carpeta**")
                new_carp_name = st.text_input("Nombre de la Nueva Carpeta")
                if st.button("Crear Carpeta", use_container_width=True):
                    if new_carp_name:
                        c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (new_carp_name.strip(),))
                        conn.commit()
                        show_success_alert(f"✅ Carpeta '{new_carp_name}' creada exitosamente.")
                        st.rerun()
            with c2_c:
                st.markdown("**✏️ Renombrar Carpeta Existente**")
                c.execute("SELECT nombre_carpeta FROM repositorio_carpetas")
                cur_carps = [r[0] for r in c.fetchall()]
                old_c = st.selectbox("Seleccione Carpeta a Renombrar", cur_carps)
                ren_c = st.text_input("Nuevo Nombre de Carpeta")
                if st.button("Renombrar Carpeta", use_container_width=True):
                    if ren_c:
                        c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (ren_c.strip(), old_c))
                        c.execute("UPDATE repositorio_archivos SET carpeta = ? WHERE carpeta = ?", (ren_c.strip(), old_c))
                        conn.commit()
                        show_success_alert(f"✅ Carpeta renombrada de '{old_c}' a '{ren_c}'.")
                        st.rerun()
    # MÓDULO 10: BUSCAR Y LISTAR PACIENTES
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Residentes")
        search_query = st.text_input("🔎 Buscar por Nombre, Folio o Expediente").strip().lower()
        filtro_estado = st.radio("Filtrar por Estado", ["Todos", "🟢 Activos", "🔴 Bloqueados"], horizontal=True)
        query = "SELECT paciente_id, expediente, nombre_completo, fecha_nacimiento, fecha_ingreso, etapa_actual, estado FROM pacientes"
        conds = []
        params = []
        if filtro_estado == "🟢 Activos":
            conds.append("estado = 'Activo'")
        elif filtro_estado == "🔴 Bloqueados":
            conds.append("estado = 'Bloqueado'")
        if search_query:
            conds.append("(LOWER(nombre_completo) LIKE ? OR LOWER(paciente_id) LIKE ? OR LOWER(expediente) LIKE ?)")
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        if conds:
            query += " WHERE " + " AND ".join(conds)
        c.execute(query, params)
        res_dir = c.fetchall()
        st.subheader(f"Resultados Encontrados: {len(res_dir)}")
        if res_dir:
            for r in res_dir:
                st.info(f"👤 **{r[2]}** | Folio: `{r[0]}` | Exp: `{r[1]}` | Ingreso: `{r[4]}` | Etapa: `{r[5]}` | Estado: `{r[6]}`")
    # MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        tab_sec1, tab_sec2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        with tab_sec1:
            st.subheader("Cambio de Contraseña Personal")
            with st.form("form_cambio_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_n1 = st.text_input("Nueva Contraseña", type="password")
                p_n2 = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p = st.form_submit_button("Actualizar Contraseña")
                if btn_p:
                    if p_n1 != p_n2:
                        st.error("Las nuevas contraseñas no coinciden.")
                    else:
                        ok_u = verificar_login(st.session_state['username'], p_act)
                        if ok_u:
                            new_h = hash_pass(p_n1)
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (new_h, st.session_state['username']))
                            conn.commit()
                            show_success_alert("✅ Contraseña actualizada exitosamente.")
                        else:
                            st.error("Contraseña actual incorrecta.")
        with tab_sec2:
            st.subheader("Alta y Administración de Cuentas de Personal")
            if st.session_state['username'] == 'admin' or st.session_state.get('rol') == 'Administrador':
                with st.form("form_nuevo_usr"):
                    cu1, cu2, cu3 = st.columns(3)
                    with cu1:
                        u_name = st.text_input("Usuario (Login) *")
                        u_pass = st.text_input("Contraseña *", type="password")
                    with cu2:
                        u_full = st.text_input("Nombre Completo *")
                    with cu3:
                        u_rol = st.selectbox("Rol de Acceso", ["Administrador", "Nivel 2 Lectura/Escritura", "Nivel 3 Solo Lectura"])
                    btn_add_u = st.form_submit_button("➕ Registrar Usuario", use_container_width=True)
                    if btn_add_u:
                        if not u_name or not u_pass:
                            st.error("⚠️ Usuario y Contraseña son obligatorios.")
                        else:
                            c.execute("SELECT id FROM usuarios WHERE username = ?", (u_name,))
                            if c.fetchone():
                                st.error("⛔ El nombre de usuario ya existe.")
                            else:
                                pass_h = hash_pass(u_pass)
                                c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, 'Activo')", (u_name, pass_h, u_full, u_rol))
                                conn.commit()
                                show_success_alert(f"✅ Usuario '{u_name}' registrado exitosamente.")
                                st.rerun()
                st.divider()
                st.subheader("Personal Registrado")
                c.execute("SELECT id, username, nombre_completo, rol, estado FROM usuarios")
                usrs = c.fetchall()
                for ru in usrs:
                    col_u1, col_u2 = st.columns([3, 1])
                    with col_u1:
                        st.write(f"👤 **{ru[2]}** (`{ru[1]}`) | Rol: `{ru[3]}` | Estado: `{ru[4]}`")
                    with col_u2:
                        if ru[1] != 'admin':
                            btn_label = "🔴 Bloquear" if ru[4] == 'Activo' else "🟢 Activar"
                            new_st = 'Bloqueado' if ru[4] == 'Activo' else 'Activo'
                            if st.button(btn_label, key=f"btn_u_{ru[0]}"):
                                c.execute("UPDATE usuarios SET estado = ? WHERE id = ?", (new_st, ru[0]))
                                conn.commit()
                                show_success_alert(f"Estado de usuario {ru[1]} cambiado a {new_st}.")
                                st.rerun()
            else:
                st.warning("⚠️ Solo los usuarios administradores pueden gestionar las cuentas del personal.")
    # MÓDULO 12: RESPALDO Y RESTAURACIÓN
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.subheader("1. Descargar Respaldo de Base de Datos")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f_db:
                st.download_button(
                    label="💾 Descargar Copia de Seguridad (.db)",
                    data=f_db,
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
        st.divider()
        st.subheader("2. Restaurar Base de Datos desde Respaldo")
        up_db = st.file_uploader("Seleccione archivo .db para restaurar", type=["db"])
        if up_db:
            if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                with open(DB_FILE, "wb") as f_out_db:
                    f_out_db.write(up_db.getbuffer())
                show_success_alert("✅ Base de datos restaurada exitosamente.")
                st.rerun()
    conn.close()
if __name__ == '__main__':
    main()
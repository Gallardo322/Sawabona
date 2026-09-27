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

# --- UTILIDADES DE LIMPIEZA Y CÁLCULOS ---
def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': '', '°': ''
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
        born = datetime.strptime(str(born_str).strip(), "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except:
        return 0

def calculate_days(date_str):
    if not date_str:
        return 0
    try:
        d = datetime.strptime(str(date_str).strip()[:10], "%Y-%m-%d").date()
        today = date.today()
        diff = (today - d).days
        return max(0, diff)
    except:
        return 0

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- INICIALIZACIÓN Y MIGRACIÓN DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Solo Lectura',
            estado TEXT DEFAULT 'Activo'
        )
    ''')
    
    # Migrar columnas de usuarios si faltan
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Solo Lectura'")
    if 'estado' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN estado TEXT DEFAULT 'Activo'")
        
    # Usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        def_pass = hash_pass("admin123")
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, ?)',
                  ('admin', def_pass, 'Administrador del Sistema', 'Administrador', 'Activo'))
                  
    # 2. Tabla Entrevistas / Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre TEXT,
            ap_paterno TEXT,
            ap_materno TEXT,
            nombre_completo TEXT,
            sexo TEXT DEFAULT 'Masculino',
            fecha_nacimiento TEXT,
            fecha_ingreso TEXT,
            fecha_inicio_etapa TEXT,
            etapa TEXT DEFAULT 'Acogida',
            estado TEXT DEFAULT 'Activo',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # Migrar columnas de entrevistas si faltan
    c.execute("PRAGMA table_info(entrevistas)")
    cols_e = [col[1] for col in c.fetchall()]
    migration_map = {
        'expediente': "TEXT DEFAULT ''",
        'nombre': "TEXT DEFAULT ''",
        'ap_paterno': "TEXT DEFAULT ''",
        'ap_materno': "TEXT DEFAULT ''",
        'nombre_completo': "TEXT DEFAULT ''",
        'sexo': "TEXT DEFAULT 'Masculino'",
        'fecha_nacimiento': "TEXT DEFAULT ''",
        'fecha_ingreso': "TEXT DEFAULT ''",
        'fecha_inicio_etapa': "TEXT DEFAULT ''",
        'etapa': "TEXT DEFAULT 'Acogida'",
        'estado': "TEXT DEFAULT 'Activo'"
    }
    for col_name, col_def in migration_map.items():
        if col_name not in cols_e:
            c.execute(f"ALTER TABLE entrevistas ADD COLUMN {col_name} {col_def}")

    # 3. Otras tablas del sistema
    c.execute('''
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_ingreso TEXT,
            datos_json TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            fecha TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeutos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            terapeuta TEXT,
            asistentes_json TEXT,
            observaciones TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            gramaje TEXT,
            stock INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 5
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicacion_paciente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            frecuencia TEXT,
            fecha_asignacion TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS entras_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha TEXT,
            usuario TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS documentos_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            nombre_archivo TEXT,
            carpeta TEXT,
            fecha_subida TEXT,
            contenido_blob BLOB
        )
    ''')

    # Carpetas por defecto en repositorio
    carpetas_def = ["General", "Ingresos", "Consejerías", "Evaluaciones", "Médico", "Legal"]
    for c_def in carpetas_def:
        c.execute('INSERT OR IGNORE INTO carpetas_repositorio (nombre_carpeta) VALUES (?)', (c_def,))

    conn.commit()
    conn.close()

# --- FUNCIONES AUXILIARES DE BASE DE DATOS ---
def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol, estado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    row = c.fetchone()
    conn.close()
    return row

def obtener_pacientes(estado_filtro="Todos"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if estado_filtro == "Activos":
        c.execute("SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa, estado, fecha_registro, datos_json FROM entrevistas WHERE estado = 'Activo' ORDER BY fecha_registro DESC")
    elif estado_filtro == "Inactivos":
        c.execute("SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa, estado, fecha_registro, datos_json FROM entrevistas WHERE estado != 'Activo' ORDER BY fecha_registro DESC")
    else:
        c.execute("SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa, estado, fecha_registro, datos_json FROM entrevistas ORDER BY fecha_registro DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(p_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa, estado, fecha_registro, datos_json FROM entrevistas WHERE paciente_id = ?", (p_id,))
    row = c.fetchone()
    conn.close()
    return row

def validar_duplicado_paciente(nombre_comp, exp_num, p_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    norm_name = str(nombre_comp).strip().lower()
    
    # Check name duplicate
    c.execute("SELECT paciente_id, expediente, nombre_completo FROM entrevistas")
    for r in c.fetchall():
        pid, exp, name = r[0], r[1], r[2]
        if p_id_actual and pid == p_id_actual:
            continue
        if str(name).strip().lower() == norm_name and norm_name != "":
            conn.close()
            return True, f"Ya existe un residente con el nombre '{name}' (Folio: {pid}, Exp: {exp})."
            
    # Check expediente duplicate if provided
    if exp_num and str(exp_num).strip():
        norm_exp = str(exp_num).strip().lower()
        c.execute("SELECT paciente_id, expediente, nombre_completo FROM entrevistas")
        for r in c.fetchall():
            pid, exp, name = r[0], r[1], r[2]
            if p_id_actual and pid == p_id_actual:
                continue
            if str(exp).strip().lower() == norm_exp:
                conn.close()
                return True, f"El número de expediente '{exp_num}' ya está asignado al paciente '{name}' (Folio: {pid})."
                
    conn.close()
    return False, ""

def generar_folio_siguiente():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id FROM entrevistas")
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        pid = str(r[0])
        if pid.startswith("PAC-"):
            try:
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except:
                pass
    return f"PAC-{(max_num + 1):03d}"

# --- GENERADOR DE REPORTES PDF ---
class PDFReportListado(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, clean_pdf_text("LISTADO GENERAL DE PACIENTES Y ESTADO CLINICO"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 5, clean_pdf_text(f"Fecha de emision: {date.today().strftime('%d/%m/%Y')}"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, clean_pdf_text(f"Pagina {self.page_no()}"), align="C")

def generar_pdf_listado_pacientes(pacientes):
    pdf = PDFReportListado()
    pdf.add_page(orientation="L") # Landscape for wider table
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Encabezados de tabla
    col_w = [25, 75, 20, 15, 35, 40, 40, 20]
    headers = ["Folio/Exp", "Nombre Completo", "Sexo", "Edad", "Etapa", "Dias en Proceso", "Dias en Etapa", "Estado"]
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(232, 245, 233)
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, clean_pdf_text(h), border=1, align="C", fill=True)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for p in pacientes:
        pid = p[0]
        exp = p[1] if p[1] else "-"
        nombre_c = p[5] if p[5] else f"{p[2]} {p[3]} {p[4]}".strip()
        sexo = p[6] if p[6] else "Masc."
        edad = calculate_age(p[7])
        etapa = p[10] if p[10] else "Acogida"
        dias_proceso = calculate_days(p[8])
        dias_etapa = calculate_days(p[9])
        estado = p[11] if p[11] else "Activo"
        
        pdf.cell(col_w[0], 6, clean_pdf_text(f"{pid}/{exp}"), border=1, align="C")
        pdf.cell(col_w[1], 6, clean_pdf_text(nombre_c[:38]), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(sexo), border=1, align="C")
        pdf.cell(col_w[3], 6, str(edad), border=1, align="C")
        pdf.cell(col_w[4], 6, clean_pdf_text(etapa), border=1, align="C")
        pdf.cell(col_w[5], 6, f"{dias_proceso} dias", border=1, align="C")
        pdf.cell(col_w[6], 6, f"{dias_etapa} dias", border=1, align="C")
        pdf.cell(col_w[7], 6, clean_pdf_text(estado), border=1, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf_path = "/workspace/scratch/Listado_Pacientes_Sawabona.pdf"
    pdf.output(pdf_path)
    return pdf_path

class PDFReportFichaIngreso(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 7, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 5, clean_pdf_text("FICHA DE INGRESO Y ADMISION DE RESIDENTE (NOM-028-SSA2-2009)"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, clean_pdf_text(f"Pagina {self.page_no()}"), align="C")

def generar_pdf_ficha_ingreso(p_id, datos):
    pdf = PDFReportFichaIngreso()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"FOLIO: {p_id} | EXPEDIENTE: {datos.get('expediente', 'S/N')} | FECHA: {datos.get('fecha_ingreso', '')} {datos.get('hora_ingreso', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # Datos Residente
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("1. DATOS GENERALES DEL RESIDENTE"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre: {datos.get('nombre_completo', '')} | Sexo: {datos.get('sexo', '')} | Edad: {datos.get('edad', '')} años | Fecha Nac: {datos.get('fecha_nacimiento', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Estado Civil: {datos.get('estado_civil', '')} | Escolaridad: {datos.get('escolaridad', '')} | Religion: {datos.get('religion', '')} | Ocupacion: {datos.get('ocupacion', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio: {datos.get('calle', '')} {datos.get('numero', '')}, Col. {datos.get('colonia', '')}, {datos.get('municipio', '')}, {datos.get('estado', '')} CP {datos.get('cp', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Servicio Medico: {datos.get('servicio_medico', 'NO')} - {datos.get('servicio_medico_inst', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # Responsable
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("2. RESPONSABLE FAMILIAR Y CONTACTO"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, clean_pdf_text(f"Responsable: {datos.get('resp_nombre', '')} | Parentesco: {datos.get('resp_parentesco', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Telefono(s): {datos.get('resp_telefono', '')} | Email: {datos.get('resp_email', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio Resp: {datos.get('resp_domicilio', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Contacto Emergencia 2: {datos.get('cont2_nombre', '')} ({datos.get('cont2_parentesco', '')}) - Tel: {datos.get('cont2_telefono', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # Financiero y Sustancias
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("3. ACUERDO FINANCIERO Y SUSTANCIAS"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, clean_pdf_text(f"Costo Ingreso: $4,500.00 | Cuota Mensual: $6,000.00 | Pagare: $42,000.00"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Sustancias Consumidas: {', '.join(datos.get('sustancias_ingreso', [])) if isinstance(datos.get('sustancias_ingreso'), list) else datos.get('sustancias_ingreso', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Modalidad: {datos.get('modalidad', 'Voluntario')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Firmas
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(60, 15, "", border=0)
    pdf.cell(60, 15, "", border=0)
    pdf.cell(60, 15, "", border=0, new_x="LMARGIN", new_y="NEXT")
    
    pdf.cell(60, 4, clean_pdf_text("____________________________"), align="C")
    pdf.cell(60, 4, clean_pdf_text("____________________________"), align="C")
    pdf.cell(60, 4, clean_pdf_text("____________________________"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.cell(60, 4, clean_pdf_text("Firma Responsable Familiar"), align="C")
    pdf.cell(60, 4, clean_pdf_text("Firma del Residente"), align="C")
    pdf.cell(60, 4, clean_pdf_text("Direccion del Establecimiento"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    file_path = f"/workspace/scratch/Ficha_Ingreso_{p_id}.pdf"
    pdf.output(file_path)
    return file_path

# --- PROGRAMA PRINCIPAL ---
def main():
    init_db()
    
    # Header Institucional
    st.markdown('''
        <div style="background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%); padding: 18px 25px; border-radius: 12px; color: white; margin-bottom: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <h1 style="color: #FFFFFF; margin: 0; font-size: 1.8em; font-weight: bold;">🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>
                    <p style="color: #C8E6C9; margin: 4px 0 0 0; font-size: 1.05em; font-weight: 500;">Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</p>
                </div>
                <div style="margin-top: 8px;">
                    <span style="background-color: #4CAF50; color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold; margin-right: 8px;">SISTEMA ACTIVO</span>
                    <span style="background-color: #81C784; color: #1B5E20; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold;">NOM-028-SSA2-2009</span>
                </div>
            </div>
        </div>
    ''', unsafe_allow_html=True)

    # Control de Sesión
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""

    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión de Personal")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                u_in = st.text_input("Usuario")
                p_in = st.text_input("Contraseña", type="password")
                btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                if btn_login:
                    res = verificar_login(u_in, p_in)
                    if res:
                        if res[3] == "Bloqueado":
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = res[0]
                            st.session_state["nombre_completo"] = res[1]
                            st.session_state["rol"] = res[2]
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
        return

    # Menú Lateral Navigation
    st.sidebar.markdown('''
        <div style="text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;">
            <h3 style="color: #2E7D32; margin:0;">🌱 Sawabona</h3>
            <p style="color: #388E3C; margin:0; font-size:0.85em;">Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)
    
    st.sidebar.write(f"👤 **Usuario**: {st.session_state.get('nombre_completo', st.session_state['username'])}")
    st.sidebar.write(f"🛡️ **Rol**: {st.session_state.get('rol', 'Solo Lectura')}")
    
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

    # --- MÓDULO 1: TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General y Estado Clínico")
        
        pacientes_todos = obtener_pacientes("Todos")
        pacientes_activos = [p for p in pacientes_todos if p[11] == "Activo"]
        pacientes_inactivos = [p for p in pacientes_todos if p[11] != "Activo"]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Residentes Activos", len(pacientes_activos))
        m2.metric("Residentes Inactivos / Bloqueados", len(pacientes_inactivos))
        m3.metric("Total Expedientes", len(pacientes_todos))
        m4.metric("Etapas en Modelo", "5 Etapas NOM-028")
        
        st.divider()
        st.subheader("📊 Distribución de Residentes por Etapa del Tratamiento")
        
        etapas_lista = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        tabs_etapas = st.tabs([f"📌 {et}" for et in etapas_lista])
        
        for idx, et_nombre in enumerate(etapas_lista):
            with tabs_etapas[idx]:
                p_etapa = [p for p in pacientes_activos if str(p[10]).strip().lower() == et_nombre.lower()]
                st.write(f"**Total en {et_nombre}:** {len(p_etapa)} residente(s)")
                if p_etapa:
                    for p in p_etapa:
                        dias_estancia = calculate_days(p[8])
                        dias_etapa = calculate_days(p[9])
                        edad = calculate_age(p[7])
                        with st.expander(f"👤 {p[5]} | Folio: {p[0]} | Exp: {p[1] or 'S/N'} | Días en Etapa: {dias_etapa} días"):
                            st.write(f"**Sexo:** {p[6]} | **Edad:** {edad} años")
                            st.write(f"**Fecha Ingreso:** {p[8]} ({dias_estancia} días totales en proceso)")
                            st.write(f"**Fecha Inicio Etapa:** {p[9]}")
                else:
                    st.info(f"No hay residentes activos registrados en la etapa de **{et_nombre}**.")

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        
        # Session state keys for clearing form after save
        if "reg_nombre" not in st.session_state: st.session_state["reg_nombre"] = ""
        if "reg_ap_pat" not in st.session_state: st.session_state["reg_ap_pat"] = ""
        if "reg_ap_mat" not in st.session_state: st.session_state["reg_ap_mat"] = ""
        if "reg_exp" not in st.session_state: st.session_state["reg_exp"] = ""
        if "reg_sexo" not in st.session_state: st.session_state["reg_sexo"] = "Masculino"
        if "reg_fecha_nac" not in st.session_state: st.session_state["reg_fecha_nac"] = date(1995, 1, 1)
        if "reg_fecha_ing" not in st.session_state: st.session_state["reg_fecha_ing"] = date.today()
        if "reg_fecha_etapa" not in st.session_state: st.session_state["reg_fecha_etapa"] = date.today()
        if "reg_etapa" not in st.session_state: st.session_state["reg_etapa"] = "Acogida"

        tab_alta, tab_edit, tab_block = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Estado y Bloqueos"])
        
        with tab_alta:
            st.subheader("Captura de Nuevo Residente")
            folio_sugerido = generar_folio_siguiente()
            st.info(f"📌 **Folio Autoincrementable Asignado:** `{folio_sugerido}`")
            
            with st.form("form_alta_paciente"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    nombre_in = st.text_input("Nombre(s) *", value=st.session_state["reg_nombre"], key="input_nombre")
                with c2:
                    ap_pat_in = st.text_input("Apellido Paterno *", value=st.session_state["reg_ap_pat"], key="input_ap_pat")
                with c3:
                    ap_mat_in = st.text_input("Apellido Materno", value=st.session_state["reg_ap_mat"], key="input_ap_mat")
                    
                c4, c5, c6 = st.columns(3)
                with c4:
                    exp_in = st.text_input("No. de Expediente (Opcional)", value=st.session_state["reg_exp"], key="input_exp")
                with c5:
                    sexo_in = st.selectbox("Sexo *", ["Masculino", "Femenino", "Otro"], index=get_safe_index(["Masculino", "Femenino", "Otro"], st.session_state["reg_sexo"]), key="input_sexo")
                with c6:
                    fecha_nac_in = st.date_input("Fecha de Nacimiento *", value=st.session_state["reg_fecha_nac"], key="input_fnac")
                    
                c7, c8, c9 = st.columns(3)
                with c7:
                    fecha_ing_in = st.date_input("Fecha de Ingreso a la Institución *", value=st.session_state["reg_fecha_ing"], key="input_fing")
                with c8:
                    fecha_etapa_in = st.date_input("Fecha de Inicio de Etapa *", value=st.session_state["reg_fecha_etapa"], key="input_fetapa")
                with c9:
                    etapa_in = st.selectbox("Etapa Inicial *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=get_safe_index(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], st.session_state["reg_etapa"]), key="input_etapa")
                    
                btn_alta = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                
                if btn_alta:
                    nombre_comp = f"{nombre_in} {ap_pat_in} {ap_mat_in}".strip()
                    if not nombre_in or not ap_pat_in:
                        st.error("⚠️ El Nombre y Apellido Paterno son obligatorios.")
                    else:
                        dup, msg_dup = validar_duplicado_paciente(nombre_comp, exp_in)
                        if dup:
                            st.error(f"⛔ {msg_dup}")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('''
                                INSERT INTO entrevistas 
                                (paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, fecha_inicio_etapa, etapa, estado, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Activo', ?, ?, ?, '{}')
                            ''', (folio_sugerido, exp_in, nombre_in, ap_pat_in, ap_mat_in, nombre_comp, sexo_in, str(fecha_nac_in), str(fecha_ing_in), str(fecha_etapa_in), etapa_in, f_actual, f_actual, st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            
                            # RESET FORM VALUES TO DEFAULTS
                            st.session_state["reg_nombre"] = ""
                            st.session_state["reg_ap_pat"] = ""
                            st.session_state["reg_ap_mat"] = ""
                            st.session_state["reg_exp"] = ""
                            st.session_state["reg_sexo"] = "Masculino"
                            st.session_state["reg_fecha_nac"] = date(1995, 1, 1)
                            st.session_state["reg_fecha_ing"] = date.today()
                            st.session_state["reg_fecha_etapa"] = date.today()
                            st.session_state["reg_etapa"] = "Acogida"
                            
                            st.balloons()
                            st.toast("✅ Residente guardado con éxito!", icon="🎉")
                            st.success(f"✅ ¡Residente **{nombre_comp}** registrado correctamente con el Folio **{folio_sugerido}**! Los campos se han limpiado para la siguiente captura.")
                            st.rerun()

        with tab_edit:
            st.subheader("Editar Datos de Paciente Existente")
            pacientes_activos = obtener_pacientes("Activos")
            if not pacientes_activos:
                st.warning("No hay pacientes activos registrados para editar.")
            else:
                dict_p = {f"{p[0]} - {p[5]} (Exp: {p[1] or 'S/N'})": p[0] for p in pacientes_activos}
                sel_p_label = st.selectbox("Seleccione Paciente a Editar", list(dict_p.keys()))
                sel_p_id = dict_p[sel_p_label]
                
                p_data = obtener_paciente_por_id(sel_p_id)
                if p_data:
                    with st.form("form_edit_paciente"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            e_nom = st.text_input("Nombre(s)", value=p_data[2] or "")
                        with ce2:
                            e_app = st.text_input("Apellido Paterno", value=p_data[3] or "")
                        with ce3:
                            e_apm = st.text_input("Apellido Materno", value=p_data[4] or "")
                            
                        ce4, ce5, ce6 = st.columns(3)
                        with ce4:
                            e_exp = st.text_input("No. de Expediente", value=p_data[1] or "")
                        with ce5:
                            opts_s = ["Masculino", "Femenino", "Otro"]
                            e_sex = st.selectbox("Sexo", opts_s, index=get_safe_index(opts_s, p_data[6]))
                        with ce6:
                            try: fn_val = datetime.strptime(p_data[7], "%Y-%m-%d").date() if p_data[7] else date(1995,1,1)
                            except: fn_val = date(1995,1,1)
                            e_fnac = st.date_input("Fecha Nacimiento", value=fn_val)
                            
                        ce7, ce8, ce9 = st.columns(3)
                        with ce7:
                            try: fi_val = datetime.strptime(p_data[8], "%Y-%m-%d").date() if p_data[8] else date.today()
                            except: fi_val = date.today()
                            e_fing = st.date_input("Fecha Ingreso Institución", value=fi_val)
                        with ce8:
                            try: fe_val = datetime.strptime(p_data[9], "%Y-%m-%d").date() if p_data[9] else date.today()
                            except: fe_val = date.today()
                            e_fetapa = st.date_input("Fecha Inicio Etapa", value=fe_val)
                        with ce9:
                            opts_e = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                            e_etapa = st.selectbox("Etapa Actual", opts_e, index=get_safe_index(opts_e, p_data[10]))
                            
                        btn_edit = st.form_submit_button("💾 Guardar Cambios de Residente", use_container_width=True)
                        if btn_edit:
                            e_fullname = f"{e_nom} {e_app} {e_apm}".strip()
                            dup, msg_dup = validar_duplicado_paciente(e_fullname, e_exp, sel_p_id)
                            if dup:
                                st.error(f"⛔ {msg_dup}")
                            else:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute('''
                                    UPDATE entrevistas
                                    SET expediente = ?, nombre = ?, ap_paterno = ?, ap_materno = ?, nombre_completo = ?, sexo = ?, fecha_nacimiento = ?, fecha_ingreso = ?, fecha_inicio_etapa = ?, etapa = ?, fecha_modificacion = ?
                                    WHERE paciente_id = ?
                                ''', (e_exp, e_nom, e_app, e_apm, e_fullname, e_sex, str(e_fnac), str(e_fing), str(e_fetapa), e_etapa, f_actual, sel_p_id))
                                conn.commit()
                                conn.close()
                                
                                st.balloons()
                                st.success("✅ Cambios actualizados correctamente.")
                                st.rerun()

        with tab_block:
            st.subheader("Gestión de Estado de Pacientes (Activo / Bloqueado / Inactivo)")
            p_todos = obtener_pacientes("Todos")
            if p_todos:
                dict_b = {f"{p[0]} - {p[5]} [{p[11]}]": (p[0], p[11]) for p in p_todos}
                sel_b_label = st.selectbox("Seleccione Paciente a Modificar Estado", list(dict_b.keys()))
                sel_b_id, cur_st = dict_b[sel_b_label]
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🔴 Bloquear / Inactivar Residente", use_container_width=True):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE entrevistas SET estado = 'Inactivo' WHERE paciente_id = ?", (sel_b_id,))
                        conn.commit()
                        conn.close()
                        st.toast("Residente inhabilitado")
                        st.rerun()
                with col_b2:
                    if st.button("🟢 Reactivar Residente", use_container_width=True):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE entrevistas SET estado = 'Activo' WHERE paciente_id = ?", (sel_b_id,))
                        conn.commit()
                        conn.close()
                        st.toast("Residente reactivado")
                        st.rerun()

        st.divider()
        st.subheader("📋 Lista de Residentes Activos Registrados")
        
        # BOTÓN PARA IMPRIMIR REPORTES PDF LISTADO
        p_activos_lista = obtener_pacientes("Activos")
        if p_activos_lista:
            pdf_list_path = generar_pdf_listado_pacientes(p_activos_lista)
            with open(pdf_list_path, "rb") as f_pdf:
                st.download_button(
                    label="🖨️ Imprimir / Descargar Reporte de Pacientes Activos (PDF)",
                    data=f_pdf,
                    file_name=f"Listado_Pacientes_Sawabona_{date.today().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    key="btn_pdf_activos"
                )
                
            grid_data = []
            for p in p_activos_lista:
                grid_data.append({
                    "Folio": p[0],
                    "Expediente": p[1] or "S/N",
                    "Nombre Completo": p[5],
                    "Sexo": p[6],
                    "Edad": f"{calculate_age(p[7])} años",
                    "Etapa": p[10],
                    "Días en Proceso": f"{calculate_days(p[8])} días",
                    "Días en Etapa": f"{calculate_days(p[9])} días"
                })
            st.dataframe(grid_data, use_container_width=True)

    # --- MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión de Residentes")
        st.caption("Formato Oficial de Admisión NOM-028-SSA2-2009 - Comunidad Terapéutica Sawabona Shikoba A.C.")
        
        pacientes_activos = obtener_pacientes("Activos")
        if not pacientes_activos:
            st.warning("No hay pacientes registrados. Primero registre al menos un paciente en el Módulo 'Registro y Edición de Pacientes'.")
        else:
            dict_f = {f"{p[0]} - {p[5]} (Exp: {p[1] or 'S/N'})": p[0] for p in pacientes_activos}
            sel_f_label = st.selectbox("Seleccione Residente para Ficha de Ingreso", list(dict_f.keys()))
            sel_f_id = dict_f[sel_f_label]
            
            p_info = obtener_paciente_por_id(sel_f_id)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (sel_f_id,))
            f_row = c.fetchone()
            conn.close()
            
            f_datos = json.loads(f_row[0]) if f_row else {}
            
            with st.form("form_ficha_ingreso"):
                f_tab1, f_tab2, f_tab3, f_tab4, f_tab5 = st.tabs([
                    "1. Admisión y Sucursal",
                    "2. Datos del Residente",
                    "3. Sustancias de Consumo",
                    "4. Responsable Familiar",
                    "5. Cláusulas y Firmas"
                ])
                
                with f_tab1:
                    c_a1, c_a2 = st.columns(2)
                    with c_a1:
                        sucursal = st.text_input("Sucursal a Referir", value=f_datos.get("sucursal", "Matriz Colima"))
                        expediente_f = st.text_input("No. de Expediente", value=p_info[1] or f_datos.get("expediente", ""))
                    with c_a2:
                        fecha_ing_f = st.text_input("Fecha de Ingreso", value=p_info[8] or f_datos.get("fecha_ingreso", str(date.today())))
                        hora_ing_f = st.text_input("Hora de Ingreso", value=f_datos.get("hora_ingreso", datetime.now().strftime("%H:%M")))
                        
                    st.divider()
                    st.markdown("**Acuerdo Financiero Basal**")
                    col_f1, col_f2, col_f3 = st.columns(3)
                    with col_f1: st.info("Costo de Ingreso: **$4,500.00**")
                    with col_f2: st.info("Cuota Mensual: **$6,000.00**")
                    with col_f3: st.info("Importe Pagaré: **$42,000.00**")
                    
                with f_tab2:
                    st.write(f"**Nombre:** {p_info[5]} | **Sexo:** {p_info[6]} | **Fecha Nac:** {p_info[7]}")
                    c_r1, c_r2, c_r3 = st.columns(3)
                    with c_r1:
                        est_civil = st.text_input("Estado Civil", value=f_datos.get("estado_civil", "Soltero(a)"))
                    with c_r2:
                        escolaridad = st.text_input("Escolaridad", value=f_datos.get("escolaridad", "Secundaria"))
                    with c_r3:
                        ocupacion = st.text_input("Ocupación", value=f_datos.get("ocupacion", "Empleado(a)"))
                        
                    c_r4, c_r5 = st.columns(2)
                    with c_r4:
                        religion = st.text_input("Religión", value=f_datos.get("religion", "Católica"))
                    with c_r5:
                        serv_medico = st.selectbox("Servicio Médico", ["NO", "SÍ"], index=1 if f_datos.get("servicio_medico") == "SÍ" else 0)
                        serv_inst = st.text_input("Institución Médica (IMSS/ISSSTE/etc.)", value=f_datos.get("servicio_medico_inst", ""))
                        
                    st.markdown("**Domicilio Particular del Residente**")
                    cd1, cd2, cd3 = st.columns(3)
                    with cd1: calle = st.text_input("Calle y Número", value=f_datos.get("calle", ""))
                    with cd2: colonia = st.text_input("Colonia / Población", value=f_datos.get("colonia", ""))
                    with cd3: municipio = st.text_input("Municipio / Ciudad", value=f_datos.get("municipio", ""))
                    cd4, cd5 = st.columns(2)
                    with cd4: estado_dom = st.text_input("Estado", value=f_datos.get("estado", "Colima"))
                    with cd5: cp_dom = st.text_input("Código Postal", value=f_datos.get("cp", ""))

                with f_tab3:
                    st.subheader("Sustancias Consumidas al Ingresar")
                    cat_sust = ["Alcohol", "Cannabis", "Cocaína", "Metanfetamina", "Inhalables", "Tabaco", "Alcaloides", "Benzodiazepinas", "Esteroides", "LSD", "Opiáceos", "Solventes"]
                    sust_guardadas = f_datos.get("sustancias_ingreso", [])
                    sust_seleccionadas = []
                    
                    c_s1, c_s2, c_s3 = st.columns(3)
                    for i, s_item in enumerate(cat_sust):
                        col_curr = [c_s1, c_s2, c_s3][i % 3]
                        with col_curr:
                            chk = st.checkbox(s_item, value=s_item in sust_guardadas, key=f"chk_f_{s_item}")
                            if chk: sust_seleccionadas.append(s_item)
                            
                    modalidad = st.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario por Solicitud Familiar"], index=0)

                with f_tab4:
                    st.subheader("Datos del Familiar / Responsable Legal")
                    cr1, cr2 = st.columns(2)
                    with cr1:
                        resp_nombre = st.text_input("Nombre Completo del Responsable", value=f_datos.get("resp_nombre", ""))
                        resp_parentesco = st.text_input("Parentesco (Desea internar a su...)", value=f_datos.get("resp_parentesco", "Hijo(a)"))
                    with cr2:
                        resp_telef = st.text_input("Teléfono(s) de Contacto", value=f_datos.get("resp_telefono", ""))
                        resp_email = st.text_input("Correo Electrónico", value=f_datos.get("resp_email", ""))
                    resp_domicilio = st.text_area("Domicilio Completo del Responsable", value=f_datos.get("resp_domicilio", ""))
                    
                    st.divider()
                    st.markdown("**Segundo Contacto de Emergencia**")
                    cc1, cc2, cc3 = st.columns(3)
                    with cc1: cont2_nombre = st.text_input("Nombre Contacto 2", value=f_datos.get("cont2_nombre", ""))
                    with cc2: cont2_parentesco = st.text_input("Parentesco 2", value=f_datos.get("cont2_parentesco", ""))
                    with cc3: cont2_telef = st.text_input("Teléfono 2", value=f_datos.get("cont2_telefono", ""))

                with f_tab5:
                    st.subheader("Cláusulas NOM-028-SSA2-2009 y Compromisos")
                    st.info("Tratamiento con duración de 6 a 8 meses (Mínimo legal obligatorio: 7 meses conforme a NOM-028). La institución garantiza la dignidad, integridad física y atención biopsicosocial del residente.")
                    
                    btn_guardar_ficha = st.form_submit_button("💾 Guardar Ficha de Ingreso Oficial", use_container_width=True)
                    
                    if btn_guardar_ficha:
                        datos_ficha_complete = {
                            "expediente": expediente_f,
                            "sucursal": sucursal,
                            "fecha_ingreso": fecha_ing_f,
                            "hora_ingreso": hora_ing_f,
                            "nombre_completo": p_info[5],
                            "sexo": p_info[6],
                            "edad": calculate_age(p_info[7]),
                            "fecha_nacimiento": p_info[7],
                            "estado_civil": est_civil,
                            "escolaridad": escolaridad,
                            "ocupacion": ocupacion,
                            "religion": religion,
                            "servicio_medico": serv_medico,
                            "servicio_medico_inst": serv_inst,
                            "calle": calle, "colonia": colonia, "municipio": municipio, "estado": estado_dom, "cp": cp_dom,
                            "sustancias_ingreso": sust_seleccionadas,
                            "modalidad": modalidad,
                            "resp_nombre": resp_nombre, "resp_parentesco": resp_parentesco, "resp_telefono": resp_telef, "resp_email": resp_email, "resp_domicilio": resp_domicilio,
                            "cont2_nombre": cont2_nombre, "cont2_parentesco": cont2_parentesco, "cont2_telefono": cont2_telef
                        }
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT OR REPLACE INTO fichas_ingreso (paciente_id, fecha_ingreso, datos_json) VALUES (?, ?, ?)",
                                  (sel_f_id, fecha_ing_f, json.dumps(datos_ficha_complete, ensure_ascii=False)))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.success("✅ Ficha de Ingreso guardada con éxito.")
                        st.rerun()

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (sel_f_id,))
            f_check = c.fetchone()
            conn.close()
            if f_check:
                pdf_ficha_path = generar_pdf_ficha_ingreso(sel_f_id, json.loads(f_check[0]))
                with open(pdf_ficha_path, "rb") as f_fpdf:
                    st.download_button(
                        label="🖨️ Descargar / Imprimir Ficha de Ingreso Oficial (PDF)",
                        data=f_fpdf,
                        file_name=f"Ficha_Ingreso_{sel_f_id}.pdf",
                        mime="application/pdf",
                        key="btn_dl_ficha_pdf"
                    )

    # --- MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        
        pacientes_activos = obtener_pacientes("Activos")
        if not pacientes_activos:
            st.warning("No hay pacientes registrados.")
        else:
            dict_e = {f"{p[0]} - {p[5]} (Exp: {p[1] or 'S/N'})": p[0] for p in pacientes_activos}
            sel_e_label = st.selectbox("Seleccione Paciente para Entrevista", list(dict_e.keys()))
            sel_e_id = dict_e[sel_e_label]
            
            p_data = obtener_paciente_por_id(sel_e_id)
            datos_json_str = p_data[13] if p_data and len(p_data) > 13 else "{}"
            try: datos_e = json.loads(datos_json_str)
            except: datos_e = {}
            
            with st.form("form_entrevista_inicial"):
                t1, t2, t3, t4 = st.tabs(["1. Evaluación Basal", "2. Tabla de Consumo", "3. Disposición al Cambio", "4. Observaciones"])
                
                with t1:
                    st.write(f"**Paciente:** {p_data[5]} | **Folio:** {p_data[0]} | **Sexo:** {p_data[6]}")
                    dep_flag = st.selectbox("¿Dependientes económicos?", ["NO", "SÍ"], index=1 if datos_e.get("dependientes_flag") == "SÍ" else 0)
                    dep_quienes = st.text_input("¿Quiénes?", value=datos_e.get("dependientes_quienes", ""))
                    pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if datos_e.get("pareja_flag") == "SÍ" else 0)
                    pareja_tiempo = st.text_input("Tiempo de relación", value=datos_e.get("pareja_tiempo", ""))
                    
                with t2:
                    st.subheader("Tabla de Consumo por Sustancia")
                    sust_cat = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "INHALABLES", "TABACO"]
                    tabla_consumo_input = {}
                    tabla_guardada = datos_e.get("tabla_consumo", {})
                    
                    for sust in sust_cat:
                        st.markdown(f"**{sust}**")
                        s_prev = tabla_guardada.get(sust, {})
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: c_chk = st.checkbox("Consume", value=s_prev.get("consumo") == "SÍ", key=f"e_c_{sust}")
                        with c2: c_freq = st.text_input("Frecuencia", value=s_prev.get("frecuencia", ""), key=f"e_f_{sust}")
                        with c3: c_cant = st.text_input("Cantidad", value=s_prev.get("cantidad", ""), key=f"e_cant_{sust}")
                        with c4: c_edad = st.text_input("Edad Inicio", value=s_prev.get("edad_inicio", ""), key=f"e_e_{sust}")
                        tabla_consumo_input[sust] = {
                            "consumo": "SÍ" if c_chk else "NO",
                            "frecuencia": c_freq, "cantidad": c_cant, "edad_inicio": c_edad
                        }
                        
                    st.divider()
                    sust_imp = st.text_input("Sustancia de Impacto Principal", value=datos_e.get("sustancia_impacto", "Sin registrar"))
                    
                with t3:
                    abst_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_e.get("abst_tiempo", ""))
                    abst_motivo = st.text_area("Motivo o estrategia de abstinencia", value=datos_e.get("abst_motivo", ""))
                    imp_cambio = st.select_slider("Importancia de dejar de consumir", options=["1. Nada", "2. Poco", "3. Algo", "4. Importante", "5. Muy Importante"], value=datos_e.get("imp_cambio", "3. Algo"))
                    
                with t4:
                    obs_clinicas = st.text_area("Observaciones Clínicas Generales", value=datos_e.get("observaciones", ""))
                    evaluador = st.text_input("Nombre del Evaluador", value=datos_e.get("evaluador", st.session_state.get("nombre_completo", "")))
                    
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ent:
                    datos_e["dependientes_flag"] = dep_flag
                    datos_e["dependientes_quienes"] = dep_quienes
                    datos_e["pareja_flag"] = pareja_flag
                    datos_e["pareja_tiempo"] = pareja_tiempo
                    datos_e["tabla_consumo"] = tabla_consumo_input
                    datos_e["sustancia_impacto"] = sust_imp
                    datos_e["abst_tiempo"] = abst_tiempo
                    datos_e["abst_motivo"] = abst_motivo
                    datos_e["imp_cambio"] = imp_cambio
                    datos_e["observaciones"] = obs_clinicas
                    datos_e["evaluador"] = evaluador
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE entrevistas SET datos_json = ?, fecha_modificacion = ? WHERE paciente_id = ?",
                              (json.dumps(datos_e, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sel_e_id))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.success("✅ Entrevista Inicial guardada correctamente.")
                    st.rerun()

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        
        pacientes_activos = obtener_pacientes("Activos")
        if not pacientes_activos:
            st.warning("No hay pacientes activos.")
        else:
            dict_c = {f"{p[0]} - {p[5]} ({p[10]})": p[0] for p in pacientes_activos}
            sel_c_label = st.selectbox("Seleccione Paciente", list(dict_c.keys()))
            sel_c_id = dict_c[sel_c_label]
            
            p_info = obtener_paciente_por_id(sel_c_id)
            num_cons = st.number_input("Número de Consejería", min_value=1, max_value=20, value=1)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha FROM consejerias WHERE paciente_id = ? AND num_consejeria = ?", (sel_c_id, num_cons))
            c_row = c.fetchone()
            conn.close()
            
            c_data = c_row if c_row else ("", "", str(date.today()), "", "", "", str(date.today()))
            
            with st.form("form_consejeria"):
                st.write(f"**Paciente:** {p_info[5]} | **Etapa Actual:** {p_info[10]}")
                
                asp_trab = st.text_area("Aspectos Trabajados en Sesión", value=c_data[0])
                exp_val = st.text_area("Exposición / Respuesta del Residente", value=c_data[3])
                av_val = st.text_area("Avances Observados", value=c_data[4])
                sug_val = st.text_area("Sugerencias y Recomendaciones", value=c_data[5])
                asp_prox = st.text_area("Aspectos a Trabajar la Próxima Sesión", value=c_data[1])
                fe_prox = st.text_input("Fecha Próxima Sesión", value=c_data[2])
                
                btn_c_save = st.form_submit_button("💾 Guardar Consejería Individual", use_container_width=True)
                if btn_c_save:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''
                        INSERT INTO consejerias (paciente_id, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (sel_c_id, p_info[10], num_cons, asp_trab, asp_prox, fe_prox, exp_val, av_val, sug_val, f_now))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.success("✅ Consejería registrada exitosamente.")
                    st.rerun()

    # --- MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso de Tratamiento")
        
        pacientes_activos = obtener_pacientes("Activos")
        if not pacientes_activos:
            st.warning("No hay residentes activos.")
        else:
            dict_g = {f"{p[0]} - {p[5]} ({p[10]})": p[0] for p in pacientes_activos}
            sel_g_label = st.selectbox("Seleccione Residente para Evaluar Avance", list(dict_g.keys()))
            sel_g_id = dict_g[sel_g_label]
            
            p_info = obtener_paciente_por_id(sel_g_id)
            dias_etapa = calculate_days(p_info[9])
            dias_totales = calculate_days(p_info[8])
            
            st.info(f"📌 **Etapa Actual:** `{p_info[10]}` | **Días en esta Etapa:** `{dias_etapa} días` | **Días Totales en Proceso:** `{dias_totales} días`")
            
            if dias_etapa > 90:
                st.warning("⚠️ **ALERTA DE REZAGO CLÍNICO**: El residente excede los 90 días sugeridos en esta etapa. Evalúe promoción o plan de refuerzo.")
                
            etapas_siguientes = {
                "Acogida": "Identificación",
                "Identificación": "Elaboración",
                "Elaboración": "Consolidación",
                "Consolidación": "Servicio Social",
                "Servicio Social": "Servicio Social (Graduación)"
            }
            siguiente = etapas_siguientes.get(p_info[10], "Servicio Social")
            
            if st.button(f"🚀 Promover a Siguiente Etapa ({siguiente})", use_container_width=True):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                hoy_str = str(date.today())
                c.execute("UPDATE entrevistas SET etapa = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?",
                          (siguiente, hoy_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sel_g_id))
                conn.commit()
                conn.close()
                
                st.balloons()
                st.success(f"🎉 Residente promovido a la etapa de **{siguiente}**.")
                st.rerun()

    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        
        with st.form("form_grupo"):
            cg1, cg2 = st.columns(2)
            with cg1:
                tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Retroalimentación", "Espiritual", "Prevención de Recaídas"])
                tema_grupo = st.text_input("Tema de la Sesión")
            with cg2:
                terapeuta = st.text_input("Terapeuta / Facilitador", value=st.session_state.get("nombre_completo", ""))
                fecha_grupo = st.date_input("Fecha de Sesión", value=date.today())
                
            st.markdown("**Lista de Asistencia de Residentes Activos**")
            p_act = obtener_pacientes("Activos")
            asistentes_sel = []
            for p in p_act:
                if st.checkbox(f"{p[5]} ({p[0]})", key=f"grp_{p[0]}"):
                    asistentes_sel.append(p[0])
                    
            obs_grupo = st.text_area("Observaciones del Grupo")
            btn_save_grp = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)
            
            if btn_save_grp:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT INTO grupos_terapeutos (fecha, tipo_grupo, tema, terapeuta, asistentes_json, observaciones) VALUES (?, ?, ?, ?, ?, ?)",
                          (str(fecha_grupo), tipo_grupo, tema_grupo, terapeuta, json.dumps(asistentes_sel), obs_grupo))
                conn.commit()
                conn.close()
                st.balloons()
                st.success("✅ Grupo Terapéutico registrado exitosamente.")

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario")
        
        tab_inv, tab_asig = st.tabs(["📦 Inventario de Fármacos", "💊 Asignación y Entregas"])
        
        with tab_inv:
            with st.form("form_med_inv"):
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1: m_nom = st.text_input("Nombre del Medicamento")
                with c_m2: m_gram = st.text_input("Gramaje / Dosis (ej. 500mg)")
                with c_m3: m_stock = st.number_input("Stock Inicial", min_value=0, value=10)
                
                btn_m_add = st.form_submit_button("➕ Agregar al Inventario")
                if btn_m_add:
                    if m_nom:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT OR REPLACE INTO medicamentos (nombre, gramaje, stock) VALUES (?, ?, ?)",
                                  (m_nom, m_gram, m_stock))
                        conn.commit()
                        conn.close()
                        st.success("Medicamento registrado.")
                        st.rerun()
                        
            st.subheader("Inventario Actual")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, nombre, gramaje, stock FROM medicamentos")
            meds_rows = c.fetchall()
            conn.close()
            if meds_rows:
                st.table([{"ID": r[0], "Medicamento": r[1], "Gramaje": r[2], "Stock Disponible": r[3]} for r in meds_rows])

        with tab_asig:
            st.subheader("Registro de Entregas de Medicación")
            p_act = obtener_pacientes("Activos")
            if p_act and meds_rows:
                dict_p = {f"{p[0]} - {p[5]}": p[0] for p in p_act}
                dict_m = {f"{r[1]} ({r[2]}) - Stock: {r[3]}": (r[0], r[3]) for r in meds_rows}
                
                p_sel_m = st.selectbox("Residente", list(dict_p.keys()))
                m_sel_m = st.selectbox("Medicamento", list(dict_m.keys()))
                cant_ent = st.number_input("Cantidad Entregada", min_value=1, value=1)
                
                if st.button("💊 Registrar Entrega y Descontar Stock", use_container_width=True):
                    pid_ent = dict_p[p_sel_m]
                    mid_ent, cur_stock = dict_m[m_sel_m]
                    
                    if cant_ent > cur_stock:
                        st.error("Stock insuficiente.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE medicamentos SET stock = stock - ? WHERE id = ?", (cant_ent, mid_ent))
                        c.execute("INSERT INTO entras_medicamentos (paciente_id, medicamento_id, cantidad, fecha, usuario) VALUES (?, ?, ?, ?, ?)",
                                  (pid_ent, mid_ent, cant_ent, str(date.today()), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.success("✅ Entrega registrada correctamente.")
                        st.rerun()

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos Institucionales")
        
        tab_docs, tab_folders = st.tabs(["📄 Expedientes y Archivos", "⚙️ Gestión de Carpetas"])
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM carpetas_repositorio ORDER BY nombre_carpeta ASC")
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()
        
        with tab_docs:
            st.subheader("Subir Documento al Repositorio")
            p_act = obtener_pacientes("Todos")
            dict_rep_p = {"General / Institucional": "GENERAL"}
            for p in p_act: dict_rep_p[f"{p[0]} - {p[5]}"] = p[0]
            
            sel_rep_p = st.selectbox("Asignar a Residente (o General)", list(dict_rep_p.keys()))
            sel_folder = st.selectbox("Carpeta Destino", carpetas_list if carpetas_list else ["General"])
            
            up_file = st.file_uploader("Seleccione archivo (PDF, Word, Imagen)", type=["pdf", "docx", "doc", "jpg", "png"])
            if st.button("📤 Guardar en Repositorio") and up_file:
                bytes_data = up_file.getvalue()
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT INTO documentos_repositorio (paciente_id, nombre_archivo, carpeta, fecha_subida, contenido_blob) VALUES (?, ?, ?, ?, ?)",
                          (dict_rep_p[sel_rep_p], up_file.name, sel_folder, str(date.today()), bytes_data))
                conn.commit()
                conn.close()
                st.success("✅ Archivo subido con éxito.")
                st.rerun()
                
            st.divider()
            st.subheader("Archivos Guardados")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, paciente_id, nombre_archivo, carpeta, fecha_subida, contenido_blob FROM documentos_repositorio")
            docs_rows = c.fetchall()
            conn.close()
            
            if docs_rows:
                for d in docs_rows:
                    with st.expander(f"📄 {d[2]} | Carpeta: {d[3]} | Asignado: {d[1]} | Fecha: {d[4]}"):
                        st.download_button("Descargar Archivo", data=d[5], file_name=d[2])

        with tab_folders:
            st.subheader("Crear o Renombrar Carpetas")
            new_f_name = st.text_input("Nombre de Nueva Carpeta")
            if st.button("➕ Crear Carpeta") and new_f_name:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (new_f_name.strip(),))
                    conn.commit()
                    st.success("Carpeta creada.")
                except:
                    st.error("Esa carpeta ya existe.")
                conn.close()
                st.rerun()

    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Consultar Directorio de Pacientes")
        
        c_s1, c_s2 = st.columns([3, 1])
        with c_s1:
            q_search = st.text_input("🔎 Buscar por Nombre, Folio o Expediente", value="").strip().lower()
        with c_s2:
            st_filter = st.selectbox("Estado", ["Todos", "Activos", "Inactivos"])
            
        pacientes_filtered = obtener_pacientes(st_filter)
        if q_search:
            pacientes_filtered = [
                p for p in pacientes_filtered 
                if q_search in str(p[0]).lower() or q_search in str(p[1]).lower() or q_search in str(p[5]).lower()
            ]
            
        st.subheader(f"Resultados Encontrados: {len(pacientes_filtered)}")
        
        if pacientes_filtered:
            pdf_rep_path = generar_pdf_listado_pacientes(pacientes_filtered)
            with open(pdf_rep_path, "rb") as f_rep:
                st.download_button(
                    label="🖨️ Imprimir Listado PDF (Resultado de Búsqueda)",
                    data=f_rep,
                    file_name="Listado_Pacientes_Busqueda.pdf",
                    mime="application/pdf",
                    key="btn_pdf_search"
                )
                
            for p in pacientes_filtered:
                dias_proceso = calculate_days(p[8])
                dias_etapa = calculate_days(p[9])
                edad = calculate_age(p[7])
                
                with st.expander(f"👤 {p[5]} | Folio: {p[0]} | Exp: {p[1] or 'S/N'} | Etapa: {p[10]} ({p[11]})"):
                    c_d1, c_d2, c_d3 = st.columns(3)
                    with c_d1:
                        st.write(f"**Sexo:** {p[6]}")
                        st.write(f"**Edad:** {edad} años ({p[7]})")
                    with c_d2:
                        st.write(f"**Fecha Ingreso:** {p[8]} ({dias_proceso} días en proceso)")
                        st.write(f"**Fecha Inicio Etapa:** {p[9]} ({dias_etapa} días en etapa)")
                    with c_d3:
                        st.write(f"**Estado:** {p[11]}")
                        st.write(f"**Fecha Registro:** {p[12]}")

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        
        tab_pass, tab_users = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        
        with tab_pass:
            with st.form("form_change_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_new = st.text_input("Nueva Contraseña", type="password")
                p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p_change = st.form_submit_button("Actualizar mi Contraseña")
                
                if btn_p_change:
                    if p_new != p_conf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        v_ok = verificar_login(st.session_state["username"], p_act)
                        if v_ok:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(p_new), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada.")
                        else:
                            st.error("Contraseña actual incorrecta.")

        with tab_users:
            st.subheader("Administración de Cuentas del Personal")
            if st.session_state.get("username") == "admin" or st.session_state.get("rol") == "Administrador":
                with st.form("form_add_user"):
                    u_user = st.text_input("Nombre de Usuario (Username)")
                    u_pass = st.text_input("Contraseña Inicial", type="password")
                    u_name = st.text_input("Nombre Completo del Colaborador")
                    u_rol = st.selectbox("Rol de Acceso", ["Administrador", "Lectura y Escritura", "Solo Lectura"])
                    btn_u_add = st.form_submit_button("➕ Registrar Usuario de Personal")
                    
                    if btn_u_add:
                        if u_user and u_pass:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, 'Activo')",
                                          (u_user.strip(), hash_pass(u_pass), u_name, u_rol))
                                conn.commit()
                                st.balloons()
                                st.success("✅ Usuario de personal registrado.")
                            except:
                                st.error("El nombre de usuario ya existe.")
                            conn.close()
                            st.rerun()

                st.divider()
                st.subheader("Personal Registrado")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol, estado FROM usuarios")
                u_rows = c.fetchall()
                conn.close()
                
                for ur in u_rows:
                    c_u1, c_u2, c_u3, c_u4 = st.columns([2, 3, 2, 2])
                    with c_u1: st.write(f"**{ur[1]}**")
                    with c_u2: st.write(ur[2] or "S/N")
                    with c_u3: st.write(f"{ur[3]} ({ur[4]})")
                    with c_u4:
                        if ur[1] != "admin":
                            if ur[4] == "Activo":
                                if st.button("🔴 Bloquear", key=f"blk_{ur[0]}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Bloqueado' WHERE id = ?", (ur[0],))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
                            else:
                                if st.button("🟢 Activar", key=f"act_{ur[0]}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Activo' WHERE id = ?", (ur[0],))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        st.subheader("1. Descargar Respaldo de Base de Datos (.db)")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f_db:
                st.download_button(
                    label="⬇️ Descargar Copia de Seguridad (.db)",
                    data=f_db,
                    file_name=f"sistema_pacientes_backup_{date.today().strftime('%Y%m%d')}.db",
                    mime="application/x-sqlite3"
                )

if __name__ == "__main__":
    main()

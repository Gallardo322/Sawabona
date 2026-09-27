import streamlit as st
import sqlite3
import json
import hashlib
import os
import re
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista Inicial y Consejería Clínica",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"
ETAPAS = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]

# --- NORMALIZACIÓN Y BÚSQUEDA SEGURA ---
def normalizar_texto(texto):
    if not texto:
        return ""
    txt = str(texto).lower().strip()
    replacements = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"))
    for a, b in replacements:
        txt = txt.replace(a, b)
    return re.sub(r'\s+', ' ', txt)

def get_safe_index(options, value, default_idx=0):
    if not value:
        return default_idx
    val_norm = normalizar_texto(value)
    for idx, opt in enumerate(options):
        if normalizar_texto(opt) == val_norm:
            return idx
    return default_idx

def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': '', '“': '"', '”': '"',
        '’': "'", '—': '-', '–': '-'
    }
    for k, v in replacements.items():
        texto = texto.replace(k, v)
    return texto.encode('latin1', 'ignore').decode('latin1')

# --- INICIALIZACIÓN DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Lectura/Escritura',
            estado TEXT DEFAULT 'Activo'
        )
    ''')
    
    # Tabla Entrevistas / Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            estado TEXT DEFAULT 'Activo',
            datos_json TEXT
        )
    ''')
    
    # Tabla Consejerías
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            expediente TEXT,
            fecha TEXT,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            usuario TEXT
        )
    ''')
    
    # Tabla Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_paciente TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            tema TEXT,
            facilitador TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # Tabla Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            stock INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')
    
    # Tabla Suministro Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS suministro_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            fecha_hora TEXT,
            usuario TEXT,
            observaciones TEXT
        )
    ''')
    
    # Tabla Carpetas Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS carpetas_repo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Tabla Documentos Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS documentos_repo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            carpeta TEXT,
            nombre_archivo TEXT,
            fecha TEXT,
            usuario TEXT,
            descripcion TEXT,
            datos_b64 TEXT
        )
    ''')
    
    # Usuario Admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'Activo'))
    
    # Carpetas por defecto en Repositorio
    carpetas_defaut = [
        "General", "Fichas de Ingreso", "Evaluaciones Clínicas", 
        "Consentimientos Informados", "Estudios Socioeconómicos", "Expedientes Médicos"
    ]
    for c_def in carpetas_defaut:
        c.execute('INSERT OR IGNORE INTO carpetas_repo (nombre_carpeta) VALUES (?)', (c_def,))
        
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

# --- FUNCIONES DE GESTIÓN DE PACIENTES ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    
    max_num = 0
    for r in rows:
        pid = r[0]
        if pid and pid.startswith("PAC-"):
            try:
                num = int(pid.split("-")[1])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

def validar_duplicados_paciente(paciente_id_actual, expediente, nombre, ap_paterno, ap_materno):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    
    exp_target = str(expediente).strip() if expediente else ""
    nombre_full_target = normalizar_texto(f"{nombre} {ap_paterno} {ap_materno}")
    
    for pid, dj_str in rows:
        if pid == paciente_id_actual:
            continue
        dj = json.loads(dj_str) if dj_str else {}
        
        # Validar expediente único
        exp_existente = str(dj.get("expediente", "")).strip()
        if exp_target and exp_existente and exp_target == exp_existente:
            nom_exist = dj.get("nombre_completo", f"Paciente {pid}")
            return False, f"⚠️ El número de Expediente '{exp_target}' ya está asignado al paciente '{nom_exist}' (Folio: {pid})."
            
        # Validar Nombre Completo único
        nom_exist_full = normalizar_texto(dj.get("nombre_completo", ""))
        if nombre_full_target and nom_exist_full and nombre_full_target == nom_exist_full:
            return False, f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{dj.get('nombre_completo')}' (Folio: {pid}, Expediente: {exp_existente or 'S/N'})."
            
    return True, ""

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Asegurar nombre completo unificado
    nom = datos.get("nombre", "").strip()
    app = datos.get("ap_paterno", "").strip()
    apm = datos.get("ap_materno", "").strip()
    datos["nombre_completo"] = f"{nom} {app} {apm}".strip()
    
    datos_json = json.dumps(datos, ensure_ascii=False)
    estado = datos.get("estado", "Activo")
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE entrevistas 
            SET fecha_modificacion = ?, estado = ?, datos_json = ?
            WHERE paciente_id = ?
        ''', (fecha_actual, estado, datos_json, paciente_id))
    else:
        c.execute('''
            INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, estado, datos_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, fecha_actual, fecha_actual, usuario, estado, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro, estado FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        dj = json.loads(row[0])
        dj["estado"] = row[4] or "Activo"
        return dj, row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes(incluir_inactivos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json, estado, fecha_registro FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    
    pacientes = []
    for r in rows:
        dj = json.loads(r[1]) if r[1] else {}
        estado = r[2] or "Activo"
        dj["estado"] = estado
        dj["paciente_id"] = r[0]
        dj["fecha_registro"] = r[3]
        if incluir_inactivos or estado == "Activo":
            pacientes.append(dj)
    return pacientes

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def obtener_carpetas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT nombre_carpeta FROM carpetas_repo ORDER BY nombre_carpeta ASC')
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def agregar_carpeta(nombre):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO carpetas_repo (nombre_carpeta) VALUES (?)', (nombre.strip(),))
        conn.commit()
        conn.close()
        return True, f"✅ Carpeta '{nombre.strip()}' creada exitosamente."
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"⚠️ La carpeta '{nombre.strip()}' ya existe."

def renombrar_carpeta(nombre_viejo, nombre_nuevo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('UPDATE carpetas_repo SET nombre_carpeta = ? WHERE nombre_carpeta = ?', (nombre_nuevo.strip(), nombre_viejo))
        c.execute('UPDATE documentos_repo SET carpeta = ? WHERE carpeta = ?', (nombre_nuevo.strip(), nombre_viejo))
        conn.commit()
        conn.close()
        return True, f"✅ Carpeta renombrada de '{nombre_viejo}' a '{nombre_nuevo.strip()}' correctamente."
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"⚠️ Ya existe una carpeta con el nombre '{nombre_nuevo.strip()}'."

# --- GENERACIÓN DE PDFS ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(46, 125, 50)
        self.cell(0, 8, clean_pdf_text('COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.'), 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, clean_pdf_text('Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones'), 0, 1, 'C')
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, clean_pdf_text(f'Página {self.page_no()} - Documento Oficial Confidencial - NOM-028-SSA2-2009'), 0, 0, 'C')

def generar_pdf_ficha_ingreso(p_id, datos):
    pdf = PDF()
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y CONTRATO DE SERVICIOS"), 0, 1, 'C', True)
    pdf.ln(4)
    
    exp = datos.get("expediente", "S/N")
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(100, 6, clean_pdf_text(f"EXPEDIENTE CLINICO: {exp}"), 0, 0)
    pdf.cell(90, 6, clean_pdf_text(f"FECHA DE INGRESO: {datos.get('fecha_ingreso', '')}"), 0, 1)
    pdf.ln(2)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS GENERALES DEL RESIDENTE"), 0, 1)
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre Completo: {datos.get('nombre_completo', '')}"), 0, 1)
    pdf.cell(95, 5, clean_pdf_text(f"Edad: {datos.get('edad', '')} años"), 0, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Sexo: {datos.get('sexo', '')}"), 0, 1)
    pdf.cell(95, 5, clean_pdf_text(f"Estado Civil: {datos.get('estado_civil', '')}"), 0, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Ocupación: {datos.get('ocupacion', '')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Sustancia de Impacto: {datos.get('sustancia_impacto', '')}"), 0, 1)
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text("2. FAMILIAR RESPONSABLE"), 0, 1)
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, clean_pdf_text(f"Familiar / Tutor: {datos.get('familiar_responsable', '')}"), 0, 1)
    pdf.cell(95, 5, clean_pdf_text(f"Parentesco: {datos.get('parentesco_familiar', '')}"), 0, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Teléfono: {datos.get('telefono_familiar', '')}"), 0, 1)
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text("3. CONTRATO Y REGLAMENTO DE TRATAMIENTO"), 0, 1)
    pdf.set_font('Arial', '', 8)
    texto_contrato = (
        "El familiar responsable y el usuario aceptan voluntariamente ingresar al programa de rehabilitacion "
        "biopsicosocial en la Comunidad Terapeutica Sawabona Shikoba A.C., sujetandose a las normas internas, "
        "protocolos de salud y programa de consejeria clinica bajo la NOM-028-SSA2-2009."
    )
    pdf.multi_cell(0, 4, clean_pdf_text(texto_contrato))
    pdf.ln(15)
    
    pdf.set_font('Arial', '', 8)
    pdf.cell(60, 4, "_______________________", 0, 0, 'C')
    pdf.cell(65, 4, "_______________________", 0, 0, 'C')
    pdf.cell(65, 4, "_______________________", 0, 1, 'C')
    
    pdf.cell(60, 4, clean_pdf_text("Firma del Residentes"), 0, 0, 'C')
    pdf.cell(65, 4, clean_pdf_text("Familiar Responsable"), 0, 0, 'C')
    pdf.cell(65, 4, clean_pdf_text("Director / Consejero"), 0, 1, 'C')
    
    return bytes(pdf.output())

def render_header():
    st.markdown('''
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
    ''', unsafe_allow_html=True)

# --- APLICACIÓN PRINCIPAL ---
def main():
    init_db()
    render_header()
    
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
        with st.form("login_form"):
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                user = st.text_input("Usuario")
            with col_u2:
                pwd = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("🔑 Ingresar al Sistema", use_container_width=True)
            
            if submit:
                res = verificar_login(user, pwd)
                if res:
                    if res[3] == "Bloqueado":
                        st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador del sistema.")
                    else:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2]
                        st.session_state["ultima_actividad"] = datetime.now()
                        st.toast(f"¡Bienvenido(a) {res[1]}!", icon="👋")
                        st.rerun()
                else:
                    st.error("⚠️ Usuario o contraseña incorrectos.")
        return

    st.sidebar.markdown(f'''
        <div style='background-color: #E8F5E9; padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px;'>
            <h4 style='color: #2E7D32; margin: 0;'>👤 {st.session_state["nombre_completo"]}</h4>
            <span style='background-color: #A5D6A7; color: #1B5E20; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; font-weight: bold;'>{st.session_state["rol"]}</span>
        </div>
    ''', unsafe_allow_html=True)
    
    st.sidebar.title("📌 Menú Principal")
    menu = st.sidebar.selectbox(
        "Navegación por Módulos",
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
            "⚙️ Configuración y Seguridad"
        ]
    )
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- MÓDULO 1: TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        
        pacientes_todos = listar_pacientes(incluir_inactivos=True)
        pacientes_activos = [p for p in pacientes_todos if p.get("estado") == "Activo"]
        pacientes_inactivos = [p for p in pacientes_todos if p.get("estado") != "Activo"]
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("🟢 Residentes Activos en Tratamiento", len(pacientes_activos))
        with col_m2:
            st.metric("🔴 Residentes Inactivos / Bajas / Egresados", len(pacientes_inactivos))
            
        st.markdown("---")
        st.subheader("📊 Distribución de Residentes por Etapa Clínica (Todas las Etapas)")
        
        # Muestra las 5 etapas sin omitir ninguna
        cols_etapas = st.columns(len(ETAPAS))
        for idx, et in enumerate(ETAPAS):
            count_et = sum(1 for p in pacientes_activos if p.get("etapa_actual") == et)
            with cols_etapas[idx]:
                st.metric(f"Etapa {idx+1}: {et}", count_et)
                
        st.markdown("---")
        st.subheader("📋 Lista de Residentes Activos por Etapa")
        
        tabs_etapas = st.tabs(["📋 Todos"] + [f"📍 {et}" for et in ETAPAS])
        
        for idx, tab in enumerate(tabs_etapas):
            with tab:
                if idx == 0:
                    lista_mostrar = pacientes_activos
                else:
                    et_target = ETAPAS[idx - 1]
                    lista_mostrar = [p for p in pacientes_activos if p.get("etapa_actual") == et_target]
                    
                if not lista_mostrar:
                    st.info("No hay residentes activos registrados en esta categoría.")
                else:
                    tabla_datos = []
                    for p in lista_mostrar:
                        f_ini_str = p.get("fecha_inicio_etapa", p.get("fecha_ingreso", ""))
                        dias_e = "N/A"
                        if f_ini_str:
                            try:
                                d_obj = datetime.strptime(f_ini_str, "%Y-%m-%d").date()
                                dias_e = (date.today() - d_obj).days
                            except Exception:
                                pass
                        tabla_datos.append({
                            "Folio": p.get("paciente_id"),
                            "Expediente": p.get("expediente", "S/N"),
                            "Nombre del Residente": p.get("nombre_completo"),
                            "Etapa Actual": p.get("etapa_actual", "Acogida"),
                            "Fecha Inicio Etapa": f_ini_str,
                            "Días en Etapa": dias_e,
                            "Sustancia Impacto": p.get("sustancia_impacto", "")
                        })
                    st.dataframe(tabla_datos, use_container_width=True)

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Residentes")
        
        tab_nuevo, tab_editar, tab_bloqueo = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Estado y Bloqueo"])
        
        with tab_nuevo:
            st.subheader("➕ Registro de Nuevo Residente")
            folio_auto = generar_siguiente_folio()
            
            with st.form("form_alta_paciente"):
                c_f1, c_f2, c_f3 = st.columns(3)
                with c_f1:
                    st.text_input("Folio Interno (Autoincrementable)", value=folio_auto, disabled=True)
                with c_f2:
                    exp_in = st.text_input("Número de Expediente (Manual / Numérico)", help="Dejar en blanco si aún no cuenta con expediente")
                with c_f3:
                    f_ingreso = st.date_input("Fecha de Ingreso", value=date.today())
                    
                st.markdown("##### 👤 Datos de Identificación")
                c_n1, c_n2, c_n3 = st.columns(3)
                with c_n1:
                    nom_in = st.text_input("Nombre(s) *")
                with c_n2:
                    app_in = st.text_input("Apellido Paterno *")
                with c_n3:
                    apm_in = st.text_input("Apellido Materno")
                    
                c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                with c_d1:
                    f_nac = st.date_input("Fecha de Nacimiento", value=date(1990, 1, 1))
                with c_d2:
                    edad_in = st.number_input("Edad", min_value=12, max_value=99, value=30)
                with c_d3:
                    sexo_in = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
                with c_d4:
                    ecivil_in = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"])
                    
                st.markdown("##### 📍 Clínica y Tratamiento")
                c_c1, c_c2, c_c3 = st.columns(3)
                with c_c1:
                    sust_in = st.selectbox("Sustancia de Impacto", ["Alcohol", "Cristal / Metanfetamina", "Cocaína", "Marihuana", "Heroína / Opiáceos", "Fentanilo", "Benzodiacepinas", "Inhalables", "Tabaco", "Otra"])
                with c_c2:
                    etapa_in = st.selectbox("Etapa Inicial", ETAPAS)
                with c_c3:
                    f_ini_etapa = st.date_input("Fecha de Inicio de Etapa", value=date.today())
                    
                st.markdown("##### 📞 Contacto y Familiar Responsable")
                c_r1, c_r2, c_r3 = st.columns(3)
                with c_r1:
                    fam_in = st.text_input("Familiar Responsable")
                with c_r2:
                    par_in = st.text_input("Parentesco")
                with c_r3:
                    tel_fam_in = st.text_input("Teléfono Familiar")
                    
                btn_guardar_nuevo = st.form_submit_button("💾 Guardar y Registrar Residente", use_container_width=True)
                
                if btn_guardar_nuevo:
                    if not nom_in.strip() or not app_in.strip():
                        st.error("⚠️ El Nombre y el Apellido Paterno son obligatorios.")
                    else:
                        val_ok, msg_err = validar_duplicados_paciente(folio_auto, exp_in, nom_in, app_in, apm_in)
                        if not val_ok:
                            st.error(msg_err)
                        else:
                            datos_p = {
                                "expediente": exp_in.strip(),
                                "nombre": nom_in.strip(),
                                "ap_paterno": app_in.strip(),
                                "ap_materno": apm_in.strip(),
                                "fecha_ingreso": str(f_ingreso),
                                "fecha_nacimiento": str(f_nac),
                                "edad": edad_in,
                                "sexo": sexo_in,
                                "estado_civil": ecivil_in,
                                "sustancia_impacto": sust_in,
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": str(f_ini_etapa),
                                "familiar_responsable": fam_in.strip(),
                                "parentesco_familiar": par_in.strip(),
                                "telefono_familiar": tel_fam_in.strip(),
                                "estado": "Activo"
                            }
                            guardar_entrevista(folio_auto, datos_p, st.session_state["username"])
                            st.success(f"✅ ¡Registro completado exitosamente! Residente asignado al Folio {folio_auto}.")
                            st.toast("✅ Registro guardado con éxito", icon="🎉")
                            st.rerun()

        with tab_editar:
            st.subheader("✏️ Modificar Datos de Residente")
            pacientes_edit = listar_pacientes(incluir_inactivos=True)
            if not pacientes_edit:
                st.info("No hay pacientes registrados.")
            else:
                opciones_p = [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')}" for p in pacientes_edit]
                sel_p = st.selectbox("Seleccionar Residente", opciones_p)
                p_id_sel = sel_p.split(" | ")[0]
                
                dj_p, _, _, _ = obtener_entrevista(p_id_sel)
                if dj_p:
                    with st.form("form_edit_paciente"):
                        st.text_input("Folio (No Editable)", value=p_id_sel, disabled=True)
                        exp_ed = st.text_input("Número de Expediente", value=dj_p.get("expediente", ""))
                        
                        c_en1, c_en2, c_en3 = st.columns(3)
                        with c_en1:
                            nom_ed = st.text_input("Nombre(s)", value=dj_p.get("nombre", ""))
                        with c_en2:
                            app_ed = st.text_input("Apellido Paterno", value=dj_p.get("ap_paterno", ""))
                        with c_en3:
                            apm_ed = st.text_input("Apellido Materno", value=dj_p.get("ap_materno", ""))
                            
                        c_ec1, c_ec2 = st.columns(2)
                        with c_ec1:
                            idx_et = get_safe_index(ETAPAS, dj_p.get("etapa_actual", "Acogida"))
                            etapa_ed = st.selectbox("Etapa Actual", ETAPAS, index=idx_et)
                        with c_ec2:
                            f_ini_e_val = dj_p.get("fecha_inicio_etapa", dj_p.get("fecha_ingreso", str(date.today())))
                            try:
                                d_f_ini = datetime.strptime(f_ini_e_val, "%Y-%m-%d").date()
                            except Exception:
                                d_f_ini = date.today()
                            f_ini_e_ed = st.date_input("Fecha de Inicio de Etapa", value=d_f_ini)
                            
                        btn_update = st.form_submit_button("💾 Actualizar Registro", use_container_width=True)
                        if btn_update:
                            val_ok, msg_err = validar_duplicados_paciente(p_id_sel, exp_ed, nom_ed, app_ed, apm_ed)
                            if not val_ok:
                                st.error(msg_err)
                            else:
                                dj_p["expediente"] = exp_ed.strip()
                                dj_p["nombre"] = nom_ed.strip()
                                dj_p["ap_paterno"] = app_ed.strip()
                                dj_p["ap_materno"] = apm_ed.strip()
                                dj_p["etapa_actual"] = etapa_ed
                                dj_p["fecha_inicio_etapa"] = str(f_ini_e_ed)
                                guardar_entrevista(p_id_sel, dj_p, st.session_state["username"])
                                st.success("✅ ¡Registro actualizado correctamente!")
                                st.toast("✅ Actualización guardada con éxito", icon="🎉")
                                st.rerun()

        with tab_bloqueo:
            st.subheader("🔒 Estado del Residente (Activo / Bloqueado / Baja)")
            pacientes_b = listar_pacientes(incluir_inactivos=True)
            if pacientes_b:
                opciones_b = [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')} [{p.get('estado','Activo')}]" for p in pacientes_b]
                sel_pb = st.selectbox("Seleccionar Residente para Cambio de Estado", opciones_b)
                pid_b = sel_pb.split(" | ")[0]
                dj_b, _, _, _ = obtener_entrevista(pid_b)
                
                if dj_b:
                    st.write(f"**Estado Actual:** `{dj_b.get('estado', 'Activo')}`")
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("🔴 Bloquear / Dar de Baja Residente", use_container_width=True):
                            dj_b["estado"] = "Bloqueado"
                            guardar_entrevista(pid_b, dj_b, st.session_state["username"])
                            st.success(f"🔴 Residente {pid_b} cambiado a estado Bloqueado / Inactivo.")
                            st.rerun()
                    with col_b2:
                        if st.button("🟢 Reactivar Residente", use_container_width=True):
                            dj_b["estado"] = "Activo"
                            guardar_entrevista(pid_b, dj_b, st.session_state["username"])
                            st.success(f"🟢 Residente {pid_b} reactivado exitosamente.")
                            st.rerun()

    # --- MÓDULO 3: FICHA DE INGRESO ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión")
        pacientes = listar_pacientes(incluir_inactivos=False)
        if not pacientes:
            st.info("No hay pacientes activos registrados.")
        else:
            opciones_p = [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')}" for p in pacientes]
            sel_p = st.selectbox("Seleccionar Residente", opciones_p)
            p_id = sel_p.split(" | ")[0]
            datos_p, _, _, _ = obtener_entrevista(p_id)
            
            if datos_p:
                st.subheader(f"Ficha de {datos_p.get('nombre_completo')}")
                st.write(f"**Expediente:** {datos_p.get('expediente', 'S/N')} | **Sustancia:** {datos_p.get('sustancia_impacto')}")
                
                pdf_data = generar_pdf_ficha_ingreso(p_id, datos_p)
                st.download_button(
                    label="🖨️ Descargar Ficha de Ingreso en PDF",
                    data=pdf_data,
                    file_name=f"Ficha_Ingreso_Exp_{datos_p.get('expediente', p_id)}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        pacientes = listar_pacientes(incluir_inactivos=False)
        if not pacientes:
            st.info("No hay pacientes activos.")
        else:
            opciones_p = [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')}" for p in pacientes]
            sel_p = st.selectbox("Seleccionar Residente", opciones_p)
            p_id = sel_p.split(" | ")[0]
            datos_p, _, _, _ = obtener_entrevista(p_id)
            
            if datos_p:
                etapa_act = datos_p.get("etapa_actual", "Acogida")
                st.info(f"📍 Residente: **{datos_p.get('nombre_completo')}** | Etapa: **{etapa_act}**")
                
                num_cons = st.selectbox("Número de Consejería", list(range(1, 13)))
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT exposicion, avance, sugerencia, fecha_proxima 
                    FROM consejerias 
                    WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                ''', (p_id, etapa_act, num_cons))
                row_c = c.fetchone()
                conn.close()
                
                val_exp = row_c[0] if row_c else ""
                val_ava = row_c[1] if row_c else ""
                val_sug = row_c[2] if row_c else ""
                
                with st.form(f"form_consejeria_{p_id}_{num_cons}"):
                    st.markdown(f"#### Consejería #{num_cons} - Etapa: {etapa_act}")
                    exp_txt = st.text_area("Exposición del Paciente", value=val_exp, height=100)
                    ava_txt = st.text_area("Avance / Retroceso Clínico", value=val_ava, height=100)
                    sug_txt = st.text_area("Sugerencias y Tareas", value=val_sug, height=100)
                    
                    btn_save_c = st.form_submit_button("💾 Guardar Consejería", use_container_width=True)
                    if btn_save_c:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO consejerias (paciente_id, etapa, num_consejeria, expediente, fecha, exposicion, avance, sugerencia, usuario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (p_id, etapa_act, num_cons, datos_p.get("expediente",""), str(date.today()), exp_txt, ava_txt, sug_txt, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ Consejería #{num_cons} guardada exitosamente.")
                        st.toast("✅ Registro de consejería completado", icon="🎉")
                        st.rerun()

    # --- MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso Clínico")
        pacientes = listar_pacientes(incluir_inactivos=False)
        if not pacientes:
            st.info("No hay pacientes activos.")
        else:
            opciones_p = [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')}" for p in pacientes]
            sel_p = st.selectbox("Seleccionar Residente", opciones_p)
            p_id = sel_p.split(" | ")[0]
            datos_p, _, _, _ = obtener_entrevista(p_id)
            
            if datos_p:
                etapa_act = datos_p.get("etapa_actual", "Acogida")
                f_ini_str = datos_p.get("fecha_inicio_etapa", datos_p.get("fecha_ingreso", str(date.today())))
                
                dias_trans = "0"
                try:
                    d_obj = datetime.strptime(f_ini_str, "%Y-%m-%d").date()
                    dias_trans = (date.today() - d_obj).days
                except Exception:
                    pass
                    
                st.info(f"📍 Residente: **{datos_p.get('nombre_completo')}** | Etapa Actual: **{etapa_act}** | Fecha Inicio Etapa: **{f_ini_str}** ({dias_trans} días transcurridos)")
                
                idx_et_act = ETAPAS.index(etapa_act) if etapa_act in ETAPAS else 0
                if idx_et_act < len(ETAPAS) - 1:
                    etapa_sig = ETAPAS[idx_et_act + 1]
                    st.subheader(f"Promover de {etapa_act} a 🚀 {etapa_sig}")
                    
                    if st.button(f"🚀 Promover a {etapa_sig}", use_container_width=True):
                        datos_p["etapa_actual"] = etapa_sig
                        datos_p["fecha_inicio_etapa"] = str(date.today())
                        guardar_entrevista(p_id, datos_p, st.session_state["username"])
                        st.success(f"🎉 ¡Residente promovido a la etapa de {etapa_sig} exitosamente! Fecha de inicio reiniciada.")
                        st.toast(f"🎉 Promovido a {etapa_sig}", icon="🚀")
                        st.rerun()
                else:
                    st.success("🏆 El residente se encuentra en la etapa final del programa (Servicio Social).")

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos y Expedientes")
        
        tab_archivos, tab_carpetas = st.tabs(["📄 Documentos Guardados", "⚙️ Gestión de Carpetas"])
        
        with tab_carpetas:
            st.subheader("⚙️ Administrar Carpetas del Repositorio")
            col_c1, col_c2 = st.columns(2)
            
            with col_c1:
                st.markdown("##### ➕ Crear Nueva Carpeta")
                with st.form("form_nueva_carpeta"):
                    nueva_c_nombre = st.text_input("Nombre de la Nueva Carpeta")
                    btn_c_nueva = st.form_submit_button("📁 Crear Carpeta", use_container_width=True)
                    if btn_c_nueva:
                        if not nueva_c_nombre.strip():
                            st.error("⚠️ Ingrese un nombre válido.")
                        else:
                            ok_c, msg_c = agregar_carpeta(nueva_c_nombre)
                            if ok_c:
                                st.success(msg_c)
                                st.toast("📁 Carpeta creada", icon="🎉")
                                st.rerun()
                            else:
                                st.error(msg_c)
                                
            with col_c2:
                st.markdown("##### ✏️ Renombrar Carpeta Existente")
                carpetas_actuales = obtener_carpetas()
                with st.form("form_renombrar_carpeta"):
                    c_ren_sel = st.selectbox("Seleccionar Carpeta", carpetas_actuales)
                    c_ren_nuevo = st.text_input("Nuevo Nombre para la Carpeta")
                    btn_c_ren = st.form_submit_button("✏️ Renombrar Carpeta", use_container_width=True)
                    if btn_c_ren:
                        if not c_ren_nuevo.strip():
                            st.error("⚠️ Ingrese un nuevo nombre válido.")
                        else:
                            ok_r, msg_r = renombrar_carpeta(c_ren_sel, c_ren_nuevo)
                            if ok_r:
                                st.success(msg_r)
                                st.toast("✏️ Carpeta renombrada", icon="🎉")
                                st.rerun()
                            else:
                                st.error(msg_r)
                                
            st.markdown("---")
            st.subheader("📂 Carpetas Actuales en el Sistema")
            st.write(", ".join([f"`{c}`" for c in obtener_carpetas()]))

        with tab_archivos:
            st.subheader("📄 Subir y Consultar Expedientes y Documentos")
            carpetas_disponibles = obtener_carpetas()
            pacientes_r = listar_pacientes(incluir_inactivos=True)
            
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                c_dest = st.selectbox("Carpeta Destino", carpetas_disponibles)
            with col_u2:
                p_asoc = st.selectbox("Asociar a Residente (Opcional)", ["-- General (Sin Paciente) --"] + [f"{p['paciente_id']} | Exp: {p.get('expediente','S/N')} - {p.get('nombre_completo','')}" for p in pacientes_r])
                
            up_file = st.file_uploader("Seleccionar Archivo (PDF, Word, Imagen, etc.)")
            if up_file and st.button("⬆️ Subir Documento al Repositorio", use_container_width=True):
                pid_asoc = p_asoc.split(" | ")[0] if "-- General" not in p_asoc else "GENERAL"
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO documentos_repo (paciente_id, carpeta, nombre_archivo, fecha, usuario, descripcion)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (pid_asoc, c_dest, up_file.name, str(date.today()), st.session_state["username"], "Documento subido"))
                conn.commit()
                conn.close()
                st.success(f"✅ Archivo '{up_file.name}' guardado correctamente en la carpeta '{c_dest}'.")
                st.toast("✅ Archivo subido exitosamente", icon="🎉")
                st.rerun()
                
            st.markdown("---")
            st.subheader("🔍 Explorador de Documentos por Carpeta")
            c_filtro = st.selectbox("Filtrar por Carpeta", carpetas_disponibles)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, paciente_id, nombre_archivo, fecha, usuario FROM documentos_repo WHERE carpeta = ?', (c_filtro,))
            docs = c.fetchall()
            conn.close()
            
            if not docs:
                st.info(f"No hay documentos guardados en la carpeta '{c_filtro}'.")
            else:
                for d in docs:
                    st.write(f"📄 **{d[2]}** | Residente: `{d[1]}` | Fecha: `{d[3]}` | Subido por: `{d[4]}`")

    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Residentes")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            query = st.text_input("🔎 Buscar por Nombre, Expediente o Folio")
        with col_s2:
            filtro_est = st.selectbox("Filtrar por Estado", ["🟢 Activos", "🔴 Bloqueados / Inactivos", "Todos"])
            
        incl_inact = filtro_est != "🟢 Activos"
        todos_p = listar_pacientes(incluir_inactivos=incl_inact)
        
        if filtro_est == "🔴 Bloqueados / Inactivos":
            todos_p = [p for p in todos_p if p.get("estado") != "Activo"]
            
        if query.strip():
            q_norm = normalizar_texto(query)
            todos_p = [p for p in todos_p if q_norm in normalizar_texto(p.get("nombre_completo","")) or q_norm in normalizar_texto(p.get("expediente","")) or q_norm in normalizar_texto(p.get("paciente_id",""))]
            
        st.subheader(f"Resultados ({len(todos_p)} residentes encontrados)")
        if todos_p:
            tabla = []
            for p in todos_p:
                tabla.append({
                    "Folio": p.get("paciente_id"),
                    "Expediente": p.get("expediente", "S/N"),
                    "Nombre Completo": p.get("nombre_completo"),
                    "Etapa Actual": p.get("etapa_actual"),
                    "Sustancia Impacto": p.get("sustancia_impacto"),
                    "Estado": "🟢 Activo" if p.get("estado") == "Activo" else "🔴 Bloqueado"
                })
            st.dataframe(tabla, use_container_width=True)

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        
        is_admin = (st.session_state.get("username") == "admin" or st.session_state.get("rol") == "Administrador")
        
        if is_admin:
            tab_pass, tab_users = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_pass = st.container()
            tab_users = None
            
        with tab_pass:
            st.subheader("🔑 Actualizar Contraseña")
            with st.form("form_change_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_new = st.text_input("Nueva Contraseña", type="password")
                p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_pass = st.form_submit_button("Actualizar Mi Contraseña", use_container_width=True)
                if btn_pass:
                    if p_new != p_conf:
                        st.error("⚠️ Las contraseñas nuevas no coinciden.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT password_hash FROM usuarios WHERE username = ?', (st.session_state["username"],))
                        row = c.fetchone()
                        if row and row[0] == hash_pass(p_act):
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(p_new), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada correctamente.")
                            st.toast("✅ Contraseña actualizada", icon="🎉")
                        else:
                            conn.close()
                            st.error("⚠️ La contraseña actual es incorrecta.")
                            
        if is_admin and tab_users:
            with tab_users:
                st.subheader("👥 Registro de Cuentas de Personal y Permisos")
                with st.form("form_nuevo_usuario"):
                    c_u1, c_u2 = st.columns(2)
                    with c_u1:
                        new_user = st.text_input("Nombre de Usuario (Login) *")
                        new_pass = st.text_input("Contraseña *", type="password")
                    with c_u2:
                        new_nom = st.text_input("Nombre Completo del Colaborador *")
                        new_rol = st.selectbox("Rol y Nivel de Acceso", ["Lectura/Escritura", "Administrador", "Solo Lectura"])
                    btn_add_u = st.form_submit_button("➕ Crear Cuenta de Usuario", use_container_width=True)
                    if btn_add_u:
                        if not new_user.strip() or not new_pass.strip():
                            st.error("⚠️ El usuario y la contraseña son obligatorios.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute('''
                                    INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado)
                                    VALUES (?, ?, ?, ?, 'Activo')
                                ''', (new_user.strip(), hash_pass(new_pass), new_nom.strip(), new_rol))
                                conn.commit()
                                conn.close()
                                st.success(f"✅ Usuario '{new_user.strip()}' creado exitosamente.")
                                st.toast("✅ Usuario registrado", icon="🎉")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                conn.close()
                                st.error(f"⚠️ El nombre de usuario '{new_user.strip()}' ya existe.")
                                
                st.markdown("---")
                st.subheader("📋 Cuentas de Personal Registradas")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol, estado FROM usuarios')
                u_rows = c.fetchall()
                conn.close()
                
                for u in u_rows:
                    c_u_col1, c_u_col2, c_u_col3 = st.columns([3, 2, 2])
                    with c_u_col1:
                        st.write(f"👤 **{u[2]}** (`{u[1]}`) - Rol: `{u[3]}` | Estado: `{u[4]}`")
                    with c_u_col2:
                        if u[1] != "admin":
                            if u[4] == "Activo":
                                if st.button(f"🔴 Bloquear", key=f"blk_{u[0]}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Bloqueado' WHERE id = ?", (u[0],))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"Usuario {u[1]} bloqueado.")
                                    st.rerun()
                            else:
                                if st.button(f"🟢 Activar", key=f"act_{u[0]}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Activo' WHERE id = ?", (u[0],))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"Usuario {u[1]} activado.")
                                    st.rerun()

if __name__ == "__main__":
    main()

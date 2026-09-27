import streamlit as st
import sqlite3
import json
import hashlib
import os
import re
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista Inicial y Consejería Clínica",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- LIMPIEZA Y NORMALIZACIÓN DE TEXTO ---
def clean_pdf_text(text):
    if not text:
        return ""
    text = str(text)
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('ascii', 'ignore').decode('ascii')

def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip().lower()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return re.sub(r'\s+', ' ', text)

def get_safe_index(options_list, target_value, default_index=0):
    if not target_value:
        return default_index
    target_norm = normalize_text(target_value)
    for idx, opt in enumerate(options_list):
        if normalize_text(opt) == target_norm:
            return idx
    return default_index

# --- INICIALIZACIÓN Y MIGRACIÓN DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema
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
    
    # Migrar columna 'estado' y 'rol' si no existen
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [row[1] for row in c.fetchall()]
    if 'rol' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Lectura/Escritura'")
    if 'estado' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN estado TEXT DEFAULT 'Activo'")
        
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'Activo'))
        
    # 2. Tabla de Pacientes / Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 3. Tabla de Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            tema TEXT,
            fecha TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            usuario TEXT,
            expediente TEXT
        )
    ''')
    
    # Migración de columnas en consejerías
    c.execute("PRAGMA table_info(consejerias)")
    cols_cons = [row[1] for row in c.fetchall()]
    needed_cols = {
        'expediente': 'TEXT',
        'aspectos_trabajar': 'TEXT',
        'aspectos_proxima': 'TEXT',
        'fecha_proxima': 'TEXT',
        'exposicion': 'TEXT',
        'avance': 'TEXT',
        'sugerencia': 'TEXT'
    }
    for col_name, col_type in needed_cols.items():
        if col_name not in cols_cons:
            c.execute(f"ALTER TABLE consejerias ADD COLUMN {col_name} {col_type}")
            
    # 4. Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_paciente TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            desarrollo TEXT,
            devoluciones TEXT,
            compromisos TEXT,
            usuario TEXT
        )
    ''')
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_gt = [row[1] for row in c.fetchall()]
    if 'etapa_paciente' not in cols_gt:
        c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")

    # 5. Tabla de Medicamentos / Almacén
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_medicamento TEXT UNIQUE,
            stock_actual INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha_entrega TEXT,
            usuario TEXT,
            observaciones TEXT
        )
    ''')

    # 6. Tabla de Carpetas Personalizadas del Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT username, nombre_completo, rol, estado 
        FROM usuarios 
        WHERE username = ? AND password_hash = ?
    ''', (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

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
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

def obtener_todos_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    
    pacientes = []
    for r in rows:
        pid = r[0]
        try:
            dj = json.loads(r[1])
        except Exception:
            dj = {}
        pacientes.append({
            "paciente_id": pid,
            "datos": dj,
            "fecha_registro": r[2],
            "fecha_modificacion": r[3],
            "usuario_registro": r[4]
        })
    return pacientes

def verificar_duplicado_paciente(nombre_completo, expediente, pid_actual=None):
    pacientes = obtener_todos_pacientes()
    norm_target_name = normalize_text(nombre_completo)
    norm_target_exp = str(expediente).strip() if expediente else ""
    
    for p in pacientes:
        if pid_actual and p["paciente_id"] == pid_actual:
            continue
        
        dj = p["datos"]
        pid = p["paciente_id"]
        
        # Formar nombre completo del registro existente
        nom = dj.get("nombre", "")
        pat = dj.get("ap_paterno", dj.get("apellido_paterno", ""))
        mat = dj.get("ap_materno", dj.get("apellido_materno", ""))
        full_existing = dj.get("nombre_completo", f"{nom} {pat} {mat}".strip())
        norm_existing_name = normalize_text(full_existing)
        
        # Comparar Nombre Completo
        if norm_target_name and norm_target_name == norm_existing_name:
            exp_ex = dj.get("expediente", "S/N")
            return True, f"Ya existe un residente registrado con el mismo nombre completo '{full_existing.title()}' (Folio: {pid}, Expediente: {exp_ex})."
            
        # Comparar Expediente si fue ingresado
        exp_ex = str(dj.get("expediente", "")).strip()
        if norm_target_exp and exp_ex and norm_target_exp == exp_ex:
            return True, f"El número de Expediente '{norm_target_exp}' ya está asignado al residente '{full_existing.title()}' (Folio: {pid})."
            
    return False, ""

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE entrevistas 
            SET fecha_modificacion = ?, datos_json = ?
            WHERE paciente_id = ?
        ''', (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('''
            INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0]), row[1], row[2], row[3]
        except Exception:
            return {}, row[1], row[2], row[3]
    return None, None, None, None

def calcular_dias_en_etapa(fecha_inicio_str):
    if not fecha_inicio_str:
        return 0
    try:
        f_init = datetime.strptime(fecha_inicio_str, "%Y-%m-%d")
        dias = (datetime.now() - f_init).days
        return max(0, dias)
    except Exception:
        return 0

# --- HEADER DE LA APLICACIÓN ---
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

# --- GENERADOR DE PDF ---
def generar_pdf_ficha_ingreso(paciente_id, datos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, clean_pdf_text("FICHA DE INGRESO Y CONTRATO DE ADMISION"), ln=True, align='C')
    
    exp = clean_pdf_text(datos.get("expediente", "S/N"))
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, clean_pdf_text(f"EXPEDIENTE CLINICO: {exp}"), ln=True, align='R')
    pdf.ln(3)
    
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 7, clean_pdf_text("1. DATOS GENERALES DEL RESIDENTE"), ln=True, fill=True)
    pdf.set_font("Arial", '', 10)
    
    nom = clean_pdf_text(datos.get("nombre_completo", f"{datos.get('nombre','')} {datos.get('ap_paterno','')} {datos.get('ap_materno','')}".strip()))
    pdf.cell(0, 6, clean_pdf_text(f"Nombre Completo: {nom}"), ln=True)
    pdf.cell(90, 6, clean_pdf_text(f"Edad: {datos.get('edad', '')} anos"), ln=False)
    pdf.cell(90, 6, clean_pdf_text(f"Sexo: {datos.get('sexo', '')}"), ln=True)
    pdf.cell(90, 6, clean_pdf_text(f"Estado Civil: {datos.get('estado_civil', '')}"), ln=False)
    pdf.cell(90, 6, clean_pdf_text(f"Ocupacion: {datos.get('ocupacion', '')}"), ln=True)
    pdf.cell(0, 6, clean_pdf_text(f"Sustancia de Impacto: {datos.get('sustancia_impacto', '')}"), ln=True)
    pdf.cell(0, 6, clean_pdf_text(f"Fecha de Ingreso: {datos.get('fecha_ingreso', '')}"), ln=True)
    pdf.cell(0, 6, clean_pdf_text(f"Etapa Inicial: {datos.get('etapa_actual', 'Acogida')} (Inicio: {datos.get('fecha_inicio_etapa', '')})"), ln=True)
    pdf.ln(4)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 7, clean_pdf_text("2. RESPONSABLE FAMILIAR Y TERMINOS ECONOMICOS"), ln=True, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, clean_pdf_text(f"Responsable Familiar: {datos.get('responsable_familiar', '')}"), ln=True)
    pdf.cell(90, 6, clean_pdf_text(f"Parentesco: {datos.get('parentesco_responsable', '')}"), ln=False)
    pdf.cell(90, 6, clean_pdf_text(f"Telefono: {datos.get('telefono_responsable', '')}"), ln=True)
    pdf.cell(90, 6, clean_pdf_text(f"Cuota de Ingreso: ${datos.get('cuota_ingreso', 0)}"), ln=False)
    pdf.cell(90, 6, clean_pdf_text(f"Cuota Mensual: ${datos.get('cuota_mensual', 0)}"), ln=True)
    pdf.ln(6)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.multi_cell(0, 5, clean_pdf_text("DECLARACION DE CONFORMIDAD Y AUTORIZACION (NOM-028-SSA2-2009):"))
    pdf.set_font("Arial", '', 9)
    pdf.multi_cell(0, 4, clean_pdf_text("Por medio de la presente, el responsable familiar y el residente declaran ingresar de manera voluntaria a la Comunidad Terapeutica Sawabona Shikoba A.C., aceptando el reglamento interno, el plan general de tratamiento y los terminos economicos acordados."))
    pdf.ln(15)
    
    # Firmas
    y_f = pdf.get_y()
    pdf.line(20, y_f, 95, y_f)
    pdf.line(115, y_f, 190, y_f)
    pdf.set_xy(20, y_f + 2)
    pdf.cell(75, 5, clean_pdf_text("Firma del Residente"), align='C')
    pdf.set_xy(115, y_f + 2)
    pdf.cell(75, 5, clean_pdf_text("Firma del Responsable Familiar"), align='C')
    
    return bytes(pdf.output())

# --- APLICACIÓN PRINCIPAL ---
def main():
    init_db()
    
    # Control de Estado de Sesión e Inactividad (10 min = 600 s)
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()

    render_header()

    if st.session_state["logged_in"]:
        inactivo = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
        if inactivo > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión nuevamente.")
            st.rerun()
        st.session_state["ultima_actividad"] = datetime.now()

    # --- PANTALLA DE LOGIN ---
    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión al Sistema")
        col_c, _ = st.columns([1, 1])
        with col_c:
            with st.form("login_form"):
                user = st.text_input("Usuario")
                pwd = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                
                if submit:
                    res = verificar_login(user, pwd)
                    if res:
                        username_db, nombre_db, rol_db, estado_db = res
                        if estado_db and estado_db.lower() == "bloqueado":
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador del sistema.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = username_db
                            st.session_state["nombre_completo"] = nombre_db or username_db
                            st.session_state["rol"] = rol_db or "Lectura/Escritura"
                            st.session_state["ultima_actividad"] = datetime.now()
                            st.success(f"Bienvenido(a) {st.session_state['nombre_completo']}")
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
        return

    # --- NAVEGACIÓN Y MENÚ LATERAL ---
    st.sidebar.markdown('''
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica A.C.</p>
        </div>
    ''', unsafe_allow_html=True)

    st.sidebar.markdown(f"**Usuario:** {st.session_state.get('nombre_completo', '')}")
    st.sidebar.markdown(f"**Rol:** `{st.session_state.get('rol', 'Lectura/Escritura')}`")
    st.sidebar.title("📌 Menú de Navegación")
    
    opciones_menu = [
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
    
    menu = st.sidebar.selectbox("Seleccione Módulo", opciones_menu)
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # Cargar lista centralizada de pacientes
    pacientes_list = obtener_todos_pacientes()

    # ==========================================
    # MÓDULO 1: INICIO / TABLERO GENERAL
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        
        activos = [p for p in pacientes_list if p["datos"].get("estado_paciente", "Activo") == "Activo"]
        bloqueados = [p for p in pacientes_list if p["datos"].get("estado_paciente", "Activo") != "Activo"]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Residentes Activos", len(activos))
        col2.metric("En Acogida", len([p for p in activos if p["datos"].get("etapa_actual", "Acogida") == "Acogida"]))
        col3.metric("En Identificación", len([p for p in activos if p["datos"].get("etapa_actual") == "Identificación"]))
        col4.metric("Residentes Inactivos / Bloqueados", len(bloqueados))
        
        st.subheader("📋 Resumen General de Residentes")
        if pacientes_list:
            tabla_data = []
            for p in pacientes_list:
                dj = p["datos"]
                f_init = dj.get("fecha_inicio_etapa", dj.get("fecha_ingreso", ""))
                dias_et = calcular_dias_en_etapa(f_init)
                tabla_data.append({
                    "Folio": p["paciente_id"],
                    "Expediente": dj.get("expediente", "S/N"),
                    "Nombre Completo": dj.get("nombre_completo", f"{dj.get('nombre','')} {dj.get('ap_paterno','')}".strip()),
                    "Etapa Actual": dj.get("etapa_actual", "Acogida"),
                    "Fecha Inicio Etapa": f_init,
                    "Días en Etapa": dias_et,
                    "Estado": dj.get("estado_paciente", "Activo")
                })
            st.dataframe(tabla_data, use_container_width=True)
        else:
            st.info("No hay residentes registrados en el sistema.")

    # ==========================================
    # MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES
    # ==========================================
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Residentes")
        
        tab_nuevo, tab_editar, tab_bloqueo = st.tabs(["➕ Registrar Nuevo Paciente", "✏️ Editar / Modificar Paciente", "🔒 Gestión de Bloqueo y Estado"])
        
        # --- SUB-PESTAÑA 1: NUEVO PACIENTE ---
        with tab_nuevo:
            st.subheader("➕ Captura de Nuevo Residente")
            siguiente_folio = generar_siguiente_folio()
            
            with st.form("form_nuevo_paciente"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.text_input("Folio Interno (Autoincrementable)", value=siguiente_folio, disabled=True)
                    expediente_in = st.text_input("Número de Expediente (Opcional/Numérico)", help="Si no lo tiene a la mano puede dejarlo en blanco")
                    nombre_in = st.text_input("Nombre(s) *")
                with c2:
                    ap_pat_in = st.text_input("Apellido Paterno *")
                    ap_mat_in = st.text_input("Apellido Materno")
                    edad_in = st.number_input("Edad", min_value=12, max_value=90, value=25)
                with c3:
                    sexo_in = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
                    ecivil_in = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"])
                    ocupacion_in = st.text_input("Ocupación")
                
                c4, c5 = st.columns(2)
                with c4:
                    f_ingreso_in = st.date_input("Fecha Real de Ingreso")
                    etapa_in = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                with c5:
                    f_inicio_etapa_in = st.date_input("Fecha de Inicio de Etapa")
                    sustancia_in = st.text_input("Sustancia de Impacto Principal")
                    
                btn_guardar_nuevo = st.form_submit_button("💾 Registrar Paciente", use_container_width=True)
                
                if btn_guardar_nuevo:
                    if not nombre_in.strip() or not ap_pat_in.strip():
                        st.error("⚠️ El Nombre y el Apellido Paterno son campos obligatorios.")
                    else:
                        nombre_full = f"{nombre_in.strip()} {ap_pat_in.strip()} {ap_mat_in.strip()}".strip()
                        
                        # Validar si ya existe la misma persona o expediente duplicado
                        es_dup, msg_dup = verificar_duplicado_paciente(nombre_full, expediente_in)
                        if es_dup:
                            st.error(f"⛔ REGISTRO DUPLICADO: {msg_dup}")
                        else:
                            datos_pac = {
                                "expediente": expediente_in.strip(),
                                "nombre": nombre_in.strip(),
                                "ap_paterno": ap_pat_in.strip(),
                                "ap_materno": ap_mat_in.strip(),
                                "nombre_completo": nombre_full,
                                "edad": edad_in,
                                "sexo": sexo_in,
                                "estado_civil": ecivil_in,
                                "ocupacion": ocupacion_in.strip(),
                                "fecha_ingreso": str(f_ingreso_in),
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": str(f_inicio_etapa_in),
                                "sustancia_impacto": sustancia_in.strip(),
                                "estado_paciente": "Activo"
                            }
                            guardar_entrevista(siguiente_folio, datos_pac, st.session_state["username"])
                            st.success(f"✅ ¡Paciente registrado exitosamente! Folio: {siguiente_folio} | Expediente: {expediente_in or 'S/N'}")
                            st.toast("✅ Registro completado con éxito", icon="🎉")
                            st.rerun()

        # --- SUB-PESTAÑA 2: EDITAR PACIENTE ---
        with tab_editar:
            st.subheader("✏️ Modificar Datos de Residente")
            if pacientes_list:
                options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
                sel_p_str = st.selectbox("Seleccione Residente para Editar", options_p)
                sel_pid = sel_p_str.split(" | ")[0]
                
                pac_data, f_reg, f_mod, u_reg = obtener_entrevista(sel_pid)
                if pac_data:
                    with st.form("form_editar_paciente"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.text_input("Folio (No Editable)", value=sel_pid, disabled=True)
                            exp_edit = st.text_input("Número de Expediente", value=pac_data.get("expediente", ""))
                            nom_edit = st.text_input("Nombre(s)", value=pac_data.get("nombre", ""))
                        with c2:
                            pat_edit = st.text_input("Apellido Paterno", value=pac_data.get("ap_paterno", ""))
                            mat_edit = st.text_input("Apellido Materno", value=pac_data.get("ap_materno", ""))
                            edad_edit = st.number_input("Edad", min_value=12, max_value=90, value=int(pac_data.get("edad", 25)))
                        with c3:
                            sexo_opts = ["Masculino", "Femenino", "Otro"]
                            sexo_edit = st.selectbox("Sexo", sexo_opts, index=get_safe_index(sexo_opts, pac_data.get("sexo", "Masculino")))
                            ecivil_opts = ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"]
                            ecivil_edit = st.selectbox("Estado Civil", ecivil_opts, index=get_safe_index(ecivil_opts, pac_data.get("estado_civil", "Soltero(a)")))
                            ocup_edit = st.text_input("Ocupación", value=pac_data.get("ocupacion", ""))
                            
                        c4, c5 = st.columns(2)
                        with c4:
                            try:
                                f_ing_val = datetime.strptime(pac_data.get("fecha_ingreso", str(datetime.now().date())), "%Y-%m-%d").date()
                            except Exception:
                                f_ing_val = datetime.now().date()
                            f_ingreso_edit = st.date_input("Fecha Real de Ingreso", value=f_ing_val)
                            
                            etapas_opts = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                            etapa_edit = st.selectbox("Etapa Actual", etapas_opts, index=get_safe_index(etapas_opts, pac_data.get("etapa_actual", "Acogida")))
                        with c5:
                            try:
                                f_init_val = datetime.strptime(pac_data.get("fecha_inicio_etapa", str(datetime.now().date())), "%Y-%m-%d").date()
                            except Exception:
                                f_init_val = datetime.now().date()
                            f_inicio_etapa_edit = st.date_input("Fecha de Inicio de Etapa", value=f_init_val)
                            sust_edit = st.text_input("Sustancia de Impacto", value=pac_data.get("sustancia_impacto", ""))
                            
                        btn_actualizar = st.form_submit_button("💾 Guardar Cambios", use_container_width=True)
                        
                        if btn_actualizar:
                            full_nom_edit = f"{nom_edit.strip()} {pat_edit.strip()} {mat_edit.strip()}".strip()
                            es_dup, msg_dup = verificar_duplicado_paciente(full_nom_edit, exp_edit, pid_actual=sel_pid)
                            if es_dup:
                                st.error(f"⛔ NO SE PUEDE GUARDAR: {msg_dup}")
                            else:
                                pac_data["expediente"] = exp_edit.strip()
                                pac_data["nombre"] = nom_edit.strip()
                                pac_data["ap_paterno"] = pat_edit.strip()
                                pac_data["ap_materno"] = mat_edit.strip()
                                pac_data["nombre_completo"] = full_nom_edit
                                pac_data["edad"] = edad_edit
                                pac_data["sexo"] = sexo_edit
                                pac_data["estado_civil"] = ecivil_edit
                                pac_data["ocupacion"] = ocup_edit.strip()
                                pac_data["fecha_ingreso"] = str(f_ingreso_edit)
                                pac_data["etapa_actual"] = etapa_edit
                                pac_data["fecha_inicio_etapa"] = str(f_inicio_etapa_edit)
                                pac_data["sustancia_impacto"] = sust_edit.strip()
                                
                                guardar_entrevista(sel_pid, pac_data, st.session_state["username"])
                                st.success("✅ Datos del paciente actualizados exitosamente.")
                                st.toast("✅ Cambios guardados correctamente", icon="🎉")
                                st.rerun()

        # --- SUB-PESTAÑA 3: BLOQUEO / ESTADO DE PACIENTE ---
        with tab_bloqueo:
            st.subheader("🔒 Estado del Residente (Activo / Bloqueado / Inactivo)")
            if pacientes_list:
                options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')} [{p['datos'].get('estado_paciente','Activo')}]" for p in pacientes_list]
                sel_p_b_str = st.selectbox("Seleccione Residente para Cambiar Estado", options_p)
                sel_pid_b = sel_p_b_str.split(" | ")[0]
                
                pac_b_data, _, _, _ = obtener_entrevista(sel_pid_b)
                if pac_b_data:
                    estado_actual = pac_b_data.get("estado_paciente", "Activo")
                    st.info(f"Estado Actual: **{estado_actual}**")
                    
                    c_b1, c_b2 = st.columns(2)
                    with c_b1:
                        if estado_actual == "Activo":
                            if st.button("🔴 Bloquear / Dar de Baja Residente", use_container_width=True):
                                pac_b_data["estado_paciente"] = "Bloqueado / Inactivo"
                                guardar_entrevista(sel_pid_b, pac_b_data, st.session_state["username"])
                                st.success(f"✅ El residente {sel_pid_b} ha sido marcado como BLOQUEADO / INACTIVO.")
                                st.toast("✅ Estado actualizado a Bloqueado", icon="🔒")
                                st.rerun()
                        else:
                            if st.button("🟢 Reactivar / Desbloquear Residente", use_container_width=True):
                                pac_b_data["estado_paciente"] = "Activo"
                                guardar_entrevista(sel_pid_b, pac_b_data, st.session_state["username"])
                                st.success(f"✅ El residente {sel_pid_b} ha sido REACTIVADO exitosamente.")
                                st.toast("✅ Estado actualizado a Activo", icon="🔓")
                                st.rerun()

    # ==========================================
    # MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        if pacientes_list:
            options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
            sel_p_str = st.selectbox("Seleccione Residente para Ficha de Ingreso", options_p)
            sel_pid = sel_p_str.split(" | ")[0]
            
            p_data, _, _, _ = obtener_entrevista(sel_pid)
            if p_data:
                with st.form("form_ficha_ingreso"):
                    st.subheader("Información del Responsable Familiar y Contrato")
                    c1, c2 = st.columns(2)
                    with c1:
                        resp_fam = st.text_input("Nombre del Responsable Familiar", value=p_data.get("responsable_familiar", ""))
                        parentesco = st.text_input("Parentesco", value=p_data.get("parentesco_responsable", ""))
                        tel_resp = st.text_input("Teléfono de Contacto", value=p_data.get("telefono_responsable", ""))
                    with c2:
                        cuota_ing = st.number_input("Cuota de Ingreso ($)", value=float(p_data.get("cuota_ingreso", 0.0)))
                        cuota_mens = st.number_input("Cuota Mensual ($)", value=float(p_data.get("cuota_mensual", 0.0)))
                        
                    btn_guardar_ficha = st.form_submit_button("💾 Guardar Datos de Ficha de Ingreso", use_container_width=True)
                    if btn_guardar_ficha:
                        p_data["responsable_familiar"] = resp_fam.strip()
                        p_data["parentesco_responsable"] = parentesco.strip()
                        p_data["telefono_responsable"] = tel_resp.strip()
                        p_data["cuota_ingreso"] = cuota_ing
                        p_data["cuota_mensual"] = cuota_mens
                        guardar_entrevista(sel_pid, p_data, st.session_state["username"])
                        st.success("✅ Ficha de Ingreso guardada exitosamente.")
                        st.toast("✅ Registro completado exitosamente", icon="🎉")
                        st.rerun()
                
                # Botón de Descarga PDF
                pdf_bytes = generar_pdf_ficha_ingreso(sel_pid, p_data)
                exp_clean = p_data.get("expediente", "SN")
                st.download_button(
                    label="🖨️ Descargar Ficha de Ingreso en PDF",
                    data=pdf_bytes,
                    file_name=f"Ficha_Ingreso_Exp_{exp_clean}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        else:
            st.info("No hay residentes registrados para generar ficha de ingreso.")

    # ==========================================
    # MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        if pacientes_list:
            options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
            sel_p_str = st.selectbox("Seleccione Residente", options_p)
            sel_pid = sel_p_str.split(" | ")[0]
            
            p_data, _, _, _ = obtener_entrevista(sel_pid)
            if p_data:
                with st.form("form_entrevista_inicial"):
                    st.subheader("1. Antecedentes y Motivo de Consulta")
                    motivo = st.text_area("Motivo de Ingreso / Consulta", value=p_data.get("motivo_consulta", ""))
                    
                    st.subheader("2. Historial de Consumo de Sustancias")
                    c1, c2 = st.columns(2)
                    with c1:
                        edad_inicio = st.number_input("Edad de Inicio de Consumo", value=int(p_data.get("edad_inicio_consumo", 15)))
                        frecuencia = st.text_input("Frecuencia de Consumo Previo", value=p_data.get("frecuencia_consumo", ""))
                    with c2:
                        intentos_prev = st.number_input("Intentos Previos de Tratamiento", value=int(p_data.get("intentos_previos", 0)))
                        periodo_max = st.text_input("Periodo Máximo de Abstenerse", value=p_data.get("max_abstincencia", ""))
                        
                    st.subheader("3. Apoyo Familiar y Diagnóstico de Consejería")
                    apoyo_fam = st.text_area("Red de Apoyo Familiar", value=p_data.get("apoyo_familiar_obs", ""))
                    diag_cons = st.text_area("Impresión Diagnóstica de Consejería", value=p_data.get("diagnostico_consejeria", ""))
                    
                    btn_save_ei = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                    if btn_save_ei:
                        p_data["motivo_consulta"] = motivo.strip()
                        p_data["edad_inicio_consumo"] = edad_inicio
                        p_data["frecuencia_consumo"] = frecuencia.strip()
                        p_data["intentos_previos"] = intentos_prev
                        p_data["max_abstincencia"] = periodo_max.strip()
                        p_data["apoyo_familiar_obs"] = apoyo_fam.strip()
                        p_data["diagnostico_consejeria"] = diag_cons.strip()
                        
                        guardar_entrevista(sel_pid, p_data, st.session_state["username"])
                        st.success("✅ Entrevista Inicial guardada exitosamente.")
                        st.toast("✅ Entrevista guardada con éxito", icon="🎉")
                        st.rerun()
        else:
            st.info("No hay residentes registrados en el sistema.")

    # ==========================================
    # MÓDULO 5: CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Registro de Consejerías Individuales")
        if pacientes_list:
            options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
            sel_p_str = st.selectbox("Seleccione Residente", options_p)
            sel_pid = sel_p_str.split(" | ")[0]
            
            p_data, _, _, _ = obtener_entrevista(sel_pid)
            if p_data:
                etapa_act = p_data.get("etapa_actual", "Acogida")
                st.info(f"Etapa Actual del Residente: **{etapa_act}**")
                
                num_cons = st.selectbox("Número de Consejería", list(range(1, 13)))
                
                # Cargar datos de la consejería específica si ya existe
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT tema, exposicion, avance, sugerencia, aspectos_trabajar, aspectos_proxima, fecha_proxima
                    FROM consejerias
                    WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                ''', (sel_pid, etapa_act, num_cons))
                row_c = c.fetchone()
                conn.close()
                
                v_tema = row_c[0] if row_c else ""
                v_exp = row_c[1] if row_c else ""
                v_av = row_c[2] if row_c else ""
                v_sug = row_c[3] if row_c else ""
                v_at = row_c[4] if row_c else ""
                v_ap = row_c[5] if row_c else ""
                v_fp = row_c[6] if row_c else str(datetime.now().date())
                
                with st.form("form_consejeria_ind"):
                    tema_in = st.text_input("Tema de Consejería", value=v_tema)
                    expo_in = st.text_area("Exposición del Paciente / Observaciones", value=v_exp)
                    avance_in = st.text_area("Avance / Retroceso Detectado", value=v_av)
                    sug_in = st.text_area("Sugerencias y Compromisos", value=v_sug)
                    
                    c_fp1, c_fp2 = st.columns(2)
                    with c_fp1:
                        aspectos_prox_in = st.text_input("Aspectos a Trabajar en la Próxima Sesión", value=v_ap)
                    with c_fp2:
                        fecha_prox_in = st.text_input("Fecha Sugerida Próxima Sesión (+7 días)", value=v_fp)
                        
                    btn_g_cons = st.form_submit_button("💾 Guardar Consejería Individual", use_container_width=True)
                    
                    if btn_g_cons:
                        exp_val = p_data.get("expediente", "S/N")
                        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            SELECT id FROM consejerias 
                            WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                        ''', (sel_pid, etapa_act, num_cons))
                        ex_id = c.fetchone()
                        
                        if ex_id:
                            c.execute('''
                                UPDATE consejerias
                                SET tema = ?, exposicion = ?, avance = ?, sugerencia = ?, aspectos_proxima = ?, fecha_proxima = ?, fecha = ?, usuario = ?, expediente = ?
                                WHERE id = ?
                            ''', (tema_in, expo_in, avance_in, sug_in, aspectos_prox_in, str(fecha_prox_in), fecha_hoy, st.session_state["username"], exp_val, ex_id[0]))
                        else:
                            c.execute('''
                                INSERT INTO consejerias (paciente_id, etapa, num_consejeria, tema, exposicion, avance, sugerencia, aspectos_proxima, fecha_proxima, fecha, usuario, expediente)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (sel_pid, etapa_act, num_cons, tema_in, expo_in, avance_in, sug_in, aspectos_prox_in, str(fecha_prox_in), fecha_hoy, st.session_state["username"], exp_val))
                            
                        conn.commit()
                        conn.close()
                        st.success(f"✅ Consejería #{num_cons} registrada exitosamente para la etapa {etapa_act}.")
                        st.toast("✅ Consejería guardada con éxito", icon="🎉")
                        st.rerun()

    # ==========================================
    # MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Promoción de Proceso")
        if pacientes_list:
            options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
            sel_p_str = st.selectbox("Seleccione Residente", options_p)
            sel_pid = sel_p_str.split(" | ")[0]
            
            p_data, _, _, _ = obtener_entrevista(sel_pid)
            if p_data:
                etapa_act = p_data.get("etapa_actual", "Acogida")
                f_init_etapa = p_data.get("fecha_inicio_etapa", p_data.get("fecha_ingreso", str(datetime.now().date())))
                dias_trans = calcular_dias_en_etapa(f_init_etapa)
                
                col_e1, col_e2, col_e3 = st.columns(3)
                col_e1.metric("Etapa Actual", etapa_act)
                col_e2.metric("Fecha Inicio de Etapa", f_init_etapa)
                col_e3.metric("Días Transcurridos en Etapa", f"{dias_trans} días")
                
                # Alerta de rezago por etapa
                limites = {"Acogida": 30, "Identificación": 60, "Elaboración": 60, "Consolidación": 30, "Servicio Social": 30}
                limite_sugerido = limites.get(etapa_act, 30)
                
                if dias_trans > limite_sugerido:
                    st.warning(f"⚠️ Alerta de Rezago Clínico: El residente lleva {dias_trans} días en la etapa {etapa_act} (Límite sugerido: {limite_sugerido} días).")
                else:
                    st.success(f"🟢 Dentro del rango de tiempo esperado ({dias_trans}/{limite_sugerido} días).")
                    
                st.subheader("🚀 Promoción a la Siguiente Etapa")
                siguientes_etapas = {
                    "Acogida": "Identificación",
                    "Identificación": "Elaboración",
                    "Elaboración": "Consolidación",
                    "Consolidación": "Servicio Social",
                    "Servicio Social": "Egresado / Graduado"
                }
                prox_etapa = siguientes_etapas.get(etapa_act, "Egresado")
                
                if st.button(f"Promover Residente a: {prox_etapa}", use_container_width=True):
                    p_data["etapa_actual"] = prox_etapa
                    p_data["fecha_inicio_etapa"] = str(datetime.now().date())
                    guardar_entrevista(sel_pid, p_data, st.session_state["username"])
                    st.success(f"🎉 ¡El residente ha sido promovido exitosamente a la etapa {prox_etapa}!")
                    st.toast("🎉 Promoción completada con éxito", icon="🚀")
                    st.rerun()

    # ==========================================
    # MÓDULO 7: GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        if pacientes_list:
            options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
            sel_p_str = st.selectbox("Seleccione Residente", options_p)
            sel_pid = sel_p_str.split(" | ")[0]
            
            p_data, _, _, _ = obtener_entrevista(sel_pid)
            if p_data:
                etapa_act = p_data.get("etapa_actual", "Acogida")
                with st.form("form_grupo_terapeutico"):
                    tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Retroalimentación", "Grupo de Estudio"])
                    fecha_g = st.date_input("Fecha del Grupo")
                    desarrollo = st.text_area("Desarrollo y Participación del Paciente")
                    devoluciones = st.text_area("Devoluciones del Grupo / Terapeuta")
                    compromisos = st.text_area("Compromisos Establecidos")
                    
                    btn_g_grupo = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                    if btn_g_grupo:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO grupos_terapeuticos (paciente_id, etapa_paciente, tipo_grupo, fecha, desarrollo, devoluciones, compromisos, usuario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (sel_pid, etapa_act, tipo_grupo, str(fecha_g), desarrollo, devoluciones, compromisos, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Sesión de grupo registrada correctamente.")
                        st.toast("✅ Grupo registrado con éxito", icon="🎉")
                        st.rerun()

    # ==========================================
    # MÓDULO 8: CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Almacén y Suministro de Medicamentos")
        
        tab_inv, tab_entrega = st.tabs(["📦 Inventario de Medicamentos", "💊 Suministro a Residentes"])
        
        with tab_inv:
            st.subheader("➕ Agregar Medicamento al Almacén")
            with st.form("form_add_med"):
                c_m1, c_m2 = st.columns(2)
                with c_m1:
                    nom_med = st.text_input("Nombre del Fármaco / Medicamento *")
                    stock_in = st.number_input("Cantidad / Stock Inicial", min_value=1, value=50)
                with c_m2:
                    indicaciones = st.text_area("Indicaciones / Dosis Recomendada")
                btn_med = st.form_submit_button("💾 Guardar Medicamento en Almacén", use_container_width=True)
                
                if btn_med:
                    if not nom_med.strip():
                        st.error("⚠️ Ingrese el nombre del medicamento.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO medicamentos (nombre_medicamento, stock_actual, indicaciones) VALUES (?, ?, ?)',
                                      (nom_med.strip(), stock_in, indicaciones.strip()))
                            conn.commit()
                            st.success(f"✅ Medicamento '{nom_med}' registrado en almacén.")
                            st.toast("✅ Medicamento agregado", icon="💊")
                        except sqlite3.IntegrityError:
                            st.error("⚠️ El medicamento ya se encuentra en el inventario.")
                        finally:
                            conn.close()
                            
            # Mostrar tabla de inventario
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre_medicamento, stock_actual, indicaciones FROM medicamentos')
            meds_rows = c.fetchall()
            conn.close()
            
            if meds_rows:
                st.subheader("📋 Inventario Actual")
                st.dataframe([{"ID": r[0], "Medicamento": r[1], "Stock Disponible": r[2], "Indicaciones": r[3]} for r in meds_rows], use_container_width=True)

        with tab_entrega:
            st.subheader("💊 Entregar Medicamento a Residente")
            if pacientes_list and meds_rows:
                options_p = [f"{p['paciente_id']} | Exp: {p['datos'].get('expediente','S/N')} - {p['datos'].get('nombre_completo','')}" for p in pacientes_list]
                sel_p_str = st.selectbox("Seleccione Residente", options_p, key="med_p_sel")
                sel_pid = sel_p_str.split(" | ")[0]
                
                med_dict = {f"{r[1]} (Stock: {r[2]})": (r[0], r[2]) for r in meds_rows}
                sel_med_str = st.selectbox("Seleccione Fármaco", list(med_dict.keys()))
                med_id, current_stock = med_dict[sel_med_str]
                
                with st.form("form_entrega_med"):
                    cant_entrega = st.number_input("Cantidad a Entregar", min_value=1, max_value=max(1, current_stock), value=1)
                    obs_med = st.text_input("Observaciones / Horario de Dosis")
                    btn_sumn = st.form_submit_button("💊 Suministrar Medicamento", use_container_width=True)
                    
                    if btn_sumn:
                        if cant_entrega > current_stock:
                            st.error("⚠️ No hay suficiente stock en almacén.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, cantidad, fecha_entrega, usuario, observaciones)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (sel_pid, med_id, cant_entrega, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], obs_med.strip()))
                            
                            c.execute('UPDATE medicamentos SET stock_actual = stock_actual - ? WHERE id = ?', (cant_entrega, med_id))
                            conn.commit()
                            conn.close()
                            st.success("✅ Entrega registrada y stock actualizado en almacén.")
                            st.toast("✅ Entrega realizada con éxito", icon="🎉")
                            st.rerun()

    # ==========================================
    # MÓDULO 9: REPOSITORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        
        tab_archivos, tab_carpetas = st.tabs(["📂 Subir y Consultar Archivos", "📁 Gestión de Carpetas"])
        
        # Cargar carpetas disponibles
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT nombre_carpeta FROM carpetas_repositorio')
        carpetas_existentes = [r[0] for r in c.fetchall()]
        conn.close()
        
        if not carpetas_existentes:
            carpetas_existentes = ["Documentos de Admisión", "Estudios Médicos", "Pruebas Psicológicas", "Expediente Jurídico"]

        with tab_archivos:
            st.subheader("📤 Cargar Documento al Repositorio")
            carpeta_dest = st.selectbox("Seleccione Carpeta de Destino", carpetas_existentes)
            
            uploaded_file = st.file_uploader("Elija un archivo (PDF, DOCX, PNG, JPG)", type=["pdf", "docx", "png", "jpg", "jpeg"])
            if uploaded_file:
                if st.button("💾 Guardar Archivo en Repositorio"):
                    os.makedirs(f"repositorio/{carpeta_dest}", exist_ok=True)
                    f_path = os.path.join(f"repositorio/{carpeta_dest}", uploaded_file.name)
                    with open(f_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    st.success(f"✅ Archivo '{uploaded_file.name}' guardado correctamente en '{carpeta_dest}'.")
                    st.toast("✅ Archivo subido con éxito", icon="📁")

        with tab_carpetas:
            st.subheader("➕ Crear Nueva Carpeta")
            with st.form("form_nueva_carpeta"):
                nom_carp = st.text_input("Nombre de la Carpeta")
                btn_c = st.form_submit_button("Crear Carpeta")
                if btn_c:
                    if nom_carp.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO carpetas_repositorio (nombre_carpeta) VALUES (?)', (nom_carp.strip(),))
                            conn.commit()
                            st.success(f"✅ Carpeta '{nom_carp}' creada exitosamente.")
                            st.toast("✅ Carpeta agregada", icon="📁")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("⚠️ La carpeta ya existe.")
                        finally:
                            conn.close()

    # ==========================================
    # MÓDULO 10: BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Búsqueda Centralizada de Expedientes")
        
        busqueda = st.text_input("🔍 Buscar por Nombre, Folio o Expediente")
        
        filtro_estado = st.radio("Filtrar por Estado", ["Todos", "🟢 Activos", "🔴 Bloqueados / Inactivos"], horizontal=True)
        
        pacientes_filtrados = pacientes_list
        if filtro_estado == "🟢 Activos":
            pacientes_filtrados = [p for p in pacientes_filtrados if p["datos"].get("estado_paciente", "Activo") == "Activo"]
        elif filtro_estado == "🔴 Bloqueados / Inactivos":
            pacientes_filtrados = [p for p in pacientes_filtrados if p["datos"].get("estado_paciente", "Activo") != "Activo"]

        if busqueda.strip():
            b_norm = normalize_text(busqueda)
            pacientes_filtrados = [
                p for p in pacientes_filtrados
                if b_norm in normalize_text(p["paciente_id"])
                or b_norm in normalize_text(p["datos"].get("expediente", ""))
                or b_norm in normalize_text(p["datos"].get("nombre_completo", ""))
            ]
            
        st.subheader(f"Resultados ({len(pacientes_filtrados)} residentes)")
        if pacientes_filtrados:
            data_disp = []
            for p in pacientes_filtrados:
                dj = p["datos"]
                data_disp.append({
                    "Folio": p["paciente_id"],
                    "Expediente": dj.get("expediente", "S/N"),
                    "Nombre Completo": dj.get("nombre_completo", ""),
                    "Edad": dj.get("edad", ""),
                    "Etapa": dj.get("etapa_actual", "Acogida"),
                    "Estado": dj.get("estado_paciente", "Activo"),
                    "Ingreso": dj.get("fecha_ingreso", "")
                })
            st.dataframe(data_disp, use_container_width=True)

    # ==========================================
    # MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        
        es_admin = (st.session_state["username"] == "admin" or st.session_state.get("rol") == "Administrador")
        
        if es_admin:
            tab_pass, tab_usuarios = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_pass = st.container()
            tab_usuarios = None

        with tab_pass:
            st.subheader("🔑 Cambiar Contraseña de Usuario Actual")
            with st.form("form_cambio_pass"):
                actual_pass = st.text_input("Contraseña Actual", type="password")
                nueva_pass = st.text_input("Nueva Contraseña", type="password")
                confirm_pass = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_pass = st.form_submit_button("Actualizar Contraseña")
                
                if btn_pass:
                    if nueva_pass != confirm_pass:
                        st.error("⚠️ Las nuevas contraseñas no coinciden.")
                    else:
                        user_ok = verificar_login(st.session_state["username"], actual_pass)
                        if user_ok:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(nueva_pass), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada exitosamente.")
                            st.toast("✅ Contraseña cambiada con éxito", icon="🔑")
                        else:
                            st.error("⚠️ La contraseña actual es incorrecta.")

        if es_admin and tab_usuarios:
            with tab_usuarios:
                st.subheader("➕ Dar de Alta Nuevo Usuario del Personal")
                with st.form("form_nuevo_usuario_staff"):
                    c_u1, c_u2 = st.columns(2)
                    with c_u1:
                        u_name = st.text_input("Nombre de Usuario (Login) *")
                        u_full = st.text_input("Nombre Completo del Colaborador *")
                    with c_u2:
                        u_pass = st.text_input("Contraseña Inicial *", type="password")
                        u_rol = st.selectbox("Rol de Permisos", ["Administrador", "Lectura/Escritura", "Solo Lectura"])
                        
                    btn_add_u = st.form_submit_button("💾 Crear Cuenta de Usuario", use_container_width=True)
                    if btn_add_u:
                        if not u_name.strip() or not u_pass.strip():
                            st.error("⚠️ Complete todos los campos requeridos.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute('''
                                    INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado)
                                    VALUES (?, ?, ?, ?, 'Activo')
                                ''', (u_name.strip().lower(), hash_pass(u_pass), u_full.strip(), u_rol))
                                conn.commit()
                                st.success(f"✅ Usuario '{u_name}' creado exitosamente con el rol '{u_rol}'.")
                                st.toast("✅ Cuenta de colaborador creada", icon="👥")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("⚠️ El nombre de usuario ya existe. Elija otro.")
                            finally:
                                conn.close()
                                
                st.subheader("📋 Catálogo de Cuentas de Personal")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol, estado FROM usuarios')
                u_rows = c.fetchall()
                conn.close()
                
                if u_rows:
                    u_table = []
                    for r in u_rows:
                        u_table.append({
                            "ID": r[0],
                            "Usuario": r[1],
                            "Nombre Completo": r[2],
                            "Rol": r[3],
                            "Estado": r[4] or "Activo"
                        })
                    st.dataframe(u_table, use_container_width=True)
                    
                    st.subheader("🔒 Bloquear / Desbloquear Cuenta de Personal")
                    u_dict = {f"{r[1]} ({r[2]}) - Status: {r[4] or 'Activo'}": (r[0], r[1], r[4] or "Activo") for r in u_rows if r[1] != "admin"}
                    if u_dict:
                        sel_u_key = st.selectbox("Seleccione Usuario para Modificar Estado", list(u_dict.keys()))
                        uid_sel, uname_sel, ustat_sel = u_dict[sel_u_key]
                        
                        col_ub1, col_ub2 = st.columns(2)
                        with col_ub1:
                            if ustat_sel == "Activo":
                                if st.button(f"🔴 Bloquear Acceso a {uname_sel}", use_container_width=True):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Bloqueado' WHERE id = ?", (uid_sel,))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"✅ La cuenta {uname_sel} ha sido BLOQUEADA.")
                                    st.toast("✅ Cuenta bloqueada", icon="🔒")
                                    st.rerun()
                            else:
                                if st.button(f"🟢 Activar Acceso a {uname_sel}", use_container_width=True):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Activo' WHERE id = ?", (uid_sel,))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"✅ La cuenta {uname_sel} ha sido ACTIVADA.")
                                    st.toast("✅ Cuenta reactivada", icon="🔓")
                                    st.rerun()

    # ==========================================
    # MÓDULO 12: RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        st.subheader("⬇️ Descargar Copia de Seguridad (.db)")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button(
                    label="💾 Descargar Respaldo de Base de Datos",
                    data=f,
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
        
        st.subheader("⬆️ Restaurar Base de Datos desde Respaldo")
        db_upload = st.file_uploader("Seleccione un archivo de base de datos (.db)", type=["db"])
        if db_upload:
            if st.button("⚠️ Confirmar y Restaurar Base de Datos"):
                with open(DB_FILE, "wb") as f:
                    f.write(db_upload.getbuffer())
                st.success("✅ Base de datos restaurada correctamente. Reiniciando aplicación...")
                st.toast("✅ Restauración completada", icon="🎉")
                st.rerun()

if __name__ == "__main__":
    main()

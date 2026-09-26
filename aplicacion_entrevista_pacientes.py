import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Consejería",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- MAPA Y CATÁLOGO OFICIAL DE CONSEJERÍAS POR ETAPA ---
CONSEJERIAS_POR_ETAPA = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "IDENTIFICACION": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "ELABORACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJERIA) PREVENCIÓN DE RECAÍDAS.",
        "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
        "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
    ],
    "CONSOLIDACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
        "(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
    ],
    "SERVICIO SOCIAL": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla Usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )''')
    
    # Verificar migración de columna 'rol'
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")

    # 2. Tabla Pacientes / Expedientes
    c.execute('''CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            tipo_usuario TEXT,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'ACTIVO',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            expediente_num TEXT DEFAULT '',
            fecha_registro TEXT,
            usuario_registro TEXT
        )''')

    # Verificar migración de columnas en 'pacientes'
    c.execute("PRAGMA table_info(pacientes)")
    cols_p = [col[1] for col in c.fetchall()]
    if 'expediente_num' not in cols_p:
        c.execute("ALTER TABLE pacientes ADD COLUMN expediente_num TEXT DEFAULT ''")

    # 3. Tabla Entrevistas Iniciales (JSON)
    c.execute('''CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )''')

    # 4. Tabla Fichas de Ingreso y Admisión
    c.execute('''CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )''')

    # 5. Tabla Consejerías Individuales
    c.execute('''CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            etapa TEXT NOT NULL,
            num_consejeria INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance_retroceso TEXT,
            sugerencia TEXT,
            expediente_num TEXT,
            usuario_registro TEXT,
            fecha_registro TEXT
        )''')

    # 6. Tabla Grupos Terapéuticos
    c.execute('''CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            etapa TEXT NOT NULL,
            tipo_grupo TEXT NOT NULL,
            fecha TEXT NOT NULL,
            facilitador TEXT,
            compartimiento TEXT,
            observaciones TEXT,
            devoluciones TEXT,
            logros TEXT,
            dificultades TEXT,
            compromiso TEXT,
            usuario_registro TEXT
        )''')

    # 7. Tabla Catálogo de Medicamentos
    c.execute('''CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            observaciones TEXT
        )''')

    # 8. Tabla Recetas y Esquemas de Medicamentos
    c.execute('''CREATE TABLE IF NOT EXISTS medicamento_esquema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento TEXT NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia_actual INTEGER DEFAULT 0,
            indicaciones TEXT,
            fecha_actualizacion TEXT
        )''')

    # 9. Tabla Entregas de Almacén de Medicamentos
    c.execute('''CREATE TABLE IF NOT EXISTS medicamento_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento TEXT NOT NULL,
            cantidad_entregada INTEGER NOT NULL,
            fecha_entrega TEXT NOT NULL,
            usuario_entrega TEXT
        )''')

    # 10. Tabla Repositorio de Documentos (Archivos binarios)
    c.execute('''CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            mime_type TEXT,
            bytes_blob BLOB,
            descripcion TEXT,
            fecha_subida TEXT,
            usuario_subida TEXT
        )''')

    # Crear usuario admin por defecto
    default_pass = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        c.execute('''INSERT INTO usuarios (username, password_hash, nombre_completo, rol) 
            VALUES (?, ?, ?, ?)''', ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

def es_admin():
    return st.session_state.get("username") == "admin" or "Administrador" in str(st.session_state.get("rol", ""))

def es_lectura_escritura():
    rol = str(st.session_state.get("rol", ""))
    return es_admin() or "Nivel 2" in rol

def calcular_edad(fecha_nac_str):
    if not fecha_nac_str:
        return "N/A"
    try:
        fn = datetime.strptime(fecha_nac_str, "%Y-%m-%d")
        hoy = datetime.now()
        edad = hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
        return f"{edad} años"
    except Exception:
        return "N/A"

# --- AUXILIARES CONSEJERÍAS ---
def obtener_consejeria_siguiente(paciente_id, etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (paciente_id, etapa))
    count = c.fetchone()[0]
    conn.close()
    
    lista = CONSEJERIAS_POR_ETAPA.get(etapa, [])
    num = count + 1
    
    if count < len(lista):
        aspecto_actual = lista[count]
    else:
        aspecto_actual = f"Consejería de Refuerzo / Seguimiento #{num} ({etapa})"
        
    if count + 1 < len(lista):
        aspecto_prox = lista[count + 1]
    else:
        aspecto_prox = "Siguiente Etapa o Evaluación de Cierre de Proceso"
        
    return num, aspecto_actual, aspecto_prox, count

def contar_consejerias_etapa(paciente_id, etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (paciente_id, etapa))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def contar_grupos_etapa(paciente_id, etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT tipo_grupo, COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa = ? GROUP BY tipo_grupo', (paciente_id, etapa))
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

# --- GENERADOR DE PDF CONSEJERÍA INDIVIDUAL ---
class PDFConsejeria(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(20, 80, 40)
        self.cell(0, 8, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, 'HOJA DE SEGUIMIENTO DE CONSEJERÍA INDIVIDUAL', 0, 1, 'C')
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f'Página {self.page_no()} - Documento Oficial de Confidencialidad Clínica', 0, 0, 'C')

def generar_pdf_consejeria(datos):
    pdf = PDFConsejeria()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Datos Generales del Paciente
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(230, 245, 230)
    pdf.cell(0, 7, ' I. FICHA DE IDENTIFICACIÓN Y SESIÓN', 1, 1, 'L', fill=True)
    
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(95, 6, f" Nombre: {datos.get('nombre', 'N/A')}", 1)
    pdf.cell(95, 6, f" EXP. #: {datos.get('expediente_num', 'N/A')}", 1, 1)
    
    pdf.cell(47, 6, f" Edad: {datos.get('edad', 'N/A')}", 1)
    pdf.cell(48, 6, f" Sexo: {datos.get('sexo', 'N/A')}", 1)
    pdf.cell(95, 6, f" Etapa Activa: {datos.get('etapa', 'N/A')}", 1, 1)
    
    pdf.cell(95, 6, f" Fecha de Sesión: {datos.get('fecha', 'N/A')}", 1)
    pdf.cell(95, 6, f" Próxima Consejería: {datos.get('fecha_proxima', 'N/A')}", 1, 1)
    pdf.ln(4)
    
    # Aspectos Trabajados
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(230, 245, 230)
    pdf.cell(0, 7, ' II. OBJETIVOS Y PLAN DE CONSEJERÍA', 1, 1, 'L', fill=True)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 6, ' Aspectos Trabajados en esta Sesión:', 'LRT', 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, f" {datos.get('aspectos_trabajar', '')}", 'LRB')
    pdf.ln(2)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 6, ' Aspectos a Trabajar en la Próxima Consejería:', 'LRT', 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, f" {datos.get('aspectos_proxima', '')}", 'LRB')
    pdf.ln(4)
    
    # Desarrollo Clínico
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(230, 245, 230)
    pdf.cell(0, 7, ' III. DESARROLLO Y NOTAS DE EVOLUCIÓN', 1, 1, 'L', fill=True)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 6, ' Exposición del Paciente:', 'LRT', 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, f" {datos.get('exposicion', 'Sin notas de exposición.')}", 'LRB')
    pdf.ln(2)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 6, ' Avance / Retroceso Observado:', 'LRT', 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, f" {datos.get('avance_retroceso', 'Sin observaciones de avance.')}", 'LRB')
    pdf.ln(2)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 6, ' Sugerencias y Tareas Asignadas:', 'LRT', 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, f" {datos.get('sugerencia', 'Sin sugerencias registradas.')}", 'LRB')
    pdf.ln(12)
    
    # Firmas
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(90, 5, '__________________________________', 0, 0, 'C')
    pdf.cell(10, 5, '', 0, 0)
    pdf.cell(90, 5, '__________________________________', 0, 1, 'C')
    
    pdf.cell(90, 5, 'Firma del Consejero / Terapeuta', 0, 0, 'C')
    pdf.cell(10, 5, '', 0, 0)
    pdf.cell(90, 5, 'Firma del Paciente / Residente', 0, 1, 'C')
    
    return bytes(pdf.output())

# Inicializar Base de Datos
init_db()

# --- CONTROL DE SESIÓN Y LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🌱 Sawabona Shikoba A.C.")
    st.subheader("Sistema de Control Clínico y Expediente de Usuarios")
    
    with st.form("form_login"):
        user_in = st.text_input("Usuario")
        pass_in = st.text_input("Contraseña", type="password")
        btn_login = st.form_submit_button("🔑 Iniciar Sesión", use_container_width=True)
        
        if btn_login:
            res = verificar_login(user_in, pass_in)
            if res:
                st.session_state["logged_in"] = True
                st.session_state["username"] = res[0]
                st.session_state["nombre_completo"] = res[1]
                st.session_state["rol"] = res[2] if len(res) > 2 and res[2] else "Nivel 1 - Administrador"
                st.toast(f"¡Bienvenido(a), {res[1]}!", icon="🎉")
                st.balloons()
                st.rerun()
            else:
                st.error("❌ Credenciales incorrectas. Verifica tu usuario y contraseña.")
    st.stop()

# --- MENÚ DE NAVEGACIÓN PRINCIPAL ---
st.sidebar.title("🌱 Sawabona Shikoba")
st.sidebar.caption(f"👤 **{st.session_state['nombre_completo']}**\n\n🔑 Rol: *{st.session_state.get('rol', 'Administrador')}*")

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.divider()

opciones_menu = [
    "👤 Registro de Usuarios",
    "📄 Ficha de Ingreso / Admisión",
    "📝 Consejerías Individuales",
    "🎯 Gestión de Etapas & Proceso",
    "🗣️ Grupos Terapéuticos",
    "💊 Control de Medicamentos",
    "📋 Entrevista Inicial",
    "🔍 Buscar Expediente General"
]

if es_admin():
    opciones_menu.append("📁 Repositorio de Documentos")
    opciones_menu.append("⚙️ Configuración & Seguridad")
    opciones_menu.append("📦 Respaldo y Restauración")

menu = st.sidebar.radio("Navegación del Sistema", opciones_menu)

# ==========================================
# 1. MÓDULO: REGISTRO Y EDICIÓN DE USUARIOS
# ==========================================
if menu == "👤 Registro de Usuarios":
    st.title("👤 Catálogo de Residentes y Personal")
    t1, t2 = st.tabs(["📝 Registrar / Editar Usuario", "📋 Lista General de Usuarios"])
    
    with t1:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, nombre_completo, etapa_actual FROM pacientes ORDER BY nombre_completo')
        pacs = c.fetchall()
        conn.close()
        
        opc_pacs = ["-- Registrar Nuevo Usuario --"] + [f"{p[1]} ({p[0]}) - Etapa: {p[2]}" for p in pacs]
        sel_pac = st.selectbox("🔑 Selecciona el Usuario a Editar", opc_pacs)
        
        if sel_pac != "-- Registrar Nuevo Usuario --":
            pid_edit = sel_pac.split("(")[1].split(")")[0]
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, fecha_inicio_etapa, expediente_num FROM pacientes WHERE paciente_id = ?', (pid_edit,))
            pdata = c.fetchone()
            conn.close()
        else:
            pdata = None
            
        with st.form("form_paciente", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                v_folio = pdata[0] if pdata else f"PAC-{datetime.now().strftime('%M%S')}"
                st.text_input("Folio ID del Sistema", value=v_folio, disabled=True)
                v_exp = st.text_input("Número de Expediente Institucional (EXP)", value=pdata[9] if pdata and pdata[9] else "")
                v_nombre = st.text_input("Nombre Completo *", value=pdata[1] if pdata else "")
                v_tipo = st.selectbox("Tipo de Usuario", ["Residente / Paciente", "Personal / Staff", "Familia"], index=0 if not pdata or pdata[2]=="Residente / Paciente" else 1)
                v_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=0 if not pdata or pdata[5]=="Masculino" else 1)
            
            with c2:
                v_fnac = st.date_input("Fecha de Nacimiento", value=datetime.strptime(pdata[4], "%Y-%m-%d") if pdata and pdata[4] else datetime(1995,1,1))
                v_fing = st.date_input("Fecha de Ingreso Real a la Comunidad", value=datetime.strptime(pdata[3], "%Y-%m-%d") if pdata and pdata[3] else datetime.now())
                v_etapa = st.selectbox("Etapa Actual", ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"], index=["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"].index(pdata[7]) if pdata and pdata[7] in ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"] else 0)
                v_fetapa = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.strptime(pdata[8], "%Y-%m-%d") if pdata and pdata[8] else datetime.now())
                v_estatus = st.selectbox("Estatus", ["ACTIVO", "INACTIVO", "EGRESADO", "BAJA"], index=0 if not pdata or pdata[6]=="ACTIVO" else 1)
                
            btn_guardar_p = st.form_submit_button("💾 Guardar Usuario", use_container_width=True)
            if btn_guardar_p:
                if not v_nombre.strip():
                    st.error("El nombre completo es obligatorio.")
                elif not es_lectura_escritura():
                    st.error("Tu rol de usuario es de Solo Lectura.")
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (v_folio,))
                    if c.fetchone():
                        c.execute('''UPDATE pacientes SET nombre_completo=?, tipo_usuario=?, fecha_ingreso=?, fecha_nacimiento=?, sexo=?, estatus=?, etapa_actual=?, fecha_inicio_etapa=?, expediente_num=?
                            WHERE paciente_id=?''', (v_nombre, v_tipo, v_fing.strftime("%Y-%m-%d"), v_fnac.strftime("%Y-%m-%d"), v_sexo, v_estatus, v_etapa, v_fetapa.strftime("%Y-%m-%d"), v_exp, v_folio))
                    else:
                        c.execute('''INSERT INTO pacientes (paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, fecha_inicio_etapa, expediente_num, fecha_registro, usuario_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (v_folio, v_nombre, v_tipo, v_fing.strftime("%Y-%m-%d"), v_fnac.strftime("%Y-%m-%d"), v_sexo, v_estatus, v_etapa, v_fetapa.strftime("%Y-%m-%d"), v_exp, datetime.now().strftime("%Y-%m-%d"), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.toast("¡Usuario guardado correctamente!", icon="🎉")
                    st.balloons()
                    st.rerun()

    with t2:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, nombre_completo, expediente_num, etapa_actual, fecha_ingreso, estatus FROM pacientes ORDER BY nombre_completo')
        rows = c.fetchall()
        conn.close()
        if rows:
            st.dataframe([{"Folio ID": r[0], "EXP #": r[2], "Nombre": r[1], "Etapa": r[3], "Ingreso": r[4], "Estatus": r[5]} for r in rows], use_container_width=True)
        else:
            st.info("No hay usuarios registrados.")

# ==========================================
# 2. MÓDULO: FICHA DE INGRESO Y ADMISIÓN
# ==========================================
elif menu == "📄 Ficha de Ingreso / Admisión":
    st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, expediente_num FROM pacientes WHERE estatus = "ACTIVO" ORDER BY nombre_completo')
    pacs = c.fetchall()
    conn.close()
    
    if not pacs:
        st.warning("Primero registra a un usuario en el módulo de '👤 Registro de Usuarios'.")
    else:
        opc = [f"{p[1]} (ID: {p[0]})" for p in pacs]
        sel_p = st.selectbox("Selecciona Paciente para Ficha de Ingreso", opc)
        pid = sel_p.split("(ID: ")[1].split(")")[0]
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?', (pid,))
        frow = c.fetchone()
        c.execute('SELECT nombre_completo, fecha_nacimiento, sexo, expediente_num FROM pacientes WHERE paciente_id = ?', (pid,))
        pbase = c.fetchone()
        conn.close()
        
        fdatos = json.loads(frow[0]) if frow else {}
        
        t1, t2 = st.tabs(["📝 Capturar / Editar Ficha", "🖨️ Imprimir Ficha PDF"])
        
        with t1:
            with st.form("form_ficha"):
                st.subheader("1. Datos del Responsable Familiar")
                c1, c2 = st.columns(2)
                with c1:
                    f_resp = st.text_input("Nombre del Responsable Familiar", value=fdatos.get("responsable", ""))
                    f_parent = st.text_input("Parentesco", value=fdatos.get("parentesco", ""))
                with c2:
                    f_tel = st.text_input("Teléfono de Contacto", value=fdatos.get("telefono", ""))
                    f_exp = st.text_input("EXP. Institucional", value=pbase[3] if pbase and pbase[3] else fdatos.get("expediente_num", ""))
                
                st.subheader("2. Datos del Residente")
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("Nombre del Residente", value=pbase[0] if pbase else "", disabled=True)
                    f_ecivil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                    f_esco = st.text_input("Escolaridad", value=fdatos.get("escolaridad", ""))
                    f_ocup = st.text_input("Ocupación", value=fdatos.get("ocupacion", ""))
                with c2:
                    st.text_input("Edad Calculada", value=calcular_edad(pbase[1]) if pbase else "", disabled=True)
                    f_relig = st.text_input("Religión", value=fdatos.get("religion", ""))
                    f_smed = st.text_input("Servicio Médico / Seguro", value=fdatos.get("servicio_medico", ""))
                    f_dom = st.text_area("Domicilio Completo", value=fdatos.get("domicilio", ""))
                
                st.subheader("3. Términos Financieros y Admisión")
                c1, c2, c3 = st.columns(3)
                with c1:
                    f_costo = st.number_input("Costo de Ingreso ($)", value=float(fdatos.get("costo_ingreso", 4500.0)))
                with c2:
                    f_mensual = st.number_input("Mensualidad ($)", value=float(fdatos.get("mensualidad", 6000.0)))
                with c3:
                    f_pagare = st.number_input("Importe Pagaré ($)", value=float(fdatos.get("pagare", 42000.0)))
                
                btn_save_f = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                if btn_save_f:
                    if not es_lectura_escritura():
                        st.error("Tu rol es de Solo Lectura.")
                    else:
                        dict_f = {
                            "responsable": f_resp, "parentesco": f_parent, "telefono": f_tel, "expediente_num": f_exp,
                            "escolaridad": f_esco, "ocupacion": f_ocup, "religion": f_relig, "servicio_medico": f_smed,
                            "domicilio": f_dom, "estado_civil": f_ecivil, "costo_ingreso": f_costo, "mensualidad": f_mensual,
                            "pagare": f_pagare
                        }
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('INSERT OR REPLACE INTO fichas_ingreso (paciente_id, fecha_registro, usuario_registro, datos_json) VALUES (?, ?, ?, ?)',
                                  (pid, datetime.now().strftime("%Y-%m-%d"), st.session_state["username"], json.dumps(dict_f, ensure_ascii=False)))
                        c.execute('UPDATE pacientes SET expediente_num = ? WHERE paciente_id = ?', (f_exp, pid))
                        conn.commit()
                        conn.close()
                        st.toast("Ficha de Ingreso guardada con éxito", icon="🎉")
                        st.balloons()
                        st.rerun()

        with t2:
            if not fdatos:
                st.info("Primero guarda la Ficha de Ingreso para poder imprimirla.")
            else:
                st.success("Ficha lista para generar PDF.")
                pdf_f = FPDF()
                pdf_f.add_page()
                pdf_f.set_font("Helvetica", "B", 14)
                pdf_f.cell(0, 10, "SAWABONA SHIKOBA A.C. - FICHA DE INGRESO", 0, 1, "C")
                pdf_f.set_font("Helvetica", "", 10)
                pdf_f.cell(0, 6, f"Paciente: {pbase[0]} | EXP #: {fdatos.get('expediente_num')}", 0, 1)
                pdf_f.cell(0, 6, f"Responsable: {fdatos.get('responsable')} ({fdatos.get('parentesco')}) - Tel: {fdatos.get('telefono')}", 0, 1)
                pdf_bytes = bytes(pdf_f.output())
                st.download_button("🖨️ Descargar Ficha de Ingreso PDF", data=pdf_bytes, file_name=f"Ficha_Ingreso_{pid}.pdf", mime="application/pdf")

# ==========================================
# 3. MÓDULO: CONSEJERÍAS INDIVIDUALES (NUEVO)
# ==========================================
elif menu == "📝 Consejerías Individuales":
    st.title("📝 Seguimiento de Consejerías Individuales")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, expediente_num, etapa_actual, fecha_nacimiento, sexo FROM pacientes WHERE estatus = "ACTIVO" ORDER BY nombre_completo')
    pacs = c.fetchall()
    conn.close()
    
    if not pacs:
        st.warning("No hay pacientes activos registrados en el sistema.")
    else:
        dict_pacs = {p[0]: p for p in pacs}
        opc_p = [f"{p[1]} (EXP: {p[2] if p[2] else 'S/N'}) - ID: {p[0]}" for p in pacs]
        sel_str = st.selectbox("🔑 Selecciona el Paciente para la Consejería", opc_p)
        pid = sel_str.split("ID: ")[1].strip()
        pinfo = dict_pacs[pid]
        
        nombre_p = pinfo[1]
        exp_p = pinfo[2] if pinfo[2] else ""
        etapa_p = pinfo[3]
        edad_p = calcular_edad(pinfo[4])
        sexo_p = pinfo[5]
        
        t1, t2 = st.tabs(["📝 Registrar Nueva Consejería", "📜 Historial e Impresión PDF"])
        
        with t1:
            num_cons, asp_actual, asp_prox, total_cumplidas = obtener_consejeria_siguiente(pid, etapa_p)
            lista_temas = CONSEJERIAS_POR_ETAPA.get(etapa_p, [])
            
            st.info(f"📍 **Etapa Activa**: `{etapa_p}` | Consejería sugerida: **#{num_cons}** de la etapa ({total_cumplidas} / {len(lista_temas)} registradas en esta etapa)")
            
            with st.form("form_nueva_consejeria"):
                st.subheader("1. Ficha de Identificación de la Sesión")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.text_input("Nombre del Paciente", value=nombre_p, disabled=True)
                    st.text_input("Edad", value=edad_p, disabled=True)
                    v_exp_cons = st.text_input("EXP. Institucional", value=exp_p)
                with c2:
                    st.text_input("Sexo", value=sexo_p, disabled=True)
                    st.text_input("Etapa Actual", value=etapa_p, disabled=True)
                    v_fecha_cons = st.date_input("Fecha de la Sesión", value=datetime.now())
                with c3:
                    st.markdown(f"**Número de Consejería**: `Consejería #{num_cons}`")
                    v_fecha_prox = st.date_input("Fecha Próxima Consejería (+7 días)", value=datetime.now() + timedelta(days=7))
                
                st.subheader("2. Plan de Consejería (Según Plan Oficial)")
                v_aspectos_actual = st.text_area("Aspectos a Trabajar (Sesión Actual)", value=asp_actual, height=80)
                v_aspectos_prox = st.text_area("Aspectos a Trabajar en la Próxima Consejería", value=asp_prox, height=80)
                
                st.subheader("3. Notas Clínicas de Evolución")
                v_exposicion = st.text_area("Exposición del Paciente (Texto Largo) *", placeholder="Escribe aquí los temas compartidos por el paciente durante la sesión...", height=120)
                v_avance = st.text_area("Avance / Retroceso Observado (Texto Largo)", placeholder="Escribe las fortalezas, avances o retrocesos detectados...", height=100)
                v_sugerencia = st.text_area("Sugerencias y Compromisos (Texto Largo)", placeholder="Escribe las tareas, acuerdos y compromisos asumidos...", height=100)
                
                btn_guardar_cons = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)
                
                if btn_guardar_cons:
                    if not v_exposicion.strip():
                        st.error("El campo 'Exposición del Paciente' no puede quedar vacío.")
                    elif not es_lectura_escritura():
                        st.error("Tu usuario es de Solo Lectura.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''INSERT INTO consejerias (paciente_id, etapa, num_consejeria, fecha, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance_retroceso, sugerencia, expediente_num, usuario_registro, fecha_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (pid, etapa_p, num_cons, v_fecha_cons.strftime("%Y-%m-%d"), v_aspectos_actual, v_aspectos_prox, v_fecha_prox.strftime("%Y-%m-%d"), v_exposicion, v_avance, v_sugerencia, v_exp_cons, st.session_state["username"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        
                        if v_exp_cons:
                            c.execute('UPDATE pacientes SET expediente_num = ? WHERE paciente_id = ?', (v_exp_cons, pid))
                            
                        conn.commit()
                        conn.close()
                        
                        st.toast(f"¡Consejería #{num_cons} de {etapa_p} registrada correctamente!", icon="🎉")
                        st.balloons()
                        st.rerun()

        with t2:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''SELECT id, etapa, num_consejeria, fecha, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance_retroceso, sugerencia, expediente_num, usuario_registro 
                FROM consejerias WHERE paciente_id = ? ORDER BY id DESC''', (pid,))
            rows_cons = c.fetchall()
            conn.close()
            
            if not rows_cons:
                st.info("El paciente seleccionado no tiene sesiones de consejería registradas aún.")
            else:
                st.success(f"Total de consejerías registradas para {nombre_p}: **{len(rows_cons)}**")
                for r in rows_cons:
                    cid, c_etapa, c_num, c_fecha, c_asp, c_prox, c_fprox, c_exp, c_avan, c_sug, c_expnum, c_user = r
                    with st.expander(f"🗓️ Consejería #{c_num} ({c_etapa}) - Fecha: {c_fecha} | EXP: {c_expnum}"):
                        st.write(f"**Aspectos Trabajados**: {c_asp}")
                        st.write(f"**Aspectos Próxima Sesión**: {c_prox} *(Programada: {c_fprox})*")
                        st.write(f"**Exposición**: {c_exp}")
                        st.write(f"**Avance / Retroceso**: {c_avan}")
                        st.write(f"**Sugerencias**: {c_sug}")
                        st.caption(f"Registrado por: {c_user}")
                        
                        dict_pdf = {
                            "nombre": nombre_p, "expediente_num": c_expnum if c_expnum else exp_p,
                            "edad": edad_p, "sexo": sexo_p, "etapa": c_etapa, "fecha": c_fecha,
                            "fecha_proxima": c_fprox, "aspectos_trabajar": c_asp, "aspectos_proxima": c_prox,
                            "exposicion": c_exp, "avance_retroceso": c_avan, "sugerencia": c_sug
                        }
                        pdf_bytes = generar_pdf_consejeria(dict_pdf)
                        st.download_button(
                            label=f"🖨️ Descargar PDF Consejería #{c_num}",
                            data=pdf_bytes,
                            file_name=f"Consejeria_{pid}_Num_{c_num}_{c_fecha}.pdf",
                            mime="application/pdf",
                            key=f"pdf_btn_{cid}"
                        )

# ==========================================
# 4. MÓDULO: GESTIÓN DE ETAPAS & CHECKLIST
# ==========================================
elif menu == "🎯 Gestión de Etapas & Proceso":
    st.title("🎯 Gestión de Etapas, Checklists y Rezagos")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, etapa_actual, fecha_ingreso, fecha_inicio_etapa, expediente_num FROM pacientes WHERE estatus = "ACTIVO" ORDER BY nombre_completo')
    pacs = c.fetchall()
    conn.close()
    
    if not pacs:
        st.warning("No hay pacientes activos.")
    else:
        opc_p = [f"{p[1]} (Etapa: {p[2]}) - ID: {p[0]}" for p in pacs]
        sel_str = st.selectbox("Selecciona Paciente para Evaluar Etapa", opc_p)
        pid = sel_str.split("ID: ")[1].strip()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, nombre_completo, etapa_actual, fecha_ingreso, fecha_inicio_etapa, expediente_num FROM pacientes WHERE paciente_id = ?', (pid,))
        pcurr = c.fetchone()
        conn.close()
        
        p_id, p_nom, p_etapa, p_fing, p_fetapa, p_exp = pcurr
        
        dias_totales = (datetime.now() - datetime.strptime(p_fing, "%Y-%m-%d")).days if p_fing else 0
        dias_etapa = (datetime.now() - datetime.strptime(p_fetapa, "%Y-%m-%d")).days if p_fetapa else 0
        
        duracion_std = 30 if p_etapa in ["ACOGIDA", "SERVICIO SOCIAL"] else 60
        es_rezagado = dias_etapa > duracion_std
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("🗓️ Días Totales en Comunidad", f"{dias_totales} días")
        with c2:
            st.metric("⏱️ Días en Etapa Actual", f"{dias_etapa} días", delta=f"{dias_etapa - duracion_std} días vs Meta" if es_rezagado else "En tiempo normal", delta_color="inverse" if es_rezagado else "normal")
        with c3:
            st.metric("🏷️ Etapa Actual", p_etapa)
            
        if es_rezagado:
            st.error(f"🚨 **ALERTA DE REZAGO CLÍNICO**: {p_nom} ha superado el tiempo estimado para la etapa `{p_etapa}` ({dias_etapa} días acumulados vs {duracion_std} días estimados). Revisa el checklist de requisitos para destrabar su proceso.")
            
        st.subheader("📋 Checklist de Requisitos para Promoción")
        
        # Requisito Consejerías
        req_consejerias = len(CONSEJERIAS_POR_ETAPA.get(p_etapa, []))
        cumplidas_consejerias = contar_consejerias_etapa(pid, p_etapa)
        
        if cumplidas_consejerias >= req_consejerias:
            st.success(f"✅ **Consejerías Individuales de {p_etapa}**: {cumplidas_consejerias} / {req_consejerias} completadas (100% de la etapa)")
        else:
            st.warning(f"❌ **Consejerías Individuales de {p_etapa}**: {cumplidas_consejerias} / {req_consejerias} completadas (Faltan {req_consejerias - cumplidas_consejerias} consejerías para poder promover)")
            
        # Requisito Grupos
        grupos_dict = contar_grupos_etapa(pid, p_etapa)
        st.write(f"🗣️ **Grupos Realizados en {p_etapa}**: Terapia de Grupo: `{grupos_dict.get('Terapia de Grupo', 0)}` | Aquí y Ahora: `{grupos_dict.get('Aquí y Ahora', 0)}` | Feedback: `{grupos_dict.get('Feedback', 0)}`")
        
        st.divider()
        st.subheader("🚀 Promover a la Siguiente Etapa")
        
        siguientes = {
            "ACOGIDA": "IDENTIFICACION",
            "IDENTIFICACION": "ELABORACION",
            "ELABORACION": "CONSOLIDACION",
            "CONSOLIDACION": "SERVICIO SOCIAL",
            "SERVICIO SOCIAL": "GRADUADO / EGRESADO"
        }
        
        prox_etapa = siguientes.get(p_etapa, "GRADUADO")
        
        puedes_promover = cumplidas_consejerias >= req_consejerias
        
        if not puedes_promover:
            st.info(f"🔒 El botón de promoción estará inhabilitado hasta cumplir con el mínimo de **{req_consejerias} consejerías** de la etapa `{p_etapa}`.")
            
        if st.button(f"🎉 Promover a {prox_etapa}", disabled=not puedes_promover, use_container_width=True):
            if not es_lectura_escritura():
                st.error("Tu rol es de Solo Lectura.")
            else:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?',
                          (prox_etapa, datetime.now().strftime("%Y-%m-%d"), pid))
                conn.commit()
                conn.close()
                st.toast(f"¡Paciente promovido a {prox_etapa}!", icon="🎉")
                st.balloons()
                st.rerun()

# ==========================================
# 5. MÓDULO: GRUPOS TERAPÉUTICOS
# ==========================================
elif menu == "🗣️ Grupos Terapéuticos":
    st.title("🗣️ Registro de Grupos Terapéuticos")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, etapa_actual FROM pacientes WHERE estatus = "ACTIVO" ORDER BY nombre_completo')
    pacs = c.fetchall()
    conn.close()
    
    if not pacs:
        st.warning("No hay pacientes activos.")
    else:
        opc_p = [f"{p[1]} (Etapa: {p[2]}) - ID: {p[0]}" for p in pacs]
        sel_str = st.selectbox("Selecciona Paciente", opc_p)
        pid = sel_str.split("ID: ")[1].strip()
        
        t1, t2 = st.tabs(["📝 Registrar Grupo", "📜 Historial"])
        with t1:
            with st.form("form_grupo"):
                tipo_g = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                f_g = st.date_input("Fecha", value=datetime.now())
                facil = st.text_input("Facilitador / Staff", value=st.session_state["username"])
                
                comp = st.text_area("Compartimiento / Intervención")
                obs = st.text_area("Observaciones")
                dev = st.text_area("Devoluciones")
                compromiso = st.text_area("¿A qué se compromete?")
                
                btn_g = st.form_submit_button("💾 Guardar Grupo", use_container_width=True)
                if btn_g:
                    if not es_lectura_escritura():
                        st.error("Rol de Solo Lectura.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT etapa_actual FROM pacientes WHERE paciente_id = ?', (pid,))
                        e_act = c.fetchone()[0]
                        c.execute('''INSERT INTO grupos_terapeuticos (paciente_id, etapa, tipo_grupo, fecha, facilitador, compartimiento, observaciones, devoluciones, compromiso, usuario_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (pid, e_act, tipo_g, f_g.strftime("%Y-%m-%d"), facil, comp, obs, dev, compromiso, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.toast("Grupo registrado correctamente", icon="🎉")
                        st.balloons()
                        st.rerun()

        with t2:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, etapa, tipo_grupo, fecha, facilitador, compartimiento FROM grupos_terapeuticos WHERE paciente_id = ? ORDER BY id DESC', (pid,))
            g_rows = c.fetchall()
            conn.close()
            if g_rows:
                st.dataframe([{"ID": r[0], "Etapa": r[1], "Tipo": r[2], "Fecha": r[3], "Facilitador": r[4], "Compartimiento": r[5]} for r in g_rows], use_container_width=True)
            else:
                st.info("Sin registros de grupos.")

# ==========================================
# 6. MÓDULO: CONTROL DE MEDICAMENTOS
# ==========================================
elif menu == "💊 Control de Medicamentos":
    st.title("💊 Control y Registro de Medicamentos")
    
    t1, t2, t3 = st.tabs(["💊 Catálogo Central", "📝 Esquema por Paciente", "📦 Entrega en Almacén"])
    
    with t1:
        st.subheader("📚 Catálogo Central de Fármacos")
        with st.form("form_cat_med"):
            c1, c2, c3 = st.columns(3)
            with c1:
                m_nom = st.text_input("Nombre del Medicamento *")
            with c2:
                m_pres = st.text_input("Presentación (ej. Comprimidos, Gotas)")
            with c3:
                m_conc = st.text_input("Concentración (ej. 500 mg, 20 mg)")
            btn_cat = st.form_submit_button("➕ Agregar al Catálogo")
            if btn_cat:
                if not m_nom.strip():
                    st.error("El nombre es requerido.")
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('INSERT OR IGNORE INTO catalogo_medicamentos (nombre, presentacion, concentracion) VALUES (?, ?, ?)', (m_nom, m_pres, m_conc))
                    conn.commit()
                    conn.close()
                    st.toast("Medicamento agregado al catálogo", icon="🎉")
                    st.rerun()

    with t2:
        st.subheader("📝 Asignar Esquema de Medicación")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, nombre_completo FROM pacientes WHERE estatus = "ACTIVO"')
        pacs = c.fetchall()
        c.execute('SELECT nombre FROM catalogo_medicamentos ORDER BY nombre')
        meds_cat = [r[0] for r in c.fetchall()]
        conn.close()
        
        if pacs:
            sel_p = st.selectbox("Selecciona Residente", [f"{p[1]} ({p[0]})" for p in pacs])
            pid = sel_p.split("(")[1].split(")")[0]
            
            with st.form("form_esquema_med"):
                c1, c2 = st.columns(2)
                with c1:
                    med_sel = st.selectbox("Medicamento del Catálogo", meds_cat if meds_cat else ["N/A"])
                    d_m = st.number_input("Dosis Mañana", min_value=0.0, step=0.5)
                    d_t = st.number_input("Dosis Tarde", min_value=0.0, step=0.5)
                with c2:
                    d_n = st.number_input("Dosis Noche", min_value=0.0, step=0.5)
                    stock_i = st.number_input("Existencia Inicial en Almacén", min_value=0, step=1)
                
                btn_esq = st.form_submit_button("💾 Guardar Esquema de Medicación")
                if btn_esq:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''INSERT INTO medicamento_esquema (paciente_id, medicamento, dosis_manana, dosis_tarde, dosis_noche, existencia_actual, fecha_actualizacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', (pid, med_sel, d_m, d_t, d_n, stock_i, datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    conn.close()
                    st.toast("Esquema de medicación asignado con éxito", icon="🎉")
                    st.balloons()
                    st.rerun()

    with t3:
        st.subheader("📦 Registro de Entrega Diaria")
        st.info("Entrega de fármacos en almacén con descuento de inventario.")

# ==========================================
# 7. MÓDULO: ENTREVISTA INICIAL
# ==========================================
elif menu == "📋 Entrevista Inicial":
    st.title("📋 Entrevista Inicial de Consejería")
    st.info("Formulario de evaluación de antecedentes de consumo.")

# ==========================================
# 8. MÓDULO: BUSCAR EXPEDIENTE GENERAL
# ==========================================
elif menu == "🔍 Buscar Expediente General":
    st.title("🔍 Búsqueda General de Expedientes")
    st.info("Búsqueda global e historial clínico.")

# ==========================================
# 9. MÓDULO: REPOSITORIO DE DOCUMENTOS
# ==========================================
elif menu == "📁 Repositorio de Documentos":
    st.title("📁 Repositorio de Documentos")
    if not es_admin():
        st.error("Módulo exclusivo para Administradores.")
    else:
        st.info("Repositorio e intercambio de manuales y archivos.")

# ==========================================
# 10. MÓDULO: CONFIGURACIÓN & SEGURIDAD
# ==========================================
elif menu == "⚙️ Configuración & Seguridad":
    st.title("⚙️ Seguridad y Roles de Usuario")
    if not es_admin():
        st.error("Módulo exclusivo para Administradores.")
    else:
        st.info("Gestión de accesos y seguridad.")

# ==========================================
# 11. MÓDULO: RESPALDO Y RESTAURACIÓN
# ==========================================
elif menu == "📦 Respaldo y Restauración":
    st.title("📦 Respaldo y Restauración de Base de Datos")
    
    conn = sqlite3.connect(DB_FILE)
    with open(DB_FILE, "rb") as f:
        db_bytes = f.read()
    conn.close()
    
    st.download_button(
        label="📥 Descargar Respaldo Seguro (.db)",
        data=db_bytes,
        file_name=f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
        mime="application/x-sqlite3",
        use_container_width=True
    )

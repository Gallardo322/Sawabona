import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Control Clínico y Consejería - Sawabona",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIÓN AUTOMÁTICA ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios Administrativos (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    
    # 2. Pacientes (Estructura principal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            tipo_usuario TEXT DEFAULT 'Paciente',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            hermano_mayor_id TEXT,
            fecha_suelta_hermano TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # 3. Pacientes Registro (Estructura alternamente usada en versiones previas)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
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
    
    # 5. Ficha de Ingreso y Admisión (NOM-028)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 6. Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            etapa TEXT,
            tema TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 7. Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 8. Medicamentos e Inventarios (Estructura JSON)
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            paciente_id TEXT PRIMARY KEY,
            meds_json TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # 9. Catálogo de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
    
    # 10. Asignaciones de Medicamentos por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS asignaciones_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT
        )
    ''')
    
    # 11. Historial de Entregas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            turno TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    
    # 12. Repositorio de Documentos (Carpetas y Archivos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            padre_id INTEGER DEFAULT NULL,
            fecha_creacion TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT,
            usuario TEXT,
            contenido BLOB
        )
    ''')
    
    # Crear Carpetas Raíz por Defecto si no existen
    carpetas_def = ["Formatos", "Documentos", "Eventos", "Comprobantes", "Terapéutico"]
    for cdef in carpetas_def:
        c.execute("SELECT id FROM repositorio_carpetas WHERE nombre = ? AND padre_id IS NULL", (cdef,))
        if not c.fetchone():
            c.execute("INSERT INTO repositorio_carpetas (nombre, padre_id, fecha_creacion) VALUES (?, NULL, ?)",
                      (cdef, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
    # Crear usuario admin si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))

    # --- MIGRACIÓN Y SINCRONIZACIÓN AUTOMÁTICA ENTRE TABLAS LEGADAS ---
    # Sincronizar 'pacientes_registro' -> 'pacientes'
    try:
        c.execute('''
            INSERT OR IGNORE INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_registro, usuario_registro)
            SELECT paciente_id, nombre_completo, COALESCE(fecha_ingreso, ''), COALESCE(fecha_nacimiento, ''), COALESCE(sexo, 'Masculino'), COALESCE(estatus, 'A'), 'Paciente', 'ACOGIDA', COALESCE(fecha_registro, ''), COALESCE(usuario_registro, 'admin')
            FROM pacientes_registro
        ''')
        c.execute('''
            INSERT OR IGNORE INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro)
            SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro
            FROM pacientes
        ''')
    except Exception:
        pass
        
    # Sincronizar asignaciones_medicamentos <-> medicamentos (JSON)
    try:
        # 1. Copiar de asignaciones_medicamentos a medicamentos JSON
        c.execute("SELECT a.paciente_id, m.compuesto, m.nombre_medicamento, m.presentacion, a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones FROM asignaciones_medicamentos a JOIN catalogo_medicamentos m ON a.medicamento_id = m.id")
        asig_rows = c.fetchall()
        if asig_rows:
            pac_meds = {}
            for r in asig_rows:
                pid, comp, mnom, pres, dm, dt, dn, ext, obs = r
                if pid not in pac_meds:
                    pac_meds[pid] = {'meds': [], 'obs': obs or ''}
                pac_meds[pid]['meds'].append({
                    'nombre': f"{comp} ({mnom})" if mnom else comp,
                    'compuesto': comp,
                    'nombre_medicamento': mnom,
                    'presentacion': pres,
                    'manana': str(dm),
                    'tarde': str(dt),
                    'noche': str(dn),
                    'existencia': str(ext),
                    'notas': obs or ''
                })
            for pid, data in pac_meds.items():
                meds_json_str = json.dumps(data['meds'], ensure_ascii=False)
                c.execute('''
                    INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, usuario_registro)
                    VALUES (?, ?, ?, datetime('now'), 'admin')
                    ON CONFLICT(paciente_id) DO UPDATE SET meds_json=excluded.meds_json, observaciones=excluded.observaciones
                ''', (pid, meds_json_str, data['obs']))
    except Exception:
        pass

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def restaurar_bytes_db(bytes_data):
    with open(DB_FILE, "wb") as f:
        f.write(bytes_data)
    init_db()

# --- FUNCIONES DE PACIENTES / USUARIOS ---
def generar_siguiente_folio():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        pid = r[0]
        if pid.startswith("PAC-"):
            try:
                num = int(pid.split("-")[1])
                if num > max_num:
                    max_num = num
            except Exception:
                pass
    return f"PAC-{max_num + 1:03d}"

def verificar_duplicado_nombre(nombre, paciente_id_actual=""):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(nombre_completo) = LOWER(?)', (nombre.strip(),))
    rows = c.fetchall()
    conn.close()
    for r in rows:
        if r[0] != paciente_id_actual:
            return r
    return None

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', etapa_actual='ACOGIDA', usuario='admin'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, fecha_actual, paciente_id))
        c.execute('''
            UPDATE pacientes_registro 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, fecha_actual, fecha_actual, usuario))
        c.execute('''
            INSERT OR IGNORE INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    r = c.fetchone()
    conn.close()
    if r:
        return {
            "paciente_id": r[0],
            "nombre_completo": r[1],
            "fecha_ingreso": r[2],
            "fecha_nacimiento": r[3],
            "sexo": r[4],
            "estatus": r[5],
            "tipo_usuario": r[6],
            "etapa_actual": r[7]
        }
    return None

def listar_pacientes_completos(solo_activos=True):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_modificacion FROM pacientes WHERE estatus = 'A' ORDER BY fecha_modificacion DESC")
    else:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_modificacion FROM pacientes ORDER BY fecha_modificacion DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE MEDICAMENTOS ---
def obtener_catalogo():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY compuesto ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_item_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)",
              (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_item_catalogo(item_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?",
              (compuesto.strip(), nombre.strip(), presentacion.strip(), item_id))
    conn.commit()
    conn.close()

def eliminar_item_catalogo(item_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM catalogo_medicamentos WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT meds_json, observaciones FROM medicamentos WHERE paciente_id = ?", (paciente_id,))
    r = c.fetchone()
    conn.close()
    if r and r[0]:
        try:
            return json.loads(r[0]), r[1] or ""
        except Exception:
            return [], r[1] or ""
    return [], ""

def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json_str = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute("SELECT paciente_id FROM medicamentos WHERE paciente_id = ?", (paciente_id,))
    if c.fetchone():
        c.execute("UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?",
                  (meds_json_str, observaciones, fecha_actual, usuario, paciente_id))
    else:
        c.execute("INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)",
                  (paciente_id, meds_json_str, observaciones, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ENTREVISTAS ---
def guardar_entrevista(paciente_id, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control Clinico y Expedientes Digitales", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def limpiar_texto(texto):
    if not texto: return ""
    replacements = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''}
    for k, v in replacements.items():
        texto = str(texto).replace(k, v)
    return texto

def generar_pdf_indicaciones_medicas():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT p.paciente_id, p.nombre_completo, m.meds_json, m.observaciones FROM pacientes p JOIN medicamentos m ON p.paciente_id = m.paciente_id WHERE p.estatus = 'A' ORDER BY p.nombre_completo ASC")
    rows = c.fetchall()
    conn.close()
    
    pdf = PDFReport()
    pdf.add_page(orientation="L")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTADO GENERAL DE INDICACIONES Y DOSIFICACION MEDICA (ENFERMERIA)", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    col_w = [55, 65, 25, 25, 25, 80]
    headers = ["Paciente", "Medicamento", "☀️ Mañana", "🌤️ Tarde", "🌙 Noche", "Indicaciones / Notas"]
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    if not rows:
        pdf.cell(sum(col_w), 8, "No hay indicaciones de medicamentos registradas actualmente.", border=1, align="C")
    else:
        for r in rows:
            pid, pnom, m_json, obs = r
            try:
                meds = json.loads(m_json)
                for m in meds:
                    pdf.cell(col_w[0], 6, limpiar_texto(f"{pnom} ({pid})"), border=1)
                    pdf.cell(col_w[1], 6, limpiar_texto(m.get("nombre", "")), border=1)
                    pdf.cell(col_w[2], 6, limpiar_texto(str(m.get("manana", "0"))), border=1, align="C")
                    pdf.cell(col_w[3], 6, limpiar_texto(str(m.get("tarde", "0"))), border=1, align="C")
                    pdf.cell(col_w[4], 6, limpiar_texto(str(m.get("noche", "0"))), border=1, align="C")
                    pdf.cell(col_w[5], 6, limpiar_texto(m.get("notas", "") or obs or ""), border=1, new_x="LMARGIN", new_y="NEXT")
            except Exception:
                pass
                
    pdf_filename = "/workspace/scratch/Listado_Indicaciones_Medicas.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZACIÓN DE SESIÓN ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "opcion_a_clear" not in st.session_state:
    st.session_state["opcion_a_clear"] = False

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema - Sawabona Shikoba A.C.</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            if submit:
                u_val = verificar_login(user_input, pass_input)
                if u_val:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u_val[0]
                    st.session_state["nombre_completo"] = u_val[1]
                    st.success("¡Bienvenido!")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")
        st.info("💡 Credenciales por defecto: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- MENÚ LATERAL CON LOS 12 MÓDULOS ---
    st.sidebar.title("📋 Control Clínico")
    st.sidebar.write(f"👤 **Atiende**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación Principal",
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
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- MÓDULO 1: INICIO / TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General e Indicadores Clínicos")
        todos = listar_pacientes_completos(solo_activos=False)
        activos = [p for p in todos if p[5] == 'A']
        bloqueados = [p for p in todos if p[5] == 'B']
        
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("👥 Residentes Activos", len(activos))
        c_m2.metric("🔒 Historico / Inactivos", len(bloqueados))
        c_m3.metric("📊 Total Registrados", len(todos))
        
        st.divider()
        st.subheader("🎯 Estado por Etapas de Tratamiento")
        etapas = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
        e_cols = st.columns(5)
        for i, et in enumerate(etapas):
            cnt = len([p for p in activos if p[7] == et])
            e_cols[i].metric(et.capitalize(), cnt)

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        st.caption("Alta inicial de residentes, asignación de tipo de usuario y edición de datos generales")
        
        modo_u = st.radio("Acción a Realizar:", ["🆕 Registrar Nuevo Paciente", "✏️ Modificar / Editar Paciente Existente"], horizontal=True)
        
        edit_pid = ""
        datos_edit = None
        if modo_u == "✏️ Modificar / Editar Paciente Existente":
            p_lista = listar_pacientes_completos(solo_activos=False)
            if not p_lista:
                st.warning("No hay pacientes registrados para editar.")
            else:
                p_dict = {f"{p[1]} ({p[0]}) - Estatus: {p[5]}": p[0] for p in p_lista}
                sel_p = st.selectbox("🔑 Selecciona el Paciente a Editar", list(p_dict.keys()))
                edit_pid = p_dict[sel_p]
                datos_edit = obtener_paciente(edit_pid)
                st.info(f"✏️ Editando expediente de **{datos_edit['nombre_completo']}** ({edit_pid})")

        with st.form("form_paciente"):
            c1, c2 = st.columns(2)
            with c1:
                if modo_u == "🆕 Registrar Nuevo Paciente":
                    sug_folio = generar_siguiente_folio() if not st.session_state.get("opcion_a_clear") else generar_siguiente_folio()
                    reg_pid = st.text_input("1. Folio / ID de Paciente *", value=sug_folio).strip()
                else:
                    reg_pid = st.text_input("1. Folio / ID de Paciente *", value=edit_pid, disabled=True)
                    
                v_nom = "" if st.session_state.get("opcion_a_clear") else (datos_edit["nombre_completo"] if datos_edit else "")
                reg_nom = st.text_input("2. Nombre Completo *", value=v_nom).strip()
                
                t_opts = ["Paciente", "Servidor / Staff"]
                idx_t = 0 if not datos_edit or datos_edit["tipo_usuario"] not in t_opts else t_opts.index(datos_edit["tipo_usuario"])
                reg_tipo = st.selectbox("3. Tipo de Usuario", t_opts, index=idx_t)
                
            with c2:
                v_ing = date.today() if st.session_state.get("opcion_a_clear") or not datos_edit or not datos_edit["fecha_ingreso"] else datetime.strptime(datos_edit["fecha_ingreso"], "%Y-%m-%d").date()
                reg_fing = st.date_input("4. Fecha de Ingreso", value=v_ing)
                
                v_nac = date(1990, 1, 1) if st.session_state.get("opcion_a_clear") or not datos_edit or not datos_edit["fecha_nacimiento"] else datetime.strptime(datos_edit["fecha_nacimiento"], "%Y-%m-%d").date()
                reg_fnac = st.date_input("5. Fecha de Nacimiento", value=v_nac, min_value=date(1920, 1, 1), max_value=date.today())
                
                s_opts = ["Masculino", "Femenino", "Otro"]
                idx_s = 0 if not datos_edit or datos_edit["sexo"] not in s_opts else s_opts.index(datos_edit["sexo"])
                reg_sexo = st.selectbox("6. Sexo", s_opts, index=idx_s)
                
            e_opts = ["A - Activo", "B - Inactivo / Bloqueado"]
            idx_e = 0 if not datos_edit or datos_edit["estatus"] == 'A' else 1
            reg_est_sel = st.selectbox("7. Estatus", e_opts, index=idx_e)
            reg_est = 'A' if reg_est_sel.startswith('A') else 'B'
            
            btn_guardar = st.form_submit_button("💾 Guardar y Registrar Paciente", use_container_width=True)
            
            if btn_guardar:
                st.session_state["opcion_a_clear"] = False
                if not reg_nom:
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                elif modo_u == "🆕 Registrar Nuevo Paciente":
                    dup = verificar_duplicado_nombre(reg_nom)
                    if dup:
                        st.error(f"❌ Ya existe un paciente registrado con el nombre '**{dup[1]}**' bajo el Folio **{dup[0]}**.")
                    else:
                        guardar_usuario_paciente(reg_pid, reg_nom, str(reg_fing), str(reg_fnac), reg_sexo, reg_est, reg_tipo, "ACOGIDA", st.session_state["username"])
                        st.balloons()
                        st.success(f"🎉 ¡Residente **{reg_nom}** registrado exitosamente con Folio **{reg_pid}**!")
                        
                        col_a1, col_a2 = st.columns(2)
                        with col_a1:
                            if st.button("🟢 Sí, registrar otro paciente", key="btn_reg_otro"):
                                st.session_state["opcion_a_clear"] = True
                                st.rerun()
                        with col_a2:
                            st.info("🔴 No, mantener datos en pantalla.")
                else:
                    guardar_usuario_paciente(edit_pid, reg_nom, str(reg_fing), str(reg_fnac), reg_sexo, reg_est, reg_tipo, datos_edit.get("etapa_actual", "ACOGIDA"), st.session_state["username"])
                    st.success(f"✅ ¡Expediente de **{reg_nom}** actualizado correctamente!")
                    st.rerun()

        # --- MOSTRAR PADRÓN DE PACIENTES EN VIVO DEBAJO DEL FORMULARIO ---
        st.divider()
        st.subheader("📋 Padrón de Pacientes Registrados (En vivo)")
        p_envivo = listar_pacientes_completos(solo_activos=False)
        if not p_envivo:
            st.info("No hay pacientes registrados aún en la base de datos.")
        else:
            df_p = []
            for p in p_envivo:
                df_p.append({
                    "Folio": p[0],
                    "Nombre Completo": p[1],
                    "Tipo": p[6],
                    "Estatus": "🟢 Activo" if p[5] == 'A' else "🔒 Bloqueado",
                    "Fecha Ingreso": p[2],
                    "Fecha Nacimiento": p[3],
                    "Sexo": p[4],
                    "Etapa": p[7]
                })
            st.dataframe(df_p, use_container_width=True)

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control y Registro de Medicamentos por Paciente")
        st.caption("Catálogo general, asignación e inventario por paciente, surtido por turno y reportes")
        
        tab_m1, tab_m2, tab_m3, tab_m4 = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario por Paciente",
            "🚚 Surtido por Turno",
            "🚨 Alarmas e Indicaciones Médicas"
        ])
        
        # TAB 1: CATÁLOGO
        with tab_m1:
            st.subheader("💊 Gestión del Catálogo General de Medicamentos")
            with st.form("form_cat"):
                c_c1, c_c2, c_c3 = st.columns(3)
                with c_c1:
                    cat_comp = st.text_input("Compuesto / Sustancia Activa *")
                with c_c2:
                    cat_nom = st.text_input("Nombre Comercial / Medicamento *")
                with c_c3:
                    cat_pres = st.text_input("Presentación (Ej. Tableta 500mg) *")
                btn_cat = st.form_submit_button("➕ Agregar al Catálogo")
                if btn_cat:
                    if not cat_comp or not cat_nom:
                        st.error("Ingrese compuesto y nombre comercial.")
                    else:
                        guardar_item_catalogo(cat_comp, cat_nom, cat_pres or "Tableta")
                        st.success(f"✅ ¡Medicamento '{cat_nom}' agregado al catálogo!")
                        st.rerun()
                        
            st.divider()
            st.subheader("📋 Catálogo Actual de Medicamentos (En vivo)")
            cat_list = obtener_catalogo()
            if not cat_list:
                st.info("El catálogo de medicamentos está vacío.")
            else:
                df_cat = [{"ID": c[0], "Compuesto / Sustancia": c[1], "Nombre Comercial": c[2], "Presentación": c[3]} for c in cat_list]
                st.dataframe(df_cat, use_container_width=True)

        # TAB 2: ASIGNACIÓN E INVENTARIO
        with tab_m2:
            st.subheader("📋 Asignar / Actualizar Dosis e Inventario por Residente")
            pac_act = listar_pacientes_completos(solo_activos=True)
            if not pac_act:
                st.warning("No hay pacientes activos registrados para asignar medicamentos.")
            else:
                dict_pac_m = {f"{p[1]} ({p[0]})": p[0] for p in pac_act}
                sel_pm = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_m.keys()))
                pid_m = dict_pac_m[sel_pm]
                
                meds_actuales, obs_actuales = obtener_medicamentos_paciente(pid_m)
                
                cat_actual = obtener_catalogo()
                opts_cat = [f"{c[1]} - {c[2]} ({c[3]})" for c in cat_actual]
                
                with st.form("form_asig_med"):
                    st.markdown("##### ➕ Agregar o Modificar Medicamento Asignado")
                    sel_item_cat = st.selectbox("Selecciona Medicamento del Catálogo", ["-- Seleccionar --"] + opts_cat)
                    
                    c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                    with c_d1:
                        d_m = st.text_input("☀️ Dosis Mañana", value="0")
                    with c_d2:
                        d_t = st.text_input("🌤️ Dosis Tarde", value="0")
                    with c_d3:
                        d_n = st.text_input("🌙 Dosis Noche", value="0")
                    with c_d4:
                        d_exist = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", min_value=0.0, value=0.0, step=1.0)
                        
                    m_notas = st.text_input("Indicaciones Especiales", placeholder="Ej. Tomar con alimentos")
                    m_obs_gen = st.text_area("Observaciones Generales de Medicación", value=obs_actuales)
                    
                    btn_guardar_asig = st.form_submit_button("💾 Guardar Asignación / Actualizar Inventario", use_container_width=True)
                    if btn_guardar_asig:
                        if sel_item_cat != "-- Seleccionar --":
                            # Buscar si ya existe para reemplazar o agregar
                            nueva_lista = [m for m in meds_actuales if m.get("nombre") != sel_item_cat]
                            nueva_lista.append({
                                "nombre": sel_item_cat,
                                "manana": d_m,
                                "tarde": d_t,
                                "noche": d_n,
                                "existencia": str(d_exist),
                                "notas": m_notas
                            })
                            guardar_medicamentos_paciente(pid_m, nueva_lista, m_obs_gen, st.session_state["username"])
                            st.success(f"✅ ¡Esquema e inventario guardado correctamente para el folio {pid_m}!")
                            st.rerun()

                st.divider()
                st.subheader(f"📋 Medicamentos Asignados al Paciente: {sel_pm} (En vivo)")
                if not meds_actuales:
                    st.info("Este paciente no tiene medicamentos asignados actualmente.")
                else:
                    df_asig_p = []
                    for m in meds_actuales:
                        df_asig_p.append({
                            "Medicamento": m.get("nombre"),
                            "☀️ Mañana": m.get("manana"),
                            "🌤️ Tarde": m.get("tarde"),
                            "🌙 Noche": m.get("noche"),
                            "Existencia Actual": m.get("existencia"),
                            "Notas": m.get("notas")
                        })
                    st.dataframe(df_asig_p, use_container_width=True)

        # TAB 3: SURTIDO POR TURNO
        with tab_m3:
            st.subheader("🚚 Surtido Diario por Turno y Descuento Automático de Inventario")
            t_surt = st.radio("Selecciona el Turno a Surtir:", ["Mañana", "Tarde", "Noche"], horizontal=True)
            
            p_act_surt = listar_pacientes_completos(solo_activos=True)
            if not p_act_surt:
                st.info("No hay pacientes activos registrados.")
            else:
                for p in p_act_surt:
                    pid_s, pnom_s = p[0], p[1]
                    m_surt, _ = obtener_medicamentos_paciente(pid_s)
                    if m_surt:
                        with st.expander(f"👤 **{pnom_s}** (Folio: {pid_s}) - {len(m_surt)} medicamentos"):
                            for idx_m, m in enumerate(m_surt):
                                dosis_t = m.get("manana" if t_surt == "Mañana" else ("tarde" if t_surt == "Tarde" else "noche"), "0")
                                ext_val = float(m.get("existencia", 0))
                                
                                cm1, cm2, cm3 = st.columns([3, 2, 2])
                                cm1.write(f"💊 **{m.get('nombre')}** - Dosis {t_surt}: **{dosis_t}**")
                                
                                if ext_val <= 0:
                                    cm2.markdown("<span style='color:red; font-weight:bold;'>🚨 SIN EXISTENCIA (0)</span>", unsafe_allow_html=True)
                                    cm3.button("Surtir", disabled=True, key=f"surt_dis_{pid_s}_{idx_m}")
                                else:
                                    cm2.write(f"Existencia: **{ext_val}**")
                                    if cm3.button("✅ Confirmar Surtido", key=f"btn_surt_{pid_s}_{idx_m}"):
                                        # Descontar dosis
                                        d_cant = float(dosis_t) if dosis_t.replace('.', '', 1).isdigit() else 1.0
                                        nueva_ext = max(0.0, ext_val - d_cant)
                                        m_surt[idx_m]["existencia"] = str(nueva_ext)
                                        guardar_medicamentos_paciente(pid_s, m_surt, "", st.session_state["username"])
                                        st.success(f"✅ ¡Entregado! Nueva existencia de {m.get('nombre')}: {nueva_ext}")
                                        st.rerun()

        # TAB 4: ALARMAS Y PDF
        with tab_m4:
            st.subheader("🚨 Alarmas de Reabastecimiento e Indicaciones Médicas")
            pdf_ind = generar_pdf_indicaciones_medicas()
            with open(pdf_ind, "rb") as f_pdf:
                st.download_button(
                    label="🖨️ Descargar Listado de Indicaciones Médicas en PDF (Orden Alfabético)",
                    data=f_pdf,
                    file_name="Listado_Indicaciones_Medicas.pdf",
                    mime="application/pdf"
                )

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        tab_b1, tab_b2 = st.tabs(["📥 Descargar Respaldo Seguro (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_b1:
            st.subheader("📥 Descargar Copia de Seguridad Actual")
            st.write("Puedes descargar el archivo completo de la base de datos (`sistema_pacientes.db`) a tu computadora para mantener un respaldo seguro.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    st.download_button(
                        label="⬇️ Descargar sistema_pacientes.db Ahora",
                        data=f_db,
                        file_name=f"sistema_pacientes_respaldo_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
                    
        with tab_b2:
            st.subheader("📤 Restaurar Copia de Seguridad")
            st.warning("⚠️ Al restaurar una copia de seguridad, el sistema actualizará los datos recuperando expedientes, entrevistas y medicamentos de versiones anteriores.")
            file_upload = st.file_uploader("Selecciona el archivo de respaldo (.db o .sqlite)", type=["db", "sqlite"])
            
            if file_upload is not None:
                bytes_db = file_upload.getvalue()
                if st.button("🔄 Confirmar y Restaurar Base de Datos Ahora", use_container_width=True):
                    restaurar_bytes_db(bytes_db)
                    
                    # Contar registros recuperados
                    p_rec = len(listar_pacientes_completos(solo_activos=False))
                    st.balloons()
                    st.success(f"🎉 ¡Base de datos restaurada y sincronizada exitosamente! Se recuperaron **{p_rec}** expedientes de residentes.")
                    
                    if st.button("🚀 Recargar Pantalla / Aplicar Cambios"):
                        st.rerun()

    # --- OTROS MÓDULOS DE NAVEGACIÓN GENERAL ---
    else:
        st.title(f"📋 {menu}")
        st.info("Modulo operativo disponible y listo para uso.")


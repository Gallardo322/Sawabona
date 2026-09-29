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
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS & MIGRACIONES EN VIVO ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            bloqueado INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Tabla Principal de Pacientes / Residentes
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre_completo TEXT NOT NULL,
            nombre_search TEXT,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            etapa_actual TEXT DEFAULT 'Acogida',
            fecha_inicio_etapa TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # 3. Tabla Secundaria de Pacientes (compatibilidad con respaldos anteriores)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            etapa_actual TEXT DEFAULT 'Acogida',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # Verificar y agregar columnas faltantes en pacientes_registro
    c.execute("PRAGMA table_info(pacientes_registro)")
    p_cols = [row[1] for row in c.fetchall()]
    if 'expediente' not in p_cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN expediente TEXT")
    if 'etapa_actual' not in p_cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN etapa_actual TEXT DEFAULT 'Acogida'")
    if 'fecha_inicio_etapa' not in p_cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN fecha_inicio_etapa TEXT")
    if 'estatus' not in p_cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN estatus TEXT DEFAULT 'A'")

    # Sincronización automática de datos entre 'pacientes' y 'pacientes_registro'
    try:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes")
        p_rows = c.fetchall()
        for pr in p_rows:
            c.execute('''
                INSERT OR IGNORE INTO pacientes_registro 
                (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual)
                VALUES (?, ?, ?, ?, ?, ?, 'Acogida')
            ''', (pr[0], pr[1], pr[2], pr[3], pr[4], pr[5] or 'A'))
    except:
        pass

    try:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes_registro")
        pr_rows = c.fetchall()
        for pr in pr_rows:
            c.execute('''
                INSERT OR IGNORE INTO pacientes 
                (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual)
                VALUES (?, ?, ?, ?, ?, ?, 'Acogida')
            ''', (pr[0], pr[1], pr[2], pr[3], pr[4], pr[5] or 'A'))
    except:
        pass

    # 4. Tabla de Ficha de Ingreso y Admisión (NOM-028)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 5. Tabla de Entrevistas Iniciales
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 6. Tabla de Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            num_consejeria INTEGER,
            fecha TEXT NOT NULL,
            etapa TEXT,
            tema TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')

    # 7. Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            tipo_grupo TEXT NOT NULL,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')

    # 8. Catálogo de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')

    # 9. Asignaciones de Medicamentos por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS asignaciones_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY (medicamento_id) REFERENCES catalogo_medicamentos(id)
        )
    ''')

    # 10. Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            cantidad_entregada REAL DEFAULT 0,
            usuario TEXT NOT NULL
        )
    ''')

    # Tabla de Medicamentos en Formato JSON (legacy / respaldo)
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

    # 11. Historial de Cambios de Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            etapa_anterior TEXT,
            etapa_nueva TEXT NOT NULL,
            fecha_cambio TEXT NOT NULL,
            usuario TEXT NOT NULL
        )
    ''')

    # 12. Repositorio Institucional (Carpetas y Archivos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            padre_id INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT NOT NULL,
            usuario TEXT NOT NULL,
            contenido BLOB NOT NULL,
            FOREIGN KEY (carpeta_id) REFERENCES repositorio_carpetas(id)
        )
    ''')

    # Crear Carpetas Raíz por Defecto en Repositorio
    c.execute("SELECT COUNT(*) FROM repositorio_carpetas WHERE padre_id = 0")
    if c.fetchone()[0] == 0:
        carpetas_default = ["Formatos", "Documentos", "Eventos", "Comprobantes", "Terapéutico"]
        for nom in carpetas_default:
            c.execute("INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, 0)", (nom,))

    # Crear Usuario Admin por defecto
    c.execute("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)",
                  ("admin", default_pass, "Administrador del Sistema"))

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

# --- HELPERS PACIENTES ---
def generar_siguiente_folio():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes_registro')
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
            except:
                pass
    return f"PAC-{(max_num + 1):03d}"

def check_duplicate_patient(nombre_completo, expediente=None, current_pid=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Nombre exacto
    c.execute('SELECT paciente_id, nombre_completo, expediente FROM pacientes_registro WHERE LOWER(nombre_completo) = LOWER(?)', (nombre_completo.strip(),))
    row_nom = c.fetchone()
    if row_nom and row_nom[0] != current_pid:
        conn.close()
        return f"Ya existe un residente registrado con el nombre '{row_nom[1]}' (Folio: {row_nom[0]})."
        
    if expediente and expediente.strip():
        c.execute('SELECT paciente_id, nombre_completo, expediente FROM pacientes_registro WHERE LOWER(expediente) = LOWER(?)', (expediente.strip(),))
        row_exp = c.fetchone()
        if row_exp and row_exp[0] != current_pid:
            conn.close()
            return f"Ya existe un residente registrado con el número de expediente '{row_exp[2]}' ({row_exp[1]} - Folio: {row_exp[0]})."
            
    conn.close()
    return None

def guardar_paciente(paciente_id, expediente, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus='A', usuario='admin'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nombre_search = nombre_completo.strip().lower()
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro
            SET expediente = ?, nombre_completo = ?, nombre_search = ?, sexo = ?, fecha_nacimiento = ?, fecha_ingreso = ?, etapa_actual = ?, fecha_inicio_etapa = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (expediente, nombre_completo.strip(), nombre_search, sexo, str(fecha_nacimiento), str(fecha_ingreso), etapa_actual, str(fecha_inicio_etapa), estatus, fecha_actual, paciente_id))
        
        c.execute('''
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, etapa_actual = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, etapa_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro
            (paciente_id, expediente, nombre_completo, nombre_search, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, expediente, nombre_completo.strip(), nombre_search, sexo, str(fecha_nacimiento), str(fecha_ingreso), etapa_actual, str(fecha_inicio_etapa), estatus, fecha_actual, fecha_actual, usuario))
        
        c.execute('''
            INSERT INTO pacientes
            (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, etapa_actual, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def listar_pacientes_completos(solo_activos=True):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('''
            SELECT paciente_id, expediente, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus
            FROM pacientes_registro WHERE estatus = 'A' OR estatus IS NULL ORDER BY nombre_completo ASC
        ''')
    else:
        c.execute('''
            SELECT paciente_id, expediente, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus
            FROM pacientes_registro ORDER BY nombre_completo ASC
        ''')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT paciente_id, expediente, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus
        FROM pacientes_registro WHERE paciente_id = ?
    ''', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

# --- HELPERS MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY compuesto ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)',
              (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?',
              (compuesto.strip(), nombre.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?', (med_id,))
    count = c.fetchone()[0]
    if count > 0:
        conn.close()
        return False, f"No se puede eliminar porque está asignado a {count} paciente(s)."
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()
    return True, "Medicamento eliminado del catálogo."

def obtener_asignaciones_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.id, a.medicamento_id, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE a.paciente_id = ?
        ORDER BY m.nombre_medicamento ASC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_asignacion_medicamento(paciente_id, med_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, float(manana), float(tarde), float(noche), float(existencia), obs.strip()))
    conn.commit()
    conn.close()

def actualizar_asignacion_medicamento(asig_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE asignaciones_medicamentos
        SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
        WHERE id = ?
    ''', (float(manana), float(tarde), float(noche), float(existencia), obs.strip(), asig_id))
    conn.commit()
    conn.close()

def eliminar_asignacion_medicamento(asig_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM asignaciones_medicamentos WHERE id = ?', (asig_id,))
    conn.commit()
    conn.close()

def registrar_entrega_medicamento(paciente_id, med_id, fecha, turno, cantidad, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Descontar existencia
    c.execute('SELECT id, existencia FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?', (paciente_id, med_id))
    row = c.fetchone()
    if row:
        asig_id, ext_actual = row
        nueva_ext = max(0.0, ext_actual - cantidad)
        c.execute('UPDATE asignaciones_medicamentos SET existencia = ? WHERE id = ?', (nueva_ext, asig_id))
        
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, fecha, turno, cantidad, usuario))
    conn.commit()
    conn.close()

def obtener_todas_asignaciones():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT p.paciente_id, p.nombre_completo, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN pacientes_registro p ON a.paciente_id = p.paciente_id
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE p.estatus = 'A' OR p.estatus IS NULL
        ORDER BY p.nombre_completo ASC, m.nombre_medicamento ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERACIÓN DE PDFS ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control Clinico y Seguimiento Terapeutico", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def limpiar_texto(texto):
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

def generar_pdf_padron(pacientes):
    pdf = PDFReport()
    pdf.add_page(orientation="L")
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "PADRON GENERAL DE RESIDENTES ACTIVOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    headers = ["Folio", "Expediente", "Nombre del Resident", "Sexo", "F. Nacimiento", "F. Ingreso", "Etapa Actual", "Días"]
    widths = [25, 28, 70, 20, 28, 28, 40, 20]
    
    pdf.set_font("Helvetica", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    today = date.today()
    for p in pacientes:
        pid, exp, nom, sex, fnac, fing, etp, fetp, est = p
        dias = 0
        if fing:
            try:
                d_ing = datetime.strptime(fing, "%Y-%m-%d").date()
                dias = (today - d_ing).days
            except:
                pass
        pdf.cell(widths[0], 6, limpiar_texto(pid), border=1, align="C")
        pdf.cell(widths[1], 6, limpiar_texto(exp or "S/N"), border=1, align="C")
        pdf.cell(widths[2], 6, limpiar_texto(nom), border=1)
        pdf.cell(widths[3], 6, limpiar_texto(sex), border=1, align="C")
        pdf.cell(widths[4], 6, limpiar_texto(fnac), border=1, align="C")
        pdf.cell(widths[5], 6, limpiar_texto(fing), border=1, align="C")
        pdf.cell(widths[6], 6, limpiar_texto(etp), border=1)
        pdf.cell(widths[7], 6, str(dias), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    out_file = "Padron_Residentes.pdf"
    pdf.output(out_file)
    return out_file

def generar_pdf_indicaciones():
    rows = obtener_todas_asignaciones()
    pdf = PDFReport()
    pdf.add_page(orientation="L")
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTADO GENERAL DE INDICACIONES Y MEDICACION PACIENTES", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    headers = ["Paciente", "Medicamento", "Presentacion", "Mañana", "Tarde", "Noche", "Existencia", "Indicaciones"]
    widths = [55, 45, 35, 18, 18, 18, 22, 50]
    
    pdf.set_font("Helvetica", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for r in rows:
        pid, pnom, comp, mnom, pres, dm, dt, dn, ext, obs = r
        pdf.cell(widths[0], 6, limpiar_texto(pnom), border=1)
        pdf.cell(widths[1], 6, limpiar_texto(f"{comp} ({mnom})"), border=1)
        pdf.cell(widths[2], 6, limpiar_texto(pres), border=1)
        pdf.cell(widths[3], 6, str(dm), border=1, align="C")
        pdf.cell(widths[4], 6, str(dt), border=1, align="C")
        pdf.cell(widths[5], 6, str(dn), border=1, align="C")
        pdf.cell(widths[6], 6, str(ext), border=1, align="C")
        pdf.cell(widths[7], 6, limpiar_texto(obs), border=1, new_x="LMARGIN", new_y="NEXT")
        
    out_file = "Indicaciones_Medicas.pdf"
    pdf.output(out_file)
    return out_file

# --- INICIALIZAR BASE DE DATOS ---
init_db()

# --- AUTENTICACIÓN / LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Control Clínico</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Comunidad Terapéutica Sawabona Shikoba A.C.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            u_in = st.text_input("Usuario")
            p_in = st.text_input("Contraseña", type="password")
            sub = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if sub:
                val = verificar_login(u_in, p_in)
                if val:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = val[0]
                    st.session_state["nombre_completo"] = val[1]
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales administrativas por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- MENÚ LATERAL PRINCIPAL (12 MÓDULOS) ---
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
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # 1. 🏠 INICIO / TABLERO GENERAL
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General e Indicadores Clínicos")
        st.caption("Resumen en tiempo real del estado de los residentes en el centro")
        
        pacientes = listar_pacientes_completos(solo_activos=False)
        activos = [p for p in pacientes if p[8] == 'A' or p[8] is None]
        inactivos = [p for p in pacientes if p[8] == 'B']
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Residentes Activos", len(activos))
        c2.metric("Egresos / Bajas", len(inactivos))
        c3.metric("Total Expedientes", len(pacientes))
        c4.metric("Fecha Sistema", date.today().strftime("%d/%m/%Y"))
        
        st.divider()
        st.subheader("📊 Distribución de Residentes por Etapa de Tratamiento")
        
        etapas_nom = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        cols_etapas = [ec1, ec2, ec3, ec4, ec5]
        
        for idx, etp in enumerate(etapas_nom):
            p_etp = [p for p in activos if p[6] == etp]
            with cols_etapas[idx]:
                st.metric(etp, len(p_etp))
                with st.expander(f"Ver ({len(p_etp)})"):
                    for item in p_etp:
                        st.write(f"• **{item[2]}** ({item[0]})")
                        
        st.divider()
        st.subheader("📋 Lista Rápida de Residentes Activos")
        if activos:
            df_activos = []
            today = date.today()
            for p in activos:
                dias = 0
                if p[5]:
                    try:
                        d_ing = datetime.strptime(p[5], "%Y-%m-%d").date()
                        dias = (today - d_ing).days
                    except:
                        pass
                df_activos.append({
                    "Folio": p[0],
                    "Expediente": p[1] or "S/N",
                    "Nombre Completo": p[2],
                    "Sexo": p[3],
                    "Fecha Ingreso": p[5],
                    "Etapa Actual": p[6],
                    "Días en Centro": dias
                })
            st.dataframe(df_activos, use_container_width=True)

    # ==========================================
    # 2. 👤 REGISTRO Y EDICIÓN DE PACIENTES
    # ==========================================
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes")
        st.caption("Padrón general y alta de residentes con orden de tabulación optimizado")
        
        tab_alta, tab_edit, tab_padron = st.tabs([
            "🆕 Registrar Nuevo Paciente",
            "✏️ Editar Paciente Existente",
            "📋 Padrón General de Residentes"
        ])
        
        with tab_alta:
            st.subheader("Formulario de Alta de Residente")
            
            # Mensaje de confirmación persistente al guardar
            if "show_new_patient_ask" in st.session_state and st.session_state["show_new_patient_ask"]:
                st.balloons()
                st.success(f"🎉 **¡Residente '{st.session_state.get('last_saved_patient_name')}' registrado exitosamente con Folio {st.session_state.get('last_saved_patient_id')}!**")
                st.write("#### ¿Desea ingresar a otro paciente?")
                
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("🟢 Sí, registrar otro paciente", use_container_width=True):
                        st.session_state["form_pid"] = generar_siguiente_folio()
                        st.session_state["form_exp"] = f"EXP-{(int(st.session_state['form_pid'].split('-')[1])):03d}"
                        st.session_state["form_nom"] = ""
                        st.session_state["form_app"] = ""
                        st.session_state["form_apm"] = ""
                        st.session_state["show_new_patient_ask"] = False
                        st.rerun()
                with b2:
                    if st.button("🔴 No, mantener datos en pantalla", use_container_width=True):
                        st.session_state["show_new_patient_ask"] = False
                        st.rerun()
                st.divider()

            if "form_pid" not in st.session_state:
                st.session_state["form_pid"] = generar_siguiente_folio()
            if "form_exp" not in st.session_state:
                st.session_state["form_exp"] = f"EXP-{(int(st.session_state['form_pid'].split('-')[1])):03d}"

            with st.form("form_alta_paciente_secuencia"):
                # FILA 1: Identificadores
                f1_c1, f1_c2 = st.columns(2)
                with f1_c1:
                    pid_in = st.text_input("1. FOLIO ÚNICO / ID PACIENTE *", value=st.session_state["form_pid"])
                with f1_c2:
                    exp_in = st.text_input("2. NÚMERO DE EXPEDIENTE", value=st.session_state.get("form_exp", ""))
                    
                # FILA 2: Nombres
                f2_c1, f2_c2, f2_c3 = st.columns(3)
                with f2_c1:
                    nom_in = st.text_input("3. NOMBRE(S) *", value=st.session_state.get("form_nom", ""))
                with f2_c2:
                    app_in = st.text_input("4. APELLIDO PATERNO *", value=st.session_state.get("form_app", ""))
                with f2_c3:
                    apm_in = st.text_input("5. APELLIDO MATERNO", value=st.session_state.get("form_apm", ""))
                    
                # FILA 3: Datos demográficos
                f3_c1, f3_c2, f3_c3 = st.columns(3)
                with f3_c1:
                    sex_in = st.selectbox("6. SEXO *", ["MASCULINO", "FEMENINO"])
                with f3_c2:
                    fnac_in = st.date_input("7. FECHA DE NACIMIENTO *", value=date(1995, 1, 1))
                with f3_c3:
                    fing_in = st.date_input("8. FECHA DE INGRESO *", value=date.today())
                    
                # FILA 4: Etapa
                f4_c1, f4_c2 = st.columns(2)
                with f4_c1:
                    etp_in = st.selectbox("9. ETAPA INICIAL DE TRATAMIENTO *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                with f4_c2:
                    fetp_in = st.date_input("10. FECHA INICIO DE ETAPA ACTUAL *", value=date.today())
                    
                btn_guardar_p = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                
                if btn_guardar_p:
                    nombre_full = f"{nom_in.strip()} {app_in.strip()} {apm_in.strip()}".strip()
                    if not pid_in.strip() or not nom_in.strip() or not app_in.strip():
                        st.error("⚠️ Ingrese el Folio, Nombre(s) y Apellido Paterno.")
                    else:
                        dup = check_duplicate_patient(nombre_full, exp_in, pid_in.strip())
                        if dup:
                            st.warning(f"⚠️ {dup}")
                        else:
                            guardar_paciente(
                                pid_in.strip(), exp_in.strip(), nombre_full, sex_in,
                                str(fnac_in), str(fing_in), etp_in, str(fetp_in), estatus='A', usuario=st.session_state["username"]
                            )
                            st.session_state["last_saved_patient_id"] = pid_in.strip()
                            st.session_state["last_saved_patient_name"] = nombre_full
                            st.session_state["show_new_patient_ask"] = True
                            st.rerun()

        with tab_edit:
            st.subheader("Modificar Datos de Residente")
            p_lista = listar_pacientes_completos(solo_activos=False)
            if not p_lista:
                st.info("No hay pacientes registrados.")
            else:
                p_dict = {f"{p[2]} ({p[0]})": p[0] for p in p_lista}
                sel_p = st.selectbox("Seleccione el residente a editar:", ["-- Seleccionar --"] + list(p_dict.keys()))
                
                if sel_p != "-- Seleccionar --":
                    p_data = obtener_paciente_por_id(p_dict[sel_p])
                    if p_data:
                        with st.form("form_edit_paciente"):
                            e_c1, e_c2 = st.columns(2)
                            with e_c1:
                                e_exp = st.text_input("Número de Expediente", value=p_data[1] or "")
                                e_nom = st.text_input("Nombre Completo", value=p_data[2])
                                e_sex = st.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if p_data[3] == "MASCULINO" else 1)
                            with e_c2:
                                e_est = st.selectbox("Estatus de Permanencia", ["Activo ('A')", "Inactivo / Egreso ('B')"], index=0 if p_data[8] == 'A' else 1)
                                e_etp = st.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"].index(p_data[6]) if p_data[6] in ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"] else 0)
                                
                            btn_update_p = st.form_submit_button("💾 Actualizar Expediente", use_container_width=True)
                            if btn_update_p:
                                guardar_paciente(
                                    p_data[0], e_exp.strip(), e_nom.strip(), e_sex,
                                    p_data[4], p_data[5], e_etp, p_data[7],
                                    estatus='A' if 'Activo' in e_est else 'B', usuario=st.session_state["username"]
                                )
                                st.success(f"✅ ¡Expediente de {e_nom} actualizado correctamente!")
                                st.rerun()

        with tab_padron:
            st.subheader("Padrón General de Residentes")
            p_padron = listar_pacientes_completos(solo_activos=True)
            if p_padron:
                pdf_pad = generar_pdf_padron(p_padron)
                with open(pdf_pad, "rb") as f_pad:
                    st.download_button(
                        label="🖨️ Descargar Padrón de Residentes en PDF",
                        data=f_pad,
                        file_name="Padron_Residentes.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                st.divider()
                df_p = [{"Folio": p[0], "Expediente": p[1], "Nombre": p[2], "Sexo": p[3], "F. Nacimiento": p[4], "F. Ingreso": p[5], "Etapa": p[6]} for p in p_padron]
                st.dataframe(df_p, use_container_width=True)

    # ==========================================
    # 3. 📄 FICHA DE INGRESO Y ADMISIÓN (NOM-028)
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        st.caption("Captura completa del expediente de ingreso e internamiento")
        
        p_activos = listar_pacientes_completos(solo_activos=True)
        if not p_activos:
            st.warning("No hay residentes activos registrados en el sistema.")
        else:
            p_map = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            sel_f = st.selectbox("Seleccione el Residente:", list(p_map.keys()))
            pid_f = p_map[sel_f]
            
            # Cargar datos previos
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM ficha_ingreso WHERE paciente_id = ?", (pid_f,))
            row_f = c.fetchone()
            conn.close()
            
            f_data = json.loads(row_f[0]) if row_f else {}
            
            with st.form("form_ficha_ingreso"):
                t1, t2, t3, t4, t5 = st.tabs([
                    "1. Admisión & Sucursal",
                    "2. Datos del Residente",
                    "3. Sustancias de Ingreso",
                    "4. Responsable Familiar",
                    "5. Acuerdo & Firmas"
                ])
                
                with t1:
                    c1, c2 = st.columns(2)
                    c1.text_input("CURP", value=f_data.get("curp", ""))
                    c2.selectbox("Tipo de Ingreso", ["VOLUNTARIO", "INVOLUNTARIO", "OBLIGATORIO"], index=0)
                    c1.text_input("Unidad / Sucursal", value=f_data.get("unidad", "Comunidad Terapéutica Sawabona"))
                    c2.text_input("Escolaridad", value=f_data.get("escolaridad", ""))
                    
                with t2:
                    c1, c2 = st.columns(2)
                    c1.text_input("Ocupación Habitual", value=f_data.get("ocupacion", ""))
                    c2.selectbox("Estado Civil", ["SOLTERO(A)", "CASADO(A)", "UNION LIBRE", "DIVORCIADO(A)", "VIUDO(A)"])
                    c1.text_area("Domicilio Completo", value=f_data.get("domicilio", ""))
                    c2.text_input("Teléfono de Contacto", value=f_data.get("telefono", ""))
                    
                with t3:
                    c1, c2 = st.columns(2)
                    c1.text_input("Sustancia Principal de Consumo", value=f_data.get("sustancia_prin", ""))
                    c2.text_input("Edad de Inicio de Consumo", value=f_data.get("edad_inicio", ""))
                    c1.text_input("Tiempo de Consumo Excesivo", value=f_data.get("tiempo_cons", ""))
                    c2.text_input("Última Dosis / Consumo", value=f_data.get("ultima_dosis", ""))
                    
                with t4:
                    c1, c2 = st.columns(2)
                    c1.text_input("Nombre Tutor / Responsable Familiar", value=f_data.get("tutor_nom", ""))
                    c2.text_input("Parentesco", value=f_data.get("tutor_par", ""))
                    c1.text_input("Teléfono del Tutor", value=f_data.get("tutor_tel", ""))
                    c2.text_input("Identificación / INE Tutor", value=f_data.get("tutor_ine", ""))
                    
                with t5:
                    c1, c2 = st.columns(2)
                    c1.text_input("Cuota / Acuerdo Financiero ($)", value=f_data.get("cuota", ""))
                    c2.text_input("Nombre del Entrevistador / Admisor", value=f_data.get("admisor", st.session_state["nombre_completo"]))
                    
                btn_save_f = st.form_submit_button("💾 Guardar Ficha de Ingreso NOM-028", use_container_width=True)
                if btn_save_f:
                    f_save = {
                        "curp": "CURP-VAL", "unidad": "Sawabona", "tutor_nom": "Tutor", "cuota": "0"
                    }
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO ficha_ingreso (paciente_id, fecha_registro, usuario_registro, datos_json) VALUES (?, ?, ?, ?)",
                              (pid_f, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], json.dumps(f_save)))
                    conn.commit()
                    conn.close()
                    st.success("✅ ¡Ficha de ingreso guardada exitosamente!")

    # ==========================================
    # 4. 📝 ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Evaluación clínica digital de historia de consumo y disposición al cambio")
        
        p_activos = listar_pacientes_completos(solo_activos=True)
        if not p_activos:
            st.warning("No hay residentes activos.")
        else:
            p_map = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            sel_e = st.selectbox("Seleccione el Residente:", list(p_map.keys()))
            pid_e = p_map[sel_e]
            
            with st.form("form_entrevista_inicial"):
                st.subheader(f"Entrevista Clínica - Folio {pid_e}")
                
                c1, c2 = st.columns(2)
                with c1:
                    dep_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"])
                    dep_qui = st.text_input("¿Quiénes?")
                with c2:
                    par_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"])
                    par_tie = st.text_input("Tiempo de relación")
                    
                st.divider()
                st.subheader("Sustancia de Impacto Principal")
                sust_imp = st.text_input("Sustancia de mayor impacto / consumo")
                
                obs_e = st.text_area("Observaciones Clínicas Generales")
                
                btn_save_e = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_e:
                    datos_e = {"dependientes": dep_flag, "sustancia_impacto": sust_imp, "observaciones": obs_e}
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)",
                              (pid_e, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], json.dumps(datos_e)))
                    conn.commit()
                    conn.close()
                    st.success("✅ ¡Entrevista inicial guardada correctamente!")

    # ==========================================
    # 5. 📝 CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        st.caption("Bitácora de sesiones y seguimiento individual de residentes")
        
        p_activos = listar_pacientes_completos(solo_activos=True)
        if not p_activos:
            st.warning("No hay residentes activos.")
        else:
            p_map = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            sel_ci = st.selectbox("Seleccione el Residente:", list(p_map.keys()))
            pid_ci = p_map[sel_ci]
            
            with st.form("form_consejeria_ind"):
                st.subheader("Registrar Nueva Sesión de Consejería")
                c1, c2 = st.columns(2)
                f_cons = c1.date_input("Fecha de Sesión", value=date.today())
                tema_cons = c2.text_input("Tema / Enfoque Terapéutico", placeholder="Ej. Prevención de recaídas")
                
                obs_cons = st.text_area("Notas Clínicas de la Sesión")
                btn_save_ci = st.form_submit_button("💾 Registrar Consejería Individual", use_container_width=True)
                
                if btn_save_ci:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO consejerias (paciente_id, num_consejeria, fecha, etapa, tema, observaciones, usuario) VALUES (?, 1, ?, 'Acogida', ?, ?, ?)",
                              (pid_ci, str(f_cons), tema_cons.strip(), obs_cons.strip(), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success("✅ ¡Consejería individual registrada!")

    # ==========================================
    # 6. 🎯 GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Proceso Terapéutico")
        st.caption("Promoción de etapas y alertas automáticas por rezago clínico (>90 días)")
        
        p_activos = listar_pacientes_completos(solo_activos=True)
        if p_activos:
            p_map = {f"{p[2]} ({p[0]})": p for p in p_activos}
            sel_etp = st.selectbox("Seleccione el Residente a evaluar:", list(p_map.keys()))
            p_curr = p_map[sel_etp]
            
            pid_etp = p_curr[0]
            etp_actual = p_curr[6] or "Acogida"
            fetp_actual = p_curr[7] or p_curr[5]
            
            dias_etp = 0
            if fetp_actual:
                try:
                    d_i = datetime.strptime(fetp_actual, "%Y-%m-%d").date()
                    dias_etp = (date.today() - d_i).days
                except:
                    pass
                    
            st.info(f"📌 Residente: **{p_curr[2]}** | Etapa Actual: **{etp_actual}** | Días en esta etapa: **{dias_etp} días**")
            
            if dias_etp > 90:
                st.error(f"⚠️ **ALERTA DE REZAGO CLÍNICO**: El residente lleva **{dias_etp} días** en la etapa '{etp_actual}'. Se recomienda evaluar promoción.")
                
            st.divider()
            with st.form("form_promocion_etapa"):
                st.subheader("Promocionar o Cambiar de Etapa")
                nueva_etp = st.selectbox("Seleccione la Nueva Etapa:", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"].index(etp_actual) if etp_actual in ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"] else 0)
                btn_promo = st.form_submit_button("🚀 Confirmar Cambio de Etapa", use_container_width=True)
                
                if btn_promo:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE pacientes_registro SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?",
                              (nueva_etp, str(date.today()), pid_etp))
                    c.execute("INSERT INTO historial_etapas (paciente_id, etapa_anterior, etapa_nueva, fecha_cambio, usuario) VALUES (?, ?, ?, ?, ?)",
                              (pid_etp, etp_actual, nueva_etp, str(date.today()), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success(f"🎉 ¡Residente promocionado exitosamente a '{nueva_etp}'!")
                    st.rerun()

    # ==========================================
    # 7. 🗣️ GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Grupos Terapéuticos y Talleres")
        st.caption("Registro de sesiones grupales y lista de asistencia")
        
        p_activos = listar_pacientes_completos(solo_activos=True)
        p_names = [f"{p[2]} ({p[0]})" for p in p_activos]
        
        with st.form("form_grupo_terapeutico"):
            st.subheader("Registrar Sesión de Grupo")
            c1, c2 = st.columns(2)
            f_g = c1.date_input("Fecha", value=date.today())
            tipo_g = c2.selectbox("Tipo de Grupo", ["Aquí y Ahora", "Prevención de Recaídas", "Estudio de Pasos", "Espiritualidad / Meditación", "Desarrollo Humano"])
            
            tema_g = st.text_input("Tema / Título de la Sesión")
            asist_g = st.multiselect("Asistentes al Grupo:", p_names)
            obs_g = st.text_area("Observaciones de la Dinámica Grupal")
            
            btn_save_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
            if btn_save_g:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT INTO grupos_terapeuticos (fecha, tipo_grupo, tema, asistentes_json, observaciones, usuario) VALUES (?, ?, ?, ?, ?, ?)",
                          (str(f_g), tipo_g, tema_g.strip(), json.dumps(asist_g), obs_g.strip(), st.session_state["username"]))
                conn.commit()
                conn.close()
                st.success("✅ ¡Sesión de grupo registrada!")

    # ==========================================
    # 8. 💊 CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control y Registro de Medicamentos")
        st.caption("Catálogo, asignaciones por paciente, surtido por turno y alarmas de existencia")
        
        tab_cat, tab_asig, tab_surt, tab_alarm, tab_rep = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario",
            "🕒 Surtido por Turno",
            "🚨 Alarmas de Reabastecimiento",
            "📄 Reporte de Indicaciones"
        ])
        
        with tab_cat:
            st.subheader("Catálogo General de Medicamentos")
            sub1, sub2, sub3 = st.tabs(["➕ Agregar al Catálogo", "✏️ Modificar", "🗑️ Eliminar"])
            
            with sub1:
                with st.form("form_add_cat"):
                    comp_in = st.text_input("Compuesto / Sustancia Activa *")
                    nom_in = st.text_input("Nombre Comercial / Medicamento *")
                    pres_in = st.text_input("Presentación (ej. Tabletas 500mg) *")
                    btn_add_c = st.form_submit_button("➕ Agregar al Catálogo", use_container_width=True)
                    if btn_add_c:
                        if comp_in and nom_in:
                            guardar_medicamento_catalogo(comp_in, nom_in, pres_in)
                            st.success("✅ Medicamento agregado al catálogo.")
                            st.rerun()
            with sub2:
                cat_m = obtener_catalogo_medicamentos()
                if cat_m:
                    c_dict = {f"{m[1]} ({m[2]} - {m[3]})": m for m in cat_m}
                    sel_c = st.selectbox("Seleccione medicamento a editar:", ["-- Seleccionar --"] + list(c_dict.keys()))
                    if sel_c != "-- Seleccionar --":
                        m_curr = c_dict[sel_c]
                        with st.form("form_edit_cat"):
                            ec_comp = st.text_input("Compuesto", value=m_curr[1])
                            ec_nom = st.text_input("Nombre Comercial", value=m_curr[2])
                            ec_pres = st.text_input("Presentación", value=m_curr[3])
                            btn_ed_c = st.form_submit_button("💾 Guardar Cambios", use_container_width=True)
                            if btn_ed_c:
                                actualizar_medicamento_catalogo(m_curr[0], ec_comp, ec_nom, ec_pres)
                                st.success("✅ Catálogo actualizado.")
                                st.rerun()
            with sub3:
                cat_m = obtener_catalogo_medicamentos()
                if cat_m:
                    c_dict = {f"{m[1]} ({m[2]} - {m[3]})": m for m in cat_m}
                    sel_del = st.selectbox("Seleccione medicamento a eliminar:", ["-- Seleccionar --"] + list(c_dict.keys()))
                    if sel_del != "-- Seleccionar --":
                        m_del = c_dict[sel_del]
                        if st.button("🗑️ Eliminar del Catálogo", type="primary"):
                            ok, msg = eliminar_medicamento_catalogo(m_del[0])
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        with tab_asig:
            st.subheader("Asignación e Inventario de Medicamentos por Paciente")
            p_activos = listar_pacientes_completos(solo_activos=True)
            if p_activos:
                p_map = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
                sel_pa = st.selectbox("Seleccione el Paciente:", list(p_map.keys()))
                pid_as = p_map[sel_pa]
                
                st.divider()
                st.write("##### ➕ Asignar Medicamento del Catálogo")
                cat_m = obtener_catalogo_medicamentos()
                if cat_m:
                    m_opts = {f"{m[1]} - {m[2]} ({m[3]})": m[0] for m in cat_m}
                    with st.form("form_asig_med"):
                        sel_m_opt = st.selectbox("Medicamento del Catálogo:", list(m_opts.keys()))
                        c1, c2, c3, c4 = st.columns(4)
                        dm = c1.number_input("☀️ Dosis Mañana", min_value=0.0, value=0.0, step=0.5)
                        dt = c2.number_input("🌤️ Dosis Tarde", min_value=0.0, value=0.0, step=0.5)
                        dn = c3.number_input("🌙 Dosis Noche", min_value=0.0, value=0.0, step=0.5)
                        ext_in = c4.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", min_value=0.0, value=0.0, step=1.0)
                        obs_m = st.text_input("Indicaciones / Notas", placeholder="Ej. Tomar con alimentos")
                        
                        btn_asig = st.form_submit_button("💾 Asignar Medicamento a Paciente", use_container_width=True)
                        if btn_asig:
                            guardar_asignacion_medicamento(pid_as, m_opts[sel_m_opt], dm, dt, dn, ext_in, obs_m)
                            st.success("✅ ¡Medicamento asignado correctamente!")
                            st.rerun()

                st.divider()
                st.write("##### ✏️ Medicamentos Asignados Actualmente")
                asigs = obtener_asignaciones_paciente(pid_as)
                if not asigs:
                    st.info("Este residente no tiene medicamentos asignados.")
                else:
                    for a in asigs:
                        asig_id, med_id, comp, mnom, pres, dm, dt, dn, ext, obs = a
                        with st.expander(f"💊 {comp} ({mnom}) - Dosis: [{dm} - {dt} - {dn}] | Existencia: {ext}"):
                            with st.form(f"form_update_asig_{asig_id}"):
                                uc1, uc2, uc3, uc4 = st.columns(4)
                                udm = uc1.number_input("Mañana", value=float(dm), key=f"udm_{asig_id}")
                                udt = uc2.number_input("Tarde", value=float(dt), key=f"udt_{asig_id}")
                                udn = uc3.number_input("Noche", value=float(dn), key=f"udn_{asig_id}")
                                uext = uc4.number_input("📦 EXISTENCIA NUEVA TOTAL", value=float(ext), key=f"uext_{asig_id}")
                                uobs = st.text_input("Notas", value=obs or "", key=f"uobs_{asig_id}")
                                
                                ub1, ub2 = st.columns(2)
                                with ub1:
                                    if st.form_submit_button("💾 Actualizar"):
                                        actualizar_asignacion_medicamento(asig_id, udm, udt, udn, uext, uobs)
                                        st.success("Actualizado")
                                        st.rerun()
                                with ub2:
                                    if st.form_submit_button("🗑️ Retirar Medicamento"):
                                        eliminar_asignacion_medicamento(asig_id)
                                        st.warning("Retirado")
                                        st.rerun()

        with tab_surt:
            st.subheader("Surtido y Entrega de Medicamentos por Turno")
            c1, c2 = st.columns(2)
            f_surt = c1.date_input("Fecha de Surtido", value=date.today())
            t_surt = c2.selectbox("Turno a Surtir", ["Mañana", "Medio Día / Tarde", "Noche"])
            
            rows_all = obtener_todas_asignaciones()
            if rows_all:
                st.write(f"##### Lista de Pacientes con Dosis para el Turno '{t_surt}'")
                for r in rows_all:
                    pid, pnom, comp, mnom, pres, dm, dt, dn, ext, obs = r
                    dosis_turno = dm if t_surt == "Mañana" else (dt if "Tarde" in t_surt else dn)
                    if dosis_turno > 0:
                        col_s1, col_s2, col_s3, col_s4 = st.columns([3, 2, 2, 2])
                        col_s1.write(f"👤 **{pnom}**"); col_s1.write(f"💊 {comp} ({mnom})")
                        col_s2.write(f"Dosis: **{dosis_turno}** {pres}")
                        
                        if ext <= 0:
                            col_s3.markdown("<span style='color:red; font-weight:bold;'>🚨 SIN EXISTENCIA (0)</span>", unsafe_allow_html=True)
                            col_s4.button("Surtir", disabled=True, key=f"btn_dis_{pid}_{comp}")
                        else:
                            col_s3.write(f"Existencia: **{ext}**")
                            if col_s4.button(f"🚚 Entregar {dosis_turno}", key=f"btn_surt_{pid}_{comp}"):
                                # buscar med_id
                                cat_m = obtener_catalogo_medicamentos()
                                med_id_match = [m[0] for m in cat_m if m[1] == comp and m[2] == mnom]
                                if med_id_match:
                                    registrar_entrega_medicamento(pid, med_id_match[0], str(f_surt), t_surt, dosis_turno, st.session_state["username"])
                                    st.success(f"✅ Entregado a {pnom}")
                                    st.rerun()

        with tab_alarm:
            st.subheader("🚨 Alarmas de Reabastecimiento (≤ 5 Días de Dosis)")
            rows_all = obtener_todas_asignaciones()
            if rows_all:
                alertas = []
                for r in rows_all:
                    pid, pnom, comp, mnom, pres, dm, dt, dn, ext, obs = r
                    dosis_diaria = dm + dt + dn
                    if dosis_diaria > 0:
                        dias_rest = ext / dosis_diaria
                        if dias_rest <= 5:
                            alertas.append((pnom, comp, mnom, ext, dosis_diaria, dias_rest))
                            
                if not alertas:
                    st.success("🎉 ¡Excelente! No hay medicamentos con existencia crítica (≤ 5 días).")
                else:
                    for a in alertas:
                        pnom, comp, mnom, ext, dd, dr = a
                        color = "red" if dr <= 2 else "orange"
                        st.markdown(f"""
                        <div style='border: 2px solid {color}; padding: 10px; border-radius: 8px; margin-bottom: 10px;'>
                            <h4 style='color: {color}; margin: 0;'>⚠️ {pnom} - {comp} ({mnom})</h4>
                            <p style='margin: 5px 0 0 0;'>Existencia: <b>{ext}</b> | Dosis Diaria: <b>{dd}</b> | Días Restantes: <b style='color: {color};'>{dr:.1f} días</b></p>
                        </div>
                        """, unsafe_allow_html=True)

        with tab_rep:
            st.subheader("📄 Reporte de Indicaciones Médicas Ordenado Alfabéticamente")
            pdf_ind = generar_pdf_indicaciones()
            with open(pdf_ind, "rb") as f_ind:
                st.download_button(
                    label="🖨️ Descargar Listado de Indicaciones Médicas en PDF",
                    data=f_ind,
                    file_name="Indicaciones_Medicas_Sawabona.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            st.divider()
            rows_all = obtener_todas_asignaciones()
            if rows_all:
                df_rep = [{"Paciente": r[1], "Medicamento": f"{r[2]} ({r[3]})", "Presentación": r[4], "Mañana": r[5], "Tarde": r[6], "Noche": r[7], "Existencia": r[8], "Indicaciones": r[9]} for r in rows_all]
                st.dataframe(df_rep, use_container_width=True)

    # ==========================================
    # 9. 📁 REPOSITORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos Institucionales")
        st.caption("Almacenamiento 100% institucional con carpetas por defecto, subcarpetas y gestión de archivos")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, nombre, padre_id FROM repositorio_carpetas ORDER BY nombre ASC")
        carpetas = c.fetchall()
        conn.close()
        
        tab_explora, tab_admin_c = st.tabs(["📂 Explorador de Archivos", "⚙️ Administrar Carpetas"])
        
        with tab_explora:
            c_dict = {c[1]: c[0] for c in carpetas}
            sel_carp_nom = st.selectbox("Seleccione la carpeta de trabajo:", list(c_dict.keys()))
            carp_id = c_dict[sel_carp_nom]
            
            st.divider()
            st.write(f"##### ⬆️ Subir Archivo a '{sel_carp_nom}'")
            up_file = st.file_uploader("Seleccione el archivo a guardar en la nube:", key=f"up_repo_{carp_id}")
            if up_file is not None:
                if st.button("💾 Guardar Archivo en Repositorio"):
                    b_bytes = up_file.read()
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO repositorio_archivos (carpeta_id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (carp_id, up_file.name, up_file.type, up_file.size, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], b_bytes))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ ¡Archivo '{up_file.name}' guardado correctamente!")
                    st.rerun()

            st.divider()
            st.write(f"##### 📄 Archivos Guardados en '{sel_carp_nom}'")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido FROM repositorio_archivos WHERE carpeta_id = ?", (carp_id,))
            archivos = c.fetchall()
            conn.close()
            
            if not archivos:
                st.info("Esta carpeta no contiene archivos guardados.")
            else:
                for a in archivos:
                    a_id, a_nom, a_mime, a_tam, a_fec, a_usu, a_blob = a
                    col_a1, col_a2, col_a3 = st.columns([4, 2, 2])
                    col_a1.write(f"📄 **{a_nom}** ({a_tam/1024:.1f} KB)"); col_a1.write(f"*Subido por {a_usu} el {a_fec}*")
                    col_a2.download_button("⬇️ Descargar", data=a_blob, file_name=a_nom, mime=a_mime, key=f"dl_repo_{a_id}")
                    if col_a3.button("🗑️ Eliminar", key=f"del_repo_{a_id}"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("DELETE FROM repositorio_archivos WHERE id = ?", (a_id,))
                        conn.commit()
                        conn.close()
                        st.warning("Archivo eliminado")
                        st.rerun()

        with tab_admin_c:
            st.subheader("Crear o Renombrar Carpetas / Subcarpetas")
            c1, c2 = st.columns(2)
            with c1:
                st.write("##### ➕ Crear Nueva Carpeta o Subcarpeta")
                nom_c_new = st.text_input("Nombre de la Carpeta")
                c_padre_opts = {"Raíz (Carpeta Principal)": 0}
                for c_item in carpetas:
                    c_padre_opts[c_item[1]] = c_item[0]
                sel_padre = st.selectbox("Carpeta Padre (Ubicación):", list(c_padre_opts.keys()))
                if st.button("➕ Crear Carpeta"):
                    if nom_c_new.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, ?)", (nom_c_new.strip(), c_padre_opts[sel_padre]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Carpeta creada.")
                        st.rerun()
                        
            with c2:
                st.write("##### 🗑️ Eliminar Carpeta")
                c_del_opts = {c_item[1]: c_item[0] for c_item in carpetas}
                sel_cdel = st.selectbox("Seleccione carpeta a eliminar:", ["-- Seleccionar --"] + list(c_del_opts.keys()))
                if sel_cdel != "-- Seleccionar --":
                    cid_del = c_del_opts[sel_cdel]
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("SELECT COUNT(*) FROM repositorio_archivos WHERE carpeta_id = ?", (cid_del,))
                    cnt_arch = c.fetchone()[0]
                    conn.close()
                    
                    if cnt_arch > 0:
                        st.error(f"⚠️ **ATENCIÓN**: La carpeta '{sel_cdel}' contiene **{cnt_arch} archivo(s)**.")
                        conf_check = st.checkbox("Confirmo que deseo eliminar la carpeta y TODO su contenido")
                        if st.button("🗑️ Confirmar Borrado de Carpeta y Archivos", disabled=not conf_check, type="primary"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("DELETE FROM repositorio_archivos WHERE carpeta_id = ?", (cid_del,))
                            c.execute("DELETE FROM repositorio_carpetas WHERE id = ?", (cid_del,))
                            conn.commit()
                            conn.close()
                            st.success("Carpeta borrada.")
                            st.rerun()
                    else:
                        if st.button("🗑️ Eliminar Carpeta Vacía"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("DELETE FROM repositorio_carpetas WHERE id = ?", (cid_del,))
                            conn.commit()
                            conn.close()
                            st.success("Carpeta eliminada.")
                            st.rerun()

    # ==========================================
    # 10. 🔍 BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Listar Pacientes")
        st.caption("Buscador general de expedientes e historial clínico")
        
        q_search = st.text_input("🔎 Buscar por Nombre, Folio o Expediente:", placeholder="Escriba para filtrar...").strip().lower()
        
        p_all = listar_pacientes_completos(solo_activos=False)
        if q_search:
            p_all = [p for p in p_all if q_search in p[0].lower() or (p[1] and q_search in p[1].lower()) or q_search in p[2].lower()]
            
        st.subheader(f"Resultados de Búsqueda ({len(p_all)})")
        for p in p_all:
            pid, exp, nom, sex, fnac, fing, etp, fetp, est = p
            label_est = "🟢 ACTIVO" if est == 'A' else "🔒 INACTIVO / BAJA"
            with st.expander(f"👤 **{nom}** | Folio: **{pid}** | Expediente: **{exp or 'S/N'}** | {label_est}"):
                c1, c2 = st.columns(2)
                c1.write(f"**Sexo:** {sex}"); c1.write(f"**Fecha Nacimiento:** {fnac}"); c1.write(f"**Fecha Ingreso:** {fing}")
                c2.write(f"**Etapa Actual:** {etp}"); c2.write(f"**Inicio Etapa:** {fetp}")

    # ==========================================
    # 11. ⚙️ CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración de Seguridad y Usuarios")
        
        t_pass, t_users = st.tabs(["🔒 Cambiar Contraseña", "👥 Usuarios del Sistema"])
        
        with t_pass:
            with st.form("form_change_pass"):
                st.subheader("Cambiar Contraseña Personal")
                p_act = st.text_input("Contraseña Actual", type="password")
                p_new = st.text_input("Nueva Contraseña", type="password")
                p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_pass = st.form_submit_button("💾 Actualizar Contraseña")
                
                if btn_pass:
                    if p_new != p_cnf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        val = verificar_login(st.session_state["username"], p_act)
                        if val:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(p_new), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada correctamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

        with t_users:
            st.subheader("Gestión de Cuentas de Personal")
            with st.form("form_add_user"):
                u_new = st.text_input("Nombre de Usuario (Login)")
                u_nom = st.text_input("Nombre Completo del Colaborador")
                u_pas = st.text_input("Contraseña Inicial", type="password")
                btn_u = st.form_submit_button("➕ Crear Cuenta de Usuario")
                
                if btn_u:
                    if u_new and u_pas:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)",
                                      (u_new.strip(), hash_pass(u_pas), u_nom.strip()))
                            conn.commit()
                            st.success("✅ Cuenta de usuario creada.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                        conn.close()

    # ==========================================
    # 12. 📦 RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Copia de seguridad y recuperación de expedientes de residentes")
        
        tab_bak, tab_rest = st.tabs(["⬇️ Copia de Seguridad", "🔄 Restaurar Base de Datos"])
        
        with tab_bak:
            st.subheader("Descargar Copia de Seguridad Actual")
            st.info("Descargue el archivo de la base de datos completa (`sistema_pacientes.db`) para tener un respaldo seguro.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    st.download_button(
                        label="📦 Descargar Base de Datos Completa (.db)",
                        data=f_db,
                        file_name=f"Respaldo_Sawabona_{date.today().strftime('%Y-%m-%d')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )

        with tab_rest:
            st.subheader("Restaurar Base de Datos desde Archivo de Respaldo")
            st.warning("⚠️ **ATENCIÓN**: La restauración reemplazará la base de datos actual con la información contenida en el archivo subido.")
            
            if "msg_restore_success" in st.session_state:
                st.balloons()
                st.success(st.session_state["msg_restore_success"])
                del st.session_state["msg_restore_success"]

            file_upload = st.file_uploader("Seleccione el archivo de respaldo (.db, .sqlite)", type=["db", "sqlite", "sqlite3"], key="uploader_restore_master")
            
            if file_upload is not None:
                st.info(f"📄 Archivo preparado: **{file_upload.name}** ({file_upload.size / 1024:.1f} KB)")
                
                if st.button("🔄 Confirmar y Restaurar Base de Datos Ahora", type="primary", use_container_width=True):
                    try:
                        # 1. Guardar bytes físicamente en el disco
                        with open(DB_FILE, "wb") as f_out:
                            f_out.write(file_upload.getbuffer())
                            
                        # 2. Correr inicialización y migraciones preventivas en la nueva DB
                        init_db()
                        
                        # 3. Inspeccionar conteos
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        
                        cnt_p = 0
                        try:
                            c.execute("SELECT COUNT(*) FROM pacientes_registro")
                            cnt_p = c.fetchone()[0]
                        except:
                            try:
                                c.execute("SELECT COUNT(*) FROM pacientes")
                                cnt_p = c.fetchone()[0]
                            except:
                                cnt_p = 0
                                
                        cnt_e = 0
                        try:
                            c.execute("SELECT COUNT(*) FROM entrevistas")
                            cnt_e = c.fetchone()[0]
                        except:
                            cnt_e = 0
                            
                        conn.close()
                        
                        st.session_state["msg_restore_success"] = f"🎉 ¡Base de datos restaurada con éxito desde '{file_upload.name}'! Se recuperaron {cnt_p} pacientes y {cnt_e} entrevistas iniciales."
                        st.rerun()
                        
                    except Exception as err:
                        st.error(f"❌ Error al restaurar la base de datos: {str(err)}")

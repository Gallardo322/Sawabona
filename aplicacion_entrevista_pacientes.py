import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Control Clínico - Sawabona",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- INICIALIZACIÓN DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios del sistema (login)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            bloqueado INTEGER DEFAULT 0
        )
    """)
    
    # 2. Pacientes / Registro Basal
    c.execute("""
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre_completo TEXT NOT NULL,
            nombre_search TEXT NOT NULL,
            apellido_paterno TEXT,
            apellido_materno TEXT,
            nombres TEXT,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            etapa_actual TEXT DEFAULT 'Acogida',
            fecha_inicio_etapa TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    """)
    
    # Check columns in pacientes_registro
    c.execute("PRAGMA table_info(pacientes_registro)")
    cols = [col[1] for col in c.fetchall()]
    if "expediente" not in cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN expediente TEXT")
    if "etapa_actual" not in cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN etapa_actual TEXT DEFAULT 'Acogida'")
    if "fecha_inicio_etapa" not in cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN fecha_inicio_etapa TEXT")
    if "estatus" not in cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN estatus TEXT DEFAULT 'A'")
        
    # 3. Ficha de Ingreso
    c.execute("""
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 4. Entrevistas Iniciales
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 5. Consejerías Individuales
    c.execute("""
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
    """)
    
    # 6. Historial de Etapas
    c.execute("""
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            fecha_inicio TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    """)
    
    # 7. Grupos Terapéuticos
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    """)
    
    # 8. Catálogo de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    """)
    
    # 9. Asignaciones de Medicamentos por Paciente
    c.execute("""
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
    """)
    
    # 10. Entregas de Medicamentos por Turno
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            cantidad_entregada REAL DEFAULT 0,
            usuario TEXT NOT NULL
        )
    """)
    
    # 11. Repositorio de Documentos - Carpetas
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT NOT NULL,
            carpeta_padre_id INTEGER DEFAULT NULL,
            fecha_creacion TEXT,
            usuario TEXT
        )
    """)
    
    # Carpetas por defecto en Repositorio
    c.execute("SELECT count(*) FROM repositorio_carpetas")
    if c.fetchone()[0] == 0:
        carpetas_default = ["Formatos", "Documentos", "Eventos", "Comprobantes", "Terapéutico"]
        f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for f_nom in carpetas_default:
            c.execute("INSERT INTO repositorio_carpetas (nombre_carpeta, carpeta_padre_id, fecha_creacion, usuario) VALUES (?, NULL, ?, 'sistema')",
                      (f_nom, f_actual))
                      
    # 12. Repositorio de Documentos - Archivos
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT,
            usuario TEXT,
            contenido BLOB NOT NULL,
            FOREIGN KEY (carpeta_id) REFERENCES repositorio_carpetas(id)
        )
    """)
    
    # Usuario Admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
                  
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

# --- FUNCIONES DE PACIENTES ---
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

def generar_siguiente_expediente():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT expediente FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        exp = r[0]
        if exp and exp.startswith("EXP-"):
            try:
                num = int(exp.split("-")[1])
                if num > max_num:
                    max_num = num
            except:
                pass
    return f"EXP-{(max_num + 1):03d}"

def check_duplicate_patient(nombre_comp, exp, current_pid=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, expediente FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    
    n_search = nombre_comp.strip().lower()
    exp_search = exp.strip().lower() if exp else ""
    
    for r in rows:
        pid, r_nom, r_exp = r
        if current_pid and pid == current_pid:
            continue
        if r_nom.strip().lower() == n_search:
            return f"Ya existe un residente registrado con el mismo nombre completo (Folio: {pid})."
        if exp_search and r_exp and r_exp.strip().lower() == exp_search:
            return f"Ya existe un residente con el número de expediente '{exp}' (Folio: {pid})."
    return None

def guardar_paciente_registro(paciente_id, expediente, nombres, ap_paterno, ap_materno, fecha_ingreso, fecha_nacimiento, sexo, etapa_inicial, fecha_inicio_etapa, estatus, usuario):
    init_db()
    nombre_comp = f"{nombres.strip()} {ap_paterno.strip()} {ap_materno.strip()}".strip()
    nombre_search = nombre_comp.lower()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute("""
            UPDATE pacientes_registro
            SET expediente = ?, nombre_completo = ?, nombre_search = ?, apellido_paterno = ?, apellido_materno = ?, nombres = ?,
                fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        """, (expediente, nombre_comp, nombre_search, ap_paterno.strip(), ap_materno.strip(), nombres.strip(),
              str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute("""
            INSERT INTO pacientes_registro 
            (paciente_id, expediente, nombre_completo, nombre_search, apellido_paterno, apellido_materno, nombres,
             fecha_ingreso, fecha_nacimiento, sexo, etapa_actual, fecha_inicio_etapa, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, expediente, nombre_comp, nombre_search, ap_paterno.strip(), ap_materno.strip(), nombres.strip(),
              str(fecha_ingreso), str(fecha_nacimiento), sexo, etapa_inicial, str(fecha_inicio_etapa), estatus, fecha_actual, fecha_actual, usuario))
              
        c.execute("""
            INSERT INTO historial_etapas (paciente_id, etapa, fecha_inicio, observaciones, usuario)
            VALUES (?, ?, ?, 'Etapa inicial de ingreso', ?)
        """, (paciente_id, etapa_inicial, str(fecha_inicio_etapa), usuario))
        
    conn.commit()
    conn.close()

def listar_pacientes_registrados(solo_activos=False):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute("SELECT paciente_id, expediente, nombre_completo, sexo, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus FROM pacientes_registro WHERE estatus = 'A' ORDER BY nombre_completo ASC")
    else:
        c.execute("SELECT paciente_id, expediente, nombre_completo, sexo, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus FROM pacientes_registro ORDER BY nombre_completo ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_registro(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, etapa_actual, fecha_inicio_etapa, estatus FROM pacientes_registro WHERE paciente_id = ?", (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def cambiar_etapa_paciente(paciente_id, nueva_etapa, fecha_inicio, obs, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE pacientes_registro SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?", (nueva_etapa, str(fecha_inicio), paciente_id))
    c.execute("INSERT INTO historial_etapas (paciente_id, etapa, fecha_inicio, observaciones, usuario) VALUES (?, ?, ?, ?, ?)",
              (paciente_id, nueva_etapa, str(fecha_inicio), obs, usuario))
    conn.commit()
    conn.close()

# --- FUNCIONES DE MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)",
              (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?",
              (compuesto.strip(), nombre.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?", (med_id,))
    asig_count = c.fetchone()[0]
    if asig_count > 0:
        conn.close()
        return False, "No se puede eliminar el medicamento porque está asignado a pacientes activos."
    c.execute("DELETE FROM catalogo_medicamentos WHERE id = ?", (med_id,))
    conn.commit()
    conn.close()
    return True, "Medicamento eliminado exitosamente."

def obtener_asignaciones_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.medicamento_id, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE a.paciente_id = ?
        ORDER BY m.nombre_medicamento ASC
    """, (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_asignacion_medicamento(paciente_id, med_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?", (paciente_id, med_id))
    row = c.fetchone()
    if row:
        c.execute("""
            UPDATE asignaciones_medicamentos
            SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
            WHERE id = ?
        """, (manana, tarde, noche, existencia, obs, row[0]))
    else:
        c.execute("""
            INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, med_id, manana, tarde, noche, existencia, obs))
    conn.commit()
    conn.close()

def actualizar_asignacion_medicamento(asig_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE asignaciones_medicamentos
        SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
        WHERE id = ?
    """, (manana, tarde, noche, existencia, obs, asig_id))
    conn.commit()
    conn.close()

def eliminar_asignacion_medicamento(asig_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM asignaciones_medicamentos WHERE id = ?", (asig_id,))
    conn.commit()
    conn.close()

def registrar_entrega_medicamento(paciente_id, med_id, fecha, turno, cantidad, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario) VALUES (?, ?, ?, ?, ?, ?)",
              (paciente_id, med_id, str(fecha), turno, cantidad, usuario))
    c.execute("SELECT existencia FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?", (paciente_id, med_id))
    row = c.fetchone()
    if row:
        nueva_ex = max(0.0, float(row[0]) - float(cantidad))
        c.execute("UPDATE asignaciones_medicamentos SET existencia = ? WHERE paciente_id = ? AND medicamento_id = ?",
                  (nueva_ex, paciente_id, med_id))
    conn.commit()
    conn.close()

def obtener_todas_asignaciones():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT p.nombre_completo, p.paciente_id, p.expediente,
               m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN pacientes_registro p ON a.paciente_id = p.paciente_id
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE p.estatus = 'A'
        ORDER BY p.nombre_completo ASC, m.nombre_medicamento ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def obtener_carpetas_repositorio():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nombre_carpeta, carpeta_padre_id, fecha_creacion FROM repositorio_carpetas ORDER BY nombre_carpeta ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def crear_carpeta_repositorio(nombre, padre_id, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO repositorio_carpetas (nombre_carpeta, carpeta_padre_id, fecha_creacion, usuario) VALUES (?, ?, ?, ?)",
              (nombre.strip(), padre_id, f_actual, usuario))
    conn.commit()
    conn.close()

def renombrar_carpeta_repositorio(carpeta_id, nuevo_nombre):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE id = ?", (nuevo_nombre.strip(), carpeta_id))
    conn.commit()
    conn.close()

def contar_contenido_carpeta(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM repositorio_archivos WHERE carpeta_id = ?", (carpeta_id,))
    num_archivos = c.fetchone()[0]
    c.execute("SELECT count(*) FROM repositorio_carpetas WHERE carpeta_padre_id = ?", (carpeta_id,))
    num_subcarpetas = c.fetchone()[0]
    conn.close()
    return num_archivos, num_subcarpetas

def eliminar_carpeta_repositorio(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM repositorio_carpetas WHERE carpeta_padre_id = ?", (carpeta_id,))
    sub_ids = [r[0] for r in c.fetchall()]
    for s_id in sub_ids:
        eliminar_carpeta_repositorio(s_id)
    c.execute("DELETE FROM repositorio_archivos WHERE carpeta_id = ?", (carpeta_id,))
    c.execute("DELETE FROM repositorio_carpetas WHERE id = ?", (carpeta_id,))
    conn.commit()
    conn.close()

def guardar_archivo_repositorio(carpeta_id, nombre_archivo, tipo_mime, tamano, usuario, contenido_bytes):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO repositorio_archivos (carpeta_id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (carpeta_id, nombre_archivo, tipo_mime, tamano, f_actual, usuario, contenido_bytes))
    conn.commit()
    conn.close()

def listar_archivos_carpeta(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario FROM repositorio_archivos WHERE carpeta_id = ? ORDER BY nombre_archivo ASC", (carpeta_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_archivo_repositorio(archivo_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nombre_archivo, tipo_mime, contenido FROM repositorio_archivos WHERE id = ?", (archivo_id,))
    row = c.fetchone()
    conn.close()
    return row

def eliminar_archivo_repositorio(archivo_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM repositorio_archivos WHERE id = ?", (archivo_id,))
    conn.commit()
    conn.close()

# --- GENERACIÓN DE PDFS ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(self.epw, 7, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.cell(self.epw, 5, "Sistema Clinico de Atencion y Control de Pacientes", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

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

def generar_pdf_indicaciones(asignaciones):
    pdf = PDFReport()
    pdf.add_page(orientation="L")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTADO DE INDICACIONES Y DOSIS DE MEDICAMENTOS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    col_w = [50, 45, 35, 30, 25, 25, 60]
    headers = ["Paciente", "Medicamento", "Presentacion", "Esquema (M/T/N)", "Existencia", "Dias Rest.", "Observaciones"]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for row in asignaciones:
        p_nom, p_id, exp, comp, m_nom, pres, d_m, d_t, d_n, ex, obs = row
        consumo_diario = float(d_m) + float(d_t) + float(d_n)
        dias_rest = round(float(ex) / consumo_diario, 1) if consumo_diario > 0 else "N/A"
        esquema = f"{d_m} / {d_t} / {d_n}"
        
        pdf.cell(col_w[0], 6, limpiar_texto(p_nom[:28]), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(m_nom[:24]), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(pres[:18]), border=1)
        pdf.cell(col_w[3], 6, esquema, border=1, align="C")
        pdf.cell(col_w[4], 6, str(ex), border=1, align="C")
        pdf.cell(col_w[5], 6, str(dias_rest), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto((obs or "")[:35]), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = "Indicaciones_Medicamentos.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIAR APLICACIÓN ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Control Clínico</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sawabona Shikoba A.C. - Ingrese sus credenciales</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submit:
                usuario_valido = verificar_login(user_input, pass_input)
                if usuario_valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usuario_valido[0]
                    st.session_state["nombre_completo"] = usuario_valido[1]
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- MENÚ DE NAVEGACIÓN LATERAL (12 MÓDULOS) ---
    st.sidebar.title("📋 Control Clínico")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu_opciones = [
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
    
    menu = st.sidebar.radio("Navegación Principal", menu_opciones)
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- MÓDULO 1: TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General de Atenciones")
        st.caption("Resumen ejecutivo de residentes, etapas y atenciones médicas")
        
        pacientes_activos = listar_pacientes_registrados(solo_activos=True)
        pacientes_todos = listar_pacientes_registrados(solo_activos=False)
        
        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        c_m1.metric("Residentes Activos", len(pacientes_activos))
        c_m2.metric("Total Historico", len(pacientes_todos))
        c_m3.metric("Residentes Inactivos", len(pacientes_todos) - len(pacientes_activos))
        c_m4.metric("Medicamentos Asignados", len(obtener_todas_asignaciones()))
        
        st.divider()
        st.subheader("📊 Distribución de Residentes por Etapa de Tratamiento")
        
        etapas_lista = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        etapas_count = {e: 0 for e in etapas_lista}
        
        for p in pacientes_activos:
            et = p[5] or "Acogida"
            if et in etapas_count:
                etapas_count[et] += 1
            else:
                etapas_count["Acogida"] += 1
                
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        ec1.metric("1. Acogida", etapas_count["Acogida"])
        ec2.metric("2. Identificación", etapas_count["Identificación"])
        ec3.metric("3. Elaboración", etapas_count["Elaboración"])
        ec4.metric("4. Consolidación", etapas_count["Consolidación"])
        ec5.metric("5. Servicio Social", etapas_count["Servicio Social"])

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Residentes")
        st.caption("Padrón general y alta de expedientes de residentes")
        
        if "reset_reg_form" not in st.session_state:
            st.session_state["reset_reg_form"] = False
        if "show_success_confirm" not in st.session_state:
            st.session_state["show_success_confirm"] = False
        if "last_registered_name" not in st.session_state:
            st.session_state["last_registered_name"] = ""
        if "last_registered_folio" not in st.session_state:
            st.session_state["last_registered_folio"] = ""

        if st.session_state["show_success_confirm"]:
            st.success(f"🎉 ¡Residente **{st.session_state['last_registered_name']}** registrado exitosamente con Folio **{st.session_state['last_registered_folio']}**!")
            st.markdown("### ¿Desea ingresar a otro paciente?")
            c_conf1, c_conf2 = st.columns(2)
            with c_conf1:
                if st.button("🟢 Sí, registrar otro paciente", use_container_width=True, type="primary"):
                    st.session_state["reset_reg_form"] = True
                    st.session_state["show_success_confirm"] = False
                    st.rerun()
            with c_conf2:
                if st.button("🔴 No, mantener datos en pantalla", use_container_width=True):
                    st.session_state["show_success_confirm"] = False
                    st.rerun()

        if st.session_state["reset_reg_form"]:
            val_folio = generar_siguiente_folio()
            val_exp = generar_siguiente_expediente()
            val_nom = ""
            val_app = ""
            val_apm = ""
            val_sexo = "Masculino"
            val_f_nac = date(1995, 1, 1)
            val_f_ing = date.today()
            val_etapa = "Acogida"
            val_f_etapa = date.today()
            st.session_state["reset_reg_form"] = False
        else:
            val_folio = generar_siguiente_folio()
            val_exp = generar_siguiente_expediente()
            val_nom = st.session_state.get("reg_nom", "")
            val_app = st.session_state.get("reg_app", "")
            val_apm = st.session_state.get("reg_apm", "")
            val_sexo = st.session_state.get("reg_sexo", "Masculino")
            val_f_nac = st.session_state.get("reg_f_nac", date(1995, 1, 1))
            val_f_ing = st.session_state.get("reg_f_ing", date.today())
            val_etapa = st.session_state.get("reg_etapa", "Acogida")
            val_f_etapa = st.session_state.get("reg_f_etapa", date.today())

        st.subheader("📋 Formulario de Registro Basal (Secuencia Tabulación 1-10)")
        
        with st.form("form_registro_paciente"):
            rf1_1, rf1_2 = st.columns(2)
            with rf1_1:
                f_pid = st.text_input("1. Folio Único / ID Paciente *", value=val_folio, help="Consecutivo automático PAC-XXX")
            with rf1_2:
                f_exp = st.text_input("2. Número de Expediente *", value=val_exp, help="Número de expediente interno EXP-XXX")
                
            rf2_1, rf2_2, rf2_3 = st.columns(3)
            with rf2_1:
                f_nom = st.text_input("3. Nombre(s) *", value=val_nom)
            with rf2_2:
                f_app = st.text_input("4. Apellido Paterno *", value=val_app)
            with rf2_3:
                f_apm = st.text_input("5. Apellido Materno *", value=val_apm)
                
            rf3_1, rf3_2, rf3_3 = st.columns(3)
            with rf3_1:
                f_sexo = st.selectbox("6. Sexo *", ["Masculino", "Femenino"], index=0 if val_sexo=="Masculino" else 1)
            with rf3_2:
                f_fnac = st.date_input("7. Fecha de Nacimiento *", value=val_f_nac, min_value=date(1930, 1, 1))
            with rf3_3:
                f_fing = st.date_input("8. Fecha de Ingreso Institucional *", value=val_f_ing)
                
            rf4_1, rf4_2 = st.columns(2)
            with rf4_1:
                f_etapa = st.selectbox("9. Etapa Inicial *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=0)
            with rf4_2:
                f_fetapa = st.date_input("10. Fecha Inicio Etapa Actual *", value=val_f_etapa)
                
            btn_guardar_p = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
            
            if btn_guardar_p:
                if not f_pid.strip() or not f_nom.strip() or not f_app.strip():
                    st.error("⚠️ Los campos Folio, Nombre y Apellido Paterno son obligatorios.")
                else:
                    dup_err = check_duplicate_patient(f"{f_nom} {f_app} {f_apm}", f_exp, current_pid=f_pid)
                    if dup_err:
                        st.error(f"⚠️ {dup_err}")
                    else:
                        guardar_paciente_registro(f_pid.strip(), f_exp.strip(), f_nom.strip(), f_app.strip(), f_apm.strip(),
                                                  f_fing, f_fnac, f_sexo, f_etapa, f_fetapa, "A", st.session_state["username"])
                        st.balloons()
                        st.session_state["last_registered_name"] = f"{f_nom.strip()} {f_app.strip()}"
                        st.session_state["last_registered_folio"] = f_pid.strip()
                        st.session_state["show_success_confirm"] = True
                        st.rerun()

        st.divider()
        st.subheader("👥 Padrón General de Residentes Registrados")
        todos_p = listar_pacientes_registrados(solo_activos=False)
        if todos_p:
            data_p = []
            for tp in todos_p:
                data_p.append({
                    "Folio": tp[0],
                    "Expediente": tp[1],
                    "Nombre Completo": tp[2],
                    "Sexo": tp[3],
                    "Fecha Ingreso": tp[4],
                    "Etapa Actual": tp[5],
                    "Estatus": "🟢 Activo" if tp[7]=="A" else "🔴 Inactivo"
                })
            st.dataframe(data_p, use_container_width=True)

    # --- MÓDULO 3: FICHA DE INGRESO ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión")
        st.caption("Captura de datos de admisión y contrato institucional Sawabona")
        p_activos = listar_pacientes_registrados(solo_activos=True)
        if not p_activos:
            st.warning("No hay pacientes activos para generar Ficha de Ingreso.")
        else:
            p_dict = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            p_sel = st.selectbox("Seleccionar Residente:", list(p_dict.keys()))
            pid = p_dict[p_sel]
            st.info(f"📌 Residente seleccionado: **{p_sel}**")

    # --- MÓDULO 4: ENTREVISTA INICIAL ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Evaluación clínica digital de consumo y disposición al cambio")
        p_activos = listar_pacientes_registrados(solo_activos=True)
        if not p_activos:
            st.warning("No hay pacientes activos para registrar entrevista.")
        else:
            p_dict = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            p_sel = st.selectbox("Seleccionar Residente:", list(p_dict.keys()), key="ent_sel")
            pid = p_dict[p_sel]
            st.info(f"📌 Residente seleccionado: **{p_sel}**")

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        st.caption("Bitácora de sesiones y seguimiento individual")
        p_activos = listar_pacientes_registrados(solo_activos=True)
        if not p_activos:
            st.warning("No hay pacientes activos.")
        else:
            p_dict = {f"{p[2]} ({p[0]})": p[0] for p in p_activos}
            p_sel = st.selectbox("Seleccionar Residente:", list(p_dict.keys()), key="cons_sel")
            pid = p_dict[p_sel]
            st.info(f"📌 Residente seleccionado: **{p_sel}**")

    # --- MÓDULO 6: GESTIÓN DE ETAPAS ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso Terapéutico")
        st.caption("Seguimiento y promoción por las 5 etapas del programa")
        
        p_activos = listar_pacientes_registrados(solo_activos=True)
        if p_activos:
            st.subheader("Residentes y Promoción de Etapas")
            for p in p_activos:
                f_start = p[6] or str(date.today())
                try:
                    d_init = datetime.strptime(f_start, "%Y-%m-%d").date()
                    dias_in = (date.today() - d_init).days
                except:
                    dias_in = 0
                    
                with st.expander(f"👤 **{p[2]}** (Folio: {p[0]}) ➔ Etapa Actual: **{p[5]}** ({dias_in} días en esta etapa)"):
                    if dias_in > 90:
                        st.warning(f"🚨 **Alerta de Rezago**: El residente lleva {dias_in} días en la etapa '{p[5]}'. Se sugiere evaluación de promoción.")
                    
                    with st.form(f"form_etapa_{p[0]}"):
                        n_etapa = st.selectbox("Nueva Etapa:", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"].index(p[5] or "Acogida"))
                        f_netapa = st.date_input("Fecha Inicio Nueva Etapa", value=date.today())
                        obs_etapa = st.text_input("Observaciones de Promoción")
                        btn_petapa = st.form_submit_button("💾 Actualizar Etapa")
                        if btn_petapa:
                            cambiar_etapa_paciente(p[0], n_etapa, f_netapa, obs_etapa, st.session_state["username"])
                            st.success(f"✅ Promovido a {n_etapa}")
                            st.rerun()

    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Grupos Terapéuticos y Talleres")
        st.caption("Registro de sesiones grupales y lista de asistencia")
        
        with st.form("form_grupo_ter"):
            fg_f = st.date_input("Fecha de la Sesión", value=date.today())
            fg_tipo = st.selectbox("Tipo de Grupo", ["Aquí y Ahora", "Prevención de Recaídas", "Estudio de Pasos", "Espiritualidad", "Gestión Emocional", "Taller Temático"])
            fg_tema = st.text_input("Tema de la Sesión *")
            
            p_activos = listar_pacientes_registrados(solo_activos=True)
            asist_sel = []
            if p_activos:
                st.write("Seleccionar Residentes Asistentes:")
                for p in p_activos:
                    if st.checkbox(f"{p[2]} ({p[0]})", key=f"gt_{p[0]}"):
                        asist_sel.append(p[0])
                        
            fg_obs = st.text_area("Observaciones de la Sesión")
            btn_ggrupo = st.form_submit_button("💾 Guardar Sesión Grupal")
            if btn_ggrupo:
                if not fg_tema.strip():
                    st.error("El tema es obligatorio.")
                else:
                    st.success(f"✅ Grupo '{fg_tipo}' registrado con {len(asist_sel)} asistentes.")

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control y Administración de Medicamentos")
        st.caption("Catálogo general, asignación e inventario por paciente, surtido por turno y alarmas")
        
        tab_cat, tab_asig, tab_surt, tab_alarm, tab_rep = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario por Paciente",
            "🕒 Surtido por Turno",
            "🚨 Alarmas de Reabastecimiento",
            "📄 Reporte de Indicaciones"
        ])
        
        with tab_cat:
            st.subheader("Catálogo General de Medicamentos")
            t_cat1, t_cat2, t_cat3 = st.tabs(["➕ Agregar Medicamento", "✏️ Modificar Medicamento", "🗑️ Eliminar Medicamento"])
            
            with t_cat1:
                with st.form("form_add_cat"):
                    c_comp = st.text_input("Nombre del Compuesto / Sustancia Activa *", placeholder="Ej. Paracetamol, Sertralina")
                    c_nom = st.text_input("Nombre Comercial / Medicamento *", placeholder="Ej. Tylenol, Zoloft")
                    c_pres = st.text_input("Presentación *", placeholder="Ej. Tabletas 500mg, Cápsulas 20mg")
                    btn_cadd = st.form_submit_button("💾 Guardar en Catálogo")
                    if btn_cadd:
                        if not c_comp or not c_nom or not c_pres:
                            st.error("⚠️ Todos los campos son obligatorios.")
                        else:
                            guardar_medicamento_catalogo(c_comp, c_nom, c_pres)
                            st.success(f"✅ Medicamento '{c_nom}' guardado en catálogo.")
                            st.rerun()
                            
            with t_cat2:
                cat_actual = obtener_catalogo_medicamentos()
                if not cat_actual:
                    st.info("El catálogo está vacío.")
                else:
                    med_sel_mod = st.selectbox("Seleccione medicamento a modificar:", [f"{m[0]} - {m[2]} ({m[1]})" for m in cat_actual])
                    med_id_mod = int(med_sel_mod.split(" - ")[0])
                    m_data = [m for m in cat_actual if m[0] == med_id_mod][0]
                    
                    with st.form("form_mod_cat"):
                        mc_comp = st.text_input("Compuesto", value=m_data[1])
                        mc_nom = st.text_input("Nombre Comercial", value=m_data[2])
                        mc_pres = st.text_input("Presentación", value=m_data[3])
                        btn_cmod = st.form_submit_button("💾 Actualizar Medicamento")
                        if btn_cmod:
                            actualizar_medicamento_catalogo(med_id_mod, mc_comp, mc_nom, mc_pres)
                            st.success("✅ Medicamento actualizado exitosamente.")
                            st.rerun()

            with t_cat3:
                cat_actual = obtener_catalogo_medicamentos()
                if cat_actual:
                    med_sel_del = st.selectbox("Seleccione medicamento a eliminar:", [f"{m[0]} - {m[2]} ({m[1]})" for m in cat_actual], key="del_cat")
                    med_id_del = int(med_sel_del.split(" - ")[0])
                    if st.button("🗑️ Eliminar de Catálogo", type="primary"):
                        ok_del, msg_del = eliminar_medicamento_catalogo(med_id_del)
                        if ok_del:
                            st.success(f"✅ {msg_del}")
                            st.rerun()
                        else:
                            st.error(f"⚠️ {msg_del}")

        with tab_asig:
            st.subheader("Asignación de Medicamentos e Inventario por Paciente")
            p_activos = listar_pacientes_registrados(solo_activos=True)
            
            if not p_activos:
                st.warning("No hay pacientes activos registrados.")
            else:
                p_dict = {f"{p[2]} ({p[0]} - Exp: {p[1]})": p[0] for p in p_activos}
                p_sel_nom = st.selectbox("Elegir paciente activo:", list(p_dict.keys()))
                pid_asig = p_dict[p_sel_nom]
                
                asig_pac = obtener_asignaciones_paciente(pid_asig)
                
                t_asig1, t_asig2 = st.tabs(["➕ Asignar Medicamento de Catálogo", "✏️ Modificar Dosis / Existencia Nueva"])
                
                with t_asig1:
                    cat_meds = obtener_catalogo_medicamentos()
                    if not cat_meds:
                        st.info("Primero agregue medicamentos al Catálogo General.")
                    else:
                        c_dict = {f"{m[2]} - {m[1]} ({m[3]})": m[0] for m in cat_meds}
                        m_sel_c = st.selectbox("Seleccionar Medicamento de Catálogo:", list(c_dict.keys()))
                        m_id_c = c_dict[m_sel_c]
                        
                        with st.form("form_asig_med"):
                            ca1, ca2, ca3 = st.columns(3)
                            with ca1:
                                d_man = st.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=1.0)
                            with ca2:
                                d_tar = st.number_input("🌤️ Dosis Medio Día / Tarde", min_value=0.0, step=0.5, value=0.0)
                            with ca3:
                                d_noc = st.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=1.0)
                                
                            ex_nueva = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL (Unidades/Pastillas)", min_value=0.0, step=1.0, value=30.0)
                            obs_asig = st.text_input("Observaciones / Indicaciones especiales", placeholder="Ej. Tomar con alimentos")
                            
                            btn_gasig = st.form_submit_button("💾 Guardar Asignación")
                            if btn_gasig:
                                guardar_asignacion_medicamento(pid_asig, m_id_c, d_man, d_tar, d_noc, ex_nueva, obs_asig)
                                st.success("✅ Asignación de medicamento guardada correctamente.")
                                st.rerun()

                with t_asig2:
                    if not asig_pac:
                        st.info("El paciente seleccionado no tiene medicamentos asignados.")
                    else:
                        asig_dict = {f"{a[3]} ({a[4]}) - Dosis: {a[5]}/{a[6]}/{a[7]} - Exist: {a[8]}": a[0] for a in asig_pac}
                        asig_sel_nom = st.selectbox("Seleccionar asignación a modificar:", list(asig_dict.keys()))
                        asig_id_mod = asig_dict[asig_sel_nom]
                        a_data = [a for a in asig_pac if a[0] == asig_id_mod][0]
                        
                        with st.form("form_mod_asig"):
                            ma1, ma2, ma3 = st.columns(3)
                            with ma1:
                                md_man = st.number_input("Dosis Mañana", value=float(a_data[5]), step=0.5)
                            with ma2:
                                md_tar = st.number_input("Dosis Tarde", value=float(a_data[6]), step=0.5)
                            with ma3:
                                md_noc = st.number_input("Dosis Noche", value=float(a_data[7]), step=0.5)
                                
                            mex_nueva = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", value=float(a_data[8]), step=1.0)
                            mobs_asig = st.text_input("Observaciones", value=a_data[9] or "")
                            
                            col_amb1, col_amb2 = st.columns(2)
                            with col_amb1:
                                btn_masig = st.form_submit_button("💾 Actualizar Asignación", use_container_width=True)
                            with col_amb2:
                                btn_retir = st.form_submit_button("🗑️ Retirar Medicamento", use_container_width=True)
                                
                            if btn_masig:
                                actualizar_asignacion_medicamento(asig_id_mod, md_man, md_tar, md_noc, mex_nueva, mobs_asig)
                                st.success("✅ Asignación actualizada correctamente.")
                                st.rerun()
                            if btn_retir:
                                eliminar_asignacion_medicamento(asig_id_mod)
                                st.success("✅ Medicamento retirado del paciente.")
                                st.rerun()

        with tab_surt:
            st.subheader("🕒 Surtido y Entrega de Dosis por Turno")
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                f_surtido = st.date_input("Fecha de Surtido", value=date.today())
            with c_s2:
                turno_surtido = st.selectbox("Turno a Surtir", ["Mañana", "Medio Día / Tarde", "Noche"])
                
            p_activos = listar_pacientes_registrados(solo_activos=True)
            if not p_activos:
                st.info("No hay pacientes activos.")
            else:
                st.markdown(f"#### Residentes con Dosis Programada para Turno: **{turno_surtido}**")
                hay_dosis = False
                
                for p in p_activos:
                    asigs = obtener_asignaciones_paciente(p[0])
                    asigs_turno = []
                    for a in asigs:
                        dosis_t = float(a[5]) if turno_surtido=="Mañana" else (float(a[6]) if turno_surtido=="Medio Día / Tarde" else float(a[7]))
                        if dosis_t > 0:
                            asigs_turno.append((a, dosis_t))
                            
                    if asigs_turno:
                        hay_dosis = True
                        with st.expander(f"👤 **{p[2]}** (Folio: {p[0]} | Exp: {p[1]})", expanded=True):
                            for a_tuple in asigs_turno:
                                a_item, dosis_indicada = a_tuple
                                m_id = a_item[1]
                                m_nom = a_item[3]
                                m_pres = a_item[4]
                                ex_act = float(a_item[8])
                                
                                cs1, cs2, cs3, cs4 = st.columns([3, 1.5, 1.5, 2])
                                cs1.write(f"💊 **{m_nom}** ({m_pres})")
                                cs2.write(f"Dosis: **{dosis_indicada}**")
                                
                                if ex_act <= 0:
                                    cs3.error("🚨 SIN EXISTENCIA (0)")
                                    cant_entregar = 0.0
                                else:
                                    cs3.success(f"Existencia: {ex_act}")
                                    cant_entregar = dosis_indicada
                                    
                                with cs4:
                                    if st.button(f"Surtir {cant_entregar} dosis", key=f"surt_{p[0]}_{m_id}_{turno_surtido}", disabled=(ex_act<=0)):
                                        registrar_entrega_medicamento(p[0], m_id, f_surtido, turno_surtido, cant_entregar, st.session_state["username"])
                                        st.success(f"✅ Surtido {m_nom} a {p[2]}")
                                        st.rerun()

        with tab_alarm:
            st.subheader("🚨 Alarmas de Reabastecimiento (≤ 5 Días de Dosis)")
            todas_asig = obtener_todas_asignaciones()
            
            alarmas_list = []
            for a in todas_asig:
                p_nom, p_id, exp, comp, m_nom, pres, d_m, d_t, d_n, ex, obs = a
                consumo = float(d_m) + float(d_t) + float(d_n)
                if consumo > 0:
                    dias_rest = float(ex) / consumo
                    if dias_rest <= 5.0:
                        alarmas_list.append((p_nom, p_id, m_nom, pres, ex, consumo, round(dias_rest, 1)))
                        
            if not alarmas_list:
                st.success("✅ Todos los pacientes cuentan con existencia suficiente para más de 5 días.")
            else:
                for al in alarmas_list:
                    p_nom, p_id, m_nom, pres, ex, consumo, dias_rest = al
                    if dias_rest <= 2.0:
                        st.error(f"🚨 **{p_nom}** (Folio: {p_id}) | Medicamento: **{m_nom}** ({pres}) ➔ Existencia: **{ex}** unidades | Días restantes: **{dias_rest} días**")
                    else:
                        st.warning(f"⚠️ **{p_nom}** (Folio: {p_id}) | Medicamento: **{m_nom}** ({pres}) ➔ Existencia: **{ex}** unidades | Días restantes: **{dias_rest} días**")

        with tab_rep:
            st.subheader("📄 Listado Completo de Indicaciones Médicas")
            todas_asig = obtener_todas_asignaciones()
            
            if not todas_asig:
                st.info("No hay asignaciones registradas.")
            else:
                rep_data = []
                for a in todas_asig:
                    p_nom, p_id, exp, comp, m_nom, pres, d_m, d_t, d_n, ex, obs = a
                    consumo = float(d_m) + float(d_t) + float(d_n)
                    dias_r = round(float(ex) / consumo, 1) if consumo > 0 else "N/A"
                    rep_data.append({
                        "Paciente": p_nom,
                        "Folio": p_id,
                        "Medicamento": m_nom,
                        "Presentación": pres,
                        "☀️ Mañana": d_m,
                        "🌤️ Tarde": d_t,
                        "🌙 Noche": d_n,
                        "Existencia": ex,
                        "Días Restantes": dias_r,
                        "Observaciones": obs
                    })
                st.dataframe(rep_data, use_container_width=True)
                
                pdf_ind = generar_pdf_indicaciones(todas_asig)
                with open(pdf_ind, "rb") as f_ind:
                    st.download_button(
                        label="🖨️ Descargar Listado de Indicaciones Médicas en PDF",
                        data=f_ind,
                        file_name="Listado_Indicaciones_Medicamentos.pdf",
                        mime="application/pdf"
                    )

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Institucional de Documentos")
        st.caption("Almacenamiento institucional de formatos, documentos, comprobantes y talleres")
        
        c_carpetas = obtener_carpetas_repositorio()
        
        tab_rep1, tab_rep2 = st.tabs(["📂 Explorar y Gestionar Archivos", "⚙️ Crear / Renombrar / Eliminar Carpetas"])
        
        with tab_rep1:
            st.subheader("Explorador de Carpetas Institucionales")
            c_dict = {f"📁 {c[1]}": c[0] for c in c_carpetas}
            c_sel_nom = st.selectbox("Seleccionar carpeta:", list(c_dict.keys()))
            c_id_sel = c_dict[c_sel_nom]
            
            archivos = listar_archivos_carpeta(c_id_sel)
            
            st.markdown("##### ⬆️ Subir Archivo a esta Carpeta")
            with st.form("form_upload_repo"):
                up_file = st.file_uploader("Seleccionar archivo (PDF, Word, Excel, Imágenes)")
                btn_up = st.form_submit_button("⬆️ Subir Archivo al Repositorio")
                if btn_up and up_file:
                    f_bytes = up_file.getvalue()
                    guardar_archivo_repositorio(c_id_sel, up_file.name, up_file.type, up_file.size, st.session_state["username"], f_bytes)
                    st.success(f"✅ Archivo '{up_file.name}' guardado exitosamente.")
                    st.rerun()
                    
            st.divider()
            st.markdown(f"##### 📄 Archivos en {c_sel_nom}")
            if not archivos:
                st.info("Esta carpeta no contiene archivos.")
            else:
                for arch in archivos:
                    a_id, a_nom, a_mime, a_tam, a_fecha, a_user = arch
                    col_ar1, col_ar2, col_ar3 = st.columns([4, 2, 1])
                    col_ar1.write(f"📄 **{a_nom}** ({round(a_tam/1024, 1)} KB) - Subido el {a_fecha}")
                    
                    row_data = obtener_archivo_repositorio(a_id)
                    if row_data:
                        col_ar2.download_button(
                            label="⬇️ Descargar",
                            data=row_data[2],
                            file_name=row_data[0],
                            mime=row_data[1],
                            key=f"down_repo_{a_id}"
                        )
                        
                    if col_ar3.button("🗑️", key=f"del_repo_{a_id}"):
                        eliminar_archivo_repositorio(a_id)
                        st.success("Archivo eliminado.")
                        st.rerun()

        with tab_rep2:
            st.subheader("Gestión de Carpetas")
            t_f1, t_f2, t_f3 = st.tabs(["➕ Crear Carpeta/Subcarpeta", "✏️ Renombrar Carpeta", "🗑️ Eliminar Carpeta"])
            
            with t_f1:
                with st.form("form_crear_carpeta"):
                    nom_f = st.text_input("Nombre de la Carpeta *")
                    padre_opt = ["-- Carpeta Raíz (Principal) --"] + [f"{c[1]} (ID: {c[0]})" for c in c_carpetas]
                    padre_sel = st.selectbox("Carpeta Padre:", padre_opt)
                    p_id_val = None if padre_sel.startswith("--") else int(padre_sel.split("ID: ")[1].replace(")", ""))
                    
                    btn_fadd = st.form_submit_button("➕ Crear Carpeta")
                    if btn_fadd:
                        if not nom_f.strip():
                            st.error("El nombre es obligatorio.")
                        else:
                            crear_carpeta_repositorio(nom_f, p_id_val, st.session_state["username"])
                            st.success("✅ Carpeta creada.")
                            st.rerun()

            with t_f2:
                c_mod_sel = st.selectbox("Seleccionar carpeta a renombrar:", [f"{c[1]} (ID: {c[0]})" for c in c_carpetas])
                c_id_ren = int(c_mod_sel.split("ID: ")[1].replace(")", ""))
                with st.form("form_ren_carpeta"):
                    n_ren = st.text_input("Nuevo Nombre")
                    btn_fren = st.form_submit_button("✏️ Renombrar")
                    if btn_fren and n_ren.strip():
                        renombrar_carpeta_repositorio(c_id_ren, n_ren)
                        st.success("✅ Carpeta renombrada.")
                        st.rerun()

            with t_f3:
                c_del_sel = st.selectbox("Seleccionar carpeta a eliminar:", [f"{c[1]} (ID: {c[0]})" for c in c_carpetas], key="f_del_sel")
                c_id_del = int(c_del_sel.split("ID: ")[1].replace(")", ""))
                
                n_arch, n_sub = contar_contenido_carpeta(c_id_del)
                if n_arch > 0 or n_sub > 0:
                    st.error(f"🚨 **ADVERTENCIA DE SEGURIDAD**: La carpeta contiene {n_arch} archivo(s) y {n_sub} subcarpeta(s).")
                    chk_del = st.checkbox("Confirmo que deseo eliminar permanentemente la carpeta y TODO su contenido.")
                    if st.button("🗑️ Eliminar Carpeta y Contenido", type="primary", disabled=not chk_del):
                        eliminar_carpeta_repositorio(c_id_del)
                        st.success("✅ Carpeta y contenido eliminados.")
                        st.rerun()
                else:
                    if st.button("🗑️ Eliminar Carpeta Vacía", type="primary"):
                        eliminar_carpeta_repositorio(c_id_del)
                        st.success("✅ Carpeta eliminada.")
                        st.rerun()

    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Consultar Residentes")
        st.caption("Búsqueda general por Nombre, Folio (PAC-XXX) o Expediente (EXP-XXX)")
        
        q_search = st.text_input("🔎 Buscar por Nombre, Folio (PAC-XXX) o Expediente (EXP-XXX)", placeholder="Escriba aquí para buscar...")
        p_todos = listar_pacientes_registrados(solo_activos=False)
        
        if q_search.strip():
            q_norm = q_search.strip().lower()
            p_filtrados = [p for p in p_todos if q_norm in p[2].lower() or q_norm in p[0].lower() or (p[1] and q_norm in p[1].lower())]
        else:
            p_filtrados = p_todos
            
        st.write(f"Resultados encontrados: **{len(p_filtrados)}**")
        
        for p in p_filtrados:
            with st.expander(f"👤 **{p[2]}** | Folio: **{p[0]}** | Exp: **{p[1]}** | Etapa: **{p[5]}** | Status: {'🟢 Activo' if p[7]=='A' else '🔴 Inactivo'}"):
                p_data = obtener_paciente_registro(p[0])
                if p_data:
                    st.write(f"**Fecha Ingreso:** {p_data[6]} | **Fecha Nacimiento:** {p_data[7]} | **Sexo:** {p_data[8]}")
                    st.write(f"**Fecha Inicio Etapa Actual ({p_data[9]}):** {p_data[10]}")

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad")
        st.subheader("Cambiar Contraseña de Usuario")
        
        with st.form("form_pass_change"):
            pass_act = st.text_input("Contraseña Actual", type="password")
            pass_nueva = st.text_input("Nueva Contraseña", type="password")
            pass_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
            btn_pass = st.form_submit_button("💾 Actualizar Contraseña")
            
            if btn_pass:
                if pass_nueva != pass_conf:
                    st.error("Las nuevas contraseñas no coinciden.")
                else:
                    u_ok = verificar_login(st.session_state["username"], pass_act)
                    if u_ok:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hash_pass(pass_nueva), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Contraseña actualizada exitosamente.")
                    else:
                        st.error("La contraseña actual es incorrecta.")

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de la Base de Datos")
        st.caption("Copia de seguridad y restauración completa del sistema")
        
        tab_b1, tab_b2 = st.tabs(["⬇️ Copia de Seguridad", "🔄 Restauración de Respaldo"])
        
        with tab_b1:
            st.subheader("Descargar Copia de Seguridad Actual")
            st.info("Haga clic en el botón para descargar el archivo `sistema_pacientes.db` con toda la información registrada.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    f_bytes = f_db.read()
                    st.download_button(
                        label="⬇️ Descargar Copia de Seguridad (.db)",
                        data=f_bytes,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
            else:
                st.error("No se encontró el archivo de base de datos.")

        with tab_b2:
            st.subheader("Restaurar Base de Datos desde un Archivo .db")
            st.warning("⚠️ **ATENCIÓN DE SEGURIDAD**: La restauración reemplazará completamente la base de datos actual con los datos del archivo cargado.")
            
            uploaded_db = st.file_uploader("Seleccione el archivo .db o .sqlite de respaldo", type=["db", "sqlite", "sqlite3"])
            
            if uploaded_db is not None:
                st.error("🚨 Se ha seleccionado un archivo. Presione el botón de abajo únicamente si está seguro de reemplazar toda la base de datos actual.")
                
                if st.button("🔄 Confirmar y Restaurar Base de Datos Ahora", type="primary", use_container_width=True):
                    try:
                        db_bytes = uploaded_db.getvalue()
                        
                        with open(DB_FILE, "wb") as f_out:
                            f_out.write(db_bytes)
                            
                        init_db()
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT count(*) FROM pacientes_registro")
                        c_pac = c.fetchone()[0]
                        conn.close()
                        
                        st.balloons()
                        st.success(f"🎉 ¡Base de datos restaurada con éxito! Se cargaron los datos del respaldo ({c_pac} residentes registrados en la base de datos).")
                        st.info("Presione el botón de abajo para recargar la pantalla con los nuevos datos.")
                        
                        if st.button("🚀 Recargar Pantalla / Aplicar Cambios", use_container_width=True):
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ Error al restaurar la base de datos: {e}")

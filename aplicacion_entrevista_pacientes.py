import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Comunidad Terapéutica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de Usuarios Administrativos (Login)
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'
        )
    \'\'\')
    
    # Migración de columna rol si no existe
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'")
        
    # Tabla de Pacientes
    c.execute(\'\'\'
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
    \'\'\')
    
    # Tabla de Entrevistas de Consejería
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    \'\'\')

    # Tabla de Fichas de Ingreso y Admisión (Nueva)
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    \'\'\')
    
    # Tabla de Medicamentos e Inventario
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS medicamentos (
            paciente_id TEXT PRIMARY KEY,
            meds_json TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    \'\'\')

    # Tabla de Catálogo Central de Medicamentos
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            observaciones TEXT
        )
    \'\'\')
    
    # Tabla de Historial de Entregas de Medicamentos
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    \'\'\')
    
    # Tabla de Grupos Terapéuticos
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS grupos_terapeutos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            etapa_al_momento TEXT,
            fecha_grupo TEXT,
            facilitador TEXT,
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    \'\'\')
    
    # Tabla de Historial de Cambios de Etapa
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_origen TEXT,
            etapa_destino TEXT,
            fecha_cambio TEXT,
            usuario_autoriza TEXT
        )
    \'\'\')
    
    # Tabla de Requisitos por Etapa
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    \'\'\')

    # Tabla de Repositorio de Documentos en la Nube
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT,
            nombre_archivo TEXT,
            mime_type TEXT,
            bytes_blob BLOB,
            descripcion TEXT,
            fecha_subida TEXT,
            usuario_subida TEXT
        )
    \'\'\')
    
    # Crear o asegurar usuario admin supremo
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")
                  
    # Poblar Catálogo Inicial de Medicamentos si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_def = [
            ('Omeprazol', 'Cápsulas', '20 mg', 'Protector gástrico'),
            ('Paracetamol', 'Comprimidos', '500 mg', 'Analgésico y antipirético'),
            ('Ibuprofeno', 'Grageas', '400 mg', 'Antiinflamatorio'),
            ('Clonazepam', 'Tabletas', '2 mg', 'Uso controlado psiquiátrico'),
            ('Fluoxetina', 'Cápsulas', '20 mg', 'Antidepresivo'),
            ('Complejo B', 'Tabletas', 'Estándar', 'Multivitamínico de apoyo')
        ]
        c.executemany('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, observaciones) VALUES (?, ?, ?, ?)', meds_def)

    # Poblar Requisitos Iniciales de Etapas
    c.execute('SELECT COUNT(*) FROM requisitos_etapas')
    if c.fetchone()[0] == 0:
        reqs = [
            ('ACOGIDA', 'Compromiso Existencial', 0),
            ('ACOGIDA', '2 Señalamientos correctos', 0),
            ('ACOGIDA', '5 Reglas de Usuario', 0),
            ('ACOGIDA', '5 Reglas de Convivencia', 0),
            ('ACOGIDA', '4 Grupos "Terapia de Grupo"', 1),
            ('ACOGIDA', '2 Grupos "Aquí y Ahora"', 1),
            
            ('IDENTIFICACIÓN', 'Autobiografía', 0),
            ('IDENTIFICACIÓN', 'Oración de la mañana', 0),
            ('IDENTIFICACIÓN', 'Filosofía de la Comunidad', 0),
            ('IDENTIFICACIÓN', '10 Reglas de Usuario', 0),
            ('IDENTIFICACIÓN', '10 Reglas de Convivencia', 0),
            ('IDENTIFICACIÓN', '4 Grupos "Aquí y Ahora"', 1),
            ('IDENTIFICACIÓN', '4 Grupos "Terapia de Grupo"', 1),
            ('IDENTIFICACIÓN', '4 Grupos "Feedbacks"', 1),
            
            ('ELABORACIÓN', 'Filosofía del Ayer, Hoy y Mañana', 0),
            ('ELABORACIÓN', 'Oración del Medio día', 0),
            ('ELABORACIÓN', '15 Reglas de Usuario', 0),
            ('ELABORACIÓN', '15 Reglas de Convivencia', 0),
            ('ELABORACIÓN', 'Proyecto de vida', 0),
            ('ELABORACIÓN', '4 Grupos "Aquí y Ahora"', 1),
            ('ELABORACIÓN', '4 Grupos "Terapia de Grupo"', 1),
            ('ELABORACIÓN', '4 Grupos "Feedbacks"', 1),
            
            ('CONSOLIDACIÓN', '30 Reglas de Usuario', 0),
            ('CONSOLIDACIÓN', '20 Reglas de Convivencia', 0),
            ('CONSOLIDACIÓN', 'Oración del Medio día', 0),
            ('CONSOLIDACIÓN', 'Plan de Servicio Social', 0),
            ('CONSOLIDACIÓN', '2 Grupos "Aquí y Ahora"', 1),
            ('CONSOLIDACIÓN', '2 Grupos "Terapia de Grupo"', 1),
            ('CONSOLIDACIÓN', '2 Grupos "Feedbacks"', 1),
            
            ('SERVICIO SOCIAL', '30 Dias de Servicio', 0),
            ('SERVICIO SOCIAL', '2 Grupos "Aquí y Ahora"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Terapia de Grupo"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Feedbacks"', 1)
        ]
        c.executemany('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', reqs)
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def es_admin():
    u = st.session_state.get("username", "")
    r = st.session_state.get("rol", "")
    return u == "admin" or "Nivel 1" in str(r)

def es_lectura_escritura():
    r = st.session_state.get("rol", "")
    return es_admin() or "Nivel 2" in str(r)

# --- FUNCIONES DE PACIENTES ---
def listar_pacientes_completo():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(\'\'\'
        SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, 
               tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano, fecha_modificacion
        FROM pacientes ORDER BY paciente_id ASC
    \'\'\')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def guardar_usuario_paciente(paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa, f_inicio_etapa, usuario_act):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute(\'\'\'
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?,
                fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        \'\'\', (nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa, f_inicio_etapa, fecha_actual, usuario_act, paciente_id))
    else:
        c.execute(\'\'\'
            INSERT INTO pacientes 
            (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, 
             etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        \'\'\', (paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa, f_inicio_etapa, fecha_actual, fecha_actual, usuario_act))
        
    conn.commit()
    conn.close()

def verificar_duplicado_nombre(nombre_completo, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nom_clean = " ".join(nombre_completo.strip().upper().split())
    if paciente_id_actual:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE UPPER(nombre_completo) = ? AND paciente_id != ?', (nom_clean, paciente_id_actual))
    else:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE UPPER(nombre_completo) = ?', (nom_clean,))
    row = c.fetchone()
    conn.close()
    return row

def eliminar_paciente_db(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    c.execute('DELETE FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    c.execute('DELETE FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    c.execute('DELETE FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    c.execute('DELETE FROM grupos_terapeutos WHERE paciente_id = ?', (paciente_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE FICHA DE INGRESO ---
def guardar_ficha_ingreso(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute(\'\'\'
            UPDATE ficha_ingreso 
            SET fecha_modificacion = ?, datos_json = ?, usuario_registro = ?
            WHERE paciente_id = ?
        \'\'\', (fecha_actual, datos_json, usuario, paciente_id))
    else:
        c.execute(\'\'\'
            INSERT INTO ficha_ingreso (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?)
        \'\'\', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_ficha_ingreso(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def eliminar_ficha_ingreso_db(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ENTREVISTA ---
def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute(\'\'\'
            UPDATE entrevistas 
            SET fecha_modificacion = ?, datos_json = ?, usuario_registro = ?
            WHERE paciente_id = ?
        \'\'\', (fecha_actual, datos_json, usuario, paciente_id))
    else:
        c.execute(\'\'\'
            INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?)
        \'\'\', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(\'\'\'
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    \'\'\', (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "Todas las carpetas":
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC', (carpeta_filtro,))
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- CLASE PARA GENERACIÓN DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(106, 27, 154) # Morado Sawabona
        self.cell(0, 8, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, 'C. Corregidora # 135 Col. Centro Colima Col. C.P. 28000 | Tel: 312 136 1123', 0, 1, 'C')
        self.ln(3)
        self.set_draw_color(106, 27, 154)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()} | Documento Confidencial de Sawabona Shikoba A.C.', 0, 0, 'C')

def limpiar_texto(texto):
    if not texto:
        return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

def generar_pdf_ficha_ingreso(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 8, limpiar_texto(f"FICHA DE INGRESO Y ADMISIÓN - EXP: {paciente_id}"), 0, 1, 'C')
    pdf.ln(2)
    
    # 1. Datos del Paciente
    pdf.set_fill_color(240, 235, 248)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, limpiar_texto(" 1. DATOS GENERALES DEL PACIENTE"), 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 9)
    
    d_p = datos.get("paciente", {})
    pdf.cell(95, 6, limpiar_texto(f"Nombre: {d_p.get('nombre', '')}"), 1, 0)
    pdf.cell(45, 6, limpiar_texto(f"Edad: {d_p.get('edad', '')}"), 1, 0)
    pdf.cell(50, 6, limpiar_texto(f"F. Nac: {d_p.get('f_nac', '')}"), 1, 1)
    
    pdf.cell(65, 6, limpiar_texto(f"Estado Civil: {d_p.get('estado_civil', '')}"), 1, 0)
    pdf.cell(65, 6, limpiar_texto(f"Escolaridad: {d_p.get('escolaridad', '')}"), 1, 0)
    pdf.cell(60, 6, limpiar_texto(f"Ocupación: {d_p.get('ocupacion', '')}"), 1, 1)
    
    pdf.cell(95, 6, limpiar_texto(f"Religión: {d_p.get('religion', '')}"), 1, 0)
    pdf.cell(95, 6, limpiar_texto(f"Servicios Médicos: {d_p.get('serv_medicos', '')}"), 1, 1)
    
    d_dom = d_p.get("domicilio", {})
    pdf.cell(0, 6, limpiar_texto(f"Domicilio: {d_dom.get('calle', '')} #{d_dom.get('num', '')}, Col. {d_dom.get('colonia', '')}, {d_dom.get('municipio', '')}, {d_dom.get('estado', '')} C.P. {d_dom.get('cp', '')}"), 1, 1)
    pdf.ln(3)

    # 2. Datos del Responsable y Costos
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, limpiar_texto(" 2. RESPONSABLE DEL INGRESO Y TÉRMINOS FINANCIEROS"), 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 9)
    
    d_r = datos.get("responsable", {})
    pdf.cell(100, 6, limpiar_texto(f"Responsable: {d_r.get('nombre', '')}"), 1, 0)
    pdf.cell(45, 6, limpiar_texto(f"Parentesco: {d_r.get('parentesco', '')}"), 1, 0)
    pdf.cell(45, 6, limpiar_texto(f"Teléfono: {d_r.get('telefono', '')}"), 1, 1)
    
    d_f = datos.get("financiero", {})
    pdf.cell(65, 6, limpiar_texto(f"Sucursal: {d_f.get('sucursal', '')}"), 1, 0)
    pdf.cell(65, 6, limpiar_texto(f"Fecha Ingreso: {d_f.get('f_ingreso', '')} {d_f.get('h_ingreso', '')}"), 1, 0)
    pdf.cell(60, 6, limpiar_texto(f"Modalidad: {d_f.get('modalidad', '')}"), 1, 1)
    
    pdf.cell(65, 6, limpiar_texto(f"Costo Ingreso: ${d_f.get('costo_ingreso', 0):,}"), 1, 0)
    pdf.cell(65, 6, limpiar_texto(f"Mensualidad: ${d_f.get('mensualidad', 0):,}"), 1, 0)
    pdf.cell(60, 6, limpiar_texto(f"Pagaré por: ${d_f.get('pagare', 0):,}"), 1, 1)
    pdf.ln(3)

    # 3. Sustancias de Consumo
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, limpiar_texto(" 3. SUSTANCIAS DE CONSUMO Y SUSTANCIA DE IMPACTO"), 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 9)
    susts = datos.get("sustancias", [])
    sust_str = ", ".join(susts) if susts else "Ninguna especificada"
    pdf.multi_cell(0, 6, limpiar_texto(f"Sustancias detectadas: {sust_str}"), 1, 'L')
    pdf.cell(0, 6, limpiar_texto(f"Sustancia de Impacto Principal: {datos.get('sustancia_impacto', 'No especificada')}"), 1, 1, 'L')
    pdf.ln(3)

    # 4. Cláusula NOM-028-SSA2-2009
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(0, 5, limpiar_texto("AUTORIZACIÓN Y COMPROMISO DE TRATAMIENTO (NOM-028-SSA2-2009)"), 0, 1, 'L')
    pdf.set_font('Arial', '', 8)
    clausula = ("El responsable manifiesta su conformidad para internar voluntaria/involuntariamente a su familiar por un periodo recomendado "
                "de 6 a 8 meses para su rehabilitación integral en la Comunidad Terapéutica Sawabona Shikoba A.C., con apego a los "
                "derechos humanos y lineamientos sanitarios oficiales de la NOM-028-SSA2-2009.")
    pdf.multi_cell(0, 4, limpiar_texto(clausula), 1, 'J')
    pdf.ln(12)

    # Firmas
    pdf.cell(90, 6, "________________________________________", 0, 0, 'C')
    pdf.cell(10, 6, "", 0, 0)
    pdf.cell(90, 6, "________________________________________", 0, 1, 'C')
    pdf.set_font('Arial', 'B', 8)
    pdf.cell(90, 4, limpiar_texto("FIRMA DEL RESPONSABLE FAMILIAR"), 0, 0, 'C')
    pdf.cell(10, 4, "", 0, 0)
    pdf.cell(90, 4, limpiar_texto("DIRECTOR / ENCARGADO DEL ESTABLECIMIENTO"), 0, 1, 'C')

    output_path = f"/workspace/scratch/ficha_ingreso_{paciente_id}.pdf"
    pdf.output(output_path)
    return output_path

# --- INICIALIZACIÓN ---
init_db()

# --- AUTENTICACIÓN / LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center; color: #6A1B9A;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #4A148C;'>Sistema de Control y Comunidad Terapéutica</h3>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔑 Iniciar Sesión en el Sistema")
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit_login:
                valido = verificar_login(user_input, pass_input)
                if valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = valido[0]
                    st.session_state["nombre_completo"] = valido[1]
                    st.session_state["rol"] = valido[2]
                    st.toast(f"🎉 ¡Bienvenido {valido[1]}!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
    st.stop()

# --- BARRA LATERAL Y NAVEGACIÓN ---
st.sidebar.title("🌱 Sawabona Shikoba")
st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
st.sidebar.write(f"🏷️ **Rol**: {st.session_state['rol']}")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.write("---")

opciones_menu = [
    "🏠 Inicio / Resumen General",
    "📄 Ficha de Ingreso y Admisión",
    "👤 Registro y Edición de Usuarios",
    "📝 Entrevista Inicial de Consejería",
    "🎯 Gestión de Etapas & Proceso",
    "🗣️ Grupos Terapéuticos",
    "💊 Control de Medicamentos e Inventario",
    "📦 Respaldo y Restauración"
]

if es_admin():
    opciones_menu.append("📁 Repositorio de Documentos")
    opciones_menu.append("⚙️ Seguridad & Roles")

menu = st.sidebar.radio("Navegación del Sistema", opciones_menu)

# --- MÓDULO 0: INICIO / RESUMEN ---
if menu == "🏠 Inicio / Resumen General":
    st.title("🏠 Panel Principal de Sawabona Shikoba A.C.")
    st.write("Bienvenido al sistema de gestión clínica, seguimiento de residentes y control operativo.")
    
    pacs = listar_pacientes_completo()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Residentes Capturados", len(pacs))
    c2.metric("Residentes Activos", len([p for p in pacs if p[5] == 'A']))
    c3.metric("Residentes en Acogida", len([p for p in pacs if p[7] == 'ACOGIDA']))
    c4.metric("Residentes en Servicio Social", len([p for p in pacs if p[7] == 'SERVICIO SOCIAL']))
    st.write("---")
    
    st.subheader("📋 Lista Rápida de Residentes Registrados")
    if pacs:
        data_table = []
        for p in pacs:
            f_ing = p[2] if p[2] else "No registrada"
            dias_tot = "N/A"
            if p[2]:
                try:
                    d_obj = datetime.strptime(p[2], "%Y-%m-%d").date()
                    dias_tot = f"{(date.today() - d_obj).days} días"
                except:
                    pass
            data_table.append({
                "Folio / ID": p[0],
                "Nombre Completo": p[1],
                "Fecha Ingreso Real": f_ing,
                "Días Totales": dias_tot,
                "Etapa Actual": p[7],
                "Estatus": "Activo" if p[5] == 'A' else "Inactivo"
            })
        st.dataframe(data_table, use_container_width=True)
    else:
        st.info("No hay residentes capturados aún en la base de datos.")

# --- MÓDULO 1: FICHA DE INGRESO Y ADMISIÓN (SOLICITADO) ---
elif menu == "📄 Ficha de Ingreso y Admisión":
    st.title("📄 Ficha de Ingreso, Solicitud y Admisión")
    st.write("Módulo para capturar, editar, eliminar e imprimir el contrato de admisión basado en **`ingreso AV Sawabona.pdf`**.")
    
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["🆕 Registrar / Editar Ficha", "🔍 Consultar Fichas", "🗑️ Eliminar Ficha"])
    
    pacs_all = listar_pacientes_completo()
    
    with sub_tab1:
        st.subheader("Captura de Ficha de Admisión")
        
        modo_f = st.radio("Acción a realizar:", ["🆕 Crear Nueva Ficha de Ingreso", "✏️ Modificar Ficha Existente"], horizontal=True)
        
        edit_f_id = None
        datos_prev = {}
        
        if modo_f == "✏️ Modificar Ficha Existente":
            if not pacs_all:
                st.warning("No hay pacientes registrados en el sistema.")
            else:
                opc_fichas = [f"{p[0]} - {p[1]}" for p in pacs_all]
                sel_f = st.selectbox("🔑 Selecciona el Paciente a Modificar:", opc_fichas)
                edit_f_id = sel_f.split(" - ")[0]
                datos_prev, _, _, _ = obtener_ficha_ingreso(edit_f_id)
                if not datos_prev:
                    st.info("Este paciente no tiene una Ficha de Ingreso previa guardada. Puedes capturarla ahora.")
                    datos_prev = {}

        p_id_f = edit_f_id if modo_f == "✏️ Modificar Ficha Existente" and edit_f_id else st.text_input("Folio / ID del Paciente (ej: PAC-001)", value=f"PAC-{len(pacs_all)+1:03d}")
        
        prev_pac = datos_prev.get("paciente", {})
        prev_resp = datos_prev.get("responsable", {})
        prev_fin = datos_prev.get("financiero", {})
        
        with st.form(f"form_ficha_ingreso_{p_id_f}"):
            st.markdown("### 1. Datos del Responsable del Ingreso")
            col_r1, col_r2, col_r3 = st.columns([2, 1, 1])
            resp_nombre = col_r1.text_input("Nombre Completo del Responsable Familiar", value=prev_resp.get("nombre", ""))
            resp_parentesco = col_r2.text_input("Parentesco (Padre, Madre, Cónyuge)", value=prev_resp.get("parentesco", ""))
            resp_tel = col_r3.text_input("Teléfono del Responsable", value=prev_resp.get("telefono", ""))
            
            st.markdown("### 2. Datos Generales del Usuario / Paciente")
            col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
            pac_nombre = col_p1.text_input("Nombre Completo del Paciente", value=prev_pac.get("nombre", ""))
            pac_edad = col_p2.number_input("Edad", min_value=12, max_value=99, value=int(prev_pac.get("edad", 25)))
            
            f_nac_val = date.today()
            if prev_pac.get("f_nac"):
                try: f_nac_val = datetime.strptime(prev_pac.get("f_nac"), "%Y-%m-%d").date()
                except: pass
            pac_f_nac = col_p3.date_input("Fecha de Nacimiento", value=f_nac_val)
            
            col_p4, col_p5, col_p6, col_p7 = st.columns(4)
            pac_est_civil = col_p4.selectbox("Estado Civil", ["SOLTERO(A)", "CASADO(A)", "UNION LIBRE", "DIVORCIADO(A)", "VIUDO(A)"], index=0)
            pac_escolaridad = col_p5.selectbox("Escolaridad", ["PRIMARIA", "SECUNDARIA", "PREPARATORIA", "LICENCIATURA", "POSGRADO", "NINGUNA"], index=1)
            pac_religion = col_p6.text_input("Religión", value=prev_pac.get("religion", "Católico"))
            pac_ocupacion = col_p7.text_input("Ocupación", value=prev_pac.get("ocupacion", "Empleado"))
            
            st.markdown("#### Domicilio del Paciente")
            col_d1, col_d2, col_d3 = st.columns([2, 1, 1])
            d_prev = prev_pac.get("domicilio", {})
            dom_calle = col_d1.text_input("Calle y Número", value=d_prev.get("calle", ""))
            dom_col = col_d2.text_input("Colonia / Población", value=d_prev.get("colonia", ""))
            dom_mun = col_d3.text_input("Municipio", value=d_prev.get("municipio", "Colima"))
            
            col_d4, col_d5 = st.columns(2)
            dom_edo = col_d4.text_input("Estado", value=d_prev.get("estado", "Colima"))
            dom_cp = col_d5.text_input("Código Postal", value=d_prev.get("cp", "28000"))
            
            st.markdown("### 3. Sustancias de Consumo y Sustancia de Impacto")
            opc_sust = ["Alcohol", "Cannabis", "Cocaína", "Metanfetaminas", "Alucinógenos", "Inhalables", "Tabaco", "Benzodiazepinas", "Solventes", "Opiáceos", "Anfetaminas"]
            prev_sust = datos_prev.get("sustancias", ["Alcohol", "Cannabis"])
            
            sust_sel = st.multiselect("Selecciona todas las sustancias consumidas:", opc_sust, default=[s for s in prev_sust if s in opc_sust])
            sust_impacto = st.selectbox("Sustancia de Impacto Principal:", opc_sust, index=0)
            
            st.markdown("### 4. Sucursal, Costos y Términos de Internamiento")
            col_f1, col_f2, col_f3 = st.columns(3)
            f_sucursal = col_f1.text_input("Sucursal", value=prev_fin.get("sucursal", "Matriz Colima"))
            f_costo_ingreso = col_f2.number_input("Costo de Ingreso ($)", value=float(prev_fin.get("costo_ingreso", 4500.0)))
            f_mensualidad = col_f3.number_input("Mensualidad ($)", value=float(prev_fin.get("mensualidad", 6000.0)))
            
            col_f4, col_f5 = st.columns(2)
            f_pagare = col_f4.number_input("Importe de Pagaré ($)", value=float(prev_fin.get("pagare", 42000.0)))
            f_modalidad = col_f5.selectbox("Modalidad de Internamiento (NOM-028-SSA2-2009)", ["VOLUNTARIO", "INVOLUNTARIO"], index=0)
            
            btn_guardar_f = st.form_submit_button("💾 Guardar Ficha de Ingreso y Admisión", use_container_width=True)
            
            if btn_guardar_f:
                if not es_lectura_escritura():
                    st.error("🔒 Tu rol no tiene permisos de edición.")
                elif not pac_nombre or not p_id_f:
                    st.error("⚠️ El Nombre del Paciente y el Folio son obligatorios.")
                else:
                    dict_ficha = {
                        "paciente": {
                            "nombre": pac_nombre,
                            "edad": pac_edad,
                            "f_nac": str(pac_f_nac),
                            "estado_civil": pac_est_civil,
                            "escolaridad": pac_escolaridad,
                            "religion": pac_religion,
                            "ocupacion": pac_ocupacion,
                            "serv_medicos": "Sí",
                            "domicilio": {
                                "calle": dom_calle,
                                "colonia": dom_col,
                                "municipio": dom_mun,
                                "estado": dom_edo,
                                "cp": dom_cp
                            }
                        },
                        "responsable": {
                            "nombre": resp_nombre,
                            "parentesco": resp_parentesco,
                            "telefono": resp_tel
                        },
                        "sustancias": sust_sel,
                        "sustancia_impacto": sust_impacto,
                        "financiero": {
                            "sucursal": f_sucursal,
                            "costo_ingreso": f_costo_ingreso,
                            "mensualidad": f_mensualidad,
                            "pagare": f_pagare,
                            "modalidad": f_modalidad,
                            "f_ingreso": str(date.today()),
                            "h_ingreso": datetime.now().strftime("%H:%M")
                        }
                    }
                    
                    guardar_ficha_ingreso(p_id_f, dict_ficha, st.session_state["username"])
                    # Sincronizar usuario paciente si no existe
                    guardar_usuario_paciente(p_id_f, pac_nombre, str(date.today()), str(pac_f_nac), "MASCULINO", "A", "Paciente", "ACOGIDA", str(date.today()), st.session_state["username"])
                    
                    st.success(f"✅ ¡Ficha de Ingreso guardada correctamente para **{pac_nombre}** ({p_id_f})!")
                    st.toast("🎉 Ficha guardada en la base de datos.")
                    st.balloons()

    with sub_tab2:
        st.subheader("Consultar e Imprimir Ficha de Ingreso")
        if not pacs_all:
            st.info("No hay pacientes con fichas para consultar.")
        else:
            opc_cons = [f"{p[0]} - {p[1]}" for p in pacs_all]
            sel_c = st.selectbox("Selecciona el Paciente:", opc_cons, key="sel_cons_ficha")
            p_id_c = sel_c.split(" - ")[0]
            
            d_f, f_reg, f_mod, u_reg = obtener_ficha_ingreso(p_id_c)
            if not d_f:
                st.warning("Este residente no cuenta con Ficha de Ingreso capturada.")
            else:
                st.success(f"📋 Ficha de Ingreso | Folio: **{p_id_c}** | Capturado por: **{u_reg}** el {f_reg}")
                st.json(d_f)
                
                pdf_path = generar_pdf_ficha_ingreso(p_id_c, d_f)
                with open(pdf_path, "rb") as f_bytes:
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso en PDF",
                        data=f_bytes,
                        file_name=f"Ficha_Ingreso_{p_id_c}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    with sub_tab3:
        st.subheader("Eliminar Ficha de Ingreso")
        if not es_admin():
            st.error("🔒 Solo el Administrador puede eliminar fichas de ingreso.")
        else:
            if pacs_all:
                opc_del = [f"{p[0]} - {p[1]}" for p in pacs_all]
                sel_del = st.selectbox("Selecciona la Ficha a Eliminar:", opc_del, key="sel_del_ficha")
                p_id_del = sel_del.split(" - ")[0]
                
                if st.button("🗑️ Confirmar Eliminación Permanente", type="primary"):
                    eliminar_ficha_ingreso_db(p_id_del)
                    st.success(f"✅ Ficha del paciente {p_id_del} eliminada correctamente.")
                    st.toast("🗑️ Ficha eliminada.")
                    st.balloons()
                    st.rerun()

# --- MÓDULO 2: REGISTRO DE USUARIOS ---
elif menu == "👤 Registro y Edición de Usuarios":
    st.title("👤 Registro y Edición de Pacientes")
    st.write("Gestión de catálogo de pacientes, fechas de ingreso, etapas y roles.")
    
    modo_u = st.radio("Acción:", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
    pacs = listar_pacientes_completo()
    
    edit_id = None
    u_data = None
    if modo_u == "✏️ Modificar / Editar Usuario Existente":
        if not pacs:
            st.warning("No hay usuarios registrados aún.")
        else:
            opcs = [f"{p[0]} - {p[1]}" for p in pacs]
            s_u = st.selectbox("🔑 Selecciona el Usuario a Editar:", opcs)
            edit_id = s_u.split(" - ")[0]
            u_data = obtener_paciente(edit_id)

    p_id_field = edit_id if modo_u == "✏️ Modificar / Editar Usuario Existente" and edit_id else f"PAC-{len(pacs)+1:03d}"
    
    with st.form(f"form_paciente_{p_id_field}"):
        col1, col2 = st.columns(2)
        n_comp = col1.text_input("Nombre Completo del Paciente", value=u_data[1] if u_data else "")
        t_usr = col2.selectbox("Tipo de Usuario", ["Paciente", "Residente Reingreso", "Personal/Staff"], index=0)
        
        col3, col4, col5 = st.columns(3)
        
        f_ing_def = date.today()
        if u_data and u_data[2]:
            try: f_ing_def = datetime.strptime(u_data[2], "%Y-%m-%d").date()
            except: pass
        f_ingreso = col3.date_input("Fecha de Ingreso Real", value=f_ing_def)
        
        f_nac_def = date.today()
        if u_data and u_data[3]:
            try: f_nac_def = datetime.strptime(u_data[3], "%Y-%m-%d").date()
            except: pass
        f_nac = col4.date_input("Fecha de Nacimiento", value=f_nac_def)
        
        sexo = col5.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if not u_data or u_data[4]=='MASCULINO' else 1)
        
        col6, col7, col8 = st.columns(3)
        estatus = col6.selectbox("Estatus", ["A - Activo", "B - Bloqueado / Bofetada", "I - Inactivo / Egresado"], index=0)
        estatus_code = estatus.split(" - ")[0]
        
        etapas_lst = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
        etapa_act = col7.selectbox("Etapa Actual", etapas_lst, index=etapas_lst.index(u_data[7]) if u_data and u_data[7] in etapas_lst else 0)
        
        f_etapa_def = date.today()
        if u_data and u_data[8]:
            try: f_etapa_def = datetime.strptime(u_data[8], "%Y-%m-%d").date()
            except: pass
        f_inicio_etapa = col8.date_input("Fecha Inicio de Etapa Actual", value=f_etapa_def)
        
        btn_g_u = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True)
        
        if btn_g_u:
            if not es_lectura_escritura():
                st.error("🔒 No tienes permisos de edición.")
            elif not n_comp:
                st.error("⚠️ El Nombre Completo es obligatorio.")
            else:
                dup = verificar_duplicado_nombre(n_comp, p_id_field)
                if dup:
                    st.error(f"❌ Ya existe un paciente registrado con el nombre '**{dup[1]}**' (Folio: {dup[0]}).")
                else:
                    guardar_usuario_paciente(p_id_field, n_comp, str(f_ingreso), str(f_nac), sexo, estatus_code, t_usr, etapa_act, str(f_inicio_etapa), st.session_state["username"])
                    st.success(f"✅ ¡Paciente **{n_comp}** ({p_id_field}) guardado exitosamente!")
                    st.toast("🎉 Datos de paciente actualizados.")
                    st.balloons()

# --- MÓDULO: REPOSITORIO DE DOCUMENTOS ---
elif menu == "📁 Repositorio de Documentos":
    st.title("📁 Repositorio de Documentos, Manuales y Formatos")
    st.write("Almacenamiento y descarga de archivos en la nube organizados por carpetas.")
    
    if not es_admin():
        st.error("🔒 Módulo exclusivo para Administradores.")
    else:
        carpetas = [
            "Todas las carpetas",
            "📋 Formatos Clínicos y Administrativos",
            "📖 Manuales de Operación",
            "⚖️ Reglamentos y Normativas",
            "📑 Plantillas de Evaluación",
            "📁 Documentos Generales"
        ]
        
        c_filtro = st.selectbox("🔍 Filtrar por Carpeta:", carpetas)
        st.write("---")
        
        col_up, col_list = st.columns([1, 2])
        
        with col_up:
            st.subheader("📤 Subir Nuevo Documento")
            with st.form("form_subir_doc"):
                carp_sel = st.selectbox("Carpeta Destino:", carpetas[1:])
                file_up = st.file_uploader("Selecciona archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "png", "jpg", "txt"])
                desc_up = st.text_area("Descripción / Notas del documento")
                btn_subir = st.form_submit_button("📤 Subir Documento a la Nube")
                
                if btn_subir:
                    if file_up is not None:
                        f_bytes = file_up.read()
                        guardar_documento_repositorio(carp_sel, file_up.name, file_up.type, f_bytes, desc_up, st.session_state["username"])
                        st.success(f"✅ ¡Documento **{file_up.name}** guardado en la carpeta '{carp_sel}'!")
                        st.toast("🎉 Documento subido.")
                        st.balloons()
                    else:
                        st.error("⚠️ Selecciona un archivo válido.")

        with col_list:
            st.subheader("📥 Documentos Disponibles")
            docs = obtener_documentos_repositorio(c_filtro)
            if not docs:
                st.info("No se encontraron documentos en la carpeta seleccionada.")
            else:
                for d in docs:
                    d_id, d_carp, d_nom, d_mime, d_bytes, d_desc, d_fsub, d_usub = d
                    with st.expander(f"📄 {d_nom} ({d_carp})"):
                        st.write(f"**Descripción**: {d_desc}")
                        st.write(f"**Subido por**: {d_usub} el {d_fsub}")
                        
                        col_d1, col_d2 = st.columns(2)
                        col_d1.download_button(
                            label="📥 Descargar Archivo",
                            data=d_bytes,
                            file_name=d_nom,
                            mime=d_mime if d_mime else "application/octet-stream"
                        )
                        if col_d2.button("🗑️ Eliminar", key=f"del_doc_{d_id}"):
                            eliminar_documento_repositorio(d_id)
                            st.success("Documento eliminado.")
                            st.toast("🗑️ Archivo eliminado.")
                            st.rerun()

# --- MÓDULO: RESPALDO Y RESTAURACIÓN ---
elif menu == "📦 Respaldo y Restauración":
    st.title("📦 Respaldo y Restauración de Base de Datos")
    st.write("Descarga una copia completa de seguridad (`.db`) para proteger todos tus registros, fotos y documentos.")
    
    t1, t2 = st.tabs(["📥 Descargar Respaldo Seguro", "📤 Restaurar Base de Datos"])
    
    with t1:
        st.subheader("Descargar Respaldo `.db` Completo")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f_db:
                st.download_button(
                    label="📥 Descargar Copia de Seguridad (.db)",
                    data=f_db,
                    file_name=f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
            st.info("💡 **Recomendación**: Descarga este respaldo al terminar tu jornada para proteger tus datos ante cualquier reinicio del servidor.")
            
    with t2:
        st.subheader("Restaurar desde un Archivo de Respaldo")
        if not es_admin():
            st.error("🔒 Solo el Administrador puede restaurar la base de datos.")
        else:
            db_file_up = st.file_uploader("Selecciona el archivo `.db` de respaldo:", type=["db", "sqlite"])
            if db_file_up is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", type="primary"):
                    with open(DB_FILE, "wb") as f_out:
                        f_out.write(db_file_up.read())
                    st.success("✅ Base de datos restaurada correctamente.")
                    st.toast("🎉 Restauración exitosa.")
                    st.balloons()
                    st.rerun()

# --- OTROS MÓDULOS PERMANECEN ACTIVOS Y FUNCIONALES ---

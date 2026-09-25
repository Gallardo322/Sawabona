import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Control Clínico y Consejería",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    # Tabla de Registro Basal de Pacientes / Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            nombre_search TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    # Asegurar columna estatus si la tabla ya existía de versiones anteriores
    c.execute("PRAGMA table_info(pacientes_registro)")
    cols = [col[1] for col in c.fetchall()]
    if "estatus" not in cols and "paciente_id" in cols:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN estatus TEXT DEFAULT 'A'")

    # Tabla de Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    # Tabla de Medicamentos
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
    
    # Crear usuario administrador por defecto si no existe
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

# --- FUNCIONES DE PACIENTES / USUARIOS REGISTRADOS ---
def guardar_paciente_registro(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, usuario, estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nombre_clean = nombre_completo.strip().lower()
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro 
            SET nombre_completo = ?, nombre_search = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), nombre_clean, str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro (paciente_id, nombre_completo, nombre_search, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), nombre_clean, str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def buscar_paciente_duplicado(nombre_completo, paciente_id_actual=""):
    """Busca si existe un paciente con el mismo nombre (insensible a mayúsculas/minúsculas)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre_completo.strip().lower()
    c.execute('''
        SELECT paciente_id, nombre_completo, estatus FROM pacientes_registro 
        WHERE (LOWER(nombre_search) = ? OR LOWER(nombre_completo) = ?) AND paciente_id != ?
    ''', (nombre_clean, nombre_clean, paciente_id_actual))
    row = c.fetchone()
    conn.close()
    return row

def obtener_paciente_registro(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro
        FROM pacientes_registro WHERE paciente_id = ?
    ''', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        UPDATE pacientes_registro 
        SET estatus = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (nuevo_estatus, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def listar_pacientes_registrados(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('''
            SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion 
            FROM pacientes_registro 
            WHERE estatus = 'A' OR estatus IS NULL
            ORDER BY nombre_completo ASC
        ''')
    else:
        c.execute('''
            SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion 
            FROM pacientes_registro 
            ORDER BY estatus ASC, nombre_completo ASC
        ''')
    rows = c.fetchall()
    conn.close()
    return rows

def generar_siguiente_id():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    
    max_num = 0
    for row in rows:
        pid = row[0]
        if pid.startswith("PAC-"):
            try:
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except:
                pass
    return f"PAC-{max_num + 1:03d}"

# --- FUNCIONES DE ENTREVISTAS ---
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
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes_entrevista(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('''
            SELECT e.paciente_id, e.fecha_registro, e.fecha_modificacion, e.usuario_registro, p.nombre_completo, p.estatus
            FROM entrevistas e
            LEFT JOIN pacientes_registro p ON e.paciente_id = p.paciente_id
            WHERE p.estatus = 'A' OR p.estatus IS NULL
            ORDER BY e.fecha_modificacion DESC
        ''')
    else:
        c.execute('''
            SELECT e.paciente_id, e.fecha_registro, e.fecha_modificacion, e.usuario_registro, p.nombre_completo, COALESCE(p.estatus, 'A')
            FROM entrevistas e
            LEFT JOIN pacientes_registro p ON e.paciente_id = p.paciente_id
            ORDER BY e.fecha_modificacion DESC
        ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, lista_meds, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(lista_meds, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE medicamentos 
            SET meds_json = ?, observaciones = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (meds_json, observaciones, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_medicamentos(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3], row[4]
    return [], "", None, None, None

def listar_todos_medicamentos(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('''
            SELECT m.paciente_id, m.meds_json, m.observaciones, m.fecha_modificacion, p.nombre_completo, p.estatus
            FROM medicamentos m
            LEFT JOIN pacientes_registro p ON m.paciente_id = p.paciente_id
            WHERE p.estatus = 'A' OR p.estatus IS NULL
        ''')
    else:
        c.execute('''
            SELECT m.paciente_id, m.meds_json, m.observaciones, m.fecha_modificacion, p.nombre_completo, COALESCE(p.estatus, 'A')
            FROM medicamentos m
            LEFT JOIN pacientes_registro p ON m.paciente_id = p.paciente_id
        ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADORES DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SISTEMA DE CONTROL CLINICO Y CONSEJERIA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Expediente Oficial de Paciente", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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

def generar_pdf_entrevista(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p_reg = obtener_paciente_registro(paciente_id)
    nombre_p = p_reg[1] if p_reg else "N/A"
    f_ing = p_reg[2] if p_reg else "N/A"
    f_nac = p_reg[3] if p_reg else "N/A"
    sexo_p = p_reg[4] if p_reg else "N/A"
    estatus_p = "ACTIVO ('A')" if (p_reg and p_reg[5] == 'A') else "BLOQUEADO ('B')"
    
    # Encabezado del Paciente
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"PACIENTE / FOLIO: {limpiar_texto(paciente_id)} - {limpiar_texto(nombre_p)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha Ingreso: {limpiar_texto(f_ing)} | Fecha Nacimiento: {limpiar_texto(f_nac)} | Sexo: {limpiar_texto(sexo_p)} | Estatus: {limpiar_texto(estatus_p)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Dependientes econ.: {limpiar_texto(datos.get('dependientes_flag', ''))} ({limpiar_texto(datos.get('dependientes_quienes', ''))}) | Pareja: {limpiar_texto(datos.get('pareja_flag', ''))} ({limpiar_texto(datos.get('pareja_tiempo', ''))})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla de Consumo
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "ENTREVISTA INICIAL - CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    
    col_widths = [28, 20, 25, 30, 28, 22, 37]
    headers = ["Sustancia", "Consumo", "Forma", "Frecuencia", "Cantidad", "Edad Inic.", "Lugar"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    tabla_consumo = datos.get("tabla_consumo", {})
    for sust, vals in tabla_consumo.items():
        pdf.cell(col_widths[0], 6, limpiar_texto(sust), border=1)
        pdf.cell(col_widths[1], 6, limpiar_texto(str(vals.get("consumo", ""))), border=1, align="C")
        pdf.cell(col_widths[2], 6, limpiar_texto(str(vals.get("forma", ""))), border=1)
        pdf.cell(col_widths[3], 6, limpiar_texto(str(vals.get("frecuencia", ""))), border=1)
        pdf.cell(col_widths[4], 6, limpiar_texto(str(vals.get("cantidad", ""))), border=1)
        pdf.cell(col_widths[5], 6, limpiar_texto(str(vals.get("edad_inicio", ""))), border=1, align="C")
        pdf.cell(col_widths[6], 6, limpiar_texto(str(vals.get("lugar", ""))), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    
    # Sustancia de Impacto
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))} | Normally consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Disposición al Cambio
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Situación Socio-Familiar
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "SITUACION SOCIAL-FAMILIAR Y RIESGO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Integrantes de la familia: {limpiar_texto(datos.get('familia_integrantes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Relaciones sexuales tras consumir: {limpiar_texto(datos.get('relaciones_post_consumo', ''))} | Abuso fisico/sexual: {limpiar_texto(datos.get('abuso_flag', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION DE LA SESION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Evaluador: {limpiar_texto(datos.get('evaluador_nombre', ''))} ({limpiar_texto(datos.get('evaluador_cargo', ''))})", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos(paciente_id, lista_meds, observaciones):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p_reg = obtener_paciente_registro(paciente_id)
    nombre_p = p_reg[1] if p_reg else "N/A"
    f_ing = p_reg[2] if p_reg else "N/A"
    f_nac = p_reg[3] if p_reg else "N/A"
    sexo_p = p_reg[4] if p_reg else "N/A"
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, f"HOJA DE MEDICACION Y DOSIS DIARIA", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"PACIENTE / FOLIO: {limpiar_texto(paciente_id)} - {limpiar_texto(nombre_p)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Fecha Ingreso: {limpiar_texto(f_ing)} | Fecha Nacimiento: {limpiar_texto(f_nac)} | Sexo: {limpiar_texto(sexo_p)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [45, 20, 20, 20, 25, 60]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Existencia", "Indicaciones"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    for m in lista_meds:
        pdf.cell(col_w[0], 6, limpiar_texto(m.get("nombre", "")), border=1)
        pdf.cell(col_w[1], 6, str(m.get("dosis_manana", 0)), border=1, align="C")
        pdf.cell(col_w[2], 6, str(m.get("dosis_tarde", 0)), border=1, align="C")
        pdf.cell(col_w[3], 6, str(m.get("dosis_noche", 0)), border=1, align="C")
        pdf.cell(col_w[4], 6, str(m.get("existencia", 0)), border=1, align="C")
        pdf.cell(col_w[5], 6, limpiar_texto(m.get("indicaciones", "")), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.epw, 5, "Observaciones / Indicaciones Clinicas:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones))
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras(lista_alertas):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA CONSOLIDADA DE COMPRAS DE MEDICAMENTO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [25, 45, 40, 20, 20, 20, 20]
    headers = ["Folio", "Paciente", "Medicamento", "Exist.", "Dosis/Dia", "Estatus", "Sugerido"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_alertas:
        pdf.cell(col_w[0], 6, limpiar_texto(item["paciente_id"]), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(item["nombre_paciente"]), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(item["medicamento"]), border=1)
        pdf.cell(col_w[3], 6, str(item["existencia"]), border=1, align="C")
        pdf.cell(col_w[4], 6, str(item["dosis_diaria"]), border=1, align="C")
        pdf.cell(col_w[5], 6, limpiar_texto(item["estado_alerta"]), border=1, align="C")
        pdf.cell(col_w[6], 6, str(item["compra_sugerida"]), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR DB Y ESTADO ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema Clínico</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales para continuar</p>", unsafe_allow_html=True)
    
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
    # --- BARRA LATERAL ---
    st.sidebar.title("📋 Menú Principal")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "👤 Registro de Usuarios",
            "📝 Nueva Entrevista / Editar",
            "💊 Control de Medicamentos y Dosis",
            "🚨 Alertas de Existencia y Compras",
            "🔍 Buscar y Listar Pacientes",
            "⚙️ Seguridad / Contraseña"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # =========================================================================
    # SECCIÓN 1: REGISTRO DE USUARIOS / PACIENTES
    # =========================================================================
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro General de Pacientes / Usuarios")
        st.caption("Paso inicial obligatorio: Dar de alta al paciente en el sistema antes de llenar formularios o asignar medicamentos.")
        
        tab_reg, tab_list_act, tab_list_bloc = st.tabs([
            "➕ Captura / Edición de Usuario",
            "🟢 Usuarios Activos ('A')",
            "🔒 Usuarios Bloqueados ('B')"
        ])
        
        with tab_reg:
            pacientes_todos = listar_pacientes_registrados(solo_activos=False)
            opciones_pacientes = ["-- CREAR NUEVO USUARIO --"] + [f"{p[0]} - {p[1]} ({'Activo' if p[5] == 'A' else 'BLOQUEADO'})" for p in pacientes_todos]
            
            seleccion_p = st.selectbox("Seleccione un usuario existente para editar o cree uno nuevo:", opciones_pacientes)
            
            p_id_def = generar_siguiente_id()
            nombre_def = ""
            ingreso_def = date.today()
            nacimiento_def = date(1995, 1, 1)
            sexo_def = "Masculino"
            estatus_def = "A"
            es_edicion = False
            
            if seleccion_p != "-- CREAR NUEVO USUARIO --":
                pid_sel = seleccion_p.split(" - ")[0]
                p_info = obtener_paciente_registro(pid_sel)
                if p_info:
                    es_edicion = True
                    p_id_def = p_info[0]
                    nombre_def = p_info[1]
                    try:
                        ingreso_def = datetime.strptime(p_info[2], "%Y-%m-%d").date()
                    except:
                        pass
                    try:
                        nacimiento_def = datetime.strptime(p_info[3], "%Y-%m-%d").date()
                    except:
                        pass
                    sexo_def = p_info[4] if p_info[4] in ["Masculino", "Femenino", "Otro"] else "Masculino"
                    estatus_def = p_info[5] if p_info[5] in ["A", "B"] else "A"
            
            with st.form("form_registro_usuario"):
                st.subheader("Datos del Expediente Basal")
                col_u1, col_u2 = st.columns(2)
                
                with col_u1:
                    paciente_id = st.text_input("🔑 Folio / ID de Paciente *", value=p_id_def, disabled=es_edicion).strip()
                    nombre_completo = st.text_input("👤 Nombre Completo *", value=nombre_def, help="El sistema valida que no exista un usuario registrado con este mismo nombre (sin importar mayúsculas o minúsculas).").strip()
                    sexo = st.selectbox("Sexo *", ["Masculino", "Femenino", "Otro"], index=["Masculino", "Femenino", "Otro"].index(sexo_def))
                
                with col_u2:
                    fecha_ingreso = st.date_input("📅 Fecha de Ingreso *", value=ingreso_def)
                    fecha_nacimiento = st.date_input("🎂 Fecha de Nacimiento *", value=nacimiento_def)
                    estatus_opcion = st.selectbox("Estatus de Usuario *", ["A - Activo", "B - Bloqueado"], index=0 if estatus_def == "A" else 1)
                    estatus_code = "A" if estatus_opcion.startswith("A") else "B"
                
                btn_guardar_u = st.form_submit_button("💾 Guardar Usuario", use_container_width=True)
                
                if btn_guardar_u:
                    if not paciente_id or not nombre_completo:
                        st.error("⚠️ El Folio y el Nombre Completo son campos obligatorios.")
                    else:
                        # Verificar duplicados por nombre (insensible a mayúsculas/minúsculas)
                        duplicado = buscar_paciente_duplicado(nombre_completo, paciente_id_actual=paciente_id)
                        if duplicado:
                            dup_id, dup_nombre, dup_estatus = duplicado
                            est_str = "ACTIVO ('A')" if dup_estatus == 'A' else "BLOQUEADO ('B')"
                            st.error(f"❌ **Imposible registrar:** Ya existe un usuario registrado con el nombre **'{dup_nombre}'** bajo el Folio **{dup_id}** (Estatus actual: **{est_str}**). No se permiten registros duplicados.")
                        else:
                            guardar_paciente_registro(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, st.session_state["username"], estatus=estatus_code)
                            st.success(f"✅ ¡Usuario **{nombre_completo}** ({paciente_id}) guardado con éxito con Estatus '{estatus_code}'!")
                            st.rerun()

        with tab_list_act:
            st.subheader("🟢 Directorio de Usuarios Activos ('A')")
            activos = listar_pacientes_registrados(solo_activos=True)
            if not activos:
                st.info("No hay usuarios activos registrados actualmente.")
            else:
                for act in activos:
                    pid, nom, f_ing, f_nac, sx, est, f_mod = act
                    with st.expander(f"👤 **{nom}** ({pid}) | Ingreso: {f_ing} | Estatus: Activo"):
                        c_a1, c_a2 = st.columns([3, 1])
                        with c_a1:
                            st.write(f"**Fecha de Nacimiento:** {f_nac} | **Sexo:** {sx}")
                            st.write(f"**Última Modificación:** {f_mod}")
                        with c_a2:
                            if st.button(f"🔒 Bloquear Usuario", key=f"btn_bloc_{pid}"):
                                cambiar_estatus_paciente(pid, "B")
                                st.warning(f"Usuario {pid} ha sido Bloqueado ('B').")
                                st.rerun()

        with tab_list_bloc:
            st.subheader("🔒 Directorio de Usuarios Bloqueados ('B')")
            st.caption("Los usuarios bloqueados no aparecen en los formularios de captura diaria, pero su información se conserva intacta y puede reactivarse aquí en cualquier momento.")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion FROM pacientes_registro WHERE estatus = 'B' ORDER BY nombre_completo ASC")
            bloqueados = c.fetchall()
            conn.close()
            
            if not bloqueados:
                st.success("No hay usuarios bloqueados en el sistema.")
            else:
                for bloc in bloqueados:
                    pid, nom, f_ing, f_nac, sx, est, f_mod = bloc
                    with st.expander(f"🔒 **{nom}** ({pid}) | Ingreso: {f_ing} | Estatus: BLOQUEADO"):
                        c_b1, c_b2 = st.columns([3, 1])
                        with c_b1:
                            st.write(f"**Fecha de Nacimiento:** {f_nac} | **Sexo:** {sx}")
                            st.write(f"**Última Modificación:** {f_mod}")
                        with c_b2:
                            if st.button(f"🔓 Desbloquear (Activar)", key=f"btn_act_{pid}"):
                                cambiar_estatus_paciente(pid, "A")
                                st.success(f"Usuario {pid} ha sido Reactivado ('A').")
                                st.rerun()

    # =========================================================================
    # SECCIÓN 2: FORMULARIO DE ENTREVISTA DE CONSEJERÍA
    # =========================================================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Evaluación clínica digital de consumo de sustancias")
        
        pacientes_activos = listar_pacientes_registrados(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos registrados en el sistema. Por favor, vaya primero al módulo **'👤 Registro de Usuarios'** para dar de alta al paciente.")
        else:
            opciones_pac_ent = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
            paciente_sel_str = st.selectbox("🔑 Seleccione el Paciente (Solo Usuarios Activos):", opciones_pac_ent)
            
            paciente_id_input = paciente_sel_str.split(" - ")[0]
            info_reg = obtener_paciente_registro(paciente_id_input)
            
            if info_reg:
                st.info(f"👤 **Paciente Seleccionado:** {info_reg[1]} | **Ingreso:** {info_reg[2]} | **Nacimiento:** {info_reg[3]} | **Sexo:** {info_reg[4]} | **Estatus:** Activo ('A')")
            
            datos_existentes = {}
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if datos_cargados:
                st.success(f"📌 Expediente de Entrevista existente cargado (Registrado el {f_reg} por {u_reg}).")
                datos_existentes = datos_cargados
            else:
                st.info("🆕 Folio sin entrevista previa. Complete los campos para registrar la evaluación.")

            with st.form("formulario_entrevista"):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "1. Datos Generales",
                    "2. Consumo de Sustancias",
                    "3. Disposición al Cambio",
                    "4. Entorno y Riesgos",
                    "5. Observaciones y Firma"
                ])
                
                with tab1:
                    st.subheader("Datos Socio-Demográficos Basales")
                    c1, c2 = st.columns(2)
                    with c1:
                        dependientes_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], 
                                                         index=1 if datos_existentes.get("dependientes_flag") == "SÍ" else 0)
                        dependientes_quienes = st.text_input("¿Quiénes o quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
                    with c2:
                        pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"],
                                                   index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
                        pareja_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo", ""))

                with tab2:
                    st.subheader("Tabla de Consumo de Sustancias")
                    sustancias_lista = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO"]
                    tabla_consumo_guardada = datos_existentes.get("tabla_consumo", {})
                    tabla_consumo_input = {}
                    
                    for sust in sustancias_lista:
                        st.markdown(f"**{sust}**")
                        s_data = tabla_consumo_guardada.get(sust, {})
                        col_a, col_b, col_c, col_d, col_e, col_f = st.columns([1, 1.5, 1.5, 1.5, 1, 1.5])
                        
                        with col_a:
                            c_val = st.checkbox("Consume", value=s_data.get("consumo") == "SÍ", key=f"c_{sust}")
                        with col_b:
                            forma_val = st.text_input("Forma", value=s_data.get("forma", ""), key=f"forma_{sust}")
                        with col_c:
                            frec_val = st.text_input("Frecuencia", value=s_data.get("frecuencia", ""), key=f"frec_{sust}")
                        with col_d:
                            cant_val = st.text_input("Cantidad", value=s_data.get("cantidad", ""), key=f"cant_{sust}")
                        with col_e:
                            edad_val = st.text_input("Edad Inicio", value=s_data.get("edad_inicio", ""), key=f"edad_{sust}")
                        with col_f:
                            lugar_val = st.text_input("Lugar", value=s_data.get("lugar", ""), key=f"lugar_{sust}")
                            
                        tabla_consumo_input[sust] = {
                            "consumo": "SÍ" if c_val else "NO",
                            "forma": forma_val,
                            "frecuencia": frec_val,
                            "cantidad": cant_val,
                            "edad_inicio": edad_val,
                            "lugar": lugar_val
                        }
                        st.divider()

                    st.subheader("Sustancia de Impacto y Patrón")
                    col_imp1, col_imp2, col_imp3 = st.columns(3)
                    with col_imp1:
                        sustancia_impacto = st.text_input("Sustancia de Impacto Principal", value=datos_existentes.get("sustancia_impacto", ""))
                    with col_imp2:
                        tiempo_excesivo = st.text_input("¿Desde hace cuánto consume de forma excesiva?", value=datos_existentes.get("tiempo_excesivo", ""))
                    with col_imp3:
                        modo_consumo = st.selectbox("Normalmente consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"],
                                                   index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo en esa ocasión?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("En los últimos 6 meses, mayor periodo sin consumir", value=datos_existentes.get("abst_6meses", ""))
                    
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Importancia de dejar de consumir:", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar y Riesgos")
                    familia_integrantes = st.text_area("Integrantes de la familia con mayor contacto:", value=datos_existentes.get("familia_integrantes", ""))
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        relaciones_post_consumo = st.selectbox("¿Relaciones sexuales tras consumir?", ["NO", "SÍ"], index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_flag = st.selectbox("¿Abuso físico o sexual por consumo?", ["NO", "SÍ"], index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                with tab5:
                    st.subheader("Observaciones Clínica")
                    problemas_sesion = st.text_area("Problemas durante la sesión:", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales:", value=datos_existentes.get("observaciones", ""))
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica:", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador:", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Entrevista de Consejería", use_container_width=True)
                
                if guardar_btn:
                    datos_completos = {
                        "dependientes_flag": dependientes_flag,
                        "dependientes_quienes": dependientes_quienes,
                        "pareja_flag": pareja_flag,
                        "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input,
                        "sustancia_impacto": sustancia_impacto,
                        "tiempo_excesivo": tiempo_excesivo,
                        "modo_consumo": modo_consumo,
                        "abst_mayor_tiempo": abst_mayor_tiempo,
                        "abst_fecha": abst_fecha,
                        "abst_motivo": abst_motivo,
                        "abst_6meses": abst_6meses,
                        "importancia_cambio": importancia_cambio,
                        "familia_integrantes": familia_integrantes,
                        "relaciones_post_consumo": relaciones_post_consumo,
                        "abuso_flag": abuso_flag,
                        "problemas_sesion": problemas_sesion,
                        "observaciones": observaciones,
                        "evaluador_nombre": evaluador_nombre,
                        "evaluador_cargo": evaluador_cargo
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.success(f"✅ ¡Entrevista para {paciente_sel_str} guardada correctamente!")

    # =========================================================================
    # SECCIÓN 3: CONTROL DE MEDICAMENTOS Y DOSIS
    # =========================================================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosis Diaria")
        st.caption("Asignación de esquemas de dosificación (mañana, tarde, noche) y control de existencias.")
        
        pacientes_activos = listar_pacientes_registrados(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos registrados en el sistema.")
        else:
            opciones_pac_med = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
            paciente_med_sel = st.selectbox("🔑 Seleccione el Paciente (Solo Usuarios Activos):", opciones_pac_med)
            
            paciente_med_id = paciente_med_sel.split(" - ")[0]
            info_reg = obtener_paciente_registro(paciente_med_id)
            if info_reg:
                st.info(f"👤 **Paciente:** {info_reg[1]} | **Ingreso:** {info_reg[2]} | **Nacimiento:** {info_reg[3]} | **Sexo:** {info_reg[4]}")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            if f_mod_m:
                st.success(f"📌 Esquema de medicación cargado. Última modificación: {f_mod_m} por {u_reg_m}")
            
            if "num_meds" not in st.session_state:
                st.session_state["num_meds"] = max(1, len(meds_cargados))
                
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("➕ Agregar otro medicamento"):
                    st.session_state["num_meds"] += 1
                    st.rerun()
            with col_b2:
                if st.session_state["num_meds"] > 1 and st.button("➖ Quitar último medicamento"):
                    st.session_state["num_meds"] -= 1
                    st.rerun()
            
            with st.form("form_medicamentos"):
                lista_meds_input = []
                for idx in range(st.session_state["num_meds"]):
                    m_data = meds_cargados[idx] if idx < len(meds_cargados) else {}
                    st.markdown(f"##### 💊 Medicamento #{idx + 1}")
                    
                    c_m1, c_m2, c_m3, c_m4, c_m5, c_m6 = st.columns([2.5, 1, 1, 1, 1.2, 2.5])
                    with c_m1:
                        m_nombre = st.text_input("Nombre de Medicamento", value=m_data.get("nombre", ""), key=f"m_nom_{idx}")
                    with c_m2:
                        m_man = st.number_input("☀️ Mañana", min_value=0, value=int(m_data.get("dosis_manana", 0)), key=f"m_man_{idx}")
                    with c_m3:
                        m_tar = st.number_input("🌤️ Tarde", min_value=0, value=int(m_data.get("dosis_tarde", 0)), key=f"m_tar_{idx}")
                    with c_m4:
                        m_noc = st.number_input("🌙 Noche", min_value=0, value=int(m_data.get("dosis_noche", 0)), key=f"m_noc_{idx}")
                    with c_m5:
                        m_exist = st.number_input("📦 Existencia", min_value=0, value=int(m_data.get("existencia", 0)), key=f"m_ex_{idx}")
                    with c_m6:
                        m_ind = st.text_input("Indicaciones", value=m_data.get("indicaciones", ""), key=f"m_ind_{idx}")
                    
                    if m_nombre.strip():
                        dosis_dia = m_man + m_tar + m_noc
                        if m_exist < dosis_dia:
                            st.error(f"🔴 **Alerta Crítica:** La existencia actual ({m_exist}) no alcanza para cubrir la dosis del día de mañana ({dosis_dia} dosis/día).")
                        elif m_exist < (dosis_dia * 3):
                            st.warning(f"🟡 **Alerta Preventiva:** Queda medicamento para {m_exist // dosis_dia if dosis_dia > 0 else 0} días.")
                        else:
                            st.caption(f"🟢 Stock suficiente para ~{m_exist // dosis_dia if dosis_dia > 0 else 0} días.")
                    st.divider()
                    
                    if m_nombre.strip():
                        lista_meds_input.append({
                            "nombre": m_nombre.strip(),
                            "dosis_manana": m_man,
                            "dosis_tarde": m_tar,
                            "dosis_noche": m_noc,
                            "existencia": m_exist,
                            "indicaciones": m_ind.strip()
                        })
                
                obs_meds = st.text_area("Observaciones o Contraindicaciones Clínicas:", value=obs_cargadas)
                btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema e Inventario de Medicamentos", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_med_id, lista_meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos e inventario guardados correctamente para {paciente_med_sel}!")

            if meds_cargados:
                pdf_med = generar_pdf_medicamentos(paciente_med_id, meds_cargados, obs_cargadas)
                with open(pdf_med, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Hoja de Medicación (PDF)",
                        data=f,
                        file_name=f"Medicacion_{paciente_med_id}.pdf",
                        mime="application/pdf"
                    )

    # =========================================================================
    # SECCIÓN 4: ALERTAS DE EXISTENCIA Y LISTA DE COMPRAS
    # =========================================================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Control de Alertas de Existencia y Compras")
        st.caption("Consolidado de medicamentos para usuarios activos que requieren reabastecimiento urgente.")
        
        todos_meds = listar_todos_medicamentos(solo_activos=True)
        alertas_criticas = []
        alertas_preventivas = []
        lista_compras_pdf = []
        
        for reg in todos_meds:
            p_id, m_json, obs, f_mod, nom_p, est_p = reg
            meds_list = json.loads(m_json) if m_json else []
            nom_paciente_str = nom_p if nom_p else p_id
            
            for m in meds_list:
                m_nom = m.get("nombre", "")
                m_ex = int(m.get("existencia", 0))
                d_dia = int(m.get("dosis_manana", 0)) + int(m.get("dosis_tarde", 0)) + int(m.get("dosis_noche", 0))
                
                if d_dia > 0:
                    if m_ex < d_dia:
                        item = {
                            "paciente_id": p_id,
                            "nombre_paciente": nom_paciente_str,
                            "medicamento": m_nom,
                            "existencia": m_ex,
                            "dosis_diaria": d_dia,
                            "estado_alerta": "CRÍTICO (<1 día)",
                            "compra_sugerida": (d_dia * 30) - m_ex
                        }
                        alertas_criticas.append(item)
                        lista_compras_pdf.append(item)
                    elif m_ex < (d_dia * 3):
                        item = {
                            "paciente_id": p_id,
                            "nombre_paciente": nom_paciente_str,
                            "medicamento": m_nom,
                            "existencia": m_ex,
                            "dosis_diaria": d_dia,
                            "estado_alerta": "PREVENTIVO (<3 días)",
                            "compra_sugerida": (d_dia * 30) - m_ex
                        }
                        alertas_preventivas.append(item)
                        lista_compras_pdf.append(item)

        m1, m2 = st.columns(2)
        with m1:
            st.metric("🔴 Alertas Críticas (Insuficiente para mañana)", len(alertas_criticas))
        with m2:
            st.metric("🟡 Alertas Preventivas (Menos de 3 días)", len(alertas_preventivas))
            
        st.divider()
        
        if alertas_criticas:
            st.subheader("🔴 Lista Urgente de Pacientes (Sin dosis suficiente para mañana)")
            for ac in alertas_criticas:
                st.error(f"👤 **Paciente:** {ac['nombre_paciente']} ({ac['paciente_id']}) | 💊 **Medicamento:** {ac['medicamento']} | **Existencia:** {ac['existencia']} | **Dosis diaria:** {ac['dosis_diaria']}")

        if alertas_preventivas:
            st.subheader("🟡 Lista Preventiva (Próximos a agotarse en menos de 3 días)")
            for ap in alertas_preventivas:
                st.warning(f"👤 **Paciente:** {ap['nombre_paciente']} ({ap['paciente_id']}) | 💊 **Medicamento:** {ap['medicamento']} | **Existencia:** {ap['existencia']} | **Dosis diaria:** {ap['dosis_diaria']}")

        if not alertas_criticas and not alertas_preventivas:
            st.success("🟢 ¡Todos los pacientes activos cuentan con existencias suficientes de medicamento!")

        if lista_compras_pdf:
            st.divider()
            pdf_compras = generar_pdf_compras(lista_compras_pdf)
            with open(pdf_compras, "rb") as f:
                st.download_button(
                    label="🖨️ Descargar Lista Consolidada de Compras (PDF)",
                    data=f,
                    file_name=f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # =========================================================================
    # SECCIÓN 5: BUSCAR Y LISTAR PACIENTES (HISTORIAL Y PDFS)
    # =========================================================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Expedientes y Registros Clínicos")
        
        filtro_estatus = st.radio("Filtrar Registros por Estatus:", ["Solo Usuarios Activos ('A')", "Todos los Usuarios (Incluyendo Bloqueados)"], horizontal=True)
        solo_act = True if filtro_estatus.startswith("Solo") else False
        
        pacientes_ent = listar_pacientes_entrevista(solo_activos=solo_act)
        
        if not pacientes_ent:
            st.warning("No hay registros de entrevistas coincidentes con el filtro de búsqueda.")
        else:
            st.subheader(f"Total de entrevistas registradas: {len(pacientes_ent)}")
            
            for pac in pacientes_ent:
                p_id, f_reg, f_mod, u_reg, nom_p, est_p = pac
                nombre_p_str = nom_p if nom_p else "Sin Nombre"
                badge_est = "🟢 Activo" if est_p == 'A' else "🔒 BLOQUEADO"
                
                with st.expander(f"👤 **{nombre_p_str}** (Folio: **{p_id}**) | {badge_est} | Modificado: {f_mod}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        p_reg = obtener_paciente_registro(p_id)
                        if p_reg:
                            st.write(f"**Fecha Ingreso:** {p_reg[2]} | **Fecha Nacimiento:** {p_reg[3]} | **Sexo:** {p_reg[4]}")
                        st.write(f"**Fecha de Registro de Entrevista:** {f_reg} por {u_reg}")
                    with c_det2:
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_file = generar_pdf_entrevista(p_id, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{p_id}"
                                )

    # =========================================================================
    # SECCIÓN 6: SEGURIDAD Y CONFIGURACIÓN
    # =========================================================================
    elif menu == "⚙️ Seguridad / Contraseña":
        st.title("⚙️ Configuración de Seguridad")
        st.subheader("Cambiar Contraseña de Usuario")
        
        with st.form("form_cambio_pass"):
            actual_pass = st.text_input("Contraseña Actual", type="password")
            nueva_pass = st.text_input("Nueva Contraseña", type="password")
            confirm_pass = st.text_input("Confirmar Nueva Contraseña", type="password")
            btn_pass = st.form_submit_button("Actualizar Contraseña")
            
            if btn_pass:
                if nueva_pass != confirm_pass:
                    st.error("Las nuevas contraseñas no coinciden.")
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
                    else:
                        st.error("La contraseña actual es incorrecta.")

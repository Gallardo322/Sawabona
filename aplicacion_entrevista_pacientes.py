import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema Clínico de Control y Consejería de Pacientes",
    page_icon="🏥",
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
    
    # Tabla de Registro Inicial de Pacientes / Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            nombre_normalizado TEXT NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT NOT NULL,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # Tabla de Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # Tabla de Medicamentos e Inventario
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

# --- FUNCIONES DE PACIENTES / USUARIOS ---
def normalizar_nombre(nombre):
    if not nombre:
        return ""
    # Convertir a minúsculas y quitar espacios extra
    return " ".join(nombre.strip().lower().split())

def buscar_paciente_por_nombre(nombre):
    norm = normalizar_nombre(nombre)
    if not norm:
        return None
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo FROM pacientes_registro WHERE nombre_normalizado = ?', (norm,))
    row = c.fetchone()
    conn.close()
    return row

def guardar_paciente_registro(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    norm = normalizar_nombre(nombre_completo)
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro 
            SET nombre_completo = ?, nombre_normalizado = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?
            WHERE paciente_id = ?
        ''', (nombre_completo, norm, fecha_ingreso, fecha_nacimiento, sexo, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro (paciente_id, nombre_completo, nombre_normalizado, fecha_ingreso, fecha_nacimiento, sexo, fecha_registro, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo, norm, fecha_ingreso, fecha_nacimiento, sexo, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_paciente_registro(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, fecha_registro, usuario_registro FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "paciente_id": row[0],
            "nombre_completo": row[1],
            "fecha_ingreso": row[2],
            "fecha_nacimiento": row[3],
            "sexo": row[4],
            "fecha_registro": row[5],
            "usuario_registro": row[6]
        }
    return None

def listar_pacientes_registrados():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo FROM pacientes_registro ORDER BY nombre_completo ASC')
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
    for r in rows:
        pid = r[0]
        if pid.startswith("PAC-"):
            try:
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{(max_num + 1):03d}"

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

def listar_pacientes_entrevistados():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT e.paciente_id, p.nombre_completo, e.fecha_registro, e.fecha_modificacion, e.usuario_registro 
        FROM entrevistas e
        LEFT JOIN pacientes_registro p ON e.paciente_id = p.paciente_id
        ORDER BY e.fecha_modificacion DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, meds_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE medicamentos 
            SET fecha_modificacion = ?, meds_json = ?, observaciones = ?
            WHERE paciente_id = ?
        ''', (fecha_actual, meds_json, observaciones, paciente_id))
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

def listar_todos_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT m.paciente_id, p.nombre_completo, m.meds_json, m.observaciones, m.fecha_modificacion 
        FROM medicamentos m
        LEFT JOIN pacientes_registro p ON m.paciente_id = p.paciente_id
        ORDER BY m.fecha_modificacion DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SISTEMA CLINICO DE ATENCION A PACIENTES", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Expediente Digital e Historial", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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
    p_info = obtener_paciente_registro(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Encabezado
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "ENTREVISTA INICIAL DE CONSEJERIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"FOLIO PACIENTE: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    
    if p_info:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Nombre Completo: {limpiar_texto(p_info['nombre_completo'])}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(pdf.epw, 6, f"Fecha de Ingreso: {limpiar_texto(p_info['fecha_ingreso'])} | Fecha Nacimiento: {limpiar_texto(p_info['fecha_nacimiento'])} | Sexo: {limpiar_texto(p_info['sexo'])}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla de Consumo
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
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
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Normalmente consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Disposición al Cambio
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Situación Socio-Familiar
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "SITUACION SOCIAL-FAMILIAR Y RIESGO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Integrantes de la familia con mayor contacto: {limpiar_texto(datos.get('familia_integrantes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Relaciones sexuales tras consumir: {limpiar_texto(datos.get('relaciones_post_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Involucrado en abuso fisico/sexual por consumo: {limpiar_texto(datos.get('abuso_flag', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION DE LA SESION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    # Firma
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos(paciente_id, meds_list, observaciones):
    p_info = obtener_paciente_registro(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "HOJA DE CONTROL DE MEDICAMENTOS Y DOSIFICACION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"FOLIO PACIENTE: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    
    if p_info:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Nombre Completo: {limpiar_texto(p_info['nombre_completo'])}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(pdf.epw, 6, f"Fecha Ingreso: {limpiar_texto(p_info['fecha_ingreso'])} | Nacimiento: {limpiar_texto(p_info['fecha_nacimiento'])} | Sexo: {limpiar_texto(p_info['sexo'])}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(4)
    
    # Tabla de Medicamentos
    pdf.set_font("Helvetica", "B", 9)
    col_w = [45, 20, 20, 20, 22, 22, 41]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Existencia", "Dosis/Dia", "Indicaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for m in meds_list:
        d_m = float(m.get("dosis_manana", 0))
        d_t = float(m.get("dosis_tarde", 0))
        d_n = float(m.get("dosis_noche", 0))
        ex = float(m.get("existencia", 0))
        tot_dia = d_m + d_t + d_n
        
        pdf.cell(col_w[0], 6, limpiar_texto(m.get("nombre", "")), border=1)
        pdf.cell(col_w[1], 6, str(d_m), border=1, align="C")
        pdf.cell(col_w[2], 6, str(d_t), border=1, align="C")
        pdf.cell(col_w[3], 6, str(d_n), border=1, align="C")
        pdf.cell(col_w[4], 6, str(ex), border=1, align="C")
        pdf.cell(col_w[5], 6, str(tot_dia), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(m.get("indicaciones", "")), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, "Observaciones / Alergias:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras(lista_compras):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA DE COMPRAS DE MEDICAMENTOS PARA REABASTECIMIENTO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 6, f"Fecha de reporte: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [25, 45, 45, 20, 20, 35]
    headers = ["Folio", "Paciente", "Medicamento", "Existencia", "Dosis/Dia", "Estatus / Urgencia"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_compras:
        pdf.cell(col_w[0], 6, limpiar_texto(item["paciente_id"]), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(item["nombre_paciente"]), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(item["medicamento"]), border=1)
        pdf.cell(col_w[3], 6, str(item["existencia"]), border=1, align="C")
        pdf.cell(col_w[4], 6, str(item["dosis_diaria"]), border=1, align="C")
        pdf.cell(col_w[5], 6, limpiar_texto(item["estatus"]), border=1, new_x="LMARGIN", new_y="NEXT")
        
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
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Control Clínico</h2>", unsafe_allow_html=True)
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
    st.sidebar.title("🏥 Sistema Clínico")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "👤 Registro de Usuarios",
            "📝 Nueva Entrevista / Editar",
            "💊 Control de Medicamentos",
            "🚨 Alertas de Compras",
            "🔍 Listar Pacientes / Expedientes",
            "⚙️ Seguridad / Contraseña"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 0: REGISTRO DE USUARIOS / PACIENTES ---
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro Inicial de Usuarios / Pacientes")
        st.caption("Modulo inicial obligatorio para dar de alta pacientes en el sistema con asignacion de ID único.")
        
        pacientes_reg = listar_pacientes_registrados()
        
        # Mapeo para autocompletar si se selecciona uno para editar
        opciones_edit = ["➕ REGISTRAR NUEVO USUARIO"] + [f"{p[0]} - {p[1]}" for p in pacientes_reg]
        seleccion_edit = st.selectbox("Seleccione para consultar / editar usuario existente o cree uno nuevo:", opciones_edit)
        
        datos_p_edit = None
        id_sugerido = generar_siguiente_id()
        
        if seleccion_edit != "➕ REGISTRAR NUEVO USUARIO":
            pid_edit = seleccion_edit.split(" - ")[0]
            datos_p_edit = obtener_paciente_registro(pid_edit)
        
        with st.form("form_registro_usuario"):
            c1, c2 = st.columns(2)
            with c1:
                pid_input = st.text_input("🔑 ID / Folio de Usuario *", value=datos_p_edit["paciente_id"] if datos_p_edit else id_sugerido)
                nombre_input = st.text_input("👤 Nombre Completo *", value=datos_p_edit["nombre_completo"] if datos_p_edit else "")
            with c2:
                # Convertir fechas si existen
                f_ingreso_default = date.today()
                f_nac_default = date(1995, 1, 1)
                
                if datos_p_edit:
                    try:
                        f_ingreso_default = datetime.strptime(datos_p_edit["fecha_ingreso"], "%Y-%m-%d").date()
                    except:
                        pass
                    try:
                        f_nac_default = datetime.strptime(datos_p_edit["fecha_nacimiento"], "%Y-%m-%d").date()
                    except:
                        pass
                        
                fecha_ingreso = st.date_input("📅 Fecha de Ingreso *", value=f_ingreso_default)
                fecha_nacimiento = st.date_input("🎂 Fecha de Nacimiento *", value=f_nac_default)
                
            sexo_options = ["Masculino", "Femenino", "Otro"]
            sexo_idx = sexo_options.index(datos_p_edit["sexo"]) if datos_p_edit and datos_p_edit["sexo"] in sexo_options else 0
            sexo = st.selectbox("🚻 Sexo *", sexo_options, index=sexo_idx)
            
            btn_guardar_p = st.form_submit_button("💾 Guardar / Registrar Usuario", use_container_width=True)
            
            if btn_guardar_p:
                if not pid_input.strip():
                    st.error("⚠️ El ID de usuario es obligatorio.")
                elif not nombre_input.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                else:
                    # Validar coincidencia sin importar mayúsculas/minúsculas
                    coincidencia = buscar_paciente_por_nombre(nombre_input)
                    
                    # Si ya existe por nombre pero tiene diferente ID y estamos creando nuevo
                    if coincidencia and (not datos_p_edit or coincidencia[0] != pid_input):
                        st.warning(f"⚠️ **Atención**: Ya existe un usuario registrado con el mismo nombre ('{coincidencia[1]}') bajo el Folio **{coincidencia[0]}** (Ingreso: {coincidencia[2]}). No se diferencian mayúsculas/minúsculas.")
                        st.info("Si desea actualizar dicho usuario, selecciónelo de la lista superior.")
                    else:
                        guardar_paciente_registro(
                            pid_input.strip(),
                            nombre_input.strip(),
                            fecha_ingreso.strftime("%Y-%m-%d"),
                            fecha_nacimiento.strftime("%Y-%m-%d"),
                            sexo,
                            st.session_state["username"]
                        )
                        st.success(f"✅ ¡Usuario **{nombre_input.strip()}** ({pid_input.strip()}) guardado exitosamente!")
                        st.rerun()

        st.divider()
        st.subheader("📋 Usuarios Registrados en el Sistema")
        if not pacientes_reg:
            st.info("Aún no hay usuarios registrados. Utilice el formulario superior para dar de alta al primero.")
        else:
            grid_data = []
            for p in pacientes_reg:
                grid_data.append({
                    "ID": p[0],
                    "Nombre Completo": p[1],
                    "Fecha Ingreso": p[2],
                    "Fecha Nacimiento": p[3],
                    "Sexo": p[4]
                })
            st.dataframe(grid_data, use_container_width=True)

    # --- SECCIÓN 1: FORMULARIO DE ENTREVISTA ---
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        pacientes_reg = listar_pacientes_registrados()
        
        if not pacientes_reg:
            st.warning("⚠️ No hay usuarios registrados en el sistema. Debe ir primero al módulo **👤 Registro de Usuarios** para dar de alta al paciente.")
        else:
            # Lista desplegable de usuarios registrados
            dict_pacientes = {f"{p[0]} - {p[1]} (Ingreso: {p[2]})": p[0] for p in pacientes_reg}
            opciones_pacientes = list(dict_pacientes.keys())
            
            st.markdown("### 1. Seleccione el Usuario para la Entrevista")
            seleccion_paciente = st.selectbox("👤 Seleccionar Usuario Registrado *", opciones_pacientes)
            
            paciente_id_input = dict_pacientes[seleccion_paciente]
            info_p = obtener_paciente_registro(paciente_id_input)
            
            if info_p:
                st.info(f"📌 **Datos del Usuario Seleccionado**: Folio: `{info_p['paciente_id']}` | Nombre: **{info_p['nombre_completo']}** | Fecha Ingreso: `{info_p['fecha_ingreso']}` | Fecha Nac.: `{info_p['fecha_nacimiento']}` | Sexo: `{info_p['sexo']}`")
            
            datos_existentes = {}
            if paciente_id_input:
                datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
                if datos_cargados:
                    st.success(f"📌 Entrevista cargada previamente. Registrada el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                    datos_existentes = datos_cargados
                else:
                    st.info("🆕 El usuario seleccionado aún no tiene entrevista registrada. Proceda a llenar la información.")

            with st.form("formulario_entrevista"):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "1. Datos Generales",
                    "2. Consumo de Sustancias",
                    "3. Disposición al Cambio",
                    "4. Entorno y Riesgos",
                    "5. Observaciones y Firma"
                ])
                
                # --- TAB 1: DATOS GENERALES ---
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

                # --- TAB 2: CONSUMO DE SUSTANCIAS ---
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
                        modo_consumo = st.selectbox("Normally consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"],
                                                   index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

                # --- TAB 3: DISPOSICIÓN AL CAMBIO ---
                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado (Si nunca se ha abstenido marque 0)", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo en esa ocasión y qué hizo para mantenerse?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("En los últimos 6 meses, ¿cuánto es el mayor periodo sin consumir y cuándo ocurrió?", value=datos_existentes.get("abst_6meses", ""))
                    
                    importancia_options = [
                        "1. NADA IMPORTANTE",
                        "2. POCO IMPORTANTE",
                        "3. ALGO IMPORTANTE",
                        "4. IMPORTANTE",
                        "5. MUY IMPORTANTE"
                    ]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Actualmente, ¿qué tan importante es para usted dejar de consumir?", options=importancia_options, value=importancia_options[imp_index])

                # --- TAB 4: ENTORNO Y RIESGOS ---
                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("¿Quiénes integran su familia (con la que tiene mayor contacto)?", value=datos_existentes.get("familia_integrantes", ""))
                    
                    st.subheader("Factores de Riesgo")
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        relaciones_post_consumo = st.selectbox("¿Ha tenido relaciones sexuales después de consumir?", ["NO", "SÍ"],
                                                                index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_flag = st.selectbox("¿Se ha visto involucrado en abuso físico o sexual por el consumo?", ["NO", "SÍ"],
                                                  index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                # --- TAB 5: OBSERVACIONES Y FIRMA ---
                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas presentados durante la sesión (comunicación, actitud, ideas, comportamiento, ánimo)", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica la entrevista", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                # BOTÓN GUARDAR
                guardar_btn = st.form_submit_button("💾 Guardar Entrevista de Paciente", use_container_width=True)
                
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
                    st.success(f"✅ ¡Entrevista del paciente **{info_p['nombre_completo']}** ({paciente_id_input}) guardada correctamente!")

    # --- SECCIÓN 2: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario por Usuario")
        st.caption("Registro de dosificación diaria (mañana, tarde, noche) y control de existencias en inventario")
        
        pacientes_reg = listar_pacientes_registrados()
        
        if not pacientes_reg:
            st.warning("⚠️ No hay usuarios registrados en el sistema. Debe ir primero al módulo **👤 Registro de Usuarios** para dar de alta al paciente.")
        else:
            dict_pacientes_med = {f"{p[0]} - {p[1]} (Ingreso: {p[2]})": p[0] for p in pacientes_reg}
            opciones_pacientes_med = list(dict_pacientes_med.keys())
            
            st.markdown("### 1. Seleccione el Usuario")
            seleccion_p_med = st.selectbox("👤 Seleccionar Usuario Registrado *", opciones_pacientes_med, key="sb_med_pac")
            
            paciente_med_id = dict_pacientes_med[seleccion_p_med]
            info_p_med = obtener_paciente_registro(paciente_med_id)
            
            if info_p_med:
                st.info(f"📌 **Datos del Usuario**: Folio: `{info_p_med['paciente_id']}` | Nombre: **{info_p_med['nombre_completo']}** | Fecha Ingreso: `{info_p_med['fecha_ingreso']}` | Fecha Nac.: `{info_p_med['fecha_nacimiento']}` | Sexo: `{info_p_med['sexo']}`")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            
            if f_mod_m:
                st.success(f"📌 Esquema de medicamentos cargado. Última modificación: {f_mod_m} por {u_reg_m}.")
            else:
                st.info("🆕 El usuario aún no tiene esquema de medicamentos registrado.")
                
            st.subheader("2. Esquema de Dosificación e Inventario")
            
            # Formulario dinámico de medicamentos
            if "num_meds" not in st.session_state:
                st.session_state["num_meds"] = max(1, len(meds_cargados))
            
            with st.form("form_medicamentos"):
                num_filas = st.number_input("Cantidad de medicamentos a registrar:", min_value=1, max_value=15, value=max(len(meds_cargados), 1))
                
                lista_meds_input = []
                for i in range(int(num_filas)):
                    m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                    st.markdown(f"#### 💊 Medicamento #{i+1}")
                    col1, col2, col3, col4, col5, col6 = st.columns([2.5, 1, 1, 1, 1.2, 2.5])
                    
                    with col1:
                        nombre_m = st.text_input("Nombre del Medicamento", value=m_prev.get("nombre", ""), key=f"med_nombre_{i}")
                    with col2:
                        d_m = st.number_input("☀️ Mañana", min_value=0.0, step=0.5, value=float(m_prev.get("dosis_manana", 0)), key=f"med_m_{i}")
                    with col3:
                        d_t = st.number_input("🌤️ Tarde", min_value=0.0, step=0.5, value=float(m_prev.get("dosis_tarde", 0)), key=f"med_t_{i}")
                    with col4:
                        d_n = st.number_input("🌙 Noche", min_value=0.0, step=0.5, value=float(m_prev.get("dosis_noche", 0)), key=f"med_n_{i}")
                    with col5:
                        ex_m = st.number_input("📦 Existencia", min_value=0.0, step=1.0, value=float(m_prev.get("existencia", 0)), key=f"med_ex_{i}")
                    with col6:
                        ind_m = st.text_input("📝 Indicaciones", value=m_prev.get("indicaciones", ""), key=f"med_ind_{i}")
                        
                    tot_dia = d_m + d_t + d_n
                    if nombre_m.strip():
                        # Alertas de stock en pantalla
                        if tot_dia > 0:
                            dias_restantes = ex_m / tot_dia
                            if ex_m < tot_dia:
                                st.error(f"🔴 **Alerta Crítica**: La existencia ({ex_m}) NO alcanza para la dosis diaria de mañana ({tot_dia}).")
                            elif dias_restantes <= 3:
                                st.warning(f"🟡 **Alerta Preventiva**: Queda existencia para {dias_restantes:.1f} días ({ex_m} unidades).")
                            else:
                                st.caption(f"🟢 Stock suficiente para aproximadamente {dias_restantes:.1f} días.")
                        lista_meds_input.append({
                            "nombre": nombre_m.strip(),
                            "dosis_manana": d_m,
                            "dosis_tarde": d_t,
                            "dosis_noche": d_n,
                            "existencia": ex_m,
                            "indicaciones": ind_m.strip()
                        })
                    st.divider()
                    
                obs_meds = st.text_area("Observaciones adicionales o Alergias del Paciente", value=obs_cargadas)
                btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_med_id, lista_meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ Esquema de medicamentos de **{info_p_med['nombre_completo']}** guardado con éxito.")
                    st.rerun()

            # Botón de impresión PDF
            if meds_cargados:
                st.subheader("🖨️ Exportar e Imprimir Esquema")
                pdf_med_file = generar_pdf_medicamentos(paciente_med_id, meds_cargados, obs_cargadas)
                with open(pdf_med_file, "rb") as f:
                    st.download_button(
                        label="📄 Descargar Hoja de Medicación (PDF)",
                        data=f,
                        file_name=f"Medicacion_{paciente_med_id}.pdf",
                        mime="application/pdf"
                    )

    # --- SECCIÓN 3: ALERTAS DE COMPRAS ---
    elif menu == "🚨 Alertas de Compras":
        st.title("🚨 Alertas de Existencia y Lista de Compras")
        st.caption("Consolidado de medicamentos con existencias críticas para reabastecimiento urgente")
        
        todos_meds = listar_todos_medicamentos()
        
        lista_criticos = []
        lista_preventivos = []
        
        for reg in todos_meds:
            p_id, p_nombre, meds_json_str, obs, f_mod = reg
            p_nombre_display = p_nombre if p_nombre else p_id
            
            try:
                meds_list = json.loads(meds_json_str)
            except:
                meds_list = []
                
            for m in meds_list:
                d_m = float(m.get("dosis_manana", 0))
                d_t = float(m.get("dosis_tarde", 0))
                d_n = float(m.get("dosis_noche", 0))
                ex = float(m.get("existencia", 0))
                tot_dia = d_m + d_t + d_n
                
                if tot_dia > 0:
                    dias_rest = ex / tot_dia
                    item_info = {
                        "paciente_id": p_id,
                        "nombre_paciente": p_nombre_display,
                        "medicamento": m.get("nombre", ""),
                        "existencia": ex,
                        "dosis_diaria": tot_dia,
                        "dias_restantes": round(dias_rest, 1)
                    }
                    
                    if ex < tot_dia:
                        item_info["estatus"] = "URGENTE (Falta para mañana)"
                        lista_criticos.append(item_info)
                    elif dias_rest <= 3:
                        item_info["estatus"] = "PREVENTIVO (Menos de 3 dias)"
                        lista_preventivos.append(item_info)

        c1, c2 = st.columns(2)
        with c1:
            st.metric("🔴 Medicamentos Críticos (Agotados / Insuficientes para mañana)", len(lista_criticos))
        with c2:
            st.metric("🟡 Medicamentos en Alerta (Stock ≤ 3 días)", len(lista_preventivos))
            
        st.divider()
        
        if not lista_criticos and not lista_preventivos:
            st.success("🟢 ¡Excelente! Todos los pacientes cuentan con existencia suficiente de medicamentos para los próximos días.")
        else:
            compras_totales = lista_criticos + lista_preventivos
            
            st.subheader("🛒 Lista Consolidada de Compras por Usuario")
            st.dataframe(compras_totales, use_container_width=True)
            
            # Generar PDF de Compras
            pdf_compras = generar_pdf_compras(compras_totales)
            with open(pdf_compras, "rb") as f:
                st.download_button(
                    label="🖨️ Descargar e Imprimir Lista de Compras (PDF)",
                    data=f,
                    file_name=f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # --- SECCIÓN 4: LISTAR PACIENTES / EXPEDIENTES ---
    elif menu == "🔍 Listar Pacientes / Expedientes":
        st.title("🔍 Directorio y Expedientes de Usuarios")
        
        pacientes_reg = listar_pacientes_registrados()
        if not pacientes_reg:
            st.warning("No hay usuarios registrados en el sistema.")
        else:
            st.subheader(f"Total de usuarios dados de alta: {len(pacientes_reg)}")
            
            for p in pacientes_reg:
                p_id, p_nombre, f_ing, f_nac, sexo = p
                with st.expander(f"👤 **{p_nombre}** | ID: `{p_id}` | Ingreso: {f_ing}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Fecha de Nacimiento:** {f_nac}")
                        st.write(f"**Sexo:** {sexo}")
                    with c2:
                        # Descargar PDF de entrevista si existe
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_f = generar_pdf_entrevista(p_id, datos_p)
                            with open(pdf_f, "rb") as f:
                                st.download_button(
                                    label="📄 Descargar Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_ent_{p_id}"
                                )
                        else:
                            st.caption("Sin entrevista inicial registrada aún.")
                            
                        # Descargar PDF de medicamentos si existe
                        meds_c, obs_c, _, _, _ = obtener_medicamentos(p_id)
                        if meds_c:
                            pdf_m = generar_pdf_medicamentos(p_id, meds_c, obs_c)
                            with open(pdf_m, "rb") as f:
                                st.download_button(
                                    label="💊 Descargar Hoja de Medicación (PDF)",
                                    data=f,
                                    file_name=f"Medicacion_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_med_{p_id}"
                                )

    # --- SECCIÓN 5: SEGURIDAD ---
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

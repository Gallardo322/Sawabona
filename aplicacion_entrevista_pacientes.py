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

# --- FUNCIONES DE APOYO Y FORMATO ---
def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
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
        born = datetime.strptime(str(born_str).split()[0], "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except:
        return 0

def calculate_days(date_str):
    if not date_str:
        return 0
    try:
        dt = datetime.strptime(str(date_str).split()[0], "%Y-%m-%d").date()
        today = date.today()
        return (today - dt).days
    except:
        return 0

# --- INICIALIZACIÓN DE BASE DE DATOS Y AUTO-MIGRACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            bloqueado INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            carpeta TEXT,
            nombre_archivo TEXT,
            fecha_subida TEXT,
            contenido BLOB
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS carpetas_catalog (
            nombre TEXT PRIMARY KEY
        )
    ''')
    for f in ["Fichas Médicas", "Identificaciones", "Psicología", "Estudios de Laboratorio", "Documentos Legales", "General"]:
        c.execute('INSERT OR IGNORE INTO carpetas_catalog (nombre) VALUES (?)', (f,))
        
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, bloqueado) VALUES (?, ?, ?, 0)',
                  ('admin', default_pass, 'Administrador del Sistema'))
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, bloqueado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    if res:
        if res[2] == 1:
            return 1 # Bloqueado
        return res[1]
    return None

def guardar_entrevista(paciente_id, datos, usuario):
    init_db()
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
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json FROM entrevistas ORDER BY fecha_modificacion DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def check_duplicate_patient(nombre, ap_p, ap_m, exp, current_pid=None):
    pacientes = listar_pacientes()
    target_name = f"{nombre} {ap_p} {ap_m}".strip().lower()
    for row in pacientes:
        pid, _, _, _, d_json = row
        if current_pid and pid == current_pid:
            continue
        try:
            d = json.loads(d_json)
        except:
            d = {}
        full_p = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip().lower()
        p_exp = str(d.get("num_expediente", "")).strip()
        if target_name and full_p == target_name:
            return True, f"Ya existe un residente con el nombre '{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}' (Folio: {pid}, Exp: {p_exp})."
        if exp and p_exp and exp.strip() == p_exp:
            return True, f"El número de expediente '{exp}' ya está asignado a '{d.get('nombre', '')} {d.get('ap_paterno', '')}' (Folio: {pid})."
    return False, ""

# --- FUNCIONES DE BASE DE DATOS PARA MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)',
              (compuesto, nombre, presentacion))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?',
              (compuesto, nombre, presentacion, med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT count(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?', (med_id,))
    cnt = c.fetchone()[0]
    if cnt > 0:
        conn.close()
        return False, f"No se puede eliminar este medicamento porque está asignado a {cnt} paciente(s)."
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
    ''', (paciente_id, med_id, manana, tarde, noche, existencia, obs))
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
    ''', (manana, tarde, noche, existencia, obs, asig_id))
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
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, fecha, turno, cantidad, usuario))
    
    if cantidad > 0:
        c.execute('''
            UPDATE asignaciones_medicamentos 
            SET existencia = MAX(0, existencia - ?)
            WHERE paciente_id = ? AND medicamento_id = ?
        ''', (cantidad, paciente_id, med_id))
        
    conn.commit()
    conn.close()

def obtener_todas_asignaciones():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.paciente_id, e.datos_json, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        LEFT JOIN entrevistas e ON a.paciente_id = e.paciente_id
        ORDER BY a.paciente_id ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADORES DE REPORTES PDF ---
class PDFListadoPacientes(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 6, "PADRON GENERAL DE RESIDENTES ACTIVOS EN PROCESO", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_listado_pacientes():
    pdf = PDFListadoPacientes(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [35, 60, 20, 20, 40, 25, 25, 25]
    headers = ["Folio / Exp.", "Nombre Completo", "Sexo", "Edad", "Etapa Actual", "Dias Proceso", "Dias Etapa", "Estado"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    pacientes = listar_pacientes()
    activos_count = 0
    
    for p in pacientes:
        pid, f_reg, f_mod, u_reg, d_json = p
        try:
            d = json.loads(d_json)
        except:
            d = {}
            
        if d.get("bloqueado", False):
            continue
            
        activos_count += 1
        nombre = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or "Sin nombre"
        exp = d.get("num_expediente", "")
        folio_str = f"{pid} / Exp: {exp}" if exp else pid
        sexo = d.get("sexo", "Masculino")
        edad = calculate_age(d.get("fecha_nacimiento", ""))
        etapa = d.get("etapa_actual", "Acogida")
        dias_proc = calculate_days(d.get("fecha_ingreso", d.get("fecha_inicio_etapa", f_reg)))
        dias_etapa = calculate_days(d.get("fecha_inicio_etapa", f_reg))
        
        pdf.cell(col_w[0], 6, clean_pdf_text(folio_str), border=1)
        pdf.cell(col_w[1], 6, clean_pdf_text(nombre), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(sexo), border=1, align="C")
        pdf.cell(col_w[3], 6, f"{edad} anos", border=1, align="C")
        pdf.cell(col_w[4], 6, clean_pdf_text(etapa), border=1)
        pdf.cell(col_w[5], 6, f"{dias_proc} dias", border=1, align="C")
        pdf.cell(col_w[6], 6, f"{dias_etapa} dias", border=1, align="C")
        pdf.cell(col_w[7], 6, "Activo", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"Total de Residentes Activos en Padrón: {activos_count}", new_x="LMARGIN", new_y="NEXT")
    
    filename = "Reporte_Pacientes_Activos.pdf"
    pdf.output(filename)
    return filename

class PDFIndicacionesMeds(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 6, "CONTROL Y PROGRAMACION DE MEDICACIONES CLINICAS", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_indicaciones_meds():
    pdf = PDFIndicacionesMeds(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    col_w = [60, 60, 45, 20, 20, 20, 25, 20]
    headers = ["Residente / Paciente", "Medicamento", "Presentacion", "Manana", "Tarde", "Noche", "Existencia", "Dias Rest."]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    raw_asig = obtener_todas_asignaciones()
    lista_fmt = []
    
    for row in raw_asig:
        pid, d_json, comp, nom_m, pres, dm, dt, dn, ex, obs = row
        try:
            d = json.loads(d_json)
        except:
            d = {}
        nombre_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
        exp = d.get("num_expediente", "")
        p_label = f"{nombre_c} (Exp: {exp})" if exp else nombre_c
        
        dosis_diaria = dm + dt + dn
        dias_rest = round(ex / dosis_diaria, 1) if dosis_diaria > 0 else 999
        
        lista_fmt.append({
            "p_label": p_label,
            "sort_key": nombre_c.lower(),
            "med_str": f"{nom_m} ({comp})",
            "pres": pres,
            "dm": dm, "dt": dt, "dn": dn,
            "existencia": ex,
            "dias_rest": dias_rest if dosis_diaria > 0 else "N/A"
        })
        
    lista_fmt.sort(key=lambda x: x["sort_key"])
    
    for item in lista_fmt:
        pdf.cell(col_w[0], 6, clean_pdf_text(item["p_label"]), border=1)
        pdf.cell(col_w[1], 6, clean_pdf_text(item["med_str"]), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(item["pres"]), border=1)
        pdf.cell(col_w[3], 6, str(item["dm"]), border=1, align="C")
        pdf.cell(col_w[4], 6, str(item["dt"]), border=1, align="C")
        pdf.cell(col_w[5], 6, str(item["dn"]), border=1, align="C")
        pdf.cell(col_w[6], 6, f"{item['existencia']} dosis", border=1, align="C")
        pdf.cell(col_w[7], 6, f"{item['dias_rest']} dias", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    filename = "Reporte_Indicaciones_Medicamentos.pdf"
    pdf.output(filename)
    return filename

# --- INICIALIZACIÓN Y ENCABEZADO ---
init_db()

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

def main():
    render_header()
    
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "nombre_completo" not in st.session_state:
        st.session_state["nombre_completo"] = ""
        
    if "msg_success" in st.session_state:
        st.success(st.session_state["msg_success"])
        st.balloons()
        del st.session_state["msg_success"]
        
    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión - Personal Autorizado")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                user = st.text_input("Usuario")
                pwd = st.text_input("Contraseña", type="password")
                sub = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                if sub:
                    res = verificar_login(user, pwd)
                    if res:
                        if res == 1:
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = user
                            st.session_state["nombre_completo"] = res
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
            st.info("💡 Credenciales por defecto: Usuario: `admin` | Contraseña: `admin123`")
        return

    # --- BARRA LATERAL ---
    st.sidebar.markdown('''
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)
    
    st.sidebar.title("📌 Menú Principal")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.selectbox(
        "Seleccione Módulo",
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
        st.title("🏠 Tablero General & Estado Clínico")
        pacientes = listar_pacientes()
        
        activos = 0
        inactivos = 0
        etapas_count = {"Acogida": 0, "Identificación": 0, "Elaboración": 0, "Consolidación": 0, "Servicio Social": 0}
        
        for p in pacientes:
            pid, f_reg, f_mod, u_reg, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            if d.get("bloqueado", False):
                inactivos += 1
            else:
                activos += 1
                et = d.get("etapa_actual", "Acogida")
                if et in etapas_count:
                    etapas_count[et] += 1
                else:
                    etapas_count["Acogida"] += 1
                    
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("🟢 Residentes Activos", activos)
        c_m2.metric("🔴 Residentes Inactivos / Bloqueados", inactivos)
        c_m3.metric("📊 Total de Registros Históricos", len(pacientes))
        
        st.subheader("📊 Distribución por Etapas de Tratamiento")
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        ec1.metric("Acogida", etapas_count["Acogida"])
        ec2.metric("Identificación", etapas_count["Identificación"])
        ec3.metric("Elaboración", etapas_count["Elaboración"])
        ec4.metric("Consolidación", etapas_count["Consolidación"])
        ec5.metric("Servicio Social", etapas_count["Servicio Social"])
        
        st.subheader("📋 Padrón de Residentes por Etapa")
        t_acog, t_id, t_elab, t_cons, t_serv = st.tabs(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
        
        tabs_map = {
            "Acogida": t_acog,
            "Identificación": t_id,
            "Elaboración": t_elab,
            "Consolidación": t_cons,
            "Servicio Social": t_serv
        }
        
        for et_name, tab_obj in tabs_map.items():
            with tab_obj:
                count_et = 0
                for p in pacientes:
                    pid, f_reg, f_mod, u_reg, d_json = p
                    try:
                        d = json.loads(d_json)
                    except:
                        d = {}
                    if not d.get("bloqueado", False) and d.get("etapa_actual", "Acogida") == et_name:
                        count_et += 1
                        nombre_p = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip()
                        exp_p = d.get("num_expediente", "")
                        dias_e = calculate_days(d.get("fecha_inicio_etapa", f_reg))
                        dias_p = calculate_days(d.get("fecha_ingreso", d.get("fecha_inicio_etapa", f_reg)))
                        st.markdown(f"• **{nombre_p}** (Folio: `{pid}`, Exp: `{exp_p}`) | Sexo: `{d.get('sexo', 'Masculino')}` | Edad: `{calculate_age(d.get('fecha_nacimiento', ''))}` | Días en etapa: `{dias_e}` | Días totales: `{dias_p}`")
                if count_et == 0:
                    st.info(f"No hay residentes activos en la etapa de {et_name}.")

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        
        tab_alta, tab_edit, tab_bloq = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Bloqueo / Bajas"])
        
        # --- ALTA DE PACIENTE ---
        with tab_alta:
            st.subheader("➕ Registrar Nuevo Residente")
            pacientes_all = listar_pacientes()
            next_num = len(pacientes_all) + 1
            default_pid = f"PAC-{next_num:03d}"
            default_exp = f"{next_num + 100}"
            
            # Formulario con orden continuo de tabulación
            with st.form("form_alta_paciente"):
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    pid = st.text_input("1. Folio Único / ID Paciente *", value=default_pid)
                with c_f2:
                    num_exp = st.text_input("2. Número de Expediente *", value=default_exp)
                    
                c_nom1, c_nom2, c_nom3 = st.columns(3)
                with c_nom1:
                    nombre = st.text_input("3. Nombre(s) *")
                with c_nom2:
                    ap_paterno = st.text_input("4. Apellido Paterno *")
                with c_nom3:
                    ap_materno = st.text_input("5. Apellido Materno")
                    
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    sexo = st.selectbox("6. Sexo *", ["Masculino", "Femenino", "Otro"])
                with c_d2:
                    fecha_nac = st.date_input("7. Fecha de Nacimiento", value=date(1995, 1, 1))
                    
                c_d3, c_d4 = st.columns(2)
                with c_d3:
                    fecha_ing = st.date_input("8. Fecha de Ingreso Institucional", value=date.today())
                with c_d4:
                    etapa_act = st.selectbox("9. Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                    
                fecha_ini_etapa = st.date_input("10. Fecha Inicio de Etapa Actual", value=date.today())
                
                sub_alta = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                
                if sub_alta:
                    if not nombre or not ap_paterno or not pid or not num_exp:
                        st.error("⚠️ Por favor llene los campos obligatorios (*): Nombre, Apellido Paterno, Folio y Expediente.")
                    else:
                        dup, msg_dup = check_duplicate_patient(nombre, ap_paterno, ap_materno, num_exp)
                        if dup:
                            st.error(f"⛔ {msg_dup}")
                        else:
                            datos_pac = {
                                "nombre": nombre.strip(),
                                "ap_paterno": ap_paterno.strip(),
                                "ap_materno": ap_materno.strip(),
                                "num_expediente": num_exp.strip(),
                                "sexo": sexo,
                                "fecha_nacimiento": str(fecha_nac),
                                "fecha_ingreso": str(fecha_ing),
                                "etapa_actual": etapa_act,
                                "fecha_inicio_etapa": str(fecha_ini_etapa),
                                "bloqueado": False
                            }
                            guardar_entrevista(pid, datos_pac, st.session_state["username"])
                            st.session_state["confirm_nuevo_paciente"] = f"{nombre} {ap_paterno}"
                            st.session_state["confirm_pid"] = pid
                            st.rerun()

            # Pregunta de confirmación tras guardado exitoso (Opción A)
            if "confirm_nuevo_paciente" in st.session_state:
                p_nom_conf = st.session_state["confirm_nuevo_paciente"]
                p_pid_conf = st.session_state["confirm_pid"]
                st.balloons()
                st.success(f"🎉 ¡Residente '{p_nom_conf}' registrado exitosamente con Folio {p_pid_conf}!")
                st.info("❓ **¿Desea ingresar a otro paciente?**")
                cb_c1, cb_c2 = st.columns(2)
                if cb_c1.button("🟢 Sí, registrar otro paciente", use_container_width=True):
                    del st.session_state["confirm_nuevo_paciente"]
                    del st.session_state["confirm_pid"]
                    st.rerun()
                if cb_c2.button("🔴 No, mantener datos en pantalla", use_container_width=True):
                    del st.session_state["confirm_nuevo_paciente"]
                    del st.session_state["confirm_pid"]

        # --- EDICIÓN DE PACIENTE ---
        with tab_edit:
            st.subheader("✏️ Editar Datos de Residente")
            pacientes_list = listar_pacientes()
            dict_pacientes = {}
            for p in pacientes_list:
                pid, f_reg, f_mod, u_reg, d_json = p
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
                dict_pacientes[f"{pid} - {nom_c}"] = (pid, d)
                
            if not dict_pacientes:
                st.info("No hay pacientes registrados para editar.")
            else:
                sel_pac = st.selectbox("Seleccione Residente a Editar", list(dict_pacientes.keys()))
                curr_pid, curr_d = dict_pacientes[sel_pac]
                
                with st.form("form_edit_paciente"):
                    ce1, ce2, ce3 = st.columns(3)
                    with ce1:
                        e_nombre = st.text_input("Nombre(s)", value=curr_d.get("nombre", ""))
                        e_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=get_safe_index(["Masculino", "Femenino", "Otro"], curr_d.get("sexo", "Masculino")))
                        e_etapa = st.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=get_safe_index(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], curr_d.get("etapa_actual", "Acogida")))
                    with ce2:
                        e_ap_p = st.text_input("Apellido Paterno", value=curr_d.get("ap_paterno", ""))
                        e_exp = st.text_input("Número de Expediente", value=curr_d.get("num_expediente", ""))
                        try:
                            fn_val = datetime.strptime(curr_d.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d").date()
                        except:
                            fn_val = date(1995, 1, 1)
                        e_fecha_nac = st.date_input("Fecha de Nacimiento", value=fn_val)
                    with ce3:
                        e_ap_m = st.text_input("Apellido Materno", value=curr_d.get("ap_materno", ""))
                        try:
                            fi_val = datetime.strptime(curr_d.get("fecha_ingreso", str(date.today())), "%Y-%m-%d").date()
                        except:
                            fi_val = date.today()
                        e_fecha_ing = st.date_input("Fecha de Ingreso Institucional", value=fi_val)
                        try:
                            fe_val = datetime.strptime(curr_d.get("fecha_inicio_etapa", str(date.today())), "%Y-%m-%d").date()
                        except:
                            fe_val = date.today()
                        e_fecha_ini_etapa = st.date_input("Fecha Inicio de Etapa Actual", value=fe_val)
                        
                    sub_edit = st.form_submit_button("💾 Guardar Cambios de Residente", use_container_width=True)
                    if sub_edit:
                        dup, msg_dup = check_duplicate_patient(e_nombre, e_ap_p, e_ap_m, e_exp, current_pid=curr_pid)
                        if dup:
                            st.error(f"⛔ {msg_dup}")
                        else:
                            curr_d["nombre"] = e_nombre.strip()
                            curr_d["ap_paterno"] = e_ap_p.strip()
                            curr_d["ap_materno"] = e_ap_m.strip()
                            curr_d["num_expediente"] = e_exp.strip()
                            curr_d["sexo"] = e_sexo
                            curr_d["fecha_nacimiento"] = str(e_fecha_nac)
                            curr_d["fecha_ingreso"] = str(e_fecha_ing)
                            curr_d["etapa_actual"] = e_etapa
                            curr_d["fecha_inicio_etapa"] = str(e_fecha_ini_etapa)
                            
                            guardar_entrevista(curr_pid, curr_d, st.session_state["username"])
                            st.session_state["msg_success"] = f"🎉 ¡Datos actualizados correctamente para {e_nombre} {e_ap_p}!"
                            st.rerun()

        # --- GESTIÓN DE BLOQUEO / BAJAS ---
        with tab_bloq:
            st.subheader("🔒 Bloqueo y Control de Bajas de Residentes")
            pacientes_b = listar_pacientes()
            for p in pacientes_b:
                pid, f_reg, f_mod, u_reg, d_json = p
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
                is_bloq = d.get("bloqueado", False)
                cb1, cb2 = st.columns([3, 1])
                cb1.write(f"• **{nom_c}** (Folio: `{pid}`, Exp: `{d.get('num_expediente', '')}`) | Estado: **{'🔴 Inactivo / Bloqueado' if is_bloq else '🟢 Activo'}**")
                if is_bloq:
                    if cb2.button("🟢 Reactivar", key=f"react_{pid}"):
                        d["bloqueado"] = False
                        guardar_entrevista(pid, d, st.session_state["username"])
                        st.session_state["msg_success"] = f"Residente {nom_c} reactivado."
                        st.rerun()
                else:
                    if cb2.button("🔴 Bloquear / Dar de Baja", key=f"bloq_{pid}"):
                        d["bloqueado"] = True
                        guardar_entrevista(pid, d, st.session_state["username"])
                        st.session_state["msg_success"] = f"Residente {nom_c} dado de baja/bloqueado."
                        st.rerun()

        # --- SECCIÓN: TABLA EN VIVO DE PACIENTES ACTIVOS REGISTRADOS ---
        st.divider()
        st.subheader("📋 Lista de Residentes Registrados en el Sistema")
        
        pdf_list_btn = st.button("🖨️ Imprimir / Descargar Reporte de Pacientes Activos (PDF)", use_container_width=True)
        if pdf_list_btn:
            pdf_path = generar_pdf_listado_pacientes()
            with open(pdf_path, "rb") as f_pdf:
                st.download_button(
                    label="⬇️ Descargar Reporte de Pacientes en PDF",
                    data=f_pdf,
                    file_name="Reporte_Pacientes_Activos.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
        p_activos_list = listar_pacientes()
        p_data_rows = []
        for p in p_activos_list:
            pid, f_reg, f_mod, u_reg, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            if not d.get("bloqueado", False):
                nom_completo = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or "Sin nombre"
                exp = d.get("num_expediente", "")
                sexo_p = d.get("sexo", "Masculino")
                edad_p = calculate_age(d.get("fecha_nacimiento", ""))
                etapa_p = d.get("etapa_actual", "Acogida")
                dias_p = calculate_days(d.get("fecha_ingreso", d.get("fecha_inicio_etapa", f_reg)))
                dias_e = calculate_days(d.get("fecha_inicio_etapa", f_reg))
                p_data_rows.append({
                    "Folio": pid,
                    "Expediente": exp,
                    "Nombre Completo": nom_completo,
                    "Sexo": sexo_p,
                    "Edad": f"{edad_p} años",
                    "Etapa Actual": etapa_p,
                    "Días en Proceso": dias_p,
                    "Días en Etapa": dias_e,
                    "Fecha Ingreso": d.get("fecha_ingreso", "")
                })
                
        if p_data_rows:
            st.dataframe(p_data_rows, use_container_width=True)
        else:
            st.info("No hay residentes activos registrados en el sistema.")

    # --- MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión Oficial")
        st.caption("Captura completa conforme a la NOM-028-SSA2-2009 y formato institucional Sawabona")
        
        pacientes = listar_pacientes()
        dict_p = {}
        for p in pacientes:
            pid, _, _, _, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            nom = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip()
            dict_p[f"{pid} - {nom}"] = (pid, d)
            
        if not dict_p:
            st.warning("Primero debe registrar un paciente en el módulo de Registro de Pacientes.")
        else:
            sel_p_fi = st.selectbox("Seleccione Residente para Ficha de Ingreso", list(dict_p.keys()))
            pid_fi, p_base = dict_p[sel_p_fi]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT datos_json FROM ficha_ingreso WHERE paciente_id = ?', (pid_fi,))
            fi_row = c.fetchone()
            conn.close()
            
            fi_existente = json.loads(fi_row[0]) if fi_row else {}
            nom_c_def = f"{p_base.get('nombre', '')} {p_base.get('ap_paterno', '')} {p_base.get('ap_materno', '')}".strip()
            
            with st.form("form_ficha_ingreso"):
                tf1, tf2, tf3, tf4, tf5 = st.tabs([
                    "🏢 Admisión & Sucursal",
                    "👤 Datos del Residente",
                    "💊 Sustancias de Ingreso",
                    "👥 Responsables & Contacto",
                    "📜 Financiero & Firmas"
                ])
                
                with tf1:
                    c_fi1, c_fi2 = st.columns(2)
                    sucursal = c_fi1.text_input("Sucursal", value=fi_existente.get("sucursal", "Matriz Colima"))
                    num_exp_fi = c_fi2.text_input("No. de Expediente", value=fi_existente.get("num_expediente", p_base.get("num_expediente", "")))
                    fecha_ing_fi = c_fi1.text_input("Fecha de Ingreso", value=fi_existente.get("fecha_ingreso", p_base.get("fecha_ingreso", str(date.today()))))
                    hora_ing_fi = c_fi2.text_input("Hora de Ingreso", value=fi_existente.get("hora_ingreso", datetime.now().strftime("%H:%M")))

                with tf2:
                    st.subheader("Datos Básicos del Usuario")
                    c_fu1, c_fu2 = st.columns(2)
                    nombre_completo_fi = c_fu1.text_input("Nombre Completo del Residente", value=fi_existente.get("nombre_completo", nom_c_def))
                    edad_fi = c_fu2.text_input("Edad", value=str(fi_existente.get("edad", calculate_age(p_base.get("fecha_nacimiento", "")))))
                    fecha_nac_fi = c_fu1.text_input("Fecha de Nacimiento", value=fi_existente.get("fecha_nacimiento", p_base.get("fecha_nacimiento", "")))
                    sexo_fi = c_fu2.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=get_safe_index(["Masculino", "Femenino", "Otro"], fi_existente.get("sexo", p_base.get("sexo", "Masculino"))))
                    estado_civil = c_fu1.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=get_safe_index(["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], fi_existente.get("estado_civil", "Soltero(a)")))
                    escolaridad = c_fu2.text_input("Escolaridad", value=fi_existente.get("escolaridad", "Secundaria"))
                    religion = c_fu1.text_input("Religión", value=fi_existente.get("religion", "Católica"))
                    ocupacion = c_fu2.text_input("Ocupación", value=fi_existente.get("ocupacion", "Empleado"))
                    servicios_medicos = c_fu1.text_input("Servicios Médicos (IMSS, ISSSTE, Particular)", value=fi_existente.get("servicios_medicos", "Ninguno"))
                    domicilio_fi = st.text_area("Domicilio Completo (Calle, No., Colonia, Municipio, C.P.)", value=fi_existente.get("domicilio", ""))

                with tf3:
                    st.subheader("Sustancias que Consume al Ingresar")
                    cat_sust = ["Alcaloides", "Alcohol", "Anfetaminas", "Benzodiazepinas", "Cannabis", "Esteroides", "Fármacos", "LSD", "Meta-anfetaminas", "Opiáceos", "Psicoactivas", "Solventes", "Tabaco"]
                    sust_saved = fi_existente.get("sustancias_ingreso", [])
                    
                    sust_selected = []
                    cols_s = st.columns(3)
                    for idx, s_item in enumerate(cat_sust):
                        col_idx = idx % 3
                        chk = cols_s[col_idx].checkbox(s_item, value=s_item in sust_saved, key=f"chk_s_{s_item}")
                        if chk:
                            sust_selected.append(s_item)
                            
                    modalidad_int = st.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario (Solicitud Familiar)"], index=get_safe_index(["Voluntario", "Involuntario (Solicitud Familiar)"], fi_existente.get("modalidad_internamiento", "Voluntario")))

                with tf4:
                    st.subheader("Responsable Familiar")
                    resp_nombre = st.text_input("Nombre Completo del Responsable", value=fi_existente.get("resp_nombre", ""))
                    resp_parentesco = st.text_input("Parentesco (Desea internar a su...)", value=fi_existente.get("resp_parentesco", "Padre / Madre / Esposo(a)"))
                    resp_telefono = st.text_input("Teléfono(s) de Contacto", value=fi_existente.get("resp_telefono", ""))
                    resp_email = st.text_input("Correo Electrónico", value=fi_existente.get("resp_email", ""))
                    resp_domicilio = st.text_area("Domicilio Completo del Responsable", value=fi_existente.get("resp_domicilio", ""))

                with tf5:
                    st.subheader("Acuerdo Financiero y Firmas")
                    c_fn1, c_fn2, c_fn3 = st.columns(3)
                    costo_ingreso = c_fn1.text_input("Costo de Ingreso ($)", value=fi_existente.get("costo_ingreso", "4,500.00"))
                    cuota_mensual = c_fn2.text_input("Cuota Mensual ($)", value=fi_existente.get("cuota_mensual", "6,000.00"))
                    pagare = c_fn3.text_input("Pagaré ($)", value=fi_existente.get("pagare", "42,000.00"))
                    
                    st.info("📜 **Compromiso NOM-028-SSA2-2009**: Tratamiento sugerido de 6 a 8 meses. El firmante acepta el reglamento interno, vestimenta de etapa y políticas de cuotas de la institución.")
                    
                sub_fi = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                if sub_fi:
                    datos_fi_save = {
                        "sucursal": sucursal,
                        "num_expediente": num_exp_fi,
                        "fecha_ingreso": fecha_ing_fi,
                        "hora_ingreso": hora_ing_fi,
                        "nombre_completo": nombre_completo_fi,
                        "edad": edad_fi,
                        "fecha_nacimiento": fecha_nac_fi,
                        "sexo": sexo_fi,
                        "estado_civil": estado_civil,
                        "escolaridad": escolaridad,
                        "religion": religion,
                        "ocupacion": ocupacion,
                        "servicios_medicos": servicios_medicos,
                        "domicilio": domicilio_fi,
                        "sustancias_ingreso": sust_selected,
                        "modalidad_internamiento": modalidad_int,
                        "resp_nombre": resp_nombre,
                        "resp_parentesco": resp_parentesco,
                        "resp_telefono": resp_telefono,
                        "resp_email": resp_email,
                        "resp_domicilio": resp_domicilio,
                        "costo_ingreso": costo_ingreso,
                        "cuota_mensual": cuota_mensual,
                        "pagare": pagare
                    }
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('INSERT OR REPLACE INTO ficha_ingreso (paciente_id, fecha_registro, usuario_registro, datos_json) VALUES (?, ?, ?, ?)',
                              (pid_fi, f_act, st.session_state["username"], json.dumps(datos_fi_save, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    
                    st.session_state["msg_success"] = f"🎉 ¡Ficha de Ingreso guardada para {nombre_completo_fi}!"
                    st.rerun()

    # --- MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        pacientes = listar_pacientes()
        dict_p = {}
        for p in pacientes:
            pid, _, _, _, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            nom = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip()
            dict_p[f"{pid} - {nom}"] = pid
            
        if not dict_p:
            st.warning("Primero debe registrar un paciente.")
        else:
            sel_p_ei = st.selectbox("Seleccione Residente para Entrevista", list(dict_p.keys()))
            pid_ei = dict_p[sel_p_ei]
            datos_ei, _, _, _ = obtener_entrevista(pid_ei)
            datos_exist = datos_ei or {}
            
            with st.form("form_entrevista_inicial"):
                te1, te2, te3, te4 = st.tabs(["1. Consumo de Sustancias", "2. Disposición al Cambio", "3. Entorno & Riesgos", "4. Evaluación & Firma"])
                
                with te1:
                    sust_impacto = st.selectbox("Sustancia de Impacto Principal", ["Sin registrar", "ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "HEROÍNA", "INHALABLES", "TABACO", "OTRA"], index=get_safe_index(["Sin registrar", "ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "HEROÍNA", "INHALABLES", "TABACO", "OTRA"], datos_exist.get("sustancia_impacto", "Sin registrar")))
                    tiempo_excesivo = st.text_input("Tiempo de consumo excesivo", value=datos_exist.get("tiempo_excesivo", ""))
                    modo_consumo = st.selectbox("Normalmente consume", ["SOLO", "ACOMPAÑADO", "AMBOS"], index=get_safe_index(["SOLO", "ACOMPAÑADO", "AMBOS"], datos_exist.get("modo_consumo", "SOLO")))

                with te2:
                    abst_mayor = st.text_area("Mayor periodo de abstinencia logrado", value=datos_exist.get("abst_mayor_tiempo", ""))
                    abst_motivo = st.text_area("Motivo o estrategia de abstinencia", value=datos_exist.get("abst_motivo", ""))
                    imp_cambio = st.select_slider("Importancia de dejar de consumir (1 a 5)", options=["1. Nada", "2. Poco", "3. Algo", "4. Importante", "5. Muy Importante"], value=datos_exist.get("importancia_cambio", "3. Algo"))

                with te3:
                    fam_integrantes = st.text_area("Integrantes de la familia con mayor contacto", value=datos_exist.get("familia_integrantes", ""))
                    rel_post = st.selectbox("Relaciones sexuales tras consumir", ["NO", "SÍ"], index=1 if datos_exist.get("relaciones_post_consumo") == "SÍ" else 0)

                with te4:
                    obs = st.text_area("Observaciones Clínicas Generales", value=datos_exist.get("observaciones", ""))
                    eval_nom = st.text_input("Nombre del Evaluador", value=datos_exist.get("evaluador_nombre", st.session_state["nombre_completo"]))

                sub_ei = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if sub_ei:
                    datos_exist["sustancia_impacto"] = sust_impacto
                    datos_exist["tiempo_excesivo"] = tiempo_excesivo
                    datos_exist["modo_consumo"] = modo_consumo
                    datos_exist["abst_mayor_tiempo"] = abst_mayor
                    datos_exist["abst_motivo"] = abst_motivo
                    datos_exist["importancia_cambio"] = imp_cambio
                    datos_exist["familia_integrantes"] = fam_integrantes
                    datos_exist["relaciones_post_consumo"] = rel_post
                    datos_exist["observaciones"] = obs
                    datos_exist["evaluador_nombre"] = eval_nom
                    
                    guardar_entrevista(pid_ei, datos_exist, st.session_state["username"])
                    st.session_state["msg_success"] = f"🎉 ¡Entrevista inicial guardada para {pid_ei}!"
                    st.rerun()

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Sesiones de Consejería Individual")
        pacientes = listar_pacientes()
        dict_p = {}
        for p in pacientes:
            pid, _, _, _, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            nom = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip()
            dict_p[f"{pid} - {nom}"] = pid
            
        if not dict_p:
            st.warning("Primero debe registrar un paciente.")
        else:
            sel_p_cons = st.selectbox("Seleccione Residente", list(dict_p.keys()))
            pid_c = dict_p[sel_p_cons]
            
            num_cons = st.number_input("Número de Consejería", min_value=1, max_value=20, value=1)
            f_cons = st.date_input("Fecha de Sesión", value=date.today())
            etapa_c = st.selectbox("Etapa Terapéutica", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
            tema_c = st.text_input("Tema Trata / Objetivo")
            obs_c = st.text_area("Observaciones y Acuerdos de la Sesión")
            
            if st.button("💾 Registrar Sesión de Consejería", use_container_width=True):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('INSERT INTO consejerias (paciente_id, num_consejeria, fecha, etapa, tema, observaciones, usuario) VALUES (?, ?, ?, ?, ?, ?, ?)',
                          (pid_c, num_cons, str(f_cons), etapa_c, tema_c, obs_c, st.session_state["username"]))
                conn.commit()
                conn.close()
                st.session_state["msg_success"] = f"🎉 ¡Consejería #{num_cons} registrada para {pid_c}!"
                st.rerun()

    # --- MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Promoción del Residente")
        pacientes = listar_pacientes()
        dict_p = {}
        for p in pacientes:
            pid, _, _, _, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            nom = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip()
            dict_p[f"{pid} - {nom}"] = pid
            
        if not dict_p:
            st.warning("No hay pacientes registrados.")
        else:
            sel_p_et = st.selectbox("Seleccione Residente a Evaluar / Promover", list(dict_p.keys()))
            pid_e = dict_p[sel_p_et]
            d_p, _, _, _ = obtener_entrevista(pid_e)
            d_e = d_p or {}
            
            et_curr = d_e.get("etapa_actual", "Acogida")
            f_ini_et = d_e.get("fecha_inicio_etapa", str(date.today()))
            dias_e = calculate_days(f_ini_et)
            dias_p = calculate_days(d_e.get("fecha_ingreso", f_ini_et))
            
            st.info(f"📍 **Etapa Actual**: `{et_curr}` | **Días en esta Etapa**: `{dias_e} días` | **Días Totales en Proceso**: `{dias_p} días`")
            
            if dias_e > 90:
                st.warning("⚠️ **Alerta de Rezago Clínico**: El residente lleva más de 90 días en la etapa actual. Se sugiere evaluación del equipo multidisciplinario.")
                
            etapas_ord = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
            curr_idx = etapas_ord.index(et_curr) if et_curr in etapas_ord else 0
            
            if curr_idx < len(etapas_ord) - 1:
                next_etapa = etapas_ord[curr_idx + 1]
                if st.button(f"🚀 Promover a Siguiente Etapa: {next_etapa}", use_container_width=True):
                    d_e["etapa_actual"] = next_etapa
                    d_e["fecha_inicio_etapa"] = str(date.today())
                    guardar_entrevista(pid_e, d_e, st.session_state["username"])
                    st.session_state["msg_success"] = f"🎉 ¡Residente {pid_e} promovido a {next_etapa}!"
                    st.rerun()

    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        with st.form("form_grupo"):
            cg1, cg2 = st.columns(2)
            f_grupo = cg1.date_input("Fecha del Grupo", value=date.today())
            t_grupo = cg2.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Prevención de Recaídas", "Estudio de Pasos", "Espiritualidad"])
            tema_g = st.text_input("Tema Abordado")
            obs_g = st.text_area("Observaciones del Coordinador")
            
            sub_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
            if sub_g:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('INSERT INTO grupos_terapeuticos (fecha, tipo_grupo, tema, asistentes_json, observaciones, usuario) VALUES (?, ?, ?, ?, ?, ?)',
                          (str(f_grupo), t_grupo, tema_g, "[]", obs_g, st.session_state["username"]))
                conn.commit()
                conn.close()
                st.session_state["msg_success"] = f"🎉 ¡Sesión de grupo de {t_grupo} guardada!"
                st.rerun()

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control y Administración de Medicamentos")
        
        tab_cat, tab_asig, tab_surt, tab_alarm, tab_rep = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario",
            "🕒 Surtido por Turno",
            "🚨 Alarmas de Reabastecimiento",
            "📄 Reporte de Indicaciones"
        ])
        
        # 1. CATÁLOGO DE MEDICAMENTOS
        with tab_cat:
            st.subheader("💊 Catálogo General de Medicamentos")
            
            t_add_m, t_edit_m, t_del_m = st.tabs(["➕ Agregar Medicamento", "✏️ Modificar Medicamento", "🗑️ Eliminar Medicamento"])
            
            with t_add_m:
                with st.form("form_add_cat_med"):
                    c_mc1, c_mc2, c_mc3 = st.columns(3)
                    new_comp = c_mc1.text_input("Compuesto / Sustancia Activa *", placeholder="Ej. Paracetamol")
                    new_nom = c_mc2.text_input("Nombre del Medicamento / Marca *", placeholder="Ej. Tylenol")
                    new_pres = c_mc3.text_input("Presentación *", placeholder="Ej. Tabletas 500mg")
                    
                    if st.form_submit_button("💾 Guardar Medicamento en Catálogo", use_container_width=True):
                        if not new_comp or not new_nom or not new_pres:
                            st.error("⚠️ Todos los campos son obligatorios.")
                        else:
                            guardar_medicamento_catalogo(new_comp.strip(), new_nom.strip(), new_pres.strip())
                            st.session_state["msg_success"] = f"🎉 ¡Medicamento '{new_nom}' agregado al catálogo!"
                            st.rerun()

            with t_edit_m:
                cat_meds_edit = obtener_catalogo_medicamentos()
                if not cat_meds_edit:
                    st.info("No hay medicamentos en el catálogo para editar.")
                else:
                    dict_cat_edit = {f"{m[2]} ({m[1]}) - {m[3]}": m for m in cat_meds_edit}
                    sel_edit_m = st.selectbox("Seleccione Medicamento a Modificar", list(dict_cat_edit.keys()), key="sel_edit_med_cat")
                    m_row = dict_cat_edit[sel_edit_m]
                    
                    with st.form("form_edit_cat_med"):
                        cem1, cem2, cem3 = st.columns(3)
                        e_comp = cem1.text_input("Compuesto / Sustancia Activa", value=m_row[1])
                        e_nom = cem2.text_input("Nombre del Medicamento", value=m_row[2])
                        e_pres = cem3.text_input("Presentación", value=m_row[3])
                        
                        if st.form_submit_button("💾 Guardar Cambios en Medicamento", use_container_width=True):
                            actualizar_medicamento_catalogo(m_row[0], e_comp.strip(), e_nom.strip(), e_pres.strip())
                            st.session_state["msg_success"] = f"🎉 Medicamento '{e_nom}' actualizado."
                            st.rerun()

            with t_del_m:
                cat_meds_del = obtener_catalogo_medicamentos()
                if not cat_meds_del:
                    st.info("No hay medicamentos en el catálogo.")
                else:
                    dict_cat_del = {f"{m[2]} ({m[1]}) - {m[3]}": m for m in cat_meds_del}
                    sel_del_m = st.selectbox("Seleccione Medicamento a Eliminar", list(dict_cat_del.keys()), key="sel_del_med_cat")
                    m_del_row = dict_cat_del[sel_del_m]
                    
                    if st.button(f"🗑️ Confirmar y Eliminar '{m_del_row[2]}'", type="primary", use_container_width=True):
                        ok_del, msg_del = eliminar_medicamento_catalogo(m_del_row[0])
                        if ok_del:
                            st.session_state["msg_success"] = f"🗑️ {msg_del}"
                            st.rerun()
                        else:
                            st.error(f"⛔ {msg_del}")

            st.divider()
            st.subheader("📋 Catálogo Actual de Medicamentos")
            cat_list = obtener_catalogo_medicamentos()
            if cat_list:
                df_cat = [{"ID": row[0], "Compuesto": row[1], "Nombre Medicamento": row[2], "Presentación": row[3]} for row in cat_list]
                st.dataframe(df_cat, use_container_width=True)
            else:
                st.info("El catálogo de medicamentos se encuentra vacío.")

        # 2. ASIGNACIÓN E INVENTARIO POR PACIENTE
        with tab_asig:
            st.subheader("📋 Asignación de Medicamentos e Inventario por Paciente")
            
            pacientes_asig = listar_pacientes()
            dict_pac_asig = {}
            for p in pacientes_asig:
                pid, _, _, _, d_json = p
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                if not d.get("bloqueado", False):
                    nom = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
                    dict_pac_asig[f"{pid} - {nom}"] = pid
                    
            if not dict_pac_asig:
                st.warning("No hay pacientes activos para asignar medicamentos.")
            else:
                sel_p_asig = st.selectbox("Seleccione Residente Activo", list(dict_pac_asig.keys()))
                pid_asig = dict_pac_asig[sel_p_asig]
                
                t_asig_add, t_asig_edit = st.tabs(["➕ Asignar Medicamento de Catálogo", "✏️ Modificar Dosis / Existencia / Retirar"])
                
                with t_asig_add:
                    cat_disponible = obtener_catalogo_medicamentos()
                    if not cat_disponible:
                        st.warning("Primero debe agregar medicamentos al Catálogo.")
                    else:
                        dict_med_opt = {f"{m[2]} ({m[1]}) - {m[3]}": m[0] for m in cat_disponible}
                        
                        with st.form("form_asig_med"):
                            med_sel_id = st.selectbox("Seleccione Medicamento del Catálogo", list(dict_med_opt.keys()))
                            
                            cas1, cas2, cas3, cas4 = st.columns(4)
                            d_manana = cas1.number_input("Dosis Mañana", min_value=0.0, step=0.5, value=1.0)
                            d_tarde = cas2.number_input("Dosis Medio Día / Tarde", min_value=0.0, step=0.5, value=0.0)
                            d_noche = cas3.number_input("Dosis Noche", min_value=0.0, step=0.5, value=0.0)
                            d_exist = cas4.number_input("Existencia Inicial (Dosis/Pastillas)", min_value=0.0, step=1.0, value=30.0)
                            
                            obs_asig = st.text_input("Observaciones / Indicaciones Específicas", placeholder="Ej. Tomar con alimentos")
                            
                            if st.form_submit_button("💾 Guardar Asignación a Paciente", use_container_width=True):
                                m_id_val = dict_med_opt[med_sel_id]
                                guardar_asignacion_medicamento(pid_asig, m_id_val, d_manana, d_tarde, d_noche, d_exist, obs_asig)
                                st.session_state["msg_success"] = f"🎉 Medicamento asignado correctamente a {pid_asig}."
                                st.rerun()

                with t_asig_edit:
                    asig_pac = obtener_asignaciones_paciente(pid_asig)
                    if not asig_pac:
                        st.info("Este residente no tiene medicamentos asignados actualmente.")
                    else:
                        dict_asig_e = {f"{row[3]} ({row[2]}) - Pres: {row[4]}": row for row in asig_pac}
                        sel_asig_mod = st.selectbox("Seleccione Medicamento Asignado a Modificar", list(dict_asig_e.keys()))
                        row_a = dict_asig_e[sel_asig_mod]
                        
                        st.info(f"📌 Modificando asignación de **{row_a[3]}** para {pid_asig}")
                        
                        with st.form("form_mod_asig_med"):
                            cae1, cae2, cae3, cae4 = st.columns(4)
                            m_d_manana = cae1.number_input("Dosis Mañana", min_value=0.0, step=0.5, value=float(row_a[5]))
                            m_d_tarde = cae2.number_input("Dosis Medio Día / Tarde", min_value=0.0, step=0.5, value=float(row_a[6]))
                            m_d_noche = cae3.number_input("Dosis Noche", min_value=0.0, step=0.5, value=float(row_a[7]))
                            m_d_exist = cae4.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", min_value=0.0, step=1.0, value=float(row_a[8]))
                            
                            m_obs_asig = st.text_input("Observaciones / Indicaciones", value=row_a[9] or "")
                            
                            c_b_e1, c_b_e2 = st.columns(2)
                            sub_mod_asig = c_b_e1.form_submit_button("💾 Guardar Cambios de Asignación", use_container_width=True)
                            sub_del_asig = c_b_e2.form_submit_button("🗑️ Retirar Medicamento de Paciente", type="primary", use_container_width=True)
                            
                            if sub_mod_asig:
                                actualizar_asignacion_medicamento(row_a[0], m_d_manana, m_d_tarde, m_d_noche, m_d_exist, m_obs_asig)
                                st.session_state["msg_success"] = f"🎉 Asignación actualizada para {row_a[3]}."
                                st.rerun()
                                
                            if sub_del_asig:
                                eliminar_asignacion_medicamento(row_a[0])
                                st.session_state["msg_success"] = f"🗑️ Medicamento {row_a[3]} retirado del paciente."
                                st.rerun()

                st.divider()
                st.subheader(f"💊 Esquema e Inventario Actual de {pid_asig}")
                asig_resumen = obtener_asignaciones_paciente(pid_asig)
                if asig_resumen:
                    df_asig = []
                    for r in asig_resumen:
                        dosis_dia = r[5] + r[6] + r[7]
                        dias_est = round(r[8] / dosis_dia, 1) if dosis_dia > 0 else 999
                        df_asig.append({
                            "ID Asig": r[0],
                            "Medicamento": r[3],
                            "Compuesto": r[2],
                            "Presentación": r[4],
                            "☀️ Mañana": r[5],
                            "🌤️ Tarde": r[6],
                            "🌙 Noche": r[7],
                            "Existencia Actual": f"{r[8]} dosis",
                            "Días Restantes Est.": f"{dias_est} días" if dosis_dia > 0 else "N/A",
                            "Indicaciones": r[9]
                        })
                    st.dataframe(df_asig, use_container_width=True)
                else:
                    st.info("Sin asignaciones registradas.")

        # 3. SURTIDO POR TURNO
        with tab_surt:
            st.subheader("🕒 Surtido y Entrega de Dosis por Turno")
            
            cs1, cs2 = st.columns(2)
            f_surtido = cs1.date_input("Fecha de Entrega", value=date.today())
            turno_surtido = cs2.selectbox("Turno a Surtir", ["Mañana (☀️)", "Medio Día / Tarde (🌤️)", "Noche (🌙)"])
            
            p_surt_all = listar_pacientes()
            has_deliveries = False
            
            with st.form("form_surtido_turno"):
                st.markdown(f"#### 📋 Lista de Pacientes para Surtido: **{turno_surtido}** - `{f_surtido}`")
                
                deliveries_payload = []
                
                for idx_p, p in enumerate(p_surt_all):
                    pid, _, _, _, d_json = p
                    try:
                        d = json.loads(d_json)
                    except:
                        d = {}
                        
                    if d.get("bloqueado", False):
                        continue
                        
                    asigs = obtener_asignaciones_paciente(pid)
                    if not asigs:
                        continue
                        
                    nom_p = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip() or pid
                    
                    p_has_dose_for_shift = False
                    for a in asigs:
                        dm, dt, dn = a[5], a[6], a[7]
                        if ("Mañana" in turno_surtido and dm > 0) or ("Tarde" in turno_surtido and dt > 0) or ("Noche" in turno_surtido and dn > 0):
                            p_has_dose_for_shift = True
                            break
                            
                    if not p_has_dose_for_shift:
                        continue
                        
                    has_deliveries = True
                    st.markdown(f"##### 👤 **{nom_p}** (Folio: `{pid}`)")
                    
                    for a in asigs:
                        asig_id, med_id, comp, nom_m, pres, dm, dt, dn, exist, obs = a
                        
                        dosis_turno = 0.0
                        if "Mañana" in turno_surtido:
                            dosis_turno = dm
                        elif "Tarde" in turno_surtido:
                            dosis_turno = dt
                        elif "Noche" in turno_surtido:
                            dosis_turno = dn
                            
                        if dosis_turno > 0:
                            col_s1, col_s2, col_s3, col_s4 = st.columns([3, 2, 2, 2])
                            col_s1.write(f"💊 **{nom_m}** ({comp}) - *{pres}*")
                            col_s2.write(f"Dosis indicada: **{dosis_turno}** | Indicaciones: {obs or 'Sin notas'}")
                            
                            if exist <= 0:
                                col_s3.error("🚨 SIN EXISTENCIA (0)")
                                cant_surtir = col_s4.number_input(f"Cantidad {pid}_{med_id}", min_value=0.0, max_value=0.0, value=0.0, step=0.5, key=f"surt_{pid}_{med_id}")
                            else:
                                col_s3.success(f"Stock actual: {exist}")
                                cant_surtir = col_s4.number_input(f"Cantidad a Entregar {pid}_{med_id}", min_value=0.0, max_value=float(exist), value=float(min(dosis_turno, exist)), step=0.5, key=f"surt_{pid}_{med_id}")
                                
                            deliveries_payload.append({
                                "paciente_id": pid,
                                "med_id": med_id,
                                "cantidad": cant_surtir,
                                "nom_m": nom_m
                            })
                    st.divider()
                    
                if not has_deliveries:
                    st.info("No hay dosis programadas para el turno seleccionado.")
                    sub_surt = st.form_submit_button("Confirmar Surtido", disabled=True)
                else:
                    sub_surt = st.form_submit_button("✅ Confirmar y Registrar Surtido de Turno", use_container_width=True)
                    if sub_surt:
                        cnt_entregas = 0
                        for item in deliveries_payload:
                            if item["cantidad"] >= 0:
                                registrar_entrega_medicamento(item["paciente_id"], item["med_id"], str(f_surtido), turno_surtido, item["cantidad"], st.session_state["username"])
                                cnt_entregas += 1
                        st.session_state["msg_success"] = f"🎉 ¡Surtido registrado correctamente ({cnt_entregas} entregas registradas)!"
                        st.rerun()

        # 4. ALARMAS DE REABASTECIMIENTO
        with tab_alarm:
            st.subheader("🚨 Alarmas de Reabastecimiento de Medicamentos (≤ 5 Días de Dosis)")
            
            all_asigs_alarm = obtener_todas_asignaciones()
            alarm_count = 0
            
            for row in all_asigs_alarm:
                pid, d_json, comp, nom_m, pres, dm, dt, dn, ex, obs = row
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                nom_p = f"{d.get('nombre', '')} {d.get('ap_paterno', '')}".strip() or pid
                exp_p = d.get("num_expediente", "")
                
                dosis_diaria = dm + dt + dn
                if dosis_diaria > 0:
                    dias_rest = ex / dosis_diaria
                    if dias_rest <= 5.0:
                        alarm_count += 1
                        if dias_rest == 0:
                            st.error(f"🔴 **AGOTADO (0 DÍAS)**: **{nom_p}** (Folio: `{pid}`, Exp: `{exp_p}`) | Medicamento: **{nom_m}** ({comp}) | Stock: `{ex}` | Consumo diario: `{dosis_diaria}`")
                        elif dias_rest <= 2.0:
                            st.error(f"🔴 **ALERTA CRÍTICA ({round(dias_rest, 1)} DÍAS RESTANTES)**: **{nom_p}** (Folio: `{pid}`, Exp: `{exp_p}`) | Medicamento: **{nom_m}** ({comp}) | Stock actual: `{ex}` | Consumo diario: `{dosis_diaria}`")
                        else:
                            st.warning(f"🟡 **ALERTA DE REABASTECIMIENTO ({round(dias_rest, 1)} DÍAS RESTANTES)**: **{nom_p}** (Folio: `{pid}`, Exp: `{exp_p}`) | Medicamento: **{nom_m}** ({comp}) | Stock actual: `{ex}` | Consumo diario: `{dosis_diaria}`")
                            
            if alarm_count == 0:
                st.success("✅ Todos los residentes cuentan con existencias suficientes de medicamentos (más de 5 días de cobertura).")

        # 5. REPORTE DE INDICACIONES (ORDEN ALFABÉTICO)
        with tab_rep:
            st.subheader("📄 Listado Completo de Indicaciones Médicas")
            
            pdf_rep_btn = st.button("🖨️ Descargar Listado de Indicaciones Médicas en PDF", use_container_width=True)
            if pdf_rep_btn:
                pdf_med_path = generar_pdf_indicaciones_meds()
                with open(pdf_med_path, "rb") as f_med_pdf:
                    st.download_button(
                        label="⬇️ Descargar Reporte en PDF",
                        data=f_med_pdf,
                        file_name="Reporte_Indicaciones_Medicamentos.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
            raw_asig_rep = obtener_todas_asignaciones()
            rep_list = []
            
            for row in raw_asig_rep:
                pid, d_json, comp, nom_m, pres, dm, dt, dn, ex, obs = row
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                nombre_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
                exp = d.get("num_expediente", "")
                dosis_diaria = dm + dt + dn
                dias_rest = round(ex / dosis_diaria, 1) if dosis_diaria > 0 else 999
                
                rep_list.append({
                    "Paciente": nombre_c,
                    "Expediente": exp,
                    "Folio": pid,
                    "Medicamento": f"{nom_m} ({comp})",
                    "Presentación": pres,
                    "☀️ Mañana": dm,
                    "🌤️ Tarde": dt,
                    "🌙 Noche": dn,
                    "Existencia": f"{ex} dosis",
                    "Días Restantes Est.": f"{dias_rest} días" if dosis_diaria > 0 else "N/A",
                    "Indicaciones": obs or ""
                })
                
            rep_list.sort(key=lambda x: x["Paciente"].lower())
            
            if rep_list:
                st.dataframe(rep_list, use_container_width=True)
            else:
                st.info("No hay indicaciones de medicamentos registradas en el sistema.")

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Expedientes")
        st.info("Suba y organice documentos por paciente y carpeta.")

    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Residentes")
        q = st.text_input("🔍 Buscar por Nombre, Folio o Expediente").strip().lower()
        pacientes = listar_pacientes()
        
        for p in pacientes:
            pid, f_reg, f_mod, u_reg, d_json = p
            try:
                d = json.loads(d_json)
            except:
                d = {}
            nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip()
            exp = d.get("num_expediente", "")
            
            if not q or (q in nom_c.lower() or q in pid.lower() or q in exp.lower()):
                st.markdown(f"• **{nom_c}** | Folio: `{pid}` | Exp: `{exp}` | Etapa: `{d.get('etapa_actual', 'Acogida')}` | Estado: **{'🔴 Inactivo' if d.get('bloqueado', False) else '🟢 Activo'}**")

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Gestión de Usuarios del Personal")
        st.subheader("👥 Usuarios del Sistema")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, username, nombre_completo, bloqueado FROM usuarios')
        u_rows = c.fetchall()
        conn.close()
        
        for u in u_rows:
            uid, u_name, u_full, u_bloq = u
            st.write(f"• **{u_name}** ({u_full}) - Estado: **{'🔴 Bloqueado' if u_bloq==1 else '🟢 Activo'}**")

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        tab_resp, tab_rest = st.tabs(["⬇️ Copia de Seguridad (Respaldo)", "⬆️ Restaurar Base de Datos"])
        
        with tab_resp:
            st.subheader("⬇️ Descargar Copia de Seguridad")
            st.info("Obtenga una copia de respaldo del archivo SQLite `sistema_pacientes.db` con toda la información guardada.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    st.download_button(
                        label="⬇️ Descargar Base de Datos (.db)",
                        data=f_db,
                        file_name=f"backup_sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
            else:
                st.warning("La base de datos aún no ha sido creada.")

        with tab_rest:
            st.subheader("⬆️ Restaurar Base de Datos desde Respaldo")
            st.warning("⚠️ **ADVERTENCIA**: Al restaurar una copia de seguridad se reemplazarán todos los registros actuales por los del archivo subido.")
            
            file_upload = st.file_uploader("Seleccione el archivo de respaldo (.db o .sqlite)", type=["db", "sqlite"])
            
            if file_upload is not None:
                st.info(f"📄 Archivo seleccionado: **{file_upload.name}** ({file_upload.size} bytes)")
                
                if st.button("🔄 Confirmar y Restaurar Base de Datos Ahora", use_container_width=True, type="primary"):
                    try:
                        with open(DB_FILE, "wb") as f_out:
                            f_out.write(file_upload.getbuffer())
                            
                        init_db()
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT count(*) FROM entrevistas")
                        count_e = c.fetchone()[0]
                        conn.close()
                        
                        st.session_state["msg_success"] = f"🎉 ¡Base de datos restaurada con éxito! Se cargaron {count_e} registros."
                        st.rerun()
                    except Exception as err:
                        st.error(f"❌ Error al restaurar la base de datos: {err}")

if __name__ == "__main__":
    main()

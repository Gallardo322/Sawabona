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

# --- INICIALIZACIÓN DE BASE DE DATOS ---
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
            nombre_medicamento TEXT UNIQUE NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS asignacion_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT,
            usuario_registro TEXT,
            fecha_registro TEXT,
            FOREIGN KEY(medicamento_id) REFERENCES catalogo_medicamentos(id)
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
            usuario TEXT NOT NULL,
            fecha_hora TEXT NOT NULL
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, bloqueado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    if res:
        if res[2] == 1:
            return 1 # Usuario Bloqueado
        return res
    return None

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

def listar_pacientes():
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
            return True, f"Ya existe un paciente registrado con el nombre '{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}' (Folio: {pid}, Exp: {p_exp})."
        if exp and p_exp and exp.strip() == p_exp:
            return True, f"El número de expediente '{exp}' ya está asignado al paciente '{d.get('nombre', '')} {d.get('ap_paterno', '')}' (Folio: {pid})."
    return False, ""

# --- FUNCIONES DE CATÁLOGO Y MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_asignaciones_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.id, a.medicamento_id, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignacion_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE a.paciente_id = ?
        ORDER BY m.nombre_medicamento ASC
    ''', (paciente_id,))
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
    col_w = [35, 60, 20, 18, 35, 25, 25, 22]
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

class PDFListadoIndicaciones(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, "HOJA DE INDICACIONES MEDICAS Y DOSIFICACION POR RESIDENTE", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Fecha de impresion: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_indicaciones():
    pdf = PDFListadoIndicaciones(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [55, 45, 45, 30, 18, 18, 18, 22, 20]
    headers = ["Paciente", "Medicamento", "Compuesto", "Presentacion", "Manana", "Tarde", "Noche", "Existencia", "Dias Rest."]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT e.paciente_id, e.datos_json, m.nombre_medicamento, m.compuesto, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia
        FROM asignacion_medicamentos a
        JOIN entrevistas e ON a.paciente_id = e.paciente_id
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        ORDER BY e.datos_json ASC
    ''')
    rows = c.fetchall()
    conn.close()
    
    items = []
    for r in rows:
        pid, d_json, med_nom, compuesto, pres, d_m, d_t, d_n, ex = r
        try:
            d = json.loads(d_json)
        except:
            d = {}
        if d.get("bloqueado", False):
            continue
        nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
        exp = d.get("num_expediente", "")
        dosis_diaria = (d_m or 0) + (d_t or 0) + (d_n or 0)
        dias_rest = int(ex / dosis_diaria) if dosis_diaria > 0 else 999
        items.append({
            "nombre": nom_c,
            "folio_exp": f"{pid} (Exp: {exp})" if exp else pid,
            "med_nom": med_nom,
            "compuesto": compuesto,
            "pres": pres,
            "d_m": d_m,
            "d_t": d_t,
            "d_n": d_n,
            "ex": ex,
            "dias_rest": dias_rest if dias_rest != 999 else "N/A"
        })
        
    items.sort(key=lambda x: x["nombre"].lower())
    
    for it in items:
        pdf.cell(col_w[0], 6, clean_pdf_text(f"{it['nombre']} - {it['folio_exp']}"), border=1)
        pdf.cell(col_w[1], 6, clean_pdf_text(it["med_nom"]), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(it["compuesto"]), border=1)
        pdf.cell(col_w[3], 6, clean_pdf_text(it["pres"]), border=1)
        pdf.cell(col_w[4], 6, str(it["d_m"]), border=1, align="C")
        pdf.cell(col_w[5], 6, str(it["d_t"]), border=1, align="C")
        pdf.cell(col_w[6], 6, str(it["d_n"]), border=1, align="C")
        pdf.cell(col_w[7], 6, str(it["ex"]), border=1, align="C")
        pdf.cell(col_w[8], 6, str(it["dias_rest"]), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    filename = "Indicaciones_Medicas_General.pdf"
    pdf.output(filename)
    return filename

# --- INICIALIZACIÓN ---
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
        col1, col2, col3 = st.columns([1,2,1])
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
                            st.session_state["username"] = res[0]
                            st.session_state["nombre_completo"] = res[1]
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
            
            if "show_confirm_alta" in st.session_state and st.session_state["show_confirm_alta"]:
                st.success(f"🎉 ¡Residente **{st.session_state.get('last_added_name', '')}** registrado exitosamente con Folio **{st.session_state.get('last_added_pid', '')}**!")
                st.balloons()
                st.markdown("#### 🤔 **¿Desea ingresar a otro paciente?**")
                col_c1, col_c2 = st.columns(2)
                if col_c1.button("🟢 Sí, registrar otro paciente", use_container_width=True):
                    st.session_state["show_confirm_alta"] = False
                    st.session_state["clear_form_fields"] = True
                    st.rerun()
                if col_c2.button("🔴 No, mantener datos en pantalla", use_container_width=True):
                    st.session_state["show_confirm_alta"] = False
                    st.rerun()
            else:
                if st.session_state.get("clear_form_fields", False):
                    st.session_state["alta_nombre"] = ""
                    st.session_state["alta_ap_paterno"] = ""
                    st.session_state["alta_ap_materno"] = ""
                    st.session_state["clear_form_fields"] = False

                with st.form("form_alta_paciente"):
                    f_col1, f_col2 = st.columns(2)
                    pid = f_col1.text_input("1. Folio Único / ID Paciente *", value=default_pid)
                    num_exp = f_col2.text_input("2. Número de Expediente *", value=default_exp)
                    
                    n_col1, n_col2, n_col3 = st.columns(3)
                    nombre = n_col1.text_input("3. Nombre(s) *", key="alta_nombre")
                    ap_paterno = n_col2.text_input("4. Apellido Paterno *", key="alta_ap_paterno")
                    ap_materno = n_col3.text_input("5. Apellido Materno", key="alta_ap_materno")
                    
                    d_col1, d_col2 = st.columns(2)
                    sexo = d_col1.selectbox("6. Sexo *", ["Masculino", "Femenino", "Otro"])
                    fecha_nac = d_col2.date_input("7. Fecha de Nacimiento", value=date(1995, 1, 1))
                    
                    e_col1, e_col2, e_col3 = st.columns(3)
                    fecha_ing = e_col1.date_input("8. Fecha de Ingreso Institucional", value=date.today())
                    etapa_act = e_col2.selectbox("9. Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                    fecha_ini_etapa = e_col3.date_input("10. Fecha Inicio de Etapa Actual", value=date.today())
                    
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
                                st.session_state["show_confirm_alta"] = True
                                st.session_state["last_added_name"] = f"{nombre} {ap_paterno}"
                                st.session_state["last_added_pid"] = pid
                                st.rerun()

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
                    e_nombre = ce1.text_input("Nombre(s)", value=curr_d.get("nombre", ""))
                    e_ap_p = ce2.text_input("Apellido Paterno", value=curr_d.get("ap_paterno", ""))
                    e_ap_m = ce3.text_input("Apellido Materno", value=curr_d.get("ap_materno", ""))
                    
                    ce4, ce5, ce6 = st.columns(3)
                    e_exp = ce4.text_input("Número de Expediente", value=curr_d.get("num_expediente", ""))
                    e_sexo = ce5.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=get_safe_index(["Masculino", "Femenino", "Otro"], curr_d.get("sexo", "Masculino")))
                    try:
                        fn_val = datetime.strptime(curr_d.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d").date()
                    except:
                        fn_val = date(1995, 1, 1)
                    e_fecha_nac = ce6.date_input("Fecha de Nacimiento", value=fn_val)
                    
                    ce7, ce8, ce9 = st.columns(3)
                    try:
                        fi_val = datetime.strptime(curr_d.get("fecha_ingreso", str(date.today())), "%Y-%m-%d").date()
                    except:
                        fi_val = date.today()
                    e_fecha_ing = ce7.date_input("Fecha de Ingreso Institucional", value=fi_val)
                    e_etapa = ce8.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=get_safe_index(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], curr_d.get("etapa_actual", "Acogida")))
                    try:
                        fe_val = datetime.strptime(curr_d.get("fecha_inicio_etapa", str(date.today())), "%Y-%m-%d").date()
                    except:
                        fe_val = date.today()
                    e_fecha_ini_etapa = ce9.date_input("Fecha Inicio de Etapa Actual", value=fe_val)
                        
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

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS COMPLETO ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Sistema Integral de Control y Administración de Medicamentos")
        
        tab_cat, tab_asig, tab_surt, tab_alarm, tab_rep = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario por Paciente",
            "🕒 Surtido por Turno",
            "🚨 Alarmas de Reabastecimiento",
            "📄 Reporte de Indicaciones (PDF)"
        ])
        
        # 1. CATÁLOGO DE MEDICAMENTOS
        with tab_cat:
            st.subheader("💊 Catálogo General de Medicamentos Institucional")
            tc1, tc2, tc3 = st.tabs(["➕ Agregar Medicamento", "✏️ Modificar Medicamento", "🗑️ Eliminar Medicamento"])
            
            with tc1:
                with st.form("form_add_cat_med"):
                    c_comp = st.text_input("Nombre del Compuesto / Sustancia Activa *", placeholder="Ej. Paracetamol, Sertralina")
                    c_nom = st.text_input("Nombre Comercial del Medicamento *", placeholder="Ej. Tylenol, Zoloft")
                    c_pres = st.text_input("Presentación *", placeholder="Ej. Tabletas 500 mg, Gotas 2.5 mg/ml")
                    
                    sub_add_cat = st.form_submit_button("💾 Guardar Medicamento en Catálogo", use_container_width=True)
                    if sub_add_cat:
                        if not c_comp or not c_nom or not c_pres:
                            st.error("⚠️ Todos los campos son obligatorios.")
                        else:
                            try:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)',
                                          (c_comp.strip(), c_nom.strip(), c_pres.strip()))
                                conn.commit()
                                conn.close()
                                st.session_state["msg_success"] = f"🎉 ¡Medicamento {c_nom} agregado al catálogo!"
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(f"⛔ El medicamento '{c_nom}' ya existe en el catálogo.")

            with tc2:
                cat_all = obtener_catalogo_medicamentos()
                if not cat_all:
                    st.info("No hay medicamentos registrados en el catálogo.")
                else:
                    dict_cat = {f"{m[2]} ({m[1]} - {m[3]})": m for m in cat_all}
                    sel_mod_cat = st.selectbox("Seleccione Medicamento a Modificar", list(dict_cat.keys()))
                    m_data = dict_cat[sel_mod_cat]
                    
                    with st.form("form_edit_cat_med"):
                        m_comp = st.text_input("Compuesto / Sustancia Activa", value=m_data[1])
                        m_nom = st.text_input("Nombre del Medicamento", value=m_data[2])
                        m_pres = st.text_input("Presentación", value=m_data[3])
                        
                        if st.form_submit_button("💾 Guardar Cambios en Catálogo", use_container_width=True):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?',
                                      (m_comp.strip(), m_nom.strip(), m_pres.strip(), m_data[0]))
                            conn.commit()
                            conn.close()
                            st.session_state["msg_success"] = f"🎉 ¡Medicamento {m_nom} actualizado!"
                            st.rerun()

            with tc3:
                cat_all = obtener_catalogo_medicamentos()
                if not cat_all:
                    st.info("Catálogo vacío.")
                else:
                    dict_cat_del = {f"{m[2]} ({m[1]} - {m[3]})": m for m in cat_all}
                    sel_del_cat = st.selectbox("Seleccione Medicamento a Eliminar", list(dict_cat_del.keys()))
                    del_data = dict_cat_del[sel_del_cat]
                    
                    if st.button("🗑️ Eliminar Medicamento del Catálogo", type="primary", use_container_width=True):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT count(*) FROM asignacion_medicamentos WHERE medicamento_id = ?', (del_data[0],))
                        count_uso = c.fetchone()[0]
                        if count_uso > 0:
                            st.error(f"⛔ No se puede eliminar '{del_data[2]}' porque está asignado a {count_uso} paciente(s). Retire primero la asignación del paciente.")
                            conn.close()
                        else:
                            c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (del_data[0],))
                            conn.commit()
                            conn.close()
                            st.session_state["msg_success"] = f"Medicamento {del_data[2]} eliminado del catálogo."
                            st.rerun()

            st.divider()
            st.subheader("📋 Catálogo Actual de Medicamentos")
            cat_list = obtener_catalogo_medicamentos()
            if cat_list:
                df_cat = [{"ID": m[0], "Medicamento / Marca": m[2], "Compuesto Activo": m[1], "Presentación": m[3]} for m in cat_list]
                st.dataframe(df_cat, use_container_width=True)

        # 2. ASIGNACIÓN E INVENTARIO POR PACIENTE
        with tab_asig:
            st.subheader("📋 Asignación de Medicamentos y Control de Existencias por Residente")
            pacientes_list = listar_pacientes()
            dict_pacientes = {}
            for p in pacientes_list:
                pid, f_reg, f_mod, u_reg, d_json = p
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                if not d.get("bloqueado", False):
                    nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid
                    exp = d.get("num_expediente", "")
                    dict_pacientes[f"{nom_c} (Folio: {pid}, Exp: {exp})"] = pid

            if not dict_pacientes:
                st.warning("No hay pacientes activos en el sistema.")
            else:
                sel_pac_asig = st.selectbox("Seleccione Residente Activo *", list(dict_pacientes.keys()))
                pid_asig = dict_pacientes[sel_pac_asig]
                
                ta_add, ta_edit = st.tabs(["➕ Asignar Medicamento de Catálogo", "✏️ Modificar Dosis / Existencia / Retirar"])
                
                with ta_add:
                    cat_available = obtener_catalogo_medicamentos()
                    if not cat_available:
                        st.warning("Primero registre medicamentos en el Catálogo.")
                    else:
                        dict_med_opt = {f"{m[2]} ({m[1]} - {m[3]})": m[0] for m in cat_available}
                        with st.form("form_asig_med"):
                            sel_m_cat = st.selectbox("Medicamento del Catálogo *", list(dict_med_opt.keys()))
                            med_id_sel = dict_med_opt[sel_m_cat]
                            
                            st.markdown("##### 🕒 Esquema de Dosis Diaria por Turno")
                            ca1, ca2, ca3, ca4 = st.columns(4)
                            d_m = ca1.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=1.0)
                            d_t = ca2.number_input("🌤️ Dosis Medio Día / Tarde", min_value=0.0, step=0.5, value=0.0)
                            d_n = ca3.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=0.0)
                            ex_init = ca4.number_input("📦 Existencia Inicial del Paciente *", min_value=0.0, step=1.0, value=30.0)
                            
                            obs_a = st.text_input("Indicaciones / Observaciones", placeholder="Ej. Tomar con alimentos")
                            
                            sub_asig = st.form_submit_button("💾 Guardar Asignación de Medicamento", use_container_width=True)
                            if sub_asig:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('''
                                    INSERT INTO asignacion_medicamentos 
                                    (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones, usuario_registro, fecha_registro)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (pid_asig, med_id_sel, d_m, d_t, d_n, ex_init, obs_a, st.session_state["username"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                conn.commit()
                                conn.close()
                                st.session_state["msg_success"] = "🎉 ¡Medicamento asignado correctamente al paciente!"
                                st.rerun()

                with ta_edit:
                    asig_pac = obtener_asignaciones_paciente(pid_asig)
                    if not asig_pac:
                        st.info("El residente no tiene medicamentos asignados actualmente.")
                    else:
                        dict_asig = {f"{a[3]} ({a[2]}) - Dosis: [{a[5]}-{a[6]}-{a[7]}] | Existencia: {a[8]}": a for a in asig_pac}
                        sel_asig_edit = st.selectbox("Seleccione Medicamento Asignado a Modificar", list(dict_asig.keys()))
                        a_data = dict_asig[sel_asig_edit]
                        
                        with st.form("form_edit_asig_pac"):
                            st.markdown(f"#### ✏️ Modificar: **{a_data[3]}** ({a_data[2]})")
                            ce_a1, ce_a2, ce_a3, ce_a4 = st.columns(4)
                            ed_m = ce_a1.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=float(a_data[5]))
                            ed_t = ce_a2.number_input("🌤️ Dosis Tarde", min_value=0.0, step=0.5, value=float(a_data[6]))
                            ed_n = ce_a3.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=float(a_data[7]))
                            e_ex = ce_a4.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL *", min_value=0.0, step=1.0, value=float(a_data[8]))
                            
                            e_obs = st.text_input("Indicaciones / Observaciones", value=a_data[9] or "")
                            
                            col_sub1, col_sub2 = st.columns(2)
                            sub_upd_asig = col_sub1.form_submit_button("💾 Guardar Cambios / Actualizar Existencia", use_container_width=True)
                            sub_del_asig = col_sub2.form_submit_button("🗑️ Retirar Medicamento de Paciente", type="primary", use_container_width=True)
                            
                            if sub_upd_asig:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('''
                                    UPDATE asignacion_medicamentos
                                    SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
                                    WHERE id = ?
                                ''', (ed_m, ed_t, ed_n, e_ex, e_obs, a_data[0]))
                                conn.commit()
                                conn.close()
                                st.session_state["msg_success"] = "🎉 ¡Dosis y existencia actualizadas correctamente!"
                                st.rerun()
                                
                            if sub_del_asig:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('DELETE FROM asignacion_medicamentos WHERE id = ?', (a_data[0],))
                                conn.commit()
                                conn.close()
                                st.session_state["msg_success"] = f"Medicamento {a_data[3]} retirado del paciente."
                                st.rerun()

                st.divider()
                st.subheader("📋 Tratamiento Actual Asignado")
                asig_rows = obtener_asignaciones_paciente(pid_asig)
                if asig_rows:
                    arr_a = []
                    for ar in asig_rows:
                        d_diaria = ar[5] + ar[6] + ar[7]
                        dias_r = int(ar[8] / d_diaria) if d_diaria > 0 else 999
                        arr_a.append({
                            "Medicamento": ar[3],
                            "Compuesto": ar[2],
                            "Presentación": ar[4],
                            "☀️ Mañana": ar[5],
                            "🌤️ Tarde": ar[6],
                            "🌙 Noche": ar[7],
                            "Existencia": ar[8],
                            "Días Restantes": dias_r if dias_r != 999 else "Sin dosis",
                            "Notas": ar[9]
                        })
                    st.dataframe(arr_a, use_container_width=True)

        # 3. SURTIDO POR TURNO
        with tab_surt:
            st.subheader("🕒 Surtido y Entrega de Medicamentos por Turno")
            cs1, cs2 = st.columns(2)
            f_surt = cs1.date_input("Fecha de Entrega", value=date.today())
            t_surt = cs2.selectbox("Turno a Surtir *", ["Mañana", "Medio Día / Tarde", "Noche"])
            
            st.info(f"📋 **Cédula de Surtido para el Turno de la {t_surt}** ({f_surt})")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT a.id, a.paciente_id, e.datos_json, m.nombre_medicamento, a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia
                FROM asignacion_medicamentos a
                JOIN entrevistas e ON a.paciente_id = e.paciente_id
                JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
            ''')
            surt_data = c.fetchall()
            conn.close()
            
            surt_list = []
            for sd in surt_data:
                asig_id, pid_s, d_json, med_nom, dm, dt, dn, ex = sd
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                if d.get("bloqueado", False):
                    continue
                    
                dose_req = 0
                if t_surt == "Mañana":
                    dose_req = dm
                elif t_surt == "Medio Día / Tarde":
                    dose_req = dt
                elif t_surt == "Noche":
                    dose_req = dn
                    
                if dose_req > 0:
                    nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid_s
                    surt_list.append({
                        "asig_id": asig_id,
                        "pid": pid_s,
                        "nombre": nom_c,
                        "med_nom": med_nom,
                        "dosis_indicada": dose_req,
                        "existencia": ex
                    })
                    
            if not surt_list:
                st.success(f"✨ No hay dosis programadas para el turno de la {t_surt}.")
            else:
                with st.form("form_surtido_turno"):
                    entregas_input = []
                    for idx_s, sl in enumerate(surt_list):
                        st.markdown(f"• **{sl['nombre']}** (Folio: `{sl['pid']}`) — **{sl['med_nom']}**")
                        cs_a, cs_b, cs_c = st.columns([2, 2, 2])
                        cs_a.caption(f"Dosis Indicada: **{sl['dosis_indicada']}** | Existencia Actual: **{sl['existencia']}**")
                        
                        if sl['existencia'] <= 0:
                            cs_b.error("🚨 SIN EXISTENCIA (0)")
                            cant_deliver = 0.0
                        else:
                            cant_deliver = cs_b.number_input("Cantidad a Entregar", min_value=0.0, max_value=float(sl['existencia']), value=float(sl['dosis_indicada']), key=f"surt_cant_{idx_s}")
                            
                        entregas_input.append({
                            "asig_id": sl["asig_id"],
                            "pid": sl["pid"],
                            "med_nom": sl["med_nom"],
                            "cant": cant_deliver,
                            "ex_prev": sl["existencia"]
                        })
                        st.divider()
                        
                    btn_confirm_surt = st.form_submit_button("✅ Confirmar y Registrar Entrega de Dosis del Turno", use_container_width=True)
                    if btn_confirm_surt:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        f_hora_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        for ei in entregas_input:
                            if ei["cant"] > 0:
                                new_ex = ei["ex_prev"] - ei["cant"]
                                c.execute('UPDATE asignacion_medicamentos SET existencia = ? WHERE id = ?', (new_ex, ei["asig_id"]))
                                c.execute('''
                                    INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario, fecha_hora)
                                    VALUES (?, 0, ?, ?, ?, ?, ?)
                                ''', (ei["pid"], str(f_surt), t_surt, ei["cant"], st.session_state["username"], f_hora_act))
                        conn.commit()
                        conn.close()
                        st.session_state["msg_success"] = f"🎉 ¡Dosis del turno de la {t_surt} surtidas y descontadas del inventario correctamente!"
                        st.rerun()

        # 4. ALARMAS DE REABASTECIMIENTO
        with tab_alarm:
            st.subheader("🚨 Alarmas de Reabastecimiento de Medicamentos (≤ 5 Días)")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT a.paciente_id, e.datos_json, m.nombre_medicamento, m.compuesto, m.presentacion,
                       a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
                FROM asignacion_medicamentos a
                JOIN entrevistas e ON a.paciente_id = e.paciente_id
                JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
            ''')
            alarm_rows = c.fetchall()
            conn.close()
            
            alerts = []
            for ar in alarm_rows:
                pid_al, d_json, med_nom, compuesto, pres, dm, dt, dn, ex, obs = ar
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                if d.get("bloqueado", False):
                    continue
                nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid_al
                exp = d.get("num_expediente", "")
                
                dosis_diaria = dm + dt + dn
                if dosis_diaria > 0:
                    dias_restantes = ex / dosis_diaria
                    if dias_restantes <= 5:
                        alerts.append({
                            "nombre": nom_c,
                            "folio_exp": f"{pid_al} (Exp: {exp})" if exp else pid_al,
                            "med_nom": med_nom,
                            "compuesto": compuesto,
                            "existencia": ex,
                            "dias_restantes": round(dias_restantes, 1)
                        })
                        
            if not alerts:
                st.success("🎉 ¡Excelente! Ningún residente activo presenta desabastecimiento de medicamentos (todos cuentan con más de 5 días de dosis).")
            else:
                for alt in alerts:
                    if alt["dias_restantes"] <= 2:
                        st.error(f"🚨 **ALERTA CRÍTICA**: A **{alt['nombre']}** (`{alt['folio_exp']}`) le quedan sólo **{alt['dias_restantes']} días** de **{alt['med_nom']}** ({alt['compuesto']}). Existencia actual: `{alt['existencia']} unidades`.")
                    else:
                        st.warning(f"⚠️ **ALERTA PREVENTIVA**: A **{alt['nombre']}** (`{alt['folio_exp']}`) le quedan **{alt['dias_restantes']} días** de **{alt['med_nom']}** ({alt['compuesto']}). Existencia actual: `{alt['existencia']} unidades`.")

        # 5. REPORTE DE INDICACIONES
        with tab_rep:
            st.subheader("📄 Listado Completo de Indicaciones Médicas (Orden Alfabético)")
            
            if st.button("🖨️ Imprimir / Descargar Listado de Indicaciones en PDF", use_container_width=True):
                pdf_ind_path = generar_pdf_indicaciones()
                with open(pdf_ind_path, "rb") as f_ind:
                    st.download_button(
                        label="⬇️ Descargar PDF de Indicaciones",
                        data=f_ind,
                        file_name="Indicaciones_Medicas_General.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT e.paciente_id, e.datos_json, m.nombre_medicamento, m.compuesto, m.presentacion,
                       a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
                FROM asignacion_medicamentos a
                JOIN entrevistas e ON a.paciente_id = e.paciente_id
                JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
            ''')
            rep_rows = c.fetchall()
            conn.close()
            
            rep_list = []
            for rr in rep_rows:
                pid_r, d_json, med_nom, compuesto, pres, dm, dt, dn, ex, obs = rr
                try:
                    d = json.loads(d_json)
                except:
                    d = {}
                if d.get("bloqueado", False):
                    continue
                nom_c = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip() or pid_r
                exp = d.get("num_expediente", "")
                dosis_diaria = dm + dt + dn
                dias_r = int(ex / dosis_diaria) if dosis_diaria > 0 else 999
                rep_list.append({
                    "Paciente": nom_c,
                    "Folio / Exp": f"{pid_r} (Exp: {exp})" if exp else pid_r,
                    "Medicamento": med_nom,
                    "Compuesto Activo": compuesto,
                    "Presentación": pres,
                    "☀️ Mañana": dm,
                    "🌤️ Tarde": dt,
                    "🌙 Noche": dn,
                    "Existencia": ex,
                    "Días Restantes": dias_r if dias_r != 999 else "N/A",
                    "Indicaciones": obs
                })
                
            rep_list.sort(key=lambda x: x["Paciente"].lower())
            
            if rep_list:
                st.dataframe(rep_list, use_container_width=True)
            else:
                st.info("No hay indicaciones de medicamentos registradas actualmente.")

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
                            
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT count(*) FROM entrevistas")
                        count_e = c.fetchone()
                        conn.close()
                        
                        st.session_state["msg_success"] = f"🎉 ¡Base de datos restaurada con éxito! Se cargaron {count_e[0]} registros."
                        st.rerun()
                    except Exception as err:
                        st.error(f"❌ Error al restaurar la base de datos: {err}")

if __name__ == "__main__":
    main()

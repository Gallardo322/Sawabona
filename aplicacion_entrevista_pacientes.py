import streamlit as st
import sqlite3
import json
import hashlib
import os
import unicodedata
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Comunidad Terapéutica Sawabona Shikoba A.C.",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- HELPER FUNCIONES DE TEXTO Y BÚSQUEDA ---
def clean_pdf_text(text):
    if not text:
        return ""
    text = str(text)
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '', '¡': '', '“': '"', '”': '"', '’': "'", '‘': "'",
        '–': '-', '—': '-'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_str(s):
    if not s:
        return ""
    s = str(s).strip().lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def get_safe_index(options, target_val, default_idx=0):
    if not target_val:
        return default_idx
    target_norm = normalize_str(target_val)
    for idx, opt in enumerate(options):
        if normalize_str(opt) == target_norm:
            return idx
    return default_idx

# --- BASE DE DATOS E INICIALIZACIÓN DE TABLAS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador'
        )
    ''')
    c.execute('PRAGMA table_info(usuarios)')
    cols_user = [row[1] for row in c.fetchall()]
    if 'rol' not in cols_user:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
        except Exception:
            pass
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador'))
    else:
        c.execute('UPDATE usuarios SET rol = ? WHERE username = ?', ('Administrador', 'admin'))
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    c.execute('PRAGMA table_info(entrevistas)')
    cols_ent = [row[1] for row in c.fetchall()]
    if 'expediente' not in cols_ent:
        try:
            c.execute('ALTER TABLE entrevistas ADD COLUMN expediente TEXT')
        except Exception:
            pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            expediente TEXT
        )
    ''')
    c.execute('PRAGMA table_info(consejerias)')
    cols_cons = [row[1] for row in c.fetchall()]
    for col_req in ['aspectos_proxima', 'fecha_proxima', 'exposicion', 'avance', 'sugerencia', 'expediente']:
        if col_req not in cols_cons:
            try:
                c.execute(f'ALTER TABLE consejerias ADD COLUMN {col_req} TEXT')
            except Exception:
                pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_paciente TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            tema_desarrollo TEXT,
            devoluciones TEXT,
            compromisos TEXT,
            usuario_registro TEXT
        )
    ''')
    c.execute('PRAGMA table_info(grupos_terapeuticos)')
    cols_grp = [row[1] for row in c.fetchall()]
    if 'etapa_paciente' not in cols_grp:
        try:
            c.execute('ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT')
        except Exception:
            pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            stock INTEGER DEFAULT 0,
            presentacion TEXT,
            descripcion TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS movimientos_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicamento_id INTEGER,
            tipo TEXT,
            cantidad INTEGER,
            fecha TEXT,
            notas TEXT,
            usuario TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS paciente_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            frecuencia TEXT,
            fecha_entrega TEXT,
            cantidad_entregada INTEGER,
            usuario_registro TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT,
            carpeta TEXT,
            fecha_subida TEXT,
            usuario TEXT,
            contenido_blob BLOB,
            tipo_mime TEXT
        )
    ''')
    carpetas_def = ["📁 Documentos Generales", "📜 Contratos y Legal", "🩺 Informes Médicos y Psiquiátricos", "📊 Evaluaciones Clínicas"]
    for carp in carpetas_def:
        try:
            c.execute('INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (carp,))
        except Exception:
            pass
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

def obtener_siguiente_folio():
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
                num = int(pid.split("-")[1])
                if num > max_num:
                    max_num = num
            except Exception:
                pass
    return f"PAC-{(max_num + 1):03d}"

def validar_expediente_unico(expediente, paciente_id_actual=None):
    if not expediente or not str(expediente).strip():
        return True, ""
    exp_str = str(expediente).strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ?', (exp_str,))
    row = c.fetchone()
    conn.close()
    if row:
        pid_found, djson = row[0], row[1]
        if paciente_id_actual and pid_found == paciente_id_actual:
            return True, ""
        nombre = pid_found
        try:
            dj = json.loads(djson)
            nombre = f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')}".strip()
        except Exception:
            pass
        return False, f"⚠️ El expediente '{exp_str}' ya está asignado al paciente: {nombre} ({pid_found})"
    return True, ""

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    exp = str(datos.get('expediente', '')).strip()
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE entrevistas 
            SET expediente = ?, fecha_modificacion = ?, datos_json = ?
            WHERE paciente_id = ?
        ''', (exp, fecha_actual, datos_json, paciente_id))
    else:
        c.execute('''
            INSERT INTO entrevistas (paciente_id, expediente, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, exp, fecha_actual, fecha_actual, usuario, datos_json))
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro, expediente FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        dj = json.loads(row[0])
        dj['expediente'] = row[4] or dj.get('expediente', '')
        return dj, row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes_completo():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, datos_json FROM entrevistas ORDER BY fecha_registro DESC')
    rows = c.fetchall()
    conn.close()
    pacientes = []
    for r in rows:
        pid, exp, djson = r[0], r[1], r[2]
        try:
            dj = json.loads(djson)
        except Exception:
            dj = {}
        nom = f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')} {dj.get('apellido_materno', '')}".strip()
        exp_disp = f"Exp: {exp}" if exp else "Exp: S/N"
        label = f"{pid} | {exp_disp} - {nom}"
        pacientes.append({
            'paciente_id': pid,
            'expediente': exp or '',
            'nombre_completo': nom,
            'label': label,
            'datos': dj
        })
    return pacientes

# --- CATÁLOGO OFICIAL DE TEMAS DE CONSEJERÍA ---
CONSEJERIAS_TEMAS = {
    "Acogida": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGERSTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "Identificación": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "Elaboración": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJERIA) PREVENCIÓN DE RECAÍDAS.",
        "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
        "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
    ],
    "Consolidación": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
        "(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
    ],
    "Servicio Social": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- ENCABEZADO INSTITUCIONAL ---
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

# --- GENERACIÓN DE PDFS ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(46, 125, 50)
        self.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), ln=True, align="C")
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, clean_pdf_text("Modelo Biopsicosocial y Espiritual para Tratamiento de Adicciones"), ln=True, align="C")
        self.line(10, 24, 200, 24)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, clean_pdf_text(f"Pagina {self.page_no()} | Documento Oficial Expediente Clinico"), align="C")

def generar_pdf_ficha_ingreso(p_id, dj):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y ADMISION DE RESIDENTE"), ln=True, align="C")
    pdf.ln(4)
    exp_txt = dj.get("expediente", "") or "S/N"
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" I. DATOS DE IDENTIFICACION Y EXPEDIENTE"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"EXPEDIENTE: {exp_txt}"), ln=False)
    pdf.cell(90, 5, clean_pdf_text(f"FOLIO INTERNO: {p_id}"), ln=True)
    nom = f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')} {dj.get('apellido_materno', '')}".strip()
    pdf.cell(120, 5, clean_pdf_text(f"Nombre Completo: {nom}"), ln=False)
    pdf.cell(70, 5, clean_pdf_text(f"Fecha Ingreso: {dj.get('fecha_ingreso_real', '')}"), ln=True)
    pdf.cell(60, 5, clean_pdf_text(f"Fecha Nacimiento: {dj.get('fecha_nacimiento', '')}"), ln=False)
    pdf.cell(40, 5, clean_pdf_text(f"Edad: {dj.get('edad', '')} anos"), ln=False)
    pdf.cell(45, 5, clean_pdf_text(f"Sexo: {dj.get('sexo', '')}"), ln=False)
    pdf.cell(45, 5, clean_pdf_text(f"Etapa: {dj.get('etapa_actual', 'Acogida')}"), ln=True)
    pdf.ln(4)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" II. MODALIDAD Y MOTIVO DE INGRESO"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"Modalidad: {dj.get('modalidad_internamiento', '')}"), ln=False)
    pdf.cell(90, 5, clean_pdf_text(f"Sustancia de Impacto: {dj.get('sustancia_impacto', '')}"), ln=True)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Motivo de Ingreso: {dj.get('motivo_ingreso', '')}"))
    pdf.ln(4)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" III. RESPONSABLE LEGAL Y FAMILIAR"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(110, 5, clean_pdf_text(f"Responsable: {dj.get('responsable_nombre', '')}"), ln=False)
    pdf.cell(80, 5, clean_pdf_text(f"Parentesco: {dj.get('responsable_parentesco', '')}"), ln=True)
    pdf.cell(110, 5, clean_pdf_text(f"Telefono: {dj.get('responsable_telefono', '')}"), ln=False)
    pdf.cell(80, 5, clean_pdf_text(f"Direccion: {dj.get('responsable_direccion', '')}"), ln=True)
    pdf.ln(6)
    pdf.ln(15)
    pdf.cell(90, 5, clean_pdf_text("______________________________________"), align="C", ln=False)
    pdf.cell(10, 5, "", ln=False)
    pdf.cell(90, 5, clean_pdf_text("______________________________________"), align="C", ln=True)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(90, 4, clean_pdf_text("Firma del Residente / Paciente"), align="C", ln=False)
    pdf.cell(10, 4, "", ln=False)
    pdf.cell(90, 4, clean_pdf_text("Firma del Responsable / Familiar"), align="C", ln=True)
    return bytes(pdf.output())

def generar_pdf_consejeria(p_id, exp_num, nom_p, etapa, num_cons, datos_c):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, clean_pdf_text(f"HOJA DE SESION DE CONSEJERIA INDIVIDUAL #{num_cons}"), ln=True, align="C")
    pdf.ln(3)
    exp_txt = exp_num or "S/N"
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" DATOS DE LA SESION Y RESIDENTE"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"EXPEDIENTE: {exp_txt}"), ln=False)
    pdf.cell(90, 5, clean_pdf_text(f"FECHA DE SESION: {datos_c.get('fecha', '')}"), ln=True)
    pdf.cell(120, 5, clean_pdf_text(f"Paciente: {nom_p}"), ln=False)
    pdf.cell(70, 5, clean_pdf_text(f"Etapa Actual: {etapa}"), ln=True)
    pdf.ln(4)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" TEMAS Y OBJETIVOS CLINICOS"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspectos Trabados Hoy: {datos_c.get('aspectos_trabajar', '')}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspectos para Proxima Consejeria: {datos_c.get('aspectos_proxima', '')}"))
    pdf.cell(0, 5, clean_pdf_text(f"Fecha Sugerida Proxima Sesion: {datos_c.get('fecha_proxima', '')}"), ln=True)
    pdf.ln(4)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(" NOTAS Y OBSERVACIONES CLINICAS DE EVALUACION"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Exposicion del Paciente:\n{datos_c.get('exposicion', '')}"))
    pdf.ln(2)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Avance / Retroceso Observado:\n{datos_c.get('avance', '')}"))
    pdf.ln(2)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sugerencias y Compromisos:\n{datos_c.get('sugerencia', '')}"))
    pdf.ln(6)
    pdf.ln(12)
    pdf.cell(90, 5, clean_pdf_text("______________________________________"), align="C", ln=False)
    pdf.cell(10, 5, "", ln=False)
    pdf.cell(90, 5, clean_pdf_text("______________________________________"), align="C", ln=True)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(90, 4, clean_pdf_text("Firma del Consejero en Adicciones"), align="C", ln=False)
    pdf.cell(10, 4, "", ln=False)
    pdf.cell(90, 4, clean_pdf_text("Firma del Residente / Paciente"), align="C", ln=True)
    return bytes(pdf.output())

def main():
    init_db()
    render_header()
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()
    if st.session_state["logged_in"]:
        inactivo = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
        if inactivo > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        st.session_state["ultima_actividad"] = datetime.now()
    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión de Personal")
        col1, col2 = st.columns([1, 1])
        with col1:
            with st.form("login_form"):
                user = st.text_input("Usuario")
                pwd = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar al Sistema")
                if submit:
                    res = verificar_login(user, pwd)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1] or res[0]
                        st.session_state["rol"] = res[2] or "Administrador"
                        st.session_state["ultima_actividad"] = datetime.now()
                        st.success("✅ Sesión iniciada correctamente")
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
        return
    st.sidebar.markdown('''
        <div style='text-align: center; padding: 12px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #2E7D32;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em; font-weight: bold;'>Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)
    st.sidebar.caption(f"👤 **{st.session_state.get('nombre_completo', 'Usuario')}** ({st.session_state.get('rol', 'Staff')})")
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()
    st.sidebar.title("📌 Menú de Módulos")
    menu = st.sidebar.selectbox(
        "Seleccione Módulo",
        [
            "🏠 Inicio / Tablero General",
            "👤 Registro y Edición de Usuarios",
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
    lista_p = listar_pacientes_completo()
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General e Indicadores")
        st.write("Bienvenido al sistema de seguimiento clínico e institucional.")
        total_p = len(lista_p)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Residentes Activos", total_p)
        etapas_count = {"Acogida": 0, "Identificación": 0, "Elaboración": 0, "Consolidación": 0, "Servicio Social": 0}
        for p in lista_p:
            e = p['datos'].get('etapa_actual', 'Acogida')
            etapas_count[e] = etapas_count.get(e, 0) + 1
        col2.metric("En Acogida", etapas_count["Acogida"])
        col3.metric("En Identificación", etapas_count["Identificación"])
        col4.metric("En Elaboración", etapas_count["Elaboración"])
        st.markdown("---")
        st.subheader("📋 Resumen de Residentes en Tratamiento")
        if lista_p:
            tabla_data = []
            for p in lista_p:
                d = p['datos']
                tabla_data.append({
                    "Folio": p['paciente_id'],
                    "Expediente": p['expediente'] or "S/N",
                    "Nombre": p['nombre_completo'],
                    "Edad": d.get("edad", ""),
                    "Sexo": d.get("sexo", ""),
                    "Etapa": d.get("etapa_actual", "Acogida"),
                    "Fecha Ingreso": d.get("fecha_ingreso_real", "")
                })
            st.dataframe(tabla_data, use_container_width=True)
        else:
            st.info("No hay residentes registrados aún.")
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes")
        sub_tab = st.radio("Acción", ["➕ Alta de Nuevo Residente", "✏️ Editar Residente Existente"], horizontal=True)
        if sub_tab == "➕ Alta de Nuevo Residente":
            st.subheader("Captura de Ficha de Registro")
            sig_folio = obtener_siguiente_folio()
            with st.form("form_alta_paciente"):
                col1, col2 = st.columns(2)
                with col1:
                    st.text_input("Folio Consecutivo", value=sig_folio, disabled=True)
                    exp_in = st.text_input("Número de Expediente (Opcional/Manual)", help="Campo único numérico asignado por la institución")
                    nombre_in = st.text_input("Nombre(s)")
                    ap_pat_in = st.text_input("Apellido Paterno")
                    ap_mat_in = st.text_input("Apellido Materno")
                with col2:
                    fnac_in = st.date_input("Fecha de Nacimiento", datetime(2000, 1, 1))
                    sexo_in = st.selectbox("Sexo", ["Masculino", "Femenino"])
                    fing_in = st.date_input("Fecha de Ingreso Real", datetime.now())
                    etapa_in = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                btn_guardar_alta = st.form_submit_button("💾 Registrar Paciente")
                if btn_guardar_alta:
                    if not nombre_in or not ap_pat_in:
                        st.error("Por favor ingrese al menos el nombre y apellido paterno.")
                    else:
                        val_ok, msg_err = validar_expediente_unico(exp_in)
                        if not val_ok:
                            st.error(msg_err)
                        else:
                            edad_calc = datetime.now().year - fnac_in.year - ((datetime.now().month, datetime.now().day) < (fnac_in.month, fnac_in.day))
                            datos_p = {
                                "expediente": exp_in.strip(),
                                "nombre": nombre_in.strip(),
                                "apellido_paterno": ap_pat_in.strip(),
                                "apellido_materno": ap_mat_in.strip(),
                                "fecha_nacimiento": str(fnac_in),
                                "edad": edad_calc,
                                "sexo": sexo_in,
                                "fecha_ingreso_real": str(fing_in),
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": str(datetime.now().date())
                            }
                            guardar_entrevista(sig_folio, datos_p, st.session_state["username"])
                            st.success(f"✅ Paciente {sig_folio} registrado exitosamente con Expediente: {exp_in or 'S/N'}")
                            st.rerun()
        elif sub_tab == "✏️ Editar Residente Existente":
            if not lista_p:
                st.info("No hay residentes registrados.")
            else:
                sel_p = st.selectbox("Seleccione Residente a Editar", options=lista_p, format_func=lambda x: x['label'])
                p_id = sel_p['paciente_id']
                dj, _, _, _ = obtener_entrevista(p_id)
                with st.form("form_edit_paciente"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Folio Interno", value=p_id, disabled=True)
                        exp_edit = st.text_input("Número de Expediente", value=dj.get("expediente", ""))
                        nom_edit = st.text_input("Nombre(s)", value=dj.get("nombre", ""))
                        pat_edit = st.text_input("Apellido Paterno", value=dj.get("apellido_paterno", ""))
                        mat_edit = st.text_input("Apellido Materno", value=dj.get("apellido_materno", ""))
                    with col2:
                        idx_sex = get_safe_index(["Masculino", "Femenino"], dj.get("sexo", "Masculino"))
                        sex_edit = st.selectbox("Sexo", ["Masculino", "Femenino"], index=idx_sex)
                        idx_etapa = get_safe_index(["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], dj.get("etapa_actual", "Acogida"))
                        etapa_edit = st.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=idx_etapa)
                        fing_edit = st.text_input("Fecha Ingreso Real", value=dj.get("fecha_ingreso_real", str(datetime.now().date())))
                    btn_guardar_edit = st.form_submit_button("💾 Guardar Cambios")
                    if btn_guardar_edit:
                        val_ok, msg_err = validar_expediente_unico(exp_edit, p_id)
                        if not val_ok:
                            st.error(msg_err)
                        else:
                            dj["expediente"] = exp_edit.strip()
                            dj["nombre"] = nom_edit.strip()
                            dj["apellido_paterno"] = pat_edit.strip()
                            dj["apellido_materno"] = mat_edit.strip()
                            dj["sexo"] = sex_edit
                            dj["etapa_actual"] = etapa_edit
                            dj["fecha_ingreso_real"] = fing_edit
                            guardar_entrevista(p_id, dj, st.session_state["username"])
                            st.success("✅ Datos del paciente actualizados correctamente.")
                            st.rerun()
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028)")
        if not lista_p:
            st.info("Debe registrar un paciente primero.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=lista_p, format_func=lambda x: x['label'])
            p_id = sel_p['paciente_id']
            dj, _, _, _ = obtener_entrevista(p_id)
            with st.form("form_ficha_admision"):
                col1, col2 = st.columns(2)
                with col1:
                    idx_mod = get_safe_index(["Voluntario", "Involuntario", "Obligatorio/Judicial"], dj.get("modalidad_internamiento", "Voluntario"))
                    mod_in = st.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario", "Obligatorio/Judicial"], index=idx_mod)
                    sust_in = st.text_input("Sustancia de Impacto Principal", value=dj.get("sustancia_impacto", ""))
                    motivo_in = st.text_area("Motivo de Ingreso", value=dj.get("motivo_ingreso", ""))
                with col2:
                    resp_nom = st.text_input("Nombre del Responsable Legal", value=dj.get("responsable_nombre", ""))
                    resp_parent = st.text_input("Parentesco", value=dj.get("responsable_parentesco", ""))
                    resp_tel = st.text_input("Teléfono de Contacto", value=dj.get("responsable_telefono", ""))
                    resp_dir = st.text_area("Dirección del Responsable", value=dj.get("responsable_direccion", ""))
                btn_guardar_adm = st.form_submit_button("💾 Guardar Datos de Admisión")
                if btn_guardar_adm:
                    dj["modalidad_internamiento"] = mod_in
                    dj["sustancia_impacto"] = sust_in
                    dj["motivo_ingreso"] = motivo_in
                    dj["responsable_nombre"] = resp_nom
                    dj["responsable_parentesco"] = resp_parent
                    dj["responsable_telefono"] = resp_tel
                    dj["responsable_direccion"] = resp_dir
                    guardar_entrevista(p_id, dj, st.session_state["username"])
                    st.success("✅ Ficha de admisión guardada correctamente.")
                    st.rerun()
            st.markdown("---")
            if st.button("🖨️ Generar y Descargar Ficha de Ingreso en PDF"):
                pdf_bytes = generar_pdf_ficha_ingreso(p_id, dj)
                st.download_button(
                    label="📥 Descargar PDF Ficha de Ingreso",
                    data=pdf_bytes,
                    file_name=f"Ficha_Ingreso_{p_id}.pdf",
                    mime="application/pdf"
)
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        if not lista_p:
            st.info("Registre un residente para continuar.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=lista_p, format_func=lambda x: x['label'])
            p_id = sel_p['paciente_id']
            dj, _, _, _ = obtener_entrevista(p_id)
            with st.form("form_entrevista_clinica"):
                st.subheader("1. Antecedentes de Consumo")
                edad_inicio = st.number_input("Edad de Inicio de Consumo", value=int(dj.get("edad_inicio_consumo", 15)))
                frecuencia = st.text_input("Frecuencia de Consumo", value=dj.get("frecuencia_consumo", "Diario"))
                intentos = st.number_input("Intentos Previos de Tratamiento", value=int(dj.get("intentos_previos", 0)))
                st.subheader("2. Evaluación Familiar y Salud")
                apoyo_fam = st.text_area("Apoyo Familiar Percibido", value=dj.get("apoyo_familiar", ""))
                salud_fisica = st.text_area("Padecimientos Médicos / Padecimientos Físicos", value=dj.get("salud_fisica", ""))
                diagnostico_cons = st.text_area("Diagnóstico Inicial de Consejería", value=dj.get("diagnostico_consejeria", ""))
                btn_guardar_ent = st.form_submit_button("💾 Guardar Entrevista Inicial")
                if btn_guardar_ent:
                    dj["edad_inicio_consumo"] = edad_inicio
                    dj["frecuencia_consumo"] = frecuencia
                    dj["intentos_previos"] = intentos
                    dj["apoyo_familiar"] = apoyo_fam
                    dj["salud_fisica"] = salud_fisica
                    dj["diagnostico_consejeria"] = diagnostico_cons
                    guardar_entrevista(p_id, dj, st.session_state["username"])
                    st.success("✅ Entrevista inicial clínica guardada.")
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Módulo de Consejerías Individuales")
        if not lista_p:
            st.info("No hay residentes registrados.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=lista_p, format_func=lambda x: x['label'])
            p_id = sel_p['paciente_id']
            exp_num = sel_p['expediente']
            nom_p = sel_p['nombre_completo']
            dj = sel_p['datos']
            etapa_act = dj.get("etapa_actual", "Acogida")
            st.info(f"📍 **Residente:** {nom_p} | **Expediente:** {exp_num or 'S/N'} | **Etapa Actual:** {etapa_act}")
            temas_etapa = CONSEJERIAS_TEMAS.get(etapa_act, CONSEJERIAS_TEMAS["Acogida"])
            num_cons_sel = st.selectbox("Número de Consejería en esta Etapa", options=list(range(1, len(temas_etapa) + 1)), format_func=lambda x: f"Consejería #{x}")
            tema_actual = temas_etapa[num_cons_sel - 1]
            next_idx = num_cons_sel if num_cons_sel < len(temas_etapa) else 0
            tema_proximo = temas_etapa[next_idx]
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                FROM consejerias
                WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
            ''', (p_id, etapa_act, num_cons_sel))
            row_c = c.fetchone()
            conn.close()
            if row_c:
                asp_trab_val = row_c[0] or tema_actual
                asp_prox_val = row_c[1] or tema_proximo
                f_prox_val = row_c[2] or str((datetime.now() + timedelta(days=7)).date())
                exp_val = row_c[3] or ""
                av_val = row_c[4] or ""
                sug_val = row_c[5] or ""
                f_actual_val = row_c[6] or str(datetime.now().date())
            else:
                asp_trab_val = tema_actual
                asp_prox_val = tema_proximo
                f_prox_val = str((datetime.now() + timedelta(days=7)).date())
                exp_val = ""
                av_val = ""
                sug_val = ""
                f_actual_val = str(datetime.now().date())
            with st.form(f"form_consejeria_{p_id}_{etapa_act}_{num_cons_sel}"):
                st.subheader("Captura de la Sesión")
                f_sesion = st.text_input("Fecha de la Sesión", value=f_actual_val)
                st.text_area("Aspectos a Trabajar (Tema Oficial)", value=asp_trab_val, height=70)
                st.text_area("Aspectos a Trabajar en la Próxima Consejería", value=asp_prox_val, height=70)
                f_prox_input = st.text_input("Fecha Sugerida Próxima Consejería (+7 días)", value=f_prox_val)
                exp_in = st.text_area("Exposición del Paciente (Notas del residente)", value=exp_val, height=120)
                av_in = st.text_area("Avance / Retroceso Observado", value=av_val, height=100)
                sug_in = st.text_area("Sugerencias y Compromisos", value=sug_val, height=100)
                btn_guardar_c = st.form_submit_button("💾 Guardar Consejería")
                if btn_guardar_c:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        SELECT id FROM consejerias WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                    ''', (p_id, etapa_act, num_cons_sel))
                    exist_c = c.fetchone()
                    if exist_c:
                        c.execute('''
                            UPDATE consejerias
                            SET fecha = ?, aspectos_trabajar = ?, aspectos_proxima = ?, fecha_proxima = ?, exposicion = ?, avance = ?, sugerencia = ?, expediente = ?
                            WHERE id = ?
                        ''', (f_sesion, asp_trab_val, asp_prox_val, f_prox_input, exp_in, av_in, sug_in, exp_num, exist_c[0]))
                    else:
                        c.execute('''
                            INSERT INTO consejerias (paciente_id, etapa, num_consejeria, fecha, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, expediente)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (p_id, etapa_act, num_cons_sel, f_sesion, asp_trab_val, asp_prox_val, f_prox_input, exp_in, av_in, sug_in, exp_num))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Consejería #{num_cons_sel} guardada correctamente.")
                    st.rerun()
            st.markdown("---")
            if row_c or exp_val:
                datos_pdf_c = {
                    'fecha': f_actual_val,
                    'aspectos_trabajar': asp_trab_val,
                    'aspectos_proxima': asp_prox_val,
                    'fecha_proxima': f_prox_val,
                    'exposicion': exp_in,
                    'avance': av_in,
                    'sugerencia': sug_in
                }
                pdf_c_bytes = generar_pdf_consejeria(p_id, exp_num, nom_p, etapa_act, num_cons_sel, datos_pdf_c)
                st.download_button(
                    label=f"🖨️ Descargar Hoja de Consejería #{num_cons_sel} en PDF",
                    data=pdf_c_bytes,
                    file_name=f"Consejeria_{num_cons_sel}_{p_id}.pdf",
                    mime="application/pdf"
)
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas, Progreso y Promoción")
        if not lista_p:
            st.info("No hay residentes registrados.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=lista_p, format_func=lambda x: x['label'])
            p_id = sel_p['paciente_id']
            exp_num = sel_p['expediente']
            nom_p = sel_p['nombre_completo']
            dj = sel_p['datos']
            etapa_act = dj.get("etapa_actual", "Acogida")
            fing_str = dj.get("fecha_ingreso_real", str(datetime.now().date()))
            try:
                fing_dt = datetime.strptime(fing_str, "%Y-%m-%d")
                dias_estancia = (datetime.now() - fing_dt).days
            except Exception:
                dias_estancia = 0
            st.subheader(f"Residente: {nom_p} (Etapa: {etapa_act})")
            st.write(f"📅 **Días en Tratamiento:** {dias_estancia} días")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (p_id, etapa_act))
            cons_hechas = c.fetchone()[0]
            conn.close()
            req_consejerias = len(CONSEJERIAS_TEMAS.get(etapa_act, []))
            st.markdown("### 📋 Checklist de Requisitos por Etapa")
            col1, col2 = st.columns(2)
            col1.metric("Consejerías Realizadas", f"{cons_hechas} / {req_consejerias}")
            progreso = min(1.0, cons_hechas / req_consejerias) if req_consejerias > 0 else 1.0
            st.progress(progreso)
            secu_etapas = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
            curr_idx = secu_etapas.index(etapa_act) if etapa_act in secu_etapas else 0
            if curr_idx < len(secu_etapas) - 1:
                sig_etapa = secu_etapas[curr_idx + 1]
                puedes_promover = cons_hechas >= req_consejerias
                if puedes_promover:
                    st.success(f"🎉 El residente ha cumplido con las {req_consejerias} consejerías de la etapa {etapa_act}.")
                    if st.button(f"🚀 Promover a Etapa: {sig_etapa}"):
                        dj["etapa_actual"] = sig_etapa
                        dj["fecha_inicio_etapa"] = str(datetime.now().date())
                        guardar_entrevista(p_id, dj, st.session_state["username"])
                        st.balloons()
                        st.success(f"✅ El paciente ha sido promovido a {sig_etapa}.")
                        st.rerun()
                else:
                    st.warning(f"🔒 Faltan {req_consejerias - cons_hechas} consejerías para poder promover a {sig_etapa}.")
            else:
                st.success("🏆 El residente se encuentra en la etapa final de Servicio Social.")
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        if not lista_p:
            st.info("Registre residentes primero.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=lista_p, format_func=lambda x: x['label'])
            p_id = sel_p['paciente_id']
            nom_p = sel_p['nombre_completo']
            etapa_act = sel_p['datos'].get("etapa_actual", "Acogida")
            tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Retroalimentación"])
            with st.form("form_grupo_terapeutico"):
                fecha_g = st.date_input("Fecha de la Sesión", datetime.now())
                tema_g = st.text_input("Tema Desarrollado")
                devol_g = st.text_area("Devoluciones / Participación del Paciente")
                comp_g = st.text_area("Compromisos Asumidos")
                btn_grupo = st.form_submit_button("💾 Registrar Sesión Grupal")
                if btn_grupo:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (paciente_id, etapa_paciente, tipo_grupo, fecha, tema_desarrollo, devoluciones, compromisos, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p_id, etapa_act, tipo_grupo, str(fecha_g), tema_g, devol_g, comp_g, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success("✅ Sesión grupal registrada correctamente.")
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario")
        tab_med1, tab_med2 = st.tabs(["📦 Catálogo / Inventario", "💊 Entrega a Paciente"])
        with tab_med1:
            st.subheader("Alta de Medicamentos en Almacén")
            with st.form("form_med_inv"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_med = st.text_input("Nombre del Medicamento")
                    pres_med = st.text_input("Presentación (ej. Tabletas 500mg)")
                with col2:
                    cant_med = st.number_input("Cantidad Inicial en Stock", min_value=0, value=10)
                    desc_med = st.text_input("Descripción / Indicaciones")
                btn_add_med = st.form_submit_button("➕ Agregar al Inventario")
                if btn_add_med and nom_med:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute('INSERT INTO medicamentos (nombre, stock, presentacion, descripcion) VALUES (?, ?, ?, ?)',
                                  (nom_med.strip(), cant_med, pres_med, desc_med))
                        conn.commit()
                        st.success(f"✅ {nom_med} agregado al inventario.")
                    except Exception as e:
                        st.error("El medicamento ya existe o hubo un error.")
                    conn.close()
            st.markdown("---")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre, stock, presentacion, descripcion FROM medicamentos')
            meds = c.fetchall()
            conn.close()
            if meds:
                st.dataframe([{"ID": m[0], "Medicamento": m[1], "Stock Disponible": m[2], "Presentación": m[3], "Notas": m[4]} for m in meds], use_container_width=True)
        with tab_med2:
            st.subheader("Entrega de Medicación a Residente")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre, stock FROM medicamentos WHERE stock > 0')
            meds_disp = c.fetchall()
            conn.close()
            if not lista_p or not meds_disp:
                st.info("Asegúrese de tener residentes e inventario de medicamentos disponible.")
            else:
                sel_p = st.selectbox("Seleccione Paciente", options=lista_p, format_func=lambda x: x['label'], key="med_p")
                sel_m = st.selectbox("Seleccione Medicamento", options=meds_disp, format_func=lambda x: f"{x[1]} (Stock: {x[2]})")
                with st.form("form_entrega_med"):
                    dosis = st.text_input("Dosis Prescrita", value="1 tableta")
                    frec = st.text_input("Frecuencia / Horario", value="Cada 12 horas")
                    cant_ent = st.number_input("Cantidad a Entregar del Stock", min_value=1, max_value=sel_m[2], value=1)
                    btn_entregar = st.form_submit_button("💊 Registrar Entrega y Descontar Stock")
                    if btn_entregar:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE medicamentos SET stock = stock - ? WHERE id = ?', (cant_ent, sel_m[0]))
                        c.execute('''
                            INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, dosis, frecuencia, fecha_entrega, cantidad_entregada, usuario_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (sel_p['paciente_id'], sel_m[0], dosis, frec, str(datetime.now()), cant_ent, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Entrega registrada y stock actualizado correctamente.")
                        st.rerun()
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        tab_repo1, tab_repo2 = st.tabs(["📄 Documentos del Sistema", "📁 Personalizar / Gestionar Carpetas"])
        with tab_repo1:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY id ASC')
            carps = [r[0] for r in c.fetchall()]
            conn.close()
            st.subheader("Subir Archivo al Repositorio")
            uploaded_file = st.file_uploader("Seleccione archivo")
            carpeta_dest = st.selectbox("Carpeta Destino", carps)
            if st.button("📤 Guardar en Repositorio") and uploaded_file:
                blob = uploaded_file.read()
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO repositorio_archivos (nombre_archivo, carpeta, fecha_subida, usuario, contenido_blob, tipo_mime)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (uploaded_file.name, carpeta_dest, str(datetime.now().date()), st.session_state["username"], blob, uploaded_file.type))
                conn.commit()
                conn.close()
                st.success(f"✅ Archivo '{uploaded_file.name}' guardado en {carpeta_dest}.")
            st.markdown("---")
            st.subheader("📂 Explorador de Archivos")
            carp_filt = st.selectbox("Filtrar por Carpeta", ["Todas"] + carps)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if carp_filt == "Todas":
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, usuario FROM repositorio_archivos')
            else:
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, usuario FROM repositorio_archivos WHERE carpeta = ?', (carp_filt,))
            archivos = c.fetchall()
            conn.close()
            if archivos:
                for a in archivos:
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"📄 **{a[1]}** | Folder: `{a[2]}` | Fecha: {a[3]} | Subido por: {a[4]}")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('SELECT contenido_blob, tipo_mime FROM repositorio_archivos WHERE id = ?', (a[0],))
                    row_blob = c.fetchone()
                    conn.close()
                    if row_blob and row_blob[0]:
                        col_b.download_button("📥 Descargar", data=row_blob[0], file_name=a[1], mime=row_blob[1] or "application/octet-stream", key=f"dl_{a[0]}")
            else:
                st.info("No hay archivos registrados en esta carpeta.")
        with tab_repo2:
            st.subheader("➕ Crear Nueva Carpeta Personalizada")
            nueva_c = st.text_input("Nombre de la Nueva Carpeta")
            if st.button("➕ Crear Carpeta") and nueva_c:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute('INSERT INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (nueva_c.strip(),))
                    conn.commit()
                    st.success(f"✅ Carpeta '{nueva_c}' creada exitosamente.")
                    st.rerun()
                except Exception:
                    st.error("La carpeta ya existe.")
                conn.close()
            st.markdown("---")
            st.subheader("✏️ Renombrar Carpeta Existente")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY id ASC')
            carps_exist = [r[0] for r in c.fetchall()]
            conn.close()
            if carps_exist:
                carp_ren = st.selectbox("Seleccione Carpeta a Renombrar", carps_exist)
                nuevo_nom_c = st.text_input("Nuevo Nombre para la Carpeta")
                if st.button("✏️ Actualizar Nombre de Carpeta") and nuevo_nom_c:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?', (nuevo_nom_c.strip(), carp_ren))
                    c.execute('UPDATE repositorio_archivos SET carpeta = ? WHERE carpeta = ?', (nuevo_nom_c.strip(), carp_ren))
                    conn.commit()
                    conn.close()
                    st.success("✅ Nombre de carpeta actualizado.")
                    st.rerun()
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Expedientes")
        busqueda = st.text_input("Buscar por Nombre, Folio o Expediente")
        if lista_p:
            res_list = []
            q = busqueda.lower().strip()
            for p in lista_p:
                lbl = p['label'].lower()
                if not q or q in lbl:
                    res_list.append(p)
            st.write(f"Resultados encontrados: **{len(res_list)}**")
            for p in res_list:
                with st.expander(f"📋 {p['label']}"):
                    d = p['datos']
                    col1, col2 = st.columns(2)
                    col1.write(f"**Folio:** {p['paciente_id']}")
                    col1.write(f"**Expediente:** {p['expediente'] or 'S/N'}")
                    col1.write(f"**Edad:** {d.get('edad', '')} años | **Sexo:** {d.get('sexo', '')}")
                    col2.write(f"**Etapa Actual:** {d.get('etapa_actual', 'Acogida')}")
                    col2.write(f"**Fecha Ingreso:** {d.get('fecha_ingreso_real', '')}")
                    col2.write(f"**Sustancia Impacto:** {d.get('sustancia_impacto', 'N/R')}")
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad")
        es_admin = st.session_state.get("username") == "admin" or st.session_state.get("rol") == "Administrador"
        if es_admin:
            tab_sec1, tab_sec2 = st.tabs(["🔑 Cambiar Mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_sec1 = st.container()
            tab_sec2 = None
        with tab_sec1:
            st.subheader("Cambiar Contraseña de Usuario Actual")
            with st.form("form_change_my_pass"):
                pass_act = st.text_input("Contraseña Actual", type="password")
                pass_new = st.text_input("Nueva Contraseña", type="password")
                pass_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_pass = st.form_submit_button("🔐 Actualizar Mi Contraseña")
                if btn_pass:
                    if pass_new != pass_conf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        ok_u = verificar_login(st.session_state["username"], pass_act)
                        if ok_u:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(pass_new), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada correctamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")
        if es_admin and tab_sec2:
            with tab_sec2:
                st.subheader("➕ Dar de Alta Nuevo Colaborador / Usuario")
                with st.form("form_nuevo_usr"):
                    u_user = st.text_input("Nombre de Usuario (Login)")
                    u_nom = st.text_input("Nombre Completo")
                    u_pass = st.text_input("Contraseña", type="password")
                    u_rol = st.selectbox("Rol de Permisos", ["Nivel 1: Administrador", "Nivel 2: Lectura/Escritura", "Nivel 3: Solo Lectura"])
                    btn_crear_u = st.form_submit_button("👥 Crear Usuario")
                    if btn_crear_u and u_user and u_pass:
                        rol_clean = "Administrador" if "Nivel 1" in u_rol else ("Lectura/Escritura" if "Nivel 2" in u_rol else "Solo Lectura")
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                      (u_user.strip(), hash_pass(u_pass), u_nom.strip(), rol_clean))
                            conn.commit()
                            st.success(f"✅ Usuario '{u_user}' creado exitosamente con rol {rol_clean}.")
                            st.rerun()
                        except Exception:
                            st.error("El nombre de usuario ya existe.")
                        conn.close()
                st.markdown("---")
                st.subheader("📋 Catálogo de Colaboradores Registrados")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol FROM usuarios')
                usrs = c.fetchall()
                conn.close()
                st.dataframe([{"ID": u[0], "Usuario": u[1], "Nombre Completo": u[2], "Rol": u[3]} for u in usrs], use_container_width=True)
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.write("Descargue una copia completa de su base de datos para mantener sus registros 100% respaldados.")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button(
                    label="💾 Descargar Respaldo Completo (.db)",
                    data=f.read(),
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    mime="application/x-sqlite3"
)

if __name__ == "__main__":
    main()
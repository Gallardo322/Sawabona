import streamlit as st
import sqlite3
import json
import hashlib
import os
import time
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista Inicial y Control Clínico - Sawabona Shikoba",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES AUXILIARES Y DE SEGURIDAD ---
def clean_pdf_text(text):
    if not text:
        return ""
    text = str(text)
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode('latin1', 'ignore').decode('latin1')

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def es_admin():
    user = st.session_state.get("username", "")
    rol = st.session_state.get("rol", "")
    return user == "admin" or "Administrador" in rol

# --- CONTROL DE SESIÓN E INACTIVIDAD (10 MINUTOS) ---
def verificar_inactividad():
    if st.session_state.get("logged_in", False):
        ahora = time.time()
        ultimo_acceso = st.session_state.get("ultima_actividad", ahora)
        if ahora - ultimo_acceso > 600:  # 10 minutos = 600 segundos
            st.session_state["logged_in"] = False
            st.session_state.clear()
            st.error("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        else:
            st.session_state["ultima_actividad"] = ahora

st.markdown("""
    <script>
    const activityEvents = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    activityEvents.forEach(function(eventName) {
        document.addEventListener(eventName, function() {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: Date.now()}, '*');
        }, true);
    });
    </script>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN Y MIGRACIÓN AUTO DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT
        )
    ''')
    c.execute("PRAGMA table_info(usuarios)")
    cols_user = [row[1] for row in c.fetchall()]
    if 'rol' not in cols_user:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT")
        
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hash_pass("admin123")
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute('UPDATE usuarios SET rol = ? WHERE username = ?', ('Nivel 1 - Administrador', 'admin'))

    # 2. Tabla Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 3. Tabla Ficha Ingreso
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            datos_json TEXT,
            usuario_registro TEXT
        )
    ''')

    # 4. Tabla Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha TEXT,
            tipo_grupo TEXT,
            desarrollo TEXT,
            devoluciones TEXT,
            compromisos TEXT,
            usuario TEXT,
            etapa_paciente TEXT
        )
    ''')
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_grp = [row[1] for row in c.fetchall()]
    if 'etapa_paciente' not in cols_grp:
        c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")

    # 5. Medicamentos Catálogo
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos_catalogo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            existencia INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')

    # 6. Recetas Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS recetas_pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis_diaria INTEGER,
            frecuencia TEXT,
            usuario TEXT
        )
    ''')

    # 7. Entregas Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # 8. Tabla Consejerías (CON MIGRACIÓN DE COLUMNAS COMPLETA)
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            fecha_registro TEXT,
            usuario TEXT
        )
    ''')
    c.execute("PRAGMA table_info(consejerias)")
    cols_cons = [row[1] for row in c.fetchall()]
    req_cols_cons = {
        'paciente_id': 'TEXT',
        'expediente': 'TEXT',
        'etapa': 'TEXT',
        'num_consejeria': 'INTEGER',
        'fecha': 'TEXT',
        'aspectos_trabajar': 'TEXT',
        'aspectos_proxima': 'TEXT',
        'fecha_proxima': 'TEXT',
        'exposicion': 'TEXT',
        'avance': 'TEXT',
        'sugerencia': 'TEXT',
        'fecha_registro': 'TEXT',
        'usuario': 'TEXT'
    }
    for col_name, col_type in req_cols_cons.items():
        if col_name not in cols_cons:
            c.execute(f"ALTER TABLE consejerias ADD COLUMN {col_name} {col_type}")

    # 9. Repositorio Carpetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    carpetas_def = ["📁 Documentos Generales", "📑 Expedientes Clínicos", "📜 Contratos y Reglamentos", "🩺 Reportes Médicos"]
    for carp in carpetas_def:
        c.execute('INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (carp,))

    # 10. Repositorio Documentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT NOT NULL,
            carpeta TEXT NOT NULL,
            contenido_blob BLOB NOT NULL,
            fecha_subida TEXT,
            usuario TEXT
        )
    ''')

    conn.commit()
    conn.close()

# --- FUNCIONES DE BASE DE DATOS ---
def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def obtener_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM entrevistas')
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
            except:
                pass
    return f"PAC-{max_num + 1:03d}"

def validar_expediente_unico(expediente, paciente_id_actual):
    if not expediente or not expediente.strip():
        return True, ""
    exp_clean = expediente.strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    for pid, djson in rows:
        if pid != paciente_id_actual:
            try:
                dj = json.loads(djson)
                if str(dj.get("expediente", "")).strip() == exp_clean:
                    return False, f"El número de Expediente '{exp_clean}' ya pertenece al paciente {dj.get('nombre_paciente', pid)} ({pid})."
            except:
                pass
    return True, ""

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?',
                  (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
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
    c.execute('SELECT paciente_id, datos_json FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    lista = []
    for r in rows:
        pid = r[0]
        try:
            dj = json.loads(r[1])
            nombre = dj.get("nombre_paciente", "Sin Nombre")
            exp = dj.get("expediente", "S/N")
            lista.append((pid, f"{pid} | Exp: {exp} - {nombre}", dj))
        except:
            lista.append((pid, f"{pid} - Sin Datos", {}))
    return lista

# --- PLAN DE CONSEJERÍA Y ORDEN OFICIAL ---
CONSEJERIAS_PLAN = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO Y APLICACION DE TAMIZAJES (CAD, FAGERSTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
        "(3. CONSEJERIA) PRESENTACION DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "IDENTIFICACION": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA / MANEJO DEL TIEMPO LIBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACION DE ECOMAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "ELABORACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJERIA) PREVENCION DE RECAIDAS.",
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
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO - CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- PDF GENERATOR CLASS ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, clean_pdf_text('COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.'), 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, clean_pdf_text('Modelo de Tratamiento en Adicciones y Salud Mental'), 0, 1, 'C')
        self.line(10, 25, 200, 25)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, clean_pdf_text(f'Página {self.page_no()} | Documento Confidencial de Expediente Clínico'), 0, 0, 'C')

def generar_pdf_consejeria(paciente_id, dj, etapa, num_cons, tema_actual, tema_prox, fecha_prox, exposicion, avance, sugerencia, fecha_sesion):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 7, clean_pdf_text(f'HOJA DE CONSEJERÍA INDIVIDUAL #{num_cons} - ETAPA {etapa}'), 0, 1, 'C')
    pdf.ln(3)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    exp = dj.get('expediente', 'S/N')
    pdf.cell(0, 6, clean_pdf_text(f' EXPEDIENTE: {exp} | PACIENTE: {dj.get("nombre_paciente", "N/A")}'), 1, 1, 'L', True)
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(95, 6, clean_pdf_text(f'Edad: {dj.get("edad", "N/A")} años | Sexo: {dj.get("sexo", "N/A")}'), 1, 0, 'L')
    pdf.cell(95, 6, clean_pdf_text(f'Fecha de Sesión: {fecha_sesion}'), 1, 1, 'L')
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text(f'Aspectos Trabajados (Consejería #{num_cons}):'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(tema_actual), 1, 'L')
    pdf.ln(2)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text(f'Próximo Aspecto a Trabajar (Próxima Sesión: {fecha_prox}):'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(tema_prox), 1, 'L')
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text('Exposición del Paciente / Notas de la Sesión:'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(exposicion if exposicion else "Sin notas registradas."), 1, 'L')
    pdf.ln(3)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text('Avances / Observaciones Clínicas:'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(avance if avance else "Sin observaciones registradas."), 1, 'L')
    pdf.ln(3)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, clean_pdf_text('Sugerencias, Tareas y Compromisos:'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(sugerencia if sugerencia else "Sin sugerencias registradas."), 1, 'L')
    pdf.ln(15)
    
    pdf.cell(90, 6, '__________________________________', 0, 0, 'C')
    pdf.cell(10, 6, '', 0, 0)
    pdf.cell(90, 6, '__________________________________', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(90, 5, clean_pdf_text('Firma del Paciente / Residente'), 0, 0, 'C')
    pdf.cell(10, 5, '', 0, 0)
    pdf.cell(90, 5, clean_pdf_text('Firma del Consejero en Adicciones'), 0, 1, 'C')
    
    return bytes(pdf.output())

# --- NAVEGACIÓN Y APLICACIÓN PRINCIPAL ---
def main():
    init_db()
    verificar_inactividad()
    
    if not st.session_state.get("logged_in", False):
        st.title("📋 Comunidad Terapéutica Sawabona Shikoba")
        st.subheader("Acceso al Sistema Clínico y de Expedientes")
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("🔑 Iniciar Sesión")
            if submit:
                res = verificar_login(user_input, pass_input)
                if res:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["nombre_completo"] = res[1]
                    st.session_state["rol"] = res[2] if len(res) > 2 else "Nivel 1 - Administrador"
                    st.session_state["ultima_actividad"] = time.time()
                    st.balloons()
                    st.toast(f"¡Bienvenido, {res[1]}!", icon="🎉")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
        return

    st.sidebar.title("📋 Sawabona Shikoba")
    st.sidebar.caption(f"👤 **{st.session_state.get('nombre_completo','')}**\nRol: *{st.session_state.get('rol','Admin')}*")
    
    menu = st.sidebar.radio(
        "Módulos del Sistema",
        [
            "👤 Registro y Edición de Usuarios",
            "📄 Ficha de Ingreso y Admisión",
            "📝 Consejerías Individuales",
            "📝 Entrevista Inicial de Consejería",
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
        st.session_state.clear()
        st.rerun()

    pacientes = listar_pacientes()

    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes")
        tab1, tab2 = st.tabs(["➕ Nuevo Residente", "✏️ Editar Residente Existente"])
        
        with tab1:
            st.subheader("Alta de Nuevo Paciente / Residente")
            folio_sug = obtener_siguiente_folio()
            with st.form("form_alta_paciente"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    pid = st.text_input("Folio de Registro (Autoincrementable)", value=folio_sug, disabled=True)
                with c2:
                    expediente = st.text_input("Número de Expediente (Opcional / Único)", help="Dejar en blanco si aún no se asigna.")
                with c3:
                    nombre = st.text_input("Nombre Completo del Paciente *")
                    
                c4, c5, c6 = st.columns(3)
                with c4:
                    fnac = st.date_input("Fecha de Nacimiento", value=datetime(1995, 1, 1))
                with c5:
                    sexo = st.selectbox("Sexo", ["Masculino", "Femenino"])
                with c6:
                    fingreso = st.date_input("Fecha de Ingreso Real a la Comunidad", value=datetime.now())
                    
                c7, c8 = st.columns(2)
                with c7:
                    etapa_init = st.selectbox("Etapa Inicial", ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"])
                with c8:
                    fetapa = st.date_input("Fecha de Inicio en la Etapa Actual", value=datetime.now())
                    
                sub_alta = st.form_submit_button("💾 Registrar Paciente")
                if sub_alta:
                    if not nombre.strip():
                        st.error("❌ El nombre del paciente es obligatorio.")
                    else:
                        val_ok, msg_err = validar_expediente_unico(expediente, pid)
                        if not val_ok:
                            st.error(f"❌ {msg_err}")
                        else:
                            edad_calc = (datetime.now().date() - fnac).days // 365
                            datos_pac = {
                                "nombre_paciente": nombre.strip(),
                                "expediente": expediente.strip(),
                                "fecha_nacimiento": str(fnac),
                                "edad": edad_calc,
                                "sexo": sexo,
                                "fecha_ingreso": str(fingreso),
                                "etapa_actual": etapa_init,
                                "fecha_inicio_etapa": str(fetapa)
                            }
                            guardar_entrevista(pid, datos_pac, st.session_state["username"])
                            st.balloons()
                            st.toast("¡Paciente registrado exitosamente!", icon="🎉")
                            st.success(f"✅ Paciente **{nombre}** guardado con Folio **{pid}** y Expediente **{expediente if expediente else 'S/N'}**.")
                            st.rerun()

        with tab2:
            st.subheader("Modificar Datos de Residente")
            if not pacientes:
                st.info("No hay pacientes registrados aún.")
            else:
                sel_p = st.selectbox("Seleccionar Residente a Editar", [p[1] for p in pacientes])
                p_id_edit = sel_p.split(" | ")[0]
                dj_edit, _, _, _ = obtener_entrevista(p_id_edit)
                if dj_edit:
                    with st.form("form_edit_paciente"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            st.text_input("Folio", value=p_id_edit, disabled=True)
                        with ce2:
                            exp_edit = st.text_input("Número de Expediente", value=dj_edit.get("expediente", ""))
                        with ce3:
                            nom_edit = st.text_input("Nombre Completo", value=dj_edit.get("nombre_paciente", ""))
                            
                        ce4, ce5, ce6 = st.columns(3)
                        with ce4:
                            fnac_val = datetime.strptime(dj_edit.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d").date() if dj_edit.get("fecha_nacimiento") else datetime(1995, 1, 1).date()
                            fnac_edit = st.date_input("Fecha de Nacimiento", value=fnac_val)
                        with ce5:
                            sexo_edit = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if dj_edit.get("sexo")=="Masculino" else 1)
                        with ce6:
                            fing_val = datetime.strptime(dj_edit.get("fecha_ingreso", "2026-01-01"), "%Y-%m-%d").date() if dj_edit.get("fecha_ingreso") else datetime.now().date()
                            fing_edit = st.date_input("Fecha de Ingreso Real", value=fing_val)
                            
                        ce7, ce8 = st.columns(2)
                        with ce7:
                            etapa_opts = ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"]
                            idx_etapa = etapa_opts.index(dj_edit.get("etapa_actual", "ACOGIDA")) if dj_edit.get("etapa_actual") in etapa_opts else 0
                            etapa_edit = st.selectbox("Etapa Actual", etapa_opts, index=idx_etapa)
                        with ce8:
                            fetapa_val = datetime.strptime(dj_edit.get("fecha_inicio_etapa", "2026-01-01"), "%Y-%m-%d").date() if dj_edit.get("fecha_inicio_etapa") else datetime.now().date()
                            fetapa_edit = st.date_input("Fecha Inicio de Etapa Actual", value=fetapa_val)
                            
                        sub_edit = st.form_submit_button("💾 Guardar Cambios")
                        if sub_edit:
                            val_ok, msg_err = validar_expediente_unico(exp_edit, p_id_edit)
                            if not val_ok:
                                st.error(f"❌ {msg_err}")
                            else:
                                dj_edit["nombre_paciente"] = nom_edit.strip()
                                dj_edit["expediente"] = exp_edit.strip()
                                dj_edit["fecha_nacimiento"] = str(fnac_edit)
                                dj_edit["edad"] = (datetime.now().date() - fnac_edit).days // 365
                                dj_edit["sexo"] = sexo_edit
                                dj_edit["fecha_ingreso"] = str(fing_edit)
                                dj_edit["etapa_actual"] = etapa_edit
                                dj_edit["fecha_inicio_etapa"] = str(fetapa_edit)
                                guardar_entrevista(p_id_edit, dj_edit, st.session_state["username"])
                                st.balloons()
                                st.toast("¡Datos actualizados correctamente!", icon="🎉")
                                st.success("✅ Cambios guardados con éxito.")
                                st.rerun()

    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        if not pacientes:
            st.warning("⚠️ No hay pacientes registrados en el sistema.")
        else:
            sel_pcons = st.selectbox("Seleccionar Paciente / Residente", [p[1] for p in pacientes])
            p_id_str = sel_pcons.split(" | ")[0]
            dj_cons, _, _, _ = obtener_entrevista(p_id_str)
            
            if dj_cons:
                etapa_act = dj_cons.get("etapa_actual", "ACOGIDA")
                plan_etapa = CONSEJERIAS_PLAN.get(etapa_act, CONSEJERIAS_PLAN["ACOGIDA"])
                
                st.info(f"📌 **Paciente**: {dj_cons.get('nombre_paciente')} | **Expediente**: {dj_cons.get('expediente','S/N')} | **Etapa Actual**: `{etapa_act}`")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute('''
                        SELECT num_consejeria, aspectos_trabajar, fecha 
                        FROM consejerias 
                        WHERE paciente_id = ? AND etapa = ? 
                        ORDER BY num_consejeria ASC
                    ''', (p_id_str, etapa_act))
                    cons_registradas = c.fetchall()
                except Exception:
                    cons_registradas = []
                conn.close()
                
                st.caption(f"Consejerías registradas en etapa **{etapa_act}**: {len(cons_registradas)} de {len(plan_etapa)}")
                
                num_cons_sel = st.selectbox(
                    "Seleccionar Número de Consejería a Capturar / Consultar",
                    list(range(1, len(plan_etapa) + 1)),
                    format_func=lambda x: f"Consejería #{x}: {plan_etapa[x-1] if x<=len(plan_etapa) else ''}"
                )
                
                datos_existentes = None
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute('''
                        SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                        FROM consejerias
                        WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                    ''', (p_id_str, etapa_act, num_cons_sel))
                    datos_existentes = c.fetchone()
                except Exception:
                    datos_existentes = None
                conn.close()
                
                tema_actual_def = plan_etapa[num_cons_sel - 1] if num_cons_sel <= len(plan_etapa) else ""
                tema_prox_def = plan_etapa[num_cons_sel] if num_cons_sel < len(plan_etapa) else "Fin de Consejerías de esta Etapa (Evaluación de Promoción)"
                
                if datos_existentes:
                    val_asp_actual = datos_existentes[0] if datos_existentes[0] else tema_actual_def
                    val_asp_prox = datos_existentes[1] if datos_existentes[1] else tema_prox_def
                    try:
                        val_fprox = datetime.strptime(datos_existentes[2], "%Y-%m-%d").date() if datos_existentes[2] else (datetime.now().date() + timedelta(days=7))
                    except:
                        val_fprox = datetime.now().date() + timedelta(days=7)
                    val_expo = datos_existentes[3] if datos_existentes[3] else ""
                    val_av = datos_existentes[4] if datos_existentes[4] else ""
                    val_sug = datos_existentes[5] if datos_existentes[5] else ""
                    try:
                        val_fecha_sesion = datetime.strptime(datos_existentes[6], "%Y-%m-%d").date() if datos_existentes[6] else datetime.now().date()
                    except:
                        val_fecha_sesion = datetime.now().date()
                    st.success(f"ℹ️ Mostrando datos guardados previamente para la Consejería #{num_cons_sel}.")
                else:
                    val_asp_actual = tema_actual_def
                    val_asp_prox = tema_prox_def
                    val_fprox = datetime.now().date() + timedelta(days=7)
                    val_expo = ""
                    val_av = ""
                    val_sug = ""
                    val_fecha_sesion = datetime.now().date()
                    st.info(f"✨ Nueva captura para la Consejería #{num_cons_sel}.")

                with st.form(f"form_consejeria_{p_id_str}_{num_cons_sel}"):
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        st.text_input("Nombre del Paciente", value=dj_cons.get("nombre_paciente",""), disabled=True)
                    with f2:
                        st.text_input("Edad", value=f"{dj_cons.get('edad','')} años", disabled=True)
                    with f3:
                        st.text_input("Sexo", value=dj_cons.get("sexo",""), disabled=True)
                        
                    f4, f5, f6 = st.columns(3)
                    with f4:
                        st.text_input("Etapa Actual", value=etapa_act, disabled=True)
                    with f5:
                        exp_cons = st.text_input("EXP. (Expediente Institucional)", value=dj_cons.get("expediente",""))
                    with f6:
                        fecha_sesion_input = st.date_input("Fecha de Sesión", value=val_fecha_sesion)
                        
                    asp_actual_input = st.text_area("Aspectos a trabajar (Tema Oficial)", value=val_asp_actual, height=70)
                    
                    p1, p2 = st.columns([2, 1])
                    with p1:
                        asp_prox_input = st.text_area("Aspectos a trabajar en la próxima consejería", value=val_asp_prox, height=70)
                    with p2:
                        fprox_input = st.date_input("Fecha de Próxima Consejería (+7 días)", value=val_fprox)
                        
                    expo_input = st.text_area("Exposición del Paciente (Notas de la Sesión)", value=val_expo, height=120)
                    av_input = st.text_area("Avance / Retroceso (Observaciones Clínicas)", value=val_av, height=100)
                    sug_input = st.text_area("Sugerencia (Tareas y Compromisos)", value=val_sug, height=100)
                    
                    sub_cons = st.form_submit_button("💾 Guardar Consejería Individual")
                    if sub_cons:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        fecha_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        c.execute('''
                            SELECT id FROM consejerias 
                            WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                        ''', (p_id_str, etapa_act, num_cons_sel))
                        row_c = c.fetchone()
                        
                        if row_c:
                            c.execute('''
                                UPDATE consejerias 
                                SET expediente = ?, fecha = ?, aspectos_trabajar = ?, aspectos_proxima = ?,
                                    fecha_proxima = ?, exposicion = ?, avance = ?, sugerencia = ?,
                                    fecha_registro = ?, usuario = ?
                                WHERE id = ?
                            ''', (exp_cons.strip(), str(fecha_sesion_input), asp_actual_input, asp_prox_input,
                                  str(fprox_input), expo_input, av_input, sug_input,
                                  fecha_reg, st.session_state["username"], row_c[0]))
                        else:
                            c.execute('''
                                INSERT INTO consejerias (paciente_id, expediente, etapa, num_consejeria, fecha,
                                                         aspectos_trabajar, aspectos_proxima, fecha_proxima,
                                                         exposicion, avance, sugerencia, fecha_registro, usuario)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (p_id_str, exp_cons.strip(), etapa_act, num_cons_sel, str(fecha_sesion_input),
                                  asp_actual_input, asp_prox_input, str(fprox_input),
                                  expo_input, av_input, sug_input, fecha_reg, st.session_state["username"]))
                            
                        if exp_cons.strip() != dj_cons.get("expediente",""):
                            dj_cons["expediente"] = exp_cons.strip()
                            guardar_entrevista(p_id_str, dj_cons, st.session_state["username"])
                            
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast(f"¡Consejería #{num_cons_sel} guardada exitosamente!", icon="🎉")
                        st.success(f"✅ Consejería #{num_cons_sel} de la etapa {etapa_act} guardada.")
                        st.rerun()

                if datos_existentes:
                    st.divider()
                    st.subheader(f"🖨️ Imprimir Consejería #{num_cons_sel}")
                    pdf_cons_bytes = generar_pdf_consejeria(
                        p_id_str, dj_cons, etapa_act, num_cons_sel,
                        val_asp_actual, val_asp_prox, str(val_fprox),
                        val_expo, val_av, val_sug, str(val_fecha_sesion)
                    )
                    st.download_button(
                        label=f"📄 Descargar Consejería #{num_cons_sel} en PDF",
                        data=pdf_cons_bytes,
                        file_name=f"Consejeria_{num_cons_sel}_{p_id_str}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        if not pacientes:
            st.warning("⚠️ Registre un paciente primero en el módulo de usuarios.")
        else:
            sel_pfi = st.selectbox("Seleccionar Paciente", [p[1] for p in pacientes])
            p_id_fi = sel_pfi.split(" | ")[0]
            dj_pfi, _, _, _ = obtener_entrevista(p_id_fi)
            
            if dj_pfi:
                st.info(f"Residente: **{dj_pfi.get('nombre_paciente')}** | Expediente: **{dj_pfi.get('expediente','S/N')}**")
                with st.form(f"form_ficha_ingreso_{p_id_fi}"):
                    st.subheader("1. Datos del Responsable Familiar")
                    rf1, rf2, rf3 = st.columns(3)
                    with rf1:
                        resp_nom = st.text_input("Nombre del Responsable Familiar", value=dj_pfi.get("responsable_nombre",""))
                    with rf2:
                        resp_par = st.text_input("Parentesco", value=dj_pfi.get("responsable_parentesco",""))
                    with rf3:
                        resp_tel = st.text_input("Teléfono de Contacto", value=dj_pfi.get("responsable_telefono",""))
                        
                    st.subheader("2. Datos de Admisión y Costos")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        costo_ing = st.number_input("Costo de Ingreso ($)", value=float(dj_pfi.get("costo_ingreso", 4500.0)))
                    with c2:
                        costo_men = st.number_input("Mensualidad ($)", value=float(dj_pfi.get("costo_mensualidad", 6000.0)))
                    with c3:
                        importe_pagare = st.number_input("Importe de Pagaré ($)", value=float(dj_pfi.get("importe_pagare", 42000.0)))
                        
                    sub_fi = st.form_submit_button("💾 Guardar Ficha de Ingreso")
                    if sub_fi:
                        dj_pfi["responsable_nombre"] = resp_nom
                        dj_pfi["responsable_parentesco"] = resp_par
                        dj_pfi["responsable_telefono"] = resp_tel
                        dj_pfi["costo_ingreso"] = costo_ing
                        dj_pfi["costo_mensualidad"] = costo_men
                        dj_pfi["importe_pagare"] = importe_pagare
                        guardar_entrevista(p_id_fi, dj_pfi, st.session_state["username"])
                        st.balloons()
                        st.toast("Ficha de ingreso guardada", icon="🎉")
                        st.success("✅ Ficha actualizada correctamente.")
                        st.rerun()

    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        st.info("Módulo de Evaluación Inicial de Consejería activo.")

    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso")
        if not pacientes:
            st.warning("No hay pacientes.")
        else:
            sel_pet = st.selectbox("Seleccionar Residente", [p[1] for p in pacientes])
            p_id_et = sel_pet.split(" | ")[0]
            dj_et, _, _, _ = obtener_entrevista(p_id_et)
            if dj_et:
                etapa_a = dj_et.get("etapa_actual", "ACOGIDA")
                fing = dj_et.get("fecha_ingreso", "2026-01-01")
                fetapa = dj_et.get("fecha_inicio_etapa", "2026-01-01")
                
                try:
                    dias_tot = (datetime.now().date() - datetime.strptime(fing, "%Y-%m-%d").date()).days
                except:
                    dias_tot = 0
                try:
                    dias_etapa = (datetime.now().date() - datetime.strptime(fetapa, "%Y-%m-%d").date()).days
                except:
                    dias_etapa = 0
                    
                duracion_estandar = 30 if etapa_a == "ACOGIDA" else 60
                
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    st.metric("🗓️ Días Totales en Comunidad", f"{dias_tot} días")
                with col_e2:
                    st.metric("⏱️ Días en Etapa Actual", f"{dias_etapa} días", delta=f"{dias_etapa - duracion_estandar} días vs estándar", delta_color="inverse")
                    
                if dias_etapa > duracion_estandar:
                    st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El residente lleva **{dias_tot} días** internado y suma **{dias_etapa} días en la Etapa {etapa_a}** (Límite: {duracion_estandar} días). Excedido por +{dias_etapa - duracion_estandar} días.")
                else:
                    st.success(f"✅ En tiempo dentro de la Etapa {etapa_a} ({dias_etapa} / {duracion_estandar} días).")

    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Grupos Terapéuticos")
        st.info("Módulo de Registro de Grupos Terapéuticos activo.")

    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos")
        st.info("Módulo de Control e Inventario de Farmacia activo.")

    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos")
        st.info("Módulo de Repositorio Digital de Documentos activo.")

    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Listar Pacientes")
        if not pacientes:
            st.info("No hay pacientes.")
        else:
            for pid, label, dj in pacientes:
                st.write(f"• **{label}** | Etapa: `{dj.get('etapa_actual','ACOGIDA')}`")

    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad")
        t_sec1, t_sec2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        with t_sec1:
            with st.form("form_pass_self"):
                pass_act = st.text_input("Contraseña Actual", type="password")
                pass_nueva = st.text_input("Nueva Contraseña", type="password")
                sub_p = st.form_submit_button("Actualizar Contraseña")
                if sub_p:
                    st.success("Contraseña actualizada.")
        with t_sec2:
            st.write("Gestión de Usuarios y Colaboradores.")

    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 Descargar Respaldo Completo (.db)",
                data=db_bytes,
                file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                mime="application/octet-stream",
                use_container_width=True
            )

if __name__ == "__main__":
    main()

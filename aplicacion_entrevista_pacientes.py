import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Comunidad Terapéutica Sawabona Shikoba - Sistema de Control",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- UTILIDAD DE BÚSQUEDA SEGURA DE ÍNDICE ---
def get_safe_index(options, value, default_idx=0):
    if not value:
        return default_idx
    str_val = str(value).strip().lower()
    for i, opt in enumerate(options):
        if str(opt).strip().lower() == str_val:
            return i
    # Intento de búsqueda aproximada ignorando acentos
    def normalizar(s):
        return str(s).strip().lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')
    norm_val = normalizar(value)
    for i, opt in enumerate(options):
        if normalizar(opt) == norm_val:
            return i
    return default_idx

# --- LIMPIEZA DE TEXTO PARA PDF ---
def clean_pdf_text(text):
    if not text:
        return ""
    text = str(text)
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '', '¡': '', '“': '"', '”': '"', '’': "'", '‘': "'",
        '–': '-', '—': '-', '…': '...'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode('latin-1', 'ignore').decode('latin-1')

# --- FUNCIONES DE BASE DE DATOS E MIGRACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Lectura/Escritura'
        )
    ''')
    
    # Migración de tabla usuarios
    c.execute("PRAGMA table_info(usuarios)")
    cols_usr = [col[1] for col in c.fetchall()]
    if "rol" not in cols_usr:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Lectura/Escritura'")
        except Exception:
            pass

    # Tabla de Pacientes / Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # Tabla de Consejerías
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            fecha TEXT,
            usuario TEXT
        )
    ''')
    
    # Migración de tabla consejerias
    c.execute("PRAGMA table_info(consejerias)")
    cols_cons = [col[1] for col in c.fetchall()]
    m_cols = {
        "expediente": "TEXT", "etapa": "TEXT", "num_consejeria": "INTEGER",
        "aspectos_trabajar": "TEXT", "aspectos_proxima": "TEXT", "fecha_proxima": "TEXT",
        "exposicion": "TEXT", "avance": "TEXT", "sugerencia": "TEXT", "fecha": "TEXT", "usuario": "TEXT"
    }
    for col_name, col_type in m_cols.items():
        if col_name not in cols_cons:
            try:
                c.execute(f"ALTER TABLE consejerias ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

    # Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            desarrollo TEXT,
            devoluciones TEXT,
            compromisos TEXT,
            etapa_paciente TEXT,
            usuario TEXT
        )
    ''')
    
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_grup = [col[1] for col in c.fetchall()]
    if "etapa_paciente" not in cols_grup:
        try:
            c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")
        except Exception:
            pass

    # Tabla de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_medicamento TEXT UNIQUE NOT NULL,
            stock_actual INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')

    # Tabla de Medicación Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicacion_paciente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            frecuencia TEXT,
            estado TEXT DEFAULT 'Activo'
        )
    ''')

    # Tabla de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad_entregada INTEGER,
            fecha_entrega TEXT,
            usuario TEXT
        )
    ''')

    # Tabla de Carpetas Personalizadas del Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Insertar carpetas por defecto si no existen
    carpetas_def = ["Documentos Generales", "Formatos Clinicos", "Manuales y Guias", "Expedientes Digitales"]
    for c_def in carpetas_def:
        try:
            c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (c_def,))
        except Exception:
            pass

    # Tabla de Repositorio de Documentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT NOT NULL,
            carpeta TEXT NOT NULL,
            datos_blob BLOB,
            fecha_subida TEXT,
            usuario TEXT
        )
    ''')

    # Crear usuario admin por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Administrador' WHERE username = 'admin'")

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
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

def validar_expediente_unico(expediente, paciente_id_actual=None):
    if not expediente or str(expediente).strip() == "":
        return True, ""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    exp_str = str(expediente).strip()
    for pid, d_json in rows:
        if paciente_id_actual and pid == paciente_id_actual:
            continue
        if d_json:
            try:
                dj = json.loads(d_json)
                exp_exist = str(dj.get("expediente", "")).strip()
                if exp_exist and exp_exist == exp_str:
                    nom = dj.get("nombre_completo", "Sin Nombre")
                    return False, f"El Expediente '{exp_str}' ya esta asignado al paciente {nom} ({pid})."
            except Exception:
                pass
    return True, ""

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
    c.execute('SELECT paciente_id, datos_json, fecha_registro FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    
    pacientes = []
    for row in rows:
        p_id = row[0]
        f_reg = row[2]
        try:
            datos = json.loads(row[1])
            exp = datos.get("expediente", "")
            exp_label = f" (Exp: {exp})" if exp else ""
            nombre = datos.get("nombre_completo", "Sin nombre")
            etapa = datos.get("etapa_actual", "Acogida")
            pacientes.append({
                "id": p_id,
                "expediente": exp,
                "label": f"{p_id}{exp_label} - {nombre} [{etapa}]",
                "nombre": nombre,
                "etapa": etapa,
                "fecha_registro": f_reg,
                "datos": datos
            })
        except Exception:
            pass
    return pacientes

# --- CLASE PDF GENERAL ---
class PDFEntrevista(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, clean_pdf_text('COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.'), 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, clean_pdf_text('Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones'), 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, clean_pdf_text(f'Pagina {self.page_no()}'), 0, 0, 'C')

def generar_pdf_ficha_ingreso(p_id, dj):
    pdf = PDFEntrevista()
    pdf.add_page()
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y ADMISION DE USUARIO"), 0, 1, "C")
    pdf.ln(3)

    exp_num = dj.get('expediente', '') if dj.get('expediente', '') else 'S/N'
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"EXPEDIENTE INSTITUCIONAL: {exp_num}"), 0, 1, "R")
    pdf.ln(2)

    # 1. Responsable
    pdf.set_fill_color(220, 240, 220)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS DEL RESPONSABLE DEL INGRESO"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre: {dj.get('responsable_nombre', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Parentesco: {dj.get('responsable_parentesco', 'N/A')} | Tel: {dj.get('responsable_telefono', 'N/A')}"), 0, 1)
    pdf.ln(3)

    # 2. Datos Paciente
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. DATOS GENERALES DEL PACIENTE"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre Completo: {dj.get('nombre_completo', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Edad: {dj.get('edad', 'N/A')} anos | Fecha Nacimiento: {dj.get('fecha_nacimiento', 'N/A')} | Estado Civil: {dj.get('estado_civil', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Escolaridad: {dj.get('escolaridad', 'N/A')} | Religion: {dj.get('religion', 'N/A')} | Ocupacion: {dj.get('ocupacion', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Servicios Medicos: {dj.get('servicios_medicos', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio: {dj.get('calle', '')} #{dj.get('num_ext', '')}, Col. {dj.get('colonia', '')}, {dj.get('municipio', '')}, {dj.get('estado', '')}"), 0, 1)
    pdf.ln(3)

    # 3. Sustancias
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. SUSTANCIAS DE CONSUMO"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    susts = ", ".join(dj.get("sustancias_consumo", [])) if dj.get("sustancias_consumo") else "Ninguna registrada"
    pdf.cell(0, 5, clean_pdf_text(f"Sustancias de consumo: {susts}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Sustancia de Impacto Principal: {dj.get('sustancia_impacto', 'N/A')}"), 0, 1)
    pdf.ln(3)

    # 4. Términos
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("4. TERMINOS FINANCIEROS Y MODALIDAD"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Sucursal a Referir: {dj.get('sucursal', 'N/A')} | Modalidad: {dj.get('modalidad_ingreso', 'Voluntario')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Costo de Ingreso: ${dj.get('costo_ingreso', 4500):,.2f} | Mensualidad: ${dj.get('costo_mensual', 6000):,.2f} | Pagare: ${dj.get('importe_pagare', 42000):,.2f}"), 0, 1)
    pdf.ln(5)

    # Cláusula NOM-028
    pdf.set_font("Arial", "I", 8)
    pdf.multi_cell(0, 4, clean_pdf_text("DECLARACION DE CONFORMIDAD Y AUTORIZACION (NOM-028-SSA2-2009):\nPor medio de la presente, el responsable familiar y/o usuario autoriza el ingreso residencial voluntario a la Comunidad Terapeutica Sawabona Shikoba A.C., aceptando el reglamento interno, costos acordados y el plan general de tratamiento integral."))
    pdf.ln(12)

    # Firmas
    pdf.set_font("Arial", "B", 9)
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 1, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma del Responsable Familiar"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("Director / Encargado de Centro"), 0, 1, "C")

    return bytes(pdf.output())

def generar_pdf_consejeria(p_id, dj, num_cons, asp_trab, asp_prox, f_prox, exp, av, sug, fecha_c):
    pdf = PDFEntrevista()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, clean_pdf_text(f"HOJA DE CONSEJERIA INDIVIDUAL #{num_cons}"), 0, 1, "C")
    pdf.ln(3)

    exp_num = dj.get('expediente', '') if dj.get('expediente', '') else 'S/N'
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text(f"EXPEDIENTE: {exp_num} | FECHA SESION: {fecha_c}"), 0, 1, "R")
    pdf.ln(2)

    # Datos
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(0, 6, clean_pdf_text("DATOS IDENTIFICATIVOS DEL PACIENTE"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre: {dj.get('nombre_completo', 'N/A')} | Edad: {dj.get('edad', 'N/A')} anos | Sexo: {dj.get('sexo', 'N/A')}"), 0, 1)
    pdf.cell(0, 5, clean_pdf_text(f"Etapa Actual: {dj.get('etapa_actual', 'Acogida')}"), 0, 1)
    pdf.ln(3)

    # Temas
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, clean_pdf_text("TEMAS Y PLANIFICACION DE CONSEJERIA"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspectos Trabados Hoy: {asp_trab}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspectos Próxima Consejería: {asp_prox}"))
    pdf.cell(0, 5, clean_pdf_text(f"Fecha Próxima Consejería Programada: {f_prox}"), 0, 1)
    pdf.ln(3)

    # Desarrollo
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, clean_pdf_text("DESARROLLO DE LA SESION"), 1, 1, "L", 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Exposición del Paciente:\n{exp if exp else 'Sin notas'}\n"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Avances / Observaciones:\n{av if av else 'Sin notas'}\n"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sugerencias y Compromisos:\n{sug if sug else 'Sin notas'}\n"))
    pdf.ln(10)

    # Firmas
    pdf.set_font("Arial", "B", 9)
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 1, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma del Consejero / Terapeuta"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma del Paciente / Residente"), 0, 1, "C")

    return bytes(pdf.output())

# --- PROGRAMA PRINCIPAL ---
def main():
    init_db()

    # Mapeo de Consejerías
    CATALOGO_CONSEJERIAS = {
        "Acogida": [
            "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
            "(2. CONSEJERIA) ESTADO DE ANIMO APLICACION DE TAMIZAJES (CAD, FAGERSTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
            "(3. CONSEJERIA) PRESENTACION DE PLAN DE TRATAMIENTO.",
            "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
        ],
        "Identificación": [
            "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
            "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
            "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
            "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.",
            "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
            "(6. CONSEJERIA) ELABORACION DE ECOMAPA (MAQUETA O DIBUJO).",
            "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
            "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
        ],
        "Elaboración": [
            "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
            "(2. CONSEJERIA) EVALUACION DEL PLAN DE TRATAMIENTO.",
            "(3. CONSEJERIA) HABILIDADES COGNITIVAS-CONDUCTUALES.",
            "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
            "(5. CONSEJERIA) PREVENCION DE RECAIDAS.",
            "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
            "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
            "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
        ],
        "Consolidación": [
            "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
            "(2. CONSEJERIA) EVALUACION Y/O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
            "(3. CONSEJERIA) HABILIDADES PARA LA VIDA.",
            "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
        ],
        "Servicio Social": [
            "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
            "(2. CONSEJERIA) ALTERNATIVAS DE CAMBIO - CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
            "(3. CONSEJERIA) CIERRE DE CONSEJERIA.",
            "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
        ]
    }

    OPCIONES_ETAPAS = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]

    # Autenticación
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # Control de Inactividad (10 minutos)
    if st.session_state["logged_in"]:
        ahora = datetime.now()
        if "ultima_actividad" in st.session_state:
            diferencia = (ahora - st.session_state["ultima_actividad"]).total_seconds()
            if diferencia > 600:
                st.session_state["logged_in"] = False
                st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
                st.rerun()
        st.session_state["ultima_actividad"] = ahora

    if not st.session_state["logged_in"]:
        st.markdown("<h1 style='text-align: center;'>🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Sistema de Gestión Clínica e Expedientes</h3>", unsafe_allow_html=True)
        st.write("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔐 Iniciar Sesión")
            with st.form("login_form"):
                user = st.text_input("Usuario")
                passwd = st.text_input("Contraseña", type="password")
                btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                
                if btn_login:
                    res = verificar_login(user, passwd)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2] if len(res) > 2 and res[2] else "Lectura/Escritura"
                        st.session_state["ultima_actividad"] = datetime.now()
                        st.success(f"Bienvenido, {res[1]}")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos.")
        return

    # Script JS de auto-recarga por inactividad
    st.markdown("""
        <script>
        var timeout;
        function resetTimer() {
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                window.location.reload();
            }, 600000);
        }
        window.onload = resetTimer;
        document.onmousemove = resetTimer;
        document.onkeypress = resetTimer;
        </script>
    """, unsafe_allow_html=True)

    # BARRA LATERAL
    st.sidebar.image("https://img.icons8.com/color/96/handshake.png", width=70)
    st.sidebar.title("🌱 Sawabona Shikoba A.C.")
    st.sidebar.caption(f"👤 Usuario: **{st.session_state.get('nombre_completo', '')}**")
    st.sidebar.caption(f"🛡️ Rol: **{st.session_state.get('rol', 'Lectura/Escritura')}**")

    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    st.sidebar.write("---")
    menu = st.sidebar.radio(
        "Navegación del Sistema",
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

    # 1. INICIO / TABLERO GENERAL
    if menu == "🏠 Inicio / Tablero General":
        st.title("🌱 Tablero General de la Comunidad")
        st.markdown("#### Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones")
        st.write("---")
        
        pacientes = listar_pacientes()
        total_p = len(pacientes)
        
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        
        counts = {"Acogida": 0, "Identificación": 0, "Elaboración": 0, "Consolidación": 0, "Servicio Social": 0}
        for p in pacientes:
            et = p.get("etapa", "Acogida")
            if et in counts:
                counts[et] += 1
            else:
                counts["Acogida"] += 1

        col_m1.metric("Total Residentes", total_p)
        col_m2.metric("Acogida", counts["Acogida"])
        col_m3.metric("Identificación", counts["Identificación"])
        col_m4.metric("Elaboración", counts["Elaboración"])
        col_m5.metric("Consolidación / Serv.", counts["Consolidación"] + counts["Servicio Social"])
        
        st.write("---")
        st.subheader("📋 Resumen de Residentes Activos")
        if pacientes:
            tb_data = []
            for p in pacientes:
                dj = p["datos"]
                f_nac = dj.get("fecha_nacimiento", "")
                edad = dj.get("edad", "")
                exp = p["expediente"] if p["expediente"] else "S/N"
                f_ing = dj.get("fecha_ingreso", p["fecha_registro"])
                tb_data.append({
                    "Folio": p["id"],
                    "Expediente": exp,
                    "Nombre del Residente": p["nombre"],
                    "Edad": edad,
                    "Etapa Actual": p["etapa"],
                    "Fecha de Ingreso": f_ing
                })
            st.dataframe(tb_data, use_container_width=True)
        else:
            st.info("No hay residentes registrados actualmente.")

    # 2. REGISTRO Y EDICIÓN DE USUARIOS
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes")
        
        tab_reg, tab_edit = st.tabs(["➕ Nuevo Registro de Paciente", "✏️ Modificar Paciente Existente"])
        
        with tab_reg:
            st.subheader("Captura de Datos Básicos")
            siguiente_folio = obtener_siguiente_folio()
            
            with st.form("form_nuevo_paciente"):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    st.text_input("Folio Consecutivo", value=siguiente_folio, disabled=True)
                    exp_in = st.text_input("Número de Expediente (Asignado por Institución - Numérico u Opcional)")
                    nom_in = st.text_input("Nombre Completo del Paciente *")
                    fnac_in = st.date_input("Fecha de Nacimiento", value=datetime(1995, 1, 1))
                    sex_in = st.selectbox("Sexo", ["Masculino", "Femenino"])
                
                with col_f2:
                    fing_in = st.date_input("Fecha de Ingreso a la Institución", value=datetime.now())
                    etapa_in = st.selectbox("Etapa Inicial", OPCIONES_ETAPAS, index=0)
                    fetapa_in = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.now())
                    tel_in = st.text_input("Teléfono de Contacto / Familiar")
                
                btn_crear = st.form_submit_button("💾 Guardar y Dar de Alta Residente")
                
                if btn_crear:
                    if not nom_in.strip():
                        st.error("El nombre completo es obligatorio.")
                    else:
                        val_ok, msg_err = validar_expediente_unico(exp_in)
                        if not val_ok:
                            st.error(msg_err)
                        else:
                            edad_calc = datetime.now().year - fnac_in.year - ((datetime.now().month, datetime.now().day) < (fnac_in.month, fnac_in.day))
                            datos_p = {
                                "folio": siguiente_folio,
                                "expediente": str(exp_in).strip(),
                                "nombre_completo": nom_in.strip(),
                                "fecha_nacimiento": str(fnac_in),
                                "edad": edad_calc,
                                "sexo": sex_in,
                                "fecha_ingreso": str(fing_in),
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": str(fetapa_in),
                                "telefono_contacto": tel_in.strip()
                            }
                            guardar_entrevista(siguiente_folio, datos_p, st.session_state["username"])
                            st.balloons()
                            st.success(f"✅ Paciente registrado con Folio {siguiente_folio} y Expediente '{exp_in if exp_in else 'S/N'}'")

        with tab_edit:
            st.subheader("Editar Ficha de Residente")
            pacientes = listar_pacientes()
            if not pacientes:
                st.info("No hay pacientes para editar.")
            else:
                p_opts = {p["id"]: p["label"] for p in pacientes}
                sel_p_id = st.selectbox("Seleccione el Paciente a Modificar", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                
                dj_edit, _, _, _ = obtener_entrevista(sel_p_id)
                if dj_edit:
                    with st.form("form_edit_paciente"):
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            st.text_input("Folio (No Editable)", value=sel_p_id, disabled=True)
                            exp_edit = st.text_input("Número de Expediente", value=dj_edit.get("expediente", ""))
                            nom_edit = st.text_input("Nombre Completo", value=dj_edit.get("nombre_completo", ""))
                            
                            try:
                                fnac_val = datetime.strptime(dj_edit.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d")
                            except Exception:
                                fnac_val = datetime(1995, 1, 1)
                            fnac_edit = st.date_input("Fecha de Nacimiento", value=fnac_val)
                            
                            idx_sex = get_safe_index(["Masculino", "Femenino"], dj_edit.get("sexo", "Masculino"))
                            sex_edit = st.selectbox("Sexo", ["Masculino", "Femenino"], index=idx_sex)

                        with col_e2:
                            try:
                                fing_val = datetime.strptime(dj_edit.get("fecha_ingreso", str(datetime.now().date())), "%Y-%m-%d")
                            except Exception:
                                fing_val = datetime.now()
                            fing_edit = st.date_input("Fecha de Ingreso", value=fing_val)
                            
                            idx_etapa = get_safe_index(OPCIONES_ETAPAS, dj_edit.get("etapa_actual", "Acogida"))
                            etapa_edit = st.selectbox("Etapa Actual", OPCIONES_ETAPAS, index=idx_etapa)
                            
                            try:
                                fetapa_val = datetime.strptime(dj_edit.get("fecha_inicio_etapa", str(datetime.now().date())), "%Y-%m-%d")
                            except Exception:
                                fetapa_val = datetime.now()
                            fetapa_edit = st.date_input("Fecha Inicio Etapa Actual", value=fetapa_val)
                            
                            tel_edit = st.text_input("Teléfono Contacto", value=dj_edit.get("telefono_contacto", ""))

                        btn_actualizar = st.form_submit_button("💾 Guardar Cambios")
                        
                        if btn_actualizar:
                            val_ok, msg_err = validar_expediente_unico(exp_edit, paciente_id_actual=sel_p_id)
                            if not val_ok:
                                st.error(msg_err)
                            else:
                                edad_calc = datetime.now().year - fnac_edit.year - ((datetime.now().month, datetime.now().day) < (fnac_edit.month, fnac_edit.day))
                                dj_edit["expediente"] = str(exp_edit).strip()
                                dj_edit["nombre_completo"] = nom_edit.strip()
                                dj_edit["fecha_nacimiento"] = str(fnac_edit)
                                dj_edit["edad"] = edad_calc
                                dj_edit["sexo"] = sex_edit
                                dj_edit["fecha_ingreso"] = str(fing_edit)
                                dj_edit["etapa_actual"] = etapa_edit
                                dj_edit["fecha_inicio_etapa"] = str(fetapa_edit)
                                dj_edit["telefono_contacto"] = tel_edit.strip()
                                
                                guardar_entrevista(sel_p_id, dj_edit, st.session_state["username"])
                                st.toast("✅ Ficha de residente actualizada correctamente")
                                st.success("Guardado exitoso. Refrescando...")
                                st.rerun()

    # 3. FICHA DE INGRESO Y ADMISIÓN
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión de Usuario")
        st.caption("Apego a la Norma Oficial Mexicana NOM-028-SSA2-2009")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("Debe dar de alta al paciente primero en 'Registro y Edición de Usuarios'.")
        else:
            p_opts = {p["id"]: p["label"] for p in pacientes}
            sel_pid = st.selectbox("Seleccione el Paciente para la Ficha", list(p_opts.keys()), format_func=lambda x: p_opts[x])
            
            dj_f, _, _, _ = obtener_entrevista(sel_pid)
            if dj_f:
                tab_f_edit, tab_f_pdf = st.tabs(["📝 Formulario Ficha de Ingreso", "🖨️ Imprimir / Descargar Contrato PDF"])
                
                with tab_f_edit:
                    with st.form("form_ficha_ingreso"):
                        st.markdown("##### 1. Datos del Responsable del Ingreso")
                        col_r1, col_r2, col_r3 = st.columns(3)
                        with col_r1:
                            r_nom = st.text_input("Nombre Responsable Familiar", value=dj_f.get("responsable_nombre", ""))
                        with col_r2:
                            r_par = st.text_input("Parentesco", value=dj_f.get("responsable_parentesco", ""))
                        with col_r3:
                            r_tel = st.text_input("Teléfono Responsable", value=dj_f.get("responsable_telefono", dj_f.get("telefono_contacto", "")))
                        
                        st.markdown("##### 2. Datos Generales del Paciente")
                        col_d1, col_d2, col_d3 = st.columns(3)
                        with col_d1:
                            p_nom = st.text_input("Nombre del Paciente", value=dj_f.get("nombre_completo", ""), disabled=True)
                            eciv_opts = ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"]
                            p_eciv = st.selectbox("Estado Civil", eciv_opts, index=get_safe_index(eciv_opts, dj_f.get("estado_civil", "Soltero(a)")))
                            p_calle = st.text_input("Calle y Número", value=dj_f.get("calle", ""))
                        with col_d2:
                            p_esc = st.text_input("Escolaridad", value=dj_f.get("escolaridad", ""))
                            p_rel = st.text_input("Religión", value=dj_f.get("religion", ""))
                            p_col = st.text_input("Colonia", value=dj_f.get("colonia", ""))
                        with col_d3:
                            p_ocup = st.text_input("Ocupación", value=dj_f.get("ocupacion", ""))
                            p_med = st.text_input("Servicios Médicos (IMSS/ISSSTE/Particular)", value=dj_f.get("servicios_medicos", ""))
                            p_mun = st.text_input("Municipio / Estado", value=dj_f.get("municipio", ""))

                        st.markdown("##### 3. Sustancias de Consumo")
                        sust_opts = ["Alcohol", "Cannabis (Marihuana)", "Cocaína / Crack", "Metanfetaminas (Kryppy/Cristal)", "Tabaco", "Benzodiazepinas", "Inhalables", "Otros"]
                        sust_sel = st.multiselect("Sustancias Consumidas", sust_opts, default=dj_f.get("sustancias_consumo", []))
                        
                        idx_imp = get_safe_index(sust_opts, dj_f.get("sustancia_impacto", "Alcohol"))
                        sust_impacto = st.selectbox("Sustancia de Impacto Principal", sust_opts, index=idx_imp)

                        st.markdown("##### 4. Términos Financieros y Modalidad")
                        col_t1, col_t2, col_t3 = st.columns(3)
                        with col_t1:
                            suc_sel = st.selectbox("Sucursal / Sede", ["Sawabona Shikoba - Principal"], index=0)
                            mod_opts = ["Voluntario", "Involuntario (NOM-028)"]
                            mod_sel = st.selectbox("Modalidad de Internamiento", mod_opts, index=get_safe_index(mod_opts, dj_f.get("modalidad_ingreso", "Voluntario")))
                        with col_t2:
                            costo_ing = st.number_input("Costo de Ingreso ($)", value=float(dj_f.get("costo_ingreso", 4500)))
                            costo_mens = st.number_input("Mensualidad ($)", value=float(dj_f.get("costo_mensual", 6000)))
                        with col_t3:
                            imp_pag = st.number_input("Importe Pagaré ($)", value=float(dj_f.get("importe_pagare", 42000)))

                        btn_f_save = st.form_submit_button("💾 Guardar Ficha de Ingreso")
                        
                        if btn_f_save:
                            dj_f["responsable_nombre"] = r_nom
                            dj_f["responsable_parentesco"] = r_par
                            dj_f["responsable_telefono"] = r_tel
                            dj_f["estado_civil"] = p_eciv
                            dj_f["calle"] = p_calle
                            dj_f["colonia"] = p_col
                            dj_f["municipio"] = p_mun
                            dj_f["escolaridad"] = p_esc
                            dj_f["religion"] = p_rel
                            dj_f["ocupacion"] = p_ocup
                            dj_f["servicios_medicos"] = p_med
                            dj_f["sustancias_consumo"] = sust_sel
                            dj_f["sustancia_impacto"] = sust_impacto
                            dj_f["sucursal"] = suc_sel
                            dj_f["modalidad_ingreso"] = mod_sel
                            dj_f["costo_ingreso"] = costo_ing
                            dj_f["costo_mensual"] = costo_mens
                            dj_f["importe_pagare"] = imp_pag
                            
                            guardar_entrevista(sel_pid, dj_f, st.session_state["username"])
                            st.balloons()
                            st.toast("✅ Ficha de ingreso guardada exitosamente.")

                with tab_f_pdf:
                    st.subheader("Imprimir Contrato y Ficha de Admisión")
                    pdf_bytes = generar_pdf_ficha_ingreso(sel_pid, dj_f)
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso en PDF",
                        data=pdf_bytes,
                        file_name=f"Ficha_Ingreso_{sel_pid}.pdf",
                        mime="application/pdf"
                    )

    # 4. ENTREVISTA INICIAL DE CONSEJERÍA
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("Debe dar de alta al paciente primero.")
        else:
            p_opts = {p["id"]: p["label"] for p in pacientes}
            sel_pid = st.selectbox("Seleccione el Paciente para la Entrevista", list(p_opts.keys()), format_func=lambda x: p_opts[x])
            
            dj_e, _, _, _ = obtener_entrevista(sel_pid)
            if dj_e:
                with st.form("form_entrevista_inicial"):
                    st.subheader("1. Motivo de Consulta e Historial de Consumo")
                    motivo = st.text_area("Motivo Principal de Ingreso / Consulta", value=dj_e.get("motivo_consulta", ""))
                    hist_consumo = st.text_area("Historial General de Consumo (Edades de inicio, patrones)", value=dj_e.get("historial_consumo", ""))
                    
                    st.subheader("2. Apoyo Familiar y Red Social")
                    apoyo_fam = st.text_area("Dinámica Familiar y Disposición de Apoyo", value=dj_e.get("apoyo_familiar", ""))
                    
                    st.subheader("3. Diagnóstico e Impresión del Consejero")
                    diag_cons = st.text_area("Impresión Diagnóstica Preliminar", value=dj_e.get("diagnostico_consejero", ""))
                    
                    btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial")
                    if btn_save_ent:
                        dj_e["motivo_consulta"] = motivo
                        dj_e["historial_consumo"] = hist_consumo
                        dj_e["apoyo_familiar"] = apoyo_fam
                        dj_e["diagnostico_consejero"] = diag_cons
                        guardar_entrevista(sel_pid, dj_e, st.session_state["username"])
                        st.success("✅ Entrevista Inicial guardada correctamente.")

    # 5. CONSEJERÍAS INDIVIDUALES
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("Debe dar de alta al paciente primero.")
        else:
            p_opts = {p["id"]: p["label"] for p in pacientes}
            sel_pid = st.selectbox("Seleccione el Residente", list(p_opts.keys()), format_func=lambda x: p_opts[x])
            
            dj_c, _, _, _ = obtener_entrevista(sel_pid)
            if dj_c:
                etapa_act = dj_c.get("etapa_actual", "Acogida")
                if etapa_act not in CATALOGO_CONSEJERIAS:
                    etapa_act = "Acogida"
                
                temas_etapa = CATALOGO_CONSEJERIAS[etapa_act]
                
                st.info(f"📍 Residente: **{dj_c.get('nombre_completo')}** | Etapa Activa: **{etapa_act}**")
                
                tab_c_reg, tab_c_hist = st.tabs(["📝 Capturar Consejería", "📜 Historial e Impresión PDF"])
                
                with tab_c_reg:
                    num_cons_sel = st.selectbox("Seleccione el Número de Consejería", list(range(1, len(temas_etapa) + 1)), format_func=lambda x: f"Consejería #{x} - {etapa_act}")
                    
                    # Cargar datos previos si existen
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute('''
                            SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                            FROM consejerias
                            WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                        ''', (sel_pid, etapa_act, num_cons_sel))
                        row_cons = c.fetchone()
                    except Exception:
                        row_cons = None
                    conn.close()

                    # Lógica de pre-llenado en blanco si es nueva
                    if row_cons:
                        asp_trab_val = row_cons[0]
                        asp_prox_val = row_cons[1]
                        try:
                            f_prox_val = datetime.strptime(row_cons[2], "%Y-%m-%d")
                        except Exception:
                            f_prox_val = datetime.now() + timedelta(days=7)
                        exp_val = row_cons[3] if row_cons[3] else ""
                        av_val = row_cons[4] if row_cons[4] else ""
                        sug_val = row_cons[5] if row_cons[5] else ""
                        f_sesion_val = row_cons[6]
                    else:
                        asp_trab_val = temas_etapa[num_cons_sel - 1]
                        if num_cons_sel < len(temas_etapa):
                            asp_prox_val = temas_etapa[num_cons_sel]
                        else:
                            asp_prox_val = "Orientación para Siguiente Etapa / Cierre"
                        f_prox_val = datetime.now() + timedelta(days=7)
                        exp_val = ""
                        av_val = ""
                        sug_val = ""
                        f_sesion_val = datetime.now().strftime("%Y-%m-%d")

                    with st.form("form_captura_consejeria"):
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            st.text_input("Expediente", value=dj_c.get("expediente", "S/N"), disabled=True)
                            st.text_input("Aspectos a Trabajar Hoy", value=asp_trab_val)
                            f_prox_in = st.date_input("Fecha Próxima Consejería (Sugerido +7 días)", value=f_prox_val)
                        
                        with col_c2:
                            st.text_input("Fecha Sesión Actual", value=f_sesion_val, disabled=True)
                            st.text_input("Aspectos a Trabajar en Próxima Consejería", value=asp_prox_val)

                        exp_in = st.text_area("Exposición del Paciente *", value=exp_val, help="Si es nueva consejería este campo aparece en blanco.")
                        av_in = st.text_area("Avance / Retroceso Observado *", value=av_val)
                        sug_in = st.text_area("Sugerencias y Tareas Asignadas *", value=sug_val)

                        btn_save_c = st.form_submit_button("💾 Guardar Sesión de Consejería")
                        
                        if btn_save_c:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                SELECT id FROM consejerias 
                                WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                            ''', (sel_pid, etapa_act, num_cons_sel))
                            exist_c = c.fetchone()
                            
                            f_hoy = datetime.now().strftime("%Y-%m-%d")
                            if exist_c:
                                c.execute('''
                                    UPDATE consejerias
                                    SET aspectos_trabajar = ?, aspectos_proxima = ?, fecha_proxima = ?,
                                        exposicion = ?, avance = ?, sugerencia = ?, fecha = ?, usuario = ?
                                    WHERE id = ?
                                ''', (asp_trab_val, asp_prox_val, str(f_prox_in), exp_in, av_in, sug_in, f_hoy, st.session_state["username"], exist_c[0]))
                            else:
                                c.execute('''
                                    INSERT INTO consejerias 
                                    (paciente_id, expediente, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (sel_pid, dj_c.get("expediente", ""), etapa_act, num_cons_sel, asp_trab_val, asp_prox_val, str(f_prox_in), exp_in, av_in, sug_in, f_hoy, st.session_state["username"]))
                            
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.success(f"✅ Consejería #{num_cons_sel} guardada exitosamente.")
                            st.rerun()

                with tab_c_hist:
                    st.subheader("Historial de Consejerías Registradas")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute('''
                            SELECT num_consejeria, aspectos_trabajar, fecha, exposicion, avance, sugerencia, aspectos_proxima, fecha_proxima
                            FROM consejerias
                            WHERE paciente_id = ? AND etapa = ?
                            ORDER BY num_consejeria ASC
                        ''', (sel_pid, etapa_act))
                        rows_hist = c.fetchall()
                    except Exception:
                        rows_hist = []
                    conn.close()

                    if not rows_hist:
                        st.info("No hay consejerías registradas para este residente en la etapa actual.")
                    else:
                        for rh in rows_hist:
                            with st.expander(f"Consejería #{rh[0]} - {rh[1]} ({rh[2]})"):
                                st.write(f"**Exposición:** {rh[3]}")
                                st.write(f"**Avances:** {rh[4]}")
                                st.write(f"**Sugerencias:** {rh[5]}")
                                
                                pdf_c = generar_pdf_consejeria(sel_pid, dj_c, rh[0], rh[1], rh[6], rh[7], rh[3], rh[4], rh[5], rh[2])
                                st.download_button(
                                    label=f"🖨️ Descargar PDF Consejería #{rh[0]}",
                                    data=pdf_c,
                                    file_name=f"Consejeria_{rh[0]}_{sel_pid}.pdf",
                                    mime="application/pdf",
                                    key=f"btn_pdf_c_{rh[0]}"
                                )

    # 6. GESTIÓN DE ETAPAS & PROCESO
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Promoción de Proceso")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("Debe haber pacientes registrados.")
        else:
            p_opts = {p["id"]: p["label"] for p in pacientes}
            sel_pid = st.selectbox("Seleccione el Paciente a Evaluar", list(p_opts.keys()), format_func=lambda x: p_opts[x])
            
            dj_p, _, _, _ = obtener_entrevista(sel_pid)
            if dj_p:
                etapa_act = dj_p.get("etapa_actual", "Acogida")
                
                # Cálculo de días en estancia
                f_ing_str = dj_p.get("fecha_ingreso", datetime.now().strftime("%Y-%m-%d"))
                try:
                    dias_estancia = (datetime.now() - datetime.strptime(f_ing_str, "%Y-%m-%d")).days
                except Exception:
                    dias_estancia = 0
                    
                st.subheader(f"Estado Clínico de {dj_p.get('nombre_completo')}")
                st.info(f"📌 Etapa Actual: **{etapa_act}** | Días en Estancia Total: **{dias_estancia} días**")

                # Conteo de Consejerías
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (sel_pid, etapa_act))
                    num_cons_hechas = c.fetchone()[0]
                except Exception:
                    num_cons_hechas = 0
                
                # Conteo de Grupos
                try:
                    c.execute('SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?', (sel_pid, etapa_act))
                    num_grup_hechos = c.fetchone()[0]
                except Exception:
                    num_grup_hechos = 0
                conn.close()

                req_cons = len(CATALOGO_CONSEJERIAS.get(etapa_act, []))
                
                st.markdown("#### Checklist de Requisitos para Cambio de Etapa")
                c_ok1 = num_cons_hechas >= req_cons
                st.write(f"{'✅' if c_ok1 else '❌'} **Consejerías Completadas**: {num_cons_hechas} de {req_cons} requeridas")
                st.write(f"🗣️ **Participación en Grupos Terapéuticos en esta etapa**: {num_grup_hechos} sesiones")

                # Promoción de Etapa
                st.write("---")
                if etapa_act in OPCIONES_ETAPAS:
                    idx_curr = OPCIONES_ETAPAS.index(etapa_act)
                    if idx_curr < len(OPCIONES_ETAPAS) - 1:
                        sig_etapa = OPCIONES_ETAPAS[idx_curr + 1]
                        if c_ok1:
                            st.success(f"🎉 El paciente cumple con las consejerías requeridas para avanzar a **{sig_etapa}**.")
                            if st.button(f"🚀 Promover Paciente a {sig_etapa}"):
                                dj_p["etapa_actual"] = sig_etapa
                                dj_p["fecha_inicio_etapa"] = datetime.now().strftime("%Y-%m-%d")
                                guardar_entrevista(sel_pid, dj_p, st.session_state["username"])
                                st.balloons()
                                st.success(f"¡Paciente promovido con éxito a {sig_etapa}!")
                                st.rerun()
                        else:
                            st.warning(f"⚠️ Para promover a **{sig_etapa}** se requiere completar {req_cons} consejerías individualizadas.")

    # 7. GRUPOS TERAPÉUTICOS
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("Debe registrar pacientes primero.")
        else:
            p_opts = {p["id"]: p["label"] for p in pacientes}
            sel_pid = st.selectbox("Seleccione el Residente Participante", list(p_opts.keys()), format_func=lambda x: p_opts[x])
            
            dj_g, _, _, _ = obtener_entrevista(sel_pid)
            if dj_g:
                with st.form("form_grupo"):
                    t_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Retroalimentación", "Seminario"])
                    f_grupo = st.date_input("Fecha del Grupo", value=datetime.now())
                    des_grupo = st.text_area("Desarrollo de la Participación del Paciente")
                    dev_grupo = st.text_area("Devoluciones e Impresiones del Grupo / Terapeuta")
                    comp_grupo = st.text_area("Compromisos Asumidos")
                    
                    btn_save_g = st.form_submit_button("💾 Guardar Sesión de Grupo")
                    
                    if btn_save_g:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO grupos_terapeuticos 
                            (paciente_id, tipo_grupo, fecha, desarrollo, devoluciones, compromisos, etapa_paciente, usuario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (sel_pid, t_grupo, str(f_grupo), des_grupo, dev_grupo, comp_grupo, dj_g.get("etapa_actual", "Acogida"), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Registro de grupo guardado exitosamente.")

    # 8. CONTROL DE MEDICAMENTOS
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario")
        
        tab_m1, tab_m2, tab_m3 = st.tabs(["📦 Catálogo de Fármacos", "📋 Dosis por Paciente", "🚚 Entrega y Salida de Almacén"])
        
        with tab_m1:
            st.subheader("Gestión de Inventario de Fármacos")
            with st.form("form_nuevo_med"):
                m_nom = st.text_input("Nombre del Medicamento / Miligramos")
                m_stock = st.number_input("Stock Inicial (Unidades/Pastillas)", min_value=0, value=100)
                m_ind = st.text_input("Indicaciones Generales")
                btn_m_save = st.form_submit_button("➕ Agregar al Catálogo")
                
                if btn_m_save:
                    if not m_nom.strip():
                        st.error("Ingrese el nombre del medicamento.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO medicamentos (nombre_medicamento, stock_actual, indicaciones) VALUES (?, ?, ?)',
                                      (m_nom.strip(), m_stock, m_ind))
                            conn.commit()
                            st.success("Medicamento agregado.")
                        except Exception:
                            st.error("El medicamento ya existe.")
                        conn.close()

            # Ver Inventario
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre_medicamento, stock_actual, indicaciones FROM medicamentos')
            meds_list = c.fetchall()
            conn.close()
            
            if meds_list:
                st.dataframe([{"ID": m[0], "Medicamento": m[1], "Stock": m[2], "Indicaciones": m[3]} for m in meds_list], use_container_width=True)

        with tab_m2:
            st.subheader("Asignación de Medicación a Paciente")
            pacientes = listar_pacientes()
            if pacientes and meds_list:
                p_opts = {p["id"]: p["label"] for p in pacientes}
                m_opts = {m[0]: m[1] for m in meds_list}
                
                sel_pid = st.selectbox("Seleccione Paciente", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                sel_med = st.selectbox("Seleccione Medicamento", list(m_opts.keys()), format_func=lambda x: m_opts[x])
                
                with st.form("form_asignar_med"):
                    dosis_in = st.text_input("Dosis (ej. 1 pastilla)")
                    frec_in = st.text_input("Frecuencia (ej. Cada 12 horas)")
                    btn_asig = st.form_submit_button("💾 Asignar Dosis")
                    
                    if btn_asig:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('INSERT INTO medicacion_paciente (paciente_id, medicamento_id, dosis, frecuencia) VALUES (?, ?, ?, ?)',
                                  (sel_pid, sel_med, dosis_in, frec_in))
                        conn.commit()
                        conn.close()
                        st.success("Dosis asignada al paciente.")

        with tab_m3:
            st.subheader("Registro de Entregas y Salida de Almacén")
            if pacientes and meds_list:
                p_opts = {p["id"]: p["label"] for p in pacientes}
                m_opts = {m[0]: f"{m[1]} (Stock: {m[2]})" for m in meds_list}
                
                sel_pid = st.selectbox("Paciente Receptor", list(p_opts.keys()), format_func=lambda x: p_opts[x], key="p_ent")
                sel_med = st.selectbox("Medicamento a Entregar", list(m_opts.keys()), format_func=lambda x: m_opts[x], key="m_ent")
                
                with st.form("form_entrega_med"):
                    cant_ent = st.number_input("Cantidad a Entregar", min_value=1, value=1)
                    btn_entreg = st.form_submit_button("📦 Registrar Entrega")
                    
                    if btn_entreg:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT stock_actual FROM medicamentos WHERE id = ?', (sel_med,))
                        st_act = c.fetchone()[0]
                        
                        if cant_ent > st_act:
                            st.error("❌ No hay suficiente stock en almacén.")
                        else:
                            c.execute('UPDATE medicamentos SET stock_actual = stock_actual - ? WHERE id = ?', (cant_ent, sel_med))
                            f_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, cantidad_entregada, fecha_entrega, usuario) VALUES (?, ?, ?, ?, ?)',
                                      (sel_pid, sel_med, cant_ent, f_hoy, st.session_state["username"]))
                            conn.commit()
                            st.success("✅ Entrega registrada y stock actualizado.")
                        conn.close()

    # 9. REPOSOTORIO DE DOCUMENTOS
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos en la Nube")
        
        tab_r1, tab_r2, tab_r3 = st.tabs(["📄 Documentos Subidos", "📤 Subir Archivo", "📁 Personalizar / Gestionar Carpetas"])
        
        # Obtener Carpetas
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY nombre_carpeta ASC')
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()

        with tab_r1:
            c_filter = st.selectbox("Filtrar por Carpeta", ["Todas"] + carpetas_list)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if c_filter == "Todas":
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, usuario, LENGTH(datos_blob) FROM repositorio_documentos')
            else:
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, usuario, LENGTH(datos_blob) FROM repositorio_documentos WHERE carpeta = ?', (c_filter,))
            docs = c.fetchall()
            conn.close()
            
            if not docs:
                st.info("No hay documentos en esta carpeta.")
            else:
                for d in docs:
                    col_d1, col_d2, col_d3 = st.columns([3, 2, 1])
                    col_d1.write(f"📄 **{d[1]}** ({d[2]})")
                    col_d2.caption(f"Subido por {d[4]} el {d[3]}")
                    
                    # Botón de descarga
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('SELECT datos_blob FROM repositorio_documentos WHERE id = ?', (d[0],))
                    blob_data = c.fetchone()[0]
                    conn.close()
                    
                    col_d3.download_button(
                        label="📥 Descargar",
                        data=blob_data,
                        file_name=d[1],
                        key=f"btn_dl_doc_{d[0]}"
                    )

        with tab_r2:
            st.subheader("Subir Nuevo Documento al Repositorio")
            c_target = st.selectbox("Seleccione Carpeta Destino", carpetas_list)
            file_up = st.file_uploader("Cargar Archivo (PDF, Word, Excel, Imagen)")
            
            if file_up and st.button("📤 Guardar en Repositorio"):
                file_bytes = file_up.read()
                f_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO repositorio_documentos (nombre_archivo, carpeta, datos_blob, fecha_subida, usuario)
                    VALUES (?, ?, ?, ?, ?)
                ''', (file_up.name, c_target, file_bytes, f_hoy, st.session_state["username"]))
                conn.commit()
                conn.close()
                st.balloons()
                st.success("✅ Archivo guardado correctamente en el repositorio.")

        with tab_r3:
            st.subheader("Administración de Carpetas")
            with st.form("form_nueva_carpeta"):
                n_c_nom = st.text_input("Nombre de la Nueva Carpeta")
                btn_nc = st.form_submit_button("➕ Crear Carpeta")
                if btn_nc:
                    if n_c_nom.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (n_c_nom.strip(),))
                            conn.commit()
                            st.success("Carpeta creada.")
                            st.rerun()
                        except Exception:
                            st.error("La carpeta ya existe.")
                        conn.close()

            st.write("---")
            if carpetas_list:
                st.subheader("Renombrar Carpeta Existente")
                c_ren_sel = st.selectbox("Carpeta a Renombrar", carpetas_list)
                c_ren_new = st.text_input("Nuevo Nombre")
                if st.button("✏️ Confirmar Renombrado"):
                    if c_ren_new.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?', (c_ren_new.strip(), c_ren_sel))
                            c.execute('UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?', (c_ren_new.strip(), c_ren_sel))
                            conn.commit()
                            st.success("Carpeta actualizada.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error al renombrar: {ex}")
                        conn.close()

    # 10. BUSCAR Y LISTAR PACIENTES
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Listar Expedientes Generales")
        
        pacientes = listar_pacientes()
        search_q = st.text_input("🔎 Buscar por Nombre, Folio o Expediente")
        
        if search_q:
            q_lower = search_q.lower()
            pacientes = [p for p in pacientes if q_lower in p["nombre"].lower() or q_lower in p["id"].lower() or q_lower in str(p["expediente"]).lower()]
            
        st.subheader(f"Resultados ({len(pacientes)} pacientes encontrados)")
        for p in pacientes:
            with st.expander(f"{p['id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']} [{p['etapa']}]"):
                dj = p["datos"]
                st.write(f"**Edad:** {dj.get('edad', 'N/A')} años | **Sexo:** {dj.get('sexo', 'N/A')}")
                st.write(f"**Fecha Ingreso:** {dj.get('fecha_ingreso', 'N/A')} | **Contacto:** {dj.get('telefono_contacto', 'N/A')}")
                st.write(f"**Responsable:** {dj.get('responsable_nombre', 'N/A')} ({dj.get('responsable_parentesco', 'N/A')})")

    # 11. CONFIGURACIÓN Y SEGURIDAD
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        
        es_admin = (st.session_state.get("username") == "admin") or (str(st.session_state.get("rol")).lower() == "administrador")
        
        if es_admin:
            tab_s1, tab_s2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_s1 = st.container()
            tab_s2 = None

        with tab_s1:
            st.subheader("Cambiar Contraseña")
            with st.form("form_cambio_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_nueva = st.text_input("Nueva Contraseña", type="password")
                p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_pass = st.form_submit_button("Actualizar Contraseña")
                
                if btn_pass:
                    if p_nueva != p_conf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        user_ok = verificar_login(st.session_state["username"], p_act)
                        if user_ok:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(p_nueva), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada.")
                        else:
                            st.error("Contraseña actual incorrecta.")

        if es_admin and tab_s2:
            with tab_s2:
                st.subheader("Registrar Nuevo Usuario de Personal")
                with st.form("form_nuevo_usuario_staff"):
                    u_usr = st.text_input("Nombre de Usuario (Username) *")
                    u_nom = st.text_input("Nombre Completo del Colaborador *")
                    u_pass = st.text_input("Contraseña Inicial *", type="password")
                    u_rol = st.selectbox("Rol y Permisos", ["Lectura/Escritura", "Solo Lectura", "Administrador"])
                    btn_u_save = st.form_submit_button("➕ Crear Cuenta de Usuario")
                    
                    if btn_u_save:
                        if not u_usr.strip() or not u_pass.strip():
                            st.error("Llene los campos obligatorios.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                          (u_usr.strip(), hash_pass(u_pass), u_nom.strip(), u_rol))
                                conn.commit()
                                st.success(f"✅ Usuario '{u_usr}' creado correctamente.")
                                st.rerun()
                            except Exception:
                                st.error("El nombre de usuario ya existe.")
                            conn.close()

                st.write("---")
                st.subheader("Personal Registrado")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol FROM usuarios')
                usrs = c.fetchall()
                conn.close()
                st.dataframe([{"ID": u[0], "Username": u[1], "Nombre Completo": u[2], "Rol": u[3]} for u in usrs], use_container_width=True)

    # 12. RESPALDO Y RESTAURACIÓN
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.info("Descargue su copia de seguridad `.db` regularmente para resguardar todos los pacientes, consejerías y documentos.")
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.subheader("📥 Descargar Respaldo")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                f_nom_bk = f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                st.download_button(
                    label="📥 Descargar Base de Datos (.db)",
                    data=db_bytes,
                    file_name=f_nom_bk,
                    mime="application/x-sqlite3"
                )

        with col_b2:
            st.subheader("📤 Restaurar Respaldo")
            file_db = st.file_uploader("Cargar Archivo .db de Respaldo", type=["db", "sqlite"])
            if file_db and st.button("⚠️ Confirmar Restauración"):
                with open(DB_FILE, "wb") as f:
                    f.write(file_db.read())
                st.balloons()
                st.success("✅ Base de datos restaurada correctamente. Reiniciando...")
                st.rerun()

if __name__ == "__main__":
    main()

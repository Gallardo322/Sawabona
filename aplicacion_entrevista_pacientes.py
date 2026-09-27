import streamlit as st
import sqlite3
import json
import hashlib
import os
import re
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista Inicial y Consejería - Sawabona Shikoba A.C.",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'
        )
    ''')
    
    # Verificar columna rol en usuarios
    c.execute("PRAGMA table_info(usuarios)")
    cols_usr = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'")

    # 2. Tabla de Pacientes Registro Central
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            expediente TEXT,
            nombre TEXT NOT NULL,
            fecha_nac TEXT,
            edad INTEGER,
            sexo TEXT,
            fecha_ingreso TEXT,
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            status TEXT DEFAULT 'ACTIVO'
        )
    ''')
    
    # Verificar columnas en pacientes_registro
    c.execute("PRAGMA table_info(pacientes_registro)")
    cols_pac = [col[1] for col in c.fetchall()]
    if 'expediente' not in cols_pac:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN expediente TEXT")
    if 'folio' not in cols_pac:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN folio TEXT")
    if 'fecha_ingreso' not in cols_pac:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN fecha_ingreso TEXT")
    if 'etapa_actual' not in cols_pac:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN etapa_actual TEXT DEFAULT 'ACOGIDA'")
    if 'fecha_inicio_etapa' not in cols_pac:
        c.execute("ALTER TABLE pacientes_registro ADD COLUMN fecha_inicio_etapa TEXT")

    # 3. Tabla de Entrevistas Clinicas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 4. Tabla Ficha de Ingreso
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # 5. Tabla Consejerias Individuales
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
            usuario_registro TEXT
        )
    ''')

    # 6. Tabla Grupos Terapeuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha TEXT,
            tipo_grupo TEXT,
            desarrollo TEXT,
            devolucion TEXT,
            compromiso TEXT,
            etapa_paciente TEXT,
            usuario_registro TEXT
        )
    ''')
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_grp = [col[1] for col in c.fetchall()]
    if 'etapa_paciente' not in cols_grp:
        c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")

    # 7. Tabla Catalogo Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            existencia INTEGER DEFAULT 0,
            unidad TEXT DEFAULT 'tabletas'
        )
    ''')

    # 8. Tabla Recetas / Medicamentos Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS recetas_pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            horario TEXT,
            fecha_inicio TEXT
        )
    ''')

    # 9. Tabla Entregas Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha_entrega TEXT,
            usuario TEXT
        )
    ''')

    # 10. Tabla Repositorio Documentos
    c.execute('''
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
    ''')

    # 11. Tabla Repositorio Carpetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute("SELECT COUNT(*) FROM repositorio_carpetas")
    if c.fetchone()[0] == 0:
        carpetas_def = [
            '📁 Documentos Generales',
            '📑 Manuales y Reglamentos',
            '📜 Formatos y Contratos',
            '🩺 Fichas Médicas y Psicológicas'
        ]
        for carp in carpetas_def:
            c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (carp,))

    # Usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol) 
            VALUES (?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")

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
    usr = st.session_state.get("username", "")
    rol = st.session_state.get("rol", "")
    return usr == "admin" or "Nivel 1" in str(rol) or "Administrador" in str(rol)

def clean_pdf_text(texto):
    if not texto:
        return ""
    # Reemplazar acentos y caracteres no-latin1
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '', '¡': '', '“': '"', '”': '"', '’': "'", '‘': "'"
    }
    for orig, sub in reemplazos.items():
        texto = texto.replace(orig, sub)
    return texto.encode('latin1', 'ignore').decode('latin1')

# --- CLASE PDF REPORT ---
class PDF_Report(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(26, 82, 118)
        self.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), 0, 1, 'C')
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, clean_pdf_text("Modelo de Tratamiento para Adicciones y Conductas Autodestructivas"), 0, 1, 'C')
        self.line(10, 24, 200, 24)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, clean_pdf_text(f"Página {self.page_no()} | Documento Confidencial de Uso Clínico Interno"), 0, 0, 'C')

def generar_pdf_ficha_ingreso(paciente_row, datos_ficha):
    pdf = PDF_Report()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y ADMISIÓN OFICIAL"), 0, 1, 'C')
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 240, 250)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS DE IDENTIFICACIÓN DEL RESIDENTE"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    
    exp_txt = paciente_row[2] if paciente_row[2] else "S/N"
    pdf.cell(95, 5, clean_pdf_text(f"Expediente No.: {exp_txt}"), 1, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Folio Interno: {paciente_row[1]}"), 1, 1)
    
    pdf.cell(190, 5, clean_pdf_text(f"Nombre Completo: {paciente_row[3]}"), 1, 1)
    pdf.cell(63, 5, clean_pdf_text(f"Edad: {paciente_row[5]} años"), 1, 0)
    pdf.cell(63, 5, clean_pdf_text(f"Fecha Nacimiento: {paciente_row[4]}"), 1, 0)
    pdf.cell(64, 5, clean_pdf_text(f"Sexo: {paciente_row[6]}"), 1, 1)

    pdf.cell(95, 5, clean_pdf_text(f"Estado Civil: {datos_ficha.get('estado_civil', 'N/A')}"), 1, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Escolaridad: {datos_ficha.get('escolaridad', 'N/A')}"), 1, 1)

    pdf.cell(95, 5, clean_pdf_text(f"Ocupacion: {datos_ficha.get('ocupacion', 'N/A')}"), 1, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Religion: {datos_ficha.get('religion', 'N/A')}"), 1, 1)

    pdf.cell(190, 5, clean_pdf_text(f"Domicilio: {datos_ficha.get('calle', '')} #{datos_ficha.get('num_ext', '')}, Col. {datos_ficha.get('colonia', '')}, {datos_ficha.get('municipio', '')}, {datos_ficha.get('estado', '')}"), 1, 1)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. RESPONSABLE FAMILIAR Y TÉRMINOS"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(120, 5, clean_pdf_text(f"Responsable: {datos_ficha.get('responsable_nombre', 'N/A')}"), 1, 0)
    pdf.cell(70, 5, clean_pdf_text(f"Parentesco: {datos_ficha.get('responsable_parentesco', 'N/A')}"), 1, 1)
    pdf.cell(120, 5, clean_pdf_text(f"Telefono de Contacto: {datos_ficha.get('responsable_telefono', 'N/A')}"), 1, 0)
    pdf.cell(70, 5, clean_pdf_text(f"Modalidad: {datos_ficha.get('modalidad_ingreso', 'Voluntario')}"), 1, 1)

    pdf.cell(63, 5, clean_pdf_text(f"Costo Ingreso: ${datos_ficha.get('costo_ingreso', 0):,.2f}"), 1, 0)
    pdf.cell(63, 5, clean_pdf_text(f"Mensualidad: ${datos_ficha.get('costo_mensual', 0):,.2f}"), 1, 0)
    pdf.cell(64, 5, clean_pdf_text(f"Pagare: ${datos_ficha.get('costo_pagare', 0):,.2f}"), 1, 1)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. SUSTANCIAS DE CONSUMO"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    susts = ", ".join(datos_ficha.get('sustancias', [])) if datos_ficha.get('sustancias') else "Ninguna especificada"
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sustancias Consumidas: {susts}"), 1)
    pdf.cell(0, 5, clean_pdf_text(f"Sustancia de Impacto Principal: {datos_ficha.get('sustancia_impacto', 'N/A')}"), 1, 1)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 8)
    pdf.multi_cell(0, 4, clean_pdf_text("DECLARACIÓN Y AUTORIZACIÓN NOM-028-SSA2-2009: El responsable familiar y el residente declaran ingresar de manera voluntaria y en pleno conocimiento de los reglamentos, estatutos y costos del establecimiento Sawabona Shikoba A.C."), 1)
    
    pdf.ln(18)
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 1, 'C')
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(90, 4, clean_pdf_text("Firma del Responsable Familiar"), 0, 0, 'C')
    pdf.cell(10, 4, "", 0, 0)
    pdf.cell(90, 4, clean_pdf_text("Director / Encargado de Establecimiento"), 0, 1, 'C')

    return bytes(pdf.output())

def generar_pdf_consejeria(paciente_row, cons_data):
    pdf = PDF_Report()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, clean_pdf_text("REPORTE DE SESIÓN DE CONSEJERÍA INDIVIDUAL"), 0, 1, 'C')
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS GENERALES DEL RESIDENTE"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    
    exp_txt = paciente_row[2] if paciente_row[2] else "S/N"
    pdf.cell(95, 5, clean_pdf_text(f"EXPEDIENTE: {exp_txt}"), 1, 0)
    pdf.cell(95, 5, clean_pdf_text(f"FECHA DE SESION: {cons_data['fecha']}"), 1, 1)

    pdf.cell(120, 5, clean_pdf_text(f"NOMBRE: {paciente_row[3]}"), 1, 0)
    pdf.cell(35, 5, clean_pdf_text(f"EDAD: {paciente_row[5]} anos"), 1, 0)
    pdf.cell(35, 5, clean_pdf_text(f"SEXO: {paciente_row[6]}"), 1, 1)

    pdf.cell(95, 5, clean_pdf_text(f"ETAPA ACTUAL: {cons_data['etapa']}"), 1, 0)
    pdf.cell(95, 5, clean_pdf_text(f"CONSEJERIA NO.: {cons_data['num_consejeria']}"), 1, 1)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. OBJETIVOS Y TEMAS TRABAJADOS"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspectos Trabajados: {cons_data['aspectos_trabajar']}"), 1)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Proxima Consejeria Sugerida: {cons_data['aspectos_proxima']}"), 1)
    pdf.cell(0, 5, clean_pdf_text(f"Fecha Programada Proxima Consejeria: {cons_data['fecha_proxima']}"), 1, 1)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. NOTAS DE EVOLUCIÓN CLÍNICA Y TAREAS"), 1, 1, 'L', True)
    pdf.set_font("Helvetica", "", 9)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Exposicion del Paciente / Notas compartidas:"), 0, 1)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(cons_data['exposicion'] or "Sin notas registradas"), 1)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Avance / Retroceso (Observaciones de Evolucion):"), 0, 1)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(cons_data['avance'] or "Sin observaciones registradas"), 1)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Sugerencias y Compromisos Asignados:"), 0, 1)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(cons_data['sugerencia'] or "Sin compromisos registrados"), 1)
    pdf.ln(15)

    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, clean_pdf_text("__________________________________________"), 0, 1, 'C')
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(90, 4, clean_pdf_text("Firma del Consejero / Terapeuta"), 0, 0, 'C')
    pdf.cell(10, 4, "", 0, 0)
    pdf.cell(90, 4, clean_pdf_text("Firma de Conformidad del Residente"), 0, 1, 'C')

    return bytes(pdf.output())

# --- DICCIONARIO DE CONSEJERÍAS SECUENCIALES ---
CONSEJERIAS_POR_ETAPA = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "IDENTIFICACION": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "ELABORACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJRIA) PREVENCIÓN DE RECAÍDAS.",
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
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- APLICACIÓN PRINCIPAL STREAMLIT ---
def main():
    init_db()

    # --- CONTROL DE INACTIVIDAD (10 MINUTOS = 600 SEG) ---
    ahora_ts = datetime.now().timestamp()
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = ahora_ts

    # Verificar si pasaron mas de 600 segundos (10 mins)
    if st.session_state["logged_in"]:
        if ahora_ts - st.session_state["ultima_actividad"] > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión nuevamente.")
            st.rerun()
        else:
            st.session_state["ultima_actividad"] = ahora_ts

    # Script JavaScript para resetear timeout por movimiento de mouse o teclado
    st.components.v1.html("""
        <script>
        var timeout = 600000; // 10 minutos en milisegundos
        var timer;
        function resetTimer() {
            clearTimeout(timer);
            timer = setTimeout(function() {
                window.parent.postMessage({type: 'streamlit:render'}, '*');
            }, timeout);
        }
        window.onload = resetTimer;
        document.onmousemove = resetTimer;
        document.onkeypress = resetTimer;
        document.onclick = resetTimer;
        document.onscroll = resetTimer;
        </script>
    """, height=0)

    # --- PANTALLA DE LOGIN ---
    if not st.session_state["logged_in"]:
        st.title("🔒 Sistema Clinico de Consejeria - Sawabona Shikoba")
        st.markdown("Por favor ingrese sus credenciales de acceso institucional.")
        
        col_c1, col_c2, col_c3 = st.columns([1, 2, 1])
        with col_c2:
            with st.form("login_form"):
                user_input = st.text_input("Usuario")
                pass_input = st.text_input("Contrasena", type="password")
                btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                
                if btn_login:
                    res = verificar_login(user_input, pass_input)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2]
                        st.session_state["ultima_actividad"] = datetime.now().timestamp()
                        st.balloons()
                        st.toast(f"¡Bienvenido(a) {res[1]}!")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos.")
            st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
        return

    # --- BARRA LATERAL (SIDEBAR) Y MENÚ ---
    st.sidebar.title("📋 Control Clinico")
    st.sidebar.caption(f"👤 **{st.session_state['nombre_completo']}**")
    st.sidebar.caption(f"🛡️ Rol: `{st.session_state.get('rol', 'Usuario')}`")
    
    opciones_menu = [
        "👤 Registro y Edicion de Pacientes",
        "📄 Ficha de Ingreso y Admision",
        "📝 Entrevista Inicial de Consejeria",
        "📝 Consejerias Individuales",
        "🎯 Gestion de Etapas & Proceso",
        "🗣️ Grupos Terapeuticos",
        "💊 Control de Medicamentos",
        "📁 Repositorio de Documentos",
        "🔍 Buscar y Listar Pacientes",
        "⚙️ Configuracion y Seguridad",
        "📦 Respaldo y Restauracion"
    ]
    
    menu = st.sidebar.radio("Navegación", opciones_menu)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesion", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # =========================================================================
    # 1. MÓDULO: REGISTRO Y EDICIÓN DE PACIENTES
    # =========================================================================
    if menu == "👤 Registro y Edicion de Pacientes":
        st.title("👤 Registro y Edición de Pacientes (Residentes)")
        st.markdown("Gestión centralizada del catálogo de pacientes y fechas de etapa.")

        tab1, tab2 = st.tabs(["➕ Registrar Nuevo Paciente", "✏️ Editar Paciente Existente"])

        with tab1:
            st.subheader("Alta de Nuevo Residente")
            c.execute("SELECT MAX(id) FROM pacientes_registro")
            max_id = c.fetchone()[0] or 0
            folio_sugerido = f"PAC-{max_id + 1:03d}"

            with st.form("form_alta_paciente"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.text_input("Folio Interno (Autoincrementable)", value=folio_sugerido, disabled=True)
                    f_expediente = st.text_input("Expediente (Manual y Único)", help="Dejar en blanco si aún no tiene asignado expediente físico.")
                    f_nombre = st.text_input("Nombre Completo del Residente *")
                with col2:
                    f_fecha_nac = st.date_input("Fecha de Nacimiento", value=date(1995, 1, 1))
                    edad_calc = (date.today() - f_fecha_nac).days // 365
                    st.number_input("Edad Calculada", value=edad_calc, disabled=True)
                    f_sexo = st.selectbox("Sexo", ["Masculino", "Femenino"])
                with col3:
                    f_ingreso = st.date_input("Fecha de Ingreso Real", value=date.today())
                    f_etapa = st.selectbox("Etapa Inicial", ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"])
                    f_inicio_etapa = st.date_input("Fecha de Inicio en la Etapa", value=date.today())

                btn_alta = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)

                if btn_alta:
                    if not f_nombre.strip():
                        st.error("⚠️ El nombre del residente es obligatorio.")
                    else:
                        exp_val = f_expediente.strip() if f_expediente.strip() else None
                        if exp_val:
                            c.execute("SELECT id FROM pacientes_registro WHERE expediente = ?", (exp_val,))
                            if c.fetchone():
                                st.error(f"⚠️ El número de Expediente '{exp_val}' ya está asignado a otro residente.")
                                conn.close()
                                return

                        c.execute('''
                            INSERT INTO pacientes_registro 
                            (folio, expediente, nombre, fecha_nac, edad, sexo, fecha_ingreso, etapa_actual, fecha_inicio_etapa, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO')
                        ''', (folio_sugerido, exp_val, f_nombre.strip(), str(f_fecha_nac), edad_calc, f_sexo, str(f_ingreso), f_etapa, str(f_inicio_etapa)))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Paciente registrado exitosamente!")
                        st.success(f"Residente registrado con Folio: {folio_sugerido}")

        with tab2:
            st.subheader("Modificar Datos de Residente")
            c.execute("SELECT id, folio, expediente, nombre, fecha_nac, edad, sexo, fecha_ingreso, etapa_actual, fecha_inicio_etapa FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
            pacientes_list = c.fetchall()

            if not pacientes_list:
                st.info("No hay pacientes activos registrados.")
            else:
                opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]}": p for p in pacientes_list}
                sel_p_txt = st.selectbox("Seleccionar Residente a Editar", list(opciones_p.keys()))
                p_data = opciones_p[sel_p_txt]

                with st.form("form_edit_paciente"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.text_input("Folio (No editable)", value=p_data[1], disabled=True)
                        e_expediente = st.text_input("Expediente", value=p_data[2] or "")
                        e_nombre = st.text_input("Nombre Completo", value=p_data[3])
                    with col2:
                        try:
                            fn_val = datetime.strptime(p_data[4], "%Y-%m-%d").date() if p_data[4] else date(1995, 1, 1)
                        except:
                            fn_val = date(1995, 1, 1)
                        e_fecha_nac = st.date_input("Fecha de Nacimiento", value=fn_val)
                        e_edad = (date.today() - e_fecha_nac).days // 365
                        e_sexo = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if p_data[6]=="Masculino" else 1)
                    with col3:
                        try:
                            fi_val = datetime.strptime(p_data[7], "%Y-%m-%d").date() if p_data[7] else date.today()
                        except:
                            fi_val = date.today()
                        e_ingreso = st.date_input("Fecha de Ingreso Real", value=fi_val)
                        
                        etapas_opts = ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"]
                        idx_et = etapas_opts.index(p_data[8]) if p_data[8] in etapas_opts else 0
                        e_etapa = st.selectbox("Etapa Actual", etapas_opts, index=idx_et)

                        try:
                            fie_val = datetime.strptime(p_data[9], "%Y-%m-%d").date() if p_data[9] else date.today()
                        except:
                            fie_val = date.today()
                        e_inicio_etapa = st.date_input("Fecha de Inicio de Etapa Actual", value=fie_val)

                    btn_edit = st.form_submit_button("🔄 Actualizar Datos del Residente", use_container_width=True)

                    if btn_edit:
                        exp_val = e_expediente.strip() if e_expediente.strip() else None
                        if exp_val and exp_val != p_data[2]:
                            c.execute("SELECT id FROM pacientes_registro WHERE expediente = ? AND id != ?", (exp_val, p_data[0]))
                            if c.fetchone():
                                st.error(f"⚠️ El número de Expediente '{exp_val}' ya pertenece a otro residente.")
                                conn.close()
                                return

                        c.execute('''
                            UPDATE pacientes_registro 
                            SET expediente = ?, nombre = ?, fecha_nac = ?, edad = ?, sexo = ?, fecha_ingreso = ?, etapa_actual = ?, fecha_inicio_etapa = ?
                            WHERE id = ?
                        ''', (exp_val, e_nombre.strip(), str(e_fecha_nac), e_edad, e_sexo, str(e_ingreso), e_etapa, str(e_inicio_etapa), p_data[0]))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Datos actualizados correctamente!")
                        st.success("Información del residente actualizada.")

    # =========================================================================
    # 2. MÓDULO: FICHA DE INGRESO Y ADMISIÓN (NOM-028)
    # =========================================================================
    elif menu == "📄 Ficha de Ingreso y Admision":
        st.title("📄 Ficha de Ingreso y Contrato de Admisión")
        st.markdown("Captura oficial de contrato de internamiento en apego a la norma **NOM-028-SSA2-2009**.")

        c.execute("SELECT id, folio, expediente, nombre, fecha_nac, edad, sexo FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
        pacientes_list = c.fetchall()

        if not pacientes_list:
            st.warning("⚠️ No hay pacientes activos registrados. Por favor registre un residente primero.")
        else:
            opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]}": p for p in pacientes_list}
            sel_p_txt = st.selectbox("Seleccionar Residente para Ficha de Ingreso", list(opciones_p.keys()))
            p_sel = opciones_p[sel_p_txt]
            p_id_str = str(p_sel[0])

            c.execute("SELECT datos_json FROM ficha_ingreso WHERE paciente_id = ?", (p_id_str,))
            row_f = c.fetchone()
            d_f = json.loads(row_f[0]) if row_f else {}

            tab_f1, tab_f2 = st.tabs(["📝 Formulario de Ficha de Ingreso", "🖨️ Ver e Imprimir Ficha PDF"])

            with tab_f1:
                with st.form("form_ficha_ingreso"):
                    st.subheader("1. Datos del Responsable Familiar")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        resp_nombre = st.text_input("Nombre del Responsable Familiar *", value=d_f.get("responsable_nombre", ""))
                    with col2:
                        resp_parentesco = st.selectbox("Parentesco", ["Padre", "Madre", "Cónyuge", "Hermano(a)", "Hijo(a)", "Tutor Legal", "Otro"], index=0)
                    with col3:
                        resp_tel = st.text_input("Teléfono de Contacto *", value=d_f.get("responsable_telefono", ""))

                    st.subheader("2. Datos Complementarios del Residente")
                    col4, col5, col6 = st.columns(3)
                    with col4:
                        est_civil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                        escolaridad = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria / Bachillerato", "Licenciatura", "Postgrado", "Ninguna"], index=2)
                    with col5:
                        ocupacion = st.text_input("Ocupación Habitual", value=d_f.get("ocupacion", ""))
                        religion = st.text_input("Religión", value=d_f.get("religion", "Católica"))
                    with col6:
                        serv_medico = st.selectbox("Servicio Médico", ["IMSS", "ISSSTE", "INSABI / IMSS BIENESTAR", "Particular", "Ninguno"], index=3)

                    st.markdown("**Domicilio Completo:**")
                    col_d1, col_d2, col_d3 = st.columns(3)
                    with col_d1:
                        calle = st.text_input("Calle y Número", value=d_f.get("calle", ""))
                        colonia = st.text_input("Colonia", value=d_f.get("colonia", ""))
                    with col_d2:
                        municipio = st.text_input("Municipio / Alcaldía", value=d_f.get("municipio", ""))
                        estado_dom = st.text_input("Estado", value=d_f.get("estado", "Jalisco"))
                    with col_d3:
                        cp_dom = st.text_input("Código Postal", value=d_f.get("cp", ""))

                    st.subheader("3. Sustancias de Consumo")
                    opts_sust = ["Alcohol", "Cannabis (Marihuana)", "Metanfetaminas (Cristal)", "Cocaína", "Tabaco", "Benzodiazepinas", "Inhalables", "Heroína / Opiáceos", "Otros"]
                    sust_selected = st.multiselect("Sustancias Consumidas", opts_sust, default=d_f.get("sustancias", ["Alcohol", "Metanfetaminas (Cristal)"]))
                    sust_impacto = st.selectbox("Sustancia de Impacto Principal", opts_sust, index=2)

                    st.subheader("4. Términos Financieros y Modalidad")
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        c_ingreso = st.number_input("Costo de Ingreso ($)", value=float(d_f.get("costo_ingreso", 4500.0)))
                        c_mensual = st.number_input("Mensualidad ($)", value=float(d_f.get("costo_mensual", 6000.0)))
                    with col_t2:
                        c_pagare = st.number_input("Importe de Pagaré ($)", value=float(d_f.get("costo_pagare", 42000.0)))
                        modalidad = st.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario (NOM-028)"], index=0)
                    with col_t3:
                        sucursal = st.text_input("Sucursal / Clinica", value=d_f.get("sucursal", "Sawabona Shikoba Principal"))

                    btn_guardar_f = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)

                    if btn_guardar_f:
                        datos_a_guardar = {
                            "responsable_nombre": resp_nombre,
                            "responsable_parentesco": resp_parentesco,
                            "responsable_telefono": resp_tel,
                            "estado_civil": est_civil,
                            "escolaridad": escolaridad,
                            "ocupacion": ocupacion,
                            "religion": religion,
                            "servicio_medico": serv_medico,
                            "calle": calle,
                            "colonia": colonia,
                            "municipio": municipio,
                            "estado": estado_dom,
                            "cp": cp_dom,
                            "sustancias": sust_selected,
                            "sustancia_impacto": sust_impacto,
                            "costo_ingreso": c_ingreso,
                            "costo_mensual": c_mensual,
                            "costo_pagare": c_pagare,
                            "modalidad_ingreso": modalidad,
                            "sucursal": sucursal
                        }
                        
                        f_json = json.dumps(datos_a_guardar, ensure_ascii=False)
                        f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        c.execute("INSERT OR REPLACE INTO ficha_ingreso (paciente_id, datos_json, fecha_registro, usuario_registro) VALUES (?, ?, ?, ?)",
                                  (p_id_str, f_json, f_now, st.session_state["username"]))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Ficha de ingreso guardada exitosamente!")
                        st.success("Ficha guardada correctamente. Puede pasar a la pestaña de impresión.")

            with tab_f2:
                st.subheader("Vista Previa y Descarga de Ficha en PDF")
                if not d_f:
                    st.info("Aún no se ha capturado el formulario de la ficha de ingreso para este paciente.")
                else:
                    pdf_bytes = generar_pdf_ficha_ingreso(p_sel, d_f)
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso Oficial en PDF",
                        data=pdf_bytes,
                        file_name=f"Ficha_Ingreso_{p_sel[1]}_{p_sel[3].replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # =========================================================================
    # 3. MÓDULO: ENTREVISTA INICIAL DE CONSEJERÍA
    # =========================================================================
    elif menu == "📝 Entrevista Inicial de Consejeria":
        st.title("📝 Entrevista Inicial de Consejería")
        st.markdown("Evaluación clínica integral del historial de consumo, dinámica familiar y plan de tratamiento.")

        c.execute("SELECT id, folio, expediente, nombre, fecha_nac, edad, sexo FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
        pacientes_list = c.fetchall()

        if not pacientes_list:
            st.warning("⚠️ No hay pacientes activos registrados.")
        else:
            opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]}": p for p in pacientes_list}
            sel_p_txt = st.selectbox("Seleccionar Residente para Entrevista Inicial", list(opciones_p.keys()))
            p_sel = opciones_p[sel_p_txt]
            p_id_str = str(p_sel[0])

            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (p_id_str,))
            row_e = c.fetchone()
            d_e = json.loads(row_e[0]) if row_e else {}

            with st.form("form_entrevista_inicial"):
                st.subheader("1. Historial de Consumo y Diagnóstico de Adicción")
                col1, col2 = st.columns(2)
                with col1:
                    e_edad_inicio = st.number_input("Edad de Primer Consumo (Años)", value=int(d_e.get("edad_inicio", 15)))
                    e_motivo_cons = st.text_area("Motivo o Detonante Principal de Consumo", value=d_e.get("motivo_consumo", ""))
                with col2:
                    e_patron = st.selectbox("Patrón de Consumo", ["Diario / Continuo", "Fin de Semana / Fiestas", "Por Baches / Periodos", "Experimental"], index=0)
                    e_intentos = st.number_input("Número de Anexos / Tratamientos Previos", value=int(d_e.get("intentos_previos", 0)))

                st.subheader("2. Evaluación Familiar y Social")
                col3, col4 = st.columns(2)
                with col3:
                    e_red_apoyo = st.text_area("Red de Apoyo Familiar Principal", value=d_e.get("red_apoyo", ""))
                with col4:
                    e_antecedentes = st.text_area("Antecedentes de Adicción o Psiquiatría en la Familia", value=d_e.get("antecedentes_fam", ""))

                st.subheader("3. Diagnóstico y Plan Inicial de Consejería")
                e_observaciones = st.text_area("Observaciones Clínicas del Consejero", value=d_e.get("observaciones", ""), height=100)
                e_plan_inicial = st.text_area("Plan Inicial de Trabajo Recomendado", value=d_e.get("plan_inicial", ""), height=100)

                btn_guardar_e = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)

                if btn_guardar_e:
                    datos_e_save = {
                        "edad_inicio": e_edad_inicio,
                        "motivo_consumo": e_motivo_cons,
                        "patron_consumo": e_patron,
                        "intentos_previos": e_intentos,
                        "red_apoyo": e_red_apoyo,
                        "antecedentes_fam": e_antecedentes,
                        "observaciones": e_observaciones,
                        "plan_inicial": e_plan_inicial
                    }
                    e_json = json.dumps(datos_e_save, ensure_ascii=False)
                    e_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    c.execute("INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)",
                              (p_id_str, e_now, e_now, st.session_state["username"], e_json))
                    conn.commit()
                    st.balloons()
                    st.toast("✅ ¡Entrevista inicial guardada exitosamente!")
                    st.success("Entrevista clínica registrada.")

    # =========================================================================
    # 4. MÓDULO: CONSEJERÍAS INDIVIDUALES (DINÁMICO Y REACTIVO)
    # =========================================================================
    elif menu == "📝 Consejerias Individuales":
        st.title("📝 Registro de Consejerías Individuales")
        st.markdown("Seguimiento secuencial de temas y evaluación de avances por consejería.")

        c.execute("SELECT id, folio, expediente, nombre, fecha_nac, edad, sexo, etapa_actual FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
        pacientes_list = c.fetchall()

        if not pacientes_list:
            st.warning("⚠️ No hay pacientes activos registrados.")
        else:
            opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]} (Etapa: {p[7]})": p for p in pacientes_list}
            sel_p_txt = st.selectbox("Seleccionar Residente", list(opciones_p.keys()))
            p_sel = opciones_p[sel_p_txt]
            p_id_str = str(p_sel[0])
            exp_paciente_actual = p_sel[2] or "S/N"
            etapa_act = p_sel[7]

            st.info(f"📌 **Etapa Activa del Residente**: `{etapa_act}` | **Expediente**: `{exp_paciente_actual}`")

            temas_etapa = CONSEJERIAS_POR_ETAPA.get(etapa_act, [])
            if not temas_etapa:
                st.error("No se encontraron consejerías configuradas para la etapa actual.")
            else:
                # Consultar consejerias ya capturadas
                c.execute("SELECT num_consejeria FROM consejerias WHERE paciente_id = ? AND etapa = ? ORDER BY num_consejeria ASC", (p_id_str, etapa_act))
                cons_grabadas = [r[0] for r in c.fetchall()]

                # Determinar default num
                default_num = 1
                if cons_grabadas:
                    max_grabada = max(cons_grabadas)
                    if max_grabada < len(temas_etapa):
                        default_num = max_grabada + 1
                    else:
                        default_num = len(temas_etapa)

                # Selector de numero de consejeria
                opciones_cons_num = [f"Consejería #{i+1}: {temas_etapa[i]}" for i in range(len(temas_etapa))]
                
                sel_cons_txt = st.selectbox(
                    "Seleccionar Número de Consejería a Trabajar/Consultar",
                    opciones_cons_num,
                    index=default_num - 1,
                    key=f"sel_cons_idx_{p_id_str}_{etapa_act}"
                )
                
                num_cons_sel = opciones_cons_num.index(sel_cons_txt) + 1

                # REACCION REACTIVA: Cargar datos de la BD o poner en blanco si NO existe
                c.execute('''
                    SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                    FROM consejerias
                    WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                ''', (p_id_str, etapa_act, num_cons_sel))
                row_c_exist = c.fetchone()

                if row_c_exist:
                    val_asp_trabajar = row_c_exist[0]
                    val_asp_prox = row_c_exist[1]
                    try:
                        val_f_prox = datetime.strptime(row_c_exist[2], "%Y-%m-%d").date()
                    except:
                        val_f_prox = date.today() + timedelta(days=7)
                    val_exposicion = row_c_exist[3] or ""
                    val_avance = row_c_exist[4] or ""
                    val_sugerencia = row_c_exist[5] or ""
                    val_fecha_sesion = row_c_exist[6] or datetime.now().strftime("%Y-%m-%d")
                    status_msg = "ℹ️ **Esta consejería ya fue capturada anteriormente. Puede modificar sus datos a continuación.**"
                else:
                    val_asp_trabajar = temas_etapa[num_cons_sel - 1]
                    val_asp_prox = temas_etapa[num_cons_sel] if num_cons_sel < len(temas_etapa) else "Finalización de Temas de Etapa"
                    val_f_prox = date.today() + timedelta(days=7)
                    val_exposicion = ""
                    val_avance = ""
                    val_sugerencia = ""
                    val_fecha_sesion = datetime.now().strftime("%Y-%m-%d")
                    status_msg = "🆕 **Esta consejería no ha sido capturada aún. Los campos de texto están limpios para su llenado.**"

                st.markdown(status_msg)

                # Clave dinamica unica para forzar re-render de Streamlit cuando cambia num_cons_sel
                key_suf = f"{p_id_str}_{etapa_act}_{num_cons_sel}"

                with st.form(f"form_consejeria_{key_suf}"):
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        st.text_input("Expediente", value=exp_paciente_actual, disabled=True)
                        st.text_input("Fecha de Sesión", value=val_fecha_sesion, disabled=True)
                    with col_c2:
                        st.text_area("Aspectos a Trabajar (Tema Oficial)", value=val_asp_trabajar, height=80, disabled=True)
                    with col_c3:
                        c_asp_prox = st.text_input("Próximo Tema Sugerido", value=val_asp_prox, key=f"prox_{key_suf}")
                        c_f_prox = st.date_input("Fecha de Próxima Consejería (+7 Días)", value=val_f_prox, key=f"fprox_{key_suf}")

                    st.markdown("---")
                    c_exposicion = st.text_area("Exposición del Paciente (Notas compartidas por el residente) *", value=val_exposicion, height=120, key=f"exp_{key_suf}")
                    c_avance = st.text_area("Avance / Retroceso (Observaciones de evolución clínica) *", value=val_avance, height=100, key=f"ava_{key_suf}")
                    c_sugerencia = st.text_area("Sugerencia (Tareas, acuerdos y compromisos asignados) *", value=val_sugerencia, height=100, key=f"sug_{key_suf}")

                    btn_save_c = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)

                    if btn_save_c:
                        c.execute("DELETE FROM consejerias WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?",
                                  (p_id_str, etapa_act, num_cons_sel))
                        
                        c.execute('''
                            INSERT INTO consejerias 
                            (paciente_id, expediente, etapa, num_consejeria, fecha, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, usuario_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (p_id_str, exp_paciente_actual, etapa_act, num_cons_sel, val_fecha_sesion, val_asp_trabajar, c_asp_prox, str(c_f_prox), c_exposicion, c_avance, c_sugerencia, st.session_state["username"]))
                        
                        conn.commit()
                        st.balloons()
                        st.toast(f"✅ ¡Consejería #{num_cons_sel} guardada exitosamente!")
                        st.success(f"Sesión de consejería #{num_cons_sel} guardada correctamente.")
                        st.rerun()

                # Boton de impresion PDF
                if row_c_exist or 'btn_save_c' in locals():
                    st.markdown("---")
                    st.subheader("🖨️ Documento Impreso en PDF")
                    cons_data_pdf = {
                        "etapa": etapa_act,
                        "num_consejeria": num_cons_sel,
                        "fecha": val_fecha_sesion,
                        "aspectos_trabajar": val_asp_trabajar,
                        "aspectos_proxima": c_asp_prox if 'c_asp_prox' in locals() else val_asp_prox,
                        "fecha_proxima": str(c_f_prox) if 'c_f_prox' in locals() else str(val_f_prox),
                        "exposicion": c_exposicion if 'c_exposicion' in locals() else val_exposicion,
                        "avance": c_avance if 'c_avance' in locals() else val_avance,
                        "sugerencia": c_sugerencia if 'c_sugerencia' in locals() else val_sugerencia
                    }
                    pdf_c_bytes = generar_pdf_consejeria(p_sel, cons_data_pdf)
                    st.download_button(
                        label=f"🖨️ Descargar Hoja de Consejería #{num_cons_sel} en PDF",
                        data=pdf_c_bytes,
                        file_name=f"Consejeria_{num_cons_sel}_{p_sel[1]}_{p_sel[3].replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # =========================================================================
    # 5. MÓDULO: GESTIÓN DE ETAPAS & PROCESO
    # =========================================================================
    elif menu == "🎯 Gestion de Etapas & Proceso":
        st.title("🎯 Evaluación de Etapas y Control de Rezagos")
        st.markdown("Monitoreo en tiempo real de días en comunidad, estancamiento y checklist de promoción.")

        c.execute("SELECT id, folio, expediente, nombre, fecha_ingreso, etapa_actual, fecha_inicio_etapa FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
        pacientes_list = c.fetchall()

        if not pacientes_list:
            st.warning("No hay pacientes activos.")
        else:
            opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]} (Etapa: {p[5]})": p for p in pacientes_list}
            sel_p_txt = st.selectbox("Seleccionar Residente para Diagnostico", list(opciones_p.keys()))
            p_sel = opciones_p[sel_p_txt]
            p_id_str = str(p_sel[0])

            # Duraciones estimadas por etapa
            duracion_etapa = {"ACOGIDA": 30, "IDENTIFICACION": 60, "ELABORACION": 60, "CONSOLIDACION": 30, "SERVICIO SOCIAL": 30}
            
            # Calculo de dias
            try:
                f_ing = datetime.strptime(p_sel[4], "%Y-%m-%d").date()
            except:
                f_ing = date.today()
            try:
                f_iet = datetime.strptime(p_sel[6], "%Y-%m-%d").date()
            except:
                f_iet = date.today()

            dias_comunidad = (date.today() - f_ing).days
            dias_etapa = (date.today() - f_iet).days
            dur_max = duracion_etapa.get(p_sel[5], 30)

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("🗓️ Días Totales en Comunidad", f"{dias_comunidad} días")
            with col_m2:
                st.metric("⏱️ Días en Etapa Actual", f"{dias_etapa} días", f"Máximo estimado: {dur_max} días")
            with col_m3:
                st.metric("📌 Etapa Activa", p_sel[5])

            # Alerta de Rezago
            if dias_etapa > dur_max:
                exceso = dias_etapa - dur_max
                st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El residente lleva **{dias_comunidad} días internado** y suma **{dias_etapa} días en la etapa {p_sel[5]}** (Duración recomendada: {dur_max} días). Se ha excedido por **+{exceso} días**.")

            st.markdown("---")
            st.subheader("📋 Checklist Clínico para Promoción de Etapa")

            # Conteo de consejerias en esta etapa
            c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?", (p_id_str, p_sel[5]))
            num_cons_hechas = c.fetchone()[0]
            num_cons_req = len(CONSEJERIAS_POR_ETAPA.get(p_sel[5], []))

            # Conteo de grupos en esta etapa con proteccion
            try:
                c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?", (p_id_str, p_sel[5]))
                num_grupos = c.fetchone()[0]
            except:
                num_grupos = 0

            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                st.markdown("**1. Requisitos Cuantitativos de la Etapa:**")
                if num_cons_hechas >= num_cons_req:
                    st.success(f"✅ **Consejerías Individuales**: {num_cons_hechas} / {num_cons_req} completadas.")
                else:
                    st.warning(f"❌ **Consejerías Individuales**: {num_cons_hechas} / {num_cons_req} completadas (Faltan {num_cons_req - num_cons_hechas}).")

                st.info(f"🗣️ **Grupos Terapéuticos Registrados**: {num_grupos} sesiones en esta etapa.")

            with col_chk2:
                st.markdown("**2. Evaluación Cualitativa:**")
                chk_autobio = st.checkbox("Autobiografía / Historia de Vida Entregada", value=True)
                chk_reglas = st.checkbox("Aceptación y Cumplimiento de Reglas de Convivencia", value=True)
                chk_eval_comite = st.checkbox("Aprobación del Comité Clínico de Consejería", value=(num_cons_hechas >= num_cons_req))

            st.markdown("---")
            siguiente_etapa_dict = {
                "ACOGIDA": "IDENTIFICACION",
                "IDENTIFICACION": "ELABORACION",
                "ELABORACION": "CONSOLIDACION",
                "CONSOLIDACION": "SERVICIO SOCIAL",
                "SERVICIO SOCIAL": "EGRESADO"
            }
            sig_et = siguiente_etapa_dict.get(p_sel[5], "EGRESADO")

            puedes_promover = (num_cons_hechas >= num_cons_req) and chk_eval_comite
            if st.button(f"🎉 Promover Residente a Etapa: {sig_et}", disabled=not puedes_promover, use_container_width=True):
                hoy_str = str(date.today())
                c.execute("UPDATE pacientes_registro SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE id = ?", (sig_et, hoy_str, p_sel[0]))
                conn.commit()
                st.balloons()
                st.toast(f"¡Residente promovido a {sig_et}!")
                st.success(f"Residente promovido exitosamente a {sig_et}.")
                st.rerun()

    # =========================================================================
    # 6. MÓDULO: GRUPOS TERAPÉUTICOS
    # =========================================================================
    elif menu == "🗣️ Grupos Terapeuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.markdown("Captura de asistencias y participación en *Terapia de Grupo*, *Aquí y Ahora* y *Feedback*.")

        c.execute("SELECT id, folio, expediente, nombre, etapa_actual FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
        pacientes_list = c.fetchall()

        if not pacientes_list:
            st.warning("No hay pacientes activos.")
        else:
            opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]}": p for p in pacientes_list}
            sel_p_txt = st.selectbox("Seleccionar Residente", list(opciones_p.keys()))
            p_sel = opciones_p[sel_p_txt]
            p_id_str = str(p_sel[0])

            with st.form("form_grupo_terapeuta"):
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    g_tipo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo / Proceso", "Aquí y Ahora", "Grupo de Feedback / Confrontación", "Seminario Terapéutico"])
                    g_fecha = st.date_input("Fecha del Grupo", value=date.today())
                with col_g2:
                    st.text_input("Etapa del Paciente al Momento del Grupo", value=p_sel[4], disabled=True)

                g_desarrollo = st.text_area("Desarrollo / Participación del Residente en la Sesión", height=100)
                g_devolucion = st.text_area("Devolución Terapéutica / Observaciones del Staff", height=100)
                g_compromiso = st.text_area("Compromiso Asignado al Residente", height=80)

                btn_g_save = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)

                if btn_g_save:
                    c.execute('''
                        INSERT INTO grupos_terapeuticos 
                        (paciente_id, fecha, tipo_grupo, desarrollo, devolucion, compromiso, etapa_paciente, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p_id_str, str(g_fecha), g_tipo, g_desarrollo, g_devolucion, g_compromiso, p_sel[4], st.session_state["username"]))
                    conn.commit()
                    st.balloons()
                    st.toast("✅ ¡Registro de grupo guardado!")
                    st.success("Sesión de grupo registrada correctamente.")

    # =========================================================================
    # 7. MÓDULO: CONTROL DE MEDICAMENTOS E INVENTARIO
    # =========================================================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario de Almacén")
        
        tab_m1, tab_m2, tab_m3 = st.tabs(["📦 Entregas Diarias", "💊 Recetas por Paciente", "🏛️ Catálogo de Almacén"])

        with tab_m1:
            st.subheader("Registrar Entrega Diaria de Medicamentos")
            c.execute("SELECT id, folio, expediente, nombre FROM pacientes_registro WHERE status='ACTIVO' ORDER BY id DESC")
            pacientes_list = c.fetchall()

            if not pacientes_list:
                st.info("No hay pacientes registrados.")
            else:
                opciones_p = {f"{p[1]} | Exp: {p[2] or 'S/N'} - {p[3]}": p for p in pacientes_list}
                sel_p_txt = st.selectbox("Seleccionar Paciente para Entrega", list(opciones_p.keys()))
                p_sel = opciones_p[sel_p_txt]
                p_id_str = str(p_sel[0])

                c.execute('''
                    SELECT r.id, m.nombre, r.dosis, r.horario, m.existencia, m.id
                    FROM recetas_pacientes r
                    JOIN catalogo_medicamentos m ON r.medicamento_id = m.id
                    WHERE r.paciente_id = ?
                ''', (p_id_str,))
                recetas = c.fetchall()

                if not recetas:
                    st.warning("Este paciente no tiene medicamentos recetados actualmente.")
                else:
                    with st.form("form_entrega_meds"):
                        st.markdown("**Medicamentos Recetados:**")
                        entregas_dict = {}
                        for r in recetas:
                            m_nombre = r[1]
                            dosis_txt = r[2]
                            stock = r[4]
                            med_id = r[5]

                            col_e1, col_e2, col_e3 = st.columns([2, 1, 1])
                            with col_e1:
                                st.markdown(f"**{m_nombre}** ({dosis_txt} - {r[3]})")
                                st.caption(f"Stock disponible en almacén: `{stock}`")
                            with col_e2:
                                # Proteccion ante stock cero o menor a dosis
                                cant_sugerida = min(1, stock) if stock > 0 else 0
                                cant = st.number_input(f"Cantidad a entregar ({m_nombre})", min_value=0, max_value=max(0, stock), value=cant_sugerida, key=f"med_{r[0]}")
                                entregas_dict[med_id] = (cant, stock)
                            with col_e3:
                                if stock == 0:
                                    st.error("⚠️ Sin stock")

                        btn_entregar = st.form_submit_button("🚚 Registrar Entrega y Descontar Almacén", use_container_width=True)

                        if btn_entregar:
                            f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            for med_id, (cant, stock_actual) in entregas_dict.items():
                                if cant > 0:
                                    nuevo_stock = stock_actual - cant
                                    c.execute("UPDATE catalogo_medicamentos SET existencia = ? WHERE id = ?", (nuevo_stock, med_id))
                                    c.execute("INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, cantidad, fecha_entrega, usuario) VALUES (?, ?, ?, ?, ?)",
                                              (p_id_str, med_id, cant, f_now, st.session_state["username"]))
                            conn.commit()
                            st.balloons()
                            st.toast("✅ ¡Entrega de medicamentos registrada y stock actualizado!")
                            st.success("Medicamentos entregados y descontados del almacén.")

        with tab_m2:
            st.subheader("Asignar Receta a Paciente")
            c.execute("SELECT id, folio, expediente, nombre FROM pacientes_registro WHERE status='ACTIVO'")
            p_list = c.fetchall()
            c.execute("SELECT id, nombre, presentacion, existencia FROM catalogo_medicamentos")
            m_list = c.fetchall()

            if not p_list or not m_list:
                st.info("Requiere tener pacientes y medicamentos registrados en el catálogo.")
            else:
                p_opts = {f"{p[1]} - {p[3]}": p[0] for p in p_list}
                m_opts = {f"{m[1]} ({m[2]}) - Stock: {m[3]}": m[0] for m in m_list}

                with st.form("form_asignar_receta"):
                    p_rec_id = st.selectbox("Paciente", list(p_opts.keys()))
                    m_rec_id = st.selectbox("Medicamento", list(m_opts.keys()))
                    dosis_in = st.text_input("Dosis (ej. 1 tableta, 500mg)", value="1 tableta")
                    horario_in = st.text_input("Horario (ej. Cada 8 horas / Mañana y Noche)", value="Cada 12 horas")

                    if st.form_submit_button("➕ Asignar Medicamento a Receta"):
                        c.execute("INSERT INTO recetas_pacientes (paciente_id, medicamento_id, dosis, horario, fecha_inicio) VALUES (?, ?, ?, ?, ?)",
                                  (str(p_opts[p_rec_id]), m_opts[m_rec_id], dosis_in, horario_in, str(date.today())))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Medicamento asignado a la receta!")
                        st.success("Receta actualizada.")

        with tab_m3:
            st.subheader("Catálogo e Inventario de Almacén")
            with st.form("form_nuevo_med"):
                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    nom_med = st.text_input("Nombre del Medicamento *")
                with col_n2:
                    pres_med = st.text_input("Presentación (ej. Caja 30 tabletas 500mg)")
                with col_n3:
                    exist_med = st.number_input("Existencia Inicial", min_value=0, value=50)

                if st.form_submit_button("➕ Registrar Medicamento en Almacén"):
                    if nom_med.strip():
                        c.execute("INSERT OR REPLACE INTO catalogo_medicamentos (nombre, presentacion, existencia) VALUES (?, ?, ?)",
                                  (nom_med.strip(), pres_med, exist_med))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Medicamento agregado al catálogo!")
                        st.rerun()

            st.markdown("---")
            c.execute("SELECT id, nombre, presentacion, existencia FROM catalogo_medicamentos")
            meds_db = c.fetchall()
            if meds_db:
                st.dataframe(meds_db, use_container_width=True)

    # =========================================================================
    # 8. MÓDULO: REPOSITORIO DE DOCUMENTOS Y CARPETAS
    # =========================================================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos en la Nube")
        
        tab_r1, tab_r2, tab_r3 = st.tabs(["📤 Subir Documento", "📂 Explorar / Descargar", "📁 Personalizar Carpetas"])

        # Cargar carpetas
        c.execute("SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY nombre_carpeta ASC")
        carpetas_list = [r[0] for r in c.fetchall()]

        with tab_r1:
            st.subheader("Subir Archivo al Repositorio")
            with st.form("form_subir_doc"):
                carpeta_sel = st.selectbox("Carpeta de Destino", carpetas_list)
                archivo_subido = st.file_uploader("Seleccionar Archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "doc", "xlsx", "png", "jpg"])
                desc_doc = st.text_area("Descripción / Notas del Documento")

                if st.form_submit_button("📤 Subir Documento a la Nube"):
                    if archivo_subido is not None:
                        bytes_data = archivo_subido.read()
                        f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute('''
                            INSERT INTO repositorio_documentos 
                            (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (carpeta_sel, archivo_subido.name, archivo_subido.type, bytes_data, desc_doc, f_now, st.session_state["username"]))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Documento subido exitosamente a la nube!")
                        st.success(f"Archivo '{archivo_subido.name}' guardado en '{carpeta_sel}'.")

        with tab_r2:
            st.subheader("Documentos Almacenados")
            carp_filtro = st.selectbox("Filtrar por Carpeta", ["-- Todas las Carpetas --"] + carpetas_list)
            
            if carp_filtro == "-- Todas las Carpetas --":
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos ORDER BY id DESC")
            else:
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC", (carp_filtro,))
            
            docs_db = c.fetchall()

            if not docs_db:
                st.info("No hay documentos subidos en esta carpeta.")
            else:
                for doc in docs_db:
                    col_doc1, col_doc2 = st.columns([3, 1])
                    with col_doc1:
                        st.markdown(f"📄 **{doc[2]}** (`{doc[1]}`)")
                        st.caption(f"Subido el: {doc[6]} | Notas: {doc[5] or 'Sin notas'}")
                    with col_doc2:
                        st.download_button(
                            label="📥 Descargar",
                            data=doc[4],
                            file_name=doc[2],
                            mime=doc[3],
                            key=f"dl_doc_{doc[0]}"
                        )
                    st.markdown("---")

        with tab_r3:
            st.subheader("Gestión y Personalización de Carpetas")
            if not es_admin():
                st.warning("🔒 Solo los administradores pueden crear o renombrar carpetas.")
            else:
                col_k1, col_k2 = st.columns(2)
                with col_k1:
                    st.markdown("**➕ Crear Nueva Carpeta:**")
                    with st.form("form_nueva_carp"):
                        nom_nueva_c = st.text_input("Nombre de la Nueva Carpeta")
                        if st.form_submit_button("➕ Crear Carpeta"):
                            if nom_nueva_c.strip():
                                c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (nom_nueva_c.strip(),))
                                conn.commit()
                                st.balloons()
                                st.toast("✅ ¡Carpeta creada!")
                                st.rerun()

                with col_k2:
                    st.markdown("**✏️ Renombrar Carpeta Existente:**")
                    with st.form("form_rename_carp"):
                        c_a_renom = st.selectbox("Carpeta a Renombrar", carpetas_list)
                        c_nuevo_nom = st.text_input("Nuevo Nombre")
                        if st.form_submit_button("✏️ Renombrar Carpeta"):
                            if c_nuevo_nom.strip():
                                c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (c_nuevo_nom.strip(), c_a_renom))
                                c.execute("UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?", (c_nuevo_nom.strip(), c_a_renom))
                                conn.commit()
                                st.balloons()
                                st.toast("✅ ¡Carpeta renombrada!")
                                st.rerun()

    # =========================================================================
    # 9. MÓDULO: BUSCAR Y LISTAR PACIENTES
    # =========================================================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Búsqueda de Pacientes")
        st.markdown("Consulta centralizada del estatus de todos los residentes.")

        c.execute("SELECT folio, expediente, nombre, edad, sexo, fecha_ingreso, etapa_actual, status FROM pacientes_registro ORDER BY id DESC")
        pacientes_all = c.fetchall()

        if not pacientes_all:
            st.info("No hay pacientes registrados en la base de datos.")
        else:
            busqueda = st.text_input("🔎 Buscar paciente por Folio, Expediente o Nombre")
            if busqueda:
                pacientes_filtrados = [p for p in pacientes_all if busqueda.lower() in f"{p[0]} {p[1]} {p[2]}".lower()]
            else:
                pacientes_filtrados = pacientes_all

            st.markdown(f"**Total de pacientes encontrados:** `{len(pacientes_filtrados)}`")
            for p in pacientes_filtrados:
                with st.expander(f"👤 {p[0]} | Exp: {p[1] or 'S/N'} - {p[2]} ({p[6]})"):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        st.write(f"**Folio:** {p[0]}")
                        st.write(f"**Expediente:** {p[1] or 'S/N'}")
                        st.write(f"**Nombre:** {p[2]}")
                        st.write(f"**Edad:** {p[3]} años | **Sexo:** {p[4]}")
                    with col_p2:
                        st.write(f"**Fecha de Ingreso:** {p[5]}")
                        st.write(f"**Etapa Actual:** {p[6]}")
                        st.write(f"**Estado:** `{p[7]}`")

    # =========================================================================
    # 10. MÓDULO: CONFIGURACIÓN Y SEGURIDAD
    # =========================================================================
    elif menu == "⚙️ Configuracion y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")

        if es_admin():
            tab_s1, tab_s2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_s1 = st.container()
            tab_s2 = None

        with tab_s1:
            st.subheader("Cambiar Mi Contraseña de Acceso")
            with st.form("form_cambiar_mi_pass"):
                pass_act = st.text_input("Contraseña Actual", type="password")
                pass_new1 = st.text_input("Nueva Contraseña", type="password")
                pass_new2 = st.text_input("Confirmar Nueva Contraseña", type="password")

                if st.form_submit_button("🔒 Actualizar mi Contraseña"):
                    if hash_pass(pass_act) != verificar_login(st.session_state["username"], pass_act)[1] if verificar_login(st.session_state["username"], pass_act) else False:
                        st.error("❌ La contraseña actual es incorrecta.")
                    elif pass_new1 != pass_new2:
                        st.error("❌ Las nuevas contraseñas no coinciden.")
                    elif len(pass_new1) < 4:
                        st.error("❌ La nueva contraseña debe tener al menos 4 caracteres.")
                    else:
                        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hash_pass(pass_new1), st.session_state["username"]))
                        conn.commit()
                        st.balloons()
                        st.toast("✅ ¡Contraseña actualizada exitosamente!")
                        st.success("Su contraseña ha sido cambiada.")

        if tab_s2:
            with tab_s2:
                st.subheader("Gestión de Usuarios del Personal")
                with st.form("form_alta_usuario"):
                    col_u1, col_u2, col_u3 = st.columns(3)
                    with col_u1:
                        u_user = st.text_input("Nombre de Usuario (Login) *")
                    with col_u2:
                        u_nombre = st.text_input("Nombre Completo del Personal *")
                    with col_u3:
                        u_rol = st.selectbox("Rol / Nivel de Permisos", ["Nivel 1 - Administrador", "Nivel 2 - Lectura y Escritura", "Nivel 3 - Solo Lectura"])

                    u_pass = st.text_input("Contraseña Inicial", type="password")

                    if st.form_submit_button("➕ Crear Nuevo Usuario de Personal"):
                        if u_user.strip() and u_pass.strip():
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                                      (u_user.strip(), hash_pass(u_pass.strip()), u_nombre.strip(), u_rol))
                            conn.commit()
                            st.balloons()
                            st.toast("✅ ¡Nuevo usuario registrado!")
                            st.rerun()

                st.markdown("---")
                st.subheader("Usuarios Registrados en el Sistema")
                c.execute("SELECT id, username, nombre_completo, rol FROM usuarios")
                st.dataframe(c.fetchall(), use_container_width=True)

    # =========================================================================
    # 11. MÓDULO: RESPALDO Y RESTAURACIÓN
    # =========================================================================
    elif menu == "📦 Respaldo y Restauracion":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.markdown("Descarga un archivo completo de la base de datos con todos los expedientes, firmas y documentos.")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.subheader("📥 Descargar Respaldo")
            st.markdown("Haz clic abajo para guardar el archivo `.db` en tu computadora.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                st.download_button(
                    label="📥 Descargar Respaldo Completo (.db)",
                    data=db_bytes,
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )

        with col_b2:
            st.subheader("📤 Restaurar Respaldo")
            if not es_admin():
                st.warning("🔒 Solo administradores pueden restaurar bases de datos.")
            else:
                res_file = st.file_uploader("Seleccionar archivo de respaldo (.db)", type=["db", "sqlite"])
                if res_file is not None:
                    if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                        with open(DB_FILE, "wb") as f:
                            f.write(res_file.read())
                        st.balloons()
                        st.toast("✅ ¡Base de datos restaurada correctamente!")
                        st.success("Base de datos restaurada. La página se recargará.")
                        st.rerun()

    conn.close()

if __name__ == "__main__":
    main()

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
    page_title="Sawabona Shikoba - Sistema de Gestión Clínico",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- CONTROL DE INACTIVIDAD (10 MINUTOS) ---
TIMEOUT_SECONDS = 600

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if st.session_state["logged_in"]:
    ahora = time.time()
    if "ultima_actividad" in st.session_state:
        inactivo = ahora - st.session_state["ultima_actividad"]
        if inactivo > TIMEOUT_SECONDS:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
    st.session_state["ultima_actividad"] = ahora

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de Usuarios
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador'
        )
    """)
    
    # Verificar columna rol en usuarios
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [col[1] for col in c.fetchall()]
    if "rol" not in cols_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
        
    # Crear o asegurar usuario admin por defecto
    c.execute("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("""
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol)
            VALUES (?, ?, ?, ?)
        """, ("admin", default_pass, "Administrador del Sistema", "Administrador"))
    else:
        c.execute("UPDATE usuarios SET rol = 'Administrador' WHERE username = 'admin'")
        
    # Tabla de Pacientes / Entrevistas
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT UNIQUE,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    c.execute("PRAGMA table_info(entrevistas)")
    cols_e = [col[1] for col in c.fetchall()]
    if "expediente" not in cols_e:
        c.execute("ALTER TABLE entrevistas ADD COLUMN expediente TEXT UNIQUE")
        
    # Tabla de Fichas de Ingreso
    c.execute("""
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            fecha_ingreso TEXT,
            datos_json TEXT
        )
    """)
    
    # Tabla de Consejerías Individuales
    c.execute("""
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
    """)
    
    c.execute("PRAGMA table_info(consejerias)")
    cols_c = [col[1] for col in c.fetchall()]
    needed_c = {
        "expediente": "TEXT",
        "aspectos_trabajar": "TEXT",
        "aspectos_proxima": "TEXT",
        "fecha_proxima": "TEXT",
        "exposicion": "TEXT",
        "avance": "TEXT",
        "sugerencia": "TEXT",
        "fecha": "TEXT",
        "usuario": "TEXT"
    }
    for col_name, col_type in needed_c.items():
        if col_name not in cols_c:
            c.execute(f"ALTER TABLE consejerias ADD COLUMN {col_name} {col_type}")
            
    # Tabla de Grupos Terapéuticos
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            etapa_paciente TEXT,
            fecha TEXT,
            desarrollo TEXT,
            devoluciones TEXT,
            compromisos TEXT,
            usuario TEXT
        )
    """)
    
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_g = [col[1] for col in c.fetchall()]
    if "etapa_paciente" not in cols_g:
        c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")
        
    # Tabla de Medicamentos / Catálogo
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            existencia INTEGER DEFAULT 0
        )
    """)
    
    # Tabla de Esquema de Dosis Pacientes
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamentos_paciente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            med_id INTEGER,
            dosis_manana INTEGER DEFAULT 0,
            dosis_tarde INTEGER DEFAULT 0,
            dosis_noche INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    """)
    
    # Tabla de Entregas de Almacén
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            med_id INTEGER,
            cantidad_entregada INTEGER,
            fecha TEXT,
            usuario TEXT
        )
    """)
    
    # Tabla de Repositorio de Documentos Nube
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            archivo_blob BLOB,
            fecha_subida TEXT,
            usuario TEXT
        )
    """)
    
    # Tabla de Carpetas Personalizadas
    c.execute("""
        CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    """)
    
    # Carpetas predeterminadas si no existen
    carpetas_init = ['📄 Manuales y Reglamentos', '📋 Formatos Clinicos', '🩺 Evaluaciones Medicas', '📑 Documentos Generales']
    for carb in carpetas_init:
        c.execute('INSERT OR IGNORE INTO carpetas_repositorio (nombre_carpeta) VALUES (?)', (carb,))
        
    conn.commit()
    conn.close()

init_db()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?",
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '', '¡': '', '”': '"', '“': '"', '’': "'"
    }
    for orig, repl in replacements.items():
        texto = texto.replace(orig, repl)
    return texto.encode('latin-1', 'replace').decode('latin-1')

def obtener_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id FROM entrevistas")
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
    return f"PAC-{max_num + 1:03d}"

def validar_expediente_unico(expediente, paciente_id_actual=""):
    if not expediente or not expediente.strip():
        return True, ""
    exp_clean = expediente.strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ?", (exp_clean,))
    row = c.fetchone()
    conn.close()
    if row and row[0] != paciente_id_actual:
        nombre = "Otro paciente"
        try:
            d = json.loads(row[1])
            nombre = d.get("nombre_completo", "Otro paciente")
        except:
            pass
        return False, f"⚠️ El número de Expediente '{exp_clean}' ya está asignado al paciente: {nombre} ({row[0]})."
    return True, ""

def listar_pacientes_completos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, expediente, datos_json FROM entrevistas ORDER BY fecha_registro DESC")
    rows = c.fetchall()
    conn.close()
    lista = []
    for r in rows:
        pid = r[0]
        exp = r[1] or "S/N"
        try:
            d = json.loads(r[2])
            nombre = d.get("nombre_completo", "Sin Nombre")
            etapa = d.get("etapa_actual", "Acogida")
        except:
            nombre = "Sin Nombre"
            etapa = "Acogida"
        etiqueta = f"{pid} | Exp: {exp} - {nombre} ({etapa})"
        lista.append((pid, exp, nombre, etapa, etiqueta, r[2]))
    return lista

# --- PLAN DE CONSEJERÍAS ---
PLAN_CONSEJERIAS = {
    "Acogida": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).",
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
        "(5. CONSEJRIA) PREVENCIÓN DE RECAÍDAS.",
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
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO - CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- GENERADORES PDF ---
def generar_pdf_ficha_ingreso(p_id, exp, datos_j):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), 0, 1, "C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, clean_pdf_text("Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones"), 0, 1, "C")
    pdf.cell(0, 5, clean_pdf_text("FICHA DE INGRESO Y ADMISION DE RESIDENTES"), 0, 1, "C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"EXPEDIENTE: {exp if exp else 'S/N'}"), 0, 1, "R")
    pdf.ln(3)
    
    dj = json.loads(datos_j) if isinstance(datos_j, str) else datos_j
    
    def sec_title(t):
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(220, 240, 220)
        pdf.cell(0, 6, clean_pdf_text(t), 1, 1, "L", fill=True)
        pdf.set_font("Arial", "", 9)
        
    sec_title("1. DATOS DEL RESPONSABLE DEL INGRESO")
    pdf.multi_cell(0, 5, clean_pdf_text(f"Nombre: {dj.get('responsable_nombre', '')} | Parentesco: {dj.get('responsable_parentesco', '')} | Tel: {dj.get('responsable_telefono', '')}"))
    pdf.ln(2)
    
    sec_title("2. DATOS GENERALES DEL PACIENTE")
    pdf.multi_cell(0, 5, clean_pdf_text(f"Nombre: {dj.get('nombre_completo', '')} | Edad: {dj.get('edad', '')} anos | Sexo: {dj.get('sexo', '')}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Fecha Nacimiento: {dj.get('fecha_nacimiento', '')} | Escolaridad: {dj.get('escolaridad', '')} | Ocupacion: {dj.get('ocupacion', '')}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Estado Civil: {dj.get('estado_civil', '')} | Religion: {dj.get('religion', '')} | Servicio Medico: {dj.get('servicio_medico', '')}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Domicilio: {dj.get('calle_numero', '')}, Col. {dj.get('colonia', '')}, {dj.get('municipio', '')}, {dj.get('estado', '')} CP {dj.get('codigo_postal', '')}"))
    pdf.ln(2)
    
    sec_title("3. SUSTANCIAS DE CONSUMO Y TRATAMIENTO")
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sustancias de Consumo: {', '.join(dj.get('sustancias', []))}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sustancia de Impacto Principal: {dj.get('sustancia_impacto', '')}"))
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sucursal Asignada: {dj.get('sucursal', '')} | Modalidad: {dj.get('modalidad', 'Voluntario')}"))
    pdf.ln(2)
    
    sec_title("4. TERMINOS FINANCIEROS Y CONTRACTUALES")
    pdf.multi_cell(0, 5, clean_pdf_text(f"Costo de Ingreso: ${dj.get('costo_ingreso', 4500):,.2f} | Mensualidad: ${dj.get('costo_mensual', 6000):,.2f} | Pagare: ${dj.get('importe_pagare', 42000):,.2f}"))
    pdf.ln(3)
    
    pdf.set_font("Arial", "B", 8)
    pdf.multi_cell(0, 4, clean_pdf_text("DECLARACION DE CONFORMIDAD Y AUTORIZACION (NOM-028-SSA2-2009): Por medio de la presente, autorizo el ingreso y tratamiento especializado del paciente en la C.T. Sawabona Shikoba A.C., aceptando los reglamentos, cuotas de recuperacion y compromisos terapeuticos establecidos."))
    pdf.ln(12)
    
    pdf.set_font("Arial", "B", 9)
    pdf.cell(90, 5, clean_pdf_text("___________________________________"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("___________________________________"), 0, 1, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma del Responsable Familiar"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("Director / Encargado del Establecimiento"), 0, 1, "C")
    
    return bytes(pdf.output())

def generar_pdf_consejeria(p_id, exp, nombre_paciente, etapa, num_cons, asp_trab, asp_prox, fec_prox, exposicion, avance, sugerencia, fecha):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), 0, 1, "C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, clean_pdf_text("HOJA CLINICA DE CONSEJERIA INDIVIDUAL"), 0, 1, "C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 10)
    pdf.cell(100, 6, clean_pdf_text(f"PACIENTE: {nombre_paciente}"), 0, 0, "L")
    pdf.cell(0, 6, clean_pdf_text(f"EXPEDIENTE: {exp if exp else 'S/N'}"), 0, 1, "R")
    pdf.cell(100, 6, clean_pdf_text(f"ETAPA: {etapa}"), 0, 0, "L")
    pdf.cell(0, 6, clean_pdf_text(f"FECHA SESION: {fecha}"), 0, 1, "R")
    pdf.cell(0, 6, clean_pdf_text(f"CONSEJERIA NUMERO: #{num_cons}"), 0, 1, "L")
    pdf.ln(4)
    
    def blk(tit, contenido):
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(0, 6, clean_pdf_text(tit), 1, 1, "L", fill=True)
        pdf.set_font("Arial", "", 9)
        pdf.multi_cell(0, 5, clean_pdf_text(contenido if contenido else "Sin observaciones."))
        pdf.ln(2)
        
    blk("ASPECTOS TRABAJADOS EN ESTA CONSEJERIA:", asp_trab)
    blk("EXPOSICION DEL PACIENTE:", exposicion)
    blk("AVANCE / RETROCESO OBSERVADO:", avance)
    blk("SUGERENCIAS Y TAREAS ASIGNADAS:", sugerencia)
    blk("PROXIMA CONSEJERIA Y FECHA:", f"Tema proximo: {asp_prox} | Fecha programada: {fec_prox}")
    
    pdf.ln(12)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(90, 5, clean_pdf_text("___________________________________"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("___________________________________"), 0, 1, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma del Consejero / Terapeuta"), 0, 0, "C")
    pdf.cell(90, 5, clean_pdf_text("Firma de Conformidad del Paciente"), 0, 1, "C")
    
    return bytes(pdf.output())

# --- APLICACIÓN PRINCIPAL STREAMLIT ---
def main():
    if not st.session_state["logged_in"]:
        st.markdown("<h1 style='text-align: center; color: #2E7D32;'>🌱 COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</h3>", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔐 Iniciar Sesión en el Sistema")
            with st.form("login_form"):
                u_input = st.text_input("Usuario")
                p_input = st.text_input("Contraseña", type="password")
                btn_login = st.form_submit_button("Ingresar")
                
                if btn_login:
                    res = verificar_login(u_input, p_input)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2] if (len(res) > 2 and res[2]) else ("Administrador" if u_input.lower() == "admin" else "Lectura/Escritura")
                        st.session_state["ultima_actividad"] = time.time()
                        st.balloons()
                        st.toast(f"¡Bienvenido(a) {res[1]}!")
                        st.rerun()
                    else:
                        st.error("⚠️ Usuario o contraseña incorrectos.")
        return

    # --- BARRA LATERAL (SIDEBAR) ---
    st.sidebar.markdown("### 🌱 C.T. SAWABONA SHIKOBA")
    st.sidebar.caption(f"👤 **{st.session_state.get('nombre_completo', 'Usuario')}**")
    st.sidebar.caption(f"🔑 Rol: **{st.session_state.get('rol', 'Usuario')}**")
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()
        
    st.sidebar.markdown("---")
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

    # BANNER SUPERIOR INSTITUCIONAL
    st.markdown("""
        <div style="background-color: #2E7D32; padding: 12px; border-radius: 8px; color: white; text-align: center; margin-bottom: 20px;">
            <h2 style="margin:0; color: white;">🌱 COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.</h2>
            <p style="margin:0; font-size: 14px;">Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones | Sistema Clínico Institucional</p>
        </div>
    """, unsafe_allow_html=True)

    # --- MÓDULO 1: INICIO / TABLERO ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control Institucional")
        pacientes = listar_pacientes_completos()
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Total Residentes Activos", len(pacientes))
        with col_m2:
            acogida_cnt = sum(1 for p in pacientes if p[3] == "Acogida")
            st.metric("En Etapa Acogida", acogida_cnt)
        with col_m3:
            ident_cnt = sum(1 for p in pacientes if p[3] == "Identificación")
            st.metric("En Identificación", ident_cnt)
        with col_m4:
            elab_cnt = sum(1 for p in pacientes if p[3] in ["Elaboración", "Consolidación", "Servicio Social"])
            st.metric("En Etapas Avanzadas", elab_cnt)
            
        st.markdown("---")
        st.subheader("📋 Resumen General de Residentes en Tratamiento")
        if pacientes:
            for p in pacientes:
                st.info(f"👤 **{p[2]}** | 🆔 Folio: **{p[0]}** | 📁 Expediente: **{p[1]}** | 🎯 Etapa: **{p[3]}**")
        else:
            st.write("No hay residentes registrados aún.")

    # --- MÓDULO 2: REGISTRO Y EDICIÓN ---
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Modificación de Residentes")
        
        tab_alta, tab_edit = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Modificar Paciente Existente"])
        
        with tab_alta:
            st.subheader("Formulario de Alta de Residente")
            sugerido_folio = obtener_siguiente_folio()
            
            with st.form("form_alta_paciente"):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("Folio Interno (Autoincrementable)", value=sugerido_folio, disabled=True)
                    exp_in = st.text_input("Número de Expediente (Manual / Numérico)", help="Si no lo tiene a la mano puede dejarlo en blanco")
                    nom_in = st.text_input("Nombre Completo del Paciente *")
                    f_nac = st.date_input("Fecha de Nacimiento", value=datetime(1995, 1, 1))
                with c2:
                    sex_in = st.selectbox("Sexo", ["Masculino", "Femenino"])
                    f_ing = st.date_input("Fecha de Ingreso a la Institución", value=datetime.now())
                    etapa_in = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                    f_etapa = st.date_input("Fecha Inicio de Etapa Actual", value=datetime.now())
                    
                btn_alta = st.form_submit_button("💾 Registrar Paciente")
                
                if btn_alta:
                    if not nom_in.strip():
                        st.error("El nombre completo del paciente es obligatorio.")
                    else:
                        ok_exp, msg_exp = validar_expediente_unico(exp_in, sugerido_folio)
                        if not ok_exp:
                            st.error(msg_exp)
                        else:
                            datos = {
                                "nombre_completo": nom_in.strip(),
                                "expediente": exp_in.strip(),
                                "fecha_nacimiento": f_nac.strftime("%Y-%m-%d"),
                                "sexo": sex_in,
                                "fecha_ingreso": f_ing.strftime("%Y-%m-%d"),
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": f_etapa.strftime("%Y-%m-%d")
                            }
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute("""
                                INSERT INTO entrevistas (paciente_id, expediente, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (sugerido_folio, exp_in.strip(), f_now, f_now, st.session_state["username"], json.dumps(datos, ensure_ascii=False)))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast(f"✅ Paciente {nom_in} registrado con éxito con Folio {sugerido_folio}.")
                            st.success(f"✅ Paciente registrado con Folio **{sugerido_folio}** y Expediente **{exp_in if exp_in else 'S/N'}**.")

        with tab_edit:
            st.subheader("Editar Datos del Residente")
            pacientes = listar_pacientes_completos()
            if not pacientes:
                st.write("No hay residentes registrados para editar.")
            else:
                opciones = {p[4]: p for p in pacientes}
                sel_p = st.selectbox("Seleccione Paciente a Editar", list(opciones.keys()))
                p_data = opciones[sel_p]
                pid = p_data[0]
                
                try:
                    dj = json.loads(p_data[5])
                except:
                    dj = {}
                    
                with st.form("form_edit_paciente"):
                    e_c1, e_c2 = st.columns(2)
                    with e_c1:
                        st.text_input("Folio (No Editable)", value=pid, disabled=True)
                        exp_edit = st.text_input("Número de Expediente", value=dj.get("expediente", p_data[1]))
                        nom_edit = st.text_input("Nombre Completo", value=dj.get("nombre_completo", p_data[2]))
                        sex_edit = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if dj.get("sexo")=="Masculino" else 1)
                    with e_c2:
                        etapa_edit = st.selectbox("Etapa Actual", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"].index(dj.get("etapa_actual", "Acogida")))
                        f_ing_edit = st.text_input("Fecha de Ingreso (YYYY-MM-DD)", value=dj.get("fecha_ingreso", datetime.now().strftime("%Y-%m-%d")))
                        f_etapa_edit = st.text_input("Fecha Inicio de Etapa (YYYY-MM-DD)", value=dj.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d")))
                        
                    btn_edit = st.form_submit_button("💾 Guardar Cambios")
                    if btn_edit:
                        ok_exp, msg_exp = validar_expediente_unico(exp_edit, pid)
                        if not ok_exp:
                            st.error(msg_exp)
                        else:
                            dj["nombre_completo"] = nom_edit.strip()
                            dj["expediente"] = exp_edit.strip()
                            dj["sexo"] = sex_edit
                            dj["etapa_actual"] = etapa_edit
                            dj["fecha_ingreso"] = f_ing_edit.strip()
                            dj["fecha_inicio_etapa"] = f_etapa_edit.strip()
                            
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute("""
                                UPDATE entrevistas
                                SET expediente = ?, fecha_modificacion = ?, datos_json = ?
                                WHERE paciente_id = ?
                            """, (exp_edit.strip(), f_now, json.dumps(dj, ensure_ascii=False), pid))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast("✅ Cambios guardados correctamente.")
                            st.success("✅ Expediente actualizado exitosamente.")

    # --- MÓDULO 3: FICHA DE INGRESO ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión de Residentes")
        pacientes = listar_pacientes_completos()
        
        if not pacientes:
            st.warning("Debe registrar al menos un paciente para gestionar Fichas de Ingreso.")
        else:
            opciones = {p[4]: p for p in pacientes}
            sel_label = st.selectbox("Seleccione Residente", list(opciones.keys()))
            p_sel = opciones[sel_label]
            pid = p_sel[0]
            exp = p_sel[1]
            nombre_p = p_sel[2]
            
            # Cargar datos previos si existen
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (pid,))
            row_f = c.fetchone()
            conn.close()
            
            f_dj = json.loads(row_f[0]) if (row_f and row_f[0]) else {}
            
            st.markdown("---")
            with st.form("form_ficha_ingreso"):
                st.subheader("1. Datos del Responsable del Ingreso")
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    resp_nom = st.text_input("Nombre Completo Responsable", value=f_dj.get("responsable_nombre", ""))
                with fc2:
                    resp_par = st.selectbox("Parentesco", ["Padre", "Madre", "Cónyuge", "Hermano/a", "Hijo/a", "Tutor Legal", "Otro"], index=0)
                with fc3:
                    resp_tel = st.text_input("Teléfono de Contacto", value=f_dj.get("responsable_telefono", ""))
                    
                st.subheader("2. Datos Generales del Paciente")
                gc1, gc2, gc3 = st.columns(3)
                with gc1:
                    p_edad = st.number_input("Edad", min_value=12, max_value=90, value=f_dj.get("edad", 25))
                    p_f_nac = st.text_input("Fecha Nacimiento (YYYY-MM-DD)", value=f_dj.get("fecha_nacimiento", "1998-05-15"))
                with gc2:
                    p_esc = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria", "Licenciatura", "Postgrado", "Trunca"], index=2)
                    p_ocup = st.text_input("Ocupación", value=f_dj.get("ocupacion", "Empleado"))
                with gc3:
                    p_est = st.selectbox("Estado Civil", ["Soltero/a", "Casado/a", "Unión Libre", "Divorciado/a", "Viudo/a"], index=0)
                    p_serv = st.text_input("Servicio Médico", value=f_dj.get("servicio_medico", "IMSS / Ninguno"))
                    
                st.subheader("3. Domicilio y Sustancias")
                dc1, dc2 = st.columns(2)
                with dc1:
                    p_calle = st.text_input("Calle y Número", value=f_dj.get("calle_numero", ""))
                    p_col = st.text_input("Colonia", value=f_dj.get("colonia", ""))
                    p_mun = st.text_input("Municipio / Alcaldía", value=f_dj.get("municipio", ""))
                    p_est_dom = st.text_input("Estado", value=f_dj.get("estado", "Jalisco"))
                    p_cp = st.text_input("Código Postal", value=f_dj.get("codigo_postal", ""))
                with dc2:
                    sust_list = ["Alcohol", "Cannabis (Marihuana)", "Cocaína", "Metanfetaminas (Crystal)", "Tabaco", "Heroína / Opiáceos", "Benzodiazepinas"]
                    sust_sel = st.multiselect("Sustancias de Consumo", sust_list, default=f_dj.get("sustancias", ["Alcohol", "Metanfetaminas (Crystal)"]))
                    sust_imp = st.text_input("Sustancia de Impacto Principal", value=f_dj.get("sustancia_impacto", "Metanfetaminas (Crystal)"))
                    sucursal_in = st.text_input("Sucursal Asignada", value=f_dj.get("sucursal", "Sawabona - Central"))
                    modalidad_in = st.selectbox("Modalidad de Internamiento (NOM-028)", ["Voluntario", "Involuntario", "Obligatorio por Autoridad"], index=0)
                    
                st.subheader("4. Términos Financieros")
                fin1, fin2, fin3 = st.columns(3)
                with fin1:
                    c_ingreso = st.number_input("Costo de Ingreso ($)", value=float(f_dj.get("costo_ingreso", 4500.0)))
                with fin2:
                    c_mensual = st.number_input("Mensualidad ($)", value=float(f_dj.get("costo_mensual", 6000.0)))
                with fin3:
                    c_pagare = st.number_input("Importe Pagaré ($)", value=float(f_dj.get("importe_pagare", 42000.0)))
                    
                btn_ficha = st.form_submit_button("💾 Guardar Ficha de Ingreso")
                
                if btn_ficha:
                    f_datos = {
                        "responsable_nombre": resp_nom,
                        "responsable_parentesco": resp_par,
                        "responsable_telefono": resp_tel,
                        "nombre_completo": nombre_p,
                        "edad": p_edad,
                        "sexo": p_sel[3],
                        "fecha_nacimiento": p_f_nac,
                        "escolaridad": p_esc,
                        "ocupacion": p_ocup,
                        "estado_civil": p_est,
                        "servicio_medico": p_serv,
                        "calle_numero": p_calle,
                        "colonia": p_col,
                        "municipio": p_mun,
                        "estado": p_est_dom,
                        "codigo_postal": p_cp,
                        "sustancias": sust_sel,
                        "sustancia_impacto": sust_imp,
                        "sucursal": sucursal_in,
                        "modalidad": modalidad_in,
                        "costo_ingreso": c_ingreso,
                        "costo_mensual": c_mensual,
                        "importe_pagare": c_pagare
                    }
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("""
                        INSERT OR REPLACE INTO fichas_ingreso (paciente_id, expediente, fecha_ingreso, datos_json)
                        VALUES (?, ?, ?, ?)
                    """, (pid, exp, f_now, json.dumps(f_datos, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("✅ Ficha de Ingreso guardada exitosamente.")
                    st.success("✅ Ficha de Ingreso y Admisión guardada con éxito.")

            st.markdown("---")
            st.subheader("🖨️ Impresión de Ficha de Admisión")
            if row_f or f_dj:
                pdf_bytes = generar_pdf_ficha_ingreso(pid, exp, f_dj if f_dj else f_datos)
                st.download_button(
                    label="🖨️ Descargar Ficha de Ingreso en PDF",
                    data=pdf_bytes,
                    file_name=f"Ficha_Ingreso_{pid}_{exp}.pdf",
                    mime="application/pdf",
                    key=f"btn_pdf_fi_{pid}"
                )

    # --- MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        pacientes = listar_pacientes_completos()
        
        if not pacientes:
            st.warning("Registre un paciente primero para acceder a la entrevista inicial.")
        else:
            opciones = {p[4]: p for p in pacientes}
            sel_l = st.selectbox("Seleccione Residente", list(opciones.keys()))
            p_sel = opciones[sel_l]
            pid = p_sel[0]
            exp = p_sel[1]
            
            try:
                datos_ent = json.loads(p_sel[5])
            except:
                datos_ent = {}
                    
            with st.form("form_entrevista_inicial"):
                st.subheader("1. Antecedentes de Consumo y Salud")
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_edad_inicio = st.number_input("Edad de Inicio de Consumo", value=datos_ent.get("edad_inicio_consumo", 15))
                    e_motivo = st.text_area("Motivo Principal de Consulta", value=datos_ent.get("motivo_consulta", ""))
                with ec2:
                    e_trat_prev = st.selectbox("Tratamientos Previos", ["Ninguno", "1 a 2 internamientos", "3 a 5 internamientos", "Más de 5 internamientos"])
                    e_salud = st.text_area("Padecimientos Médicos / Diagnósticos", value=datos_ent.get("padecimientos_medicos", "Ninguno reportado"))
                    
                st.subheader("2. Apoyo Familiar y Diagnóstico de Consejería")
                st.text_area("Red de Apoyo Familiar", value=datos_ent.get("apoyo_familiar", "Familia nuclear dispuesta al proceso"))
                st.text_area("Diagnóstico Inicial del Consejero", value=datos_ent.get("diagnostico_inicial", "Paciente apto para inicio de programa residencial"))
                
                btn_ent = st.form_submit_button("💾 Guardar Entrevista Inicial")
                if btn_ent:
                    datos_ent["edad_inicio_consumo"] = e_edad_inicio
                    datos_ent["motivo_consulta"] = e_motivo
                    datos_ent["tratamientos_previos"] = e_trat_prev
                    datos_ent["padecimientos_medicos"] = e_salud
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?",
                              (f_now, json.dumps(datos_ent, ensure_ascii=False), pid))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("✅ Entrevista Inicial guardada.")
                    st.success("✅ Datos de la Entrevista Inicial actualizados correctamente.")

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales de Seguimiento")
        pacientes = listar_pacientes_completos()
        
        if not pacientes:
            st.warning("Registre un paciente para realizar consejerías.")
        else:
            opciones = {p[4]: p for p in pacientes}
            sel_l = st.selectbox("Seleccione Paciente", list(opciones.keys()))
            p_sel = opciones[sel_l]
            pid = p_sel[0]
            exp = p_sel[1]
            nombre_p = p_sel[2]
            etapa_p = p_sel[3]
            
            st.info(f"👤 **{nombre_p}** | Folio: **{pid}** | Expediente: **{exp}** | Etapa Activa: **{etapa_p}**")
            
            temas_etapa = PLAN_CONSEJERIAS.get(etapa_p, PLAN_CONSEJERIAS["Acogida"])
            num_cons_list = list(range(1, len(temas_etapa) + 1))
            
            c_top1, c_top2 = st.columns(2)
            with c_top1:
                num_sel = st.selectbox("Seleccione Número de Consejería", num_cons_list)
            with c_top2:
                fecha_s = st.date_input("Fecha de la Sesión", value=datetime.now())
                
            tema_actual = temas_etapa[num_sel - 1]
            prox_num = num_sel if num_sel < len(temas_etapa) else num_sel
            tema_prox = temas_etapa[prox_num] if num_sel < len(temas_etapa) else "Cierre de Etapa / Evaluación de Objetivos"
            
            # Consultar si ya existe esta consejería
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                FROM consejerias
                WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
            """, (pid, etapa_p, num_sel))
            row_c = c.fetchone()
            conn.close()
            
            if row_c:
                st.info(f"ℹ️ Mostrando datos registrados previamente para la Consejería #{num_sel}.")
                val_exp = row_c[3] or ""
                val_av = row_c[4] or ""
                val_sug = row_c[5] or ""
                val_f_prox = row_c[2] or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            else:
                st.success(f"✨ Nueva Consejería #{num_sel} sin capturar. Los campos están limpios.")
                val_exp = ""
                val_av = ""
                val_sug = ""
                val_f_prox = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                
            with st.form(f"form_cons_{pid}_{etapa_p}_{num_sel}"):
                st.text_input("Aspectos Trabajados (Tema de la Sesión)", value=tema_actual, disabled=True)
                st.text_input("Aspectos a Trabajar en Próxima Consejería", value=tema_prox, disabled=True)
                
                f_prox_dt = datetime.now() + timedelta(days=7)
                try:
                    f_prox_dt = datetime.strptime(val_f_prox, "%Y-%m-%d")
                except:
                    pass
                fec_prox_in = st.date_input("Fecha de la Próxima Consejería", value=f_prox_dt)
                
                exp_in = st.text_area("Exposición del Paciente", value=val_exp, help="Notas vertidas por el residente")
                av_in = st.text_area("Avance / Retroceso Observado", value=val_av)
                sug_in = st.text_area("Sugerencias y Tareas Asignadas", value=val_sug)
                
                btn_g_cons = st.form_submit_button("💾 Guardar Consejería")
                
                if btn_g_cons:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_actual_str = fecha_s.strftime("%Y-%m-%d")
                    f_prox_str = fec_prox_in.strftime("%Y-%m-%d")
                    
                    c.execute("""
                        SELECT id FROM consejerias WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                    """, (pid, etapa_p, num_sel))
                    exist_c = c.fetchone()
                    
                    if exist_c:
                        c.execute("""
                            UPDATE consejerias
                            SET expediente = ?, aspectos_trabajar = ?, aspectos_proxima = ?, fecha_proxima = ?, exposicion = ?, avance = ?, sugerencia = ?, fecha = ?, usuario = ?
                            WHERE id = ?
                        """, (exp, tema_actual, tema_prox, f_prox_str, exp_in, av_in, sug_in, f_actual_str, st.session_state["username"], exist_c[0]))
                    else:
                        c.execute("""
                            INSERT INTO consejerias (paciente_id, expediente, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (pid, exp, etapa_p, num_sel, tema_actual, tema_prox, f_prox_str, exp_in, av_in, sug_in, f_actual_str, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast(f"✅ Consejería #{num_sel} guardada con éxito.")
                    st.success(f"✅ Consejería #{num_sel} registrada correctamente.")
                    st.rerun()

            st.markdown("---")
            st.subheader("🖨️ Impresión de Consejería en PDF")
            if row_c:
                pdf_c_bytes = generar_pdf_consejeria(pid, exp, nombre_p, etapa_p, num_sel, tema_actual, tema_prox, val_f_prox, val_exp, val_av, val_sug, row_c[6] or datetime.now().strftime("%Y-%m-%d"))
                st.download_button(
                    label=f"🖨️ Descargar PDF Consejería #{num_sel}",
                    data=pdf_c_bytes,
                    file_name=f"Consejeria_{num_sel}_{pid}_{exp}.pdf",
                    mime="application/pdf",
                    key=f"btn_pdf_cons_{num_sel}"
                )

    # --- MÓDULO 6: GESTIÓN DE ETAPAS ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Proceso Terapéutico")
        pacientes = listar_pacientes_completos()
        
        if not pacientes:
            st.warning("No hay pacientes registrados.")
        else:
            opciones = {p[4]: p for p in pacientes}
            sel_l = st.selectbox("Seleccione Paciente a Evaluar", list(opciones.keys()))
            p_sel = opciones[sel_l]
            pid = p_sel[0]
            exp = p_sel[1]
            nombre_p = p_sel[2]
            etapa_p = p_sel[3]
            
            try:
                dj = json.loads(p_sel[5])
            except:
                dj = {}
                
            f_ini_etapa_str = dj.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d"))
            try:
                d_ini = datetime.strptime(f_ini_etapa_str, "%Y-%m-%d")
                dias_estancia = (datetime.now() - d_ini).days
            except:
                dias_estancia = 0
                
            st.subheader(f"Residente: {nombre_p} | Etapa Actual: {etapa_p}")
            st.info(f"📅 Fecha de Inicio en Etapa: **{f_ini_etapa_str}** | ⏱️ Días Transcurridos: **{dias_estancia} días**")
            
            if dias_estancia > 60:
                st.warning(f"⚠️ **Alerta de Rezago**: El paciente lleva {dias_estancia} días en la etapa {etapa_p}. Se recomienda evaluación clínica.")
                
            # Contar consejerías realizadas
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?", (pid, etapa_p))
            cnt_cons = c.fetchone()[0]
            
            # Contar grupos
            try:
                c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?", (pid, etapa_p))
                cnt_g = c.fetchone()[0]
            except:
                cnt_g = 0
            conn.close()
            
            req_cons = len(PLAN_CONSEJERIAS.get(etapa_p, [1,2,3,4]))
            st.markdown("### 📋 Checklist Requisitos para Cambio de Etapa")
            st.write(f"- Consejerías Individuales Completadas: **{cnt_cons} de {req_cons}** ({'✅ Cumplido' if cnt_cons>=req_cons else '❌ Pendiente'})")
            st.write(f"- Participación en Grupos Terapéuticos: **{cnt_g} sesiones**")
            
            etapas_orden = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
            idx_act = etapas_orden.index(etapa_p) if etapa_p in etapas_orden else 0
            
            if idx_act < len(etapas_orden) - 1:
                sig_etapa = etapas_orden[idx_act + 1]
                puedes_promover = cnt_cons >= req_cons
                
                if puedes_promover:
                    st.success(f"🎉 El residente ha cumplido con todas las consejerías de {etapa_p}. ¡Listo para ser promovido a {sig_etapa}!")
                else:
                    st.error(f"🔒 Candado Activo: Requiere completar {req_cons - cnt_cons} consejería(s) más para poder promover a {sig_etapa}.")
                    
                if st.button(f"🎉 Promover a {sig_etapa}", disabled=not puedes_promover):
                    dj["etapa_actual"] = sig_etapa
                    dj["fecha_inicio_etapa"] = datetime.now().strftime("%Y-%m-%d")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?",
                              (f_now, json.dumps(dj, ensure_ascii=False), pid))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast(f"¡Paciente promovido exitosamente a {sig_etapa}!")
                    st.success(f"✅ Paciente promovido a la etapa {sig_etapa}.")
                    st.rerun()

    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        pacientes = listar_pacientes_completos()
        
        if not pacientes:
            st.warning("Registre pacientes para la sesión grupal.")
        else:
            opciones = {p[4]: p for p in pacientes}
            sel_l = st.selectbox("Seleccione Paciente", list(opciones.keys()))
            p_sel = opciones[sel_l]
            pid = p_sel[0]
            etapa_p = p_sel[3]
            
            with st.form("form_grupo"):
                t_grupo = st.selectbox("Tipo de Grupo Terapéutico", ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Seminario de Prevención"])
                f_grupo = st.date_input("Fecha", value=datetime.now())
                des_grupo = st.text_area("Desarrollo de la Sesión")
                dev_grupo = st.text_area("Devoluciones e Intervenciones")
                comp_grupo = st.text_area("Compromisos Acordados")
                
                btn_g = st.form_submit_button("💾 Guardar Sesión Grupal")
                if btn_g:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO grupos_terapeuticos (paciente_id, tipo_grupo, etapa_paciente, fecha, desarrollo, devoluciones, compromisos, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (pid, t_grupo, etapa_p, f_grupo.strftime("%Y-%m-%d"), des_grupo, dev_grupo, comp_grupo, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("✅ Sesión grupal registrada.")
                    st.success("✅ Registro de grupo guardado exitosamente.")

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario")
        
        tab_cat, tab_esq, tab_ent = st.tabs(["💊 Catálogo de Fármacos", "📋 Esquema por Paciente", "📦 Entrega de Almacén"])
        
        with tab_cat:
            st.subheader("Registrar Fármaco en Inventario")
            with st.form("form_med_cat"):
                m_nom = st.text_input("Nombre del Medicamento *")
                m_pres = st.text_input("Presentación (ej. Tabletas 500mg)")
                m_exist = st.number_input("Existencia Inicial en Almacén", min_value=0, value=100)
                btn_m = st.form_submit_button("➕ Agregar al Catálogo")
                if btn_m:
                    if m_nom:
                        try:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("INSERT INTO catalogo_medicamentos (nombre, presentacion, existencia) VALUES (?, ?, ?)",
                                      (m_nom.strip(), m_pres.strip(), m_exist))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast("✅ Medicamento agregado.")
                            st.success(f"✅ {m_nom} agregado al inventario.")
                        except:
                            st.error("El medicamento ya existe en el catálogo.")

        with tab_esq:
            st.subheader("Asignación de Dosis Diaria a Residente")
            pacientes = listar_pacientes_completos()
            if pacientes:
                opciones = {p[4]: p for p in pacientes}
                p_sel = opciones[st.selectbox("Paciente", list(opciones.keys()))]
                pid = p_sel[0]
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, nombre, presentacion, existencia FROM catalogo_medicamentos")
                meds = c.fetchall()
                conn.close()
                
                if meds:
                    m_opts = {f"{m[1]} ({m[2]}) - Stock: {m[3]}": m[0] for m in meds}
                    sel_m_lbl = st.selectbox("Medicamento", list(m_opts.keys()))
                    med_id = m_opts[sel_m_lbl]
                    
                    with st.form("form_esq_med"):
                        d_m = st.number_input("Dosis Mañana", min_value=0, value=1)
                        d_t = st.number_input("Dosis Tarde", min_value=0, value=0)
                        d_n = st.number_input("Dosis Noche", min_value=0, value=1)
                        ind = st.text_input("Indicaciones Especiales", value="Tomar con alimentos")
                        btn_esq = st.form_submit_button("💾 Guardar Esquema")
                        if btn_esq:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO medicamentos_paciente (paciente_id, med_id, dosis_manana, dosis_tarde, dosis_noche, indicaciones)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (pid, med_id, d_m, d_t, d_n, ind))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast("✅ Esquema asignado.")
                            st.success("✅ Esquema de medicamentos guardado.")

        with tab_ent:
            st.subheader("Entrega Diaria desde Almacén")
            pacientes = listar_pacientes_completos()
            if pacientes:
                opciones = {p[4]: p for p in pacientes}
                p_sel = opciones[st.selectbox("Paciente a Entregar", list(opciones.keys()))]
                pid = p_sel[0]
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""
                    SELECT mp.id, cm.nombre, cm.presentacion, cm.existencia, (mp.dosis_manana + mp.dosis_tarde + mp.dosis_noche), cm.id
                    FROM medicamentos_paciente mp
                    JOIN catalogo_medicamentos cm ON mp.med_id = cm.id
                    WHERE mp.paciente_id = ?
                """, (pid,))
                items = c.fetchall()
                conn.close()
                
                if not items:
                    st.info("El paciente no tiene dosis configuradas en su esquema.")
                else:
                    for it in items:
                        m_nombre = it[1]
                        stock = it[3]
                        dosis = it[4]
                        m_id = it[5]
                        
                        st.markdown(f"**{m_nombre}** | Stock Almacén: `{stock}` | Dosis Recomendada: `{dosis}`")
                        if stock <= 0:
                            st.warning("⚠️ Sin existencias disponibles en almacén.")
                            max_safe = 0
                            val_safe = 0
                        else:
                            max_safe = stock
                            val_safe = min(dosis, stock)
                            
                        cant_ent = st.number_input(f"Cantidad a entregar de {m_nombre}", min_value=0, max_value=max_safe, value=val_safe, key=f"ent_{pid}_{m_id}")
                        if st.button(f"📦 Entregar {m_nombre}", key=f"btn_ent_{pid}_{m_id}"):
                            if cant_ent > 0:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE catalogo_medicamentos SET existencia = existencia - ? WHERE id = ?", (cant_ent, m_id))
                                c.execute("""
                                    INSERT INTO entregas_medicamentos (paciente_id, med_id, cantidad_entregada, fecha, usuario)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (pid, m_id, cant_ent, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                                conn.commit()
                                conn.close()
                                st.balloons()
                                st.toast(f"✅ Entregadas {cant_ent} unidades de {m_nombre}.")
                                st.success("✅ Entrega realizada e inventario actualizado.")
                                st.rerun()

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        
        tab_sub, tab_list, tab_carp = st.tabs(["📤 Subir Documento", "📂 Consultar Repositorio", "📁 Personalizar Carpetas"])
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM carpetas_repositorio")
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()
        
        with tab_sub:
            with st.form("form_subir_doc"):
                f_up = st.file_uploader("Seleccione archivo (PDF, DOCX, XLSX, etc.)")
                cat_up = st.selectbox("Carpeta Destino", carpetas_list if carpetas_list else ["General"])
                btn_up = st.form_submit_button("📤 Guardar en Repositorio")
                
                if btn_up and f_up:
                    blob_data = f_up.read()
                    f_name = f_up.name
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO repositorio_documentos (nombre_archivo, categoria, archivo_blob, fecha_subida, usuario)
                        VALUES (?, ?, ?, ?, ?)
                    """, (f_name, cat_up, blob_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("✅ Archivo guardado en repositorio.")
                    st.success(f"✅ Documento '{f_name}' guardado en carpeta '{cat_up}'.")

        with tab_list:
            cat_filtro = st.selectbox("Filtrar por Carpeta", ["Todas las Carpetas"] + carpetas_list)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if cat_filtro == "Todas las Carpetas":
                c.execute("SELECT id, nombre_archivo, categoria, fecha_subida, usuario, archivo_blob FROM repositorio_documentos ORDER BY id DESC")
            else:
                c.execute("SELECT id, nombre_archivo, categoria, fecha_subida, usuario, archivo_blob FROM repositorio_documentos WHERE categoria = ? ORDER BY id DESC", (cat_filtro,))
            docs = c.fetchall()
            conn.close()
            
            if docs:
                for doc in docs:
                    doc_id, d_name, d_cat, d_fec, d_usr, d_blob = doc
                    col_d1, col_d2 = st.columns([3, 1])
                    with col_d1:
                        st.markdown(f"📄 **{d_name}** | Carpeta: `{d_cat}` | Subido: `{d_fec}` por `{d_usr}`")
                    with col_d2:
                        st.download_button(
                            label="📥 Descargar",
                            data=d_blob,
                            file_name=d_name,
                            key=f"dl_doc_{doc_id}"
                        )
            else:
                st.write("No hay documentos guardados en esta carpeta.")

        with tab_carp:
            st.subheader("Administración de Carpetas del Repositorio")
            
            with st.form("form_nueva_carpeta"):
                n_carp = st.text_input("Nombre de la Nueva Carpeta")
                btn_nc = st.form_submit_button("➕ Crear Carpeta")
                if btn_nc and n_carp.strip():
                    try:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (n_carp.strip(),))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("✅ Carpeta creada.")
                        st.success(f"✅ Carpeta '{n_carp.strip()}' creada.")
                        st.rerun()
                    except:
                        st.error("La carpeta ya existe.")

    # --- MÓDULO 10: BUSCAR Y LISTAR ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio General de Pacientes")
        pacientes = listar_pacientes_completos()
        
        busqueda = st.text_input("🔎 Buscar por Folio, Expediente o Nombre")
        if pacientes:
            for p in pacientes:
                pid, exp, nombre, etapa, etiqueta, d_json = p
                if not busqueda or busqueda.lower() in etiqueta.lower():
                    st.markdown(f"### 👤 {nombre}")
                    st.write(f"- Folio: **{pid}** | Expediente: **{exp}** | Etapa: **{etapa}**")
                    with st.expander("📄 Ver Expediente Completo"):
                        try:
                            st.json(json.loads(d_json))
                        except:
                            st.write(d_json)
                    st.markdown("---")

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")
        
        username_act = str(st.session_state.get("username", "")).strip().lower()
        rol_act = str(st.session_state.get("rol", "")).strip().lower()
        
        es_admin = (username_act == "admin" or rol_act in ["administrador", "admin"])
        
        if es_admin:
            tab_pass, tab_users = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_pass = st.container()
            tab_users = None
            
        with tab_pass:
            st.subheader("Cambiar Contraseña de la Cuenta Activa")
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
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(nueva_pass), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast("✅ Contraseña actualizada.")
                            st.success("✅ Contraseña modificada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

        if tab_users and es_admin:
            with tab_users:
                st.subheader("Dar de Alta Colaborador / Personal")
                with st.form("form_nuevo_usuario"):
                    nu_user = st.text_input("Usuario (Username) *")
                    nu_pass = st.text_input("Contraseña *", type="password")
                    nu_name = st.text_input("Nombre Completo *")
                    nu_rol = st.selectbox("Rol de Permisos", ["Administrador", "Lectura/Escritura", "Solo Lectura"])
                    btn_nu = st.form_submit_button("➕ Registrar Usuario")
                    
                    if btn_nu:
                        if not nu_user or not nu_pass or not nu_name:
                            st.error("Todos los campos marcados con * son obligatorios.")
                        else:
                            try:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("""
                                    INSERT INTO usuarios (username, password_hash, nombre_completo, rol)
                                    VALUES (?, ?, ?, ?)
                                """, (nu_user.strip(), hash_pass(nu_pass), nu_name.strip(), nu_rol))
                                conn.commit()
                                conn.close()
                                st.balloons()
                                st.toast(f"✅ Usuario {nu_user} registrado.")
                                st.success(f"✅ Colaborador '{nu_name}' registrado exitosamente con rol {nu_rol}.")
                            except sqlite3.IntegrityError:
                                st.error(f"⚠️ El nombre de usuario '{nu_user}' ya existe.")
                                
                st.markdown("---")
                st.subheader("👥 Usuarios Registrados en el Sistema")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol FROM usuarios")
                users_list = c.fetchall()
                conn.close()
                
                for u in users_list:
                    st.write(f"- 👤 **{u[2]}** (`{u[1]}`) | Rol: **{u[3]}**")

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        col_r1, col_r2 = st.columns(2)
        
        with col_r1:
            st.subheader("📥 Descargar Copia de Seguridad")
            st.write("Descargue el archivo de la base de datos `.db` con toda la información cargada.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="📥 Descargar Respaldo Completo (.db)",
                        data=f,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3"
                    )

        with col_r2:
            st.subheader("📤 Restaurar Copia de Seguridad")
            db_up = st.file_uploader("Cargar archivo de respaldo (.db)", type=["db", "sqlite", "sqlite3"])
            if db_up and st.button("⚠️ Confirmar Restauración"):
                with open(DB_FILE, "wb") as f:
                    f.write(db_up.read())
                st.balloons()
                st.toast("✅ Base de datos restaurada.")
                st.success("✅ Base de datos restaurada correctamente. Reiniciando sesión...")
                st.rerun()

if __name__ == "__main__":
    main()

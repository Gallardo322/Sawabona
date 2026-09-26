import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Consejería",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    """)
    
    # Migrar columna rol si no existe
    c.execute("PRAGMA table_info(usuarios)")
    cols = [col[1] for col in c.fetchall()]
    if 'rol' not in cols:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
    
    # 2. Pacientes / Registro
    c.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            tipo TEXT,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'ACTIVO',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            hermano_mayor_id TEXT
        )
    """)
    
    # 3. Entrevistas Iniciales
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 4. Fichas de Ingreso (NOM-028)
    c.execute("""
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 5. Consejerías Individuales
    c.execute("""
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            aspectos_trabajados TEXT,
            proximos_aspectos TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance_retroceso TEXT,
            sugerencia TEXT,
            expediente_num TEXT,
            usuario_registro TEXT
        )
    """)
    
    # 6. Grupos Terapéuticos
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha TEXT,
            tipo_grupo TEXT,
            etapa TEXT,
            facilitador TEXT,
            compartimiento TEXT,
            observaciones TEXT,
            devoluciones TEXT,
            compromiso TEXT,
            logros TEXT,
            dificultades TEXT,
            usuario_registro TEXT
        )
    """)
    
    # 7. Catálogo de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT
        )
    """)
    
    # 8. Medicamentos e Inventario
    c.execute("""
        CREATE TABLE IF NOT EXISTS dosis_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento TEXT,
            manana INTEGER DEFAULT 0,
            tarde INTEGER DEFAULT 0,
            noche INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventario_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicamento TEXT UNIQUE,
            existencia INTEGER DEFAULT 0
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha TEXT,
            medicamento TEXT,
            cantidad INTEGER,
            usuario_registro TEXT
        )
    """)
    
    # 9. Repositorio de Documentos y Carpetas
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    """)
    
    c.execute("""
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
    """)
    
    # Insertar carpetas por defecto si no existen
    carpetas_def = [
        "📋 Formatos Clínicos y Administrativos",
        "📖 Manuales de Operación",
        "⚖️ Reglamentos y Normativas",
        "📑 Plantillas de Evaluación",
        "📁 Documentos Generales"
    ]
    for c_def in carpetas_def:
        c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (c_def,))
        
    # Insertar usuario admin por defecto si no existe
    default_pass = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("""
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol)
            VALUES ('admin', ?, 'Administrador del Sistema', 'Nivel 1 - Administrador')
        """, (default_pass,))
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
    user = st.session_state.get("username", "")
    rol = st.session_state.get("rol", "")
    return user == "admin" or "Nivel 1" in rol or "Administrador" in rol

def es_lectura_escritura():
    rol = st.session_state.get("rol", "")
    return es_admin() or "Nivel 2" in rol

# --- CATÁLOGO OFICIAL DE CONSEJERÍAS POR ETAPA ---
PLAN_CONSEJERIAS = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGERSTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "IDENTIFICACIÓN": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "ELABORACIÓN": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJERIA) PREVENCIÓN DE RECAÍDAS.",
        "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
        "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
    ],
    "CONSOLIDACIÓN": [
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

DURACION_ETAPAS = {
    "ACOGIDA": 30,
    "IDENTIFICACIÓN": 60,
    "ELABORACIÓN": 60,
    "CONSOLIDACIÓN": 30,
    "SERVICIO SOCIAL": 30
}

# --- FUNCIONES DE APOYO Y HELPER ---
def obtener_pacientes_lista():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, nombre_completo, tipo, fecha_ingreso, etapa_actual, fecha_inicio_etapa, fecha_nacimiento, sexo FROM pacientes WHERE estatus = 'ACTIVO' ORDER BY nombre_completo")
    rows = c.fetchall()
    conn.close()
    return rows

# Inicializar DB siempre al arrancar
init_db()

# --- MANEJO DE SESIÓN DE USUARIO ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = ""

if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Comunidad Terapéutica - Sistema de Gestión e Historia Clínica</h3>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Iniciar Sesión")
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("🔑 Entrar al Sistema", use_container_width=True)
            
            if submit_login:
                res = verificar_login(user_input, pass_input)
                if res:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["nombre_completo"] = res[1]
                    st.session_state["rol"] = res[2] if len(res) > 2 and res[2] else "Nivel 1 - Administrador"
                    st.balloons()
                    st.toast("¡Bienvenido a Sawabona Shikoba!", icon="🎉")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
    st.stop()

# --- MENÚ LATERAL DE NAVEGACIÓN COMPLETO ---
st.sidebar.title("🌱 Sawabona Shikoba")
st.sidebar.caption(f"👤 Usuario: **{st.session_state['nombre_completo']}**\n\n🛡️ Rol: **{st.session_state['rol']}**")

menu_options = [
    "👤 Registro y Edición de Usuarios",
    "📄 Ficha de Ingreso y Admisión",
    "📝 Entrevista Inicial de Consejería",
    "📝 Consejerías Individuales",
    "🎯 Gestión de Etapas & Proceso",
    "🗣️ Grupos Terapéuticos",
    "💊 Control de Medicamentos",
    "📁 Repositorio de Documentos",
    "🔍 Buscar y Listar Pacientes",
    "⚙️ Configuración & Seguridad",
    "📦 Respaldo y Restauración"
]

menu = st.sidebar.radio("📌 Menú Principal", menu_options)

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.rerun()

# ==============================================================================
# 1. 👤 REGISTRO Y EDICIÓN DE USUARIOS / RESIDENTES
# ==============================================================================
if menu == "👤 Registro y Edición de Usuarios":
    st.title("👤 Registro y Edición de Residentes")
    st.write("Administra las fichas de los usuarios/residentes de la comunidad, sus fechas basales de ingreso y etapa actual.")
    
    tab1, tab2 = st.tabs(["➕ Registrar Nuevo Residente", "✏️ Editar Residente Existente"])
    
    with tab1:
        st.subheader("Datos de Registro")
        with st.form("form_nuevo_paciente"):
            c1, c2 = st.columns(2)
            with c1:
                folio = st.text_input("Folio / ID de Paciente (ej. PAC-001)")
                nombre = st.text_input("Nombre Completo del Residente")
                tipo = st.selectbox("Tipo de Usuario", ["Usuario en Tratamiento", "Hermano Mayor", "Staff / Voluntario"])
                sexo = st.selectbox("Sexo", ["Masculino", "Femenino"])
            with c2:
                fecha_nac = st.date_input("Fecha de Nacimiento", value=datetime(1995, 1, 1))
                fecha_ingreso = st.date_input("Fecha de Ingreso Real a la Comunidad", value=datetime.today())
                etapa_ini = st.selectbox("Etapa Inicial en el Sistema", list(PLAN_CONSEJERIAS.keys()))
                fecha_inicio_etapa = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.today())
                
            btn_guardar = st.form_submit_button("💾 Registrar Residente", use_container_width=True)
            if btn_guardar:
                if not folio or not nombre:
                    st.error("El Folio y el Nombre Completo son obligatorios.")
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT OR REPLACE INTO pacientes 
                        (paciente_id, nombre_completo, tipo, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, fecha_inicio_etapa)
                        VALUES (?, ?, ?, ?, ?, ?, 'ACTIVO', ?, ?)
                    """, (folio, nombre, tipo, fecha_ingreso.strftime("%Y-%m-%d"), fecha_nac.strftime("%Y-%m-%d"), sexo, etapa_ini, fecha_inicio_etapa.strftime("%Y-%m-%d")))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Residente registrado correctamente!", icon="🎉")
                    st.success(f"✅ Residente {nombre} ({folio}) dado de alta en Etapa {etapa_ini}.")

    with tab2:
        st.subheader("Editar Residente")
        pacientes = obtener_pacientes_lista()
        if not pacientes:
            st.info("No hay residentes registrados.")
        else:
            opciones_pac = {f"{p[0]} - {p[1]} ({p[4]})": p for p in pacientes}
            sel = st.selectbox("🔑 Selecciona el Residente a Editar", list(opciones_pac.keys()))
            p_data = opciones_pac[sel]
            p_id = p_data[0]
            
            with st.form(f"form_edit_pac_{p_id}"):
                c1, c2 = st.columns(2)
                with c1:
                    e_nombre = st.text_input("Nombre Completo", value=p_data[1])
                    e_tipo = st.selectbox("Tipo de Usuario", ["Usuario en Tratamiento", "Hermano Mayor", "Staff / Voluntario"], index=0 if p_data[2] == "Usuario en Tratamiento" else 1)
                    e_sexo = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if p_data[7] == "Masculino" else 1)
                    
                    try:
                        f_nac_val = datetime.strptime(p_data[6], "%Y-%m-%d")
                    except:
                        f_nac_val = datetime(1995, 1, 1)
                    e_f_nac = st.date_input("Fecha de Nacimiento", value=f_nac_val)
                    
                with c2:
                    try:
                        f_ing_val = datetime.strptime(p_data[3], "%Y-%m-%d")
                    except:
                        f_ing_val = datetime.today()
                    e_f_ing = st.date_input("Fecha de Ingreso Real a la Comunidad", value=f_ing_val)
                    
                    etapas_lst = list(PLAN_CONSEJERIAS.keys())
                    idx_etapa = etapas_lst.index(p_data[4]) if p_data[4] in etapas_lst else 0
                    e_etapa = st.selectbox("Etapa Actual", etapas_lst, index=idx_etapa)
                    
                    try:
                        f_ietapa_val = datetime.strptime(p_data[5], "%Y-%m-%d") if p_data[5] else datetime.today()
                    except:
                        f_ietapa_val = datetime.today()
                    e_f_ietapa = st.date_input("Fecha de Inicio de Etapa Actual", value=f_ietapa_val)
                    
                btn_mod = st.form_submit_button("💾 Actualizar Residente", use_container_width=True)
                if btn_mod:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        UPDATE pacientes 
                        SET nombre_completo = ?, tipo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, etapa_actual = ?, fecha_inicio_etapa = ?
                        WHERE paciente_id = ?
                    """, (e_nombre, e_tipo, e_f_ing.strftime("%Y-%m-%d"), e_f_nac.strftime("%Y-%m-%d"), e_sexo, e_etapa, e_f_ietapa.strftime("%Y-%m-%d"), p_id))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Datos del residente actualizados!", icon="🎉")
                    st.success(f"✅ Se actualizaron los datos de {e_nombre}.")

# ==============================================================================
# 2. 📄 FICHA DE INGRESO Y ADMISIÓN (NOM-028)
# ==============================================================================
elif menu == "📄 Ficha de Ingreso y Admisión":
    st.title("📄 Ficha de Ingreso y Admisión de Residente")
    st.write("Formulario oficial de ingreso a la Comunidad Terapéutica Sawabona Shikoba A.C.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.warning("Primero debes registrar al menos un residente en '👤 Registro y Edición de Usuarios'.")
    else:
        opciones_pac = {f"{p[0]} - {p[1]}": p for p in pacientes}
        sel_pac = st.selectbox("🔑 Selecciona el Residente para la Ficha de Ingreso", list(opciones_pac.keys()))
        pac_data = opciones_pac[sel_pac]
        p_id = pac_data[0]
        
        tab1, tab2 = st.tabs(["📝 Formulario de Ficha de Ingreso", "🖨️ Consultar e Imprimir PDF"])
        
        with tab1:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
            row_ficha = c.fetchone()
            conn.close()
            
            d_ficha = json.loads(row_ficha[0]) if row_ficha else {}
            
            with st.form("form_ficha_ingreso"):
                st.subheader("1. Datos del Responsable Familiar")
                c1, c2 = st.columns(2)
                with c1:
                    resp_nombre = st.text_input("Nombre Completo del Responsable", value=d_ficha.get("responsable_nombre", ""))
                    resp_parentesco = st.text_input("Parentesco (ej. Padre, Madre, Cónyuge)", value=d_ficha.get("responsable_parentesco", ""))
                with c2:
                    resp_tel = st.text_input("Teléfono de Contacto", value=d_ficha.get("responsable_tel", ""))
                    resp_domicilio = st.text_input("Domicilio del Responsable", value=d_ficha.get("responsable_domicilio", ""))
                    
                st.subheader("2. Datos Generales del Residente")
                c1, c2, c3 = st.columns(3)
                with c1:
                    est_civil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                    escolaridad = st.text_input("Escolaridad", value=d_ficha.get("escolaridad", "Secundaria"))
                with c2:
                    religion = st.text_input("Religión", value=d_ficha.get("religion", "Católica"))
                    ocupacion = st.text_input("Ocupación", value=d_ficha.get("ocupacion", "Empleado"))
                with c3:
                    servicio_medico = st.text_input("Servicio Médico (ej. IMSS, ISSSTE, Ninguno)", value=d_ficha.get("servicio_medico", "Ninguno"))
                    domicilio_pac = st.text_input("Domicilio Completo del Residente", value=d_ficha.get("domicilio_paciente", ""))
                    
                st.subheader("3. Consumo de Sustancias")
                sustancias_opts = ["Alcohol", "Cannabis (Marihuana)", "Cocaína", "Metanfetamina (Cristal)", "Tabaco", "Benzodiazepinas", "Inhalables", "Heroína/Opiáceos"]
                sust_sel = st.multiselect("Sustancias Consumidas", sustancias_opts, default=d_ficha.get("sustancias", ["Alcohol", "Metanfetamina (Cristal)"]))
                sust_impacto = st.selectbox("Sustancia de Impacto Principal", sustancias_opts, index=0)
                
                st.subheader("4. Términos Financieros y Modalidad")
                c1, c2, c3 = st.columns(3)
                with c1:
                    costo_ingreso = st.number_input("Costo de Ingreso ($)", value=float(d_ficha.get("costo_ingreso", 4500.0)))
                with c2:
                    mensualidad = st.number_input("Costo Mensual ($)", value=float(d_ficha.get("mensualidad", 6000.0)))
                with c3:
                    pagare = st.number_input("Importe Pagaré ($)", value=float(d_ficha.get("pagare", 42000.0)))
                    
                modalidad = st.radio("Modalidad de Internamiento (NOM-028-SSA2-2009)", ["VOLUNTARIO", "INVOLUNTARIO"], index=0)
                
                btn_f = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                if btn_f:
                    datos_guardar = {
                        "responsable_nombre": resp_nombre,
                        "responsable_parentesco": resp_parentesco,
                        "responsable_tel": resp_tel,
                        "responsable_domicilio": resp_domicilio,
                        "estado_civil": est_civil,
                        "escolaridad": escolaridad,
                        "religion": religion,
                        "ocupacion": ocupacion,
                        "servicio_medico": servicio_medico,
                        "domicilio_paciente": domicilio_pac,
                        "sustancias": sust_sel,
                        "sustancia_impacto": sust_impacto,
                        "costo_ingreso": costo_ingreso,
                        "mensualidad": mensualidad,
                        "pagare": pagare,
                        "modalidad": modalidad
                    }
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT OR REPLACE INTO fichas_ingreso (paciente_id, fecha_registro, usuario_registro, datos_json)
                        VALUES (?, ?, ?, ?)
                    """, (p_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], json.dumps(datos_guardar, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Ficha de Ingreso guardada con éxito!", icon="🎉")
                    st.success("✅ Ficha de Ingreso registrada correctamente.")

        with tab2:
            st.subheader("Resumen e Impresión")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json, fecha_registro FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
            row_f = c.fetchone()
            conn.close()
            
            if not row_f:
                st.info("Aún no se ha capturado la Ficha de Ingreso para este residente.")
            else:
                dj = json.loads(row_f[0])
                st.markdown(f"**Residente**: {pac_data[1]} | **Folio**: {p_id}")
                st.markdown(f"**Responsable**: {dj.get('responsable_nombre')} ({dj.get('responsable_parentesco')}) - Tel: {dj.get('responsable_tel')}")
                st.markdown(f"**Modalidad**: {dj.get('modalidad')} | **Sustancia de Impacto**: {dj.get('sustancia_impacto')}")
                st.markdown(f"**Costo Ingreso**: ${dj.get('costo_ingreso')} | **Mensualidad**: ${dj.get('mensualidad')}")
                
                def generar_pdf_ficha():
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 14)
                    pdf.cell(0, 10, "COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.", 0, 1, "C")
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 8, "FICHA OFICIAL DE INGRESO Y ADMISIÓN DE RESIDENTE", 0, 1, "C")
                    pdf.set_font("Arial", "I", 9)
                    pdf.cell(0, 6, "Apegado a la Norma Oficial Mexicana NOM-028-SSA2-2009", 0, 1, "C")
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", "B", 10)
                    pdf.cell(0, 6, f"DATOS DE ADMISIÓN - FOLIO: {p_id}", 1, 1, "L")
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(0, 5, f"Fecha de Ingreso: {pac_data[3]} | Nombre: {pac_data[1]}", 0, 1)
                    pdf.cell(0, 5, f"Fecha Nacimiento: {pac_data[6]} | Sexo: {pac_data[7]}", 0, 1)
                    pdf.cell(0, 5, f"Estado Civil: {dj.get('estado_civil')} | Escolaridad: {dj.get('escolaridad')} | Ocupación: {dj.get('ocupacion')}", 0, 1)
                    pdf.cell(0, 5, f"Domicilio: {dj.get('domicilio_paciente')}", 0, 1)
                    pdf.ln(3)
                    
                    pdf.set_font("Arial", "B", 10)
                    pdf.cell(0, 6, "DATOS DEL RESPONSABLE FAMILIAR", 1, 1, "L")
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(0, 5, f"Nombre: {dj.get('responsable_nombre')} | Parentesco: {dj.get('responsable_parentesco')}", 0, 1)
                    pdf.cell(0, 5, f"Teléfono: {dj.get('responsable_tel')} | Domicilio: {dj.get('responsable_domicilio')}", 0, 1)
                    pdf.ln(3)
                    
                    pdf.set_font("Arial", "B", 10)
                    pdf.cell(0, 6, "DIAGNÓSTICO INICIAL Y SUSTANCIAS", 1, 1, "L")
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(0, 5, f"Sustancia de Impacto Principal: {dj.get('sustancia_impacto')}", 0, 1)
                    pdf.cell(0, 5, f"Sustancias Consumidas: {', '.join(dj.get('sustancias', []))}", 0, 1)
                    pdf.cell(0, 5, f"Modalidad de Internamiento: {dj.get('modalidad')}", 0, 1)
                    pdf.ln(3)
                    
                    pdf.set_font("Arial", "B", 10)
                    pdf.cell(0, 6, "TÉRMINOS ECONÓMICOS Y COMPROMISO", 1, 1, "L")
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(0, 5, f"Costo de Ingreso: ${dj.get('costo_ingreso')} | Mensualidad: ${dj.get('mensualidad')} | Pagaré: ${dj.get('pagare')}", 0, 1)
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", "I", 8)
                    pdf.multi_cell(0, 4, "DECLARACIÓN Y AUTORIZACIÓN: Por medio del presente documento se autoriza el ingreso voluntario/involuntario del residente a la Comunidad Terapéutica Sawabona Shikoba A.C., aceptando los reglamentos internos y compromisos del proceso de rehabilitación.")
                    pdf.ln(15)
                    
                    pdf.cell(90, 6, "___________________________________", 0, 0, "C")
                    pdf.cell(90, 6, "___________________________________", 0, 1, "C")
                    pdf.cell(90, 5, "Firma del Responsable Familiar", 0, 0, "C")
                    pdf.cell(90, 5, "Firma del Director / Encargado", 0, 1, "C")
                    
                    return pdf.output(dest='S').encode('latin-1', errors='replace')
                
                pdf_bytes = generar_pdf_ficha()
                st.download_button(
                    "🖨️ Descargar Ficha de Ingreso en PDF",
                    data=pdf_bytes,
                    file_name=f"ficha_ingreso_{p_id}.pdf",
                    mime="application/pdf"
                )

# ==============================================================================
# 3. 📝 ENTREVISTA INICIAL DE CONSEJERÍA
# ==============================================================================
elif menu == "📝 Entrevista Inicial de Consejería":
    st.title("📋 Entrevista Inicial de Consejería")
    st.write("Evaluación clínica detallada e historia de consumo del residente.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.warning("Primero debes registrar al menos un residente.")
    else:
        opciones_pac = {f"{p[0]} - {p[1]}": p for p in pacientes}
        sel_pac = st.selectbox("🔑 Selecciona el Residente para la Entrevista", list(opciones_pac.keys()))
        pac_data = opciones_pac[sel_pac]
        p_id = pac_data[0]
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (p_id,))
        row_e = c.fetchone()
        conn.close()
        
        d_ent = json.loads(row_e[0]) if row_e else {}
        
        with st.form("form_entrevista_inicial"):
            st.subheader("1. Historial de Consumo y Adicciones")
            c1, c2 = st.columns(2)
            with c1:
                edad_inicio = st.number_input("Edad de Inicio de Consumo", min_value=5, max_value=80, value=int(d_ent.get("edad_inicio", 15)))
                motivo_ingreso = st.text_area("Motivo de Ingreso / Crisis Actual", value=d_ent.get("motivo_ingreso", ""))
            with c2:
                intentos_previos = st.number_input("Tratamientos Previos / Anexos", min_value=0, max_value=50, value=int(d_ent.get("intentos_previos", 0)))
                patron_consumo = st.text_area("Patrón de Consumo (Diario, Fines de semana, Binge)", value=d_ent.get("patron_consumo", ""))
                
            st.subheader("2. Evaluación Social, Familiar y Psicológica")
            c1, c2 = st.columns(2)
            with c1:
                dinamica_familiar = st.text_area("Dinámica Familiar y Apoyo Red Social", value=d_ent.get("dinamica_familiar", ""))
                antecedentes_medicos = st.text_area("Antecedentes Médicos / Enfermedades", value=d_ent.get("antecedentes_medicos", ""))
            with c2:
                estado_disposicion = st.select_slider("Disposición al Cambio", options=["Precontemplación", "Contemplación", "Preparación", "Acción", "Mantenimiento"], value=d_ent.get("estado_disposicion", "Contemplación"))
                diagnostico_consejero = st.text_area("Diagnóstico del Consejero e Impresión Diagnóstica", value=d_ent.get("diagnostico_consejero", ""))
                
            btn_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
            if btn_ent:
                d_save = {
                    "edad_inicio": edad_inicio,
                    "motivo_ingreso": motivo_ingreso,
                    "intentos_previos": intentos_previos,
                    "patron_consumo": patron_consumo,
                    "dinamica_familiar": dinamica_familiar,
                    "antecedentes_medicos": antecedentes_medicos,
                    "estado_disposicion": estado_disposicion,
                    "diagnostico_consejero": diagnostico_consejero
                }
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (p_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"], json.dumps(d_save, ensure_ascii=False)))
                conn.commit()
                conn.close()
                st.balloons()
                st.toast("¡Entrevista Inicial guardada exitosamente!", icon="🎉")
                st.success("✅ Historia clínica guardada.")

# ==============================================================================
# 4. 📝 CONSEJERÍAS INDIVIDUALES (SEGUIMIENTO POR PLAN DE CONSEJERÍA)
# ==============================================================================
elif menu == "📝 Consejerías Individuales":
    st.title("📝 Consejerías Individuales y Seguimiento")
    st.write("Registro continuo de consejerías individuales conforme al Plan Oficial de Consejería.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.warning("Primero debes registrar residentes.")
    else:
        opciones_pac = {f"{p[0]} - {p[1]} ({p[4]})": p for p in pacientes}
        sel_pac = st.selectbox("🔑 Selecciona el Residente", list(opciones_pac.keys()))
        p_data = opciones_pac[sel_pac]
        p_id = p_data[0]
        etapa_act = p_data[4]
        
        try:
            f_nac = datetime.strptime(p_data[6], "%Y-%m-%d")
            edad_calc = (datetime.now() - f_nac).days // 365
        except:
            edad_calc = 0
            
        tab1, tab2 = st.tabs(["📝 Registrar Nueva Consejería", "📜 Historial e Impresión PDF"])
        
        with tab1:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?", (p_id, etapa_act))
            num_cons_prev = c.fetchone()[0]
            conn.close()
            
            num_cons_actual = num_cons_prev + 1
            cat_etapa = PLAN_CONSEJERIAS.get(etapa_act, [])
            
            aspecto_sugerido = cat_etapa[num_cons_prev] if num_cons_prev < len(cat_etapa) else "Consejería de Refuerzo / Seguimiento Especial"
            proximo_sugerido = cat_etapa[num_cons_actual] if num_cons_actual < len(cat_etapa) else "Siguiente Etapa o Evaluación de Promoción"
            
            st.info(f"📌 **Etapa Actual**: {etapa_act} | **Consejería N°**: {num_cons_actual} de {len(cat_etapa)}")
            
            with st.form("form_nueva_consejeria"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.text_input("Nombre del Residente", value=p_data[1], disabled=True)
                    st.text_input("Edad", value=f"{edad_calc} años", disabled=True)
                with c2:
                    st.text_input("Sexo", value=p_data[7], disabled=True)
                    expediente_num = st.text_input("N° de Expediente Institucional", value=f"EXP-{p_id}")
                with c3:
                    fecha_cons = st.date_input("Fecha de Consejería", value=datetime.today())
                    fecha_prox = st.date_input("Fecha de Próxima Consejería (+7 días)", value=datetime.today() + timedelta(days=7))
                    
                st.subheader("Aspectos a Trabajar")
                aspectos = st.text_area("Aspectos Trabajados en esta Sesión", value=aspecto_sugerido, height=70)
                proximos = st.text_area("Aspectos a Trabajar en la Próxima Consejería", value=proximo_sugerido, height=70)
                
                st.subheader("Notas Clínicas de la Sesión")
                exposicion = st.text_area("Exposición (Texto del Paciente / Temas Compartidos)", height=100)
                avance_retro = st.text_area("Avance / Retroceso (Observaciones Clínicas)", height=90)
                sugerencia = st.text_area("Sugerencias y Tareas Asignadas", height=90)
                
                btn_g_cons = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)
                if btn_g_cons:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO consejerias 
                        (paciente_id, fecha, etapa, num_consejeria, aspectos_trabajados, proximos_aspectos, fecha_proxima, exposicion, avance_retroceso, sugerencia, expediente_num, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_id, fecha_cons.strftime("%Y-%m-%d"), etapa_act, num_cons_actual, aspectos, proximos, fecha_prox.strftime("%Y-%m-%d"), exposicion, avance_retro, sugerencia, expediente_num, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Consejería guardada correctamente!", icon="🎉")
                    st.success(f"✅ Consejería #{num_cons_actual} en Etapa {etapa_act} registrada.")

        with tab2:
            st.subheader("Historial de Consejerías")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, fecha, etapa, num_consejeria, aspectos_trabajados, exposicion, avance_retroceso, sugerencia, fecha_proxima FROM consejerias WHERE paciente_id = ? ORDER BY id DESC", (p_id,))
            rows_cons = c.fetchall()
            conn.close()
            
            if not rows_cons:
                st.info("No hay consejerías registradas para este residente.")
            else:
                for rc in rows_cons:
                    with st.expander(f"📅 Consejería #{rc[3]} - Etapa {rc[2]} ({rc[1]})"):
                        st.markdown(f"**Aspectos Trabajados**: {rc[4]}")
                        st.markdown(f"**Exposición**: {rc[5]}")
                        st.markdown(f"**Avance / Retroceso**: {rc[6]}")
                        st.markdown(f"**Sugerencias**: {rc[7]}")
                        st.markdown(f"**Próxima Consejería**: {rc[8]}")
                        
                        def gen_pdf_cons(data_c):
                            pdf = FPDF()
                            pdf.add_page()
                            pdf.set_font("Arial", "B", 14)
                            pdf.cell(0, 10, "SAWABONA SHIKOBA A.C. - HOJA DE CONSEJERÍA INDIVIDUAL", 0, 1, "C")
                            pdf.set_font("Arial", "", 10)
                            pdf.cell(0, 6, f"Residente: {p_data[1]} | Folio: {p_id} | Edad: {edad_calc} años", 0, 1)
                            pdf.cell(0, 6, f"Etapa: {data_c[2]} | Consejería N°: {data_c[3]} | Fecha: {data_c[1]}", 0, 1)
                            pdf.ln(5)
                            
                            pdf.set_font("Arial", "B", 10)
                            pdf.cell(0, 6, "ASPECTOS TRABAJADOS", 1, 1, "L")
                            pdf.set_font("Arial", "", 9)
                            pdf.multi_cell(0, 5, str(data_c[4]))
                            pdf.ln(3)
                            
                            pdf.set_font("Arial", "B", 10)
                            pdf.cell(0, 6, "EXPOSICIÓN Y NOTAS DEL PACIENTE", 1, 1, "L")
                            pdf.set_font("Arial", "", 9)
                            pdf.multi_cell(0, 5, str(data_c[5]))
                            pdf.ln(3)
                            
                            pdf.set_font("Arial", "B", 10)
                            pdf.cell(0, 6, "EVOLUCIÓN (AVANCE / RETROCESO)", 1, 1, "L")
                            pdf.set_font("Arial", "", 9)
                            pdf.multi_cell(0, 5, str(data_c[6]))
                            pdf.ln(3)
                            
                            pdf.set_font("Arial", "B", 10)
                            pdf.cell(0, 6, "SUGERENCIAS Y COMPROMISOS", 1, 1, "L")
                            pdf.set_font("Arial", "", 9)
                            pdf.multi_cell(0, 5, str(data_c[7]))
                            pdf.ln(15)
                            
                            pdf.cell(90, 6, "___________________________________", 0, 0, "C")
                            pdf.cell(90, 6, "___________________________________", 0, 1, "C")
                            pdf.cell(90, 5, "Firma del Consejero", 0, 0, "C")
                            pdf.cell(90, 5, "Firma del Residente", 0, 1, "C")
                            
                            return pdf.output(dest='S').encode('latin-1', errors='replace')
                            
                        pdf_c_bytes = gen_pdf_cons(rc)
                        st.download_button(
                            f"🖨️ Descargar PDF Consejería #{rc[3]}",
                            data=pdf_c_bytes,
                            file_name=f"consejeria_{p_id}_{rc[3]}.pdf",
                            mime="application/pdf",
                            key=f"btn_pdf_cons_{rc[0]}"
                        )

# ==============================================================================
# 5. 🎯 GESTIÓN DE ETAPAS & PROCESO Y REZAGOS
# ==============================================================================
elif menu == "🎯 Gestión de Etapas & Proceso":
    st.title("🎯 Gestión de Etapas, Rezagos y Proceso Terapéutico")
    st.write("Monitoreo de estancia, checklist dinámico de requisitos y evaluación de rezago clínico.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.warning("No hay residentes registrados.")
    else:
        opciones_pac = {f"{p[0]} - {p[1]} ({p[4]})": p for p in pacientes}
        sel_pac = st.selectbox("🔑 Selecciona el Residente a Evaluar", list(opciones_pac.keys()))
        p_data = opciones_pac[sel_pac]
        p_id = p_data[0]
        etapa_act = p_data[4]
        
        try:
            f_ing = datetime.strptime(p_data[3], "%Y-%m-%d")
            dias_totales = (datetime.now() - f_ing).days
        except:
            dias_totales = 0
            
        try:
            f_ietapa = datetime.strptime(p_data[5], "%Y-%m-%d") if p_data[5] else datetime.now()
            dias_etapa = (datetime.now() - f_ietapa).days
        except:
            dias_etapa = 0
            
        duracion_estandar = DURACION_ETAPAS.get(etapa_act, 30)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa = ?", (p_id, etapa_act))
        grupos_hechos = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?", (p_id, etapa_act))
        consejerias_hechas = c.fetchone()[0]
        conn.close()
        
        total_cons_req = len(PLAN_CONSEJERIAS.get(etapa_act, []))
        
        st.subheader("📊 Diagnóstico de Estancia y Rezago")
        c1, c2, c3 = st.columns(3)
        c1.metric("🗓️ Días Totales en Comunidad", f"{dias_totales} días")
        c2.metric("⏱️ Días en Etapa Actual", f"{dias_etapa} días", f"Máx. Estándar: {duracion_estandar} días")
        c3.metric("📝 Consejerías de Etapa", f"{consejerias_hechas} / {total_cons_req}")
        
        if dias_etapa > duracion_estandar:
            exceso = dias_etapa - duracion_estandar
            st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El residente lleva **{dias_totales} días internado** y suma **{dias_etapa} días en la Etapa {etapa_act}** (Duración recomendada: {duracion_estandar} días). Presenta un retraso de **+{exceso} días**.")
        else:
            st.success(f"✅ El residente se encuentra dentro del tiempo estándar de su etapa ({dias_etapa} de {duracion_estandar} días).")
            
        st.subheader("📋 Checklist de Requisitos para Promoción")
        st.markdown(f"**1. Consejerías Individuales**: {'✅ COMPLETADO' if consejerias_hechas >= total_cons_req else f'❌ PENDIENTE ({consejerias_hechas}/{total_cons_req})'}")
        st.markdown(f"**2. Asistencia a Grupos Terapéuticos**: {'✅ REGISTRADOS' if grupos_hechos >= 4 else f'❌ PENDIENTE ({grupos_hechos}/4 mínimos)'}")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            req_auto = st.checkbox("Autobiografía / Carta de Entrada Entregada", value=True if etapa_act != "ACOGIDA" else False)
            req_reglas = st.checkbox("Aceptación de Reglamentos y Convivencia", value=True)
        with col_p2:
            req_proyecto = st.checkbox("Proyecto de Vida Presentado", value=True if etapa_act in ["CONSOLIDACIÓN", "SERVICIO SOCIAL"] else False)
            
        listo_promocion = (consejerias_hechas >= total_cons_req) and (grupos_hechos >= 2) and req_auto and req_reglas
        
        st.write("---")
        if listo_promocion:
            st.success("🎉 ¡El residente ha cumplido con todos los requisitos para su promoción de etapa!")
            etapas_lista = list(PLAN_CONSEJERIAS.keys())
            idx_a = etapas_lista.index(etapa_act)
            if idx_a < len(etapas_lista) - 1:
                sig_etapa = etapas_lista[idx_a + 1]
                if st.button(f"🎉 Promover Residente a Etapa {sig_etapa}", use_container_width=True):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        UPDATE pacientes 
                        SET etapa_actual = ?, fecha_inicio_etapa = ?
                        WHERE paciente_id = ?
                    """, (sig_etapa, datetime.now().strftime("%Y-%m-%d"), p_id))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast(f"¡Promovido a {sig_etapa}!", icon="🎉")
                    st.success(f"✅ El residente fue promovido exitosamente a la Etapa {sig_etapa}.")
        else:
            st.warning("⚠️ El botón de promoción se activará cuando se completen las consejerías y requisitos pendientes de la etapa.")

# ==============================================================================
# 6. 🗣️ GRUPOS TERAPÉUTICOS
# ==============================================================================
elif menu == "🗣️ Grupos Terapéuticos":
    st.title("🗣️ Registro de Grupos Terapéuticos")
    st.write("Bitácora de participación en Terapia de Grupo, Aquí y Ahora y Feedback.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.warning("No hay residentes registrados.")
    else:
        opciones_pac = {f"{p[0]} - {p[1]} ({p[4]})": p for p in pacientes}
        sel_pac = st.selectbox("🔑 Selecciona el Residente", list(opciones_pac.keys()))
        p_data = opciones_pac[sel_pac]
        p_id = p_data[0]
        etapa_act = p_data[4]
        
        tab1, tab2 = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        with tab1:
            with st.form("form_grupo_terapeutico"):
                c1, c2 = st.columns(2)
                with c1:
                    tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                    facilitador = st.text_input("Facilitador / Staff a Cargo", value=st.session_state["nombre_completo"])
                with c2:
                    fecha_g = st.date_input("Fecha de la Sesión", value=datetime.today())
                    st.text_input("Etapa del Residente", value=etapa_act, disabled=True)
                    
                st.subheader("Desarrollo de la Sesión")
                compartimiento = st.text_area("Compartimiento / Tema Expuesto", height=90)
                observaciones = st.text_area("Observaciones Clínicas", height=80)
                devoluciones = st.text_area("Devoluciones del Grupo y Consejero", height=80)
                compromiso = st.text_area("¿Cómo se queda y a qué se compromete?", height=80)
                
                logros = ""
                dificultades = ""
                if tipo_grupo == "Feedback":
                    logros = st.text_area("Logros Observados", height=60)
                    dificultades = st.text_area("Dificultades Afrontadas", height=60)
                    
                btn_g_grupo = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                if btn_g_grupo:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO grupos_terapeuticos 
                        (paciente_id, fecha, tipo_grupo, etapa, facilitador, compartimiento, observaciones, devoluciones, compromiso, logros, dificultades, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_id, fecha_g.strftime("%Y-%m-%d"), tipo_grupo, etapa_act, facilitador, compartimiento, observaciones, devoluciones, compromiso, logros, dificultades, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Sesión de grupo registrada!", icon="🎉")
                    st.success("✅ Sesión guardada en el historial del residente.")

        with tab2:
            st.subheader("Historial de Grupos Terapéuticos")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, fecha, tipo_grupo, etapa, facilitador, compartimiento, devoluciones, compromiso FROM grupos_terapeuticos WHERE paciente_id = ? ORDER BY id DESC", (p_id,))
            rows_g = c.fetchall()
            conn.close()
            
            if not rows_g:
                st.info("No hay registros de grupos para este residente.")
            else:
                for rg in rows_g:
                    with st.expander(f"🗣️ {rg[2]} - {rg[1]} (Facilitador: {rg[4]})"):
                        st.markdown(f"**Compartimiento**: {rg[5]}")
                        st.markdown(f"**Devoluciones**: {rg[6]}")
                        st.markdown(f"**Compromiso**: {rg[7]}")

# ==============================================================================
# 7. 💊 CONTROL DE MEDICAMENTOS E INVENTARIO
# ==============================================================================
elif menu == "💊 Control de Medicamentos":
    st.title("💊 Control de Medicamentos e Inventario")
    st.write("Catálogo central, recetario por paciente, entregas en almacén y reportes de consumo.")
    
    tab1, tab2, tab3, tab4 = st.tabs(["💊 Catálogo Central", "📋 Dosis por Paciente", "📦 Entregas en Almacén", "📊 Reporte de Consumo"])
    
    with tab1:
        st.subheader("Catálogo Central de Fármacos")
        with st.form("form_cat_med"):
            c1, c2, c3 = st.columns(3)
            m_nombre = c1.text_input("Nombre del Medicamento")
            m_pres = c2.selectbox("Presentación", ["Comprimidos", "Cápsulas", "Gotas", "Jarabe", "Inyectable", "Solución"])
            m_conc = c3.text_input("Concentración (ej. 500 mg, 20 mg)")
            
            btn_cat = st.form_submit_button("➕ Agregar al Catálogo", use_container_width=True)
            if btn_cat:
                if m_nombre:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion) VALUES (?, ?, ?)", (m_nombre, m_pres, m_conc))
                        c.execute("INSERT OR IGNORE INTO inventario_medicamentos (medicamento, existencia) VALUES (?, 0)", (m_nombre,))
                        conn.commit()
                        st.balloons()
                        st.toast("¡Medicamento agregado al catálogo!", icon="🎉")
                        st.success(f"✅ {m_nombre} registrado.")
                    except:
                        st.error("El medicamento ya existe en el catálogo.")
                    conn.close()

    with tab2:
        st.subheader("Configurar Receta / Dosis por Paciente")
        pacientes = obtener_pacientes_lista()
        if pacientes:
            opciones_pac = {f"{p[0]} - {p[1]}": p for p in pacientes}
            sel_pac = st.selectbox("🔑 Selecciona Residente", list(opciones_pac.keys()), key="sel_med_p")
            p_id = opciones_pac[sel_pac][0]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT nombre FROM catalogo_medicamentos ORDER BY nombre")
            meds_cat = [r[0] for r in c.fetchall()]
            conn.close()
            
            if not meds_cat:
                st.info("Primero agrega medicamentos al Catálogo Central.")
            else:
                with st.form("form_dosis_pac"):
                    med_sel = st.selectbox("Medicamento", meds_cat)
                    c1, c2, c3 = st.columns(3)
                    d_m = c1.number_input("Mañana (unidades)", min_value=0, max_value=10, value=1)
                    d_t = c2.number_input("Tarde (unidades)", min_value=0, max_value=10, value=0)
                    d_n = c3.number_input("Noche (unidades)", min_value=0, max_value=10, value=1)
                    indic = st.text_input("Indicaciones Médicas", value="Tomar con alimentos")
                    
                    btn_dosis = st.form_submit_button("💾 Guardar Dosis de Medicamento", use_container_width=True)
                    if btn_dosis:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO dosis_medicamentos (paciente_id, medicamento, manana, tarde, noche, indicaciones)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (p_id, med_sel, d_m, d_t, d_n, indic))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Esquema de dosis guardado!", icon="🎉")
                        st.success("✅ Dosis registrada para el residente.")

    with tab3:
        st.subheader("📦 Entrega Diaria desde Almacén")
        pacientes = obtener_pacientes_lista()
        if pacientes:
            opciones_pac = {f"{p[0]} - {p[1]}": p for p in pacientes}
            sel_pac = st.selectbox("🔑 Selecciona Residente para Entrega", list(opciones_pac.keys()), key="sel_ent_p")
            p_id = opciones_pac[sel_pac][0]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT d.medicamento, d.manana + d.tarde + d.noche AS total_dosis, COALESCE(i.existencia, 0)
                FROM dosis_medicamentos d
                LEFT JOIN inventario_medicamentos i ON d.medicamento = i.medicamento
                WHERE d.paciente_id = ?
            """, (p_id,))
            receta = c.fetchall()
            conn.close()
            
            if not receta:
                st.info("El residente no tiene medicamentos recetados.")
            else:
                for idx, item in enumerate(receta):
                    m_nombre, tot_dosis, stock = item[0], item[1], item[2]
                    cant_sugerida = min(tot_dosis, stock) if stock > 0 else 0
                    
                    st.write(f"💊 **{m_nombre}** | Dosis Diaria: `{tot_dosis}` | Stock Almacén: `{stock}`")
                    if stock <= 0:
                        st.error("⚠️ Sin existencias disponibles en almacén.")
                    else:
                        cant_entregar = st.number_input(f"Cantidad a entregar de {m_nombre}", min_value=0, max_value=max(1, stock), value=cant_sugerida, key=f"ent_{p_id}_{idx}")
                        if st.button(f"📦 Confirmar Entrega de {m_nombre}", key=f"btn_ent_{p_id}_{idx}"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE inventario_medicamentos SET existencia = existencia - ? WHERE medicamento = ?", (cant_entregar, m_nombre))
                            c.execute("INSERT INTO entregas_medicamentos (paciente_id, fecha, medicamento, cantidad, usuario_registro) VALUES (?, ?, ?, ?, ?)",
                                      (p_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m_nombre, cant_entregar, st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast("¡Entrega registrada y stock actualizado!", icon="🎉")
                            st.success(f"✅ Se entregaron {cant_entregar} unidades de {m_nombre}.")

    with tab4:
        st.subheader("📊 Reporte de Consumo Global")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT m.nombre, COALESCE(i.existencia, 0), SUM(d.manana + d.tarde + d.noche) FROM catalogo_medicamentos m LEFT JOIN inventario_medicamentos i ON m.nombre = i.medicamento LEFT JOIN dosis_medicamentos d ON m.nombre = d.medicamento GROUP BY m.nombre")
        rep = c.fetchall()
        conn.close()
        
        if rep:
            for r in rep:
                st.markdown(f"💊 **{r[0]}** ➔ Stock Almacén: `{r[1]}` unidades | Consumo Diario Comunidad: `{r[2] if r[2] else 0}` unidades")

# ==============================================================================
# 8. 📁 REPOSITORIO DE DOCUMENTOS Y CARPETAS
# ==============================================================================
elif menu == "📁 Repositorio de Documentos":
    st.title("📁 Repositorio de Documentos y Manuales")
    st.write("Biblioteca institucional de formatos, reglamentos y manuales de la comunidad.")
    
    if not es_admin():
        st.error("⛔ Acceso restringido. Solo los usuarios con rol de Administrador pueden acceder al Repositorio de Documentos.")
    else:
        tab1, tab2, tab3 = st.tabs(["📤 Subir Documento", "📥 Consultar y Descargar", "📁 Personalizar / Gestionar Carpetas"])
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY nombre_carpeta")
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()
        
        with tab1:
            st.subheader("Subir Archivo a la Nube")
            with st.form("form_subir_doc"):
                carpeta_sel = st.selectbox("Carpeta Destino", carpetas_list)
                desc_doc = st.text_input("Descripción o Notas del Documento")
                file_up = st.file_uploader("Selecciona un archivo (PDF, Word, Excel, Img)", type=["pdf", "docx", "xlsx", "png", "jpg", "txt"])
                
                btn_up = st.form_submit_button("📤 Subir Archivo al Repositorio", use_container_width=True)
                if btn_up:
                    if not file_up:
                        st.error("Por favor selecciona un archivo.")
                    else:
                        blob_bytes = file_up.read()
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO repositorio_documentos 
                            (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (carpeta_sel, file_up.name, file_up.type, blob_bytes, desc_doc, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Archivo subido al repositorio!", icon="🎉")
                        st.success(f"✅ Documento {file_up.name} guardado en la carpeta '{carpeta_sel}'.")

        with tab2:
            st.subheader("Documentos Disponibles")
            filtro_c = st.selectbox("Filtrar por Carpeta", ["TODAS"] + carpetas_list)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if filtro_c == "TODAS":
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos ORDER BY id DESC")
            else:
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC", (filtro_c,))
            docs = c.fetchall()
            conn.close()
            
            if not docs:
                st.info("No hay documentos guardados en esta carpeta.")
            else:
                for d in docs:
                    d_id, d_carp, d_nom, d_mime, d_blob, d_desc, d_f = d[0], d[1], d[2], d[3], d[4], d[5], d[6]
                    with st.expander(f"📄 {d_nom} ({d_carp}) - {d_f}"):
                        st.write(f"**Notas**: {d_desc}")
                        st.download_button(
                            f"📥 Descargar {d_nom}",
                            data=d_blob,
                            file_name=d_nom,
                            mime=d_mime,
                            key=f"dl_{d_id}"
                        )

        with tab3:
            st.subheader("Gestionar Carpetas")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### ➕ Crear Nueva Carpeta")
                nueva_c = st.text_input("Nombre de la Nueva Carpeta")
                if st.button("➕ Crear Carpeta"):
                    if nueva_c:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (nueva_c,))
                            conn.commit()
                            st.balloons()
                            st.toast("¡Carpeta creada!", icon="🎉")
                            st.success(f"✅ Carpeta '{nueva_c}' creada.")
                            st.rerun()
                        except:
                            st.error("La carpeta ya existe.")
                        conn.close()
                        
            with c2:
                st.markdown("#### ✏️ Renombrar Carpeta Existente")
                ren_c = st.selectbox("Selecciona Carpeta a Renombrar", carpetas_list)
                nuevo_nom = st.text_input("Nuevo Nombre de Carpeta")
                if st.button("✏️ Renombrar Carpeta"):
                    if nuevo_nom:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (nuevo_nom, ren_c))
                        c.execute("UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?", (nuevo_nom, ren_c))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Carpeta renombrada!", icon="🎉")
                        st.success("✅ Nombre actualizado.")
                        st.rerun()

# ==============================================================================
# 9. 🔍 BUSCAR Y LISTAR PACIENTES (EXPEDIENTE GENERAL)
# ==============================================================================
elif menu == "🔍 Buscar y Listar Pacientes":
    st.title("🔍 Buscar y Consultar Expedientes Generales")
    st.write("Vista centralizada del expediente clínico e historial de cada residente.")
    
    pacientes = obtener_pacientes_lista()
    if not pacientes:
        st.info("No hay residentes registrados en el sistema.")
    else:
        busqueda = st.text_input("🔍 Buscar por Nombre o Folio", "")
        filtrados = [p for p in pacientes if busqueda.lower() in p[0].lower() or busqueda.lower() in p[1].lower()]
        
        st.subheader(f"Total de Residentes Encontrados: {len(filtrados)}")
        for pac in filtrados:
            p_id = pac[0]
            with st.expander(f"👤 {pac[1]} (Folio: {p_id}) | Etapa: {pac[4]}"):
                st.markdown(f"**Tipo de Usuario**: {pac[2]} | **Fecha de Ingreso Real**: {pac[3]}")
                st.markdown(f"**Fecha de Nacimiento**: {pac[6]} | **Sexo**: {pac[7]}")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (p_id,))
                r_e = c.fetchone()
                c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
                r_f = c.fetchone()
                conn.close()
                
                if r_f:
                    df = json.loads(r_f[0])
                    st.markdown(f"📋 **Ficha Ingreso**: Responsable: {df.get('responsable_nombre')} ({df.get('responsable_tel')}) | Sustancia Impacto: {df.get('sustancia_impacto')}")
                if r_e:
                    de = json.loads(r_e[0])
                    st.markdown(f"📝 **Entrevista Inicial**: Motivo Ingreso: {de.get('motivo_ingreso')} | Disposición: {de.get('estado_disposicion')}")

# ==============================================================================
# 10. ⚙️ CONFIGURACIÓN & SEGURIDAD
# ==============================================================================
elif menu == "⚙️ Configuración & Seguridad":
    st.title("⚙️ Configuración de Seguridad y Roles")
    st.write("Administración de usuarios de personal, asignación de permisos y cambio de contraseñas.")
    
    tab1, tab2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Administración de Personal y Roles"])
    
    with tab1:
        st.subheader("Cambiar Contraseña Personal")
        with st.form("form_cambio_pass"):
            actual_p = st.text_input("Contraseña Actual", type="password")
            nueva_p = st.text_input("Nueva Contraseña", type="password")
            conf_p = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            btn_cp = st.form_submit_button("Actualizar mi Contraseña")
            if btn_cp:
                if nueva_p != conf_p:
                    st.error("Las contraseñas no coinciden.")
                elif not verificar_login(st.session_state["username"], actual_p):
                    st.error("La contraseña actual es incorrecta.")
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hash_pass(nueva_p), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast("¡Contraseña actualizada!", icon="🎉")
                    st.success("✅ Contraseña modificada correctamente.")

    with tab2:
        if not es_admin():
            st.error("⛔ Solo los usuarios con rol de Administrador pueden administrar las cuentas de personal.")
        else:
            st.subheader("Crear / Editar Cuentas de Personal")
            with st.form("form_nuevo_usr"):
                c1, c2 = st.columns(2)
                u_user = c1.text_input("Nombre de Usuario (Login)")
                u_nom = c2.text_input("Nombre Completo")
                u_pass = c1.text_input("Contraseña Inicial", type="password")
                u_rol = c2.selectbox("Rol y Permisos", [
                    "Nivel 1 - Administrador",
                    "Nivel 2 - Lectura y Escritura",
                    "Nivel 3 - Solo Lectura"
                ])
                
                btn_nu = st.form_submit_button("➕ Crear Usuario de Personal", use_container_width=True)
                if btn_nu:
                    if u_user and u_pass:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                                      (u_user, hash_pass(u_pass), u_nom, u_rol))
                            conn.commit()
                            st.balloons()
                            st.toast("¡Usuario de personal creado!", icon="🎉")
                            st.success(f"✅ Cuenta '{u_user}' creada con rol {u_rol}.")
                        except:
                            st.error("El usuario ya existe.")
                        conn.close()

# ==============================================================================
# 11. 📦 RESPALDO Y RESTAURACIÓN DE BASE DE DATOS (.DB)
# ==============================================================================
elif menu == "📦 Respaldo y Restauración":
    st.title("📦 Respaldo y Restauración de Base de Datos")
    st.write("Protección total de expedientes, consejerías y documentos subidos al repositorio.")
    
    if not es_admin():
        st.error("⛔ Acceso restringido. Solo Administradores pueden gestionar respaldos.")
    else:
        st.subheader("📥 Descargar Respaldo Completo")
        st.info("Descarga una copia exacta de tu base de datos (`sistema_pacientes.db`). Este archivo incluye a todos los residentes, entrevistas, consejerías y todos los documentos reales subidos al repositorio.")
        
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                db_bytes = f.read()
                
            st.download_button(
                "📥 Descargar Archivo de Respaldo (.db)",
                data=db_bytes,
                file_name=f"respaldo_sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
            
        st.write("---")
        st.subheader("📤 Restaurar Base de Datos desde Respaldo")
        up_db = st.file_uploader("Selecciona un archivo de respaldo (.db)", type=["db", "sqlite", "sqlite3"])
        
        if up_db:
            if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                with open(DB_FILE, "wb") as f:
                    f.write(up_db.read())
                st.balloons()
                st.toast("¡Base de datos restaurada con éxito!", icon="🎉")
                st.success("✅ Se restauraron todos los expedientes, consejerías y documentos. La página se reiniciará en 2 segundos.")
                st.rerun()

import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Comunidad Terapéutica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema (Login & Roles)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    """)
    
    # Migración de columna rol si no existe
    c.execute("PRAGMA table_info(usuarios)")
    cols = [col[1] for col in c.fetchall()]
    if 'rol' not in cols:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
    
    # 2. Tabla de Pacientes / Residentes
    c.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            tipo_usuario TEXT DEFAULT 'Paciente',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            hermano_mayor_id TEXT,
            fecha_suelta_hermano TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    """)
    
    # Migración de fecha_inicio_etapa si no existe
    c.execute("PRAGMA table_info(pacientes)")
    cols_p = [col[1] for col in c.fetchall()]
    if 'fecha_inicio_etapa' not in cols_p:
        c.execute("ALTER TABLE pacientes ADD COLUMN fecha_inicio_etapa TEXT")
    
    # 3. Tabla de Entrevistas de Consejería
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 4. Tabla de Fichas de Ingreso y Admisión
    c.execute("""
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    # 5. Tabla de Catálogo Central de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            indicaciones TEXT
        )
    """)
    
    # 6. Tabla de Medicamentos e Inventario por Paciente
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamentos (
            paciente_id TEXT PRIMARY KEY,
            meds_json TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    """)
    
    # 7. Tabla de Historial de Entregas de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    """)
    
    # 8. Tabla de Grupos Terapéuticos
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeutos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            etapa_al_momento TEXT,
            fecha_grupo TEXT,
            facilitador TEXT,
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    """)
    
    # 9. Tabla de Historial de Cambios de Etapa
    c.execute("""
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_origen TEXT,
            etapa_destino TEXT,
            fecha_cambio TEXT,
            usuario_autoriza TEXT
        )
    """)
    
    # 10. Tabla de Requisitos por Etapa
    c.execute("""
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    """)
    
    # 11. Tabla de Repositorio de Documentos (Almacenamiento en Nube/DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            mime_type TEXT,
            bytes_blob BLOB,
            descripcion TEXT,
            fecha_subida TEXT,
            usuario_subida TEXT
        )
    """)
    
    # Crear usuario administrador por defecto
    c.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")
        
    # Poblado inicial de catálogo de medicamentos si está vacío
    c.execute("SELECT COUNT(*) FROM catalogo_medicamentos")
    if c.fetchone()[0] == 0:
        meds_base = [
            ("Omeprazol", "Cápsulas", "20 mg", "Protector gástrico"),
            ("Paracetamol", "Comprimidos", "500 mg", "Analgésico / Antipirético"),
            ("Ibuprofeno", "Comprimidos", "400 mg", "Antiinflamatorio"),
            ("Sertralina", "Comprimidos", "50 mg", "Antidepresivo"),
            ("Clonazepam", "Gotas / Comprimidos", "2.5 mg/ml", "Ansiolítico (Controlado)"),
            ("Olanzapina", "Comprimidos", "10 mg", "Antipsicótico"),
            ("Complex B", "Grageas", "Estándar", "Suplemento vitamínico")
        ]
        c.executemany("INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, indicaciones) VALUES (?, ?, ?, ?)", meds_base)
                  
    # Poblado de requisitos de etapas si está vacía
    c.execute("SELECT COUNT(*) FROM requisitos_etapas")
    if c.fetchone()[0] == 0:
        reqs = [
            ('ACOGIDA', 'Compromiso Existencial', 0),
            ('ACOGIDA', '2 Señalamientos correctos', 0),
            ('ACOGIDA', '5 Reglas de Usuario', 0),
            ('ACOGIDA', '5 Reglas de Convivencia', 0),
            
            ('IDENTIFICACIÓN', 'Autobiografía', 0),
            ('IDENTIFICACIÓN', 'Oración de la mañana', 0),
            ('IDENTIFICACIÓN', 'Filosofía de la Comunidad', 0),
            ('IDENTIFICACIÓN', '10 Reglas de Usuario', 0),
            ('IDENTIFICACIÓN', '10 Reglas de Convivencia', 0),
            ('IDENTIFICACIÓN', '4 Grupos "Aquí y Ahora"', 1),
            ('IDENTIFICACIÓN', '4 Grupos "Terapia de Grupo"', 1),
            ('IDENTIFICACIÓN', '4 Grupos "Feedbacks"', 1),
            
            ('ELABORACIÓN', 'Filosofía del Ayer, Hoy y Mañana', 0),
            ('ELABORACIÓN', 'Oración del Medio día', 0),
            ('ELABORACIÓN', '15 Reglas de Usuario', 0),
            ('ELABORACIÓN', '15 Reglas de Convivencia', 0),
            ('ELABORACIÓN', 'Proyecto de vida', 0),
            ('ELABORACIÓN', '4 Grupos "Aquí y Ahora"', 1),
            ('ELABORACIÓN', '4 Grupos "Terapia de Grupo"', 1),
            ('ELABORACIÓN', '4 Grupos "Feedbacks"', 1),
            
            ('CONSOLIDACIÓN', '30 Reglas de Usuario', 0),
            ('CONSOLIDACIÓN', '20 Reglas de Convivencia', 0),
            ('CONSOLIDACIÓN', 'Oración del Medio día', 0),
            ('CONSOLIDACIÓN', 'Plan de Servicio Social', 0),
            ('CONSOLIDACIÓN', '2 Grupos "Aquí y Ahora"', 1),
            ('CONSOLIDACIÓN', '2 Grupos "Terapia de Grupo"', 1),
            ('CONSOLIDACIÓN', '2 Grupos "Feedbacks"', 1),
            
            ('SERVICIO SOCIAL', '30 Días de Servicio', 0),
            ('SERVICIO SOCIAL', '2 Grupos "Aquí y Ahora"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Terapia de Grupo"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Feedbacks"', 1)
        ]
        c.executemany("INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)", reqs)
    
    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES DE AUTENTICACIÓN Y ROLES ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?",
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

def obtener_rol_usuario(username):
    if username == "admin":
        return "Nivel 1 - Administrador"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT rol FROM usuarios WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else "Nivel 2 - Lectura y Escritura"

def es_admin():
    if "username" in st.session_state and st.session_state["username"] == "admin":
        return True
    rol = st.session_state.get("rol", "")
    return "Nivel 1" in rol or "Administrador" in rol

def puede_escribir():
    if es_admin():
        return True
    rol = st.session_state.get("rol", "")
    return "Nivel 2" in rol or "Escritura" in rol

# --- FUNCIONES DE PACIENTES ---
def generar_siguiente_paciente_id():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id FROM pacientes WHERE paciente_id LIKE 'PAC-%'")
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        try:
            num = int(r[0].replace("PAC-", ""))
            if num > max_num:
                max_num = num
        except:
            pass
    return f"PAC-{max_num + 1:03d}"

def guardar_usuario_paciente(p_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo, f_inicio_etapa, etapa_actual, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT paciente_id FROM pacientes WHERE paciente_id = ?", (p_id,))
    if c.fetchone():
        c.execute("""
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, 
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        """, (nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa_actual, f_inicio_etapa, f_act, p_id))
    else:
        c.execute("""
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa_actual, f_inicio_etapa, f_act, f_act, usuario))
    conn.commit()
    conn.close()

def listar_pacientes_todos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, estatus, etapa_actual, fecha_inicio_etapa FROM pacientes ORDER BY paciente_id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente(p_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?", (p_id,))
    row = c.fetchone()
    conn.close()
    return row

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
CARPETAS_DEFECTO = [
    "📋 Formatos Clínicos y Administrativos",
    "📖 Manuales de Operación",
    "⚖️ Reglamentos y Normativas",
    "📑 Plantillas de Evaluación",
    "📁 Documentos Generales"
]

def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_data, descripcion, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (carpeta, nombre_archivo, mime_type, bytes_data, descripcion, f_act, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro="Todas"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro == "Todas":
        c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY id DESC")
    else:
        c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC", (carpeta_filtro,))
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM repositorio_documentos WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE FICHA DE INGRESO ---
def guardar_ficha_ingreso(p_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute("SELECT paciente_id FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
    if c.fetchone():
        c.execute("UPDATE fichas_ingreso SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?", (f_act, datos_json, p_id))
    else:
        c.execute("INSERT INTO fichas_ingreso (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)",
                  (p_id, f_act, f_act, usuario, datos_json))
    conn.commit()
    conn.close()

def obtener_ficha_ingreso(p_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def eliminar_ficha_ingreso(p_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM fichas_ingreso WHERE paciente_id = ?", (p_id,))
    conn.commit()
    conn.close()

# --- INTERFAZ DE LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #4CAF50;'>Sistema Integral de Control Terapéutico y Expedientes</h3>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Iniciar Sesión en el Sistema")
        with st.form("form_login"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if btn_login:
                usr = verificar_login(user_input, pass_input)
                if usr:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usr[0]
                    st.session_state["nombre_completo"] = usr[1]
                    st.session_state["rol"] = usr[2] if len(usr) > 2 else "Nivel 1 - Administrador"
                    st.toast(f"🎉 ¡Bienvenido de nuevo, {usr[1]}!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
    st.stop()

# --- MENÚ PRINCIPAL LATERAL ---
st.sidebar.title("🌱 Sawabona Shikoba")
st.sidebar.write("👤 **" + str(st.session_state['nombre_completo']) + "**")
st.sidebar.caption("🔑 " + str(st.session_state.get('rol', 'Administrador')))

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.write("---")

opciones_menu = [
    "🏠 Inicio / Dashboard",
    "📄 Ficha de Ingreso y Admisión",
    "👤 Registro de Usuarios",
    "📝 Entrevista Inicial Consejería",
    "🎯 Gestión de Etapas & Rezagos",
    "🗣️ Grupos Terapéuticos",
    "💊 Control de Medicamentos",
    "📁 Repositorio de Documentos",
    "🔍 Buscar y Listar Pacientes",
    "⚙️ Configuración & Seguridad",
    "📦 Respaldo y Restauración"
]

menu = st.sidebar.radio("Navegación del Sistema", opciones_menu)

# --- 🏠 MÓDULO: DASHBOARD / INICIO ---
if menu == "🏠 Inicio / Dashboard":
    st.title("🏠 Panel Principal de Control Terapéutico")
    st.write("Bienvenido al sistema central de administración y seguimiento de **Sawabona Shikoba A.C.**")
    
    pacientes = listar_pacientes_todos()
    tot_pacientes = len(pacientes)
    activos = len([p for p in pacientes if p[3] == 'A'])
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Residentes", tot_pacientes)
    c2.metric("Residentes Activos", activos)
    c3.metric("Residentes Inactivos", tot_pacientes - activos)
    c4.metric("Estado del Sistema", "Online 🟢")
    st.write("---")
    
    st.subheader("📌 Residentes Activos y Días de Estancia")
    if pacientes:
        data_table = []
        hoy = date.today()
        for p in pacientes:
            if p[3] == 'A':
                f_ing = p[2]
                dias_tot = 0
                if f_ing:
                    try:
                        d_obj = datetime.strptime(f_ing, "%Y-%m-%d").date()
                        dias_tot = (hoy - d_obj).days
                    except:
                        pass
                
                f_etapa = p[5] if len(p) > 5 and p[5] else f_ing
                dias_etapa = 0
                if f_etapa:
                    try:
                        e_obj = datetime.strptime(f_etapa, "%Y-%m-%d").date()
                        dias_etapa = (hoy - e_obj).days
                    except:
                        pass
                        
                data_table.append({
                    "Folio": p[0],
                    "Nombre Completo": p[1],
                    "Etapa Activa": p[4],
                    "Fecha Ingreso": p[2],
                    "Días Totales en Comunidad": f"{dias_tot} días",
                    "Días en Etapa Actual": f"{dias_etapa} días"
                })
        st.dataframe(data_table, use_container_width=True)

# --- 📄 MÓDULO: FICHA DE INGRESO Y ADMISIÓN ---
elif menu == "📄 Ficha de Ingreso y Admisión":
    st.title("📄 Ficha de Ingreso y Contrato de Admisión")
    
    tab1, tab2, tab3 = st.tabs(["🆕 Registrar / Editar Ficha", "🔍 Consultar e Imprimir PDF", "🗑️ Eliminar Ficha"])
    
    with tab1:
        st.subheader("Captura de Ficha de Admisión (NOM-028-SSA2-2009)")
        pacientes = listar_pacientes_todos()
        opc_pacientes = {"🆕 Crear Nuevo Registro de Ingreso": "NUEVO"}
        for p in pacientes:
            opc_pacientes[f"{p[1]} ({p[0]})"] = p[0]
            
        sel_pac = st.selectbox("Selecciona Paciente o Nuevo", list(opc_pacientes.keys()), key="ficha_sel")
        p_id_target = opc_pacientes[sel_pac]
        
        datos_ex, f_reg, f_mod, u_reg = (None, None, None, None)
        if p_id_target != "NUEVO":
            datos_ex, f_reg, f_mod, u_reg = obtener_ficha_ingreso(p_id_target)
            
        default_id = p_id_target if p_id_target != "NUEVO" else generar_siguiente_paciente_id()
        d_val = datos_ex if datos_ex else {}
        
        with st.form("form_ficha_ingreso"):
            st.markdown("### 1. Datos del Responsable Familiar")
            c1, c2 = st.columns(2)
            resp_nombre = c1.text_input("Nombre Completo del Responsable", value=d_val.get("resp_nombre", ""))
            resp_parentesco = c2.text_input("Parentesco", value=d_val.get("resp_parentesco", "Padre / Madre / Cónyuge"))
            resp_telefono = c1.text_input("Teléfono de Contacto", value=d_val.get("resp_telefono", ""))
            
            st.markdown("### 2. Datos Generales del Paciente")
            c3, c4 = st.columns(2)
            pac_folio = c3.text_input("Folio de Paciente", value=default_id, disabled=True)
            pac_nombre = c4.text_input("Nombre Completo del Paciente *", value=d_val.get("pac_nombre", ""))
            pac_edad = c3.number_input("Edad", min_value=12, max_value=99, value=int(d_val.get("pac_edad", 25)))
            pac_fnac = c4.date_input("Fecha de Nacimiento", value=datetime.strptime(d_val.get("pac_fnac", "2000-01-01"), "%Y-%m-%d") if d_val.get("pac_fnac") else date(2000, 1, 1))
            pac_ecivil = c3.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
            pac_escolaridad = c4.text_input("Escolaridad", value=d_val.get("pac_escolaridad", "Secundaria / Preparatoria"))
            pac_ocupacion = c3.text_input("Ocupación", value=d_val.get("pac_ocupacion", "Empleado / Comercio"))
            pac_domicilio = st.text_area("Domicilio Completo (Calle, Número, Colonia, C.P., Municipio, Estado)", value=d_val.get("pac_domicilio", ""))
            
            st.markdown("### 3. Sustancias de Consumo")
            sustancias_opc = ["Alcohol", "Cannabis (Marihuana)", "Metanfetaminas (Cristal)", "Cocaína", "Tabaco", "Benzodiazepinas", "Inhalantes", "Opioides"]
            sust_sel = st.multiselect("Sustancias de consumo habitual", sustancias_opc, default=d_val.get("sust_sel", ["Alcohol", "Metanfetaminas (Cristal)"]))
            sust_impacto = st.selectbox("Sustancia de Impacto Principal", sustancias_opc, index=2)
            
            st.markdown("### 4. Términos Financieros y Modalidad")
            c5, c6 = st.columns(2)
            costo_ingreso = c5.number_input("Costo de Ingreso ($)", value=float(d_val.get("costo_ingreso", 4500.0)))
            costo_mensual = c6.number_input("Mensualidad ($)", value=float(d_val.get("costo_mensual", 6000.0)))
            pagare_imp = c5.number_input("Importe Pagaré ($)", value=float(d_val.get("pagare_imp", 42000.0)))
            modalidad = c6.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario (por familiar/responsable)"], index=0)
            
            btn_guardar_ficha = st.form_submit_button("💾 Guardar Ficha de Ingreso y Admisión", use_container_width=True)
            
            if btn_guardar_ficha:
                if not pac_nombre:
                    st.error("⚠️ El nombre del paciente es obligatorio.")
                else:
                    d_save = {
                        "resp_nombre": resp_nombre,
                        "resp_parentesco": resp_parentesco,
                        "resp_telefono": resp_telefono,
                        "pac_nombre": pac_nombre,
                        "pac_edad": pac_edad,
                        "pac_fnac": pac_fnac.strftime("%Y-%m-%d"),
                        "pac_ecivil": pac_ecivil,
                        "pac_escolaridad": pac_escolaridad,
                        "pac_ocupacion": pac_ocupacion,
                        "pac_domicilio": pac_domicilio,
                        "sust_sel": sust_sel,
                        "sust_impacto": sust_impacto,
                        "costo_ingreso": costo_ingreso,
                        "costo_mensual": costo_mensual,
                        "pagare_imp": pagare_imp,
                        "modalidad": modalidad
                    }
                    f_hoy = date.today().strftime("%Y-%m-%d")
                    guardar_usuario_paciente(default_id, pac_nombre, f_hoy, pac_fnac.strftime("%Y-%m-%d"), "MASCULINO", 'A', "Paciente", f_hoy, "ACOGIDA", st.session_state["username"])
                    guardar_ficha_ingreso(default_id, d_save, st.session_state["username"])
                    st.success(f"✅ ¡Ficha de Ingreso guardada exitosamente para **{pac_nombre}** ({default_id})!")
                    st.balloons()
                    st.toast("🎉 Ficha guardada e integrada al expediente del usuario.")

    with tab2:
        st.subheader("Consultar e Imprimir Ficha de Ingreso en PDF")
        pacientes = listar_pacientes_todos()
        if pacientes:
            sel_print = st.selectbox("Selecciona Paciente a Imprimir", [f"{p[1]} ({p[0]})" for p in pacientes], key="ficha_print_sel")
            p_id_p = sel_print.split("(")[-1].replace(")", "").strip()
            
            datos_p, f_r, f_m, u_r = obtener_ficha_ingreso(p_id_p)
            if datos_p:
                st.info(f"📋 **Paciente**: {datos_p.get('pac_nombre')} | **Folio**: {p_id_p} | **Responsable**: {datos_p.get('resp_nombre')}")
                
                class PDF_Ficha(FPDF):
                    def header(self):
                        self.set_font('Arial', 'B', 14)
                        self.cell(0, 8, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
                        self.set_font('Arial', 'I', 10)
                        self.cell(0, 5, 'FICHA DE INGRESO Y CONTRATO DE ADMISIÓN', 0, 1, 'C')
                        self.ln(5)
                    def footer(self):
                        self.set_y(-15)
                        self.set_font('Arial', 'I', 8)
                        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

                pdf = PDF_Ficha()
                pdf.add_page()
                pdf.set_font("Arial", "", 10)
                
                pdf.set_font("Arial", "B", 11)
                pdf.cell(0, 7, "1. DATOS DEL RESPONSABLE FAMILIAR", 1, 1, 'L')
                pdf.set_font("Arial", "", 10)
                pdf.cell(0, 6, f"Nombre: {datos_p.get('resp_nombre')} | Parentesco: {datos_p.get('resp_parentesco')}", 0, 1)
                pdf.cell(0, 6, f"Teléfono: {datos_p.get('resp_telefono')}", 0, 1)
                pdf.ln(3)
                
                pdf.set_font("Arial", "B", 11)
                pdf.cell(0, 7, "2. DATOS DEL PACIENTE / RESIDENTE", 1, 1, 'L')
                pdf.set_font("Arial", "", 10)
                pdf.cell(0, 6, f"Nombre: {datos_p.get('pac_nombre')} | Folio: {p_id_p}", 0, 1)
                pdf.cell(0, 6, f"Edad: {datos_p.get('pac_edad')} años | F. Nacimiento: {datos_p.get('pac_fnac')}", 0, 1)
                pdf.cell(0, 6, f"Estado Civil: {datos_p.get('pac_ecivil')} | Escolaridad: {datos_p.get('pac_escolaridad')}", 0, 1)
                pdf.multi_cell(0, 6, f"Domicilio: {datos_p.get('pac_domicilio')}")
                pdf.ln(3)
                
                pdf.set_font("Arial", "B", 11)
                pdf.cell(0, 7, "3. DIAGNÓSTICO DE CONSUMO Y TÉRMINOS", 1, 1, 'L')
                pdf.set_font("Arial", "", 10)
                pdf.cell(0, 6, f"Sustancia de Impacto: {datos_p.get('sust_impacto')}", 0, 1)
                pdf.cell(0, 6, f"Sustancias Consumidas: {', '.join(datos_p.get('sust_sel', []))}", 0, 1)
                pdf.cell(0, 6, f"Modalidad: {datos_p.get('modalidad')} | Costo Ingreso: ${datos_p.get('costo_ingreso'):,.2f} | Mensualidad: ${datos_p.get('costo_mensual'):,.2f}", 0, 1)
                pdf.ln(10)
                
                pdf.multi_cell(0, 5, "DECLARACIÓN DE CONFORMIDAD Y AUTORIZACIÓN (NOM-028-SSA2-2009): Por medio de la presente, el responsable familiar y el usuario declaran que ingresan de manera voluntaria/autorizada a la Comunidad Terapéutica Sawabona Shikoba A.C., aceptando el reglamento interno y los términos terapéuticos establecidos.")
                pdf.ln(20)
                
                pdf.cell(90, 6, "__________________________________", 0, 0, 'C')
                pdf.cell(90, 6, "__________________________________", 0, 1, 'C')
                pdf.cell(90, 5, "Firma del Responsable Familiar", 0, 0, 'C')
                pdf.cell(90, 5, "Firma del Director / Encargado", 0, 1, 'C')
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1', errors='replace')
                st.download_button(f"🖨️ Descargar Ficha de Ingreso en PDF ({p_id_p})", data=pdf_bytes, file_name=f"Ficha_Ingreso_{p_id_p}.pdf", mime="application/pdf")
            else:
                st.warning("No se encontró Ficha de Ingreso para este residente.")

    with tab3:
        st.subheader("Eliminar Ficha de Ingreso")
        if es_admin():
            pacientes = listar_pacientes_todos()
            if pacientes:
                sel_del = st.selectbox("Selecciona Ficha a Eliminar", [f"{p[1]} ({p[0]})" for p in pacientes], key="ficha_del_sel")
                p_id_d = sel_del.split("(")[-1].replace(")", "").strip()
                
                if st.button("⚠️ Confirmar Eliminación Permanente de Ficha", type="primary"):
                    eliminar_ficha_ingreso(p_id_d)
                    st.success(f"✅ Ficha de Ingreso eliminada para {p_id_d}.")
                    st.toast("Ficha eliminada de la base de datos.")
                    st.rerun()
        else:
            st.error("🔒 Solo los usuarios con rol de Administrador pueden eliminar fichas.")

# --- 👤 MÓDULO: REGISTRO DE USUARIOS ---
elif menu == "👤 Registro de Usuarios":
    st.title("👤 Registro y Edición de Usuarios / Residentes")
    
    pacientes = listar_pacientes_todos()
    modo_usuario = st.radio("Acción a realizar", ["🆕 Registrar Nuevo Usuario", "✏️ Editar Usuario Existente"], horizontal=True)
    
    p_edit = None
    edit_id = ""
    if modo_usuario == "✏️ Editar Usuario Existente":
        if pacientes:
            opc_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes}
            sel_p = st.selectbox("🔑 Selecciona el Usuario a Editar", list(opc_p.keys()))
            edit_id = opc_p[sel_p]
            p_edit = obtener_paciente(edit_id)
        else:
            st.warning("No hay usuarios registrados para editar.")
            
    with st.form(f"form_usuario_{edit_id if edit_id else 'nuevo'}"):
        st.subheader("Datos del Usuario / Residente")
        c1, c2 = st.columns(2)
        
        reg_id = c1.text_input("Folio ID Paciente", value=p_edit[0] if p_edit else generar_siguiente_paciente_id(), disabled=True)
        reg_nombre = c2.text_input("Nombre Completo *", value=p_edit[1] if p_edit else "")
        
        f_ing_val = datetime.strptime(p_edit[2], "%Y-%m-%d").date() if (p_edit and p_edit[2]) else date.today()
        reg_fingreso = c1.date_input("Fecha de Ingreso Real a la Comunidad", value=f_ing_val)
        
        f_nac_val = datetime.strptime(p_edit[3], "%Y-%m-%d").date() if (p_edit and p_edit[3]) else date(2000, 1, 1)
        reg_fnac = c2.date_input("Fecha de Nacimiento", value=f_nac_val)
        
        sex_idx = 0 if (p_edit and p_edit[4] == "MASCULINO") else (1 if (p_edit and p_edit[4] == "FEMENINO") else 0)
        reg_sexo = c1.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=sex_idx)
        
        est_idx = 0 if (p_edit and p_edit[5] == "A") else 1
        reg_estatus = c2.selectbox("Estatus de Usuario", ["Activo ('A')", "Inactivo / Egreso ('I')"], index=est_idx)
        est_code = "A" if "Activo" in reg_estatus else "I"
        
        etapas_lista = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
        etapa_actual_val = p_edit[7] if (p_edit and p_edit[7]) else "ACOGIDA"
        etapa_idx = etapas_lista.index(etapa_actual_val) if etapa_actual_val in etapas_lista else 0
        reg_etapa = c1.selectbox("Etapa Actual en el Proceso", etapas_lista, index=etapa_idx)
        
        f_etapa_val = datetime.strptime(p_edit[8], "%Y-%m-%d").date() if (p_edit and len(p_edit) > 8 and p_edit[8]) else f_ing_val
        reg_fetapa = c2.date_input("Fecha de Inicio de Etapa Actual", value=f_etapa_val)
        
        btn_guardar_u = st.form_submit_button("💾 Guardar Datos del Usuario", use_container_width=True)
        
        if btn_guardar_u:
            if not reg_nombre:
                st.error("⚠️ El nombre completo es obligatorio.")
            else:
                guardar_usuario_paciente(
                    reg_id, reg_nombre, 
                    reg_fingreso.strftime("%Y-%m-%d"), 
                    reg_fnac.strftime("%Y-%m-%d"), 
                    reg_sexo, est_code, "Paciente", 
                    reg_fetapa.strftime("%Y-%m-%d"), 
                    reg_etapa, 
                    st.session_state["username"]
                )
                st.success(f"✅ ¡Usuario **{reg_nombre}** ({reg_id}) guardado exitosamente!")
                st.balloons()
                st.toast("🎉 Datos de usuario actualizados correctamente.")
                st.rerun()

# --- 🎯 MÓDULO: GESTIÓN DE ETAPAS & REZAGOS ---
elif menu == "🎯 Gestión de Etapas & Rezagos":
    st.title("🎯 Gestión de Etapas, Rezagos y Hermano Mayor")
    
    tab1, tab2 = st.tabs(["📊 Evaluador de Etapa y Rezagos", "🤝 Asignación de Hermano Mayor"])
    
    with tab1:
        st.subheader("Evaluador Clínico de Etapa y Control de Rezagos")
        pacientes = listar_pacientes_todos()
        if pacientes:
            opc_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes if p[3] == 'A'}
            if opc_p:
                sel_p = st.selectbox("Selecciona Residente para Evaluar", list(opc_p.keys()))
                p_id_e = opc_p[sel_p]
                p_info = obtener_paciente(p_id_e)
                
                hoy = date.today()
                f_ing = p_info[2]
                f_etapa = p_info[8] if p_info[8] else f_ing
                
                dias_tot = (hoy - datetime.strptime(f_ing, "%Y-%m-%d").date()).days if f_ing else 0
                dias_etapa = (hoy - datetime.strptime(f_etapa, "%Y-%m-%d").date()).days if f_etapa else 0
                
                duracion_estandar = {"ACOGIDA": 30, "IDENTIFICACIÓN": 60, "ELABORACIÓN": 60, "CONSOLIDACIÓN": 60, "SERVICIO SOCIAL": 30}
                dur_est = duracion_estandar.get(p_info[7], 30)
                
                st.markdown(f"### Residente: **{p_info[1]}** ({p_id_e})")
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Etapa Activa", p_info[7])
                col_m2.metric("Días Totales en Comunidad", f"{dias_tot} días")
                col_m3.metric("Días en Etapa Actual", f"{dias_etapa} / {dur_est} días")
                
                if dias_etapa > dur_est:
                    exceso = dias_etapa - dur_est
                    st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El paciente lleva **{dias_tot} días internado** y suma **{dias_etapa} días en la Etapa {p_info[7]}** (Duración estimada: {dur_est} días). Se ha excedido por **+{exceso} días** sin haber completado su promoción.")
                else:
                    st.success(f"🟢 **PROCESO DENTRO DE TIEMPO**: Al paciente le restan **{dur_est - dias_etapa} días** dentro del margen estándar de la etapa {p_info[7]}.")
                st.write("---")
            else:
                st.info("No hay pacientes activos en la comunidad.")

    with tab2:
        st.subheader("Asignación de Hermano Mayor y Suelta")
        st.info("Asigna o registra la suelta del Hermano Mayor para acompañar al nuevo residente.")

# --- 🗣️ MÓDULO: GRUPOS TERAPÉUTICOS ---
elif menu == "🗣️ Grupos Terapéuticos":
    st.title("🗣️ Registro y Control de Grupos Terapéuticos")
    
    tab1, tab2 = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
    
    with tab1:
        st.subheader("Registrar Nueva Sesión de Grupo Terapéutico")
        pacientes = listar_pacientes_todos()
        if pacientes:
            opc_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes if p[3] == 'A'}
            sel_g = st.selectbox("Selecciona Paciente para el Grupo", list(opc_p.keys()))
            p_id_g = opc_p[sel_g]
            p_info_g = obtener_paciente(p_id_g)
            
            with st.form("form_grupo"):
                c1, c2 = st.columns(2)
                tipo_grupo = c1.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                f_grupo = c2.date_input("Fecha de Sesión", value=date.today())
                facilitador = c1.text_input("Facilitador / Staff a Cargo", value=st.session_state["nombre_completo"])
                
                compartimiento = st.text_area("Compartimiento del Paciente (Lo que expuso en el grupo)")
                observaciones = st.text_area("Observaciones del Facilitador / Grupo")
                devoluciones = st.text_area("Devoluciones Recibidas")
                compromiso = st.text_input("¿Cómo se queda y a qué se compromete?")
                
                btn_guardar_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                
                if btn_guardar_g:
                    d_grupo = {
                        "compartimiento": compartimiento,
                        "observaciones": observaciones,
                        "devoluciones": devoluciones,
                        "compromiso": compromiso
                    }
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("""
                        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_id_g, tipo_grupo, p_info_g[7], f_grupo.strftime("%Y-%m-%d"), facilitador, json.dumps(d_grupo, ensure_ascii=False), f_act, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ ¡Sesión de **{tipo_grupo}** registrada para **{p_info_g[1]}**!")
                    st.balloons()
                    st.toast("🎉 Grupo registrado exitosamente.")

    with tab2:
        st.subheader("Consultar Historial de Grupos Terapéuticos")
        st.write("Consulta y descarga el historial impreso de sesiones.")

# --- 💊 MÓDULO: CONTROL DE MEDICAMENTOS ---
elif menu == "💊 Control de Medicamentos":
    st.title("💊 Control de Medicamentos, Almacén e Inventario")
    
    tab1, tab2, tab3 = st.tabs(["📦 Entrega Diaria de Medicamentos", "📑 Catálogo y Receta Paciente", "📊 Consumo Global en Clínica"])
    
    with tab1:
        st.subheader("Surtir y Registrar Entrega Diaria en Almacén")
        pacientes = listar_pacientes_todos()
        if pacientes:
            opc_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes if p[3] == 'A'}
            sel_m = st.selectbox("Selecciona Paciente a Surtir", list(opc_p.keys()))
            p_id_m = opc_p[sel_m]
            p_info_m = obtener_paciente(p_id_m)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT meds_json FROM medicamentos WHERE paciente_id = ?", (p_id_m,))
            row = c.fetchone()
            conn.close()
            
            meds_lista = json.loads(row[0]) if (row and row[0]) else []
            
            if meds_lista:
                st.write(f"Esquema prescrito para **{p_info_m[1]}**:")
                with st.form("form_entrega_meds"):
                    entregas_dict = {}
                    for idx, m in enumerate(meds_lista):
                        ex = int(m.get("existencia", 0))
                        d_m = int(m.get("dosis_m", 0))
                        d_t = int(m.get("dosis_t", 0))
                        d_n = int(m.get("dosis_n", 0))
                        tot_dosis = d_m + d_t + d_n
                        
                        st.markdown(f"**{m.get('nombre')}** ({m.get('concentracion')}) - Existencia en Almacén: **{ex}** | Dosis Diaria: **{tot_dosis}**")
                        
                        if ex <= 0:
                            st.warning("⚠️ Sin existencias disponibles en almacén.")
                            entregas_dict[m.get('nombre')] = 0
                        else:
                            cant_sug = min(tot_dosis, ex)
                            cant_ent = st.number_input(f"Cantidad a entregar de {m.get('nombre')}", min_value=0, max_value=ex, value=cant_sug, key=f"ent_{idx}")
                            entregas_dict[m.get('nombre')] = cant_ent
                            
                    btn_entregar = st.form_submit_button("🚚 Confirmar Entrega y Descontar de Almacén", use_container_width=True)
                    if btn_entregar:
                        # Actualizar existencias
                        for m in meds_lista:
                            nom = m.get('nombre')
                            if nom in entregas_dict:
                                m['existencia'] = max(0, int(m.get('existencia', 0)) - entregas_dict[nom])
                                
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute("UPDATE medicamentos SET meds_json = ?, fecha_modificacion = ? WHERE paciente_id = ?", (json.dumps(meds_lista, ensure_ascii=False), f_act, p_id_m))
                        
                        c.execute("""
                            INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
                            VALUES (?, ?, ?, ?)
                        """, (p_id_m, f_act, st.session_state["username"], json.dumps(entregas_dict, ensure_ascii=False)))
                        conn.commit()
                        conn.close()
                        
                        st.success(f"✅ ¡Entrega registrada y descontada del inventario para **{p_info_m[1]}**!")
                        st.balloons()
                        st.toast("🎉 Medicamentos entregados exitosamente.")
                        st.rerun()
            else:
                st.info("Este paciente no tiene medicamentos ni esquema registrado.")

    with tab2:
        st.subheader("Catálogo de Medicamentos y Prescripción del Paciente")
        st.write("Gestiona la receta médica individual de cada paciente.")

    with tab3:
        st.subheader("Reporte de Consumo Global en la Clínica")
        st.write("Consulta el total de medicamentos requeridos en toda la comunidad.")

# --- 📁 MÓDULO: REPOSITORIO DE DOCUMENTOS ---
elif menu == "📁 Repositorio de Documentos":
    st.title("📁 Repositorio de Documentos, Formatos y Manuales")
    
    if not es_admin():
        st.error("🔒 **ACCESO RESTRINGIDO**: Solo los usuarios con rol de **Nivel 1 - Administrador** pueden acceder al Repositorio de Documentos.")
    else:
        st.write("Centraliza los formatos, manuales, reglamentos y plantillas de la institución en la nube.")
        
        tab1, tab2 = st.tabs(["📥 Consultar y Descargar Documentos", "📤 Subir Nuevo Documento"])
        
        with tab1:
            st.subheader("Documentos Disponibles en la Nube")
            filtro_carp = st.selectbox("Filtrar por Carpeta", ["Todas"] + CARPETAS_DEFECTO)
            
            docs = obtener_documentos_repositorio(filtro_carp)
            if docs:
                for doc in docs:
                    doc_id, carp, nom_arch, mime, bytes_b, desc, f_sub, u_sub = doc
                    with st.expander(f"📄 **{nom_arch}** ({carp}) - Subido el {f_sub}"):
                        st.write(f"**Descripción / Nota**: {desc if desc else 'Sin descripción'}")
                        st.write(f"**Subido por**: {u_sub}")
                        
                        st.download_button(
                            f"📥 Descargar {nom_arch}",
                            data=bytes_b,
                            file_name=nom_arch,
                            mime=mime,
                            key=f"dl_doc_{doc_id}"
                        )
                        
                        if st.button(f"🗑️ Eliminar {nom_arch}", key=f"del_doc_{doc_id}"):
                            eliminar_documento_repositorio(doc_id)
                            st.success(f"✅ Documento {nom_arch} eliminado.")
                            st.toast("Documento eliminado del repositorio.")
                            st.rerun()
            else:
                st.info("No hay documentos subidos en esta carpeta.")

        with tab2:
            st.subheader("Subir Nuevo Documento al Repositorio")
            with st.form("form_upload_doc"):
                carp_sub = st.selectbox("Selecciona Carpeta de Destino", CARPETAS_DEFECTO)
                arch_file = st.file_uploader("Selecciona archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "png", "jpg"])
                desc_sub = st.text_input("Descripción breve / Notas de versión")
                
                btn_up = st.form_submit_button("📤 Subir Archivo al Repositorio", use_container_width=True)
                
                if btn_up:
                    if arch_file is not None:
                        b_data = arch_file.read()
                        guardar_documento_repositorio(carp_sub, arch_file.name, arch_file.type, b_data, desc_sub, st.session_state["username"])
                        st.success(f"✅ ¡Archivo **{arch_file.name}** subido exitosamente a la carpeta **{carp_sub}**!")
                        st.balloons()
                        st.toast("🎉 Documento guardado en el repositorio.")
                    else:
                        st.error("⚠️ Debes seleccionar un archivo para subir.")

# --- 🔍 MÓDULO: BUSCAR Y LISTAR PACIENTES ---
elif menu == "🔍 Buscar y Listar Pacientes":
    st.title("🔍 Registro General de Residentes y Búsqueda")
    pacientes = listar_pacientes_todos()
    if pacientes:
        query = st.text_input("🔎 Buscar por Nombre o Folio ID")
        res = [p for p in pacientes if query.lower() in p[1].lower() or query.lower() in p[0].lower()] if query else pacientes
        
        st.subheader(f"Total de registros encontrados: {len(res)}")
        data_p = []
        for p in res:
            data_p.append({
                "Folio": p[0],
                "Nombre Completo": p[1],
                "Fecha Ingreso": p[2],
                "Estatus": "Activo" if p[3] == 'A' else "Inactivo",
                "Etapa Actual": p[4]
            })
        st.dataframe(data_p, use_container_width=True)
    else:
        st.info("No hay residentes registrados en el sistema.")

# --- ⚙️ MÓDULO: CONFIGURACIÓN & SEGURIDAD ---
elif menu == "⚙️ Configuración & Seguridad":
    st.title("⚙️ Configuración de Seguridad y Roles")
    
    tab1, tab2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Gestión de Usuarios y Roles de Personal"])
    
    with tab1:
        st.subheader("Actualizar mi Contraseña de Acceso")
        with st.form("form_pass"):
            pass_act = st.text_input("Contraseña Actual", type="password")
            pass_new = st.text_input("Nueva Contraseña", type="password")
            pass_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            btn_up_p = st.form_submit_button("Actualizar Contraseña")
            if btn_up_p:
                usr = verificar_login(st.session_state["username"], pass_act)
                if usr:
                    if pass_new == pass_conf and pass_new != "":
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hash_pass(pass_new), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Contraseña actualizada exitosamente.")
                        st.balloons()
                    else:
                        st.error("⚠️ Las contraseñas nuevas no coinciden o están vacías.")
                else:
                    st.error("❌ La contraseña actual es incorrecta.")

    with tab2:
        st.subheader("Crear Usuarios de Personal y Asignar Roles")
        if es_admin():
            with st.form("form_nuevo_usuario_staff"):
                nu_user = st.text_input("Nombre de Usuario (Login)")
                nu_nombre = st.text_input("Nombre Completo del Personal")
                nu_pass = st.text_input("Contraseña", type="password")
                nu_rol = st.selectbox("Rol y Nivel de Acceso", [
                    "Nivel 1 - Administrador",
                    "Nivel 2 - Lectura y Escritura (Staff)",
                    "Nivel 3 - Solo Lectura"
                ])
                
                btn_crear_st = st.form_submit_button("➕ Crear Cuenta de Personal", use_container_width=True)
                if btn_crear_st:
                    if nu_user and nu_pass and nu_nombre:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                                      (nu_user, hash_pass(nu_pass), nu_nombre, nu_rol))
                            conn.commit()
                            st.success(f"✅ Usuario **{nu_user}** creado exitosamente con el rol **{nu_rol}**.")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ Error al crear usuario: {e}")
                        finally:
                            conn.close()
                    else:
                        st.error("⚠️ Todos los campos son obligatorios.")
        else:
            st.error("🔒 Solo los administradores pueden gestionar usuarios y roles del personal.")

# --- 📦 MÓDULO: RESPALDO Y RESTAURACIÓN ---
elif menu == "📦 Respaldo y Restauración":
    st.title("📦 Respaldo y Restauración de Base de Datos")
    st.write("Descarga una copia completa de seguridad de tu base de datos o restaura una copia previa.")
    
    tab1, tab2 = st.tabs(["📥 Descargar Respaldo Seguro", "📤 Restaurar Base de Datos"])
    
    with tab1:
        st.subheader("Descargar Respaldo Actual (`.db`)")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                db_bytes = f.read()
            f_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                "📥 Descargar Respaldo de Base de Datos (.db)",
                data=db_bytes,
                file_name=f"Sawabona_Respaldo_DB_{f_str}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
            st.info("💡 Este archivo contiene todos los residentes, expedientes, inventario de medicamentos, grupos y documentos subidos al repositorio.")

    with tab2:
        st.subheader("Restaurar Base de Datos desde Archivo (`.db`)")
        if es_admin():
            up_db = st.file_uploader("Selecciona archivo de respaldo `.db`", type=["db", "sqlite3"])
            if up_db is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", type="primary"):
                    with open(DB_FILE, "wb") as f:
                        f.write(up_db.read())
                    st.success("✅ Base de datos restaurada correctamente. Reiniciando aplicación...")
                    st.balloons()
                    st.toast("🎉 Base de datos restaurada.")
                    st.rerun()
        else:
            st.error("🔒 Solo los administradores pueden restaurar la base de datos.")

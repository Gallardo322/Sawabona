import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Comunidad Terapéutica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios Administrativos del Sistema (Login y Roles)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador'
        )
    ''')
    # Tabla de Pacientes / Residentes
    c.execute('''
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
    ''')
    # Tabla de Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    # Tabla Catálogo Central de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT
        )
    ''')
    # Tabla de Medicamentos e Inventario por Paciente
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
    # Tabla de Historial de Entregas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    # Tabla de Grupos Terapéuticos
    c.execute('''
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
    ''')
    # Tabla de Historial de Cambios de Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_origen TEXT,
            etapa_destino TEXT,
            fecha_cambio TEXT,
            usuario_autoriza TEXT
        )
    ''')
    # Tabla de Requisitos por Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')
    # Tabla de Repositorio de Documentos
    c.execute('''
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
    ''')
    
    # Crear usuario admin por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador'))
                  
    # Poblar Catálogo Inicial de Medicamentos si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_base = [
            ('Fluoxetina', 'Cápsula', '20 mg'),
            ('Sertralina', 'Tableta', '50 mg'),
            ('Valproato de Magnesio', 'Tableta', '200 mg'),
            ('Olanzapina', 'Tableta', '10 mg'),
            ('Quetiapina', 'Tableta', '100 mg'),
            ('Omeprazol', 'Cápsula', '20 mg'),
            ('Paracetamol', 'Tableta', '500 mg'),
            ('Clonazepam', 'Gotas', '2.5 mg/ml')
        ]
        c.executemany('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion) VALUES (?, ?, ?)', meds_base)

    # Poblar Requisitos Iniciales de Etapas si está vacía
    c.execute('SELECT COUNT(*) FROM requisitos_etapas')
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
            
            ('SERVICIO SOCIAL', '30 Dias de Servicio', 0),
            ('SERVICIO SOCIAL', '2 Grupos "Aquí y Ahora"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Terapia de Grupo"', 1),
            ('SERVICIO SOCIAL', '2 Grupos "Feedbacks"', 1)
        ]
        c.executemany('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', reqs)
    
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

# --- FUNCIONES DE PACIENTES ---
def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa, fecha_inicio_etapa, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa, fecha_inicio_etapa, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa, fecha_inicio_etapa, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def verificar_duplicado_nombre(nombre_completo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = LOWER(TRIM(?))', (nombre_completo,))
    res = c.fetchone()
    conn.close()
    return res

def obtener_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes')
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

# --- CATÁLOGO DE MEDICAMENTOS ---
def obtener_catalogo_meds():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, presentacion, concentracion FROM catalogo_medicamentos ORDER BY nombre ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_med(nombre, presentacion, concentracion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion) VALUES (?, ?, ?)',
                  (nombre.strip(), presentacion.strip(), concentracion.strip()))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

# --- REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta and carpeta != "Todas las Carpetas":
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC', (carpeta,))
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuta(paciente_id, tipo_grupo, etapa_actual, fecha_grupo, facilitador, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_actual, fecha_grupo, facilitador, datos_json, fecha_actual, usuario))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM grupos_terapeutos 
        WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?
    ''', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def obtener_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro
        FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREVISTAS ---
def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
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

# --- MEDICAMENTOS DE PACIENTE ---
def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE medicamentos 
            SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (meds_json, observaciones, fecha_actual, usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (meds_json, observaciones, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2]
    return [], "", ""

def guardar_entrega_meds(paciente_id, entregado_por, detalle_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_list, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, entregado_por, detalle_json))
    conn.commit()
    conn.close()

# --- REQUISITOS Y PROMOS ---
def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def promover_paciente_etapa(paciente_id, etapa_origen, etapa_destino, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (etapa_destino, fecha_actual, fecha_actual, paciente_id))
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario))
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (hermano_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def suelta_hermano_mayor(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (fecha_actual, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

# --- INICIALIZAR BASE DE DATOS ---
init_db()

# --- AUTENTICACIÓN Y SESIÓN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["nombre_completo"] = ""
    st.session_state["rol"] = "Solo Lectura"

if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema de Control, Expedientes y Comunidad Terapéutica</h3>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Iniciar Sesión")
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submit:
                usuario_valido = verificar_login(user_input, pass_input)
                if usuario_valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usuario_valido[0]
                    st.session_state["nombre_completo"] = usuario_valido[1]
                    st.session_state["rol"] = usuario_valido[2] if len(usuario_valido) > 2 else "Administrador"
                    st.success(f"¡Bienvenido(a) {usuario_valido[1]}!")
                    st.toast(f"🔑 Sesión iniciada como {usuario_valido[2]}")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- MENÚ DE NAVEGACIÓN Y ROLES ---
    user_rol = st.session_state.get("rol", "Solo Lectura")
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **{st.session_state['nombre_completo']}**")
    st.sidebar.caption(f"🛡️ Rol: **{user_rol}**")
    st.sidebar.write("---")
    
    # Construcción de Opciones del Menú según Rol
    opciones_menu = [
        "👤 Registro y Edición de Usuarios",
        "📝 Nueva Entrevista / Editar",
        "🔍 Buscar y Listar Pacientes",
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "💊 Control de Medicamentos y Dosis",
        "🚚 Entrega de Medicamentos",
        "🚨 Alertas de Farmacia y Compras",
        "📦 Respaldo y Restauración"
    ]
    
    if user_rol == "Administrador":
        opciones_menu.append("📁 Repositorio de Documentos")
        opciones_menu.append("⚙️ Seguridad y Usuarios del Sistema")

    menu = st.sidebar.radio("Navegación", opciones_menu)
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    es_admin = (user_rol == "Administrador")
    es_escritura = (user_rol in ["Administrador", "Lectura y Escritura"])
    es_solo_lectura = (user_rol == "Solo Lectura")

    if es_solo_lectura:
        st.info("ℹ️ **Modo Solo Lectura**: Puedes consultar historiales, buscar expedientes e imprimir reportes PDF.")

    # --- MÓDULO 1: REGISTRO Y EDICIÓN DE USUARIOS ---
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes / Usuarios")
        
        pacientes_existentes = obtener_pacientes()
        
        modo_usuario = st.radio("Acción:", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        edit_paciente_id = None
        datos_edit = None
        
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            if not pacientes_existentes:
                st.warning("No hay usuarios registrados aún en el sistema.")
            else:
                opciones_pac = {f"{p[0]} - {p[1]}": p[0] for p in pacientes_existentes}
                sel_key = st.selectbox("🔑 Selecciona el Usuario a Editar", list(opciones_pac.keys()))
                if sel_key:
                    edit_paciente_id = opciones_pac[sel_key]
                    datos_edit = obtener_paciente_por_id(edit_paciente_id)
        
        form_key = f"form_usuario_{edit_paciente_id}" if edit_paciente_id else "form_usuario_nuevo"
        
        with st.form(form_key):
            st.subheader("Datos de Identificación del Usuario")
            c_u1, c_u2 = st.columns(2)
            
            val_folio = edit_paciente_id if edit_paciente_id else obtener_siguiente_folio()
            val_nombre = datos_edit[1] if datos_edit else ""
            val_f_ingreso = datetime.strptime(datos_edit[2], "%Y-%m-%d").date() if datos_edit and datos_edit[2] else date.today()
            val_f_nac = datetime.strptime(datos_edit[3], "%Y-%m-%d").date() if datos_edit and datos_edit[3] else date(2000, 1, 1)
            val_sexo = datos_edit[4] if datos_edit and datos_edit[4] in ["Masculino", "Femenino", "Otro"] else "Masculino"
            val_estatus = datos_edit[5] if datos_edit else "A"
            val_tipo = datos_edit[6] if datos_edit else "Paciente"
            val_etapa = datos_edit[7] if datos_edit else "ACOGIDA"
            val_f_etapa = datetime.strptime(datos_edit[8], "%Y-%m-%d").date() if datos_edit and datos_edit[8] else date.today()

            with c_u1:
                reg_paciente_id = st.text_input("🔑 Folio / ID de Paciente", value=val_folio, disabled=True if edit_paciente_id else False)
                reg_nombre_completo = st.text_input("👤 Nombre Completo *", value=val_nombre)
                reg_tipo_usuario = st.selectbox("Categoría de Usuario", ["Paciente", "Servidor / Staff"], index=0 if val_tipo == "Paciente" else 1)
                reg_etapa = st.selectbox("Etapa Inicial / Actual", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"], index=["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"].index(val_etapa) if val_etapa in ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"] else 0)

            with c_u2:
                reg_f_ingreso = st.date_input("📅 Fecha de Ingreso Real a la Clínica", value=val_f_ingreso)
                reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=val_f_nac, min_value=date(1920, 1, 1), max_value=date.today())
                reg_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=["Masculino", "Femenino", "Otro"].index(val_sexo))
                reg_estatus = st.selectbox("Estatus en Sistema", ["A - Activo", "B - Bloqueado / Salida"], index=0 if val_estatus == 'A' else 1)[0]
                reg_f_etapa = st.date_input("📅 Fecha de Inicio en Etapa Actual", value=val_f_etapa)

            btn_guardar_usuario = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True, disabled=not es_escritura)
            
            if btn_guardar_usuario:
                if not reg_nombre_completo:
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                elif modo_usuario == "🆕 Registrar Nuevo Usuario":
                    dup = verificar_duplicado_nombre(reg_nombre_completo)
                    if dup:
                        st.error(f"❌ Ya existe un usuario registrado con el nombre '**{dup[1]}**' (Folio **{dup[0]}**).")
                    else:
                        guardar_usuario_paciente(reg_paciente_id, reg_nombre_completo, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, reg_estatus, reg_tipo_usuario, reg_etapa, str(reg_f_etapa), st.session_state["username"])
                        st.success(f"✅ ¡Usuario {reg_nombre_completo} registrado exitosamente!")
                        st.toast(f"🎉 Registrado: {reg_nombre_completo}")
                        st.balloons()
                else:
                    guardar_usuario_paciente(edit_paciente_id, reg_nombre_completo, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, reg_estatus, reg_tipo_usuario, reg_etapa, str(reg_f_etapa), st.session_state["username"])
                    st.success(f"✅ ¡Usuario **{reg_nombre_completo}** ({edit_paciente_id}) actualizado exitosamente!")
                    st.toast(f"🎉 Actualizado: {reg_nombre_completo}")

    # --- MÓDULO 2: NUEVA ENTREVISTA / EDITAR ---
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        pacientes = obtener_pacientes()
        if not pacientes:
            st.warning("Debe registrar al menos un usuario en el sistema antes de llenar la entrevista.")
        else:
            opciones_p = {f"{p[0]} - {p[1]}": p[0] for p in pacientes}
            p_sel = st.selectbox("🔑 Selecciona el Residente", list(opciones_p.keys()))
            paciente_id_input = opciones_p[p_sel]
            
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            datos_existentes = datos_cargados if datos_cargados else {}
            
            if datos_cargados:
                st.info(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Última modificación: {f_mod}")

            with st.form("form_entrevista_completa"):
                tab1, tab2, tab3 = st.tabs(["1. Datos Socio-Demográficos", "2. Consumo y Sustancias", "3. Observaciones y Firma"])
                
                with tab1:
                    c_e1, c_e2 = st.columns(2)
                    with c_e1:
                        dep_flag = st.selectbox("¿Dependientes económicos?", ["NO", "SÍ"], index=1 if datos_existentes.get("dep_flag") == "SÍ" else 0)
                        dep_quienes = st.text_input("¿Quiénes?", value=datos_existentes.get("dep_quienes", ""))
                    with c_e2:
                        pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
                        pareja_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo", ""))
                        
                with tab2:
                    sustancias_lista = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO"]
                    tabla_consumo_guardada = datos_existentes.get("tabla_consumo", {})
                    tabla_consumo_input = {}
                    
                    for sust in sustancias_lista:
                        st.markdown(f"**{sust}**")
                        s_data = tabla_consumo_guardada.get(sust, {})
                        col_a, col_b, col_c = st.columns([1, 2, 2])
                        with col_a:
                            c_val = st.checkbox("Consume", value=s_data.get("consumo") == "SÍ", key=f"c_{sust}")
                        with col_b:
                            frec_val = st.text_input("Frecuencia", value=s_data.get("frecuencia", ""), key=f"frec_{sust}")
                        with col_c:
                            cant_val = st.text_input("Cantidad", value=s_data.get("cantidad", ""), key=f"cant_{sust}")
                        tabla_consumo_input[sust] = {"consumo": "SÍ" if c_val else "NO", "frecuencia": frec_val, "cantidad": cant_val}
                
                with tab3:
                    observaciones = st.text_area("Observaciones Clínicas del Evaluador", value=datos_existentes.get("observaciones", ""))
                    evaluador_nombre = st.text_input("Nombre del Evaluador / Consejero", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    
                btn_guardar_entrevista = st.form_submit_button("💾 Guardar Expediente de Paciente", use_container_width=True, disabled=not es_escritura)
                
                if btn_guardar_entrevista:
                    datos_completos = {
                        "dep_flag": dep_flag, "dep_quienes": dep_quienes,
                        "pareja_flag": pareja_flag, "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input, "observaciones": observaciones,
                        "evaluador_nombre": evaluador_nombre
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente!")
                    st.toast("🎉 Expediente de consejería guardado")

    # --- MÓDULO 3: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro y Expedientes de Pacientes")
        pacientes = obtener_pacientes()
        if not pacientes:
            st.warning("No hay pacientes registrados en el sistema.")
        else:
            st.subheader(f"Total de Registros: {len(pacientes)}")
            for pac in pacientes:
                p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_etapa, p_fetapa, p_hmayor, p_fsuelta = pac
                est_badge = "🟢 Activo" if p_est == 'A' else "🔴 Salida / Bloqueado"
                with st.expander(f"👤 **{p_nom}** | Folio: `{p_id}` | Etapa: **{p_etapa}** | {est_badge}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Fecha Ingreso Real:** {p_fing}")
                        st.write(f"**Fecha Nacimiento:** {p_fnac}")
                        st.write(f"**Sexo:** {p_sex}")
                        st.write(f"**Categoría:** {p_tipo}")
                    with c2:
                        st.write(f"**Etapa Actual:** {p_etapa}")
                        st.write(f"**Fecha Inicio Etapa:** {p_fetapa}")
                        if p_hmayor:
                            st.write(f"**Hermano Mayor:** {p_hmayor}")

    # --- MÓDULO 4: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Control de Etapas, Avance y Hermano Mayor")
        pacientes = [p for p in obtener_pacientes() if p[6] == "Paciente" and p[5] == "A"]
        if not pacientes:
            st.warning("No hay pacientes activos para evaluar su proceso.")
        else:
            opciones_p = {f"{p[0]} - {p[1]} ({p[7]})": p for p in pacientes}
            p_sel_key = st.selectbox("🔑 Selecciona el Residente a Evaluar", list(opciones_p.keys()))
            p_data = opciones_p[p_sel_key]
            
            p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_etapa, p_fetapa, p_hmayor, p_fsuelta = p_data
            
            st.markdown(f"### 👤 {p_nom} | Folio: `{p_id}`")
            
            duracion_etapas = {"ACOGIDA": 30, "IDENTIFICACIÓN": 60, "ELABORACIÓN": 60, "CONSOLIDACIÓN": 30, "SERVICIO SOCIAL": 30}
            dias_duracion_esperada = duracion_etapas.get(p_etapa, 30)
            
            f_ingreso_dt = datetime.strptime(p_fing, "%Y-%m-%d").date() if p_fing else date.today()
            f_etapa_dt = datetime.strptime(p_fetapa, "%Y-%m-%d").date() if p_fetapa else date.today()
            
            dias_totales_clinica = (date.today() - f_ingreso_dt).days
            dias_en_etapa_actual = (date.today() - f_etapa_dt).days
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Días Totales en Clínica", f"{dias_totales_clinica} días")
            col_m2.metric(f"Días en Etapa ({p_etapa})", f"{dias_en_etapa_actual} / {dias_duracion_esperada} días")
            
            dias_restantes = dias_duracion_esperada - dias_en_etapa_actual
            if dias_restantes < 0:
                col_m3.error(f"⚠️ RESIDENTE EN REZAGO (+{abs(dias_restantes)} días excedidos)")
            elif dias_restantes <= 5:
                col_m3.warning(f"🚨 ALERTA: Le quedan {dias_restantes} días para cambio de etapa")
            else:
                col_m3.success(f"🟢 Tiempo normal ({dias_restantes} días restantes)")

            st.write("---")
            
            st.subheader(f"📋 Checklist de Requisitos para Etapa: **{p_etapa}**")
            reqs_etapa = obtener_requisitos_etapa(p_etapa)
            
            reqs_completados = True
            for req in reqs_etapa:
                r_id, r_txt, es_grupo = req
                if es_grupo:
                    tipo_g_search = "Terapia de Grupo" if "Terapia" in r_txt else ("Aquí y Ahora" if "Aquí" in r_txt else "Feedback")
                    cant_req = 4 if "4" in r_txt else (2 if "2" in r_txt else 1)
                    cant_hechos = contar_grupos_paciente_etapa(p_id, p_etapa, tipo_g_search)
                    cumple = cant_hechos >= cant_req
                    st.checkbox(f"{r_txt} (Registrados: {cant_hechos}/{cant_req})", value=cumple, disabled=True)
                    if not cumple:
                        reqs_completados = False
                else:
                    chk = st.checkbox(f"{r_txt}", key=f"chk_{p_id}_{r_id}")
                    if not chk:
                        reqs_completados = False
            
            etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            curr_idx = etapas_orden.index(p_etapa) if p_etapa in etapas_orden else 0
            
            if curr_idx < len(etapas_orden) - 1:
                sig_etapa = etapas_orden[curr_idx + 1]
                if st.button(f"🚀 Promover a Siguiente Etapa: {sig_etapa}", disabled=not (reqs_completados and es_escritura), use_container_width=True):
                    promover_paciente_etapa(p_id, p_etapa, sig_etapa, st.session_state["username"])
                    st.success(f"¡{p_nom} promovido exitosamente a {sig_etapa}!")
                    st.toast(f"🎉 Promovido a {sig_etapa}")
                    st.rerun()

    # --- MÓDULO 5: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        pacientes = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes:
            st.warning("No hay pacientes activos registrados.")
        else:
            opciones_p = {f"{p[0]} - {p[1]} ({p[7]})": p for p in pacientes}
            p_sel_g = st.selectbox("🔑 Selecciona el Residente", list(opciones_p.keys()))
            p_data_g = opciones_p[p_sel_g]
            p_id_g, p_nom_g, _, _, _, _, _, p_etapa_g, _, _, _ = p_data_g
            
            tipo_grupo = st.radio("Tipo de Grupo:", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"], horizontal=True)
            
            with st.form("form_grupo_terapeuta"):
                st.subheader(f"Captura de Sesión: **{tipo_grupo}** | Paciente: {p_nom_g} ({p_etapa_g})")
                
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    f_grupo = st.date_input("Fecha de la Sesión", value=date.today())
                with c_g2:
                    facilitador = st.text_input("Facilitador / Consejero", value=st.session_state["nombre_completo"])
                
                if tipo_grupo == "Feedback":
                    logros = st.text_area("Logros Observados")
                    dificultades = st.text_area("Dificultades Presentadas")
                    observaciones_g = st.text_area("Observaciones Clínicas")
                    devoluciones_g = st.text_area("Devoluciones Terapéuticas")
                    compromiso_g = st.text_area("¿Cómo se queda y a qué se compromete?")
                    datos_g = {"logros": logros, "dificultades": dificultades, "observaciones": observaciones_g, "devoluciones": devoluciones_g, "compromiso": compromiso_g}
                else:
                    compartimiento = st.text_area("Compartimiento del Residente")
                    observaciones_g = st.text_area("Observaciones Clínicas")
                    devoluciones_g = st.text_area("Devoluciones Terapéuticas")
                    compromiso_g = st.text_area("¿Cómo se queda y a qué se compromete?")
                    datos_g = {"compartimiento": compartimiento, "observaciones": observaciones_g, "devoluciones": devoluciones_g, "compromiso": compromiso_g}

                btn_guardar_grupo = st.form_submit_button("💾 Registrar Sesión de Grupo", use_container_width=True, disabled=not es_escritura)
                
                if btn_guardar_grupo:
                    guardar_grupo_terapeuta(p_id_g, tipo_grupo, p_etapa_g, str(f_grupo), facilitador, datos_g, st.session_state["username"])
                    st.success(f"✅ Sesión de {tipo_grupo} registrada exitosamente para {p_nom_g}.")
                    st.toast("🎉 Grupo guardado y contabilizado en su etapa")

    # --- MÓDULO 6: CONTROL DE MEDICAMENTOS Y CATÁLOGO ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Dosis, Inventario y Catálogo Central")
        
        tab_med1, tab_med2, tab_med3 = st.tabs(["💊 Asignar Dosis a Paciente", "📚 Catálogo Central de Medicamentos", "📊 Reporte Global por Medicamento"])
        
        with tab_med1:
            pacientes = [p for p in obtener_pacientes() if p[5] == "A"]
            if not pacientes:
                st.warning("No hay pacientes registrados.")
            else:
                opciones_p = {f"{p[0]} - {p[1]}": p[0] for p in pacientes}
                p_sel_m = st.selectbox("🔑 Selecciona el Residente para Medicación", list(opciones_p.keys()))
                p_id_m = opciones_p[p_sel_m]
                
                meds_cargados, obs_meds, _ = obtener_medicamentos_paciente(p_id_m)
                
                cat_meds = obtener_catalogo_meds()
                opciones_cat = [f"{m[1]} ({m[2]} - {m[3]})" for m in cat_meds] if cat_meds else ["Otro"]
                
                with st.form("form_esquema_meds"):
                    st.subheader(f"Esquema de Dosis para: {p_sel_m}")
                    num_meds = st.number_input("Número de Medicamentos a Asignar", min_value=1, max_value=10, value=max(len(meds_cargados), 1))
                    
                    meds_input = []
                    for i in range(num_meds):
                        m_exist = meds_cargados[i] if i < len(meds_cargados) else {}
                        st.markdown(f"**Medicamento #{i+1}**")
                        c_m1, c_m2, c_m3, c_m4, c_m5 = st.columns([3, 1, 1, 1, 1])
                        
                        with c_m1:
                            med_nom = st.selectbox(f"Medicamento #{i+1}", opciones_cat, key=f"cat_m_{p_id_m}_{i}")
                        with c_m2:
                            d_manana = st.number_input("☀️ Mañana", min_value=0.0, step=0.5, value=float(m_exist.get("dosis_manana", 0)), key=f"man_{p_id_m}_{i}")
                        with c_m3:
                            d_tarde = st.number_input("🌤️ Tarde", min_value=0.0, step=0.5, value=float(m_exist.get("dosis_tarde", 0)), key=f"tar_{p_id_m}_{i}")
                        with c_m4:
                            d_noche = st.number_input("🌙 Noche", min_value=0.0, step=0.5, value=float(m_exist.get("dosis_noche", 0)), key=f"noc_{p_id_m}_{i}")
                        with c_m5:
                            ex_stock = st.number_input("📦 Existencia", min_value=0, value=int(m_exist.get("existencia", 0)), key=f"ex_{p_id_m}_{i}")
                            
                        meds_input.append({
                            "nombre": med_nom, "dosis_manana": d_manana, "dosis_tarde": d_tarde, "dosis_noche": d_noche, "existencia": ex_stock
                        })
                    
                    obs_input = st.text_area("Observaciones o Alergias Medicamentosas", value=obs_meds)
                    btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema de Dosis", use_container_width=True, disabled=not es_escritura)
                    
                    if btn_guardar_meds:
                        guardar_medicamentos_paciente(p_id_m, meds_input, obs_input, st.session_state["username"])
                        st.success("✅ ¡Esquema de medicamentos guardado exitosamente!")
                        st.toast("🎉 Dosis e inventario actualizados")

        with tab_med2:
            st.subheader("📚 Catálogo Central de Medicamentos")
            if es_escritura:
                with st.form("form_add_cat_med"):
                    c_c1, c_c2, c_c3 = st.columns(3)
                    with c_c1:
                        new_nom = st.text_input("Nombre del Medicamento")
                    with c_c2:
                        new_pres = st.selectbox("Presentación", ["Tableta", "Cápsula", "Gotas", "Jarabe", "Inyectable", "Otro"])
                    with c_c3:
                        new_conc = st.text_input("Concentración (ej. 500 mg, 20 mg)")
                    btn_cat = st.form_submit_button("➕ Agregar al Catálogo")
                    if btn_cat and new_nom:
                        if agregar_catalogo_med(new_nom, new_pres, new_conc):
                            st.success(f"✅ ¡{new_nom} agregado al catálogo!")
                            st.rerun()
            
            cat_actual = obtener_catalogo_meds()
            st.dataframe([{"ID": m[0], "Nombre": m[1], "Presentación": m[2], "Concentración": m[3]} for m in cat_actual], use_container_width=True)

        with tab_med3:
            st.subheader("📊 Consumo Global por Medicamento en la Comunidad")
            cat_actual = obtener_catalogo_meds()
            if cat_actual:
                sel_m_report = st.selectbox("Selecciona Medicamento para Reporte", [m[1] for m in cat_actual])
                
                todos_pacientes = obtener_pacientes()
                consumo_filas = []
                total_diario_comunidad = 0.0
                total_stock_comunidad = 0
                
                for p in todos_pacientes:
                    pid, pnom = p[0], p[1]
                    m_list, _, _ = obtener_medicamentos_paciente(pid)
                    for m in m_list:
                        if sel_m_report in m.get("nombre", ""):
                            d_m = float(m.get("dosis_manana", 0))
                            d_t = float(m.get("dosis_tarde", 0))
                            d_n = float(m.get("dosis_noche", 0))
                            d_tot = d_m + d_t + d_n
                            ex = int(m.get("existencia", 0))
                            total_diario_comunidad += d_tot
                            total_stock_comunidad += ex
                            consumo_filas.append({
                                "Residente": pnom, "Folio": pid, "Mañana": d_m, "Tarde": d_t, "Noche": d_n, "Dosis Diaria Total": d_tot, "Stock Individual": ex
                            })
                            
                col_r1, col_r2 = st.columns(2)
                col_r1.metric("Consumo Diario Total en la Clínica", f"{total_diario_comunidad:.1f} unidades/día")
                col_r2.metric("Stock Total Acumulado en Almacén", f"{total_stock_comunidad} unidades")
                
                if consumo_filas:
                    st.dataframe(consumo_filas, use_container_width=True)
                else:
                    st.info("Ningún residente tiene asignado este medicamento actualmente.")

    # --- MÓDULO 7: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Entrega y Descuento de Stock")
        pacientes = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes:
            st.warning("No hay pacientes activos.")
        else:
            opciones_p = {f"{p[0]} - {p[1]}": p[0] for p in pacientes}
            p_sel_e = st.selectbox("🔑 Selecciona el Residente para Entrega", list(opciones_p.keys()))
            p_id_e = opciones_p[p_sel_e]
            
            meds_cargados, obs_meds, _ = obtener_medicamentos_paciente(p_id_e)
            if not meds_cargados:
                st.warning("Este paciente no tiene medicamentos registrados en su esquema.")
            else:
                with st.form("form_entrega_meds"):
                    st.subheader(f"Entrega para: {p_sel_e}")
                    
                    entregas_input = []
                    for i, m in enumerate(meds_cargados):
                        m_nom = m.get("nombre", f"Med #{i+1}")
                        d_m = float(m.get("dosis_manana", 0))
                        d_t = float(m.get("dosis_tarde", 0))
                        d_n = float(m.get("dosis_noche", 0))
                        d_diaria = d_m + d_t + d_n
                        ex_actual = int(m.get("existencia", 0))
                        
                        val_default = min(int(d_diaria), ex_actual) if ex_actual > 0 else 0
                        
                        st.markdown(f"💊 **{m_nom}** | Dosis recomendada: `{d_diaria}` | Stock actual: `{ex_actual}`")
                        cant_entregar = st.number_input(f"Cantidad a Entregar para {m_nom}", min_value=0, max_value=ex_actual, value=val_default, key=f"ent_{p_id_e}_{i}")
                        entregas_input.append({"index": i, "nombre": m_nom, "entregado": cant_entregar, "anterior": ex_actual, "nuevo_stock": ex_actual - cant_entregar})
                    
                    btn_ejecutar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar Stock", use_container_width=True, disabled=not es_escritura)
                    
                    if btn_ejecutar_entrega:
                        for e in entregas_input:
                            idx = e["index"]
                            meds_cargados[idx]["existencia"] = e["nuevo_stock"]
                        
                        guardar_medicamentos_paciente(p_id_e, meds_cargados, obs_meds, st.session_state["username"])
                        guardar_entrega_meds(p_id_e, st.session_state["nombre_completo"], entregas_input)
                        st.success("✅ Entrega registrada exitosamente. Inventario actualizado.")
                        st.toast("🎉 Entrega guardada y stock descontado")

    # --- MÓDULO 8: ALERTAS DE FARMACIA ---
    elif menu == "🚨 Alertas de Farmacia y Compras":
        st.title("🚨 Alertas Preventivas de Inventario y Farmacia")
        todos_pacientes = [p for p in obtener_pacientes() if p[5] == "A"]
        
        alertas_criticas = []
        alertas_preventivas = []
        
        for p in todos_pacientes:
            pid, pnom = p[0], p[1]
            meds, _, _ = obtener_medicamentos_paciente(pid)
            for m in meds:
                d_tot = float(m.get("dosis_manana", 0)) + float(m.get("dosis_tarde", 0)) + float(m.get("dosis_noche", 0))
                ex = int(m.get("existencia", 0))
                if d_tot > 0:
                    dias_cobertura = ex / d_tot
                    item = {"paciente": pnom, "folio": pid, "medicamento": m.get("nombre"), "existencia": ex, "dosis_diaria": d_tot, "dias": dias_cobertura}
                    if dias_cobertura <= 1:
                        alertas_criticas.append(item)
                    elif dias_cobertura <= 3:
                        alertas_preventivas.append(item)
                        
        if not alertas_criticas and not alertas_preventivas:
            st.success("✅ El inventario de farmacia se encuentra en niveles óptimos para todos los pacientes.")
        else:
            if alertas_criticas:
                st.error("🚨 **ALERTAS CRÍTICAS (Se agotan en menos de 1 día):**")
                for ac in alertas_criticas:
                    st.write(f"• **{ac['paciente']}** (`{ac['folio']}`) | **{ac['medicamento']}** | Quedan: `{ac['existencia']}` pastillas (Dosis diaria: `{ac['dosis_diaria']}`)")
            
            if alertas_preventivas:
                st.warning("⚠️ **ALERTAS PREVENTIVAS (Se agotan en menos de 3 días):**")
                for ap in alertas_preventivas:
                    st.write(f"• **{ap['paciente']}** (`{ap['folio']}`) | **{ap['medicamento']}** | Quedan: `{ap['existencia']}` pastillas ({ap['dias']:.1f} días de cobertura)")

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS (SOLO ADMIN) ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos, Formatos y Manuales")
        if not es_admin:
            st.error("🔒 Acceso Restringido: Este módulo es exclusivo para administradores.")
        else:
            tab_doc1, tab_doc2 = st.tabs(["📥 Descargar Documentos", "📤 Subir Nuevo Documento"])
            
            carpetas_default = [
                "Todas las Carpetas",
                "📋 Formatos Clínicos y Administrativos",
                "📖 Manuales de Operación",
                "⚖️ Reglamentos y Normativas",
                "📑 Plantillas de Evaluación",
                "📁 Documentos Generales"
            ]
            
            with tab_doc1:
                c_filtro = st.selectbox("Filtrar por Carpeta:", carpetas_default)
                docs = obtener_documentos_repositorio(c_filtro)
                
                if not docs:
                    st.info("No hay documentos subidos en esta carpeta.")
                else:
                    for doc in docs:
                        d_id, d_carp, d_nom, d_mime, d_blob, d_desc, d_fsub, d_usub = doc
                        with st.expander(f"📄 **{d_nom}** | Carpeta: `{d_carp}` | Fecha: {d_fsub}"):
                            st.write(f"**Descripción:** {d_desc if d_desc else 'Sin descripción'}")
                            st.write(f"**Subido por:** {d_usub}")
                            col_d1, col_d2 = st.columns([2, 1])
                            with col_d1:
                                st.download_button(
                                    label=f"📥 Descargar {d_nom}",
                                    data=d_blob,
                                    file_name=d_nom,
                                    mime=d_mime if d_mime else "application/octet-stream",
                                    key=f"down_doc_{d_id}"
                                )
                            with col_d2:
                                if st.button("🗑️ Eliminar", key=f"del_doc_{d_id}"):
                                    eliminar_documento_repositorio(d_id)
                                    st.success("Documento eliminado.")
                                    st.rerun()

            with tab_doc2:
                with st.form("form_subir_documento"):
                    st.subheader("Subir Nuevo Documento a la Nube")
                    carp_sel = st.selectbox("Selecciona Carpeta de Destino", carpetas_default[1:])
                    file_up = st.file_uploader("Selecciona Archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "doc", "xls", "png", "jpg"])
                    desc_up = st.text_input("Descripción o Notas del Documento")
                    
                    btn_up = st.form_submit_button("📤 Subir Archivo al Repositorio")
                    if btn_up:
                        if not file_up:
                            st.error("Por favor selecciona un archivo.")
                        else:
                            file_bytes = file_up.read()
                            guardar_documento_repositorio(carp_sel, file_up.name, file_up.type, file_bytes, desc_up, st.session_state["username"])
                            st.success(f"✅ ¡Archivo {file_up.name} guardado en {carp_sel}!")
                            st.toast("🎉 Documento subido al repositorio")

    # --- MÓDULO 10: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        tab_r1, tab_r2 = st.tabs(["📥 Descargar Respaldo Seguro", "📤 Restaurar Base de Datos"])
        
        with tab_r1:
            st.subheader("Descargar Copia de Seguridad (.db)")
            st.write("Descarga un respaldo completo que incluye todos los residentes, entrevistas, medicamentos, entregas, grupos y documentos.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="📥 Descargar Respaldo de Base de Datos (.db)",
                        data=f,
                        file_name=f"Sawabona_Respaldo_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )

        with tab_r2:
            st.subheader("Restaurar Base de Datos desde Respaldo")
            if not es_admin:
                st.error("🔒 Solo los administradores pueden restaurar la base de datos.")
            else:
                db_upload = st.file_uploader("Carga tu archivo de respaldo (.db)", type=["db", "sqlite3"])
                if db_upload and st.button("⚠️ Confirmar Restauración de Base de Datos"):
                    with open(DB_FILE, "wb") as f:
                        f.write(db_upload.read())
                    st.success("✅ Base de datos restaurada exitosamente.")
                    st.toast("🎉 Restauración completa")
                    st.rerun()

    # --- MÓDULO 11: SEGURIDAD Y ROLES (SOLO ADMIN) ---
    elif menu == "⚙️ Seguridad y Usuarios del Sistema":
        st.title("⚙️ Configuración de Seguridad y Roles")
        if not es_admin:
            st.error("🔒 Acceso Restringido: Este módulo es exclusivo para administradores.")
        else:
            tab_s1, tab_s2 = st.tabs(["👤 Administrar Usuarios del Sistema", "🔑 Cambiar Mi Contraseña"])
            
            with tab_s1:
                st.subheader("Crear / Editar Cuentas de Acceso al Sistema")
                with st.form("form_crear_usuario_sistema"):
                    c_s1, c_s2, c_s3 = st.columns(3)
                    with c_s1:
                        new_u_username = st.text_input("Nombre de Usuario (Login)")
                    with c_s2:
                        new_u_nombre = st.text_input("Nombre Completo del Personal")
                    with c_s3:
                        new_u_pass = st.text_input("Contraseña", type="password")
                    
                    new_u_rol = st.selectbox("Rol y Permisos", ["Administrador", "Lectura y Escritura", "Solo Lectura"])
                    btn_create_sys_user = st.form_submit_button("➕ Registrar Cuenta de Acceso")
                    
                    if btn_create_sys_user and new_u_username and new_u_pass:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                      (new_u_username.strip(), hash_pass(new_u_pass), new_u_nombre.strip(), new_u_rol))
                            conn.commit()
                            st.success(f"✅ ¡Cuenta `{new_u_username}` creada con rol **{new_u_rol}**!")
                        except Exception as ex:
                            st.error(f"Error al crear usuario: {ex}")
                        finally:
                            conn.close()

                st.write("---")
                st.subheader("Cuentas Registradas en el Sistema")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol FROM usuarios')
                usrs = c.fetchall()
                conn.close()
                st.dataframe([{"ID": u[0], "Usuario": u[1], "Nombre Personal": u[2], "Rol": u[3]} for u in usrs], use_container_width=True)

            with tab_s2:
                with st.form("form_cambio_pass"):
                    actual_pass = st.text_input("Contraseña Actual", type="password")
                    nueva_pass = st.text_input("Nueva Contraseña", type="password")
                    confirm_pass = st.text_input("Confirmar Nueva Contraseña", type="password")
                    btn_pass = st.form_submit_button("Actualizar Mi Contraseña")
                    
                    if btn_pass:
                        if nueva_pass != confirm_pass:
                            st.error("Las contraseñas no coinciden.")
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
                                st.error("Contraseña actual incorrecta.")

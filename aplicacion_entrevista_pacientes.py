import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Comunidad Terapéutica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios Administrativos / Staff
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    """)
    
    # Migración de columna 'rol' si la tabla usuarios ya existía
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [row[1] for row in c.fetchall()]
    if 'rol' not in cols_u:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
        except Exception:
            pass

    # Asegurar que admin tenga rol Administrador
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")

    # 2. Tabla de Pacientes / Residentes de la Comunidad
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
    
    # Migraciones en pacientes si faltaran columnas
    c.execute("PRAGMA table_info(pacientes)")
    cols_p = [row[1] for row in c.fetchall()]
    if 'fecha_inicio_etapa' not in cols_p:
        try:
            c.execute("ALTER TABLE pacientes ADD COLUMN fecha_inicio_etapa TEXT")
        except Exception:
            pass

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

    # 4. Tabla Catálogo de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_medicamento TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            observaciones TEXT
        )
    """)
    
    # Población inicial de catálogo de medicamentos si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_iniciales = [
            ('Paracetamol', 'Comprimidos', '500 mg', 'Analgésico / Antipirético'),
            ('Ibuprofeno', 'Comprimidos', '400 mg', 'Antiinflamatorio'),
            ('Omeprazol', 'Cápsulas', '20 mg', 'Protector gástrico'),
            ('Complex B', 'Tabletas', 'Multivitamínico', 'Suplemento vitamínico'),
            ('Sertralina', 'Tabletas', '50 mg', 'Ansiolítico / Antidepresivo'),
            ('Clonazepam', 'Gotas', '2.5 mg/ml', 'Uso controlado con receta')
        ]
        c.executemany('INSERT INTO catalogo_medicamentos (nombre_medicamento, presentacion, concentracion, observaciones) VALUES (?, ?, ?, ?)', meds_iniciales)

    # 5. Tabla de Medicamentos e Inventario por Paciente
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

    # 6. Tabla de Historial de Entregas de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    """)

    # 7. Tabla de Grupos Terapéuticos (Terapia de Grupo, Aquí y Ahora, Feedback)
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

    # 8. Tabla de Historial de Cambios de Etapa
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

    # 9. Tabla de Requisitos por Etapa (Configurable)
    c.execute("""
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    """)
    
    # Población inicial de requisitos de etapas si está vacía
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

    # 10. Tabla de Repositorio de Documentos (Archivos PDF, Word, Excel, etc.)
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

    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES AUXILIARES DE SEGURIDAD Y PERMISOS ---
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
    if "username" in st.session_state and st.session_state["username"] == "admin":
        return True
    rol = st.session_state.get("rol", "")
    return "Nivel 1" in rol or "Administrador" in rol

def puede_escribir():
    if es_admin():
        return True
    rol = st.session_state.get("rol", "")
    return "Nivel 2" in rol or "Escritura" in rol

# --- FUNCIONES DE MANEJO DE PACIENTES Y GRUPOS ---
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
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = " ".join(nombre.strip().upper().split())
    if paciente_id_actual:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE paciente_id != ?', (paciente_id_actual,))
    else:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    for pid, pnom, pest in rows:
        if " ".join(pnom.strip().upper().split()) == nombre_clean:
            return pid, pnom, pest
    return None

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, usuario_act):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ing_str = fecha_ingreso.strftime("%Y-%m-%d") if isinstance(fecha_ingreso, (datetime, date)) else str(fecha_ingreso)
    f_nac_str = fecha_nacimiento.strftime("%Y-%m-%d") if isinstance(fecha_nacimiento, (datetime, date)) else str(fecha_nacimiento)
    f_ini_etapa_str = fecha_inicio_etapa.strftime("%Y-%m-%d") if isinstance(fecha_inicio_etapa, (datetime, date)) else str(fecha_inicio_etapa)
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    if existe:
        c.execute("""
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?,
                fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        """, (nombre_completo, f_ing_str, f_nac_str, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa_str, fecha_actual, usuario_act, paciente_id))
    else:
        c.execute("""
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, nombre_completo, f_ing_str, f_nac_str, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa_str, fecha_actual, fecha_actual, usuario_act))
    conn.commit()
    conn.close()

def listar_todos_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def promover_paciente_etapa(paciente_id, etapa_origen, etapa_destino, usuario_act):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy_str = datetime.now().strftime("%Y-%m-%d")
    
    # Actualizar etapa_actual y reiniciar fecha_inicio_etapa
    c.execute("""
        UPDATE pacientes
        SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?, usuario_registro = ?
        WHERE paciente_id = ?
    """, (etapa_destino, f_hoy_str, fecha_actual_str, usuario_act, paciente_id))
    
    # Guardar en historial
    c.execute("""
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    """, (paciente_id, etapa_origen, etapa_destino, fecha_actual_str, usuario_act))
    
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_mayor_id, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (fecha_hoy, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeutico(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_dict, usuario_act):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos_dict, ensure_ascii=False)
    c.execute("""
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_actual, usuario_act))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa_actual, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM grupos_terapeutos
        WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?
    """, (paciente_id, etapa_actual, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro
        FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC
    """, (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE CATÁLOGO Y MEDICAMENTOS ---
def listar_catalogo_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre_medicamento, presentacion, concentracion, observaciones FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_medicamento(nombre, presentacion, concentracion, observaciones):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO catalogo_medicamentos (nombre_medicamento, presentacion, concentracion, observaciones) VALUES (?, ?, ?, ?)',
                  (nombre, presentacion, concentracion, observaciones))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0]), row[1]
    return [], ""

def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario_act):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute("""
            UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        """, (meds_json, observaciones, fecha_actual, usuario_act, paciente_id))
    else:
        c.execute("""
            INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario_act))
    conn.commit()
    conn.close()

# --- FUNCIONES DEL REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario_subida):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_actual, usuario_subida))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "Todas las Carpetas":
        c.execute("""
            SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida
            FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC
        """, (carpeta_filtro,))
    else:
        c.execute("""
            SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida
            FROM repositorio_documentos ORDER BY id DESC
        """)
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- AUTENTICACIÓN / SESIÓN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = "Nivel 1 - Administrador"

if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema Integral de Control y Comunidad Terapéutica</h3>", unsafe_allow_html=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Iniciar Sesión")
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit_login:
                res = verificar_login(user_input, pass_input)
                if res:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["nombre_completo"] = res[1]
                    st.session_state["rol"] = res[2] if len(res) > 2 and res[2] else "Nivel 1 - Administrador"
                    st.toast(f"¡Bienvenido, {res[1]}!", icon="🎉")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
    st.stop()

# --- BARRA LATERAL (NAVEGACIÓN Y ROL) ---
st.sidebar.title("🌱 Sawabona Shikoba")
st.sidebar.markdown(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
st.sidebar.caption(f"🔑 **Rol**: {st.session_state['rol']}")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["nombre_completo"] = ""
    st.session_state["rol"] = ""
    st.rerun()

st.sidebar.divider()

opciones_menu = [
    "🎯 Gestión de Etapas & Proceso",
    "👤 Registro y Edición de Usuarios",
    "🗣️ Grupos Terapéuticos",
    "📝 Entrevista Inicial de Consejería",
    "💊 Control de Medicamentos & Dosis",
    "🚚 Entrega de Medicamentos",
    "📦 Respaldo y Restauración"
]

if es_admin():
    opciones_menu.append("📁 Repositorio de Documentos")
    opciones_menu.append("⚙️ Configuración & Seguridad")

menu = st.sidebar.radio("Navegación", opciones_menu)

# ==============================================================================
# MÓDULO 1: 🎯 GESTIÓN DE ETAPAS & PROCESO (CON REZAGOS Y CHECKLIST)
# ==============================================================================
if menu == "🎯 Gestión de Etapas & Proceso":
    st.title("🎯 Gestión de Etapas & Proceso Individual")
    st.markdown("Seguimiento del avance en las 5 etapas del tratamiento, alertas de tiempo y control de rezago.")
    
    pacs = listar_todos_pacientes()
    solo_pacientes = [p for p in pacs if p[6] == 'Paciente' and p[5] == 'A']
    
    if not solo_pacientes:
        st.warning("No hay pacientes activos registrados en el sistema.")
    else:
        tab_avance, tab_hermano, tab_historial = st.tabs([
            "📊 Evaluador de Etapa y Rezagos",
            "🤝 Hermano Menor & Mayor",
            "📜 Historial de Cambios de Etapa"
        ])
        
        # --- TAB 1: EVALUADOR DE ETAPA Y REZAGOS ---
        with tab_avance:
            opcs_pacientes = [f"{p[0]} - {p[1]} (Etapa actual: {p[7]})" for p in solo_pacientes]
            sel_pac_str = st.selectbox("🔑 Selecciona el Residente a Evaluar", opcs_pacientes)
            sel_pid = sel_pac_str.split(" - ")[0]
            
            p_data = obtener_paciente(sel_pid)
            # p_data: (id, nombre, f_ingreso, f_nac, sexo, estatus, tipo, etapa_act, f_ini_etapa, h_mayor, f_suelta)
            p_id, p_nom, p_fing, p_fnac, p_sexo, p_est, p_tipo, p_etapa, p_fini_etapa, p_hmayor, p_fsuelta = p_data
            
            # Cálculo de fechas
            hoy = date.today()
            try:
                dt_fing = datetime.strptime(p_fing, "%Y-%m-%d").date()
            except Exception:
                dt_fing = hoy
            
            try:
                dt_fini_etapa = datetime.strptime(p_fini_etapa, "%Y-%m-%d").date() if p_fini_etapa else dt_fing
            except Exception:
                dt_fini_etapa = dt_fing

            dias_totales_clinica = (hoy - dt_fing).days
            dias_en_etapa_actual = (hoy - dt_fini_etapa).days
            
            # Duraciones estándar de etapas
            duracion_etapas = {
                'ACOGIDA': 30,
                'IDENTIFICACIÓN': 60,
                'ELABORACIÓN': 60,
                'CONSOLIDACIÓN': 30,
                'SERVICIO SOCIAL': 30
            }
            
            duracion_req = duracion_etapas.get(p_etapa, 30)
            
            # ALERTAS DE TIEMPO Y REZAGO / ESTANCAMIENTO
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("🗓️ Días Totales en Comunidad", f"{dias_totales_clinica} días", help="Días desde la fecha de ingreso real")
            col_m2.metric("⏱️ Días en Etapa Actual", f"{dias_en_etapa_actual} / {duracion_req} días", help=f"Días desde el inicio de {p_etapa}")
            
            dias_restantes = duracion_req - dias_en_etapa_actual
            
            if dias_en_etapa_actual > duracion_req:
                excedido = dias_en_etapa_actual - duracion_req
                col_m3.metric("⚠️ Estado de Tiempo", "EN REZAGO", f"+{excedido} días excedidos", delta_color="inverse")
                st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El paciente **{p_nom}** lleva **{dias_totales_clinica} días internado** en la comunidad y suma **{dias_en_etapa_actual} días en la Etapa {p_etapa}** (Duración estimada: {duracion_req} días). Se ha excedido por **+{excedido} días** sin haber cumplido su promoción.")
            elif dias_restantes <= 5:
                col_m3.metric("🚨 Estado de Tiempo", "PRÓXIMO A CUMPLIR", f"{dias_restantes} días restantes")
                st.warning(f"⏰ **ALERTA TEMPRANA DE CAMBIO DE ETAPA**: **{p_nom}** está a **{dias_restantes} días** de cumplir los {duracion_req} días programados para la etapa **{p_etapa}**. Por favor revisa el checklist de requisitos para preparar su evaluación.")
            else:
                col_m3.metric("✅ Estado de Tiempo", "EN TIEMPO NORMAL", f"{dias_restantes} días restantes")

            # Barra de progreso
            prog_val = min(1.0, max(0.0, dias_en_etapa_actual / duracion_req))
            st.progress(prog_val, text=f"Avance en días de {p_etapa}: {dias_en_etapa_actual} de {duracion_req} días ({int(prog_val * 100)}%)")
            
            st.divider()
            st.subheader(f"📋 Checklist de Requisitos y Diagnóstico de Bloqueo: Etapa {p_etapa}")
            
            # Cargar requisitos configurados de la base de datos
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ?', (p_etapa,))
            reqs_etapa = c.fetchall()
            conn.close()
            
            items_completados = 0
            items_totales = len(reqs_etapa)
            
            with st.form(f"form_checklist_{p_id}_{p_etapa}"):
                st.markdown("##### Marca los requisitos completados o verifica el conteo automático de grupos:")
                
                chk_states = {}
                for req_id, req_texto, es_grupo in reqs_etapa:
                    if es_grupo:
                        # Extraer tipo de grupo del texto
                        tipo_g = "Terapia de Grupo"
                        if "Aquí y Ahora" in req_texto:
                            tipo_g = "Aquí y Ahora"
                        elif "Feedback" in req_texto:
                            tipo_g = "Feedback"
                        
                        cnt_g = contar_grupos_paciente_etapa(p_id, p_etapa, tipo_g)
                        
                        # Determinar meta requerida
                        meta_g = 2
                        if "4" in req_texto:
                            meta_g = 4
                        elif "15" in req_texto:
                            meta_g = 15
                        
                        es_cumplido = (cnt_g >= meta_g)
                        if es_cumplido:
                            items_completados += 1
                            st.success(f"✅ **{req_texto}**: Completado ({cnt_g} / {meta_g} sesiones registradas en sistema)")
                        else:
                            st.error(f"❌ **{req_texto}**: PENDIENTE ({cnt_g} / {meta_g} sesiones registradas) ➔ *Faltan {meta_g - cnt_g} grupos*")
                        chk_states[req_id] = es_cumplido
                    else:
                        c_val = st.checkbox(f"📌 {req_texto}", key=f"chk_{p_id}_{req_id}")
                        if c_val:
                            items_completados += 1
                        chk_states[req_id] = c_val
                
                st.divider()
                pct_checklist = (items_completados / items_totales * 100) if items_totales > 0 else 100
                st.markdown(f"**Porcentaje de Requisitos Cumplidos**: `{items_completados} / {items_totales}` (**{pct_checklist:.0f}%**)")
                
                etapas_orden = ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL']
                idx_curr = etapas_orden.index(p_etapa) if p_etapa in etapas_orden else 0
                siguiente_etapa = etapas_orden[idx_curr + 1] if idx_curr + 1 < len(etapas_orden) else None
                
                puedes_promover = (items_completados == items_totales) and (siguiente_etapa is not None) and puede_escribir()
                
                if siguiente_etapa is None:
                    st.info("🎉 El paciente se encuentra en la etapa final (**SERVICIO SOCIAL**).")
                    btn_promover = st.form_submit_button("🏁 Proceso de Etapas Completado", disabled=True)
                else:
                    btn_promover = st.form_submit_button(f"🚀 Promover a Siguiente Etapa: {siguiente_etapa}", disabled=not puedes_promover, use_container_width=True)
                    if not puedes_promover:
                        st.caption("🔒 *El botón de promoción se habilitará únicamente cuando todos los requisitos del checklist estén marcados al 100%.*")
                    
                    if btn_promover:
                        promover_paciente_etapa(p_id, p_etapa, siguiente_etapa, st.session_state["username"])
                        st.success(f"🎉 ¡El paciente **{p_nom}** ha sido promovido exitosamente a la etapa **{siguiente_etapa}**!")
                        st.toast(f"¡Promoción registrada para {p_nom}!", icon="🎉")
                        st.balloons()
                        st.rerun()

        # --- TAB 2: HERMANO MENOR & MAYOR ---
        with tab_hermano:
            st.subheader("🤝 Asignación y Control de Hermano Menor / Mayor")
            st.caption("Durante los primeros 15 días en ACOGIDA, el residente ingresa como Hermano Menor y se le asigna un Hermano Mayor.")
            
            p_hermanos = [p for p in solo_pacientes if p[7] == 'ACOGIDA']
            if not p_hermanos:
                st.info("No hay residentes actualmente en la etapa de **ACOGIDA**.")
            else:
                for ph in p_hermanos:
                    ph_id, ph_nom, ph_fing = ph[0], ph[1], ph[2]
                    ph_hmayor, ph_fsuelta = ph[9], ph[10]
                    
                    dt_fing = datetime.strptime(ph_fing, "%Y-%m-%d").date() if ph_fing else hoy
                    dt_suelta_prog = dt_fing + timedelta(days=15)
                    dias_acogida = (hoy - dt_fing).days
                    
                    with st.expander(f"👤 **{ph_nom}** ({ph_id}) - {dias_acogida} días en Acogida"):
                        st.write(f"- **Fecha de Ingreso**: {ph_fing}")
                        st.write(f"- **Fecha Programada de Suelta de Hermano Mayor**: {dt_suelta_prog.strftime('%Y-%m-%d')} (A los 15 días)")
                        
                        if ph_fsuelta:
                            st.success(f"✅ **Hermano Mayor Soltado el**: {ph_fsuelta}")
                        else:
                            if dias_acogida >= 15:
                                st.warning("⚠️ El residente ya cumplió sus 15 días de acompañamiento. Ya puede ser soltado.")
                            else:
                                st.info(f"⏳ Le faltan {15 - dias_acogida} días para cumplir el periodo de Hermano Menor.")
                            
                            posibles_mayores = [f"{pm[0]} - {pm[1]} ({pm[7]})" for pm in pacs if pm[0] != ph_id]
                            sel_hmayor = st.selectbox("Asignar Hermano Mayor", posibles_mayores, key=f"sel_hm_{ph_id}")
                            
                            col_h1, col_h2 = st.columns(2)
                            with col_h1:
                                if st.button("💾 Asignar Hermano Mayor", key=f"btn_hm_{ph_id}"):
                                    hm_id = sel_hmayor.split(" - ")[0]
                                    asignar_hermano_mayor(ph_id, hm_id)
                                    st.success("✅ Hermano Mayor asignado.")
                                    st.toast("Hermano Mayor asignado.", icon="✅")
                                    st.rerun()
                            with col_h2:
                                if st.button("🔓 Marcar que Hermano Mayor lo Suelta", key=f"btn_suelta_{ph_id}"):
                                    registrar_suelta_hermano(ph_id)
                                    st.success("✅ Suelta registrada.")
                                    st.toast("Suelta de Hermano Mayor registrada.", icon="🔓")
                                    st.rerun()

        # --- TAB 3: HISTORIAL DE CAMBIOS DE ETAPA ---
        with tab_historial:
            st.subheader("📜 Historial Registro de Cambios de Etapa")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT h.id, p.nombre_completo, h.etapa_origen, h.etapa_destino, h.fecha_cambio, h.usuario_autoriza
                FROM historial_etapas h
                JOIN pacientes p ON h.paciente_id = p.paciente_id
                ORDER BY h.id DESC
            """)
            h_rows = c.fetchall()
            conn.close()
            
            if not h_rows:
                st.info("No se han registrado promociones de etapa aún en el sistema.")
            else:
                st.dataframe(
                    [{"ID": r[0], "Paciente": r[1], "Origen": r[2], "Destino": r[3], "Fecha Cambio": r[4], "Autorizó": r[5]} for r in h_rows],
                    use_container_width=True
                )

# ==============================================================================
# MÓDULO 2: 👤 REGISTRO Y EDICIÓN DE USUARIOS
# ==============================================================================
elif menu == "👤 Registro y Edición de Usuarios":
    st.title("👤 Registro y Edición de Usuarios")
    st.markdown("Gestión de expedientes de Pacientes/Residentes y Servidores/Staff de la comunidad.")
    
    modo = st.radio("Modo de Operación", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
    
    pacs_all = listar_todos_pacientes()
    
    if modo == "✏️ Modificar / Editar Usuario Existente" and not pacs_all:
        st.warning("No hay usuarios registrados en el sistema para editar.")
    else:
        edit_data = None
        if modo == "✏️ Modificar / Editar Usuario Existente":
            opcs_edit = [f"{p[0]} - {p[1]} ({p[6]})" for p in pacs_all]
            sel_u_edit = st.selectbox("🔑 Selecciona el Usuario a Editar", opcs_edit)
            edit_pid = sel_u_edit.split(" - ")[0]
            edit_data = obtener_paciente(edit_pid)
        
        # Clave dinámica para refrescar el formulario al cambiar de usuario
        form_key = f"user_form_{edit_data[0]}" if edit_data else "user_form_new"
        
        with st.form(form_key):
            st.subheader("📋 Datos del Usuario")
            
            if edit_data:
                u_id, u_nom, u_fing, u_fnac, u_sex, u_est, u_tipo, u_etapa, u_fini_etapa, _, _ = edit_data
                val_id = u_id
                val_nom = u_nom
                val_tipo = u_tipo
                val_sex = u_sex
                val_est = u_est
                val_etapa = u_etapa
                try:
                    val_fing = datetime.strptime(u_fing, "%Y-%m-%d").date()
                except Exception:
                    val_fing = date.today()
                try:
                    val_fnac = datetime.strptime(u_fnac, "%Y-%m-%d").date()
                except Exception:
                    val_fnac = date(1990, 1, 1)
                try:
                    val_fini_etapa = datetime.strptime(u_fini_etapa, "%Y-%m-%d").date() if u_fini_etapa else val_fing
                except Exception:
                    val_fini_etapa = val_fing
            else:
                val_id = obtener_siguiente_folio()
                val_nom = ""
                val_tipo = "Paciente"
                val_sex = "Masculino"
                val_est = "A"
                val_etapa = "ACOGIDA"
                val_fing = date.today()
                val_fnac = date(1995, 1, 1)
                val_fini_etapa = date.today()
            
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Folio / ID", value=val_id, disabled=True)
                reg_nom = st.text_input("Nombre Completo", value=val_nom)
                reg_tipo = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if val_tipo == "Paciente" else 1)
                reg_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=["Masculino", "Femenino", "Otro"].index(val_sex) if val_sex in ["Masculino", "Femenino", "Otro"] else 0)
            
            with col2:
                reg_fing = st.date_input("Fecha de Ingreso Real a la Comunidad", value=val_fing, min_value=date(2000, 1, 1))
                reg_etapa = st.selectbox("Etapa Actual", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"], index=["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"].index(val_etapa) if val_etapa in ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"] else 0)
                reg_fini_etapa = st.date_input("Fecha de Inicio de la Etapa Actual", value=val_fini_etapa, min_value=date(2000, 1, 1), help="Si el residente ya estaba internado en esta etapa, selecciona la fecha aproximada en que inició su etapa actual.")
                reg_fnac = st.date_input("Fecha de Nacimiento", value=val_fnac, min_value=date(1920, 1, 1))
                reg_estatus = st.selectbox("Estatus", ["A - Activo", "B - Inactivo / Bloqueado"], index=0 if val_est == "A" else 1)

            st.divider()
            btn_guardar_u = st.form_submit_button("💾 Guardar Usuario", use_container_width=True, disabled=not puede_escribir())
            
            if btn_guardar_u:
                if not reg_nom.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                else:
                    est_code = "A" if "A" in reg_estatus else "B"
                    dup = verificar_duplicado_nombre(reg_nom, paciente_id_actual=val_id if edit_data else None)
                    if dup and modo == "🆕 Registrar Nuevo Usuario":
                        st.error(f"❌ Ya existe un usuario con el nombre '**{dup[1]}**' registrado bajo el Folio **{dup[0]}**.")
                    else:
                        guardar_usuario_paciente(
                            val_id, reg_nom, reg_fing, reg_fnac, reg_sexo, est_code, reg_tipo, reg_etapa, reg_fini_etapa, st.session_state["username"]
                        )
                        st.success(f"🎉 ¡Usuario **{reg_nom}** ({val_id}) guardado correctamente en la base de datos!")
                        st.toast("Usuario guardado correctamente.", icon="🎉")
                        st.balloons()
                        st.rerun()

# ==============================================================================
# MÓDULO 3: 🗣️ GRUPOS TERAPÉUTICOS
# ==============================================================================
elif menu == "🗣️ Grupos Terapéuticos":
    st.title("🗣️ Registro de Grupos Terapéuticos")
    st.markdown("Captura de sesiones de Terapia de Grupo, Aquí y Ahora, y Feedback.")
    
    pacs_g = [p for p in listar_todos_pacientes() if p[5] == 'A' and p[6] == 'Paciente']
    
    if not pacs_g:
        st.warning("No hay pacientes activos registrados en el sistema.")
    else:
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        with tab_reg_g:
            opcs_g = [f"{p[0]} - {p[1]} (Etapa: {p[7]})" for p in pacs_g]
            sel_pac_g = st.selectbox("🔑 Selecciona el Paciente", opcs_g)
            pid_g = sel_pac_g.split(" - ")[0]
            p_obj = obtener_paciente(pid_g)
            
            tipo_g = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
            
            with st.form("form_grupo_terapeutico"):
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.text_input("Folio del Paciente", value=p_obj[0], disabled=True)
                    st.text_input("Nombre del Paciente", value=p_obj[1], disabled=True)
                    st.text_input("Etapa al Momento", value=p_obj[7], disabled=True)
                with col_g2:
                    f_grupo = st.date_input("Fecha del Grupo", value=date.today())
                    facilitador = st.text_input("Nombre del Facilitador / Staff")
                
                st.divider()
                datos_dict = {}
                if tipo_g in ["Terapia de Grupo", "Aquí y Ahora"]:
                    datos_dict["Compartimiento"] = st.text_area("Compartimiento (Texto largo)")
                    datos_dict["Observaciones"] = st.text_area("Observaciones")
                    datos_dict["Devoluciones"] = st.text_area("Devoluciones")
                    datos_dict["Como_se_queda"] = st.text_area("¿Cómo se queda y a qué se compromete?")
                else: # Feedback
                    datos_dict["Logros"] = st.text_area("Logros (Texto largo)")
                    datos_dict["Dificultades"] = st.text_area("Dificultades (Texto largo)")
                    datos_dict["Observaciones"] = st.text_area("Observaciones")
                    datos_dict["Devoluciones"] = st.text_area("Devoluciones")
                    datos_dict["Como_se_queda"] = st.text_area("¿Cómo se queda y a qué se compromete?")
                
                btn_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True, disabled=not puede_escribir())
                if btn_g:
                    if not facilitador.strip():
                        st.error("⚠️ Debe ingresar el nombre del facilitador.")
                    else:
                        guardar_grupo_terapeutico(
                            p_obj[0], tipo_g, p_obj[7], f_grupo.strftime("%Y-%m-%d"), facilitador, datos_dict, st.session_state["username"]
                        )
                        st.success(f"🎉 ¡Sesión de **{tipo_g}** registrada exitosamente para **{p_obj[1]}**!")
                        st.toast("Sesión de grupo guardada.", icon="🎉")
                        st.balloons()
                        st.rerun()

        with tab_hist_g:
            opcs_gh = [f"{p[0]} - {p[1]}" for p in pacs_g]
            sel_gh = st.selectbox("🔑 Selecciona el Paciente para Ver Historial", opcs_gh)
            pid_gh = sel_gh.split(" - ")[0]
            
            p_gh_obj = obtener_paciente(pid_gh)
            list_g = listar_grupos_paciente(pid_gh)
            
            if not list_g:
                st.info(f"No hay sesiones de grupo registradas para {p_gh_obj[1]}.")
            else:
                st.markdown(f"#### Total de sesiones registradas: `{len(list_g)}`")
                for r in list_g:
                    # r: (id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro)
                    with st.expander(f"🗣️ **{r[1]}** | Fecha: {r[3]} | Etapa: {r[2]} | Facilitador: {r[4]}"):
                        d_j = json.loads(r[5])
                        for k, v in d_j.items():
                            st.write(f"**{k.replace('_', ' ')}**: {v}")

# ==============================================================================
# MÓDULO 4: 📝 ENTREVISTA INICIAL DE CONSEJERÍA
# ==============================================================================
elif menu == "📝 Entrevista Inicial de Consejería":
    st.title("📝 Entrevista Inicial de Consejería")
    pacs_ent = [p for p in listar_todos_pacientes() if p[6] == 'Paciente']
    
    if not pacs_ent:
        st.warning("No hay pacientes registrados.")
    else:
        opcs_e = [f"{p[0]} - {p[1]}" for p in pacs_ent]
        sel_e = st.selectbox("🔑 Selecciona el Paciente", opcs_e)
        pid_e = sel_e.split(" - ")[0]
        
        # Cargar entrevista si existe
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (pid_e,))
        e_row = c.fetchone()
        conn.close()
        
        datos_e = json.loads(e_row[0]) if e_row and e_row[0] else {}
        
        with st.form("form_entrevista_inicial"):
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "1. Demografía", "2. Consumo Sustancias", "3. Disposición al Cambio", "4. Entorno / Riesgo", "5. Observaciones"
            ])
            
            with tab1:
                e_empleo = st.text_input("Ocupación / Empleo", value=datos_e.get("empleo", ""))
                e_vivienda = st.text_input("Situación de Vivienda", value=datos_e.get("vivienda", ""))
                e_financiero = st.text_input("Responsabilidades Financieras", value=datos_e.get("financiero", ""))
            
            with tab2:
                e_sustancias = st.text_area("Sustancias de Consumo (Frecuencia, cantidad, detonantes)", value=datos_e.get("sustancias", ""))
                e_sintomas = st.text_area("Síntomas de Abstinencia / Pérdida de Control", value=datos_e.get("sintomas", ""))
            
            with tab3:
                e_motivacion = st.text_area("Motivación para el Cambio / Periodos de Sobriedad Previo", value=datos_e.get("motivacion", ""))
            
            with tab4:
                e_familia = st.text_area("Dinámica Familiar y Entorno Social", value=datos_e.get("familia", ""))
            
            with tab5:
                e_obs = st.text_area("Observaciones del Consejero / Plan Clínico Inicial", value=datos_e.get("observaciones", ""))
            
            btn_guardar_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True, disabled=not puede_escribir())
            
            if btn_guardar_ent:
                d_save = {
                    "empleo": e_empleo, "vivienda": e_vivienda, "financiero": e_financiero,
                    "sustancias": e_sustancias, "sintomas": e_sintomas, "motivacion": e_motivacion,
                    "familia": e_familia, "observaciones": e_obs
                }
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (pid_e,))
                if c.fetchone():
                    c.execute('UPDATE entrevistas SET datos_json = ?, fecha_modificacion = ? WHERE paciente_id = ?',
                              (json.dumps(d_save, ensure_ascii=False), f_act, pid_e))
                else:
                    c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                              (pid_e, f_act, f_act, st.session_state["username"], json.dumps(d_save, ensure_ascii=False)))
                conn.commit()
                conn.close()
                st.success("🎉 ¡Entrevista guardada correctamente!")
                st.toast("Entrevista guardada.", icon="🎉")

# ==============================================================================
# MÓDULO 5: 💊 CONTROL DE MEDICAMENTOS & DOSIS (CON CATÁLOGO Y REPORTES)
# ==============================================================================
elif menu == "💊 Control de Medicamentos & Dosis":
    st.title("💊 Control de Medicamentos & Dosis")
    
    tab_dosis, tab_cat, tab_rep = st.tabs(["💊 Asignación de Dosis", "📚 Catálogo Central", "📊 Reporte Global por Medicamento"])
    
    # --- TAB DOSIS ---
    with tab_dosis:
        pacs_m = [p for p in listar_todos_pacientes() if p[5] == 'A' and p[6] == 'Paciente']
        if not pacs_m:
            st.warning("No hay pacientes activos registrados.")
        else:
            opcs_m = [f"{p[0]} - {p[1]}" for p in pacs_m]
            sel_m = st.selectbox("🔑 Selecciona el Paciente", opcs_m, key="sel_med_p")
            pid_m = sel_m.split(" - ")[0]
            
            meds_curr, obs_curr = obtener_medicamentos_paciente(pid_m)
            cat_list = listar_catalogo_medicamentos()
            nombres_cat = [f"{r[1]} ({r[2]} - {r[3]})" for r in cat_list]
            
            st.subheader(f"Esquema de Medicación para {sel_m}")
            
            with st.form("form_meds_paciente"):
                m_count = st.number_input("Número de Medicamentos asignados", min_value=1, max_value=10, value=max(1, len(meds_curr)))
                meds_new = []
                
                for i in range(int(m_count)):
                    st.markdown(f"**Medicamento #{i+1}**")
                    c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 2])
                    
                    m_prev = meds_curr[i] if i < len(meds_curr) else {}
                    
                    with c1:
                        if nombres_cat:
                            nom_m = st.selectbox(f"Medicamento #{i+1}", nombres_cat, key=f"cat_m_{i}")
                        else:
                            nom_m = st.text_input(f"Nombre Medicamento #{i+1}", value=m_prev.get("nombre", ""), key=f"txt_m_{i}")
                    with c2:
                        d_m = st.number_input("Mañana", min_value=0, value=int(m_prev.get("manana", 0)), key=f"m_{i}")
                    with c3:
                        d_t = st.number_input("Tarde", min_value=0, value=int(m_prev.get("tarde", 0)), key=f"t_{i}")
                    with c4:
                        d_n = st.number_input("Noche", min_value=0, value=int(m_prev.get("noche", 0)), key=f"n_{i}")
                    with c5:
                        ex_m = st.number_input("Existencia Stock", min_value=0, value=int(m_prev.get("existencia", 0)), key=f"ex_{i}")
                    
                    meds_new.append({
                        "nombre": nom_m, "manana": d_m, "tarde": d_t, "noche": d_n, "existencia": ex_m
                    })
                
                obs_med = st.text_area("Observaciones Médicas", value=obs_curr)
                btn_m_save = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True, disabled=not puede_escribir())
                
                if btn_m_save:
                    guardar_medicamentos_paciente(pid_m, meds_new, obs_med, st.session_state["username"])
                    st.success("🎉 ¡Esquema de medicamentos guardado correctamente!")
                    st.toast("Esquema de medicamentos guardado.", icon="🎉")

    # --- TAB CATÁLOGO CENTRAL ---
    with tab_cat:
        st.subheader("📚 Catálogo Central de Medicamentos")
        c_list = listar_catalogo_medicamentos()
        st.dataframe([{"ID": r[0], "Nombre": r[1], "Presentación": r[2], "Concentración": r[3], "Observaciones": r[4]} for r in c_list], use_container_width=True)
        
        with st.expander("➕ Agregar Nuevo Medicamento al Catálogo"):
            with st.form("form_add_cat"):
                c_nom = st.text_input("Nombre del Medicamento")
                c_pres = st.text_input("Presentación (ej. Comprimidos, Gotas, Cápsulas)")
                c_conc = st.text_input("Concentración (ej. 500 mg, 20 mg)")
                c_obs = st.text_input("Observaciones / Categoría")
                if st.form_submit_button("Guardar en Catálogo") and puede_escribir():
                    if c_nom.strip():
                        res = agregar_catalogo_medicamento(c_nom, c_pres, c_conc, c_obs)
                        if res:
                            st.success("✅ Guardado en catálogo.")
                            st.rerun()
                        else:
                            st.error("❌ El medicamento ya existe en el catálogo.")

    # --- TAB REPORTE GLOBAL ---
    with tab_rep:
        st.subheader("📊 Reporte de Consumo Global por Medicamento")
        cat_all = listar_catalogo_medicamentos()
        if cat_all:
            sel_med_rep = st.selectbox("Selecciona Medicamento a Consultar", [f"{r[1]} ({r[2]} - {r[3]})" for r in cat_all])
            
            # Buscar consumo across all patients
            pacs_active = [p for p in listar_todos_pacientes() if p[5] == 'A']
            pac_con_med = []
            consumo_total_diario = 0
            stock_total_almacen = 0
            
            for pa in pacs_active:
                m_list, _ = obtener_medicamentos_paciente(pa[0])
                for m_item in m_list:
                    if sel_med_rep in m_item.get("nombre", "") or m_item.get("nombre", "") in sel_med_rep:
                        tot_diario = m_item.get("manana", 0) + m_item.get("tarde", 0) + m_item.get("noche", 0)
                        ex = m_item.get("existencia", 0)
                        consumo_total_diario += tot_diario
                        stock_total_almacen += ex
                        pac_con_med.append({
                            "Folio": pa[0], "Paciente": pa[1], "Etapa": pa[7],
                            "Dosis Mañana": m_item.get("manana", 0),
                            "Dosis Tarde": m_item.get("tarde", 0),
                            "Dosis Noche": m_item.get("noche", 0),
                            "Consumo Diario": tot_diario,
                            "Stock Actual": ex
                        })
            
            col_r1, col_r2 = st.columns(2)
            col_r1.metric("💊 Consumo Diario Total en Clínica", f"{consumo_total_diario} unidades/día")
            col_r2.metric("📦 Stock Total en Almacén", f"{stock_total_almacen} unidades")
            
            if pac_con_med:
                st.dataframe(pac_con_med, use_container_width=True)
            else:
                st.info("Ningún residente tiene asignado este medicamento actualmente.")

# ==============================================================================
# MÓDULO 6: 🚚 ENTREGA DE MEDICAMENTOS
# ==============================================================================
elif menu == "🚚 Entrega de Medicamentos":
    st.title("🚚 Entrega Diaria de Medicamentos")
    pacs_ent_m = [p for p in listar_todos_pacientes() if p[5] == 'A' and p[6] == 'Paciente']
    
    if not pacs_ent_m:
        st.warning("No hay pacientes activos registrados.")
    else:
        opcs_em = [f"{p[0]} - {p[1]}" for p in pacs_ent_m]
        sel_em = st.selectbox("🔑 Selecciona el Paciente para Entrega", opcs_em)
        pid_em = sel_em.split(" - ")[0]
        
        meds_ent, obs_ent = obtener_medicamentos_paciente(pid_em)
        
        if not meds_ent:
            st.info("Este paciente no tiene esquema de medicamentos asignado.")
        else:
            with st.form("form_entrega_diaria"):
                st.markdown(f"##### Registrando Entrega de Medicamentos para `{sel_em}`")
                f_entrega = st.date_input("Fecha de Entrega", value=date.today())
                
                entregas_confirmadas = []
                for idx, mi in enumerate(meds_ent):
                    st.write(f"💊 **{mi['nombre']}** | Stock Actual: `{mi['existencia']}`")
                    tot_dosis = mi['manana'] + mi['tarde'] + mi['noche']
                    cant_ent = st.number_input(f"Cantidad a entregar de {mi['nombre']}", min_value=0, max_value=mi['existencia'], value=tot_dosis, key=f"ent_{idx}")
                    entregas_confirmadas.append({"index": idx, "nombre": mi['nombre'], "cantidad": cant_ent})
                
                btn_do_entrega = st.form_submit_button("🚚 Confirmar y Descontar de Inventario", use_container_width=True, disabled=not puede_escribir())
                
                if btn_do_entrega:
                    # Descontar stock
                    for item in entregas_confirmadas:
                        meds_ent[item['index']]['existencia'] -= item['cantidad']
                    
                    guardar_medicamentos_paciente(pid_em, meds_ent, obs_ent, st.session_state["username"])
                    
                    # Guardar registro entrega
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
                              (pid_em, f_now, st.session_state["username"], json.dumps(entregas_confirmadas, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    
                    st.success("🎉 ¡Entrega realizada y descontada del inventario correctamente!")
                    st.toast("Entrega confirmada.", icon="🚚")
                    st.rerun()

# ==============================================================================
# MÓDULO 7: 📦 RESPALDO Y RESTAURACIÓN DE BASE DE DATOS
# ==============================================================================
elif menu == "📦 Respaldo y Restauración":
    st.title("📦 Respaldo y Restauración de Base de Datos")
    st.markdown("Guarda una copia segura de tu información para evitar pérdidas ante reinicios del servidor.")
    
    tab_down, tab_up = st.tabs(["📥 Descargar Respaldo (.db)", "📤 Restaurar Base de Datos"])
    
    with tab_down:
        st.subheader("📥 Descargar Copia de Seguridad")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                bytes_db = f.read()
            
            fname = f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%m_%H%M%S')}.db"
            st.download_button(
                label="📥 Descargar Archivo de Respaldo (.db)",
                data=bytes_db,
                file_name=fname,
                mime="application/x-sqlite3",
                use_container_width=True
            )
            st.info("💡 **Recomendación**: Descarga una copia al finalizar tu jornada para respaldar tus registros.")
        else:
            st.error("No se encontró la base de datos.")

    with tab_up:
        st.subheader("📤 Cargar y Restaurar Respaldo")
        st.warning("⚠️ **ATENCIÓN**: Restaurar un respaldo reemplazará la base de datos actual con la información del archivo cargado.")
        
        uploaded_db = st.file_uploader("Selecciona el archivo de respaldo (.db)", type=["db", "sqlite"])
        if uploaded_db and puede_escribir():
            if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                with open(DB_FILE, "wb") as f:
                    f.write(uploaded_db.getbuffer())
                st.success("🎉 ¡Base de datos restaurada exitosamente!")
                st.toast("Base de datos restaurada.", icon="🎉")
                st.rerun()

# ==============================================================================
# MÓDULO 8: 📁 REPOSITORIO DE DOCUMENTOS (SOLO ADMIN)
# ==============================================================================
elif menu == "📁 Repositorio de Documentos":
    st.title("📁 Repositorio de Documentos y Formatos")
    st.markdown("Almacén de manuales, formatos de admisión, reglamentos y plantillas clínicas.")
    
    carpetas_def = [
        "📋 Formatos Clínicos y Administrativos",
        "📖 Manuales de Operación",
        "⚖️ Reglamentos y Normativas",
        "📑 Plantillas de Evaluación",
        "📁 Documentos Generales"
    ]
    
    tab_rep_ver, tab_rep_up = st.tabs(["📂 Explorar y Descargar Archivos", "📤 Subir Nuevo Archivo"])
    
    with tab_rep_ver:
        c_filtro = st.selectbox("Filtrar por Carpeta", ["Todas las Carpetas"] + carpetas_def)
        docs = obtener_documentos_repositorio(c_filtro)
        
        if not docs:
            st.info("No hay documentos subidos en esta carpeta.")
        else:
            for doc in docs:
                # doc: (id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                with st.expander(f"📄 **{doc[2]}** | Carpeta: `{doc[1]}` | Subido: {doc[6]}"):
                    st.write(f"**Descripción / Notas**: {doc[5]}")
                    st.write(f"**Subido por**: {doc[7]}")
                    
                    c_d1, c_d2 = st.columns(2)
                    with c_d1:
                        st.download_button(
                            label=f"📥 Descargar {doc[2]}",
                            data=doc[4],
                            file_name=doc[2],
                            mime=doc[3],
                            key=f"down_doc_{doc[0]}"
                        )
                    with c_d2:
                        if es_admin():
                            if st.button("🗑️ Eliminar Archivo", key=f"del_doc_{doc[0]}"):
                                eliminar_documento_repositorio(doc[0])
                                st.success("Archivo eliminado.")
                                st.rerun()

    with tab_rep_up:
        with st.form("form_subir_doc"):
            st.subheader("Subir Documento a la Nube")
            up_carpeta = st.selectbox("Carpeta Destino", carpetas_def)
            up_file = st.file_uploader("Selecciona el Archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "png", "jpg", "txt"])
            up_desc = st.text_input("Descripción o Notas del Archivo")
            
            if st.form_submit_button("📤 Subir Documento al Repositorio") and es_admin():
                if up_file:
                    bytes_f = up_file.getbuffer().tobytes()
                    guardar_documento_repositorio(
                        up_carpeta, up_file.name, up_file.type, bytes_f, up_desc, st.session_state["username"]
                    )
                    st.success(f"🎉 ¡Archivo **{up_file.name}** subido al repositorio!")
                    st.toast("Documento guardado.", icon="🎉")
                    st.rerun()
                else:
                    st.error("⚠️ Debes seleccionar un archivo para subir.")

# ==============================================================================
# MÓDULO 9: ⚙️ CONFIGURACIÓN & SEGURIDAD (SOLO ADMIN)
# ==============================================================================
elif menu == "⚙️ Configuración & Seguridad":
    st.title("⚙️ Configuración & Seguridad del Sistema")
    
    tab_roles, tab_pass, tab_reqs = st.tabs(["👥 Gestión de Usuarios y Roles", "🔑 Cambiar Mi Contraseña", "⚙️ Requisitos por Etapa"])
    
    with tab_roles:
        st.subheader("👥 Gestión de Cuentas de Acceso al Sistema")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, username, nombre_completo, rol FROM usuarios')
        users_list = c.fetchall()
        conn.close()
        
        st.dataframe([{"ID": u[0], "Usuario": u[1], "Nombre": u[2], "Rol / Nivel": u[3]} for u in users_list], use_container_width=True)
        
        with st.expander("➕ Crear Nueva Cuenta para Personal / Staff"):
            with st.form("form_create_user_account"):
                nu_user = st.text_input("Nombre de Usuario (Login)")
                nu_name = st.text_input("Nombre Completo del Personal")
                nu_pass = st.text_input("Contraseña Inicial", type="password")
                nu_rol = st.selectbox("Nivel de Acceso / Rol", [
                    "Nivel 1 - Administrador",
                    "Nivel 2 - Lectura y Escritura",
                    "Nivel 3 - Solo Lectura"
                ])
                if st.form_submit_button("Crear Cuenta"):
                    if nu_user.strip() and nu_pass.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                      (nu_user.strip(), hash_pass(nu_pass), nu_name.strip(), nu_rol))
                            conn.commit()
                            st.success(f"✅ Cuenta **{nu_user}** creada exitosamente.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("❌ El nombre de usuario ya existe.")
                        conn.close()

    with tab_pass:
        st.subheader("🔑 Cambiar Mi Contraseña")
        with st.form("form_change_pass"):
            p_act = st.text_input("Contraseña Actual", type="password")
            p_new = st.text_input("Nueva Contraseña", type="password")
            p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
            if st.form_submit_button("Actualizar Contraseña"):
                res = verificar_login(st.session_state["username"], p_act)
                if not res:
                    st.error("❌ La contraseña actual es incorrecta.")
                elif p_new != p_cnf:
                    st.error("❌ La nueva contraseña y la confirmación no coinciden.")
                elif len(p_new) < 4:
                    st.error("❌ La contraseña debe tener al menos 4 caracteres.")
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                              (hash_pass(p_new), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success("✅ Contraseña actualizada exitosamente.")

    with tab_reqs:
        st.subheader("⚙️ Configuración Dinámica de Requisitos por Etapa")
        sel_e_conf = st.selectbox("Selecciona Etapa a Configurar", ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL'])
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ?', (sel_e_conf,))
        reqs_curr = c.fetchall()
        conn.close()
        
        for rq in reqs_curr:
            c_r1, c_r2 = st.columns([4, 1])
            c_r1.write(f"📌 {rq[1]} {'(Grupo contabilizado automáticamente)' if rq[2] else ''}")
            if c_r2.button("🗑️ Eliminar", key=f"del_req_{rq[0]}"):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (rq[0],))
                conn.commit()
                conn.close()
                st.rerun()
        
        with st.form(f"form_add_req_{sel_e_conf}"):
            st.markdown("##### ➕ Agregar Nuevo Requisito a esta Etapa")
            n_req_txt = st.text_input("Texto del Requisito")
            n_req_grupo = st.checkbox("¿Es un conteo automático de grupo?")
            if st.form_submit_button("Agregar Requisito"):
                if n_req_txt.strip():
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)',
                              (sel_e_conf, n_req_txt.strip(), 1 if n_req_grupo else 0))
                    conn.commit()
                    conn.close()
                    st.success("Requisito agregado.")
                    st.rerun()

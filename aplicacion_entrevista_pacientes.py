import streamlit as st
import sqlite3
import json
import hashlib
import os
import shutil
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Comunidad Terapéutica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Staff (Login y Roles)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    """)
    
    # Asegurar usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))

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
    
    # Migraciones para la tabla de pacientes
    c.execute("PRAGMA table_info(pacientes)")
    cols_pacientes = [col[1] for col in c.fetchall()]
    m_pacientes = {
        "tipo_usuario": "TEXT DEFAULT 'Paciente'",
        "etapa_actual": "TEXT DEFAULT 'ACOGIDA'",
        "fecha_inicio_etapa": "TEXT",
        "hermano_mayor_id": "TEXT",
        "fecha_suelta_hermano": "TEXT"
    }
    for col_name, col_def in m_pacientes.items():
        if col_name not in cols_pacientes:
            try:
                c.execute(f"ALTER TABLE pacientes ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

    # 3. Tabla de Entrevistas Iniciales
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)

    # 4. Tabla de Medicamentos e Inventario por Paciente
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

    # 5. Tabla de Historial de Entregas de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    """)

    # 6. Tabla de Catálogo Central de Tipos de Grupo
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_tipos_grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1,
            es_confronto INTEGER DEFAULT 0,
            campos_json TEXT
        )
    """)

    # Poblar Tipos de Grupo Base si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_tipos_grupos')
    if c.fetchone()[0] == 0:
        grupos_base = [
            ("Terapia de Grupo", "Sesión de terapia grupal regular o en confronto", 1, 1, json.dumps(["Compartimiento", "Observaciones", "Devoluciones", "Como se queda", "Compromiso", "Facilitador"])),
            ("Aquí y Ahora", "Sesión de expresión emocional del momento presente", 1, 1, json.dumps(["Compartimiento", "Observaciones", "Devoluciones", "Como se queda", "Compromiso", "Facilitador"])),
            ("Feedback", "Sesión de retroalimentación de fortalezas y dificultades", 1, 0, json.dumps(["Dificultades", "Fortalezas", "Devoluciones", "Como se queda", "Compromiso", "Facilitador"])),
            ("Confronto Especial", "Sesión de confrontación terapéutica especial", 1, 1, json.dumps(["Situación", "Observaciones", "Devoluciones", "Como se queda", "Compromiso", "Facilitador"]))
        ]
        c.executemany('INSERT INTO catalogo_tipos_grupos (nombre, descripcion, activo, es_confronto, campos_json) VALUES (?, ?, ?, ?, ?)', grupos_base)

    # 7. Tabla de Registro de Grupos Terapéuticos
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeutos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            etapa_al_momento TEXT,
            modalidad TEXT DEFAULT 'Normal',
            fecha_grupo TEXT,
            facilitador TEXT,
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    """)

    # Migración de columna 'modalidad' en grupos_terapeutos
    c.execute("PRAGMA table_info(grupos_terapeutos)")
    cols_gt = [col[1] for col in c.fetchall()]
    if "modalidad" not in cols_gt:
        try:
            c.execute("ALTER TABLE grupos_terapeutos ADD COLUMN modalidad TEXT DEFAULT 'Normal'")
        except Exception:
            pass

    # 8. Tabla de Configuración de Tiempos Objetivo por Etapa
    c.execute("""
        CREATE TABLE IF NOT EXISTS config_etapas (
            etapa TEXT PRIMARY KEY,
            dias_objetivo INTEGER NOT NULL,
            orden INTEGER NOT NULL
        )
    """)

    c.execute('SELECT COUNT(*) FROM config_etapas')
    if c.fetchone()[0] == 0:
        etapas_base = [
            ('ACOGIDA', 30, 1),
            ('IDENTIFICACIÓN', 60, 2),
            ('ELABORACIÓN', 60, 3),
            ('CONSOLIDACIÓN', 30, 4),
            ('SERVICIO SOCIAL', 30, 5)
        ]
        c.executemany('INSERT INTO config_etapas (etapa, dias_objetivo, orden) VALUES (?, ?, ?)', etapas_base)

    # 9. Tabla de Requisitos de Etapas
    c.execute("""
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0,
            tipo_grupo_requerido TEXT,
            cantidad_grupo_requerida INTEGER DEFAULT 0
        )
    """)

    # Migración de columnas para grupos requeridos
    c.execute("PRAGMA table_info(requisitos_etapas)")
    cols_req = [col[1] for col in c.fetchall()]
    if "tipo_grupo_requerido" not in cols_req:
        try:
            c.execute("ALTER TABLE requisitos_etapas ADD COLUMN tipo_grupo_requerido TEXT")
            c.execute("ALTER TABLE requisitos_etapas ADD COLUMN cantidad_grupo_requerida INTEGER DEFAULT 0")
        except Exception:
            pass

    # Poblar / Actualizar Requisitos de Etapas Actualizados
    c.execute('SELECT COUNT(*) FROM requisitos_etapas')
    if c.fetchone()[0] == 0:
        reqs_nuevos = [
            # 1. Acogida (30 días)
            ('ACOGIDA', 'Compromiso Existencial', 0, None, 0),
            ('ACOGIDA', '2 Señalamientos Asertivos', 0, None, 0),
            ('ACOGIDA', '5 Reglas de Usuario', 0, None, 0),
            ('ACOGIDA', '5 Reglas de convivencia', 0, None, 0),
            
            # 2. Identificación (60 días)
            ('IDENTIFICACIÓN', 'Oración de la mañana', 0, None, 0),
            ('IDENTIFICACIÓN', '5 Factores de riesgo internos', 0, None, 0),
            ('IDENTIFICACIÓN', '5 Factores de riesgo externos', 0, None, 0),
            ('IDENTIFICACIÓN', '5 Factores de protección internos', 0, None, 0),
            ('IDENTIFICACIÓN', '5 Factores de protección externos', 0, None, 0),
            ('IDENTIFICACIÓN', 'Ecomapa', 0, None, 0),
            ('IDENTIFICACIÓN', '10 Reglas de Usuario', 0, None, 0),
            ('IDENTIFICACIÓN', '10 Reglas de convivencia', 0, None, 0),
            ('IDENTIFICACIÓN', '4 grupos de "Aquí y Ahora"', 1, 'Aquí y Ahora', 4),
            ('IDENTIFICACIÓN', '4 grupos de "Terapia de Grupo"', 1, 'Terapia de Grupo', 4),
            ('IDENTIFICACIÓN', '4 grupos de "Feedback"', 1, 'Feedback', 4),
            
            # 3. Elaboración (60 días)
            ('ELABORACIÓN', 'Oración del medio día', 0, None, 0),
            ('ELABORACIÓN', 'Filosofía de la comunidad', 0, None, 0),
            ('ELABORACIÓN', '15 Reglas de Usuario', 0, None, 0),
            ('ELABORACIÓN', '15 Reglas de convivencia', 0, None, 0),
            ('ELABORACIÓN', 'Plan de tratamiento', 0, None, 0),
            ('ELABORACIÓN', '4 grupos de "Aquí y Ahora"', 1, 'Aquí y Ahora', 4),
            ('ELABORACIÓN', '4 grupos de "Terapia de Grupo"', 1, 'Terapia de Grupo', 4),
            ('ELABORACIÓN', '4 grupos de "Feedback"', 1, 'Feedback', 4),
            
            # 4. Consolidación (30 días)
            ('CONSOLIDACIÓN', 'Filosofía del Hoy, Aquí y Mañana', 0, None, 0),
            ('CONSOLIDACIÓN', 'Oración de la Noche', 0, None, 0),
            ('CONSOLIDACIÓN', '20 Reglas de Usuario', 0, None, 0),
            ('CONSOLIDACIÓN', '20 Reglas de convivencia', 0, None, 0),
            ('CONSOLIDACIÓN', 'Proyecto de Vida', 0, None, 0),
            ('CONSOLIDACIÓN', 'Plan de Servicio Social', 0, None, 0),
            ('CONSOLIDACIÓN', '2 grupos de "Aquí y Ahora"', 1, 'Aquí y Ahora', 2),
            ('CONSOLIDACIÓN', '2 grupos de "Terapia de Grupo"', 1, 'Terapia de Grupo', 2),
            ('CONSOLIDACIÓN', '2 grupos de "Feedback"', 1, 'Feedback', 2),
            
            # 5. Servicio Social (30 días)
            ('SERVICIO SOCIAL', 'Lograr la Luz Verde', 0, None, 0)
        ]
        c.executemany('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo, tipo_grupo_requerido, cantidad_grupo_requerida) VALUES (?, ?, ?, ?, ?)', reqs_nuevos)

    # 10. Tabla de Cumplimiento Individual de Requisitos
    c.execute("""
        CREATE TABLE IF NOT EXISTS cumplimiento_requisitos (
            paciente_id TEXT,
            requisito_id INTEGER,
            etapa TEXT,
            cumplido INTEGER DEFAULT 1,
            fecha_cumplido TEXT,
            usuario_registro TEXT,
            PRIMARY KEY (paciente_id, requisito_id)
        )
    """)

    # 11. Tabla de Historial de Etapas
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

    # 12. Tabla de Repositorio de Documentos
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

    # 13. Tabla de Catálogo Central de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            concentracion TEXT,
            presentacion TEXT,
            descripcion TEXT
        )
    """)

    conn.commit()
    conn.close()

# Inicializar Base de Datos al arrancar
init_db()

# --- FUNCIONES DE AUTENTICACIÓN Y SEGURIDAD ---
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
    rol = st.session_state.get("rol", "")
    return "Administrador" in rol or "Nivel 1" in rol

def puede_escribir():
    rol = st.session_state.get("rol", "")
    return "Nivel 3" not in rol

def es_solo_lectura():
    rol = st.session_state.get("rol", "")
    return "Nivel 3" in rol

# --- HELPER DE CÁLCULO DE DÍAS EN ETAPA ---
def calcular_dias_en_etapa(fecha_ingreso_str, fecha_inicio_etapa_str):
    hoy = date.today()
    f_ingreso = None
    f_etapa = None

    if fecha_ingreso_str:
        try:
            f_ingreso = datetime.strptime(str(fecha_ingreso_str).split()[0], "%Y-%m-%d").date()
        except Exception:
            pass

    if fecha_inicio_etapa_str:
        try:
            f_etapa = datetime.strptime(str(fecha_inicio_etapa_str).split()[0], "%Y-%m-%d").date()
        except Exception:
            pass

    # Regla explicada por el usuario:
    # Si la fecha de inicio de etapa es mayor a la fecha de ingreso,
    # se calculan los días a partir de esa fecha de inicio de etapa.
    # De lo contrario (o si es igual/menor), se toma a partir de fecha_inicio_etapa si existe, o fecha_ingreso.
    if f_etapa and f_ingreso and f_etapa > f_ingreso:
        base_date = f_etapa
    elif f_etapa:
        base_date = f_etapa
    elif f_ingreso:
        base_date = f_ingreso
    else:
        base_date = hoy

    dias = (hoy - base_date).days
    return max(0, dias)

def obtener_config_etapas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT etapa, dias_objetivo, orden FROM config_etapas ORDER BY orden ASC')
    rows = c.fetchall()
    conn.close()
    dict_dias = {}
    for etapa, dias, orden in rows:
        dict_dias[etapa] = dias
    return dict_dias

# --- FUNCIONES DE PACIENTES ---
def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', etapa='ACOGIDA', fecha_inicio_etapa=None, usuario='system'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    f_ing_str = fecha_ingreso.strftime("%Y-%m-%d") if isinstance(fecha_ingreso, (date, datetime)) else str(fecha_ingreso)
    f_nac_str = fecha_nacimiento.strftime("%Y-%m-%d") if isinstance(fecha_nacimiento, (date, datetime)) else str(fecha_nacimiento)
    f_ini_etapa_str = fecha_inicio_etapa.strftime("%Y-%m-%d") if isinstance(fecha_inicio_etapa, (date, datetime)) else (str(fecha_inicio_etapa) if fecha_inicio_etapa else f_ing_str)

    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute("""
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        """, (nombre_completo, f_ing_str, f_nac_str, sexo, estatus, tipo_usuario, etapa, f_ini_etapa_str, fecha_actual, paciente_id))
    else:
        c.execute("""
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, nombre_completo, f_ing_str, f_nac_str, sexo, estatus, tipo_usuario, etapa, f_ini_etapa_str, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def listar_pacientes_todos(solo_activos=False, solo_pacientes=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id FROM pacientes WHERE 1=1'
    params = []
    if solo_activos:
        query += ' AND estatus = "A"'
    if solo_pacientes:
        query += ' AND tipo_usuario = "Paciente"'
    query += ' ORDER BY nombre_completo ASC'
    c.execute(query, params)
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

def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes ORDER BY ROWID DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row and row[0].startswith('PAC-'):
        try:
            num = int(row[0].split('-')[1]) + 1
            return f'PAC-{num:03d}'
        except Exception:
            pass
    return 'PAC-001'

def verificar_duplicado_nombre(nombre_completo, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre_completo.strip().lower()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    for pid, pnom, pest in rows:
        if paciente_id_actual and pid == paciente_id_actual:
            continue
        if pnom.strip().lower() == nombre_clean:
            return pid, pnom, pest
    return None

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def obtener_catalogo_tipos_grupos(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT id, nombre, descripcion, activo, es_confronto, campos_json FROM catalogo_tipos_grupos WHERE activo = 1 ORDER BY nombre ASC')
    else:
        c.execute('SELECT id, nombre, descripcion, activo, es_confronto, campos_json FROM catalogo_tipos_grupos ORDER BY nombre ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_tipo_grupo(nombre, descripcion, es_confronto, campos_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    campos_json = json.dumps(campos_list)
    try:
        c.execute('INSERT INTO catalogo_tipos_grupos (nombre, descripcion, activo, es_confronto, campos_json) VALUES (?, ?, 1, ?, ?)',
                  (nombre.strip(), descripcion.strip(), 1 if es_confronto else 0, campos_json))
        conn.commit()
        conn.close()
        return True, "Tipo de grupo creado exitosamente."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Ya existe un tipo de grupo con ese nombre."

def cambiar_estatus_tipo_grupo(grupo_id, nuevo_estado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_tipos_grupos SET activo = ? WHERE id = ?', (1 if nuevo_estado else 0, grupo_id))
    conn.commit()
    conn.close()

def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, modalidad, fecha_grupo, facilitador, datos_dict, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_grp_str = fecha_grupo.strftime("%Y-%m-%d") if isinstance(fecha_grupo, (date, datetime)) else str(fecha_grupo)
    datos_json = json.dumps(datos_dict)

    c.execute("""
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, modalidad, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (paciente_id, tipo_grupo, etapa_al_momento, modalidad, f_grp_str, facilitador, datos_json, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, modalidad, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def contar_grupos_etapa_paciente(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def eliminar_grupo_terapeuto(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM grupos_terapeutos WHERE id = ?', (grupo_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE REQUISITOS Y ETAPAS ---
def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, etapa, requisito, es_grupo, tipo_grupo_requerido, cantidad_grupo_requerida FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def marcar_cumplimiento_requisito(paciente_id, requisito_id, etapa, cumplido, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if cumplido:
        c.execute("""
            INSERT OR REPLACE INTO cumplimiento_requisitos (paciente_id, requisito_id, etapa, cumplido, fecha_cumplido, usuario_registro)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (paciente_id, requisito_id, etapa, fecha_actual, usuario))
    else:
        c.execute('DELETE FROM cumplimiento_requisitos WHERE paciente_id = ? AND requisito_id = ?', (paciente_id, requisito_id))
    conn.commit()
    conn.close()

def obtener_cumplimientos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT requisito_id, cumplido FROM cumplimiento_requisitos WHERE paciente_id = ?', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def promover_paciente_etapa(paciente_id, etapa_origen, etapa_destino, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_hoy_str = datetime.now().strftime("%Y-%m-%d")

    # Actualizar etapa del paciente y resetear fecha_inicio_etapa a hoy
    c.execute("""
        UPDATE pacientes
        SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    """, (etapa_destino, fecha_hoy_str, fecha_actual, paciente_id))

    # Guardar en historial
    c.execute("""
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    """, (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario))

    conn.commit()
    conn.close()

def agregar_requisito_etapa(etapa, requisito, es_grupo=0, tipo_grupo=None, cantidad=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO requisitos_etapas (etapa, requisito, es_grupo, tipo_grupo_requerido, cantidad_grupo_requerida)
        VALUES (?, ?, ?, ?, ?)
    """, (etapa, requisito.strip(), es_grupo, tipo_grupo, cantidad))
    conn.commit()
    conn.close()

def eliminar_requisito_etapa(requisito_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (requisito_id,))
    conn.commit()
    conn.close()

def actualizar_dias_objetivo_etapa(etapa, dias):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE config_etapas SET dias_objetivo = ? WHERE etapa = ?', (dias, etapa))
    conn.commit()
    conn.close()

# --- FUNCIONES DE HERMANO MAYOR ---
def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        UPDATE pacientes
        SET hermano_mayor_id = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    """, (hermano_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
        UPDATE pacientes
        SET hermano_mayor_id = NULL, fecha_suelta_hermano = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    """, (fecha_hoy, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "TODAS":
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY fecha_subida DESC', (carpeta_filtro,))
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY fecha_subida DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE CATÁLOGO Y MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, concentracion, presentacion, descripcion FROM catalogo_medicamentos ORDER BY nombre ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(nombre, concentracion, presentacion, descripcion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO catalogo_medicamentos (nombre, concentracion, presentacion, descripcion) VALUES (?, ?, ?, ?)',
                  (nombre.strip(), concentracion.strip(), presentacion.strip(), descripcion.strip()))
        conn.commit()
        conn.close()
        return True, "Medicamento registrado exitosamente."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Ya existe un medicamento con ese nombre."

def eliminar_medicamento_catalogo(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

def guardar_entrevista(paciente_id, datos_dict, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos_dict)
    c.execute("""
        INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
        VALUES (?, ?, ?, ?, ?)
    """, (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return None

def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list)
    c.execute("""
        INSERT OR REPLACE INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        meds = json.loads(row[0]) if row[0] else []
        return meds, row[1] or "", row[2] or ""
    return [], "", ""

def registrar_entrega_medicamentos(paciente_id, entregado_por, detalle_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_list)
    c.execute("""
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
        VALUES (?, ?, ?, ?)
    """, (paciente_id, fecha_actual, entregado_por, detalle_json))
    conn.commit()
    conn.close()

# --- HELPER DE LIMPIEZA DE TEXTO PARA PDF ---
def limpiar_texto(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    for k, v in replacements.items():
        texto = texto.replace(k, v)
    return texto

# --- CLASE PDF CON ENCABEZADO Y PIE ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 8, limpiar_texto("SAWABONA SHIKOBA - COMUNIDAD TERAPÉUTICA"), 0, 1, "C")
        self.set_font("Arial", "I", 9)
        self.cell(0, 5, limpiar_texto("Sistema Integral de Control y Seguimiento Clínico"), 0, 1, "C")
        self.line(10, 24, 200, 24)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

def generar_pdf_grupos_paciente(paciente_id, nombre_paciente):
    grupos = obtener_grupos_paciente(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, limpiar_texto(f"EXPEDIENTE DE GRUPOS TERAPÉUTICOS"), 0, 1, "L")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, limpiar_texto(f"Paciente: {nombre_paciente} | Folio: {paciente_id}"), 0, 1, "L")
    pdf.cell(0, 6, limpiar_texto(f"Fecha de Emisión: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), 0, 1, "L")
    pdf.ln(4)

    if not grupos:
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 8, limpiar_texto("No hay sesiones de grupo registradas para este paciente."), 0, 1, "L")
    else:
        for g in grupos:
            gid, tgrp, etapa, modalidad, fgrp, fac, djson, freg, ureg = g
            datos = json.loads(djson) if djson else {}
            pdf.set_fill_color(230, 230, 230)
            pdf.set_font("Arial", "B", 10)
            pdf.cell(0, 7, limpiar_texto(f"Sesión: {tgrp} [{modalidad}] - Fecha: {fgrp} (Etapa: {etapa})"), 1, 1, "L", True)
            pdf.set_font("Arial", "", 9)
            pdf.cell(0, 5, limpiar_texto(f"Facilitador: {fac} | Registrado por: {ureg} el {freg}"), 0, 1, "L")
            pdf.ln(2)

            for k, v in datos.items():
                pdf.set_font("Arial", "B", 9)
                pdf.cell(40, 5, limpiar_texto(f"{k.capitalize()}:"), 0, 0, "L")
                pdf.set_font("Arial", "", 9)
                pdf.multi_cell(0, 5, limpiar_texto(str(v)))
            pdf.ln(4)

    os.makedirs("scratch", exist_ok=True)
    pdf_path = f"scratch/Expediente_Grupos_{paciente_id}.pdf"
    pdf.output(pdf_path)
    return pdf_path

# --- INICIALIZACIÓN DE ESTADO ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: gray;'>Sistema Integral de Control y Seguimiento Clínico</h3>", unsafe_allow_html=True)
    st.divider()

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("form_login"):
            st.subheader("🔑 Inicio de Sesión de Staff")
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Iniciar Sesión", use_container_width=True)

            if btn_login:
                res = verificar_login(user_input, pass_input)
                if res:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["nombre_completo"] = res[1]
                    st.session_state["rol"] = res[2]
                    st.toast("🎉 ¡Acceso concedido!")
                    st.success("¡Bienvenido al Sistema!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL Y NAVEGACIÓN DE MENÚ ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **{st.session_state['nombre_completo']}**")
    st.sidebar.caption(f"Rol: {st.session_state['rol']}")

    opciones_menu = [
        "📝 Nueva Entrevista / Editar",
        "🔍 Buscar y Listar Pacientes",
        "👤 Registro y Edición de Usuarios",
        "🎯 Gestión de Etapas",
        "🗣️ Grupos Terapéuticos",
        "💊 Control de Medicamentos y Dosis",
        "🚚 Entrega de Medicamentos",
        "📁 Repositorio de Documentos",
        "📦 Respaldo y Restauración",
        "⚙️ Configuración & Seguridad"
    ]

    menu = st.sidebar.radio("Navegación del Sistema", opciones_menu)

    st.sidebar.divider()
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # --- MÓDULO 1: NUEVA ENTREVISTA / EDITAR ---
    # ==========================================
    if menu == "📝 Nueva Entrevista / Editar":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Captura y evaluación clínica socio-demográfica, sustancias de impacto y disposición al cambio")

        pacientes_activos = listar_pacientes_todos(solo_activos=True, solo_pacientes=True)
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados en el sistema.")
        else:
            dict_pacientes = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_activos}
            sel_p_str = st.selectbox("🔑 Selecciona el Paciente para la Entrevista", list(dict_pacientes.keys()))
            p_id_sel = dict_pacientes[sel_p_str]

            ent_data = obtener_entrevista(p_id_sel) or {}

            with st.form("form_entrevista_completa"):
                st.subheader("1. Datos Socio-Demográficos Generales")
                c_e1, c_e2, c_e3 = st.columns(3)
                with c_e1:
                    e_ocupacion = st.text_input("Ocupación / Oficio", value=ent_data.get("ocupacion", ""))
                    e_escolaridad = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria / Bachillerato", "Licenciatura / Profesional", "Posgrado", "Ninguna"], index=0)
                with c_e2:
                    e_estado_civil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                    e_hijos = st.number_input("Número de Hijos", min_value=0, max_value=20, value=int(ent_data.get("hijos", 0)))
                with c_e3:
                    e_vive_con = st.text_input("¿Con quién vive actualmente?", value=ent_data.get("vive_con", ""))
                    e_responsable = st.text_input("Familiar / Responsable Legal", value=ent_data.get("responsable", ""))

                st.divider()
                st.subheader("2. Historial de Consumo de Sustancias")
                e_sustancia_pri = st.text_input("Sustancia de Mayor Impacto / Principal", value=ent_data.get("sustancia_pri", ""))
                e_sustancias_sec = st.text_input("Sustancias Secundarias", value=ent_data.get("sustancias_sec", ""))
                e_edad_inicio = st.number_input("Edad de Inicio de Consumo", min_value=5, max_value=99, value=int(ent_data.get("edad_inicio", 15)))
                e_detonantes = st.text_area("Detonantes / Situaciones de Riesgo Identificadas", value=ent_data.get("detonantes", ""))

                st.divider()
                st.subheader("3. Disposición al Cambio y Antecedentes")
                e_motivacion = st.text_area("Motivación Principal para Ingresar a Tratamiento", value=ent_data.get("motivacion", ""))
                e_intentos_prev = st.number_input("Número de Internamientos o Tratamientos Previos", min_value=0, max_value=50, value=int(ent_data.get("intentos_prev", 0)))

                btn_guardar_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True, disabled=not puede_escribir())

                if btn_guardar_ent:
                    datos_guardar = {
                        "ocupacion": e_ocupacion,
                        "escolaridad": e_escolaridad,
                        "estado_civil": e_estado_civil,
                        "hijos": e_hijos,
                        "vive_con": e_vive_con,
                        "responsable": e_responsable,
                        "sustancia_pri": e_sustancia_pri,
                        "sustancias_sec": e_sustancias_sec,
                        "edad_inicio": e_edad_inicio,
                        "detonantes": e_detonantes,
                        "motivacion": e_motivacion,
                        "intentos_prev": e_intentos_prev
                    }
                    guardar_entrevista(p_id_sel, datos_guardar, st.session_state["username"])
                    st.toast("🎉 ¡Entrevista guardada exitosamente!")
                    st.success("✅ Datos de la entrevista inicial guardados correctamente.")

    # ==========================================
    # --- MÓDULO 2: BUSCAR Y LISTAR PACIENTES ---
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Expedientes Clínicos")
        st.caption("Consulta de residentes activos, historial de carpetas y expediente consolidado")

        busqueda = st.text_input("🔎 Buscar Paciente por Nombre o Folio...")
        todos_p = listar_pacientes_todos(solo_activos=False, solo_pacientes=False)

        if busqueda.strip():
            b_clean = busqueda.strip().lower()
            todos_p = [p for p in todos_p if b_clean in p[0].lower() or b_clean in p[1].lower()]

        if not todos_p:
            st.info("No se encontraron registros de pacientes con el criterio especificado.")
        else:
            dict_list_p = {f"{p[1]} ({p[0]}) - Etapa: {p[7]} [{'Activo' if p[5]=='A' else 'Baja'}]": p[0] for p in todos_p}
            p_sel_ver = st.selectbox("🔑 Selecciona el Paciente para Inspeccionar Expediente", list(dict_list_p.keys()))
            pid_v = dict_list_p[p_sel_ver]

            p_info = obtener_paciente_por_id(pid_v)
            if p_info:
                st.subheader(f"📌 Expediente: {p_info[1]} (`{p_info[0]}`)")
                c_v1, c_v2, c_v3, c_v4 = st.columns(4)
                dias_ac = calcular_dias_en_etapa(p_info[2], p_info[8])
                c_v1.metric("Fecha de Ingreso", p_info[2] or "N/A")
                c_v2.metric("Etapa Actual", p_info[7])
                c_v3.metric("Fecha Inicio Etapa", p_info[8] or p_info[2] or "N/A")
                c_v4.metric("Días en Etapa Actual", f"{dias_ac} días")

                tab_exp1, tab_exp2, tab_exp3 = st.tabs(["📝 Entrevista Inicial", "🗣️ Historial de Grupos", "💊 Medicamentos"])

                with tab_exp1:
                    e_dat = obtener_entrevista(pid_v)
                    if e_dat:
                        st.json(e_dat)
                    else:
                        st.info("El paciente aún no cuenta con Entrevista Inicial capturada.")

                with tab_exp2:
                    pdf_g = generar_pdf_grupos_paciente(pid_v, p_info[1])
                    if os.path.exists(pdf_g):
                        with open(pdf_g, "rb") as f:
                            st.download_button("🖨️ Descargar Expediente de Grupos (PDF)", f, file_name=f"Expediente_Grupos_{pid_v}.pdf", mime="application/pdf")

                    g_list = obtener_grupos_paciente(pid_v)
                    if not g_list:
                        st.info("No hay sesiones de grupo registradas.")
                    else:
                        for g in g_list:
                            gid, tgrp, etapa, mod, fgrp, fac, djson, freg, ureg = g
                            datos_g = json.loads(djson) if djson else {}
                            with st.expander(f"🗣️ {tgrp} [{mod}] - Fecha: {fgrp} (Etapa: {etapa})"):
                                st.write(f"**Facilitador:** {fac} | **Registrado por:** {ureg}")
                                for k, v in datos_g.items():
                                    st.write(f"**{k.capitalize()}:** {v}")

                with tab_exp3:
                    meds, obs_m, f_m = obtener_medicamentos_paciente(pid_v)
                    if meds:
                        st.dataframe(meds, use_container_width=True)
                        if obs_m:
                            st.write(f"**Observaciones:** {obs_m}")
                    else:
                        st.info("No hay esquema de medicamentos asignado a este paciente.")

    # ==========================================
    # --- MÓDULO 3: REGISTRO Y EDICIÓN USUARIOS ---
    # ==========================================
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes y Usuarios")
        st.caption("Módulo de alta de nuevos residentes, edición de datos personales y etapa inicial")

        tab_reg1, tab_reg2 = st.tabs(["🆕 Registrar Nuevo Paciente", "✏️ Editar Paciente Existente"])

        with tab_reg1:
            next_folio = generar_siguiente_folio()
            with st.form("form_alta_paciente"):
                st.subheader(f"Folio Generado: `{next_folio}`")
                c_r1, c_r2 = st.columns(2)
                with c_r1:
                    r_nombre = st.text_input("Nombre Completo del Paciente *")
                    r_f_ingreso = st.date_input("Fecha de Ingreso a la Institución *", value=date.today())
                    r_f_nac = st.date_input("Fecha de Nacimiento *", value=date(1995, 1, 1))
                with c_r2:
                    r_sexo = st.selectbox("Sexo", ["Masculino", "Femenino"])
                    r_tipo = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor", "Staff"])
                    
                    # Selección de Etapa y Fecha de Inicio de Etapa (Editables para pacientes que ingresan en etapas avanzadas)
                    r_etapa = st.selectbox("Etapa Inicial de Registro *", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"], index=0)
                    r_f_ini_etapa = st.date_input("Fecha de Inicio de esta Etapa *", value=date.today(), help="Si el paciente ingresa ya en una etapa avanzada, indique la fecha en que inició esa etapa.")

                btn_guardar_p = st.form_submit_button("💾 Guardar Registro de Paciente", use_container_width=True, disabled=not puede_escribir())

                if btn_guardar_p:
                    if not r_nombre.strip():
                        st.error("⚠️ El nombre completo es un campo obligatorio.")
                    else:
                        dup = verificar_duplicado_nombre(r_nombre)
                        if dup:
                            st.warning(f"⚠️ Ya existe un paciente con el nombre **{dup[1]}** (Folio: `{dup[0]}`).")
                        
                        guardar_usuario_paciente(
                            paciente_id=next_folio,
                            nombre_completo=r_nombre.strip(),
                            fecha_ingreso=r_f_ingreso,
                            fecha_nacimiento=r_f_nac,
                            sexo=r_sexo,
                            estatus='A',
                            tipo_usuario=r_tipo,
                            etapa=r_etapa,
                            fecha_inicio_etapa=r_f_ini_etapa,
                            usuario=st.session_state["username"]
                        )
                        st.toast(f"🎉 ¡Paciente {next_folio} registrado exitosamente!")
                        st.success(f"✅ ¡Paciente **{r_nombre}** registrado con folio `{next_folio}` en etapa **{r_etapa}**!")
                        st.balloons()
                        st.rerun()

        with tab_reg2:
            pacientes_todos = listar_pacientes_todos()
            if not pacientes_todos:
                st.info("No hay pacientes registrados.")
            else:
                dict_e = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_todos}
                sel_e_str = st.selectbox("🔑 Selecciona el Paciente a Editar", list(dict_e.keys()))
                p_e_id = dict_e[sel_e_str]

                p_edit = obtener_paciente_por_id(p_e_id)
                if p_edit:
                    with st.form("form_edit_paciente"):
                        st.subheader(f"Editando Paciente: `{p_e_id}`")
                        c_ed1, c_ed2 = st.columns(2)
                        with c_ed1:
                            ed_nombre = st.text_input("Nombre Completo *", value=p_edit[1])
                            f_ing_val = datetime.strptime(p_edit[2], "%Y-%m-%d").date() if p_edit[2] else date.today()
                            ed_f_ing = st.date_input("Fecha de Ingreso a la Institución *", value=f_ing_val)
                            
                            f_nac_val = datetime.strptime(p_edit[3], "%Y-%m-%d").date() if p_edit[3] else date(1995, 1, 1)
                            ed_f_nac = st.date_input("Fecha de Nacimiento *", value=f_nac_val)

                        with c_ed2:
                            ed_sexo = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if p_edit[4] == "Masculino" else 1)
                            ed_estatus = st.selectbox("Estatus de Permanencia", ["A - Activo", "B - Baja / Egreso"], index=0 if p_edit[5] == "A" else 1)
                            ed_tipo = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor", "Staff"], index=["Paciente", "Servidor", "Staff"].index(p_edit[6]) if p_edit[6] in ["Paciente", "Servidor", "Staff"] else 0)
                            
                            etapas_list = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                            idx_etapa = etapas_list.index(p_edit[7]) if p_edit[7] in etapas_list else 0
                            ed_etapa = st.selectbox("Etapa Actual *", etapas_list, index=idx_etapa)

                            f_ini_etapa_val = datetime.strptime(p_edit[8], "%Y-%m-%d").date() if p_edit[8] else f_ing_val
                            ed_f_ini_etapa = st.date_input("Fecha de Inicio de esta Etapa *", value=f_ini_etapa_val, help="Si la fecha de inicio de etapa es mayor a la de ingreso, los días en etapa se contabilizan desde aquí.")

                        btn_update_p = st.form_submit_button("💾 Actualizar Datos del Paciente", use_container_width=True, disabled=not puede_escribir())

                        if btn_update_p:
                            guardar_usuario_paciente(
                                paciente_id=p_e_id,
                                nombre_completo=ed_nombre.strip(),
                                fecha_ingreso=ed_f_ing,
                                fecha_nacimiento=ed_f_nac,
                                sexo=ed_sexo,
                                estatus='A' if ed_estatus.startswith('A') else 'B',
                                tipo_usuario=ed_tipo,
                                etapa=ed_etapa,
                                fecha_inicio_etapa=ed_f_ini_etapa,
                                usuario=st.session_state["username"]
                            )
                            st.toast("🎉 ¡Datos actualizados!")
                            st.success(f"✅ ¡Paciente **{ed_nombre}** actualizado exitosamente!")
                            st.rerun()

    # ==========================================
    # --- MÓDULO 4: GESTIÓN DE ETAPAS & PROCESO ---
    # ==========================================
    elif menu == "🎯 Gestión de Etapas":
        st.title("🎯 Gestión de Etapas y Semaforización del Proceso Clínico")
        st.caption("Seguimiento del tiempo en etapa, alertas visuales de permanencia y checklist de requisitos cumplidos")

        pacientes_activos = listar_pacientes_todos(solo_activos=True, solo_pacientes=True)
        config_dias = obtener_config_etapas()

        # Métricas generales de semaforización
        cant_regular = 0
        cant_alerta = 0
        cant_excedido = 0

        datos_tabla = []

        for p in pacientes_activos:
            pid, pnom, f_ing, f_nac, sexo, estatus, t_usr, etapa_curr, f_ini_etapa, h_id = p
            dias_acum = calcular_dias_en_etapa(f_ing, f_ini_etapa)
            dias_obj = config_dias.get(etapa_curr, 30)
            dias_restantes = dias_obj - dias_acum

            if dias_restantes <= 0:
                estatus_sem = "🔴 Excedido"
                cant_excedido += 1
            elif dias_restantes <= 5:
                estatus_sem = "🟡 Por vencer (≤ 5 días)"
                cant_alerta += 1
            else:
                estatus_sem = "🟢 En tiempo regular"
                cant_regular += 1

            datos_tabla.append({
                "pid": pid,
                "nombre": pnom,
                "etapa": etapa_curr,
                "f_ing": f_ing,
                "f_ini_etapa": f_ini_etapa or f_ing,
                "dias_acum": dias_acum,
                "dias_obj": dias_obj,
                "dias_restantes": dias_restantes,
                "estatus_sem": estatus_sem,
                "hermano_id": h_id
            })

        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        c_m1.metric("Total Residentes en Proceso", len(pacientes_activos))
        c_m2.metric("🟢 En Tiempo Regular", cant_regular)
        c_m3.metric("🟡 Próximos a Vencer (≤ 5d)", cant_alerta)
        c_m4.metric("🔴 Tiempo Excedido", cant_excedido)

        st.divider()

        # Filtros de visualización
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            filtro_etapa = st.selectbox("Filtrar por Etapa", ["TODAS LAS ETAPAS", "ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
        with f_col2:
            filtro_sem = st.selectbox("Filtrar por Estatus de Tiempo", ["TODOS LOS ESTATUS", "🟢 En tiempo regular", "🟡 Por vencer (≤ 5 días)", "🔴 Excedido"])

        datos_filtrados = datos_tabla
        if filtro_etapa != "TODAS LAS ETAPAS":
            datos_filtrados = [d for d in datos_filtrados if d["etapa"] == filtro_etapa]
        if filtro_sem != "TODOS LOS ESTATUS":
            datos_filtrados = [d for d in datos_filtrados if d["estatus_sem"] == filtro_sem]

        st.subheader("📋 Listado de Pacientes y Semaforización")

        if not datos_filtrados:
            st.info("No hay pacientes con los criterios de filtro seleccionados.")
        else:
            dict_p_gest = {f"{d['nombre']} ({d['pid']}) | Etapa: {d['etapa']} | Días: {d['dias_acum']}/{d['dias_obj']} | {d['estatus_sem']}": d['pid'] for d in datos_filtrados}
            p_sel_gest = st.selectbox("🔑 Selecciona un Paciente para Consultar / Marcar Requisitos", list(dict_p_gest.keys()))
            pid_g = dict_p_gest[p_sel_gest]

            p_target = [d for d in datos_tabla if d["pid"] == pid_g][0]

            st.markdown(f"### 📌 Detalle Clínico: **{p_target['nombre']}** (`{p_target['pid']}`)")
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            col_d1.metric("Etapa Actual", p_target["etapa"])
            col_d2.metric("Fecha Inicio Etapa", p_target["f_ini_etapa"])
            col_d3.metric("Días Acumulados / Objetivo", f"{p_target['dias_acum']} / {p_target['dias_obj']} días")
            col_d4.metric("Estatus Visual", p_target["estatus_sem"])

            st.divider()

            # Checklist de Requisitos de la Etapa Actual
            st.subheader(f"📝 Checklist de Requisitos para Etapa: **{p_target['etapa']}**")

            reqs_etapa = obtener_requisitos_etapa(p_target["etapa"])
            cumplimientos = obtener_cumplimientos_paciente(pid_g)

            reqs_cumplidos_count = 0
            total_reqs_count = len(reqs_etapa)

            for req in reqs_etapa:
                rid, retapa, rtxt, esg, tgrp_req, cant_req = req
                
                # Si es un requisito de grupo, se contabilizan las sesiones registradas en esta etapa
                if esg == 1 and tgrp_req:
                    cnt_completados = contar_grupos_etapa_paciente(pid_g, p_target["etapa"], tgrp_req)
                    cumplido_auto = cnt_completados >= cant_req
                    
                    if cumplido_auto:
                        reqs_cumplidos_count += 1
                        st.success(f"✅ **{rtxt}**: {cnt_completados} / {cant_req} grupos completados 🎉")
                    else:
                        st.warning(f"⏳ **{rtxt}**: {cnt_completados} / {cant_req} grupos completados")
                else:
                    is_checked = cumplimientos.get(rid, 0) == 1
                    if is_checked:
                        reqs_cumplidos_count += 1

                    chk_val = st.checkbox(f"• {rtxt}", value=is_checked, key=f"chk_req_{pid_g}_{rid}", disabled=not puede_escribir())
                    if chk_val != is_checked:
                        marcar_cumplimiento_requisito(pid_g, rid, p_target["etapa"], chk_val, st.session_state["username"])
                        st.rerun()

            st.progress(reqs_cumplidos_count / total_reqs_count if total_reqs_count > 0 else 1.0)
            st.caption(f"Avance de Requisitos: **{reqs_cumplidos_count} / {total_reqs_count}** completados")

            st.divider()
            
            # Promoción de Etapa
            st.subheader("🚀 Promoción a la Siguiente Etapa")
            siguientes_etapas = {
                "ACOGIDA": "IDENTIFICACIÓN",
                "IDENTIFICACIÓN": "ELABORACIÓN",
                "ELABORACIÓN": "CONSOLIDACIÓN",
                "CONSOLIDACIÓN": "SERVICIO SOCIAL",
                "SERVICIO SOCIAL": "EGRESADO / FINALIZADO"
            }
            sig_etapa = siguientes_etapas.get(p_target["etapa"], "SERVICIO SOCIAL")

            if sig_etapa == "EGRESADO / FINALIZADO":
                st.info("🎓 El paciente se encuentra en la etapa final del programa (Servicio Social).")
            else:
                pueden_promover = (reqs_cumplidos_count >= total_reqs_count) or es_admin()
                if not pueden_promover:
                    st.warning(f"⚠️ El paciente debe completar todos sus requisitos ({total_reqs_count}) para avanzar a **{sig_etapa}** (Requiere nivel Administrador para promover antes).")

                if st.button(f"🎓 Promover Paciente a Etapa: {sig_etapa}", disabled=not pueden_promover or not puede_escribir(), use_container_width=True):
                    promover_paciente_etapa(pid_g, p_target["etapa"], sig_etapa, st.session_state["username"])
                    st.toast(f"🎉 ¡Paciente promovido a {sig_etapa}!")
                    st.success(f"✅ ¡El paciente **{p_target['nombre']}** ha sido promovido exitosamente a **{sig_etapa}**!")
                    st.balloons()
                    st.rerun()

    # ==========================================
    # --- MÓDULO 5: GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Módulo de Grupos Terapéuticos")
        st.caption("Captura de sesiones individuales de grupo, historial completo y catálogo de tipos de grupo")

        tab_g1, tab_g2, tab_g3 = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF", "⚙️ Catálogo de Tipos de Grupo"])

        with tab_g1:
            pacientes_activos = listar_pacientes_todos(solo_activos=True, solo_pacientes=True)
            if not pacientes_activos:
                st.warning("No hay pacientes activos registrados.")
            else:
                dict_pac_g = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1], p[7]) for p in pacientes_activos}
                sel_pac_g = st.selectbox("🔑 Selecciona el Paciente *", list(dict_pac_g.keys()), key="sel_g_pac")
                p_id_g, p_nom_g, p_etapa_g = dict_pac_g[sel_pac_g]

                tipos_grupos_activos = obtener_catalogo_tipos_grupos(solo_activos=True)
                if not tipos_grupos_activos:
                    st.error("No hay tipos de grupos activos en el catálogo.")
                else:
                    dict_tipos_g = {g[1]: g for g in tipos_grupos_activos}
                    t_nombre_sel = st.selectbox("🗣️ Selecciona el Tipo de Grupo Terapéutico *", list(dict_tipos_g.keys()))
                    g_obj = dict_tipos_g[t_nombre_sel]

                    # Configuración del grupo
                    g_id_cat, g_nombre, g_desc, g_act, g_es_confronto, g_campos_raw = g_obj
                    campos_g = json.loads(g_campos_raw) if g_campos_raw else []

                    with st.form("form_registro_grupo"):
                        st.subheader(f"Captura de Sesión: **{g_nombre}**")
                        c_grp1, c_grp2, c_grp3 = st.columns(3)
                        with c_grp1:
                            st.text_input("Paciente", value=p_nom_g, disabled=True)
                            st.text_input("Expediente / Folio", value=p_id_g, disabled=True)
                        with c_grp2:
                            st.text_input("Etapa del Paciente", value=p_etapa_g, disabled=True)
                            f_grupo_val = st.date_input("Fecha del Grupo *", value=date.today())
                        with c_grp3:
                            mod_opciones = ["Normal", "Confronto"] if g_es_confronto == 1 else ["Normal"]
                            g_modalidad = st.selectbox("Modalidad de la Sesión", mod_opciones)
                            g_facilitador = st.text_input("Nombre del Facilitador / Staff *", value=st.session_state["nombre_completo"])

                        st.divider()
                        st.markdown("##### 📝 Campos de la Sesión")

                        dict_campos_captured = {}
                        for campo in campos_g:
                            if campo == "Facilitador":
                                continue
                            val_c = st.text_area(f"{campo} *", key=f"f_g_{campo}")
                            dict_campos_captured[campo] = val_c

                        btn_save_grp = st.form_submit_button(f"💾 Guardar Registro de {g_nombre}", use_container_width=True, disabled=not puede_escribir())

                        if btn_save_grp:
                            if not g_facilitador.strip():
                                st.error("⚠️ El nombre del facilitador es obligatorio.")
                            else:
                                guardar_grupo_terapeuto(
                                    paciente_id=p_id_g,
                                    tipo_grupo=g_nombre,
                                    etapa_al_momento=p_etapa_g,
                                    modalidad=g_modalidad,
                                    fecha_grupo=f_grupo_val,
                                    facilitador=g_facilitador.strip(),
                                    datos_dict=dict_campos_captured,
                                    usuario=st.session_state["username"]
                                )
                                st.toast(f"🎉 ¡Sesión de {g_nombre} registrada!")
                                st.success(f"✅ ¡Sesión de **{g_nombre}** ({g_modalidad}) registrada correctamente para **{p_nom_g}**!")
                                st.balloons()
                                st.rerun()

        with tab_g2:
            pacientes_todos = listar_pacientes_todos()
            if not pacientes_todos:
                st.info("No hay pacientes registrados.")
            else:
                dict_hist_g = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_todos}
                sel_h_g = st.selectbox("🔑 Selecciona el Paciente para Historial de Grupos", list(dict_hist_g.keys()))
                p_id_h, p_nom_h = dict_hist_g[sel_h_g]

                pdf_path = generar_pdf_grupos_paciente(p_id_h, p_nom_h)
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button("🖨️ Descargar Expediente de Grupos en PDF", f, file_name=f"Expediente_Grupos_{p_id_h}.pdf", mime="application/pdf")

                st.divider()

                grupos_pac = obtener_grupos_paciente(p_id_h)
                if not grupos_pac:
                    st.info("Este paciente no tiene sesiones de grupo registradas.")
                else:
                    for g in grupos_pac:
                        gid, tgrp, etapa_m, mod_m, fgrp, fac_m, djson_m, freg_m, ureg_m = g
                        datos_m = json.loads(djson_m) if djson_m else {}
                        with st.expander(f"🗣️ **{tgrp}** [{mod_m}] | Fecha: {fgrp} | Etapa: {etapa_m} | Facilitador: {fac_m}"):
                            col_g1, col_g2 = st.columns([4, 1])
                            with col_g1:
                                st.write(f"**Registrado por:** `{ureg_m}` el {freg_m}")
                                for k, v in datos_m.items():
                                    st.write(f"**{k.capitalize()}:** {v}")
                            with col_g2:
                                if st.button("🗑️ Eliminar", key=f"del_grp_{gid}", disabled=not puede_escribir()):
                                    eliminar_grupo_terapeuto(gid)
                                    st.toast("Sesión eliminada.")
                                    st.rerun()

        with tab_g3:
            st.subheader("⚙️ Catálogo General de Tipos de Grupo")
            st.caption("Administra los tipos de grupo disponibles en la comunidad. Desactiva los que no se usen sin borrar su historial.")

            grupos_todos_cat = obtener_catalogo_tipos_grupos(solo_activos=False)

            for g_cat in grupos_todos_cat:
                cid, cnom, cdesc, cact, ces_conf, ccampos_json = g_cat
                campos_l = json.loads(ccampos_json) if ccampos_json else []

                c_cat1, c_cat2, c_cat3 = st.columns([3, 2, 1])
                with c_cat1:
                    st.write(f"🗣️ **{cnom}** {'[Permite Confronto]' if ces_conf==1 else ''}")
                    st.caption(f"Campos: {', '.join(campos_l)}")
                with c_cat2:
                    st.write(f"Estatus: {'🟢 Activo' if cact==1 else '🔴 Inactivo'}")
                with c_cat3:
                    lbl_btn = "🔴 Desactivar" if cact==1 else "🟢 Activar"
                    if st.button(lbl_btn, key=f"toggle_g_{cid}", disabled=not es_admin()):
                        cambiar_estatus_tipo_grupo(cid, cact == 0)
                        st.toast("Estatus de grupo actualizado.")
                        st.rerun()

            st.divider()
            st.subheader("➕ Agregar Nuevo Tipo de Grupo al Catálogo")
            with st.form("form_add_tipo_grupo"):
                nuevo_g_nom = st.text_input("Nombre del Tipo de Grupo *")
                nuevo_g_desc = st.text_input("Descripción Corta")
                nuevo_g_conf = st.checkbox("¿Permite elegir modalidad 'Confronto'?")
                nuevo_g_campos_str = st.text_input("Campos a Capturar (Separados por coma)", value="Compartimiento, Observaciones, Devoluciones, Como se queda, Compromiso")

                btn_add_tg = st.form_submit_button("➕ Registrar Nuevo Tipo de Grupo", use_container_width=True, disabled=not es_admin())

                if btn_add_tg:
                    if not nuevo_g_nom.strip():
                        st.error("⚠️ El nombre del grupo es obligatorio.")
                    else:
                        campos_parsed = [c.strip() for c in nuevo_g_campos_str.split(",") if c.strip()]
                        if "Facilitador" not in campos_parsed:
                            campos_parsed.append("Facilitador")
                        
                        ok_tg, msg_tg = guardar_tipo_grupo(nuevo_g_nom, nuevo_g_desc, nuevo_g_conf, campos_parsed)
                        if ok_tg:
                            st.toast("🎉 ¡Tipo de grupo agregado!")
                            st.success(f"✅ ¡Tipo de grupo **{nuevo_g_nom}** agregado exitosamente!")
                            st.rerun()
                        else:
                            st.error(msg_tg)

    # ==========================================
    # --- MÓDULO 6: CONTROL DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Prescripción y Control de Medicamentos")
        st.caption("Asignación de esquemas de medicación por paciente y consulta de catálogo central")

        tab_m1, tab_m2 = st.tabs(["💊 Asignar Esquema por Paciente", "📦 Catálogo Central de Farmacia"])

        with tab_m1:
            pacientes_activos = listar_pacientes_todos(solo_activos=True, solo_pacientes=True)
            if not pacientes_activos:
                st.warning("No hay pacientes activos.")
            else:
                dict_pac_m = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
                sel_p_m = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_m.keys()))
                p_id_m = dict_pac_m[sel_p_m]

                meds_curr, obs_curr, _ = obtener_medicamentos_paciente(p_id_m)
                cat_meds = obtener_catalogo_medicamentos()

                st.subheader("📋 Esquema Actual del Paciente")
                if meds_curr:
                    st.dataframe(meds_curr, use_container_width=True)

                st.divider()
                st.subheader("➕ Modificar / Agregar Medicamentos al Esquema")

                if not cat_meds:
                    st.error("El catálogo de medicamentos está vacío.")
                else:
                    opciones_cat_meds = [f"{m[1]} - {m[2]} ({m[3]})" for m in cat_meds]
                    
                    with st.form("form_add_med_paciente"):
                        med_sel_cat = st.selectbox("Selecciona Medicamento del Catálogo", opciones_cat_meds)
                        col_d1, col_d2, col_d3 = st.columns(3)
                        col_d1.number_input("Dosis Mañana", min_value=0.0, step=0.5, key="m_manana")
                        col_d2.number_input("Dosis Tarde", min_value=0.0, step=0.5, key="m_tarde")
                        col_d3.number_input("Dosis Noche", min_value=0.0, step=0.5, key="m_noche")

                        m_ex = st.number_input("Existencia / Stock Asignado en Farmacia", min_value=0, value=30, key="m_existencia")
                        m_indicaciones = st.text_input("Indicaciones Especiales", key="m_indicaciones")

                        btn_add_m = st.form_submit_button("➕ Agregar al Esquema del Paciente", use_container_width=True, disabled=not puede_escribir())

                        if btn_add_m:
                            nuevo_med_dict = {
                                "nombre": med_sel_cat.split(" - ")[0],
                                "dosis_manana": st.session_state["m_manana"],
                                "dosis_tarde": st.session_state["m_tarde"],
                                "dosis_noche": st.session_state["m_noche"],
                                "existencia": m_ex,
                                "indicaciones": m_indicaciones
                            }
                            meds_curr.append(nuevo_med_dict)
                            guardar_medicamentos_paciente(p_id_m, meds_curr, obs_curr, st.session_state["username"])
                            st.toast("🎉 ¡Medicamento agregado al esquema!")
                            st.success("✅ Esquema de medicamentos actualizado exitosamente.")
                            st.rerun()

        with tab_m2:
            st.subheader("📦 Catálogo Central de Farmacia")
            cat_all = obtener_catalogo_medicamentos()
            st.dataframe(cat_all, use_container_width=True)

            st.divider()
            st.subheader("➕ Agregar Medicamento al Catálogo Central")
            with st.form("form_add_cat_med"):
                c_cm1, c_cm2 = st.columns(2)
                with c_cm1:
                    cm_nom = st.text_input("Nombre del Medicamento *")
                    cm_conc = st.text_input("Concentración (ej. 500 mg, 20 mg)")
                with c_cm2:
                    cm_pres = st.text_input("Presentación (ej. Comprimidos, Cápsulas, Gotas)")
                    cm_desc = st.text_input("Descripción / Familia")

                btn_save_cm = st.form_submit_button("💾 Guardar en Catálogo Central", use_container_width=True, disabled=not es_admin())

                if btn_save_cm:
                    if not cm_nom.strip():
                        st.error("⚠️ El nombre es obligatorio.")
                    else:
                        ok_cm, msg_cm = guardar_medicamento_catalogo(cm_nom, cm_conc, cm_pres, cm_desc)
                        if ok_cm:
                            st.toast("🎉 ¡Medicamento agregado al catálogo!")
                            st.success("✅ Guardado en catálogo central.")
                            st.rerun()
                        else:
                            st.error(msg_cm)

    # ==========================================
    # --- MÓDULO 7: ENTREGA DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro y Descuento de Medicamentos Entregados")
        st.caption("Surtido diario y actualización de existencias en el almacén de farmacia")

        pacientes_activos = listar_pacientes_todos(solo_activos=True, solo_pacientes=True)
        if not pacientes_activos:
            st.warning("No hay pacientes activos.")
        else:
            dict_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_ent = st.selectbox("🔑 Selecciona el Residente para Surtido", list(dict_ent.keys()))
            p_id_ent = dict_ent[sel_p_ent]

            meds_list, obs_m, _ = obtener_medicamentos_paciente(p_id_ent)
            if not meds_list:
                st.info("El paciente no tiene medicamentos registrados en su esquema.")
            else:
                with st.form("form_surtir_meds"):
                    st.subheader(f"Surtido para: `{p_id_ent}`")
                    detalles_entrega = []
                    
                    for i, m in enumerate(meds_list):
                        m_nom = m.get("nombre", f"Med #{i+1}")
                        d_m = float(m.get("dosis_manana", 0))
                        d_t = float(m.get("dosis_tarde", 0))
                        d_n = float(m.get("dosis_noche", 0))
                        d_total_dia = d_m + d_t + d_n
                        ex_actual = int(m.get("existencia", 0))

                        col_e1, col_e2 = st.columns([3, 2])
                        col_e1.markdown(f"💊 **{m_nom}** | Dosis diaria: `{d_total_dia}` | Existencia: `{ex_actual}`")
                        cant_a_entregar = col_e2.number_input(f"Entregar ({m_nom})", min_value=0, max_value=ex_actual, value=min(int(d_total_dia), ex_actual), key=f"ent_{i}")

                        detalles_entrega.append({
                            "index": i,
                            "nombre": m_nom,
                            "cantidad": cant_a_entregar,
                            "existencia_previa": ex_actual,
                            "existencia_nueva": ex_actual - cant_a_entregar
                        })

                    btn_confirm_ent = st.form_submit_button("📦 Registrar Entrega y Descontar Stock", use_container_width=True, disabled=not puede_escribir())

                    if btn_confirm_ent:
                        for d in detalles_entrega:
                            idx = d["index"]
                            meds_list[idx]["existencia"] = d["existencia_nueva"]

                        guardar_medicamentos_paciente(p_id_ent, meds_list, obs_m, st.session_state["username"])
                        registrar_entrega_medicamentos(p_id_ent, st.session_state["nombre_completo"], detalles_entrega)
                        st.toast("🎉 Entrega registrada e inventario descontado.")
                        st.success("✅ Entrega registrada exitosamente.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 8: REPOSITORIO DE DOCUMENTOS ---
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Archivero Digital y Repositorio de Documentos")
        st.caption("Almacenamiento seguro de manuales, formatos oficiales, consentimientos e informativos")

        tab_doc1, tab_doc2 = st.tabs(["📜 Consultar / Descargar Documentos", "📤 Subir Nuevo Documento"])

        with tab_doc1:
            carpetas_opts = ["TODAS", "Formatos Oficiales", "Manuales y Guías", "Consentimientos", "Reglamentos", "Otros"]
            c_filtro = st.selectbox("Filtrar por Carpeta", carpetas_opts)

            docs = obtener_documentos_repositorio(c_filtro)
            if not docs:
                st.info("No hay documentos guardados en esta carpeta.")
            else:
                for doc in docs:
                    doc_id, carpeta, nombre, mime_type, desc, fecha_s, usr_s = doc
                    c_doc1, c_doc2 = st.columns([4, 1])
                    with c_doc1:
                        st.write(f"📄 **{nombre}** (`{carpeta}`) - Subido por `{usr_s}` el {fecha_s}")
                        if desc:
                            st.caption(desc)
                    with c_doc2:
                        if st.button("🗑️ Eliminar", key=f"del_doc_{doc_id}", disabled=not es_admin()):
                            eliminar_documento_repositorio(doc_id)
                            st.toast("Documento eliminado.")
                            st.rerun()

        with tab_doc2:
            st.subheader("📤 Subir Archivo al Repositorio")
            with st.form("form_subir_doc"):
                carp_sub = st.selectbox("Carpeta de Destino *", ["Formatos Oficiales", "Manuales y Guías", "Consentimientos", "Reglamentos", "Otros"])
                arch_sub = st.file_uploader("Selecciona el Archivo *", type=["pdf", "docx", "xlsx", "png", "jpg"])
                desc_sub = st.text_input("Descripción Corta")

                btn_up_doc = st.form_submit_button("📤 Guardar Documento", use_container_width=True, disabled=not es_admin())

                if btn_up_doc:
                    if not arch_sub:
                        st.error("⚠️ Debes seleccionar un archivo.")
                    else:
                        bytes_data = arch_sub.read()
                        guardar_documento_repositorio(
                            carpeta=carp_sub,
                            nombre_archivo=arch_sub.name,
                            mime_type=arch_sub.type,
                            bytes_blob=bytes_data,
                            descripcion=desc_sub,
                            usuario=st.session_state["username"]
                        )
                        st.toast("🎉 ¡Documento subido con éxito!")
                        st.success(f"✅ Archivo **{arch_sub.name}** guardado en la carpeta `{carp_sub}`.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 9: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Copia de seguridad del sistema y restauración mediante archivo .db")

        st.subheader("⬇️ Descargar Copia de Seguridad (.db)")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button("💾 Descargar Copia de Seguridad de Base de Datos (.db)", f, file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db", mime="application/octet-stream")

        st.divider()
        st.subheader("⬆️ Restaurar Base de Datos desde Archivo")
        st.warning("⚠️ La restauración reemplazará completamente la base de datos actual. Asegúrate de respaldar previamente.")

        db_upload = st.file_uploader("Selecciona archivo .db para restaurar", type=["db", "sqlite"])
        if db_upload and st.button("🔥 Confirmar Restauración", disabled=not es_admin()):
            with open(DB_FILE, "wb") as f:
                f.write(db_upload.read())
            st.toast("🎉 Base de datos restaurada con éxito.")
            st.success("✅ Restauración completada. Reiniciando la aplicación...")
            st.rerun()

    # ==========================================
    # --- MÓDULO 10: CONFIGURACIÓN & SEGURIDAD ---
    # ==========================================
    elif menu == "⚙️ Configuración & Seguridad":
        st.title("⚙️ Configuración del Sistema & Seguridad")
        st.caption("Administración de usuarios staff, requisitos de etapas y cambio de contraseña")

        tab_s1, tab_s2, tab_s3 = st.tabs(["🔑 Cambiar Contraseña", "⚙️ Tiempos y Requisitos por Etapa", "👥 Usuarios Staff y Roles"])

        with tab_s1:
            st.subheader("Cambiar Contraseña")
            with st.form("form_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_nva = st.text_input("Nueva Contraseña", type="password")
                p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p = st.form_submit_button("Actualizar Contraseña")

                if btn_p:
                    if p_nva != p_cnf:
                        st.error("Las nuevas contraseñas no coinciden.")
                    else:
                        ok_p = verificar_login(st.session_state["username"], p_act)
                        if ok_p:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(p_nva), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.toast("🎉 Contraseña actualizada.")
                            st.success("✅ Contraseña actualizada correctamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

        with tab_s2:
            st.subheader("⚙️ Configuración de Tiempos Objetivo por Etapa")
            cfg_dias = obtener_config_etapas()

            for etapa_k, dias_v in cfg_dias.items():
                c_t1, c_t2 = st.columns([3, 1])
                with c_t1:
                    dias_nvo = st.number_input(f"Días Objetivo para **{etapa_k}**", min_value=1, max_value=365, value=dias_v, key=f"dias_e_{etapa_k}", disabled=not es_admin())
                with c_t2:
                    if st.button("💾 Guardar", key=f"btn_dias_{etapa_k}", disabled=not es_admin()):
                        actualizar_dias_objetivo_etapa(etapa_k, dias_nvo)
                        st.toast("Tiempo objetivo actualizado.")
                        st.rerun()

            st.divider()
            st.subheader("⚙️ Administrador de Requisitos por Etapa")
            etapa_sel_cfg = st.selectbox("Selecciona Etapa a Configurar", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])

            reqs_cfg = obtener_requisitos_etapa(etapa_sel_cfg)
            st.write(f"Requisitos actuales para **{etapa_sel_cfg}**:")

            for r_id, r_et, r_txt, r_esg, r_tgrp, r_cant in reqs_cfg:
                c_r1, c_r2 = st.columns([4, 1])
                with c_r1:
                    info_g = f" ({r_cant} sesiones de {r_tgrp})" if r_esg == 1 else ""
                    st.write(f"• {r_txt}{info_g}")
                with c_r2:
                    if st.button("🗑️ Eliminar", key=f"del_req_{r_id}", disabled=not es_admin()):
                        eliminar_requisito_etapa(r_id)
                        st.toast("Requisito eliminado.")
                        st.rerun()

            st.divider()
            st.subheader("➕ Agregar Nuevo Requisito a esta Etapa")
            with st.form("form_add_req_cfg"):
                nvo_req_txt = st.text_input("Descripción del Requisito *")
                es_grp_chk = st.checkbox("¿Es un requisito de conteo de Grupo Terapéutico?")

                tg_activos = obtener_catalogo_tipos_grupos(solo_activos=True)
                opts_tg = [g[1] for g in tg_activos] if tg_activos else ["Aquí y Ahora", "Terapia de Grupo", "Feedback"]
                sel_tg_req = st.selectbox("Tipo de Grupo Requerido", opts_tg)
                cant_tg_req = st.number_input("Cantidad de Sesiones Requeridas", min_value=1, max_value=50, value=4)

                btn_add_r_cfg = st.form_submit_button("➕ Agregar Requisito", use_container_width=True, disabled=not es_admin())

                if btn_add_r_cfg:
                    if not nvo_req_txt.strip():
                        st.error("⚠️ La descripción es obligatoria.")
                    else:
                        agregar_requisito_etapa(
                            etapa=etapa_sel_cfg,
                            requisito=nvo_req_txt.strip(),
                            es_grupo=1 if es_grp_chk else 0,
                            tipo_grupo=sel_tg_req if es_grp_chk else None,
                            cantidad=cant_tg_req if es_grp_chk else 0
                        )
                        st.toast("🎉 Requisito agregado exitosamente.")
                        st.success("✅ Requisito registrado.")
                        st.rerun()

        with tab_s3:
            st.subheader("👥 Gestión de Usuarios Staff")
            st.caption("Creación y administración de cuentas de staff con permisos diferenciados")

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, username, nombre_completo, rol FROM usuarios ORDER BY username ASC')
            usr_staff = c.fetchall()
            conn.close()

            st.dataframe([{"ID": u[0], "Usuario": u[1], "Nombre Completo": u[2], "Rol": u[3]} for u in usr_staff], use_container_width=True)

            st.divider()
            st.subheader("➕ Registrar Nuevo Usuario de Staff")
            with st.form("form_add_usr_staff"):
                u_uname = st.text_input("Nombre de Usuario (Login) *")
                u_full = st.text_input("Nombre Completo *")
                u_pass = st.text_input("Contraseña *", type="password")
                u_rol = st.selectbox("Rol y Nivel de Acceso", [
                    "Nivel 1 - Administrador",
                    "Nivel 2 - Equipo Clínico / Consejero",
                    "Nivel 3 - Consultor (Solo Lectura)"
                ])

                btn_add_staff = st.form_submit_button("➕ Registrar Usuario Staff", use_container_width=True, disabled=not es_admin())

                if btn_add_staff:
                    if not u_uname.strip() or not u_full.strip() or not u_pass:
                        st.error("⚠️ Todos los campos son obligatorios.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                      (u_uname.strip(), hash_pass(u_pass), u_full.strip(), u_rol))
                            conn.commit()
                            conn.close()
                            st.toast("🎉 Usuario staff registrado.")
                            st.success(f"✅ Usuario **{u_uname}** registrado con éxito.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            conn.close()
                            st.error("⚠️ Ya existe un usuario con ese nombre de usuario.")

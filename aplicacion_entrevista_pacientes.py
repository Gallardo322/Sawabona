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

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios Administrativos / Staff
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador',
            estatus TEXT DEFAULT 'A'
        )
    ''')
    c.execute("PRAGMA table_info(usuarios)")
    cols_usr = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_usr:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
        except Exception:
            pass
    if 'estatus' not in cols_usr:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN estatus TEXT DEFAULT 'A'")
        except Exception:
            pass

    # Default admin
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'A'))
                  
    # 2. Tabla de Pacientes / Residentes
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
    
    # 3. Tabla de Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 4. Tabla de Catálogo General de Medicamentos (Maestro)
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_med TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            stock_global INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')
    
    # 5. Tabla de Medicamentos e Inventario Asignado por Paciente
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
    
    # 6. Tabla de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    
    # 7. Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeutos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            etapa_al_momento TEXT,
            fecha_grupo TEXT,
            facilitador TEXT,
            modalidad TEXT DEFAULT 'Normal',
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')
    c.execute("PRAGMA table_info(grupos_terapeutos)")
    cols_grp = [col[1] for col in c.fetchall()]
    if 'modalidad' not in cols_grp:
        try:
            c.execute("ALTER TABLE grupos_terapeutos ADD COLUMN modalidad TEXT DEFAULT 'Normal'")
        except Exception:
            pass
            
    # 8. Tabla de Historial de Etapas
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
    
    # 9. Tabla de Requisitos por Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')
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
    c.execute("PRAGMA table_info(usuarios)")
    cols = [col[1] for col in c.fetchall()]
    
    if 'rol' in cols and 'estatus' in cols:
        c.execute('SELECT username, nombre_completo, COALESCE(rol, "Administrador"), COALESCE(estatus, "A") FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        result = c.fetchone()
        conn.close()
        if result:
            if result[3] == 'B':
                return "BLOQUEADO"
            return result
        return None
    else:
        c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        result = c.fetchone()
        conn.close()
        if result:
            return (result[0], result[1], "Administrador", "A")
        return None

def obtener_usuarios_sistema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("PRAGMA table_info(usuarios)")
    cols = [col[1] for col in c.fetchall()]
    if 'rol' in cols and 'estatus' in cols:
        c.execute('SELECT id, username, nombre_completo, COALESCE(rol, "Administrador"), COALESCE(estatus, "A") FROM usuarios ORDER BY username')
    else:
        c.execute("SELECT id, username, nombre_completo, 'Administrador' as rol, 'A' as estatus FROM usuarios ORDER BY username")
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_usuario_sistema(username, password, nombre_completo, rol, estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM usuarios WHERE username = ?', (username,))
    row = c.fetchone()
    if row:
        if password:
            c.execute('UPDATE usuarios SET password_hash = ?, nombre_completo = ?, rol = ?, estatus = ? WHERE username = ?',
                      (hash_pass(password), nombre_completo, rol, estatus, username))
        else:
            c.execute('UPDATE usuarios SET nombre_completo = ?, rol = ?, estatus = ? WHERE username = ?',
                      (nombre_completo, rol, estatus, username))
    else:
        if not password:
            conn.close()
            return False, "La contraseña es requerida para un nuevo usuario."
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  (username, hash_pass(password), nombre_completo, rol, estatus))
    conn.commit()
    conn.close()
    return True, "Usuario guardado exitosamente."

def cambiar_estatus_usuario_sistema(username, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE usuarios SET estatus = ? WHERE username = ?', (nuevo_estatus, username))
    conn.commit()
    conn.close()

def eliminar_usuario_sistema(username):
    if username == "admin":
        return False, "No se puede eliminar el usuario principal 'admin'."
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    return True, "Usuario eliminado correctamente."

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

# --- FUNCIONES DE PACIENTES / RESIDENTES ---
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
        except:
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

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', etapa_actual='ACOGIDA', fecha_inicio_etapa=None, usuario_reg='system'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ing = fecha_ingreso.strftime("%Y-%m-%d") if isinstance(fecha_ingreso, (date, datetime)) else str(fecha_ingreso)
    f_nac = fecha_nacimiento.strftime("%Y-%m-%d") if isinstance(fecha_nacimiento, (date, datetime)) else str(fecha_nacimiento)
    f_ini_etapa = fecha_inicio_etapa.strftime("%Y-%m-%d") if isinstance(fecha_inicio_etapa, (date, datetime)) else (str(fecha_inicio_etapa) if fecha_inicio_etapa else f_ing)
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, fecha_actual, usuario_reg))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_bd(filtro_estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if filtro_estatus == 'TODOS':
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, hermano_mayor_id FROM pacientes ORDER BY nombre_completo')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, hermano_mayor_id FROM pacientes WHERE estatus = ? ORDER BY nombre_completo', (filtro_estatus,))
    rows = c.fetchall()
    conn.close()
    return rows

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET estatus = ?, fecha_modificacion = ? WHERE paciente_id = ?', (nuevo_estatus, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ENTREVISTA ---
def guardar_entrevista(paciente_id, datos_dict, usuario_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos_dict, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?',
                  (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, fecha_actual, fecha_actual, usuario_reg, datos_json))
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

# --- FUNCIONES DE CATÁLOGO GENERAL Y MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre_med, presentacion, stock_global, indicaciones FROM catalogo_medicamentos ORDER BY nombre_med')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_catalogo_medicamento(nombre_med, presentacion, stock_global, indicaciones, med_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if med_id:
        c.execute('''
            UPDATE catalogo_medicamentos SET nombre_med = ?, presentacion = ?, stock_global = ?, indicaciones = ?
            WHERE id = ?
        ''', (nombre_med.strip(), presentacion.strip(), stock_global, indicaciones.strip(), med_id))
    else:
        c.execute('''
            INSERT INTO catalogo_medicamentos (nombre_med, presentacion, stock_global, indicaciones)
            VALUES (?, ?, ?, ?)
        ''', (nombre_med.strip(), presentacion.strip(), stock_global, indicaciones.strip()))
    conn.commit()
    conn.close()

def eliminar_catalogo_medicamento(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ? WHERE paciente_id = ?',
                  (meds_json, observaciones, fecha_actual, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)',
                  (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario_reg))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        meds = json.loads(row[0]) if row[0] else []
        obs = row[1] if row[1] else ""
        return meds, obs
    return [], ""

def registrar_entrega_medicamento(paciente_id, entregado_por, detalle_entrega, meds_actualizados, obs_actualizadas):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_entrega, ensure_ascii=False)
    
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, fecha_actual, entregado_por, detalle_json))
              
    meds_json = json.dumps(meds_actualizados, ensure_ascii=False)
    c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (meds_json, obs_actualizadas, fecha_actual, paciente_id))
              
    conn.commit()
    conn.close()

def listar_entregas_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, fecha_entrega, entregado_por, detalle_json FROM entregas_medicamentos WHERE paciente_id = ? ORDER BY id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, modalidad, datos, usuario_reg, grupo_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_grp = fecha_grupo.strftime("%Y-%m-%d") if isinstance(fecha_grupo, (date, datetime)) else str(fecha_grupo)
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    if grupo_id:
        c.execute('''
            UPDATE grupos_terapeutos SET paciente_id = ?, tipo_grupo = ?, etapa_al_momento = ?, fecha_grupo = ?, facilitador = ?, modalidad = ?, datos_json = ?, usuario_registro = ?
            WHERE id = ?
        ''', (paciente_id, tipo_grupo, etapa_al_momento, f_grp, facilitador, modalidad, datos_json, usuario_reg, grupo_id))
    else:
        c.execute('''
            INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, modalidad, datos_json, fecha_registro, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, tipo_grupo, etapa_al_momento, f_grp, facilitador, modalidad, datos_json, fecha_actual, usuario_reg))
    conn.commit()
    conn.close()

def eliminar_grupo_terapeuto(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM grupos_terapeutos WHERE id = ?', (grupo_id,))
    conn.commit()
    conn.close()

def contar_grupos_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM grupos_terapeutos 
        WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?
    ''', (paciente_id, etapa, tipo_grupo))
    count = c.fetchone()[0]
    conn.close()
    return count

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("PRAGMA table_info(grupos_terapeutos)")
    cols = [col[1] for col in c.fetchall()]
    if 'modalidad' in cols:
        c.execute('''
            SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro, COALESCE(modalidad, 'Normal')
            FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC
        ''', (paciente_id,))
    else:
        c.execute('''
            SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro, 'Normal' as modalidad
            FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC
        ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ETAPAS Y PROCESO ---
def cambiar_etapa_paciente(paciente_id, etapa_origen, etapa_destino, usuario_autoriza):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (etapa_destino, f_hoy, fecha_actual, paciente_id))
              
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario_autoriza))
              
    conn.commit()
    conn.close()

def obtener_historial_etapas(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza FROM historial_etapas WHERE paciente_id = ? ORDER BY id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ?', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (hermano_mayor_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def soltar_hermano_mayor(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET hermano_mayor_id = NULL, fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (f_hoy, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

# --- CLASE PDF BASE ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "🌱 Sawabona Shikoba - Comunidad Terapéutica", new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 5, "Sistema Integral de Control y Seguimiento Clínico", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(3)
        self.line(10, self.get_y(), self.epw + 10, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}} | Expediente Confidencial", align="C")

def generar_pdf_entrevista(paciente_id):
    p = obtener_paciente(paciente_id)
    if not p:
        return None
    e_data = obtener_entrevista(paciente_id)
    if not e_data:
        return None
        
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "EXPEDIENTE INICIAL DE CONSEJERÍA Y EVALUACIÓN", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"DATOS GENERALES DEL PACIENTE ({paciente_id})", border="B", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw/2, 5, f"Nombre Completo: {limpiar_texto(p[1])}")
    pdf.cell(pdf.epw/2, 5, f"Estatus: {'Activo' if p[5]=='A' else 'Inactivo'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw/2, 5, f"Fecha de Ingreso: {p[2]}")
    pdf.cell(pdf.epw/2, 5, f"Fecha Nacimiento: {p[3]}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw/2, 5, f"Sexo: {p[4]}")
    pdf.cell(pdf.epw/2, 5, f"Etapa Actual: {p[7]}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    for sec_key, sec_val in e_data.items():
        if isinstance(sec_val, dict):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, limpiar_texto(sec_key).upper(), border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            for k, v in sec_val.items():
                if isinstance(v, list):
                    v_str = ", ".join([str(x) for x in v])
                else:
                    v_str = str(v)
                pdf.multi_cell(pdf.epw, 5, f"• {limpiar_texto(k)}: {limpiar_texto(v_str)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            
    pdf_filename = f"Entrevista_{paciente_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_general_meds():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTA GENERAL DE MEDICAMENTOS Y DOSIS (TODOS LOS PACIENTES)", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de impresión: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pacientes = listar_pacientes_bd('A')
    
    for p in pacientes:
        pid, pnom = p[0], p[1]
        meds, obs = obtener_medicamentos_paciente(pid)
        if meds:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(pnom)} ({pid}) - Etapa: {p[7]}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "B", 8)
            col_w = [45, 20, 20, 20, 25, 25, 35]
            pdf.cell(col_w[0], 5, "Medicamento", border=1)
            pdf.cell(col_w[1], 5, "Mañana", border=1, align="C")
            pdf.cell(col_w[2], 5, "Tarde", border=1, align="C")
            pdf.cell(col_w[3], 5, "Noche", border=1, align="C")
            pdf.cell(col_w[4], 5, "Total Dosis", border=1, align="C")
            pdf.cell(col_w[5], 5, "Existencia", border=1, align="C")
            pdf.cell(col_w[6], 5, "Indicaciones", border=1, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", "", 8)
            for m in meds:
                nom = m.get("nombre", "")
                m_d = str(m.get("manana", 0))
                t_d = str(m.get("tarde", 0))
                n_d = str(m.get("noche", 0))
                tot = str(m.get("total_dosis", 0))
                exi = str(m.get("existencia", 0))
                ind = str(m.get("indicaciones", ""))
                
                pdf.cell(col_w[0], 5, limpiar_texto(nom[:22]), border=1)
                pdf.cell(col_w[1], 5, m_d, border=1, align="C")
                pdf.cell(col_w[2], 5, t_d, border=1, align="C")
                pdf.cell(col_w[3], 5, n_d, border=1, align="C")
                pdf.cell(col_w[4], 5, tot, border=1, align="C")
                pdf.cell(col_w[5], 5, exi, border=1, align="C")
                pdf.cell(col_w[6], 5, limpiar_texto(ind[:20]), border=1, new_x="LMARGIN", new_y="NEXT")
            if obs:
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(obs)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            
    pdf_filename = f"Lista_General_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_entrega_meds(paciente_id, pnom, detalle_entrega, entregado_por):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "COMPROBANTE DE SURTIDO / ENTREGA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"DATOS DE LA ENTREGA - PACIENTE: {limpiar_texto(pnom)} ({paciente_id})", border="B", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw/2, 5, f"Fecha de Entrega: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    pdf.cell(pdf.epw/2, 5, f"Entregado por (Staff): {limpiar_texto(entregado_por)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [70, 45, 45]
    pdf.cell(col_w[0], 6, "Medicamento", border=1)
    pdf.cell(col_w[1], 6, "Cantidad Entregada", border=1, align="C")
    pdf.cell(col_w[2], 6, "Existencia Restante", border=1, new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf.set_font("Helvetica", "", 9)
    for item in detalle_entrega:
        pdf.cell(col_w[0], 6, limpiar_texto(item['nombre']), border=1)
        pdf.cell(col_w[1], 6, str(item['cant_entregada']), border=1, align="C")
        pdf.cell(col_w[2], 6, str(item['existencia_restante']), border=1, new_x="LMARGIN", new_y="NEXT", align="C")
        
    pdf.ln(10)
    pdf.cell(pdf.epw/2, 10, "_______________________________", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(pdf.epw/2, 5, f"Firma Staff: {limpiar_texto(entregado_por)}", align="C")
    
    pdf_filename = f"Comprobante_Entrega_{paciente_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_historial_grupos(paciente_id):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p = obtener_paciente(paciente_id)
    pnom = p[1] if p else paciente_id
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE GRUPOS TERAPEUTICOS - {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresion: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    grupos = listar_grupos_paciente(paciente_id)
    if not grupos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay sesiones de grupos registrados para este paciente.", align="C")
    else:
        for g in grupos:
            gid, tgrp, etapa, fgrp, fac, djson, freg, ureg, mod = g
            datos = json.loads(djson)
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"GRUPO: {limpiar_texto(tgrp)} ({mod}) | Etapa: {etapa} | Fecha: {fgrp} | Facilitador: {limpiar_texto(fac)}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            
            if tgrp in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                pdf.multi_cell(pdf.epw, 5, f"Compartimiento: {limpiar_texto(datos.get('compartimiento', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(datos.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(datos.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
            else: # Feedback
                pdf.multi_cell(pdf.epw, 5, f"Logros: {limpiar_texto(datos.get('logros', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Dificultades: {limpiar_texto(datos.get('dificultades', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(datos.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(datos.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
            
    pdf_filename = f"Expediente_Grupos_{paciente_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR DB Y ESTADO ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = "Administrador"

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: gray;'>Sistema Integral de Control y Seguimiento Clínico</h3>", unsafe_allow_html=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submit:
                res_login = verificar_login(user_input, pass_input)
                if res_login == "BLOQUEADO":
                    st.error("❌ La cuenta de este usuario se encuentra temporalmente bloqueada/inactiva (periodo de vacaciones). Contacte al Administrador.")
                elif res_login:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res_login[0]
                    st.session_state["nombre_completo"] = res_login[1]
                    st.session_state["rol"] = res_login[2]
                    st.toast("🎉 ¡Acceso concedido!")
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL CON LAS 12 OPCIONES DEL MENÚ ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Staff**: {st.session_state['nombre_completo']} ({st.session_state.get('rol', 'Administrador')})")
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["nombre_completo"] = ""
        st.session_state["rol"] = "Administrador"
        st.rerun()
        
    st.sidebar.divider()
    
    menu = st.sidebar.radio(
        "Navegación del Sistema",
        [
            "👤 Registro y Edición de Usuarios",
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "📦 Catálogo General de Medicamentos",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "📦 Respaldo y Restauración",
            "👥 Usuarios y Roles del Sistema",
            "⚙️ Configuración / Seguridad"
        ]
    )
    
    # ==========================================
    # --- MÓDULO 1: REGISTRO Y EDICIÓN DE PACIENTES/USUARIOS ---
    # ==========================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes y Servidores")
        st.caption("Captura de expediente basal de pacientes o servidores de la comunidad")
        
        modo_u = st.radio("Acción:", ["🆕 Registrar Nuevo", "✏️ Editar Existente"], horizontal=True)
        
        pacientes_todos = listar_pacientes_bd('TODOS')
        p_edit = None
        edit_pid = None
        
        if modo_u == "✏️ Editar Existente":
            if not pacientes_todos:
                st.info("No hay pacientes registrados.")
            else:
                dict_p = {f"{p[1]} ({p[0]}) - Estatus: {'Activo' if p[5]=='A' else 'Inactivo'}": p[0] for p in pacientes_todos}
                sel_p_str = st.selectbox("🔑 Selecciona el Paciente a Editar", list(dict_p.keys()))
                edit_pid = dict_p[sel_p_str]
                p_edit = obtener_paciente(edit_pid)
                
        with st.form("form_paciente"):
            c1, c2, c3 = st.columns(3)
            with c1:
                val_id = p_edit[0] if p_edit else generar_siguiente_folio()
                f_id = st.text_input("Folio ID (Autogenerado)", value=val_id, disabled=True)
                val_nom = p_edit[1] if p_edit else ""
                f_nom = st.text_input("Nombre Completo *", value=val_nom)
            with c2:
                val_ing = datetime.strptime(p_edit[2], "%Y-%m-%d").date() if p_edit and p_edit[2] else date.today()
                f_ingreso = st.date_input("Fecha de Ingreso *", value=val_ing)
                val_nac = datetime.strptime(p_edit[3], "%Y-%m-%d").date() if p_edit and p_edit[3] else date(1995, 1, 1)
                f_nacimiento = st.date_input("Fecha de Nacimiento *", value=val_nac)
            with c3:
                sexo_opts = ["Masculino", "Femenino"]
                idx_s = sexo_opts.index(p_edit[4]) if p_edit and p_edit[4] in sexo_opts else 0
                f_sexo = st.selectbox("Sexo *", sexo_opts, index=idx_s)
                
                tipo_opts = ["Paciente", "Servidor"]
                idx_t = tipo_opts.index(p_edit[6]) if p_edit and p_edit[6] in tipo_opts else 0
                f_tipo = st.selectbox("Tipo de Usuario *", tipo_opts, index=idx_t)
                
            st.divider()
            c4, c5 = st.columns(2)
            with c4:
                estatus_opts = ["Activo (A)", "Inactivo (I)"]
                idx_est = 0 if (p_edit and p_edit[5] == 'A') or not p_edit else 1
                f_estatus_sel = st.selectbox("Estatus del Paciente *", estatus_opts, index=idx_est)
                f_estatus = 'A' if f_estatus_sel.startswith("Activo") else 'I'
            with c5:
                etapas_list = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_et = etapas_list.index(p_edit[7]) if p_edit and p_edit[7] in etapas_list else 0
                f_etapa = st.selectbox("Etapa Inicial / Actual *", etapas_list, index=idx_et)
                
            btn_guardar_p = st.form_submit_button("💾 Guardar Registro de Paciente", use_container_width=True)
            
            if btn_guardar_p:
                if not f_nom.strip():
                    st.error("⚠️ El nombre completo es obligatorio.")
                else:
                    dup = verificar_duplicado_nombre(f_nom, edit_pid)
                    if dup and modo_u == "🆕 Registrar Nuevo":
                        st.error(f"⚠️ Ya existe un paciente registrado con el nombre **{dup[1]}** (Folio: `{dup[0]}`).")
                    else:
                        guardar_usuario_paciente(f_id, f_nom, f_ingreso, f_nacimiento, f_sexo, f_estatus, f_tipo, f_etapa, usuario_reg=st.session_state["username"])
                        st.toast("🎉 ¡Registro guardado exitosamente!")
                        st.success(f"✅ ¡Paciente **{f_nom}** ({f_id}) guardado exitosamente!")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 2: NUEVA ENTREVISTA / EDITAR ---
    # ==========================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Cuestionario clínico de admisión, antecedentes de consumo y disposición al cambio")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay pacientes activos para realizar entrevistas.")
        else:
            dict_p_ent = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_activos}
            sel_p_ent = st.selectbox("🔑 Selecciona el Paciente", list(dict_p_ent.keys()))
            p_id_ent = dict_p_ent[sel_p_ent]
            
            ent_prev = obtener_entrevista(p_id_ent) or {}
            
            with st.form("form_entrevista_inicial"):
                st.subheader("I. Datos Socio-Demográficos & Ocupacionales")
                sec1 = ent_prev.get("socio_demografico", {})
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    estado_civil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                    ocupacion = st.text_input("Ocupación habitual", value=sec1.get("ocupacion", ""))
                with c_e2:
                    nivel_estudios = st.selectbox("Nivel de Estudios", ["Primaria", "Secundaria", "Preparatoria", "Licenciatura / Técnica", "Ninguno"], index=0)
                    vive_con = st.text_input("¿Con quién vive actualmente?", value=sec1.get("vive_con", ""))
                    
                st.divider()
                st.subheader("II. Historial de Consumo de Sustancias")
                sec2 = ent_prev.get("historial_consumo", {})
                sustancias_list = ["Alcohol", "Tabaco", "Cannabis", "Metanfetaminas (Cristal)", "Cocaína", "Opioides", "Inhalables", "Benzodiacepinas"]
                prev_sust = sec2.get("sustancias_usadas", [])
                sust_sel = st.multiselect("Sustancias de Consumo Usadas", sustancias_list, default=[s for s in prev_sust if s in sustancias_list])
                
                c_c1, c_c2 = st.columns(2)
                with c_c1:
                    edad_inicio = st.number_input("Edad de inicio de consumo", min_value=5, max_value=80, value=int(sec2.get("edad_inicio", 15)))
                    sustancia_principal = st.selectbox("Sustancia de Mayor Impacto / Principal", sustancias_list, index=0)
                with c_c2:
                    frecuencia_consumo = st.selectbox("Frecuencia de Consumo Reciente", ["Diario", "3-5 veces por semana", "Fines de semana", "Ocasional / Binge"], index=0)
                    ultimo_consumo = st.date_input("Fecha del Último Consumo", value=date.today())
                    
                st.divider()
                st.subheader("III. Motivación y Disposición al Cambio")
                sec3 = ent_prev.get("motivacion", {})
                motivo_ingreso = st.text_area("Motivo principal de ingreso (palabras del paciente)", value=sec3.get("motivo_ingreso", ""))
                intentos_previos = st.number_input("Número de tratamientos / internamientos previos", min_value=0, max_value=30, value=int(sec3.get("intentos_previos", 0)))
                
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                
                if btn_save_ent:
                    datos_ent = {
                        "socio_demografico": {
                            "estado_civil": estado_civil,
                            "ocupacion": ocupacion,
                            "nivel_estudios": nivel_estudios,
                            "vive_con": vive_con
                        },
                        "historial_consumo": {
                            "sustancias_usadas": sust_sel,
                            "edad_inicio": edad_inicio,
                            "sustancia_principal": sustancia_principal,
                            "frecuencia_consumo": frecuencia_consumo,
                            "ultimo_consumo": str(ultimo_consumo)
                        },
                        "motivacion": {
                            "motivo_ingreso": motivo_ingreso,
                            "intentos_previos": intentos_previos
                        }
                    }
                    guardar_entrevista(p_id_ent, datos_ent, st.session_state["username"])
                    st.toast("🎉 ¡Entrevista guardada exitosamente!")
                    st.success("✅ ¡Entrevista inicial registrada exitosamente!")

    # ==========================================
    # --- MÓDULO 3: BUSCAR Y LISTAR PACIENTES ---
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio General y Expedientes de Pacientes")
        st.caption("Consulta de expediente completo, filtro por estatus e impresión de entrevistas")
        
        filtro_e = st.radio("Filtro de Estatus:", ["Activos únicamente", "Inactivos únicamente", "Mostrar Todos"], horizontal=True)
        f_code = 'A' if filtro_e.startswith("Activos") else ('I' if filtro_e.startswith("Inactivos") else 'TODOS')
        
        pacientes_list = listar_pacientes_bd(f_code)
        
        if not pacientes_list:
            st.info("No se encontraron registros de pacientes con el filtro seleccionado.")
        else:
            for p in pacientes_list:
                pid, pnom, fing, fnac, psex, pest, ptipo, petapa, phermano = p
                badge = "🟢 Activo" if pest == 'A' else "🔴 Inactivo"
                
                with st.expander(f"👤 **{pnom}** ({pid}) | Estatus: {badge} | Etapa: **{petapa}** | Tipo: {ptipo}"):
                    c_l1, c_l2 = st.columns(2)
                    with c_l1:
                        st.write(f"**Fecha de Ingreso:** {fing}")
                        st.write(f"**Fecha de Nacimiento:** {fnac}")
                        st.write(f"**Sexo:** {psex}")
                    with c_l2:
                        st.write(f"**Hermano Mayor ID:** {phermano if phermano else 'Sin asignar'}")
                        if pest == 'A':
                            if st.button("🔴 Dar de Baja / Inactivar", key=f"btn_inact_{pid}"):
                                cambiar_estatus_paciente(pid, 'I')
                                st.toast(f"Paciente {pid} dado de baja.")
                                st.rerun()
                        else:
                            if st.button("🟢 Reactivar Paciente", key=f"btn_act_{pid}"):
                                cambiar_estatus_paciente(pid, 'A')
                                st.toast(f"Paciente {pid} reactivado.")
                                st.rerun()
                                
                    st.divider()
                    pdf_ent = generar_pdf_entrevista(pid)
                    if pdf_ent:
                        with open(pdf_ent, "rb") as f:
                            st.download_button(
                                label="🖨️ Descargar Entrevista Inicial (PDF)",
                                data=f,
                                file_name=pdf_ent,
                                mime="application/pdf",
                                key=f"dl_pdf_ent_{pid}"
                            )
                    else:
                        st.caption("⚠️ Este paciente aún no tiene Entrevista Inicial registrada.")

    # ==========================================
    # --- MÓDULO 4: GESTIÓN DE ETAPAS & PROCESO ---
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas del Programa & Proceso")
        st.caption("Verificación de requisitos por etapa, asignación de Hermano Mayor y promoción")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados.")
        else:
            dict_p_et = {f"{p[1]} ({p[0]}) - Etapa Actual: {p[7]}": p for p in pacientes_activos}
            sel_p_et = st.selectbox("🔑 Selecciona el Paciente a Gestionar", list(dict_p_et.keys()))
            p_curr = dict_p_et[sel_p_et]
            pid_et, pnom_et, petapa_curr = p_curr[0], p_curr[1], p_curr[7]
            
            tab_et1, tab_et2, tab_et3 = st.tabs(["📋 Checklist y Requisitos", "🤝 Hermano Mayor / Menor", "📜 Historial de Cambios"])
            
            with tab_et1:
                st.subheader(f"Requisitos Teóricos y Grupos para Etapa: **{petapa_curr}**")
                reqs = obtener_requisitos_etapa(petapa_curr)
                if not reqs:
                    st.info(f"No hay requisitos registrados para la etapa {petapa_curr}.")
                else:
                    for rid, rtxt, esg in reqs:
                        if esg == 1:
                            if "Aquí y Ahora" in rtxt:
                                cant = contar_grupos_etapa(pid_et, petapa_curr, "Aquí y Ahora")
                            elif "Terapia de Grupo" in rtxt:
                                cant = contar_grupos_etapa(pid_et, petapa_curr, "Terapia de Grupo")
                            elif "Feedbacks" in rtxt:
                                cant = contar_grupos_etapa(pid_et, petapa_curr, "Feedback")
                            else:
                                cant = 0
                            st.write(f"• **{rtxt}**: Asistencias completadas: `{cant}`")
                        else:
                            st.checkbox(f"• {rtxt}", key=f"chk_req_{rid}")
                            
                st.divider()
                st.subheader("Promoción / Cambio de Etapa")
                etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                curr_idx = etapas_orden.index(petapa_curr) if petapa_curr in etapas_orden else 0
                
                if curr_idx < len(etapas_orden) - 1:
                    siguiente_etapa = etapas_orden[curr_idx + 1]
                    if st.button(f"🚀 Promover a Siguiente Etapa: **{siguiente_etapa}**", use_container_width=True):
                        cambiar_etapa_paciente(pid_et, petapa_curr, siguiente_etapa, st.session_state["username"])
                        st.toast(f"🎉 ¡Paciente promovido a {siguiente_etapa}!")
                        st.success(f"✅ ¡{pnom_et} ha sido promovido exitosamente a **{siguiente_etapa}**!")
                        st.balloons()
                        st.rerun()
                else:
                    st.success("🎉 ¡El paciente se encuentra en la etapa final de SERVICIO SOCIAL!")
                    
            with tab_et2:
                st.subheader("Asignación y Suelta de Hermano Mayor")
                p_info_full = obtener_paciente(pid_et)
                hm_id = p_info_full[9]
                f_suelta = p_info_full[10]
                
                if hm_id:
                    hm_info = obtener_paciente(hm_id)
                    hm_nom = hm_info[1] if hm_info else hm_id
                    st.success(f"🤝 **Hermano Mayor Asignado:** {hm_nom} (`{hm_id}`)")
                    if st.button("🔓 Realizar Suelta de Hermano Mayor"):
                        soltar_hermano_mayor(pid_et)
                        st.toast("Suelta de Hermano realizada.")
                        st.rerun()
                else:
                    if f_suelta:
                        st.info(f"ℹ️ Este paciente tuvo suelta de hermano el: **{f_suelta}**.")
                    st.write("Selecciona un residente en etapa avanzada para asignarlo como Hermano Mayor:")
                    posibles_hm = [p for p in pacientes_activos if p[0] != pid_et]
                    if posibles_hm:
                        dict_hm = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in posibles_hm}
                        sel_hm = st.selectbox("Seleccionar Hermano Mayor", list(dict_hm.keys()))
                        if st.button("🤝 Asignar Hermano Mayor"):
                            asignar_hermano_mayor(pid_et, dict_hm[sel_hm])
                            st.toast("Hermano Mayor asignado.")
                            st.rerun()

            with tab_et3:
                st.subheader("Historial de Transiciones de Etapa")
                h_etapas = obtener_historial_etapas(pid_et)
                if not h_etapas:
                    st.info("Sin historial de cambios de etapa registrados.")
                else:
                    for e_orig, e_dest, f_cambio, u_aut in h_etapas:
                        st.write(f"• **{f_cambio}**: Cambio de `{e_orig}` ➔ **`{e_dest}`** (Autorizado por: {u_aut})")

    # ==========================================
    # --- MÓDULO 5: REGISTRO DE GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Módulo para capturar, modificar, eliminar y consultar sesiones de Terapia de Grupo, Aquí y Ahora, Feedback y Confronto Especial")
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar / Editar Sesión de Grupo", "📜 Historial, Conteo y PDF"])
        
        with tab_reg_g:
            pacientes_activos = listar_pacientes_bd('A')
            if not pacientes_activos:
                st.warning("No hay pacientes activos registrados.")
            else:
                dict_pac_g = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1], p[7]) for p in pacientes_activos}
                sel_pac_g = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_g.keys()), key="sel_grp_pac")
                p_id_g, p_nombre_g, p_etapa_g = dict_pac_g[sel_pac_g]
                
                modo_grp = st.radio("Acción a Realizar:", ["🆕 Capturar Nueva Sesión", "✏️ Editar / Modificar Sesión Existente"], horizontal=True)
                
                grupos_prev = listar_grupos_paciente(p_id_g)
                g_edit_data = None
                edit_gid = None
                
                if modo_grp == "✏️ Editar / Modificar Sesión Existente":
                    if not grupos_prev:
                        st.info("Este paciente no tiene sesiones de grupo registradas para editar.")
                    else:
                        dict_g_edit = {f"ID: {g[0]} | {g[1]} ({g[8]}) | Fecha: {g[3]} | Facilitador: {g[4]}": g for g in grupos_prev}
                        sel_g_edit_str = st.selectbox("🔑 Selecciona la Sesión de Grupo a Modificar", list(dict_g_edit.keys()))
                        g_edit_data = dict_g_edit[sel_g_edit_str]
                        edit_gid = g_edit_data[0]
                        
                tipo_opts_g = ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Confronto Especial"]
                idx_t_g = 0
                if g_edit_data and g_edit_data[1] in tipo_opts_g:
                    idx_t_g = tipo_opts_g.index(g_edit_data[1])
                tipo_grupo = st.selectbox("🗣️ Tipo de Grupo Terapéutico", tipo_opts_g, index=idx_t_g)
                
                with st.form("form_grupo_terapeuto"):
                    st.subheader(f"Formulario: {tipo_grupo}")
                    c_g1, c_g2, c_g3 = st.columns(3)
                    with c_g1:
                        st.text_input("Paciente", value=p_nombre_g, disabled=True)
                        st.text_input("Folio", value=p_id_g, disabled=True)
                    with c_g2:
                        val_et_g = g_edit_data[2] if g_edit_data else p_etapa_g
                        st.text_input("Etapa del Paciente al Momento del Grupo", value=val_et_g, disabled=True)
                        val_f_g = datetime.strptime(g_edit_data[3], "%Y-%m-%d").date() if g_edit_data and g_edit_data[3] else date.today()
                        f_grupo = st.date_input("Fecha del Grupo", value=val_f_g)
                    with c_g3:
                        val_fac_g = g_edit_data[4] if g_edit_data else st.session_state["nombre_completo"]
                        facilitador_nombre = st.text_input("Nombre del Facilitador / Staff *", value=val_fac_g)
                        
                        mod_opts = ["Normal", "Especial"]
                        idx_m = 0
                        if g_edit_data and len(g_edit_data) > 8 and g_edit_data[8] == "Especial":
                            idx_m = 1
                        modalidad_grupo = st.selectbox("Modalidad del Grupo *", mod_opts, index=idx_m)
                        
                    st.divider()
                    
                    datos_g_prev = json.loads(g_edit_data[5]) if g_edit_data else {}
                    
                    if tipo_grupo in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                        compartimiento = st.text_area("Compartimiento (Texto largo) *", value=datos_g_prev.get("compartimiento", ""))
                        observaciones = st.text_area("Observaciones (Texto largo)", value=datos_g_prev.get("observaciones", ""))
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=datos_g_prev.get("devoluciones", ""))
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=datos_g_prev.get("compromiso", ""))
                        
                        btn_guardar_grupo = st.form_submit_button(f"💾 Guardar Registro de {tipo_grupo}", use_container_width=True)
                        
                        if btn_guardar_grupo:
                            if not facilitador_nombre or not compartimiento or not compromiso:
                                st.error("⚠️ Facilitador, Compartimiento y Compromiso son campos obligatorios.")
                            else:
                                datos_grp = {
                                    "compartimiento": compartimiento,
                                    "observaciones": observaciones,
                                    "devoluciones": devoluciones,
                                    "compromiso": compromiso
                                }
                                guardar_grupo_terapeuto(p_id_g, tipo_grupo, val_et_g, f_grupo, facilitador_nombre, modalidad_grupo, datos_grp, st.session_state["username"], edit_gid)
                                st.toast(f"🎉 ¡Sesión de {tipo_grupo} registrada exitosamente!")
                                st.success(f"✅ ¡Sesión de **{tipo_grupo}** ({modalidad_grupo}) guardada exitosamente para **{p_nombre_g}** ({p_id_g})!")
                                st.balloons()
                                st.rerun()
                    else: # Feedback
                        logros = st.text_area("Logros (Texto largo) *", value=datos_g_prev.get("logros", ""))
                        dificultades = st.text_area("Dificultades (Texto largo) *", value=datos_g_prev.get("dificultades", ""))
                        observaciones = st.text_area("Observaciones (Texto largo)", value=datos_g_prev.get("observaciones", ""))
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=datos_g_prev.get("devoluciones", ""))
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=datos_g_prev.get("compromiso", ""))
                        
                        btn_guardar_grupo = st.form_submit_button("💾 Guardar Registro de Feedback", use_container_width=True)
                        
                        if btn_guardar_grupo:
                            if not facilitador_nombre or not logros or not dificultades or not compromiso:
                                st.error("⚠️ Facilitador, Logros, Dificultades y Compromiso son campos obligatorios.")
                            else:
                                datos_grp = {
                                    "logros": logros,
                                    "dificultades": dificultades,
                                    "observaciones": observaciones,
                                    "devoluciones": devoluciones,
                                    "compromiso": compromiso
                                }
                                guardar_grupo_terapeuto(p_id_g, tipo_grupo, val_et_g, f_grupo, facilitador_nombre, modalidad_grupo, datos_grp, st.session_state["username"], edit_gid)
                                st.toast("🎉 ¡Sesión de Feedback registrada exitosamente!")
                                st.success(f"✅ ¡Sesión de **Feedback** ({modalidad_grupo}) guardada exitosamente para **{p_nombre_g}** ({p_id_g})!")
                                st.balloons()
                                st.rerun()

        with tab_hist_g:
            pacientes_todos = listar_pacientes_bd('TODOS')
            if not pacientes_todos:
                st.info("No hay pacientes registrados.")
            else:
                dict_hist = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_todos}
                sel_h = st.selectbox("🔑 Selecciona el Paciente para Ver Expediente de Grupos", list(dict_hist.keys()))
                p_info_h = dict_hist[sel_h]
                p_id_h = p_info_h[0]
                p_etapa_h = p_info_h[7]
                
                col_mc1, col_mc2, col_mc3, col_mc4 = st.columns(4)
                with col_mc1:
                    cnt_tg = contar_grupos_etapa(p_id_h, p_etapa_h, "Terapia de Grupo")
                    st.metric("Terapia de Grupo", f"{cnt_tg} sesiones", help=f"En etapa {p_etapa_h}")
                with col_mc2:
                    cnt_aa = contar_grupos_etapa(p_id_h, p_etapa_h, "Aquí y Ahora")
                    st.metric("Aquí y Ahora", f"{cnt_aa} sesiones", help=f"En etapa {p_etapa_h}")
                with col_mc3:
                    cnt_fb = contar_grupos_etapa(p_id_h, p_etapa_h, "Feedback")
                    st.metric("Feedback", f"{cnt_fb} sesiones", help=f"En etapa {p_etapa_h}")
                with col_mc4:
                    cnt_ce = contar_grupos_etapa(p_id_h, p_etapa_h, "Confronto Especial")
                    st.metric("Confronto Especial", f"{cnt_ce} sesiones", help=f"En etapa {p_etapa_h}")
                    
                st.divider()
                pdf_grp = generar_pdf_historial_grupos(p_id_h)
                with open(pdf_grp, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Expediente Completo de Grupos en PDF",
                        data=f,
                        file_name=pdf_grp,
                        mime="application/pdf",
                        key=f"pdf_grp_{p_id_h}"
                    )
                    
                st.divider()
                grupos_list = listar_grupos_paciente(p_id_h)
                if not grupos_list:
                    st.warning("Este paciente no tiene sesiones de grupo registradas.")
                else:
                    for g in grupos_list:
                        gid, tgrp, etapa, fgrp, fac, djson, freg, ureg, mod = g
                        datos = json.loads(djson)
                        with st.expander(f"🗣️ **{tgrp}** (`{mod}`) | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"):
                            st.write(f"**Registrado por:** {ureg} el {freg}")
                            if tgrp in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                                st.write(f"**Compartimiento:** {datos.get('compartimiento', '')}")
                                st.write(f"**Observaciones:** {datos.get('observaciones', '')}")
                                st.write(f"**Devoluciones:** {datos.get('devoluciones', '')}")
                                st.write(f"**¿Cómo se queda y compromiso?:** {datos.get('compromiso', '')}")
                            else:
                                st.write(f"**Logros:** {datos.get('logros', '')}")
                                st.write(f"**Dificultades:** {datos.get('dificultades', '')}")
                                st.write(f"**Observaciones:** {datos.get('observaciones', '')}")
                                st.write(f"**Devoluciones:** {datos.get('devoluciones', '')}")
                                st.write(f"**¿Cómo se queda y compromiso?:** {datos.get('compromiso', '')}")
                                
                            st.divider()
                            if st.button("🗑️ Eliminar esta Sesión", key=f"btn_del_grp_{gid}"):
                                eliminar_grupo_terapeuto(gid)
                                st.toast(f"Sesión {gid} eliminada.")
                                st.rerun()

    # ==========================================
    # --- MÓDULO 6: CATÁLOGO GENERAL DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "📦 Catálogo General de Medicamentos":
        st.title("📦 Catálogo Maestro de Medicamentos e Inventario Global")
        st.caption("Administración del catálogo maestro de farmacia de la comunidad")
        
        tab_cat1, tab_cat2 = st.tabs(["📋 Ver Catálogo Maestro", "➕ Agregar / Editar Medicamento"])
        
        with tab_cat1:
            cat_meds = obtener_catalogo_medicamentos()
            if not cat_meds:
                st.info("No hay medicamentos registrados en el catálogo general.")
            else:
                for cm in cat_meds:
                    cm_id, cm_nom, cm_pres, cm_stock, cm_ind = cm
                    st_badge = "🔴 Alerta Stock Bajo" if cm_stock < 10 else "🟢 Disponible"
                    
                    with st.expander(f"💊 **{cm_nom}** ({cm_pres}) | Stock Global: **{cm_stock}** unidades | Estatus: {st_badge}"):
                        st.write(f"**Indicaciones / Usos:** {cm_ind if cm_ind else 'Sin especificación'}")
                        if st.button("🗑️ Eliminar del Catálogo", key=f"del_cat_{cm_id}"):
                            eliminar_catalogo_medicamento(cm_id)
                            st.toast(f"Medicamento {cm_nom} eliminado del catálogo.")
                            st.rerun()
                            
        with tab_cat2:
            st.subheader("Registrar Nuevo Medicamento en Catálogo Maestro")
            with st.form("form_add_catalogo"):
                c_m1, c_m2 = st.columns(2)
                with c_m1:
                    cat_nom = st.text_input("Nombre Comercial / Genérico del Medicamento *")
                    cat_pres = st.text_input("Presentación (ej. Tabletas 500mg, Jarabe) *")
                with c_m2:
                    cat_stock = st.number_input("Stock Global Inicial en Farmacia", min_value=0, value=100)
                    cat_ind = st.text_input("Indicaciones / Pauta habitual")
                    
                btn_cat_save = st.form_submit_button("💾 Guardar en Catálogo Maestro", use_container_width=True)
                
                if btn_cat_save:
                    if not cat_nom.strip() or not cat_pres.strip():
                        st.error("⚠️ El nombre y la presentación del medicamento son obligatorios.")
                    else:
                        guardar_catalogo_medicamento(cat_nom, cat_pres, cat_stock, cat_ind)
                        st.toast(f"🎉 ¡{cat_nom} agregado al catálogo maestro!")
                        st.success(f"✅ ¡Medicamento **{cat_nom}** guardado exitosamente!")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 7: CONTROL DE MEDICAMENTOS Y DOSIS ---
    # ==========================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Prescripción e Inventario Individual por Paciente")
        st.caption("Asignación de esquema de dosis (Mañana, Tarde, Noche) e inventario asignado a cada paciente")
        
        st.subheader("🖨️ Lista General de Prescripciones")
        pdf_gen_meds = generar_pdf_lista_general_meds()
        with open(pdf_gen_meds, "rb") as f:
            st.download_button(
                label="📄 Imprimir Lista General (PDF) - Todos los Pacientes Alfabéticamente",
                data=f,
                file_name=pdf_gen_meds,
                mime="application/pdf",
                key="btn_pdf_gen_meds"
            )
            
        st.divider()
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados.")
        else:
            dict_p_med = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1]) for p in pacientes_activos}
            sel_p_med = st.selectbox("🔑 Selecciona el Paciente para Prescripción", list(dict_p_med.keys()))
            p_id_med, p_nom_med = dict_p_med[sel_p_med]
            
            meds_curr, obs_curr = obtener_medicamentos_paciente(p_id_med)
            
            st.subheader(f"Configurar Esquema de Dosis para: **{p_nom_med}** ({p_id_med})")
            
            cat_maestro = obtener_catalogo_medicamentos()
            cat_list_names = [cm[1] for cm in cat_maestro] if cat_maestro else []
            
            if "temp_meds_list" not in st.session_state or st.session_state.get("curr_p_med") != p_id_med:
                st.session_state["temp_meds_list"] = meds_curr
                st.session_state["curr_p_med"] = p_id_med
                
            st.write("Medicamentos prescritos actualmente:")
            if not st.session_state["temp_meds_list"]:
                st.info("Sin medicamentos prescritos para este paciente.")
            else:
                for idx_m, m_item in enumerate(st.session_state["temp_meds_list"]):
                    c_m1, c_m2, c_m3, c_m4, c_m5, c_m6 = st.columns([3, 1, 1, 1, 1, 1])
                    with c_m1:
                        st.write(f"💊 **{m_item['nombre']}** ({m_item.get('indicaciones', '')})")
                    with c_m2:
                        st.write(f"Mañana: {m_item.get('manana', 0)}")
                    with c_m3:
                        st.write(f"Tarde: {m_item.get('tarde', 0)}")
                    with c_m4:
                        st.write(f"Noche: {m_item.get('noche', 0)}")
                    with c_m5:
                        st.write(f"Stock: {m_item.get('existencia', 0)}")
                    with c_m6:
                        if st.button("🗑️", key=f"del_m_temp_{idx_m}"):
                            st.session_state["temp_meds_list"].pop(idx_m)
                            st.rerun()
                            
            st.divider()
            st.subheader("➕ Agregar Medicamento a Prescripción")
            with st.form("form_add_prescripcion"):
                if cat_list_names:
                    med_nom_sel = st.selectbox("Seleccionar del Catálogo Maestro", cat_list_names)
                else:
                    med_nom_sel = st.text_input("Nombre del Medicamento *")
                    
                c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                with c_d1:
                    d_manana = st.number_input("Dosis Mañana", min_value=0, value=1)
                with c_d2:
                    d_tarde = st.number_input("Dosis Tarde", min_value=0, value=0)
                with c_d3:
                    d_noche = st.number_input("Dosis Noche", min_value=0, value=1)
                with c_d4:
                    existencia_p = st.number_input("Existencia inicial asignada", min_value=0, value=30)
                    
                m_ind = st.text_input("Indicaciones de Toma (ej. Después de alimentos)")
                
                btn_add_presc = st.form_submit_button("➕ Agregar a Prescripción")
                if btn_add_presc:
                    if not med_nom_sel:
                        st.error("Selecciona o escribe el medicamento.")
                    else:
                        tot_d = d_manana + d_tarde + d_noche
                        nuevo_m = {
                            "nombre": med_nom_sel,
                            "manana": d_manana,
                            "tarde": d_tarde,
                            "noche": d_noche,
                            "total_dosis": tot_d,
                            "existencia": existencia_p,
                            "indicaciones": m_ind
                        }
                        st.session_state["temp_meds_list"].append(nuevo_m)
                        st.toast("Medicamento agregado a la lista temporal.")
                        st.rerun()
                        
            st.divider()
            with st.form("form_save_full_presc"):
                obs_final = st.text_area("Observaciones generales de prescripción", value=obs_curr)
                btn_save_all_presc = st.form_submit_button("💾 Guardar Prescripción Completa del Paciente", use_container_width=True)
                
                if btn_save_all_presc:
                    guardar_medicamentos_paciente(p_id_med, st.session_state["temp_meds_list"], obs_final, st.session_state["username"])
                    st.toast("🎉 ¡Prescripción guardada exitosamente!")
                    st.success("✅ ¡Prescripción e inventario del paciente actualizados exitosamente!")

    # ==========================================
    # --- MÓDULO 8: ENTREGA DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Surtido y Entrega Diaria de Medicamentos")
        st.caption("Entrega de dosis a residentes, descuento automático de inventario y generación de comprobante")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados.")
        else:
            dict_p_ent = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1]) for p in pacientes_activos}
            sel_p_del = st.selectbox("🔑 Selecciona el Paciente a Entregar Dosis", list(dict_p_ent.keys()))
            p_id_del, p_nom_del = dict_p_ent[sel_p_del]
            
            meds_pac, obs_pac = obtener_medicamentos_paciente(p_id_del)
            
            if not meds_pac:
                st.warning("Este paciente no tiene medicamentos prescritos en su esquema.")
            else:
                st.subheader(f"Formulario de Entrega para: **{p_nom_del}**")
                
                with st.form("form_surtido_diario"):
                    entregado_por = st.text_input("Nombre de la Persona que Entrega (Staff) *", value=st.session_state["nombre_completo"])
                    
                    st.write("Selecciona la cantidad de dosis entregada para cada medicamento:")
                    surtido_items = []
                    meds_actualizados = []
                    
                    for idx_m, m in enumerate(meds_pac):
                        c_s1, c_s2, c_s3 = st.columns([3, 2, 2])
                        with c_s1:
                            st.write(f"💊 **{m['nombre']}** | Stock actual: `{m.get('existencia', 0)}`")
                            st.caption(f"Indicaciones: {m.get('indicaciones', 'Sin indicación')}")
                        with c_s2:
                            cant_ent = st.number_input(f"Cantidad a Entregar", min_value=0, max_value=m.get("existencia", 0), value=1, key=f"cant_ent_{idx_m}")
                        with c_s3:
                            restante = m.get("existencia", 0) - cant_ent
                            st.write(f"Stock resultante: `{restante}`")
                            
                        surtido_items.append({
                            "nombre": m['nombre'],
                            "cant_entregada": cant_ent,
                            "existencia_restante": restante
                        })
                        
                        m_copy = dict(m)
                        m_copy["existencia"] = restante
                        meds_actualizados.append(m_copy)
                        
                    btn_confirm_surtido = st.form_submit_button("🚚 Confirmar Entrega y Descontar Stock", use_container_width=True)
                    
                    if btn_confirm_surtido:
                        if not entregado_por.strip():
                            st.error("El nombre de quien entrega es obligatorio.")
                        else:
                            registrar_entrega_medicamento(p_id_del, entregado_por, surtido_items, meds_actualizados, obs_pac)
                            pdf_ent_med = generar_pdf_entrega_meds(p_id_del, p_nom_del, surtido_items, entregado_por)
                            st.toast("🎉 ¡Entrega registrada exitosamente!")
                            st.success(f"✅ ¡Surtido registrado para **{p_nom_del}**!")
                            
                            with open(pdf_ent_med, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar Comprobante de Entrega en PDF",
                                    data=f,
                                    file_name=pdf_ent_med,
                                    mime="application/pdf"
                                )
                            st.balloons()

    # ==========================================
    # --- MÓDULO 9: ALERTAS DE EXISTENCIA Y COMPRAS ---
    # ==========================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencia & Lista de Compras de Farmacia")
        st.caption("Monitoreo de inventario crítico y generación de lista de compras")
        
        st.subheader("📦 Estado de Stock en Catálogo Maestro")
        cat_maestro = obtener_catalogo_medicamentos()
        
        if not cat_maestro:
            st.info("No hay medicamentos en el catálogo general.")
        else:
            alertas = [m for m in cat_maestro if m[3] < 10]
            if alertas:
                st.error(f"🚨 **Alerta de Reabastecimiento**: Se detectaron `{len(alertas)}` medicamentos con stock menor a 10 unidades.")
                for a in alertas:
                    st.write(f"• ⚠️ **{a[1]}** ({a[2]}): Quedan sólo `{a[3]}` unidades en existencia.")
            else:
                st.success("🟢 **Inventario Saludable**: Todos los medicamentos en catálogo cuentan con stock adecuado (≥ 10 unidades).")
                
        st.divider()
        st.subheader("🖨️ Generar Lista de Compras Impresa")
        pdf_compras = generar_pdf_lista_general_meds()
        with open(pdf_compras, "rb") as f:
            st.download_button(
                label="📄 Imprimir Reporte Completo de Inventario y Existencias (PDF)",
                data=f,
                file_name=pdf_compras,
                mime="application/pdf",
                key="dl_pdf_compras"
            )

    # ==========================================
    # --- MÓDULO 10: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Descarga de copias de seguridad de la base de datos sqlite y restauración de datos")
        
        tab_b1, tab_b2 = st.tabs(["💾 Generar Respaldo (.db)", "📥 Restaurar Respaldo"])
        
        with tab_b1:
            st.subheader("Descargar Respaldo Actual de la Base de Datos")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="💾 Descargar Respaldo Base de Datos (sistema_pacientes.db)",
                        data=f,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
            else:
                st.error("No se encontró el archivo de base de datos.")
                
        with tab_b2:
            st.subheader("Restaurar la Base de Datos desde un Archivo de Respaldo")
            uploaded_db = st.file_uploader("Sube tu archivo .db de respaldo", type=["db"])
            if uploaded_db is not None:
                if st.button("🚨 Confirmar Restauración de Base de Datos", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    st.toast("🎉 ¡Base de datos restaurada exitosamente!")
                    st.success("✅ ¡Base de datos restaurada exitosamente! Por favor reinicia la página.")
                    st.rerun()

    # ==========================================
    # --- MÓDULO 11: USUARIOS Y ROLES DEL SISTEMA ---
    # ==========================================
    elif menu == "👥 Usuarios y Roles del Sistema":
        st.title("👥 Gestión de Usuarios Staff y Roles del Sistema")
        st.caption("Alta de personal de staff, asignación de roles (Administrador, Consejero, Médico/Farmacia) y bloqueo por vacaciones")
        
        rol_actual = st.session_state.get("rol", "Administrador")
        if rol_actual != "Administrador":
            st.warning("🔒 Esta sección de administración de usuarios y roles es exclusiva para usuarios con rol de **Administrador / Director**.")
        else:
            modo_usr_sys = st.radio("Acción a Realizar:", ["🆕 Registrar Nuevo Usuario", "✏️ Editar / Modificar Usuario Existente"], horizontal=True)
            
            lista_usr_sys = obtener_usuarios_sistema()
            usr_edit_data = None
            edit_uname = ""
            
            if modo_usr_sys == "✏️ Editar / Modificar Usuario Existente":
                if not lista_usr_sys:
                    st.info("No hay usuarios registrados en el sistema.")
                else:
                    dict_usr = {f"{u[2]} ({u[1]}) - Rol: {u[3]} [{ 'Activo' if u[4]=='A' else 'Bloqueado' }]": u for u in lista_usr_sys}
                    sel_u_str = st.selectbox("🔑 Selecciona el Usuario del Sistema a Editar", list(dict_usr.keys()))
                    usr_edit_data = dict_usr[sel_u_str]
                    edit_uname = usr_edit_data[1]
                    
            with st.form("form_gestion_usuario_sistema"):
                c_u1, c_u2 = st.columns(2)
                with c_u1:
                    val_uname = usr_edit_data[1] if usr_edit_data else ""
                    sys_uname = st.text_input("👤 Nombre de Usuario (Login) *", value=val_uname, disabled=(modo_usr_sys == "✏️ Editar / Modificar Usuario Existente"))
                    
                    val_full = usr_edit_data[2] if usr_edit_data else ""
                    sys_full = st.text_input("📛 Nombre Completo del Usuario *", value=val_full)
                    
                with c_u2:
                    roles_opts = ["Administrador", "Consejero / Evaluador Clínico", "Médico / Farmacia"]
                    idx_r = 0
                    if usr_edit_data and usr_edit_data[3] in roles_opts:
                        idx_r = roles_opts.index(usr_edit_data[3])
                    sys_rol = st.selectbox("🏷️ Rol de Sistema *", roles_opts, index=idx_r)
                    
                    est_opts = ["A - Activo", "B - Bloqueado (Vacaciones / Inactivo)"]
                    idx_e = 0
                    if usr_edit_data and usr_edit_data[4] == 'B':
                        idx_e = 1
                    sys_est_sel = st.selectbox("📌 Estatus de la Cuenta *", est_opts, index=idx_e)
                    sys_est = 'A' if sys_est_sel.startswith('A') else 'B'
                    
                pass_lbl = "🔑 Contraseña (dejar en blanco para conservar actual)" if modo_usr_sys == "✏️ Editar / Modificar Usuario Existente" else "🔑 Contraseña *"
                sys_pass = st.text_input(pass_lbl, type="password")
                
                btn_save_sys_usr = st.form_submit_button("💾 Guardar Usuario del Sistema", use_container_width=True)
                
                if btn_save_sys_usr:
                    if modo_usr_sys == "🆕 Registrar Nuevo Usuario":
                        if not sys_uname.strip() or not sys_full.strip() or not sys_pass:
                            st.error("⚠️ Nombre de usuario, nombre completo y contraseña son campos obligatorios para nuevos usuarios.")
                        else:
                            ok_u, msg_u = guardar_usuario_sistema(sys_uname.strip(), sys_pass, sys_full.strip(), sys_rol, sys_est)
                            if ok_u:
                                st.toast(f"🎉 ¡Usuario {sys_uname} registrado exitosamente!")
                                st.success(f"✅ ¡Usuario **{sys_full}** (`{sys_uname}`) registrado exitosamente con rol **{sys_rol}**!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_u}")
                    else:
                        if not sys_full.strip():
                            st.error("⚠️ El nombre completo es obligatorio.")
                        else:
                            ok_u, msg_u = guardar_usuario_sistema(edit_uname, sys_pass if sys_pass else None, sys_full.strip(), sys_rol, sys_est)
                            if ok_u:
                                st.toast(f"🎉 ¡Usuario {edit_uname} actualizado exitosamente!")
                                st.success(f"✅ ¡Usuario **{sys_full}** (`{edit_uname}`) actualizado exitosamente!")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_u}")
                                
            st.divider()
            st.subheader("📋 Directorio de Usuarios del Sistema")
            if not lista_usr_sys:
                st.info("No hay usuarios registrados.")
            else:
                for u_item in lista_usr_sys:
                    uid, uname, ufull, urol, uest = u_item
                    st_badge = "🟢 Activo" if uest == 'A' else "🔒 Bloqueado (Vacaciones)"
                    col_us1, col_us2, col_us3 = st.columns([4, 2, 2])
                    with col_us1:
                        st.write(f"👤 **{ufull}** (`{uname}`) | Rol: **{urol}** | Estatus: {st_badge}")
                    with col_us2:
                        if uest == 'A':
                            dis_block = (uname == st.session_state["username"] or uname == "admin")
                            if st.button("🔒 Bloquear", key=f"btn_blk_sys_{uname}", disabled=dis_block, help="Bloquear por vacaciones o inactividad"):
                                cambiar_estatus_usuario_sistema(uname, 'B')
                                st.toast(f"🔒 Usuario {uname} bloqueado por vacaciones.")
                                st.rerun()
                        else:
                            if st.button("🟢 Activar", key=f"btn_act_sys_{uname}"):
                                cambiar_estatus_usuario_sistema(uname, 'A')
                                st.toast(f"🟢 Usuario {uname} reactivado.")
                                st.rerun()
                    with col_us3:
                        dis_del = (uname == st.session_state["username"] or uname == "admin")
                        if st.button("🗑️ Eliminar", key=f"btn_del_sys_{uname}", disabled=dis_del):
                            ok_d, msg_d = eliminar_usuario_sistema(uname)
                            if ok_d:
                                st.toast(f"🗑️ Usuario {uname} eliminado.")
                                st.rerun()
                            else:
                                st.error(msg_d)

    # ==========================================
    # --- MÓDULO 12: CONFIGURACIÓN / SEGURIDAD ---
    # ==========================================
    elif menu == "⚙️ Configuración / Seguridad":
        st.title("⚙️ Configuración del Sistema & Requisitos")
        
        tab_sec1, tab_sec2 = st.tabs(["🔑 Cambiar Contraseña", "⚙️ Administrar Requisitos por Etapa"])
        
        with tab_sec1:
            st.subheader("Cambiar Contraseña de Usuario Staff")
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
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(nueva_pass), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.toast("🎉 ¡Contraseña actualizada exitosamente!")
                            st.success("✅ Contraseña actualizada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")
                            
        with tab_sec2:
            st.subheader("Administrador de Requisitos por Etapa")
            etapa_sel = st.selectbox("Selecciona la Etapa a Configurar", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
            
            reqs_curr = obtener_requisitos_etapa(etapa_sel)
            st.write(f"Requisitos actuales para **{etapa_sel}**:")
            
            for rid, rtxt, esg in reqs_curr:
                cr1, cr2 = st.columns([4, 1])
                with cr1:
                    st.write(f"• {rtxt} {'(Sesión de Grupo)' if esg==1 else ''}")
                with cr2:
                    if st.button("🗑️ Eliminar", key=f"del_req_{rid}"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (rid,))
                        conn.commit()
                        conn.close()
                        st.toast("Requisito eliminado.")
                        st.rerun()
                        
            st.divider()
            st.subheader("Agregar Nuevo Requisito Teórico / Conductual")
            with st.form("form_add_req"):
                nuevo_req_txt = st.text_input("Descripción del Requisito")
                es_grupo_chk = st.checkbox("¿Es un requisito de Grupo Terapéutico?")
                btn_add_req = st.form_submit_button("➕ Agregar Requisito")
                
                if btn_add_req:
                    if not nuevo_req_txt.strip():
                        st.error("La descripción del requisito es obligatoria.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', (etapa_sel, nuevo_req_txt.strip(), 1 if es_grupo_chk else 0))
                        conn.commit()
                        conn.close()
                        st.toast("🎉 ¡Requisito agregado exitosamente!")
                        st.success("✅ Requisito agregado exitosamente.")
                        st.rerun()

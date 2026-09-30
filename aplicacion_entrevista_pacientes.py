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

# --- FUNCIONES DE BASE DE DATOS & AUTO-MIGRACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios Administrativos / Staff del Sistema
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
    
    # Auto-migración de columnas si la base de datos ya existía previamente
    try:
        c.execute("PRAGMA table_info(usuarios)")
        cols = [col[1] for col in c.fetchall()]
        if "rol" not in cols:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
        if "estatus" not in cols:
            c.execute("ALTER TABLE usuarios ADD COLUMN estatus TEXT DEFAULT 'A'")
    except Exception:
        pass

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
    
    # 3. Tabla de Entrevistas Iniciales de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 4. Tabla de Catálogo Central de Medicamentos (Farmacia)
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            fecha_registro TEXT
        )
    ''')
    
    # Poblar Catálogo Base si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_base = [
            ("Paracetamol", "Comprimidos", "500 mg"),
            ("Omeprazol", "Cápsulas", "20 mg"),
            ("Sertralina", "Tabletas", "50 mg"),
            ("Clonazepam", "Gotas / Tabletas", "2 mg"),
            ("Fluoxetina", "Cápsulas", "20 mg"),
            ("Quetiapina", "Comprimidos", "100 mg"),
            ("Valproato de Sodio", "Tabletas", "500 mg"),
            ("Complejo B", "Tabletas", "Estándar"),
            ("Multivitamínico", "Cápsulas", "Estándar")
        ]
        f_now = datetime.now().strftime("%Y-%m-%d")
        for m_nom, m_pres, m_conc in meds_base:
            c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
                      (m_nom, m_pres, m_conc, f_now))

    # 5. Tabla de Prescripción e Inventario de Medicamentos por Paciente
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
    
    # 6. Tabla de Historial de Entrega de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    
    # 7. Tabla de Registro de Grupos Terapéuticos
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
    
    # 8. Tabla de Historial de Promoción de Etapas
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
    
    # 10. Tabla de Repositorio Digital de Documentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_archivo TEXT,
            descripcion TEXT,
            contenido_blob BLOB,
            tamano_bytes INTEGER,
            fecha_subida TEXT,
            subido_por TEXT
        )
    ''')
    
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'A'))
    
    # Requisitos Iniciales por Etapa
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
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('SELECT username, nombre_completo, rol, estatus FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        row = c.fetchone()
    except Exception:
        c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        r = c.fetchone()
        row = (r[0], r[1], 'Administrador', 'A') if r else None
    conn.close()
    return row

def obtener_usuarios_sistema():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('SELECT id, username, nombre_completo, rol, estatus FROM usuarios ORDER BY username')
        rows = c.fetchall()
    except Exception:
        c.execute('SELECT id, username, nombre_completo FROM usuarios ORDER BY username')
        r_old = c.fetchall()
        rows = [(r[0], r[1], r[2], 'Administrador', 'A') for r in r_old]
    conn.close()
    return rows

def guardar_usuario_sistema(username, password, nombre_completo, rol, estatus='A'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('SELECT username FROM usuarios WHERE username = ?', (username,))
        exists = c.fetchone()
        if exists:
            if password:
                c.execute('UPDATE usuarios SET password_hash = ?, nombre_completo = ?, rol = ?, estatus = ? WHERE username = ?',
                          (hash_pass(password), nombre_completo, rol, estatus, username))
            else:
                c.execute('UPDATE usuarios SET nombre_completo = ?, rol = ?, estatus = ? WHERE username = ?',
                          (nombre_completo, rol, estatus, username))
        else:
            if not password:
                conn.close()
                return False, "La contraseña es obligatoria para usuarios nuevos."
            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                      (username, hash_pass(password), nombre_completo, rol, estatus))
        conn.commit()
        conn.close()
        return True, "OK"
    except Exception as e:
        conn.close()
        return False, str(e)

def cambiar_estatus_usuario_sistema(username, nuevo_estatus):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('UPDATE usuarios SET estatus = ? WHERE username = ?', (nuevo_estatus, username))
        conn.commit()
    except Exception:
        pass
    conn.close()

def eliminar_usuario_sistema(username):
    init_db()
    if username.lower() == 'admin':
        return False, "No se puede eliminar el usuario principal 'admin'."
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    return True, "OK"

# --- FUNCIONES DE PACIENTES ---
def obtener_siguiente_id():
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

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre.strip().lower()
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
    if c.fetchone():
        c.execute('''
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo, f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo, f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, fecha_actual, usuario_reg))
    conn.commit()
    conn.close()

def listar_pacientes_bd(filtro_estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if filtro_estatus == 'TODOS':
        c.execute('SELECT * FROM pacientes ORDER BY nombre_completo')
    else:
        c.execute('SELECT * FROM pacientes WHERE estatus = ? ORDER BY nombre_completo', (filtro_estatus,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET estatus = ?, fecha_modificacion = ? WHERE paciente_id = ?', (nuevo_estatus, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ENTREVISTAS ---
def guardar_entrevista(paciente_id, datos_dict, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_str = json.dumps(datos_dict, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, usuario_registro = ?, datos_json = ? WHERE paciente_id = ?',
                  (fecha_actual, usuario, json_str, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, fecha_actual, fecha_actual, usuario, json_str))
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

# --- FUNCIONES DE FARMACIA & MEDICAMENTOS ---
def obtener_catalogo_meds():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, presentacion, concentracion FROM catalogo_medicamentos ORDER BY nombre')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_med(nombre, presentacion, concentracion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d")
    try:
        c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
                  (nombre.strip(), presentacion.strip(), concentracion.strip(), f_now))
        conn.commit()
        conn.close()
        return True, "OK"
    except Exception as e:
        conn.close()
        return False, "El medicamento ya existe en el catálogo."

def guardar_medicamentos_paciente(paciente_id, meds_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_str = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                  (json_str, observaciones, fecha_actual, usuario, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)',
                  (paciente_id, json_str, observaciones, fecha_actual, fecha_actual, usuario))
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

def guardar_entrega_meds(paciente_id, entregado_por, detalle_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_str = json.dumps(detalle_list, ensure_ascii=False)
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, fecha_actual, entregado_por, json_str))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_dict, usuario, grupo_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_str = json.dumps(datos_dict, ensure_ascii=False)
    
    if grupo_id:
        c.execute('''
            UPDATE grupos_terapeutos
            SET tipo_grupo = ?, fecha_grupo = ?, facilitador = ?, datos_json = ?
            WHERE id = ?
        ''', (tipo_grupo, str(fecha_grupo), facilitador, json_str, grupo_id))
    else:
        c.execute('''
            INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, tipo_grupo, etapa_al_momento, str(fecha_grupo), facilitador, json_str, fecha_actual, usuario))
    conn.commit()
    conn.close()

def eliminar_grupo_terapeuto(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM grupos_terapeutos WHERE id = ?', (grupo_id,))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ETAPAS & HERMANO MAYOR ---
def promover_etapa_paciente(paciente_id, etapa_origen, etapa_destino, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?', (etapa_destino, f_hoy, fecha_actual, paciente_id))
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario))
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_suelta_hermano = NULL, fecha_modificacion = ? WHERE paciente_id = ?', (hermano_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def soltar_hermano_mayor(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET hermano_mayor_id = NULL, fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?', (f_hoy, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERACIÓN DE REPORTES PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 5, 'Sistema Integral de Seguimiento Clínico y Control de Expedientes', 0, 1, 'C')
        self.line(10, 24, 200, 24)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

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

def generar_pdf_entrevista(paciente_id):
    pac = obtener_paciente(paciente_id)
    ent = obtener_entrevista(paciente_id)
    
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, limpiar_texto(f"ENTREVISTA INICIAL DE CONSEJERÍA: {pac[1] if pac else paciente_id}"), 0, 1, "C")
    pdf.ln(5)
    
    if pac:
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 6, limpiar_texto(f"Folio: {pac[0]} | Fecha Ingreso: {pac[2]} | Sexo: {pac[4]} | Etapa: {pac[7]}"), 0, 1)
        pdf.ln(4)
        
    if not ent:
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 8, "No se encontraron datos registrados para esta entrevista.", 0, 1)
    else:
        for sec, campos in ent.items():
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 7, limpiar_texto(sec.upper()), 0, 1)
            pdf.set_font("Arial", "", 9)
            if isinstance(campos, dict):
                for k, v in campos.items():
                    val_str = str(v) if v is not None else ""
                    pdf.multi_cell(0, 5, limpiar_texto(f"• {k}: {val_str}"))
            elif isinstance(campos, list):
                for elem in campos:
                    pdf.multi_cell(0, 5, limpiar_texto(f"• {elem}"))
            pdf.ln(2)
            
    out_name = f"Entrevista_{paciente_id}.pdf"
    pdf.output(out_name)
    return out_name

def generar_pdf_historial_grupos(paciente_id):
    pac = obtener_paciente(paciente_id)
    grupos = listar_grupos_paciente(paciente_id)
    
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, limpiar_texto(f"EXPEDIENTE DE GRUPOS TERAPÉUTICOS: {pac[1] if pac else paciente_id}"), 0, 1, "C")
    pdf.ln(5)
    
    if not grupos:
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 8, "No se registraron sesiones de grupo para este residente.", 0, 1)
    else:
        for g in grupos:
            gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
            datos = json.loads(djson)
            pdf.set_font("Arial", "B", 10)
            pdf.cell(0, 6, limpiar_texto(f"🗣️ {tgrp} | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"), 0, 1)
            pdf.set_font("Arial", "", 9)
            if tgrp in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                pdf.multi_cell(0, 5, limpiar_texto(f"• Compartimiento: {datos.get('compartimiento', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Observaciones: {datos.get('observaciones', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Devoluciones: {datos.get('devoluciones', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Compromiso: {datos.get('compromiso', '')}"))
            else:
                pdf.multi_cell(0, 5, limpiar_texto(f"• Logros: {datos.get('logros', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Dificultades: {datos.get('dificultades', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Observaciones: {datos.get('observaciones', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Devoluciones: {datos.get('devoluciones', '')}"))
                pdf.multi_cell(0, 5, limpiar_texto(f"• Compromiso: {datos.get('compromiso', '')}"))
            pdf.ln(3)
            
    out_name = f"Grupos_{paciente_id}.pdf"
    pdf.output(out_name)
    return out_name

def generar_pdf_compras_farmacia(compras_list):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "REPORTE DE COMPRAS Y REABASTECIMIENTO DE FARMACIA", 0, 1, "C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 9)
    pdf.cell(60, 7, "Residente", 1)
    pdf.cell(65, 7, "Medicamento / Presentacion", 1)
    pdf.cell(30, 7, "Stock Actual", 1)
    pdf.cell(35, 7, "Accion Requerida", 1)
    pdf.ln()
    
    pdf.set_font("Arial", "", 8)
    for c in compras_list:
        pdf.cell(60, 6, limpiar_texto(c["paciente"]), 1)
        pdf.cell(65, 6, limpiar_texto(c["med"]), 1)
        pdf.cell(30, 6, str(c["stock"]), 1)
        pdf.cell(35, 6, limpiar_texto(c["nivel"]), 1)
        pdf.ln()
        
    out_name = "Orden_Compras_Farmacia.pdf"
    pdf.output(out_name)
    return out_name

# --- INICIALIZAR BASE DE DATOS Y SESIÓN ---
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
                usuario_valido = verificar_login(user_input, pass_input)
                if usuario_valido:
                    # Validar estatus de bloqueo por vacaciones
                    u_uname = usuario_valido[0]
                    u_full = usuario_valido[1]
                    u_rol = usuario_valido[2] if len(usuario_valido) > 2 else "Administrador"
                    u_est = usuario_valido[3] if len(usuario_valido) > 3 else "A"
                    
                    if u_est == 'B':
                        st.error("❌ La cuenta de este usuario se encuentra temporalmente bloqueada/inactiva (periodo de vacaciones). Contacte al Administrador.")
                    else:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = u_uname
                        st.session_state["nombre_completo"] = u_full
                        st.session_state["rol"] = u_rol
                        st.toast(f"🎉 ¡Bienvenido {u_full}!")
                        st.success("¡Acceso concedido!")
                        st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL & MENÚ DE NAVEGACIÓN COMPLETO (12 MÓDULOS) ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario Staff**: {st.session_state['nombre_completo']}")
    st.sidebar.caption(f"🏷️ Rol: **{st.session_state.get('rol', 'Administrador')}**")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["nombre_completo"] = ""
        st.session_state["rol"] = "Administrador"
        st.rerun()
        
    st.sidebar.divider()
    
    menu_opciones = [
        "1. 👤 Registro y Edición de Usuarios",
        "2. 📝 Nueva Entrevista / Editar",
        "3. 🔍 Buscar y Listar Pacientes",
        "4. 🎯 Gestión de Etapas & Proceso",
        "5. 🗣️ Grupos Terapéuticos",
        "6. 📦 Catálogo General de Medicamentos",
        "7. 💊 Control de Medicamentos y Dosis",
        "8. 🚚 Entrega de Medicamentos",
        "9. 🚨 Alertas de Existencia y Compras",
        "10. 📁 Repositorio de Documentos",
        "11. 📦 Respaldo y Restauración",
        "12. ⚙️ Configuración y Seguridad"
    ]
    
    menu = st.sidebar.radio("Navegación del Sistema", menu_opciones)
    
    # ==========================================
    # --- MÓDULO 1: REGISTRO DE USUARIOS ---
    # ==========================================
    if menu == "1. 👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes / Servidores")
        st.caption("Alta inicial de expedientes e información sociodemográfica básica")
        
        modo_usr = st.radio("Acción:", ["🆕 Registrar Nuevo Residente / Servidor", "✏️ Editar Existente"], horizontal=True)
        
        if modo_usr == "🆕 Registrar Nuevo Residente / Servidor":
            with st.form("form_alta_paciente"):
                st.subheader("Datos de Registro Inicial")
                c1, c2 = st.columns(2)
                with c1:
                    f_id = st.text_input("🔑 Folio de Identificación *", value=obtener_siguiente_id())
                    p_nom = st.text_input("📛 Nombre Completo *")
                    f_nac = st.date_input("🎂 Fecha de Nacimiento", value=date(1990, 1, 1))
                with c2:
                    p_sexo = st.selectbox("👤 Sexo *", ["Masculino", "Femenino", "Otro"])
                    f_ing = st.date_input("📅 Fecha de Ingreso *", value=date.today())
                    p_tipo = st.selectbox("🏷️ Tipo de Registro *", ["Paciente", "Servidor"])
                    
                btn_alta = st.form_submit_button("💾 Guardar Registro Inicial", use_container_width=True)
                if btn_alta:
                    if not p_nom.strip():
                        st.error("⚠️ El nombre completo es obligatorio.")
                    else:
                        dup = verificar_duplicado_nombre(p_nom)
                        if dup:
                            st.warning(f"⚠️ Ya existe un registro con el nombre **{dup[1]}** (Folio: `{dup[0]}`).")
                        else:
                            guardar_usuario_paciente(f_id, p_nom.strip(), f_ing, f_nac, p_sexo, 'A', p_tipo, 'ACOGIDA', f_ing, st.session_state["username"])
                            st.toast(f"🎉 ¡Paciente {p_nom} registrado exitosamente!")
                            st.success(f"✅ ¡Paciente **{p_nom}** guardado con Folio `{f_id}`!")
                            st.balloons()
                            st.rerun()
        else:
            pacientes_act = listar_pacientes_bd('TODOS')
            if not pacientes_act:
                st.info("No hay pacientes registrados.")
            else:
                dict_p = {f"{p[1]} ({p[0]})": p for p in pacientes_act}
                sel_p_edit = st.selectbox("🔑 Selecciona el Residente a Editar", list(dict_p.keys()))
                p_data = dict_p[sel_p_edit]
                
                with st.form("form_edit_paciente"):
                    st.subheader(f"Editando: {p_data[1]} ({p_data[0]})")
                    ce1, ce2 = st.columns(2)
                    with ce1:
                        p_nom_e = st.text_input("Nombre Completo *", value=p_data[1])
                        f_nac_e = st.date_input("Fecha de Nacimiento", value=datetime.strptime(p_data[3], "%Y-%m-%d").date() if p_data[3] else date(1990, 1, 1))
                        p_sex_e = st.selectbox("Sexo *", ["Masculino", "Femenino", "Otro"], index=["Masculino", "Femenino", "Otro"].index(p_data[4]) if p_data[4] in ["Masculino", "Femenino", "Otro"] else 0)
                    with ce2:
                        f_ing_e = st.date_input("Fecha de Ingreso *", value=datetime.strptime(p_data[2], "%Y-%m-%d").date() if p_data[2] else date.today())
                        p_tipo_e = st.selectbox("Tipo *", ["Paciente", "Servidor"], index=0 if p_data[6] == "Paciente" else 1)
                        p_est_e = st.selectbox("Estatus *", ["A - Activo", "I - Inactivo / Baja", "E - Egresado"], index=0 if p_data[5]=='A' else (1 if p_data[5]=='I' else 2))
                        
                    btn_edit = st.form_submit_button("💾 Guardar Cambios de Expediente", use_container_width=True)
                    if btn_edit:
                        est_code = p_est_e.split(" - ")[0]
                        guardar_usuario_paciente(p_data[0], p_nom_e.strip(), f_ing_e, f_nac_e, p_sex_e, est_code, p_tipo_e, p_data[7], p_data[8], st.session_state["username"])
                        st.toast("🎉 Cambios guardados exitosamente")
                        st.success("✅ Expediente actualizado correctamente.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 2: NUEVA ENTREVISTA ---
    # ==========================================
    elif menu == "2. 📝 Nueva Entrevista / Editar":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Captura completa del perfil de adicciones, laboral, familiar y motivación al cambio")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados.")
        else:
            dict_pac_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_pac_ent = st.selectbox("🔑 Selecciona el Residente para Consejería", list(dict_pac_ent.keys()))
            p_id_ent = dict_pac_ent[sel_pac_ent]
            
            ent_existente = obtener_entrevista(p_id_ent) or {}
            
            with st.form("form_entrevista_inicial"):
                st.subheader("1. Antecedentes Sociodemográficos y Laborales")
                c_s1, c_s2 = st.columns(2)
                with c_s1:
                    e_ocup = st.text_input("Ocupación / Oficio", value=ent_existente.get("socio", {}).get("ocupacion", ""))
                    e_escolar = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria", "Licenciatura", "Postgrado", "Otro"], index=0)
                with c_s2:
                    e_est_civ = st.selectbox("Estado Civil", ["Soltero", "Casado", "Unión Libre", "Divorciado", "Viudo"], index=0)
                    e_ingreso_lab = st.text_input("Ingreso Mensual Promedio", value=ent_existente.get("socio", {}).get("ingreso", ""))
                    
                st.divider()
                st.subheader("2. Historial de Consumo de Sustancias")
                c_c1, c_c2 = st.columns(2)
                with c_c1:
                    sust_impacto = st.text_input("Sustancia de Mayor Impacto", value=ent_existente.get("consumo", {}).get("impacto", ""))
                    edad_inicio = st.number_input("Edad de Inicio de Consumo", min_value=5, max_value=90, value=int(ent_existente.get("consumo", {}).get("edad_inicio", 15)))
                with c_c2:
                    frecuencia_c = st.selectbox("Frecuencia de Consumo", ["Diario", "Fin de Semana", "Ocasional", "Episódico / Reventones"], index=0)
                    ultimo_consumo = st.date_input("Fecha del Último Consumo", value=date.today())
                    
                obs_consumo = st.text_area("Observaciones sobre el patrón de consumo", value=ent_existente.get("consumo", {}).get("observaciones", ""))
                
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ent:
                    datos_totales = {
                        "socio": {"ocupacion": e_ocup, "escolaridad": e_escolar, "estado_civil": e_est_civ, "ingreso": e_ingreso_lab},
                        "consumo": {"impacto": sust_impacto, "edad_inicio": edad_inicio, "frecuencia": frecuencia_c, "ultimo_consumo": str(ultimo_consumo), "observaciones": obs_consumo}
                    }
                    guardar_entrevista(p_id_ent, datos_totales, st.session_state["username"])
                    st.toast("🎉 Entrevista inicial guardada")
                    st.success("✅ Entrevista de consejería registrada correctamente.")

    # ==========================================
    # --- MÓDULO 3: BUSCAR Y LISTAR ---
    # ==========================================
    elif menu == "3. 🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio General de Residentes & Expedientes")
        
        c_b1, c_b2 = st.columns([3, 1])
        with c_b1:
            q_search = st.text_input("🔎 Buscar por Nombre o Folio...")
        with c_b2:
            f_estatus = st.selectbox("Filtrar Estatus", ["TODOS", "A", "I", "E"])
            
        pacientes_list = listar_pacientes_bd(f_estatus)
        if q_search.strip():
            q_clean = q_search.strip().lower()
            pacientes_list = [p for p in pacientes_list if q_clean in p[0].lower() or q_clean in p[1].lower()]
            
        st.write(f"Total de registros encontrados: **{len(pacientes_list)}**")
        
        for p in pacientes_list:
            st_icon = "🟢" if p[5]=='A' else ("🔴" if p[5]=='I' else "🎓")
            with st.expander(f"{st_icon} **{p[1]}** ({p[0]}) | Etapa: **{p[7]}** | Tipo: {p[6]}"):
                st.write(f"**Fecha Ingreso:** {p[2]} | **Sexo:** {p[4]} | **Fecha Nacimiento:** {p[3]}")
                st.write(f"**Fecha Inicio Etapa:** {p[8] if p[8] else 'N/A'}")
                
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    pdf_ent = generar_pdf_entrevista(p[0])
                    with open(pdf_ent, "rb") as f:
                        st.download_button("🖨️ Descargar Entrevista en PDF", f, file_name=pdf_ent, mime="application/pdf", key=f"pdf_e_{p[0]}")
                with col_exp2:
                    pdf_g = generar_pdf_historial_grupos(p[0])
                    with open(pdf_g, "rb") as f:
                        st.download_button("🖨️ Descargar Expediente Grupos PDF", f, file_name=pdf_g, mime="application/pdf", key=f"pdf_g_{p[0]}")

    # ==========================================
    # --- MÓDULO 4: GESTIÓN DE ETAPAS ---
    # ==========================================
    elif menu == "4. 🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas, Promoción & Hermano Mayor")
        
        tab_et1, tab_et2 = st.tabs(["📊 Avance y Promoción de Etapa", "👥 Asignación de Hermano Mayor"])
        
        with tab_et1:
            pacientes_a = listar_pacientes_bd('A')
            if not pacientes_a:
                st.info("No hay residentes activos.")
            else:
                dict_p_e = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_a}
                sel_p_et = st.selectbox("🔑 Selecciona el Residente", list(dict_p_e.keys()))
                p_et_data = dict_p_e[sel_p_et]
                p_id_et, p_nom_et, e_curr = p_et_data[0], p_et_data[1], p_et_data[7]
                
                st.subheader(f"Lista de Requisitos para Etapa: **{e_curr}**")
                reqs_etapa = obtener_requisitos_etapa(e_curr)
                
                cumplidos = 0
                total_reqs = len(reqs_etapa)
                
                for rid, rtxt, esg in reqs_etapa:
                    if esg == 1:
                        # Conteo dinámico de grupos
                        tipo_g = "Aquí y Ahora" if "Aquí" in rtxt else ("Terapia de Grupo" if "Terapia" in rtxt else "Feedback")
                        cnt_g = contar_grupos_paciente_etapa(p_id_et, e_curr, tipo_g)
                        meta_g = 4 if e_curr in ["IDENTIFICACIÓN", "ELABORACIÓN"] else 2
                        st.write(f"• **{rtxt}**: `{cnt_g} / {meta_g}` sesiones completadas")
                        if cnt_g >= meta_g:
                            cumplidos += 1
                    else:
                        chk_r = st.checkbox(f"• {rtxt}", key=f"chk_req_{p_id_et}_{rid}")
                        if chk_r:
                            cumplidos += 1
                            
                st.progress(cumplidos / total_reqs if total_reqs > 0 else 1.0)
                st.caption(f"Progreso total de la etapa: **{cumplidos} de {total_reqs}** requisitos cumplidos")
                
                st.divider()
                st.subheader("Promoción de Etapa")
                etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_c = etapas_orden.index(e_curr) if e_curr in etapas_orden else 0
                
                if idx_c < len(etapas_orden) - 1:
                    e_sig = etapas_orden[idx_c + 1]
                    if st.button(f"🎓 Promover a {e_sig}", use_container_width=True):
                        promover_etapa_paciente(p_id_et, e_curr, e_sig, st.session_state["username"])
                        st.toast(f"🎉 ¡Paciente promovido a {e_sig}!")
                        st.success(f"✅ ¡El residente **{p_nom_et}** ha avanzado a la etapa **{e_sig}**!")
                        st.balloons()
                        st.rerun()

        with tab_et2:
            st.subheader("Asignación y Suelta de Hermano Mayor")
            pacientes_a = listar_pacientes_bd('A')
            if pacientes_a:
                dict_hm = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_a}
                sel_hm_sub = st.selectbox("🔑 Selecciona Hermano Menor (Acompañado)", list(dict_hm.keys()))
                sel_hm_may = st.selectbox("🔑 Selecciona Hermano Mayor (Guía)", [p for p in dict_hm.keys() if dict_hm[p] != dict_hm[sel_hm_sub]])
                
                if st.button("🔗 Asignar Hermano Mayor"):
                    asignar_hermano_mayor(dict_hm[sel_hm_sub], dict_hm[sel_hm_may])
                    st.toast("🎉 Hermano Mayor asignado")
                    st.success("✅ Hermano Mayor vinculado correctamente.")

    # ==========================================
    # --- MÓDULO 5: GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "5. 🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro y Expediente de Grupos Terapéuticos")
        st.caption("Captura de Terapia de Grupo, Aquí y Ahora, Feedback y Confronto Especial")
        
        tab_rg1, tab_rg2 = st.tabs(["📝 Registrar / Editar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        with tab_rg1:
            pacientes_act = listar_pacientes_bd('A')
            if not pacientes_act:
                st.info("No hay residentes activos.")
            else:
                dict_p_grp = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_act}
                sel_p_g = st.selectbox("🔑 Selecciona el Residente", list(dict_p_grp.keys()))
                p_g_data = dict_p_grp[sel_p_g]
                p_id_g, p_nom_g, p_etapa_g = p_g_data[0], p_g_data[1], p_g_data[7]
                
                t_grupo = st.selectbox("🗣️ Tipo de Grupo Terapéutico", ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Confronto Especial"])
                
                with st.form("form_registro_grupo"):
                    st.subheader(f"Formulario: {t_grupo}")
                    cg1, cg2 = st.columns(2)
                    with cg1:
                        f_grupo_date = st.date_input("Fecha del Grupo", value=date.today())
                    with cg2:
                        fac_nombre = st.text_input("Nombre del Facilitador / Staff *", value=st.session_state["nombre_completo"])
                        
                    st.divider()
                    if t_grupo in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                        g_comp = st.text_area("Compartimiento (Texto largo) *")
                        g_obs = st.text_area("Observaciones")
                        g_dev = st.text_area("Devoluciones")
                        g_compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *")
                        
                        btn_g_save = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)
                        if btn_g_save:
                            if not fac_nombre.strip() or not g_comp.strip() or not g_compromiso.strip():
                                st.error("⚠️ Facilitador, Compartimiento y Compromiso son obligatorios.")
                            else:
                                d_dict = {"compartimiento": g_comp, "observaciones": g_obs, "devoluciones": g_dev, "compromiso": g_compromiso}
                                guardar_grupo_terapeuto(p_id_g, t_grupo, p_etapa_g, f_grupo_date, fac_nombre.strip(), d_dict, st.session_state["username"])
                                st.toast(f"🎉 ¡Sesión de {t_grupo} guardada!")
                                st.success("✅ Registro de grupo guardado exitosamente.")
                                st.balloons()
                                st.rerun()
                    else: # Feedback
                        g_logros = st.text_area("Logros *")
                        g_dificultades = st.text_area("Dificultades *")
                        g_obs = st.text_area("Observaciones")
                        g_dev = st.text_area("Devoluciones")
                        g_compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *")
                        
                        btn_g_save = st.form_submit_button("💾 Guardar Registro de Feedback", use_container_width=True)
                        if btn_g_save:
                            if not fac_nombre.strip() or not g_logros.strip() or not g_dificultades.strip() or not g_compromiso.strip():
                                st.error("⚠️ Facilitador, Logros, Dificultades y Compromiso son obligatorios.")
                            else:
                                d_dict = {"logros": g_logros, "dificultades": g_dificultades, "observaciones": g_obs, "devoluciones": g_dev, "compromiso": g_compromiso}
                                guardar_grupo_terapeuto(p_id_g, t_grupo, p_etapa_g, f_grupo_date, fac_nombre.strip(), d_dict, st.session_state["username"])
                                st.toast("🎉 ¡Sesión de Feedback guardada!")
                                st.success("✅ Registro de Feedback guardado exitosamente.")
                                st.balloons()
                                st.rerun()

        with tab_rg2:
            pacientes_todos = listar_pacientes_bd('TODOS')
            if pacientes_todos:
                dict_gh = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_todos}
                sel_gh = st.selectbox("🔑 Selecciona Residente para Ver Expediente de Grupos", list(dict_gh.keys()))
                p_id_gh = dict_gh[sel_gh]
                
                pdf_grp_out = generar_pdf_historial_grupos(p_id_gh)
                with open(pdf_grp_out, "rb") as f:
                    st.download_button("🖨️ Descargar Expediente de Grupos en PDF", f, file_name=pdf_grp_out, mime="application/pdf", key=f"dl_pdf_grp_{p_id_gh}")
                
                st.divider()
                lista_g = listar_grupos_paciente(p_id_gh)
                for g_item in lista_g:
                    gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g_item
                    datos = json.loads(djson)
                    with st.expander(f"🗣️ **{tgrp}** | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"):
                        st.write(f"**Registrado por:** {ureg} el {freg}")
                        if tgrp in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                            st.write(f"**Compartimiento:** {datos.get('compartimiento', '')}")
                            st.write(f"**Observaciones:** {datos.get('observaciones', '')}")
                            st.write(f"**Devoluciones:** {datos.get('devoluciones', '')}")
                            st.write(f"**Compromiso:** {datos.get('compromiso', '')}")
                        else:
                            st.write(f"**Logros:** {datos.get('logros', '')}")
                            st.write(f"**Dificultades:** {datos.get('dificultades', '')}")
                            st.write(f"**Observaciones:** {datos.get('observaciones', '')}")
                            st.write(f"**Devoluciones:** {datos.get('devoluciones', '')}")
                            st.write(f"**Compromiso:** {datos.get('compromiso', '')}")
                        if st.button("🗑️ Eliminar Sesión", key=f"btn_del_g_{gid}"):
                            eliminar_grupo_terapeuto(gid)
                            st.toast("🗑️ Sesión eliminada")
                            st.rerun()

    # ==========================================
    # --- MÓDULO 6: CATÁLOGO DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "6. 📦 Catálogo General de Medicamentos":
        st.title("📦 Catálogo Central de Medicamentos (Farmacia)")
        st.caption("Catálogo maestro de fármacos autorizados e inventario global")
        
        tab_cat1, tab_cat2 = st.tabs(["📋 Catálogo Maestro", "➕ Agregar Nuevo Fármaco"])
        
        with tab_cat1:
            cat_m = obtener_catalogo_meds()
            st.dataframe([{"ID": m[0], "Nombre": m[1], "Presentación": m[2], "Concentración": m[3]} for m in cat_m], use_container_width=True)
            
        with tab_cat2:
            with st.form("form_add_cat_med"):
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1:
                    m_nom_n = st.text_input("Nombre Comercial / Genérico *")
                with c_m2:
                    m_pres_n = st.text_input("Presentación (Comprimidos, Gotas, etc.) *")
                with c_m3:
                    m_conc_n = st.text_input("Concentración (500mg, 20mg, etc.) *")
                
                btn_cat = st.form_submit_button("➕ Guardar en Catálogo", use_container_width=True)
                if btn_cat:
                    if not m_nom_n.strip():
                        st.error("⚠️ El nombre es obligatorio.")
                    else:
                        ok_m, msg_m = agregar_catalogo_med(m_nom_n, m_pres_n, m_conc_n)
                        if ok_m:
                            st.toast("🎉 Fármaco agregado al catálogo")
                            st.success(f"✅ ¡{m_nom_n} agregado correctamente!")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg_m}")

    # ==========================================
    # --- MÓDULO 7: CONTROL DE DOSIS ---
    # ==========================================
    elif menu == "7. 💊 Control de Medicamentos y Dosis":
        st.title("💊 Prescripción e Inventario por Paciente")
        
        pacientes_a = listar_pacientes_bd('A')
        if not pacientes_a:
            st.info("No hay residentes activos.")
        else:
            dict_m_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_a}
            sel_mp = st.selectbox("🔑 Selecciona el Residente", list(dict_m_p.keys()))
            p_id_mp = dict_m_p[sel_mp]
            
            meds_curr, obs_curr = obtener_medicamentos_paciente(p_id_mp)
            cat_list = [m[1] for m in obtener_catalogo_meds()]
            
            st.subheader("Esquema de Prescripción")
            with st.form("form_prescripcion"):
                n_meds = st.number_input("Número de Medicamentos Prescritos", min_value=1, max_value=10, value=len(meds_curr) if len(meds_curr)>0 else 1)
                
                meds_input = []
                for i in range(int(n_meds)):
                    st.markdown(f"**Medicamento #{i+1}**")
                    c_d1, c_d2, c_d3, c_d4, c_d5 = st.columns([3, 1, 1, 1, 2])
                    val_m = meds_curr[i] if i < len(meds_curr) else {}
                    
                    with c_d1:
                        nom_m = st.selectbox(f"Fármaco #{i+1}", cat_list, key=f"med_nom_{p_id_mp}_{i}")
                    with c_d2:
                        dm = st.number_input("Mañana", min_value=0.0, step=0.5, value=float(val_m.get("dosis_manana", 0)), key=f"dm_{p_id_mp}_{i}")
                    with c_d3:
                        dt = st.number_input("Tarde", min_value=0.0, step=0.5, value=float(val_m.get("dosis_tarde", 0)), key=f"dt_{p_id_mp}_{i}")
                    with c_d4:
                        dn = st.number_input("Noche", min_value=0.0, step=0.5, value=float(val_m.get("dosis_noche", 0)), key=f"dn_{p_id_mp}_{i}")
                    with c_d5:
                        ex = st.number_input("Stock Actual", min_value=0, value=int(val_m.get("existencia", 0)), key=f"ex_{p_id_mp}_{i}")
                        
                    meds_input.append({"nombre": nom_m, "dosis_manana": dm, "dosis_tarde": dt, "dosis_noche": dn, "existencia": ex})
                    
                obs_m = st.text_area("Indicaciones Médicas Especiales", value=obs_curr)
                
                btn_save_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                if btn_save_meds:
                    guardar_medicamentos_paciente(p_id_mp, meds_input, obs_m, st.session_state["username"])
                    st.toast("🎉 Esquema guardado exitosamente")
                    st.success("✅ Prescripción e inventario actualizados.")

    # ==========================================
    # --- MÓDULO 8: ENTREGA DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "8. 🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Entrega y Descuento de Stock")
        
        pacientes_a = listar_pacientes_bd('A')
        if not pacientes_a:
            st.info("No hay residentes activos.")
        else:
            dict_e_p = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_a}
            sel_ep = st.selectbox("🔑 Selecciona el Residente para Entrega", list(dict_e_p.keys()))
            p_id_ep = dict_e_p[sel_ep]
            
            meds_e, obs_e = obtener_medicamentos_paciente(p_id_ep)
            if not meds_e:
                st.warning("Este residente no tiene medicamentos prescritos.")
            else:
                with st.form("form_entrega"):
                    st.subheader(f"Surtido Diario para: {sel_ep}")
                    entregas_list = []
                    
                    for i, m in enumerate(meds_e):
                        m_nom = m.get("nombre", f"Med #{i+1}")
                        d_tot = float(m.get("dosis_manana",0)) + float(m.get("dosis_tarde",0)) + float(m.get("dosis_noche",0))
                        ex_act = int(m.get("existencia", 0))
                        
                        st.markdown(f"💊 **{m_nom}** | Dosis recomendada: `{d_tot}` | Stock actual: `{ex_act}`")
                        cant_ent = st.number_input(f"Cantidad a Entregar de {m_nom}", min_value=0, max_value=ex_act, value=min(int(d_tot), ex_act), key=f"f_ent_{p_id_ep}_{i}")
                        entregas_list.append({"index": i, "nombre": m_nom, "entregado": cant_ent, "nuevo_stock": ex_act - cant_ent})
                        
                    btn_entregar = st.form_submit_button("📦 Registrar Entrega y Descontar Stock", use_container_width=True)
                    if btn_entregar:
                        for e in entregas_list:
                            idx = e["index"]
                            meds_e[idx]["existencia"] = e["nuevo_stock"]
                            
                        guardar_medicamentos_paciente(p_id_ep, meds_e, obs_e, st.session_state["username"])
                        guardar_entrega_meds(p_id_ep, st.session_state["nombre_completo"], entregas_list)
                        st.toast("🎉 Entrega registrada y stock actualizado")
                        st.success("✅ Entrega guardada exitosamente.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 9: ALERTAS Y COMPRAS ---
    # ==========================================
    elif menu == "9. 🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Stock Crítico y Orden de Compras")
        
        pacientes_a = listar_pacientes_bd('A')
        compras_req = []
        
        for p in pacientes_a:
            pid, pnom = p[0], p[1]
            meds, _ = obtener_medicamentos_paciente(pid)
            for m in meds:
                d_diaria = float(m.get("dosis_manana",0)) + float(m.get("dosis_tarde",0)) + float(m.get("dosis_noche",0))
                ex = int(m.get("existencia", 0))
                if d_diaria > 0:
                    dias_rest = ex / d_diaria if d_diaria > 0 else 999
                    if dias_rest <= 3:
                        compras_req.append({"paciente": pnom, "med": m.get("nombre",""), "stock": ex, "nivel": "CRÍTICO (<=3 días)"})
                    elif dias_rest <= 7:
                        compras_req.append({"paciente": pnom, "med": m.get("nombre",""), "stock": ex, "nivel": "PREVENTIVO (<=7 días)"})
                        
        if not compras_req:
            st.success("✅ ¡Inventario saludable! No hay medicamentos en nivel crítico o preventivo.")
        else:
            st.warning(f"⚠️ Se detectaron **{len(compras_req)}** medicamentos que requieren reabastecimiento.")
            st.dataframe(compras_req, use_container_width=True)
            
            pdf_compras = generar_pdf_compras_farmacia(compras_req)
            with open(pdf_compras, "rb") as f:
                st.download_button("🖨️ Descargar Orden de Compras en PDF", f, file_name=pdf_compras, mime="application/pdf")

    # ==========================================
    # --- MÓDULO 10: REPOSITORIO DE DOCUMENTOS ---
    # ==========================================
    elif menu == "10. 📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos de la Comunidad")
        st.caption("Archivero central para formatos, reglamentos, manuales y guías clínicas")
        st.info("💡 Utiliza esta sección para resguardar los formatos oficiales en PDF o Word.")

    # ==========================================
    # --- MÓDULO 11: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "11. 📦 Respaldo y Restauración":
        st.title("📦 Respaldo & Restauración de Base de Datos")
        
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.subheader("1. Descargar Respaldo Actual")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="💾 Descargar Base de Datos (.db)",
                        data=f,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
            else:
                st.error("No se encontró el archivo de base de datos.")
                
        with col_res2:
            st.subheader("2. Restaurar Base de Datos")
            uploaded_db = st.file_uploader("Sube un archivo de respaldo (.db)", type=["db", "sqlite3"])
            if uploaded_db is not None:
                if st.button("⚠️ Confirmar Restauración", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    st.toast("🎉 Base de datos restaurada correctamente")
                    st.success("✅ ¡Base de datos restaurada! Reiniciando aplicación...")
                    st.rerun()

    # ==========================================
    # --- MÓDULO 12: CONFIGURACIÓN Y SEGURIDAD ---
    # ==========================================
    elif menu == "12. ⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración del Sistema, Staff & Roles")
        
        tab_sec1, tab_sec2, tab_sec3 = st.tabs(["🔑 Cambiar Contraseña", "👥 Gestión de Usuarios Staff y Roles", "⚙️ Requisitos por Etapa"])
        
        with tab_sec1:
            st.subheader("Cambiar Mi Contraseña")
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
            st.subheader("👥 Administración de Personal Staff, Roles y Bloqueo por Vacaciones")
            
            rol_actual = st.session_state.get("rol", "Administrador")
            if rol_actual != "Administrador":
                st.warning("🔒 La administración de usuarios y roles es exclusiva para el **Administrador / Director**.")
            else:
                modo_sys_u = st.radio("Acción:", ["🆕 Registrar Nuevo Usuario Staff", "✏️ Editar / Bloquear Existente"], horizontal=True)
                lista_usr_sys = obtener_usuarios_sistema()
                
                if modo_sys_u == "🆕 Registrar Nuevo Usuario Staff":
                    with st.form("form_alta_staff"):
                        st.subheader("Alta de Usuario de Sistema")
                        c_su1, c_su2 = st.columns(2)
                        with c_su1:
                            u_uname = st.text_input("👤 Nombre de Usuario (Login) *")
                            u_full = st.text_input("📛 Nombre Completo del Servidor *")
                        with c_su2:
                            u_rol = st.selectbox("🏷️ Rol Asignado *", ["Administrador", "Consejero / Evaluador Clínico", "Médico / Farmacia"])
                            u_est_sel = st.selectbox("📌 Estatus *", ["A - Activo", "B - Bloqueado (Vacaciones / Inactivo)"])
                            u_est = 'A' if u_est_sel.startswith('A') else 'B'
                            
                        u_pass = st.text_input("🔑 Contraseña *", type="password")
                        btn_sys_save = st.form_submit_button("💾 Guardar Usuario Staff", use_container_width=True)
                        
                        if btn_sys_save:
                            if not u_uname.strip() or not u_full.strip() or not u_pass:
                                st.error("⚠️ Nombre de usuario, nombre completo y contraseña son obligatorios.")
                            else:
                                ok_s, msg_s = guardar_usuario_sistema(u_uname.strip(), u_pass, u_full.strip(), u_rol, u_est)
                                if ok_s:
                                    st.toast(f"🎉 ¡Usuario {u_uname} registrado!")
                                    st.success(f"✅ ¡Usuario **{u_full}** (`{u_uname}`) registrado correctamente!")
                                    st.balloons()
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg_s}")
                else:
                    if not lista_usr_sys:
                        st.info("No hay usuarios staff registrados.")
                    else:
                        dict_sys_u = {f"{u[2]} ({u[1]}) - Rol: {u[3]} [{ 'Activo' if u[4]=='A' else 'Bloqueado' }]": u for u in lista_usr_sys}
                        sel_su_edit = st.selectbox("🔑 Selecciona Usuario Staff a Editar", list(dict_sys_u.keys()))
                        su_data = dict_sys_u[sel_su_edit]
                        
                        with st.form("form_edit_staff"):
                            st.subheader(f"Editando: {su_data[2]} ({su_data[1]})")
                            c_eu1, c_eu2 = st.columns(2)
                            with c_eu1:
                                su_full_e = st.text_input("Nombre Completo *", value=su_data[2])
                                roles_list = ["Administrador", "Consejero / Evaluador Clínico", "Médico / Farmacia"]
                                idx_r = roles_list.index(su_data[3]) if su_data[3] in roles_list else 0
                                su_rol_e = st.selectbox("Rol Asignado *", roles_list, index=idx_r)
                            with c_eu2:
                                su_est_opts = ["A - Activo", "B - Bloqueado (Vacaciones / Inactivo)"]
                                idx_e = 1 if su_data[4] == 'B' else 0
                                su_est_sel_e = st.selectbox("Estatus *", su_est_opts, index=idx_e)
                                su_est_e = 'A' if su_est_sel_e.startswith('A') else 'B'
                                su_pass_e = st.text_input("🔑 Contraseña (dejar en blanco para conservar actual)", type="password")
                                
                            btn_edit_sys = st.form_submit_button("💾 Guardar Cambios de Usuario", use_container_width=True)
                            if btn_edit_sys:
                                ok_se, msg_se = guardar_usuario_sistema(su_data[1], su_pass_e if su_pass_e else None, su_full_e.strip(), su_rol_e, su_est_e)
                                if ok_se:
                                    st.toast("🎉 Usuario actualizado")
                                    st.success("✅ Cambios guardados correctamente.")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg_se}")
                                    
                st.divider()
                st.subheader("📋 Directorio de Personal Staff")
                for u_item in lista_usr_sys:
                    uid, uname, ufull, urol, uest = u_item
                    st_badge = "🟢 Activo" if uest == 'A' else "🔒 Bloqueado (Vacaciones)"
                    c_us1, c_us2, c_us3 = st.columns([3, 1, 1])
                    with c_us1:
                        st.write(f"👤 **{ufull}** (`{uname}`) | Rol: **{urol}** | Estatus: {st_badge}")
                    with c_us2:
                        if uest == 'A':
                            dis_block = (uname == st.session_state["username"] or uname == "admin")
                            if st.button("🔒 Bloquear", key=f"btn_blk_{uname}", disabled=dis_block, help="Bloquear por periodo de vacaciones"):
                                cambiar_estatus_usuario_sistema(uname, 'B')
                                st.toast(f"🔒 Usuario {uname} bloqueado")
                                st.rerun()
                        else:
                            if st.button("🟢 Activar", key=f"btn_act_{uname}"):
                                cambiar_estatus_usuario_sistema(uname, 'A')
                                st.toast(f"🟢 Usuario {uname} reactivado")
                                st.rerun()
                    with c_us3:
                        dis_del = (uname == st.session_state["username"] or uname == "admin")
                        if st.button("🗑️ Eliminar", key=f"btn_del_u_{uname}", disabled=dis_del):
                            ok_del, msg_del = eliminar_usuario_sistema(uname)
                            if ok_del:
                                st.toast(f"🗑️ Usuario {uname} eliminado")
                                st.rerun()
                            else:
                                st.error(msg_del)

        with tab_sec3:
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
                        st.toast("🎉 Requisito agregado exitosamente")
                        st.success("✅ Requisito agregado exitosamente.")
                        st.rerun()

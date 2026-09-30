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

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios Administrativos del Sistema (Login & Roles)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador',
            estatus TEXT DEFAULT 'A'
        )
    """)
    
    # Migración segura de columnas si la DB proviene de una versión anterior
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
    
    # 4. Tabla de Catálogo Central de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            fecha_registro TEXT
        )
    """)
    
    # Poblar Catálogo Base si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_base = [
            ("Fluoxetina", "Cápsula", "20 mg"),
            ("Sertralina", "Tableta", "50 mg"),
            ("Valproato de Magnesio", "Tableta", "200 mg"),
            ("Olanzapina", "Tableta", "10 mg"),
            ("Quetiapina", "Tableta", "100 mg"),
            ("Omeprazol", "Cápsula", "20 mg"),
            ("Paracetamol", "Tableta", "500 mg"),
            ("Clonazepam", "Gotas", "2.5 mg/ml")
        ]
        f_now = datetime.now().strftime("%Y-%m-%d")
        for m_nom, m_pres, m_conc in meds_base:
            try:
                c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
                          (m_nom, m_pres, m_conc, f_now))
            except Exception:
                pass
    
    # 5. Tabla de Medicamentos e Inventario asignados a Pacientes
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
    
    # 6. Tabla de Historial de Entregas
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    """)
    
    # 7. Tabla de Grupos Terapéuticos
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
    
    # 9. Tabla de Requisitos por Etapa
    c.execute("""
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    """)
    
    # 10. Tabla de Repositorio de Documentos (Solo Administrador)
    c.execute("""
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
    """)
    
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'A'))
    
    # Requisitos Iniciales
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
    # Consulta ultra-segura basada únicamente en columnas fundamentales
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    
    uname, ufull = row[0], row[1]
    rol = "Administrador"
    estatus = "A"
    
    try:
        c.execute('SELECT rol, estatus FROM usuarios WHERE username = ?', (uname,))
        r = c.fetchone()
        if r:
            rol = r[0] if r[0] else "Administrador"
            estatus = r[1] if r[1] else "A"
    except Exception:
        pass
        
    conn.close()
    return (uname, ufull, rol, estatus)

def obtener_usuarios_sistema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('SELECT id, username, nombre_completo, rol, estatus FROM usuarios ORDER BY username')
        rows = c.fetchall()
    except Exception:
        c.execute('SELECT id, username, nombre_completo FROM usuarios ORDER BY username')
        raw = c.fetchall()
        rows = [(r[0], r[1], r[2], "Administrador", "A") for r in raw]
    conn.close()
    return rows

def guardar_usuario_sistema(username, password, nombre_completo, rol, estatus='A'):
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
            return False, "La contraseña es requerida para nuevos usuarios."
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  (username, hash_pass(password), nombre_completo, rol, estatus))
    conn.commit()
    conn.close()
    return True, "Usuario del sistema guardado correctamente."

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

# --- FUNCIONES DE PACIENTES Y SERVIDORES ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes ORDER BY ROWID DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row and row[0].startswith("PAC-"):
        try:
            num = int(row[0].split("-")[1]) + 1
            return f"PAC-{num:03d}"
        except Exception:
            pass
    return "PAC-001"

def verificar_duplicado_nombre(nombre_completo, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    nombre_clean = nombre_completo.strip().lower()
    for pid, pnom, pest in rows:
        if paciente_id_actual and pid == paciente_id_actual:
            continue
        if pnom.strip().lower() == nombre_clean:
            return pid, pnom, pest
    return None

def guardar_paciente(paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo_usr, etapa_act, f_ini_etapa, usr_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ing_str = f_ingreso.strftime("%Y-%m-%d") if isinstance(f_ingreso, (date, datetime)) else str(f_ingreso)
    f_nac_str = f_nac.strftime("%Y-%m-%d") if isinstance(f_nac, (date, datetime)) else str(f_nac)
    f_ini_str = f_ini_etapa.strftime("%Y-%m-%d") if isinstance(f_ini_etapa, (date, datetime)) else (str(f_ini_etapa) if f_ini_etapa else f_ing_str)
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute("""
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        """, (nombre, f_ing_str, f_nac_str, sexo, estatus, tipo_usr, etapa_act, f_ini_str, f_act, paciente_id))
    else:
        c.execute("""
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, nombre, f_ing_str, f_nac_str, sexo, estatus, tipo_usr, etapa_act, f_ini_str, f_act, f_act, usr_reg))
    conn.commit()
    conn.close()

def obtener_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes ORDER BY nombre_completo')
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

def promover_etapa(paciente_id, etapa_origen, etapa_destino, usr_autoriza):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (etapa_destino, f_hoy, f_act, paciente_id))
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_origen, etapa_destino, f_act, usr_autoriza))
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (hermano_id, f_act, paciente_id))
    conn.commit()
    conn.close()

def soltar_hermano_mayor(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (f_hoy, f_act, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE FARMACIA Y MEDICAMENTOS ---
def obtener_catalogo_meds():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, presentacion, concentracion, fecha_registro FROM catalogo_medicamentos ORDER BY nombre')
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
        return True, "Medicamento agregado al catálogo central."
    except Exception as e:
        conn.close()
        return False, f"El medicamento ya existe o hubo un error: {e}"

def eliminar_catalogo_med(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

def guardar_medicamentos_paciente(paciente_id, meds_json, observaciones, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    m_str = json.dumps(meds_json, ensure_ascii=False)
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                  (m_str, observaciones, f_act, usr, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)',
                  (paciente_id, m_str, observaciones, f_act, f_act, usr))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return json.loads(row[0]), row[1], row[2]
        except Exception:
            return [], row[1], row[2]
    return [], "", ""

def guardar_entrega_meds(paciente_id, entregado_por, detalle_json):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    d_str = json.dumps(detalle_json, ensure_ascii=False)
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, f_act, entregado_por, d_str))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, modalidad, datos, usuario_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_grp = fecha_grupo.strftime("%Y-%m-%d") if isinstance(fecha_grupo, (date, datetime)) else str(fecha_grupo)
    datos["modalidad"] = modalidad
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute("""
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (paciente_id, tipo_grupo, etapa_al_momento, f_grp, facilitador, datos_json, f_act, usuario_reg))
    conn.commit()
    conn.close()

def actualizar_grupo_terapeuto(grupo_id, tipo_grupo, fecha_grupo, facilitador, modalidad, datos):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_grp = fecha_grupo.strftime("%Y-%m-%d") if isinstance(fecha_grupo, (date, datetime)) else str(fecha_grupo)
    datos["modalidad"] = modalidad
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute("""
        UPDATE grupos_terapeutos
        SET tipo_grupo = ?, fecha_grupo = ?, facilitador = ?, datos_json = ?
        WHERE id = ?
    """, (tipo_grupo, f_grp, facilitador, datos_json, grupo_id))
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
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    count = c.fetchone()[0]
    conn.close()
    return count

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC', (paciente_id,))
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

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def listar_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "TODAS":
        c.execute('SELECT id, carpeta, nombre_archivo, tipo_archivo, descripcion, tamano_bytes, fecha_subida, subido_por FROM repositorio_documentos WHERE carpeta = ? ORDER BY fecha_subida DESC', (carpeta_filtro,))
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, tipo_archivo, descripcion, tamano_bytes, fecha_subida, subido_por FROM repositorio_documentos ORDER BY fecha_subida DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_documento_repositorio(carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_bytes, subido_por):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tamano = len(contenido_bytes)
    c.execute("""
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_blob, tamano_bytes, fecha_subida, subido_por)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (carpeta, nombre_archivo, tipo_archivo, descripcion, sqlite3.Binary(contenido_bytes), tamano, f_act, subido_por))
    conn.commit()
    conn.close()

def obtener_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, carpeta, nombre_archivo, tipo_archivo, contenido_blob FROM repositorio_documentos WHERE id = ?', (doc_id,))
    row = c.fetchone()
    conn.close()
    return row

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE REPORTES PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 5, "Sistema Integral de Control y Seguimiento Clínico", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.line(10, self.get_y(), self.epw + 10, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")

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

def generar_pdf_entrevista(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p = obtener_paciente(paciente_id)
    pnom = p[1] if p else paciente_id
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE CONSEJERÍA E HISTORIAL CLINICO - {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresión: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    for sec_title, fields in datos.items():
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(pdf.epw, 7, limpiar_texto(sec_title.upper()), border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.ln(2)
        if isinstance(fields, dict):
            for f_key, f_val in fields.items():
                val_str = str(f_val) if f_val is not None else ""
                pdf.multi_cell(pdf.epw, 5, f"{limpiar_texto(f_key)}: {limpiar_texto(val_str)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        
    pdf_filename = f"Expediente_{paciente_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_compras():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTA DE COMPRAS DE MEDICAMENTOS Y STOCK CRÍTICO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    pacientes = [p for p in obtener_pacientes() if p[5] == "A"]
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [45, 55, 25, 20, 25, 20]
    headers = ["Residente", "Medicamento", "Dosis Diaria", "Stock", "Días Rest.", "Comprar"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for p in pacientes:
        pid, pnom = p[0], p[1]
        meds, _, _ = obtener_medicamentos_paciente(pid)
        for m in meds:
            d_tot = float(m.get("dosis_manana", 0)) + float(m.get("dosis_tarde", 0)) + float(m.get("dosis_noche", 0))
            ex = int(m.get("existencia", 0))
            if d_tot > 0:
                dias = ex / d_tot
                if dias <= 7:
                    cs = max(0, int((d_tot * 30) - ex))
                    pdf.cell(col_w[0], 6, limpiar_texto(pnom[:22]), border=1)
                    pdf.cell(col_w[1], 6, limpiar_texto(m.get("nombre", "")[:28]), border=1)
                    pdf.cell(col_w[2], 6, f"{d_tot:.1f}", border=1, align="C")
                    pdf.cell(col_w[3], 6, str(ex), border=1, align="C")
                    pdf.cell(col_w[4], 6, f"{dias:.1f} d", border=1, align="C")
                    pdf.cell(col_w[5], 6, str(cs), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
            
    pdf_filename = f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_historial_grupos(paciente_id):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p = obtener_paciente(paciente_id)
    pnom = p[1] if p else paciente_id
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE GRUPOS TERAPÉUTICOS - {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresión: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    grupos = listar_grupos_paciente(paciente_id)
    if not grupos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay sesiones de grupos registrados para este paciente.", align="C")
    else:
        for g in grupos:
            gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
            datos = json.loads(djson)
            mod = datos.get("modalidad", "Normal")
            
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

# --- INICIALIZAR DB Y ESTADO DE SESIÓN ---
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
                    uname, ufull, urol, uest = usuario_valido
                    if uest == 'B':
                        st.error("❌ La cuenta de este usuario se encuentra temporalmente bloqueada/inactiva (periodo de vacaciones). Contacte al Administrador.")
                    else:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = uname
                        st.session_state["nombre_completo"] = ufull
                        st.session_state["rol"] = urol
                        st.toast("🎉 ¡Acceso concedido!")
                        st.success("¡Acceso concedido!")
                        st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL Y NAVEGACIÓN (12 MÓDULOS) ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario Staff**: {st.session_state['nombre_completo']}")
    st.sidebar.caption(f"🏷️ **Rol**: {st.session_state['rol']}")
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["nombre_completo"] = ""
        st.session_state["rol"] = "Administrador"
        st.rerun()
        
    st.sidebar.divider()
    
    menu_opciones = [
        "👤 Registro y Edición de Usuarios",
        "📝 Nueva Entrevista / Editar",
        "🔍 Buscar y Listar Pacientes",
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "📦 Catálogo General de Medicamentos",
        "💊 Control de Medicamentos y Dosis",
        "🚚 Entrega de Medicamentos",
        "🚨 Alertas de Existencia y Compras",
        "📁 Repositorio de Documentos",
        "📦 Respaldo y Restauración",
        "⚙️ Configuración / Seguridad"
    ]
    
    menu = st.sidebar.radio("Navegación del Sistema", menu_opciones)
    
    # PERMISOS POR ROL
    es_admin = (st.session_state["rol"] == "Administrador")
    es_clinico = (st.session_state["rol"] in ["Administrador", "Consejero / Evaluador Clínico"])
    es_farmacia = (st.session_state["rol"] in ["Administrador", "Médico / Farmacia"])
    
    # ==========================================
    # --- MÓDULO 1: REGISTRO DE PACIENTES Y SERVIDORES ---
    # ==========================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes y Servidores")
        st.caption("Módulo para dar de alta o actualizar residentes, servidores y personal operativo")
        
        modo = st.radio("Selecciona Acción:", ["🆕 Registrar Nuevo Residente / Servidor", "✏️ Editar Usuario Existente"], horizontal=True)
        
        all_p = obtener_pacientes()
        p_edit_data = None
        
        if modo == "✏️ Editar Usuario Existente":
            if not all_p:
                st.warning("No hay usuarios registrados en el sistema.")
            else:
                dict_p = {f"{p[1]} ({p[0]}) - {p[6]} [{p[5]}]": p[0] for p in all_p}
                sel_p_key = st.selectbox("🔑 Selecciona el Residente / Servidor a Editar", list(dict_p.keys()))
                sel_p_id = dict_p[sel_p_key]
                p_edit_data = obtener_paciente(sel_p_id)
                
        with st.form("form_paciente"):
            st.subheader("Datos Basales e Identificación")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                if modo == "🆕 Registrar Nuevo Residente / Servidor":
                    p_id = st.text_input("🔑 Folio Único *", value=generar_siguiente_folio(), disabled=True)
                else:
                    p_id = st.text_input("🔑 Folio Único *", value=p_edit_data[0] if p_edit_data else "", disabled=True)
                    
                val_nom = p_edit_data[1] if p_edit_data else ""
                p_nom = st.text_input("📛 Nombre Completo *", value=val_nom)
                
            with c2:
                val_fing = datetime.strptime(p_edit_data[2], "%Y-%m-%d").date() if (p_edit_data and p_edit_data[2]) else date.today()
                p_fing = st.date_input("📅 Fecha de Ingreso *", value=val_fing)
                
                val_fnac = datetime.strptime(p_edit_data[3], "%Y-%m-%d").date() if (p_edit_data and p_edit_data[3]) else date(2000, 1, 1)
                p_fnac = st.date_input("🎂 Fecha de Nacimiento *", value=val_fnac)
                
            with c3:
                sex_opts = ["MASCULINO", "FEMENINO"]
                idx_sex = sex_opts.index(p_edit_data[4]) if (p_edit_data and p_edit_data[4] in sex_opts) else 0
                p_sexo = st.selectbox("👤 Sexo *", sex_opts, index=idx_sex)
                
                type_opts = ["Paciente", "Servidor", "Staff Operativo"]
                idx_type = type_opts.index(p_edit_data[6]) if (p_edit_data and p_edit_data[6] in type_opts) else 0
                p_tipo = st.selectbox("🏷️ Tipo de Usuario *", type_opts, index=idx_type)
                
            st.divider()
            c4, c5 = st.columns(2)
            with c4:
                etapas_opts = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_et = etapas_opts.index(p_edit_data[7]) if (p_edit_data and p_edit_data[7] in etapas_opts) else 0
                p_etapa = st.selectbox("🎯 Etapa Inicial / Actual *", etapas_opts, index=idx_et)
            with c5:
                est_opts = ["A - ACTIVO", "B - BAJA / EGRESADO", "S - SUSPENDIDO"]
                idx_est = 0
                if p_edit_data:
                    if p_edit_data[5] == 'B': idx_est = 1
                    elif p_edit_data[5] == 'S': idx_est = 2
                p_estatus_sel = st.selectbox("📌 Estatus *", est_opts, index=idx_est)
                p_estatus = p_estatus_sel.split(" - ")[0]
                
            btn_guardar_p = st.form_submit_button("💾 Guardar Registro de Usuario", use_container_width=True)
            
            if btn_guardar_p:
                if not p_nom.strip():
                    st.error("⚠️ El nombre completo del residente es un campo obligatorio.")
                else:
                    dup = verificar_duplicado_nombre(p_nom, p_id)
                    if dup and modo == "🆕 Registrar Nuevo Residente / Servidor":
                        st.warning(f"⚠️ Ya existe un usuario registrado con el nombre **{p_nom}** (Folio: {dup[0]}).")
                    else:
                        guardar_paciente(p_id, p_nom.strip(), p_fing, p_fnac, p_sexo, p_estatus, p_tipo, p_etapa, p_fing, st.session_state["username"])
                        st.toast("🎉 ¡Registro guardado exitosamente!")
                        st.success(f"✅ ¡Usuario **{p_nom}** (`{p_id}`) guardado exitosamente!")
                        st.balloons()
                        st.rerun()

    # ==========================================
    # --- MÓDULO 2: NUEVA ENTREVISTA DE CONSEJERÍA ---
    # ==========================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📝 Entrevista Inicial de Consejería y Evaluación")
        st.caption("Captura completa socio-demográfica, sustancias de consumo y tamizajes")
        
        pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados.")
        else:
            dict_p_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_e = st.selectbox("🔑 Selecciona el Residente para Entrevista", list(dict_p_ent.keys()))
            p_id_ent = dict_p_ent[sel_p_e]
            
            st.info(f"📋 Formulario de Consejería Inicial para el folio: **{p_id_ent}**")
            with st.form("form_entrevista"):
                st.subheader("1. Información General y Socio-Demográfica")
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    e_ocupacion = st.text_input("Ocupación / Oficio")
                    e_estudios = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria / Bachillerato", "Licenciatura", "Postgrado", "Sin estudios"])
                with c_e2:
                    e_ecivil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"])
                    e_vivienda = st.selectbox("Tipo de Vivienda", ["Propia", "Rentada", "Familiar", "Situación de calle"])
                    
                st.divider()
                st.subheader("2. Sustancias de Consumo y Patrones")
                e_sust_impacto = st.text_input("Sustancia de Mayor Impacto / Principal")
                e_sust_inicio = st.text_input("Edad de Inicio de Consumo")
                e_sust_frecuencia = st.selectbox("Frecuencia de Consumo Reciente", ["Diario", "3-4 veces por semana", "Fines de semana", "Ocasional / En crisis"])
                
                st.divider()
                st.subheader("3. Tamizajes Clínicos")
                e_beck_ans = st.number_input("Puntaje Beck Ansiedad (0-63)", min_value=0, max_value=63, value=0)
                e_beck_dep = st.number_input("Puntaje Beck Depresión (0-63)", min_value=0, max_value=63, value=0)
                
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ent:
                    datos_ent = {
                        "Socio-Demografico": {"Ocupación": e_ocupacion, "Escolaridad": e_estudios, "Estado Civil": e_ecivil, "Vivienda": e_vivienda},
                        "Consumo": {"Sustancia Principal": e_sust_impacto, "Edad Inicio": e_sust_inicio, "Frecuencia": e_sust_frecuencia},
                        "Tamizajes": {"Beck Ansiedad": e_beck_ans, "Beck Depresion": e_beck_dep}
                    }
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    d_str = json.dumps(datos_ent, ensure_ascii=False)
                    c.execute('INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                              (p_id_ent, f_act, f_act, st.session_state["username"], d_str))
                    conn.commit()
                    conn.close()
                    st.success("✅ Entrevista inicial guardada exitosamente.")
                    st.toast("🎉 Entrevista guardada")

    # ==========================================
    # --- MÓDULO 3: BUSCAR Y LISTAR PACIENTES ---
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio General de Residentes y Expedientes")
        st.caption("Consulta alfabética, filtro por estatus y descarga de PDF")
        
        all_p = obtener_pacientes()
        if not all_p:
            st.info("No hay residentes registrados.")
        else:
            df_p = [{"Folio": p[0], "Nombre": p[1], "Ingreso": p[2], "Sexo": p[4], "Estatus": p[5], "Tipo": p[6], "Etapa": p[7]} for p in all_p]
            st.dataframe(df_p, use_container_width=True)
            
            st.divider()
            dict_pdf = {f"{p[1]} ({p[0]})": p[0] for p in all_p}
            sel_pdf = st.selectbox("🔑 Selecciona Residente para Generar Expediente PDF", list(dict_pdf.keys()))
            pid_pdf = dict_pdf[sel_pdf]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (pid_pdf,))
            r_ent = c.fetchone()
            conn.close()
            
            datos_ent = json.loads(r_ent[0]) if (r_ent and r_ent[0]) else {"Aviso": {"Estado": "Sin entrevista registrada aún"}}
            pdf_path = generar_pdf_entrevista(pid_pdf, datos_ent)
            
            with open(pdf_path, "rb") as f:
                st.download_button("🖨️ Descargar Expediente de Consejería (PDF)", data=f, file_name=pdf_path, mime="application/pdf", use_container_width=True)

    # ==========================================
    # --- MÓDULO 4: GESTIÓN DE ETAPAS & PROCESO ---
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas, Promoción y Hermano Mayor")
        
        pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes_activos:
            st.warning("No hay usuarios activos.")
        else:
            dict_p_et = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_activos}
            sel_p_et = st.selectbox("🔑 Selecciona el Residente a Gestionar", list(dict_p_et.keys()))
            p_data = dict_p_et[sel_p_et]
            p_id_et, p_nom_et, p_etapa_act = p_data[0], p_data[1], p_data[7]
            
            st.subheader(f"Residente: {p_nom_et} | Etapa Actual: **{p_etapa_act}**")
            
            t_prom, t_hermano = st.tabs(["🚀 Promover de Etapa", "🤝 Asignación de Hermano Mayor"])
            
            with t_prom:
                st.write("Verificación de Requisitos teóricos y sesiones de grupo:")
                reqs = obtener_requisitos_etapa(p_etapa_act)
                for rid, rtxt, esg in reqs:
                    if esg == 1:
                        tipo_g = "Terapia de Grupo"
                        if "Aquí y Ahora" in rtxt: tipo_g = "Aquí y Ahora"
                        elif "Feedback" in rtxt: tipo_g = "Feedback"
                        cnt = contar_grupos_etapa(p_id_et, p_etapa_act, tipo_g)
                        st.write(f"• **{rtxt}**: `{cnt}` sesiones registradas en esta etapa")
                    else:
                        st.write(f"• {rtxt}")
                        
                st.divider()
                etapas_list = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                curr_idx = etapas_list.index(p_etapa_act) if p_etapa_act in etapas_list else 0
                if curr_idx < len(etapas_list) - 1:
                    next_etapa = etapas_list[curr_idx + 1]
                    if st.button(f"🚀 Promover a {next_etapa}", use_container_width=True):
                        promover_etapa(p_id_et, p_etapa_act, next_etapa, st.session_state["username"])
                        st.success(f"🎉 ¡{p_nom_et} promovido exitosamente a **{next_etapa}**!")
                        st.balloons()
                        st.rerun()
                else:
                    st.info("El residente se encuentra en la etapa máxima (SERVICIO SOCIAL).")
                    
            with t_hermano:
                st.subheader("Asignación de Hermano Mayor")
                posibles_hm = [p for p in pacientes_activos if p[0] != p_id_et]
                if posibles_hm:
                    dict_hm = {f"{p[1]} ({p[0]})": p[0] for p in posibles_hm}
                    sel_hm = st.selectbox("Selecciona Hermano Mayor", list(dict_hm.keys()))
                    if st.button("🤝 Asignar Hermano Mayor"):
                        asignar_hermano_mayor(p_id_et, dict_hm[sel_hm])
                        st.success("Hermano Mayor asignado exitosamente.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 5: GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Módulo para capturar, modificar, eliminar y consultar sesiones de Terapia de Grupo, Aquí y Ahora, Feedback y Confronto Especial")
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar / Editar Sesión de Grupo", "📜 Historial, Conteo y PDF"])
        
        with tab_reg_g:
            pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
            if not pacientes_activos:
                st.warning("No hay usuarios activos registrados.")
            else:
                modo_grp = st.radio("Acción a realizar:", ["🆕 Registrar Nueva Sesión", "✏️ Modificar Sesión Existente"], horizontal=True)
                
                dict_pac_g = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1], p[7]) for p in pacientes_activos}
                sel_pac_g = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_g.keys()), key="sel_grp_pac")
                p_id_g, p_nombre_g, p_etapa_g = dict_pac_g[sel_pac_g]
                
                g_edit_id = None
                datos_edit_g = {}
                
                if modo_grp == "✏️ Modificar Sesión Existente":
                    list_g_p = listar_grupos_paciente(p_id_g)
                    if not list_g_p:
                        st.info("Este paciente no tiene sesiones de grupo registradas para editar.")
                    else:
                        dict_g_edit = {f"ID: {g[0]} | {g[1]} | Fecha: {g[3]} | Facilitador: {g[4]}": g for g in list_g_p}
                        sel_ge = st.selectbox("Selecciona la sesión a editar:", list(dict_g_edit.keys()))
                        g_edit_obj = dict_g_edit[sel_ge]
                        g_edit_id = g_edit_obj[0]
                        datos_edit_g = json.loads(g_edit_obj[5])
                        
                cat_grupos = ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Confronto Especial"]
                tipo_grupo = st.selectbox("🗣️ Tipo de Grupo Terapéutico", cat_grupos)
                
                with st.form("form_grupo_terapeuto"):
                    st.subheader(f"Formulario: {tipo_grupo}")
                    c_g1, c_g2, c_g3 = st.columns(3)
                    with c_g1:
                        st.text_input("Paciente", value=p_nombre_g, disabled=True)
                        st.text_input("Folio", value=p_id_g, disabled=True)
                    with c_g2:
                        st.text_input("Etapa Actual del Paciente", value=p_etapa_g, disabled=True)
                        f_grupo = st.date_input("Fecha del Grupo", value=date.today())
                    with c_g3:
                        facilitador_nombre = st.text_input("Nombre del Facilitador / Staff *", value=st.session_state["nombre_completo"])
                        modalidad_sel = st.selectbox("Modalidad del Grupo *", ["Normal", "Especial"])
                        
                    st.divider()
                    
                    if tipo_grupo in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                        val_comp = datos_edit_g.get("compartimiento", "")
                        val_obs = datos_edit_g.get("observaciones", "")
                        val_dev = datos_edit_g.get("devoluciones", "")
                        val_cmpr = datos_edit_g.get("compromiso", "")
                        
                        compartimiento = st.text_area("Compartimiento (Texto largo) *", value=val_comp)
                        observaciones = st.text_area("Observaciones (Texto largo)", value=val_obs)
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=val_dev)
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=val_cmpr)
                        
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
                                if modo_grp == "🆕 Registrar Nueva Sesión":
                                    guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, modalidad_sel, datos_grp, st.session_state["username"])
                                    st.toast(f"🎉 ¡Sesión de {tipo_grupo} registrada exitosamente!")
                                else:
                                    actualizar_grupo_terapeuto(g_edit_id, tipo_grupo, f_grupo, facilitador_nombre, modalidad_sel, datos_grp)
                                    st.toast("🎉 ¡Sesión de grupo actualizada exitosamente!")
                                st.success("✅ ¡Operación realizada exitosamente!")
                                st.balloons()
                                st.rerun()
                    else: # Feedback
                        val_log = datos_edit_g.get("logros", "")
                        val_dif = datos_edit_g.get("dificultades", "")
                        val_obs = datos_edit_g.get("observaciones", "")
                        val_dev = datos_edit_g.get("devoluciones", "")
                        val_cmpr = datos_edit_g.get("compromiso", "")
                        
                        logros = st.text_area("Logros (Texto largo) *", value=val_log)
                        dificultades = st.text_area("Dificultades (Texto largo) *", value=val_dif)
                        observaciones = st.text_area("Observaciones (Texto largo)", value=val_obs)
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=val_dev)
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=val_cmpr)
                        
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
                                if modo_grp == "🆕 Registrar Nueva Sesión":
                                    guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, modalidad_sel, datos_grp, st.session_state["username"])
                                    st.toast("🎉 ¡Sesión de Feedback registrada exitosamente!")
                                else:
                                    actualizar_grupo_terapeuto(g_edit_id, tipo_grupo, f_grupo, facilitador_nombre, modalidad_sel, datos_grp)
                                    st.toast("🎉 ¡Sesión de Feedback actualizada exitosamente!")
                                st.success("✅ ¡Operación realizada exitosamente!")
                                st.balloons()
                                st.rerun()

        with tab_hist_g:
            pacientes_todos = obtener_pacientes()
            if not pacientes_todos:
                st.info("No hay usuarios registrados.")
            else:
                dict_hist = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_todos}
                sel_h = st.selectbox("🔑 Selecciona el Paciente para Ver Expediente de Grupos", list(dict_hist.keys()))
                p_id_h = dict_hist[sel_h]
                
                pdf_grp = generar_pdf_historial_grupos(p_id_h)
                with open(pdf_grp, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Expediente de Grupos en PDF",
                        data=f,
                        file_name=pdf_grp,
                        mime="application/pdf",
                        key=f"pdf_grp_{p_id_h}"
                    )
                    
                st.divider()
                
                st.subheader("📊 Métrica de Sesiones en Etapa Actual")
                p_obj_h = obtener_paciente(p_id_h)
                etapa_h = p_obj_h[7] if p_obj_h else "ACOGIDA"
                
                cm1, cm2, cm3, cm4 = st.columns(4)
                cm1.metric("Terapia de Grupo", contar_grupos_etapa(p_id_h, etapa_h, "Terapia de Grupo"))
                cm2.metric("Aquí y Ahora", contar_grupos_etapa(p_id_h, etapa_h, "Aquí y Ahora"))
                cm3.metric("Feedback", contar_grupos_etapa(p_id_h, etapa_h, "Feedback"))
                cm4.metric("Confronto Especial", contar_grupos_etapa(p_id_h, etapa_h, "Confronto Especial"))
                
                st.divider()
                grupos_list = listar_grupos_paciente(p_id_h)
                if not grupos_list:
                    st.warning("Este usuario no tiene sesiones de grupo registradas.")
                else:
                    for g in grupos_list:
                        gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
                        datos = json.loads(djson)
                        mod = datos.get("modalidad", "Normal")
                        with st.expander(f"🗣️ **{tgrp}** ({mod}) | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"):
                            st.write(f"**Registrado por:** {ureg} el {freg}")
                            if st.button("🗑️ Eliminar esta sesión de grupo", key=f"del_g_{gid}"):
                                eliminar_grupo_terapeuto(gid)
                                st.toast("🗑️ Sesión eliminada.")
                                st.rerun()
                                
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

    # ==========================================
    # --- MÓDULO 6: CATÁLOGO CENTRAL DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "📦 Catálogo General de Medicamentos":
        st.title("📦 Catálogo Maestro de Medicamentos")
        st.caption("Administración del inventario central de fármacos disponibles en la clínica")
        
        tab_cat1, tab_cat2 = st.tabs(["📋 Catálogo de Fármacos", "➕ Agregar Nuevo Medicamento"])
        
        with tab_cat1:
            cat_meds = obtener_catalogo_meds()
            if not cat_meds:
                st.info("El catálogo central de medicamentos está vacío.")
            else:
                for m in cat_meds:
                    mid, mnom, mpres, mconc, mfreg = m
                    col_m1, col_m2 = st.columns([4, 1])
                    with col_m1:
                        st.write(f"💊 **{mnom}** | Presentación: `{mpres}` | Concentración: `{mconc}`")
                    with col_m2:
                        if st.button("🗑️ Eliminar", key=f"del_med_cat_{mid}"):
                            eliminar_catalogo_med(mid)
                            st.toast("Medicamento eliminado del catálogo.")
                            st.rerun()
                            
        with tab_cat2:
            with st.form("form_add_cat_med"):
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1:
                    m_nombre = st.text_input("Nombre del Medicamento *")
                with c_m2:
                    m_pres = st.text_input("Presentación (Cápsulas, Tabletas, Gotas) *")
                with c_m3:
                    m_conc = st.text_input("Concentración (mg, ml) *")
                    
                btn_add_cat = st.form_submit_button("➕ Agregar al Catálogo Central", use_container_width=True)
                if btn_add_cat:
                    if not m_nombre.strip() or not m_pres.strip() or not m_conc.strip():
                        st.error("⚠️ Todos los campos son obligatorios.")
                    else:
                        ok_m, msg_m = agregar_catalogo_med(m_nombre, m_pres, m_conc)
                        if ok_m:
                            st.toast("🎉 ¡Medicamento agregado exitosamente!")
                            st.success(f"✅ ¡**{m_nombre}** agregado al catálogo maestro!")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg_m}")

    # ==========================================
    # --- MÓDULO 7: CONTROL DE MEDICAMENTOS Y DOSIS ---
    # ==========================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Prescripción e Inventario Asignado por Paciente")
        st.caption("Asignación individual de fármacos, dosis diaria (Mañana, Tarde, Noche) y control de stock")
        
        pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados.")
        else:
            dict_p_med = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_m = st.selectbox("🔑 Selecciona el Residente para Prescripción", list(dict_p_med.keys()))
            p_id_m = dict_p_med[sel_p_m]
            
            cat_meds = obtener_catalogo_meds()
            meds_actuales, obs_actuales, _ = obtener_medicamentos_paciente(p_id_m)
            
            st.subheader(f"Esquema Farmacológico Individual: {sel_p_m}")
            
            with st.form("form_prescripcion"):
                st.write("Selecciona los medicamentos prescritos y define la dosis diaria:")
                
                nuevos_meds_list = []
                for idx, m_cat in enumerate(cat_meds):
                    mid, mnom, mpres, mconc, _ = m_cat
                    
                    prev_assigned = next((item for item in meds_actuales if item.get("nombre") == mnom), None)
                    is_checked = (prev_assigned is not None)
                    
                    chk = st.checkbox(f"💊 **{mnom}** ({mpres} - {mconc})", value=is_checked, key=f"chk_med_{p_id_m}_{mid}")
                    if chk:
                        c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                        with c_d1:
                            dm = st.number_input(f"Mañana ({mnom})", min_value=0.0, step=0.5, value=float(prev_assigned.get("dosis_manana", 0)) if prev_assigned else 0.0, key=f"dm_{p_id_m}_{mid}")
                        with c_d2:
                            dt = st.number_input(f"Tarde ({mnom})", min_value=0.0, step=0.5, value=float(prev_assigned.get("dosis_tarde", 0)) if prev_assigned else 0.0, key=f"dt_{p_id_m}_{mid}")
                        with c_d3:
                            dn = st.number_input(f"Noche ({mnom})", min_value=0.0, step=0.5, value=float(prev_assigned.get("dosis_noche", 0)) if prev_assigned else 0.0, key=f"dn_{p_id_m}_{mid}")
                        with c_d4:
                            ex = st.number_input(f"Stock Asignado ({mnom})", min_value=0, step=1, value=int(prev_assigned.get("existencia", 0)) if prev_assigned else 0, key=f"ex_{p_id_m}_{mid}")
                            
                        nuevos_meds_list.append({
                            "nombre": mnom, "presentacion": mpres, "concentracion": mconc,
                            "dosis_manana": dm, "dosis_tarde": dt, "dosis_noche": dn, "existencia": ex
                        })
                        st.divider()
                        
                obs_meds_in = st.text_area("Observaciones e Indicaciones Médicas", value=obs_actuales)
                
                btn_save_pres = st.form_submit_button("💾 Guardar Esquema Farmacológico", use_container_width=True)
                if btn_save_pres:
                    guardar_medicamentos_paciente(p_id_m, nuevos_meds_list, obs_meds_in, st.session_state["username"])
                    st.toast("🎉 Esquema de medicamentos actualizado.")
                    st.success("✅ Esquema farmacológico guardado exitosamente.")
                    st.rerun()

    # ==========================================
    # --- MÓDULO 8: ENTREGA DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Surtido Diario y Descuento de Stock")
        st.caption("Surtido directo a residentes con actualización inmediata de inventario")
        
        pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados.")
        else:
            dict_p_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_e = st.selectbox("🔑 Selecciona el Residente a Surtir", list(dict_p_ent.keys()))
            p_id_e = dict_p_ent[sel_p_e]
            
            meds_list, obs_meds, _ = obtener_medicamentos_paciente(p_id_e)
            if not meds_list:
                st.warning("Este residente no tiene medicamentos asignados en su esquema.")
            else:
                with st.form("form_entrega_meds"):
                    st.subheader(f"Surtido para: {sel_p_e}")
                    
                    surtido_items = []
                    for i, m in enumerate(meds_list):
                        mnom = m.get("nombre", f"Fármaco #{i+1}")
                        d_diaria = float(m.get("dosis_manana", 0)) + float(m.get("dosis_tarde", 0)) + float(m.get("dosis_noche", 0))
                        ex_actual = int(m.get("existencia", 0))
                        
                        val_def = min(int(d_diaria), ex_actual) if ex_actual > 0 else 0
                        
                        st.markdown(f"💊 **{mnom}** | Dosis diaria requerida: `{d_diaria}` | Stock actual: `{ex_actual}`")
                        cant = st.number_input(f"Cantidad a Entregar ({mnom})", min_value=0, max_value=ex_actual, value=val_def, key=f"surt_{p_id_e}_{i}")
                        surtido_items.append({"idx": i, "nombre": mnom, "entregado": cant, "anterior": ex_actual, "nuevo_stock": ex_actual - cant})
                        
                    btn_confirm_surtido = st.form_submit_button("📦 Confirmar Entrega y Descontar Inventario", use_container_width=True)
                    if btn_confirm_surtido:
                        for s in surtido_items:
                            idx = s["idx"]
                            meds_list[idx]["existencia"] = s["nuevo_stock"]
                            
                        guardar_medicamentos_paciente(p_id_e, meds_list, obs_meds, st.session_state["username"])
                        guardar_entrega_meds(p_id_e, st.session_state["nombre_completo"], surtido_items)
                        st.toast("🎉 Surtido entregado e inventario actualizado.")
                        st.success("✅ Entrega registrada correctamente.")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 9: ALERTAS DE EXISTENCIA Y COMPRAS ---
    # ==========================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas Preventivas de Inventario y Compras")
        st.caption("Monitoreo automático de stock crítico por debajo de 7 días de reserva")
        
        pdf_compras = generar_pdf_lista_compras()
        with open(pdf_compras, "rb") as f:
            st.download_button("📄 Imprimir Lista de Compras (PDF)", data=f, file_name=pdf_compras, mime="application/pdf", use_container_width=True)
            
        st.divider()
        pacientes_activos = [p for p in obtener_pacientes() if p[5] == "A"]
        
        alertas = []
        for p in pacientes_activos:
            pid, pnom = p[0], p[1]
            meds, _, _ = obtener_medicamentos_paciente(pid)
            for m in meds:
                d_diaria = float(m.get("dosis_manana", 0)) + float(m.get("dosis_tarde", 0)) + float(m.get("dosis_noche", 0))
                ex = int(m.get("existencia", 0))
                if d_diaria > 0:
                    dias = ex / d_diaria
                    if dias <= 7:
                        alertas.append({"Residente": pnom, "Folio": pid, "Medicamento": m.get("nombre"), "Dosis Diaria": d_diaria, "Stock": ex, "Días Restantes": f"{dias:.1f} días"})
                        
        if alertas:
            st.warning(f"⚠️ Se detectaron **{len(alertas)}** medicamentos con inventario en nivel crítico (menos de 7 días).")
            st.dataframe(alertas, use_container_width=True)
        else:
            st.success("✅ Todos los residentes cuentan con inventario suficiente para más de 7 días.")

    # ==========================================
    # --- MÓDULO 10: REPOSITORIO DE DOCUMENTOS ---
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos y Archivero Digital")
        st.caption("Almacenamiento exclusivo de formatos, reglamentos y plantillas clínicas")
        
        if not es_admin:
            st.warning("🔒 El acceso al repositorio digital es exclusivo para el **Administrador**.")
        else:
            tab_rep1, tab_rep2 = st.tabs(["📂 Consultar Documentos", "📤 Subir Nuevo Documento"])
            
            with tab_rep1:
                docs = listar_documentos_repositorio()
                if not docs:
                    st.info("El repositorio digital no contiene archivos aún.")
                else:
                    for d in docs:
                        did, dcarp, dnom, dtipo, ddesc, dtam, dfsub, dsubpor = d
                        col_doc1, col_doc2, col_doc3 = st.columns([3, 1, 1])
                        with col_doc1:
                            st.write(f"📄 **{dnom}** (`{dcarp}`) | Subido por: {dsubpor} el {dfsub}")
                            if ddesc: st.caption(ddesc)
                        with col_doc2:
                            d_obj = obtener_documento_repositorio(did)
                            if d_obj and d_obj[4]:
                                st.download_button("📥 Descargar", data=d_obj[4], file_name=dnom, mime=dtipo, key=f"dl_doc_{did}")
                        with col_doc3:
                            if st.button("🗑️ Eliminar", key=f"del_doc_{did}"):
                                eliminar_documento_repositorio(did)
                                st.toast("Archivo eliminado.")
                                st.rerun()
                                
            with tab_rep2:
                with st.form("form_upload_doc"):
                    f_carp = st.text_input("Carpeta / Categoría (Ej: Formatos, Reglamentos, Actas)")
                    f_desc = st.text_area("Descripción corta del archivo")
                    up_file = st.file_uploader("Selecciona el archivo a subir", type=["pdf", "docx", "xlsx", "png", "jpg"])
                    
                    btn_up_doc = st.form_submit_button("📤 Subir Archivo al Repositorio", use_container_width=True)
                    if btn_up_doc:
                        if not up_file or not f_carp.strip():
                            st.error("⚠️ La categoría y el archivo son obligatorios.")
                        else:
                            f_bytes = up_file.read()
                            guardar_documento_repositorio(f_carp.strip(), up_file.name, up_file.type, f_desc, f_bytes, st.session_state["username"])
                            st.toast("🎉 ¡Documento subido correctamente!")
                            st.success("✅ Archivo guardado en el repositorio digital.")
                            st.rerun()

    # ==========================================
    # --- MÓDULO 11: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Copias de Seguridad y Restauración de Base de Datos")
        
        tab_b1, tab_b2 = st.tabs(["⬇️ Descargar Copia de Seguridad", "⬆️ Restaurar Base de Datos"])
        
        with tab_b1:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="📦 Descargar Respaldo `.db` Completo",
                        data=f,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
            else:
                st.error("No se encontró el archivo de base de datos.")
                
        with tab_b2:
            if not es_admin:
                st.warning("🔒 La restauración de base de datos es exclusiva para el **Administrador**.")
            else:
                st.warning("⚠️ **ATENCIÓN**: Restaurar una base de datos sobrescribirá la información actual.")
                up_db = st.file_uploader("Selecciona el archivo `.db` a restaurar", type=["db", "sqlite3"])
                if st.button("🚨 Sobrescribir y Restaurar Base de Datos") and up_db:
                    with open(DB_FILE, "wb") as f:
                        f.write(up_db.read())
                    st.success("✅ Base de datos restaurada exitosamente.")
                    st.toast("🎉 Restauración completa. Reiniciando...")
                    st.rerun()

    # ==========================================
    # --- MÓDULO 12: CONFIGURACIÓN / SEGURIDAD ---
    # ==========================================
    elif menu == "⚙️ Configuración / Seguridad":
        st.title("⚙️ Configuración del Sistema & Seguridad")
        
        tab_sec1, tab_sec2, tab_sec3 = st.tabs(["🔑 Cambiar Contraseña", "👥 Usuarios y Roles del Sistema", "⚙️ Administrar Requisitos por Etapa"])
        
        with tab_sec1:
            st.subheader("Cambiar Contraseña del Usuario Actual")
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
            st.subheader("👥 Gestión de Usuarios y Roles del Sistema")
            st.caption("Alta de personal de staff, asignación de roles (Administrador, Consejero, Médico/Farmacia) y bloqueo por vacaciones")
            
            if not es_admin:
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
                        col_us1, col_us2, col_us3 = st.columns([3, 1, 1])
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
                        st.toast("🎉 ¡Requisito agregado exitosamente!")
                        st.success("✅ Requisito agregado exitosamente.")
                        st.rerun()

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

# --- FUNCIONES DE BASE DE DATOS & INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios Administrativos (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    
    # 2. Pacientes / Residentes
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
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
    
    # 3. Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 4. Ficha de Ingreso (NOM-028)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 5. Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            etapa TEXT,
            tema TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 6. Grupos Terapéuticos
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

    # 7. TABLAS RELACIONALES DE MEDICAMENTOS (CATÁLOGO Y ASIGNACIONES)
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS asignaciones_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY (medicamento_id) REFERENCES catalogo_medicamentos(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER DEFAULT 0,
            fecha TEXT NOT NULL,
            turno TEXT DEFAULT '',
            cantidad_entregada REAL DEFAULT 0,
            usuario TEXT NOT NULL,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')

    # Tabla legada 'medicamentos' para migración
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

    # 8. Repositorio de Documentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            padre_id INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT,
            usuario TEXT,
            contenido BLOB,
            FOREIGN KEY (carpeta_id) REFERENCES repositorio_carpetas(id)
        )
    ''')

    # 9. Historial y Requisitos
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_origen TEXT,
            etapa_destino TEXT,
            fecha_cambio TEXT,
            usuario TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')
    
    # Crear admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
        
    # Inicializar Carpetas por Defecto en Repositorio
    c.execute('SELECT COUNT(*) FROM repositorio_carpetas WHERE padre_id = 0')
    if c.fetchone()[0] == 0:
        carpetas_defecto = ["Formatos", "Documentos", "Eventos", "Comprobantes", "Terapéutico"]
        for nom_c in carpetas_defecto:
            c.execute('INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, 0)', (nom_c,))

    # Sincronización entre pacientes y pacientes_registro
    try:
        c.execute('INSERT OR IGNORE INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual) SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, COALESCE(estatus, "A"), COALESCE(tipo_usuario, "Paciente"), COALESCE(etapa_actual, "ACOGIDA") FROM pacientes_registro')
        c.execute('INSERT OR IGNORE INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual) SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, COALESCE(estatus, "A"), COALESCE(tipo_usuario, "Paciente"), COALESCE(etapa_actual, "ACOGIDA") FROM pacientes')
    except Exception:
        pass

    # Sincronización de migraciones de medicamentos desde meds_json si existen
    try:
        c.execute('SELECT paciente_id, meds_json, observaciones FROM medicamentos WHERE meds_json IS NOT NULL AND meds_json != ""')
        meds_legacy = c.fetchall()
        for p_id_leg, m_json, obs_leg in meds_legacy:
            try:
                m_items = json.loads(m_json)
                if isinstance(m_items, list):
                    for item in m_items:
                        m_nom = item.get('nombre', '').strip()
                        if m_nom:
                            c.execute('SELECT id FROM catalogo_medicamentos WHERE LOWER(nombre_medicamento) = LOWER(?)', (m_nom,))
                            cat_row = c.fetchone()
                            if cat_row:
                                med_id = cat_row[0]
                            else:
                                c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)', (m_nom, m_nom, 'Unidad'))
                                med_id = c.lastrowid
                            
                            c.execute('SELECT id FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?', (p_id_leg, med_id))
                            asig_row = c.fetchone()
                            if not asig_row:
                                dm = float(item.get('dosis_manana', 0) or 0)
                                dt = float(item.get('dosis_tarde', 0) or 0)
                                dn = float(item.get('dosis_noche', 0) or 0)
                                ex = float(item.get('existencia', 0) or 0)
                                ind = item.get('indicaciones', '')
                                c.execute('''
                                    INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', (p_id_leg, med_id, dm, dt, dn, ex, ind or obs_leg))
            except Exception:
                pass
    except Exception:
        pass

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def limpiar_texto(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    for k, v in replacements.items():
        texto = str(texto).replace(k, v)
    return texto

# --- FUNCIONES DE PACIENTES / RESIDENTES ---
def obtener_siguiente_id():
    init_db()
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
            except Exception:
                pass
    return f"PAC-{(max_num + 1):03d}"

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(nombre_completo) = LOWER(?)', (nombre.strip(),))
    rows = c.fetchall()
    conn.close()
    for r in rows:
        if r[0] != paciente_id_actual:
            return r
    return None

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', etapa_actual='ACOGIDA', fecha_inicio_etapa=None, usuario_reg='system'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ini_e = str(fecha_inicio_etapa) if fecha_inicio_etapa else str(fecha_ingreso)
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, f_ini_e, fecha_actual, paciente_id))
        c.execute('''
            UPDATE pacientes_registro
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, f_ini_e, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, f_ini_e, fecha_actual, fecha_actual, usuario_reg))
        c.execute('''
            INSERT INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, tipo_usuario, etapa_actual, f_ini_e, fecha_actual, fecha_actual, usuario_reg))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_bd(estatus_filtro='A'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if estatus_filtro == 'A':
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes WHERE estatus = "A" ORDER BY nombre_completo ASC')
    elif estatus_filtro == 'B':
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes WHERE estatus = "B" ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREVISTAS DE CONSEJERÍA ---
def guardar_entrevista(paciente_id, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE entrevistas 
            SET datos_json = ?, fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (datos_json, fecha_actual, usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

# --- FUNCIONES DE CATÁLOGO Y ASIGNACIÓN DE MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion)
        VALUES (?, ?, ?)
    ''', (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE catalogo_medicamentos
        SET compuesto = ?, nombre_medicamento = ?, presentacion = ?
        WHERE id = ?
    ''', (compuesto.strip(), nombre.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?', (med_id,))
    cnt = c.fetchone()[0]
    if cnt > 0:
        conn.close()
        return False, f"No se puede eliminar: Este medicamento está asignado actualmente a {cnt} paciente(s)."
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()
    return True, "Medicamento eliminado del catálogo con éxito."

def obtener_asignaciones_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.id, a.medicamento_id, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE a.paciente_id = ?
        ORDER BY m.nombre_medicamento ASC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_asignacion_medicamento(paciente_id, med_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?', (paciente_id, med_id))
    row = c.fetchone()
    if row:
        c.execute('''
            UPDATE asignaciones_medicamentos
            SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
            WHERE id = ?
        ''', (manana, tarde, noche, existencia, obs, row[0]))
    else:
        c.execute('''
            INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, med_id, manana, tarde, noche, existencia, obs))
    conn.commit()
    conn.close()

def actualizar_asignacion_medicamento(asig_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE asignaciones_medicamentos
        SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
        WHERE id = ?
    ''', (manana, tarde, noche, existencia, obs, asig_id))
    conn.commit()
    conn.close()

def eliminar_asignacion_medicamento(asig_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM asignaciones_medicamentos WHERE id = ?', (asig_id,))
    conn.commit()
    conn.close()

def registrar_entrega_medicamento(paciente_id, med_id, fecha, turno, cantidad, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario, entregado_por)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, fecha, turno, cantidad, usuario, usuario))
    
    c.execute('''
        UPDATE asignaciones_medicamentos
        SET existencia = MAX(0, existencia - ?)
        WHERE paciente_id = ? AND medicamento_id = ?
    ''', (cantidad, paciente_id, med_id))
    
    conn.commit()
    conn.close()

def obtener_todas_asignaciones():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.paciente_id, p.nombre_completo, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        JOIN pacientes p ON a.paciente_id = p.paciente_id
        WHERE p.estatus = "A"
        ORDER BY p.nombre_completo ASC, m.nombre_medicamento ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE GRUPOS Y ETAPAS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos, usuario_reg):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_al_momento, str(fecha_grupo), facilitador, datos_json, fecha_actual, usuario_reg))
    c.execute('''
        INSERT INTO grupos_terapeuticos (paciente_id, tipo_grupo, etapa, fecha, facilitador, datos_json, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_al_momento, str(fecha_grupo), facilitador, datos_json, usuario_reg))
    conn.commit()
    conn.close()

def contar_grupos_etapa(paciente_id, etapa, tipo_grupo):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def listar_grupos_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def cambiar_etapa_paciente(paciente_id, etapa_origen, etapa_destino, usuario_autoriza):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = str(date.today())
    
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?', (etapa_destino, f_hoy, fecha_actual, paciente_id))
    c.execute('UPDATE pacientes_registro SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?', (etapa_destino, f_hoy, fecha_actual, paciente_id))
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario) VALUES (?, ?, ?, ?, ?)', (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario_autoriza))
    
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_mayor_id, paciente_id))
    c.execute('UPDATE pacientes_registro SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_mayor_id, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_hoy = str(date.today())
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (f_hoy, paciente_id))
    c.execute('UPDATE pacientes_registro SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (f_hoy, paciente_id))
    conn.commit()
    conn.close()

def obtener_requisitos_etapa(etapa):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SAWABONA SHIKOBA - COMUNIDAD TERAPEUTICA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control Clinico y Consejeria", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"NUMERO DE PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    
    col_widths = [28, 20, 25, 30, 28, 22, 37]
    headers = ["Sustancia", "Consumo", "Forma", "Frecuencia", "Cantidad", "Edad Inic.", "Lugar"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    tabla_consumo = datos.get("tabla_consumo", {})
    for sust, vals in tabla_consumo.items():
        pdf.cell(col_widths[0], 6, limpiar_texto(sust), border=1)
        pdf.cell(col_widths[1], 6, limpiar_texto(str(vals.get("consumo", ""))), border=1, align="C")
        pdf.cell(col_widths[2], 6, limpiar_texto(str(vals.get("forma", ""))), border=1)
        pdf.cell(col_widths[3], 6, limpiar_texto(str(vals.get("frecuencia", ""))), border=1)
        pdf.cell(col_widths[4], 6, limpiar_texto(str(vals.get("cantidad", ""))), border=1)
        pdf.cell(col_widths[5], 6, limpiar_texto(str(vals.get("edad_inicio", ""))), border=1, align="C")
        pdf.cell(col_widths[6], 6, limpiar_texto(str(vals.get("lugar", ""))), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Normally consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir: {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "SITUACION SOCIAL-FAMILIAR", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Integrantes de la familia: {limpiar_texto(datos.get('familia_integrantes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION CLINICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_general_meds():
    pdf = PDFReport('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(pdf.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 6, "LISTADO GENERAL DE INDICACIONES MEDICAS Y DOSIFICACION", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    asignaciones = obtener_todas_asignaciones()
    
    if not asignaciones:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay medicamentos asignados a pacientes en este momento.", align="C")
    else:
        col_w = [65, 55, 30, 20, 20, 20, 25, 42]
        headers = ["Paciente", "Medicamento", "Presentacion", "Mañana", "Tarde", "Noche", "Stock", "Notas"]
        
        pdf.set_font("Helvetica", "B", 8)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 6, h, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 8)
        for row in asignaciones:
            p_id, p_nom, comp, m_nom, pres, d_m, d_t, d_n, ext, obs = row
            med_txt = f"{comp} ({m_nom})" if comp != m_nom else m_nom
            
            pdf.cell(col_w[0], 5, limpiar_texto(f"{p_nom} ({p_id})"), border=1)
            pdf.cell(col_w[1], 5, limpiar_texto(med_txt), border=1)
            pdf.cell(col_w[2], 5, limpiar_texto(pres), border=1, align="C")
            pdf.cell(col_w[3], 5, str(int(d_m) if d_m == int(d_m) else d_m), border=1, align="C")
            pdf.cell(col_w[4], 5, str(int(d_t) if d_t == int(d_t) else d_t), border=1, align="C")
            pdf.cell(col_w[5], 5, str(int(d_n) if d_n == int(d_n) else d_n), border=1, align="C")
            pdf.cell(col_w[6], 5, str(int(ext) if ext == int(ext) else ext), border=1, align="C")
            pdf.cell(col_w[7], 5, limpiar_texto(obs or ""), border=1, new_x="LMARGIN", new_y="NEXT")
            
    fn = f"Listado_General_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(fn)
    return fn

# --- INICIALIZAR DB Y ESTADO ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

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
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usuario_valido[0]
                    st.session_state["nombre_completo"] = usuario_valido[1]
                    st.toast("🎉 ¡Acceso concedido!")
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL CON NAVEGACIÓN COMPLETA (12 MÓDULOS) ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario Staff**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación del Sistema",
        [
            "🏠 Inicio / Tablero General",
            "👤 Registro y Edición de Pacientes",
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
    
    if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # --- MÓDULO 1: INICIO / TABLERO GENERAL ---
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General - Resumen Ejecutivo")
        st.caption("Visión general de residentes activos, distribución por etapas de tratamiento y alertas")
        
        activos = listar_pacientes_bd('A')
        bloqueados = listar_pacientes_bd('B')
        
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Residentes Activos", len(activos))
        c_m2.metric("Expedientes Inactivos / Bajas", len(bloqueados))
        c_m3.metric("Total Expedientes Registrados", len(activos) + len(bloqueados))
        
        st.divider()
        st.subheader("🎯 Distribución de Residentes por Etapa de Tratamiento")
        
        etapas_conteo = {"ACOGIDA": 0, "IDENTIFICACIÓN": 0, "ELABORACIÓN": 0, "CONSOLIDACIÓN": 0, "SERVICIO SOCIAL": 0}
        for p in activos:
            et = p[7] if len(p) > 7 and p[7] in etapas_conteo else "ACOGIDA"
            etapas_conteo[et] += 1
            
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        ec1.metric("Acogida", etapas_conteo["ACOGIDA"])
        ec2.metric("Identificación", etapas_conteo["IDENTIFICACIÓN"])
        ec3.metric("Elaboración", etapas_conteo["ELABORACIÓN"])
        ec4.metric("Consolidación", etapas_conteo["CONSOLIDACIÓN"])
        ec5.metric("Servicio Social", etapas_conteo["SERVICIO SOCIAL"])

    # ==========================================
    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    # ==========================================
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        st.caption("Módulo de alta, edición de datos basales, estatus y asignación de etapa inicial")
        
        modo_u = st.radio("Acción a Realizar", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        todos_p = listar_pacientes_bd('TODOS')
        edit_pid = None
        dados_p = None
        
        if modo_u == "✏️ Modificar / Editar Usuario Existente":
            if not todos_p:
                st.warning("No hay usuarios registrados aún en el sistema.")
            else:
                dict_p_edit = {f"{p[1]} ({p[0]})": p[0] for p in todos_p}
                sel_p_edit = st.selectbox("🔑 Selecciona el Residente a Editar", list(dict_p_edit.keys()))
                edit_pid = dict_p_edit[sel_p_edit]
                dados_p = obtener_paciente(edit_pid)
                
        if dados_p:
            v_id = dados_p[0]
            v_nom = dados_p[1]
            try: v_f_ing = datetime.strptime(dados_p[2], "%Y-%m-%d").date() if dados_p[2] else date.today()
            except: v_f_ing = date.today()
            try: v_f_nac = datetime.strptime(dados_p[3], "%Y-%m-%d").date() if dados_p[3] else date(1990, 1, 1)
            except: v_f_nac = date(1990, 1, 1)
            v_sexo = dados_p[4] if dados_p[4] in ["Masculino", "Femenino"] else "Masculino"
            v_est = dados_p[5] if dados_p[5] in ["A", "B"] else "A"
            v_tipo = dados_p[6] if dados_p[6] in ["Paciente", "Servidor"] else "Paciente"
            v_etapa = dados_p[7] if dados_p[7] in ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"] else "ACOGIDA"
        else:
            v_id = obtener_siguiente_id()
            v_nom = ""
            v_f_ing = date.today()
            v_f_nac = date(1990, 1, 1)
            v_sexo = "Masculino"
            v_est = "A"
            v_tipo = "Paciente"
            v_etapa = "ACOGIDA"

        form_key = f"form_usr_{edit_pid if edit_pid else 'nuevo'}"
        
        with st.form(form_key):
            st.subheader("Datos Basales del Usuario")
            c1, c2 = st.columns(2)
            with c1:
                reg_pid = st.text_input("🔑 Folio / ID de Usuario *", value=v_id, disabled=(modo_u == "✏️ Modificar / Editar Usuario Existente"))
                reg_nom = st.text_input("👤 Nombre Completo *", value=v_nom)
                reg_tipo = st.selectbox("🏷️ Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if v_tipo == "Paciente" else 1)
                reg_sexo = st.selectbox("🚻 Sexo", ["Masculino", "Femenino"], index=0 if v_sexo == "Masculino" else 1)
            with c2:
                reg_f_ing = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=v_f_ing, min_value=date(1920, 1, 1), max_value=date.today())
                reg_f_nac = st.date_input("🎂 Fecha de Nacimiento", value=v_f_nac, min_value=date(1920, 1, 1), max_value=date.today())
                reg_est = st.selectbox("📌 Estatus", ["A - Activo", "B - Bloqueado"], index=0 if v_est == "A" else 1)
                reg_etapa = st.selectbox("🎯 Etapa Inicial / Actual", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"], index=["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"].index(v_etapa))
                
            btn_guardar_u = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True)
            
            if btn_guardar_u:
                if not reg_nom.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                elif modo_u == "🆕 Registrar Nuevo Usuario":
                    dup = verificar_duplicado_nombre(reg_nom)
                    if dup:
                        dup_id, dup_nom, dup_est = dup
                        st.error(f"❌ Imposible registrar: Ya existe el nombre '**{dup_nom}**' bajo el Folio **{dup_id}**.")
                    else:
                        code_est = "A" if reg_est.startswith("A") else "B"
                        guardar_usuario_paciente(reg_pid, reg_nom, reg_f_ing, reg_f_nac, reg_sexo, code_est, reg_tipo, reg_etapa, reg_f_ing, st.session_state["username"])
                        st.toast(f"🎉 ¡Usuario {reg_nom} registrado!")
                        st.success(f"✅ ¡Usuario **{reg_nom}** ({reg_pid}) registrado exitosamente!")
                        st.balloons()
                        st.rerun()
                else:
                    code_est = "A" if reg_est.startswith("A") else "B"
                    guardar_usuario_paciente(edit_pid, reg_nom, reg_f_ing, reg_f_nac, reg_sexo, code_est, reg_tipo, reg_etapa, reg_f_ing, st.session_state["username"])
                    st.toast(f"🎉 ¡Usuario {reg_nom} actualizado!")
                    st.success(f"✅ ¡Usuario **{reg_nom}** ({edit_pid}) actualizado exitosamente!")
                    st.balloons()
                    st.rerun()

        st.divider()
        st.subheader("📋 Padrón de Pacientes Registrados (En vivo)")
        p_padrón = listar_pacientes_bd('A')
        if p_padrón:
            df_pad = [{"Folio": p[0], "Nombre Completo": p[1], "Ingreso": p[2], "Nacimiento": p[3], "Sexo": p[4], "Tipo": p[6], "Etapa": p[7]} for p in p_padrón]
            st.dataframe(df_pad, use_container_width=True)
        else:
            st.info("No hay pacientes activos en el padrón.")

    # ==========================================
    # --- MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN ---
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        st.caption("Captura de admisión oficial y contrato de tratamiento")
        p_act = listar_pacientes_bd('A')
        if not p_act:
            st.warning("No hay pacientes activos.")
        else:
            dict_f = {f"{p[1]} ({p[0]})": p[0] for p in p_act}
            sel_f = st.selectbox("🔑 Selecciona el Residente", list(dict_f.keys()))
            st.info(f"Ficha de Ingreso lista para captura de **{sel_f}**.")

    # ==========================================
    # --- MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias y perfil socio-demográfico")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("Debe registrar un usuario activo primero.")
        else:
            dict_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_ent = st.selectbox("🔑 Selecciona el Paciente a Entrevistar", list(dict_ent.keys()))
            paciente_id_input = dict_ent[sel_ent]
            
            datos_existentes, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if not datos_existentes:
                datos_existentes = {}
                st.info(f"🆕 Iniciando nueva entrevista para **{sel_ent}**.")
            else:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}.")

            with st.form("formulario_entrevista"):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "1. Datos Generales",
                    "2. Consumo de Sustancias",
                    "3. Disposición al Cambio",
                    "4. Entorno y Riesgos",
                    "5. Observaciones y Firma"
                ])
                
                with tab1:
                    st.subheader("Datos Socio-Demográficos Basales")
                    c1, c2 = st.columns(2)
                    with c1:
                        dependientes_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], index=1 if datos_existentes.get("dependientes_flag") == "SÍ" else 0)
                        dependientes_quienes = st.text_input("¿Quiénes o cuántos?", value=datos_existentes.get("dependientes_quienes", ""))
                    with c2:
                        pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
                        pareja_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo", ""))

                with tab2:
                    st.subheader("Tabla de Consumo de Sustancias")
                    sustancias_lista = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO"]
                    tabla_consumo_guardada = datos_existentes.get("tabla_consumo", {})
                    tabla_consumo_input = {}
                    
                    for sust in sustancias_lista:
                        st.markdown(f"**{sust}**")
                        s_data = tabla_consumo_guardada.get(sust, {})
                        col_a, col_b, col_c, col_d, col_e, col_f = st.columns([1, 1.5, 1.5, 1.5, 1, 1.5])
                        with col_a:
                            c_val = st.checkbox("Consume", value=s_data.get("consumo") == "SÍ", key=f"c_{sust}")
                        with col_b:
                            forma_val = st.text_input("Forma", value=s_data.get("forma", ""), key=f"forma_{sust}")
                        with col_c:
                            frec_val = st.text_input("Frecuencia", value=s_data.get("frecuencia", ""), key=f"frec_{sust}")
                        with col_d:
                            cant_val = st.text_input("Cantidad", value=s_data.get("cantidad", ""), key=f"cant_{sust}")
                        with col_e:
                            edad_val = st.text_input("Edad Inicio", value=s_data.get("edad_inicio", ""), key=f"edad_{sust}")
                        with col_f:
                            lugar_val = st.text_input("Lugar", value=s_data.get("lugar", ""), key=f"lugar_{sust}")
                            
                        tabla_consumo_input[sust] = {
                            "consumo": "SÍ" if c_val else "NO",
                            "forma": forma_val,
                            "frecuencia": frec_val,
                            "cantidad": cant_val,
                            "edad_inicio": edad_val,
                            "lugar": lugar_val
                        }
                        st.divider()

                    st.subheader("Sustancia de Impacto y Patrón")
                    col_imp1, col_imp2, col_imp3 = st.columns(3)
                    with col_imp1:
                        sustancia_impacto = st.text_input("Sustancia de Impacto Principal", value=datos_existentes.get("sustancia_impacto", ""))
                    with col_imp2:
                        tiempo_excesivo = st.text_input("¿Desde hace cuánto consume de forma excesiva?", value=datos_existentes.get("tiempo_excesivo", ""))
                    with col_imp3:
                        modo_consumo = st.selectbox("Normally consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"], index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo en esa ocasión?", value=datos_existentes.get("abst_motivo", ""))
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Actualmente, ¿qué tan importante es dejar de consumir?", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("¿Quiénes integran su familia?", value=datos_existentes.get("familia_integrantes", ""))

                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Expediente de Paciente", use_container_width=True)
                
                if guardar_btn:
                    datos_completos = {
                        "dependientes_flag": dependientes_flag,
                        "dependientes_quienes": dependientes_quienes,
                        "pareja_flag": pareja_flag,
                        "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input,
                        "sustancia_impacto": sustancia_impacto,
                        "tiempo_excesivo": tiempo_excesivo,
                        "modo_consumo": modo_consumo,
                        "abst_mayor_tiempo": abst_mayor_tiempo,
                        "abst_fecha": abst_fecha,
                        "abst_motivo": abst_motivo,
                        "importancia_cambio": importancia_cambio,
                        "familia_integrantes": familia_integrantes,
                        "observaciones": observaciones,
                        "evaluador_nombre": evaluador_nombre,
                        "evaluador_cargo": evaluador_cargo
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.toast("🎉 ¡Expediente guardado exitosamente!")
                    st.success(f"✅ ¡Expediente **{paciente_id_input}** guardado correctamente!")
                    st.balloons()
                    st.rerun()

    # ==========================================
    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales")
        st.caption("Registro de sesiones individuales de consejería por etapa")
        p_act = listar_pacientes_bd('A')
        if not p_act:
            st.warning("No hay pacientes activos.")
        else:
            dict_c = {f"{p[1]} ({p[0]})": p[0] for p in p_act}
            sel_c = st.selectbox("🔑 Selecciona el Residente", list(dict_c.keys()))
            st.info(f"Sesiones de consejería para **{sel_c}**.")

    # ==========================================
    # --- MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO ---
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Seguimiento de Proceso")
        st.caption("Control de avance por las 5 etapas del programa de la comunidad Sawabona Shikoba")
        
        pacientes_activos = [p for p in listar_pacientes_bd('A') if p[6] == 'Paciente']
        
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados en proceso.")
        else:
            dict_pac = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_activos}
            sel_pac_et = st.selectbox("🔑 Selecciona el Paciente a Evaluar", list(dict_pac.keys()))
            p_id_et = dict_pac[sel_pac_et]
            
            p_data = obtener_paciente(p_id_et)
            p_nom = p_data[1]
            p_fing = p_data[2]
            p_etapa = p_data[7]
            p_f_ini_etapa = p_data[8]
            h_mayor_id = p_data[9]
            f_suelta = p_data[10]
            
            try:
                dt_ing = datetime.strptime(p_fing, "%Y-%m-%d").date()
                dias_totales = (date.today() - dt_ing).days
            except:
                dias_totales = 0
                
            try:
                dt_etapa = datetime.strptime(p_f_ini_etapa, "%Y-%m-%d").date()
                dias_etapa = (date.today() - dt_etapa).days
            except:
                dias_etapa = 0
                
            duracion_etapas = {"ACOGIDA": 30, "IDENTIFICACIÓN": 60, "ELABORACIÓN": 60, "CONSOLIDACIÓN": 30, "SERVICIO SOCIAL": 30}
            dias_meta = duracion_etapas.get(p_etapa, 30)
            dias_restantes = dias_meta - dias_etapa
            
            st.subheader(f"📊 Ficha de Avance: **{p_nom}** ({p_id_et})")
            c_e1, c_e2, c_e3, c_e4 = st.columns(4)
            c_e1.metric("Etapa Actual", p_etapa)
            c_e2.metric("Días en Etapa Actual", f"{dias_etapa} / {dias_meta} días")
            c_e3.metric("Días Totales en Clínica", f"{dias_totales} días")
            c_e4.metric("Días Faltantes para Meta", f"{max(0, dias_restantes)} días")
            
            prog = min(1.0, max(0.0, dias_etapa / dias_meta))
            st.progress(prog, text=f"Progreso en {p_etapa}: {int(prog*100)}%")
            
            if dias_etapa > 90:
                st.warning(f"⚠️ **ALERTA DE REZAGO CLÍNICO**: El paciente lleva {dias_etapa} días en la etapa {p_etapa} (>90 días).")

    # ==========================================
    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro y Asistencia a Grupos Terapéuticos")
        st.caption("Bitácoras de Terapia de Grupo, Aquí y Ahora, Prevención de Recaídas y Feedbacks")
        p_act = listar_pacientes_bd('A')
        if not p_act:
            st.warning("No hay pacientes activos.")
        else:
            dict_g = {f"{p[1]} ({p[0]})": p[0] for p in p_act}
            sel_g = st.selectbox("🔑 Selecciona el Residente", list(dict_g.keys()))
            st.info(f"Registro de grupo para **{sel_g}**.")

    # ==========================================
    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS (CATÁLOGO RESTABLECIDO Y ASIGNACIÓN CON RETIRO) ---
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control y Registro de Medicamentos")
        st.caption("Catálogo general, prescripción de medicamentos por catálogo, existencia nueva total y surtido diario")
        
        tab_med1, tab_med2, tab_med3, tab_med4 = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario",
            "🚚 Surtido Diario por Turno",
            "🚨 Alertas de Reabastecimiento"
        ])
        
        # --- TAB 1: CATÁLOGO DE MEDICAMENTOS ---
        with tab_med1:
            st.subheader("💊 Gestión del Catálogo General de Medicamentos")
            subtab_c1, subtab_c2, subtab_c3 = st.tabs(["➕ Agregar Medicamento al Catálogo", "✏️ Modificar Medicamento", "🗑️ Eliminar del Catálogo"])
            
            with subtab_c1:
                with st.form("form_add_cat_med"):
                    c_c1, c_c2, c_c3 = st.columns(3)
                    with c_c1:
                        cat_compuesto = st.text_input("Compuesto / Sustancia Activa *", placeholder="Ej. Paracetamol, Clonazepam").strip()
                    with c_c2:
                        cat_nombre = st.text_input("Nombre Comercial / Medicamento *", placeholder="Ej. Tylenol, Rivotril").strip()
                    with c_c3:
                        cat_pres = st.text_input("Presentación *", placeholder="Ej. Tabletas 500mg, Gotas").strip()
                    
                    btn_add_cat = st.form_submit_button("➕ Guardar Medicamento en Catálogo", use_container_width=True)
                    if btn_add_cat:
                        if not cat_compuesto or not cat_nombre or not cat_pres:
                            st.error("⚠️ Todos los campos (Compuesto, Nombre Comercial y Presentación) son obligatorios.")
                        else:
                            guardar_medicamento_catalogo(cat_compuesto, cat_nombre, cat_pres)
                            st.toast("🎉 ¡Medicamento agregado al catálogo!")
                            st.success(f"✅ ¡**{cat_nombre}** ({cat_compuesto}) guardado exitosamente en el catálogo!")
                            st.balloons()
                            st.rerun()

            with subtab_c2:
                cat_lista = obtener_catalogo_medicamentos()
                if not cat_lista:
                    st.info("No hay medicamentos registrados en el catálogo aún.")
                else:
                    dict_cat_edit = {f"{m[2]} ({m[1]}) - {m[3]}": m for m in cat_lista}
                    sel_cat_mod = st.selectbox("🔑 Selecciona el Medicamento a Modificar", list(dict_cat_edit.keys()))
                    m_data = dict_cat_edit[sel_cat_mod]
                    
                    with st.form("form_edit_cat_med"):
                        c_e1, c_e2, c_e3 = st.columns(3)
                        with c_e1:
                            mod_compuesto = st.text_input("Compuesto / Sustancia Activa *", value=m_data[1])
                        with c_e2:
                            mod_nombre = st.text_input("Nombre Comercial *", value=m_data[2])
                        with c_e3:
                            mod_pres = st.text_input("Presentación *", value=m_data[3])
                            
                        btn_mod_cat = st.form_submit_button("💾 Guardar Cambios en Catálogo", use_container_width=True)
                        if btn_mod_cat:
                            actualizar_medicamento_catalogo(m_data[0], mod_compuesto, mod_nombre, mod_pres)
                            st.toast("🎉 ¡Catálogo actualizado!")
                            st.success(f"✅ ¡Medicamento **{mod_nombre}** actualizado en el catálogo!")
                            st.rerun()

            with subtab_c3:
                cat_lista = obtener_catalogo_medicamentos()
                if not cat_lista:
                    st.info("No hay medicamentos en el catálogo.")
                else:
                    dict_cat_del = {f"{m[2]} ({m[1]}) - {m[3]}": m[0] for m in cat_lista}
                    sel_cat_del = st.selectbox("🔑 Selecciona el Medicamento a Eliminar del Catálogo", list(dict_cat_del.keys()))
                    m_del_id = dict_cat_del[sel_cat_del]
                    
                    if st.button("🗑️ Eliminar Medicamento del Catálogo", use_container_width=True):
                        ok_del, msg_del = eliminar_medicamento_catalogo(m_del_id)
                        if ok_del:
                            st.toast("🗑️ Medicamento eliminado.")
                            st.success(msg_del)
                            st.rerun()
                        else:
                            st.error(msg_del)

            st.divider()
            st.subheader("📋 Catálogo Actual de Medicamentos (En vivo)")
            cat_actual = obtener_catalogo_medicamentos()
            if cat_actual:
                df_cat = [{"ID": c[0], "Compuesto": c[1], "Nombre Comercial": c[2], "Presentación": c[3]} for c in cat_actual]
                st.dataframe(df_cat, use_container_width=True)
            else:
                st.info("El catálogo de medicamentos está vacío.")

        # --- TAB 2: ASIGNACIÓN E INVENTARIO ---
        with tab_med2:
            st.subheader("📋 Asignación de Medicamentos del Catálogo a Residentes")
            pacientes_activos = listar_pacientes_bd('A')
            
            if not pacientes_activos:
                st.warning("No hay usuarios activos registrados para asignar medicamentos.")
            else:
                dict_pac_asig = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
                sel_p_asig = st.selectbox("🔑 Selecciona el Residente", list(dict_pac_asig.keys()))
                pid_asig = dict_pac_asig[sel_p_asig]
                
                cat_disponible = obtener_catalogo_medicamentos()
                
                if not cat_disponible:
                    st.warning("⚠️ No hay medicamentos registrados en el catálogo. Registre medicamentos en la pestaña '💊 Catálogo de Medicamentos' para poder asignarlos.")
                else:
                    st.markdown("##### ➕ Asignar Medicamento Jalándolo del Catálogo")
                    dict_cat_opt = {f"{c[2]} ({c[1]}) - {c[3]}": c[0] for c in cat_disponible}
                    
                    with st.form("form_nueva_asig"):
                        sel_med_asig = st.selectbox("💊 Seleccionar Medicamento del Catálogo *", list(dict_cat_opt.keys()))
                        med_id_sel = dict_cat_opt[sel_med_asig]
                        
                        ca1, ca2, ca3, ca4 = st.columns(4)
                        with ca1:
                            dos_m = st.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=0.0)
                        with ca2:
                            dos_t = st.number_input("🌤️ Dosis Tarde", min_value=0.0, step=0.5, value=0.0)
                        with ca3:
                            dos_n = st.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=0.0)
                        with ca4:
                            ext_nueva = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL *", min_value=0.0, step=1.0, value=0.0)
                            
                        obs_asig = st.text_input("Indicaciones Específicas / Observaciones", placeholder="Ej. Tomar con alimentos")
                        btn_asig = st.form_submit_button("💾 Asignar / Actualizar Medicamento al Paciente", use_container_width=True)
                        
                        if btn_asig:
                            guardar_asignacion_medicamento(pid_asig, med_id_sel, dos_m, dos_t, dos_n, ext_nueva, obs_asig)
                            st.toast("🎉 ¡Medicamento asignado exitosamente!")
                            st.success("✅ ¡Medicamento asignado/actualizado correctamente!")
                            st.balloons()
                            st.rerun()

                st.divider()
                st.subheader(f"📋 Medicamentos Actualmente Asignados ({sel_p_asig})")
                asig_pac = obtener_asignaciones_paciente(pid_asig)
                
                if not asig_pac:
                    st.info("Este residente no tiene medicamentos asignados actualmente.")
                else:
                    st.caption("Modifique las dosis, ajuste la existencia total o presione 'RETIRAR MEDICAMENTO' para eliminar un registro específico:")
                    for a in asig_pac:
                        # a: (asig_id, med_id, compuesto, nombre_med, presentacion, dosis_m, dosis_t, dosis_n, existencia, obs)
                        asig_id, m_id, comp, mnom, pres, dm, dt, dn, ext, obs = a
                        with st.expander(f"💊 **{mnom}** ({comp}) - {pres} | Existencia Total: **{ext}**", expanded=True):
                            with st.form(key=f"form_mod_asig_{asig_id}"):
                                cm1, cm2, cm3, cm4 = st.columns(4)
                                with cm1:
                                    edit_dm = st.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=float(dm), key=f"edm_{asig_id}")
                                with cm2:
                                    edit_dt = st.number_input("🌤️ Dosis Tarde", min_value=0.0, step=0.5, value=float(dt), key=f"edt_{asig_id}")
                                with cm3:
                                    edit_dn = st.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=float(dn), key=f"edn_{asig_id}")
                                with cm4:
                                    edit_ext = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", min_value=0.0, step=1.0, value=float(ext), key=f"eext_{asig_id}")
                                    
                                edit_obs = st.text_input("Indicaciones / Notas", value=obs or "", key=f"eobs_{asig_id}")
                                
                                c_btn1, c_btn2 = st.columns([3, 1])
                                with c_btn1:
                                    btn_mod_a = st.form_submit_button("💾 Guardar Cambios de Dosis y Existencia", use_container_width=True)
                                with c_btn2:
                                    btn_retirar_a = st.form_submit_button("🗑️ RETIRAR MEDICAMENTO", use_container_width=True, type="secondary")
                                    
                                if btn_mod_a:
                                    actualizar_asignacion_medicamento(asig_id, edit_dm, edit_dt, edit_dn, edit_ext, edit_obs)
                                    st.toast("🎉 ¡Dosis y existencia actualizadas!")
                                    st.success(f"✅ ¡Actualizado **{mnom}** correctamente!")
                                    st.rerun()
                                    
                                if btn_retirar_a:
                                    eliminar_asignacion_medicamento(asig_id)
                                    st.toast("🗑️ Medicamento retirado del paciente.")
                                    st.success(f"✅ ¡Se retiró el medicamento **{mnom}** del expediente del residente!")
                                    st.rerun()

        # --- TAB 3: SURTIDO DIARIO POR TURNO ---
        with tab_med3:
            st.subheader("🚚 Surtido Diario de Medicamentos por Turno")
            turno_surt = st.radio("Turno a Surtir:", ["Mañana", "Medio Día / Tarde", "Noche"], horizontal=True)
            
            p_surt_lista = listar_pacientes_bd('A')
            if not p_surt_lista:
                st.warning("No hay usuarios activos.")
            else:
                hay_surtido = False
                for p_s in p_surt_lista:
                    p_id_s, p_nom_s = p_s[0], p_s[1]
                    asigs = obtener_asignaciones_paciente(p_id_s)
                    
                    asigs_turno = []
                    for a in asigs:
                        dm, dt, dn = a[5], a[6], a[7]
                        d_turno = dm if turno_surt == "Mañana" else (dt if "Tarde" in turno_surt else dn)
                        if d_turno > 0:
                            asigs_turno.append((a, d_turno))
                            
                    if asigs_turno:
                        hay_surtido = True
                        with st.expander(f"👤 **{p_nom_s}** ({p_id_s}) - {len(asigs_turno)} medicamento(s) por surtir en turno {turno_surt}", expanded=True):
                            for a, d_t in asigs_turno:
                                asig_id, m_id, comp, mnom, pres, dm, dt, dn, ext, obs = a
                                c_s1, c_s2, c_s3, c_s4 = st.columns([3, 2, 2, 2])
                                with c_s1:
                                    st.write(f"💊 **{mnom}** ({comp}) - {pres}")
                                    if obs: st.caption(f"Notas: {obs}")
                                with c_s2:
                                    st.write(f"Dosis Turno: **{d_t}**")
                                with c_s3:
                                    st.write(f"Existencia Total: **{ext}**")
                                with c_s4:
                                    if ext <= 0:
                                        st.markdown("<span style='color:red; font-weight:bold;'>🚨 SIN EXISTENCIA (0)</span>", unsafe_allow_html=True)
                                        st.button("Surtir", disabled=True, key=f"btn_dis_surt_{asig_id}_{turno_surt}")
                                    else:
                                        if st.button("📦 Surtir Dosis", key=f"btn_surt_{asig_id}_{turno_surt}"):
                                            registrar_entrega_medicamento(p_id_s, m_id, str(date.today()), turno_surt, d_t, st.session_state["username"])
                                            st.toast(f"✅ ¡Surtido realizado a {p_nom_s}!")
                                            st.success(f"✅ Surtido de {d_t} unidad(es) de {mnom} a {p_nom_s} realizado. Existencia restante: {ext - d_t}")
                                            st.rerun()
                                st.divider()
                                
                if not hay_surtido:
                    st.info(f"No hay dosis programadas para el turno **{turno_surt}** en ningún paciente activo.")

        # --- TAB 4: ALERTAS DE REABASTECIMIENTO ---
        with tab_med4:
            st.subheader("🚨 Alertas de Reabastecimiento e Insumos Faltantes (<= 5 Días)")
            p_act_alert = listar_pacientes_bd('A')
            
            alertas = []
            for p_a in p_act_alert:
                pid, pnom = p_a[0], p_a[1]
                asigs_p = obtener_asignaciones_paciente(pid)
                for a in asigs_p:
                    asig_id, m_id, comp, mnom, pres, dm, dt, dn, ext, obs = a
                    dosis_diaria = dm + dt + dn
                    if dosis_diaria > 0:
                        dias_cobertura = ext / dosis_diaria
                        if dias_cobertura <= 5:
                            alertas.append({
                                "paciente_id": pid,
                                "paciente_nombre": pnom,
                                "medicamento": mnom,
                                "compuesto": comp,
                                "presentacion": pres,
                                "dosis_diaria": dosis_diaria,
                                "existencia": ext,
                                "dias_cobertura": dias_cobertura
                            })
                            
            if not alertas:
                st.success("✅ **INVENTARIO ÓPTIMO**: Todos los residentes cuentan con existencia suficiente para más de 5 días de tratamiento.")
            else:
                st.warning(f"⚠️ Se han detectado **{len(alertas)} medicamento(s)** con existencia crítica (5 días o menos de cobertura):")
                for al in alertas:
                    if al["dias_cobertura"] <= 2:
                        st.error(f"🚨 **ALERTA CRÍTICA - {al['paciente_nombre']} ({al['paciente_id']})** | Medicamento: **{al['medicamento']}** ({al['compuesto']}) | Existencia: **{al['existencia']}** | Dosis diaria: **{al['dosis_diaria']}** (Cubre solo {al['dias_cobertura']:.1f} días)")
                    else:
                        st.warning(f"⚠️ **ALERTA PREVENTIVA - {al['paciente_nombre']} ({al['paciente_id']})** | Medicamento: **{al['medicamento']}** ({al['compuesto']}) | Existencia: **{al['existencia']}** | Dosis diaria: **{al['dosis_diaria']}** (Cubre {al['dias_cobertura']:.1f} días)")

            st.divider()
            pdf_gen_meds = generar_pdf_lista_general_meds()
            with open(pdf_gen_meds, "rb") as f:
                st.download_button(
                    label="🖨️ Descargar Listado General de Indicaciones Médicas (PDF)",
                    data=f,
                    file_name=pdf_gen_meds,
                    mime="application/pdf",
                    key="btn_pdf_gen_meds_tab4",
                    use_container_width=True
                )

    # ==========================================
    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Institucional de Documentos")
        st.caption("Gestión centralizada de plantillas, formatos, eventos, comprobantes y evaluaciones")
        
        # Obtener carpetas raíz
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id = 0 ORDER BY nombre ASC')
        carpetas_raiz = c.fetchall()
        conn.close()
        
        tab_r1, tab_r2 = st.tabs(["📂 Explorar y Gestionar Archivos", "⚙️ Administrar Carpetas"])
        
        with tab_r1:
            if not carpetas_raiz:
                st.info("No hay carpetas en el repositorio.")
            else:
                dict_carp = {c[1]: c[0] for c in carpetas_raiz}
                sel_carp_nom = st.selectbox("📂 Seleccionar Carpeta Principal", list(dict_carp.keys()))
                sel_carp_id = dict_carp[sel_carp_nom]
                
                # Obtener subcarpetas
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id = ? ORDER BY nombre ASC', (sel_carp_id,))
                subcarpetas = c.fetchall()
                conn.close()
                
                carpeta_trabajo_id = sel_carp_id
                if subcarpetas:
                    dict_sub = {"-- Raíz de esta carpeta --": sel_carp_id}
                    for sc in subcarpetas:
                        dict_sub[f"📁 {sc[1]}"] = sc[0]
                    sel_sub_nom = st.selectbox("📂 Subcarpeta (Opcional)", list(dict_sub.keys()))
                    carpeta_trabajo_id = dict_sub[sel_sub_nom]
                    
                st.divider()
                st.subheader("⬆️ Subir Documento a esta Carpeta")
                with st.form("form_upload_repo"):
                    up_file = st.file_uploader("Selecciona el archivo (PDF, Word, Excel, Imagen, etc.)")
                    btn_up = st.form_submit_button("⬆️ Subir Archivo al Repositorio")
                    if btn_up:
                        if up_file is not None:
                            f_bytes = up_file.getbuffer()
                            f_nombre = up_file.name
                            f_mime = up_file.type
                            f_tam = up_file.size
                            f_fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO repositorio_archivos (carpeta_id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (carpeta_trabajo_id, f_nombre, f_mime, f_tam, f_fecha, st.session_state["username"], f_bytes))
                            conn.commit()
                            conn.close()
                            
                            st.toast("🎉 ¡Archivo subido exitosamente!")
                            st.success(f"✅ ¡Archivo **{f_nombre}** guardado en el repositorio!")
                            st.rerun()

                st.divider()
                st.subheader("📄 Archivos Disponibles")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido FROM repositorio_archivos WHERE carpeta_id = ? ORDER BY id DESC', (carpeta_trabajo_id,))
                archivos = c.fetchall()
                conn.close()
                
                if not archivos:
                    st.info("No hay archivos en esta carpeta.")
                else:
                    for arch in archivos:
                        aid, anom, amime, atam, afech, ausr, acont = arch
                        col_a1, col_a2, col_a3 = st.columns([3, 1, 1])
                        with col_a1:
                            st.write(f"📄 **{anom}** ({atam/1024:.1f} KB)")
                            st.caption(f"Subido por {ausr} el {afech}")
                        with col_a2:
                            st.download_button("⬇️ Descargar", data=acont, file_name=anom, mime=amime, key=f"dl_repo_{aid}")
                        with col_a3:
                            if st.button("🗑️ Borrar", key=f"del_repo_{aid}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('DELETE FROM repositorio_archivos WHERE id = ?', (aid,))
                                conn.commit()
                                conn.close()
                                st.toast("🗑️ Archivo eliminado.")
                                st.rerun()

        with tab_r2:
            st.subheader("⚙️ Crear o Administrar Carpetas")
            with st.form("form_add_carp"):
                nom_nueva_carp = st.text_input("Nombre de la Carpeta *").strip()
                dict_padres = {"-- Carpeta Raíz Principal --": 0}
                for c_r in carpetas_raiz:
                    dict_padres[f"📁 {c_r[1]}"] = c_r[0]
                sel_padre = st.selectbox("Ubicación Padre", list(dict_padres.keys()))
                padre_id_val = dict_padres[sel_padre]
                
                btn_create_c = st.form_submit_button("➕ Crear Carpeta")
                if btn_create_c:
                    if not nom_nueva_carp:
                        st.error("El nombre de la carpeta es obligatorio.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, ?)', (nom_nueva_carp, padre_id_val))
                        conn.commit()
                        conn.close()
                        st.toast("🎉 ¡Carpeta creada!")
                        st.success(f"✅ ¡Carpeta **{nom_nueva_carp}** creada exitosamente!")
                        st.rerun()

    # ==========================================
    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Búsqueda de Pacientes")
        st.caption("Consulta general de expedientes, estatus e historial de entrevistas")
        
        filtro_p = st.radio("Filtrar por Estatus", ["🟢 Activos ('A')", "🔒 Bloqueados ('B')", "📋 Todos"], horizontal=True)
        cod_f = 'A' if "Activos" in filtro_p else ('B' if "Bloqueados" in filtro_p else 'TODOS')
        
        pacientes = listar_pacientes_bd(cod_f)
        
        if not pacientes:
            st.warning("No hay registros que coincidan con la selección.")
        else:
            st.subheader(f"Total de registros encontrados: {len(pacientes)}")
            for pac in pacientes:
                pid, pnom, fing, fnac, sexo, pest, tusr, etapa = pac
                est_badge = "🟢 Activo" if pest == 'A' else "🔒 Bloqueado"
                
                with st.expander(f"👤 **{pnom}** ({pid}) | Estatus: {est_badge} | Etapa: **{etapa}** | Tipo: {tusr}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.write(f"**Fecha de Ingreso:** {fing}")
                        st.write(f"**Fecha de Nacimiento:** {fnac}")
                        st.write(f"**Sexo:** {sexo}")
                    with c_det2:
                        datos_p, f_reg, f_mod, u_reg = obtener_entrevista(pid)
                        if datos_p:
                            pdf_file = generar_pdf(pid, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar PDF Entrevista",
                                    data=f,
                                    file_name=f"Entrevista_{pid}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{pid}"
                                )
                        else:
                            st.info("Sin entrevista realizada.")

    # ==========================================
    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración del Sistema & Seguridad")
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

    # ==========================================
    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Copia de seguridad completa y recuperación de expedientes")
        
        tab_res1, tab_res2 = st.tabs(["📥 Descargar Respaldo Seguro (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_res1:
            st.subheader("Copia de Seguridad de la Base de Datos")
            st.info("Descargue el archivo de base de datos `.db` para mantener a salvo todos los expedientes, catálogo, asignaciones, entregas y sesiones.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                    
                filename_bkp = f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                st.download_button(
                    label="📥 Descargar Respaldo de Base de Datos (.db)",
                    data=db_bytes,
                    file_name=filename_bkp,
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
            else:
                st.warning("No se encontró el archivo de base de datos local.")

        with tab_res2:
            st.subheader("Restaurar Base de Datos desde Respaldo")
            st.warning("⚠️ **ATENCIÓN**: Restaurar una base de datos reemplazará todos los datos actuales del sistema por los del respaldo.")
            
            uploaded_db = st.file_uploader("Seleccione el archivo de respaldo `.db`", type=["db", "sqlite3", "sqlite"])
            
            if uploaded_db is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    
                    init_db()
                    st.toast("🎉 ¡Base de datos restaurada exitosamente!")
                    st.success("✅ ¡Base de datos restaurada exitosamente! Todos sus expedientes, catálogo y asignaciones se han recuperado.")
                    st.balloons()
                    st.rerun()

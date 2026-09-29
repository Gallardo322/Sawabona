import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Control Clínico y Consejería - Sawabona Shikoba",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- INICIALIZACIÓN DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            bloqueado INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Tabla de Registro Basal de Pacientes / Residentes
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre TEXT NOT NULL,
            apellido_paterno TEXT NOT NULL,
            apellido_materno TEXT,
            nombre_completo TEXT NOT NULL,
            sexo TEXT NOT NULL,
            fecha_nacimiento TEXT,
            fecha_ingreso TEXT NOT NULL,
            etapa_inicial TEXT DEFAULT 'Acogida',
            fecha_inicio_etapa TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # 3. Tabla de Ficha de Ingreso y Admisión (NOM-028)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 4. Tabla de Entrevistas Iniciales de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 5. Tabla de Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            num_consejeria INTEGER,
            fecha TEXT NOT NULL,
            etapa TEXT,
            tema TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 6. Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            tipo_grupo TEXT NOT NULL,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 7. Tabla de Catálogo de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
    
    # 8. Tabla de Asignación de Medicamentos e Inventario por Paciente
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
    
    # 9. Tabla de Entregas / Surtido por Turno
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            cantidad_entregada REAL DEFAULT 0,
            usuario TEXT NOT NULL
        )
    ''')
    
    # 10. Tablas del Repositorio de Documentos (Carpetas y Archivos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            padre_id INTEGER DEFAULT NULL,
            FOREIGN KEY (padre_id) REFERENCES repositorio_carpetas(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT NOT NULL,
            usuario TEXT NOT NULL,
            contenido BLOB NOT NULL,
            FOREIGN KEY (carpeta_id) REFERENCES repositorio_carpetas(id)
        )
    ''')
    
    # Crear carpetas por defecto en el Repositorio si está vacío
    c.execute("SELECT count(*) FROM repositorio_carpetas WHERE padre_id IS NULL")
    if c.fetchone()[0] == 0:
        carpetas_default = ["Formatos", "Documentos", "Eventos", "Comprobantes", "Terapéutico"]
        for nom in carpetas_default:
            c.execute("INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, NULL)", (nom,))
            
    # Crear usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ? AND (bloqueado = 0 OR bloqueado IS NULL)',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

# --- FUNCIONES DE PACIENTES / RESIDENTES ---
def generar_siguiente_folio():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes_registro')
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
    return f"PAC-{(max_num + 1):03d}"

def generar_siguiente_expediente():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT expediente FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        exp = r[0]
        if exp and exp.startswith("EXP-"):
            try:
                num = int(exp.split("-")[1])
                if num > max_num:
                    max_num = num
            except:
                pass
    return f"EXP-{(max_num + 1):03d}"

def check_duplicate_patient(nombre, ap_p, ap_m, exp, current_pid=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    full_name = f"{nombre.strip()} {ap_p.strip()} {ap_m.strip()}".strip().lower()
    
    c.execute('SELECT paciente_id, nombre_completo, expediente, estatus FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    
    for r in rows:
        pid, fn, ex, st = r
        if current_pid and pid == current_pid:
            continue
        if fn.strip().lower() == full_name:
            return f"Ya existe un residente registrado con el nombre completo: '{fn}' (Folio: {pid}, Expediente: {ex or 'N/A'})."
        if exp and ex and ex.strip().lower() == exp.strip().lower():
            return f"El número de expediente '{exp}' ya está asignado al residente: '{fn}' (Folio: {pid})."
    return None

def guardar_paciente(paciente_id, expediente, nombre, ap_p, ap_m, sexo, fecha_nac, fecha_ing, etapa_ini, fecha_ini_etapa, estatus='A', usuario='admin'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nombre_comp = f"{nombre.strip()} {ap_p.strip()} {ap_m.strip()}".strip()
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes_registro
            SET expediente = ?, nombre = ?, apellido_paterno = ?, apellido_materno = ?, nombre_completo = ?,
                sexo = ?, fecha_nacimiento = ?, fecha_ingreso = ?, etapa_inicial = ?, fecha_inicio_etapa = ?,
                estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (expediente.strip(), nombre.strip(), ap_p.strip(), ap_m.strip(), nombre_comp,
              sexo, str(fecha_nac), str(fecha_ing), etapa_ini, str(fecha_ini_etapa), estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro 
            (paciente_id, expediente, nombre, apellido_paterno, apellido_materno, nombre_completo, sexo,
             fecha_nacimiento, fecha_ingreso, etapa_inicial, fecha_inicio_etapa, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, expediente.strip(), nombre.strip(), ap_p.strip(), ap_m.strip(), nombre_comp, sexo,
              str(fecha_nac), str(fecha_ing), etapa_ini, str(fecha_ini_etapa), estatus, fecha_actual, fecha_actual, usuario))
              
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, nombre, apellido_paterno, apellido_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_inicial, fecha_inicio_etapa, estatus FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_registro(solo_activos=True):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT paciente_id, expediente, nombre_completo, fecha_ingreso, etapa_inicial, fecha_inicio_etapa, estatus FROM pacientes_registro WHERE estatus = "A" ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, expediente, nombre_completo, fecha_ingreso, etapa_inicial, fecha_inicio_etapa, estatus FROM pacientes_registro ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE FICHA DE INGRESO Y ENTREVISTA ---
def guardar_ficha_ingreso(paciente_id, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE ficha_ingreso SET datos_json = ?, fecha_registro = ? WHERE paciente_id = ?', (datos_json, fecha_actual, paciente_id))
    else:
        c.execute('INSERT INTO ficha_ingreso (paciente_id, fecha_registro, usuario_registro, datos_json) VALUES (?, ?, ?, ?)',
                  (paciente_id, fecha_actual, usuario, datos_json))
    conn.commit()
    conn.close()

def obtener_ficha_ingreso(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, usuario_registro FROM ficha_ingreso WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2]
    return None, None, None

def guardar_entrevista(paciente_id, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
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

# --- FUNCIONES DE CONSEJERÍAS Y GRUPOS ---
def guardar_consejeria(paciente_id, num_consejeria, fecha, etapa, tema, observaciones, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO consejerias (paciente_id, num_consejeria, fecha, etapa, tema, observaciones, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, num_consejeria, str(fecha), etapa, tema, observaciones, usuario))
    conn.commit()
    conn.close()

def obtener_consejerias_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, num_consejeria, fecha, etapa, tema, observaciones, usuario FROM consejerias WHERE paciente_id = ? ORDER BY num_consejeria DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_grupo_terapeutico(fecha, tipo_grupo, tema, asistentes_list, observaciones, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    asistentes_json = json.dumps(asistentes_list, ensure_ascii=False)
    c.execute('''
        INSERT INTO grupos_terapeuticos (fecha, tipo_grupo, tema, asistentes_json, observaciones, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(fecha), tipo_grupo, tema, asistentes_json, observaciones, usuario))
    conn.commit()
    conn.close()

def obtener_grupos_terapeuticos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, fecha, tipo_grupo, tema, asistentes_json, observaciones, usuario FROM grupos_terapeuticos ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE MEDICAMENTOS ---
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
    c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)',
              (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?',
              (compuesto.strip(), nombre.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT count(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?', (med_id,))
    if c.fetchone()[0] > 0:
        conn.close()
        return False, "No se puede eliminar porque está asignado a uno o más pacientes."
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()
    return True, "Medicamento eliminado del catálogo."

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
    c.execute('''
        INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, float(manana), float(tarde), float(noche), float(existencia), obs.strip()))
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
    ''', (float(manana), float(tarde), float(noche), float(existencia), obs.strip(), asig_id))
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
    
    # Restar existencia
    c.execute('SELECT existencia FROM asignaciones_medicamentos WHERE paciente_id = ? AND medicamento_id = ?', (paciente_id, med_id))
    row = c.fetchone()
    if row:
        nueva_ex = max(0.0, row[0] - float(cantidad))
        c.execute('UPDATE asignaciones_medicamentos SET existencia = ? WHERE paciente_id = ? AND medicamento_id = ?', (nueva_ex, paciente_id, med_id))
        
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, str(fecha), turno, float(cantidad), usuario))
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
        JOIN pacientes_registro p ON a.paciente_id = p.paciente_id
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE p.estatus = 'A'
        ORDER BY p.nombre_completo ASC, m.nombre_medicamento ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DEL REPOSITORIO DE DOCUMENTOS ---
def obtener_carpetas_repositorio(padre_id=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if padre_id is None:
        c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id IS NULL ORDER BY nombre ASC')
    else:
        c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id = ? ORDER BY nombre ASC', (padre_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_todas_carpetas_flat(padre_id=None, nivel=0):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if padre_id is None:
        c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id IS NULL ORDER BY nombre ASC')
    else:
        c.execute('SELECT id, nombre FROM repositorio_carpetas WHERE padre_id = ? ORDER BY nombre ASC', (padre_id,))
    rows = c.fetchall()
    conn.close()
    
    resultado = []
    for cid, cnom in rows:
        prefix = "📁 " + ("  " * nivel)
        resultado.append((cid, f"{prefix}{cnom}"))
        sub_res = obtener_todas_carpetas_flat(cid, nivel + 1)
        resultado.extend(sub_res)
    return resultado

def crear_carpeta_repositorio(nombre, padre_id=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, ?)', (nombre.strip(), padre_id))
    conn.commit()
    conn.close()

def renombrar_carpeta_repositorio(carpeta_id, nuevo_nombre):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE repositorio_carpetas SET nombre = ? WHERE id = ?', (nuevo_nombre.strip(), carpeta_id))
    conn.commit()
    conn.close()

def contar_contenido_carpeta(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT count(*) FROM repositorio_archivos WHERE carpeta_id = ?', (carpeta_id,))
    n_archivos = c.fetchone()[0]
    c.execute('SELECT count(*) FROM repositorio_carpetas WHERE padre_id = ?', (carpeta_id,))
    n_subcarpetas = c.fetchone()[0]
    conn.close()
    return n_archivos, n_subcarpetas

def eliminar_carpeta_recursivo(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM repositorio_carpetas WHERE padre_id = ?', (carpeta_id,))
    hijos = c.fetchall()
    for h in hijos:
        eliminar_carpeta_recursivo(h[0])
    c.execute('DELETE FROM repositorio_archivos WHERE carpeta_id = ?', (carpeta_id,))
    c.execute('DELETE FROM repositorio_carpetas WHERE id = ?', (carpeta_id,))
    conn.commit()
    conn.close()

def guardar_archivo_repositorio(carpeta_id, nombre, tipo_mime, tamano, usuario, contenido_bytes):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO repositorio_archivos (carpeta_id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta_id, nombre, tipo_mime, tamano, fecha_act, usuario, contenido_bytes))
    conn.commit()
    conn.close()

def obtener_archivos_carpeta(carpeta_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario FROM repositorio_archivos WHERE carpeta_id = ? ORDER BY nombre_archivo ASC', (carpeta_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_contenido_archivo(archivo_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT nombre_archivo, tipo_mime, contenido FROM repositorio_archivos WHERE id = ?', (archivo_id,))
    row = c.fetchone()
    conn.close()
    return row

def eliminar_archivo_repositorio(archivo_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_archivos WHERE id = ?', (archivo_id,))
    conn.commit()
    conn.close()

# --- GENERACIÓN DE REPORTES PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.cell(self.epw, 5, "Sistema de Control Clinico y Expediente Digital", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

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

def generar_pdf_padron(pacientes):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "PADRON OFICIAL DE RESIDENTES ACTIVOS", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    col_w = [25, 25, 75, 30, 35]
    headers = ["Folio", "Expediente", "Nombre Completo", "Fecha Ingreso", "Etapa"]
    
    pdf.set_font("Helvetica", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for p in pacientes:
        pid, exp, nom, fing, etapa, _, _ = p
        pdf.cell(col_w[0], 6, limpiar_texto(pid), border=1, align="C")
        pdf.cell(col_w[1], 6, limpiar_texto(exp or 'N/A'), border=1, align="C")
        pdf.cell(col_w[2], 6, limpiar_texto(nom), border=1)
        pdf.cell(col_w[3], 6, limpiar_texto(fing), border=1, align="C")
        pdf.cell(col_w[4], 6, limpiar_texto(etapa or 'Acogida'), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    filename = "Padron_Residentes_Sawabona.pdf"
    pdf.output(filename)
    return filename

def generar_pdf_indicaciones_medicas(asig_list):
    pdf = PDFReport()
    pdf.add_page(orientation='L')
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "HOJA GENERAL DE INDICACIONES Y ESQUEMA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    col_w = [65, 65, 25, 25, 25, 30, 42]
    headers = ["Paciente", "Medicamento", "Mañana", "Tarde", "Noche", "Existencia", "Observaciones"]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for row in asig_list:
        pid, pnom, comp, mnom, pres, dm, dt, dn, ex, obs = row
        med_fmt = f"{mnom} ({comp} - {pres})"
        pdf.cell(col_w[0], 6, limpiar_texto(pnom), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(med_fmt), border=1)
        pdf.cell(col_w[2], 6, str(dm), border=1, align="C")
        pdf.cell(col_w[3], 6, str(dt), border=1, align="C")
        pdf.cell(col_w[4], 6, str(dn), border=1, align="C")
        pdf.cell(col_w[5], 6, str(ex), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(obs), border=1, new_x="LMARGIN", new_y="NEXT")
        
    filename = "Indicaciones_Medicas_General.pdf"
    pdf.output(filename)
    return filename

# --- APLICACIÓN PRINCIPAL ---
def main():
    init_db()
    
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "nombre_completo" not in st.session_state:
        st.session_state["nombre_completo"] = ""

    if not st.session_state["logged_in"]:
        st.markdown("<h2 style='text-align: center; color: #1B5E20;'>🔐 Sistema de Control Clínico y Consejería</h2>", unsafe_allow_html=True)
        st.markdown("<h4 style='text-align: center; color: #555;'>Comunidad Terapéutica Sawabona Shikoba A.C.</h4>", unsafe_allow_html=True)
        st.divider()
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                user_input = st.text_input("Usuario")
                pass_input = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("🔑 Iniciar Sesión", use_container_width=True)
                
                if submit:
                    user_ok = verificar_login(user_input, pass_input)
                    if user_ok:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = user_ok[0]
                        st.session_state["nombre_completo"] = user_ok[1]
                        st.success("¡Bienvenido al sistema!")
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
            st.info("💡 **Acceso por defecto**: Usuario: `admin` | Contraseña: `admin123`")

    else:
        # --- BARRA LATERAL CON MENÚ COMPLETO DE 12 MÓDULOS ---
        st.sidebar.markdown("<h3 style='color: #1B5E20;'>📋 SAWABONA A.C.</h3>", unsafe_allow_html=True)
        st.sidebar.write(f"👤 **Operador**: {st.session_state['nombre_completo']}")
        st.sidebar.divider()
        
        menu_opciones = [
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
        
        menu = st.sidebar.radio("Navegación principal", menu_opciones)
        
        st.sidebar.divider()
        if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state["logged_in"] = False
            st.rerun()

        # ==========================================
        # 1. 🏠 INICIO / TABLERO GENERAL
        # ==========================================
        if menu == "🏠 Inicio / Tablero General":
            st.title("🏠 Tablero General de Control Clínico")
            st.caption("Resumen ejecutivo de residentes activos y estado del tratamiento")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            total_activos = len(p_activos)
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Residentes Activos", total_activos)
            
            # Conteo de entrevistas
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT count(*) FROM entrevistas")
            count_ent = c.fetchone()[0]
            conn.close()
            
            m2.metric("Entrevistas Aplicadas", count_ent)
            
            # Medicamentos
            all_asig = obtener_todas_asignaciones()
            m3.metric("Medicamentos Asignados", len(all_asig))
            
            # Alertas medicamento
            alertas_count = 0
            for r in all_asig:
                d_total = r[5] + r[6] + r[7]
                ex = r[8]
                if d_total > 0 and (ex / d_total) <= 5:
                    alertas_count += 1
            m4.metric("Alertas Reabastecimiento", alertas_count, delta_color="inverse")
            
            st.divider()
            st.subheader("🎯 Distribución por Etapa de Tratamiento")
            
            etapas_list = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
            etapas_dict = {e: [] for e in etapas_list}
            
            for p in p_activos:
                pid, exp, nom, fing, etapa, fini_etapa, st_p = p
                etapa_actual = etapa if etapa in etapas_dict else "Acogida"
                
                # Calcular días en etapa
                dias_etapa = 0
                if fini_etapa:
                    try:
                        f_dt = datetime.strptime(fini_etapa, "%Y-%m-%d").date()
                        dias_etapa = (date.today() - f_dt).days
                    except:
                        pass
                etapas_dict[etapa_actual].append((pid, exp, nom, dias_etapa))
                
            ec1, ec2, ec3, ec4, ec5 = st.columns(5)
            cols_map = [ec1, ec2, ec3, ec4, ec5]
            
            for idx, e_nom in enumerate(etapas_list):
                with cols_map[idx]:
                    st.markdown(f"##### {e_nom}")
                    list_e = etapas_dict[e_nom]
                    st.metric("Residentes", len(list_e))
                    with st.expander(f"Ver lista ({len(list_e)})"):
                        for item in list_e:
                            d_tag = f"🔴 {item[3]} días" if item[3] > 90 else f"🟢 {item[3]} días"
                            st.write(f"• **{item[2]}** ({item[0]})\n  _{d_tag}_")

        # ==========================================
        # 2. 👤 REGISTRO Y EDICIÓN DE PACIENTES
        # ==========================================
        elif menu == "👤 Registro y Edición de Pacientes":
            st.title("👤 Registro y Edición de Pacientes / Residentes")
            st.caption("Padrón oficial de usuarios y control de expediente único")
            
            tab_alta, tab_edit, tab_padron = st.tabs([
                "➕ Alta de Nuevo Paciente",
                "✏️ Edición / Cambio de Estatus",
                "📋 Padrón General & Reporte PDF"
            ])
            
            # --- TAB 1: ALTA DE PACIENTE CON TABULACIÓN EXACTA DE 10 CAMPOS ---
            with tab_alta:
                st.subheader("Formulario de Alta de Nuevo Paciente")
                
                # Gestión de variables de sesión para limpieza
                if "reg_nombre" not in st.session_state: st.session_state["reg_nombre"] = ""
                if "reg_ap_p" not in st.session_state: st.session_state["reg_ap_p"] = ""
                if "reg_ap_m" not in st.session_state: st.session_state["reg_ap_m"] = ""
                if "show_another_prompt" not in st.session_state: st.session_state["show_another_prompt"] = False
                if "last_saved_pid" not in st.session_state: st.session_state["last_saved_pid"] = ""

                # Prompt para registrar otro paciente
                if st.session_state["show_another_prompt"]:
                    st.balloons()
                    st.success(f"🎉 ¡Residente registrado exitosamente con Folio **{st.session_state['last_saved_pid']}**!")
                    st.markdown("#### ¿Desea ingresar a otro paciente?")
                    cb1, cb2 = st.columns(2)
                    with cb1:
                        if st.button("🟢 Sí, registrar otro paciente", use_container_width=True):
                            st.session_state["reg_nombre"] = ""
                            st.session_state["reg_ap_p"] = ""
                            st.session_state["reg_ap_m"] = ""
                            st.session_state["show_another_prompt"] = False
                            st.rerun()
                    with cb2:
                        if st.button("🔴 No, mantener datos en pantalla", use_container_width=True):
                            st.session_state["show_another_prompt"] = False
                            st.rerun()
                    st.divider()

                folio_sug = generar_siguiente_folio()
                exp_sug = generar_siguiente_expediente()
                
                with st.form("form_alta_paciente"):
                    # Fila 1: 1. Folio Único | 2. Expediente
                    r1_1, r1_2 = st.columns(2)
                    with r1_1:
                        f_pid = st.text_input("1. Folio Único / ID Paciente *", value=folio_sug).strip()
                    with r1_2:
                        f_exp = st.text_input("2. Número de Expediente *", value=exp_sug).strip()
                        
                    # Fila 2: 3. Nombre | 4. Apellido Paterno | 5. Apellido Materno
                    r2_1, r2_2, r2_3 = st.columns(3)
                    with r2_1:
                        f_nom = st.text_input("3. Nombre(s) *", value=st.session_state["reg_nombre"]).strip()
                    with r2_2:
                        f_app = st.text_input("4. Apellido Paterno *", value=st.session_state["reg_ap_p"]).strip()
                    with r2_3:
                        f_apm = st.text_input("5. Apellido Materno", value=st.session_state["reg_ap_m"]).strip()
                        
                    # Fila 3: 6. Sexo | 7. Fecha de Nacimiento
                    r3_1, r3_2 = st.columns(2)
                    with r3_1:
                        f_sexo = st.selectbox("6. Sexo *", ["MASCULINO", "FEMENINO"])
                    with r3_2:
                        f_fnac = st.date_input("7. Fecha de Nacimiento *", value=date(1995, 1, 1))
                        
                    # Fila 4: 8. Fecha Ingreso | 9. Etapa Inicial | 10. Fecha Inicio Etapa
                    r4_1, r4_2, r4_3 = st.columns(3)
                    with r4_1:
                        f_fing = st.date_input("8. Fecha de Ingreso Institucional *", value=date.today())
                    with r4_2:
                        f_etapa = st.selectbox("9. Etapa Inicial *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                    with r4_3:
                        f_fetapa = st.date_input("10. Fecha Inicio de Etapa Actual *", value=date.today())
                        
                    btn_guardar_p = st.form_submit_button("💾 Guardar y Dar de Alta Residente", use_container_width=True)
                    
                    if btn_guardar_p:
                        if not f_pid or not f_exp or not f_nom or not f_app:
                            st.error("⚠️ Complete los campos obligatorios: Folio, Expediente, Nombre y Apellido Paterno.")
                        else:
                            dup_msg = check_duplicate_patient(f_nom, f_app, f_apm, f_exp, current_pid=f_pid)
                            if dup_msg:
                                st.error(f"⚠️ {dup_msg}")
                            else:
                                guardar_paciente(f_pid, f_exp, f_nom, f_app, f_apm, f_sexo, f_fnac, f_fing, f_etapa, f_fetapa, estatus='A', usuario=st.session_state["username"])
                                st.session_state["last_saved_pid"] = f_pid
                                st.session_state["show_another_prompt"] = True
                                st.rerun()

            # --- TAB 2: EDICIÓN DE PACIENTE ---
            with tab_edit:
                st.subheader("Modificar Datos o Estatus de Paciente")
                p_todos = listar_pacientes_registro(solo_activos=False)
                if not p_todos:
                    st.info("No hay pacientes registrados.")
                else:
                    options_p = [f"{p[0]} - {p[2]} ({'Activo' if p[6]=='A' else 'Inactivo'})" for p in p_todos]
                    sel_p = st.selectbox("Seleccione el residente a editar:", ["-- Seleccionar --"] + options_p)
                    
                    if sel_p != "-- Seleccionar --":
                        pid_sel = sel_p.split(" - ")[0]
                        p_data = obtener_paciente(pid_sel)
                        
                        if p_data:
                            with st.form("form_edit_paciente"):
                                e_1, e_2 = st.columns(2)
                                with e_1:
                                    st.text_input("Folio Único", value=p_data[0], disabled=True)
                                with e_2:
                                    e_exp = st.text_input("Número de Expediente *", value=p_data[1] or "")
                                    
                                e_3, e_4, e_5 = st.columns(3)
                                with e_3:
                                    e_nom = st.text_input("Nombre(s) *", value=p_data[2] or "")
                                with e_4:
                                    e_app = st.text_input("Apellido Paterno *", value=p_data[3] or "")
                                with e_5:
                                    e_apm = st.text_input("Apellido Materno", value=p_data[4] or "")
                                    
                                e_6, e_7 = st.columns(2)
                                with e_6:
                                    e_sexo = st.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if p_data[6]=="MASCULINO" else 1)
                                with e_7:
                                    try: fn_val = datetime.strptime(p_data[7], "%Y-%m-%d").date()
                                    except: fn_val = date(1995,1,1)
                                    e_fnac = st.date_input("Fecha de Nacimiento", value=fn_val)
                                    
                                e_8, e_9, e_10 = st.columns(3)
                                with e_8:
                                    try: fi_val = datetime.strptime(p_data[8], "%Y-%m-%d").date()
                                    except: fi_val = date.today()
                                    e_fing = st.date_input("Fecha de Ingreso", value=fi_val)
                                with e_9:
                                    etapas_arr = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                                    idx_e = etapas_arr.index(p_data[9]) if p_data[9] in etapas_arr else 0
                                    e_etapa = st.selectbox("Etapa Actual", etapas_arr, index=idx_e)
                                with e_10:
                                    try: fe_val = datetime.strptime(p_data[10], "%Y-%m-%d").date()
                                    except: fe_val = date.today()
                                    e_fetapa = st.date_input("Fecha Inicio Etapa", value=fe_val)
                                    
                                e_st = st.selectbox("Estatus del Residente", ["Activo ('A')", "Inactivo / Bloqueado ('B')"], index=0 if p_data[11]=='A' else 1)
                                st_char = 'A' if "Activo" in e_st else 'B'
                                
                                btn_upd_p = st.form_submit_button("💾 Guardar Cambios en Residente", use_container_width=True)
                                if btn_upd_p:
                                    dup_err = check_duplicate_patient(e_nom, e_app, e_apm, e_exp, current_pid=p_data[0])
                                    if dup_err:
                                        st.error(f"⚠️ {dup_err}")
                                    else:
                                        guardar_paciente(p_data[0], e_exp, e_nom, e_app, e_apm, e_sexo, e_fnac, e_fing, e_etapa, e_fetapa, estatus=st_char, usuario=st.session_state["username"])
                                        st.success(f"✅ ¡Datos actualizados correctamente para {p_data[0]}!")
                                        st.rerun()

            # --- TAB 3: PADRÓN GENERAL Y PDF ---
            with tab_padron:
                st.subheader("📋 Padrón de Residentes Activos")
                p_activos = listar_pacientes_registro(solo_activos=True)
                if not p_activos:
                    st.info("No hay residentes activos.")
                else:
                    df_padron = []
                    for p in p_activos:
                        df_padron.append({
                            "Folio": p[0],
                            "Expediente": p[1] or "N/A",
                            "Nombre Completo": p[2],
                            "Fecha Ingreso": p[3],
                            "Etapa Actual": p[4],
                            "Inicio Etapa": p[5]
                        })
                    st.dataframe(df_padron, use_container_width=True)
                    
                    pdf_padron_file = generar_pdf_padron(p_activos)
                    with open(pdf_padron_file, "rb") as f_pdf:
                        st.download_button(
                            label="🖨️ Descargar Padrón Oficial en PDF",
                            data=f_pdf,
                            file_name="Padron_Residentes_Sawabona.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

        # ==========================================
        # 3. 📄 FICHA DE INGRESO Y ADMISIÓN
        # ==========================================
        elif menu == "📄 Ficha de Ingreso y Admisión":
            st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
            st.caption("Documentación oficial de ingreso residencial y contrato de servicios")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            if not p_activos:
                st.warning("Debe dar de alta al residente en el Registro de Pacientes antes de llenar la Ficha.")
            else:
                p_opts = [f"{p[0]} - {p[2]}" for p in p_activos]
                sel_f = st.selectbox("Seleccione el Residente:", ["-- Seleccionar --"] + p_opts)
                
                if sel_f != "-- Seleccionar --":
                    pid_f = sel_f.split(" - ")[0]
                    f_datos, f_freg, f_ureg = obtener_ficha_ingreso(pid_f)
                    f_datos = f_datos or {}
                    
                    if f_freg:
                        st.info(f"📌 Ficha registrada el {f_freg} por {f_ureg}.")
                        
                    with st.form("form_ficha_ingreso"):
                        f_tab1, f_tab2, f_tab3, f_tab4 = st.tabs([
                            "1. Datos Personales",
                            "2. Responsable Familiar",
                            "3. Motivo & Sustancias",
                            "4. Finanzas & Firmas"
                        ])
                        
                        with f_tab1:
                            st.subheader("Datos Personales del Usuario")
                            col1, col2 = st.columns(2)
                            with col1:
                                f_curp = st.text_input("CURP", value=f_datos.get("curp", ""))
                                f_ecivil = st.selectbox("Estado Civil", ["SOLTERO(A)", "CASADO(A)", "UNION LIBRE", "DIVORCIADO(A)", "VIUDO(A)"], index=0)
                            with col2:
                                f_ocup = st.text_input("Ocupación", value=f_datos.get("ocupacion", ""))
                                f_dom = st.text_area("Domicilio Completo", value=f_datos.get("domicilio", ""))

                        with f_tab2:
                            st.subheader("Familiar o Responsable Legal")
                            col3, col4 = st.columns(2)
                            with col3:
                                f_resp_nom = st.text_input("Nombre del Responsable *", value=f_datos.get("resp_nombre", ""))
                                f_resp_par = st.text_input("Parentesco *", value=f_datos.get("resp_parentesco", ""))
                            with col4:
                                f_resp_tel = st.text_input("Teléfono de Contacto *", value=f_datos.get("resp_telefono", ""))
                                f_resp_dom = st.text_area("Domicilio del Responsable", value=f_datos.get("resp_domicilio", ""))

                        with f_tab3:
                            st.subheader("Motivo de Ingreso y Consumo")
                            f_motivo = st.text_area("Motivo Principal de Ingreso", value=f_datos.get("motivo", ""))
                            f_sust_ing = st.text_input("Sustancia Principal de Consumo", value=f_datos.get("sustancia_principal", ""))

                        with f_tab4:
                            st.subheader("Acuerdo Financiero y Observaciones")
                            f_cuota = st.text_input("Cuota de Recuperación Pactada ($)", value=f_datos.get("cuota", ""))
                            f_obs = st.text_area("Observaciones de Admisión", value=f_datos.get("observaciones", ""))
                            
                        btn_guardar_fi = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                        if btn_guardar_fi:
                            datos_fi = {
                                "curp": f_curp, "estado_civil": f_ecivil, "ocupacion": f_ocup, "domicilio": f_dom,
                                "resp_nombre": f_resp_nom, "resp_parentesco": f_resp_par, "resp_telefono": f_resp_tel, "resp_domicilio": f_resp_dom,
                                "motivo": f_motivo, "sustancia_principal": f_sust_ing, "cuota": f_cuota, "observaciones": f_obs
                            }
                            guardar_ficha_ingreso(pid_f, datos_fi, st.session_state["username"])
                            st.success(f"✅ ¡Ficha de Ingreso guardada correctamente para {pid_f}!")

        # ==========================================
        # 4. 📝 ENTREVISTA INICIAL DE CONSEJERÍA
        # ==========================================
        elif menu == "📝 Entrevista Inicial de Consejería":
            st.title("📝 Entrevista Inicial de Consejería")
            st.caption("Evaluación clínica digital de historia de consumo y disposición al cambio")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            if not p_activos:
                st.warning("Debe dar de alta al residente primero.")
            else:
                p_opts = [f"{p[0]} - {p[2]}" for p in p_activos]
                sel_e = st.selectbox("Seleccione el Residente para la Entrevista:", ["-- Seleccionar --"] + p_opts)
                
                if sel_e != "-- Seleccionar --":
                    pid_e = sel_e.split(" - ")[0]
                    e_datos, e_freg, e_fmod, e_ureg = obtener_entrevista(pid_e)
                    e_datos = e_datos or {}
                    
                    if e_freg:
                        st.info(f"📌 Entrevista registrada el {e_freg} por {e_ureg}. Última mod: {e_fmod}")
                        
                    with st.form("form_entrevista_clinica"):
                        t1, t2, t3, t4 = st.tabs([
                            "1. Historia de Consumo",
                            "2. Disposición al Cambio",
                            "3. Entorno Familiar",
                            "4. Evaluación y Firma"
                        ])
                        
                        with t1:
                            st.subheader("Historia de Consumo de Sustancias")
                            sust_imp = st.text_input("Sustancia de Mayor Impacto", value=e_datos.get("sustancia_impacto", ""))
                            edad_ini = st.text_input("Edad de Inicio de Consumo", value=e_datos.get("edad_inicio", ""))
                            patron = st.text_area("Patrón y Frecuencia de Consumo", value=e_datos.get("patron_consumo", ""))

                        with t2:
                            st.subheader("Evaluación de Disposición al Cambio")
                            abst_previa = st.text_area("Periodos de Abstinencia Previos (Si tuvo y cómo los logró)", value=e_datos.get("abstinencia_previa", ""))
                            motiva = st.text_area("Motivación Principal para Buscar Tratamiento", value=e_datos.get("motivacion", ""))

                        with t3:
                            st.subheader("Factores Sociales y Familiares")
                            fam_red = st.text_area("Red de Apoyo Familiar Principal", value=e_datos.get("red_familiar", ""))
                            riesgos = st.text_area("Riesgos Sociales Identificados", value=e_datos.get("riesgos_sociales", ""))

                        with t4:
                            st.subheader("Evaluación Global del Consejero")
                            obs_cons = st.text_area("Observaciones y Plan de Consejería", value=e_datos.get("observaciones", ""))
                            eval_nom = st.text_input("Nombre del Consejero Evaluador", value=e_datos.get("evaluador_nombre", st.session_state["nombre_completo"]))
                            
                        btn_g_e = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                        if btn_g_e:
                            d_e = {
                                "sustancia_impacto": sust_imp, "edad_inicio": edad_ini, "patron_consumo": patron,
                                "abstinencia_previa": abst_previa, "motivacion": motiva,
                                "red_familiar": fam_red, "riesgos_sociales": riesgos,
                                "observaciones": obs_cons, "evaluador_nombre": eval_nom
                            }
                            guardar_entrevista(pid_e, d_e, st.session_state["username"])
                            st.success(f"✅ ¡Entrevista guardada con éxito para {pid_e}!")

        # ==========================================
        # 5. 📝 CONSEJERÍAS INDIVIDUALES
        # ==========================================
        elif menu == "📝 Consejerías Individuales":
            st.title("📝 Bitácora de Consejerías Individuales")
            st.caption("Seguimiento continuo de sesiones de consejería personal")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            if not p_activos:
                st.warning("No hay pacientes activos.")
            else:
                p_opts = [f"{p[0]} - {p[2]}" for p in p_activos]
                sel_ci = st.selectbox("Seleccione el Residente:", ["-- Seleccionar --"] + p_opts)
                
                if sel_ci != "-- Seleccionar --":
                    pid_ci = sel_ci.split(" - ")[0]
                    p_info = obtener_paciente(pid_ci)
                    
                    st.subheader(f"Registrar Sesión para {p_info[5]} ({pid_ci})")
                    c_hist = obtener_consejerias_paciente(pid_ci)
                    next_num = len(c_hist) + 1
                    
                    with st.form("form_consejeria_ind"):
                        ci_1, ci_2, ci_3 = st.columns(3)
                        with ci_1:
                            st.text_input("Número de Consejería", value=f"Sesión #{next_num}", disabled=True)
                        with ci_2:
                            ci_fecha = st.date_input("Fecha de Sesión", value=date.today())
                        with ci_3:
                            ci_etapa = st.text_input("Etapa Actual", value=p_info[9] or "Acogida", disabled=True)
                            
                        ci_tema = st.text_input("Tema Trata / Objetivo de la Sesión *")
                        ci_obs = st.text_area("Observaciones, Compromisos y Retroalimentación *")
                        
                        btn_g_ci = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)
                        if btn_g_ci:
                            if not ci_tema or not ci_obs:
                                st.error("⚠️ Ingrese el tema y las observaciones.")
                            else:
                                guardar_consejeria(pid_ci, next_num, ci_fecha, p_info[9], ci_tema, ci_obs, st.session_state["username"])
                                st.success("✅ ¡Consejería registrada correctamente!")
                                st.rerun()

                    st.divider()
                    st.subheader("📜 Historial de Consejerías de este Residente")
                    if not c_hist:
                        st.info("Aún no hay sesiones registradas.")
                    else:
                        for c_item in c_hist:
                            with st.expander(f"Sesión #{c_item[1]} - {c_item[2]} | Tema: {c_item[4]}"):
                                st.write(f"**Etapa:** {c_item[3]} | **Atendió:** {c_item[6]}")
                                st.write(f"**Observaciones:** {c_item[5]}")

        # ==========================================
        # 6. 🎯 GESTIÓN DE ETAPAS & PROCESO
        # ==========================================
        elif menu == "🎯 Gestión de Etapas & Proceso":
            st.title("🎯 Gestión de Etapas de Tratamiento y Avance Clínico")
            st.caption("Control de avance por etapas y alertas por rezago clínico (>90 días)")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            if not p_activos:
                st.info("No hay residentes activos.")
            else:
                p_opts = [f"{p[0]} - {p[2]} (Etapa actual: {p[4]})" for p in p_activos]
                sel_ge = st.selectbox("Seleccione el residente a evaluar/promover:", ["-- Seleccionar --"] + p_opts)
                
                if sel_ge != "-- Seleccionar --":
                    pid_ge = sel_ge.split(" - ")[0]
                    p_info = obtener_paciente(pid_ge)
                    
                    st.write(f"**Residente:** {p_info[5]} | **Etapa Actual:** `{p_info[9]}`")
                    
                    dias_e = 0
                    if p_info[10]:
                        try:
                            f_dt = datetime.strptime(p_info[10], "%Y-%m-%d").date()
                            dias_e = (date.today() - f_dt).days
                        except: pass
                        
                    if dias_e > 90:
                        st.error(f"🚨 **Alerta de Rezago Clínico**: El residente lleva **{dias_e} días** en la etapa '{p_info[9]}' (Límite recomendado: 90 días).")
                    else:
                        st.success(f"🟢 El residente lleva **{dias_e} días** en la etapa '{p_info[9]}'.")

                    st.divider()
                    st.subheader("Promover o Cambiar de Etapa")
                    
                    with st.form("form_promover_etapa"):
                        etapas_list = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                        idx_cur = etapas_list.index(p_info[9]) if p_info[9] in etapas_list else 0
                        
                        ge_nueva = st.selectbox("Nueva Etapa asignada", etapas_list, index=min(idx_cur + 1, len(etapas_list)-1))
                        ge_fecha = st.date_input("Fecha de Inicio de la Nueva Etapa", value=date.today())
                        ge_motivo = st.text_area("Justificación Clínica / Observaciones del Cambio")
                        
                        btn_g_etapa = st.form_submit_button("💾 Promover / Actualizar Etapa", use_container_width=True)
                        if btn_g_etapa:
                            guardar_paciente(p_info[0], p_info[1], p_info[2], p_info[3], p_info[4], p_info[6], p_info[7], p_info[8], ge_nueva, ge_fecha, estatus=p_info[11], usuario=st.session_state["username"])
                            st.success(f"🎉 ¡Residente {p_info[0]} promovido a la etapa '{ge_nueva}' con éxito!")
                            st.rerun()

        # ==========================================
        # 7. 🗣️ GRUPOS TERAPÉUTICOS
        # ==========================================
        elif menu == "🗣️ Grupos Terapéuticos":
            st.title("🗣️ Registro de Grupos Terapéuticos y Talleres")
            st.caption("Control de asistencia e intervenciones grupales")
            
            p_activos = listar_pacientes_registro(solo_activos=True)
            
            tab_gt1, tab_gt2 = st.tabs(["➕ Registrar Nuevo Grupo", "📜 Historial de Grupos"])
            
            with tab_gt1:
                with st.form("form_grupo_terapeutico"):
                    gt_1, gt_2 = st.columns(2)
                    with gt_1:
                        gt_fecha = st.date_input("Fecha de la Sesión", value=date.today())
                    with gt_2:
                        gt_tipo = st.selectbox("Tipo de Grupo", ["Aquí y Ahora", "Prevención de Recaídas", "Estudio de Pasos", "Espiritualidad", "Desarrollo Humano", "Taller Temático"])
                        
                    gt_tema = st.text_input("Tema Abordado en la Sesión *")
                    
                    st.markdown("##### Asistencia de Residentes Activos")
                    asistentes_sel = []
                    if p_activos:
                        c_gt_a, c_gt_b = st.columns(2)
                        for idx_p, p_item in enumerate(p_activos):
                            col_target = c_gt_a if idx_p % 2 == 0 else c_gt_b
                            with col_target:
                                chk = st.checkbox(f"{p_item[2]} ({p_item[0]})", key=f"gt_p_{p_item[0]}")
                                if chk:
                                    asistentes_sel.append(p_item[0])
                                    
                    gt_obs = st.text_area("Observaciones Generales y Dinámica del Grupo")
                    btn_g_gt = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)
                    
                    if btn_g_gt:
                        if not gt_tema:
                            st.error("⚠️ Ingrese el tema de la sesión.")
                        else:
                            guardar_grupo_terapeutico(gt_fecha, gt_tipo, gt_tema, asistentes_sel, gt_obs, st.session_state["username"])
                            st.success(f"✅ ¡Grupo '{gt_tipo}' guardado exitosamente con {len(asistentes_sel)} asistentes!")
                            st.rerun()

            with tab_gt2:
                g_hist = obtener_grupos_terapeuticos()
                if not g_hist:
                    st.info("No hay grupos registrados.")
                else:
                    for g in g_hist:
                        asist_list = json.loads(g[4]) if g[4] else []
                        with st.expander(f"📅 {g[1]} | {g[2]} - Tema: {g[3]} ({len(asist_list)} Asistentes)"):
                            st.write(f"**Facilitador:** {g[6]}")
                            st.write(f"**Observaciones:** {g[5] or 'Ninguna'}")
                            st.write(f"**Asistentes (Folios):** {', '.join(asist_list) if asist_list else 'Ninguno'}")

        # ==========================================
        # 8. 💊 CONTROL DE MEDICAMENTOS
        # ==========================================
        elif menu == "💊 Control de Medicamentos":
            st.title("💊 Control y Administración de Medicamentos")
            st.caption("Catálogo, asignaciones por residente, surtido por turnos y alertas")
            
            m_tab1, m_tab2, m_tab3, m_tab4, m_tab5 = st.tabs([
                "💊 Catálogo de Medicamentos",
                "📋 Asignación e Inventario",
                "🕒 Surtido por Turno",
                "🚨 Alarmas Reabastecimiento",
                "📄 Reporte de Indicaciones PDF"
            ])
            
            # --- SUB-TAB 1: CATÁLOGO ---
            with m_tab1:
                st.subheader("Catálogo General de Medicamentos")
                cat_meds = obtener_catalogo_medicamentos()
                
                c_c1, c_c2 = st.columns([2, 1])
                with c_c1:
                    st.markdown("##### Medicamentos en Catálogo")
                    if not cat_meds:
                        st.info("El catálogo está vacío.")
                    else:
                        df_cat = [{"ID": cm[0], "Compuesto": cm[1], "Nombre Comercial": cm[2], "Presentación": cm[3]} for cm in cat_meds]
                        st.dataframe(df_cat, use_container_width=True)
                        
                with c_c2:
                    st.markdown("##### ➕ Agregar al Catálogo")
                    with st.form("form_add_cat_med"):
                        cm_comp = st.text_input("Compuesto / Sustancia Activa *")
                        cm_nom = st.text_input("Nombre Comercial / Medicamento *")
                        cm_pres = st.text_input("Presentación (Ej. Tab 500mg) *")
                        btn_cm = st.form_submit_button("💾 Guardar en Catálogo")
                        if btn_cm:
                            if cm_comp and cm_nom and cm_pres:
                                guardar_medicamento_catalogo(cm_comp, cm_nom, cm_pres)
                                st.success("✅ ¡Medicamento agregado!")
                                st.rerun()

            # --- SUB-TAB 2: ASIGNACIÓN E INVENTARIO ---
            with m_tab2:
                st.subheader("Asignación de Medicamentos por Residente")
                p_activos = listar_pacientes_registro(solo_activos=True)
                cat_meds = obtener_catalogo_medicamentos()
                
                if not p_activos or not cat_meds:
                    st.warning("Se requieren residentes activos y medicamentos en catálogo.")
                else:
                    p_opts = [f"{p[0]} - {p[2]}" for p in p_activos]
                    sel_pm = st.selectbox("Seleccione el Residente:", ["-- Seleccionar --"] + p_opts, key="sel_pm_asig")
                    
                    if sel_pm != "-- Seleccionar --":
                        pid_pm = sel_pm.split(" - ")[0]
                        asig_curr = obtener_asignaciones_paciente(pid_pm)
                        
                        st.markdown("##### Medicamentos Asignados Actualmente")
                        if not asig_curr:
                            st.info("Este residente no tiene medicamentos asignados.")
                        else:
                            for a in asig_curr:
                                with st.expander(f"💊 {a[3]} ({a[2]} - {a[4]}) | Existencia: {a[8]}"):
                                    st.write(f"**Esquema:** Mañana: {a[5]} | Tarde: {a[6]} | Noche: {a[7]}")
                                    st.write(f"**Observaciones:** {a[9]}")
                                    
                                    # Modificar existencia directamente
                                    with st.form(f"form_mod_asig_{a[0]}"):
                                        ma_m = st.number_input("Dosis Mañana", value=float(a[5]), key=f"dm_{a[0]}")
                                        ma_t = st.number_input("Dosis Tarde", value=float(a[6]), key=f"dt_{a[0]}")
                                        ma_n = st.number_input("Dosis Noche", value=float(a[7]), key=f"dn_{a[0]}")
                                        ma_ex = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL", value=float(a[8]), key=f"ex_{a[0]}")
                                        ma_obs = st.text_input("Observaciones", value=a[9], key=f"ob_{a[0]}")
                                        
                                        cb_upd, cb_del = st.columns(2)
                                        with cb_upd:
                                            if st.form_submit_button("💾 Actualizar"):
                                                actualizar_asignacion_medicamento(a[0], ma_m, ma_t, ma_n, ma_ex, ma_obs)
                                                st.success("✅ Asignación actualizada.")
                                                st.rerun()
                                        with cb_del:
                                            if st.form_submit_button("🗑️ Retirar Medicamento"):
                                                eliminar_asignacion_medicamento(a[0])
                                                st.warning("Medicamento retirado.")
                                                st.rerun()

                        st.divider()
                        st.markdown("##### ➕ Asignar Nuevo Medicamento del Catálogo")
                        med_opts = {f"{m[2]} ({m[1]} - {m[3]})": m[0] for m in cat_meds}
                        sel_m_cat = st.selectbox("Seleccione Medicamento del Catálogo:", ["-- Seleccionar --"] + list(med_opts.keys()))
                        
                        if sel_m_cat != "-- Seleccionar --":
                            id_m_cat = med_opts[sel_m_cat]
                            with st.form("form_nueva_asig"):
                                na_m = st.number_input("Dosis Mañana", value=0.0, step=0.5)
                                na_t = st.number_input("Dosis Tarde", value=0.0, step=0.5)
                                na_n = st.number_input("Dosis Noche", value=0.0, step=0.5)
                                na_ex = st.number_input("Existencia Inicial del Paciente", value=0.0, step=1.0)
                                na_obs = st.text_input("Indicaciones / Observaciones", placeholder="Ej. Tomar con alimentos")
                                
                                btn_g_na = st.form_submit_button("💾 Guardar Asignación")
                                if btn_g_na:
                                    guardar_asignacion_medicamento(pid_pm, id_m_cat, na_m, na_t, na_n, na_ex, na_obs)
                                    st.success("✅ ¡Medicamento asignado correctamente!")
                                    st.rerun()

            # --- SUB-TAB 3: SURTIDO POR TURNO ---
            with m_tab3:
                st.subheader("🕒 Surtido y Entrega de Medicamentos por Turno")
                s_fecha = st.date_input("Fecha de Entrega", value=date.today())
                s_turno = st.selectbox("Turno a Surtir", ["Mañana", "Medio Día / Tarde", "Noche"])
                
                all_asig = obtener_todas_asignaciones()
                if not all_asig:
                    st.info("No hay medicamentos asignados en el sistema.")
                else:
                    st.markdown(f"##### Lista de Pacientes con Dosis para el Turno '{s_turno}'")
                    
                    # Filtrar por dosis segun turno
                    for asig in all_asig:
                        pid, pnom, comp, mnom, pres, dm, dt, dn, ex, obs = asig
                        cant_indicada = dm if s_turno=="Mañana" else (dt if "Tarde" in s_turno else dn)
                        
                        if cant_indicada > 0:
                            col_s1, col_s2, col_s3 = st.columns([3, 1.5, 1])
                            with col_s1:
                                st.write(f"👤 **{pnom}** ({pid})\n💊 {mnom} ({comp} - {pres})\n_Indicado: {cant_indicada} unidades_")
                            with col_s2:
                                if ex <= 0:
                                    st.error("🚨 SIN EXISTENCIA (0)")
                                else:
                                    st.info(f"Existencia actual: {ex}")
                            with col_s3:
                                if ex <= 0:
                                    st.button("🚫 Bloqueado", disabled=True, key=f"btn_blk_{pid}_{mnom}")
                                else:
                                    if st.button(f"Surtir {cant_indicada}", key=f"btn_sur_{pid}_{mnom}"):
                                        # Buscar id de medicamento
                                        cat_m = obtener_catalogo_medicamentos()
                                        mid_find = None
                                        for cm in cat_m:
                                            if cm[2] == mnom: mid_find = cm[0]; break
                                        if mid_find:
                                            registrar_entrega_medicamento(pid, mid_find, s_fecha, s_turno, cant_indicada, st.session_state["username"])
                                            st.success("✅ ¡Dosis entregada!")
                                            st.rerun()
                            st.divider()

            # --- SUB-TAB 4: ALARMAS DE REABASTECIMIENTO ---
            with m_tab4:
                st.subheader("🚨 Alarmas de Reabastecimiento de Medicamentos (<= 5 Días)")
                all_asig = obtener_todas_asignaciones()
                
                alertas_list = []
                for a in all_asig:
                    pid, pnom, comp, mnom, pres, dm, dt, dn, ex, obs = a
                    d_total = dm + dt + dn
                    if d_total > 0:
                        dias_rest = ex / d_total
                        if dias_rest <= 5:
                            alertas_list.append((pid, pnom, mnom, comp, pres, ex, d_total, round(dias_rest, 1)))
                            
                if not alertas_list:
                    st.success("🟢 Todos los pacientes cuentan con existencias suficientes para más de 5 días.")
                else:
                    for al in alertas_list:
                        bg_color = "#FFCDD2" if al[7] <= 2 else "#FFF9C4"
                        st.markdown(f'''
                            <div style="background-color: {bg_color}; padding: 12px; border-radius: 8px; margin-bottom: 10px;">
                                👤 <b>{al[1]}</b> ({al[0]})<br>
                                💊 <b>{al[2]}</b> ({al[3]} - {al[4]})<br>
                                📦 Existencia actual: <b>{al[5]}</b> unidades | Consumo diario: <b>{al[6]}</b><br>
                                ⚠️ <b>DÍAS RESTANTES CALCULADOS: {al[7]} DÍAS</b>
                            </div>
                        ''', unsafe_allow_html=True)

            # --- SUB-TAB 5: REPORTE DE INDICACIONES PDF ---
            with m_tab5:
                st.subheader("📄 Listado Completo de Indicaciones Médicas")
                all_asig = obtener_todas_asignaciones()
                
                if not all_asig:
                    st.info("No hay asignaciones de medicamentos.")
                else:
                    df_ind = []
                    for a in all_asig:
                        df_ind.append({
                            "Paciente": a[1],
                            "Medicamento": f"{a[3]} ({a[2]} - {a[4]})",
                            "Mañana": a[5],
                            "Tarde": a[6],
                            "Noche": a[7],
                            "Existencia": a[8],
                            "Observaciones": a[9]
                        })
                    st.dataframe(df_ind, use_container_width=True)
                    
                    pdf_ind_file = generar_pdf_indicaciones_medicas(all_asig)
                    with open(pdf_ind_file, "rb") as f_ind:
                        st.download_button(
                            label="🖨️ Descargar Listado de Indicaciones Médicas en PDF",
                            data=f_ind,
                            file_name="Indicaciones_Medicas_General.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

        # ==========================================
        # 9. 📁 REPOSITORIO DE DOCUMENTOS (100% INSTITUCIONAL)
        # ==========================================
        elif menu == "📁 Repositorio de Documentos":
            st.title("📁 Repositorio Institucional de Documentos")
            st.caption("Gestión centralizada de archivos, formatos y carpetas de la comunidad")
            
            tab_rep1, tab_rep2 = st.tabs(["📂 Explorar y Subir Archivos", "⚙️ Administración de Carpetas"])
            
            # --- SUB-TAB 1: EXPLORAR Y SUBIR ---
            with tab_rep1:
                col_r1, col_r2 = st.columns([1, 2])
                
                with col_r1:
                    st.markdown("##### 📁 Selección de Carpeta")
                    carpetas_flat = obtener_todas_carpetas_flat(padre_id=None)
                    
                    if not carpetas_flat:
                        st.info("No hay carpetas creadas.")
                        sel_cid = None
                    else:
                        c_dict = {cf[1]: cf[0] for cf in carpetas_flat}
                        sel_c_name = st.selectbox("Carpeta destino / exploración:", list(c_dict.keys()))
                        sel_cid = c_dict[sel_c_name]
                        
                with col_r2:
                    if sel_cid is not None:
                        st.markdown(f"##### 📄 Archivos en la carpeta seleccionada")
                        archivos_c = obtener_archivos_carpeta(sel_cid)
                        
                        if not archivos_c:
                            st.info("Esta carpeta no contiene archivos aún.")
                        else:
                            for arc in archivos_c:
                                arc_id, arc_nom, arc_mime, arc_tam, arc_fsub, arc_usr = arc
                                size_kb = round(arc_tam / 1024, 1) if arc_tam else 0
                                
                                ca1, ca2, ca3 = st.columns([3, 1.5, 1])
                                with ca1:
                                    st.write(f"📄 **{arc_nom}**\n_{size_kb} KB | Subido el {arc_fsub} por {arc_usr}_")
                                with ca2:
                                    # Botón de descarga
                                    arc_data = obtener_contenido_archivo(arc_id)
                                    if arc_data and arc_data[2]:
                                        st.download_button(
                                            label="⬇️ Descargar",
                                            data=arc_data[2],
                                            file_name=arc_nom,
                                            mime=arc_mime or "application/octet-stream",
                                            key=f"dl_arc_{arc_id}"
                                        )
                                with ca3:
                                    if st.button("🗑️", key=f"del_arc_{arc_id}", help="Eliminar archivo"):
                                        eliminar_archivo_repositorio(arc_id)
                                        st.warning("Archivo eliminado.")
                                        st.rerun()
                                st.divider()
                                
                        st.divider()
                        st.markdown("##### ⬆️ Subir Nuevo Archivo a esta Carpeta")
                        with st.form("form_upload_archivo"):
                            f_up = st.file_uploader("Seleccione el archivo a cargar", type=None)
                            btn_g_up = st.form_submit_button("⬆️ Subir al Repositorio")
                            
                            if btn_g_up:
                                if f_up is not None:
                                    bytes_data = f_up.getvalue()
                                    guardar_archivo_repositorio(
                                        sel_cid, f_up.name, f_up.type, len(bytes_data),
                                        st.session_state["username"], bytes_data
                                    )
                                    st.success(f"🎉 ¡Archivo '{f_up.name}' subido exitosamente!")
                                    st.rerun()
                                else:
                                    st.error("⚠️ Seleccione un archivo antes de presionar subir.")

            # --- SUB-TAB 2: ADMINISTRACIÓN DE CARPETAS CON BORRADO ESPECIAL ---
            with tab_rep2:
                st.subheader("⚙️ Gestión y Estructura de Carpetas")
                
                ac1, ac2 = st.columns(2)
                with ac1:
                    st.markdown("##### ➕ Crear Nueva Carpeta / Subcarpeta")
                    carpetas_flat = obtener_todas_carpetas_flat(padre_id=None)
                    c_opts = {"📁 [Raíz Principal]": None}
                    for cf in carpetas_flat: c_opts[cf[1]] = cf[0]
                    
                    with st.form("form_crear_carpeta"):
                        padre_sel = st.selectbox("Carpeta Padre (Ubicación):", list(c_opts.keys()))
                        nom_carpeta_nueva = st.text_input("Nombre de la nueva carpeta *")
                        btn_c_fold = st.form_submit_button("📁 Crear Carpeta")
                        
                        if btn_c_fold:
                            if nom_carpeta_nueva.strip():
                                crear_carpeta_repositorio(nom_carpeta_nueva, c_opts[padre_sel])
                                st.success("✅ ¡Carpeta creada exitosamente!")
                                st.rerun()
                            else:
                                st.error("⚠️ Ingrese el nombre de la carpeta.")

                with ac2:
                    st.markdown("##### ✏️ Renombrar o 🗑️ Eliminar Carpeta")
                    carpetas_flat = obtener_todas_carpetas_flat(padre_id=None)
                    
                    if not carpetas_flat:
                        st.info("No hay carpetas.")
                    else:
                        c_dict_m = {cf[1]: cf[0] for cf in carpetas_flat}
                        sel_c_mod = st.selectbox("Seleccione carpeta a gestionar:", list(c_dict_m.keys()), key="sel_c_mod")
                        cid_mod = c_dict_m[sel_c_mod]
                        
                        st.markdown("---")
                        # 1. Renombrar
                        renom_val = st.text_input("Nuevo nombre para esta carpeta:", value=sel_c_mod.replace("📁 ", "").strip())
                        if st.button("✏️ Guardar Nuevo Nombre"):
                            if renom_val.strip():
                                renombrar_carpeta_repositorio(cid_mod, renom_val)
                                st.success("✅ Carpeta renombrada.")
                                st.rerun()
                                
                        st.markdown("---")
                        # 2. Eliminar con Confirmación Especial si tiene contenido
                        st.markdown("##### 🗑️ Eliminar Carpeta")
                        n_arc, n_sub = contar_contenido_carpeta(cid_mod)
                        
                        if n_arc > 0 or n_sub > 0:
                            st.error(f"🚨 **Advertencia de Seguridad**: Esta carpeta contiene **{n_arc} archivo(s)** y **{n_sub} subcarpeta(s)**.")
                            confirm_check = st.checkbox("⚠️ Confirmo que deseo eliminar permanentemente esta carpeta y TODO su contenido.", key=f"chk_del_{cid_mod}")
                            if confirm_check:
                                if st.button("🔴 ELIMINAR CARPETA Y TODO SU CONTENIDO", key=f"btn_del_fold_{cid_mod}"):
                                    eliminar_carpeta_recursivo(cid_mod)
                                    st.warning("Carpeta y su contenido eliminados permanentemente.")
                                    st.rerun()
                        else:
                            st.info("🟢 Esta carpeta está vacía.")
                            if st.button("🗑️ Eliminar Carpeta Vacía", key=f"btn_del_empty_{cid_mod}"):
                                eliminar_carpeta_recursivo(cid_mod)
                                st.success("Carpeta vacía eliminada.")
                                st.rerun()

        # ==========================================
        # 10. 🔍 BUSCAR Y LISTAR PACIENTES
        # ==========================================
        elif menu == "🔍 Buscar y Listar Pacientes":
            st.title("🔍 Buscador General de Pacientes")
            st.caption("Consulta rápida de expedientes, estatus y documentos PDF")
            
            query = st.text_input("🔍 Ingrese Nombre, Folio o Expediente del Residente:").strip().lower()
            p_todos = listar_pacientes_registro(solo_activos=False)
            
            if not p_todos:
                st.info("No hay residentes registrados.")
            else:
                res_filtrados = []
                for p in p_todos:
                    if not query or query in p[0].lower() or (p[1] and query in p[1].lower()) or query in p[2].lower():
                        res_filtrados.append(p)
                        
                st.subheader(f"Resultados encontrados: {len(res_filtrados)}")
                for pf in res_filtrados:
                    st_label = "🟢 ACTIVO" if pf[6]=='A' else "🔴 INACTIVO"
                    with st.expander(f"👤 {pf[2]} | Folio: **{pf[0]}** | Exp: **{pf[1] or 'N/A'}** ({st_label})"):
                        st.write(f"**Fecha de Ingreso:** {pf[3]} | **Etapa Actual:** {pf[4]}")
                        
                        # Botones para consultar/descargar entrevista o ficha
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            f_d, _, _ = obtener_ficha_ingreso(pf[0])
                            if f_d:
                                st.success("✓ Ficha de Ingreso Registrada")
                        with col_b2:
                            e_d, _, _, _ = obtener_entrevista(pf[0])
                            if e_d:
                                st.success("✓ Entrevista Inicial Registrada")

        # ==========================================
        # 11. ⚙️ CONFIGURACIÓN Y SEGURIDAD
        # ==========================================
        elif menu == "⚙️ Configuración y Seguridad":
            st.title("⚙️ Configuración y Seguridad del Sistema")
            st.caption("Cambio de contraseña y administración de cuentas de usuario")
            
            tab_s1, tab_s2 = st.tabs(["🔒 Cambiar mi Contraseña", "👥 Usuarios del Sistema"])
            
            with tab_s1:
                st.subheader("Actualizar mi Contraseña")
                with st.form("form_change_pass"):
                    p_act = st.text_input("Contraseña Actual", type="password")
                    p_nueva = st.text_input("Nueva Contraseña", type="password")
                    p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                    btn_pass = st.form_submit_button("🔒 Actualizar Contraseña")
                    
                    if btn_pass:
                        if p_nueva != p_conf:
                            st.error("Las nuevas contraseñas no coinciden.")
                        else:
                            user_ok = verificar_login(st.session_state["username"], p_act)
                            if user_ok:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                          (hash_pass(p_nueva), st.session_state["username"]))
                                conn.commit()
                                conn.close()
                                st.success("✅ ¡Contraseña actualizada con éxito!")
                            else:
                                st.error("La contraseña actual es incorrecta.")

            with tab_s2:
                st.subheader("Cuentas de Usuario Registradas")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo FROM usuarios")
                u_list = c.fetchall()
                conn.close()
                
                df_u = [{"ID": u[0], "Usuario": u[1], "Nombre Completo": u[2]} for u in u_list]
                st.dataframe(df_u, use_container_width=True)

        # ==========================================
        # 12. 📦 RESPALDO Y RESTAURACIÓN
        # ==========================================
        elif menu == "📦 Respaldo y Restauración":
            st.title("📦 Copias de Seguridad y Restauración de Base de Datos")
            st.caption("Resguardo periódico de información clínica y expedientes digitales")
            
            tab_bk1, tab_bk2 = st.tabs(["⬇️ Copia de Seguridad", "⬆️ Restaurar Base de Datos"])
            
            with tab_bk1:
                st.subheader("Descargar Copia de Seguridad de la Base de Datos")
                st.info("Descargue periódicamente este archivo para conservar un respaldo íntegro de todos los pacientes, fichas, medicamentos y documentos en su computadora.")
                
                if os.path.exists(DB_FILE):
                    with open(DB_FILE, "rb") as f_db:
                        st.download_button(
                            label="📦 Descargar Archivo 'sistema_pacientes.db'",
                            data=f_db,
                            file_name=f"Respaldo_Sawabona_{date.today().strftime('%Y%m%d')}.db",
                            mime="application/x-sqlite3",
                            use_container_width=True
                        )

            with tab_bk2:
                st.subheader("Restaurar Base de Datos desde un Archivo de Respaldo")
                st.warning("⚠️ **Atención**: La restauración reemplazará la base de datos actual con la del archivo seleccionado.")
                
                file_upload = st.file_uploader("Cargue un archivo '.db' previamente descargado:", type=["db", "sqlite", "sqlite3"])
                if file_upload is not None:
                    if st.button("⚠️ RESTAURAR BASE DE DATOS AHORA", use_container_width=True):
                        with open(DB_FILE, "wb") as f_out:
                            f_out.write(file_upload.getbuffer())
                            
                        init_db() # Garantiza creación de tablas en la DB restaurada
                        st.success("🎉 ¡Base de datos restaurada exitosamente!")
                        st.rerun()

if __name__ == "__main__":
    main()

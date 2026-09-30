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
    try:
        c.execute("PRAGMA table_info(usuarios)")
        cols = [col[1] for col in c.fetchall()]
        if "rol" not in cols:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
        if "estatus" not in cols:
            c.execute("ALTER TABLE usuarios ADD COLUMN estatus TEXT DEFAULT 'A'")
    except Exception:
        pass
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
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            fecha_registro TEXT
        )
    ''')
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')
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
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'A'))
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
    try:
        c.execute('SELECT username, nombre_completo, rol, estatus FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        row = c.fetchone()
        if row:
            uname, ufull, urol, uest = row
            urol = urol if urol else 'Administrador'
            uest = uest if uest else 'A'
            conn.close()
            return (uname, ufull, urol, uest)
    except Exception:
        c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
                  (username, hash_pass(password)))
        row = c.fetchone()
        if row:
            conn.close()
            return (row[0], row[1], 'Administrador', 'A')
    conn.close()
    return None

def obtener_usuarios_sistema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('SELECT id, username, nombre_completo, rol, estatus FROM usuarios ORDER BY username')
        rows = c.fetchall()
        result = []
        for r in rows:
            uid, uname, ufull, urol, uest = r
            result.append((uid, uname, ufull, urol if urol else 'Administrador', uest if uest else 'A'))
        conn.close()
        return result
    except Exception:
        c.execute('SELECT id, username, nombre_completo FROM usuarios ORDER BY username')
        rows = c.fetchall()
        result = [(r[0], r[1], r[2], 'Administrador', 'A') for r in rows]
        conn.close()
        return result

def guardar_usuario_sistema(username, password, nombre_completo, rol, estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
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
                return False, "La contraseña es obligatoria para nuevos usuarios."
            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estatus) VALUES (?, ?, ?, ?, ?)',
                      (username, hash_pass(password), nombre_completo, rol, estatus))
        conn.commit()
        conn.close()
        return True, "Usuario guardado exitosamente."
    except Exception as e:
        conn.close()
        return False, str(e)

def cambiar_estatus_usuario_sistema(username, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('UPDATE usuarios SET estatus = ? WHERE username = ?', (nuevo_estatus, username))
        conn.commit()
    except Exception:
        pass
    conn.close()

def eliminar_usuario_sistema(username):
    if username == "admin":
        return False, "No se puede eliminar el usuario administrador principal ('admin')."
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    return True, "Usuario eliminado."

# --- FUNCIONES DE PACIENTES ---
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

def guardar_paciente(paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo_usr, etapa_act, f_ini_etapa, usr_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ing = f_ingreso.strftime("%Y-%m-%d") if isinstance(f_ingreso, (date, datetime)) else str(f_ingreso)
    f_nac_str = f_nac.strftime("%Y-%m-%d") if isinstance(f_nac, (date, datetime)) else str(f_nac)
    f_ini_str = f_ini_etapa.strftime("%Y-%m-%d") if isinstance(f_ini_etapa, (date, datetime)) else str(f_ini_etapa)
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes SET 
                nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?,
                fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre, f_ing, f_nac_str, sexo, estatus, tipo_usr, etapa_act, f_ini_str, f_now, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (
                paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo,
                estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, usuario_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre, f_ing, f_nac_str, sexo, estatus, tipo_usr, etapa_act, f_ini_str, f_now, usr_reg))
    conn.commit()
    conn.close()

def listar_pacientes_completos(solo_activos=False, solo_pacientes=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE 1=1'
    params = []
    if solo_activos:
        query += " AND estatus = 'A'"
    if solo_pacientes:
        query += " AND tipo_usuario = 'Paciente'"
    query += " ORDER BY nombre_completo ASC"
    c.execute(query, params)
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
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = date.today().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (etapa_destino, f_hoy, f_now, paciente_id))
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_origen, etapa_destino, f_now, usr_autoriza))
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_suelta_hermano = NULL WHERE paciente_id = ?', (hermano_id, paciente_id))
    conn.commit()
    conn.close()

def marcar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_hoy = date.today().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (f_hoy, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE FARMACIA Y MEDICAMENTOS ---
def listar_catalogo_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, presentacion, concentracion FROM catalogo_medicamentos ORDER BY nombre ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_medicamento(nombre, presentacion, concentracion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d")
    try:
        c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
                  (nombre.strip(), presentacion.strip(), concentracion.strip(), f_now))
        conn.commit()
        conn.close()
        return True, "Medicamento agregado al catálogo."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "El medicamento ya existe en el catálogo."

def eliminar_catalogo_medicamento(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

def guardar_medicamentos_paciente(paciente_id, meds_json, observaciones, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                  (json.dumps(meds_json, ensure_ascii=False), observaciones, f_now, usr, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, usuario_registro) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, json.dumps(meds_json, ensure_ascii=False), observaciones, f_now, usr))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1]
    return [], ""

def registrar_entrega_meds(paciente_id, detalle_json, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, f_now, usr, json.dumps(detalle_json, ensure_ascii=False)))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa, fecha_g, facilitador, datos_json, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_grp = fecha_g.strftime("%Y-%m-%d") if isinstance(fecha_g, (date, datetime)) else str(fecha_g)
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa, f_grp, facilitador, json.dumps(datos_json, ensure_ascii=False), f_now, usr))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?',
              (paciente_id, etapa, tipo_grupo))
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

# --- FUNCIONES DE REQUISITOS POR ETAPA ---
def listar_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_requisito_etapa(etapa, requisito, es_grupo=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', (etapa, requisito, es_grupo))
    conn.commit()
    conn.close()

def eliminar_requisito_etapa(req_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (req_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE REPOSITORIO DE DOCUMENTOS ---
def listar_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "Todas":
        c.execute('SELECT id, carpeta, nombre_archivo, tipo_archivo, descripcion, tamano_bytes, fecha_subida, subido_por FROM repositorio_documentos WHERE carpeta = ? ORDER BY fecha_subida DESC', (carpeta_filtro,))
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, tipo_archivo, descripcion, tamano_bytes, fecha_subida, subido_por FROM repositorio_documentos ORDER BY fecha_subida DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_documento_repositorio(carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_bytes, subido_por):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tam = len(contenido_bytes)
    c.execute('''
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_blob, tamano_bytes, fecha_subida, subido_por)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_bytes, tam, f_now, subido_por))
    conn.commit()
    conn.close()

def obtener_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT nombre_archivo, tipo_archivo, contenido_blob FROM repositorio_documentos WHERE id = ?', (doc_id,))
    row = c.fetchone()
    conn.close()
    return row

def eliminar_documento_repositorio(doc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- CLASE DE REPORTE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "Sawabona Shikoba - Comunidad Terapéutica", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 5, "Sistema Integral de Control y Seguimiento Clínico", align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, 24, 200, 24)
        self.ln(6)

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
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE ENTREVISTA INICIAL - {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresion: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    for sec_title, fields in datos.items():
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(pdf.epw, 7, f"--- {limpiar_texto(sec_title).upper()} ---", border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for k, v in fields.items():
            txt_line = f"{limpiar_texto(k)}: {limpiar_texto(str(v))}"
            pdf.multi_cell(pdf.epw, 5, txt_line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf_filename = f"Entrevista_{paciente_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_grupos_paciente(p_id, p_nombre, grupos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE GRUPOS TERAPEUTICOS - {limpiar_texto(p_nombre)} ({p_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresion: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    if not grupos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay sesiones de grupos registradas para este paciente.", align="C")
    else:
        for g in grupos:
            gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
            datos = json.loads(djson)
            mod_str = datos.get("modalidad", "Normal")
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"GRUPO: {limpiar_texto(tgrp)} ({mod_str}) | Etapa: {etapa} | Fecha: {fgrp} | Facilitador: {limpiar_texto(fac)}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            if tgrp in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                pdf.multi_cell(pdf.epw, 5, f"Compartimiento: {limpiar_texto(datos.get('compartimiento', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(datos.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(datos.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(pdf.epw, 5, f"Logros: {limpiar_texto(datos.get('logros', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Dificultades: {limpiar_texto(datos.get('dificultades', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(datos.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(datos.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
    pdf_filename = f"Expediente_Grupos_{p_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
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
                        st.success(f"¡Bienvenido, {ufull} ({urol})!")
                        st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario Staff**: {st.session_state['nombre_completo']}")
    st.sidebar.caption(f"🏷️ Rol: **{st.session_state['rol']}**")
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
        "⚙️ Configuración y Seguridad"
    ]
    menu = st.sidebar.radio("Navegación del Sistema", menu_opciones)
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes y Servidores")
        st.caption("Alta de nuevos usuarios residentes o servidores en la comunidad terapéutica")
        modo_usr = st.radio("Acción a realizar:", ["🆕 Registrar Nuevo Usuario", "✏️ Editar Usuario Existente"], horizontal=True)
        edit_p_id = None
        p_data = None
        if modo_usr == "✏️ Editar Usuario Existente":
            pacientes_todos = listar_pacientes_completos(solo_activos=False)
            if not pacientes_todos:
                st.info("No hay usuarios registrados.")
            else:
                dict_p = {f"{p[1]} ({p[0]}) - Etapa: {p[7]} [{ 'Activo' if p[5]=='A' else 'Inactivo' }]": p[0] for p in pacientes_todos}
                sel_p_str = st.selectbox("🔑 Selecciona el Paciente / Servidor a Editar", list(dict_p.keys()))
                edit_p_id = dict_p[sel_p_str]
                p_data = obtener_paciente(edit_p_id)
        with st.form("form_registro_paciente"):
            st.subheader("Datos Basales del Usuario")
            c1, c2, c3 = st.columns(3)
            with c1:
                folio_val = edit_p_id if edit_p_id else generar_siguiente_folio()
                f_id = st.text_input("Folio de Identificación *", value=folio_val, disabled=True)
                nombre_val = p_data[1] if p_data else ""
                f_nom = st.text_input("Nombre Completo *", value=nombre_val)
            with c2:
                tipo_val = ["Paciente", "Servidor"]
                idx_tipo = 0
                if p_data and p_data[6] in tipo_val:
                    idx_tipo = tipo_val.index(p_data[6])
                f_tipo = st.selectbox("Tipo de Usuario *", tipo_val, index=idx_tipo)
                sexo_val = ["Masculino", "Femenino"]
                idx_sexo = 0
                if p_data and p_data[4] in sexo_val:
                    idx_sexo = sexo_val.index(p_data[4])
                f_sexo = st.selectbox("Sexo *", sexo_val, index=idx_sexo)
            with c3:
                f_ing_val = datetime.strptime(p_data[2], "%Y-%m-%d").date() if p_data and p_data[2] else date.today()
                f_ingreso = st.date_input("Fecha de Ingreso *", value=f_ing_val)
                f_nac_val = datetime.strptime(p_data[3], "%Y-%m-%d").date() if p_data and p_data[3] else date(2000, 1, 1)
                f_nacimiento = st.date_input("Fecha de Nacimiento *", value=f_nac_val)
            st.divider()
            c4, c5 = st.columns(2)
            with c4:
                etapas_list = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_etapa = 0
                if p_data and p_data[7] in etapas_list:
                    idx_etapa = etapas_list.index(p_data[7])
                f_etapa = st.selectbox("Etapa Inicial / Actual *", etapas_list, index=idx_etapa)
            with c5:
                estatus_opts = ["A - Activo", "I - Inactivo / Egreso"]
                idx_est = 0
                if p_data and p_data[5] == "I":
                    idx_est = 1
                f_est_sel = st.selectbox("Estatus *", estatus_opts, index=idx_est)
                f_estatus = "A" if f_est_sel.startswith("A") else "I"
            f_ini_etapa_val = datetime.strptime(p_data[8], "%Y-%m-%d").date() if p_data and p_data[8] else f_ingreso
            f_ini_etapa = st.date_input("Fecha de Inicio de la Etapa Actual *", value=f_ini_etapa_val)
            btn_guardar_p = st.form_submit_button("💾 Guardar Datos del Usuario", use_container_width=True)
            if btn_guardar_p:
                if not f_nom.strip():
                    st.error("⚠️ El Nombre Completo es un campo obligatorio.")
                else:
                    dup = verificar_duplicado_nombre(f_nom, edit_p_id)
                    if dup:
                        d_id, d_nom, d_est = dup
                        st.error(f"⚠️ Ya existe un usuario registrado con el nombre **{d_nom}** (Folio: `{d_id}`). Por favor verifica.")
                    else:
                        guardar_paciente(folio_val, f_nom.strip(), f_ingreso, f_nacimiento, f_sexo, f_estatus, f_tipo, f_etapa, f_ini_etapa, st.session_state["username"])
                        st.toast("🎉 ¡Usuario guardado exitosamente!")
                        st.success(f"✅ ¡Se han registrado los datos de **{f_nom}** (`{folio_val}`) exitosamente!")
                        st.balloons()
                        st.rerun()
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📝 Entrevista Inicial de Consejería")
        st.caption("Captura de evaluación socio-demográfica, consumo y tamizajes clínicos")
        pacientes_activos = listar_pacientes_completos(solo_activos=True, solo_pacientes=True)
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados para realizar entrevista.")
        else:
            dict_ent = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1]) for p in pacientes_activos}
            sel_ent_str = st.selectbox("🔑 Selecciona el Paciente", list(dict_ent.keys()), key="sel_ent_pac")
            p_id_e, p_nom_e = dict_ent[sel_ent_str]
            st.subheader(f"Formulario de Entrevista: {p_nom_e} ({p_id_e})")
            with st.form("form_entrevista_completa"):
                t_sec1, t_sec2, t_sec3 = st.tabs(["📊 Datos Sociodemográficos", "🍷 Historial de Consumo", "📋 Tamizajes Clínicos"])
                with t_sec1:
                    e_ocupacion = st.text_input("Ocupación previa")
                    e_escolaridad = st.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria", "Licenciatura / Técnica", "Ninguna"])
                    e_estado_civil = st.selectbox("Estado Civil", ["Soltero/a", "Casado/a", "Unión Libre", "Divorciado/a", "Viudo/a"])
                    e_vivienda = st.text_input("Con quién vive actualmente")
                    e_contacto_emerg = st.text_input("Nombre y Teléfono de Contacto de Emergencia")
                with t_sec2:
                    e_sustancia_princ = st.text_input("Sustancia de Mayor Impacto / Principal")
                    e_edad_inicio = st.number_input("Edad de Inicio de Consumo", min_value=5, max_value=90, value=15)
                    e_frecuencia = st.selectbox("Frecuencia de Consumo", ["Diario", "3-5 veces por semana", "Fines de semana", "Ocasional / Binge"])
                    e_intentos_previos = st.number_input("Número de Tratamientos Previos", min_value=0, max_value=50, value=0)
                    e_motivacion = st.text_area("Motivación principal para iniciar tratamiento")
                with t_sec3:
                    st.write("Score / Puntaje de Pruebas de Tamizaje Aplicadas:")
                    c_t1, c_t2 = st.columns(2)
                    with c_t1:
                        score_cad = st.number_input("CAD (Cuestionario Criterios Adicción)", min_value=0, max_value=20, value=0)
                        score_audit = st.number_input("AUDIT (Alcoholismo)", min_value=0, max_value=40, value=0)
                        score_beda = st.number_input("BEDA (Breve Escala Dependencia Alcohol)", min_value=0, max_value=45, value=0)
                    with c_t2:
                        score_fagerstrom = st.number_input("FAGERSTROM (Nicotina)", min_value=0, max_value=10, value=0)
                        score_beck_ans = st.number_input("Beck Ansiedad", min_value=0, max_value=63, value=0)
                        score_beck_dep = st.number_input("Beck Depresión", min_value=0, max_value=63, value=0)
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ent:
                    datos_ent = {
                        "Sociodemograficos": {
                            "Ocupación": e_ocupacion, "Escolaridad": e_escolaridad,
                            "Estado Civil": e_estado_civil, "Vivienda": e_vivienda,
                            "Contacto Emergencia": e_contacto_emerg
                        },
                        "Historial_Consumo": {
                            "Sustancia Principal": e_sustancia_princ, "Edad Inicio": e_edad_inicio,
                            "Frecuencia": e_frecuencia, "Tratamientos Previos": e_intentos_previos,
                            "Motivación": e_motivacion
                        },
                        "Tamizajes": {
                            "CAD": score_cad, "AUDIT": score_audit, "BEDA": score_beda,
                            "FAGERSTROM": score_fagerstrom, "Beck Ansiedad": score_beck_ans, "Beck Depresión": score_beck_dep
                        }
                    }
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (p_id_e,))
                    if c.fetchone():
                        c.execute('UPDATE entrevistas SET datos_json = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                                  (json.dumps(datos_ent, ensure_ascii=False), f_now, st.session_state["username"], p_id_e))
                    else:
                        c.execute('INSERT INTO entrevistas (paciente_id, datos_json, fecha_registro, usuario_registro) VALUES (?, ?, ?, ?)',
                                  (p_id_e, json.dumps(datos_ent, ensure_ascii=False), f_now, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.toast("🎉 ¡Entrevista guardada exitosamente!")
                    st.success(f"✅ ¡Entrevista registrada para **{p_nom_e}** (`{p_id_e}`)!")
                    st.balloons()
                    st.rerun()
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio General de Pacientes y Expedientes")
        st.caption("Consulta de expedientes, descarga de entrevistas en PDF y filtros de búsqueda")
        filtro_nom = st.text_input("🔎 Buscar por Nombre o Folio...")
        filtro_etapa = st.selectbox("Filtrar por Etapa", ["Todas", "ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
        pacientes_list = listar_pacientes_completos(solo_activos=False)
        if filtro_nom:
            pacientes_list = [p for p in pacientes_list if filtro_nom.lower() in p[1].lower() or filtro_nom.lower() in p[0].lower()]
        if filtro_etapa != "Todas":
            pacientes_list = [p for p in pacientes_list if p[7] == filtro_etapa]
        st.write(f"Se encontraron **{len(pacientes_list)}** registros:")
        for p in pacientes_list:
            pid, pnom, fing, fnac, psex, pest, ptipo, petapa, fini, hmay, fsuelta = p
            st_badge = "🟢 Activo" if pest == 'A' else "🔴 Inactivo"
            with st.expander(f"👤 **{pnom}** (`{pid}`) | Tipo: {ptipo} | Etapa: **{petapa}** | {st_badge}"):
                c_info1, c_info2 = st.columns(2)
                with c_info1:
                    st.write(f"**Fecha Ingreso:** {fing}")
                    st.write(f"**Fecha Nacimiento:** {fnac}")
                    st.write(f"**Sexo:** {psex}")
                with c_info2:
                    st.write(f"**Fecha Inicio Etapa:** {fini}")
                    if hmay:
                        hm_data = obtener_paciente(hmay)
                        h_nom = hm_data[1] if hm_data else hmay
                        st.write(f"**Hermano Mayor:** {h_nom} ({hmay})")
                        if fsuelta:
                            st.write(f"**Fecha Suelta Hermano:** {fsuelta}")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (pid,))
                row_ent = c.fetchone()
                conn.close()
                if row_ent:
                    d_ent = json.loads(row_ent[0])
                    pdf_path = generar_pdf_entrevista(pid, d_ent)
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="🖨️ Descargar Entrevista Inicial en PDF",
                            data=f,
                            file_name=pdf_path,
                            mime="application/pdf",
                            key=f"dl_ent_{pid}"
                        )
                else:
                    st.info("Sin entrevista inicial capturada.")
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Promoción de Residentes")
        st.caption("Verificación de requisitos por etapa, asignación de Hermano Mayor y promoción")
        pacientes_activos = listar_pacientes_completos(solo_activos=True, solo_pacientes=True)
        if not pacientes_activos:
            st.info("No hay pacientes activos.")
        else:
            dict_et = {f"{p[1]} ({p[0]}) - Etapa Actual: {p[7]}": p for p in pacientes_activos}
            sel_et_str = st.selectbox("🔑 Selecciona el Paciente", list(dict_et.keys()), key="sel_etapa_pac")
            p_curr = dict_et[sel_et_str]
            pid_e, pnom_e, fing_e, fnac_e, psex_e, pest_e, ptipo_e, petapa_e, fini_e, hmay_e, fsuelta_e = p_curr
            tab_et1, tab_et2, tab_et3 = st.tabs(["📋 Requisitos y Promoción", "🤝 Hermano Mayor / Menor", "📜 Historial de Etapas"])
            with tab_et1:
                st.subheader(f"Etapa Actual: **{petapa_e}** (Desde: {fini_e})")
                reqs = listar_requisitos_etapa(petapa_e)
                st.write("Requisitos para avanzar de etapa:")
                if not reqs:
                    st.info("No hay requisitos configurados para esta etapa.")
                else:
                    for rid, rtxt, esg in reqs:
                        if esg == 1:
                            if "Aquí y Ahora" in rtxt:
                                cnt = contar_grupos_paciente_etapa(pid_e, petapa_e, "Aquí y Ahora")
                            elif "Terapia de Grupo" in rtxt:
                                cnt = contar_grupos_paciente_etapa(pid_e, petapa_e, "Terapia de Grupo")
                            elif "Feedbacks" in rtxt or "Feedback" in rtxt:
                                cnt = contar_grupos_paciente_etapa(pid_e, petapa_e, "Feedback")
                            else:
                                cnt = 0
                            st.write(f"• **{rtxt}**: Registrados = **{cnt}**")
                        else:
                            st.write(f"• {rtxt}")
                st.divider()
                st.subheader("Promover a Siguiente Etapa")
                etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                if petapa_e in etapas_orden and etapas_orden.index(petapa_e) < len(etapas_orden) - 1:
                    next_etapa = etapas_orden[etapas_orden.index(petapa_e) + 1]
                    if st.button(f"🚀 Promover a {next_etapa}", use_container_width=True):
                        promover_etapa(pid_e, petapa_e, next_etapa, st.session_state["username"])
                        st.toast(f"🎉 ¡Paciente promovido a {next_etapa}!")
                        st.success(f"✅ ¡**{pnom_e}** ha sido promovido a **{next_etapa}**!")
                        st.balloons()
                        st.rerun()
                else:
                    st.success("🎉 El paciente ha alcanzado la etapa máxima (SERVICIO SOCIAL).")
            with tab_et2:
                st.subheader("Asignación de Hermano Mayor")
                if hmay_e:
                    hm_p = obtener_paciente(hmay_e)
                    h_name = hm_p[1] if hm_p else hmay_e
                    st.success(f"🤝 Hermano Mayor Asignado: **{h_name}** (`{hmay_e}`)")
                    if fsuelta_e:
                        st.info(f"📅 Fecha de Suelta: **{fsuelta_e}**")
                    else:
                        if st.button("🕊️ Registrar Suelta de Hermano Mayor"):
                            marcar_suelta_hermano(pid_e)
                            st.toast("🕊️ Suelta de hermano registrada.")
                            st.rerun()
                else:
                    posibles_hm = [p for p in pacientes_activos if p[0] != pid_e]
                    if not posibles_hm:
                        st.info("No hay otros pacientes para asignar como Hermano Mayor.")
                    else:
                        dict_hm = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in posibles_hm}
                        sel_hm_str = st.selectbox("Selecciona Hermano Mayor", list(dict_hm.keys()))
                        if st.button("🤝 Asignar Hermano Mayor"):
                            asignar_hermano_mayor(pid_e, dict_hm[sel_hm_str])
                            st.toast("🤝 Hermano Mayor asignado.")
                            st.rerun()
            with tab_et3:
                st.subheader("Historial de Cambios de Etapa")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza FROM historial_etapas WHERE paciente_id = ? ORDER BY id DESC', (pid_e,))
                h_rows = c.fetchall()
                conn.close()
                if not h_rows:
                    st.info("No hay historial de promovimiento.")
                else:
                    for ho, hd, fc, ua in h_rows:
                        st.write(f"• **{ho}** ➡️ **{hd}** | Fecha: {fc} | Autorizó: {ua}")
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Módulo para capturar, modificar, eliminar y consultar sesiones de Terapia de Grupo, Aquí y Ahora, Feedback y Confronto Especial")
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar / Editar Sesión de Grupo", "📜 Historial, Conteo y PDF"])
        with tab_reg_g:
            pacientes_activos = listar_pacientes_completos(solo_activos=True)
            if not pacientes_activos:
                st.warning("No hay usuarios activos registrados.")
            else:
                dict_pac_g = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1], p[7]) for p in pacientes_activos}
                sel_pac_g = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_g.keys()), key="sel_grp_pac")
                p_id_g, p_nombre_g, p_etapa_g = dict_pac_g[sel_pac_g]
                modo_grp = st.radio("Acción de Grupo:", ["🆕 Registrar Nueva Sesión", "✏️ Modificar Sesión Existente"], horizontal=True)
                edit_gid = None
                grp_edit_data = None
                if modo_grp == "✏️ Modificar Sesión Existente":
                    grupos_existentes = listar_grupos_paciente(p_id_g)
                    if not grupos_existentes:
                        st.info("Este paciente no tiene sesiones registradas para editar.")
                    else:
                        dict_ge = {f"{g[1]} - Fecha: {g[3]} | Facilitador: {g[4]} (ID: {g[0]})": g for g in grupos_existentes}
                        sel_ge_str = st.selectbox("Selecciona la Sesión de Grupo a Editar", list(dict_ge.keys()))
                        grp_edit_data = dict_ge[sel_ge_str]
                        edit_gid = grp_edit_data[0]
                tipo_grupo_opts = ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Confronto Especial"]
                idx_tg = 0
                if grp_edit_data and grp_edit_data[1] in tipo_grupo_opts:
                    idx_tg = tipo_grupo_opts.index(grp_edit_data[1])
                tipo_grupo = st.selectbox("🗣️ Tipo de Grupo Terapéutico", tipo_grupo_opts, index=idx_tg)
                with st.form("form_grupo_terapeuto"):
                    st.subheader(f"Formulario: {tipo_grupo}")
                    c_g1, c_g2, c_g3 = st.columns(3)
                    with c_g1:
                        st.text_input("Usuario", value=p_nombre_g, disabled=True)
                        st.text_input("Folio", value=p_id_g, disabled=True)
                    with c_g2:
                        st.text_input("Etapa Actual del Usuario", value=p_etapa_g, disabled=True)
                        f_grp_val = datetime.strptime(grp_edit_data[3], "%Y-%m-%d").date() if grp_edit_data and grp_edit_data[3] else date.today()
                        f_grupo = st.date_input("Fecha del Grupo", value=f_grp_val)
                    with c_g3:
                        fac_val = grp_edit_data[4] if grp_edit_data else st.session_state["nombre_completo"]
                        facilitador_nombre = st.text_input("Nombre del Facilitador / Staff *", value=fac_val)
                        d_json_old = json.loads(grp_edit_data[5]) if grp_edit_data else {}
                        es_especial = st.checkbox("¿Es un grupo Especial?", value=(d_json_old.get("modalidad") == "Especial"))
                        modalidad_grupo = "Especial" if es_especial else "Normal"
                        st.caption(f"Modalidad asignada: **{modalidad_grupo}**")
                    st.divider()
                    if tipo_grupo in ["Terapia de Grupo", "Aquí y Ahora", "Confronto Especial"]:
                        comp_val = d_json_old.get("compartimiento", "")
                        obs_val = d_json_old.get("observaciones", "")
                        dev_val = d_json_old.get("devoluciones", "")
                        cmpr_val = d_json_old.get("compromiso", "")
                        compartimiento = st.text_area("Compartimiento (Texto largo) *", value=comp_val)
                        observaciones = st.text_area("Observaciones (Texto largo)", value=obs_val)
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=dev_val)
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=cmpr_val)
                        btn_label = f"💾 Guardar Modificación de {tipo_grupo}" if edit_gid else f"💾 Guardar Registro de {tipo_grupo}"
                        btn_guardar_grupo = st.form_submit_button(btn_label, use_container_width=True)
                        if btn_guardar_grupo:
                            if not facilitador_nombre or not compartimiento or not compromiso:
                                st.error("⚠️ Facilitador, Compartimiento y Compromiso son campos obligatorios.")
                            else:
                                datos_grp = {
                                    "modalidad": modalidad_grupo,
                                    "compartimiento": compartimiento,
                                    "observaciones": observaciones,
                                    "devoluciones": devoluciones,
                                    "compromiso": compromiso
                                }
                                if edit_gid:
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    f_grp_str = f_grupo.strftime("%Y-%m-%d")
                                    c.execute('UPDATE grupos_terapeutos SET tipo_grupo = ?, fecha_grupo = ?, facilitador = ?, datos_json = ? WHERE id = ?',
                                              (tipo_grupo, f_grp_str, facilitador_nombre, json.dumps(datos_grp, ensure_ascii=False), edit_gid))
                                    conn.commit()
                                    conn.close()
                                    st.toast("🎉 ¡Sesión modificada exitosamente!")
                                    st.success(f"✅ ¡Sesión de **{tipo_grupo}** actualizada!")
                                else:
                                    guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, datos_grp, st.session_state["username"])
                                    st.toast("🎉 ¡Sesión de grupo registrada!")
                                    st.success(f"✅ ¡Sesión de **{tipo_grupo}** registrada para **{p_nombre_g}**!")
                                st.balloons()
                                st.rerun()
                    else:
                        logros_val = d_json_old.get("logros", "")
                        dif_val = d_json_old.get("dificultades", "")
                        obs_val = d_json_old.get("observaciones", "")
                        dev_val = d_json_old.get("devoluciones", "")
                        cmpr_val = d_json_old.get("compromiso", "")
                        logros = st.text_area("Logros (Texto largo) *", value=logros_val)
                        dificultades = st.text_area("Dificultades (Texto largo) *", value=dif_val)
                        observaciones = st.text_area("Observaciones (Texto largo)", value=obs_val)
                        devoluciones = st.text_area("Devoluciones (Texto largo)", value=dev_val)
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *", value=cmpr_val)
                        btn_label = "💾 Guardar Modificación de Feedback" if edit_gid else "💾 Guardar Registro de Feedback"
                        btn_guardar_grupo = st.form_submit_button(btn_label, use_container_width=True)
                        if btn_guardar_grupo:
                            if not facilitador_nombre or not logros or not dificultades or not compromiso:
                                st.error("⚠️ Facilitador, Logros, Dificultades y Compromiso son campos obligatorios.")
                            else:
                                datos_grp = {
                                    "modalidad": modalidad_grupo,
                                    "logros": logros,
                                    "dificultades": dificultades,
                                    "observaciones": observaciones,
                                    "devoluciones": devoluciones,
                                    "compromiso": compromiso
                                }
                                if edit_gid:
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    f_grp_str = f_grupo.strftime("%Y-%m-%d")
                                    c.execute('UPDATE grupos_terapeutos SET tipo_grupo = ?, fecha_grupo = ?, facilitador = ?, datos_json = ? WHERE id = ?',
                                              (tipo_grupo, f_grp_str, facilitador_nombre, json.dumps(datos_grp, ensure_ascii=False), edit_gid))
                                    conn.commit()
                                    conn.close()
                                    st.toast("🎉 ¡Sesión de Feedback modificada!")
                                    st.success("✅ ¡Sesión de **Feedback** actualizada!")
                                else:
                                    guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, datos_grp, st.session_state["username"])
                                    st.toast("🎉 ¡Sesión de Feedback registrada!")
                                    st.success(f"✅ ¡Sesión de **Feedback** registrada para **{p_nombre_g}**!")
                                st.balloons()
                                st.rerun()
        with tab_hist_g:
            pacientes_todos = listar_pacientes_completos(solo_activos=False)
            if not pacientes_todos:
                st.info("No hay usuarios registrados.")
            else:
                dict_hist = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_todos}
                sel_h = st.selectbox("🔑 Selecciona el Paciente para Ver Expediente de Grupos", list(dict_hist.keys()))
                p_id_h, p_nom_h = dict_hist[sel_h]
                grupos_list = listar_grupos_paciente(p_id_h)
                pdf_grp = generar_pdf_grupos_paciente(p_id_h, p_nom_h, grupos_list)
                with open(pdf_grp, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Expediente de Grupos en PDF",
                        data=f,
                        file_name=pdf_grp,
                        mime="application/pdf",
                        key=f"pdf_grp_{p_id_h}"
                    )
                st.divider()
                st.subheader("📊 Conteo de Grupos por Etapa")
                etapas_c = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                c_cols = st.columns(len(etapas_c))
                for idx, et_item in enumerate(etapas_c):
                    with c_cols[idx]:
                        st.markdown(f"**{et_item}**")
                        c_aha = contar_grupos_paciente_etapa(p_id_h, et_item, "Aquí y Ahora")
                        c_tg = contar_grupos_paciente_etapa(p_id_h, et_item, "Terapia de Grupo")
                        c_fb = contar_grupos_paciente_etapa(p_id_h, et_item, "Feedback")
                        c_ce = contar_grupos_paciente_etapa(p_id_h, et_item, "Confronto Especial")
                        st.caption(f"• A&H: {c_aha}\n• TG: {c_tg}\n• FB: {c_fb}\n• CE: {c_ce}")
                st.divider()
                st.subheader("📜 Historial de Sesiones Registradas")
                if not grupos_list:
                    st.warning("Este usuario no tiene sesiones de grupo registradas.")
                else:
                    for g in grupos_list:
                        gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
                        datos = json.loads(djson)
                        mod_str = datos.get("modalidad", "Normal")
                        col_g1, col_g2 = st.columns([5, 1])
                        with col_g1:
                            with st.expander(f"🗣️ **{tgrp}** ({mod_str}) | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"):
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
                        with col_g2:
                            if st.button("🗑️ Eliminar", key=f"del_grp_{gid}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('DELETE FROM grupos_terapeutos WHERE id = ?', (gid,))
                                conn.commit()
                                conn.close()
                                st.toast("🗑️ Sesión eliminada.")
                                st.rerun()
    elif menu == "📦 Catálogo General de Medicamentos":
        st.title("📦 Catálogo Central de Medicamentos")
        st.caption("Administración de medicamentos maestros disponibles en la comunidad")
        tab_cat1, tab_cat2 = st.tabs(["📋 Catálogo de Medicamentos", "➕ Registrar Nuevo Medicamento"])
        with tab_cat1:
            cat_meds = listar_catalogo_medicamentos()
            st.write(f"Se tienen **{len(cat_meds)}** medicamentos registrados en el catálogo:")
            for m_id, m_nom, m_pres, m_conc in cat_meds:
                col_m1, col_m2 = st.columns([4, 1])
                with col_m1:
                    st.write(f"💊 **{m_nom}** | Presentación: {m_pres} | Concentración: {m_conc}")
                with col_m2:
                    if st.button("🗑️ Eliminar", key=f"del_cat_med_{m_id}"):
                        eliminar_catalogo_medicamento(m_id)
                        st.toast(f"🗑️ Medicamento {m_nom} eliminado del catálogo.")
                        st.rerun()
        with tab_cat2:
            with st.form("form_add_cat_med"):
                st.subheader("Agregar Medicamento al Catálogo Central")
                c_cm1, c_cm2, c_cm3 = st.columns(3)
                with c_cm1:
                    cm_nom = st.text_input("Nombre Comercial / Genérico *")
                with c_cm2:
                    cm_pres = st.selectbox("Presentación *", ["Tabletas", "Cápsulas", "Comprimidos", "Gotas", "Jarabe", "Inyectable", "Crema / Pomada", "Otro"])
                with c_cm3:
                    cm_conc = st.text_input("Concentración / Dosis (ej: 500 mg, 20 mg/ml) *")
                btn_cm = st.form_submit_button("➕ Guardar Medicamento en Catálogo", use_container_width=True)
                if btn_cm:
                    if not cm_nom.strip() or not cm_conc.strip():
                        st.error("⚠️ Nombre y Concentración son obligatorios.")
                    else:
                        ok_cm, msg_cm = agregar_catalogo_medicamento(cm_nom, cm_pres, cm_conc)
                        if ok_cm:
                            st.toast("🎉 Medicamento guardado en el catálogo.")
                            st.success(f"✅ ¡**{cm_nom}** agregado exitosamente!")
                            st.rerun()
                        else:
                            st.error(msg_cm)
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Prescripción e Inventario por Paciente")
        st.caption("Asignación de esquema de medicamentos, horarios y stock individual")
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        if not pacientes_activos:
            st.warning("No hay pacientes activos.")
        else:
            dict_m = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_activos}
            sel_m_str = st.selectbox("🔑 Selecciona el Paciente", list(dict_m.keys()), key="sel_med_pac")
            p_id_m, p_nom_m = dict_m[sel_m_str]
            meds_curr, obs_curr = obtener_medicamentos_paciente(p_id_m)
            cat_meds = listar_catalogo_medicamentos()
            st.subheader(f"Esquema Médico de: **{p_nom_m}** (`{p_id_m}`)")
            with st.form("form_meds_paciente"):
                st.write("Configura la dosis y existencia para este paciente:")
                num_meds = st.number_input("Número de medicamentos recetados", min_value=1, max_value=10, value=max(len(meds_curr), 1))
                meds_form_list = []
                for i in range(int(num_meds)):
                    st.markdown(f"**Medicamento #{i+1}**")
                    c_f1, c_f2, c_f3, c_f4, c_f5 = st.columns([3, 1, 1, 1, 2])
                    m_old = meds_curr[i] if i < len(meds_curr) else {}
                    with c_f1:
                        opts_cat = [f"{m[1]} ({m[2]} - {m[3]})" for m in cat_meds]
                        if not opts_cat:
                            opts_cat = ["Sin catálogo disponible"]
                        idx_m = 0
                        if m_old.get("nombre") in opts_cat:
                            idx_m = opts_cat.index(m_old.get("nombre"))
                        f_m_nom = st.selectbox(f"Medicamento #{i+1}", opts_cat, index=idx_m, key=f"m_nom_{i}")
                    with c_f2:
                        f_m_manana = st.number_input("Mañana", min_value=0.0, step=0.5, value=float(m_old.get("manana", 0)), key=f"m_man_{i}")
                    with c_f3:
                        f_m_tarde = st.number_input("Tarde", min_value=0.0, step=0.5, value=float(m_old.get("tarde", 0)), key=f"m_tar_{i}")
                    with c_f4:
                        f_m_noche = st.number_input("Noche", min_value=0.0, step=0.5, value=float(m_old.get("noche", 0)), key=f"m_noc_{i}")
                    with c_f5:
                        f_m_stock = st.number_input("Existencia / Stock", min_value=0, value=int(m_old.get("stock", 0)), key=f"m_stk_{i}")
                    meds_form_list.append({
                        "nombre": f_m_nom,
                        "manana": f_m_manana,
                        "tarde": f_m_tarde,
                        "noche": f_m_noche,
                        "stock": f_m_stock
                    })
                obs_meds = st.text_area("Observaciones Médicas / Indicaciones Especiales", value=obs_curr)
                btn_save_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                if btn_save_meds:
                    guardar_medicamentos_paciente(p_id_m, meds_form_list, obs_meds, st.session_state["username"])
                    st.toast("🎉 Esquema médico actualizado.")
                    st.success(f"✅ ¡Esquema de medicamentos guardado para **{p_nom_m}**!")
                    st.rerun()
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro y Entrega de Medicamentos")
        st.caption("Surtido diario de medicamentos y descuento automático de inventario")
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        if not pacientes_activos:
            st.warning("No hay pacientes activos.")
        else:
            dict_e = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_activos}
            sel_e_str = st.selectbox("🔑 Selecciona el Paciente a Entregar", list(dict_e.keys()), key="sel_entreg_pac")
            p_id_ent, p_nom_ent = dict_e[sel_e_str]
            meds_curr, obs_curr = obtener_medicamentos_paciente(p_id_ent)
            if not meds_curr:
                st.warning("Este paciente no tiene prescripción médica registrada.")
            else:
                st.subheader(f"Surtido para: **{p_nom_ent}** (`{p_id_ent}`)")
                with st.form("form_entrega_diaria"):
                    st.write("Confirma las cantidades a entregar hoy (se descontarán del stock):")
                    detalle_entrega = []
                    meds_actualizados = []
                    for idx, m in enumerate(meds_curr):
                        nom_m = m.get("nombre", "")
                        stk_act = int(m.get("stock", 0))
                        col_e1, col_e2, col_e3 = st.columns([3, 1, 1])
                        with col_e1:
                            st.write(f"💊 **{nom_m}** (Stock Actual: **{stk_act}**)")
                        with col_e2:
                            cant_ent = st.number_input("Cantidad a entregar", min_value=0, max_value=stk_act, value=1 if stk_act > 0 else 0, key=f"ent_{idx}")
                        with col_e3:
                            stk_rest = stk_act - cant_ent
                            st.write(f"Stock Restante: **{stk_rest}**")
                        detalle_entrega.append({
                            "nombre": nom_m,
                            "entregado": cant_ent,
                            "stock_restante": stk_rest
                        })
                        m_copy = dict(m)
                        m_copy["stock"] = stk_rest
                        meds_actualizados.append(m_copy)
                    entregado_por = st.text_input("Nombre de quien entrega / Médico", value=st.session_state["nombre_completo"])
                    btn_registrar_e = st.form_submit_button("🚚 Registrar Entrega y Descontar Stock", use_container_width=True)
                    if btn_registrar_e:
                        guardar_medicamentos_paciente(p_id_ent, meds_actualizados, obs_curr, st.session_state["username"])
                        registrar_entrega_meds(p_id_ent, detalle_entrega, entregado_por)
                        st.toast("🎉 Entrega registrada exitosamente.")
                        st.success(f"✅ ¡Entrega registrada y stock actualizado para **{p_nom_ent}**!")
                        st.balloons()
                        st.rerun()
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Stock Crítico y Compras")
        st.caption("Monitoreo global de medicamentos con stock bajo en la comunidad")
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        alertas = []
        for p in pacientes_activos:
            pid, pnom = p[0], p[1]
            meds, _ = obtener_medicamentos_paciente(pid)
            for m in meds:
                stk = int(m.get("stock", 0))
                if stk <= 5:
                    alertas.append({
                        "paciente": pnom,
                        "id": pid,
                        "medicamento": m.get("nombre", ""),
                        "stock": stk
                    })
        if not alertas:
            st.success("🎉 ¡Excelente! No hay medicamentos con stock crítico en este momento.")
        else:
            st.warning(f"⚠️ Se tienen **{len(alertas)}** alertas de medicamentos con stock bajo (<= 5 unidades):")
            for a in alertas:
                st.write(f"• **{a['medicamento']}** | Paciente: {a['paciente']} (`{a['id']}`) | Stock Restante: **{a['stock']}**")
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        st.caption("Archivero digital seguro de archivos, formatos y normativas")
        tab_rep1, tab_rep2 = st.tabs(["📜 Explorar Repositorio", "📤 Subir Nuevo Documento"])
        with tab_rep1:
            carpetas = ["Todas", "Formatos Oficiales", "Manuales y Guías", "Expedientes Escaneados", "Normatividad", "Otros"]
            f_carp = st.selectbox("Filtrar por Carpeta", carpetas)
            docs = listar_documentos_repositorio(f_carp)
            st.write(f"Se encontraron **{len(docs)}** documentos:")
            for doc in docs:
                doc_id, carp, nom_arch, tipo_arch, desc, tam, f_sub, sub_por = doc
                st.write(f"📄 **{nom_arch}** ({carp}) | {tam/1024:.1f} KB | Subido por: {sub_por} el {f_sub}")
        with tab_rep2:
            with st.form("form_subir_doc"):
                st.subheader("Cargar Archivo al Repositorio")
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    carp_sub = st.selectbox("Carpeta Destino", ["Formatos Oficiales", "Manuales y Guías", "Expedientes Escaneados", "Normatividad", "Otros"])
                    desc_sub = st.text_input("Descripción del Documento")
                with c_d2:
                    arch_up = st.file_uploader("Selecciona el Archivo", type=["pdf", "docx", "xlsx", "png", "jpg"])
                btn_sub_doc = st.form_submit_button("📤 Guardar Documento", use_container_width=True)
                if btn_sub_doc:
                    if not arch_up:
                        st.error("⚠️ Debes seleccionar un archivo.")
                    else:
                        bytes_data = arch_up.getvalue()
                        guardar_documento_repositorio(carp_sub, arch_up.name, arch_up.type, desc_sub, bytes_data, st.session_state["username"])
                        st.toast("🎉 Documento subido exitosamente.")
                        st.success(f"✅ ¡Archivo **{arch_up.name}** guardado en el repositorio!")
                        st.rerun()
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Descarga de respaldos de seguridad `.db` y restauración del sistema")
        tab_b1, tab_b2 = st.tabs(["⬇️ Descargar Respaldo", "⬆️ Restaurar Base de Datos"])
        with tab_b1:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="📦 Descargar Respaldo Actual (.db)",
                        data=f,
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
            else:
                st.error("No se encontró la base de datos.")
        with tab_b2:
            st.warning("⚠️ La restauración sobrescribirá los datos actuales con la copia que selecciones.")
            db_upload = st.file_uploader("Selecciona el archivo de respaldo (.db)", type=["db", "sqlite3"])
            if db_upload:
                if st.button("🔥 Confirmar Restauración", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(db_upload.getvalue())
                    st.toast("🎉 ¡Base de datos restaurada!")
                    st.success("✅ ¡Base de datos restaurada exitosamente!")
                    st.rerun()
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración del Sistema & Seguridad")
        tab_sec1, tab_sec2, tab_sec3 = st.tabs(["🔑 Cambiar Mi Contraseña", "👥 Usuarios y Roles del Sistema", "⚙️ Requisitos por Etapa"])
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
            st.subheader("👥 Gestión de Usuarios y Roles del Sistema")
            st.caption("Alta de personal de staff, asignación de roles y bloqueo por vacaciones")
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
                    c_u1, c_c2 = st.columns(2)
                    with c_u1:
                        val_uname = edit_uname if usr_edit_data else ""
                        sys_uname = st.text_input("👤 Nombre de Usuario (Login) *", value=val_uname, disabled=(modo_usr_sys == "✏️ Editar / Modificar Usuario Existente"))
                        val_full = usr_edit_data[2] if usr_edit_data else ""
                        sys_full = st.text_input("📛 Nombre Completo del Usuario *", value=val_full)
                    with c_c2:
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
                        col_us1, col_us2, col_us3 = st.columns([4, 1, 1])
                        with col_us1:
                            st.write(f"👤 **{ufull}** (`{uname}`) | Rol: **{urol}** | Estatus: {st_badge}")
                        with col_us2:
                            if uest == 'A':
                                dis_block = (uname == st.session_state["username"] or uname == "admin")
                                if st.button("🔒 Bloquear", key=f"btn_blk_sys_{uname}", disabled=dis_block):
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
                            if st.button("🗑️ Eliminar", key=f"del_sys_{uname}", disabled=dis_del):
                                ok_d, msg_d = eliminar_usuario_sistema(uname)
                                if ok_d:
                                    st.toast(f"🗑️ Usuario {uname} eliminado.")
                                    st.rerun()
                                else:
                                    st.error(msg_d)
        with tab_sec3:
            st.subheader("Administrador de Requisitos por Etapa")
            etapa_sel = st.selectbox("Selecciona la Etapa a Configurar", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
            reqs_curr = listar_requisitos_etapa(etapa_sel)
            st.write(f"Requisitos actuales para **{etapa_sel}**:")
            for rid, rtxt, esg in reqs_curr:
                cr1, cr2 = st.columns([4, 1])
                with cr1:
                    st.write(f"• {rtxt} {'(Sesión de Grupo)' if esg==1 else ''}")
                with cr2:
                    if st.button("🗑️ Eliminar", key=f"del_req_{rid}"):
                        eliminar_requisito_etapa(rid)
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
                        agregar_requisito_etapa(etapa_sel, nuevo_req_txt.strip(), 1 if es_grupo_chk else 0)
                        st.toast("🎉 ¡Requisito agregado exitosamente!")
                        st.success("✅ Requisito agregado exitosamente.")
                        st.rerun()
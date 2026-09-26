import streamlit as st
import sqlite3
import json
import hashlib
import base64
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

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios Administrativos del Sistema (Login & Roles)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Administrador'
        )
    ''')
    
    # Migración por si la columna 'rol' no existe en bases antiguas
    c.execute("PRAGMA table_info(usuarios)")
    cols = [col[1] for col in c.fetchall()]
    if "rol" not in cols:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Administrador'")
    
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
    
    # 3. Tabla de Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 4. Tabla de Catálogo Central de Medicamentos
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
    
    # 5. Tabla de Medicamentos e Inventario asignados a Pacientes
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
    
    # 6. Tabla de Historial de Entregas
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
            datos_json TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # 8. Tabla de Historial de Cambios de Etapa
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
    
    # 10. Tabla de Repositorio de Documentos (Solo Administrador)
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
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador'))
    
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
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def listar_usuarios_sistema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios ORDER BY username ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_usuario_sistema(username, password, nombre_completo, rol):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    pass_h = hash_pass(password) if password else None
    
    c.execute('SELECT id, password_hash FROM usuarios WHERE username = ?', (username,))
    row = c.fetchone()
    if row:
        final_pass = pass_h if pass_h else row[1]
        c.execute('UPDATE usuarios SET password_hash = ?, nombre_completo = ?, rol = ? WHERE username = ?',
                  (final_pass, nombre_completo, rol, username))
    else:
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  (username, pass_h, nombre_completo, rol))
    conn.commit()
    conn.close()

def eliminar_usuario_sistema(username):
    if username == "admin":
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    return True

# --- FUNCIONES DE PACIENTES Y PROCESO ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id LIKE "PAC-%"')
    rows = c.fetchall()
    conn.close()
    
    nums = []
    for r in rows:
        try:
            val = int(r[0].replace("PAC-", ""))
            nums.append(val)
        except:
            pass
    siguiente = max(nums) + 1 if nums else 1
    return f"PAC-{siguiente:03d}"

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if paciente_id_actual:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = LOWER(TRIM(?)) AND paciente_id != ?', (nombre, paciente_id_actual))
    else:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = LOWER(TRIM(?))', (nombre,))
    res = c.fetchone()
    conn.close()
    return res

def guardar_paciente(paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo_usr, etapa_act, f_ini_etapa, usr_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?,
                estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?,
                fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (nombre, f_ingreso, f_nac, sexo, estatus, tipo_usr, etapa_act, f_ini_etapa, f_actual, usr_reg, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (
                paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo,
                estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre, f_ingreso, f_nac, sexo, estatus, tipo_usr, etapa_act, f_ini_etapa, f_actual, f_actual, usr_reg))
        
    conn.commit()
    conn.close()

def listar_pacientes_completos(solo_activos=False, solo_pacientes=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes'
    where = []
    if solo_activos:
        where.append("estatus = 'A'")
    if solo_pacientes:
        where.append("tipo_usuario = 'Paciente'")
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY nombre_completo ASC"
    
    c.execute(query)
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
    f_actual_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy_date = datetime.now().strftime("%Y-%m-%d")
    
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (etapa_destino, f_hoy_date, f_actual_str, paciente_id))
              
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_origen, etapa_destino, f_actual_str, usr_autoriza))
              
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (hermano_id, f_actual, paciente_id))
    conn.commit()
    conn.close()

def marcar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (f_actual, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE CATÁLOGO Y MEDICAMENTOS ---
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
        res = True
    except:
        res = False
    conn.close()
    return res

def eliminar_catalogo_medicamento(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

def guardar_medicamentos_paciente(paciente_id, meds_json, observaciones, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                  (meds_json, observaciones, f_actual, usr, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)',
                  (paciente_id, meds_json, observaciones, f_actual, f_actual, usr))
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
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, f_actual, usr, detalle_json))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS Y REQUISITOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa, fecha_g, facilitador, datos_json, usr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO grupos_terapeutos (
            paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa, fecha_g, facilitador, datos_json, f_actual, usr))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?',
              (paciente_id, etapa, tipo_grupo))
    cant = c.fetchone()[0]
    conn.close()
    return cant

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

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
    if carpeta_filtro and carpeta_filtro != "Todas las Carpetas":
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
    tamano = len(contenido_bytes) if contenido_bytes else 0
    c.execute('''
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_blob, tamano_bytes, fecha_subida, subido_por)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta, nombre_archivo, tipo_archivo, descripcion, contenido_bytes, tamano, f_now, subido_por))
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

# --- REPORTEADORES PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SAWABONA SHIKOBA - COMUNIDAD TERAPEUTICA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Evaluacion y Registro de Proceso Individual", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

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

def generar_pdf_entrevista(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"EXPEDIENTE DE ENTREVISTA INICIAL - FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "TABLA DE CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
    col_w = [28, 20, 25, 30, 28, 22, 37]
    headers = ["Sustancia", "Consumo", "Forma", "Frecuencia", "Cantidad", "Edad Inic.", "Lugar"]
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    tabla_consumo = datos.get("tabla_consumo", {})
    for sust, vals in tabla_consumo.items():
        pdf.cell(col_w[0], 6, limpiar_texto(sust), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(str(vals.get("consumo", ""))), border=1, align="C")
        pdf.cell(col_w[2], 6, limpiar_texto(str(vals.get("forma", ""))), border=1)
        pdf.cell(col_w[3], 6, limpiar_texto(str(vals.get("frecuencia", ""))), border=1)
        pdf.cell(col_w[4], 6, limpiar_texto(str(vals.get("cantidad", ""))), border=1)
        pdf.cell(col_w[5], 6, limpiar_texto(str(vals.get("edad_inicio", ""))), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(str(vals.get("lugar", ""))), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Observaciones Generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    pdf.cell(pdf.epw, 5, f"Evaluador: {limpiar_texto(datos.get('evaluador_nombre', ''))} ({limpiar_texto(datos.get('evaluador_cargo', ''))})", new_x="LMARGIN", new_y="NEXT")
    
    filename = f"Entrevista_{paciente_id}.pdf"
    pdf.output(filename)
    return filename

def generar_pdf_grupos_paciente(p_id, p_nombre, grupos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE GRUPOS TERAPEUTICOS - {limpiar_texto(p_nombre)} ({p_id})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    for g in grupos:
        g_id, tipo_g, etapa_m, f_g, fac, d_json_str = g
        d_json = json.loads(d_json_str) if d_json_str else {}
        
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, f"Grupo: {limpiar_texto(tipo_g)} | Etapa: {limpiar_texto(etapa_m)} | Fecha: {f_g}", border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(pdf.epw, 5, f"Facilitador: {limpiar_texto(fac)}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("Helvetica", "", 9)
        if tipo_g == "Feedback":
            pdf.multi_cell(pdf.epw, 5, f"Logros: {limpiar_texto(d_json.get('logros', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(pdf.epw, 5, f"Dificultades: {limpiar_texto(d_json.get('dificultades', ''))}", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(pdf.epw, 5, f"Compartimiento: {limpiar_texto(d_json.get('compartimiento', ''))}", new_x="LMARGIN", new_y="NEXT")
            
        pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(d_json.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
        pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(d_json.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
        pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(d_json.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        
    filename = f"Grupos_Terapeuta_{p_id}.pdf"
    pdf.output(filename)
    return filename

# --- INICIALIZAR DB Y ESTADO ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = "Lectura"

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_unsafe_html=True if hasattr(st, "unsafe_html") else False)
    st.markdown("<h3 style='text-align: center;'>Comunidad Terapéutica para el Tratamiento de Adicciones</h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Acceso de Personal al Sistema")
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submit:
                u_ok = verificar_login(user_input, pass_input)
                if u_ok:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u_ok[0]
                    st.session_state["nombre_completo"] = u_ok[1]
                    st.session_state["rol"] = u_ok[2] if len(u_ok) > 2 and u_ok[2] else "Administrador"
                    st.toast(f"¡Bienvenido, {u_ok[1]}!", icon="🎉")
                    st.success(f"✅ ¡Acceso concedido como **{st.session_state['rol']}**!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales Administrador por Defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    rol_actual = st.session_state.get("rol", "Lectura")
    
    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    # Etiqueta visual del Rol
    if rol_actual == "Administrador":
        st.sidebar.markdown("🏷️ **Rol**: <span style='color:red; font-weight:bold;'>Nivel 1 - Administrador</span>", unsafe_allow_html=True)
    elif rol_actual == "Lectura y Escritura":
        st.sidebar.markdown("🏷️ **Rol**: <span style='color:green; font-weight:bold;'>Nivel 2 - Lectura y Escritura</span>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown("🏷️ **Rol**: <span style='color:orange; font-weight:bold;'>Nivel 3 - Solo Lectura</span>", unsafe_allow_html=True)
        
    st.sidebar.markdown("---")
    
    # Opciones de Menú
    menu_opciones = [
        "👤 Registro y Edición de Usuarios",
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "💊 Control de Medicamentos y Dosis",
        "🚚 Entrega de Medicamentos",
        "📝 Entrevista Inicial de Consejería",
        "🔍 Buscar y Listar Pacientes",
        "📦 Respaldo y Restauración"
    ]
    
    # Módulo exclusivo para Administradores
    if rol_actual == "Administrador":
        menu_opciones.append("📁 Repositorio de Documentos")
        menu_opciones.append("⚙️ Configuración y Seguridad")
        
    menu = st.sidebar.radio("Navegación del Sistema", menu_opciones)
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # =========================================================================
    # MODULO 1: REGISTRO Y EDICIÓN DE USUARIOS
    # =========================================================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes / Servidores")
        st.caption("Catálogo oficial de usuarios de la comunidad terapéutica")
        
        # Validación Nivel 3 (Solo Lectura)
        es_solo_lectura = (rol_actual == "Lectura")
        if es_solo_lectura:
            st.warning("🔒 **Modo Consulta (Solo Lectura)**: Su nivel de usuario le permite visualizar la información pero no realizar modificaciones.")
            
        modo_usuario = st.radio("Acción a realizar:", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        pacientes_existentes = listar_pacientes_completos()
        edit_paciente_id = None
        datos_edit = None
        
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            if not pacientes_existentes:
                st.warning("No hay usuarios registrados aún para editar.")
            else:
                opciones_edit = [f"{p[0]} - {p[1]} ({p[6]})" for p in pacientes_existentes]
                sel_edit = st.selectbox("🔑 Selecciona el Usuario a Editar", opciones_edit)
                edit_paciente_id = sel_edit.split(" - ")[0]
                datos_edit = obtener_paciente(edit_paciente_id)
                
        # Formulario
        f_key = f"form_usr_{edit_paciente_id if edit_paciente_id else 'nuevo'}"
        with st.form(f_key):
            st.subheader("Datos Basales e Identificación")
            
            c_u1, c_u2 = st.columns(2)
            with c_u1:
                if modo_usuario == "🆕 Registrar Nuevo Usuario":
                    reg_paciente_id = st.text_input("Folio / ID de Usuario *", value=generar_siguiente_folio(), disabled=True)
                else:
                    reg_paciente_id = st.text_input("Folio / ID de Usuario *", value=edit_paciente_id, disabled=True)
                    
                reg_nombre = st.text_input("Nombre Completo *", value=datos_edit[1] if datos_edit else "")
                reg_tipo = st.selectbox("Tipo de Usuario *", ["Paciente", "Servidor / Staff"],
                                        index=0 if (not datos_edit or datos_edit[6] == "Paciente") else 1)
            with c_u2:
                # Fechas
                val_f_ing = datetime.strptime(datos_edit[2], "%Y-%m-%d").date() if datos_edit and datos_edit[2] else date.today()
                val_f_nac = datetime.strptime(datos_edit[3], "%Y-%m-%d").date() if datos_edit and datos_edit[3] else date(1990, 1, 1)
                
                reg_f_ingreso = st.date_input("📅 Fecha de Ingreso Real", value=val_f_ing)
                reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=val_f_nac, min_value=date(1920, 1, 1), max_value=date.today())
                
                c_s1, c_s2 = st.columns(2)
                with c_s1:
                    reg_sexo = st.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if (not datos_edit or datos_edit[4] == "MASCULINO") else 1)
                with c_s2:
                    reg_estatus = st.selectbox("Estatus *", ["A (Activo)", "B (Bloqueado / Baja)"], index=0 if (not datos_edit or datos_edit[5] == "A") else 1)
                    
            st.subheader("Etapa de Inicio en el Sistema")
            c_et1, c_et2 = st.columns(2)
            etapas_lista = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            with c_et1:
                idx_et = etapas_lista.index(datos_edit[7]) if (datos_edit and datos_edit[7] in etapas_lista) else 0
                reg_etapa = st.selectbox("Etapa Actual / Inicial", etapas_lista, index=idx_et)
            with c_et2:
                val_f_et = datetime.strptime(datos_edit[8], "%Y-%m-%d").date() if datos_edit and datos_edit[8] else date.today()
                reg_f_etapa = st.date_input("📅 Fecha de Inicio en la Etapa Actual", value=val_f_et)
                
            btn_guardar_usr = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True, disabled=es_solo_lectura)
            
            if btn_guardar_usr:
                if not reg_nombre.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                else:
                    est_letter = reg_estatus.split(" ")[0]
                    
                    if modo_usuario == "🆕 Registrar Nuevo Usuario":
                        dup = verificar_duplicado_nombre(reg_nombre)
                        if dup:
                            st.error(f"❌ Imposible registrar: Ya existe el usuario '**{dup[1]}**' bajo el Folio **{dup[0]}**.")
                        else:
                            guardar_paciente(reg_paciente_id, reg_nombre, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, est_letter, reg_tipo, reg_etapa, str(reg_f_etapa), st.session_state["username"])
                            st.toast(f"¡Usuario {reg_nombre} registrado!", icon="🎉")
                            st.success(f"✅ ¡Usuario **{reg_nombre}** registrado exitosamente con Folio **{reg_paciente_id}**!")
                    else:
                        guardar_paciente(reg_paciente_id, reg_nombre, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, est_letter, reg_tipo, reg_etapa, str(reg_f_etapa), st.session_state["username"])
                        st.toast(f"¡Usuario {reg_nombre} actualizado!", icon="🎉")
                        st.success(f"✅ ¡Usuario **{reg_nombre}** ({reg_paciente_id}) actualizado exitosamente!")

    # =========================================================================
    # MODULO 2: GESTIÓN DE ETAPAS & PROCESO
    # =========================================================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Control del Proceso de 7 Meses y Avance de Etapas")
        st.caption("Comunidad Terapéutica Sawabona Shikoba")
        
        pacientes = listar_pacientes_completos(solo_activos=True, solo_pacientes=True)
        if not pacientes:
            st.info("No hay residentes registrados activos para gestionar.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]} (Etapa: {p[7]})": p for p in pacientes}
            sel_p_key = st.selectbox("👤 Selecciona al Residente para Evaluar Avance", list(dict_pacientes.keys()))
            p_data = dict_pacientes[sel_p_key]
            
            p_id, p_nom, p_f_ing, p_f_nac, p_sex, p_est, p_tipo, p_etapa, p_f_etapa, p_h_mayor, p_f_suelta = p_data
            
            # Cálculos de tiempo
            f_hoy = date.today()
            f_ing_d = datetime.strptime(p_f_ing, "%Y-%m-%d").date() if p_f_ing else f_hoy
            f_et_d = datetime.strptime(p_f_etapa, "%Y-%m-%d").date() if p_f_etapa else f_ing_d
            
            dias_totales = (f_hoy - f_ing_d).days
            dias_en_etapa = (f_hoy - f_et_d).days
            
            duracion_etapas = {
                "ACOGIDA": 30,
                "IDENTIFICACIÓN": 60,
                "ELABORACIÓN": 60,
                "CONSOLIDACIÓN": 30,
                "SERVICIO SOCIAL": 30
            }
            dur_req = duracion_etapas.get(p_etapa, 30)
            
            st.markdown("---")
            c_m1, c_m2, c_m3 = c_m = st.columns(3)
            with c_m1:
                st.metric("Etapa Actual", p_etapa)
            with c_m2:
                st.metric("Días en Etapa Actual", f"{dias_en_etapa} / {dur_req} días")
            with c_m3:
                st.metric("Días Totales en Clínica", f"{dias_totales} días")
                
            # Alertas
            dias_restantes = dur_req - dias_en_etapa
            if dias_restantes <= 5 and dias_restantes >= 0:
                st.warning(f"⏰ **ALERTA DE PROCESO**: {p_nom} está a **{dias_restantes} días** de cumplir el tiempo estándar en **{p_etapa}**. Prepare comité para cambio de etapa.")
            elif dias_restantes < 0:
                st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO**: {p_nom} ha excedido el tiempo estándar en **{p_etapa}** por **{abs(dias_restantes)} días**. Revise los requisitos pendientes en el checklist.")
                
            st.progress(min(1.0, max(0.0, dias_en_etapa / dur_req)))
            
            tab_check, tab_hermano = st.tabs(["📋 Checklist de Requisitos de Etapa", "🤝 Control de Hermano Mayor"])
            
            with tab_check:
                st.subheader(f"Requisitos para Aprobar la Etapa: {p_etapa}")
                reqs_etapa = listar_requisitos_etapa(p_etapa)
                
                reqs_completos = True
                
                for r_id, r_nom, es_g in reqs_etapa:
                    if es_g == 1:
                        # Conteo Automático por Sistema
                        if "Aquí y Ahora" in r_nom:
                            cant_hecha = contar_grupos_paciente_etapa(p_id, p_etapa, "Aquí y Ahora")
                            req_meta = 4 if p_etapa in ["IDENTIFICACIÓN", "ELABORACIÓN"] else 2
                        elif "Terapia de Grupo" in r_nom:
                            cant_hecha = contar_grupos_paciente_etapa(p_id, p_etapa, "Terapia de Grupo")
                            req_meta = 4 if p_etapa in ["IDENTIFICACIÓN", "ELABORACIÓN"] else 2
                        elif "Feedback" in r_nom:
                            cant_hecha = contar_grupos_paciente_etapa(p_id, p_etapa, "Feedback")
                            req_meta = 4 if p_etapa in ["IDENTIFICACIÓN", "ELABORACIÓN"] else 2
                        else:
                            cant_hecha = 0
                            req_meta = 1
                            
                        cumple = (cant_hecha >= req_meta)
                        if not cumple:
                            reqs_completos = False
                            
                        st.write(f"{'✅' if cumple else '❌'} **{r_nom}**: Realizados **{cant_hecha} de {req_meta}** (Contado automáticamente por sistema)")
                    else:
                        # Checkbox manual para entregables/reglas
                        chk = st.checkbox(f"📌 {r_nom}", value=True, key=f"chk_{p_id}_{r_id}")
                        if not chk:
                            reqs_completos = False
                            
                st.markdown("---")
                
                # Siguiente Etapa
                orden_etapas = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_actual = orden_etapas.index(p_etapa)
                
                if idx_actual < len(orden_etapas) - 1:
                    siguiente_etapa = orden_etapas[idx_actual + 1]
                    if not reqs_completos:
                        st.info(f"🔒 El botón de promoción a **{siguiente_etapa}** se habilitará cuando todos los requisitos de la lista estén al 100%.")
                        
                    es_deshabilitado = (not reqs_completos) or (rol_actual == "Lectura")
                    if st.button(f"🚀 Promover a {siguiente_etapa}", disabled=es_deshabilitado, type="primary"):
                        promover_etapa(p_id, p_etapa, siguiente_etapa, st.session_state["username"])
                        st.toast(f"¡{p_nom} promovido a {siguiente_etapa}!", icon="🎉")
                        st.success(f"✅ ¡{p_nom} ha sido promovido exitosamente a **{siguiente_etapa}**!")
                        st.rerun()
                else:
                    st.success("🎓 ¡El residente ha completado la última etapa del proceso de la comunidad!")

            with tab_hermano:
                if p_etapa == "ACOGIDA":
                    st.subheader("Acompañamiento en Etapa de Acogida (Primeros 15 días)")
                    st.write(f"**Estado Actual**: Hermano Menor en Acogida")
                    st.write(f"**Hermano Mayor Asignado**: {p_h_mayor if p_h_mayor else 'Ninguno asignado'}")
                    st.write(f"**Fecha de Suelta**: {p_f_suelta if p_f_suelta else 'Pendiente'}")
                    
                    posibles_mayores = [f"{p[0]} - {p[1]}" for p in pacientes if p[0] != p_id]
                    if posibles_mayores:
                        sel_hm = st.selectbox("Asignar Hermano Mayor", posibles_mayores)
                        if st.button("🤝 Asignar Hermano Mayor", disabled=(rol_actual == "Lectura")):
                            hm_id = sel_hm.split(" - ")[0]
                            asignar_hermano_mayor(p_id, hm_id)
                            st.toast("Hermano Mayor asignado", icon="🎉")
                            st.success("✅ Hermano Mayor asignado correctamente.")
                            st.rerun()
                            
                    if p_h_mayor and not p_f_suelta:
                        if st.button("🔓 Marcar que Hermano Mayor lo Suelta (Cumplió 15 Días)", disabled=(rol_actual == "Lectura")):
                            marcar_suelta_hermano(p_id)
                            st.toast("Suelta registrada", icon="🎉")
                            st.success("✅ Se ha registrado la suelta del Hermano Mayor.")
                            st.rerun()
                else:
                    st.info("El acompañamiento de Hermano Mayor aplica principalmente para la primera etapa de ACOGIDA.")

    # =========================================================================
    # MODULO 3: GRUPOS TERAPÉUTICOS
    # =========================================================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Captura e historial de Terapia de Grupo, Aquí y Ahora y Feedbacks")
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        pacientes = listar_pacientes_completos(solo_activos=True, solo_pacientes=True)
        
        with tab_reg_g:
            if not pacientes:
                st.warning("No hay pacientes activos para registrar grupos.")
            else:
                dict_p_g = {f"{p[0]} - {p[1]} (Etapa: {p[7]})": p for p in pacientes}
                sel_p_g = st.selectbox("👤 Selecciona al Paciente", list(dict_p_g.keys()))
                p_g_data = dict_p_g[sel_p_g]
                
                p_id_g, p_nom_g, _, _, _, _, _, p_etapa_g, _, _, _ = p_g_data
                
                tipo_grupo = st.radio("Selecciona el Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"], horizontal=True)
                
                with st.form("form_grupo_terapeuto"):
                    c_g1, c_g2 = st.columns(2)
                    with c_g1:
                        f_grupo = st.date_input("📅 Fecha de la Sesión", value=date.today())
                    with c_g2:
                        facil_grupo = st.text_input("👤 Nombre del Facilitador / Staff", value=st.session_state["nombre_completo"])
                        
                    datos_g_json = {}
                    
                    if tipo_grupo == "Feedback":
                        logros_txt = st.text_area("🌟 Logros del Residente (Texto Largo)", height=100)
                        dificultades_txt = st.text_area("⚠️ Dificultades Detectadas (Texto Largo)", height=100)
                        obs_g_txt = st.text_area("📝 Observaciones Generales (Texto Largo)", height=100)
                        dev_g_txt = st.text_area("🔄 Devoluciones del Grupo (Texto Largo)", height=100)
                        compr_g_txt = st.text_area("🤝 ¿Cómo se queda y a qué se compromete? (Texto Largo)", height=100)
                        
                        datos_g_json = {
                            "logros": logros_txt,
                            "dificultades": dificultades_txt,
                            "observaciones": obs_g_txt,
                            "devoluciones": dev_g_txt,
                            "compromiso": compr_g_txt
                        }
                    else:
                        comp_txt = st.text_area("💬 Compartimiento del Residente (Texto Largo)", height=120)
                        obs_g_txt = st.text_area("📝 Observaciones del Facilitador (Texto Largo)", height=100)
                        dev_g_txt = st.text_area("🔄 Devoluciones recibidas (Texto Largo)", height=100)
                        compr_g_txt = st.text_area("🤝 ¿Cómo se queda y a qué se compromete? (Texto Largo)", height=100)
                        
                        datos_g_json = {
                            "compartimiento": comp_txt,
                            "observaciones": obs_g_txt,
                            "devoluciones": dev_g_txt,
                            "compromiso": compr_g_txt
                        }
                        
                    btn_g_save = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True, disabled=(rol_actual == "Lectura"))
                    
                    if btn_g_save:
                        guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, str(f_grupo), facil_grupo, json.dumps(datos_g_json), st.session_state["username"])
                        st.toast(f"¡Grupo {tipo_grupo} registrado!", icon="🎉")
                        st.success(f"✅ ¡Sesión de **{tipo_grupo}** registrada exitosamente para **{p_nom_g}**!")

        with tab_hist_g:
            if not pacientes:
                st.info("No hay pacientes para consultar historial.")
            else:
                sel_p_hist = st.selectbox("👤 Selecciona Paciente para Consultar Expediente de Grupos", [f"{p[0]} - {p[1]}" for p in pacientes])
                p_id_h = sel_p_hist.split(" - ")[0]
                p_nom_h = sel_p_hist.split(" - ")[1]
                
                grupos_p = listar_grupos_paciente(p_id_h)
                
                if not grupos_p:
                    st.info(f"El paciente {p_nom_h} no tiene grupos registrados aún.")
                else:
                    st.subheader(f"Total de Grupos Registrados: {len(grupos_p)}")
                    
                    pdf_g = generar_pdf_grupos_paciente(p_id_h, p_nom_h, grupos_p)
                    with open(pdf_g, "rb") as f_pdf:
                        st.download_button(
                            label="🖨️ Descargar Expediente de Grupos en PDF",
                            data=f_pdf,
                            file_name=f"Expediente_Grupos_{p_id_h}.pdf",
                            mime="application/pdf"
                        )
                        
                    for g in grupos_p:
                        g_id, t_g, e_m, f_g, fac, d_json_s = g
                        d_j = json.loads(d_json_s) if d_json_s else {}
                        
                        with st.expander(f"📌 {t_g} - Fecha: {f_g} | Etapa: {e_m} | Facilitador: {fac}"):
                            if t_g == "Feedback":
                                st.write(f"**🌟 Logros:** {d_j.get('logros', '')}")
                                st.write(f"**⚠️ Dificultades:** {d_j.get('dificultades', '')}")
                            else:
                                st.write(f"**💬 Compartimiento:** {d_j.get('compartimiento', '')}")
                            st.write(f"**📝 Observaciones:** {d_j.get('observaciones', '')}")
                            st.write(f"**🔄 Devoluciones:** {d_j.get('devoluciones', '')}")
                            st.write(f"**🤝 Compromiso:** {d_j.get('compromiso', '')}")

    # =========================================================================
    # MODULO 4: CONTROL DE MEDICAMENTOS Y DOSIS
    # =========================================================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos, Catálogo e Inventario")
        
        tab_esquema, tab_catalogo, tab_reporte_med = st.tabs([
            "📋 Esquema por Paciente",
            "📚 Catálogo Central de Medicamentos",
            "📊 Reporte por Medicamento"
        ])
        
        pacientes = listar_pacientes_completos(solo_activos=True)
        catalogo = listar_catalogo_medicamentos()
        
        with tab_esquema:
            if not pacientes:
                st.warning("No hay usuarios activos registrados.")
            else:
                sel_p_med = st.selectbox("👤 Selecciona el Paciente para Configurar Dosis", [f"{p[0]} - {p[1]}" for p in pacientes])
                p_id_m = sel_p_med.split(" - ")[0]
                p_nom_m = sel_p_med.split(" - ")[1]
                
                meds_guardados, obs_meds = obtener_medicamentos_paciente(p_id_m)
                
                st.subheader(f"Esquema de Medicación para {p_nom_m}")
                
                if "cant_filas_meds" not in st.session_state:
                    st.session_state["cant_filas_meds"] = max(1, len(meds_guardados))
                    
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button("➕ Agregar Medicamento al Esquema"):
                        st.session_state["cant_filas_meds"] += 1
                        st.rerun()
                with c_btn2:
                    if st.button("➖ Quitar Última Fila") and st.session_state["cant_filas_meds"] > 1:
                        st.session_state["cant_filas_meds"] -= 1
                        st.rerun()
                        
                nombres_cat = [f"{m[1]} ({m[2]} - {m[3]})" for m in catalogo]
                
                with st.form("form_esquema_meds"):
                    nuevos_meds = []
                    
                    for i in range(st.session_state["cant_filas_meds"]):
                        m_prev = meds_guardados[i] if i < len(meds_guardados) else {}
                        st.markdown(f"**Medicamento #{i+1}**")
                        
                        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([2.5, 1, 1, 1, 1.5, 2])
                        
                        with col_m1:
                            med_nom_saved = m_prev.get("nombre", "")
                            idx_sel = 0
                            for idx_cat, m_cat in enumerate(catalogo):
                                if m_cat[1] == med_nom_saved:
                                    idx_sel = idx_cat
                                    break
                            
                            if nombres_cat:
                                sel_cat_med = st.selectbox(f"Medicamento (Catálogo)", nombres_cat, index=idx_sel, key=f"cat_med_{p_id_m}_{i}")
                                med_nom_final = sel_cat_med.split(" (")[0]
                            else:
                                med_nom_final = st.text_input(f"Nombre Medicamento", value=med_nom_saved, key=f"txt_med_{p_id_m}_{i}")
                                
                        with col_m2:
                            d_man = st.number_input("☀️ Mañana", min_value=0, value=int(m_prev.get("manana", 0)), key=f"m_man_{p_id_m}_{i}")
                        with col_m3:
                            d_tar = st.number_input("🌤️ Tarde", min_value=0, value=int(m_prev.get("tarde", 0)), key=f"m_tar_{p_id_m}_{i}")
                        with col_m4:
                            d_noc = st.number_input("🌙 Noche", min_value=0, value=int(m_prev.get("noche", 0)), key=f"m_noc_{p_id_m}_{i}")
                        with col_m5:
                            exis = st.number_input("📦 Existencia", min_value=0, value=int(m_prev.get("existencia", 0)), key=f"m_ex_{p_id_m}_{i}")
                        with col_m6:
                            ind = st.text_input("📝 Indicaciones", value=m_prev.get("indicaciones", ""), key=f"m_ind_{p_id_m}_{i}")
                            
                        nuevos_meds.append({
                            "nombre": med_nom_final,
                            "manana": d_man,
                            "tarde": d_tar,
                            "noche": d_noc,
                            "existencia": exis,
                            "indicaciones": ind
                        })
                        st.divider()
                        
                    obs_m_txt = st.text_area("Observaciones y Alergias Medicamentosas", value=obs_meds)
                    btn_m_save = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True, disabled=(rol_actual == "Lectura"))
                    
                    if btn_m_save:
                        guardar_medicamentos_paciente(p_id_m, json.dumps(nuevos_meds), obs_m_txt, st.session_state["username"])
                        st.toast("Esquema guardado exitosamente", icon="🎉")
                        st.success(f"✅ ¡Esquema de medicamentos para **{p_nom_m}** guardado correctamente!")

        with tab_catalogo:
            st.subheader("📚 Catálogo Central de Medicamentos de la Clínica")
            st.caption("Administra los medicamentos disponibles para evitar capturas repetidas")
            
            with st.form("form_nuevo_cat_med"):
                c_c1, c_c2, c_c3 = st.columns(3)
                with c_c1:
                    c_nom = st.text_input("Nombre del Medicamento / Sustancia *")
                with c_c2:
                    c_pres = st.text_input("Presentación (Comprimidos, Cápsulas, Gotas, etc.)", value="Comprimidos")
                with c_c3:
                    c_conc = st.text_input("Concentración / Dosis (ej. 500 mg, 20 mg)", value="500 mg")
                    
                btn_cat_add = st.form_submit_button("➕ Agregar al Catálogo Central", disabled=(rol_actual == "Lectura"))
                if btn_cat_add:
                    if not c_nom.strip():
                        st.error("El nombre del medicamento es obligatorio.")
                    else:
                        if agregar_catalogo_medicamento(c_nom, c_pres, c_conc):
                            st.toast("Medicamento agregado al catálogo", icon="🎉")
                            st.success(f"✅ ¡Medicamento **{c_nom}** agregado al catálogo central!")
                            st.rerun()
                        else:
                            st.error("Ya existe un medicamento con ese nombre en el catálogo.")
                            
            st.markdown("---")
            if not catalogo:
                st.info("El catálogo está vacío.")
            else:
                st.subheader(f"Total de Medicamentos en Catálogo: {len(catalogo)}")
                for m_id, m_n, m_p, m_c in catalogo:
                    c_l1, c_l2 = st.columns([4, 1])
                    with c_l1:
                        st.write(f"💊 **{m_n}** | Presentación: {m_p} | Concentración: {m_c}")
                    with c_l2:
                        if st.button("🗑️ Eliminar", key=f"del_cat_{m_id}", disabled=(rol_actual != "Administrador")):
                            eliminar_catalogo_medicamento(m_id)
                            st.toast("Medicamento eliminado", icon="🗑️")
                            st.rerun()

        with tab_reporte_med:
            st.subheader("📊 Consumo e Inventario Global por Medicamento")
            
            if not catalogo:
                st.info("Agregue medicamentos al catálogo para consultar reportes.")
            else:
                m_nombres = [m[1] for m in catalogo]
                sel_med_rep = st.selectbox("💊 Selecciona Medicamento a Consultar", m_nombres)
                
                # Buscar qué pacientes lo consumen
                pacientes_consumidores = []
                total_consumo_diario_clinica = 0
                total_stock_clinica = 0
                
                for p in pacientes:
                    p_id, p_nom, _, _, _, _, _, _, _, _, _ = p
                    meds_p, _ = obtener_medicamentos_paciente(p_id)
                    for m in meds_p:
                        if m.get("nombre") == sel_med_rep:
                            d_diaria = m.get("manana", 0) + m.get("tarde", 0) + m.get("noche", 0)
                            pacientes_consumidores.append({
                                "id": p_id,
                                "nombre": p_nom,
                                "manana": m.get("manana", 0),
                                "tarde": m.get("tarde", 0),
                                "noche": m.get("noche", 0),
                                "dosis_diaria": d_diaria,
                                "existencia": m.get("existencia", 0),
                                "indicaciones": m.get("indicaciones", "")
                            })
                            total_consumo_diario_clinica += d_diaria
                            total_stock_clinica += m.get("existencia", 0)
                            
                st.markdown("---")
                c_r1, c_r2, c_r3 = st.columns(3)
                with c_r1:
                    st.metric("Pacientes que lo Consumen", len(pacientes_consumidores))
                with c_r2:
                    st.metric("Consumo Diario Total en Clínica", f"{total_consumo_diario_clinica} unidades")
                with c_r3:
                    st.metric("Existencia Total en Almacén", f"{total_stock_clinica} unidades")
                    
                if not pacientes_consumidores:
                    st.info(f"Ningún paciente tiene asignado actualmente el medicamento **{sel_med_rep}**.")
                else:
                    st.subheader("Desglose por Paciente")
                    for pc in pacientes_consumidores:
                        st.write(f"👤 **{pc['nombre']}** ({pc['id']}) | Dosis: ☀️ {pc['manana']} - 🌤️ {pc['tarde']} - 🌙 {pc['noche']} (Total: **{pc['dosis_diaria']}** al día) | Stock: **{pc['existencia']}** | Ind: {pc['indicaciones']}")

    # =========================================================================
    # MODULO 5: ENTREGA DE MEDICAMENTOS
    # =========================================================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Entrega de Medicamentos")
        st.caption("Descuento de stock en tiempo real y comprobante de entrega")
        
        pacientes = listar_pacientes_completos(solo_activos=True)
        if not pacientes:
            st.info("No hay pacientes activos para entregar medicamentos.")
        else:
            sel_p_e = st.selectbox("👤 Selecciona al Paciente para Entrega", [f"{p[0]} - {p[1]}" for p in pacientes])
            p_id_e = sel_p_e.split(" - ")[0]
            p_nom_e = sel_p_e.split(" - ")[1]
            
            meds_e, obs_e = obtener_medicamentos_paciente(p_id_e)
            
            if not meds_e:
                st.warning(f"El paciente {p_nom_e} no tiene medicamentos configurados en su esquema.")
            else:
                st.subheader(f"Entregar Medicación a: {p_nom_e}")
                
                with st.form("form_entrega_meds"):
                    cantidades_a_entregar = {}
                    for m in meds_e:
                        nom_m = m.get("nombre", "")
                        d_diaria = m.get("manana", 0) + m.get("tarde", 0) + m.get("noche", 0)
                        ex_m = m.get("existencia", 0)
                        
                        st.markdown(f"💊 **{nom_m}** (Dosis Diaria Recomendada: **{d_diaria}** | Existencia Actual: **{ex_m}**)")
                        val_def = min(d_diaria, ex_m) if d_diaria > 0 else 0
                        cant_ent = st.number_input(f"Cantidad a entregar de {nom_m}", min_value=0, max_value=ex_m, value=val_def, key=f"ent_{p_id_e}_{nom_m}")
                        cantidades_a_entregar[nom_m] = cant_ent
                        st.divider()
                        
                    btn_entregar = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True, disabled=(rol_actual == "Lectura"))
                    
                    if btn_entregar:
                        meds_actualizados = []
                        detalle_entrega = []
                        
                        for m in meds_e:
                            nom_m = m.get("nombre", "")
                            cant_e = cantidades_a_entregar.get(nom_m, 0)
                            nueva_ex = max(0, m.get("existencia", 0) - cant_e)
                            
                            m_copy = dict(m)
                            m_copy["existencia"] = nueva_ex
                            meds_actualizados.append(m_copy)
                            
                            detalle_entrega.append({
                                "nombre": nom_m,
                                "entregado": cant_e,
                                "existencia_restante": nueva_ex
                            })
                            
                        guardar_medicamentos_paciente(p_id_e, json.dumps(meds_actualizados), obs_e, st.session_state["username"])
                        registrar_entrega_meds(p_id_e, json.dumps(detalle_entrega), st.session_state["username"])
                        
                        st.toast("Entrega registrada exitosamente", icon="🎉")
                        st.success(f"✅ ¡Entrega registrada exitosamente para **{p_nom_e}**! Se actualizaron los inventarios.")

    # =========================================================================
    # MODULO 6: ENTREVISTA INICIAL DE CONSEJERÍA
    # =========================================================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        
        pacientes = listar_pacientes_completos(solo_activos=True)
        if not pacientes:
            st.info("Registre usuarios primero para realizar la entrevista.")
        else:
            sel_p_ent = st.selectbox("👤 Selecciona Paciente para Entrevista", [f"{p[0]} - {p[1]}" for p in pacientes])
            p_id_ent = sel_p_ent.split(" - ")[0]
            p_nom_ent = sel_p_ent.split(" - ")[1]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (p_id_ent,))
            r_ent = c.fetchone()
            conn.close()
            datos_ent = json.loads(r_ent[0]) if r_ent else {}
            
            with st.form("form_entrevista"):
                st.subheader("Datos Socio-Demográficos")
                dep_flag = st.selectbox("¿Dependientes económicos?", ["NO", "SÍ"], index=1 if datos_ent.get("dependientes_flag") == "SÍ" else 0)
                dep_qui = st.text_input("¿Quiénes?", value=datos_ent.get("dependientes_quienes", ""))
                par_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if datos_ent.get("pareja_flag") == "SÍ" else 0)
                par_time = st.text_input("Tiempo de relación", value=datos_ent.get("pareja_tiempo", ""))
                
                st.subheader("Tabla de Consumo")
                sustancias = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO"]
                t_consumo = datos_ent.get("tabla_consumo", {})
                t_input = {}
                
                for s in sustancias:
                    s_d = t_consumo.get(s, {})
                    st.markdown(f"**{s}**")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        c_v = st.checkbox("Consume", value=s_d.get("consumo") == "SÍ", key=f"ent_c_{s}")
                    with c2:
                        f_v = st.text_input("Forma", value=s_d.get("forma", ""), key=f"ent_f_{s}")
                    with c3:
                        fr_v = st.text_input("Frecuencia", value=s_d.get("frecuencia", ""), key=f"ent_fr_{s}")
                    with c4:
                        cant_v = st.text_input("Cantidad", value=s_d.get("cantidad", ""), key=f"ent_cant_{s}")
                    t_input[s] = {"consumo": "SÍ" if c_v else "NO", "forma": f_v, "frecuencia": fr_v, "cantidad": cant_v}
                    
                sust_imp = st.text_input("Sustancia de Impacto Principal", value=datos_ent.get("sustancia_impacto", ""))
                obs_ent = st.text_area("Observaciones Generales", value=datos_ent.get("observaciones", ""))
                
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    ev_nom = st.text_input("Nombre de Evaluador", value=datos_ent.get("evaluador_nombre", st.session_state["nombre_completo"]))
                with c_e2:
                    ev_car = st.text_input("Cargo Evaluador", value=datos_ent.get("evaluador_cargo", "Consejero Clínico"))
                    
                btn_s_ent = st.form_submit_button("💾 Guardar Expediente de Entrevista", use_container_width=True, disabled=(rol_actual == "Lectura"))
                
                if btn_s_ent:
                    d_com = {
                        "dependientes_flag": dep_flag, "dependientes_quienes": dep_qui,
                        "pareja_flag": par_flag, "pareja_tiempo": par_time,
                        "tabla_consumo": t_input, "sustancia_impacto": sust_imp,
                        "observaciones": obs_ent, "evaluador_nombre": ev_nom, "evaluador_cargo": ev_car
                    }
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    f_now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    d_json_str = json.dumps(d_com, ensure_ascii=False)
                    
                    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (p_id_ent,))
                    if c.fetchone():
                        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (f_now_str, d_json_str, p_id_ent))
                    else:
                        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                                  (p_id_ent, f_now_str, f_now_str, st.session_state["username"], d_json_str))
                    conn.commit()
                    conn.close()
                    
                    st.toast("Entrevista guardada", icon="🎉")
                    st.success("✅ ¡Expediente de entrevista inicial guardado con éxito!")

    # =========================================================================
    # MODULO 7: BUSCAR Y LISTAR PACIENTES
    # =========================================================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Catálogo General de Expedientes")
        
        pacientes = listar_pacientes_completos()
        if not pacientes:
            st.warning("No hay usuarios registrados en el sistema.")
        else:
            st.subheader(f"Total de Usuarios Registrados: {len(pacientes)}")
            
            for p in pacientes:
                p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_et, p_fet, p_hm, p_fsu = p
                
                with st.expander(f"👤 {p_nom} (Folio: **{p_id}**) | Tipo: **{p_tipo}** | Etapa: **{p_et}** | Estatus: **{p_est}**"):
                    c_dp1, c_dp2 = st.columns([3, 1])
                    with c_dp1:
                        st.write(f"**Fecha de Ingreso:** {p_fing} | **Fecha de Nacimiento:** {p_fnac} | **Sexo:** {p_sex}")
                        if p_tipo == "Paciente":
                            st.write(f"**Inicio en Etapa {p_et}:** {p_fet}")
                            if p_hm:
                                st.write(f"**Hermano Mayor:** {p_hm} | **Fecha Suelta:** {p_fsu if p_fsu else 'En acompañamiento'}")
                    with c_dp2:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT datos_json FROM entrevistas WHERE paciente_id = ?', (p_id,))
                        r_e = c.fetchone()
                        conn.close()
                        if r_e:
                            d_p = json.loads(r_e[0])
                            pdf_f = generar_pdf_entrevista(p_id, d_p)
                            with open(pdf_f, "rb") as f_pdf:
                                st.download_button("🖨️ Imprimir Entrevista", f_pdf, file_name=f"Entrevista_{p_id}.pdf", key=f"btn_pdf_l_{p_id}")

    # =========================================================================
    # MODULO 8: RESPALDO Y RESTAURACIÓN
    # =========================================================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Asegura y recupera tu información ante cualquier actualización o reinicio del servidor")
        
        tab_back, tab_rest = st.tabs(["📥 Descargar Respaldo Seguro (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_back:
            st.subheader("Copia de Seguridad de la Base de Datos")
            st.write("Descargue una copia exacta del archivo `.db` que contiene todos los pacientes, medicamentos, grupos y carpetas.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    st.download_button(
                        label="📥 Descargar Respaldo de Base de Datos",
                        data=f_db,
                        file_name=f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )
                    
        with tab_rest:
            st.subheader("Restaurar desde un Archivo de Respaldo")
            
            uploaded_db = st.file_uploader("Seleccione el archivo de respaldo (.db)", type=["db", "sqlite", "sqlite3"])
            if uploaded_db is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", type="primary", disabled=(rol_actual != "Administrador")):
                    with open(DB_FILE, "wb") as f_out:
                        f_out.write(uploaded_db.read())
                    st.toast("Base de datos restaurada", icon="🎉")
                    st.success("✅ ¡Base de datos restaurada exitosamente! Se actualizará la página.")
                    st.rerun()

    # =========================================================================
    # MODULO 9: REPOSITORIO DE DOCUMENTOS (EXCLUSIVO ADMINISTRADOR)
    # =========================================================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos, Formatos y Manuales")
        st.caption("Biblioteca digital centralizada de la comunidad Sawabona Shikoba (Exclusivo Administradores)")
        
        if rol_actual != "Administrador":
            st.error("🔒 Acceso Restringido: Este módulo requiere permisos de **Nivel 1 - Administrador**.")
        else:
            carpetas_defecto = [
                "📋 Formatos Clínicos y Administrativos",
                "📖 Manuales de Operación",
                "⚖️ Reglamentos y Normativas",
                "📑 Plantillas de Evaluación",
                "📁 Documentos Generales"
            ]
            
            tab_rep_list, tab_rep_up = st.tabs(["📚 Explorar Carpetas y Documentos", "📤 Subir Nuevo Documento"])
            
            with tab_rep_list:
                c_f1, c_f2 = st.columns([2, 2])
                with c_f1:
                    filter_carpeta = st.selectbox("📂 Filtrar por Carpeta", ["Todas las Carpetas"] + carpetas_defecto)
                    
                docs = listar_documentos_repositorio(filter_carpeta)
                
                if not docs:
                    st.info("No hay documentos guardados en esta carpeta aún.")
                else:
                    st.subheader(f"Total de Documentos: {len(docs)}")
                    
                    for doc_id, carp, n_arch, t_arch, desc, tam, f_sub, s_por in docs:
                        tam_kb = tam / 1024 if tam else 0
                        with st.expander(f"📄 {n_arch} ({carp}) | Subido el {f_sub} por {s_por}"):
                            st.write(f"**Descripción/Notas:** {desc if desc else 'Sin descripción'}")
                            st.write(f"**Tamaño:** {tam_kb:.1f} KB | **Tipo:** {t_arch}")
                            
                            c_d1, c_d2 = st.columns(2)
                            with c_d1:
                                d_data = obtener_documento_repositorio(doc_id)
                                if d_data and d_data[2]:
                                    st.download_button(
                                        label="📥 Descargar Archivo",
                                        data=d_data[2],
                                        file_name=n_arch,
                                        mime=t_arch if t_arch else "application/octet-stream",
                                        key=f"down_doc_{doc_id}"
                                    )
                            with c_d2:
                                if st.button("🗑️ Eliminar Archivo", key=f"del_doc_{doc_id}"):
                                    eliminar_documento_repositorio(doc_id)
                                    st.toast("Archivo eliminado", icon="🗑️")
                                    st.rerun()

            with tab_rep_up:
                st.subheader("Subir Archivo a la Nube")
                
                with st.form("form_upload_doc"):
                    up_carpeta = st.selectbox("📂 Carpeta Destino *", carpetas_defecto)
                    up_file = st.file_uploader("Seleccione el archivo (PDF, Word, Excel, Imagen, etc.) *", type=["pdf", "docx", "xlsx", "doc", "xls", "png", "jpg", "txt"])
                    up_desc = st.text_area("Notas o Descripción del Documento (ej. Versión 2026, Carta Responsiva)")
                    
                    btn_up_save = st.form_submit_button("📤 Subir Documento al Repositorio", use_container_width=True)
                    
                    if btn_up_save:
                        if not up_file:
                            st.error("Por favor seleccione un archivo para subir.")
                        else:
                            content_bytes = up_file.read()
                            guardar_documento_repositorio(up_carpeta, up_file.name, up_file.type, up_desc, content_bytes, st.session_state["username"])
                            st.toast("Documento guardado en la nube", icon="🎉")
                            st.success(f"✅ ¡Archivo **{up_file.name}** subido correctamente a la carpeta **{up_carpeta}**!")

    # =========================================================================
    # MODULO 10: CONFIGURACIÓN Y SEGURIDAD (EXCLUSIVO ADMINISTRADOR)
    # =========================================================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración del Sistema, Usuarios y Requisitos")
        
        if rol_actual != "Administrador":
            st.error("🔒 Acceso Restringido: Este módulo requiere permisos de **Nivel 1 - Administrador**.")
        else:
            tab_sys_usr, tab_sys_req = st.tabs(["👤 Gestión de Usuarios de Sistema & Roles", "📋 Configuración de Requisitos de Etapas"])
            
            with tab_sys_usr:
                st.subheader("Administración de Cuentas de Acceso y Roles")
                
                usrs_sys = listar_usuarios_sistema()
                st.table([{"Usuario": u[0], "Nombre Completo": u[1], "Rol / Nivel": u[2]} for u in usrs_sys])
                
                st.markdown("---")
                st.subheader("Crear / Modificar Usuario de Acceso")
                
                with st.form("form_sys_usr"):
                    c_su1, c_su2 = st.columns(2)
                    with c_su1:
                        su_user = st.text_input("Nombre de Usuario (Login) *")
                        su_pass = st.text_input("Contraseña (Dejar en blanco para conservar actual al editar)", type="password")
                    with c_su2:
                        su_nom = st.text_input("Nombre Completo del Personal *")
                        su_rol = st.selectbox("Rol / Nivel de Permiso *", [
                            "Administrador",
                            "Lectura y Escritura",
                            "Lectura"
                        ])
                        
                    btn_su_save = st.form_submit_button("💾 Guardar Usuario de Sistema")
                    if btn_su_save:
                        if not su_user.strip() or not su_nom.strip():
                            st.error("El usuario y el nombre completo son obligatorios.")
                        else:
                            guardar_usuario_sistema(su_user, su_pass, su_nom, su_rol)
                            st.toast("Usuario de sistema guardado", icon="🎉")
                            st.success(f"✅ ¡Usuario **{su_user}** guardado con rol **{su_rol}**!")
                            st.rerun()

            with tab_sys_req:
                st.subheader("Configuración de Requisitos por Etapa")
                
                etapas_config = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                sel_et_cfg = st.selectbox("Selecciona Etapa a Configurar", etapas_config)
                
                reqs_c = listar_requisitos_etapa(sel_et_cfg)
                for r_id, r_n, es_g in reqs_c:
                    c_rc1, c_rc2 = st.columns([4, 1])
                    with c_rc1:
                        st.write(f"📌 **{r_n}** {'(Grupo contado por sistema)' if es_g==1 else ''}")
                    with c_rc2:
                        if st.button("🗑️ Eliminar", key=f"del_req_{r_id}"):
                            eliminar_requisito_etapa(r_id)
                            st.toast("Requisito eliminado", icon="🗑️")
                            st.rerun()
                            
                st.markdown("---")
                with st.form("form_add_req"):
                    new_r_txt = st.text_input("Nuevo Requisito")
                    es_g_chk = st.checkbox("¿Es un grupo terapéutico de conteo automático?")
                    if st.form_submit_button("➕ Agregar Requisito"):
                        if new_r_txt.strip():
                            agregar_requisito_etapa(sel_et_cfg, new_r_txt, 1 if es_g_chk else 0)
                            st.toast("Requisito agregado", icon="🎉")
                            st.rerun()

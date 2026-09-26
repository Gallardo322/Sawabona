import streamlit as st
import sqlite3
import json
import hashlib
import os
import io
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

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios (Login y Roles)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    ''')
    
    # Migración de columna 'rol' en usuarios si no existe
    c.execute("PRAGMA table_info(usuarios)")
    cols_usuarios = [col[1] for col in c.fetchall()]
    if "rol" not in cols_usuarios:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
        except Exception:
            pass

    # Crear/Asegurar usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")

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
    
    # Migraciones para tabla 'pacientes'
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 4. Tabla de Medicamentos e Inventario por Paciente
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

    # 5. Tabla de Historial de Entregas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')

    # 6. Tabla de Grupos Terapéuticos
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

    # 7. Tabla de Historial de Etapas
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

    # 8. Tabla de Requisitos de Etapas
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')

    # 9. Tabla de Repositorio de Documentos
    c.execute('''
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
    ''')

    # 10. Tabla de Catálogo de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            concentracion TEXT,
            presentacion TEXT,
            descripcion TEXT
        )
    ''')

    # Poblar Requisitos Iniciales si está vacía
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

    # Poblar Catálogo Inicial de Medicamentos si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_base = [
            ('Omeprazol', '20 mg', 'Cápsulas', 'Protector gástrico'),
            ('Paracetamol', '500 mg', 'Comprimidos', 'Analgésico / Antipirético'),
            ('Ibuprofeno', '400 mg', 'Comprimidos', 'Antiinflamatorio'),
            ('Sertralina', '50 mg', 'Comprimidos', 'Antidepresivo ISRS'),
            ('Clonazepam', '2 mg', 'Comprimidos', 'Ansiolítico / Anticonvulsivo'),
            ('Quetiapina', '100 mg', 'Comprimidos', 'Antipsicótico / Estabilizador'),
            ('Complejo B', 'Multivitamínico', 'Comprimidos', 'Suplemento vitamínico')
        ]
        c.executemany('INSERT INTO catalogo_medicamentos (nombre, concentracion, presentacion, descripcion) VALUES (?, ?, ?, ?)', meds_base)

    conn.commit()
    conn.close()

# Inicializar Base de Datos al arrancar
init_db()

# --- FUNCIONES DE AUTENTICACIÓN Y ROLES ---
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
    user = str(st.session_state.get("username", "")).lower()
    rol = str(st.session_state.get("rol", ""))
    return user == "admin" or "administrador" in rol.lower() or "nivel 1" in rol.lower()

def puede_escribir():
    if es_admin():
        return True
    rol = str(st.session_state.get("rol", ""))
    return "nivel 2" in rol.lower() or "escritura" in rol.lower()

def es_solo_lectura():
    return not puede_escribir()

# --- FUNCIONES DE PACIENTES ---
def guardar_usuario_paciente(p_id, nombre, f_ingreso, f_nac, sexo, estatus, t_usuario, usuario_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (p_id,))
    ex = c.fetchone()
    if ex:
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre, f_ingreso, f_nac, sexo, estatus, t_usuario, f_act, p_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACOGIDA', ?, ?, ?, ?)
        ''', (p_id, nombre, f_ingreso, f_nac, sexo, estatus, t_usuario, f_ingreso, f_act, f_act, usuario_reg))
    conn.commit()
    conn.close()

def listar_pacientes_todos(solo_activos=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE estatus = "A" ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(p_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (p_id,))
    row = c.fetchone()
    conn.close()
    return row

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
        except Exception:
            pass
    siguiente = max(nums) + 1 if nums else 1
    return f"PAC-{siguiente:03d}"

def verificar_duplicado_nombre(nombre_completo, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nom_limpio = nombre_completo.strip().upper()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    for pid, pnom, est in rows:
        if paciente_id_actual and pid == paciente_id_actual:
            continue
        if pnom.strip().upper() == nom_limpio:
            return pid, pnom, est
    return None

# --- REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, f_act, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro and carpeta_filtro != "Todas las Carpetas":
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC', (carpeta_filtro,))
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

# --- CATÁLOGO DE MEDICAMENTOS ---
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
    c.execute('''
        INSERT OR REPLACE INTO catalogo_medicamentos (nombre, concentracion, presentacion, descripcion)
        VALUES (?, ?, ?, ?)
    ''', (nombre.strip(), concentracion.strip(), presentacion.strip(), descripcion.strip()))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()

# --- MANEJO DE ENTREVISTAS ---
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
def guardar_medicamentos_paciente(paciente_id, meds_list, obs, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE medicamentos 
            SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (meds_json, obs, f_act, usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, meds_json, obs, f_act, f_act, usuario))
    conn.commit()
    conn.close()

def obtener_medicamentos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion, usuario_registro FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0]), row[1], row[2], row[3]
    return [], "", None, None

def registrar_entrega_medicamentos(paciente_id, entregado_por, detalle_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_list, ensure_ascii=False)
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, f_act, entregado_por, detalle_json))
    conn.commit()
    conn.close()

# --- GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa, fecha_g, facilitador, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa, fecha_g, facilitador, datos_json, f_act, usuario))
    conn.commit()
    conn.close()

def obtener_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0],
            "tipo_grupo": r[1],
            "etapa": r[2],
            "fecha_grupo": r[3],
            "facilitador": r[4],
            "datos": json.loads(r[5]) if r[5] else {},
            "fecha_registro": r[6]
        })
    return res

def contar_grupos_etapa_paciente(paciente_id, etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT tipo_grupo, COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? GROUP BY tipo_grupo', (paciente_id, etapa))
    rows = c.fetchall()
    conn.close()
    counts = {"Terapia de Grupo": 0, "Aquí y Ahora": 0, "Feedback": 0}
    for tg, cnt in rows:
        if tg in counts:
            counts[tg] = cnt
    return counts

# --- GESTIÓN DE ETAPAS ---
ETAPAS_CONFIG = {
    "ACOGIDA": {"dias": 30, "siguiente": "IDENTIFICACIÓN"},
    "IDENTIFICACIÓN": {"dias": 60, "siguiente": "ELABORACIÓN"},
    "ELABORACIÓN": {"dias": 60, "siguiente": "CONSOLIDACIÓN"},
    "CONSOLIDACIÓN": {"dias": 30, "siguiente": "SERVICIO SOCIAL"},
    "SERVICIO SOCIAL": {"dias": 30, "siguiente": "GRADUADO"}
}

def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ?', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def promover_paciente_etapa(paciente_id, etapa_origen, etapa_destino, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        UPDATE pacientes 
        SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (etapa_destino, f_act, f_act, paciente_id))
    
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_origen, etapa_destino, f_act, usuario))
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?', (hermano_mayor_id, f_act, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?', (f_act, f_act, paciente_id))
    conn.commit()
    conn.close()

# --- GENERACIÓN DE PDF ---
def limpiar_texto(texto):
    if not texto:
        return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

class PDFReporte(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, limpiar_texto('🌱 SAWABONA SHIKOBA - COMUNIDAD TERAPÉUTICA'), 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 5, limpiar_texto('Sistema de Control Clínico y Seguimiento Individual'), 0, 1, 'C')
        self.line(10, 23, 200, 23)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_grupos_paciente(paciente_info, grupos):
    pdf = PDFReporte()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    
    p_id, p_nom, f_ing, f_nac, sexo, estatus, t_user, etapa, f_etapa, h_may, f_suelta = paciente_info
    
    pdf.cell(0, 7, limpiar_texto(f'EXPEDIENTE DE GRUPOS TERAPÉUTICOS - {p_nom} ({p_id})'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, limpiar_texto(f'Etapa Actual: {etapa} | Fecha Ingreso: {f_ing}'), 0, 1, 'L')
    pdf.ln(4)
    
    if not grupos:
        pdf.cell(0, 8, limpiar_texto('No hay sesiones de grupos terapéuticos registradas para este usuario.'), 0, 1, 'L')
    else:
        for g in grupos:
            pdf.set_fill_color(230, 240, 250)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(0, 7, limpiar_texto(f'• {g["tipo_grupo"]} - Fecha: {g["fecha_grupo"]} (Etapa: {g["etapa"]})'), 1, 1, 'L', True)
            pdf.set_font('Arial', '', 9)
            pdf.cell(0, 5, limpiar_texto(f'  Facilitador: {g["facilitador"]} | Registrado: {g["fecha_registro"]}'), 0, 1, 'L')
            
            d = g["datos"]
            for k, v in d.items():
                if v and str(v).strip():
                    pdf.set_font('Arial', 'B', 9)
                    pdf.cell(0, 5, limpiar_texto(f'  {k}:'), 0, 1, 'L')
                    pdf.set_font('Arial', '', 9)
                    pdf.multi_cell(0, 4, limpiar_texto(f'    {v}'))
            pdf.ln(3)
            
    return pdf.output(dest='S').encode('latin-1')

# --- CONTROL DE SESIÓN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = "Nivel 1 - Administrador"

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema de Control y Comunidad Terapéutica</h3>", unsafe_allow_html=True)
    st.write("")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔑 Iniciar Sesión")
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit:
                usuario_valido = verificar_login(user_input, pass_input)
                if usuario_valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usuario_valido[0]
                    st.session_state["nombre_completo"] = usuario_valido[1]
                    st.session_state["rol"] = usuario_valido[2] if len(usuario_valido) > 2 and usuario_valido[2] else "Nivel 1 - Administrador"
                    st.success(f"¡Bienvenido {usuario_valido[1]}!")
                    st.toast("🎉 ¡Sesión iniciada correctamente!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL Y NAVEGACIÓN ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.caption(f"🛡️ **Rol**: {st.session_state['rol']}")
    
    opciones_menu = [
        "📝 Nueva Entrevista / Editar",
        "🔍 Buscar y Listar Pacientes",
        "👤 Registro y Edición de Usuarios",
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "💊 Control de Medicamentos y Dosis",
        "🚚 Entrega de Medicamentos"
    ]
    
    # Módulos Exclusivos para Administrador
    if es_admin():
        opciones_menu.append("📁 Repositorio de Documentos")
        opciones_menu.append("⚙️ Configuración & Seguridad")
        opciones_menu.append("📦 Respaldo y Restauración")
        
    menu = st.sidebar.radio("Navegación", opciones_menu)
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 1: NUEVA ENTREVISTA / EDITAR ---
    if menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        pacientes_lista = listar_pacientes_todos(solo_activos=False)
        opciones_pac = ["-- Crear Folio Nuevo / Teclear Folio --"] + [f"{p[0]} - {p[1]}" for p in pacientes_lista]
        
        pac_sel = st.selectbox("🔑 SELECCIONAR PACIENTE REGISTRADO O TECLEAR FOLIO", opciones_pac)
        
        if pac_sel.startswith("--"):
            paciente_id_input = st.text_input("Folio o Número de Paciente *", value="").strip().upper()
        else:
            paciente_id_input = pac_sel.split(" - ")[0]
            
        datos_existentes = {}
        if paciente_id_input:
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if datos_cargados:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                datos_existentes = datos_cargados
            else:
                st.info("🆕 Folio nuevo. Complete los datos para registrar un nuevo expediente.")

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
                    dependientes_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], 
                                                     index=1 if datos_existentes.get("dependientes_flag") == "SÍ" else 0)
                    dependientes_quienes = st.text_input("¿Quiénes o quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
                with c2:
                    pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"],
                                               index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
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
                        lugar_val = st.text_input("Lugar Consumo", value=s_data.get("lugar", ""), key=f"lugar_{sust}")
                        
                    tabla_consumo_input[sust] = {
                        "consumo": "SÍ" if c_val else "NO",
                        "forma": forma_val, "frecuencia": frec_val, "cantidad": cant_val,
                        "edad_inicio": edad_val, "lugar": lugar_val
                    }

            with tab3:
                st.subheader("Evaluación de Disposición al Cambio")
                motivo_consulta = st.text_area("Motivo de consulta principal", value=datos_existentes.get("motivo_consulta", ""))
                intentos_previos = st.text_area("Intentos previos de abstinencia y tratamiento", value=datos_existentes.get("intentos_previos", ""))

            with tab4:
                st.subheader("Entorno Familiar y Factores de Riesgo")
                apoyo_familiar = st.text_area("Red de apoyo familiar y social", value=datos_existentes.get("apoyo_familiar", ""))
                riesgos_observados = st.text_area("Riesgos identificados (violencia, salud, legal)", value=datos_existentes.get("riesgos_observados", ""))

            with tab5:
                st.subheader("Observaciones Finales y Firma del Evaluador")
                obs_finales = st.text_area("Observaciones clínicas finales", value=datos_existentes.get("obs_finales", ""))
                evaluador_nombre = st.text_input("Nombre del Evaluador / Consejero", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))

            disabled_btn = es_solo_lectura()
            btn_guardar_e = st.form_submit_button("💾 Guardar Expediente de Consejería", use_container_width=True, disabled=disabled_btn)
            
            if btn_guardar_e:
                if not paciente_id_input:
                    st.error("⚠️ El Folio del Paciente es obligatorio.")
                else:
                    datos_completos = {
                        "dependientes_flag": dependientes_flag, "dependientes_quienes": dependientes_quienes,
                        "pareja_flag": pareja_flag, "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input, "motivo_consulta": motivo_consulta,
                        "intentos_previos": intentos_previos, "apoyo_familiar": apoyo_familiar,
                        "riesgos_observados": riesgos_observados, "obs_finales": obs_finales,
                        "evaluador_nombre": evaluador_nombre
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente!")
                    st.toast("🎉 ¡Expediente de consejería guardado exitosamente!")

    # --- SECCIÓN 2: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro General de Residentes")
        pacientes = listar_pacientes_todos(solo_activos=False)
        
        if not pacientes:
            st.warning("No hay pacientes registrados aún en el sistema.")
        else:
            st.subheader(f"Total de registros: {len(pacientes)}")
            for pac in pacientes:
                pid, pnom, fing, fnac, sexo, est, tuser, etapa, fetapa, hmay, fsuelta = pac
                with st.expander(f"👤 {pnom} ({pid}) - Etapa: {etapa} - Status: {'ACTIVO' if est == 'A' else 'BLOQUEADO'}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Tipo**: {tuser}")
                        st.write(f"**Fecha Ingreso**: {fing}")
                        st.write(f"**Fecha Nacimiento**: {fnac}")
                        st.write(f"**Sexo**: {sexo}")
                    with c2:
                        st.write(f"**Etapa Actual**: {etapa}")
                        st.write(f"**Inicio de Etapa**: {fetapa}")
                        if hmay:
                            st.write(f"**Hermano Mayor ID**: {hmay}")
                            st.write(f"**Suelta Hermano**: {fsuelta if fsuelta else 'Pendiente'}")

    # --- SECCIÓN 3: REGISTRO Y EDICIÓN DE USUARIOS ---
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Usuarios / Pacientes")
        
        modo_u = st.radio("Acción a realizar", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"])
        
        pacientes_todos = listar_pacientes_todos(solo_activos=False)
        
        if modo_u == "✏️ Modificar / Editar Usuario Existente":
            if not pacientes_todos:
                st.warning("No hay usuarios registrados para editar.")
                st.stop()
            opciones_edit = [f"{p[0]} - {p[1]}" for p in pacientes_todos]
            sel_u = st.selectbox("🔑 Selecciona el Usuario a Editar", opciones_edit)
            pid_edit = sel_u.split(" - ")[0]
            p_data = obtener_paciente_por_id(pid_edit)
            
            p_id_val, p_nom_val, p_fing_val, p_fnac_val, p_sexo_val, p_est_val, p_tipo_val, p_etapa_val, p_fetapa_val, p_hmay_val, p_fsuelta_val = p_data
        else:
            p_id_val = generar_siguiente_folio()
            p_nom_val, p_fing_val, p_fnac_val, p_sexo_val, p_est_val, p_tipo_val = "", str(date.today()), "2000-01-01", "MASCULINO", "A", "Paciente"

        form_key = f"form_u_{p_id_val}_{modo_u}"
        with st.form(form_key):
            st.subheader(f"Datos del Usuario ({p_id_val})")
            c1, c2 = st.columns(2)
            with c1:
                u_folio = st.text_input("Folio ID", value=p_id_val, disabled=True)
                u_nombre = st.text_input("Nombre Completo *", value=p_nom_val)
                u_tipo = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if p_tipo_val == "Paciente" else 1)
                u_sexo = st.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if p_sexo_val == "MASCULINO" else 1)
            with c2:
                u_fingreso = st.text_input("Fecha de Ingreso (YYYY-MM-DD)", value=p_fing_val if p_fing_val else str(date.today()))
                u_fnac = st.text_input("Fecha de Nacimiento (YYYY-MM-DD)", value=p_fnac_val if p_fnac_val else "2000-01-01")
                u_estatus = st.selectbox("Estatus", ["A - Activo", "B - Bloqueado / Inactivo"], index=0 if p_est_val == "A" else 1)

            btn_save_u = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True, disabled=es_solo_lectura())
            
            if btn_save_u:
                if not u_nombre.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                else:
                    est_code = "A" if u_estatus.startswith("A") else "B"
                    dup = verificar_duplicado_nombre(u_nombre, p_id_val if modo_u != "🆕 Registrar Nuevo Usuario" else None)
                    if dup:
                        st.error(f"❌ Ya existe un usuario registrado con el nombre '{dup[1]}' bajo el Folio {dup[0]}.")
                    else:
                        guardar_usuario_paciente(p_id_val, u_nombre.strip(), u_fingreso, u_fnac, u_sexo, est_code, u_tipo, st.session_state["username"])
                        st.success(f"✅ Usuario **{u_nombre}** guardado exitosamente.")
                        st.toast(f"🎉 ¡Usuario {u_nombre} guardado con éxito!")

    # --- SECCIÓN 4: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas de Tratamiento (Sawabona Shikoba)")
        
        pacientes_activos = listar_pacientes_todos(solo_activos=True)
        pacientes_solo = [p for p in pacientes_activos if p[6] == "Paciente"]
        
        if not pacientes_solo:
            st.info("No hay pacientes activos registrados en proceso de etapas.")
        else:
            opciones_et = [f"{p[0]} - {p[1]} (Etapa: {p[7]})" for p in pacientes_solo]
            sel_e = st.selectbox("🔑 Selecciona un Paciente para Revisar Avance", opciones_et)
            p_id_e = sel_e.split(" - ")[0]
            p_data = obtener_paciente_por_id(p_id_e)
            
            p_id, p_nom, f_ing, f_nac, sexo, est, tuser, etapa, f_etapa, h_may, f_suelta = p_data
            
            st.markdown("---")
            st.subheader(f"📊 Estado del Proceso: {p_nom} ({p_id})")
            
            # Cálculo de Días
            try:
                d_ingreso = datetime.strptime(f_ing, "%Y-%m-%d").date()
                dias_totales = (date.today() - d_ingreso).days
            except Exception:
                dias_totales = 0
                
            try:
                d_etapa = datetime.strptime(f_etapa.split(" ")[0], "%Y-%m-%d").date()
                dias_en_etapa = (date.today() - d_etapa).days
            except Exception:
                dias_en_etapa = 0

            dias_req_etapa = ETAPAS_CONFIG.get(etapa, {}).get("dias", 30)
            siguiente_etapa = ETAPAS_CONFIG.get(etapa, {}).get("siguiente", "GRADUADO")
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Etapa Actual", etapa)
            with col_b:
                st.metric("Días en Etapa Actual", f"{dias_en_etapa} / {dias_req_etapa} días")
            with col_c:
                st.metric("Días Totales en Clínica", f"{dias_totales} días")
                
            pct = min(1.0, max(0.0, dias_en_etapa / dias_req_etapa if dias_req_etapa > 0 else 1.0))
            st.progress(pct, text=f"Avance de Tiempo en {etapa}: {pct*100:.1f}%")
            
            # Alertas de Días o Rezago
            if dias_en_etapa >= (dias_req_etapa - 5) and dias_en_etapa <= dias_req_etapa:
                st.warning(f"⚠️ **ALERTA PREVENTIVA**: {p_nom} está a {dias_req_etapa - dias_en_etapa} días de cumplir el tiempo de su etapa {etapa}. Solicitar revisión de comité.")
            elif dias_en_etapa > dias_req_etapa:
                st.error(f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO**: {p_nom} ha superado los {dias_req_etapa} días en la etapa {etapa} por +{dias_en_etapa - dias_req_etapa} días.")

            st.markdown("---")
            tab_req, tab_hermano = st.tabs(["📋 Checklist de Requisitos de Etapa", "🤝 Hermano Menor & Mayor"])
            
            with tab_req:
                st.subheader(f"Checklist para Cambio a {siguiente_etapa}")
                reqs = obtener_requisitos_etapa(etapa)
                grupos_counts = contar_grupos_etapa_paciente(p_id, etapa)
                
                reqs_completados = 0
                total_reqs = len(reqs)
                
                for req_id, req_txt, es_grupo in reqs:
                    if es_grupo == 1:
                        req_cumplido = False
                        if "Aquí y Ahora" in req_txt and grupos_counts["Aquí y Ahora"] >= 4:
                            req_cumplido = True
                        elif "Terapia de Grupo" in req_txt and grupos_counts["Terapia de Grupo"] >= 4:
                            req_cumplido = True
                        elif "Feedback" in req_txt and grupos_counts["Feedback"] >= 4:
                            req_cumplido = True
                        elif "2 Grupos" in req_txt:
                            if "Aquí y Ahora" in req_txt and grupos_counts["Aquí y Ahora"] >= 2: req_cumplido = True
                            if "Terapia de Grupo" in req_txt and grupos_counts["Terapia de Grupo"] >= 2: req_cumplido = True
                            if "Feedback" in req_txt and grupos_counts["Feedback"] >= 2: req_cumplido = True
                            
                        st.checkbox(f"🗣️ {req_txt} (Registrados en sistema: {grupos_counts.get('Terapia de Grupo' if 'Terapia' in req_txt else 'Aquí y Ahora' if 'Aquí' in req_txt else 'Feedback', 0)})", value=req_cumplido, disabled=True)
                        if req_cumplido: reqs_completados += 1
                    else:
                        c_user = st.checkbox(f"📌 {req_txt}", key=f"req_{p_id}_{req_id}")
                        if c_user: reqs_completados += 1

                st.write("")
                listo_promover = (reqs_completados == total_reqs and total_reqs > 0 and dias_en_etapa >= (dias_req_etapa - 5))
                btn_promover = st.button(f"🚀 Promover a {siguiente_etapa}", disabled=not listo_promover or es_solo_lectura())
                
                if btn_promover:
                    promover_paciente_etapa(p_id, etapa, siguiente_etapa, st.session_state["username"])
                    st.success(f"🎉 ¡{p_nom} fue promovido exitosamente a {siguiente_etapa}!")
                    st.toast(f"🎉 ¡{p_nom} promovido a {siguiente_etapa}!")
                    st.rerun()

            with tab_hermano:
                st.subheader("Acompañamiento de Hermano Mayor (ACOGIDA)")
                if etapa == "ACOGIDA":
                    st.info("Los primeros 15 días en Acogida el usuario cuenta con un Hermano Mayor de acompañamiento.")
                    posibles_mayores = [p for p in pacientes_activos if p[0] != p_id]
                    opciones_m = ["-- Seleccionar Hermano Mayor --"] + [f"{p[0]} - {p[1]}" for p in posibles_mayores]
                    
                    hmay_sel = st.selectbox("Asignar Hermano Mayor", opciones_m)
                    if st.button("💾 Guardar Hermano Mayor", disabled=es_solo_lectura()):
                        if not hmay_sel.startswith("--"):
                            hm_id = hmay_sel.split(" - ")[0]
                            asignar_hermano_mayor(p_id, hm_id)
                            st.success("Hermano mayor asignado correctamente.")
                            st.toast("🎉 Hermano mayor asignado!")
                            st.rerun()
                            
                    if h_may:
                        st.write(f"**Hermano Mayor Actual**: {h_may}")
                        st.write(f"**Fecha de Suelta**: {f_suelta if f_suelta else 'Pendiente'}")
                        if st.button("🔓 Registrar Suelta de Hermano Mayor", disabled=es_solo_lectura()):
                            registrar_suelta_hermano(p_id)
                            st.success("Se registró la suelta del hermano mayor.")
                            st.toast("🎉 Suelta de hermano mayor registrada!")
                            st.rerun()
                else:
                    st.write("El acompañamiento de Hermano Mayor aplica principalmente para la Etapa 1 (ACOGIDA).")

    # --- SECCIÓN 5: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        pacientes_activos = listar_pacientes_todos(solo_activos=True)
        pacientes_solo = [p for p in pacientes_activos if p[6] == "Paciente"]
        
        with tab_reg_g:
            if not pacientes_solo:
                st.warning("No hay pacientes activos para registrar grupos.")
            else:
                opciones_g = [f"{p[0]} - {p[1]} (Etapa: {p[7]})" for p in pacientes_solo]
                sel_p_g = st.selectbox("Seleccionar Paciente *", opciones_g)
                pid_g = sel_p_g.split(" - ")[0]
                p_data_g = obtener_paciente_por_id(pid_g)
                
                t_grupo = st.selectbox("Tipo de Grupo *", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                f_grupo = st.text_input("Fecha del Grupo (YYYY-MM-DD)", value=str(date.today()))
                facilitador_g = st.text_input("Facilitador / Staff a cargo", value=st.session_state["nombre_completo"])
                
                with st.form("form_grupo_terapeuto"):
                    st.subheader(f"Captura de {t_grupo} - {p_data_g[1]}")
                    
                    datos_g = {}
                    if t_grupo in ["Terapia de Grupo", "Aquí y Ahora"]:
                        datos_g["Compartimiento"] = st.text_area("Compartimiento (Texto largo)")
                        datos_g["Observaciones"] = st.text_area("Observaciones")
                        datos_g["Devoluciones"] = st.text_area("Devoluciones")
                        datos_g["Como_se_queda_y_compromiso"] = st.text_area("¿Cómo se queda y a qué se compromete?")
                    else:
                        datos_g["Logros"] = st.text_area("Logros")
                        datos_g["Dificultades"] = st.text_area("Dificultades")
                        datos_g["Observaciones"] = st.text_area("Observaciones")
                        datos_g["Devoluciones"] = st.text_area("Devoluciones")
                        datos_g["Como_se_queda_y_compromiso"] = st.text_area("¿Cómo se queda y a qué se compromete?")

                    btn_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True, disabled=es_solo_lectura())
                    
                    if btn_g:
                        guardar_grupo_terapeuto(pid_g, t_grupo, p_data_g[7], f_grupo, facilitador_g, datos_g, st.session_state["username"])
                        st.success(f"✅ Sesión de {t_grupo} registrada exitosamente para **{p_data_g[1]}**.")
                        st.toast("🎉 ¡Grupo terapéutico registrado!")

        with tab_hist_g:
            if pacientes_solo:
                opciones_hist = [f"{p[0]} - {p[1]}" for p in pacientes_solo]
                sel_hist = st.selectbox("Seleccionar Paciente para Consulta", opciones_hist)
                pid_hist = sel_hist.split(" - ")[0]
                p_data_h = obtener_paciente_por_id(pid_hist)
                
                grupos_p = obtener_grupos_paciente(pid_hist)
                st.subheader(f"Historial de Grupos ({len(grupos_p)} sesiones)")
                
                pdf_bytes = generar_pdf_grupos_paciente(p_data_h, grupos_p)
                st.download_button("🖨️ Descargar Expediente de Grupos en PDF", data=pdf_bytes, file_name=f"Grupos_{pid_hist}.pdf", mime="application/pdf")
                
                for g in grupos_p:
                    with st.expander(f"🗣️ {g['tipo_grupo']} - {g['fecha_grupo']} (Etapa: {g['etapa']})"):
                        st.write(f"**Facilitador**: {g['facilitador']}")
                        for k, v in g["datos"].items():
                            st.write(f"**{k}**: {v}")

    # --- SECCIÓN 6: CONTROL DE MEDICAMENTOS Y DOSIS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Esquema de Dosis")
        
        tab_p_med, tab_cat_med, tab_rep_med = st.tabs(["💊 Esquema por Paciente", "📚 Catálogo de Medicamentos", "📊 Consumo Global"])
        
        pacientes_activos = listar_pacientes_todos(solo_activos=True)
        
        with tab_p_med:
            if not pacientes_activos:
                st.info("No hay pacientes activos para asignar esquema de medicamentos.")
            else:
                opciones_m = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
                sel_m = st.selectbox("Seleccionar Residentes *", opciones_m)
                pid_m = sel_m.split(" - ")[0]
                p_data_m = obtener_paciente_por_id(pid_m)
                
                meds_cargados, obs_med, _, _ = obtener_medicamentos_paciente(pid_m)
                
                catalogo = obtener_catalogo_medicamentos()
                nombres_cat = [f"{m[1]} ({m[2]} - {m[3]})" for m in catalogo] if catalogo else ["Sin catálogo"]
                
                st.subheader(f"Esquema de Dosis Diario - {p_data_m[1]}")
                
                with st.form("form_meds_paciente"):
                    meds_input = []
                    for i in range(5):
                        st.markdown(f"**Medicamento #{i+1}**")
                        c1, c2, c3, c4, c5 = st.columns([2.5, 1, 1, 1, 1.5])
                        m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                        
                        with c1:
                            m_nom = st.selectbox(f"Medicamento {i+1}", ["-- Ninguno --"] + nombres_cat, key=f"cat_m_{i}")
                        with c2:
                            d_man = st.number_input("Mañana", min_value=0.0, step=0.5, value=float(m_prev.get("manana", 0)), key=f"dm_{i}")
                        with c3:
                            d_tar = st.number_input("Tarde", min_value=0.0, step=0.5, value=float(m_prev.get("tarde", 0)), key=f"dt_{i}")
                        with c4:
                            d_noc = st.number_input("Noche", min_value=0.0, step=0.5, value=float(m_prev.get("noche", 0)), key=f"dn_{i}")
                        with c5:
                            e_fis = st.number_input("Existencia", min_value=0.0, step=1.0, value=float(m_prev.get("existencia", 0)), key=f"ex_{i}")
                            
                        if not m_nom.startswith("--"):
                            meds_input.append({
                                "nombre": m_nom, "manana": d_man, "tarde": d_tar, "noche": d_noc, "existencia": e_fis
                            })

                    obs_txt = st.text_area("Observaciones Medicamentosas / Alergias", value=obs_med)
                    btn_m = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True, disabled=es_solo_lectura())
                    
                    if btn_m:
                        guardar_medicamentos_paciente(pid_m, meds_input, obs_txt, st.session_state["username"])
                        st.success("✅ Esquema de medicamentos guardado correctamente.")
                        st.toast("🎉 ¡Esquema de medicamentos guardado!")

        with tab_cat_med:
            st.subheader("📚 Catálogo Central de Medicamentos")
            if puede_escribir():
                with st.form("form_add_cat"):
                    st.write("Agregar o Actualizar Medicamento en Catálogo")
                    c1, c2, c3 = st.columns(3)
                    with c1: c_nom = st.text_input("Nombre Comercial / Genérico *")
                    with c2: c_conc = st.text_input("Concentración (ej. 500 mg)")
                    with c3: c_pres = st.selectbox("Presentación", ["Comprimidos", "Cápsulas", "Gotas", "Jarabe", "Inyectable", "Otro"])
                    c_desc = st.text_input("Descripción / Indicaciones")
                    
                    if st.form_submit_button("💾 Agregar al Catálogo"):
                        if c_nom.strip():
                            guardar_medicamento_catalogo(c_nom, c_conc, c_pres, c_desc)
                            st.success("Medicamento agregado al catálogo.")
                            st.rerun()

            cats = obtener_catalogo_medicamentos()
            for cm in cats:
                st.write(f"💊 **{cm[1]}** | Concentración: {cm[2]} | Presentación: {cm[3]} | *{cm[4]}*")

        with tab_rep_med:
            st.subheader("📊 Consumo Global de Medicamentos en la Clínica")
            cats = obtener_catalogo_medicamentos()
            if cats:
                sel_m_rep = st.selectbox("Seleccionar Medicamento del Catálogo para Reporte", [m[1] for m in cats])
                
                total_diario = 0.0
                pacientes_consumidores = []
                
                for p in pacientes_activos:
                    p_id, p_nom = p[0], p[1]
                    m_list, _, _, _ = obtener_medicamentos_paciente(p_id)
                    for m in m_list:
                        if sel_m_rep in m.get("nombre", ""):
                            d_diaria = m.get("manana", 0) + m.get("tarde", 0) + m.get("noche", 0)
                            total_diario += d_diaria
                            pacientes_consumidores.append((p_id, p_nom, d_diaria, m.get("existencia", 0)))
                            
                st.metric("Consumo Diario Acumulado en la Clínica", f"{total_diario} unidades/día")
                st.write("**Pacientes que lo consumen:**")
                for pid, pnom, dd, ex in pacientes_consumidores:
                    st.write(f"• **{pnom}** ({pid}) - Dosis diaria: {dd} unidades | Stock individual: {ex}")

    # --- SECCIÓN 7: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Registro de Entrega de Medicamentos (Almacén)")
        
        pacientes_activos = listar_pacientes_todos(solo_activos=True)
        if not pacientes_activos:
            st.info("No hay pacientes activos.")
        else:
            opciones_e = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
            sel_e = st.selectbox("Seleccionar Paciente para Entrega", opciones_e)
            pid_e = sel_e.split(" - ")[0]
            p_data_e = obtener_paciente_por_id(pid_e)
            
            meds_e, _, _, _ = obtener_medicamentos_paciente(pid_e)
            
            if not meds_e:
                st.warning("Este residente no tiene medicamentos registrados en su esquema.")
            else:
                with st.form("form_entrega_meds"):
                    st.subheader(f"Registro de Entrega - {p_data_e[1]}")
                    
                    entregas_confirmadas = []
                    for i, m in enumerate(meds_e):
                        d_diaria = m.get("manana", 0) + m.get("tarde", 0) + m.get("noche", 0)
                        c1, c2, c3 = st.columns([3, 1.5, 1.5])
                        with c1:
                            st.write(f"💊 **{m['nombre']}** (Stock actual: {m['existencia']})")
                        with c2:
                            cant_e = st.number_input(f"Cantidad a entregar", min_value=0.0, value=float(d_diaria), key=f"cant_e_{i}")
                        with c3:
                            st.write(f"Dosis habitual: {d_diaria}")
                            
                        if cant_e > 0:
                            entregas_confirmadas.append({"nombre": m['nombre'], "cantidad": cant_e, "existencia_anterior": m['existencia']})

                    btn_e = st.form_submit_button("📦 Confirmar Entrega y Descontar Stock", use_container_width=True, disabled=es_solo_lectura())
                    
                    if btn_e:
                        # Descontar stock
                        for m_item in meds_e:
                            for ec in entregas_confirmadas:
                                if m_item["nombre"] == ec["nombre"]:
                                    m_item["existencia"] = max(0.0, m_item["existencia"] - ec["cantidad"])
                                    
                        guardar_medicamentos_paciente(pid_e, meds_e, "", st.session_state["username"])
                        registrar_entrega_medicamentos(pid_e, st.session_state["username"], entregas_confirmadas)
                        
                        st.success("✅ Entrega registrada exitosamente y stock actualizado.")
                        st.toast("🎉 ¡Entrega registrada correctamente!")

    # --- SECCIÓN 8: REPOSITORIO DE DOCUMENTOS (EXCLUSIVO ADMIN) ---
    elif menu == "📁 Repositorio de Documentos":
        if not es_admin():
            st.error("⛔ Acceso denegado: Este módulo es exclusivo para el Administrador del Sistema.")
            st.stop()
            
        st.title("📁 Repositorio de Documentos y Formatos")
        
        carpetas_def = [
            "Todas las Carpetas",
            "📋 Formatos Clínicos y Administrativos",
            "📖 Manuales de Operación",
            "⚖️ Reglamentos y Normativas",
            "📑 Plantillas de Evaluación",
            "📁 Documentos Generales"
        ]
        
        tab_ver_doc, tab_sub_doc = st.tabs(["📥 Consultar y Descargar Documentos", "📤 Subir Nuevo Documento"])
        
        with tab_sub_doc:
            st.subheader("Subir Archivo al Repositorio")
            with st.form("form_subir_doc"):
                carp_sel = st.selectbox("Carpeta / Categoría *", carpetas_def[1:])
                file_up = st.file_uploader("Seleccionar Archivo (PDF, Word, Excel, Imagen) *", type=["pdf", "docx", "xlsx", "png", "jpg", "txt"])
                desc_up = st.text_input("Descripción o Notas del Archivo")
                
                if st.form_submit_button("📤 Subir Documento a la Nube"):
                    if file_up is not None:
                        b_data = file_up.read()
                        guardar_documento_repositorio(carp_sel, file_up.name, file_up.type, b_data, desc_up, st.session_state["username"])
                        st.success(f"✅ Documento '{file_up.name}' subido correctamente a '{carp_sel}'.")
                        st.toast("🎉 Documento subido con éxito!")
                        st.rerun()

        with tab_ver_doc:
            c_filtro = st.selectbox("Filtrar por Carpeta", carpetas_def)
            docs = obtener_documentos_repositorio(c_filtro if c_filtro != "Todas las Carpetas" else None)
            
            st.subheader(f"Documentos Disponibles ({len(docs)})")
            for d_id, d_carp, d_nom, d_mime, d_blob, d_desc, d_fecha, d_user in docs:
                with st.expander(f"📄 {d_nom} [{d_carp}] - Subido: {d_fecha}"):
                    st.write(f"**Descripción**: {d_desc if d_desc else 'Sin descripción'}")
                    st.write(f"**Subido por**: {d_user}")
                    
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.download_button("📥 Descargar Archivo", data=d_blob, file_name=d_nom, mime=d_mime, key=f"dl_{d_id}")
                    with c2:
                        if st.button("🗑️ Eliminar Documento", key=f"del_doc_{d_id}"):
                            eliminar_documento_repositorio(d_id)
                            st.success("Documento eliminado.")
                            st.rerun()

    # --- SECCIÓN 9: CONFIGURACIÓN & SEGURIDAD (EXCLUSIVO ADMIN) ---
    elif menu == "⚙️ Configuración & Seguridad":
        if not es_admin():
            st.error("⛔ Acceso denegado: Este módulo es exclusivo para el Administrador del Sistema.")
            st.stop()
            
        st.title("⚙️ Configuración de Seguridad y Roles de Usuario")
        
        tab_u_sys, tab_req_sys, tab_pass_sys = st.tabs(["👤 Usuarios del Sistema y Roles", "🎯 Administrar Requisitos de Etapas", "🔑 Mi Contraseña"])
        
        with tab_u_sys:
            st.subheader("Usuarios con Acceso a la Aplicación")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT username, nombre_completo, rol FROM usuarios')
            users_db = c.fetchall()
            conn.close()
            
            for u_un, u_nom, u_rol in users_db:
                st.write(f"• **{u_nom}** (`{u_un}`) - Rol: **{u_rol}**")
                
            st.markdown("---")
            st.subheader("Crear o Actualizar Usuario del Sistema")
            with st.form("form_user_sys"):
                c1, c2 = st.columns(2)
                with c1:
                    new_un = st.text_input("Nombre de Usuario (Login) *")
                    new_pass = st.text_input("Contraseña *", type="password")
                with c2:
                    new_nom = st.text_input("Nombre Completo *")
                    new_rol = st.selectbox("Rol y Nivel de Acceso", [
                        "Nivel 1 - Administrador",
                        "Nivel 2 - Lectura y Escritura",
                        "Nivel 3 - Solo Lectura"
                    ])
                    
                if st.form_submit_button("💾 Guardar Usuario del Sistema"):
                    if new_un.strip() and new_pass.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        p_hash = hash_pass(new_pass)
                        c.execute('''
                            INSERT OR REPLACE INTO usuarios (username, password_hash, nombre_completo, rol)
                            VALUES (?, ?, ?, ?)
                        ''', (new_un.strip(), p_hash, new_nom.strip(), new_rol))
                        conn.commit()
                        conn.close()
                        st.success(f"Usuario '{new_un}' guardado correctamente.")
                        st.toast("🎉 Usuario del sistema guardado!")
                        st.rerun()

        with tab_req_sys:
            st.subheader("Configuración Dinámica de Requisitos por Etapa")
            e_sel_cfg = st.selectbox("Seleccionar Etapa a Configurar", list(ETAPAS_CONFIG.keys()))
            
            reqs_e = obtener_requisitos_etapa(e_sel_cfg)
            st.write("**Requisitos Actuales:**")
            for r_id, r_txt, es_g in reqs_e:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"• {r_txt} {'(Grupal)' if es_g == 1 else ''}")
                with c2:
                    if st.button("🗑️ Eliminar", key=f"del_r_{r_id}"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (r_id,))
                        conn.commit()
                        conn.close()
                        st.success("Requisito eliminado.")
                        st.rerun()
                        
            st.markdown("---")
            with st.form("form_add_req"):
                st.write("Agregar Nuevo Requisito a la Etapa")
                new_req_txt = st.text_input("Descripción del Requisito")
                es_g_val = st.checkbox("¿Es un grupo terapéutico contabilizable?")
                if st.form_submit_button("➕ Agregar Requisito"):
                    if new_req_txt.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', (e_sel_cfg, new_req_txt.strip(), 1 if es_g_val else 0))
                        conn.commit()
                        conn.close()
                        st.success("Requisito agregado.")
                        st.rerun()

        with tab_pass_sys:
            st.subheader("Cambiar Mi Contraseña")
            with st.form("form_change_my_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_new = st.text_input("Nueva Contraseña", type="password")
                
                if st.form_submit_button("🔑 Actualizar Contraseña"):
                    if verificar_login(st.session_state["username"], p_act):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(p_new), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("Contraseña actualizada exitosamente.")
                    else:
                        st.error("Contraseña actual incorrecta.")

    # --- SECCIÓN 10: RESPALDO Y RESTAURACIÓN (EXCLUSIVO ADMIN) ---
    elif menu == "📦 Respaldo y Restauración":
        if not es_admin():
            st.error("⛔ Acceso denegado: Este módulo es exclusivo para el Administrador del Sistema.")
            st.stop()
            
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        tab_back, tab_rest = st.tabs(["📥 Descargar Respaldo (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_back:
            st.subheader("Descargar Copia de Seguridad de Toda la Información")
            st.write("Guarda un archivo `.db` con todos los residentes, grupos, medicamentos y documentos.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                fn_back = f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                st.download_button("📥 Descargar Respaldo de Base de Datos", data=db_bytes, file_name=fn_back, mime="application/octet-stream")

        with tab_rest:
            st.subheader("Restaurar la Base de Datos desde un Archivo de Respaldo")
            st.warning("⚠️ **ATENCIÓN**: Restaurar un respaldo sobrescribirá la base de datos actual.")
            db_up = st.file_uploader("Seleccionar archivo de respaldo (.db)", type=["db", "sqlite"])
            
            if db_up is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos"):
                    with open(DB_FILE, "wb") as f:
                        f.write(db_up.read())
                    st.success("🎉 ¡Base de datos restaurada con éxito! La aplicación se reiniciará.")
                    st.toast("🎉 ¡Restauración completada!")
                    st.rerun()

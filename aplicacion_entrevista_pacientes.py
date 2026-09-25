import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Seguimiento",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

ETAPAS_INFO = {
    "ACOGIDA": {"duracion": 30, "orden": 1, "siguiente": "IDENTIFICACIÓN"},
    "IDENTIFICACIÓN": {"duracion": 60, "orden": 2, "siguiente": "ELABORACIÓN"},
    "ELABORACIÓN": {"duracion": 60, "orden": 3, "siguiente": "CONSOLIDACIÓN"},
    "CONSOLIDACIÓN": {"duracion": 30, "orden": 4, "siguiente": "SERVICIO SOCIAL"},
    "SERVICIO SOCIAL": {"duracion": 30, "orden": 5, "siguiente": "CONCLUIDO"}
}

REQUISITOS_DEFAULT = [
    # ACOGIDA
    ("ACOGIDA", "Compromiso Existencial", 0, "", 1),
    ("ACOGIDA", "2 Señalamientos correctos", 0, "", 1),
    ("ACOGIDA", "5 Reglas de Usuario", 0, "", 1),
    ("ACOGIDA", "5 Reglas de Convivencia", 0, "", 1),
    # IDENTIFICACIÓN
    ("IDENTIFICACIÓN", "Autobiografía", 0, "", 1),
    ("IDENTIFICACIÓN", "Oración de la mañana", 0, "", 1),
    ("IDENTIFICACIÓN", "Filosofía de la Comunidad", 0, "", 1),
    ("IDENTIFICACIÓN", "10 Reglas de Usuario", 0, "", 1),
    ("IDENTIFICACIÓN", "10 Reglas de Convivencia", 0, "", 1),
    ("IDENTIFICACIÓN", "4 Grupos 'Aquí y Ahora'", 1, "Aquí y Ahora", 4),
    ("IDENTIFICACIÓN", "4 Grupos 'Terapia de Grupo'", 1, "Terapia de Grupo", 4),
    ("IDENTIFICACIÓN", "4 Grupos 'Feedbacks'", 1, "Feedback", 4),
    # ELABORACIÓN
    ("ELABORACIÓN", "Filosofía del Ayer, Hoy y Mañana", 0, "", 1),
    ("ELABORACIÓN", "Oración del Medio día", 0, "", 1),
    ("ELABORACIÓN", "15 Reglas de Usuario", 0, "", 1),
    ("ELABORACIÓN", "15 Reglas de Convivencia", 0, "", 1),
    ("ELABORACIÓN", "Proyecto de vida", 0, "", 1),
    ("ELABORACIÓN", "4 Grupos 'Aquí y Ahora'", 1, "Aquí y Ahora", 4),
    ("ELABORACIÓN", "4 Grupos 'Terapia de Grupo'", 1, "Terapia de Grupo", 4),
    ("ELABORACIÓN", "4 Grupos 'Feedbacks'", 1, "Feedback", 4),
    # CONSOLIDACIÓN
    ("CONSOLIDACIÓN", "30 Reglas de Usuario", 0, "", 1),
    ("CONSOLIDACIÓN", "20 Reglas de Convivencia", 0, "", 1),
    ("CONSOLIDACIÓN", "Oración del Medio día", 0, "", 1),
    ("CONSOLIDACIÓN", "Plan de Servicio Social", 0, "", 1),
    ("CONSOLIDACIÓN", "2 Grupos 'Aquí y Ahora'", 1, "Aquí y Ahora", 2),
    ("CONSOLIDACIÓN", "2 Grupos 'Terapia de Grupo'", 1, "Terapia de Grupo", 2),
    ("CONSOLIDACIÓN", "2 Grupos 'Feedbacks'", 1, "Feedback", 2),
    # SERVICIO SOCIAL
    ("SERVICIO SOCIAL", "30 Días de Servicio", 0, "", 1),
    ("SERVICIO SOCIAL", "2 Grupos 'Aquí y Ahora'", 1, "Aquí y Ahora", 2),
    ("SERVICIO SOCIAL", "2 Grupos 'Terapia de Grupo'", 1, "Terapia de Grupo", 2),
    ("SERVICIO SOCIAL", "2 Grupos 'Feedbacks'", 1, "Feedback", 2)
]

# --- INICIALIZACIÓN DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Usuarios del sistema (para Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    
    # Pacientes / Residentes de la Comunidad
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT NOT NULL,
            estatus TEXT DEFAULT 'A',
            tipo_usuario TEXT DEFAULT 'Paciente',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # Medicamentos e Inventario por Paciente
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
    
    # Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrega_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregas_json TEXT,
            usuario_registro TEXT
        )
    ''')

    # Requisitos configurables por Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS etapa_requisitos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT NOT NULL,
            requisito TEXT NOT NULL,
            es_grupo INTEGER DEFAULT 0,
            tipo_grupo TEXT DEFAULT '',
            cantidad_requerida INTEGER DEFAULT 1
        )
    ''')

    # Cumplimiento manual de Requisitos por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS paciente_requisitos_manuales (
            paciente_id TEXT NOT NULL,
            etapa TEXT NOT NULL,
            requisito TEXT NOT NULL,
            cumplido INTEGER DEFAULT 0,
            PRIMARY KEY (paciente_id, etapa, requisito)
        )
    ''')

    # Registros de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_grupo TEXT NOT NULL,
            paciente_id TEXT NOT NULL,
            fecha TEXT NOT NULL,
            etapa_usuario TEXT NOT NULL,
            compartimiento TEXT,
            observaciones TEXT,
            devoluciones TEXT,
            logros TEXT,
            dificultades TEXT,
            como_se_queda_compromiso TEXT,
            facilitador TEXT,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # Historial de Cambios de Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            etapa_anterior TEXT NOT NULL,
            etapa_nueva TEXT NOT NULL,
            fecha_cambio TEXT NOT NULL,
            usuario_registra TEXT,
            observaciones TEXT
        )
    ''')

    # Acompañamiento Hermano Menor / Hermano Mayor
    c.execute('''
        CREATE TABLE IF NOT EXISTS hermanos_acompanamiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_menor_id TEXT NOT NULL,
            paciente_mayor_id TEXT NOT NULL,
            fecha_asignacion TEXT NOT NULL,
            fecha_suelta_programada TEXT,
            fecha_suelta_real TEXT,
            estatus TEXT DEFAULT 'Activo',
            observaciones TEXT,
            usuario_registra TEXT
        )
    ''')

    # Usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))

    # Cargar Requisitos por defecto si la tabla está vacía
    c.execute('SELECT COUNT(*) FROM etapa_requisitos')
    if c.fetchone()[0] == 0:
        for et, req, eg, tg, cant in REQUISITOS_DEFAULT:
            c.execute('''
                INSERT INTO etapa_requisitos (etapa, requisito, es_grupo, tipo_grupo, cantidad_requerida)
                VALUES (?, ?, ?, ?, ?)
            ''', (et, req, eg, tg, cant))

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

# --- FUNCIONES DE MANEJO DE PACIENTES / USUARIOS ---
def guardar_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', usuario_registro='admin'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Buscar si ya existe por ID
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?
            WHERE paciente_id = ?
        ''', (nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro 
            (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACOGIDA', ?, ?, ?)
        ''', (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, fecha_ingreso, fecha_actual, usuario_registro))
        
    conn.commit()
    conn.close()

def buscar_paciente_por_nombre(nombre_completo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre_completo.strip().lower()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if row[1].strip().lower() == nombre_clean:
            return row
    return None

def listar_pacientes_registrados(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa FROM pacientes_registro WHERE estatus = "A" ORDER BY LOWER(nombre_completo) ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa FROM pacientes_registro ORDER BY LOWER(nombre_completo) ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes_registro SET estatus = ? WHERE paciente_id = ?', (nuevo_estatus, paciente_id))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ETAPAS Y REQUISITOS ---
def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo, tipo_grupo, cantidad_requerida FROM etapa_requisitos WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_requisito_etapa(etapa, requisito, es_grupo, tipo_grupo, cantidad_requerida):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO etapa_requisitos (etapa, requisito, es_grupo, tipo_grupo, cantidad_requerida)
        VALUES (?, ?, ?, ?, ?)
    ''', (etapa, requisito, es_grupo, tipo_grupo, cantidad_requerida))
    conn.commit()
    conn.close()

def eliminar_requisito_etapa(req_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM etapa_requisitos WHERE id = ?', (req_id,))
    conn.commit()
    conn.close()

def obtener_requisito_manual_cumplido(paciente_id, etapa, requisito):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT cumplido FROM paciente_requisitos_manuales WHERE paciente_id = ? AND etapa = ? AND requisito = ?', (paciente_id, etapa, requisito))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def guardar_requisito_manual(paciente_id, etapa, requisito, cumplido):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO paciente_requisitos_manuales (paciente_id, etapa, requisito, cumplido)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(paciente_id, etapa, requisito) DO UPDATE SET cumplido = excluded.cumplido
    ''', (paciente_id, etapa, requisito, cumplido))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM grupos_terapeuticos 
        WHERE paciente_id = ? AND etapa_usuario = ? AND tipo_grupo = ?
    ''', (paciente_id, etapa, tipo_grupo))
    cant = c.fetchone()[0]
    conn.close()
    return cant

def promover_etapa_paciente(paciente_id, etapa_actual, etapa_siguiente, usuario_registra, observaciones=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    
    # Actualizar etapa en paciente
    c.execute('''
        UPDATE pacientes_registro 
        SET etapa_actual = ?, fecha_inicio_etapa = ?
        WHERE paciente_id = ?
    ''', (etapa_siguiente, fecha_actual, paciente_id))
    
    # Registrar en historial
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_anterior, etapa_nueva, fecha_cambio, usuario_registra, observaciones)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_actual, etapa_siguiente, fecha_actual, usuario_registra, observaciones))
    
    conn.commit()
    conn.close()

def obtener_historial_etapas(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT etapa_anterior, etapa_nueva, fecha_cambio, usuario_registra, observaciones 
        FROM historial_etapas WHERE paciente_id = ? ORDER BY id DESC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeutico(tipo_grupo, paciente_id, fecha, etapa_usuario, compartimiento, observaciones, devoluciones, logros, dificultades, como_se_queda_compromiso, facilitador, usuario_registro):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO grupos_terapeuticos 
        (tipo_grupo, paciente_id, fecha, etapa_usuario, compartimiento, observaciones, devoluciones, logros, dificultades, como_se_queda_compromiso, facilitador, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tipo_grupo, paciente_id, fecha, etapa_usuario, compartimiento, observaciones, devoluciones, logros, dificultades, como_se_queda_compromiso, facilitador, fecha_reg, usuario_registro))
    conn.commit()
    conn.close()

def listar_grupos_paciente(paciente_id=None, tipo_grupo=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT id, tipo_grupo, paciente_id, fecha, etapa_usuario, compartimiento, observaciones, devoluciones, logros, dificultades, como_se_queda_compromiso, facilitador, fecha_registro FROM grupos_terapeuticos'
    params = []
    conditions = []
    if paciente_id:
        conditions.append('paciente_id = ?')
        params.append(paciente_id)
    if tipo_grupo:
        conditions.append('tipo_grupo = ?')
        params.append(tipo_grupo)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY fecha DESC, id DESC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_grupo_terapeutico(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM grupos_terapeuticos WHERE id = ?', (grupo_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE HERMANOS ACOMPAÑAMIENTO ---
def assignar_hermano_mayor(paciente_menor_id, paciente_mayor_id, fecha_asignacion, observaciones="", usuario_registra="admin"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        f_asig = datetime.strptime(fecha_asignacion, "%Y-%m-%d")
    except:
        f_asig = datetime.now()
    f_suelta_prog = (f_asig + timedelta(days=15)).strftime("%Y-%m-%d")
    
    c.execute('''
        INSERT INTO hermanos_acompanamiento 
        (paciente_menor_id, paciente_mayor_id, fecha_asignacion, fecha_suelta_programada, estatus, observaciones, usuario_registra)
        VALUES (?, ?, ?, ?, 'Activo', ?, ?)
    ''', (paciente_menor_id, paciente_mayor_id, fecha_asignacion, f_suelta_prog, observaciones, usuario_registra))
    conn.commit()
    conn.close()

def completar_hermano_acompanamiento(asig_id, fecha_suelta_real, observaciones=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE hermanos_acompanamiento 
        SET estatus = 'Completado', fecha_suelta_real = ?, observaciones = observaciones || ' | ' || ?
        WHERE id = ?
    ''', (fecha_suelta_real, observaciones, asig_id))
    conn.commit()
    conn.close()

def obtener_hermanos_acompanamiento(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('''
            SELECT id, paciente_menor_id, paciente_mayor_id, fecha_asignacion, fecha_suelta_programada, fecha_suelta_real, estatus, observaciones 
            FROM hermanos_acompanamiento WHERE estatus = 'Activo' ORDER BY id DESC
        ''')
    else:
        c.execute('''
            SELECT id, paciente_menor_id, paciente_mayor_id, fecha_asignacion, fecha_suelta_programada, fecha_suelta_real, estatus, observaciones 
            FROM hermanos_acompanamiento ORDER BY id DESC
        ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREVISTAS & MEDICAMENTOS ---
def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
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

def guardar_medicamentos(paciente_id, lista_meds, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(lista_meds, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ? WHERE paciente_id = ?', (meds_json, observaciones, fecha_actual, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)', (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_medicamentos(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3], row[4]
    return [], "", None, None, None

def listar_todos_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, meds_json, observaciones, fecha_modificacion FROM medicamentos')
    rows = c.fetchall()
    conn.close()
    return rows

def registrar_entrega_medicamento(paciente_id, entregas_realizadas, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Obtener meds actuales
    meds_list, obs, f_r, f_m, u_r = obtener_medicamentos(paciente_id)
    if meds_list:
        for m in meds_list:
            nombre = m.get("nombre")
            if nombre in entregas_realizadas:
                cant_entregada = entregas_realizadas[nombre]
                m["existencia"] = max(0, int(m.get("existencia", 0)) - cant_entregada)
        
        # Guardar meds actualizados
        meds_json = json.dumps(meds_list, ensure_ascii=False)
        c.execute('UPDATE medicamentos SET meds_json = ?, fecha_modificacion = ? WHERE paciente_id = ?', (meds_json, fecha_actual, paciente_id))
        
        # Historial entrega
        entregas_json = json.dumps(entregas_realizadas, ensure_ascii=False)
        c.execute('INSERT INTO entrega_historial (paciente_id, fecha_entrega, entregas_json, usuario_registro) VALUES (?, ?, ?, ?)', (paciente_id, fecha_actual, entregas_json, usuario))
        
    conn.commit()
    conn.close()

# --- GENERADORES DE REPORTES PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control y Seguimiento Clinico", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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
        texto = texto.replace(k, v)
    return texto

def generar_pdf_entrevista(paciente_id, datos_entrevista, datos_paciente=None):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "ENTREVISTA INICIAL DE CONSEJERIA", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    if datos_paciente:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 5, f"Nombre: {limpiar_texto(datos_paciente[1])}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(pdf.epw, 5, f"Fecha Ingreso: {datos_paciente[2]} | Nacimiento: {datos_paciente[3]} | Sexo: {datos_paciente[4]}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla Consumo
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    col_widths = [28, 20, 25, 30, 28, 22, 37]
    headers = ["Sustancia", "Consumo", "Forma", "Frecuencia", "Cantidad", "Edad Inic.", "Lugar"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    tabla_consumo = datos_entrevista.get("tabla_consumo", {})
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
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos_entrevista.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(datos_entrevista.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_grupos_paciente(paciente_id, datos_paciente, lista_grupos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "EXPEDIENTE DE GRUPOS TERAPEUTICOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(datos_paciente[1])} (FOLIO: {paciente_id})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Etapa Actual: {datos_paciente[7]} | Fecha Ingreso: {datos_paciente[2]} | Sexo: {datos_paciente[4]}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    if not lista_grupos:
        pdf.cell(pdf.epw, 6, "No hay sesiones de grupo registradas para este paciente.", new_x="LMARGIN", new_y="NEXT")
    else:
        for g in lista_grupos:
            g_id, t_grupo, p_id, fecha, etapa_u, comp, obs, dev, logros, dif, como_queda, facil, f_reg = g
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"[{fecha}] {limpiar_texto(t_grupo)} (Etapa: {limpiar_texto(etapa_u)}) - Facilitador: {limpiar_texto(facil)}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            if comp:
                pdf.multi_cell(pdf.epw, 4.5, f"Compartimiento: {limpiar_texto(comp)}", new_x="LMARGIN", new_y="NEXT")
            if logros:
                pdf.multi_cell(pdf.epw, 4.5, f"Logros: {limpiar_texto(logros)}", new_x="LMARGIN", new_y="NEXT")
            if dif:
                pdf.multi_cell(pdf.epw, 4.5, f"Dificultades: {limpiar_texto(dif)}", new_x="LMARGIN", new_y="NEXT")
            if obs:
                pdf.multi_cell(pdf.epw, 4.5, f"Observaciones: {limpiar_texto(obs)}", new_x="LMARGIN", new_y="NEXT")
            if dev:
                pdf.multi_cell(pdf.epw, 4.5, f"Devoluciones: {limpiar_texto(dev)}", new_x="LMARGIN", new_y="NEXT")
            if como_queda:
                pdf.multi_cell(pdf.epw, 4.5, f"Como se queda / Compromiso: {limpiar_texto(como_queda)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            
    pdf_filename = f"Grupos_Terapeuticos_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_medicamentos_alfabetica():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA GENERAL DE MEDICAMENTOS Y DOSIS POR USUARIO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pacientes_activos = listar_pacientes_registrados(solo_activos=True)
    
    if not pacientes_activos:
        pdf.cell(pdf.epw, 6, "No hay usuarios activos registrados.", new_x="LMARGIN", new_y="NEXT")
    else:
        for pac in pacientes_activos:
            p_id, p_nombre, p_f_ing, p_f_nac, p_sexo, _, _, p_etapa, _ = pac
            meds_list, obs, _, _, _ = obtener_medicamentos(p_id)
            
            if meds_list:
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(p_nombre)} (FOLIO: {p_id})", border="B", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "B", 8)
                
                col_w = [45, 20, 20, 20, 22, 22, 41]
                hdrs = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis D.", "Existencia", "Indicaciones"]
                for i, h in enumerate(hdrs):
                    pdf.cell(col_w[i], 5, h, border=1, align="C")
                pdf.ln()
                
                pdf.set_font("Helvetica", "", 8)
                for m in meds_list:
                    m_m = int(m.get("dosis_manana", 0))
                    m_t = int(m.get("dosis_tarde", 0))
                    m_n = int(m.get("dosis_noche", 0))
                    d_total = m_m + m_t + m_n
                    
                    pdf.cell(col_w[0], 5, limpiar_texto(m.get("nombre", "")), border=1)
                    pdf.cell(col_w[1], 5, str(m_m), border=1, align="C")
                    pdf.cell(col_w[2], 5, str(m_t), border=1, align="C")
                    pdf.cell(col_w[3], 5, str(m_n), border=1, align="C")
                    pdf.cell(col_w[4], 5, str(d_total), border=1, align="C")
                    pdf.cell(col_w[5], 5, str(m.get("existencia", 0)), border=1, align="C")
                    pdf.cell(col_w[6], 5, limpiar_texto(m.get("indicaciones", "")), border=1, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)

    pdf_filename = f"Lista_General_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR SISTEMA ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center;'>🌿 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #2E7D32;'>Comunidad Terapéutica para el Tratamiento de Adicciones</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sistema Integral de Control y Seguimiento Clínico</p>", unsafe_allow_html=True)
    
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
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL Y NAVEGACIÓN ---
    st.sidebar.title("🌿 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "👤 Registro de Usuarios",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "📝 Entrevista Inicial Consejería",
            "🔍 Buscar y Listar Pacientes",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas y Compras Farmacia",
            "⚙️ Configuración del Sistema"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 1: REGISTRO DE USUARIOS ---
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro de Usuarios y Residentes")
        st.caption("Paso inicial para dar de alta y administrar a los integrantes de la comunidad")
        
        tab_reg, tab_activos, tab_bloqueados = st.tabs([
            "➕ Alta de Nuevo Usuario",
            "🟢 Usuarios Activos ('A')",
            "🔒 Usuarios Bloqueados ('B')"
        ])
        
        with tab_reg:
            # Calcular Folio sugerido
            pacientes_all = listar_pacientes_registrados(solo_activos=False)
            next_num = len(pacientes_all) + 1
            folio_sugerido = f"PAC-{next_num:03d}"
            
            with st.form("form_alta_usuario"):
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    reg_id = st.text_input("🔑 Folio / ID de Usuario *", value=folio_sugerido).strip()
                    reg_nombre = st.text_input("👤 Nombre Completo *").strip()
                    reg_tipo = st.selectbox("🏷️ Tipo de Usuario", ["Paciente", "Servidor / Staff"])
                with col_u2:
                    reg_f_ingreso = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=date.today())
                    reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=date(1990, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
                    reg_sexo = st.selectbox("🚻 Sexo", ["Masculino", "Femenino", "Otro"])
                
                btn_guardar_u = st.form_submit_button("💾 Dar de Alta Usuario", use_container_width=True)
                
                if btn_guardar_u:
                    if not reg_id or not reg_nombre:
                        st.error("⚠️ El Folio/ID y el Nombre Completo son obligatorios.")
                    else:
                        dup = buscar_paciente_por_nombre(reg_nombre)
                        if dup and dup[0] != reg_id:
                            st.error(f"❌ Ya existe un usuario registrado con el nombre '{dup[1]}' bajo el Folio {dup[0]} (Estatus: {dup[2]}).")
                        else:
                            guardar_paciente(reg_id, reg_nombre, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, estatus='A', tipo_usuario=reg_tipo, usuario_registro=st.session_state["username"])
                            st.success(f"✅ ¡Usuario {reg_nombre} (Folio: {reg_id}) registrado exitosamente!")
                            st.rerun()

        with tab_activos:
            activos = listar_pacientes_registrados(solo_activos=True)
            st.subheader(f"Total de Usuarios Activos: {len(activos)}")
            if activos:
                for pac in activos:
                    p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_etapa, p_fetapa = pac
                    with st.expander(f"🟢 **{p_nom}** | Folio: `{p_id}` | Tipo: **{p_tipo}** | Etapa: **{p_etapa}**"):
                        c1, c2, c3 = st.columns([2, 2, 1])
                        with c1:
                            st.write(f"**Fecha Ingreso:** {p_fing}")
                            st.write(f"**Fecha Nacimiento:** {p_fnac}")
                        with c2:
                            st.write(f"**Sexo:** {p_sex}")
                            st.write(f"**Inicio de Etapa:** {p_fetapa or p_fing}")
                        with c3:
                            if st.button(f"🔒 Bloquear", key=f"bloq_{p_id}"):
                                cambiar_estatus_paciente(p_id, 'B')
                                st.warning(f"Usuario {p_nom} cambiado a Estatus 'B' (Bloqueado).")
                                st.rerun()

        with tab_bloqueados:
            todos = listar_pacientes_registrados(solo_activos=False)
            bloqueados = [p for p in todos if p[5] == 'B']
            st.subheader(f"Total de Usuarios Bloqueados: {len(bloqueados)}")
            if bloqueados:
                for pac in bloqueados:
                    p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_etapa, p_fetapa = pac
                    with st.expander(f"🔒 **{p_nom}** | Folio: `{p_id}` | Tipo: **{p_tipo}**"):
                        c1, c2, c3 = st.columns([2, 2, 1])
                        with c1:
                            st.write(f"**Fecha Ingreso:** {p_fing}")
                        with c2:
                            st.write(f"**Sexo:** {p_sex}")
                        with c3:
                            if st.button(f"🟢 Activar", key=f"act_{p_id}"):
                                cambiar_estatus_paciente(p_id, 'A')
                                st.success(f"Usuario {p_nom} reactivado a Estatus 'A' (Activo).")
                                st.rerun()

    # --- SECCIÓN 2: GESTIÓN DE ETAPAS Y PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Avance de Pacientes")
        st.caption("Seguimiento del proceso individual de 7 meses en Sawabona Shikoba")

        tab_progreso, tab_hermanos, tab_alertas_etapa = st.tabs([
            "📊 Avance y Requisitos por Paciente",
            "🤝 Hermano Menor & Hermano Mayor",
            "🚨 Alertas de Días por Etapa"
        ])

        activos = listar_pacientes_registrados(solo_activos=True)
        # Excluir a Servidores del proceso estricto si se desea
        pacientes_proceso = [p for p in activos if p[6] == 'Paciente']

        with tab_progreso:
            if not pacientes_proceso:
                st.info("No hay usuarios registrados con tipo 'Paciente' activos.")
            else:
                opciones_p = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_proceso}
                sel_p_key = st.selectbox("👤 Seleccione Paciente para evaluar avance:", list(opciones_p.keys()))
                p_sel = opciones_p[sel_p_key]
                p_id, p_nombre, p_fing, p_fnac, p_sexo, _, _, p_etapa, p_fetapa = p_sel

                st.divider()
                st.subheader(f"📋 Evaluación de Proceso: {p_nombre} (Folio: {p_id})")
                
                col_e1, col_e2, col_e3 = st.columns(3)
                with col_e1:
                    st.metric("Etapa Actual", p_etapa)
                with col_e2:
                    f_ini_e = p_fetapa if p_fetapa else p_fing
                    try:
                        dias_estancia_etapa = (date.today() - datetime.strptime(f_ini_e, "%Y-%m-%d").date()).days
                    except:
                        dias_estancia_etapa = 0
                    duracion_target = ETAPAS_INFO.get(p_etapa, {}).get("duracion", 30)
                    st.metric("Días en Etapa Actual", f"{dias_estancia_etapa} / {duracion_target} días")
                with col_e3:
                    try:
                        dias_totales = (date.today() - datetime.strptime(p_fing, "%Y-%m-%d").date()).days
                    except:
                        dias_totales = 0
                    st.metric("Días Totales en Comunidad", f"{dias_totales} días")

                # Barra de progreso visual
                porcentaje_dias = min(1.0, max(0.0, dias_estancia_etapa / duracion_target))
                st.progress(porcentaje_dias, text=f"Avance de tiempo en {p_etapa}: {int(porcentaje_dias*100)}%")

                st.subheader(f"✅ Checklist de Requisitos para Etapa: {p_etapa}")
                reqs_etapa = obtener_requisitos_etapa(p_etapa)
                
                todos_cumplidos = True
                total_reqs = len(reqs_etapa)
                reqs_completos_count = 0

                for req_tuple in reqs_etapa:
                    r_id, r_nombre, r_es_grupo, r_tipo_grupo, r_cant_req = req_tuple
                    
                    if r_es_grupo == 1:
                        # Conteo automático de grupos registrados
                        cant_hechos = contar_grupos_paciente_etapa(p_id, p_etapa, r_tipo_grupo)
                        cumplido_auto = cant_hechos >= r_cant_req
                        if not cumplido_auto:
                            todos_cumplidos = False
                        else:
                            reqs_completos_count += 1
                        
                        st.checkbox(
                            f"🗣️ **{r_nombre}** (Realizados: {cant_hechos} / Requeridos: {r_cant_req})",
                            value=cumplido_auto,
                            disabled=True,
                            key=f"req_auto_{r_id}_{p_id}"
                        )
                    else:
                        # Requisito manual
                        estado_actual = obtener_requisito_manual_cumplido(p_id, p_etapa, r_nombre)
                        val_check = st.checkbox(
                            f"📌 **{r_nombre}**",
                            value=(estado_actual == 1),
                            key=f"req_man_{r_id}_{p_id}"
                        )
                        if val_check != (estado_actual == 1):
                            guardar_requisito_manual(p_id, p_etapa, r_nombre, 1 if val_check else 0)
                            st.rerun()
                        
                        if val_check:
                            reqs_completos_count += 1
                        else:
                            todos_cumplidos = False

                st.markdown(f"**Progreso de Requisitos:** `{reqs_completos_count} / {total_reqs} completados`")

                # Botón de Cambio de Etapa
                etapa_siguiente = ETAPAS_INFO.get(p_etapa, {}).get("siguiente", "CONCLUIDO")
                st.divider()
                
                if etapa_siguiente == "CONCLUIDO":
                    st.balloons()
                    st.success("🎉 ¡El usuario ha completado exitosamente todas las etapas del tratamiento!")
                else:
                    if todos_cumplidos:
                        st.success(f"🌟 ¡Todos los requisitos de **{p_etapa}** están al 100%! El paciente puede ser promovido.")
                        obs_cambio = st.text_input("Observaciones de Promoción de Etapa", key=f"obs_prom_{p_id}")
                        if st.button(f"🚀 Promover a Siguiente Etapa: {etapa_siguiente}", use_container_width=True):
                            promover_etapa_paciente(p_id, p_etapa, etapa_siguiente, st.session_state["username"], obs_cambio)
                            st.success(f"✅ ¡{p_nombre} promovido a la etapa **{etapa_siguiente}**!")
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Botón de promoción inhabilitado. Faltan requisitos por completar en la etapa {p_etapa}.")
                        st.button(f"🔒 Promover a Siguiente Etapa: {etapa_siguiente} (Inhabilitado)", disabled=True, use_container_width=True)

                # Historial de Etapas
                st.subheader("📜 Historial de Etapas de este Paciente")
                hist = obtener_historial_etapas(p_id)
                if hist:
                    for h in hist:
                        st.write(f"• **{h[2]}**: Avanzó de **{h[0]}** ➔ **{h[1]}** (Registrado por {h[3]}) {f'- Obs: {h[4]}' if h[4] else ''}")
                else:
                    st.caption("Aún no registra cambios de etapa previos.")

        with tab_hermanos:
            st.subheader("🤝 Control de Hermano Menor y Hermano Mayor")
            st.info("💡 En la etapa de **ACOGIDA**, durante los primeros 15 días, todo nuevo paciente es un **Hermano Menor** y se le asigna un **Hermano Mayor** para acompañarle.")

            col_hm1, col_her2 = st.columns(2)
            with col_hm1:
                st.markdown("### ➕ Asignar Acompañante")
                # Menores elegibles: Pacientes en ACOGIDA
                menores_candidatos = [p for p in pacientes_proceso if p[7] == 'ACOGIDA']
                mayores_candidatos = [p for p in activos if p[7] != 'ACOGIDA' or p[6] == 'Servidor / Staff']

                if not menores_candidatos:
                    st.caption("No hay pacientes actuales en etapa ACOGIDA.")
                else:
                    dict_menores = {f"{p[1]} ({p[0]})": p[0] for p in menores_candidatos}
                    dict_mayores = {f"{p[1]} ({p[0]} - {p[7]})": p[0] for p in mayores_candidatos}

                    with st.form("form_asignar_hermanos"):
                        sel_menor = st.selectbox("👶 Hermano Menor (Etapa Acogida)", list(dict_menores.keys()))
                        sel_mayor = st.selectbox("👨‍🏫 Hermano Mayor (Etapa Superior / Servidor)", list(dict_mayores.keys())) if dict_mayores else None
                        f_asig_hm = st.date_input("Fecha de Asignación", value=date.today())
                        obs_hm = st.text_input("Observaciones / Encargo")

                        btn_hm = st.form_submit_button("🤝 Registrar Acompañamiento")
                        if btn_hm and sel_mayor:
                            id_menor = dict_menores[sel_menor]
                            id_mayor = dict_mayores[sel_mayor]
                            assignar_hermano_mayor(id_menor, id_mayor, str(f_asig_hm), obs_hm, st.session_state["username"])
                            st.success("✅ Acompañamiento registrado correctamente.")
                            st.rerun()

            with col_her2:
                st.markdown("### 📌 Acompañamientos Activos")
                hermanos_activos = obtener_hermanos_acompanamiento(solo_activos=True)
                if not hermanos_activos:
                    st.caption("No hay acompañamientos activos registrados.")
                else:
                    for hm in hermanos_activos:
                        hm_id, men_id, may_id, f_asig, f_prog, f_real, est, obs = hm
                        p_menor = obtener_paciente_por_id(men_id)
                        p_mayor = obtener_paciente_por_id(may_id)
                        
                        nom_menor = p_menor[1] if p_menor else men_id
                        nom_mayor = p_mayor[1] if p_mayor else may_id

                        st.markdown(f"**👶 Menor:** {nom_menor} ➔ **👨‍🏫 Mayor:** {nom_mayor}")
                        st.caption(f"Asignación: {f_asig} | Suelta Programada (15 días): {f_prog}")
                        
                        if st.button(f"🔓 Marcar que Hermano Mayor lo Suelta", key=f"suelta_{hm_id}"):
                            completar_hermano_acompanamiento(hm_id, str(date.today()), "Soltado en tiempo")
                            st.success(f"Acompañamiento finalizado. {nom_menor} continúa su proceso solo.")
                            st.rerun()
                        st.divider()

        with tab_alertas_etapa:
            st.subheader("🚨 Alertas de Cumplimiento de Días por Etapa")
            st.caption("Usuarios a los que les faltan 5 días o menos para cumplir el tiempo total de su etapa actual")

            alertas_count = 0
            for pac in pacientes_proceso:
                p_id, p_nombre, p_fing, _, _, _, _, p_etapa, p_fetapa = pac
                f_ini_e = p_fetapa if p_fetapa else p_fing
                try:
                    dias_e = (date.today() - datetime.strptime(f_ini_e, "%Y-%m-%d").date()).days
                except:
                    dias_e = 0
                
                duracion_target = ETAPAS_INFO.get(p_etapa, {}).get("duracion", 30)
                dias_restantes = duracion_target - dias_e

                if dias_restantes <= 5:
                    alertas_count += 1
                    if dias_restantes <= 0:
                        st.error(f"🔴 **{p_nombre}** ({p_id}) - **{p_etapa}**: Ha cumplido **{dias_e} de {duracion_target} días**. ¡Ya puede solicitar su cambio de etapa!")
                    else:
                        st.warning(f"🟡 **{p_nombre}** ({p_id}) - **{p_etapa}**: Le faltan **{dias_restantes} días** para cumplir su etapa (Lleva {dias_e} de {duracion_target} días).")

            if alertas_count == 0:
                st.success("🟢 No hay usuarios próximos a cumplir su tiempo de etapa en los siguientes 5 días.")

    # --- SECCIÓN 3: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Captura de sesiones de Terapia de Grupo, Aquí y Ahora, y Feedbacks")

        tab_g_reg, tab_g_list = st.tabs(["📝 Registrar Nuevo Grupo", "🔍 Consulta e Impresión de Grupos"])

        activos = listar_pacientes_registrados(solo_activos=True)
        dict_activos = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in activos}

        with tab_g_reg:
            if not dict_activos:
                st.warning("No hay usuarios activos registrados.")
            else:
                tipo_g = st.selectbox("📌 Seleccione Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                sel_p_g = st.selectbox("👤 Seleccione Usuario / Paciente", list(dict_activos.keys()))
                p_data_g = dict_activos[sel_p_g]
                p_id_g, p_nom_g, _, _, _, _, _, p_etapa_g, _ = p_data_g

                st.info(f"Registrando para: **{p_nom_g}** | Folio: `{p_id_g}` | Etapa Actual: **{p_etapa_g}**")

                with st.form("form_registro_grupo"):
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        f_grupo = st.date_input("📅 Fecha de la Sesión", value=date.today())
                    with col_g2:
                        facil_g = st.text_input("👨‍💼 Nombre del Facilitador", value=st.session_state["nombre_completo"])

                    if tipo_g == "Feedback":
                        logros_g = st.text_area("🌟 Logros (Texto largo)")
                        dificultades_g = st.text_area("⚠️ Dificultades (Texto largo)")
                        comp_g = ""
                    else:
                        comp_g = st.text_area("💬 Compartimiento (Texto largo)")
                        logros_g = ""
                        dificultades_g = ""

                    obs_g = st.text_area("🔍 Observaciones (Texto largo)")
                    dev_g = st.text_area("↩️ Devoluciones (Texto largo)")
                    como_queda_g = st.text_area("🤝 ¿Cómo se queda y a qué se compromete?")

                    btn_guardar_g = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)

                    if btn_guardar_g:
                        guardar_grupo_terapeutico(
                            tipo_g, p_id_g, str(f_grupo), p_etapa_g, comp_g, obs_g, dev_g, logros_g, dificultades_g, como_queda_g, facil_g, st.session_state["username"]
                        )
                        st.success(f"✅ ¡Sesión de **{tipo_g}** registrada correctamente para {p_nom_g}!")
                        st.rerun()

        with tab_g_list:
            st.subheader("📋 Expediente de Grupos Terapéuticos por Usuario")
            if dict_activos:
                sel_p_consulta = st.selectbox("👤 Seleccione Paciente para consultar grupos:", list(dict_activos.keys()), key="sel_p_cons_g")
                p_data_cons = dict_activos[sel_p_consulta]
                p_id_c = p_data_cons[0]

                # Botón de PDF
                grupos_paciente = listar_grupos_paciente(paciente_id=p_id_c)
                if grupos_paciente:
                    pdf_g_file = generar_pdf_grupos_paciente(p_id_c, p_data_cons, grupos_paciente)
                    with open(pdf_g_file, "rb") as f_pdf_g:
                        st.download_button(
                            label="🖨️ Descargar Expediente de Grupos en PDF",
                            data=f_pdf_g,
                            file_name=f"Grupos_{p_id_c}.pdf",
                            mime="application/pdf",
                            key=f"btn_pdf_g_{p_id_c}"
                        )

                st.divider()
                if not grupos_paciente:
                    st.info("Este usuario no tiene registros de grupos aún.")
                else:
                    st.write(f"**Total de sesiones registradas:** {len(grupos_paciente)}")
                    for g in grupos_paciente:
                        g_id, t_grupo, p_id, fecha, etapa_u, comp, obs, dev, logros, dif, como_queda, facil, f_reg = g
                        with st.expander(f"🗣️ **{t_grupo}** | Fecha: {fecha} | Etapa: {etapa_u} | Facilitador: {facil}"):
                            if comp:
                                st.write(f"**Compartimiento:** {comp}")
                            if logros:
                                st.write(f"**Logros:** {logros}")
                            if dif:
                                st.write(f"**Dificultades:** {dif}")
                            if obs:
                                st.write(f"**Observaciones:** {obs}")
                            if dev:
                                st.write(f"**Devoluciones:** {dev}")
                            if como_queda:
                                st.write(f"**Cómo se queda / Compromiso:** {como_queda}")
                            
                            if st.button("🗑️ Eliminar Registro", key=f"del_g_{g_id}"):
                                eliminar_grupo_terapeutico(g_id)
                                st.warning("Registro eliminado.")
                                st.rerun()

    # --- SECCIÓN 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial Consejería":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ Primero debe dar de alta usuarios en el módulo '👤 Registro de Usuarios'.")
        else:
            dict_activos_e = {f"{p[1]} ({p[0]})": p[0] for p in activos}
            sel_pac_e = st.selectbox("👤 Seleccione el Paciente:", list(dict_activos_e.keys()))
            paciente_id_input = dict_activos_e[sel_pac_e]
            p_data_e = obtener_paciente_por_id(paciente_id_input)

            datos_existentes = {}
            if paciente_id_input:
                datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
                if datos_cargados:
                    st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                    datos_existentes = datos_cargados
                else:
                    st.info("🆕 Expediente sin entrevista previa. Complete los datos a continuación.")

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
                        dependientes_quienes = st.text_input("¿Quiénes o quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
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
                            "consumo": "SÍ" if c_val else "NO", "forma": forma_val, "frecuencia": frec_val, "cantidad": cant_val, "edad_inicio": edad_val, "lugar": lugar_val
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
                    abst_motivo = st.text_area("¿Por qué se abstuvo y qué hizo para mantenerse?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("En los últimos 6 meses, mayor periodo sin consumir", value=datos_existentes.get("abst_6meses", ""))
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Importancia de dejar de consumir", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("Integrantes de la familia con mayor contacto", value=datos_existentes.get("familia_integrantes", ""))
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        relaciones_post_consumo = st.selectbox("¿Relaciones sexuales tras consumir?", ["NO", "SÍ"], index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_flag = st.selectbox("¿Involucrado en abuso físico/sexual?", ["NO", "SÍ"], index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas durante la sesión", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Entrevista de Consejería", use_container_width=True)
                if guardar_btn:
                    datos_completos = {
                        "dependientes_flag": dependientes_flag, "dependientes_quienes": dependientes_quienes, "pareja_flag": pareja_flag, "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input, "sustancia_impacto": sustancia_impacto, "tiempo_excesivo": tiempo_excesivo, "modo_consumo": modo_consumo,
                        "abst_mayor_tiempo": abst_mayor_tiempo, "abst_fecha": abst_fecha, "abst_motivo": abst_motivo, "abst_6meses": abst_6meses, "importancia_cambio": importancia_cambio,
                        "familia_integrantes": familia_integrantes, "relaciones_post_consumo": relaciones_post_consumo, "abuso_flag": abuso_flag,
                        "problemas_sesion": problemas_sesion, "observaciones": observaciones, "evaluador_nombre": evaluador_nombre, "evaluador_cargo": evaluador_cargo
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.success(f"✅ ¡Entrevista guardada correctamente para {p_data_e[1]}!")

    # --- SECCIÓN 5: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio de Expedientes de Pacientes")
        
        filtro_estatus = st.radio("Filtrar Expedientes:", ["🟢 Solo Activos ('A')", "📜 Ver Todos (Incluye Bloqueados)"], horizontal=True)
        solo_act = True if "Solo Activos" in filtro_estatus else False
        
        pacientes = listar_pacientes_registrados(solo_activos=solo_act)
        if not pacientes:
            st.warning("No hay pacientes registrados que coincidan con el filtro.")
        else:
            st.subheader(f"Total de Registros: {len(pacientes)}")
            for pac in pacientes:
                p_id, p_nom, p_fing, p_fnac, p_sex, p_est, p_tipo, p_etapa, _ = pac
                tag_est = "🟢 Activo" if p_est == 'A' else "🔒 Bloqueado"
                with st.expander(f"👤 **{p_nom}** | Folio: `{p_id}` | Estatus: {tag_est} | Etapa: **{p_etapa}**"):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.write(f"**Fecha Ingreso:** {p_fing} | **Fecha Nacimiento:** {p_fnac} | **Sexo:** {p_sex}")
                        st.write(f"**Tipo de Usuario:** {p_tipo}")
                    with c2:
                        datos_e, _, _, _ = obtener_entrevista(p_id)
                        if datos_e:
                            pdf_ent = generar_pdf_entrevista(p_id, datos_e, pac)
                            with open(pdf_ent, "rb") as f_ent:
                                st.download_button("🖨️ Descargar Entrevista (PDF)", data=f_ent, file_name=f"Entrevista_{p_id}.pdf", mime="application/pdf", key=f"pdf_ent_{p_id}")

    # --- SECCIÓN 6: CONTROL DE MEDICAMENTOS Y DOSIS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosis por Usuario")
        st.caption("Asignación de dosis (mañana, tarde, noche) e inventario de existencias")

        # Botón PDF Lista General
        if st.button("📄 Imprimir Lista General de Medicamentos (PDF Orden Alfabético)", use_container_width=True):
            pdf_gen_m = generar_pdf_lista_medicamentos_alfabetica()
            with open(pdf_gen_m, "rb") as f_gen_m:
                st.download_button("📥 Descargar PDF Lista General", data=f_gen_m, file_name=f"Lista_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")

        st.divider()
        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ No hay usuarios activos registrados.")
        else:
            dict_activos_m = {f"{p[1]} ({p[0]})": p[0] for p in activos}
            sel_pac_m = st.selectbox("👤 Seleccione el Paciente:", list(dict_activos_m.keys()))
            paciente_med_id = dict_activos_m[sel_pac_m]
            p_data_m = obtener_paciente_por_id(paciente_med_id)

            meds_cargados, obs_cargadas, _, _, _ = obtener_medicamentos(paciente_med_id)

            with st.form("form_medicamentos"):
                st.subheader(f"Esquema de Medicación para: {p_data_m[1]}")
                cant_meds = st.number_input("¿Cuántos medicamentos diferentes toma?", min_value=1, max_value=15, value=max(1, len(meds_cargados)))
                
                lista_meds_input = []
                for i in range(int(cant_meds)):
                    m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                    st.markdown(f"**Medicamento #{i+1}**")
                    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([2, 1, 1, 1, 1, 2])
                    with col_m1:
                        m_nombre = st.text_input("Nombre / Presentación", value=m_prev.get("nombre", ""), key=f"m_nom_{i}")
                    with col_m2:
                        m_man = st.number_input("☀️ Mañana", min_value=0, value=int(m_prev.get("dosis_manana", 0)), key=f"m_man_{i}")
                    with col_m3:
                        m_tar = st.number_input("🌤️ Tarde", min_value=0, value=int(m_prev.get("dosis_tarde", 0)), key=f"m_tar_{i}")
                    with col_m4:
                        m_noc = st.number_input("🌙 Noche", min_value=0, value=int(m_prev.get("dosis_noche", 0)), key=f"m_noc_{i}")
                    with col_m5:
                        m_exi = st.number_input("📦 Existencia", min_value=0, value=int(m_prev.get("existencia", 0)), key=f"m_exi_{i}")
                    with col_m6:
                        m_ind = st.text_input("📝 Indicaciones", value=m_prev.get("indicaciones", ""), key=f"m_ind_{i}")

                    if m_nombre.strip():
                        lista_meds_input.append({
                            "nombre": m_nombre.strip(), "dosis_manana": m_man, "dosis_tarde": m_tar, "dosis_noche": m_noc, "existencia": m_exi, "indicaciones": m_ind
                        })
                    st.divider()

                obs_meds_input = st.text_area("Observaciones de Medicación / Alergias", value=obs_cargadas)
                btn_guardar_m = st.form_submit_button("💾 Guardar Esquema e Inventario", use_container_width=True)

                if btn_guardar_m:
                    guardar_medicamentos(paciente_med_id, lista_meds_input, obs_meds_input, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos guardado para {p_data_m[1]}!")
                    st.rerun()

    # --- SECCIÓN 7: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega Diaria de Medicamentos")
        st.caption("Registro de entrega y descuento automático de existencias")

        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ No hay usuarios activos registrados.")
        else:
            dict_activos_del = {f"{p[1]} ({p[0]})": p[0] for p in activos}
            sel_pac_del = st.selectbox("👤 Seleccione el Paciente:", list(dict_activos_del.keys()))
            p_id_del = dict_activos_del[sel_pac_del]
            p_data_del = obtener_paciente_por_id(p_id_del)

            meds_cargados, _, _, _, _ = obtener_medicamentos(p_id_del)
            meds_con_stock = [m for m in meds_cargados if int(m.get("existencia", 0)) > 0]

            if not meds_con_stock:
                st.warning(f"⚠️ El usuario {p_data_del[1]} no tiene medicamentos con existencia en inventario (Stock = 0).")
            else:
                with st.form("form_entrega_meds"):
                    st.subheader(f"Entrega de Medicamentos a: {p_data_del[1]}")
                    entregas_input = {}
                    
                    for m in meds_con_stock:
                        nom_m = m.get("nombre")
                        exi_m = int(m.get("existencia", 0))
                        d_man = int(m.get("dosis_manana", 0))
                        d_tar = int(m.get("dosis_tarde", 0))
                        d_noc = int(m.get("dosis_noche", 0))
                        dosis_diaria = d_man + d_tar + d_noc
                        
                        dosis_sugerida = min(exi_m, max(1, dosis_diaria))
                        
                        st.markdown(f"💊 **{nom_m}** (Existencia disponible: `{exi_m}` | Dosis diaria: `{dosis_diaria}`)")
                        cant_ent = st.number_input(f"Cantidad a entregar para {nom_m}", min_value=1, max_value=exi_m, value=dosis_sugerida, key=f"del_{nom_m}")
                        entregas_input[nom_m] = cant_ent
                        st.divider()

                    btn_confirmar_del = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)

                    if btn_confirmar_del:
                        registrar_entrega_medicamento(p_id_del, entregas_input, st.session_state["username"])
                        st.success(f"✅ ¡Entrega registrada y stock descontado correctamente para {p_data_del[1]}!")
                        st.rerun()

    # --- SECCIÓN 8: ALERTAS Y COMPRAS FARMACIA ---
    elif menu == "🚨 Alertas y Compras Farmacia":
        st.title("🚨 Alertas de Existencia y Compras de Farmacia")
        st.caption("Cálculo automático de medicamentos agotados o próximos a agotarse")

        todos_meds = listar_todos_medicamentos()
        activos_dict = {p[0]: p for p in listar_pacientes_registrados(solo_activos=True)}

        alertas_criticas = []
        alertas_preventivas = []

        for row in todos_meds:
            p_id, m_json, obs, f_mod = row
            if p_id in activos_dict:
                p_nom = activos_dict[p_id][1]
                meds = json.loads(m_json) if m_json else []
                for m in meds:
                    exi = int(m.get("existencia", 0))
                    d_diaria = int(m.get("dosis_manana", 0)) + int(m.get("dosis_tarde", 0)) + int(m.get("dosis_noche", 0))
                    if d_diaria > 0:
                        dias_cobertura = exi / d_diaria
                        item = {"paciente": p_nom, "folio": p_id, "med": m.get("nombre"), "existencia": exi, "dosis_diaria": d_diaria, "cobertura": dias_cobertura}
                        if dias_cobertura < 1.0:
                            alertas_criticas.append(item)
                        elif dias_cobertura <= 3.0:
                            alertas_preventivas.append(item)

        c_a1, c_a2 = st.columns(2)
        with c_a1:
            st.metric("🔴 Alertas Críticas (Stock < 1 día)", len(alertas_criticas))
        with c_a2:
            st.metric("🟡 Alertas Preventivas (Stock 1-3 días)", len(alertas_preventivas))

        st.subheader("🔴 Lista Urgente de Reabastecimiento")
        if not alertas_criticas:
            st.success("🟢 No hay medicamentos en alerta crítica.")
        else:
            for item in alertas_criticas:
                st.error(f"👤 **{item['paciente']}** (`{item['folio']}`) | Medicamento: **{item['med']}** | Stock actual: `{item['existencia']}` | Dosis diaria: `{item['dosis_diaria']}`")

    # --- SECCIÓN 9: CONFIGURACIÓN DEL SISTEMA ---
    elif menu == "⚙️ Configuración del Sistema":
        st.title("⚙️ Configuración del Sistema")
        st.caption("Administración de Requisitos de Etapas y Seguridad")

        tab_cfg_req, tab_cfg_sec = st.tabs(["📝 Configurar Requisitos por Etapa", "🔐 Cambiar Contraseña"])

        with tab_cfg_req:
            st.subheader("Administración de Checklist de Requisitos por Etapa")
            etapa_sel_cfg = st.selectbox("Seleccione Etapa a Configurar:", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
            
            reqs_actuales = obtener_requisitos_etapa(etapa_sel_cfg)
            st.markdown(f"**Requisitos Actuales de {etapa_sel_cfg}:**")
            for r in reqs_actuales:
                r_id, r_nom, r_eg, r_tg, r_cant = r
                col_r1, col_r2 = st.columns([4, 1])
                with col_r1:
                    if r_eg == 1:
                        st.write(f"• **{r_nom}** (Grupo Automático: {r_tg} | Requeridos: {r_cant})")
                    else:
                        st.write(f"• **{r_nom}** (Verificación Manual)")
                with col_r2:
                    if st.button("🗑️ Borrar", key=f"del_req_{r_id}"):
                        eliminar_requisito_etapa(r_id)
                        st.success("Requisito eliminado.")
                        st.rerun()

            st.divider()
            st.markdown("### ➕ Agregar Nuevo Requisito")
            with st.form("form_add_req"):
                nuevo_req_nombre = st.text_input("Nombre del Requisito *").strip()
                es_grupo_cb = st.checkbox("¿Es un grupo terapéutico con conteo automático?")
                tipo_grupo_sel = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"]) if es_grupo_cb else ""
                cant_req_num = st.number_input("Cantidad requerida", min_value=1, value=1)
                
                btn_add_r = st.form_submit_button("➕ Agregar Requisito")
                if btn_add_r and nuevo_req_nombre:
                    agregar_requisito_etapa(etapa_sel_cfg, nuevo_req_nombre, 1 if es_grupo_cb else 0, tipo_grupo_sel, int(cant_req_num))
                    st.success("✅ Requisito agregado exitosamente.")
                    st.rerun()

        with tab_cfg_sec:
            st.subheader("Cambiar Contraseña de Usuario")
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
                            st.success("✅ Contraseña actualizada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

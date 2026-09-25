import streamlit as st
import sqlite3
import json
import hashlib
import os
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

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios Administrativos del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    # Tabla de Pacientes / Residentes de la Comunidad
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
    # Tabla de Entrevistas de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    # Tabla de Medicamentos e Inventario
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
    # Tabla de Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    # Tabla de Grupos Terapéuticos (Terapia de Grupo, Aquí y Ahora, Feedback)
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
    # Tabla de Historial de Cambios de Etapa
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
    # Tabla de Requisitos por Etapa (Configurable)
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')
    
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
                  
    # Poblar Requisitos Iniciales de Etapas si está vacía
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
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

# --- FUNCIONES DE RESPALDO Y RESTAURACIÓN ---
def obtener_bytes_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            return f.read()
    return b""

def restaurar_bytes_db(bytes_data):
    with open(DB_FILE, "wb") as f:
        f.write(bytes_data)
    init_db()

# --- FUNCIONES DE PACIENTES Y USUARIOS ---
def generar_siguiente_folio():
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
            except:
                pass
    return f"PAC-{max_num + 1:03d}"

def verificar_duplicado_nombre(nombre, paciente_id_actual=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(nombre_completo) = LOWER(?)', (nombre.strip(),))
    rows = c.fetchall()
    conn.close()
    for r in rows:
        if r[0] != paciente_id_actual:
            return r
    return None

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', tipo_usuario='Paciente', usuario='admin'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACOGIDA', ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, fecha_ingreso, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "paciente_id": row[0],
            "nombre_completo": row[1],
            "fecha_ingreso": row[2],
            "fecha_nacimiento": row[3],
            "sexo": row[4],
            "estatus": row[5],
            "tipo_usuario": row[6],
            "etapa_actual": row[7],
            "fecha_inicio_etapa": row[8],
            "hermano_mayor_id": row[9],
            "fecha_suelta_hermano": row[10]
        }
    return None

def listar_pacientes_completos(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa FROM pacientes WHERE estatus = "A" ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa FROM pacientes ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREVISTA ---
def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
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

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, lista_meds, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(lista_meds, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE medicamentos 
            SET fecha_modificacion = ?, meds_json = ?, observaciones = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (fecha_actual, meds_json, observaciones, usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario))
        
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

def registrar_entrega_medicamento(paciente_id, detalle_entrega, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_entrega, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, usuario, detalle_json))
    
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS Y ETAPAS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_actual, usuario))
    
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, tipo_grupo, etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM grupos_terapeutos 
        WHERE paciente_id = ? AND tipo_grupo = ? AND etapa_al_momento = ?
    ''', (paciente_id, tipo_grupo, etapa))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro 
        FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def promover_etapa_paciente(paciente_id, etapa_origen, etapa_destino, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_hoy = date.today().strftime("%Y-%m-%d")
    
    c.execute('''
        UPDATE pacientes 
        SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (etapa_destino, fecha_hoy, fecha_actual, paciente_id))
    
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario))
    
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        UPDATE pacientes 
        SET hermano_mayor_id = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (hermano_mayor_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_hoy = date.today().strftime("%Y-%m-%d")
    c.execute('''
        UPDATE pacientes 
        SET fecha_suelta_hermano = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (fecha_hoy, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ?', (etapa,))
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

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Expediente Clinico y Seguimiento Individual", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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

def generar_pdf(paciente_id, datos):
    p_info = obtener_paciente(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Encabezado del Paciente
    pdf.set_font("Helvetica", "B", 11)
    if p_info:
        pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(p_info['nombre_completo'])} ({paciente_id})", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 5, f"Fecha de Ingreso: {p_info['fecha_ingreso']} | Fecha Nacimiento: {p_info['fecha_nacimiento']} | Sexo: {p_info['sexo']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(pdf.epw, 5, f"Etapa Actual: {p_info['etapa_actual']} | Tipo: {p_info['tipo_usuario']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "ENTREVISTA INICIAL DE CONSEJERIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla de Consumo
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
    
    # Sustancia de Impacto
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Normalmente consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Disposición al Cambio
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION DE LA SESION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_grupos(paciente_id):
    p_info = obtener_paciente(paciente_id)
    grupos = listar_grupos_paciente(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "EXPEDIENTE DE GRUPOS TERAPEUTICOS", new_x="LMARGIN", new_y="NEXT")
    if p_info:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 5, f"PACIENTE: {limpiar_texto(p_info['nombre_completo'])} ({paciente_id}) | Etapa: {p_info['etapa_actual']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        
    if not grupos:
        pdf.cell(pdf.epw, 6, "No hay sesiones de grupos registradas para este paciente.", new_x="LMARGIN", new_y="NEXT")
    else:
        for g in grupos:
            gid, tipo_g, etapa_m, f_grupo, fac, d_json, f_reg = g
            datos = json.loads(d_json)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"GRUPO: {limpiar_texto(tipo_g).upper()} | Fecha: {f_grupo} | Etapa: {etapa_m}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(pdf.epw, 5, f"Facilitador: {limpiar_texto(fac)}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 8)
            
            if tipo_g == "Feedback":
                pdf.multi_cell(pdf.epw, 4, f"Logros: {limpiar_texto(datos.get('logros', ''))}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(pdf.epw, 4, f"Dificultades: {limpiar_texto(datos.get('dificultades', ''))}", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(pdf.epw, 4, f"Compartimiento: {limpiar_texto(datos.get('compartimiento', ''))}", new_x="LMARGIN", new_y="NEXT")
                
            pdf.multi_cell(pdf.epw, 4, f"Observaciones: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(pdf.epw, 4, f"Devoluciones: {limpiar_texto(datos.get('devoluciones', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(pdf.epw, 4, f"Como se queda y compromiso: {limpiar_texto(datos.get('compromiso', ''))}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            pdf.cell(pdf.epw, 0.1, "", border="T", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            
    pdf_filename = f"Grupos_Terapeutos_{paciente_id}.pdf"
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

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🌱 Sawabona Shikoba</h2>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>Sistema de Control de Usuarios y Comunidad Terapéutica</h4>", unsafe_allow_html=True)
    
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
    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación del Sistema",
        [
            "👤 Registro de Usuarios",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "📝 Nueva Entrevista / Editar",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas y Compras de Farmacia",
            "🔍 Buscar y Listar Pacientes",
            "📦 Respaldo y Restauración",
            "⚙️ Configuración del Sistema"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 0: REGISTRO DE USUARIOS ---
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro y Gestión de Usuarios de la Comunidad")
        st.caption("Alta inicial de residentes, asignación de tipo de usuario y edición de expedientes")
        
        modo_usuario = st.radio("Modo de Operación", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        edit_paciente_id = ""
        datos_p_edit = None
        
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            todos_p_edit = listar_pacientes_completos(solo_activos=False)
            if not todos_p_edit:
                st.warning("No hay usuarios registrados aún para editar.")
            else:
                dict_p_edit = {f"{p[1]} ({p[0]}) - Estatus: {p[5]}": p[0] for p in todos_p_edit}
                sel_edit = st.selectbox("🔑 Selecciona el Usuario a Editar", list(dict_p_edit.keys()))
                edit_paciente_id = dict_p_edit[sel_edit]
                datos_p_edit = obtener_paciente(edit_paciente_id)
                st.info(f"✏️ Editando registro de **{datos_p_edit['nombre_completo']}** (Folio: **{edit_paciente_id}**)")

        with st.form("form_registro_usuario"):
            c1, c2 = st.columns(2)
            with c1:
                if modo_usuario == "🆕 Registrar Nuevo Usuario":
                    sug_folio = generar_siguiente_folio()
                    reg_paciente_id = st.text_input("🔑 Folio / ID de Paciente *", value=sug_folio).strip()
                else:
                    reg_paciente_id = st.text_input("🔑 Folio / ID de Paciente *", value=edit_paciente_id, disabled=True)
                    
                val_nombre = datos_p_edit["nombre_completo"] if datos_p_edit else ""
                reg_nombre_completo = st.text_input("👤 Nombre Completo *", value=val_nombre).strip()
                
                tipo_options = ["Paciente", "Servidor / Staff"]
                idx_tipo = 0
                if datos_p_edit and datos_p_edit["tipo_usuario"] in tipo_options:
                    idx_tipo = tipo_options.index(datos_p_edit["tipo_usuario"])
                reg_tipo_usuario = st.selectbox("🏷️ Tipo de Usuario", tipo_options, index=idx_tipo)
                
            with c2:
                val_ingreso = datetime.strptime(datos_p_edit["fecha_ingreso"], "%Y-%m-%d").date() if datos_p_edit and datos_p_edit["fecha_ingreso"] else date.today()
                reg_f_ingreso = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=val_ingreso)
                
                val_nac = datetime.strptime(datos_p_edit["fecha_nacimiento"], "%Y-%m-%d").date() if datos_p_edit and datos_p_edit["fecha_nacimiento"] else date(1990, 1, 1)
                reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=val_nac, min_value=date(1920, 1, 1), max_value=date.today())
                
                sexo_options = ["Masculino", "Femenino", "Otro"]
                idx_sexo = 0
                if datos_p_edit and datos_p_edit["sexo"] in sexo_options:
                    idx_sexo = sexo_options.index(datos_p_edit["sexo"])
                reg_sexo = st.selectbox("🧬 Sexo", sexo_options, index=idx_sexo)
                
            st.divider()
            estatus_options = ["A - Activo", "B - Bloqueado"]
            idx_est = 0
            if datos_p_edit and datos_p_edit["estatus"] == 'B':
                idx_est = 1
            reg_estatus_sel = st.selectbox("🔒 Estatus del Registro", estatus_options, index=idx_est)
            reg_estatus = 'A' if reg_estatus_sel.startswith('A') else 'B'
            
            btn_guardar_usuario = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True)
            
            if btn_guardar_usuario:
                if not reg_nombre_completo:
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                elif modo_usuario == "🆕 Registrar Nuevo Usuario":
                    dup = verificar_duplicado_nombre(reg_nombre_completo)
                    if dup:
                        dup_id, dup_nom, dup_est = dup
                        est_txt = "ACTIVO ('A')" if dup_est == 'A' else "BLOQUEADO ('B')"
                        st.error(f"❌ Imposible registrar: Ya existe un usuario registrado con el nombre '**{dup_nom}**' bajo el Folio **{dup_id}** (Estatus actual: {est_txt}). No se permiten registros duplicados.")
                    else:
                        guardar_usuario_paciente(reg_paciente_id, reg_nombre_completo, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, reg_estatus, reg_tipo_usuario, st.session_state["username"])
                        st.toast(f"🎉 ¡Usuario {reg_nombre_completo} registrado con Folio {reg_paciente_id}!")
                        st.success(f"✅ ¡Usuario {reg_nombre_completo} registrado exitosamente con Folio **{reg_paciente_id}**!")
                        st.balloons()
                else:
                    guardar_usuario_paciente(edit_paciente_id, reg_nombre_completo, str(reg_f_ingreso), str(reg_f_nacimiento), reg_sexo, reg_estatus, reg_tipo_usuario, st.session_state["username"])
                    st.toast(f"🎉 ¡Usuario {reg_nombre_completo} actualizado correctamente!")
                    st.success(f"✅ ¡Usuario **{reg_nombre_completo}** ({edit_paciente_id}) actualizado exitosamente!")

        st.divider()
        st.subheader("📋 Directorio General de Usuarios")
        tab_act, tab_bloq = st.tabs(["🟢 Usuarios Activos ('A')", "🔒 Usuarios Bloqueados ('B')"])
        
        with tab_act:
            p_activos = listar_pacientes_completos(solo_activos=True)
            if not p_activos:
                st.info("No hay usuarios activos actualmente.")
            else:
                for p in p_activos:
                    pid, pnom, fing, fnac, psex, pest, ptipo, petapa, pfetapa = p
                    with st.expander(f"👤 **{pnom}** ({pid}) - {ptipo} | Etapa: {petapa}"):
                        st.write(f"**Fecha Ingreso:** {fing} | **Fecha Nacimiento:** {fnac} | **Sexo:** {psex}")
                        st.write(f"**Etapa Actual:** {petapa} | **Tipo:** {ptipo}")

        with tab_bloq:
            todos_p = listar_pacientes_completos(solo_activos=False)
            p_bloq = [p for p in todos_p if p[5] == 'B']
            if not p_bloq:
                st.info("No hay usuarios bloqueados.")
            else:
                for p in p_bloq:
                    pid, pnom, fing, fnac, psex, pest, ptipo, petapa, pfetapa = p
                    with st.expander(f"🔒 **{pnom}** ({pid}) - BLOQUEADO"):
                        st.write(f"**Fecha Ingreso:** {fing} | **Fecha Nacimiento:** {fnac}")

    # --- SECCIÓN 1: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Avance de Pacientes")
        st.caption("Seguimiento del proceso de 7 meses, 5 etapas y asignación de Hermano Mayor")
        
        pacientes_activos = [p for p in listar_pacientes_completos(solo_activos=True) if p[6] == 'Paciente']
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados para evaluar etapas.")
        else:
            dict_pacientes = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_activos}
            sel_paciente = st.selectbox("🔑 Selecciona el Paciente", list(dict_pacientes.keys()))
            p_id_sel = dict_pacientes[sel_paciente]
            p_info = obtener_paciente(p_id_sel)
            
            dias_etapas_dict = {
                "ACOGIDA": 30,
                "IDENTIFICACIÓN": 60,
                "ELABORACIÓN": 60,
                "CONSOLIDACIÓN": 30,
                "SERVICIO SOCIAL": 30
            }
            etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            
            etapa_actual = p_info["etapa_actual"]
            dias_req_etapa = dias_etapas_dict.get(etapa_actual, 30)
            
            f_ingreso_dt = datetime.strptime(p_info["fecha_ingreso"], "%Y-%m-%d").date()
            f_etapa_dt = datetime.strptime(p_info["fecha_inicio_etapa"], "%Y-%m-%d").date() if p_info["fecha_inicio_etapa"] else f_ingreso_dt
            
            dias_en_etapa = (date.today() - f_etapa_dt).days
            dias_totales_comunidad = (date.today() - f_ingreso_dt).days
            
            st.markdown(f"### 📌 Expediente de Proceso: **{p_info['nombre_completo']}** ({p_id_sel})")
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Etapa Actual", etapa_actual)
            col_m2.metric("Días en Etapa Actual", f"{dias_en_etapa} / {dias_req_etapa} días")
            col_m3.metric("Días Totales Estancia", f"{dias_totales_comunidad} días")
            
            if dias_req_etapa - dias_en_etapa <= 5 and dias_req_etapa - dias_en_etapa > 0:
                col_m4.error(f"🚨 Faltan {dias_req_etapa - dias_en_etapa} días para solicitar Cambio de Etapa")
            elif dias_en_etapa >= dias_req_etapa:
                col_m4.success("✅ ¡Días completados! Listo para cambio de etapa")
            else:
                col_m4.info(f"⏳ Restan {dias_req_etapa - dias_en_etapa} días")
                
            st.progress(min(dias_en_etapa / dias_req_etapa, 1.0))
            
            tab_et1, tab_et2, tab_et3 = st.tabs(["📋 Checklist de Requisitos para Cambio de Etapa", "🤝 Hermano Mayor / Acompañamiento", "📜 Historial de Cambios de Etapa"])
            
            with tab_et1:
                st.subheader(f"Checklist de Requisitos para Etapa: {etapa_actual}")
                reqs_db = obtener_requisitos_etapa(etapa_actual)
                
                c_terapia = contar_grupos_paciente_etapa(p_id_sel, "Terapia de Grupo", etapa_actual)
                c_aquiyahora = contar_grupos_paciente_etapa(p_id_sel, "Aquí y Ahora", etapa_actual)
                c_feedback = contar_grupos_paciente_etapa(p_id_sel, "Feedback", etapa_actual)
                
                st.write(f"📊 **Grupos registrados en {etapa_actual}**: Terapia de Grupo: **{c_terapia}** | Aquí y Ahora: **{c_aquiyahora}** | Feedbacks: **{c_feedback}**")
                
                reqs_completos = 0
                total_reqs = len(reqs_db)
                
                with st.form("form_checklist_etapa"):
                    for r_id, r_text, es_grp in reqs_db:
                        if es_grp:
                            is_met = False
                            if "Terapia de Grupo" in r_text and c_terapia >= 2:
                                is_met = True
                            elif "Aquí y Ahora" in r_text and c_aquiyahora >= 2:
                                is_met = True
                            elif "Feedbacks" in r_text and c_feedback >= 2:
                                is_met = True
                            
                            if is_met:
                                st.checkbox(f"✅ {r_text} (Completado automáticamente por sistema)", value=True, disabled=True)
                                reqs_completos += 1
                            else:
                                st.checkbox(f"❌ {r_text} (Pendientes grupos en sistema)", value=False, disabled=True)
                        else:
                            chk = st.checkbox(f"📝 {r_text}")
                            if chk:
                                reqs_completos += 1
                                
                    st.divider()
                    st.write(f"**Progreso de Requisitos:** {reqs_completos} / {total_reqs}")
                    
                    idx_actual = etapas_orden.index(etapa_actual)
                    if idx_actual < len(etapas_orden) - 1:
                        siguiente_etapa = etapas_orden[idx_actual + 1]
                        btn_promover = st.form_submit_button(f"🚀 Promover Paciente a Etapa: {siguiente_etapa}", use_container_width=True)
                        
                        if btn_promover:
                            if reqs_completos < total_reqs:
                                st.error("⚠️ No se puede promover de etapa hasta completar el 100% de los requisitos del checklist.")
                            else:
                                promover_etapa_paciente(p_id_sel, etapa_actual, siguiente_etapa, st.session_state["username"])
                                st.toast(f"🎉 ¡{p_info['nombre_completo']} promovido a {siguiente_etapa}!")
                                st.success(f"✅ ¡{p_info['nombre_completo']} promovido exitosamente a la etapa **{siguiente_etapa}**!")
                                st.rerun()
                    else:
                        st.success("🎉 El paciente se encuentra en la etapa final de SERVICIO SOCIAL.")

            with tab_et2:
                st.subheader("🤝 Control de Hermano Menor y Hermano Mayor")
                if etapa_actual == "ACOGIDA":
                    st.info("📌 Los pacientes en etapa ACOGIDA ingresan como **Hermano Menor** durante los primeros 15 días.")
                    
                    if p_info["hermano_mayor_id"]:
                        h_mayor_info = obtener_paciente(p_info["hermano_mayor_id"])
                        h_nombre = h_mayor_info["nombre_completo"] if h_mayor_info else p_info["hermano_mayor_id"]
                        st.success(f"👤 **Hermano Mayor Asignado**: {h_nombre}")
                    else:
                        st.warning("⚠️ Sin Hermano Mayor asignado aún.")
                        
                    if p_info["fecha_suelta_hermano"]:
                        st.success(f"🔓 **Hermano Mayor lo soltó el:** {p_info['fecha_suelta_hermano']}")
                    else:
                        st.info(f"⏳ **Suelta programada (a los 15 días):** {f_ingreso_dt + date.resolution * 15}")
                        
                    st.divider()
                    col_hm1, col_hm2 = st.columns(2)
                    with col_hm1:
                        consejeros_mayores = [p for p in listar_pacientes_completos(solo_activos=True) if p[0] != p_id_sel]
                        dict_hm = {f"{p[1]} ({p[0]}) - {p[6]}": p[0] for p in consejeros_mayores}
                        if dict_hm:
                            sel_hm = st.selectbox("Asignar/Cambiar Hermano Mayor", list(dict_hm.keys()))
                            if st.button("💾 Asignar Hermano Mayor"):
                                asignar_hermano_mayor(p_id_sel, dict_hm[sel_hm])
                                st.toast("🎉 ¡Hermano Mayor asignado correctamente!")
                                st.success(f"✅ ¡Hermano Mayor asignado exitosamente!")
                                st.rerun()
                    with col_hm2:
                        if not p_info["fecha_suelta_hermano"]:
                            if st.button("🔓 Marcar que Hermano Mayor lo Suelta (Cumplió 15 días)"):
                                registrar_suelta_hermano(p_id_sel)
                                st.toast("🎉 ¡Se registró la suelta del Hermano Mayor!")
                                st.success("✅ ¡Se registró la suelta del Hermano Mayor!")
                                st.rerun()
                else:
                    st.info("Este paciente ya superó la etapa de ACOGIDA y puede desempeñarse como Hermano Mayor de nuevos ingresos.")

            with tab_et3:
                st.subheader("📜 Historial de Cambios de Etapa")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza FROM historial_etapas WHERE paciente_id = ? ORDER BY id DESC', (p_id_sel,))
                h_rows = c.fetchall()
                conn.close()
                if not h_rows:
                    st.write("No hay historial de promovimiento previo para este paciente.")
                else:
                    for h in h_rows:
                        st.write(f"🟢 **{h[0]} ➔ {h[1]}** | Fecha: {h[2]} | Autorizó: {h[3]}")

    # --- SECCIÓN 2: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro y Consulta de Grupos Terapéuticos")
        st.caption("Captura de Terapia de Grupo, Aquí y Ahora y Feedbacks por paciente")
        
        pacientes_activos = [p for p in listar_pacientes_completos(solo_activos=True) if p[6] == 'Paciente']
        if not pacientes_activos:
            st.warning("No hay pacientes activos registrados para grupos.")
        else:
            dict_g_pac = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p[0] for p in pacientes_activos}
            sel_g_p = st.selectbox("🔑 Selecciona el Paciente para el Grupo", list(dict_g_pac.keys()))
            p_id_g = dict_g_pac[sel_g_p]
            p_info_g = obtener_paciente(p_id_g)
            
            tab_g1, tab_g2 = st.tabs(["📝 Registrar Nuevo Grupo", "📜 Historial e Impresión de Grupos (PDF)"])
            
            with tab_g1:
                tipo_grupo = st.selectbox("📌 Tipo de Grupo Terapéutico", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                
                with st.form("form_grupo_terapeuto"):
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        f_grupo_inp = st.date_input("📅 Fecha de la Sesión", value=date.today())
                    with col_g2:
                        fac_inp = st.text_input("👤 Nombre del Facilitador", value=st.session_state["nombre_completo"])
                        
                    st.divider()
                    
                    if tipo_grupo == "Feedback":
                        logros_inp = st.text_area("🌟 Logros del Paciente (Texto largo)")
                        dificultades_inp = st.text_area("⚠️ Dificultades Identificadas (Texto largo)")
                        obs_g_inp = st.text_area("💬 Observaciones")
                        dev_g_inp = st.text_area("🔄 Devoluciones")
                        comp_inp = st.text_area("🤝 ¿Cómo se queda y a qué se compromete?")
                        datos_grupo_dict = {
                            "logros": logros_inp,
                            "dificultades": dificultades_inp,
                            "observaciones": obs_g_inp,
                            "devoluciones": dev_g_inp,
                            "compromiso": comp_inp
                        }
                    else:
                        comp_txt_inp = st.text_area("🗣️ Compartimiento (Texto largo)")
                        obs_g_inp = st.text_area("💬 Observaciones (Texto largo)")
                        dev_g_inp = st.text_area("🔄 Devoluciones (Texto largo)")
                        comp_inp = st.text_area("🤝 ¿Cómo se queda y a qué se compromete?")
                        datos_grupo_dict = {
                            "compartimiento": comp_txt_inp,
                            "observaciones": obs_g_inp,
                            "devoluciones": dev_g_inp,
                            "compromiso": comp_inp
                        }
                        
                    btn_guardar_g = st.form_submit_button("💾 Guardar Registro de Grupo", use_container_width=True)
                    
                    if btn_guardar_g:
                        guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_info_g["etapa_actual"], str(f_grupo_inp), fac_inp, datos_grupo_dict, st.session_state["username"])
                        st.toast(f"🎉 ¡Grupo de {tipo_grupo} registrado para {p_info_g['nombre_completo']}!")
                        st.success(f"✅ ¡Sesión de **{tipo_grupo}** registrada exitosamente para **{p_info_g['nombre_completo']}** ({p_id_g})!")

            with tab_g2:
                st.subheader(f"Historial de Grupos Terapéuticos: {p_info_g['nombre_completo']}")
                grupos_res = listar_grupos_paciente(p_id_g)
                
                pdf_g_file = generar_pdf_grupos(p_id_g)
                with open(pdf_g_file, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Expediente de Grupos en PDF",
                        data=f,
                        file_name=f"Grupos_{p_id_g}.pdf",
                        mime="application/pdf"
                    )
                    
                st.divider()
                if not grupos_res:
                    st.info("No hay registros de grupos aún para este paciente.")
                else:
                    for g in grupos_res:
                        gid, tipo_g, etapa_m, f_grupo, fac, d_json, f_reg = g
                        d_dict = json.loads(d_json)
                        with st.expander(f"🗣️ **{tipo_g}** - Fecha: {f_grupo} (Etapa: {etapa_m})"):
                            st.write(f"**Facilitador:** {fac}")
                            if tipo_g == "Feedback":
                                st.write(f"**Logros:** {d_dict.get('logros', '')}")
                                st.write(f"**Dificultades:** {d_dict.get('dificultades', '')}")
                            else:
                                st.write(f"**Compartimiento:** {d_dict.get('compartimiento', '')}")
                            st.write(f"**Observaciones:** {d_dict.get('observaciones', '')}")
                            st.write(f"**Devoluciones:** {d_dict.get('devoluciones', '')}")
                            st.write(f"**Compromiso:** {d_dict.get('compromiso', '')}")

    # --- SECCIÓN 3: NUEVA ENTREVISTA / EDITAR ---
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        if not pacientes_activos:
            st.warning("Debe registrar al menos un usuario en '👤 Registro de Usuarios' antes de aplicar la entrevista.")
        else:
            dict_pacientes = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_pac = st.selectbox("🔑 Selecciona el Usuario registrado para la Entrevista *", list(dict_pacientes.keys()))
            paciente_id_input = dict_pacientes[sel_pac]
            
            p_info = obtener_paciente(paciente_id_input)
            st.success(f"📌 Expediente Vinculado: **{p_info['nombre_completo']}** (Folio: **{paciente_id_input}**) | Ingreso: {p_info['fecha_ingreso']} | Nacimiento: {p_info['fecha_nacimiento']} | Sexo: {p_info['sexo']}")
            
            datos_existentes = {}
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if datos_cargados:
                st.info(f"📌 Entrevista cargada previamente. Registrada el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                datos_existentes = datos_cargados
            else:
                st.info("🆕 Complete la entrevista inicial para este paciente.")

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
                        modo_consumo = st.selectbox("Normally consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"],
                                                   index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado (Si nunca se ha abstenido marque 0)", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo en esa ocasión y qué hizo para mantenerse?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("En los últimos 6 meses, ¿cuánto es el mayor periodo sin consumir y cuándo ocurrió?", value=datos_existentes.get("abst_6meses", ""))
                    
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Actualmente, ¿qué tan importante es para usted dejar de consumir?", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("¿Quiénes integran su familia (con la que tiene mayor contacto)?", value=datos_existentes.get("familia_integrantes", ""))
                    
                    st.subheader("Factores de Riesgo")
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        relaciones_post_consumo = st.selectbox("¿Ha tenido relaciones sexuales después de consumir?", ["NO", "SÍ"],
                                                                index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_flag = st.selectbox("¿Se ha visto involucrado en abuso físico o sexual por el consumo?", ["NO", "SÍ"],
                                                  index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas presentados durante la sesión", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica la entrevista", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
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
                        "abst_6meses": abst_6meses,
                        "importancia_cambio": importancia_cambio,
                        "familia_integrantes": familia_integrantes,
                        "relaciones_post_consumo": relaciones_post_consumo,
                        "abuso_flag": abuso_flag,
                        "problemas_sesion": problemas_sesion,
                        "observaciones": observaciones,
                        "evaluador_nombre": evaluador_nombre,
                        "evaluador_cargo": evaluador_cargo
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.toast(f"🎉 ¡Entrevista guardada para {p_info['nombre_completo']}!")
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente en la base de datos!")

    # --- SECCIÓN 4: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos e Inventario por Paciente")
        st.caption("Captura de dosificación diaria y stock de existencia por usuario")
        
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        if not pacientes_activos:
            st.warning("Debe registrar al menos un usuario activo antes de configurar medicamentos.")
        else:
            dict_med_pac = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_med_pac = st.selectbox("🔑 Selecciona el Usuario *", list(dict_med_pac.keys()))
            paciente_med_id = dict_med_pac[sel_med_pac]
            
            p_info = obtener_paciente(paciente_med_id)
            st.info(f"📌 Usuario seleccionado: **{p_info['nombre_completo']}** (Folio: **{paciente_med_id}**)")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            
            with st.form("form_medicamentos"):
                st.subheader("Dosificación e Inventario de Medicamentos")
                num_meds = st.number_input("Número de medicamentos asignados", min_value=1, max_value=15, value=max(len(meds_cargados), 1))
                
                lista_meds_input = []
                for i in range(int(num_meds)):
                    m_data = meds_cargados[i] if i < len(meds_cargados) else {}
                    st.markdown(f"##### 💊 Medicamento #{i+1}")
                    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([2.5, 1, 1, 1, 1.5, 3])
                    
                    with col_m1:
                        m_nombre = st.text_input("Nombre del Medicamento", value=m_data.get("nombre", ""), key=f"med_nom_{i}")
                    with col_m2:
                        m_manana = st.number_input("☀️ Mañana", min_value=0, value=m_data.get("dosis_manana", 0), key=f"med_man_{i}")
                    with col_m3:
                        m_tarde = st.number_input("🌤️ Tarde", min_value=0, value=m_data.get("dosis_tarde", 0), key=f"med_tar_{i}")
                    with col_m4:
                        m_noche = st.number_input("🌙 Noche", min_value=0, value=m_data.get("dosis_noche", 0), key=f"med_noc_{i}")
                    with col_m5:
                        m_existencia = st.number_input("📦 Existencia", min_value=0, value=m_data.get("existencia", 0), key=f"med_exi_{i}")
                    with col_m6:
                        m_indica = st.text_input("📝 Indicaciones", value=m_data.get("indicaciones", ""), key=f"med_ind_{i}")
                        
                    if m_nombre.strip():
                        lista_meds_input.append({
                            "nombre": m_nombre.strip(),
                            "dosis_manana": m_manana,
                            "dosis_tarde": m_tarde,
                            "dosis_noche": m_noche,
                            "existencia": m_existencia,
                            "indicaciones": m_indica
                        })
                    st.divider()
                    
                obs_meds_inp = st.text_area("⚠️ Observaciones de Medicación / Alergias", value=obs_cargadas)
                btn_guardar_meds = st.form_submit_button("💾 Guardar Medicamentos e Inventario", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_med_id, lista_meds_input, obs_meds_inp, st.session_state["username"])
                    st.toast(f"🎉 ¡Medicamentos de {p_info['nombre_completo']} guardados!")
                    st.success(f"✅ ¡Esquema de medicamentos para **{p_info['nombre_completo']}** ({paciente_med_id}) guardado correctamente!")

    # --- SECCIÓN 5: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega de Medicamentos a Usuarios")
        st.caption("Registro de entrega diaria y descuento automático de inventario")
        
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        if not pacientes_activos:
            st.warning("Debe registrar al menos un usuario activo.")
        else:
            dict_ent_pac = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_ent_pac = st.selectbox("🔑 Selecciona el Usuario para Entrega *", list(dict_ent_pac.keys()))
            pac_ent_id = dict_ent_pac[sel_ent_pac]
            p_info = obtener_paciente(pac_ent_id)
            
            meds_disp, obs_meds, _, _, _ = obtener_medicamentos(pac_ent_id)
            meds_con_stock = [m for m in meds_disp if m.get("existencia", 0) > 0]
            
            if not meds_con_stock:
                st.warning(f"⚠️ **{p_info['nombre_completo']}** no tiene medicamentos registrados con existencia disponible (Stock > 0).")
            else:
                with st.form("form_entrega_meds"):
                    st.subheader(f"Entregar Medicamentos a: {p_info['nombre_completo']}")
                    cantidades_entrega = {}
                    
                    for idx, m in enumerate(meds_con_stock):
                        mnom = m["nombre"]
                        ex_actual = m["existencia"]
                        dosis_diaria = m["dosis_manana"] + m["dosis_tarde"] + m["dosis_noche"]
                        val_default = min(dosis_diaria if dosis_diaria > 0 else 1, ex_actual)
                        
                        col_e1, col_e2, col_e3 = st.columns([3, 2, 2])
                        with col_e1:
                            st.write(f"💊 **{mnom}** | Dosis Diaria: {dosis_diaria}")
                        with col_e2:
                            st.write(f"📦 Stock Disponible: **{ex_actual}**")
                        with col_e3:
                            cant_ent = st.number_input("Cantidad a entregar", min_value=1, max_value=ex_actual, value=val_default, key=f"ent_{idx}")
                            cantidades_entrega[mnom] = cant_ent
                        st.divider()
                        
                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                    
                    if btn_confirmar_entrega:
                        nuevos_meds = []
                        detalle_entrega = []
                        for m in meds_disp:
                            mnom = m["nombre"]
                            if mnom in cantidades_entrega:
                                c_ent = cantidades_entrega[mnom]
                                m["existencia"] = m["existencia"] - c_ent
                                detalle_entrega.append({"nombre": mnom, "entregado": c_ent, "quedan": m["existencia"]})
                            nuevos_meds.append(m)
                            
                        guardar_medicamentos(pac_ent_id, nuevos_meds, obs_meds, st.session_state["username"])
                        registrar_entrega_medicamento(pac_ent_id, detalle_entrega, st.session_state["username"])
                        st.toast(f"🎉 ¡Entrega registrada para {p_info['nombre_completo']}!")
                        st.success(f"✅ ¡Entrega registrada exitosamente para **{p_info['nombre_completo']}** ({pac_ent_id})! Se descontaron los medicamentos del inventario.")

    # --- SECCIÓN 6: ALERTAS Y COMPRAS ---
    elif menu == "🚨 Alertas y Compras de Farmacia":
        st.title("🚨 Alertas de Existencia e Inventario de Farmacia")
        st.caption("Cálculo automático de necesidades de reabastecimiento por usuario activo")
        
        pacientes_activos = listar_pacientes_completos(solo_activos=True)
        alertas_compras = []
        
        for p in pacientes_activos:
            pid = p[0]
            pnom = p[1]
            meds, _, _, _, _ = obtener_medicamentos(pid)
            for m in meds:
                mnom = m["nombre"]
                ex = m["existencia"]
                d_diaria = m["dosis_manana"] + m["dosis_tarde"] + m["dosis_noche"]
                if d_diaria > 0:
                    dias_cobertura = ex / d_diaria
                    if dias_cobertura <= 3:
                        cant_sugerida = max((d_diaria * 7) - ex, d_diaria)
                        alertas_compras.append({
                            "paciente_id": pid,
                            "nombre_completo": pnom,
                            "medicamento": mnom,
                            "existencia": ex,
                            "dosis_diaria": d_diaria,
                            "dias_cobertura": dias_cobertura,
                            "sugerido_comprar": cant_sugerida
                        })
                        
        col_a1, col_a2 = st.columns(2)
        criticas = [a for a in alertas_compras if a["dias_cobertura"] < 1]
        preventivas = [a for a in alertas_compras if a["dias_cobertura"] >= 1]
        
        col_a1.metric("🚨 Alertas Críticas (< 1 día)", len(criticas))
        col_a2.metric("⚠️ Alertas Preventivas (< 3 días)", len(preventivas))
        
        st.divider()
        if not alertas_compras:
            st.success("🟢 ¡Excelente! Todos los usuarios activos tienen inventario suficiente para más de 3 días.")
        else:
            st.subheader("📋 Detalle de Alertas por Paciente")
            for a in alertas_compras:
                if a["dias_cobertura"] < 1:
                    st.error(f"🚨 **{a['nombre_completo']}** ({a['paciente_id']}) | Medicamento: **{a['medicamento']}** | Existencia: **{a['existencia']}** | Dosis Diaria: **{a['dosis_diaria']}** (Se agota en < 1 día)")
                else:
                    st.warning(f"⚠️ **{a['nombre_completo']}** ({a['paciente_id']}) | Medicamento: **{a['medicamento']}** | Existencia: **{a['existencia']}** | Dosis Diaria: **{a['dosis_diaria']}** (Alcanza para {a['dias_cobertura']:.1f} días)")

    # --- SECCIÓN 7: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro y Expedientes de Pacientes")
        
        ver_bloq = st.checkbox("Mostrar también usuarios bloqueados ('B')")
        pacientes = listar_pacientes_completos(solo_activos=not ver_bloq)
        
        if not pacientes:
            st.warning("No hay pacientes registrados aún.")
        else:
            st.subheader(f"Total de registros encontrados: {len(pacientes)}")
            for pac in pacientes:
                pid, pnom, fing, fnac, psex, pest, ptipo, petapa, pfetapa = pac
                with st.expander(f"👤 **{pnom}** (Folio: **{pid}**) - {ptipo} | Estatus: {pest} | Etapa: {petapa}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.write(f"**Fecha Ingreso:** {fing} | **Fecha Nacimiento:** {fnac} | **Sexo:** {psex}")
                        st.write(f"**Etapa Actual:** {petapa} | **Tipo Usuario:** {ptipo}")
                    with c_det2:
                        datos_p, _, _, _ = obtener_entrevista(pid)
                        if datos_p:
                            pdf_file = generar_pdf(pid, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar PDF / Imprimir Entrevista",
                                    data=f,
                                    file_name=f"Entrevista_{pid}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{pid}"
                                )

    # --- SECCIÓN 8: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Guarda una copia de seguridad completa de tus datos y recupéralos en cualquier momento")
        
        tab_b1, tab_b2 = st.tabs(["📥 Descargar Respaldo Seguro (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_b1:
            st.subheader("📥 Descargar Copia de Seguridad")
            st.write("Puedes descargar el archivo completo de la base de datos (`sistema_pacientes.db`) a tu computadora o teléfono. Este archivo contiene **todos tus usuarios, entrevistas, medicamentos, entregas, grupos e historial de etapas**.")
            
            db_bytes = obtener_bytes_db()
            st.download_button(
                label="📥 Descargar Respaldo de Base de Datos (.db)",
                data=db_bytes,
                file_name=f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                mime="application/octet-stream",
                use_container_width=True
            )
            st.info("💡 **Recomendación:** Descarga este respaldo antes de hacer cambios al sistema o al finalizar la jornada de captura para tener tu información 100% resguardada.")
            
        with tab_b2:
            st.subheader("📤 Restaurar Copia de Seguridad")
            st.write("Si diste un reboot a la aplicación en Streamlit Cloud o quieres cargar un respaldo previo, selecciona tu archivo `.db` descargado anteriormente.")
            
            file_db_up = st.file_uploader("Selecciona el archivo de respaldo (.db)", type=["db", "sqlite"])
            if file_db_up is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                    bytes_upload = file_db_up.read()
                    restaurar_bytes_db(bytes_upload)
                    st.toast("🎉 ¡Base de datos restaurada exitosamente!")
                    st.success("✅ ¡Base de datos restaurada exitosamente! Todos tus registros han sido recuperados.")
                    st.rerun()

    # --- SECCIÓN 9: CONFIGURACIÓN DEL SISTEMA ---
    elif menu == "⚙️ Configuración del Sistema":
        st.title("⚙️ Configuración del Sistema")
        tab_cfg1, tab_cfg2 = st.tabs(["⚙️ Administración de Requisitos por Etapa", "🔐 Seguridad / Contraseña"])
        
        with tab_cfg1:
            st.subheader("Administración Dinámica de Requisitos por Etapa")
            etapa_cfg = st.selectbox("Selecciona la Etapa a Configurar", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
            
            reqs_actuales = obtener_requisitos_etapa(etapa_cfg)
            st.write(f"**Requisitos actuales para {etapa_cfg}:**")
            for r_id, r_txt, es_g in reqs_actuales:
                c_r1, c_r2 = st.columns([4, 1])
                with c_r1:
                    st.write(f"- {r_txt} {'(Contado por Grupos)' if es_g else ''}")
                with c_r2:
                    if st.button("❌ Eliminar", key=f"del_req_{r_id}"):
                        eliminar_requisito_etapa(r_id)
                        st.toast("🎉 ¡Requisito eliminado!")
                        st.success("✅ Requisito eliminado exitosamente.")
                        st.rerun()
                        
            st.divider()
            st.subheader("➕ Agregar Nuevo Requisito")
            with st.form("form_add_req"):
                nuevo_req_txt = st.text_input("Descripción del Requisito")
                es_grupo_chk = st.checkbox("¿Es un grupo que se cuenta automáticamente por sistema?")
                btn_add_req = st.form_submit_button("➕ Agregar Requisito")
                if btn_add_req:
                    if nuevo_req_txt.strip():
                        agregar_requisito_etapa(etapa_cfg, nuevo_req_txt.strip(), 1 if es_grupo_chk else 0)
                        st.toast("🎉 ¡Nuevo requisito agregado!")
                        st.success("✅ ¡Requisito agregado exitosamente!")
                        st.rerun()

        with tab_cfg2:
            st.subheader("Cambiar Contraseña de Usuario Administrador")
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
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(nueva_pass), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.toast("🎉 ¡Contraseña actualizada!")
                            st.success("✅ Contraseña actualizada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

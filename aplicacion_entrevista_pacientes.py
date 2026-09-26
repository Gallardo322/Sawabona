import streamlit as st
import sqlite3
import json
import hashlib
import os
import shutil
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

# --- FUNCIONES DE PACIENTES / RESIDENTES ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes ORDER BY ROWID DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row and row[0].startswith('PAC-'):
        try:
            num = int(row[0].replace('PAC-', '')) + 1
            return f"PAC-{num:03d}"
        except:
            pass
    return "PAC-001"

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_norm = nombre.strip().lower()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    for row in rows:
        p_id, p_nom, p_est = row
        if paciente_id_actual and p_id == paciente_id_actual:
            continue
        if p_nom.strip().lower() == nombre_norm:
            return p_id, p_nom, p_est
    return None

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, usuario, etapa_actual="ACOGIDA", fecha_inicio_etapa=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_ing = fecha_ingreso.strftime("%Y-%m-%d") if isinstance(fecha_ingreso, (date, datetime)) else str(fecha_ingreso)
    f_nac = fecha_nacimiento.strftime("%Y-%m-%d") if isinstance(fecha_nacimiento, (date, datetime)) else str(fecha_nacimiento)
    f_ini_etapa = fecha_inicio_etapa if fecha_inicio_etapa else f_ing
    est_code = 'A' if estatus.startswith('A') else 'B'
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), f_ing, f_nac, sexo, est_code, tipo_usuario, etapa_actual, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), f_ing, f_nac, sexo, est_code, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_pacientes(solo_activos=True, solo_pacientes=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes'
    conditions = []
    if solo_activos:
        conditions.append("estatus = 'A'")
    if solo_pacientes:
        conditions.append("tipo_usuario = 'Paciente'")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY nombre_completo COLLATE NOCASE ASC"
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_datos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET estatus = ?, fecha_modificacion = ? WHERE paciente_id = ?', 
              (nuevo_estatus, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), paciente_id))
    conn.commit()
    conn.close()

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
def guardar_medicamentos(paciente_id, meds_lista, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_lista, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE medicamentos 
            SET meds_json = ?, observaciones = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (meds_json, observaciones, fecha_actual, paciente_id))
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

def registrar_entrega_medicamentos(paciente_id, entregado_por, detalle_entrega):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, entregado_por, json.dumps(detalle_entrega, ensure_ascii=False)))
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_al_momento, str(fecha_grupo), facilitador, json.dumps(datos, ensure_ascii=False), fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_grupos_paciente(paciente_id, etapa=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if etapa:
        c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? ORDER BY fecha_grupo DESC', (paciente_id, etapa))
    else:
        c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0],
            "tipo_grupo": r[1],
            "etapa": r[2],
            "fecha": r[3],
            "facilitador": r[4],
            "datos": json.loads(r[5])
        })
    return res

def contar_grupos_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

# --- FUNCIONES DE ETAPAS & REQUISITOS ---
def promover_etapa(paciente_id, etapa_origen, etapa_destino, usuario_autoriza):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    # Actualizar etapa del paciente
    c.execute('''
        UPDATE pacientes 
        SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
        WHERE paciente_id = ?
    ''', (etapa_destino, fecha_hoy, fecha_actual, paciente_id))
    
    # Historial de cambios
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_origen, etapa_destino, fecha_hoy, usuario_autoriza))
    
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_mayor_id, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (fecha_hoy, paciente_id))
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

# --- GENERADORES DE PDF ---
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

class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SAWABONA SHIKOBA - COMUNIDAD TERAPEUTICA", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Entrevista Inicial de Consejería", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_entrevista(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p_data = obtener_datos_paciente(paciente_id)
    p_nom = p_data[1] if p_data else paciente_id
    f_ing = p_data[2] if p_data else ""
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"PACIENTE: {limpiar_texto(p_nom)} ({limpiar_texto(paciente_id)}) | Fecha Ingreso: {f_ing}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
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
    pdf.cell(pdf.epw, 6, f"Tiempo consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))} | Normalmente: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y EVALUACION CLINICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Evaluador: {limpiar_texto(datos.get('evaluador_nombre', ''))} | Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_general_meds():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(pdf.epw, 8, "LISTA GENERAL DE MEDICAMENTOS Y DOSIFICACION", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d %H:%M')}", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pacientes_activos = obtener_pacientes(solo_activos=True)
    if not pacientes_activos:
        pdf.cell(pdf.epw, 6, "No hay pacientes activos registrados.", new_x="LMARGIN", new_y="NEXT")
    else:
        for pac in pacientes_activos:
            p_id, p_nom, f_ing, f_nac, sexo, est, tipo, etapa, _, _, _ = pac
            meds, obs, _, _, _ = obtener_medicamentos(p_id)
            
            if meds:
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(p_nom)} ({p_id}) | Ingreso: {f_ing} | Etapa: {etapa}", border="B", new_x="LMARGIN", new_y="NEXT")
                
                col_w = [45, 20, 20, 20, 22, 20, 43]
                headers = ["Medicamento", "Mañana", "Tarde", "Noche", "D. Diaria", "Stock", "Indicaciones"]
                pdf.set_font("Helvetica", "B", 8)
                for i, h in enumerate(headers):
                    pdf.cell(col_w[i], 5, h, border=1, align="C")
                pdf.ln()
                
                pdf.set_font("Helvetica", "", 8)
                for m in meds:
                    m_nom = limpiar_texto(m.get("nombre", ""))
                    d_m = str(m.get("dosis_manana", 0))
                    d_t = str(m.get("dosis_tarde", 0))
                    d_n = str(m.get("dosis_noche", 0))
                    d_tot = str(int(m.get("dosis_manana", 0)) + int(m.get("dosis_tarde", 0)) + int(m.get("dosis_noche", 0)))
                    ex = str(m.get("existencia", 0))
                    ind = limpiar_texto(m.get("indicaciones", ""))
                    
                    pdf.cell(col_w[0], 5, m_nom, border=1)
                    pdf.cell(col_w[1], 5, d_m, border=1, align="C")
                    pdf.cell(col_w[2], 5, d_t, border=1, align="C")
                    pdf.cell(col_w[3], 5, d_n, border=1, align="C")
                    pdf.cell(col_w[4], 5, d_tot, border=1, align="C")
                    pdf.cell(col_w[5], 5, ex, border=1, align="C")
                    pdf.cell(col_w[6], 5, ind, border=1, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)

    fn = f"Lista_General_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(fn)
    return fn

# --- INICIALIZAR BASE DE DATOS Y SESIÓN ---
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
    st.markdown("<h3 style='text-align: center;'>Sistema de Control de Comunidad Terapéutica</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales de acceso</p>", unsafe_allow_html=True)
    
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
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Staff**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación del Sistema",
        [
            "👤 Registro y Edición de Usuarios",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "📦 Respaldo y Restauración",
            "⚙️ Configuración / Seguridad"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # =========================================================================
    # SECCIÓN 1: REGISTRO Y EDICIÓN DE USUARIOS
    # =========================================================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes / Usuarios")
        st.caption("Módulo de alta, edición de expediente, asignación de etapa inicial y gestión de estatus (Activo / Bloqueado)")
        
        modo_usuario = st.radio(
            "Seleccione la Acción a Realizar:",
            ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"],
            horizontal=True
        )
        st.divider()
        
        if modo_usuario == "🆕 Registrar Nuevo Usuario":
            folio_sugerido = generar_siguiente_folio()
            
            with st.form("form_alta_usuario"):
                st.subheader("📋 Datos del Nuevo Usuario")
                c1, c2 = st.columns(2)
                with c1:
                    reg_paciente_id = st.text_input("🔑 Folio / ID de Usuario *", value=folio_sugerido)
                    reg_nombre_completo = st.text_input("👤 Nombre Completo *", value="")
                    reg_tipo_usuario = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor / Staff"])
                with c2:
                    reg_f_ingreso = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=date.today())
                    reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=date(1990, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
                    reg_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
                
                c3, c4 = st.columns(2)
                with c3:
                    reg_etapa = st.selectbox("Etapa Inicial en el Tratamiento", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
                with c4:
                    reg_estatus = st.selectbox("Estatus Inicial", ["A - Activo", "B - Bloqueado"])
                    
                btn_guardar_usuario = st.form_submit_button("💾 Guardar Nuevo Usuario", use_container_width=True)
                
                if btn_guardar_usuario:
                    if not reg_nombre_completo.strip():
                        st.error("⚠️ El Nombre Completo es obligatorio.")
                    else:
                        dup = verificar_duplicado_nombre(reg_nombre_completo)
                        if dup:
                            dup_id, dup_nom, dup_est = dup
                            est_txt = "ACTIVO ('A')" if dup_est == 'A' else "BLOQUEADO ('B')"
                            st.error(f"❌ Imposible registrar: Ya existe un usuario registrado con el nombre '**{dup_nom}**' bajo el Folio **{dup_id}** (Estatus: {est_txt}).")
                        else:
                            guardar_usuario_paciente(reg_paciente_id, reg_nombre_completo, reg_f_ingreso, reg_f_nacimiento, reg_sexo, reg_estatus, reg_tipo_usuario, st.session_state["username"], etapa_actual=reg_etapa)
                            st.success(f"✅ ¡Usuario **{reg_nombre_completo}** registrado exitosamente con Folio **{reg_paciente_id}**!")
                            st.toast(f"🎉 ¡Usuario {reg_nombre_completo} registrado exitosamente!")
                            st.balloons()
                            
        else:
            # MODO EDICIÓN
            lista_todos = obtener_pacientes(solo_activos=False)
            if not lista_todos:
                st.info("No hay usuarios registrados en el sistema para editar.")
            else:
                opciones_edit = [f"{p[0]} - {p[1]} ({'Activo' if p[5]=='A' else 'Bloqueado'})" for p in lista_todos]
                
                # SELECCIONADOR FUERA DEL FORMULARIO
                sel_edit = st.selectbox("🔑 Selecciona el Usuario a Editar *", options=opciones_edit, key="select_user_to_edit")
                
                edit_id = sel_edit.split(" - ")[0]
                u_data = obtener_datos_paciente(edit_id)
                
                if u_data:
                    # Parsear fechas de forma segura
                    try:
                        f_ing_val = datetime.strptime(u_data[2], "%Y-%m-%d").date() if u_data[2] else date.today()
                    except:
                        f_ing_val = date.today()
                        
                    try:
                        f_nac_val = datetime.strptime(u_data[3], "%Y-%m-%d").date() if u_data[3] else date(1990, 1, 1)
                    except:
                        f_nac_val = date(1990, 1, 1)

                    st.markdown(f"### ✏️ Editando Expediente de: **{u_data[1]}** (`{edit_id}`)")
                    
                    # FORMULARIO CON CLAVE DINÁMICA SEGÚN EL ID DEL PACIENTE SELECCIONADO
                    with st.form(key=f"form_edit_{edit_id}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            edit_nombre = st.text_input("👤 Nombre Completo *", value=u_data[1], key=f"nom_{edit_id}")
                            edit_tipo = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if u_data[6]=="Paciente" else 1, key=f"tipo_{edit_id}")
                            edit_f_ingreso = st.date_input("📅 Fecha de Ingreso", value=f_ing_val, key=f"fing_{edit_id}")
                        with c2:
                            edit_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=f_nac_val, min_value=date(1920, 1, 1), max_value=date.today(), key=f"fnac_{edit_id}")
                            edit_sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=(["Masculino", "Femenino", "Otro"].index(u_data[4]) if u_data[4] in ["Masculino", "Femenino", "Otro"] else 0), key=f"sex_{edit_id}")
                            edit_estatus = st.selectbox("Estatus del Registro", ["A - Activo", "B - Bloqueado"], index=0 if u_data[5]=='A' else 1, key=f"est_{edit_id}")
                            
                        etapas_arr = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                        idx_etapa = etapas_arr.index(u_data[7]) if u_data[7] in etapas_arr else 0
                        edit_etapa = st.selectbox("Etapa Actual en el Tratamiento", etapas_arr, index=idx_etapa, key=f"etap_{edit_id}")
                        
                        btn_guardar_edit = st.form_submit_button("💾 Guardar Cambios del Usuario", use_container_width=True)
                        
                        if btn_guardar_edit:
                            if not edit_nombre.strip():
                                st.error("⚠️ El Nombre Completo es obligatorio.")
                            else:
                                dup = verificar_duplicado_nombre(edit_nombre, paciente_id_actual=edit_id)
                                if dup:
                                    st.error(f"❌ Imposible guardar: El nombre '{edit_nombre}' pertenece a otro registro ({dup[0]}).")
                                else:
                                    guardar_usuario_paciente(edit_id, edit_nombre, edit_f_ingreso, edit_f_nacimiento, edit_sexo, edit_estatus, edit_tipo, st.session_state["username"], etapa_actual=edit_etapa)
                                    st.success(f"✅ ¡Usuario **{edit_nombre}** (`{edit_id}`) actualizado exitosamente!")
                                    st.toast(f"🎉 ¡Usuario {edit_nombre} actualizado!")
                                    st.rerun()

        st.divider()
        st.subheader("📋 Directoria de Usuarios Registrados")
        
        tab_a, tab_b = st.tabs(["🟢 Usuarios Activos ('A')", "🔒 Usuarios Bloqueados ('B')"])
        
        with tab_a:
            activos = obtener_pacientes(solo_activos=True)
            if not activos:
                st.info("No hay usuarios activos registrados.")
            else:
                for p in activos:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"👤 **{p[1]}** (`{p[0]}`) | Tipo: **{p[6]}** | Etapa: **{p[7]}** | Ingreso: {p[2]}")
                    with col2:
                        if st.button("🔒 Bloquear", key=f"btn_block_{p[0]}"):
                            cambiar_estatus_paciente(p[0], 'B')
                            st.toast(f"🔒 Usuario {p[1]} bloqueado.")
                            st.rerun()
                            
        with tab_b:
            bloqueados = [p for p in obtener_pacientes(solo_activos=False) if p[5] == 'B']
            if not bloqueados:
                st.info("No hay usuarios bloqueados.")
            else:
                for p in bloqueados:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"🔒 **{p[1]}** (`{p[0]}`) | Tipo: **{p[6]}** | Etapa: **{p[7]}** | Ingreso: {p[2]}")
                    with col2:
                        if st.button("🔓 Desbloquear", key=f"btn_unblock_{p[0]}"):
                            cambiar_estatus_paciente(p[0], 'A')
                            st.toast(f"🔓 Usuario {p[1]} activado.")
                            st.rerun()

    # =========================================================================
    # RESTO DE MÓDULOS DEL SISTEMA
    # =========================================================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        pacientes_activos = obtener_pacientes(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ Primero debe dar de alta al menos a un usuario en 'Registro de Usuarios'.")
        else:
            opts = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
            p_sel = st.selectbox("🔑 Selecciona el Paciente para la Entrevista *", opts)
            p_id = p_sel.split(" - ")[0]
            
            datos_existentes, f_reg, f_mod, u_reg = obtener_entrevista(p_id)
            if datos_existentes:
                st.success(f"📌 Expediente existente cargado. Modificado por última vez el {f_mod}.")
            else:
                datos_existentes = {}
                st.info("🆕 Folio nuevo. Complete los datos para registrar la entrevista.")

            with st.form("form_entrevista"):
                st.subheader("Datos de Evaluación y Consumo")
                obs_text = st.text_area("Observaciones Generales de Consejería", value=datos_existentes.get("observaciones", ""))
                eval_nom = st.text_input("Nombre de quien aplica", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                eval_car = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero Clínico"))
                
                btn_save_ent = st.form_submit_button("💾 Guardar Expediente de Entrevista", use_container_width=True)
                if btn_save_ent:
                    guardar_entrevista(p_id, {"observaciones": obs_text, "evaluador_nombre": eval_nom, "evaluador_cargo": eval_car}, st.session_state["username"])
                    st.success("✅ ¡Expediente guardado correctamente!")
                    st.toast("🎉 ¡Entrevista guardada exitosamente!")

    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosis")
        
        if st.button("📄 Generar Lista General Alfabética de Medicamentos (PDF)"):
            pdf_fn = generar_pdf_lista_general_meds()
            with open(pdf_fn, "rb") as f:
                st.download_button("🖨️ Descargar Lista General (PDF)", data=f, file_name=pdf_fn, mime="application/pdf")
            st.toast("🎉 ¡Lista general de medicamentos generada!")
            
        pacientes_activos = obtener_pacientes(solo_activos=True)
        if pacientes_activos:
            opts = [f"{p[0]} - {p[1]}" for p in pacientes_activos]
            p_sel = st.selectbox("🔑 Selecciona el Paciente para Medicación *", opts)
            p_id = p_sel.split(" - ")[0]
            
            meds, obs, _, _, _ = obtener_medicamentos(p_id)
            st.info(f"Gestión de medicamentos para: **{p_sel}**")
            
            with st.form("form_meds"):
                m_nom = st.text_input("Nombre del Medicamento", value=meds[0].get("nombre","") if meds else "")
                d_m = st.number_input("Dosis Mañana", min_value=0, value=meds[0].get("dosis_manana",0) if meds else 0)
                d_t = st.number_input("Dosis Tarde", min_value=0, value=meds[0].get("dosis_tarde",0) if meds else 0)
                d_n = st.number_input("Dosis Noche", min_value=0, value=meds[0].get("dosis_noche",0) if meds else 0)
                ex = st.number_input("Existencia Física en Almacén", min_value=0, value=meds[0].get("existencia",0) if meds else 0)
                
                btn_med = st.form_submit_button("💾 Guardar Esquema de Medicamentos")
                if btn_med and m_nom:
                    nuevos_meds = [{"nombre": m_nom, "dosis_manana": d_m, "dosis_tarde": d_t, "dosis_noche": d_n, "existencia": ex}]
                    guardar_medicamentos(p_id, nuevos_meds, "", st.session_state["username"])
                    st.success("✅ ¡Medicamentos guardados exitosamente!")
                    st.toast("🎉 ¡Esquema de medicamentos actualizado!")

    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de la Base de Datos")
        st.caption("Asegura el trabajo realizado descargando una copia física de la base de datos completa.")
        
        tab_down, tab_up = st.tabs(["📥 Descargar Respaldo (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_down:
            st.subheader("📥 Copia de Seguridad de la Base de Datos")
            st.write("Descarga el archivo completo `.db` con todos los pacientes, medicamentos, entrevistas y etapas.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                fn_db = f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                st.download_button("📥 Descargar Respaldo de Base de Datos", data=db_bytes, file_name=fn_db, mime="application/octet-stream", use_container_width=True)
                
        with tab_up:
            st.subheader("📤 Restaurar la Base de Datos")
            st.warning("⚠️ **PRECAUCIÓN**: Subir un archivo de respaldo reemplazará los datos actuales.")
            
            file_up = st.file_uploader("Selecciona el archivo `.db` de respaldo", type=["db"])
            if file_up:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(file_up.getbuffer())
                    st.success("✅ ¡Base de datos restaurada exitosamente!")
                    st.toast("🎉 ¡Base de datos restaurada!")
                    st.rerun()

    else:
        st.title(f"📌 {menu}")
        st.info("Módulo en ejecución normal.")

print("Fixed full script generated successfully")

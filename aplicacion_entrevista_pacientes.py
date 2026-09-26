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
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    \'\'\')
    c.execute(\'\'\'
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
    \'\'\')
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    \'\'\')
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS medicamentos (
            paciente_id TEXT PRIMARY KEY,
            meds_json TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    \'\'\')
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    \'\'\')
    c.execute(\'\'\'
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
    \'\'\')
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_origen TEXT,
            etapa_destino TEXT,
            fecha_cambio TEXT,
            usuario_autoriza TEXT
        )
    \'\'\')
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    \'\'\')
    
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
                  
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
    existe = c.fetchone()
    
    if existe:
        c.execute(\'\'\'
            UPDATE pacientes
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, tipo_usuario = ?, etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        \'\'\', (nombre_completo.strip(), f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, paciente_id))
    else:
        c.execute(\'\'\'
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        \'\'\', (paciente_id, nombre_completo.strip(), f_ing, f_nac, sexo, estatus, tipo_usuario, etapa_actual, f_ini_etapa, fecha_actual, fecha_actual, usuario_reg))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_bd(estatus_filtro='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if estatus_filtro == 'TODOS':
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual FROM pacientes WHERE estatus = ? ORDER BY nombre_completo ASC', (estatus_filtro,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREVISTAS ---
def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    if existe:
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

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, meds_lista, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_lista, ensure_ascii=False)
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    if existe:
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ? WHERE paciente_id = ?', (meds_json, observaciones, fecha_actual, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)', (paciente_id, meds_json, observaciones, fecha_actual, fecha_actual, usuario))
    conn.commit()
    conn.close()

def obtener_medicamentos(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion, usuario_registro FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return [], "", None, None

def registrar_entrega_meds(paciente_id, entrega_items, entregado_por):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT meds_json FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "No se encontraron medicamentos para el paciente."
        
    meds_actuales = json.loads(row[0])
    
    for e in entrega_items:
        nombre_med = e['nombre']
        cant_entregada = e['cantidad']
        for m in meds_actuales:
            if m['nombre'] == nombre_med:
                m['existencia'] = max(0, int(m.get('existencia', 0)) - cant_entregada)
                
    meds_json_updated = json.dumps(meds_actuales, ensure_ascii=False)
    c.execute('UPDATE medicamentos SET meds_json = ?, fecha_modificacion = ? WHERE paciente_id = ?', (meds_json_updated, fecha_actual, paciente_id))
    
    detalle_json = json.dumps(entrega_items, ensure_ascii=False)
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)', (paciente_id, fecha_actual, entregado_por, detalle_json))
    
    conn.commit()
    conn.close()
    return True, "Entrega registrada exitosamente."

# --- FUNCIONES DE GRUPOS Y ETAPAS ---
def guardar_grupo_terapeuto(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos, usuario_reg):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_grp = fecha_grupo.strftime("%Y-%m-%d") if isinstance(fecha_grupo, (date, datetime)) else str(fecha_grupo)
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute(\'\'\'
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    \'\'\', (paciente_id, tipo_grupo, etapa_al_momento, f_grp, facilitador, datos_json, fecha_actual, usuario_reg))
    
    conn.commit()
    conn.close()

def contar_grupos_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(\'\'\'
        SELECT COUNT(*) FROM grupos_terapeutos 
        WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?
    \'\'\', (paciente_id, etapa, tipo_grupo))
    count = c.fetchone()[0]
    conn.close()
    return count

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(\'\'\'
        SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro
        FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC
    \'\'\', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def cambiar_etapa_paciente(paciente_id, etapa_origen, etapa_destino, usuario_autoriza):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    
    c.execute(\'\'\'
        UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ?, fecha_modificacion = ? WHERE paciente_id = ?
    \'\'\', (etapa_destino, f_hoy, fecha_actual, paciente_id))
    
    c.execute(\'\'\'
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza)
        VALUES (?, ?, ?, ?, ?)
    \'\'\', (paciente_id, etapa_origen, etapa_destino, fecha_actual, usuario_autoriza))
    
    conn.commit()
    conn.close()

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET hermano_mayor_id = ?, fecha_modificacion = ? WHERE paciente_id = ?', (hermano_mayor_id, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f_hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ?, fecha_modificacion = ? WHERE paciente_id = ?', (f_hoy, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADORES DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SAWABONA SHIKOBA - CLINICA DE TRATAMIENTO DE ADICCIONES", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Comunidad Terapeutica y Centro de Rehabilitacion", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p = obtener_paciente(paciente_id)
    p_nom = p[1] if p else paciente_id
    f_ing = p[2] if p else ""
    f_nac = p[3] if p else ""
    sexo = p[4] if p else ""
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"EXPEDIENTE CLINICO - NÚMERO DE PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Nombre del Paciente: {limpiar_texto(p_nom)} | Fecha Ingreso: {f_ing} | Nacimiento: {f_nac} | Sexo: {sexo}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "1. DATOS GENERALES Y SOCIO-DEMOGRÁFICOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "2. CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
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
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))} | Modo: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "3. DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir: {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "4. OBSERVACIONES Y EVALUACION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
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
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTA GENERAL DE MEDICAMENTOS Y DOSIS - PACIENTES ACTIVOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(pdf.epw, 6, f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pacientes = listar_pacientes_bd('A')
    
    for pac in pacientes:
        pid, pnom, fing, fnac, sexo, pest, tusr, etapa = pac
        meds, obs, fmod, ureg = obtener_medicamentos(pid)
        
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, f"Paciente: {limpiar_texto(pnom)} ({pid}) | Ingreso: {fing} | Nac: {fnac} | Sexo: {sexo}", border="B", new_x="LMARGIN", new_y="NEXT")
        
        if not meds:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(pdf.epw, 5, "Sin esquemas de medicamentos registrados.", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            continue
            
        pdf.set_font("Helvetica", "B", 8)
        col_w = [45, 20, 20, 20, 25, 22, 38]
        hdrs = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis Diaria", "Stock", "Indicaciones"]
        for i, h in enumerate(hdrs):
            pdf.cell(col_w[i], 5, h, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 8)
        for m in meds:
            m_nom = limpiar_texto(m.get('nombre', ''))
            d_man = m.get('dosis_manana', 0)
            d_tar = m.get('dosis_tarde', 0)
            d_noc = m.get('dosis_noche', 0)
            d_tot = d_man + d_tar + d_noc
            stock = m.get('existencia', 0)
            ind = limpiar_texto(m.get('indicaciones', ''))
            
            pdf.cell(col_w[0], 5, m_nom, border=1)
            pdf.cell(col_w[1], 5, str(d_man), border=1, align="C")
            pdf.cell(col_w[2], 5, str(d_tar), border=1, align="C")
            pdf.cell(col_w[3], 5, str(d_noc), border=1, align="C")
            pdf.cell(col_w[4], 5, str(d_tot), border=1, align="C")
            pdf.cell(col_w[5], 5, str(stock), border=1, align="C")
            pdf.cell(col_w[6], 5, ind, border=1, new_x="LMARGIN", new_y="NEXT")
            
        if obs:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(pdf.epw, 5, f"Observaciones / Alergias: {limpiar_texto(obs)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        
    pdf_filename = f"Lista_General_Medicamentos_Dosis_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_comprobante_entrega(paciente_id, entrega_items, entregado_por):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    p = obtener_paciente(paciente_id)
    pnom = p[1] if p else paciente_id
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "COMPROBANTE DE ENTREGA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha y Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"PACIENTE / RESIDENTE: {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"ENTREGADO POR (STAFF): {limpiar_texto(entregado_por)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [80, 45, 65]
    pdf.cell(col_w[0], 6, "Medicamento Entregado", border=1, align="C")
    pdf.cell(col_w[1], 6, "Cantidad Entregada", border=1, align="C")
    pdf.cell(col_w[2], 6, "Stock Restante", border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    meds_actuales, _, _, _ = obtener_medicamentos(paciente_id)
    meds_dict = {m['nombre']: m.get('existencia', 0) for m in meds_actuales}
    
    for item in entrega_items:
        m_nom = limpiar_texto(item['nombre'])
        cant = item['cantidad']
        stk = meds_dict.get(item['nombre'], 0)
        pdf.cell(col_w[0], 6, m_nom, border=1)
        pdf.cell(col_w[1], 6, str(cant), border=1, align="C")
        pdf.cell(col_w[2], 6, str(stk), border=1, align="C")
        pdf.ln()
        
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 6, "______________________________________", align="C")
    pdf.cell(100, 6, "______________________________________", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(90, 5, "Firma del Paciente / Residente", align="C")
    pdf.cell(100, 5, "Firma del Entregador (Staff)", new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf_filename = f"Comprobante_Entrega_Meds_{paciente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "LISTA DE COMPRAS Y REABASTECIMIENTO DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(pdf.epw, 6, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    pacientes = listar_pacientes_bd('A')
    alertas = []
    
    for pac in pacientes:
        pid, pnom, fing, fnac, sexo, pest, tusr, etapa = pac
        meds, obs, _, _ = obtener_medicamentos(pid)
        for m in meds:
            d_man = m.get('dosis_manana', 0)
            d_tar = m.get('dosis_tarde', 0)
            d_noc = m.get('dosis_noche', 0)
            d_diaria = d_man + d_tar + d_noc
            ex = m.get('existencia', 0)
            
            if d_diaria > 0 and ex <= (d_diaria * 3):
                cant_sugerida = (d_diaria * 30) - ex
                alertas.append((pid, pnom, m.get('nombre', ''), ex, d_diaria, max(1, cant_sugerida)))
                
    if not alertas:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay medicamentos pendientes por reabastecer en este momento.", align="C")
    else:
        pdf.set_font("Helvetica", "B", 8)
        col_w = [30, 55, 45, 20, 20, 20]
        hdrs = ["Folio", "Paciente", "Medicamento", "Stock", "Dosis/Dia", "Sugerido (30d)"]
        for i, h in enumerate(hdrs):
            pdf.cell(col_w[i], 6, h, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 8)
        for item in alertas:
            pid, pnom, mnom, ex, dd, cs = item
            pdf.cell(col_w[0], 6, pid, border=1)
            pdf.cell(col_w[1], 6, limpiar_texto(pnom), border=1)
            pdf.cell(col_w[2], 6, limpiar_texto(mnom), border=1)
            pdf.cell(col_w[3], 6, str(ex), border=1, align="C")
            pdf.cell(col_w[4], 6, str(dd), border=1, align="C")
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
    pdf.cell(pdf.epw, 8, f"EXPEDIENTE DE GRUPOS TERAPEUTICOS - {limpiar_texto(pnom)} ({paciente_id})", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Fecha de impresion: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    
    grupos = listar_grupos_paciente(paciente_id)
    if not grupos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay sesiones de grupos registrados para este paciente.", align="C")
    else:
        for g in grupos:
            gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
            datos = json.loads(djson)
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"GRUPO: {limpiar_texto(tgrp)} | Etapa: {etapa} | Fecha: {fgrp} | Facilitador: {limpiar_texto(fac)}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            
            if tgrp in ["Terapia de Grupo", "Aquí y Ahora"]:
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
    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario Staff**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación del Sistema",
        [
            "👤 Registro y Edición de Usuarios",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "📦 Respaldo y Restauración",
            "⚙️ Configuración / Seguridad"
        ]
    )
    
    if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # --- SECCIÓN 1: REGISTRO Y EDICIÓN DE USUARIOS ---
    # ==========================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Usuarios")
        st.caption("Modulo inicial para dar de alta y actualizar pacientes o servidores en la comunidad")
        
        modo_usuario = st.radio("Acción a Realizar", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        todos_pacientes = listar_pacientes_bd('TODOS')
        
        edit_paciente_id = None
        dados = None
        
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            if not todos_pacientes:
                st.warning("No hay usuarios registrados aún en el sistema.")
            else:
                opciones_edit = {f"{p[1]} ({p[0]})": p[0] for p in todos_pacientes}
                sel_edit = st.selectbox("🔑 Selecciona el Usuario a Editar", list(opciones_edit.keys()))
                edit_paciente_id = opciones_edit[sel_edit]
                dados = obtener_paciente(edit_paciente_id)
                
        if dados:
            v_id = dados[0]
            v_nombre = dados[1]
            try:
                v_f_ing = datetime.strptime(dados[2], "%Y-%m-%d").date() if dados[2] else date.today()
            except:
                v_f_ing = date.today()
            try:
                v_f_nac = datetime.strptime(dados[3], "%Y-%m-%d").date() if dados[3] else date(1990, 1, 1)
            except:
                v_f_nac = date(1990, 1, 1)
            v_sexo = dados[4] if dados[4] in ["Masculino", "Femenino"] else "Masculino"
            v_estatus = dados[5] if dados[5] in ["A", "B"] else "A"
            v_tipo = dados[6] if dados[6] in ["Paciente", "Servidor"] else "Paciente"
            v_etapa = dados[7] if dados[7] in ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"] else "ACOGIDA"
            try:
                v_f_ini_etapa = datetime.strptime(dados[8], "%Y-%m-%d").date() if dados[8] else v_f_ing
            except:
                v_f_ini_etapa = v_f_ing
        else:
            v_id = obtener_siguiente_id()
            v_nombre = ""
            v_f_ing = date.today()
            v_f_nac = date(1990, 1, 1)
            v_sexo = "Masculino"
            v_estatus = "A"
            v_tipo = "Paciente"
            v_etapa = "ACOGIDA"
            v_f_ini_etapa = date.today()

        form_key = f"form_usr_{edit_paciente_id if edit_paciente_id else 'nuevo'}"
        
        with st.form(form_key):
            st.subheader("Datos Basales del Usuario")
            c1, c2 = st.columns(2)
            with c1:
                reg_paciente_id = st.text_input("🔑 Folio / ID de Usuario *", value=v_id, disabled=(modo_usuario == "✏️ Modificar / Editar Usuario Existente"))
                reg_nombre_completo = st.text_input("👤 Nombre Completo *", value=v_nombre)
                reg_tipo_usuario = st.selectbox("🏷️ Tipo de Usuario", ["Paciente", "Servidor"], index=0 if v_tipo == "Paciente" else 1)
                reg_sexo = st.selectbox("🚻 Sexo", ["Masculino", "Femenino"], index=0 if v_sexo == "Masculino" else 1)
            with c2:
                reg_f_ingreso = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=v_f_ing, min_value=date(1920, 1, 1), max_value=date.today())
                reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=v_f_nac, min_value=date(1920, 1, 1), max_value=date.today())
                reg_estatus = st.selectbox("📌 Estatus", ["A - Activo", "B - Bloqueado"], index=0 if v_estatus == "A" else 1)
                reg_etapa_actual = st.selectbox("🎯 Etapa Inicial / Actual", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"], index=["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"].index(v_etapa))
                reg_f_ini_etapa = st.date_input("🗓️ Fecha de Inicio de Etapa Actual", value=v_f_ini_etapa, min_value=date(1920, 1, 1), max_value=date.today())
                
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
                        est_code = "A" if reg_estatus.startswith("A") else "B"
                        guardar_usuario_paciente(reg_paciente_id, reg_nombre_completo, reg_f_ingreso, reg_f_nacimiento, reg_sexo, est_code, reg_tipo_usuario, reg_etapa_actual, reg_f_ini_etapa, st.session_state["username"])
                        st.toast(f"🎉 ¡Usuario {reg_nombre_completo} registrado exitosamente!")
                        st.success(f"✅ ¡Usuario **{reg_nombre_completo}** registrado exitosamente con Folio **{reg_paciente_id}**!")
                        st.balloons()
                        st.rerun()
                else:
                    est_code = "A" if reg_estatus.startswith("A") else "B"
                    guardar_usuario_paciente(edit_paciente_id, reg_nombre_completo, reg_f_ingreso, reg_f_nacimiento, reg_sexo, est_code, reg_tipo_usuario, reg_etapa_actual, reg_f_ini_etapa, st.session_state["username"])
                    st.toast(f"🎉 ¡Usuario {reg_nombre_completo} actualizado exitosamente!")
                    st.success(f"✅ ¡Usuario **{reg_nombre_completo}** ({edit_paciente_id}) actualizado exitosamente!")
                    st.balloons()
                    st.rerun()
                    
        st.divider()
        st.subheader("📋 Directorio de Usuarios Registrados")
        
        tab_act, tab_bloq = st.tabs(["🟢 Usuarios Activos ('A')", "🔒 Usuarios Bloqueados ('B')"])
        
        with tab_act:
            p_act = listar_pacientes_bd('A')
            if not p_act:
                st.info("No hay usuarios activos registrados.")
            else:
                for p in p_act:
                    pid, pnom, fing, fnac, sexo, pest, tusr, etapa = p
                    c_a1, c_a2 = st.columns([4, 1])
                    with c_a1:
                        st.write(f"👤 **{pnom}** ({pid}) | Tipo: **{tusr}** | Etapa: **{etapa}** | Ingreso: {fing} | Nac: {fnac}")
                    with c_a2:
                        if st.button(f"🔒 Bloquear", key=f"bloq_{pid}"):
                            guardar_usuario_paciente(pid, pnom, fing, fnac, sexo, 'B', tusr, etapa, fing, st.session_state["username"])
                            st.toast(f"🔒 Usuario {pnom} bloqueado.")
                            st.rerun()
                            
        with tab_bloq:
            p_bloq = listar_pacientes_bd('B')
            if not p_bloq:
                st.info("No hay usuarios bloqueados.")
            else:
                for p in p_bloq:
                    pid, pnom, fing, fnac, sexo, pest, tusr, etapa = p
                    c_b1, c_b2 = st.columns([4, 1])
                    with c_b1:
                        st.write(f"🔒 **{pnom}** ({pid}) | Tipo: **{tusr}** | Etapa: **{etapa}** | Ingreso: {fing}")
                    with c_b2:
                        if st.button(f"🟢 Reactivar", key=f"react_{pid}"):
                            guardar_usuario_paciente(pid, pnom, fing, fnac, sexo, 'A', tusr, etapa, fing, st.session_state["username"])
                            st.toast(f"🟢 Usuario {pnom} reactivado.")
                            st.rerun()

    # ==========================================
    # --- SECCIÓN 2: GESTIÓN DE ETAPAS & PROCESO ---
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Seguimiento de Proceso")
        st.caption("Control de avance por las 5 etapas del programa de 7 meses de la comunidad Sawabona Shikoba")
        
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
                
            duracion_etapas = {
                "ACOGIDA": 30,
                "IDENTIFICACIÓN": 60,
                "ELABORACIÓN": 60,
                "CONSOLIDACIÓN": 30,
                "SERVICIO SOCIAL": 30
            }
            
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
            
            if dias_restantes <= 5 and dias_restantes >= 0:
                st.info(f"🚨 **ALERTA DE PROMONCIÓN**: Quedan solo **{dias_restantes} días** para cumplir los {dias_meta} días requeridos en {p_etapa}. Revise el checklist para preparar su cambio de etapa.")
            elif dias_etapa > dias_meta:
                st.warning(f"⚠️ **RESIDENTE EN REZAGO**: El paciente ha superado los {dias_meta} días estipulados para {p_etapa} (Lleva {dias_etapa} días).")
                
            st.divider()
            
            if p_etapa == "ACOGIDA":
                st.subheader("🤝 Control de Acompañamiento: Hermano Menor y Hermano Mayor")
                if dias_etapa <= 15 and not f_suelta:
                    st.info(f"🌱 **{p_nom}** está en sus primeros 15 días de ACOGIDA como **Hermano Menor**.")
                elif f_suelta:
                    st.success(f"✅ Hermano Mayor liberó a **{p_nom}** el **{f_suelta}**.")
                else:
                    st.warning(f"⚠️ Ha cumplido {dias_etapa} días en Acogida. Corresponde realizar la suelta del Hermano Mayor.")
                    
                c_hm1, c_hm2 = st.columns(2)
                with c_hm1:
                    hm_data = obtener_paciente(h_mayor_id) if h_mayor_id else None
                    hm_nom = hm_data[1] if hm_data else "Sin Asignar"
                    st.write(f"**Hermano Mayor Asignado**: {hm_nom}")
                    
                    posibles_mayores = [p for p in listar_pacientes_bd('A') if p[0] != p_id_et]
                    dict_may = {f"{p[1]} ({p[0]})": p[0] for p in posibles_mayores}
                    sel_may = st.selectbox("Asignar / Cambiar Hermano Mayor", ["-- Seleccionar --"] + list(dict_may.keys()))
                    if st.button("💾 Guardar Asignación de Hermano Mayor"):
                        if sel_may != "-- Seleccionar --":
                            id_m = dict_may[sel_may]
                            asignar_hermano_mayor(p_id_et, id_m)
                            st.toast("🎉 ¡Hermano Mayor asignado exitosamente!")
                            st.success(f"✅ Hermano Mayor asignado correctamente.")
                            st.rerun()
                with c_hm2:
                    if not f_suelta:
                        if st.button("🔓 Marcar que Hermano Mayor lo Suelta (Cumplió 15 días)"):
                            registrar_suelta_hermano(p_id_et)
                            st.toast("🎉 ¡Se registró la suelta del Hermano Mayor!")
                            st.success("✅ Se registró la suelta correctamente.")
                            st.rerun()
                st.divider()

            st.subheader(f"📋 Checklist de Requisitos para Cambio de Etapa ({p_etapa})")
            reqs = obtener_requisitos_etapa(p_etapa)
            
            c_grp_aha = contar_grupos_etapa(p_id_et, p_etapa, "Aquí y Ahora")
            c_grp_ter = contar_grupos_etapa(p_id_et, p_etapa, "Terapia de Grupo")
            c_grp_fee = contar_grupos_etapa(p_id_et, p_etapa, "Feedback")
            
            req_completos = True
            
            for req_id, req_text, es_grp in reqs:
                if es_grp == 1:
                    if "Aquí y Ahora" in req_text:
                        num_req = 4 if "4" in req_text else (2 if "2" in req_text else 1)
                        cumple = c_grp_aha >= num_req
                        if not cumple: req_completos = False
                        st.checkbox(f"🗣️ {req_text} (Avance: {c_grp_aha} / {num_req} sesiones registradas)", value=cumple, disabled=True)
                    elif "Terapia de Grupo" in req_text:
                        num_req = 4 if "4" in req_text else (2 if "2" in req_text else 1)
                        cumple = c_grp_ter >= num_req
                        if not cumple: req_completos = False
                        st.checkbox(f"🗣️ {req_text} (Avance: {c_grp_ter} / {num_req} sesiones registradas)", value=cumple, disabled=True)
                    elif "Feedback" in req_text or "Feedbacks" in req_text:
                        num_req = 4 if "4" in req_text else (2 if "2" in req_text else 1)
                        cumple = c_grp_fee >= num_req
                        if not cumple: req_completos = False
                        st.checkbox(f"🗣️ {req_text} (Avance: {c_grp_fee} / {num_req} sesiones registradas)", value=cumple, disabled=True)
                else:
                    chk_val = st.checkbox(f"📝 {req_text}", key=f"chk_{p_id_et}_{req_id}")
                    if not chk_val:
                        req_completos = False
                        
            st.divider()
            
            etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            idx_act = etapas_orden.index(p_etapa)
            
            if idx_act < len(etapas_orden) - 1:
                siguiente_etapa = etapas_orden[idx_act + 1]
                st.subheader(f"🚀 Promoción a la Siguiente Etapa: **{siguiente_etapa}**")
                
                if not req_completos:
                    st.error("❌ No se puede realizar el cambio de etapa. Faltan requisitos o sesiones de grupo por completar en la lista.")
                    st.button(f"🚀 Promover a {siguiente_etapa}", disabled=True, use_container_width=True)
                else:
                    st.success("🎉 ¡Todos los requisitos de la etapa actual están completados!")
                    if st.button(f"🚀 Promover a {siguiente_etapa}", use_container_width=True):
                        cambiar_etapa_paciente(p_id_et, p_etapa, siguiente_etapa, st.session_state["username"])
                        st.toast(f"🎉 ¡{p_nom} ha sido promovido a {siguiente_etapa}!")
                        st.success(f"✅ ¡{p_nom} promovido exitosamente a {siguiente_etapa}!")
                        st.balloons()
                        st.rerun()
            else:
                st.success("🎓 El paciente se encuentra en la última etapa (SERVICIO SOCIAL) previa a su graduación.")

    # ==========================================
    # --- SECCIÓN 3: GRUPOS TERAPÉUTICOS ---
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Modulo para capturar y consultar las sesiones de Terapia de Grupo, Aquí y Ahora y Feedbacks")
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        with tab_reg_g:
            pacientes_activos = listar_pacientes_bd('A')
            if not pacientes_activos:
                st.warning("No hay usuarios activos registrados.")
            else:
                dict_pac_g = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": (p[0], p[1], p[7]) for p in pacientes_activos}
                sel_pac_g = st.selectbox("🔑 Selecciona el Paciente", list(dict_pac_g.keys()), key="sel_grp_pac")
                p_id_g, p_nombre_g, p_etapa_g = dict_pac_g[sel_pac_g]
                
                tipo_grupo = st.selectbox("🗣️ Tipo de Grupo Terapéutico", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                
                with st.form("form_grupo_terapeuto"):
                    st.subheader(f"Formulario: {tipo_grupo}")
                    c_g1, c_g2, c_g3 = st.columns(3)
                    with c_g1:
                        st.text_input("Usuario", value=p_nombre_g, disabled=True)
                        st.text_input("Folio", value=p_id_g, disabled=True)
                    with c_g2:
                        st.text_input("Etapa Actual del Usuario", value=p_etapa_g, disabled=True)
                        f_grupo = st.date_input("Fecha del Grupo", value=date.today())
                    with c_g3:
                        facilitador_nombre = st.text_input("Nombre del Facilitador / Staff *", value=st.session_state["nombre_completo"])
                        
                    st.divider()
                    
                    if tipo_grupo in ["Terapia de Grupo", "Aquí y Ahora"]:
                        compartimiento = st.text_area("Compartimiento (Texto largo) *")
                        observaciones = st.text_area("Observaciones (Texto largo)")
                        devoluciones = st.text_area("Devoluciones (Texto largo)")
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *")
                        
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
                                guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, datos_grp, st.session_state["username"])
                                st.toast(f"🎉 ¡Sesión de {tipo_grupo} registrada exitosamente!")
                                st.success(f"✅ ¡Sesión de **{tipo_grupo}** registrada exitosamente para **{p_nombre_g}** ({p_id_g})!")
                                st.balloons()
                                st.rerun()
                    else: # Feedback
                        logros = st.text_area("Logros (Texto largo) *")
                        dificultades = st.text_area("Dificultades (Texto largo) *")
                        observaciones = st.text_area("Observaciones (Texto largo)")
                        devoluciones = st.text_area("Devoluciones (Texto largo)")
                        compromiso = st.text_area("¿Cómo se queda y a qué se compromete? *")
                        
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
                                guardar_grupo_terapeuto(p_id_g, tipo_grupo, p_etapa_g, f_grupo, facilitador_nombre, datos_grp, st.session_state["username"])
                                st.toast(f"🎉 ¡Sesión de Feedback registrada exitosamente!")
                                st.success(f"✅ ¡Sesión de **Feedback** registrada exitosamente para **{p_nombre_g}** ({p_id_g})!")
                                st.balloons()
                                st.rerun()

        with tab_hist_g:
            pacientes_todos = listar_pacientes_bd('TODOS')
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
                grupos_list = listar_grupos_paciente(p_id_h)
                if not grupos_list:
                    st.warning("Este usuario no tiene sesiones de grupo registradas.")
                else:
                    for g in grupos_list:
                        gid, tgrp, etapa, fgrp, fac, djson, freg, ureg = g
                        datos = json.loads(djson)
                        with st.expander(f"🗣️ **{tgrp}** | Fecha: {fgrp} | Etapa: {etapa} | Facilitador: {fac}"):
                            st.write(f"**Registrado por:** {ureg} el {freg}")
                            if tgrp in ["Terapia de Grupo", "Aquí y Ahora"]:
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
    # --- SECCIÓN 4: CONTROL DE MEDICAMENTOS Y DOSIS ---
    # ==========================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosis")
        st.caption("Prescripción de medicamentos por paciente y generación de lista general alfabética")
        
        st.subheader("🖨️ Lista General de Medicamentos y Dosis")
        pdf_gen_meds = generar_pdf_lista_general_meds()
        with open(pdf_gen_meds, "rb") as f:
            st.download_button(
                label="📄 Imprimir Lista General (PDF) - Todos los Pacientes Alfabéticamente",
                data=f,
                file_name=pdf_gen_meds,
                mime="application/pdf",
                key="btn_pdf_gen_meds"
            )
            
        st.divider()
        st.subheader("📋 Prescripción e Inventario Individual")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados.")
        else:
            dict_m = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_activos}
            sel_m = st.selectbox("🔑 Selecciona el Paciente para Prescripción", list(dict_m.keys()))
            p_id_m, p_nombre_m = dict_m[sel_m]
            
            meds_exist, obs_exist, _, _ = obtener_medicamentos(p_id_m)
            
            st.write(f"Prescribiendo medicamentos para: **{p_nombre_m}** ({p_id_m})")
            
            num_meds = st.number_input("Número de medicamentos a prescribir", min_value=1, max_value=10, value=max(1, len(meds_exist)))
            
            meds_input_list = []
            with st.form("form_prescripcion_meds"):
                for i in range(int(num_meds)):
                    st.markdown(f"**Medicamento #{i+1}**")
                    m_prev = meds_exist[i] if i < len(meds_exist) else {}
                    
                    cm1, cm2, cm3, cm4, cm5 = st.columns([3, 1, 1, 1, 2])
                    with cm1:
                        mnom = st.text_input(f"Nombre del Medicamento #{i+1}", value=m_prev.get('nombre', ''), key=f"mnom_{p_id_m}_{i}")
                    with cm2:
                        d_man = st.number_input(f"☀️ Mañana #{i+1}", min_value=0, value=int(m_prev.get('dosis_manana', 0)), key=f"dman_{p_id_m}_{i}")
                    with cm3:
                        d_tar = st.number_input(f"🌤️ Tarde #{i+1}", min_value=0, value=int(m_prev.get('dosis_tarde', 0)), key=f"dtar_{p_id_m}_{i}")
                    with cm4:
                        d_noc = st.number_input(f"🌙 Noche #{i+1}", min_value=0, value=int(m_prev.get('dosis_noche', 0)), key=f"dnoc_{p_id_m}_{i}")
                    with cm5:
                        exist = st.number_input(f"📦 Existencia #{i+1}", min_value=0, value=int(m_prev.get('existencia', 0)), key=f"ex_{p_id_m}_{i}")
                        
                    ind_val = st.text_input(f"Indicaciones Específicas #{i+1}", value=m_prev.get('indicaciones', ''), key=f"ind_{p_id_m}_{i}")
                    
                    if mnom.strip():
                        meds_input_list.append({
                            "nombre": mnom.strip(),
                            "dosis_manana": d_man,
                            "dosis_tarde": d_tar,
                            "dosis_noche": d_noc,
                            "existencia": exist,
                            "indicaciones": ind_val.strip()
                        })
                    st.divider()
                    
                obs_meds = st.text_area("Observaciones Clínicas / Alergias Medicamentosas", value=obs_exist)
                btn_save_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                
                if btn_save_meds:
                    guardar_medicamentos(p_id_m, meds_input_list, obs_meds, st.session_state["username"])
                    st.toast(f"🎉 ¡Esquema de medicamentos guardado!")
                    st.success(f"✅ ¡Esquema de medicamentos para **{p_nombre_m}** ({p_id_m}) guardado correctamente!")
                    st.balloons()
                    st.rerun()

    # ==========================================
    # --- SECCIÓN 5: ENTREGA DE MEDICAMENTOS ---
    # ==========================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega de Medicamentos")
        st.caption("Registro diario de entrega y descuento automático de inventario")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados.")
        else:
            dict_e = {f"{p[1]} ({p[0]})": (p[0], p[1]) for p in pacientes_activos}
            sel_e = st.selectbox("🔑 Selecciona el Paciente para Entrega", list(dict_e.keys()))
            p_id_e, p_nombre_e = dict_e[sel_e]
            
            meds_disp, _, _, _ = obtener_medicamentos(p_id_e)
            meds_con_stock = [m for m in meds_disp if m.get('existencia', 0) > 0]
            
            if not meds_con_stock:
                st.warning(f"⚠️ **{p_nombre_e}** no tiene medicamentos con existencia en inventario (`Existencia > 0`). Reabastezca en Control de Medicamentos.")
            else:
                st.write(f"Entregando medicamentos a: **{p_nombre_e}** ({p_id_e})")
                
                entrega_cantidades = {}
                
                with st.form("form_entrega_meds"):
                    st.subheader("Medicamentos Disponibles para Entrega")
                    for m in meds_con_stock:
                        m_nom = m['nombre']
                        d_man = m.get('dosis_manana', 0)
                        d_tar = m.get('dosis_tarde', 0)
                        d_noc = m.get('dosis_noche', 0)
                        d_diaria = d_man + d_tar + d_noc
                        stock_act = m.get('existencia', 0)
                        
                        default_entregar = min(d_diaria if d_diaria > 0 else 1, stock_act)
                        
                        ce1, ce2, ce3 = st.columns([3, 2, 2])
                        with ce1:
                            st.write(f"💊 **{m_nom}** | Dosis Diaria: {d_diaria}")
                            st.caption(f"Indicaciones: {m.get('indicaciones', 'N/A')}")
                        with ce2:
                            st.write(f"📦 Existencia Actual: **{stock_act}**")
                        with ce3:
                            cant_ent = st.number_input(f"Cantidad a entregar ({m_nom})", min_value=1, max_value=stock_act, value=default_entregar, key=f"ent_{p_id_e}_{m_nom}")
                            entrega_cantidades[m_nom] = cant_ent
                        st.divider()
                        
                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                    
                    if btn_confirmar_entrega:
                        entrega_items = [{"nombre": k, "cantidad": v} for k, v in entrega_cantidades.items() if v > 0]
                        if not entrega_items:
                            st.error("⚠️ Debe seleccionar al menos una cantidad a entregar.")
                        else:
                            ok, msg = registrar_entrega_meds(p_id_e, entrega_items, st.session_state["username"])
                            if ok:
                                st.session_state["entrega_exitosa_pdf"] = (p_id_e, entrega_items, st.session_state["username"])
                                st.toast(f"🎉 ¡Entrega registrada exitosamente para {p_nombre_e}!")
                                st.rerun()
                            else:
                                st.error(msg)
                                
                if "entrega_exitosa_pdf" in st.session_state:
                    pid_pdf, items_pdf, user_pdf = st.session_state["entrega_exitosa_pdf"]
                    if pid_pdf == p_id_e:
                        st.success(f"✅ ¡Entrega registrada exitosamente para **{p_nombre_e}** ({p_id_e})! Se descontaron los medicamentos del inventario.")
                        pdf_comprobante = generar_pdf_comprobante_entrega(pid_pdf, items_pdf, user_pdf)
                        with open(pdf_comprobante, "rb") as f:
                            st.download_button(
                                label="🖨️ Descargar Comprobante de Entrega (PDF)",
                                data=f,
                                file_name=pdf_comprobante,
                                mime="application/pdf",
                                key=f"btn_dl_entrega_{pid_pdf}"
                            )

    # ==========================================
    # --- SECCIÓN 6: ALERTAS DE EXISTENCIA Y COMPRAS ---
    # ==========================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencia y Lista de Compras")
        st.caption("Monitoreo automatico de niveles de stock e insumos criticos de farmacia")
        
        pdf_compras = generar_pdf_compras()
        with open(pdf_compras, "rb") as f:
            st.download_button(
                label="📄 Imprimir Lista de Compras (PDF)",
                data=f,
                file_name=pdf_compras,
                mime="application/pdf",
                key="btn_pdf_compras"
            )
            
        st.divider()
        
        pacientes_activos = listar_pacientes_bd('A')
        alertas_compras = []
        
        for pac in pacientes_activos:
            pid, pnom, fing, fnac, sexo, pest, tusr, etapa = pac
            meds, obs, _, _ = obtener_medicamentos(pid)
            for m in meds:
                d_man = m.get('dosis_manana', 0)
                d_tar = m.get('dosis_tarde', 0)
                d_noc = m.get('dosis_noche', 0)
                d_diaria = d_man + d_tar + d_noc
                ex = m.get('existencia', 0)
                
                if d_diaria > 0 and ex <= (d_diaria * 3):
                    cant_sug = (d_diaria * 30) - ex
                    alertas_compras.append((pid, pnom, m.get('nombre', ''), ex, d_diaria, max(1, cant_sug)))
                    
        if not alertas_compras:
            st.success("✅ **INVENTARIO OPTIMO**: Todos los pacientes cuentan con stock suficiente para mas de 3 dias.")
        else:
            st.subheader(f"⚠️ Alertas Detectadas ({len(alertas_compras)})")
            for item in alertas_compras:
                pid, pnom, mnom, ex, d_diaria, cant_sug = item
                dias_cobertura = ex / d_diaria if d_diaria > 0 else 0
                if dias_cobertura < 1:
                    st.error(f"🚨 **ALERTA CRÍTICA - {pnom} ({pid})** | Medicamento: **{mnom}** | Existencia: **{ex}** | Dosis diaria: **{d_diaria}** (Se agota en menos de 1 dia)")
                else:
                    st.warning(f"⚠️ **ALERTA PREVENTIVA - {pnom} ({pid})** | Medicamento: **{mnom}** | Existencia: **{ex}** | Dosis diaria: **{d_diaria}** (Alcanza para {dias_cobertura:.1f} dias)")

    # ==========================================
    # --- SECCIÓN 7: NUEVA ENTREVISTA / EDITAR ---
    # ==========================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluacion digital de consumo de sustancias y perfil socio-demografico")
        
        pacientes_activos = listar_pacientes_bd('A')
        if not pacientes_activos:
            st.warning("Debe registrar un usuario activo primero en el modulo 'Registro y Edicion de Usuarios'.")
        else:
            dict_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_ent = st.selectbox("🔑 Selecciona el Paciente a Entrevistar", list(dict_ent.keys()))
            paciente_id_input = dict_ent[sel_ent]
            
            datos_existentes, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if not datos_existentes:
                datos_existentes = {}
                st.info(f"🆕 Iniciando nueva entrevista para **{sel_ent}**.")
            else:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Ultima modificacion: {f_mod}")

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
    # --- SECCIÓN 8: BUSCAR Y LISTAR PACIENTES ---
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro y Consulta de Pacientes")
        st.caption("Directorio general de expedientes clinicos y entrevistas iniciales")
        
        filtro_p = st.radio("Filtrar por Estatus", ["🟢 Activos ('A')", "🔒 Bloqueados ('B')", "📋 Todos"], horizontal=True)
        cod_f = 'A' if "Activos" in filtro_p else ('B' if "Bloqueados" in filtro_p else 'TODOS')
        
        pacientes = listar_pacientes_bd(cod_f)
        
        if not pacientes:
            st.warning("No hay registros que coincidan con la seleccion.")
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
    # --- SECCIÓN 9: RESPALDO Y RESTAURACIÓN ---
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Copia de seguridad completa y recuperacion de expedientes")
        
        tab_res1, tab_res2 = st.tabs(["📥 Descargar Respaldo Seguro (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_res1:
            st.subheader("Copia de Seguridad de la Base de Datos")
            st.info("Descargue el archivo de base de datos `.db` para mantener a salvo todos los expedientes, medicamentos, entregas y sesiones de grupo.")
            
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
                st.warning("No se encontro el archivo de base de datos local.")

        with tab_res2:
            st.subheader("Restaurar Base de Datos desde Respaldo")
            st.warning("⚠️ **ATENCIÓN**: Restaurar una base de datos reemplazará todos los datos actuales del sistema.")
            
            uploaded_db = st.file_uploader("Seleccione el archivo de respaldo `.db`", type=["db", "sqlite3"])
            
            if uploaded_db is not None:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    st.toast("🎉 ¡Base de datos restaurada exitosamente!")
                    st.success("✅ ¡Base de datos restaurada exitosamente desde el archivo subido!")
                    st.balloons()
                    st.rerun()

    # ==========================================
    # --- SECCIÓN 10: CONFIGURACIÓN / SEGURIDAD ---
    # ==========================================
    elif menu == "⚙️ Configuración / Seguridad":
        st.title("⚙️ Configuración del Sistema & Seguridad")
        
        tab_sec1, tab_sec2 = st.tabs(["🔑 Cambiar Contraseña", "⚙️ Administrar Requisitos por Etapa"])
        
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

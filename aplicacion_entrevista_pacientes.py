import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Gestión y Consejería de Pacientes",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    
    # 2. Tabla de Registro Inicial de Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT NOT NULL,
            estatus TEXT DEFAULT 'A',
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
    
    # 4. Tabla de Control de Medicamentos
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
    
    # 5. Tabla de Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            fecha_entrega TEXT NOT NULL,
            usuario_registro TEXT NOT NULL,
            entregas_json TEXT NOT NULL,
            observaciones TEXT
        )
    ''')
    
    # Crear usuario admin por defecto si no existe
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

# --- FUNCIONES DE PACIENTES REGISTRO ---
def generar_siguiente_folio():
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

def buscar_duplicado_nombre(nombre_completo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes_registro')
    rows = c.fetchall()
    conn.close()
    nombre_norm = nombre_completo.strip().lower()
    for r in rows:
        if r[1].strip().lower() == nombre_norm:
            return r  # (paciente_id, nombre_completo, estatus)
    return None

def guardar_paciente_registro(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', usuario='admin'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes_registro SET estatus = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (nuevo_estatus, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def obtener_paciente_registro(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_registrados(solo_activos=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion FROM pacientes_registro WHERE estatus = 'A' ORDER BY nombre_completo ASC")
    else:
        c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion FROM pacientes_registro ORDER BY estatus ASC, nombre_completo ASC")
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

def listar_entrevistas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas ORDER BY fecha_modificacion DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, meds_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
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
    if row and row[0]:
        return json.loads(row[0]), row[1], row[2], row[3], row[4]
    return [], "", None, None, None

def listar_todos_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT m.paciente_id, m.meds_json, m.observaciones, m.fecha_modificacion, p.nombre_completo, p.estatus 
        FROM medicamentos m
        LEFT JOIN pacientes_registro p ON m.paciente_id = p.paciente_id
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE ENTREGA DE MEDICAMENTOS ---
def registrar_entrega_medicamentos(paciente_id, entregas_list, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entregas_json = json.dumps(entregas_list, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, usuario_registro, entregas_json, observaciones)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, usuario, entregas_json, observaciones))
    
    conn.commit()
    conn.close()

def listar_entregas_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT fecha_entrega, usuario_registro, entregas_json, observaciones 
        FROM entregas_medicamentos 
        WHERE paciente_id = ? 
        ORDER BY fecha_entrega DESC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SISTEMA DE ATENCION Y CONTROL CLINICO", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Reporte Oficial Expediente de Paciente", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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

def encabezado_paciente_pdf(pdf, paciente_id):
    p_info = obtener_paciente_registro(paciente_id)
    pdf.set_font("Helvetica", "B", 11)
    if p_info:
        pdf.cell(pdf.epw, 6, f"FOLIO: {limpiar_texto(p_info[0])}  |  PACIENTE: {limpiar_texto(p_info[1])}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Fecha Ingreso: {limpiar_texto(p_info[2])} | Fecha Nac.: {limpiar_texto(p_info[3])} | Sexo: {limpiar_texto(p_info[4])}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(pdf.epw, 6, f"FOLIO PACIENTE: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

def generar_pdf_entrevista(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    encabezado_paciente_pdf(pdf, paciente_id)
    
    # Datos Principales
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
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION CLINICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    # Firma
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos(paciente_id, meds_list, observaciones):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    encabezado_paciente_pdf(pdf, paciente_id)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "ESQUEMA Y CONTROL DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [45, 20, 20, 20, 22, 25, 38]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis D.", "Existencia", "Indicaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for m in meds_list:
        dm = float(m.get('dosis_manana', 0))
        dt = float(m.get('dosis_tarde', 0))
        dn = float(m.get('dosis_noche', 0))
        d_diaria = dm + dt + dn
        ex = float(m.get('existencia', 0))
        
        pdf.cell(col_w[0], 6, limpiar_texto(m.get('nombre', '')), border=1)
        pdf.cell(col_w[1], 6, str(dm), border=1, align="C")
        pdf.cell(col_w[2], 6, str(dt), border=1, align="C")
        pdf.cell(col_w[3], 6, str(dn), border=1, align="C")
        pdf.cell(col_w[4], 6, str(d_diaria), border=1, align="C")
        pdf.cell(col_w[5], 6, str(ex), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(m.get('indicaciones', '')), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "Observaciones de la Medicacion:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones if observaciones else "Sin observaciones registrado."), new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_comprobante_entrega(paciente_id, entregas_list, observaciones):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    encabezado_paciente_pdf(pdf, paciente_id)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "COMPROBANTE DE ENTREGA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de Entrega: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [60, 35, 45, 50]
    headers = ["Medicamento", "Cant. Entregada", "Stock Anterior", "Stock Restante"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    for item in entregas_list:
        pdf.cell(col_w[0], 6, limpiar_texto(item.get('nombre', '')), border=1)
        pdf.cell(col_w[1], 6, str(item.get('cantidad_entregada', 0)), border=1, align="C")
        pdf.cell(col_w[2], 6, str(item.get('existencia_previa', 0)), border=1, align="C")
        pdf.cell(col_w[3], 6, str(item.get('existencia_nueva', 0)), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, "Notas de Entrega:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, "Firma del Recibido / Entregado: ___________________________", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Comprobante_Entrega_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras(lista_compras):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA DE COMPRAS Y REABASTECIMIENTO DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de Generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [25, 45, 40, 25, 25, 30]
    headers = ["Folio", "Paciente", "Medicamento", "Existencia", "Dosis Diaria", "Sugerido Compra"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_compras:
        pdf.cell(col_w[0], 6, limpiar_texto(item['folio']), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(item['paciente']), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(item['medicamento']), border=1)
        pdf.cell(col_w[3], 6, str(item['existencia']), border=1, align="C")
        pdf.cell(col_w[4], 6, str(item['dosis_diaria']), border=1, align="C")
        pdf.cell(col_w[5], 6, str(item['sugerido_compra']), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
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
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema Clinico y Consejería</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales para continuar</p>", unsafe_allow_html=True)
    
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
    # --- BARRA LATERAL ---
    st.sidebar.title("📋 Control Clínico")
    st.sidebar.write(f"👤 **Atiende**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación principal",
        [
            "👤 Registro de Usuarios",
            "📝 Nueva Entrevista / Editar",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "🔍 Buscar y Listar Pacientes",
            "⚙️ Seguridad / Contraseña"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 0: REGISTRO DE USUARIOS (PACIENTES) ---
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro Inicial de Usuarios (Pacientes)")
        st.caption("Modulo inicial obligatorio para dar de alta pacientes en la base de datos")
        
        tab_alta, tab_activos, tab_bloqueados = st.tabs([
            "➕ Alta de Nuevo Usuario",
            "🟢 Usuarios Activos ('A')",
            "🔒 Usuarios Bloqueados ('B')"
        ])
        
        with tab_alta:
            st.subheader("Datos Basales Obligatorios")
            folio_sugerido = generar_siguiente_folio()
            
            with st.form("form_alta_usuario"):
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    pac_id_in = st.text_input("🔑 Folio / ID del Usuario *", value=folio_sugerido).strip()
                    nombre_in = st.text_input("👤 Nombre Completo del Usuario *").strip()
                with col_u2:
                    fecha_ing = st.date_input("📅 Fecha de Ingreso *", datetime.now())
                    fecha_nac = st.date_input("🎂 Fecha de Nacimiento *", datetime(1995, 1, 1))
                    sexo_in = st.selectbox("🚻 Sexo *", ["Masculino", "Femenino", "Otro"])
                    
                btn_alta = st.form_submit_button("💾 Guardar y Dar de Alta Usuario", use_container_width=True)
                
                if btn_alta:
                    if not pac_id_in or not nombre_in:
                        st.error("⚠️ El Folio y el Nombre Completo son campos obligatorios.")
                    else:
                        # Verificar duplicados insensibles a mayúsculas en 'A' y 'B'
                        duplicado = buscar_duplicado_nombre(nombre_in)
                        if duplicado and duplicado[0] != pac_id_in:
                            p_exist_id, p_exist_nom, p_exist_est = duplicado
                            est_txt = "ACTIVO ('A')" if p_exist_est == 'A' else "BLOQUEADO ('B')"
                            st.error(f"❌ **Imposible registrar**: Ya existe un usuario registrado con el nombre **'{p_exist_nom}'** bajo el Folio **{p_exist_id}** (Estatus actual: **{est_txt}**). No se permiten registros duplicados.")
                        else:
                            guardar_paciente_registro(pac_id_in, nombre_in, fecha_ing, fecha_nac, sexo_in, estatus='A', usuario=st.session_state['username'])
                            st.success(f"✅ ¡Usuario **{nombre_in}** con Folio **{pac_id_in}** dado de alta correctamente!")
                            st.rerun()

        with tab_activos:
            st.subheader("🟢 Lista de Usuarios Activos ('A')")
            activos = listar_pacientes_registrados(solo_activos=True)
            if not activos:
                st.info("No hay usuarios activos registrados.")
            else:
                for reg in activos:
                    pid, pnom, fing, fnac, psex, pest, fmod = reg
                    with st.expander(f"👤 **{pnom}** | Folio: `{pid}` | Sexo: {psex} | Ingreso: {fing}"):
                        c_a1, c_a2 = st.columns([3, 1])
                        with c_a1:
                            st.write(f"**Fecha Nacimiento:** {fnac}")
                            st.write(f"**Última Modificación:** {fmod}")
                        with c_a2:
                            if st.button(f"🔒 Bloquear Usuario", key=f"btn_bloq_{pid}"):
                                cambiar_estatus_paciente(pid, 'B')
                                st.warning(f"Usuario {pid} - {pnom} ha sido Bloqueado ('B').")
                                st.rerun()

        with tab_bloqueados:
            st.subheader("🔒 Lista de Usuarios Bloqueados ('B')")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_modificacion FROM pacientes_registro WHERE estatus = 'B' ORDER BY nombre_completo ASC")
            bloqueados = c.fetchall()
            conn.close()
            
            if not bloqueados:
                st.info("No hay usuarios bloqueados actualmente.")
            else:
                for reg in bloqueados:
                    pid, pnom, fing, fnac, psex, pest, fmod = reg
                    with st.expander(f"🔒 **{pnom}** | Folio: `{pid}` [BLOQUEADO]"):
                        c_b1, c_b2 = st.columns([3, 1])
                        with c_b1:
                            st.write(f"**Fecha Ingreso:** {fing} | **Nacimiento:** {fnac}")
                            st.write(f"**Última Modificación:** {fmod}")
                        with c_b2:
                            if st.button(f"🔓 Desbloquear / Reactivar", key=f"btn_unbloq_{pid}"):
                                cambiar_estatus_paciente(pid, 'A')
                                st.success(f"Usuario {pid} - {pnom} ha sido Reactivado ('A').")
                                st.rerun()

    # --- SECCIÓN 1: FORMULARIO DE ENTREVISTA ---
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ No hay usuarios activos en el sistema. Primero dé de alta un usuario en '👤 Registro de Usuarios'.")
        else:
            opciones_pacientes = {f"{r[0]} - {r[1]}": r[0] for r in activos}
            selected_paciente_label = st.selectbox("👤 Seleccionar Paciente Registrado (Activo) *", list(opciones_pacientes.keys()))
            paciente_id_input = opciones_pacientes[selected_paciente_label]
            
            p_info = obtener_paciente_registro(paciente_id_input)
            if p_info:
                st.info(f"📌 **Expediente del Paciente**: Folio: `{p_info[0]}` | Nombre: **{p_info[1]}** | Ingreso: {p_info[2]} | Nacimiento: {p_info[3]} | Sexo: {p_info[4]}")
            
            datos_existentes = {}
            if paciente_id_input:
                datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
                if datos_cargados:
                    st.success(f"📌 Entrevista encontrada. Registrada el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                    datos_existentes = datos_cargados
                else:
                    st.info("🆕 El paciente no tiene entrevista guardada aún. Complete el formulario a continuación.")

            with st.form("formulario_entrevista"):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "1. Datos Generales",
                    "2. Consumo de Sustancias",
                    "3. Disposición al Cambio",
                    "4. Entorno y Riesgos",
                    "5. Observaciones y Firma"
                ])
                
                # TAB 1: DATOS GENERALES
                with tab1:
                    st.subheader("Datos Socio-Demográficos Basales")
                    c1, c2 = st.columns(2)
                    with c1:
                        dependientes_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], 
                                                         index=1 if datos_existentes.get("dependientes_flag") == "SÍ" else 0)
                        dependientes_quienes = st.text_input("¿Quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
                    with c2:
                        pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"],
                                                   index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
                        pareja_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo", ""))

                # TAB 2: CONSUMO DE SUSTANCIAS
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

                # TAB 3: DISPOSICIÓN AL CAMBIO
                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió?", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo y qué hizo?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("Mayor periodo en últimos 6 meses", value=datos_existentes.get("abst_6meses", ""))
                    
                    importancia_options = [
                        "1. NADA IMPORTANTE",
                        "2. POCO IMPORTANTE",
                        "3. ALGO IMPORTANTE",
                        "4. IMPORTANTE",
                        "5. MUY IMPORTANTE"
                    ]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Importancia de dejar de consumir", options=importancia_options, value=importancia_options[imp_index])

                # TAB 4: ENTORNO Y RIESGOS
                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("Integrantes de la familia con mayor contacto", value=datos_existentes.get("familia_integrantes", ""))
                    
                    st.subheader("Factores de Riesgo")
                    c_r1, c_r2 = st.columns(2)
                    with c_r1:
                        relaciones_post_consumo = st.selectbox("¿Relaciones sexuales tras consumir?", ["NO", "SÍ"],
                                                                index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    with c_r2:
                        abuso_flag = st.selectbox("¿Involucrado en abuso físico/sexual por consumo?", ["NO", "SÍ"],
                                                  index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                # TAB 5: OBSERVACIONES Y FIRMA
                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas durante la sesión", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica la entrevista", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Entrevista del Paciente", use_container_width=True)
                
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
                    st.success(f"✅ ¡Entrevista guardada correctamente para el paciente {p_info[1]} ({paciente_id_input})!")

    # --- SECCIÓN 2: CONTROL DE MEDICAMENTOS Y DOSIS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos, Dosis y Existencias")
        st.caption("Captura de esquema de dosificación e inventario inicial por paciente")
        
        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ No hay usuarios activos en el sistema. Primero dé de alta un usuario en '👤 Registro de Usuarios'.")
        else:
            opciones_pacientes = {f"{r[0]} - {r[1]}": r[0] for r in activos}
            selected_paciente_m_label = st.selectbox("👤 Seleccionar Paciente Registrado (Activo) *", list(opciones_pacientes.keys()))
            paciente_med_id = opciones_pacientes[selected_paciente_m_label]
            
            p_info = obtener_paciente_registro(paciente_med_id)
            if p_info:
                st.info(f"📌 **Paciente Seleccionado**: Folio: `{p_info[0]}` | Nombre: **{p_info[1]}** | Ingreso: {p_info[2]}")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            if f_mod_m:
                st.success(f"📌 Registro de medicamentos cargado. Última actualización: {f_mod_m} por {u_reg_m}")
            
            st.subheader("Captura de Medicamentos")
            
            # Gestionar dinamismo de la lista de medicamentos
            if f"num_meds_{paciente_med_id}" not in st.session_state:
                st.session_state[f"num_meds_{paciente_med_id}"] = max(len(meds_cargados), 1)
            
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("➕ Agregar otro medicamento"):
                    st.session_state[f"num_meds_{paciente_med_id}"] += 1
                    st.rerun()
            with col_b2:
                if st.session_state[f"num_meds_{paciente_med_id}"] > 1:
                    if st.button("➖ Quitar último medicamento"):
                        st.session_state[f"num_meds_{paciente_med_id}"] -= 1
                        st.rerun()

            with st.form("form_medicamentos_paciente"):
                meds_input = []
                count_m = st.session_state[f"num_meds_{paciente_med_id}"]
                
                for idx in range(count_m):
                    m_data = meds_cargados[idx] if idx < len(meds_cargados) else {}
                    st.markdown(f"##### 💊 Medicamento #{idx + 1}")
                    
                    c_m1, c_m2, c_m3, c_m4, c_m5, c_m6 = st.columns([2.5, 1, 1, 1, 1.2, 2.3])
                    
                    with c_m1:
                        nom_m = st.text_input("Nombre del Medicamento", value=m_data.get("nombre", ""), key=f"m_nom_{paciente_med_id}_{idx}")
                    with c_m2:
                        dos_manana = st.number_input("☀️ Mañana", min_value=0.0, step=0.5, value=float(m_data.get("dosis_manana", 0.0)), key=f"m_man_{paciente_med_id}_{idx}")
                    with c_m3:
                        dos_tarde = st.number_input("🌤️ Tarde", min_value=0.0, step=0.5, value=float(m_data.get("dosis_tarde", 0.0)), key=f"m_tar_{paciente_med_id}_{idx}")
                    with c_m4:
                        dos_noche = st.number_input("🌙 Noche", min_value=0.0, step=0.5, value=float(m_data.get("dosis_noche", 0.0)), key=f"m_noc_{paciente_med_id}_{idx}")
                    with c_m5:
                        exis_m = st.number_input("📦 Existencia", min_value=0.0, step=1.0, value=float(m_data.get("existencia", 0.0)), key=f"m_exi_{paciente_med_id}_{idx}")
                    with c_m6:
                        indic_m = st.text_input("Indicaciones / Notas", value=m_data.get("indicaciones", ""), key=f"m_ind_{paciente_med_id}_{idx}")
                    
                    if nom_m.strip():
                        meds_input.append({
                            "nombre": nom_m.strip(),
                            "dosis_manana": dos_manana,
                            "dosis_tarde": dos_tarde,
                            "dosis_noche": dos_noche,
                            "existencia": exis_m,
                            "indicaciones": indic_m.strip()
                        })
                    st.divider()
                
                obs_meds_in = st.text_area("Observaciones de Medicación / Alergias", value=obs_cargadas)
                btn_guardar_m = st.form_submit_button("💾 Guardar Esquema de Medicamentos e Inventario", use_container_width=True)
                
                if btn_guardar_m:
                    guardar_medicamentos(paciente_med_id, meds_input, obs_meds_in, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos guardado correctamente para {p_info[1]}!")
                    st.rerun()

            # Vista preliminar y descargar PDF
            if meds_cargados:
                st.subheader("📄 Reporte Imprimible de Medicación")
                pdf_med_file = generar_pdf_medicamentos(paciente_med_id, meds_cargados, obs_cargadas)
                with open(pdf_med_file, "rb") as f_pdf:
                    st.download_button(
                        label="🖨️ Descargar Hoja de Medicación (PDF)",
                        data=f_pdf,
                        file_name=f"Medicacion_{paciente_med_id}.pdf",
                        mime="application/pdf"
                    )

    # --- NUEVO SECCIÓN: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega de Medicamentos")
        st.caption("Registro de entregas físicas a pacientes con descuento automático del inventario")
        
        activos = listar_pacientes_registrados(solo_activos=True)
        if not activos:
            st.warning("⚠️ No hay usuarios activos en el sistema.")
        else:
            opciones_pacientes = {f"{r[0]} - {r[1]}": r[0] for r in activos}
            selected_paciente_e_label = st.selectbox("👤 Seleccionar Paciente Registrado (Activo) *", list(opciones_pacientes.keys()))
            paciente_ent_id = opciones_pacientes[selected_paciente_e_label]
            
            p_info = obtener_paciente_registro(paciente_ent_id)
            if p_info:
                st.info(f"📌 **Paciente**: Folio: `{p_info[0]}` | Nombre: **{p_info[1]}** | Ingreso: {p_info[2]}")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_ent_id)
            
            # Filtrar solo los medicamentos con existencia > 0
            meds_disponibles = [m for m in meds_cargados if float(m.get('existencia', 0)) > 0]
            
            if not meds_cargados:
                st.warning("⚠️ Este paciente no tiene medicamentos registrados en 'Control de Medicamentos y Dosis'.")
            elif not meds_disponibles:
                st.error("❌ El paciente no cuenta con medicamentos disponibles en existencia (Stock 0 en todos sus medicamentos).")
            else:
                st.subheader("💊 Medicamentos Disponibles para Entrega")
                st.caption("Los cuadros de cantidad muestran por defecto la existencia actual disponible.")
                
                with st.form("form_entrega_medicamentos"):
                    items_a_entregar = []
                    
                    for idx, m in enumerate(meds_disponibles):
                        nombre_m = m.get("nombre", "")
                        exis_actual = float(m.get("existencia", 0.0))
                        d_man = float(m.get("dosis_manana", 0))
                        d_tar = float(m.get("dosis_tarde", 0))
                        d_noc = float(m.get("dosis_noche", 0))
                        d_diaria = d_man + d_tar + d_noc
                        
                        st.markdown(f"#### 💊 **{nombre_m}**")
                        c_e1, c_e2, c_e3, c_e4 = st.columns([1.5, 1.5, 1.5, 2.5])
                        
                        with c_e1:
                            st.metric("Existencia Disponible", f"{exis_actual:g}")
                        with c_e2:
                            st.metric("Dosis Diaria", f"{d_diaria:g}")
                        with c_e3:
                            # Por default, el cuadro de texto está lleno con la existencia actual de ese medicamento
                            # La cantidad debe ser al menos 1
                            val_default = max(int(exis_actual) if exis_actual.is_integer() else exis_actual, 1.0)
                            cant_entregar = st.number_input(
                                f"Cantidad a Entregar *",
                                min_value=1.0,
                                max_value=float(exis_actual),
                                value=float(val_default),
                                step=1.0,
                                key=f"ent_cant_{paciente_ent_id}_{idx}"
                            )
                        with c_e4:
                            confirmar_entrega = st.checkbox(
                                "Entregar este medicamento",
                                value=True,
                                key=f"ent_chk_{paciente_ent_id}_{idx}"
                            )
                            
                        if confirmar_entrega and cant_entregar >= 1.0:
                            items_a_entregar.append({
                                "nombre": nombre_m,
                                "cantidad_entregada": cant_entregar,
                                "existencia_previa": exis_actual,
                                "existencia_nueva": exis_actual - cant_entregar,
                                "indicaciones": m.get("indicaciones", "")
                            })
                        st.divider()
                    
                    obs_entrega = st.text_area("Observaciones o Notas de la Entrega", value="")
                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                    
                    if btn_confirmar_entrega:
                        if not items_a_entregar:
                            st.error("⚠️ Debe seleccionar al menos un medicamento con cantidad entregada de al menos 1.")
                        else:
                            # 1. Actualizar existencias en la lista original de medicamentos
                            map_nuevas_existencias = {it["nombre"]: it["existencia_nueva"] for it in items_a_entregar}
                            
                            meds_actualizados = []
                            for m in meds_cargados:
                                m_copy = dict(m)
                                if m_copy.get("nombre") in map_nuevas_existencias:
                                    m_copy["existencia"] = map_nuevas_existencias[m_copy.get("nombre")]
                                meds_actualizados.append(m_copy)
                            
                            # 2. Guardar medicamentos actualizados
                            guardar_medicamentos(paciente_ent_id, meds_actualizados, obs_cargadas, st.session_state["username"])
                            
                            # 3. Registrar transacción de entrega
                            registrar_entrega_medicamentos(paciente_ent_id, items_a_entregar, obs_entrega, st.session_state["username"])
                            
                            st.success(f"✅ ¡Entrega registrada exitosamente para {p_info[1]}! Las existencias han sido actualizadas.")
                            
                            # Generar PDF comprobante
                            pdf_ent_file = generar_pdf_comprobante_entrega(paciente_ent_id, items_a_entregar, obs_entrega)
                            with open(pdf_ent_file, "rb") as f_ent_pdf:
                                st.download_button(
                                    label="🖨️ Descargar Comprobante de Entrega (PDF)",
                                    data=f_ent_pdf,
                                    file_name=f"Comprobante_Entrega_{paciente_ent_id}.pdf",
                                    mime="application/pdf"
                                )
                            st.rerun()

            # Mostrar historial reciente de entregas
            historial_entregas = listar_entregas_paciente(paciente_ent_id)
            if historial_entregas:
                st.subheader("📋 Historial de Entregas Realizadas a este Paciente")
                for h_item in historial_entregas:
                    f_ent, u_ent, json_ent, obs_e = h_item
                    list_items = json.loads(json_ent)
                    with st.expander(f"📦 Entrega del {f_ent} | Registrado por: {u_ent}"):
                        for it in list_items:
                            st.write(f"• **{it['nombre']}**: {it['cantidad_entregada']} unidades entregadas (Stock restante: {it['existencia_nueva']})")
                        if obs_e:
                            st.caption(f"Notas: {obs_e}")

    # --- SECCIÓN 3: ALERTAS DE EXISTENCIA Y COMPRAS ---
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencia y Lista de Compras")
        st.caption("Consolidado general de reabastecimiento para medicamentos de pacientes activos ('A')")
        
        todos_meds = listar_todos_medicamentos()
        
        lista_compras = []
        criticos_count = 0
        preventivos_count = 0
        
        for reg in todos_meds:
            pid, m_json, obs, fmod, pnom, pest = reg
            if pest == 'A' and m_json:
                med_list = json.loads(m_json)
                for m in med_list:
                    dm = float(m.get('dosis_manana', 0))
                    dt = float(m.get('dosis_tarde', 0))
                    dn = float(m.get('dosis_noche', 0))
                    d_diaria = dm + dt + dn
                    exis = float(m.get('existencia', 0))
                    
                    if d_diaria > 0:
                        dias_cobertura = exis / d_diaria
                        if dias_cobertura < 1.0:
                            criticos_count += 1
                            sugerido = max(d_diaria * 7 - exis, d_diaria)
                            lista_compras.append({
                                "folio": pid,
                                "paciente": pnom,
                                "medicamento": m.get('nombre', ''),
                                "existencia": exis,
                                "dosis_diaria": d_diaria,
                                "dias_cobertura": dias_cobertura,
                                "nivel": "CRÍTICO (Menos de 1 día)",
                                "sugerido_compra": sugerido
                            })
                        elif dias_cobertura <= 3.0:
                            preventivos_count += 1
                            sugerido = max(d_diaria * 7 - exis, d_diaria)
                            lista_compras.append({
                                "folio": pid,
                                "paciente": pnom,
                                "medicamento": m.get('nombre', ''),
                                "existencia": exis,
                                "dosis_diaria": d_diaria,
                                "dias_cobertura": dias_cobertura,
                                "nivel": "PREVENTIVO (1 a 3 días)",
                                "sugerido_compra": sugerido
                            })

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("🔴 Alertas Críticas (Menos de 24h)", criticos_count)
        with col_m2:
            st.metric("🟡 Alertas Preventivas (1 a 3 días)", preventivos_count)
            
        st.divider()
        
        if not lista_compras:
            st.success("🎉 ¡Excelente! Todos los medicamentos de pacientes activos tienen existencias suficientes para más de 3 días.")
        else:
            st.subheader("📋 Lista de Personas y Medicamentos a Reabastecer")
            
            for item in lista_compras:
                color_box = "🔴" if "CRÍTICO" in item['nivel'] else "🟡"
                st.warning(f"{color_box} **{item['paciente']}** (`{item['folio']}`) — **{item['medicamento']}** | Existencia: `{item['existencia']}` | Dosis Diaria: `{item['dosis_diaria']}` | Cobertura: `{item['dias_cobertura']:.1f} días` | Sugerido Comprar: `{item['sugerido_compra']}`")
                
            pdf_compras = generar_pdf_compras(lista_compras)
            with open(pdf_compras, "rb") as f_comp:
                st.download_button(
                    label="🖨️ Descargar Lista de Compras (PDF)",
                    data=f_comp,
                    file_name=f"Lista_Compras_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )

    # --- SECCIÓN 4: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Consultas de Pacientes")
        
        filtro_estatus = st.radio("Mostrar usuarios por estatus:", ["Solo Activos ('A')", "Todos (Incluye Bloqueados 'B')"], horizontal=True)
        solo_act = (filtro_estatus == "Solo Activos ('A')")
        
        pacientes = listar_pacientes_registrados(solo_activos=solo_act)
        
        if not pacientes:
            st.warning("No hay pacientes registrados con el filtro seleccionado.")
        else:
            st.subheader(f"Total de registros encontrados: {len(pacientes)}")
            
            for pac in pacientes:
                p_id, p_nom, f_ing, f_nac, p_sex, p_est, f_mod = pac
                tag_est = "🟢 ACTIVO" if p_est == 'A' else "🔒 BLOQUEADO"
                
                with st.expander(f"👤 **{p_nom}** | Folio: `{p_id}` | [{tag_est}]"):
                    c_det1, c_det2 = st.columns([2, 1])
                    with c_det1:
                        st.write(f"**Fecha Ingreso:** {f_ing} | **Fecha Nacimiento:** {f_nac} | **Sexo:** {p_sex}")
                        st.write(f"**Última Modificación:** {f_mod}")
                    with c_det2:
                        # Descargar Entrevista PDF
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_ent = generar_pdf_entrevista(p_id, datos_p)
                            with open(pdf_ent, "rb") as f_e:
                                st.download_button(
                                    label="📄 Entrevista (PDF)",
                                    data=f_e,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_e_{p_id}"
                                )
                        
                        # Descargar Medicación PDF
                        meds_p, obs_p, _, _, _ = obtener_medicamentos(p_id)
                        if meds_p:
                            pdf_m = generar_pdf_medicamentos(p_id, meds_p, obs_p)
                            with open(pdf_m, "rb") as f_m:
                                st.download_button(
                                    label="💊 Medicación (PDF)",
                                    data=f_m,
                                    file_name=f"Medicacion_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_m_{p_id}"
                                )

    # --- SECCIÓN 5: SEGURIDAD ---
    elif menu == "⚙️ Seguridad / Contraseña":
        st.title("⚙️ Configuración de Seguridad")
        st.subheader("Cambiar Contraseña de Usuario del Sistema")
        
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
                        st.success("✅ Contraseña actualizada exitosamente.")
                    else:
                        st.error("La contraseña actual es incorrecta.")

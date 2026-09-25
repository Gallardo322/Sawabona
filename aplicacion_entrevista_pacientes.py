import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista y Control Medico",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios del Sistema (login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    # Tabla de Registro de Usuarios / Pacientes
    # Estatus: 'A' = Activo, 'B' = Bloqueado
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
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
    # Tabla de Entrevistas
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes (paciente_id)
        )
    ''')
    # Tabla de Medicamentos y Dosis por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            paciente_id TEXT PRIMARY KEY,
            meds_json TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes (paciente_id)
        )
    ''')
    # Tabla de Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_meds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregas_json TEXT,
            usuario_registro TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes (paciente_id)
        )
    ''')
    
    # Crear usuario administrador por defecto si no existe
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

# --- FUNCIONES PACIENTES ---
def guardar_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, usuario, estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes SET estatus = ?, fecha_modificacion = ? WHERE paciente_id = ?',
              (nuevo_estatus, fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def buscar_paciente_por_nombre(nombre):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre.strip().lower()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes')
    rows = c.fetchall()
    conn.close()
    for p_id, p_nombre, p_estatus in rows:
        if p_nombre.strip().lower() == nombre_clean:
            return p_id, p_nombre, p_estatus
    return None

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, fecha_modificacion, usuario_registro FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_por_estatus(estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if estatus == 'TODOS':
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes ORDER BY nombre_completo ASC')
    else:
        c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes WHERE estatus = ? ORDER BY nombre_completo ASC', (estatus,))
    rows = c.fetchall()
    conn.close()
    return rows

def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for row in rows:
        pid = row[0]
        if pid.startswith("PAC-"):
            try:
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

# --- FUNCIONES ENTREVISTAS ---
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
    c.execute('''
        SELECT e.paciente_id, p.nombre_completo, e.fecha_registro, e.fecha_modificacion, e.usuario_registro, p.estatus
        FROM entrevistas e
        JOIN pacientes p ON e.paciente_id = p.paciente_id
        ORDER BY e.fecha_modificacion DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES MEDICAMENTOS ---
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
            SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ?
            WHERE paciente_id = ?
        ''', (meds_json, observaciones, fecha_actual, usuario, paciente_id))
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

def registrar_entrega_medicamentos(paciente_id, entregas_list, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Obtener medicamentos actuales
    meds_list, obs, f_reg, f_mod, u_reg = obtener_medicamentos(paciente_id)
    
    # Map de entregas por nombre
    entregas_map = {item['nombre']: item['cantidad_entregada'] for item in entregas_list}
    
    # 2. Descontar existencias
    for med in meds_list:
        m_nombre = med.get('nombre')
        if m_nombre in entregas_map:
            cant_desc = int(entregas_map[m_nombre])
            stock_actual = int(med.get('existencia', 0))
            nuevo_stock = max(0, stock_actual - cant_desc)
            med['existencia'] = nuevo_stock
            
    # Guardar medicamentos actualizados
    guardar_medicamentos(paciente_id, meds_list, obs, usuario)
    
    # 3. Registrar en historial de entregas
    entregas_json = json.dumps(entregas_list, ensure_ascii=False)
    c.execute('''
        INSERT INTO entregas_meds (paciente_id, fecha_entrega, entregas_json, usuario_registro)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, entregas_json, usuario))
    
    conn.commit()
    conn.close()

def listar_todos_medicamentos_activos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT m.paciente_id, p.nombre_completo, m.meds_json, m.observaciones, m.fecha_modificacion
        FROM medicamentos m
        JOIN pacientes p ON m.paciente_id = p.paciente_id
        WHERE p.estatus = 'A'
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def __init__(self, titulo_reporte="REPORTE CLINICO"):
        super().__init__()
        self.titulo_reporte = titulo_reporte

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, self.titulo_reporte, border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.cell(self.epw, 5, "Sistema de Atencion y Control Clinico de Pacientes", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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

def agregar_encabezado_paciente_pdf(pdf, paciente_data):
    if paciente_data:
        p_id, p_nombre, p_ingreso, p_nac, p_sexo = paciente_data[0], paciente_data[1], paciente_data[2], paciente_data[3], paciente_data[4]
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, f"DATOS DEL PACIENTE", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(pdf.epw, 5, f"Folio: {limpiar_texto(p_id)} | Nombre: {limpiar_texto(p_nombre)}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(pdf.epw, 5, f"Fecha Ingreso: {limpiar_texto(p_ingreso)} | Fecha Nacimiento: {limpiar_texto(p_nac)} | Sexo: {limpiar_texto(p_sexo)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

def generar_pdf_entrevista(paciente_id, datos):
    p_data = obtener_paciente(paciente_id)
    pdf = PDFReport("ENTREVISTA INICIAL DE CONSEJERIA")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente_pdf(pdf, p_data)
    
    # Datos Principales
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DATOS SOCIO-DEMOGRAFICOS BASALES", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # Tabla de Consumo
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
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
        
    pdf.ln(3)
    
    # Sustancia de Impacto
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Normalmente consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # Disposición al Cambio
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Importancia actual de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION CLINICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Evaluador: {limpiar_texto(datos.get('evaluador_nombre', ''))} ({limpiar_texto(datos.get('evaluador_cargo', ''))})", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos(paciente_id, meds_list, observaciones):
    p_data = obtener_paciente(paciente_id)
    pdf = PDFReport("HOJA DE CONTROL DE MEDICAMENTOS Y DOSIS")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente_pdf(pdf, p_data)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "ESQUEMA DE DOSIFICACION DIARIA Y EXISTENCIAS", new_x="LMARGIN", new_y="NEXT")
    
    col_w = [45, 20, 20, 20, 25, 60]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Existencia", "Indicaciones"]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for m in meds_list:
        pdf.cell(col_w[0], 6, limpiar_texto(m.get('nombre', '')), border=1)
        pdf.cell(col_w[1], 6, str(m.get('dosis_manana', 0)), border=1, align="C")
        pdf.cell(col_w[2], 6, str(m.get('dosis_tarde', 0)), border=1, align="C")
        pdf.cell(col_w[3], 6, str(m.get('dosis_noche', 0)), border=1, align="C")
        pdf.cell(col_w[4], 6, str(m.get('existencia', 0)), border=1, align="C")
        pdf.cell(col_w[5], 6, limpiar_texto(m.get('indicaciones', '')), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.epw, 5, "Observaciones y Contraindicaciones:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_entrega(paciente_id, entregas_list, usuario):
    p_data = obtener_paciente(paciente_id)
    pdf = PDFReport("COMPROBANTE DE ENTREGA DE MEDICAMENTOS")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente_pdf(pdf, p_data)
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de Entrega: {fecha_actual} | Entregado por: {limpiar_texto(usuario)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DETALLE DE MEDICAMENTOS ENTREGADOS", new_x="LMARGIN", new_y="NEXT")
    
    col_w = [70, 45, 45, 30]
    headers = ["Medicamento", "Cantidad Entregada", "Stock Restante", "Estatus"]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in entregas_list:
        pdf.cell(col_w[0], 6, limpiar_texto(item.get('nombre', '')), border=1)
        pdf.cell(col_w[1], 6, str(item.get('cantidad_entregada', 0)), border=1, align="C")
        pdf.cell(col_w[2], 6, str(item.get('stock_restante', 0)), border=1, align="C")
        pdf.cell(col_w[3], 6, "ENTREGADO", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, "________________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, "Firma de Recibido / Conformidad Paciente", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrega_Meds_{paciente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras(lista_compras):
    pdf = PDFReport("LISTA DE COMPRAS Y REABASTECIMIENTO DE MEDICAMENTOS")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de Generacion: {fecha_actual}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    col_w = [25, 45, 45, 25, 25, 25]
    headers = ["Folio", "Paciente", "Medicamento", "Stock", "Dosis Diaria", "Sugerido"]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_compras:
        pdf.cell(col_w[0], 6, limpiar_texto(item['paciente_id']), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(item['paciente_nombre']), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(item['med_nombre']), border=1)
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
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema Clinico</h2>", unsafe_allow_html=True)
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
    st.sidebar.title("📋 Control Clinico")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
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

    # --- SECCIÓN 0: REGISTRO DE USUARIOS / PACIENTES ---
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro General de Usuarios / Pacientes")
        st.caption("Modulo inicial para la alta y gestion de expedientes de usuarios")
        
        tab_alta, tab_activos, tab_bloqueados = st.tabs([
            "➕ Alta de Nuevo Usuario",
            "🟢 Usuarios Activos ('A')",
            "🔒 Usuarios Bloqueados ('B')"
        ])
        
        with tab_alta:
            st.subheader("Datos de Registro de Usuario")
            folio_sugerido = generar_siguiente_folio()
            
            with st.form("form_alta_paciente"):
                c_a1, c_a2 = st.columns(2)
                with c_a1:
                    reg_id = st.text_input("🔑 Folio / ID de Usuario *", value=folio_sugerido).strip()
                    reg_nombre = st.text_input("👤 Nombre Completo *", placeholder="Ej. Augusto Lara").strip()
                with c_a2:
                    reg_f_ingreso = st.date_input("📅 Fecha de Ingreso", value=date.today())
                    reg_f_nacimiento = st.date_input(
                        "🎂 Fecha de Nacimiento",
                        value=date(1990, 1, 1),
                        min_value=date(1920, 1, 1),
                        max_value=date.today()
                    )
                    reg_sexo = st.selectbox("🚻 Sexo", ["Masculino", "Femenino", "Otro"])
                
                btn_reg_paciente = st.form_submit_button("💾 Dar de Alta Usuario", use_container_width=True)
                
                if btn_reg_paciente:
                    if not reg_id or not reg_nombre:
                        st.error("⚠️ El Folio/ID y el Nombre Completo son campos obligatorios.")
                    else:
                        # Validar si existe duplicado por nombre (insensible a mayusculas)
                        existente_nombre = buscar_paciente_por_nombre(reg_nombre)
                        if existente_nombre and existente_nombre[0] != reg_id:
                            p_id_ex, p_nom_ex, p_est_ex = existente_nombre
                            est_txt = "ACTIVO ('A')" if p_est_ex == 'A' else "BLOQUEADO ('B')"
                            st.error(f"❌ Imposible registrar: Ya existe un usuario registrado con el nombre '{p_nom_ex}' bajo el Folio **{p_id_ex}** (Estatus actual: {est_txt}). No se permiten registros duplicados.")
                        else:
                            guardar_paciente(
                                reg_id,
                                reg_nombre,
                                reg_f_ingreso.strftime("%Y-%m-%d"),
                                reg_f_nacimiento.strftime("%Y-%m-%d"),
                                reg_sexo,
                                st.session_state["username"],
                                estatus='A'
                            )
                            st.success(f"✅ Usuario **{reg_nombre}** (Folio: {reg_id}) registrado exitosamente con estatus ACTIVO ('A').")

        with tab_activos:
            st.subheader("🟢 Directorio de Usuarios Activos")
            pacientes_activos = listar_pacientes_por_estatus('A')
            if not pacientes_activos:
                st.info("No hay usuarios activos registrados.")
            else:
                for p in pacientes_activos:
                    p_id, p_nom, p_ing, p_nac, p_sex, p_est = p
                    with st.expander(f"👤 **{p_nom}** | Folio: **{p_id}** | Sexo: {p_sex}"):
                        st.write(f"**Fecha de Ingreso:** {p_ing} | **Fecha de Nacimiento:** {p_nac}")
                        if st.button(f"🔒 Bloquear Usuario ({p_id})", key=f"block_{p_id}"):
                            cambiar_estatus_paciente(p_id, 'B')
                            st.warning(f"Usuario {p_id} ({p_nom}) ha sido cambiado a estatus BLOQUEADO ('B').")
                            st.rerun()

        with tab_bloqueados:
            st.subheader("🔒 Usuarios Bloqueados / Inactivos")
            pacientes_bloqueados = listar_pacientes_por_estatus('B')
            if not pacientes_bloqueados:
                st.info("No hay usuarios bloqueados en el sistema.")
            else:
                for p in pacientes_bloqueados:
                    p_id, p_nom, p_ing, p_nac, p_sex, p_est = p
                    with st.expander(f"🔒 **{p_nom}** | Folio: **{p_id}** | Sexo: {p_sex}"):
                        st.write(f"**Fecha de Ingreso:** {p_ing} | **Fecha de Nacimiento:** {p_nac}")
                        if st.button(f"🟢 Reactivar / Desbloquear Usuario ({p_id})", key=f"unblock_{p_id}"):
                            cambiar_estatus_paciente(p_id, 'A')
                            st.success(f"Usuario {p_id} ({p_nom}) ha sido reactivado a estatus ACTIVO ('A').")
                            st.rerun()

    # --- SECCIÓN 1: FORMULARIO DE ENTREVISTA ---
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluacion digital de consumo de sustancias")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema. Vaya al modulo '👤 Registro de Usuarios' para dar de alta uno primero.")
        else:
            opciones_pacientes = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            paciente_sel_label = st.selectbox("🔑 Seleccionar Usuario / Paciente Activo *", list(opciones_pacientes.keys()))
            paciente_id_input = opciones_pacientes[paciente_sel_label]
            
            p_info = obtener_paciente(paciente_id_input)
            if p_info:
                st.info(f"📌 **Paciente**: {p_info[1]} | **Folio**: {p_info[0]} | **Ingreso**: {p_info[2]} | **F. Nac**: {p_info[3]} | **Sexo**: {p_info[4]}")

            datos_existentes = {}
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if datos_cargados:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Ultima modificacion: {f_mod}")
                datos_existentes = datos_cargados
            else:
                st.info("🆕 Folio nuevo. Complete los datos para registrar la entrevista inicial.")

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
                        dependientes_quienes = st.text_input("¿Quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
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
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente en la base de datos!")

    # --- SECCIÓN 2: CONTROL DE MEDICAMENTOS Y DOSIS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control e Inventario de Medicamentos por Paciente")
        st.caption("Gestion de dosificacion diaria y existencias en farmacia por usuario")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema.")
        else:
            opciones_pacientes = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            paciente_med_label = st.selectbox("🔑 Seleccionar Usuario / Paciente Activo *", list(opciones_pacientes.keys()))
            paciente_med_id = opciones_pacientes[paciente_med_label]
            
            p_info = obtener_paciente(paciente_med_id)
            if p_info:
                st.info(f"📌 **Paciente**: {p_info[1]} | **Folio**: {p_info[0]} | **Ingreso**: {p_info[2]} | **F. Nac**: {p_info[3]} | **Sexo**: {p_info[4]}")

            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            if meds_cargados:
                st.success(f"📌 Esquema de medicamentos cargado. Ultima modificacion: {f_mod_m} por {u_reg_m}")

            # Manejo dinamico de filas de medicamentos
            num_meds = st.number_input("Número de medicamentos a asignar", min_value=1, max_value=15, value=max(1, len(meds_cargados)))
            
            with st.form("form_medicamentos"):
                meds_input = []
                for i in range(int(num_meds)):
                    m_data = meds_cargados[i] if i < len(meds_cargados) else {}
                    st.markdown(f"##### 💊 Medicamento #{i+1}")
                    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([2.5, 1, 1, 1, 1.2, 2.5])
                    
                    with col_m1:
                        nombre_m = st.text_input(f"Nombre del Medicamento", value=m_data.get("nombre", ""), key=f"med_nom_{i}")
                    with col_m2:
                        dosis_m = st.number_input(f"☀️ Mañana", min_value=0, value=int(m_data.get("dosis_manana", 0)), key=f"med_man_{i}")
                    with col_m3:
                        dosis_t = st.number_input(f"🌤️ Tarde", min_value=0, value=int(m_data.get("dosis_tarde", 0)), key=f"med_tar_{i}")
                    with col_m4:
                        dosis_n = st.number_input(f"🌙 Noche", min_value=0, value=int(m_data.get("dosis_noche", 0)), key=f"med_noc_{i}")
                    with col_m5:
                        exist_m = st.number_input(f"📦 Existencia", min_value=0, value=int(m_data.get("existencia", 0)), key=f"med_exi_{i}")
                    with col_m6:
                        indic_m = st.text_input(f"📝 Indicaciones", value=m_data.get("indicaciones", ""), key=f"med_ind_{i}")
                    
                    if nombre_m.strip():
                        meds_input.append({
                            "nombre": nombre_m.strip(),
                            "dosis_manana": dosis_m,
                            "dosis_tarde": dosis_t,
                            "dosis_noche": dosis_n,
                            "existencia": exist_m,
                            "indicaciones": indic_m
                        })
                    st.divider()

                obs_meds = st.text_area("Observaciones Generales / Alergias / Contraindicaciones", value=obs_cargadas)
                btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema e Inventario de Medicamentos", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_med_id, meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos e inventario para **{paciente_med_id}** guardado exitosamente!")

            if meds_cargados:
                pdf_meds = generar_pdf_medicamentos(paciente_med_id, meds_cargados, obs_cargadas)
                with open(pdf_meds, "rb") as f:
                    st.download_button(
                        label="🖨️ Descargar Hoja de Medicación (PDF)",
                        data=f,
                        file_name=f"Medicacion_{paciente_med_id}.pdf",
                        mime="application/pdf"
                    )

    # --- SECCIÓN 3: ENTREGA DE MEDICAMENTOS ---
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega Diaria de Medicamentos")
        st.caption("Modulo para registrar la entrega de dosis a usuarios y descontar existencias de inventario")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema.")
        else:
            opciones_pacientes = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            paciente_ent_label = st.selectbox("🔑 Seleccionar Usuario / Paciente Activo *", list(opciones_pacientes.keys()))
            paciente_ent_id = opciones_pacientes[paciente_ent_label]
            
            p_info = obtener_paciente(paciente_ent_id)
            if p_info:
                st.info(f"📌 **Paciente**: {p_info[1]} | **Folio**: {p_info[0]} | **Ingreso**: {p_info[2]} | **F. Nac**: {p_info[3]} | **Sexo**: {p_info[4]}")

            meds_cargados, obs_cargadas, _, _, _ = obtener_medicamentos(paciente_ent_id)
            
            # Filtrar unicamente los medicamentos que tengan existencia > 0
            meds_con_existencia = [m for m in meds_cargados if int(m.get('existencia', 0)) > 0]
            
            if not meds_con_existencia:
                st.warning(f"⚠️ El usuario **{paciente_ent_id}** no tiene medicamentos disponibles en inventario (Stock = 0). Debe reabastecer existencias primero en *Control de Medicamentos y Dosis*.")
            else:
                st.subheader("📦 Medicamentos Disponibles para Entrega")
                
                # Usaremos session_state para saber si se procesó una entrega en esta iteracion
                key_entrega_pdf = f"pdf_entrega_{paciente_ent_id}"
                
                with st.form("form_entrega_meds"):
                    entregas_solicitadas = []
                    
                    for idx, m in enumerate(meds_con_existencia):
                        m_nom = m.get('nombre')
                        d_man = int(m.get('dosis_manana', 0))
                        d_tar = int(m.get('dosis_tarde', 0))
                        d_noc = int(m.get('dosis_noche', 0))
                        dosis_diaria = d_man + d_tar + d_noc
                        stock_actual = int(m.get('existencia', 0))
                        
                        # MODIFICACIÓN SOLICITADA:
                        # Por default el cuadro de texto toma la cantidad de la dosis a entregar (dosis_diaria), no la existencia
                        dosis_defecto = dosis_diaria if dosis_diaria > 0 else 1
                        val_default = min(dosis_defecto, stock_actual)
                        
                        st.markdown(f"#### 💊 **{m_nom}**")
                        c_e1, c_e2, c_e3 = st.columns([2, 2, 2])
                        with c_e1:
                            st.write(f"**Dosis Diaria:** ☀️ {d_man} | 🌤️ {d_tar} | 🌙 {d_noc} (Total: **{dosis_diaria}**)")
                            st.write(f"**Stock en Inventario:** 📦 **{stock_actual}** unidades")
                        with c_e2:
                            cant_entregar = st.number_input(
                                f"Cantidad a entregar de {m_nom}",
                                min_value=1,
                                max_value=stock_actual,
                                value=int(val_default),
                                key=f"ent_cant_{paciente_ent_id}_{idx}"
                            )
                        with c_e3:
                            st.write(f"**Nuevo Stock tras entrega:** {stock_actual - cant_entregar}")
                        st.divider()
                        
                        entregas_solicitadas.append({
                            "nombre": m_nom,
                            "cantidad_entregada": cant_entregar,
                            "stock_restante": stock_actual - cant_entregar
                        })

                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                
                # Procesar la entrega FUERA del form context para evitar el StreamlitInvalidLayoutContextError
                if btn_confirmar_entrega:
                    registrar_entrega_medicamentos(paciente_ent_id, entregas_solicitadas, st.session_state["username"])
                    st.success(f"✅ ¡Entrega de medicamentos registrada con éxito para el usuario **{paciente_ent_id}**!")
                    
                    pdf_ent = generar_pdf_entrega(paciente_ent_id, entregas_solicitadas, st.session_state["username"])
                    st.session_state[key_entrega_pdf] = pdf_ent
                    st.rerun()

                # Mostrar boton de descarga si existe un PDF generado en la sesion
                if key_entrega_pdf in st.session_state:
                    pdf_file_path = st.session_state[key_entrega_pdf]
                    if os.path.exists(pdf_file_path):
                        with open(pdf_file_path, "rb") as f:
                            st.download_button(
                                label="🖨️ Descargar Comprobante de Entrega (PDF)",
                                data=f,
                                file_name=os.path.basename(pdf_file_path),
                                mime="application/pdf",
                                key="btn_download_entrega"
                            )

    # --- SECCIÓN 4: ALERTAS Y REABASTECIMIENTO DE MEDICAMENTOS ---
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencias y Lista de Compras")
        st.caption("Deteccion automatica de medicamentos proximos a agotarse para usuarios activos")
        
        todos_meds = listar_todos_medicamentos_activos()
        
        alertas_criticas = []
        alertas_preventivas = []
        lista_compras = []
        
        for row in todos_meds:
            p_id, p_nombre, meds_json_str, obs, f_mod = row
            meds_l = json.loads(meds_json_str) if meds_json_str else []
            
            for m in meds_l:
                m_nom = m.get('nombre')
                d_man = int(m.get('dosis_manana', 0))
                d_tar = int(m.get('dosis_tarde', 0))
                d_noc = int(m.get('dosis_noche', 0))
                dosis_diaria = d_man + d_tar + d_noc
                exist = int(m.get('existencia', 0))
                
                if dosis_diaria > 0:
                    dias_restantes = exist / dosis_diaria
                    
                    if dias_restantes < 1:  # Menos de 1 dia (critico)
                        item_a = {
                            "paciente_id": p_id,
                            "paciente_nombre": p_nombre,
                            "med_nombre": m_nom,
                            "existencia": exist,
                            "dosis_diaria": dosis_diaria,
                            "dias_cubiertos": round(dias_restantes, 1),
                            "sugerido_compra": max(30, dosis_diaria * 15)  # Sugerir para 15 dias o 30 pastillas
                        }
                        alertas_criticas.append(item_a)
                        lista_compras.append(item_a)
                    elif dias_restantes <= 3:  # Menos de 3 dias (preventivo)
                        item_p = {
                            "paciente_id": p_id,
                            "paciente_nombre": p_nombre,
                            "med_nombre": m_nom,
                            "existencia": exist,
                            "dosis_diaria": dosis_diaria,
                            "dias_cubiertos": round(dias_restantes, 1),
                            "sugerido_compra": max(30, dosis_diaria * 15)
                        }
                        alertas_preventivas.append(item_p)
                        lista_compras.append(item_p)

        c_met1, c_met2, c_met3 = st.columns(3)
        with c_met1:
            st.metric("🔴 Alertas Críticas (< 1 Día)", len(alertas_criticas))
        with c_met2:
            st.metric("🟡 Alertas Preventivas (1-3 Días)", len(alertas_preventivas))
        with c_met3:
            st.metric("🛒 Total Medicamentos a Comprar", len(lista_compras))

        st.divider()

        if not lista_compras:
            st.success("🎉 ¡Excelente! Todos los usuarios activos cuentan con existencias suficientes de medicamentos para los próximos días.")
        else:
            st.subheader("🛒 Lista Consolidada de Compras por Paciente")
            
            if alertas_criticas:
                st.error("🔴 **ALERTAS CRÍTICAS - MEDICAMENTOS AGOTADOS O PRÓXIMOS A AGOTARSE HOY**")
                for ac in alertas_criticas:
                    st.write(f"• **{ac['paciente_nombre']}** (Folio: `{ac['paciente_id']}`): Medicamento **{ac['med_nombre']}** ➔ Existencia actual: **{ac['existencia']}** | Dosis Diaria: **{ac['dosis_diaria']}** (Cubre: {ac['dias_cubiertos']} días) ➔ **Sugerido comprar: {ac['sugerido_compra']} unidades**")
                st.divider()
                
            if alertas_preventivas:
                st.warning("🟡 **ALERTAS PREVENTIVAS - REABASTECER PRÓXIMOS 3 DÍAS**")
                for ap in alertas_preventivas:
                    st.write(f"• **{ap['paciente_nombre']}** (Folio: `{ap['paciente_id']}`): Medicamento **{ap['med_nombre']}** ➔ Existencia actual: **{ap['existencia']}** | Dosis Diaria: **{ap['dosis_diaria']}** (Cubre: {ap['dias_cubiertos']} días) ➔ **Sugerido comprar: {ap['sugerido_compra']} unidades**")
                st.divider()

            pdf_comp = generar_pdf_compras(lista_compras)
            with open(pdf_comp, "rb") as f:
                st.download_button(
                    label="🖨️ Descargar Lista de Compras en PDF",
                    data=f,
                    file_name=f"Lista_Compras_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )

    # --- SECCIÓN 5: BUSCAR Y LISTAR PACIENTES Y EXPEDIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio e Historial de Expedientes")
        
        filtro_estatus = st.selectbox("Filtrar por estatus de usuario:", ["ACTIVOS ('A')", "BLOQUEADOS ('B')", "TODOS"])
        est_query = 'A' if "ACTIVOS" in filtro_estatus else ('B' if "BLOQUEADOS" in filtro_estatus else 'TODOS')
        
        pacientes_lista = listar_pacientes_por_estatus(est_query)
        
        if not pacientes_lista:
            st.info("No se encontraron registros de pacientes con ese filtro.")
        else:
            st.subheader(f"Total de registros encontrados: {len(pacientes_lista)}")
            
            for p in pacientes_lista:
                p_id, p_nom, p_ing, p_nac, p_sex, p_est = p
                est_label = "🟢 ACTIVO" if p_est == 'A' else "🔒 BLOQUEADO"
                
                with st.expander(f"👤 **{p_nom}** | Folio: **{p_id}** | Estatus: {est_label}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.write(f"**Fecha de Ingreso:** {p_ing} | **Fecha de Nacimiento:** {p_nac} | **Sexo:** {p_sex}")
                        
                        meds_p, obs_p, _, _, _ = obtener_medicamentos(p_id)
                        if meds_p:
                            st.write(f"**Medicamentos Asignados:** {len(meds_p)} registrada(s)")
                    with c_det2:
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_file = generar_pdf_entrevista(p_id, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{p_id}"
                                )
                        
                        if meds_p:
                            pdf_meds_file = generar_pdf_medicamentos(p_id, meds_p, obs_p)
                            with open(pdf_meds_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar Medicación (PDF)",
                                    data=f,
                                    file_name=f"Medicacion_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_med_{p_id}"
                                )

    # --- SECCIÓN 6: SEGURIDAD ---
    elif menu == "⚙️ Seguridad / Contraseña":
        st.title("⚙️ Configuración de Seguridad")
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
                        c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                  (hash_pass(nueva_pass), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.success("✅ Contraseña actualizada exitosamente.")
                    else:
                        st.error("La contraseña actual es incorrecta.")

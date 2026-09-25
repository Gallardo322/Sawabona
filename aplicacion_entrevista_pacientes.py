import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista y Control de Pacientes",
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
    # Tabla de Pacientes (Directorio Principal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
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
            datos_json TEXT
        )
    ''')
    # Tabla de Medicamentos
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
    # Tabla de Entrega de Medicamentos (Historial)
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_meds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            detalles_json TEXT,
            fecha_entrega TEXT,
            usuario_entrega TEXT
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

# --- FUNCIONES DE PACIENTES ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes')
    rows = c.fetchall()
    conn.close()
    
    max_num = 0
    for r in rows:
        pid = r[0]
        if pid and pid.startswith("PAC-"):
            try:
                num = int(pid.split("-")[1])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{(max_num + 1):03d}"

def buscar_paciente_duplicado(nombre):
    if not nombre or not nombre.strip():
        return None
    nombre_clean = nombre.strip().lower()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = ?', (nombre_clean,))
    row = c.fetchone()
    conn.close()
    return row

def guardar_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus='A', usuario='admin'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes 
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), str(fecha_ingreso), str(fecha_nacimiento), sexo, estatus, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET estatus = ? WHERE paciente_id = ?', (nuevo_estatus, paciente_id))
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def listar_pacientes_por_estatus(estatus='A'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro FROM pacientes WHERE estatus = ? ORDER BY LOWER(nombre_completo) ASC', (estatus,))
    rows = c.fetchall()
    conn.close()
    return rows

def listar_todos_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_registro, usuario_registro FROM pacientes ORDER BY LOWER(nombre_completo) ASC')
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
        LEFT JOIN pacientes p ON e.paciente_id = p.paciente_id
        ORDER BY e.fecha_modificacion DESC
    ''')
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
    if c.fetchone():
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

def listar_todos_medicamentos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT m.paciente_id, p.nombre_completo, m.meds_json, m.observaciones, m.fecha_modificacion, p.estatus
        FROM medicamentos m
        LEFT JOIN pacientes p ON m.paciente_id = p.paciente_id
        ORDER BY LOWER(p.nombre_completo) ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def registrar_entrega_meds(paciente_id, entregas_list, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalles_json = json.dumps(entregas_list, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO entregas_meds (paciente_id, detalles_json, fecha_entrega, usuario_entrega)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, detalles_json, fecha_actual, usuario))
    
    # Descontar del inventario del paciente en la tabla medicamentos
    meds_cargados, obs_cargadas, _, _, _ = obtener_medicamentos(paciente_id)
    if meds_cargados:
        for ent in entregas_list:
            m_nombre = ent["nombre"]
            cant_entregada = ent["cantidad_entregada"]
            for med in meds_cargados:
                if med["nombre"] == m_nombre:
                    med["existencia"] = max(0, float(med.get("existencia", 0)) - cant_entregada)
        
        # Guardar existencia actualizada
        meds_json_updated = json.dumps(meds_cargados, ensure_ascii=False)
        c.execute('UPDATE medicamentos SET meds_json = ?, fecha_modificacion = ? WHERE paciente_id = ?',
                  (meds_json_updated, fecha_actual, paciente_id))
        
    conn.commit()
    conn.close()

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(self.epw, 8, "SISTEMA DE ATENCION Y CONTROL DE PACIENTES", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.cell(self.epw, 5, "Evaluacion Clinica y Tratamiento Farmacologico", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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

def agregar_encabezado_paciente(pdf, datos_p):
    if not datos_p:
        return
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    
    p_id = datos_p[0]
    p_nombre = datos_p[1]
    p_ingreso = datos_p[2]
    p_nac = datos_p[3]
    p_sexo = datos_p[4]
    
    info_line1 = f"PACIENTE: {limpiar_texto(p_nombre)} | FOLIO: {limpiar_texto(p_id)}"
    info_line2 = f"F. Ingreso: {limpiar_texto(p_ingreso)} | F. Nacimiento: {limpiar_texto(p_nac)} | Sexo: {limpiar_texto(p_sexo)}"
    
    pdf.cell(pdf.epw, 6, info_line1, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 6, info_line2, border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

def generar_pdf_entrevista(paciente_id, datos, datos_p):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente(pdf, datos_p)
    
    # Datos Principales
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "ENTREVISTA INICIAL DE CONSEJERIA", new_x="LMARGIN", new_y="NEXT")
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
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto Principal: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
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
    pdf.cell(pdf.epw, 5, f"Importancia actual de dejar de consumir: {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "EVALUACION Y EVALUADOR", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))} - Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos_paciente(paciente_id, meds_list, observaciones, datos_p):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente(pdf, datos_p)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "ESQUEMA DE DOSIFICACION DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [45, 20, 20, 20, 22, 23, 40]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis Diaria", "Existencia", "Indicaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for m in meds_list:
        d_m = float(m.get("dosis_manana", 0))
        d_t = float(m.get("dosis_tarde", 0))
        d_n = float(m.get("dosis_noche", 0))
        d_total = d_m + d_t + d_n
        ex = float(m.get("existencia", 0))
        
        pdf.cell(col_w[0], 6, limpiar_texto(m.get("nombre", "")), border=1)
        pdf.cell(col_w[1], 6, str(d_m), border=1, align="C")
        pdf.cell(col_w[2], 6, str(d_t), border=1, align="C")
        pdf.cell(col_w[3], 6, str(d_n), border=1, align="C")
        pdf.cell(col_w[4], 6, str(d_total), border=1, align="C")
        pdf.cell(col_w[5], 6, str(ex), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(m.get("indicaciones", "")), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.epw, 5, "Observaciones / Alergias:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_general_medicamentos():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA GENERAL DE PACIENTES, MEDICAMENTOS Y DOSIS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(pdf.epw, 5, f"Fecha de emision: {fecha_str} | Usuarios Activos Ordenados Alfabeticamente", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pacientes_activos = listar_pacientes_por_estatus('A')
    
    if not pacientes_activos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 8, "No hay usuarios activos registrados en el sistema.", new_x="LMARGIN", new_y="NEXT")
    else:
        for p in pacientes_activos:
            p_id, p_nombre, p_ingreso, p_nac, p_sexo, _, _, _ = p
            
            # Encabezado del paciente
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(230, 240, 250)
            p_head = f"{limpiar_texto(p_nombre)} (Folio: {p_id}) | F. Ingreso: {p_ingreso} | F. Nac: {p_nac} | Sexo: {p_sexo}"
            pdf.cell(pdf.epw, 6, p_head, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
            
            meds_cargados, obs, _, _, _ = obtener_medicamentos(p_id)
            if not meds_cargados:
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(pdf.epw, 5, "   (Sin medicamentos asignados)", border="LRB", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font("Helvetica", "B", 8)
                col_w = [45, 20, 20, 20, 22, 23, 40]
                headers = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis Diaria", "Existencia", "Indicaciones"]
                
                for i, h in enumerate(headers):
                    pdf.cell(col_w[i], 5, h, border=1, align="C")
                pdf.ln()
                
                pdf.set_font("Helvetica", "", 8)
                for m in meds_cargados:
                    d_m = float(m.get("dosis_manana", 0))
                    d_t = float(m.get("dosis_tarde", 0))
                    d_n = float(m.get("dosis_noche", 0))
                    d_total = d_m + d_t + d_n
                    ex = float(m.get("existencia", 0))
                    
                    pdf.cell(col_w[0], 5, limpiar_texto(m.get("nombre", "")), border=1)
                    pdf.cell(col_w[1], 5, str(d_m), border=1, align="C")
                    pdf.cell(col_w[2], 5, str(d_t), border=1, align="C")
                    pdf.cell(col_w[3], 5, str(d_n), border=1, align="C")
                    pdf.cell(col_w[4], 5, str(d_total), border=1, align="C")
                    pdf.cell(col_w[5], 5, str(ex), border=1, align="C")
                    pdf.cell(col_w[6], 5, limpiar_texto(m.get("indicaciones", "")), border=1, new_x="LMARGIN", new_y="NEXT")
                
                if obs:
                    pdf.set_font("Helvetica", "I", 7)
                    pdf.cell(pdf.epw, 4, f"   Obs: {limpiar_texto(obs)}", border="LRB", new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(3)
            
    pdf_filename = f"Lista_General_Medicamentos_Dosis_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_comprobante_entrega(paciente_id, entregas_list, datos_p):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    agregar_encabezado_paciente(pdf, datos_p)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "COMPROBANTE DE ENTREGA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.cell(pdf.epw, 5, f"Fecha y hora de entrega: {fecha_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [70, 40, 40, 40]
    headers = ["Medicamento", "Cant. Entregada", "Stock Restante", "Dosis Diaria"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    for ent in entregas_list:
        pdf.cell(col_w[0], 6, limpiar_texto(ent["nombre"]), border=1)
        pdf.cell(col_w[1], 6, str(ent["cantidad_entregada"]), border=1, align="C")
        pdf.cell(col_w[2], 6, str(ent["stock_restante"]), border=1, align="C")
        pdf.cell(col_w[3], 6, str(ent["dosis_diaria"]), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 5, "_______________________________________", align="C")
    pdf.cell(90, 5, "_______________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(90, 5, "Firma del Paciente / Familiar", align="C")
    pdf.cell(90, 5, "Firma de Quien Entrega", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Comprobante_Entrega_{paciente_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_compras(lista_alertas):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA DE COMPRAS Y REABASTECIMIENTO DE MEDICAMENTOS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(pdf.epw, 5, f"Fecha de reporte: {fecha_str}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = [25, 45, 38, 22, 22, 22, 16]
    headers = ["Folio", "Paciente", "Medicamento", "Existencia", "Dosis/Dia", "Sugerido", "Nivel"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for al in lista_alertas:
        pdf.cell(col_w[0], 6, limpiar_texto(al["paciente_id"]), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(al["nombre_paciente"]), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(al["medicamento"]), border=1)
        pdf.cell(col_w[3], 6, str(al["existencia"]), border=1, align="C")
        pdf.cell(col_w[4], 6, str(al["dosis_diaria"]), border=1, align="C")
        pdf.cell(col_w[5], 6, str(al["sugerido_compra"]), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(al["nivel"]), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR DB Y SESIÓN ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Pacientes</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales de usuario</p>", unsafe_allow_html=True)
    
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
    st.sidebar.title("📋 Control de Pacientes")
    st.sidebar.write(f"👤 **Atiende**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "👤 Registro de Usuarios",
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "⚙️ Seguridad / Contraseña"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # MÓDULO 1: REGISTRO DE USUARIOS (PACIENTES)
    # ==========================================
    if menu == "👤 Registro de Usuarios":
        st.title("👤 Registro de Usuarios (Pacientes)")
        st.caption("Alta, edición y control de estatus de usuarios en el sistema")
        
        tab_alta, tab_activos, tab_bloqueados = st.tabs([
            "🆕 Nuevo Registro",
            "🟢 Usuarios Activos ('A')",
            "🔒 Usuarios Bloqueados ('B')"
        ])
        
        with tab_alta:
            folio_sugerido = generar_siguiente_folio()
            with st.form("form_alta_usuario"):
                st.subheader("Datos de Identificación del Usuario")
                c1, c2 = st.columns(2)
                with c1:
                    reg_folio = st.text_input("🔑 Folio / ID de Paciente *", value=folio_sugerido)
                    reg_nombre = st.text_input("👤 Nombre Completo * (ej. Augusto Lara)")
                    reg_sexo = st.selectbox("🚻 Sexo", ["Masculino", "Femenino", "Otro"])
                with c2:
                    reg_f_ingreso = st.date_input("📅 Fecha de Ingreso", value=date.today())
                    reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=date(1990, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
                
                btn_guardar_usuario = st.form_submit_button("💾 Dar de Alta Usuario", use_container_width=True)
                
                if btn_guardar_usuario:
                    if not reg_nombre.strip():
                        st.error("⚠️ El Nombre Completo es obligatorio.")
                    elif not reg_folio.strip():
                        st.error("⚠️ El Folio / ID es obligatorio.")
                    else:
                        # Validación de duplicados case-insensitive
                        dup = buscar_paciente_duplicado(reg_nombre)
                        if dup and dup[0] != reg_folio.strip():
                            p_exist_id, p_exist_nombre, p_exist_estatus = dup
                            st_desc = "ACTIVO ('A')" if p_exist_estatus == 'A' else "BLOQUEADO ('B')"
                            st.error(f"❌ Imposible registrar: Ya existe un usuario registrado con el nombre '{p_exist_nombre}' bajo el Folio {p_exist_id} (Estatus actual: {st_desc}). No se permiten registros duplicados.")
                        else:
                            guardar_paciente(
                                reg_folio.strip(),
                                reg_nombre,
                                reg_f_ingreso,
                                reg_f_nacimiento,
                                reg_sexo,
                                estatus='A',
                                usuario=st.session_state["username"]
                            )
                            st.success(f"✅ ¡Usuario {reg_nombre} (Folio: {reg_folio.strip()}) registrado exitosamente!")
                            st.rerun()

        with tab_activos:
            st.subheader("🟢 Directorio de Usuarios Activos")
            activos = listar_pacientes_por_estatus('A')
            if not activos:
                st.info("No hay usuarios activos registrados actualmente.")
            else:
                for p in activos:
                    p_id, p_nom, p_ing, p_nac, p_sex, p_est, p_reg, p_usu = p
                    with st.expander(f"👤 **{p_nom}** | Folio: `{p_id}` | Ingreso: {p_ing}"):
                        c_a, c_b, c_c = st.columns([2, 2, 1])
                        with c_a:
                            st.write(f"**Fecha de Nacimiento:** {p_nac}")
                            st.write(f"**Sexo:** {p_sex}")
                        with c_b:
                            st.write(f"**Fecha Registro:** {p_reg}")
                            st.write(f"**Registrado por:** {p_usu}")
                        with c_c:
                            if st.button("🔒 Bloquear Usuario", key=f"bloq_{p_id}"):
                                cambiar_estatus_paciente(p_id, 'B')
                                st.warning(f"Usuario {p_nom} bloqueado.")
                                st.rerun()

        with tab_bloqueados:
            st.subheader("🔒 Directorio de Usuarios Bloqueados ('B')")
            bloqueados = listar_pacientes_por_estatus('B')
            if not bloqueados:
                st.info("No hay usuarios bloqueados en el sistema.")
            else:
                for p in bloqueados:
                    p_id, p_nom, p_ing, p_nac, p_sex, p_est, p_reg, p_usu = p
                    with st.expander(f"🔒 **{p_nom}** | Folio: `{p_id}` (BLOQUEADO)"):
                        c_a, c_b, c_c = st.columns([2, 2, 1])
                        with c_a:
                            st.write(f"**Fecha de Nacimiento:** {p_nac}")
                            st.write(f"**Sexo:** {p_sex}")
                        with c_b:
                            st.write(f"**Fecha Registro:** {p_reg}")
                            st.write(f"**Registrado por:** {p_usu}")
                        with c_c:
                            if st.button("🔓 Desbloquear / Activar", key=f"desbloq_{p_id}"):
                                cambiar_estatus_paciente(p_id, 'A')
                                st.success(f"Usuario {p_nom} desbloqueado y reactivado.")
                                st.rerun()

    # ==========================================
    # MÓDULO 2: NUEVA ENTREVISTA / EDITAR
    # ==========================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema. Primero registre un usuario en 'Registro de Usuarios'.")
        else:
            opciones_pac = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            pac_seleccionado_label = st.selectbox("👤 Seleccione el Paciente Activo *", list(opciones_pac.keys()))
            paciente_id_input = opciones_pac[pac_seleccionado_label]
            
            datos_paciente = obtener_paciente(paciente_id_input)
            if datos_paciente:
                st.info(f"📌 **Paciente:** {datos_paciente[1]} | **Folio:** {datos_paciente[0]} | **Ingreso:** {datos_paciente[2]} | **F. Nac:** {datos_paciente[3]} | **Sexo:** {datos_paciente[4]}")
            
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            datos_existentes = datos_cargados if datos_cargados else {}
            if datos_cargados:
                st.success(f"📌 Expediente de entrevista cargado. Última modificación: {f_mod} por {u_reg}")

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
                        dependientes_quienes = st.text_input("¿Quiénes o cuántos?", value=datos_existentes.get("dependientes_quienes", ""))
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
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("¿Por qué se abstuvo y qué hizo para mantenerse?", value=datos_existentes.get("abst_motivo", ""))
                    abst_6meses = st.text_area("En los últimos 6 meses, mayor periodo sin consumir", value=datos_existentes.get("abst_6meses", ""))
                    
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("¿Qué tan importante es dejar de consumir?", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("¿Quiénes integran su familia?", value=datos_existentes.get("familia_integrantes", ""))
                    relaciones_post_consumo = st.selectbox("¿Ha tenido relaciones sexuales tras consumir?", ["NO", "SÍ"], index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    abuso_flag = st.selectbox("¿Involucrado en abuso físico/sexual por consumo?", ["NO", "SÍ"], index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas presentados durante la sesión", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    c_f1, c_f2 = st.columns(2)
                    with c_f1:
                        evaluador_nombre = st.text_input("Nombre de quien aplica", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2:
                        evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Expediente de Entrevista", use_container_width=True)
                
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
                    st.success(f"✅ ¡Entrevista guardada para {datos_paciente[1]} ({paciente_id_input})!")

    # ==========================================
    # MÓDULO 3: BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio e Historial de Pacientes")
        
        filtro_ver = st.radio("Mostrar:", ["🟢 Solo Pacientes Activos ('A')", "📋 Todos los Pacientes (Incluye Bloqueados)"], horizontal=True)
        solo_act = (filtro_ver == "🟢 Solo Pacientes Activos ('A')")
        
        entrevistas = listar_entrevistas()
        if solo_act:
            entrevistas = [e for e in entrevistas if e[5] == 'A']
            
        if not entrevistas:
            st.info("No hay entrevistas registradas con ese criterio.")
        else:
            st.subheader(f"Total de entrevistas: {len(entrevistas)}")
            for ent in entrevistas:
                p_id, p_nom, f_reg, f_mod, u_reg, p_est = ent
                p_nom_str = p_nom if p_nom else p_id
                badge = "🟢 ACTIVO" if p_est == 'A' else "🔒 BLOQUEADO"
                
                with st.expander(f"👤 **{p_nom_str}** (Folio: `{p_id}`) | {badge} | Modificado: {f_mod}"):
                    datos_p = obtener_paciente(p_id)
                    datos_e, _, _, _ = obtener_entrevista(p_id)
                    
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        if datos_p:
                            st.write(f"**Fecha Ingreso:** {datos_p[2]} | **F. Nacimiento:** {datos_p[3]} | **Sexo:** {datos_p[4]}")
                        st.write(f"**Registrado el:** {f_reg} | **Por usuario:** {u_reg}")
                    with c2:
                        if datos_e and datos_p:
                            pdf_file = generar_pdf_entrevista(p_id, datos_e, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Imprimir Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{p_id}"
                                )

    # ==========================================
    # MÓDULO 4: CONTROL DE MEDICAMENTOS Y DOSIS
    # ==========================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosis")
        st.caption("Asignación de esquemas de dosificación y existencias por usuario")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema.")
        else:
            # BOTÓN PRINCIPAL PARA IMPRIMIR LA LISTA GENERAL DE MEDICAMENTOS ORDENADA ALFABÉTICAMENTE
            st.markdown("---")
            col_gen1, col_gen2 = st.columns([2, 1])
            with col_gen1:
                st.markdown("### 🖨️ Lista General de Medicamentos y Dosis")
                st.caption("Descarga la lista completa de todos los usuarios activos ordenados alfabéticamente con sus medicamentos y dosis (Mañana, Tarde, Noche).")
            with col_gen2:
                pdf_gen_file = generar_pdf_lista_general_medicamentos()
                with open(pdf_gen_file, "rb") as f_gen:
                    st.download_button(
                        label="📄 Imprimir Lista General (PDF)",
                        data=f_gen,
                        file_name=pdf_gen_file,
                        mime="application/pdf",
                        key="btn_pdf_general_meds",
                        use_container_width=True
                    )
            st.markdown("---")
            
            # SELECCIÓN Y EDICIÓN POR PACIENTE INDIVIDUAL
            opciones_pac = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            pac_seleccionado_label = st.selectbox("👤 Seleccione el Paciente Activo *", list(opciones_pac.keys()), key="select_med_pac")
            paciente_id_input = opciones_pac[pac_seleccionado_label]
            
            datos_paciente = obtener_paciente(paciente_id_input)
            if datos_paciente:
                st.info(f"📌 **Paciente:** {datos_paciente[1]} | **Folio:** {datos_paciente[0]} | **Ingreso:** {datos_paciente[2]} | **F. Nac:** {datos_paciente[3]} | **Sexo:** {datos_paciente[4]}")
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_id_input)
            
            st.subheader("Configuración de Medicamentos")
            num_meds = st.number_input("Número de medicamentos a asignar", min_value=1, max_value=15, value=max(1, len(meds_cargados)))
            
            with st.form("form_control_meds"):
                meds_input = []
                for i in range(int(num_meds)):
                    m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                    st.markdown(f"**Medicamento #{i+1}**")
                    c_a, c_b, c_c, c_d, c_e, c_f = st.columns([2.5, 1, 1, 1, 1.5, 2])
                    
                    with c_a:
                        m_nombre = st.text_input("Nombre del Medicamento", value=m_prev.get("nombre", ""), key=f"m_nom_{i}")
                    with c_b:
                        m_man = st.number_input("☀️ Mañana", min_value=0.0, value=float(m_prev.get("dosis_manana", 0)), step=0.5, key=f"m_man_{i}")
                    with c_c:
                        m_tar = st.number_input("🌤️ Tarde", min_value=0.0, value=float(m_prev.get("dosis_tarde", 0)), step=0.5, key=f"m_tar_{i}")
                    with c_d:
                        m_noc = st.number_input("🌙 Noche", min_value=0.0, value=float(m_prev.get("dosis_noche", 0)), step=0.5, key=f"m_noc_{i}")
                    with c_e:
                        m_ex = st.number_input("📦 Existencia", min_value=0.0, value=float(m_prev.get("existencia", 0)), step=1.0, key=f"m_ex_{i}")
                    with c_f:
                        m_ind = st.text_input("Indicaciones", value=m_prev.get("indicaciones", ""), key=f"m_ind_{i}")
                        
                    if m_nombre.strip():
                        meds_input.append({
                            "nombre": m_nombre.strip(),
                            "dosis_manana": m_man,
                            "dosis_tarde": m_tar,
                            "dosis_noche": m_noc,
                            "existencia": m_ex,
                            "indicaciones": m_ind
                        })
                    st.divider()
                
                obs_meds = st.text_area("Observaciones Generales / Alergias Medicamentosas", value=obs_cargadas)
                btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_id_input, meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ Esquema de medicamentos guardado para {datos_paciente[1]}.")
                    st.rerun()

            # Vista previa e impresión individual del paciente
            if meds_cargados and datos_paciente:
                st.markdown("---")
                c_p1, c_p2 = st.columns([3, 1])
                with c_p1:
                    st.write(f"**Ficha de Medicación de {datos_paciente[1]}** ({len(meds_cargados)} medicamentos registrados)")
                with c_p2:
                    pdf_med_individual = generar_pdf_medicamentos_paciente(paciente_id_input, meds_cargados, obs_cargadas, datos_paciente)
                    with open(pdf_med_individual, "rb") as f_ind:
                        st.download_button(
                            label="🖨️ Imprimir Ficha Individual (PDF)",
                            data=f_ind,
                            file_name=f"Medicacion_{paciente_id_input}.pdf",
                            mime="application/pdf",
                            key="btn_pdf_med_ind"
                        )

    # ==========================================
    # MÓDULO 5: ENTREGA DE MEDICAMENTOS
    # ==========================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega de Medicamentos")
        st.caption("Registro de entrega diaria y descuento automático del inventario")
        
        pacientes_activos = listar_pacientes_por_estatus('A')
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos en el sistema.")
        else:
            opciones_pac = {f"{p[1]} (Folio: {p[0]})": p[0] for p in pacientes_activos}
            pac_seleccionado_label = st.selectbox("👤 Seleccione el Paciente Activo *", list(opciones_pac.keys()), key="select_entrega_pac")
            paciente_id_input = opciones_pac[pac_seleccionado_label]
            
            datos_paciente = obtener_paciente(paciente_id_input)
            if datos_paciente:
                st.info(f"📌 **Paciente:** {datos_paciente[1]} | **Folio:** {datos_paciente[0]} | **Ingreso:** {datos_paciente[2]}")
            
            meds_cargados, _, _, _, _ = obtener_medicamentos(paciente_id_input)
            # Filtrar solo los medicamentos que tengan existencia > 0
            meds_disponibles = [m for m in meds_cargados if float(m.get("existencia", 0)) > 0]
            
            if not meds_disponibles:
                st.warning("⚠️ Este paciente no tiene medicamentos disponibles con existencia física en inventario (`Existencia > 0`). Primero reabastezca en 'Control de Medicamentos y Dosis'.")
            else:
                st.subheader("Medicamentos Disponibles para Entrega")
                
                # Manejo de estado para descargar comprobante post-entrega por fuera del form
                if "entrega_exitosa" not in st.session_state:
                    st.session_state["entrega_exitosa"] = False
                    st.session_state["pdf_comprobante_path"] = ""
                    st.session_state["entrega_paciente_id"] = ""

                with st.form("form_entrega_meds"):
                    items_a_entregar = []
                    for i, m in enumerate(meds_disponibles):
                        m_nom = m["nombre"]
                        d_total = float(m.get("dosis_manana", 0)) + float(m.get("dosis_tarde", 0)) + float(m.get("dosis_noche", 0))
                        ex_actual = float(m.get("existencia", 0))
                        
                        # El valor por defecto es la Dosis Diaria Total (o el stock actual si es menor)
                        dosis_defecto = d_total if d_total > 0 else 1.0
                        val_defecto = min(dosis_defecto, ex_actual)
                        
                        st.markdown(f"**💊 {m_nom}** | Dosis Diaria: `{d_total}` | Existencia Actual: `{ex_actual}`")
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            cant_entregar = st.number_input(
                                f"Cantidad a entregar de {m_nom}",
                                min_value=1.0,
                                max_value=ex_actual,
                                value=float(val_defecto),
                                step=1.0,
                                key=f"ent_{i}"
                            )
                        with c2:
                            st.caption(f"Indicaciones: {m.get('indicaciones', 'N/A')}")
                            
                        items_a_entregar.append({
                            "nombre": m_nom,
                            "cantidad_entregada": cant_entregar,
                            "stock_restante": ex_actual - cant_entregar,
                            "dosis_diaria": d_total
                        })
                        st.divider()
                        
                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                    
                    if btn_confirmar_entrega:
                        registrar_entrega_meds(paciente_id_input, items_a_entregar, st.session_state["username"])
                        pdf_comp = generar_pdf_comprobante_entrega(paciente_id_input, items_a_entregar, datos_paciente)
                        
                        st.session_state["entrega_exitosa"] = True
                        st.session_state["pdf_comprobante_path"] = pdf_comp
                        st.session_state["entrega_paciente_id"] = paciente_id_input
                        st.rerun()

                # Mostrar botón de descarga de PDF fuera del formulario
                if st.session_state.get("entrega_exitosa") and st.session_state.get("entrega_paciente_id") == paciente_id_input:
                    st.success("✅ ¡Entrega de medicamentos registrada con éxito y descontada del inventario!")
                    pdf_path = st.session_state.get("pdf_comprobante_path")
                    if pdf_path and os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as f_comp:
                            st.download_button(
                                label="🖨️ Descargar Comprobante de Entrega (PDF)",
                                data=f_comp,
                                file_name=os.path.basename(pdf_path),
                                mime="application/pdf",
                                key="btn_download_comprobante"
                            )

    # ==========================================
    # MÓDULO 6: ALERTAS DE EXISTENCIA Y COMPRAS
    # ==========================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencia y Compras")
        st.caption("Consolidado de inventario y estimación de reabastecimiento para usuarios activos")
        
        todos_meds = listar_todos_medicamentos()
        # Filtrar medicamentos solo de usuarios activos
        meds_activos = [m for m in todos_meds if m[5] == 'A']
        
        alertas = []
        criticos_count = 0
        warning_count = 0
        
        for m_row in meds_activos:
            p_id, p_nom, m_json_str, obs, f_mod, p_est = m_row
            p_nom_clean = p_nom if p_nom else p_id
            
            if m_json_str:
                try:
                    meds_list = json.loads(m_json_str)
                    for med in meds_list:
                        m_nom = med.get("nombre", "")
                        d_m = float(med.get("dosis_manana", 0))
                        d_t = float(med.get("dosis_tarde", 0))
                        d_n = float(med.get("dosis_noche", 0))
                        d_diaria = d_m + d_t + d_n
                        ex = float(med.get("existencia", 0))
                        
                        if d_diaria > 0:
                            dias_restantes = ex / d_diaria
                            if dias_restantes < 1.0:
                                nivel = "🔴 CRÍTICO"
                                criticos_count += 1
                                sugerido = max(1.0, (d_diaria * 7) - ex)
                            elif dias_restantes < 3.0:
                                nivel = "🟡 PREVENTIVO"
                                warning_count += 1
                                sugerido = max(1.0, (d_diaria * 7) - ex)
                            else:
                                continue
                                
                            alertas.append({
                                "paciente_id": p_id,
                                "nombre_paciente": p_nom_clean,
                                "medicamento": m_nom,
                                "existencia": ex,
                                "dosis_diaria": d_diaria,
                                "dias_restantes": round(dias_restantes, 1),
                                "sugerido_compra": round(sugerido, 1),
                                "nivel": nivel
                            })
                except Exception:
                    pass

        col1, col2 = st.columns(2)
        with col1:
            st.metric("🔴 Pacientes en Alerta Crítica (<1 día)", criticos_count)
        with col2:
            st.metric("🟡 Pacientes en Alerta Preventiva (<3 días)", warning_count)
            
        st.markdown("---")
        
        if not alertas:
            st.success("🎉 ¡Excelente! Todos los usuarios activos cuentan con existencias suficientes para cubrir más de 3 días de tratamiento.")
        else:
            st.subheader("📋 Lista de Medicamentos a Comprar")
            
            col_pdf1, col_pdf2 = st.columns([3, 1])
            with col_pdf2:
                pdf_compras = generar_pdf_lista_compras(alertas)
                with open(pdf_compras, "rb") as f_c:
                    st.download_button(
                        label="🖨️ Descargar Lista de Compras (PDF)",
                        data=f_c,
                        file_name=pdf_compras,
                        mime="application/pdf",
                        key="pdf_compras_btn"
                    )
                    
            for al in alertas:
                st.write(f"**{al['nivel']}** | Paciente: **{al['nombre_paciente']}** (`{al['paciente_id']}`) | Medicamento: **{al['medicamento']}**")
                st.write(f"Existencia actual: `{al['existencia']}` | Dosis diaria: `{al['dosis_diaria']}` | Días restantes: `{al['dias_restantes']}` | **Sugerido a comprar (7 días):** `{al['sugerido_compra']}`")
                st.divider()

    # ==========================================
    # MÓDULO 7: SEGURIDAD Y CONTRASEÑA
    # ==========================================
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

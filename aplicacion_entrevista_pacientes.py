import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Seguimiento Clinico",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS & INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 1. Usuarios del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    # 2. Registro de Pacientes / Usuarios de la Comunidad
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            tipo_usuario TEXT NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT NOT NULL,
            estatus TEXT DEFAULT 'A',
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            hermano_mayor_id TEXT DEFAULT NULL,
            fecha_suelta TEXT DEFAULT NULL,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    # 3. Entrevistas Iniciales
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    # 4. Medicamentos
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
    # 5. Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_meds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            fecha_entrega TEXT NOT NULL,
            meds_entregados_json TEXT NOT NULL,
            usuario_entrega TEXT NOT NULL
        )
    ''')
    # 6. Historial de Cambios de Etapa
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            etapa_origen TEXT NOT NULL,
            etapa_destino TEXT NOT NULL,
            fecha_cambio TEXT NOT NULL,
            usuario_autorizo TEXT NOT NULL
        )
    ''')
    # 7. Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            tipo_grupo TEXT NOT NULL,
            fecha TEXT NOT NULL,
            etapa_actual TEXT NOT NULL,
            compartimiento TEXT,
            observaciones TEXT,
            devoluciones TEXT,
            como_se_queda TEXT,
            logros TEXT,
            dificultades TEXT,
            facilitador TEXT NOT NULL,
            usuario_registro TEXT NOT NULL
        )
    ''')
    # 8. Requisitos de Etapas
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT NOT NULL,
            nombre_requisito TEXT NOT NULL,
            tipo_requisito TEXT NOT NULL
        )
    ''')
    # 9. Checklist Manual de Estado de Requisitos por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_checklist_manual (
            paciente_id TEXT NOT NULL,
            requisito_id INTEGER NOT NULL,
            completado INTEGER DEFAULT 0,
            PRIMARY KEY (paciente_id, requisito_id)
        )
    ''')

    # Requisitos por defecto si la tabla está vacía
    c.execute('SELECT COUNT(*) FROM requisitos_etapas')
    if c.fetchone()[0] == 0:
        reqs_def = [
            ("ACOGIDA", "Compromiso Existencial", "Manual"),
            ("ACOGIDA", "2 Señalamientos correctos", "Manual"),
            ("ACOGIDA", "5 Reglas de Usuario", "Manual"),
            ("ACOGIDA", "5 Reglas de Convivencia", "Manual"),
            
            ("IDENTIFICACIÓN", "Autobiografía", "Manual"),
            ("IDENTIFICACIÓN", "Oración de la mañana", "Manual"),
            ("IDENTIFICACIÓN", "Filosofía de la Comunidad", "Manual"),
            ("IDENTIFICACIÓN", "10 Reglas de Usuario", "Manual"),
            ("IDENTIFICACIÓN", "10 Reglas de Convivencia", "Manual"),
            ("IDENTIFICACIÓN", "4 Grupos 'Aquí y Ahora'", "Grupo"),
            ("IDENTIFICACIÓN", "4 Grupos 'Terapia de Grupo'", "Grupo"),
            ("IDENTIFICACIÓN", "4 Grupos 'Feedbacks'", "Grupo"),
            
            ("ELABORACIÓN", "Filosofía del Ayer, Hoy y Mañana", "Manual"),
            ("ELABORACIÓN", "Oración del Medio día", "Manual"),
            ("ELABORACIÓN", "15 Reglas de Usuario", "Manual"),
            ("ELABORACIÓN", "15 Reglas de Convivencia", "Manual"),
            ("ELABORACIÓN", "Proyecto de vida", "Manual"),
            ("ELABORACIÓN", "4 Grupos 'Aquí y Ahora'", "Grupo"),
            ("ELABORACIÓN", "4 Grupos 'Terapia de Grupo'", "Grupo"),
            ("ELABORACIÓN", "4 Grupos 'Feedbacks'", "Grupo"),
            
            ("CONSOLIDACIÓN", "30 Reglas de Usuario", "Manual"),
            ("CONSOLIDACIÓN", "20 Reglas de Convivencia", "Manual"),
            ("CONSOLIDACIÓN", "Oración del Medio día", "Manual"),
            ("CONSOLIDACIÓN", "Plan de Servicio Social", "Manual"),
            ("CONSOLIDACIÓN", "2 Grupos 'Aquí y Ahora'", "Grupo"),
            ("CONSOLIDACIÓN", "2 Grupos 'Terapia de Grupo'", "Grupo"),
            ("CONSOLIDACIÓN", "2 Grupos 'Feedbacks'", "Grupo"),
            
            ("SERVICIO SOCIAL", "30 Días de Servicio", "Manual"),
            ("SERVICIO SOCIAL", "2 Grupos 'Aquí y Ahora'", "Grupo"),
            ("SERVICIO SOCIAL", "2 Grupos 'Terapia de Grupo'", "Grupo"),
            ("SERVICIO SOCIAL", "2 Grupos 'Feedbacks'", "Grupo")
        ]
        c.executemany('INSERT INTO requisitos_etapas (etapa, nombre_requisito, tipo_requisito) VALUES (?, ?, ?)', reqs_def)

    # Usuario administrador por defecto
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
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except:
                pass
    return f"PAC-{(max_num + 1):03d}"

def buscar_paciente_por_nombre(nombre):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes_registro WHERE LOWER(nombre_completo) = LOWER(?)', (nombre.strip(),))
    row = c.fetchone()
    conn.close()
    return row

def guardar_o_actualizar_paciente(paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE pacientes_registro
            SET nombre_completo = ?, tipo_usuario = ?, fecha_ingreso = ?, fecha_nacimiento = ?,
                sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (nombre_completo.strip(), tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_actual, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes_registro 
            (paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, fecha_registro, fecha_modificacion, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACOGIDA', ?, ?, ?)
        ''', (paciente_id, nombre_completo.strip(), tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, fecha_actual, fecha_actual, usuario))
        
    conn.commit()
    conn.close()

def obtener_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, hermano_mayor_id, fecha_suelta, fecha_registro, fecha_modificacion FROM pacientes_registro WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "paciente_id": row[0],
            "nombre_completo": row[1],
            "tipo_usuario": row[2],
            "fecha_ingreso": row[3],
            "fecha_nacimiento": row[4],
            "sexo": row[5],
            "estatus": row[6],
            "etapa_actual": row[7],
            "hermano_mayor_id": row[8],
            "fecha_suelta": row[9],
            "fecha_registro": row[10],
            "fecha_modificacion": row[11]
        }
    return None

def listar_pacientes_registro(solo_activos=True, tipo_filtro=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT paciente_id, nombre_completo, tipo_usuario, fecha_ingreso, fecha_nacimiento, sexo, estatus, etapa_actual, hermano_mayor_id, fecha_suelta FROM pacientes_registro'
    conditions = []
    params = []
    
    if solo_activos:
        conditions.append("estatus = 'A'")
    if tipo_filtro:
        conditions.append("tipo_usuario = ?")
        params.append(tipo_filtro)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += ' ORDER BY LOWER(nombre_completo) ASC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def cambiar_estatus_paciente(paciente_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes_registro SET estatus = ? WHERE paciente_id = ?', (nuevo_estatus, paciente_id))
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

def listar_entrevistas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT e.paciente_id, p.nombre_completo, e.fecha_registro, e.fecha_modificacion, e.usuario_registro, p.estatus
        FROM entrevistas e
        JOIN pacientes_registro p ON e.paciente_id = p.paciente_id
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

def registrar_entrega_meds(paciente_id, meds_entregados, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    meds_actuales, obs, f_r, f_m, u_r = obtener_medicamentos(paciente_id)
    meds_dict = {m['nombre']: m for m in meds_actuales}
    
    for entregado in meds_entregados:
        nombre = entregado['nombre']
        cant = entregado['cantidad']
        if nombre in meds_dict:
            existencia_actual = int(meds_dict[nombre].get('existencia', 0))
            nueva_existencia = max(0, existencia_actual - cant)
            meds_dict[nombre]['existencia'] = nueva_existencia
            
    nuevos_meds_list = list(meds_dict.values())
    guardar_medicamentos(paciente_id, nuevos_meds_list, obs, usuario)
    
    entregados_json = json.dumps(meds_entregados, ensure_ascii=False)
    c.execute('''
        INSERT INTO entregas_meds (paciente_id, fecha_entrega, meds_entregados_json, usuario_entrega)
        VALUES (?, ?, ?, ?)
    ''', (paciente_id, fecha_actual, entregados_json, usuario))
    
    conn.commit()
    conn.close()

# --- FUNCIONES DE ETAPAS & GRUPOS ---
DURACION_ETAPAS = {
    "ACOGIDA": 30,
    "IDENTIFICACIÓN": 60,
    "ELABORACIÓN": 60,
    "CONSOLIDACIÓN": 30,
    "SERVICIO SOCIAL": 30
}

ORDEN_ETAPAS = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]

def promover_etapa_paciente(paciente_id, usuario_autorizo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    pac = obtener_paciente(paciente_id)
    if not pac:
        conn.close()
        return False, "Paciente no encontrado"
        
    etapa_actual = pac['etapa_actual']
    if etapa_actual not in ORDEN_ETAPAS:
        etapa_actual = "ACOGIDA"
        
    idx = ORDEN_ETAPAS.index(etapa_actual)
    if idx >= len(ORDEN_ETAPAS) - 1:
        conn.close()
        return False, "El paciente ya se encuentra en la etapa final de SERVICIO SOCIAL."
        
    nueva_etapa = ORDEN_ETAPAS[idx + 1]
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('UPDATE pacientes_registro SET etapa_actual = ? WHERE paciente_id = ?', (nueva_etapa, paciente_id))
    c.execute('''
        INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autorizo)
        VALUES (?, ?, ?, ?, ?)
    ''', (paciente_id, etapa_actual, nueva_etapa, fecha_actual, usuario_autorizo))
    
    conn.commit()
    conn.close()
    return True, nueva_etapa

def asignar_hermano_mayor(paciente_id, hermano_mayor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes_registro SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_mayor_id, paciente_id))
    conn.commit()
    conn.close()

def marcar_suelta_hermano_mayor(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE pacientes_registro SET fecha_suelta = ? WHERE paciente_id = ?', (fecha_actual, paciente_id))
    conn.commit()
    conn.close()

def guardar_grupo_terapeutico(paciente_id, tipo_grupo, fecha, etapa_actual, compartimiento, observaciones, devoluciones, como_se_queda, logros, dificultades, facilitador, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO grupos_terapeuticos 
        (paciente_id, tipo_grupo, fecha, etapa_actual, compartimiento, observaciones, devoluciones, como_se_queda, logros, dificultades, facilitador, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, fecha, etapa_actual, compartimiento, observaciones, devoluciones, como_se_queda, logros, dificultades, facilitador, usuario))
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM grupos_terapeuticos 
        WHERE paciente_id = ? AND etapa_actual = ? AND tipo_grupo = ?
    ''', (paciente_id, etapa, tipo_grupo))
    cnt = c.fetchone()[0]
    conn.close()
    return cnt

def listar_grupos_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, tipo_grupo, fecha, etapa_actual, compartimiento, observaciones, devoluciones, como_se_queda, logros, dificultades, facilitador, usuario_registro
        FROM grupos_terapeuticos
        WHERE paciente_id = ?
        ORDER BY fecha DESC, id DESC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_grupo_terapeutico(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM grupos_terapeuticos WHERE id = ?', (grupo_id,))
    conn.commit()
    conn.close()

# --- REQUISITOS CHECKLIST ---
def obtener_requisitos_etapa(etapa):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre_requisito, tipo_requisito FROM requisitos_etapas WHERE etapa = ?', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_checklist_manual_estado(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT requisito_id, completado FROM pacientes_checklist_manual WHERE paciente_id = ?', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def actualizar_checklist_manual_estado(paciente_id, requisito_id, completado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO pacientes_checklist_manual (paciente_id, requisito_id, completado)
        VALUES (?, ?, ?)
        ON CONFLICT(paciente_id, requisito_id) DO UPDATE SET completado = ?
    ''', (paciente_id, requisito_id, completado, completado))
    conn.commit()
    conn.close()

def agregar_requisito_custom(etapa, nombre_requisito, tipo_requisito):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO requisitos_etapas (etapa, nombre_requisito, tipo_requisito) VALUES (?, ?, ?)', (etapa, nombre_requisito, tipo_requisito))
    conn.commit()
    conn.close()

def eliminar_requisito_custom(requisito_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (requisito_id,))
    c.execute('DELETE FROM pacientes_checklist_manual WHERE requisito_id = ?', (requisito_id,))
    conn.commit()
    conn.close()

# --- GENERADORES DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SAWABONA SHIKOBA - CLINICA DE REHABILITACION", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control y Seguimiento Clinico Individual", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': '', '—': '-', '–': '-'
    }
    for k, v in replacements.items():
        texto = texto.replace(k, v)
    return texto

def generar_pdf_entrevista(paciente_id, datos):
    pac = obtener_paciente(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"ENTREVISTA INICIAL DE CONSEJERIA - FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    if pac:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Paciente: {limpiar_texto(pac['nombre_completo'])} | F. Ingreso: {pac['fecha_ingreso']} | F. Nac: {pac['fecha_nacimiento']} | Sexo: {pac['sexo']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "1. DATOS GENERALES", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(pdf.epw, 5, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "2. CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
    col_w = [28, 20, 25, 30, 28, 22, 37]
    headers = ["Sustancia", "Consumo", "Forma", "Frecuencia", "Cantidad", "Edad Inic.", "Lugar"]
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    tabla_c = datos.get("tabla_consumo", {})
    for sust, vals in tabla_c.items():
        pdf.cell(col_w[0], 6, limpiar_texto(sust), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(str(vals.get("consumo", ""))), border=1, align="C")
        pdf.cell(col_w[2], 6, limpiar_texto(str(vals.get("forma", ""))), border=1)
        pdf.cell(col_w[3], 6, limpiar_texto(str(vals.get("frecuencia", ""))), border=1)
        pdf.cell(col_w[4], 6, limpiar_texto(str(vals.get("cantidad", ""))), border=1)
        pdf.cell(col_w[5], 6, limpiar_texto(str(vals.get("edad_inicio", ""))), border=1, align="C")
        pdf.cell(col_w[6], 6, limpiar_texto(str(vals.get("lugar", ""))), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Sustancia de Impacto Principal: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))} | Modo: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "3. DISPOSICION AL CAMBIO Y EVALUACION CLINICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Importancia actual del cambio: {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Evaluador: {limpiar_texto(datos.get('evaluador_nombre', ''))} - Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    fname = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(fname)
    return fname

def generar_pdf_lista_general_meds():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT p.paciente_id, p.nombre_completo, p.fecha_ingreso, p.fecha_nacimiento, p.sexo, m.meds_json, m.observaciones
        FROM pacientes_registro p
        LEFT JOIN medicamentos m ON p.paciente_id = m.paciente_id
        WHERE p.estatus = 'A'
        ORDER BY LOWER(p.nombre_completo) ASC
    ''')
    rows = c.fetchall()
    conn.close()
    
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTA GENERAL DE MEDICAMENTOS Y DOSIS POR PACIENTE", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    for row in rows:
        p_id, p_nom, p_fing, p_fnac, p_sexo, meds_j, p_obs = row
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, f"PACIENTE: {limpiar_texto(p_nom)} ({p_id}) | F. Ingreso: {p_fing} | F. Nac: {p_fnac} | Sexo: {p_sexo}", border="B", new_x="LMARGIN", new_y="NEXT")
        
        meds_list = json.loads(meds_j) if meds_j else []
        if not meds_list:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(pdf.epw, 5, "Sin medicamentos asignados.", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "B", 8)
            cw = [45, 20, 20, 20, 22, 22, 41]
            hs = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis Diaria", "Existencia", "Indicaciones"]
            for i, h in enumerate(hs):
                pdf.cell(cw[i], 5, h, border=1, align="C")
            pdf.ln()
            
            pdf.set_font("Helvetica", "", 8)
            for m in meds_list:
                m_nom = limpiar_texto(m.get("nombre", ""))
                m_man = str(m.get("dosis_manana", 0))
                m_tar = str(m.get("dosis_tarde", 0))
                m_noc = str(m.get("dosis_noche", 0))
                d_diaria = str(int(m.get("dosis_manana", 0)) + int(m.get("dosis_tarde", 0)) + int(m.get("dosis_noche", 0)))
                m_exi = str(m.get("existencia", 0))
                m_ind = limpiar_texto(m.get("indicaciones", ""))
                
                pdf.cell(cw[0], 5, m_nom, border=1)
                pdf.cell(cw[1], 5, m_man, border=1, align="C")
                pdf.cell(cw[2], 5, m_tar, border=1, align="C")
                pdf.cell(cw[3], 5, m_noc, border=1, align="C")
                pdf.cell(cw[4], 5, d_diaria, border=1, align="C")
                pdf.cell(cw[5], 5, m_exi, border=1, align="C")
                pdf.cell(cw[6], 5, m_ind, border=1, new_x="LMARGIN", new_y="NEXT")
                
        if p_obs:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(pdf.epw, 5, f"Observaciones / Alergias: {limpiar_texto(p_obs)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        
    fname = f"Lista_General_Medicamentos_Dosis_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(fname)
    return fname

def generar_pdf_comprobante_entrega(paciente_id, meds_entregados, usuario_entrega):
    pac = obtener_paciente(paciente_id)
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "COMPROBANTE DE ENTREGA DE MEDICAMENTOS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Folio Paciente: {paciente_id} | Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    if pac:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Nombre del Paciente: {limpiar_texto(pac['nombre_completo'])} | F. Ingreso: {pac['fecha_ingreso']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    cw = [70, 40, 40, 40]
    hs = ["Medicamento Entregado", "Cantidad Entregada", "Stock Restante", "Entregado Por"]
    for i, h in enumerate(hs):
        pdf.cell(cw[i], 6, h, border=1, align="C")
    pdf.ln()
    
    meds_actuales, _, _, _, _ = obtener_medicamentos(paciente_id)
    meds_dict = {m['nombre']: m.get('existencia', 0) for m in meds_actuales}
    
    pdf.set_font("Helvetica", "", 9)
    for me in meds_entregados:
        n = limpiar_texto(me['nombre'])
        c = str(me['cantidad'])
        rest = str(meds_dict.get(me['nombre'], 0))
        pdf.cell(cw[0], 6, n, border=1)
        pdf.cell(cw[1], 6, c, border=1, align="C")
        pdf.cell(cw[2], 6, rest, border=1, align="C")
        pdf.cell(cw[3], 6, limpiar_texto(usuario_entrega), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw / 2, 5, "______________________________________", align="C")
    pdf.cell(pdf.epw / 2, 5, "______________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw / 2, 5, "Firma del Paciente (Recibido)", align="C")
    pdf.cell(pdf.epw / 2, 5, "Firma del Encargado / Staff", align="C", new_x="LMARGIN", new_y="NEXT")
    
    fname = f"Comprobante_Entrega_{paciente_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(fname)
    return fname

def generar_pdf_grupos_paciente(paciente_id):
    pac = obtener_paciente(paciente_id)
    grupos = listar_grupos_paciente(paciente_id)
    
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, f"EXPEDIENTE DE GRUPOS TERAPEUTICOS - FOLIO: {paciente_id}", align="C", new_x="LMARGIN", new_y="NEXT")
    if pac:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(pdf.epw, 6, f"Paciente: {limpiar_texto(pac['nombre_completo'])} | Etapa Actual: {pac['etapa_actual']}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    if not grupos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(pdf.epw, 6, "No hay sesiones de grupos registradas para este paciente.", new_x="LMARGIN", new_y="NEXT")
    else:
        for g in grupos:
            g_id, g_tipo, g_fecha, g_etapa, g_comp, g_obs, g_dev, g_queda, g_logros, g_dific, g_facil, g_user = g
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(pdf.epw, 6, f"[{g_fecha}] {limpiar_texto(g_tipo)} (Etapa: {g_etapa}) - Facilitador: {limpiar_texto(g_facil)}", border="B", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            
            if g_comp:
                pdf.multi_cell(pdf.epw, 5, f"Compartimiento: {limpiar_texto(g_comp)}", new_x="LMARGIN", new_y="NEXT")
            if g_logros:
                pdf.multi_cell(pdf.epw, 5, f"Logros: {limpiar_texto(g_logros)}", new_x="LMARGIN", new_y="NEXT")
            if g_dific:
                pdf.multi_cell(pdf.epw, 5, f"Dificultades: {limpiar_texto(g_dific)}", new_x="LMARGIN", new_y="NEXT")
            if g_obs:
                pdf.multi_cell(pdf.epw, 5, f"Observaciones: {limpiar_texto(g_obs)}", new_x="LMARGIN", new_y="NEXT")
            if g_dev:
                pdf.multi_cell(pdf.epw, 5, f"Devoluciones: {limpiar_texto(g_dev)}", new_x="LMARGIN", new_y="NEXT")
            if g_queda:
                pdf.multi_cell(pdf.epw, 5, f"Como se queda y compromiso: {limpiar_texto(g_queda)}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            
    fname = f"Expediente_Grupos_{paciente_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(fname)
    return fname

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
    st.markdown("<h1 style='text-align: center;'>🌿 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #2e7d32;'>Comunidad Terapéutica para el Tratamiento de Adicciones</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sistema Clinico e Individual de Pacientes</p>", unsafe_allow_html=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Acceso al Sistema")
            user_input = st.text_input("Usuario").strip()
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
        st.info("💡 Credenciales por defecto: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL ---
    st.sidebar.title("🌿 Sawabona Shikoba")
    st.sidebar.caption("Comunidad Terapéutica")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.divider()
    
    menu = st.sidebar.radio(
        "Navegación Principal",
        [
            "👤 Registro y Edición de Usuarios",
            "🎯 Gestión de Etapas & Proceso",
            "🗣️ Grupos Terapéuticos",
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "💊 Control de Medicamentos y Dosis",
            "🚚 Entrega de Medicamentos",
            "🚨 Alertas de Existencia y Compras",
            "⚙️ Configuración del Sistema"
        ]
    )
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # =========================================================================
    # 1. MÓDULO: REGISTRO Y EDICIÓN DE USUARIOS
    # =========================================================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Usuarios (Pacientes / Staff)")
        st.caption("Modulo inicial para dar de alta o modificar la información de los usuarios del sistema")
        
        modo_usuario = st.radio("Acción a realizar:", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        st.divider()
        
        todos_registrados = listar_pacientes_registro(solo_activos=False)
        dict_todos = {f"{p[0]} - {p[1]} ({p[2]} | Status: {p[6]})": p[0] for p in todos_registrados}
        
        datos_editar = None
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            if not dict_todos:
                st.warning("No hay usuarios registrados en el sistema para editar.")
            else:
                pac_sel_key = st.selectbox("🔑 Selecciona el Usuario a Editar (Búsqueda por Nombre o Folio):", list(dict_todos.keys()))
                pac_id_editar = dict_todos[pac_sel_key]
                datos_editar = obtener_paciente(pac_id_editar)
                st.info(f"📌 Editando información de **{datos_editar['nombre_completo']}** (Folio: `{datos_editar['paciente_id']}`)")
                
        # Formulario
        with st.form("form_registro_usuario"):
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                if modo_usuario == "✏️ Modificar / Editar Usuario Existente" and datos_editar:
                    reg_folio = st.text_input("🔑 FOLIO / ID DE USUARIO", value=datos_editar['paciente_id'], disabled=True)
                else:
                    folio_sugerido = generar_siguiente_folio()
                    reg_folio = st.text_input("🔑 FOLIO / ID DE USUARIO (Sugerido auto-incrementable)", value=folio_sugerido).strip()
                    
                reg_nombre = st.text_input("👤 Nombre Completo *", value=datos_editar['nombre_completo'] if datos_editar else "").strip()
                reg_tipo = st.selectbox("🏷️ Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if (not datos_editar or datos_editar['tipo_usuario'] == "Paciente") else 1)
                
            with c_f2:
                def_f_ing = datetime.strptime(datos_editar['fecha_ingreso'], "%Y-%m-%d").date() if datos_editar else date.today()
                def_f_nac = datetime.strptime(datos_editar['fecha_nacimiento'], "%Y-%m-%d").date() if datos_editar else date(1990, 1, 1)
                
                reg_f_ingreso = st.date_input("📅 Fecha de Ingreso a la Comunidad", value=def_f_ing)
                reg_f_nacimiento = st.date_input("🎂 Fecha de Nacimiento", value=def_f_nac, min_value=date(1920, 1, 1), max_value=date.today())
                
                idx_sexo = ["Masculino", "Femenino", "Otro"].index(datos_editar['sexo']) if (datos_editar and datos_editar['sexo'] in ["Masculino", "Femenino", "Otro"]) else 0
                reg_sexo = st.selectbox("👫 Sexo", ["Masculino", "Femenino", "Otro"], index=idx_sexo)
                
                idx_estatus = ["A (Activo)", "B (Bloqueado)"].index("A (Activo)" if (not datos_editar or datos_editar['estatus'] == "A") else "B (Bloqueado)")
                reg_estatus_sel = st.selectbox("🔒 Estatus en el Sistema", ["A (Activo)", "B (Bloqueado)"], index=idx_estatus)
                reg_estatus = "A" if reg_estatus_sel.startswith("A") else "B"

            btn_guardar_usr = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True)
            
            if btn_guardar_usr:
                if not reg_folio or not reg_nombre:
                    st.error("⚠️ El Folio y Nombre Completo son obligatorios.")
                else:
                    dup = buscar_paciente_por_nombre(reg_nombre)
                    if dup and dup[0] != reg_folio and modo_usuario == "🆕 Registrar Nuevo Usuario":
                        st.error(f"❌ Imposible registrar: Ya existe un usuario registrado con el nombre '{dup[1]}' bajo el Folio {dup[0]} (Estatus actual: {'Activo' if dup[2] == 'A' else 'Bloqueado'}).")
                    else:
                        guardar_o_actualizar_paciente(
                            paciente_id=reg_folio,
                            nombre_completo=reg_nombre,
                            tipo_usuario=reg_tipo,
                            fecha_ingreso=reg_f_ingreso.strftime("%Y-%m-%d"),
                            fecha_nacimiento=reg_f_nacimiento.strftime("%Y-%m-%d"),
                            sexo=reg_sexo,
                            estatus=reg_estatus,
                            usuario=st.session_state["username"]
                        )
                        st.success(f"✅ ¡Usuario {reg_nombre} ({reg_folio}) guardado exitosamente!")
                        st.rerun()

        st.divider()
        st.subheader("📋 Directorio General de Usuarios Registrados")
        
        tab_act, tab_bloq = st.tabs(["🟢 Usuarios Activos ('A')", "🔒 Usuarios Bloqueados ('B')"])
        
        with tab_act:
            activos = listar_pacientes_registro(solo_activos=True)
            if not activos:
                st.info("No hay usuarios activos registrados.")
            else:
                for a in activos:
                    pid, pnom, ptipo, pfing, pfnac, psex, pest, petapa, hm_id, fsuelta = a
                    with st.expander(f"👤 **{pnom}** (Folio: `{pid}`) | Tipo: {ptipo} | Etapa: {petapa}"):
                        c_a1, c_a2 = st.columns([3, 1])
                        with c_a1:
                            st.write(f"**Fecha de Ingreso:** {pfing} | **Fecha Nacimiento:** {pfnac} | **Sexo:** {psex}")
                            if ptipo == "Paciente":
                                st.write(f"**Etapa Actual:** {petapa}")
                        with c_a2:
                            if st.button("🔒 Bloquear Usuario", key=f"bloq_{pid}"):
                                cambiar_estatus_paciente(pid, "B")
                                st.success(f"Usuario {pid} bloqueado.")
                                st.rerun()
                                
        with tab_bloq:
            bloqueados = [p for p in todos_registrados if p[6] == "B"]
            if not bloqueados:
                st.info("No hay usuarios bloqueados.")
            else:
                for b in bloqueados:
                    pid, pnom, ptipo, pfing, pfnac, psex, pest, petapa, hm_id, fsuelta = b
                    with st.expander(f"🔒 **{pnom}** (Folio: `{pid}`) | Status: BLOQUEADO"):
                        c_b1, c_b2 = st.columns([3, 1])
                        with c_b1:
                            st.write(f"**Fecha de Ingreso:** {pfing} | **Fecha Nacimiento:** {pfnac} | **Sexo:** {psex}")
                        with c_b2:
                            if st.button("🟢 Desbloquear / Reactivar", key=f"act_{pid}"):
                                cambiar_estatus_paciente(pid, "A")
                                st.success(f"Usuario {pid} reactivado.")
                                st.rerun()

    # =========================================================================
    # 2. MÓDULO: GESTIÓN DE ETAPAS & PROCESO
    # =========================================================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso de Pacientes")
        st.caption("Seguimiento individual de las 5 etapas del tratamiento (7 meses) en Sawabona Shikoba")
        
        pacientes_activos = listar_pacientes_registro(solo_activos=True, tipo_filtro="Paciente")
        if not pacientes_activos:
            st.warning("⚠️ No hay pacientes con tipo 'Paciente' registrados y activos. Por favor registre uno en 'Registro de Usuarios'.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]} (Etapa: {p[7]})": p[0] for p in pacientes_activos}
            pac_sel_k = st.selectbox("🔑 Selecciona el Paciente:", list(dict_pacientes.keys()))
            pac_id_e = dict_pacientes[pac_sel_k]
            
            pac_data = obtener_paciente(pac_id_e)
            
            f_ing_dt = datetime.strptime(pac_data['fecha_ingreso'], "%Y-%m-%d").date()
            dias_totales_estancia = (date.today() - f_ing_dt).days
            
            st.markdown(f"""
            ### 👤 **{pac_data['nombre_completo']}** (`{pac_data['paciente_id']}`)
            * **Fecha de Ingreso:** {pac_data['fecha_ingreso']} (**{dias_totales_estancia} días transcurridos**)
            * **Etapa Actual:** `{pac_data['etapa_actual']}` | Duración de Etapa: **{DURACION_ETAPAS.get(pac_data['etapa_actual'], 30)} días**
            """)
            
            duracion_req = DURACION_ETAPAS.get(pac_data['etapa_actual'], 30)
            pct_dias = min(1.0, max(0.0, dias_totales_estancia / float(duracion_req)))
            st.progress(pct_dias, text=f"Progreso de tiempo en etapa {pac_data['etapa_actual']}: {dias_totales_estancia} de {duracion_req} días ({int(pct_dias*100)}%)")
            
            dias_restantes = duracion_req - dias_totales_estancia
            if 0 <= dias_restantes <= 5:
                st.warning(f"🚨 **¡ALERTA DE CUMPLIMIENTO DE ETAPA!** Al paciente le quedan **{dias_restantes} días** para cumplir su tiempo en la etapa `{pac_data['etapa_actual']}`. Verifique su checklist para solicitar cambio de etapa.")
            elif dias_restantes < 0:
                st.info(f"⏰ El paciente ha superado por {abs(dias_restantes)} días el tiempo establecido para su etapa `{pac_data['etapa_actual']}`.")

            st.divider()
            
            tab_check, tab_hm, tab_hist = st.tabs(["📋 Checklist de Requisitos", "🤝 Control Hermano Menor / Mayor", "📜 Historial de Cambios de Etapa"])
            
            with tab_check:
                st.subheader(f"Checklist de Requisitos para Etapa: `{pac_data['etapa_actual']}`")
                reqs = obtener_requisitos_etapa(pac_data['etapa_actual'])
                estados_m = obtener_checklist_manual_estado(pac_id_e)
                
                completados_totales = 0
                total_requisitos = len(reqs)
                
                for r in reqs:
                    rid, rnom, rtipo = r
                    if rtipo == "Manual":
                        ch = st.checkbox(f"📌 {rnom}", value=bool(estados_m.get(rid, 0)), key=f"chk_m_{pac_id_e}_{rid}")
                        if ch != bool(estados_m.get(rid, 0)):
                            actualizar_checklist_manual_estado(pac_id_e, rid, 1 if ch else 0)
                            st.rerun()
                        if ch:
                            completados_totales += 1
                    elif rtipo == "Grupo":
                        tipo_g = "Terapia de Grupo" if "Terapia de Grupo" in rnom else ("Aquí y Ahora" if "Aquí y Ahora" in rnom else "Feedback")
                        meta_g = 4 if "4 Grupos" in rnom else (2 if "2 Grupos" in rnom else 1)
                        actuales_g = contar_grupos_paciente_etapa(pac_id_e, pac_data['etapa_actual'], tipo_g)
                        
                        g_ok = actuales_g >= meta_g
                        st.markdown(f"{'✅' if g_ok else '⏳'} **{rnom}**: `{actuales_g} de {meta_g} registrados` {'(Completado)' if g_ok else '(Pendiente)'}")
                        if g_ok:
                            completados_totales += 1
                            
                st.divider()
                st.write(f"**Requisitos Completados:** `{completados_totales} de {total_requisitos}`")
                
                todo_listo = (completados_totales == total_requisitos) and (total_requisitos > 0)
                
                if todo_listo:
                    st.success("🎉 ¡El paciente ha cumplido con el 100% de los requisitos de esta etapa!")
                    if st.button("🚀 Promover a Siguiente Etapa", use_container_width=True):
                        ok, msg = promover_etapa_paciente(pac_id_e, st.session_state["username"])
                        if ok:
                            st.success(f"✅ ¡El paciente ha sido promovido a la etapa de {msg}!")
                            st.rerun()
                        else:
                            st.error(f"Error: {msg}")
                else:
                    st.button("🚀 Promover a Siguiente Etapa", disabled=True, use_container_width=True, help="Complete todos los requisitos del checklist para inhabilitar el bloqueo.")

            with tab_hm:
                st.subheader("🤝 Control de Acompañamiento (Hermano Menor & Mayor)")
                if pac_data['etapa_actual'] == "ACOGIDA":
                    st.info("ℹ️ En la etapa de **ACOGIDA**, los primeros 15 días el paciente cuenta con el acompañamiento de un Hermano Mayor.")
                    
                    c_hm1, c_hm2 = st.columns(2)
                    with c_hm1:
                        st.write(f"**Hermano Menor:** {pac_data['nombre_completo']}")
                        
                        posibles_hm = [p for p in listar_pacientes_registro(solo_activos=True) if p[0] != pac_id_e]
                        dict_hm = {f"{p[0]} - {p[1]} ({p[2]} | {p[7]})": p[0] for p in posibles_hm}
                        
                        hm_actual = pac_data['hermano_mayor_id']
                        idx_hm = 0
                        if hm_actual:
                            for i, k in enumerate(dict_hm.keys()):
                                if dict_hm[k] == hm_actual:
                                    idx_hm = i
                                    break
                                    
                        hm_sel_k = st.selectbox("Seleccionar Hermano Mayor:", list(dict_hm.keys()) if dict_hm else ["Sin opciones"], index=idx_hm)
                        if st.button("💾 Asignar Hermano Mayor"):
                            if dict_hm:
                                asignar_hermano_mayor(pac_id_e, dict_hm[hm_sel_k])
                                st.success("Hermano Mayor asignado.")
                                st.rerun()
                                
                    with c_hm2:
                        st.write(f"**Fecha de Suelta Programada (Día 15):** {(f_ing_dt + timedelta(days=15)).strftime('%Y-%m-%d')}")
                        if pac_data['fecha_suelta']:
                            st.success(f"✅ Hermano mayor lo soltó el: `{pac_data['fecha_suelta']}`")
                        else:
                            st.warning("⏳ Pendiente de suelta.")
                            if st.button("🔓 Marcar que Hermano Mayor lo Suelta"):
                                marcar_suelta_hermano_mayor(pac_id_e)
                                st.success("Fecha de suelta registrada.")
                                st.rerun()
                else:
                    st.write(f"El paciente ya superó la etapa de Acogida. Etapa actual: `{pac_data['etapa_actual']}`.")

            with tab_hist:
                st.subheader("📜 Historial de Cambios de Etapa")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT etapa_origen, etapa_destino, fecha_cambio, usuario_autorizo FROM historial_etapas WHERE paciente_id = ? ORDER BY id DESC', (pac_id_e,))
                hist = c.fetchall()
                conn.close()
                if not hist:
                    st.info("Sin registros de promociones de etapa anteriores.")
                else:
                    for h in hist:
                        st.write(f"🟢 **{h[0]} ➔ {h[1]}** | Fecha: `{h[2]}` | Autorizó: `{h[3]}`")

    # =========================================================================
    # 3. MÓDULO: GRUPOS TERAPÉUTICOS
    # =========================================================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro y Expediente de Grupos Terapéuticos")
        st.caption("Captura individual de Terapia de Grupo, Aquí y Ahora y Feedbacks")
        
        pacientes_activos = listar_pacientes_registro(solo_activos=True, tipo_filtro="Paciente")
        if not pacientes_activos:
            st.warning("⚠️ No hay pacientes activos registrados.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]} (Etapa: {p[7]})": p[0] for p in pacientes_activos}
            
            tab_cap, tab_res, tab_pdf = st.tabs(["📝 Capturar Grupo", "📊 Resumen de Grupos Completados", "🖨️ Expediente PDF"])
            
            with tab_cap:
                pac_sel_k = st.selectbox("🔑 Selecciona el Paciente:", list(dict_pacientes.keys()), key="grp_p_sel")
                pac_id_g = dict_pacientes[pac_sel_k]
                pac_g_data = obtener_paciente(pac_id_g)
                
                tipo_g_sel = st.selectbox("🗣️ Tipo de Grupo Terapéutico:", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"])
                
                with st.form("form_grupo_terapeutico"):
                    st.write(f"**Paciente:** `{pac_g_data['nombre_completo']}` | **Etapa:** `{pac_g_data['etapa_actual']}`")
                    c_g1, c_g2 = st.columns(2)
                    with c_g1:
                        f_grupo = st.date_input("📅 Fecha del Grupo", value=date.today())
                    with c_g2:
                        facil_grupo = st.text_input("👤 Nombre del Facilitador", value=st.session_state["nombre_completo"]).strip()
                        
                    if tipo_g_sel in ["Terapia de Grupo", "Aquí y Ahora"]:
                        comp_g = st.text_area("💬 Compartimiento (Texto largo)")
                        obs_g = st.text_area("🔍 Observaciones (Texto largo)")
                        dev_g = st.text_area("🔄 Devoluciones (Texto largo)")
                        logros_g, dific_g = "", ""
                    else:
                        logros_g = st.text_area("🌟 Logros (Texto largo)")
                        dific_g = st.text_area("⚠️ Dificultades (Texto largo)")
                        obs_g = st.text_area("🔍 Observaciones (Texto largo)")
                        dev_g = st.text_area("🔄 Devoluciones (Texto largo)")
                        comp_g = ""
                        
                    queda_g = st.text_area("🌱 ¿Cómo se queda y a qué se compromete?")
                    
                    btn_g = st.form_submit_button("💾 Registrar Sesión de Grupo", use_container_width=True)
                    if btn_g:
                        if not facil_grupo:
                            st.error("El nombre del facilitador es obligatorio.")
                        else:
                            guardar_grupo_terapeutico(
                                paciente_id=pac_id_g,
                                tipo_grupo=tipo_g_sel,
                                fecha=f_grupo.strftime("%Y-%m-%d"),
                                etapa_actual=pac_g_data['etapa_actual'],
                                compartimiento=comp_g,
                                observaciones=obs_g,
                                devoluciones=dev_g,
                                como_se_queda=queda_g,
                                logros=logros_g,
                                dificultades=dific_g,
                                facilitador=facil_grupo,
                                usuario=st.session_state["username"]
                            )
                            st.success(f"✅ Sesión de {tipo_g_sel} registrada correctamente para {pac_g_data['nombre_completo']}.")
                            st.rerun()

            with tab_res:
                st.subheader("📊 Avance General de Grupos Terapéuticos por Usuario")
                res_data = []
                for p in pacientes_activos:
                    pid, pnom, ptipo, pfing, pfnac, psex, pest, petapa, hm_id, fsuelta = p
                    c_tg = contar_grupos_paciente_etapa(pid, petapa, "Terapia de Grupo")
                    c_aa = contar_grupos_paciente_etapa(pid, petapa, "Aquí y Ahora")
                    c_fb = contar_grupos_paciente_etapa(pid, petapa, "Feedback")
                    
                    res_data.append({
                        "Folio": pid,
                        "Nombre": pnom,
                        "Etapa": petapa,
                        "Terapia de Grupo": f"{c_tg} completados",
                        "Aquí y Ahora": f"{c_aa} completados",
                        "Feedbacks": f"{c_fb} completados"
                    })
                st.dataframe(res_data, use_container_width=True)

            with tab_pdf:
                pac_sel_pdf = st.selectbox("🔑 Selecciona el Paciente para Exportar Expediente:", list(dict_pacientes.keys()), key="pdf_p_sel")
                pac_id_pdf = dict_pacientes[pac_sel_pdf]
                
                grupos_pac = listar_grupos_paciente(pac_id_pdf)
                st.write(f"Total de sesiones registradas: **{len(grupos_pac)}**")
                
                if st.button("🖨️ Generar Expediente de Grupos Terapéuticos en PDF"):
                    pdf_g_fname = generar_pdf_grupos_paciente(pac_id_pdf)
                    with open(pdf_g_fname, "rb") as f:
                        st.download_button(
                            label="⬇️ Descargar Expediente de Grupos (PDF)",
                            data=f,
                            file_name=pdf_g_fname,
                            mime="application/pdf"
                        )
                        
                st.divider()
                st.subheader("🔍 Historial de Sesiones Registradas")
                for g in grupos_pac:
                    gid, gtipo, gfec, getap, gcomp, gobs, gdev, gqueda, glog, gdif, gfac, gusr = g
                    with st.expander(f"[{gfec}] **{gtipo}** (Etapa: {getap}) - Facilitador: {gfac}"):
                        if gcomp: st.write(f"**Compartimiento:** {gcomp}")
                        if glog: st.write(f"**Logros:** {glog}")
                        if gdif: st.write(f"**Dificultades:** {gdif}")
                        if gobs: st.write(f"**Observaciones:** {gobs}")
                        if gdev: st.write(f"**Devoluciones:** {gdev}")
                        if gqueda: st.write(f"**Cómo se queda / Compromiso:** {gqueda}")
                        
                        if st.button("🗑️ Eliminar Sesión", key=f"del_g_{gid}"):
                            eliminar_grupo_terapeutico(gid)
                            st.success("Sesión eliminada.")
                            st.rerun()

    # =========================================================================
    # 4. MÓDULO: NUEVA ENTREVISTA / EDITAR
    # =========================================================================
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        pacientes_activos = listar_pacientes_registro(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ Primero debe dar de alta al usuario en el módulo 'Registro de Usuarios'.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]} (Ingreso: {p[3]})": p[0] for p in pacientes_activos}
            paciente_sel_key = st.selectbox("🔑 SELECCIONE EL PACIENTE REGISTRADO *", list(dict_pacientes.keys()))
            paciente_id_input = dict_pacientes[paciente_sel_key]
            
            pac_info = obtener_paciente(paciente_id_input)
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            datos_existentes = datos_cargados if datos_cargados else {}
            
            st.info(f"👤 **Paciente:** `{pac_info['nombre_completo']}` | **Folio:** `{pac_info['paciente_id']}` | **F. Ingreso:** `{pac_info['fecha_ingreso']}` | **F. Nac:** `{pac_info['fecha_nacimiento']}` | **Sexo:** `{pac_info['sexo']}`")

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
                        dependientes_quienes = st.text_input("¿Quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
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
                        
                        with col_a: c_val = st.checkbox("Consume", value=s_data.get("consumo") == "SÍ", key=f"c_{sust}")
                        with col_b: forma_val = st.text_input("Forma", value=s_data.get("forma", ""), key=f"forma_{sust}")
                        with col_c: frec_val = st.text_input("Frecuencia", value=s_data.get("frecuencia", ""), key=f"frec_{sust}")
                        with col_d: cant_val = st.text_input("Cantidad", value=s_data.get("cantidad", ""), key=f"cant_{sust}")
                        with col_e: edad_val = st.text_input("Edad Inicio", value=s_data.get("edad_inicio", ""), key=f"edad_{sust}")
                        with col_f: lugar_val = st.text_input("Lugar", value=s_data.get("lugar", ""), key=f"lugar_{sust}")
                            
                        tabla_consumo_input[sust] = {
                            "consumo": "SÍ" if c_val else "NO",
                            "forma": forma_val, "frecuencia": frec_val,
                            "cantidad": cant_val, "edad_inicio": edad_val, "lugar": lugar_val
                        }
                        st.divider()

                    col_imp1, col_imp2, col_imp3 = st.columns(3)
                    with col_imp1: sustancia_impacto = st.text_input("Sustancia de Impacto Principal", value=datos_existentes.get("sustancia_impacto", ""))
                    with col_imp2: tiempo_excesivo = st.text_input("¿Desde hace cuánto consume de forma excesiva?", value=datos_existentes.get("tiempo_excesivo", ""))
                    with col_imp3: modo_consumo = st.selectbox("Normalmente consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"], index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

                with tab3:
                    st.subheader("Evaluación de la Disposición al Cambio")
                    abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado", value=datos_existentes.get("abst_mayor_tiempo", ""))
                    abst_fecha = st.text_input("¿Cuándo ocurrió?", value=datos_existentes.get("abst_fecha", ""))
                    abst_motivo = st.text_area("Motivo / Estrategia", value=datos_existentes.get("abst_motivo", ""))
                    importancia_options = ["1. NADA IMPORTANTE", "2. POCO IMPORTANTE", "3. ALGO IMPORTANTE", "4. IMPORTANTE", "5. MUY IMPORTANTE"]
                    imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                    imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                    importancia_cambio = st.select_slider("Importancia de dejar de consumir", options=importancia_options, value=importancia_options[imp_index])

                with tab4:
                    st.subheader("Situación Social-Familiar")
                    familia_integrantes = st.text_area("Integrantes de la familia con mayor contacto", value=datos_existentes.get("familia_integrantes", ""))
                    relaciones_post_consumo = st.selectbox("¿Relaciones sexuales tras consumir?", ["NO", "SÍ"], index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                    abuso_flag = st.selectbox("¿Involucrado en abuso físico/sexual?", ["NO", "SÍ"], index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

                with tab5:
                    st.subheader("Evaluación Clínica y Cierre")
                    problemas_sesion = st.text_area("Problemas presentados durante la sesión", value=datos_existentes.get("problemas_sesion", ""))
                    observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                    c_f1, c_f2 = st.columns(2)
                    with c_f1: evaluador_nombre = st.text_input("Nombre de quien aplica", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                    with c_f2: evaluador_cargo = st.text_input("Cargo", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

                guardar_btn = st.form_submit_button("💾 Guardar Expediente de Paciente", use_container_width=True)
                
                if guardar_btn:
                    datos_completos = {
                        "dependientes_flag": dependientes_flag, "dependientes_quienes": dependientes_quienes,
                        "pareja_flag": pareja_flag, "pareja_tiempo": pareja_tiempo,
                        "tabla_consumo": tabla_consumo_input, "sustancia_impacto": sustancia_impacto,
                        "tiempo_excesivo": tiempo_excesivo, "modo_consumo": modo_consumo,
                        "abst_mayor_tiempo": abst_mayor_tiempo, "abst_fecha": abst_fecha,
                        "abst_motivo": abst_motivo, "importancia_cambio": importancia_cambio,
                        "familia_integrantes": familia_integrantes, "relaciones_post_consumo": relaciones_post_consumo,
                        "abuso_flag": abuso_flag, "problemas_sesion": problemas_sesion,
                        "observaciones": observaciones, "evaluador_nombre": evaluador_nombre,
                        "evaluador_cargo": evaluador_cargo
                    }
                    guardar_entrevista(paciente_id_input, datos_completos, st.session_state["username"])
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente!")

    # =========================================================================
    # 5. MÓDULO: BUSCAR Y LISTAR PACIENTES
    # =========================================================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro de Expedientes y Pacientes")
        
        filtro_status = st.radio("Filtrar por estatus:", ["🟢 Activos", "🔒 Bloqueados / Histórico"], horizontal=True)
        solo_activos = (filtro_status == "🟢 Activos")
        
        pacientes = listar_pacientes_registro(solo_activos=solo_activos)
        if not pacientes:
            st.warning("No hay registros en esta categoría.")
        else:
            st.subheader(f"Total de registros: {len(pacientes)}")
            for pac in pacientes:
                pid, pnom, ptipo, pfing, pfnac, psex, pest, petapa, hm_id, fsuelta = pac
                with st.expander(f"👤 **{pnom}** (Folio: `{pid}`) | Tipo: {ptipo} | Etapa: {petapa}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.write(f"**Fecha de Ingreso:** {pfing} | **Fecha Nacimiento:** {pfnac} | **Sexo:** {psex}")
                        st.write(f"**Estatus:** {'🟢 Activo' if pest == 'A' else '🔒 Bloqueado'}")
                    with c_det2:
                        datos_p, _, _, _ = obtener_entrevista(pid)
                        if datos_p:
                            pdf_file = generar_pdf_entrevista(pid, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar PDF Entrevista",
                                    data=f,
                                    file_name=f"Entrevista_{pid}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_e_{pid}"
                                )
                        else:
                            st.caption("Sin entrevista realizada.")

    # =========================================================================
    # 6. MÓDULO: CONTROL DE MEDICAMENTOS Y DOSIS
    # =========================================================================
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control de Medicamentos y Dosificación Diaria")
        st.caption("Captura de dosis por horario (mañana, tarde, noche) e inventario por paciente")
        
        st.subheader("🖨️ Lista General de Medicamentos y Dosis")
        if st.button("📄 Imprimir Lista General en PDF (Orden Alfabético)"):
            pdf_gen_fname = generar_pdf_lista_general_meds()
            with open(pdf_gen_fname, "rb") as f:
                st.download_button(
                    label="⬇️ Descargar PDF Lista General",
                    data=f,
                    file_name=pdf_gen_fname,
                    mime="application/pdf"
                )
        st.divider()

        pacientes_activos = listar_pacientes_registro(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ Debe registrar usuarios en el módulo 'Registro de Usuarios'.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]}": p[0] for p in pacientes_activos}
            paciente_med_sel = st.selectbox("🔑 SELECCIONE EL PACIENTE *", list(dict_pacientes.keys()), key="med_p_sel")
            paciente_med_id = dict_pacientes[paciente_med_sel]
            
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            
            if "meds_temp_list" not in st.session_state or st.session_state.get("current_med_pac") != paciente_med_id:
                st.session_state["meds_temp_list"] = meds_cargados if meds_cargados else []
                st.session_state["current_med_pac"] = paciente_med_id

            st.subheader(f"Esquema para: {paciente_med_sel}")
            
            with st.form("form_captura_meds"):
                observaciones_meds = st.text_area("📝 Observaciones Generales / Alergias Medicamentosas", value=obs_cargadas)
                st.markdown("#### Lista de Medicamentos")
                
                num_meds = len(st.session_state["meds_temp_list"])
                meds_nuevos_inputs = []
                
                for i in range(max(1, num_meds)):
                    m_data = st.session_state["meds_temp_list"][i] if i < num_meds else {}
                    st.markdown(f"**Medicamento #{i+1}**")
                    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([2, 1, 1, 1, 1, 2])
                    
                    with col_m1: m_nombre = st.text_input("Nombre / Presentación", value=m_data.get("nombre", ""), key=f"mnom_{i}")
                    with col_m2: m_manana = st.number_input("☀️ Mañana", min_value=0, value=int(m_data.get("dosis_manana", 0)), key=f"mman_{i}")
                    with col_m3: m_tarde = st.number_input("🌤️ Tarde", min_value=0, value=int(m_data.get("dosis_tarde", 0)), key=f"mtar_{i}")
                    with col_m4: m_noche = st.number_input("🌙 Noche", min_value=0, value=int(m_data.get("dosis_noche", 0)), key=f"mnoc_{i}")
                    with col_m5: m_exist = st.number_input("📦 Existencia", min_value=0, value=int(m_data.get("existencia", 0)), key=f"mexi_{i}")
                    with col_m6: m_indic = st.text_input("Indicaciones", value=m_data.get("indicaciones", ""), key=f"mind_{i}")
                    
                    if m_nombre.strip():
                        meds_nuevos_inputs.append({
                            "nombre": m_nombre.strip(),
                            "dosis_manana": m_manana,
                            "dosis_tarde": m_tarde,
                            "dosis_noche": m_noche,
                            "existencia": m_exist,
                            "indicaciones": m_indic.strip()
                        })
                    st.divider()

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    btn_add_med = st.form_submit_button("➕ Agregar otro medicamento")
                with col_btn2:
                    btn_save_meds = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)

                if btn_add_med:
                    st.session_state["meds_temp_list"].append({"nombre": "", "dosis_manana": 0, "dosis_tarde": 0, "dosis_noche": 0, "existencia": 0, "indicaciones": ""})
                    st.rerun()

                if btn_save_meds:
                    guardar_medicamentos(paciente_med_id, meds_nuevos_inputs, observaciones_meds, st.session_state["username"])
                    st.session_state["meds_temp_list"] = meds_nuevos_inputs
                    st.success("✅ Esquema de medicamentos guardado exitosamente.")
                    st.rerun()

    # =========================================================================
    # 7. MÓDULO: ENTREGA DE MEDICAMENTOS
    # =========================================================================
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega Diaria de Medicamentos")
        st.caption("Registro de dispensación y descuento automático del inventario")
        
        pacientes_activos = listar_pacientes_registro(solo_activos=True)
        if not pacientes_activos:
            st.warning("⚠️ No hay usuarios activos registrados.")
        else:
            dict_pacientes = {f"{p[0]} - {p[1]}": p[0] for p in pacientes_activos}
            pac_ent_sel = st.selectbox("🔑 SELECCIONE EL PACIENTE *", list(dict_pacientes.keys()), key="ent_p_sel")
            pac_ent_id = dict_pacientes[pac_ent_sel]
            
            meds_disp, obs_d, f_r, f_m, u_r = obtener_medicamentos(pac_ent_id)
            meds_con_stock = [m for m in meds_disp if int(m.get("existencia", 0)) > 0]
            
            if not meds_con_stock:
                st.warning(f"⚠️ El paciente {pac_ent_sel} no tiene medicamentos con existencia disponible para entregar. Por favor reabastezca en 'Control de Medicamentos'.")
            else:
                st.info(f"📦 Medicamentos disponibles para entrega de **{pac_ent_sel}**:")
                
                if "pdf_entrega_generado" not in st.session_state:
                    st.session_state["pdf_entrega_generado"] = None

                with st.form("form_entrega_meds"):
                    entregas_input = []
                    for i, m in enumerate(meds_con_stock):
                        nom_m = m['nombre']
                        exis_m = int(m.get('existencia', 0))
                        dosis_diaria = int(m.get('dosis_manana', 0)) + int(m.get('dosis_tarde', 0)) + int(m.get('dosis_noche', 0))
                        def_entregarse = min(exis_m, max(1, dosis_diaria))
                        
                        col_e1, col_e2, col_e3, col_e4 = st.columns([2, 1, 1, 1])
                        with col_e1: st.write(f"💊 **{nom_m}**")
                        with col_e2: st.write(f"Stock: `{exis_m}`")
                        with col_e3: st.write(f"Dosis diaria: `{dosis_diaria}`")
                        with col_e4:
                            cant_e = st.number_input("Cantidad a entregar", min_value=1, max_value=exis_m, value=def_entregarse, key=f"e_cant_{i}")
                            entregas_input.append({"nombre": nom_m, "cantidad": cant_e})
                        st.divider()

                    btn_confirmar_entrega = st.form_submit_button("📦 Registrar Entrega y Descontar de Existencia", use_container_width=True)
                    if btn_confirmar_entrega:
                        registrar_entrega_meds(pac_ent_id, entregas_input, st.session_state["username"])
                        pdf_e_name = generar_pdf_comprobante_entrega(pac_ent_id, entregas_input, st.session_state["username"])
                        st.session_state["pdf_entrega_generado"] = pdf_e_name
                        st.success("✅ Entrega registrada correctamente. Inventario actualizado.")
                        
                if st.session_state["pdf_entrega_generado"]:
                    with open(st.session_state["pdf_entrega_generado"], "rb") as f:
                        st.download_button(
                            label="🖨️ Descargar Comprobante de Entrega (PDF)",
                            data=f,
                            file_name=st.session_state["pdf_entrega_generado"],
                            mime="application/pdf"
                        )

    # =========================================================================
    # 8. MÓDULO: ALERTAS Y COMPRAS
    # =========================================================================
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Alertas de Existencia e Inventario de Farmacia")
        st.caption("Control consolidado de reabastecimiento para la comunidad")
        
        todos_meds = []
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            SELECT p.paciente_id, p.nombre_completo, m.meds_json
            FROM pacientes_registro p
            JOIN medicamentos m ON p.paciente_id = m.paciente_id
            WHERE p.estatus = 'A'
        ''')
        rows = c.fetchall()
        conn.close()
        
        criticos = []
        preventivos = []
        
        for r in rows:
            p_id, p_nom, m_json = r
            m_list = json.loads(m_json) if m_json else []
            for m in m_list:
                exis = int(m.get("existencia", 0))
                dosis_d = int(m.get("dosis_manana", 0)) + int(m.get("dosis_tarde", 0)) + int(m.get("dosis_noche", 0))
                if dosis_d > 0:
                    dias_cobertura = exis / float(dosis_d)
                    item = {
                        "paciente": p_nom,
                        "folio": p_id,
                        "medicamento": m.get("nombre"),
                        "existencia": exis,
                        "dosis_diaria": dosis_d,
                        "sugerido_comprar": max(30, dosis_d * 30 - exis)
                    }
                    if dias_cobertura < 1.0:
                        criticos.append(item)
                    elif dias_cobertura < 3.0:
                        preventivos.append(item)
                        
        c_m1, c_m2 = st.columns(2)
        with c_m1: st.metric("🔴 Alertas Críticas (< 1 día de stock)", len(criticos))
        with c_m2: st.metric("🟡 Alertas Preventivas (< 3 días de stock)", len(preventivos))
        
        st.divider()
        st.subheader("🛒 Lista de Medicamentos Urgentes a Comprar")
        
        items_compras = criticos + preventivos
        if not items_compras:
            st.success("🎉 ¡Excelente! Todos los medicamentos de los pacientes activos tienen stock suficiente.")
        else:
            st.dataframe(items_compras, use_container_width=True)

    # =========================================================================
    # 9. MÓDULO: CONFIGURACIÓN Y SEGURIDAD
    # =========================================================================
    elif menu == "⚙️ Configuración del Sistema":
        st.title("⚙️ Configuración y Administración")
        
        tab_req, tab_pass = st.tabs(["📝 Administración de Requisitos por Etapa", "🔐 Cambiar Contraseña"])
        
        with tab_req:
            st.subheader("Configuración Dinámica de Requisitos")
            etapa_cfg = st.selectbox("Selecciona la Etapa a Configurar:", ORDEN_ETAPAS)
            
            reqs_curr = obtener_requisitos_etapa(etapa_cfg)
            st.write(f"Requisitos actuales para **{etapa_cfg}**:")
            for r in reqs_curr:
                rid, rnom, rtipo = r
                col_r1, col_r2 = st.columns([3, 1])
                with col_r1: st.write(f"• **{rnom}** (`Tipo: {rtipo}`)")
                with col_r2:
                    if st.button("🗑️ Eliminar Requisito", key=f"del_req_{rid}"):
                        eliminar_requisito_custom(rid)
                        st.success("Requisito eliminado.")
                        st.rerun()
                        
            st.divider()
            st.subheader("➕ Agregar Nuevo Requisito a esta Etapa")
            with st.form("form_add_req"):
                nuevo_rnom = st.text_input("Nombre del Requisito *").strip()
                nuevo_rtipo = st.selectbox("Tipo de Verificación", ["Manual", "Grupo"])
                btn_add_r = st.form_submit_button("Guardar Requisito", use_container_width=True)
                if btn_add_r:
                    if not nuevo_rnom:
                        st.error("El nombre del requisito es obligatorio.")
                    else:
                        agregar_requisito_custom(etapa_cfg, nuevo_rnom, nuevo_rtipo)
                        st.success("Requisito agregado exitosamente.")
                        st.rerun()

        with tab_pass:
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

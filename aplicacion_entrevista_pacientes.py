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
    
    # 1. Tabla de Usuarios Administrativos / Personal (Login y Roles)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    ''')
    
    # 2. Tabla de Pacientes / Residentes de la Comunidad
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
    
    # 5. Tabla de Historial de Entregas de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            fecha_entrega TEXT,
            entregado_por TEXT,
            detalle_json TEXT
        )
    ''')
    
    # 6. Tabla de Grupos Terapéuticos (Terapia de Grupo, Aquí y Ahora, Feedback)
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
    
    # 7. Tabla de Historial de Cambios de Etapa
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
    
    # 8. Tabla de Requisitos por Etapa (Configurable)
    c.execute('''
        CREATE TABLE IF NOT EXISTS requisitos_etapas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            requisito TEXT,
            es_grupo INTEGER DEFAULT 0
        )
    ''')

    # 9. Tabla de Repositorio de Documentos (Archivos PDF, Word, Excel en BLOB)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            mime_type TEXT,
            bytes_blob BLOB,
            descripcion TEXT,
            fecha_subida TEXT,
            usuario_subida TEXT
        )
    ''')

    # 10. Tabla de Catálogo Central de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            fecha_registro TEXT
        )
    ''')
    
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol) 
            VALUES (?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    
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
        
    # Poblar Catálogo Inicial de Medicamentos si está vacío
    c.execute('SELECT COUNT(*) FROM catalogo_medicamentos')
    if c.fetchone()[0] == 0:
        meds_base = [
            ('PARACETAMOL', 'Comprimidos', '500 mg'),
            ('IBUPROFENO', 'Tabletas', '400 mg'),
            ('OMEPRAZOL', 'Cápsulas', '20 mg'),
            ('CLONAZEPAM', 'Gotas / Tabletas', '2.5 mg/ml'),
            ('VALPROATO DE SODIO', 'Tabletas', '500 mg'),
            ('SERTRALINA', 'Tabletas', '50 mg'),
            ('QUETIAPINA', 'Tabletas', '100 mg'),
            ('RISPERIDONA', 'Tabletas', '2 mg')
        ]
        f_reg = datetime.now().strftime("%Y-%m-%d")
        for m_nom, m_pres, m_conc in meds_base:
            c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
                      (m_nom, m_pres, m_conc, f_reg))

    conn.commit()
    conn.close()

# Ejecutar inicialización inmediatamente al importar/ejecutar el archivo
init_db()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def obtener_todos_usuarios_sistema():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, username, nombre_completo, rol FROM usuarios ORDER BY id ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_usuario_sistema(username, password, nombre_completo, rol):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    pass_h = hash_pass(password)
    c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
              (username, pass_h, nombre_completo, rol))
    conn.commit()
    conn.close()

def actualizar_password_usuario(username, nueva_password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    pass_h = hash_pass(nueva_password)
    c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (pass_h, username))
    conn.commit()
    conn.close()

# --- FUNCIONES REPOSITORIO DE DOCUMENTOS ---
def guardar_documento_repositorio(carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_subida = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, f_subida, usuario))
    conn.commit()
    conn.close()

def obtener_documentos_repositorio(carpeta_filtro="TODAS"):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if carpeta_filtro == "TODAS":
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY id DESC')
    else:
        c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC', (carpeta_filtro,))
    rows = c.fetchall()
    conn.close()
    return rows

def eliminar_documento_repositorio(doc_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM repositorio_documentos WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES CATÁLOGO MEDICAMENTOS ---
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, presentacion, concentracion FROM catalogo_medicamentos ORDER BY nombre ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_medicamento(nombre, presentacion, concentracion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_reg = datetime.now().strftime("%Y-%m-%d")
    c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, fecha_registro) VALUES (?, ?, ?, ?)',
              (nombre.strip().upper(), presentacion, concentracion, f_reg))
    conn.commit()
    conn.close()

# --- FUNCIONES DE PACIENTES ---
def obtener_siguiente_folio():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id LIKE "PAC-%" ORDER BY paciente_id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row:
        try:
            num = int(row[0].split("-")[1]) + 1
            return f"PAC-{num:03d}"
        except:
            pass
    return "PAC-001"

def verificar_duplicado_nombre(nombre, paciente_id_actual=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    nombre_clean = nombre.strip().upper()
    if paciente_id_actual:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE UPPER(TRIM(nombre_completo)) = ? AND paciente_id != ?', (nombre_clean, paciente_id_actual))
    else:
        c.execute('SELECT paciente_id, nombre_completo, estatus FROM pacientes WHERE UPPER(TRIM(nombre_completo)) = ?', (nombre_clean,))
    row = c.fetchone()
    conn.close()
    return row

def guardar_usuario_paciente(paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, usuario):
    init_db()
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
        ''', (nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, f_actual, usuario, paciente_id))
    else:
        c.execute('''
            INSERT INTO pacientes (
                paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus,
                tipo_usuario, etapa_actual, fecha_inicio_etapa, fecha_registro, fecha_modificacion, usuario_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, f_actual, f_actual, usuario))
        
    conn.commit()
    conn.close()

def listar_todos_pacientes():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes ORDER BY nombre_completo ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente_por_id(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, tipo_usuario, etapa_actual, fecha_inicio_etapa, hermano_mayor_id, fecha_suelta_hermano FROM pacientes WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    return row

def asignar_hermano_mayor(paciente_id, hermano_id, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE pacientes SET hermano_mayor_id = ? WHERE paciente_id = ?', (hermano_id, paciente_id))
    conn.commit()
    conn.close()

def registrar_suelta_hermano(paciente_id, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_suelta = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE pacientes SET fecha_suelta_hermano = ? WHERE paciente_id = ?', (f_suelta, paciente_id))
    conn.commit()
    conn.close()

def promover_paciente_etapa(paciente_id, nueva_etapa, etapa_anterior, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_cambio = datetime.now().strftime("%Y-%m-%d")
    
    # Actualizar etapa en tabla paciente
    c.execute('UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?', (nueva_etapa, f_cambio, paciente_id))
    
    # Insertar en historial de etapas
    c.execute('INSERT INTO historial_etapas (paciente_id, etapa_origen, etapa_destino, fecha_cambio, usuario_autoriza) VALUES (?, ?, ?, ?, ?)',
              (paciente_id, etapa_anterior, nueva_etapa, f_cambio, usuario))
              
    conn.commit()
    conn.close()

# --- FUNCIONES DE GRUPOS TERAPÉUTICOS ---
def guardar_grupo_terapeuta(paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('''
        INSERT INTO grupos_terapeutos (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, fecha_registro, usuario_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json, f_reg, usuario))
    
    conn.commit()
    conn.close()

def contar_grupos_paciente_etapa(paciente_id, etapa, tipo_grupo):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM grupos_terapeutos WHERE paciente_id = ? AND etapa_al_momento = ? AND tipo_grupo = ?', (paciente_id, etapa, tipo_grupo))
    cant = c.fetchone()[0]
    conn.close()
    return cant

def obtener_grupos_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, tipo_grupo, etapa_al_momento, fecha_grupo, facilitador, datos_json FROM grupos_terapeutos WHERE paciente_id = ? ORDER BY fecha_grupo DESC, id DESC', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES REQUISITOS DE ETAPAS ---
def obtener_requisitos_etapa(etapa):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, requisito, es_grupo FROM requisitos_etapas WHERE etapa = ? ORDER BY id ASC', (etapa,))
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_requisito_etapa(etapa, requisito, es_grupo=0):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO requisitos_etapas (etapa, requisito, es_grupo) VALUES (?, ?, ?)', (etapa, requisito, es_grupo))
    conn.commit()
    conn.close()

def eliminar_requisito_etapa(req_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM requisitos_etapas WHERE id = ?', (req_id,))
    conn.commit()
    conn.close()

# --- FUNCIONES DE ENTREVISTA ---
def guardar_entrevista(paciente_id, datos, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (f_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)',
                  (paciente_id, f_actual, f_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

# --- FUNCIONES DE MEDICAMENTOS ---
def guardar_medicamentos(paciente_id, meds_list, observaciones, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(meds_list, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('UPDATE medicamentos SET meds_json = ?, observaciones = ?, fecha_modificacion = ?, usuario_registro = ? WHERE paciente_id = ?',
                  (meds_json, observaciones, f_actual, usuario, paciente_id))
    else:
        c.execute('INSERT INTO medicamentos (paciente_id, meds_json, observaciones, fecha_registro, fecha_modificacion, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)',
                  (paciente_id, meds_json, observaciones, f_actual, f_actual, usuario))
                  
    conn.commit()
    conn.close()

def obtener_medicamentos(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT meds_json, observaciones, fecha_modificacion, usuario_registro FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return [], "", None, None

def registrar_entrega_medicamentos(paciente_id, detalle_entrega, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detalle_json = json.dumps(detalle_entrega, ensure_ascii=False)
    
    c.execute('INSERT INTO entregas_medicamentos (paciente_id, fecha_entrega, entregado_por, detalle_json) VALUES (?, ?, ?, ?)',
              (paciente_id, f_actual, usuario, detalle_json))
              
    conn.commit()
    conn.close()

def obtener_historial_entregas(paciente_id=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if paciente_id:
        c.execute('SELECT id, paciente_id, fecha_entrega, entregado_por, detalle_json FROM entregas_medicamentos WHERE paciente_id = ? ORDER BY id DESC', (paciente_id,))
    else:
        c.execute('SELECT id, paciente_id, fecha_entrega, entregado_por, detalle_json FROM entregas_medicamentos ORDER BY id DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_reporte_consolidado_medicamento(nombre_med_buscar):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT p.paciente_id, p.nombre_completo, m.meds_json FROM pacientes p JOIN medicamentos m ON p.paciente_id = m.paciente_id WHERE p.estatus = "A"')
    rows = c.fetchall()
    conn.close()
    
    resultados = []
    consumo_diario_total = 0.0
    existencia_total_almacen = 0.0
    
    for pid, pnom, meds_json_str in rows:
        try:
            meds = json.loads(meds_json_str)
            for m in meds:
                if m.get("nombre", "").strip().upper() == nombre_med_buscar.strip().upper():
                    m_m = float(m.get("manana", 0) or 0)
                    m_t = float(m.get("tarde", 0) or 0)
                    m_n = float(m.get("noche", 0) or 0)
                    d_diaria = m_m + m_t + m_n
                    ex = float(m.get("existencia", 0) or 0)
                    obs = m.get("indicaciones", "")
                    
                    consumo_diario_total += d_diaria
                    existencia_total_almacen += ex
                    
                    resultados.append({
                        "paciente_id": pid,
                        "nombre_completo": pnom,
                        "manana": m_m,
                        "tarde": m_t,
                        "noche": m_n,
                        "dosis_diaria": d_diaria,
                        "existencia": ex,
                        "indicaciones": obs
                    })
        except:
            pass
            
    return resultados, consumo_diario_total, existencia_total_almacen

def calcular_alertas_compras():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT p.paciente_id, p.nombre_completo, m.meds_json FROM pacientes p JOIN medicamentos m ON p.paciente_id = m.paciente_id WHERE p.estatus = "A"')
    rows = c.fetchall()
    conn.close()
    
    alertas = []
    for pid, pnom, meds_json_str in rows:
        try:
            meds = json.loads(meds_json_str)
            for m in meds:
                m_m = float(m.get("manana", 0) or 0)
                m_t = float(m.get("tarde", 0) or 0)
                m_n = float(m.get("noche", 0) or 0)
                d_diaria = m_m + m_t + m_n
                ex = float(m.get("existencia", 0) or 0)
                
                # Si la existencia dura menos de 3 días (o si dosis diaria > 0 y ex < dosis * 3)
                if d_diaria > 0 and ex <= (d_diaria * 3):
                    cant_sugerida = max(30, int(d_diaria * 30))
                    alertas.append((pid, pnom, m.get("nombre", ""), ex, d_diaria, cant_sugerida))
        except:
            pass
    return alertas

# --- GENERADORES DE PDF ---
def limpiar_texto(texto):
    if not texto:
        return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

class PDFReporte(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, limpiar_texto('SAWABONA SHIKOBA - COMUNIDAD TERAPÉUTICA'), 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 6, limpiar_texto('Clínica para el Tratamiento de Adicciones y Salud Mental'), 0, 1, 'C')
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf_grupos_paciente(p_id, p_nombre, grupos):
    pdf = PDFReporte()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, limpiar_texto(f'EXPEDIENTE DE GRUPOS TERAPÉUTICOS - {p_nombre.upper()} ({p_id})'), 0, 1, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f'Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'L')
    pdf.ln(4)
    
    if not grupos:
        pdf.cell(0, 8, limpiar_texto('No hay registros de grupos terapéuticos para este paciente.'), 0, 1, 'L')
    else:
        for g in grupos:
            gid, tipo_g, etapa_g, fecha_g, facil, datos_json_str = g
            d_g = json.loads(datos_json_str)
            
            pdf.set_fill_color(230, 240, 250)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(0, 7, limpiar_texto(f'• {tipo_g.upper()} | Etapa: {etapa_g} | Fecha: {fecha_g} | Facilitador: {facil}'), 1, 1, 'L', True)
            pdf.set_font('Arial', '', 9)
            
            if tipo_g == "Feedback":
                pdf.multi_cell(0, 5, limpiar_texto(f'Logros: {d_g.get("logros","")}'))
                pdf.multi_cell(0, 5, limpiar_texto(f'Dificultades: {d_g.get("dificultades","")}'))
            else:
                pdf.multi_cell(0, 5, limpiar_texto(f'Compartimiento: {d_g.get("compartimiento","")}'))
                
            pdf.multi_cell(0, 5, limpiar_texto(f'Observaciones: {d_g.get("observaciones","")}'))
            pdf.multi_cell(0, 5, limpiar_texto(f'Devoluciones: {d_g.get("devoluciones","")}'))
            pdf.multi_cell(0, 5, limpiar_texto(f'Como se queda / Compromiso: {d_g.get("compromiso","")}'))
            pdf.ln(3)
            
    f_name = f"Grupos_Terapeuticos_{p_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    p_path = os.path.join("/tmp", f_name)
    pdf.output(p_path)
    return p_path, f_name

# --- INICIALIZACIÓN DE SESIÓN Y CONTROL DE ACCESO ---
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
    st.markdown("<h3 style='text-align: center;'>Comunidad Terapéutica para el Tratamiento de Adicciones</h3>", unsafe_allow_html=True)
    st.write("")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔑 Iniciar Sesión en el Sistema")
            user_input = st.text_input("Usuario").strip()
            pass_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submit:
                usuario_valido = verificar_login(user_input, pass_input)
                if usuario_valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = usuario_valido[0]
                    st.session_state["nombre_completo"] = usuario_valido[1]
                    st.session_state["rol"] = usuario_valido[2] if len(usuario_valido) > 2 else "Nivel 1 - Administrador"
                    st.toast("🎉 ¡Acceso concedido! Bienvenido al sistema.")
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # --- BARRA LATERAL Y NAVEGACIÓN ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.caption(f"🔒 **Rol**: {st.session_state['rol']}")
    st.sidebar.markdown("---")
    
    rol_actual = st.session_state["rol"]
    es_admin = "Nivel 1" in rol_actual
    es_lectura_escritura = es_admin or ("Nivel 2" in rol_actual)
    
    opciones_menu = [
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "👤 Registro y Edición de Usuarios",
        "📝 Nueva Entrevista / Editar",
        "🔍 Buscar y Listar Pacientes",
        "💊 Control de Medicamentos",
        "🚚 Entrega de Medicamentos",
        "📂 Repositorio de Documentos",
        "📦 Respaldo y Restauración",
        "⚙️ Seguridad y Usuarios"
    ]
    
    menu = st.sidebar.radio("Navegación del Sistema", opciones_menu)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ---------------------------------------------------------
    # 1. MÓDULO: GESTIÓN DE ETAPAS & PROCESO
    # ---------------------------------------------------------
    if menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Avance de Pacientes")
        st.caption("Control de avance de 7 meses (5 Etapas: Acogida, Identificación, Elaboración, Consolidación, Servicio Social)")
        
        pacientes = listar_todos_pacientes()
        pacientes_activos = [p for p in pacientes if p[5] == 'A' and p[6] == 'Paciente']
        
        tab_avance, tab_hermano, tab_alertas = st.tabs([
            "📊 Avance y Checklist de Etapa",
            "🤝 Hermano Menor / Hermano Mayor",
            "🚨 Alertas de Cambio de Etapa (5 días)"
        ])
        
        with tab_avance:
            if not pacientes_activos:
                st.info("No hay pacientes activos registrados actualmente.")
            else:
                p_opts = {f"{p[1]} ({p[0]}) - Etapa: {p[7]}": p for p in pacientes_activos}
                sel_p = st.selectbox("🔑 Selecciona un Residente para evaluar:", list(p_opts.keys()))
                p_data = p_opts[sel_p]
                
                p_id, p_nombre, f_ing, f_nac, p_sexo, p_est, p_tipo, p_etapa, f_ini_etapa, h_mayor, f_suelta = p_data
                
                # Duraciones estándar
                duraciones = {
                    "ACOGIDA": 30,
                    "IDENTIFICACIÓN": 60,
                    "ELABORACIÓN": 60,
                    "CONSOLIDACIÓN": 30,
                    "SERVICIO SOCIAL": 30
                }
                etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                
                dias_etapa_req = duraciones.get(p_etapa, 30)
                
                # Calcular días transcurridos en etapa
                f_ini_dt = datetime.strptime(f_ini_etapa[:10], "%Y-%m-%d").date() if f_ini_etapa else date.today()
                dias_en_etapa = (date.today() - f_ini_dt).days
                
                # Calcular días totales en comunidad
                f_ing_dt = datetime.strptime(f_ing[:10], "%Y-%m-%d").date() if f_ing else date.today()
                dias_totales = (date.today() - f_ing_dt).days
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Etapa Actual", p_etapa)
                col2.metric("Días en Etapa Actual", f"{dias_en_etapa} de {dias_etapa_req} días")
                col3.metric("Días Totales en la Comunidad", f"{dias_totales} días")
                
                pct = min(1.0, max(0.0, dias_en_etapa / dias_etapa_req))
                st.progress(pct, text=f"Progreso de tiempo en {p_etapa}: {dias_en_etapa}/{dias_etapa_req} días ({int(pct*100)}%)")
                
                # Alerta de Rezago
                if dias_en_etapa > dias_etapa_req:
                    exceso = dias_en_etapa - dias_etapa_req
                    st.warning(f"⚠️ **ALERTA DE REZAGO CLINICO**: {p_nombre} ha excedido la duración estándar de **{p_etapa}** por **+{exceso} días**. Por favor revise el checklist a continuación para diagnosticar los requisitos faltantes.")
                
                st.markdown("---")
                st.subheader(f"📋 Checklist de Requisitos para Cambiar de Etapa ({p_etapa})")
                
                reqs_etapa = obtener_requisitos_etapa(p_etapa)
                checklist_completo = True
                
                for req_id, req_text, es_grupo in reqs_etapa:
                    if es_grupo == 1:
                        # Determinar tipo de grupo por nombre del requisito
                        tipo_g_search = "Aquí y Ahora" if "Aquí" in req_text else ("Feedback" if "Feedback" in req_text else "Terapia de Grupo")
                        req_num = 4 if "4" in req_text else (2 if "2" in req_text else 1)
                        
                        cant_hecha = contar_grupos_paciente_etapa(p_id, p_etapa, tipo_g_search)
                        cumplido = cant_hecha >= req_num
                        if not cumplido:
                            checklist_completo = False
                            
                        st.checkbox(f"🗣️ **{req_text}** (Realizados: {cant_hecha} de {req_num})", value=cumplido, disabled=True)
                    else:
                        # Requisito conductual / teórico
                        c_val = st.checkbox(f"📝 {req_text}", key=f"req_{p_id}_{p_etapa}_{req_id}")
                        if not c_val:
                            checklist_completo = False
                            
                st.markdown("---")
                idx_curr = etapas_orden.index(p_etapa) if p_etapa in etapas_orden else 0
                if idx_curr < len(etapas_orden) - 1:
                    siguiente_etapa = etapas_orden[idx_curr + 1]
                    
                    if not es_lectura_escritura:
                        st.info("Su rol es de Solo Lectura. No puede promover a los pacientes de etapa.")
                    else:
                        if checklist_completo:
                            st.success(f"🎉 ¡Todos los requisitos de la etapa **{p_etapa}** están cumplidos al 100%!")
                            if st.button(f"🚀 Promover a {p_nombre} a la Etapa: {siguiente_etapa}", use_container_width=True, type="primary"):
                                promover_paciente_etapa(p_id, siguiente_etapa, p_etapa, st.session_state["username"])
                                st.toast(f"🎉 ¡{p_nombre} promovido exitosamente a {siguiente_etapa}!")
                                st.success(f"¡{p_nombre} promovido a {siguiente_etapa}!")
                                st.rerun()
                        else:
                            st.error(f"🔒 El botón de promoción a **{siguiente_etapa}** está bloqueado porque aún faltan requisitos por completar en el checklist.")
                else:
                    st.balloons()
                    st.success("🌟 ¡El paciente se encuentra en la etapa final de SERVICIO SOCIAL!")

        with tab_hermano:
            st.subheader("🤝 Control de Hermano Menor y Hermano Mayor (ACOGIDA)")
            acogida_pacientes = [p for p in pacientes_activos if p[7] == 'ACOGIDA']
            if not acogida_pacientes:
                st.info("No hay pacientes actualmente en la etapa de ACOGIDA.")
            else:
                for p_ac in acogida_pacientes:
                    p_id, p_nom, f_ing, f_nac, p_sex, p_est, p_tip, p_et, f_ini, h_may_id, f_suelta = p_ac
                    f_ini_dt = datetime.strptime(f_ini[:10], "%Y-%m-%d").date() if f_ini else date.today()
                    dias_ac = (date.today() - f_ini_dt).days
                    
                    st.markdown(f"### 👦 {p_nom} ({p_id}) - {dias_ac} días en Acogida")
                    
                    if dias_ac <= 15 and not f_suelta:
                        st.caption("Status: **Hermano Menor Activo** (Primeros 15 días de acogida)")
                    else:
                        st.caption("Status: **Autónomo** (Hermano Mayor lo soltó o pasó de 15 días)")
                        
                    col1, col2 = st.columns(2)
                    with col1:
                        if h_may_id:
                            h_m_data = obtener_paciente_por_id(h_may_id)
                            nom_h_m = h_m_data[1] if h_m_data else h_may_id
                            st.write(f"🧑‍🤝‍🧑 **Hermano Mayor Asignado**: {nom_h_m}")
                        else:
                            st.write("🧑‍🤝‍🧑 **Hermano Mayor**: *Sin asignar*")
                            
                        # Opción de asignar si es lectura/escritura
                        if es_lectura_escritura:
                            posibles_mayores = [p for p in pacientes if p[0] != p_id and (p[7] != 'ACOGIDA' or p[6] == 'Servidor')]
                            m_opts = {f"{p[1]} ({p[0]}) - {p[7]}": p[0] for p in posibles_mayores}
                            if m_opts:
                                sel_m = st.selectbox(f"Asignar/Cambiar Hermano Mayor para {p_nom}:", list(m_opts.keys()), key=f"sel_hm_{p_id}")
                                if st.button(f"Asignar Hermano Mayor", key=f"btn_hm_{p_id}"):
                                    asignar_hermano_mayor(p_id, m_opts[sel_m], st.session_state["username"])
                                    st.toast("🎉 ¡Hermano Mayor asignado!")
                                    st.success("Asignado correctamente.")
                                    st.rerun()

                    with col2:
                        if f_suelta:
                            st.success(f"🔓 **Fecha de Suelta Registrada**: {f_suelta}")
                        else:
                            st.warning("🔒 **Hermano Menor sin Soltar**")
                            if es_lectura_escritura:
                                if st.button(f"🔓 Registrar Suelta de Hermano Mayor para {p_nom}", key=f"btn_suelta_{p_id}"):
                                    registrar_suelta_hermano(p_id, st.session_state["username"])
                                    st.toast("🎉 ¡Suelta de Hermano Mayor registrada!")
                                    st.success("Suelta registrada.")
                                    st.rerun()
                    st.markdown("---")

        with tab_alertas:
            st.subheader("🚨 Alertas Tempranas de Cambio de Etapa (5 Días de Anticipación)")
            alertas_etapa = []
            for p in pacientes_activos:
                pid, pnom, fing, fnac, psex, pest, ptip, petapa, fini, hmay, fsuel = p
                f_ini_dt = datetime.strptime(fini[:10], "%Y-%m-%d").date() if fini else date.today()
                dias_en_e = (date.today() - f_ini_dt).days
                req_dias = duraciones.get(petapa, 30)
                
                # Faltan 5 días o menos para cumplir los días requeridos
                dias_restantes = req_dias - dias_en_e
                if dias_restantes <= 5 and petapa != "SERVICIO SOCIAL":
                    alertas_etapa.append((pid, pnom, petapa, dias_en_e, req_dias, dias_restantes))
                    
            if not alertas_etapa:
                st.success("✅ No hay residentes actualmente en ventana de alerta de 5 días para cambio de etapa.")
            else:
                for pid, pnom, petapa, dias_e, req_d, d_rest in alertas_etapa:
                    if d_rest <= 0:
                        st.error(f"🚨 **LISTO PARA EVALUACIÓN**: **{pnom}** ({pid}) ha cumplido **{dias_e} de {req_d} días** en la etapa **{petapa}**. Solicitar comité de cambio de etapa.")
                    else:
                        st.warning(f"⚠️ **ALERTA PREVENTIVA (Faltan {d_rest} días)**: **{pnom}** ({pid}) lleva **{dias_e} de {req_d} días** en la etapa **{petapa}**.")

    # ---------------------------------------------------------
    # 2. MÓDULO: GRUPOS TERAPÉUTICOS
    # ---------------------------------------------------------
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        st.caption("Captura de Terapia de Grupo, Aquí y Ahora y Feedbacks por residente")
        
        pacientes = listar_todos_pacientes()
        pacientes_activos = [p for p in pacientes if p[5] == 'A' and p[6] == 'Paciente']
        
        tab_reg_g, tab_hist_g = st.tabs(["📝 Registrar Sesión de Grupo", "📜 Historial e Impresión PDF"])
        
        with tab_reg_g:
            if not pacientes_activos:
                st.info("No hay pacientes activos registrados en el sistema.")
            else:
                p_dict = {f"{p[1]} ({p[0]}) - Etapa Actual: {p[7]}": p for p in pacientes_activos}
                sel_p_g = st.selectbox("🔑 Selecciona el Residente:", list(p_dict.keys()))
                p_sel = p_dict[sel_p_g]
                p_id_g, p_nombre_g, _, _, _, _, _, etapa_g, _, _, _ = p_sel
                
                st.markdown(f"**Residente**: `{p_nombre_g}` | **Folio**: `{p_id_g}` | **Etapa al momento**: `{etapa_g}`")
                
                tipo_grupo = st.radio("Selecciona el Tipo de Grupo Terapéutico:", ["Terapia de Grupo", "Aquí y Ahora", "Feedback"], horizontal=True)
                
                with st.form("form_grupo_terapeuta"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        fecha_g = st.date_input("Fecha de la Sesión", value=date.today())
                    with col_b:
                        facilitador = st.text_input("Nombre del Facilitador / Staff", value=st.session_state["nombre_completo"])
                        
                    datos_grupo = {}
                    if tipo_grupo in ["Terapia de Grupo", "Aquí y Ahora"]:
                        datos_grupo["compartimiento"] = st.text_area("Compartimiento (Texto largo)")
                        datos_grupo["observaciones"] = st.text_area("Observaciones (Texto largo)")
                        datos_grupo["devoluciones"] = st.text_area("Devoluciones (Texto largo)")
                        datos_grupo["compromiso"] = st.text_area("¿Cómo se queda y a qué se compromete?")
                    else: # Feedback
                        datos_grupo["logros"] = st.text_area("Logros (Texto largo)")
                        datos_grupo["dificultades"] = st.text_area("Dificultades (Texto largo)")
                        datos_grupo["observaciones"] = st.text_area("Observaciones (Texto largo)")
                        datos_grupo["devoluciones"] = st.text_area("Devoluciones (Texto largo)")
                        datos_grupo["compromiso"] = st.text_area("¿Cómo se queda y a qué se compromete?")
                        
                    btn_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                    
                    if btn_g:
                        if not es_lectura_escritura:
                            st.error("Su rol es de Solo Lectura. No puede guardar sesiones.")
                        else:
                            guardar_grupo_terapeuta(p_id_g, tipo_grupo, etapa_g, str(fecha_g), facilitador, datos_grupo, st.session_state["username"])
                            st.toast(f"🎉 ¡Sesión de {tipo_grupo} registrada exitosamente para {p_nombre_g}!")
                            st.success(f"✅ Sesión de {tipo_grupo} registrada exitosamente para {p_nombre_g}.")
                            st.rerun()

        with tab_hist_g:
            if not pacientes_activos:
                st.info("No hay pacientes activos.")
            else:
                p_dict = {f"{p[1]} ({p[0]})": p for p in pacientes_activos}
                sel_p_h = st.selectbox("🔑 Selecciona el Residente para ver su historial de grupos:", list(p_dict.keys()), key="sel_hist_g")
                p_h = p_dict[sel_p_h]
                p_id_h, p_nombre_h = p_h[0], p_h[1]
                
                grupos_pac = obtener_grupos_paciente(p_id_h)
                
                col_h1, col_h2 = st.columns([2, 1])
                with col_h1:
                    st.subheader(f"Total de sesiones registradas: {len(grupos_pac)}")
                with col_h2:
                    if grupos_pac:
                        pdf_path, pdf_fname = generar_pdf_grupos_paciente(p_id_h, p_nombre_h, grupos_pac)
                        with open(pdf_path, "rb") as f_pdf:
                            st.download_button("🖨️ Descargar Expediente de Grupos (PDF)", f_pdf, file_name=pdf_fname, mime="application/pdf", use_container_width=True)
                            
                st.markdown("---")
                if not grupos_pac:
                    st.info("Este residente no tiene sesiones de grupo registradas aún.")
                else:
                    for g in grupos_pac:
                        gid, tipo_g, etapa_g, fecha_g, facil, datos_json_str = g
                        d_g = json.loads(datos_json_str)
                        
                        with st.expander(f"📌 {tipo_g} | Etapa: {etapa_g} | Fecha: {fecha_g} | Facilitador: {facil}"):
                            if tipo_g == "Feedback":
                                st.write(f"**Logros**: {d_g.get('logros','')}")
                                st.write(f"**Dificultades**: {d_g.get('dificultades','')}")
                            else:
                                st.write(f"**Compartimiento**: {d_g.get('compartimiento','')}")
                            st.write(f"**Observaciones**: {d_g.get('observaciones','')}")
                            st.write(f"**Devoluciones**: {d_g.get('devoluciones','')}")
                            st.write(f"**Compromiso**: {d_g.get('compromiso','')}")

    # ---------------------------------------------------------
    # 3. MÓDULO: REGISTRO Y EDICIÓN DE USUARIOS
    # ---------------------------------------------------------
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes y Servidores")
        
        modo_usuario = st.radio("Selecciona la acción:", ["🆕 Registrar Nuevo Usuario", "✏️ Modificar / Editar Usuario Existente"], horizontal=True)
        
        pacientes_todos = listar_todos_pacientes()
        
        folio_siguiente = obtener_siguiente_folio()
        
        # Datos por defecto
        reg_id = folio_siguiente
        reg_nom = ""
        reg_f_ing = str(date.today())
        reg_f_nac = "2000-01-01"
        reg_sex = "MASCULINO"
        reg_est = "A"
        reg_tip = "Paciente"
        reg_etapa = "ACOGIDA"
        reg_f_ini_etapa = str(date.today())
        
        if modo_usuario == "✏️ Modificar / Editar Usuario Existente":
            if not pacientes_todos:
                st.warning("No hay usuarios registrados en el sistema para editar.")
            else:
                p_opts_edit = {f"{p[0]} - {p[1]} ({'ACTIVO' if p[5]=='A' else 'BLOQUEADO'})": p[0] for p in pacientes_todos}
                sel_p_edit = st.selectbox("🔑 Selecciona el Usuario a Editar:", list(p_opts_edit.keys()))
                edit_id = p_opts_edit[sel_p_edit]
                
                p_edit_data = obtener_paciente_por_id(edit_id)
                if p_edit_data:
                    reg_id = p_edit_data[0]
                    reg_nom = p_edit_data[1]
                    reg_f_ing = p_edit_data[2] if p_edit_data[2] else str(date.today())
                    reg_f_nac = p_edit_data[3] if p_edit_data[3] else "2000-01-01"
                    reg_sex = p_edit_data[4] if p_edit_data[4] else "MASCULINO"
                    reg_est = p_edit_data[5] if p_edit_data[5] else "A"
                    reg_tip = p_edit_data[6] if p_edit_data[6] else "Paciente"
                    reg_etapa = p_edit_data[7] if p_edit_data[7] else "ACOGIDA"
                    reg_f_ini_etapa = p_edit_data[8] if p_edit_data[8] else reg_f_ing

        # Formulario dinamico
        with st.form(f"form_user_reg_{reg_id}"):
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("🔑 Folio / ID de Usuario", value=reg_id, disabled=True)
                nombre_in = st.text_input("Nombre Completo del Usuario *", value=reg_nom)
                f_ing_in = st.date_input("Fecha de Ingreso a la Comunidad", value=datetime.strptime(reg_f_ing[:10], "%Y-%m-%d").date())
                f_nac_in = st.date_input("Fecha de Nacimiento", value=datetime.strptime(reg_f_nac[:10], "%Y-%m-%d").date(), min_value=date(1920, 1, 1))
            with col2:
                sexo_in = st.selectbox("Sexo", ["MASCULINO", "FEMENINO"], index=0 if reg_sex=="MASCULINO" else 1)
                tipo_in = st.selectbox("Tipo de Usuario", ["Paciente", "Servidor / Staff"], index=0 if reg_tip=="Paciente" else 1)
                estatus_in = st.selectbox("Estatus en el Sistema", ["A - ACTIVO", "B - BLOQUEADO / EGRESADO"], index=0 if reg_est=="A" else 1)
                estatus_code = "A" if "A - " in estatus_in else "B"
                
                etapas_lista = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                idx_et = etapas_lista.index(reg_etapa) if reg_etapa in etapas_lista else 0
                etapa_in = st.selectbox("Etapa Actual", etapas_lista, index=idx_et)
                f_ini_e_in = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.strptime(reg_f_ini_etapa[:10], "%Y-%m-%d").date())
                
            btn_save_u = st.form_submit_button("💾 Guardar Usuario / Cambios", use_container_width=True)
            
            if btn_save_u:
                if not es_lectura_escritura:
                    st.error("Su rol es de Solo Lectura. No puede guardar usuarios.")
                elif not nombre_in.strip():
                    st.error("⚠️ El Nombre Completo es obligatorio.")
                else:
                    dup = verificar_duplicado_nombre(nombre_in, reg_id)
                    if dup:
                        st.error(f"❌ No se puede registrar: Ya existe un usuario con el nombre '{dup[1]}' bajo el folio {dup[0]}.")
                    else:
                        guardar_usuario_paciente(
                            reg_id, nombre_in.strip().upper(), str(f_ing_in), str(f_nac_in), sexo_in, estatus_code,
                            tipo_in, etapa_in, str(f_ini_e_in), st.session_state["username"]
                        )
                        st.toast(f"🎉 ¡Usuario {nombre_in} guardado correctamente con Folio {reg_id}!")
                        st.success(f"✅ Usuario {nombre_in} ({reg_id}) guardado correctamente.")
                        st.rerun()

    # ---------------------------------------------------------
    # 4. MÓDULO: NUEVA ENTREVISTA / EDITAR
    # ---------------------------------------------------------
    elif menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        
        pacientes = listar_todos_pacientes()
        pacientes_activos = [p for p in pacientes if p[5] == 'A']
        
        if not pacientes_activos:
            st.warning("No hay usuarios activos registrados. Por favor registre un usuario en '👤 Registro de Usuarios' primero.")
        else:
            p_dict_e = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_ent = st.selectbox("🔑 Selecciona el Residente para la Entrevista Inicial:", list(p_dict_e.keys()))
            p_id_ent = p_dict_e[sel_p_ent]
            
            datos_existentes, f_reg, f_mod, u_reg = obtener_entrevista(p_id_ent)
            if datos_existentes:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Última modificación: {f_mod}")
            else:
                datos_existentes = {}
                st.info("🆕 Folio nuevo. Complete la evaluación a continuación.")
                
            with st.form("form_entrevista_inicial"):
                tab1, tab2, tab3 = st.tabs(["1. Datos Socio-Demográficos", "2. Consumo de Sustancias", "3. Disposición y Entorno"])
                
                with tab1:
                    c1, c2 = st.columns(2)
                    with c1:
                        dep_flag = st.selectbox("¿Tiene dependientes económicos?", ["NO", "SÍ"], index=1 if datos_existentes.get("dependientes_flag")=="SÍ" else 0)
                        dep_quienes = st.text_input("¿Quiénes?", value=datos_existentes.get("dependientes_quienes",""))
                    with c2:
                        par_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=1 if datos_existentes.get("pareja_flag")=="SÍ" else 0)
                        par_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo",""))
                        
                with tab2:
                    st.subheader("Sustancias de Consumo")
                    sustancias = ["ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "TABACO"]
                    tabla_consumo = datos_existentes.get("tabla_consumo", {})
                    tabla_res = {}
                    
                    for sust in sustancias:
                        s_data = tabla_consumo.get(sust, {})
                        st.markdown(f"**{sust}**")
                        col_a, col_b, col_c = st.columns([1, 2, 2])
                        with col_a:
                            c_cons = st.checkbox("Consume", value=s_data.get("consumo")=="SÍ", key=f"c_{sust}")
                        with col_b:
                            frec = st.text_input("Frecuencia/Cantidad", value=s_data.get("frecuencia",""), key=f"f_{sust}")
                        with col_c:
                            edad = st.text_input("Edad de inicio", value=s_data.get("edad_inicio",""), key=f"e_{sust}")
                        tabla_res[sust] = {"consumo": "SÍ" if c_cons else "NO", "frecuencia": frec, "edad_inicio": edad}
                        
                with tab3:
                    motivo = st.text_area("Motivo de Ingreso", value=datos_existentes.get("motivo_ingreso",""))
                    obs_finales = st.text_area("Observaciones del Consejero", value=datos_existentes.get("observaciones_finales",""))
                    
                btn_save_ent = st.form_submit_button("💾 Guardar Expediente de Consejería", use_container_width=True)
                
                if btn_save_ent:
                    if not es_lectura_escritura:
                        st.error("Su rol es de Solo Lectura.")
                    else:
                        datos_completos = {
                            "dependientes_flag": dep_flag,
                            "dependientes_quienes": dep_quienes,
                            "pareja_flag": par_flag,
                            "pareja_tiempo": par_tiempo,
                            "tabla_consumo": tabla_res,
                            "motivo_ingreso": motivo,
                            "observaciones_finales": obs_finales
                        }
                        guardar_entrevista(p_id_ent, datos_completos, st.session_state["username"])
                        st.toast("🎉 ¡Expediente de consejería guardado exitosamente!")
                        st.success(f"✅ Expediente {p_id_ent} guardado correctamente.")
                        st.rerun()

    # ---------------------------------------------------------
    # 5. MÓDULO: BUSCAR Y LISTAR PACIENTES
    # ---------------------------------------------------------
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio de Residentes y Servidores")
        
        pacientes = listar_todos_pacientes()
        if not pacientes:
            st.info("No hay usuarios registrados aún.")
        else:
            busqueda = st.text_input("🔍 Buscar por Nombre o Folio:").strip().upper()
            pacientes_filtrados = [p for p in pacientes if busqueda in p[0].upper() or busqueda in p[1].upper()]
            
            st.subheader(f"Total encontrados: {len(pacientes_filtrados)}")
            
            for pac in pacientes_filtrados:
                pid, pnom, fing, fnac, psex, pest, ptip, petapa, fini, hmay, fsuel = pac
                est_label = "🟢 ACTIVO" if pest == 'A' else "🔴 BLOQUEADO"
                
                with st.expander(f"👤 {pnom} ({pid}) | {est_label} | Tipo: {ptip} | Etapa: {petapa}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Fecha de Ingreso**: {fing}")
                        st.write(f"**Fecha de Nacimiento**: {fnac}")
                        st.write(f"**Sexo**: {psex}")
                    with col2:
                        st.write(f"**Etapa Actual**: {petapa}")
                        st.write(f"**Inicio en Etapa**: {fini}")
                        if hmay:
                            st.write(f"**Hermano Mayor**: {hmay}")

    # ---------------------------------------------------------
    # 6. MÓDULO: CONTROL DE MEDICAMENTOS
    # ---------------------------------------------------------
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos y Dosis por Residente")
        
        pacientes = listar_todos_pacientes()
        pacientes_activos = [p for p in pacientes if p[5] == 'A' and p[6] == 'Paciente']
        cat_meds = obtener_catalogo_medicamentos()
        cat_nombres = [m[1] for m in cat_meds] if cat_meds else ["PARACETAMOL", "IBUPROFENO", "OMEPRAZOL"]
        
        tab_p_med, tab_cat_med, tab_rep_med = st.tabs(["👤 Asignar Dosis por Residente", "📚 Catálogo Central de Medicamentos", "📊 Reporte Global por Medicamento"])
        
        with tab_p_med:
            if not pacientes_activos:
                st.info("No hay residentes activos.")
            else:
                p_dict_m = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
                sel_p_m = st.selectbox("🔑 Selecciona el Residente:", list(p_dict_m.keys()))
                p_id_m = p_dict_m[sel_p_m]
                p_nom_m = sel_p_m.split(" (")[0]
                
                meds_cargados, obs_meds, _, _ = obtener_medicamentos(p_id_m)
                
                st.subheader(f"Esquema de Medicación para {p_nom_m}")
                
                with st.form("form_esquema_meds"):
                    cant_meds = st.number_input("Número de medicamentos a asignar:", min_value=1, max_value=10, value=max(1, len(meds_cargados)))
                    
                    lista_meds_input = []
                    for i in range(int(cant_meds)):
                        st.markdown(f"**Medicamento #{i+1}**")
                        m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                        
                        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                        with col1:
                            m_nom = st.selectbox(f"Medicamento", cat_nombres, key=f"med_nom_{i}")
                        with col2:
                            m_man = st.number_input(f"Mañana", min_value=0.0, step=0.5, value=float(m_prev.get("manana",0)), key=f"med_man_{i}")
                        with col3:
                            m_tar = st.number_input(f"Tarde", min_value=0.0, step=0.5, value=float(m_prev.get("tarde",0)), key=f"med_tar_{i}")
                        with col4:
                            m_noc = st.number_input(f"Noche", min_value=0.0, step=0.5, value=float(m_prev.get("noche",0)), key=f"med_noc_{i}")
                        with col5:
                            m_ex = st.number_input(f"Existencia", min_value=0.0, step=1.0, value=float(m_prev.get("existencia",0)), key=f"med_ex_{i}")
                            
                        m_ind = st.text_input(f"Indicaciones / Dosis recomendada", value=m_prev.get("indicaciones",""), key=f"med_ind_{i}")
                        
                        lista_meds_input.append({
                            "nombre": m_nom,
                            "manana": m_man,
                            "tarde": m_tar,
                            "noche": m_noc,
                            "existencia": m_ex,
                            "indicaciones": m_ind
                        })
                        st.markdown("---")
                        
                    obs_in = st.text_area("Observaciones o Alergias Medicamentosas", value=obs_meds)
                    btn_save_m = st.form_submit_button("💾 Guardar Esquema de Medicamentos", use_container_width=True)
                    
                    if btn_save_m:
                        if not es_lectura_escritura:
                            st.error("Su rol es de Solo Lectura.")
                        else:
                            guardar_medicamentos(p_id_m, lista_meds_input, obs_in, st.session_state["username"])
                            st.toast("🎉 ¡Esquema de medicamentos guardado exitosamente!")
                            st.success(f"✅ Esquema guardado para {p_nom_m}.")
                            st.rerun()

        with tab_cat_med:
            st.subheader("📚 Catálogo Centralizado de Medicamentos")
            if es_lectura_escritura:
                with st.form("form_add_cat_med"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        new_m_nom = st.text_input("Nombre del Medicamento *")
                    with c2:
                        new_m_pres = st.text_input("Presentación (ej. Tabletas, Cápsulas, Gotas)")
                    with c3:
                        new_m_conc = st.text_input("Concentración (ej. 500 mg, 20 mg)")
                    btn_cat = st.form_submit_button("➕ Agregar al Catálogo")
                    if btn_cat and new_m_nom:
                        agregar_catalogo_medicamento(new_m_nom, new_m_pres, new_m_conc)
                        st.toast("🎉 ¡Medicamento agregado al catálogo!")
                        st.success("Medicamento agregado.")
                        st.rerun()
                        
            st.markdown("---")
            cat_list = obtener_catalogo_medicamentos()
            for cm in cat_list:
                st.write(f"💊 **{cm[1]}** | Presentación: {cm[2]} | Concentración: {cm[3]}")

        with tab_rep_med:
            st.subheader("📊 Reporte Consolidado por Medicamento")
            med_sel_rep = st.selectbox("Selecciona un medicamento para ver el consumo total:", cat_nombres)
            
            res_med, cons_diario, ex_total = obtener_reporte_consolidado_medicamento(med_sel_rep)
            
            col1, col2 = st.columns(2)
            col1.metric(f"Consumo Total Diario en Clínica ({med_sel_rep})", f"{cons_diario} unidades/día")
            col2.metric(f"Existencia Total en Almacén", f"{ex_total} unidades")
            
            st.markdown("---")
            if not res_med:
                st.info(f"Ningún residente tiene asignado actualmente **{med_sel_rep}**.")
            else:
                for rm in res_med:
                    st.write(f"👤 **{rm['nombre_completo']}** ({rm['paciente_id']}) | Dosis Mañana: {rm['manana']} | Tarde: {rm['tarde']} | Noche: {rm['noche']} | **Dosis Diaria Total: {rm['dosis_diaria']}** | Existencia: {rm['existencia']}")

    # ---------------------------------------------------------
    # 7. MÓDULO: ENTREGA DE MEDICAMENTOS
    # ---------------------------------------------------------
    elif menu == "🚚 Entrega de Medicamentos":
        st.title("🚚 Entrega Diaria de Medicamentos")
        
        pacientes = listar_todos_pacientes()
        pacientes_activos = [p for p in pacientes if p[5] == 'A' and p[6] == 'Paciente']
        
        if not pacientes_activos:
            st.info("No hay residentes activos.")
        else:
            p_dict_ent = {f"{p[1]} ({p[0]})": p[0] for p in pacientes_activos}
            sel_p_d = st.selectbox("🔑 Selecciona el Residente para entregar medicamentos:", list(p_dict_ent.keys()))
            p_id_d = p_dict_ent[sel_p_d]
            p_nom_d = sel_p_d.split(" (")[0]
            
            meds_cargados, _, _, _ = obtener_medicamentos(p_id_d)
            
            if not meds_cargados:
                st.warning(f"{p_nom_d} no tiene medicamentos asignados en su esquema.")
            else:
                st.subheader(f"Medicamentos programados para {p_nom_d}")
                
                with st.form("form_entrega_meds"):
                    entrega_items = []
                    for idx, m in enumerate(meds_cargados):
                        m_nom = m.get("nombre","")
                        ex = float(m.get("existencia", 0))
                        d_diaria = float(m.get("manana",0)) + float(m.get("tarde",0)) + float(m.get("noche",0))
                        
                        # Defecto: Dosis diaria recomendada
                        default_cant = min(ex, d_diaria)
                        
                        st.write(f"💊 **{m_nom}** | Existencia en almacén: `{ex}` | Dosis diaria: `{d_diaria}`")
                        cant_entregar = st.number_input(f"Cantidad a entregar de {m_nom}:", min_value=0.0, max_value=ex, value=default_cant, step=1.0, key=f"ent_{p_id_d}_{idx}")
                        
                        entrega_items.append({
                            "nombre": m_nom,
                            "cantidad_entregada": cant_entregar,
                            "existencia_anterior": ex,
                            "existencia_nueva": ex - cant_entregar
                        })
                        st.markdown("---")
                        
                    btn_confirm_ent = st.form_submit_button("🚚 Confirmar Entrega y Descontar Almacén", use_container_width=True)
                    
                    if btn_confirm_ent:
                        if not es_lectura_escritura:
                            st.error("Su rol es de Solo Lectura.")
                        else:
                            # Actualizar existencias en la DB
                            for i, item in enumerate(entrega_items):
                                meds_cargados[i]["existencia"] = item["existencia_nueva"]
                                
                            guardar_medicamentos(p_id_d, meds_cargados, "", st.session_state["username"])
                            registrar_entrega_medicamentos(p_id_d, entrega_items, st.session_state["username"])
                            
                            st.toast(f"🎉 ¡Entrega registrada exitosamente para {p_nom_d}!")
                            st.success(f"✅ Entrega confirmada y existencias descontadas.")
                            st.rerun()

    # ---------------------------------------------------------
    # 8. MÓDULO: REPOSITORIO DE DOCUMENTOS (SOLO ADMIN)
    # ---------------------------------------------------------
    elif menu == "📂 Repositorio de Documentos":
        st.title("📂 Repositorio de Documentos y Formatos")
        
        if not es_admin:
            st.error("🔒 Acceso Restringido: El Repositorio de Documentos es exclusivo para usuarios con rol Nivel 1 - Administrador.")
        else:
            carpetas_default = [
                "📋 Formatos Clínicos y Administrativos",
                "📖 Manuales de Operación",
                "⚖️ Reglamentos y Normativas",
                "📑 Plantillas de Evaluación",
                "📁 Documentos Generales"
            ]
            
            tab_ver_doc, tab_subir_doc = st.tabs(["📥 Descargar Documentos", "📤 Subir Nuevo Documento"])
            
            with tab_subir_doc:
                st.subheader("📤 Subir Formato o Manual a la Nube")
                with st.form("form_subir_doc"):
                    c_sel = st.selectbox("Carpeta / Categoría:", carpetas_default)
                    arch_uploaded = st.file_uploader("Selecciona el archivo (PDF, Word, Excel, Imagen):", type=["pdf", "docx", "xlsx", "png", "jpg", "txt"])
                    desc_doc = st.text_area("Descripción o notas del documento:")
                    
                    btn_up_doc = st.form_submit_button("📤 Guardar Documento en la Nube", use_container_width=True)
                    
                    if btn_up_doc:
                        if not arch_uploaded:
                            st.error("Por favor selecciona un archivo.")
                        else:
                            bytes_data = arch_uploaded.read()
                            guardar_documento_repositorio(
                                c_sel, arch_uploaded.name, arch_uploaded.type, bytes_data, desc_doc, st.session_state["username"]
                            )
                            st.toast("🎉 ¡Documento subido exitosamente!")
                            st.success(f"✅ Archivo '{arch_uploaded.name}' guardado correctamente en la carpeta {c_sel}.")
                            st.rerun()

            with tab_ver_doc:
                st.subheader("📥 Explorador de Documentos")
                filtro_c = st.selectbox("Filtrar por Carpeta:", ["TODAS"] + carpetas_default)
                
                docs = obtener_documentos_repositorio(filtro_c)
                
                if not docs:
                    st.info("No hay documentos guardados en esta carpeta.")
                else:
                    for d in docs:
                        d_id, d_carp, d_nom, d_mime, d_blob, d_desc, d_fsub, d_usub = d
                        
                        with st.expander(f"📄 {d_nom} | Carpeta: {d_carp} | Subido: {d_fsub} por {d_usub}"):
                            st.write(f"**Descripción**: {d_desc}")
                            col_d1, col_d2 = st.columns(2)
                            with col_d1:
                                st.download_button(
                                    label=f"📥 Descargar {d_nom}",
                                    data=d_blob,
                                    file_name=d_nom,
                                    mime=d_mime,
                                    key=f"dl_doc_{d_id}"
                                )
                            with col_d2:
                                if st.button(f"🗑️ Eliminar Documento", key=f"del_doc_{d_id}"):
                                    eliminar_documento_repositorio(d_id)
                                    st.toast("Documento eliminado.")
                                    st.rerun()

    # ---------------------------------------------------------
    # 9. MÓDULO: RESPALDO Y RESTAURACIÓN
    # ---------------------------------------------------------
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.caption("Protección total de la información de la comunidad terapéutica")
        
        tab_down_db, tab_up_db = st.tabs(["📥 Descargar Respaldo (.db)", "📤 Restaurar Base de Datos"])
        
        with tab_down_db:
            st.subheader("📥 Generar Copia de Seguridad")
            st.write("Descargue una copia exacta del archivo de base de datos (`sistema_pacientes.db`). Este archivo contiene la totalidad de residentes, entrevistas, dosis, entregas, grupos y documentos.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    f_name_db = f"Sawabona_Respaldo_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                    st.download_button(
                        label="📥 Descargar Respaldo de Base de Datos (.db)",
                        data=f_db,
                        file_name=f_name_db,
                        mime="application/x-sqlite3",
                        type="primary",
                        use_container_width=True
                    )

        with tab_up_db:
            st.subheader("📤 Restaurar Base de Datos desde Respaldo")
            if not es_admin:
                st.error("🔒 Solo usuarios con rol Nivel 1 - Administrador pueden restaurar la base de datos.")
            else:
                uploaded_db = st.file_uploader("Selecciona el archivo de respaldo (.db):", type=["db", "sqlite3"])
                if uploaded_db:
                    st.warning("⚠️ **ADVERTENCIA**: Esta acción reemplazará toda la base de datos actual con la información del archivo de respaldo.")
                    if st.button("⚠️ Confirmar Restauración de Base de Datos", type="primary"):
                        bytes_db = uploaded_db.read()
                        with open(DB_FILE, "wb") as f_out:
                            f_out.write(bytes_db)
                        st.toast("🎉 ¡Base de datos restaurada exitosamente!")
                        st.success("¡Base de datos restaurada correctamente! Por favor reinicie la página.")
                        st.rerun()

    # ---------------------------------------------------------
    # 10. MÓDULO: SEGURIDAD Y USUARIOS
    # ---------------------------------------------------------
    elif menu == "⚙️ Seguridad y Usuarios":
        st.title("⚙️ Configuración de Seguridad y Usuarios del Sistema")
        
        tab_mi_pass, tab_adm_users, tab_adm_reqs = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Administración de Usuarios (Staff)", "⚙️ Configurar Requisitos por Etapa"])
        
        with tab_mi_pass:
            st.subheader("Cambiar mi Contraseña de Acceso")
            with st.form("form_cambiar_mi_pass"):
                p_actual = st.text_input("Contraseña Actual", type="password")
                p_nueva = st.text_input("Nueva Contraseña", type="password")
                p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p = st.form_submit_button("Actualizar mi Contraseña")
                
                if btn_p:
                    v_pass = verificar_login(st.session_state["username"], p_actual)
                    if not v_pass:
                        st.error("La contraseña actual es incorrecta.")
                    elif p_nueva != p_conf:
                        st.error("Las nuevas contraseñas no coinciden.")
                    elif len(p_nueva) < 4:
                        st.error("La nueva contraseña debe tener al menos 4 caracteres.")
                    else:
                        actualizar_password_usuario(st.session_state["username"], p_nueva)
                        st.toast("🎉 Contraseña actualizada.")
                        st.success("Contraseña actualizada correctamente.")

        with tab_adm_users:
            st.subheader("👥 Cuentas del Personal / Staff")
            if not es_admin:
                st.info("Solo el Administrador puede gestionar usuarios del sistema.")
            else:
                with st.form("form_nuevo_usuario_sys"):
                    st.markdown("**Crear nueva cuenta para el personal**")
                    c1, c2 = st.columns(2)
                    with c1:
                        u_sys_name = st.text_input("Usuario (Login) *").strip()
                        u_sys_nom = st.text_input("Nombre Completo *").strip()
                    with c2:
                        u_sys_pass = st.text_input("Contraseña Inicial *", type="password")
                        u_sys_rol = st.selectbox("Rol y Nivel de Acceso", [
                            "Nivel 1 - Administrador",
                            "Nivel 2 - Lectura y Escritura",
                            "Nivel 3 - Solo Lectura"
                        ])
                    btn_u_sys = st.form_submit_button("➕ Crear Cuenta de Usuario")
                    
                    if btn_u_sys:
                        if not u_sys_name or not u_sys_nom or not u_sys_pass:
                            st.error("Todos los campos son obligatorios.")
                        else:
                            try:
                                guardar_usuario_sistema(u_sys_name, u_sys_pass, u_sys_nom, u_sys_rol)
                                st.toast("🎉 Cuenta creada exitosamente.")
                                st.success(f"Cuenta para {u_sys_nom} creada.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al crear usuario: {e}")
                                
                st.markdown("---")
                u_rows = obtener_todos_usuarios_sistema()
                for ur in u_rows:
                    st.write(f"👤 **{ur[2]}** (`{ur[1]}`) | Rol: `{ur[3]}`")

        with tab_adm_reqs:
            st.subheader("⚙️ Configuración de Requisitos por Etapa")
            if not es_admin:
                st.info("Solo el Administrador puede modificar los requisitos de las etapas.")
            else:
                etapa_cfg = st.selectbox("Selecciona la Etapa a Configurar:", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
                reqs_c = obtener_requisitos_etapa(etapa_cfg)
                
                with st.form("form_add_req"):
                    new_req = st.text_input("Nombre del nuevo requisito:")
                    is_g = st.checkbox("Es un grupo terapéutico (se cuenta automáticamente)")
                    btn_r = st.form_submit_button("➕ Agregar Requisito")
                    if btn_r and new_req:
                        agregar_requisito_etapa(etapa_cfg, new_req, 1 if is_g else 0)
                        st.toast("Requisito agregado.")
                        st.rerun()
                        
                st.markdown("---")
                for r_item in reqs_c:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"• {r_item[1]} {'(Grupo)' if r_item[2]==1 else ''}")
                    with col2:
                        if st.button("🗑️ Eliminar", key=f"del_req_{r_item[0]}"):
                            eliminar_requisito_etapa(r_item[0])
                            st.toast("Requisito eliminado.")
                            st.rerun()

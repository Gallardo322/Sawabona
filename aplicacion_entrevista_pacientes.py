import streamlit as st
import sqlite3
import json
import hashlib
import os
import time
from datetime import datetime, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sawabona Shikoba - Sistema de Control y Consejería",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- UTILIDADES PDF ---
def clean_pdf_text(text):
    if not text:
        return ""
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "ñ": "n", "Ñ": "N", "ü": "u", "Ü": "U", "–": "-",
        "—": "-", "“": '"', "”": '"', "’": "'", "º": ".", "ª": "."
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios
    c.execute("CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, nombre_completo TEXT, rol TEXT DEFAULT 'staff')")
    
    # 2. Entrevistas / Pacientes Base
    c.execute("CREATE TABLE IF NOT EXISTS entrevistas (paciente_id TEXT PRIMARY KEY, expediente TEXT, fecha_registro TEXT, fecha_modificacion TEXT, usuario_registro TEXT, datos_json TEXT)")
    
    # 3. Fichas de Ingreso
    c.execute("CREATE TABLE IF NOT EXISTS fichas_ingreso (paciente_id TEXT PRIMARY KEY, expediente TEXT, datos_json TEXT, fecha_registro TEXT, usuario_registro TEXT)")
    
    # 4. Consejerías
    c.execute("CREATE TABLE IF NOT EXISTS consejerias (id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id TEXT, expediente TEXT, etapa TEXT, num_consejeria INTEGER, aspectos_trabajar TEXT, aspectos_proxima TEXT, fecha_proxima TEXT, exposicion TEXT, avance TEXT, sugerencia TEXT, fecha TEXT, usuario TEXT)")
    
    # 5. Grupos Terapéuticos
    c.execute("CREATE TABLE IF NOT EXISTS grupos_terapeuticos (id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id TEXT, etapa_paciente TEXT, tipo_grupo TEXT, fecha TEXT, desarrollo TEXT, devolucion TEXT, compromisos TEXT, usuario TEXT)")
    
    # 6. Medicamentos & Inventario
    c.execute("CREATE TABLE IF NOT EXISTS medicamentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL, gramaje TEXT, existencia INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS dosis_pacientes (id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id TEXT, medicamento_id INTEGER, dosis_diaria INTEGER, instrucciones TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS entregas_meds (id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id TEXT, medicamento_id INTEGER, cantidad INTEGER, fecha TEXT, usuario TEXT)")
    
    # 7. Repositorio & Carpetas
    c.execute("CREATE TABLE IF NOT EXISTS carpetas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS documentos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre_archivo TEXT NOT NULL, carpeta TEXT, contenido_blob BLOB, fecha_subida TEXT, usuario TEXT)")
    
    # Migraciones PRAGMA para asegurar columnas si la DB ya existía
    def add_col_if_missing(table, column, col_type):
        c.execute(f"PRAGMA table_info({table})")
        cols = [info[1] for info in c.fetchall()]
        if column not in cols:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            except Exception:
                pass

    add_col_if_missing("entrevistas", "expediente", "TEXT")
    add_col_if_missing("fichas_ingreso", "expediente", "TEXT")
    add_col_if_missing("grupos_terapeuticos", "etapa_paciente", "TEXT")
    add_col_if_missing("consejerias", "expediente", "TEXT")
    add_col_if_missing("consejerias", "aspectos_trabajar", "TEXT")
    add_col_if_missing("consejerias", "aspectos_proxima", "TEXT")
    add_col_if_missing("consejerias", "fecha_proxima", "TEXT")
    add_col_if_missing("consejerias", "exposicion", "TEXT")
    add_col_if_missing("consejerias", "avance", "TEXT")
    add_col_if_missing("consejerias", "sugerencia", "TEXT")
    add_col_if_missing("usuarios", "rol", "TEXT DEFAULT 'staff'")

    # Crear carpetas por defecto
    carpetas_def = ["📁 Documentos Generales", "📑 Expedientes Clínicos", "📜 Reglamentos y Formatos", "🩺 Evaluaciones Médicas"]
    for carp in carpetas_def:
        c.execute("INSERT OR IGNORE INTO carpetas (nombre) VALUES (?)", (carp,))

    # Usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'admin'))
    
    conn.commit()
    conn.close()

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

def obtener_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        pid = r[0]
        if pid and pid.startswith("PAC-"):
            try:
                num = int(pid.replace("PAC-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"PAC-{max_num + 1:03d}"

def existe_expediente(expediente, paciente_id_actual=None):
    if not expediente or not str(expediente).strip():
        return False, None
    exp_str = str(expediente).strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ?', (exp_str,))
    row = c.fetchone()
    conn.close()
    if row and row[0] != paciente_id_actual:
        dj = json.loads(row[1]) if row[1] else {}
        nombre = dj.get("nombre", row[0])
        return True, f"El número de Expediente '{exp_str}' ya pertenece al residente: {nombre} ({row[0]})"
    return False, None

def guardar_entrevista(paciente_id, expediente, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    exp_str = str(expediente).strip() if expediente else ""
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute("UPDATE entrevistas SET expediente = ?, fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?",
                  (exp_str, fecha_actual, datos_json, paciente_id))
    else:
        c.execute("INSERT INTO entrevistas (paciente_id, expediente, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?, ?)",
                  (paciente_id, exp_str, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro, expediente FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3], row[4]
    return None, None, None, None, None

def listar_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, datos_json, fecha_registro FROM entrevistas ORDER BY fecha_registro DESC')
    rows = c.fetchall()
    conn.close()
    
    pacientes = []
    for r in rows:
        dj = json.loads(r[2]) if r[2] else {}
        exp_txt = f"Exp: {r[1]}" if r[1] else "Exp: S/N"
        pacientes.append({
            "paciente_id": r[0],
            "expediente": r[1] or "",
            "etiqueta": f"{r[0]} | {exp_txt} - {dj.get('nombre', 'Sin Nombre')}",
            "nombre": dj.get('nombre', 'Sin Nombre'),
            "fecha_nacimiento": dj.get('fecha_nacimiento', ''),
            "sexo": dj.get('sexo', 'No especificado'),
            "fecha_ingreso": dj.get('fecha_ingreso_real', dj.get('fecha_ingreso', '')),
            "etapa_actual": dj.get('etapa_actual', 'ACOGIDA'),
            "fecha_inicio_etapa": dj.get('fecha_inicio_etapa', ''),
            "hermano_mayor": dj.get('hermano_mayor', ''),
            "datos_completos": dj
        })
    return pacientes

# --- CATÁLOGO DE TEMAS DE CONSEJERÍA ---
CONSEJERIAS_CATALOGO = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "IDENTIFICACION": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA / MANEJO DEL TIEMPO LIBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "ELABORACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJERIA) PREVENCIÓN DE RECAÍDAS.",
        "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
        "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
    ],
    "CONSOLIDACION": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
        "(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
    ],
    "SERVICIO SOCIAL": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- GENERADORES DE PDF ---
class PDF_Sawabona(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.set_text_color(27, 94, 32)
        self.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), 0, 1, "C")
        self.set_font("Arial", "I", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, clean_pdf_text("Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones"), 0, 1, "C")
        self.line(10, 24, 200, 24)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, clean_pdf_text(f"Página {self.page_no()} | Documento Confidencial - Uso Clínico Interno"), 0, 0, "C")

def generar_pdf_ficha_ingreso(p_info, f_datos):
    pdf = PDF_Sawabona()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y CONTRATO DE ADMISIÓN"), 0, 1, "C")
    pdf.ln(3)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(230, 245, 230)
    
    exp_display = p_info.get('expediente') or "S/N"
    pdf.cell(0, 6, clean_pdf_text(f"1. DATOS DE IDENTIFICACIÓN (EXPEDIENTE: {exp_display})"), 1, 1, "L", True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"Paciente: {p_info.get('nombre')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Folio Interno: {p_info.get('paciente_id')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Fecha Nacimiento: {p_info.get('fecha_nacimiento')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Sexo: {p_info.get('sexo')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Estado Civil: {f_datos.get('estado_civil', '')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Escolaridad: {f_datos.get('escolaridad', '')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Ocupacion: {f_datos.get('ocupacion', '')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Religion: {f_datos.get('religion', '')}"), 0, 1)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Domicilio: {f_datos.get('domicilio', '')}"))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("2. RESPONSABLE FAMILIAR"), 1, 1, "L", True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"Nombre: {f_datos.get('responsable_nombre', '')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Parentesco: {f_datos.get('responsable_parentesco', '')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Telefono: {f_datos.get('responsable_telefono', '')}"), 0, 1)
    pdf.ln(2)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("3. TÉRMINOS ECONÓMICOS Y SUCURSAL"), 1, 1, "L", True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(95, 5, clean_pdf_text(f"Sucursal: {f_datos.get('sucursal', '')}"), 0, 0)
    pdf.cell(95, 5, clean_pdf_text(f"Modalidad: {f_datos.get('modalidad', 'VOLUNTARIO')}"), 0, 1)
    pdf.cell(63, 5, clean_pdf_text(f"Costo Ingreso: ${f_datos.get('costo_ingreso', 4500):,.2f}"), 0, 0)
    pdf.cell(63, 5, clean_pdf_text(f"Mensualidad: ${f_datos.get('costo_mensual', 6000):,.2f}"), 0, 0)
    pdf.cell(64, 5, clean_pdf_text(f"Pagare: ${f_datos.get('costo_pagare', 42000):,.2f}"), 0, 1)
    pdf.ln(3)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("DECLARACIÓN DE CONFORMIDAD Y AUTORIZACIÓN (NOM-028-SSA2-2009):"), 0, 1)
    pdf.set_font("Arial", "", 8)
    clausula = ("El suscriptor declara que ingresa al residente de manera voluntaria/representada para recibir "
                "tratamiento integral en adicciones en la Comunidad Terapéutica Sawabona Shikoba A.C., "
                "aceptando el reglamento interno, los costos estipulados y participando activamente en las sesiones de "
                "consejería y reinserción familiar.")
    pdf.multi_cell(0, 4, clean_pdf_text(clausula))
    pdf.ln(15)

    pdf.cell(90, 5, "________________________________________", 0, 0, "C")
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, "________________________________________", 0, 1, "C")
    pdf.set_font("Arial", "B", 8)
    pdf.cell(90, 5, clean_pdf_text("Firma del Responsable Familiar"), 0, 0, "C")
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, clean_pdf_text("Director / Encargado del Establecimiento"), 0, 1, "C")
    
    return bytes(pdf.output())

def generar_pdf_consejeria(p_info, c_datos):
    pdf = PDF_Sawabona()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, clean_pdf_text(f"HOJA DE CONSEJERÍA INDIVIDUAL #{c_datos.get('num_consejeria', 1)}"), 0, 1, "C")
    pdf.ln(3)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(230, 245, 230)
    
    exp_display = p_info.get('expediente') or "S/N"
    pdf.cell(0, 6, clean_pdf_text(f"INFORMACIÓN DEL PACIENTE (EXPEDIENTE: {exp_display})"), 1, 1, "L", True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(100, 5, clean_pdf_text(f"Nombre: {p_info.get('nombre')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Etapa: {c_datos.get('etapa')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Edad: {c_datos.get('edad', '')} anos"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Sexo: {p_info.get('sexo')}"), 0, 1)
    pdf.cell(100, 5, clean_pdf_text(f"Fecha Sesion: {c_datos.get('fecha')}"), 0, 0)
    pdf.cell(90, 5, clean_pdf_text(f"Proxima Sesion: {c_datos.get('fecha_proxima')}"), 0, 1)
    pdf.ln(3)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("TEMAS Y EVALUACIÓN CLÍNICA"), 1, 1, "L", True)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Aspecto Trabajado:"), 0, 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(c_datos.get('aspectos_trabajar', '')))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Exposición del Paciente:"), 0, 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(c_datos.get('exposicion', '')))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Avance / Retroceso Registrado:"), 0, 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(c_datos.get('avance', '')))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Sugerencias y Compromisos:"), 0, 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(c_datos.get('sugerencia', '')))
    pdf.ln(2)

    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, clean_pdf_text("Proximo Aspecto a Trabajar:"), 0, 1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, clean_pdf_text(c_datos.get('aspectos_proxima', '')))
    pdf.ln(15)

    pdf.cell(90, 5, "________________________________________", 0, 0, "C")
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, "________________________________________", 0, 1, "C")
    pdf.set_font("Arial", "B", 8)
    pdf.cell(90, 5, clean_pdf_text("Firma del Consejero / Terapeuta"), 0, 0, "C")
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, clean_pdf_text("Firma del Residente"), 0, 1, "C")

    return bytes(pdf.output())

# --- PROGRAMA PRINCIPAL ---
def main():
    init_db()

    # Control de Sesión
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "nombre_completo" not in st.session_state:
        st.session_state["nombre_completo"] = ""
    if "rol" not in st.session_state:
        st.session_state["rol"] = "staff"

    # Control de Inactividad (10 minutos = 600 segundos)
    now_ts = time.time()
    if st.session_state["logged_in"]:
        if "ultima_actividad" in st.session_state:
            inactivo_s = now_ts - st.session_state["ultima_actividad"]
            if inactivo_s > 600:
                st.session_state["logged_in"] = False
                st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
                st.rerun()
        st.session_state["ultima_actividad"] = now_ts

        # Script de autochequeo de inactividad en frontend (600s)
        st.markdown("""
            <script>
            var lastAct = Date.now();
            function resetAct() { lastAct = Date.now(); }
            window.onload = resetAct;
            window.onmousemove = resetAct;
            window.onmousedown = resetAct;
            window.onclick = resetAct;
            window.onscroll = resetAct;
            window.onkeypress = resetAct;
            setInterval(function() {
                if (Date.now() - lastAct > 600000) {
                    window.location.reload();
                }
            }, 30000);
            </script>
        """, unsafe_allow_html=True)

    # --- PANTALLA DE ACCESO (LOGIN) ---
    if not st.session_state["logged_in"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h1 style='text-align: center; color: #1b5e20;'>🌱 Sawabona Shikoba A.C.</h1>", unsafe_allow_html=True)
            st.markdown("<h3 style='text-align: center; color: #424242;'>Sistema Integral de Control y Consejería</h3>", unsafe_allow_html=True)
            st.markdown("<hr>", unsafe_allow_html=True)
            
            with st.form("form_login"):
                u_input = st.text_input("👤 Usuario", value="admin")
                p_input = st.text_input("🔑 Contraseña", type="password", value="admin123")
                btn_ingresar = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)

                if btn_ingresar:
                    res = verificar_login(u_input, p_input)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1] or res[0]
                        st.session_state["rol"] = res[2] or "staff"
                        st.session_state["ultima_actividad"] = time.time()
                        st.balloons()
                        st.toast("¡Bienvenido al sistema!", icon="🎉")
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos.")
        return

    # --- ENCABEZADO Y LOGO DE LA PÁGINA PRINCIPAL ---
    st.markdown('''
        <div style="background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 8px solid #2e7d32; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <h1 style="color: #1b5e20; margin: 0; padding: 0; font-size: 28px;">🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>
                    <p style="color: #388e3c; margin: 5px 0 0 0; font-weight: bold; font-size: 14px;">Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</p>
                </div>
                <div style="text-align: right;">
                    <span style="background-color: #2e7d32; color: white; padding: 6px 12px; border-radius: 20px; font-weight: bold; font-size: 12px;">SISTEMA ACTIVO</span>
                </div>
            </div>
        </div>
    ''', unsafe_allow_html=True)

    # --- BARRA LATERAL (SIDEBAR & NAVEGACIÓN COMPLETA) ---
    st.sidebar.markdown("<h2 style='color: #1b5e20;'>🌱 Sawabona Shikoba</h2>", unsafe_allow_html=True)
    st.sidebar.caption(f"👤 **{st.session_state['nombre_completo']}** ({st.session_state['rol'].upper()})")
    
    OPCIONES_MENU = [
        "🏠 Inicio / Tablero General",
        "👤 Registro y Edición de Usuarios",
        "📄 Ficha de Ingreso y Admisión",
        "📝 Entrevista Inicial de Consejería",
        "📝 Consejerías Individuales",
        "🎯 Gestión de Etapas & Proceso",
        "🗣️ Grupos Terapéuticos",
        "💊 Control de Medicamentos",
        "📁 Repositorio de Documentos",
        "🔍 Buscar y Listar Pacientes",
        "⚙️ Configuración y Seguridad",
        "📦 Respaldo y Restauración"
    ]
    
    menu = st.sidebar.radio("📌 Menú Principal", OPCIONES_MENU)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    pacientes_act = listar_pacientes()

    # --- 1. INICIO / TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero Principal")
        st.markdown("Bienvenido al sistema integral de expedientes clínicos, consejería y control operativo.")
        st.markdown("---")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Residentes Activos", len(pacientes_act))
        
        # Conteo por etapa
        etapas_cnt = {"ACOGIDA": 0, "IDENTIFICACION": 0, "ELABORACION": 0, "CONSOLIDACION": 0, "SERVICIO SOCIAL": 0}
        for p in pacientes_act:
            e = p.get("etapa_actual", "ACOGIDA")
            if e in etapas_cnt:
                etapas_cnt[e] += 1
        
        c2.metric("🌱 En Acogida", etapas_cnt["ACOGIDA"])
        c3.metric("🔍 En Identificación", etapas_cnt["IDENTIFICACION"])
        c4.metric("🛠️ En Elaboración / Mas", etapas_cnt["ELABORACION"] + etapas_cnt["CONSOLIDACION"] + etapas_cnt["SERVICIO SOCIAL"])
        
        st.markdown("### 📋 Directorio Rápido de Residentes")
        if pacientes_act:
            st.dataframe([{
                "Folio": p["paciente_id"],
                "Expediente": p["expediente"] or "S/N",
                "Nombre": p["nombre"],
                "Etapa Actual": p["etapa_actual"],
                "Fecha Ingreso": p["fecha_ingreso"]
            } for p in pacientes_act], use_container_width=True)
        else:
            st.info("No hay residentes registrados aún en la base de datos.")

    # --- 2. REGISTRO Y EDICIÓN DE USUARIOS ---
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Residentes")
        
        tab1, tab2 = st.tabs(["➕ Registrar Nuevo Residente", "✏️ Editar Residente Existente"])
        
        with tab1:
            st.subheader("Alta General de Residente")
            folio_sug = obtener_siguiente_folio()
            
            with st.form("form_alta_residente"):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    st.text_input("Folio Interno (Autoincrementable)", value=folio_sug, disabled=True)
                    exp_val = st.text_input("Número de Expediente (Único, editable manual)", help="Opcional. Dejar en blanco si no se tiene a la mano.")
                    nombre_val = st.text_input("Nombre Completo del Residente *")
                    fnac_val = st.date_input("Fecha de Nacimiento", value=datetime(1995, 1, 1))
                with col_f2:
                    sexo_val = st.selectbox("Sexo", ["Masculino", "Femenino"])
                    fing_val = st.date_input("Fecha de Ingreso Real a la Comunidad", value=datetime.now())
                    etapa_val = st.selectbox("Etapa Inicial", ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"])
                    fietapa_val = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.now())
                
                btn_guardar_nuevo = st.form_submit_button("💾 Guardar y Registrar Residente", use_container_width=True)
                
                if btn_guardar_nuevo:
                    if not nombre_val.strip():
                        st.error("⚠️ El nombre del residente es obligatorio.")
                    else:
                        dup, msg = existe_expediente(exp_val)
                        if dup:
                            st.error(f"❌ {msg}")
                        else:
                            datos_gen = {
                                "nombre": nombre_val.strip(),
                                "fecha_nacimiento": str(fnac_val),
                                "sexo": sexo_val,
                                "fecha_ingreso_real": str(fing_val),
                                "etapa_actual": etapa_val,
                                "fecha_inicio_etapa": str(fietapa_val)
                            }
                            guardar_entrevista(folio_sug, exp_val.strip(), datos_gen, st.session_state["username"])
                            st.balloons()
                            st.toast(f"¡Residente {nombre_val} registrado con éxito!", icon="🎉")
                            st.success(f"✅ Residente guardado con Folio {folio_sug} y Expediente {exp_val or 'S/N'}.")
                            st.rerun()

        with tab2:
            st.subheader("Editar Datos de Residente")
            if not pacientes_act:
                st.info("No hay residentes registrados para editar.")
            else:
                sel_p = st.selectbox("Seleccione Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"])
                if sel_p:
                    p_id = sel_p["paciente_id"]
                    d_com, f_reg, f_mod, u_reg, exp_cur = obtener_entrevista(p_id)
                    d_com = d_com or {}
                    
                    with st.form("form_edit_residente"):
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            st.text_input("Folio Interno", value=p_id, disabled=True)
                            exp_edit = st.text_input("Número de Expediente", value=exp_cur or "")
                            nom_edit = st.text_input("Nombre Completo", value=d_com.get("nombre", ""))
                            try:
                                fn_default = datetime.strptime(d_com.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d")
                            except Exception:
                                fn_default = datetime(1995, 1, 1)
                            fnac_edit = st.date_input("Fecha Nacimiento", value=fn_default)
                        with col_e2:
                            sex_edit = st.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if d_com.get("sexo") == "Masculino" else 1)
                            try:
                                fi_default = datetime.strptime(d_com.get("fecha_ingreso_real", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
                            except Exception:
                                fi_default = datetime.now()
                            fing_edit = st.date_input("Fecha Ingreso Real", value=fi_default)
                            
                            etapas_list = ["ACOGIDA", "IDENTIFICACION", "ELABORACION", "CONSOLIDACION", "SERVICIO SOCIAL"]
                            et_curr = d_com.get("etapa_actual", "ACOGIDA")
                            idx_et = etapas_list.index(et_curr) if et_curr in etapas_list else 0
                            etapa_edit = st.selectbox("Etapa Actual", etapas_list, index=idx_et)
                            
                            try:
                                fie_default = datetime.strptime(d_com.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
                            except Exception:
                                fie_default = datetime.now()
                            fietapa_edit = st.date_input("Fecha Inicio Etapa", value=fie_default)

                        btn_mod = st.form_submit_button("🔄 Actualizar Residente", use_container_width=True)
                        if btn_mod:
                            dup, msg = existe_expediente(exp_edit, p_id)
                            if dup:
                                st.error(f"❌ {msg}")
                            else:
                                d_com["nombre"] = nom_edit.strip()
                                d_com["fecha_nacimiento"] = str(fnac_edit)
                                d_com["sexo"] = sex_edit
                                d_com["fecha_ingreso_real"] = str(fing_edit)
                                d_com["etapa_actual"] = etapa_edit
                                d_com["fecha_inicio_etapa"] = str(fietapa_edit)
                                
                                guardar_entrevista(p_id, exp_edit.strip(), d_com, st.session_state["username"])
                                st.balloons()
                                st.toast("¡Datos del residente actualizados!", icon="🎉")
                                st.success("✅ Residente modificado correctamente.")
                                st.rerun()

    # --- 3. FICHA DE INGRESO Y ADMISIÓN ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Contrato de Admisión")
        
        if not pacientes_act:
            st.info("Debe registrar al menos un residente en 'Registro de Usuarios' para llenar la Ficha de Ingreso.")
        else:
            sel_p = st.selectbox("Seleccione Residente para la Ficha", options=pacientes_act, format_func=lambda x: x["etiqueta"])
            p_id = sel_p["paciente_id"]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?', (p_id,))
            row_f = c.fetchone()
            conn.close()
            f_saved = json.loads(row_f[0]) if row_f else {}

            tab1, tab2 = st.tabs(["📝 Capturar Ficha", "🖨️ Ver / Imprimir Contrato PDF"])

            with tab1:
                with st.form("form_ficha_ingreso"):
                    st.subheader("1. Responsable Familiar")
                    c_f1, c_f2 = st.columns(2)
                    resp_nom = c_f1.text_input("Nombre del Responsable Familiar *", value=f_saved.get("responsable_nombre", ""))
                    resp_par = c_f2.text_input("Parentesco *", value=f_saved.get("responsable_parentesco", "PADRE / MADRE"))
                    resp_tel = c_f1.text_input("Teléfono de Contacto", value=f_saved.get("responsable_telefono", ""))

                    st.subheader("2. Datos Complementarios")
                    ec_val = c_f1.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)"], index=0)
                    esc_val = c_f2.selectbox("Escolaridad", ["Primaria", "Secundaria", "Preparatoria", "Universidad", "Ninguna"], index=1)
                    rel_val = c_f1.text_input("Religión", value=f_saved.get("religion", "Católica"))
                    ocu_val = c_f2.text_input("Ocupación", value=f_saved.get("ocupacion", "Empleado"))
                    dom_val = st.text_area("Domicilio Completo", value=f_saved.get("domicilio", ""))

                    st.subheader("3. Términos Financieros")
                    c_m1, c_m2, c_m3 = st.columns(3)
                    suc_val = c_m1.text_input("Sucursal", value=f_saved.get("sucursal", "Matriz Sawabona"))
                    mod_val = c_m2.selectbox("Modalidad", ["VOLUNTARIO", "INVOLUNTARIO"], index=0)
                    cost_ing = c_m3.number_input("Costo de Ingreso ($)", value=float(f_saved.get("costo_ingreso", 4500.0)))
                    cost_men = c_m1.number_input("Mensualidad ($)", value=float(f_saved.get("costo_mensual", 6000.0)))
                    cost_pag = c_m2.number_input("Pagaré ($)", value=float(f_saved.get("costo_pagare", 42000.0)))

                    btn_guardar_f = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                    if btn_guardar_f:
                        f_data = {
                            "responsable_nombre": resp_nom,
                            "responsable_parentesco": resp_par,
                            "responsable_telefono": resp_tel,
                            "estado_civil": ec_val,
                            "escolaridad": esc_val,
                            "religion": rel_val,
                            "ocupacion": ocu_val,
                            "domicilio": dom_val,
                            "sucursal": suc_val,
                            "modalidad": mod_val,
                            "costo_ingreso": cost_ing,
                            "costo_mensual": cost_men,
                            "costo_pagare": cost_pag
                        }
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO fichas_ingreso (paciente_id, expediente, datos_json, fecha_registro, usuario_registro)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(paciente_id) DO UPDATE SET
                            expediente = excluded.expediente,
                            datos_json = excluded.datos_json,
                            fecha_registro = excluded.fecha_registro
                        ''', (p_id, sel_p["expediente"], json.dumps(f_data, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d"), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("¡Ficha de Ingreso guardada!", icon="🎉")
                        st.success("✅ Ficha registrada de forma exitosa.")
                        st.rerun()

            with tab2:
                if not f_saved:
                    st.warning("⚠️ Primero capture y guarde la Ficha de Ingreso en la pestaña anterior.")
                else:
                    st.success("📄 Ficha de Ingreso lista para impresión.")
                    pdf_bytes = generar_pdf_ficha_ingreso(sel_p, f_saved)
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso en PDF",
                        data=pdf_bytes,
                        file_name=f"Ficha_Ingreso_{sel_p['expediente'] or sel_p['paciente_id']}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # --- 4. ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        if not pacientes_act:
            st.info("Debe registrar al menos un residente para llenar la entrevista inicial.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"])
            p_id = sel_p["paciente_id"]
            d_ent, _, _, _, _ = obtener_entrevista(p_id)
            d_ent = d_ent or {}

            with st.form("form_entrevista_clinica"):
                st.subheader("1. Antecedentes de Consumo")
                sust_prin = st.text_input("Sustancia de Impacto Principal", value=d_ent.get("sustancia_principal", ""))
                edad_inicio = st.number_input("Edad de Inicio de Consumo", value=int(d_ent.get("edad_inicio", 15)))
                frecuencia = st.text_input("Frecuencia de Consumo", value=d_ent.get("frecuencia", "Diario"))
                
                st.subheader("2. Historial Médico y Psicología")
                trats_prevs = st.text_area("Tratamientos Previos / Internamientos", value=d_ent.get("tratamientos_previos", ""))
                diag_medico = st.text_area("Diagnósticos Médicos o Psiquiátricos", value=d_ent.get("diag_medico", ""))

                st.subheader("3. Apoyo Familiar y Redes")
                red_apoyo = st.text_area("Red de Apoyo Familiar", value=d_ent.get("red_apoyo", ""))

                btn_guardar_ent = st.form_submit_button("💾 Guardar Entrevista Clínica", use_container_width=True)
                if btn_guardar_ent:
                    d_ent["sustancia_principal"] = sust_prin
                    d_ent["edad_inicio"] = edad_inicio
                    d_ent["frecuencia"] = frecuencia
                    d_ent["tratamientos_previos"] = trats_prevs
                    d_ent["diag_medico"] = diag_medico
                    d_ent["red_apoyo"] = red_apoyo

                    guardar_entrevista(p_id, sel_p["expediente"], d_ent, st.session_state["username"])
                    st.balloons()
                    st.toast("¡Entrevista de consejería guardada!", icon="🎉")
                    st.success("✅ Evaluación inicial almacenada.")
                    st.rerun()

    # --- 5. CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Control de Consejerías Individuales")
        
        if not pacientes_act:
            st.info("Debe registrar al menos un residente para realizar consejerías.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"])
            p_id = sel_p["paciente_id"]
            etapa_act = sel_p.get("etapa_actual", "ACOGIDA")
            
            temas_etapa = CONSEJERIAS_CATALOGO.get(etapa_act, CONSEJERIAS_CATALOGO["ACOGIDA"])
            num_cons_opt = list(range(1, len(temas_etapa) + 1))
            
            st.info(f"📍 **Etapa Actual del Residente:** {etapa_act} ({len(temas_etapa)} consejerías programadas)")
            
            num_cons_sel = st.selectbox("Número de Consejería a Capturar / Consultar", num_cons_opt, format_func=lambda x: f"Consejería #{x}")
            idx_tema = num_cons_sel - 1
            tema_actual = temas_etapa[idx_tema]
            tema_proximo = temas_etapa[idx_tema + 1] if (idx_tema + 1) < len(temas_etapa) else "FIN DE ETAPA / PROMOCIÓN"
            
            # Consultar si esta consejería ya fue capturada previamente
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                FROM consejerias
                WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
            ''', (p_id, etapa_act, num_cons_sel))
            c_row = c.fetchone()
            conn.close()

            # Cálculo de edad
            fnac_str = sel_p.get("fecha_nacimiento", "")
            edad_calc = ""
            if fnac_str:
                try:
                    fn = datetime.strptime(fnac_str, "%Y-%m-%d")
                    edad_calc = str((datetime.now() - fn).days // 365)
                except Exception:
                    edad_calc = ""

            tab1, tab2 = st.tabs(["📝 Formulario de Sesión", "📜 Historial e Impresión PDF"])

            with tab1:
                if c_row:
                    st.success(f"ℹ️ Mostrando datos guardados de la Consejería #{num_cons_sel}")
                    v_asp_trab = c_row[0] or tema_actual
                    v_asp_prox = c_row[1] or tema_proximo
                    v_f_prox = c_row[2] or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    v_expo = c_row[3] or ""
                    v_avan = c_row[4] or ""
                    v_sug = c_row[5] or ""
                    v_fecha = c_row[6] or datetime.now().strftime("%Y-%m-%d")
                else:
                    st.info(f"🌱 Capturando NUEVA Consejería #{num_cons_sel} (Campos vacíos)")
                    v_asp_trab = tema_actual
                    v_asp_prox = tema_proximo
                    v_f_prox = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    v_expo = ""
                    v_avan = ""
                    v_sug = ""
                    v_fecha = datetime.now().strftime("%Y-%m-%d")

                with st.form(f"form_consejeria_{p_id}_{etapa_act}_{num_cons_sel}"):
                    c_c1, c_c2, c_c3 = st.columns(3)
                    c_c1.text_input("Nombre del Residente", value=sel_p["nombre"], disabled=True)
                    c_c2.text_input("Expediente", value=sel_p["expediente"] or "S/N", disabled=True)
                    c_c3.text_input("Etapa", value=etapa_act, disabled=True)

                    c_d1, c_d2, c_d3 = st.columns(3)
                    c_d1.text_input("Edad", value=edad_calc, disabled=True)
                    c_d2.text_input("Sexo", value=sel_p["sexo"], disabled=True)
                    
                    try:
                        f_ses_val = datetime.strptime(v_fecha, "%Y-%m-%d")
                    except Exception:
                        f_ses_val = datetime.now()
                    c_d3.date_input("Fecha de la Sesión", value=f_ses_val, key="f_ses_input")

                    st.text_area("Aspectos a Trabajar (Tema Oficial)", value=v_asp_trab)
                    expo_input = st.text_area("Exposición del Paciente (Notas clínicas)", value=v_expo, height=120)
                    avan_input = st.text_area("Avance / Retroceso Registrado", value=v_avan, height=100)
                    sug_input = st.text_area("Sugerencias y Compromisos", value=v_sug, height=100)

                    st.text_area("Aspectos a Trabajar en Próxima Consejería", value=v_asp_prox)
                    
                    try:
                        fp_val = datetime.strptime(v_f_prox, "%Y-%m-%d")
                    except Exception:
                        fp_val = datetime.now() + timedelta(days=7)
                    f_prox_input = st.date_input("Fecha de Próxima Consejería (+7 días sug.)", value=fp_val, key="f_prox_input")

                    btn_guardar_cons = st.form_submit_button("💾 Guardar Consejería Individual", use_container_width=True)

                    if btn_guardar_cons:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO consejerias 
                            (paciente_id, expediente, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            p_id, sel_p["expediente"], etapa_act, num_cons_sel,
                            v_asp_trab, v_asp_prox, str(f_prox_input),
                            expo_input, avan_input, sug_input,
                            datetime.now().strftime("%Y-%m-%d"), st.session_state["username"]
                        ))
                        conn.commit()
                        conn.close()

                        st.balloons()
                        st.toast(f"¡Consejería #{num_cons_sel} guardada con éxito!", icon="🎉")
                        st.success("✅ Registro almacenado correctamente.")
                        st.rerun()

            with tab2:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT num_consejeria, fecha, aspectos_trabajar, exposicion, avance, sugerencia, aspectos_proxima, fecha_proxima
                    FROM consejerias
                    WHERE paciente_id = ? AND etapa = ?
                    ORDER BY num_consejeria ASC
                ''', (p_id, etapa_act))
                rows_cons = c.fetchall()
                conn.close()

                if not rows_cons:
                    st.info("No hay consejerías registradas aún en esta etapa.")
                else:
                    for r_c in rows_cons:
                        with st.expander(f"📋 Consejería #{r_c[0]} - Fecha: {r_c[1]}"):
                            st.write(f"**Tema:** {r_c[2]}")
                            st.write(f"**Exposición:** {r_c[3]}")
                            st.write(f"**Avance/Retroceso:** {r_c[4]}")
                            st.write(f"**Sugerencia:** {r_c[5]}")
                            st.write(f"**Próximo Tema:** {r_c[6]} (Fecha: {r_c[7]})")
                            
                            c_dict = {
                                "num_consejeria": r_c[0],
                                "fecha": r_c[1],
                                "etapa": etapa_act,
                                "edad": edad_calc,
                                "aspectos_trabajar": r_c[2],
                                "exposicion": r_c[3],
                                "avance": r_c[4],
                                "sugerencia": r_c[5],
                                "aspectos_proxima": r_c[6],
                                "fecha_proxima": r_c[7]
                            }
                            pdf_c_bytes = generar_pdf_consejeria(sel_p, c_dict)
                            st.download_button(
                                label=f"🖨️ Descargar PDF Consejería #{r_c[0]}",
                                data=pdf_c_bytes,
                                file_name=f"Consejeria_{r_c[0]}_{sel_p['expediente'] or p_id}.pdf",
                                mime="application/pdf",
                                key=f"dl_c_{p_id}_{r_c[0]}"
                            )

    # --- 6. GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Evaluación de Etapas y Alertas de Rezago")
        
        if not pacientes_act:
            st.info("No hay residentes registrados para evaluar.")
        else:
            sel_p = st.selectbox("Seleccione Residente para Diagnóstico", options=pacientes_act, format_func=lambda x: x["etiqueta"])
            p_id = sel_p["paciente_id"]
            etapa_act = sel_p.get("etapa_actual", "ACOGIDA")
            
            # Cálculo de días
            fing_str = sel_p.get("fecha_ingreso", datetime.now().strftime("%Y-%m-%d"))
            fiet_str = sel_p.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d"))
            
            try:
                d_tot = (datetime.now() - datetime.strptime(fing_str, "%Y-%m-%d")).days
            except Exception:
                d_tot = 0
            try:
                d_etapa = (datetime.now() - datetime.strptime(fiet_str, "%Y-%m-%d")).days
            except Exception:
                d_etapa = 0

            duraciones_std = {"ACOGIDA": 30, "IDENTIFICACION": 60, "ELABORACION": 60, "CONSOLIDACION": 60, "SERVICIO SOCIAL": 60}
            std_dias = duraciones_std.get(etapa_act, 30)
            
            st.markdown("---")
            col_d1, col_d2 = st.columns(2)
            col_d1.metric("🗓️ Días Totales en Comunidad", f"{d_tot} días")
            col_d2.metric(f"⏱️ Días en Etapa {etapa_act}", f"{d_etapa} / {std_dias} días est.")

            if d_etapa > std_dias:
                exceso = d_etapa - std_dias
                st.error(f"🚨 **ALERTA CLINICA DE REZAGO / ESTANCAMIENTO**: El residente lleva **{d_tot} días internado** y suma **{d_etapa} días en {etapa_act}** (Duración estimada: {std_dias} días). Se ha excedido por **+{exceso} días** sin haber sido promovido.")
            else:
                st.success("✅ Tiempo en etapa dentro del rango estándar estipulado.")

            st.markdown("### 📋 Checklist de Requisitos para Promoción")
            
            # Consultar consejerías y grupos en DB
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (p_id, etapa_act))
            cnt_cons = c.fetchone()[0]
            
            try:
                c.execute('SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?', (p_id, etapa_act))
                cnt_grup = c.fetchone()[0]
            except Exception:
                cnt_grup = 0
            conn.close()

            temas_req = len(CONSEJERIAS_CATALOGO.get(etapa_act, []))
            
            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                c_c_ok = cnt_cons >= temas_req
                st.checkbox(f"Consejerías Cumplidas ({cnt_cons} de {temas_req})", value=c_c_ok, disabled=True)
                st.checkbox(f"Grupos Terapéuticos Registrados ({cnt_grup} asistidos)", value=cnt_grup >= 4, disabled=True)
            with col_chk2:
                chk_auto = st.checkbox("Autobiografía / Carta de Historia Entregada", value=False)
                chk_reg = st.checkbox("Reglas de Convivencia Aceptadas", value=True)

            can_promote = c_c_ok and chk_auto and chk_reg
            st.markdown("---")
            if st.button(f"🎉 Promover Residente a Siguiente Etapa", disabled=not can_promote, use_container_width=True):
                siguientes = {"ACOGIDA": "IDENTIFICACION", "IDENTIFICACION": "ELABORACION", "ELABORACION": "CONSOLIDACION", "CONSOLIDACION": "SERVICIO SOCIAL"}
                nueva_e = siguientes.get(etapa_act, etapa_act)
                
                d_com, _, _, _, exp_c = obtener_entrevista(p_id)
                d_com["etapa_actual"] = nueva_e
                d_com["fecha_inicio_etapa"] = datetime.now().strftime("%Y-%m-%d")
                
                guardar_entrevista(p_id, exp_c, d_com, st.session_state["username"])
                st.balloons()
                st.toast(f"¡Residente promovido a {nueva_e}!", icon="🎉")
                st.success(f"✅ ¡Promoción exitosa a la etapa {nueva_e}!")
                st.rerun()

    # --- 7. GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Control de Grupos Terapéuticos")
        if not pacientes_act:
            st.info("Debe registrar residentes para capturar grupos.")
        else:
            sel_p = st.selectbox("Seleccione Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"])
            p_id = sel_p["paciente_id"]
            etapa_act = sel_p.get("etapa_actual", "ACOGIDA")

            with st.form("form_grupo_terapeutico"):
                t_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Retroalimentación"])
                desarrollo = st.text_area("Desarrollo de la Sesión")
                devolucion = st.text_area("Devolución / Observaciones")
                compromisos = st.text_area("Compromisos Adquiridos")

                btn_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                if btn_g:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (paciente_id, etapa_paciente, tipo_grupo, fecha, desarrollo, devolucion, compromisos, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p_id, etapa_act, t_grupo, datetime.now().strftime("%Y-%m-%d"), desarrollo, devolucion, compromisos, st.session_state["username"]))
                    conn.commit()
                    conn.close()

                    st.balloons()
                    st.toast("¡Sesión de grupo guardada!", icon="🎉")
                    st.success("✅ Registro almacenado.")
                    st.rerun()

    # --- 8. CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Inventario y Entrega de Medicamentos")
        
        tab1, tab2, tab3 = st.tabs(["📦 Catálogo de Fármacos", "📋 Asignación de Dosis", "💊 Entrega desde Almacén"])

        with tab1:
            st.subheader("Alta de Fármaco en Inventario")
            with st.form("form_alta_med"):
                c_m1, c_m2, c_m3 = st.columns(3)
                m_nom = c_m1.text_input("Nombre del Medicamento *")
                m_gram = c_m2.text_input("Gramaje / Presentación (ej. 500mg)")
                m_exist = c_m3.number_input("Existencia Inicial (Piezas)", min_value=0, value=100)
                btn_m = st.form_submit_button("💾 Registrar Medicamento", use_container_width=True)
                if btn_m:
                    if m_nom.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO medicamentos (nombre, gramaje, existencia) VALUES (?, ?, ?)', (m_nom.strip(), m_gram, m_exist))
                            conn.commit()
                            st.balloons()
                            st.toast("¡Medicamento agregado!", icon="🎉")
                            st.success("✅ Fármaco registrado en inventario.")
                        except sqlite3.IntegrityError:
                            st.error("❌ El medicamento ya existe en el catálogo.")
                        conn.close()
                        st.rerun()

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre, gramaje, existencia FROM medicamentos ORDER BY nombre ASC')
            meds_list = c.fetchall()
            conn.close()

            if meds_list:
                st.dataframe([{"ID": m[0], "Medicamento": m[1], "Gramaje": m[2], "Stock Disponible": m[3]} for m in meds_list], use_container_width=True)

        with tab2:
            st.subheader("Asignar Receta a Residente")
            if not pacientes_act or not meds_list:
                st.info("Requiere residentes y medicamentos registrados.")
            else:
                sel_p = st.selectbox("Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"], key="p_med_rec")
                sel_m = st.selectbox("Medicamento", options=meds_list, format_func=lambda x: f"{x[1]} ({x[2]}) - Stock: {x[3]}")
                
                with st.form("form_receta"):
                    dosis_cnt = st.number_input("Dosis Diaria (Piezas)", min_value=1, value=1)
                    instruc = st.text_input("Instrucciones de Toma (ej. Cada 8 hrs tras alimentos)")
                    btn_rec = st.form_submit_button("💾 Asignar Receta", use_container_width=True)
                    if btn_rec:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO dosis_pacientes (paciente_id, medicamento_id, dosis_diaria, instrucciones)
                            VALUES (?, ?, ?, ?)
                        ''', (sel_p["paciente_id"], sel_m[0], dosis_cnt, instruc))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Receta asignada!", icon="🎉")
                        st.success("✅ Esquema guardado.")
                        st.rerun()

        with tab3:
            st.subheader("Entrega Diaria de Medicamento")
            if not pacientes_act:
                st.info("No hay residentes registrados.")
            else:
                sel_p = st.selectbox("Seleccione Residente", options=pacientes_act, format_func=lambda x: x["etiqueta"], key="p_med_ent")
                p_id = sel_p["paciente_id"]

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT d.id, m.id, m.nombre, m.gramaje, m.existencia, d.dosis_diaria, d.instrucciones
                    FROM dosis_pacientes d
                    JOIN medicamentos m ON d.medicamento_id = m.id
                    WHERE d.paciente_id = ?
                ''', (p_id,))
                recetas_p = c.fetchall()
                conn.close()

                if not recetas_p:
                    st.info("Este residente no tiene medicamentos recetados.")
                else:
                    for r_m in recetas_p:
                        m_id = r_m[1]
                        m_nom = r_m[2]
                        m_stock = r_m[4]
                        m_dosis = r_m[5]

                        st.markdown(f"**💊 {m_nom} ({r_m[3]})** - Dosis diaria: {m_dosis} pza(s) | **Stock en Almacén:** {m_stock} pzas")
                        
                        if m_stock <= 0:
                            st.warning("⚠️ Sin existencias disponibles en almacén.")
                        else:
                            val_ent = min(m_dosis, m_stock)
                            cant_ent = st.number_input(f"Cantidad a entregar de {m_nom}", min_value=0, max_value=m_stock, value=val_ent, key=f"ent_{p_id}_{m_id}")
                            
                            if st.button(f"📦 Entregar {m_nom}", key=f"btn_ent_{p_id}_{m_id}"):
                                if cant_ent > 0:
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute('UPDATE medicamentos SET existencia = existencia - ? WHERE id = ?', (cant_ent, m_id))
                                    c.execute('INSERT INTO entregas_meds (paciente_id, medicamento_id, cantidad, fecha, usuario) VALUES (?, ?, ?, ?, ?)',
                                              (p_id, m_id, cant_ent, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                                    conn.commit()
                                    conn.close()
                                    st.balloons()
                                    st.toast("¡Entrega registrada!", icon="🎉")
                                    st.success(f"✅ Se entregaron {cant_ent} piezas de {m_nom}.")
                                    st.rerun()

    # --- 9. REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos y Formatos")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT nombre FROM carpetas ORDER BY nombre ASC')
        c_list = [r[0] for r in c.fetchall()]
        conn.close()

        tab1, tab2, tab3 = st.tabs(["📄 Subir y Explorar Archivos", "📁 Personalizar / Gestionar Carpetas", "🗑️ Eliminar Archivos"])

        with tab1:
            st.subheader("Subir Documento a la Nube")
            with st.form("form_subir_doc"):
                carp_sel = st.selectbox("Seleccione Carpeta Destino", c_list if c_list else ["📁 Documentos Generales"])
                f_upload = st.file_uploader("Seleccione archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "png", "jpg"])
                btn_subir = st.form_submit_button("⬆️ Subir Documento", use_container_width=True)

                if btn_subir and f_upload:
                    blob_data = f_upload.read()
                    fname = f_upload.name
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO documentos (nombre_archivo, carpeta, contenido_blob, fecha_subida, usuario)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (fname, carp_sel, blob_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                    conn.commit()
                    conn.close()

                    st.balloons()
                    st.toast("¡Documento subido con éxito!", icon="🎉")
                    st.success(f"✅ Archivo '{fname}' guardado en {carp_sel}.")
                    st.rerun()

            st.markdown("---")
            st.subheader("Archivos Guardados")
            carp_filter = st.selectbox("Filtrar por Carpeta", ["TODAS"] + c_list)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if carp_filter == "TODAS":
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, contenido_blob FROM documentos ORDER BY fecha_subida DESC')
            else:
                c.execute('SELECT id, nombre_archivo, carpeta, fecha_subida, contenido_blob FROM documentos WHERE carpeta = ? ORDER BY fecha_subida DESC', (carp_filter,))
            docs_rows = c.fetchall()
            conn.close()

            if not docs_rows:
                st.info("No hay documentos subidos en esta carpeta.")
            else:
                for d_row in docs_rows:
                    col_doc1, col_doc2 = st.columns([3, 1])
                    col_doc1.markdown(f"📄 **{d_row[1]}** ({d_row[2]}) - *Subido: {d_row[3]}*")
                    col_doc2.download_button("📥 Descargar", data=d_row[4], file_name=d_row[1], key=f"dl_doc_{d_row[0]}")

        with tab2:
            st.subheader("Gestionar Carpetas del Repositorio")
            col_cr1, col_cr2 = st.columns(2)
            
            with col_cr1:
                st.markdown("#### ➕ Crear Nueva Carpeta")
                n_carp = st.text_input("Nombre de la Nueva Carpeta")
                if st.button("➕ Crear Carpeta", use_container_width=True):
                    if n_carp.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO carpetas (nombre) VALUES (?)', (n_carp.strip(),))
                            conn.commit()
                            st.balloons()
                            st.toast("¡Carpeta creada!", icon="🎉")
                            st.success(f"✅ Carpeta '{n_carp}' creada correctamente.")
                        except sqlite3.IntegrityError:
                            st.error("❌ Ya existe una carpeta con ese nombre.")
                        conn.close()
                        st.rerun()

            with col_cr2:
                st.markdown("#### ✏️ Renombrar Carpeta Existente")
                c_ren_sel = st.selectbox("Seleccione Carpeta a Renombrar", c_list)
                c_ren_nuevo = st.text_input("Nuevo Nombre")
                if st.button("🔄 Renombrar Carpeta", use_container_width=True):
                    if c_ren_nuevo.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE carpetas SET nombre = ? WHERE nombre = ?', (c_ren_nuevo.strip(), c_ren_sel))
                        c.execute('UPDATE documentos SET carpeta = ? WHERE carpeta = ?', (c_ren_nuevo.strip(), c_ren_sel))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Carpeta renombrada!", icon="🎉")
                        st.success("✅ Carpeta y archivos actualizados.")
                        st.rerun()

        with tab3:
            st.subheader("Eliminar Documentos")
            if not docs_rows:
                st.info("No hay documentos para eliminar.")
            else:
                doc_del_sel = st.selectbox("Seleccione Documento a Borrar", docs_rows, format_func=lambda x: f"{x[1]} ({x[2]})")
                if st.button("🗑️ Confirmar Borrado de Documento", use_container_width=True):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('DELETE FROM documentos WHERE id = ?', (doc_del_sel[0],))
                    conn.commit()
                    conn.close()
                    st.toast("Documento eliminado.", icon="🗑️")
                    st.rerun()

    # --- 10. BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Búsqueda de Expedientes")
        query_s = st.text_input("Ingrese Folio, Expediente o Nombre del Residente para buscar:")
        
        if query_s.strip():
            filtro = [p for p in pacientes_act if query_s.lower() in p["paciente_id"].lower() or query_s.lower() in p["expediente"].lower() or query_s.lower() in p["nombre"].lower()]
        else:
            filtro = pacientes_act

        if not filtro:
            st.info("No se encontraron residentes con el criterio de búsqueda.")
        else:
            st.dataframe([{
                "Folio": p["paciente_id"],
                "Expediente": p["expediente"] or "S/N",
                "Nombre": p["nombre"],
                "Sexo": p["sexo"],
                "Etapa Actual": p["etapa_actual"],
                "Fecha Ingreso": p["fecha_ingreso"]
            } for p in filtro], use_container_width=True)

    # --- 11. CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración de Seguridad y Usuarios")
        
        tab1, tab2 = st.tabs(["🔑 Cambiar Mi Contraseña", "👥 Usuarios y Roles del Personal"])

        with tab1:
            st.subheader("Cambio de Contraseña")
            with st.form("form_chg_pass"):
                p_old = st.text_input("Contraseña Actual", type="password")
                p_new1 = st.text_input("Nueva Contraseña", type="password")
                p_new2 = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_cp = st.form_submit_button("🔒 Actualizar Contraseña", use_container_width=True)

                if btn_cp:
                    chk_usr = verificar_login(st.session_state["username"], p_old)
                    if not chk_usr:
                        st.error("❌ La contraseña actual es incorrecta.")
                    elif p_new1 != p_new2:
                        st.error("❌ Las nuevas contraseñas no coinciden.")
                    elif len(p_new1) < 4:
                        st.error("⚠️ La contraseña debe tener al menos 4 caracteres.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(p_new1), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Contraseña actualizada con éxito!", icon="🎉")
                        st.success("✅ Clave modificada correctamente.")

        with tab2:
            if st.session_state["rol"] != "admin":
                st.warning("🔒 Esta sección es exclusiva para usuarios con rol de Administrador.")
            else:
                st.subheader("Alta de Usuario de Personal")
                with st.form("form_alta_staff"):
                    c_u1, c_u2 = st.columns(2)
                    u_user = c_u1.text_input("Nombre de Usuario (Login) *")
                    u_nombre = c_u2.text_input("Nombre Completo del Colaborador *")
                    u_pass = c_u1.text_input("Contraseña *", type="password")
                    u_rol = c_u2.selectbox("Rol / Permisos", ["admin", "staff", "lectura"], index=1)
                    btn_u = st.form_submit_button("👤 Registrar Usuario", use_container_width=True)

                    if btn_u:
                        if u_user.strip() and u_pass.strip():
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                          (u_user.strip(), hash_pass(u_pass), u_nombre.strip(), u_rol))
                                conn.commit()
                                st.balloons()
                                st.toast("¡Usuario registrado!", icon="🎉")
                                st.success(f"✅ Usuario '{u_user}' creado exitosamente.")
                            except sqlite3.IntegrityError:
                                st.error("❌ El nombre de usuario ya existe.")
                            conn.close()
                            st.rerun()

                st.markdown("---")
                st.subheader("Usuarios Registrados en el Sistema")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT id, username, nombre_completo, rol FROM usuarios ORDER BY id ASC')
                users_rows = c.fetchall()
                conn.close()

                st.dataframe([{"ID": u[0], "Usuario": u[1], "Nombre Completo": u[2], "Rol": u[3].upper()} for u in users_rows], use_container_width=True)

    # --- 12. RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        st.info("Descargue su archivo de base de datos (`sistema_pacientes.db`) para guardar una copia de seguridad en su computadora con todos los residentes, entrevistas, consejerías y documentos.")

        col_b1, col_b2 = st.columns(2)

        with col_b1:
            st.subheader("📥 Descargar Respaldo")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f_db:
                    st.download_button(
                        label="📦 Descargar Respaldo `.db`",
                        data=f_db.read(),
                        file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )

        with col_b2:
            st.subheader("📤 Restaurar Respaldo")
            up_db = st.file_uploader("Cargar archivo `.db` de respaldo", type=["db", "sqlite"])
            if up_db and st.button("⚠️ Confirmar Restauración", use_container_width=True):
                with open(DB_FILE, "wb") as f_out:
                    f_out.write(up_db.read())
                st.balloons()
                st.toast("¡Base de datos restaurada con éxito!", icon="🎉")
                st.success("✅ Base de datos restaurada correctamente. Reiniciando vistas...")
                st.rerun()

if __name__ == "__main__":
    main()

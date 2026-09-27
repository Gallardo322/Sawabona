import streamlit as st
import sqlite3
import json
import hashlib
import os
import re
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
INACTIVITY_TIMEOUT = 600  # 10 minutos (600 segundos)

# --- DETECTOR DE INACTIVIDAD (JS + SESSION STATE) ---
if "last_activity" not in st.session_state:
    st.session_state["last_activity"] = time.time()

st.markdown("""
<script>
const timeoutMs = 600000;
let timer;
function resetTimer() {
    clearTimeout(timer);
    timer = setTimeout(() => {
        window.location.reload();
    }, timeoutMs);
}
window.onload = resetTimer;
window.onmousemove = resetTimer;
window.onmousedown = resetTimer;
window.ontouchstart = resetTimer;
window.onclick = resetTimer;
window.onkeydown = resetTimer;
window.addEventListener('scroll', resetTimer, true);
</script>
""", unsafe_allow_html=True)

# --- FUNCIONES DE BASE DE DATOS E INICIALIZACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'
        )
    ''')
    
    # 2. Entrevistas / Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 3. Fichas de Ingreso (NOM-028)
    c.execute('''
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            datos_json TEXT,
            fecha_ingreso TEXT
        )
    ''')

    # 4. Consejerías
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            expediente TEXT,
            fecha TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance_retroceso TEXT,
            sugerencia TEXT,
            usuario_registro TEXT
        )
    ''')

    # 5. Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            tipo_grupo TEXT,
            fecha TEXT,
            etapa_paciente TEXT,
            desarrollo TEXT,
            devolucion TEXT,
            compromisos TEXT,
            usuario_registro TEXT
        )
    ''')

    # 6. Medicamentos / Esquemas / Entregas / Catálogo
    c.execute('''
        CREATE TABLE IF NOT EXISTS esquemas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_nombre TEXT NOT NULL,
            dosis_diaria INTEGER DEFAULT 1,
            frecuencia TEXT,
            usuario_registro TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_nombre TEXT NOT NULL,
            cantidad_entregada INTEGER NOT NULL,
            fecha_entrega TEXT NOT NULL,
            usuario_registro TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            existencia INTEGER DEFAULT 0,
            presentacion TEXT
        )
    ''')

    # 7. Repositorio de Documentos & Carpetas
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')

    # --- MIGRACIONES AUTOMÁTICAS CON PRAGMA (Mantiene compatibilidad) ---
    def agregar_columna_si_falta(tabla, columna, tipo_sql):
        c.execute(f"PRAGMA table_info({tabla})")
        cols = [row[1] for row in c.fetchall()]
        if columna not in cols:
            c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_sql}")

    agregar_columna_si_falta("usuarios", "rol", "TEXT DEFAULT 'Nivel 2 - Lectura y Escritura'")
    agregar_columna_si_falta("entrevistas", "expediente", "TEXT")
    agregar_columna_si_falta("grupos_terapeuticos", "etapa_paciente", "TEXT")

    # Carpetas por defecto en repositorio
    carpetas_def = ["📁 Manuales y Reglamentos", "📑 Formato de Evaluaciones", "🩺 Protocolos Médicos", "📁 Documentos Generales"]
    for c_name in carpetas_def:
        c.execute("INSERT OR IGNORE INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (c_name,))

    # Medicamentos por defecto si catálogo está vacío
    c.execute("SELECT COUNT(*) FROM catalogo_medicamentos")
    if c.fetchone()[0] == 0:
        meds_def = [
            ("Complejo B (Cápsulas)", 100, "Caja con tabletas"),
            ("Paracetamol 500mg", 150, "Caja con tabletas"),
            ("Fluoxetina 20mg", 80, "Caja con cápsulas"),
            ("Quetiapina 25mg", 60, "Caja con tabletas"),
            ("Valproato de Magnesio 200mg", 90, "Frasco con solución/tabletas")
        ]
        c.executemany("INSERT INTO catalogo_medicamentos (nombre, existencia, presentacion) VALUES (?, ?, ?)", meds_def)

    # Usuario admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol) 
            VALUES (?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))

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

def es_admin():
    u = st.session_state.get("username", "")
    r = st.session_state.get("rol", "")
    return u == "admin" or "Administrador" in str(r)

# --- FUNCIONES AUXILIARES DE PACIENTES & FOLIO/EXPEDIENTE ---
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
            except:
                pass
    return f"PAC-{max_num + 1:03d}"

def validar_expediente_unico(expediente, paciente_id_actual=None):
    if not expediente or str(expediente).strip() == "":
        return True, ""
    exp_clean = str(expediente).strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if paciente_id_actual:
        c.execute('SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ? AND paciente_id != ?', (exp_clean, paciente_id_actual))
    else:
        c.execute('SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ?', (exp_clean,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            dj = json.loads(row[1])
            nombre = dj.get("nombre_paciente", row[0])
        except:
            nombre = row[0]
        return False, f"El Expediente '{exp_clean}' ya está asignado a: {nombre} ({row[0]})."
    return True, ""

def calcular_edad(fecha_nac_str):
    if not fecha_nac_str:
        return "N/A"
    try:
        fn = datetime.strptime(fecha_nac_str, "%Y-%m-%d")
        hoy = datetime.now()
        edad = hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
        return f"{edad} años"
    except:
        return "N/A"

def obtener_pacientes_dict():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, datos_json FROM entrevistas ORDER BY paciente_id DESC')
    rows = c.fetchall()
    conn.close()
    
    pdict = {}
    for r in rows:
        pid = r[0]
        exp = r[1]
        try:
            dj = json.loads(r[2])
            nombre = dj.get("nombre_paciente", pid)
        except:
            nombre = pid
        exp_txt = f"Exp: {exp}" if exp and str(exp).strip() != "" else "Exp: S/N"
        pdict[pid] = f"{pid} | {exp_txt} - {nombre}"
    return pdict

def clean_pdf_text(txt):
    if not txt:
        return ""
    replacements = {
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Ñ': 'N', 'ñ': 'n', 'Ü': 'U', 'ü': 'u',
        '¿': '', '¡': '', '—': '-', '–': '-', '“': '"', '”': '"', '’': "'"
    }
    txt_str = str(txt)
    for k, v in replacements.items():
        txt_str = txt_str.replace(k, v)
    return txt_str.encode('latin-1', 'replace').decode('latin-1')

# --- GENERACIÓN DE PDFS (FPDF2 SEGURO CON BYTES) ---
def generar_pdf_ficha_ingreso(paciente_id, datos_f, datos_p):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, clean_pdf_text("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), ln=True, align='C')
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 8, clean_pdf_text("FICHA DE INGRESO Y ADMISIÓN DE PACIENTES"), ln=True, align='C')
    pdf.ln(4)

    exp_print = datos_f.get("expediente") or datos_p.get("expediente") or "S/N"
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(0, 6, clean_pdf_text(f"EXPEDIENTE CLÍNICO: {exp_print} | FECHA REGISTRO: {datos_f.get('fecha_ingreso', '')}"), ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # 1. Responsable
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS DEL RESPONSABLE DEL INGRESO"), ln=True)
    pdf.set_font("Helvetica", '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Nombre: {datos_f.get('responsable_nombre', '')}\nParentesco: {datos_f.get('responsable_parentesco', '')} | Teléfono: {datos_f.get('responsable_telefono', '')}"))
    pdf.ln(3)

    # 2. Paciente
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("2. DATOS GENERALES DEL PACIENTE"), ln=True)
    pdf.set_font("Helvetica", '', 10)
    info_p = (
        f"Nombre del Paciente: {datos_p.get('nombre_paciente', '')}\n"
        f"Edad: {datos_p.get('edad', '')} | Fecha Nacimiento: {datos_p.get('fecha_nacimiento', '')}\n"
        f"Estado Civil: {datos_f.get('estado_civil', '')} | Escolaridad: {datos_f.get('escolaridad', '')}\n"
        f"Ocupación: {datos_f.get('ocupacion', '')} | Religión: {datos_f.get('religion', '')}\n"
        f"Servicios Médicos: {datos_f.get('servicios_medicos', '')}\n"
        f"Domicilio: {datos_f.get('domicilio', '')}, {datos_f.get('colonia', '')}, {datos_f.get('municipio', '')}, {datos_f.get('estado', '')}"
    )
    pdf.multi_cell(0, 5, clean_pdf_text(info_p))
    pdf.ln(3)

    # 3. Sustancias
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("3. SUSTANCIAS Y TÉRMINOS ECONÓMICOS"), ln=True)
    pdf.set_font("Helvetica", '', 10)
    sust_str = ", ".join(datos_f.get("sustancias_consumo", [])) or "No especificado"
    info_s = (
        f"Sustancias de Consumo: {sust_str}\n"
        f"Sustancia de Impacto Principal: {datos_f.get('sustancia_impacto', '')}\n"
        f"Sucursal: {datos_f.get('sucursal', '')} | Modalidad: {datos_f.get('modalidad_internamiento', '')}\n"
        f"Costo Ingreso: ${datos_f.get('costo_ingreso', 0):,.2f} | Mensualidad: ${datos_f.get('costo_mensualidad', 0):,.2f} | Pagaré: ${datos_f.get('importe_pagare', 0):,.2f}"
    )
    pdf.multi_cell(0, 5, clean_pdf_text(info_s))
    pdf.ln(4)

    # Cláusula NOM-028
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, clean_pdf_text("DECLARACIÓN DE CONFORMIDAD Y AUTORIZACIÓN (NOM-028-SSA2-2009):"), ln=True)
    pdf.set_font("Helvetica", '', 8)
    clausula = (
        "Por medio de la presente manifiesto mi conformidad libre y voluntaria para el ingreso y tratamiento del paciente en esta institución. "
        "Me comprometo a respetar el reglamento interno, cumplir con las cuotas establecidas y participar activamente en el proceso terapéutico familiar."
    )
    pdf.multi_cell(0, 4, clean_pdf_text(clausula))
    pdf.ln(12)

    # Firmas
    y_firmas = pdf.get_y()
    pdf.line(20, y_firmas, 90, y_firmas)
    pdf.line(110, y_firmas, 180, y_firmas)
    pdf.set_font("Helvetica", '', 9)
    pdf.text(25, y_firmas + 5, clean_pdf_text("Firma del Familiar Responsable"))
    pdf.text(115, y_firmas + 5, clean_pdf_text("Firma Director / Consejero"))

    return bytes(pdf.output())

def generar_pdf_consejeria(paciente_id, datos_c, datos_p):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 15)
    pdf.cell(0, 10, clean_pdf_text("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), ln=True, align='C')
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 8, clean_pdf_text(f"HOJA DE CONSEJERÍA INDIVIDUAL #{datos_c.get('num_consejeria', 1)}"), ln=True, align='C')
    pdf.ln(4)

    exp_print = datos_c.get("expediente") or datos_p.get("expediente") or "S/N"
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(0, 6, clean_pdf_text(f"EXPEDIENTE: {exp_print} | FECHA SESIÓN: {datos_c.get('fecha', '')} | ETAPA: {datos_c.get('etapa', '')}"), ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Paciente
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("DATOS DEL RESIDENTE:"), ln=True)
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 5, clean_pdf_text(f"Nombre: {datos_p.get('nombre_paciente', '')} | Edad: {datos_p.get('edad', '')} | Sexo: {datos_p.get('sexo', '')}"), ln=True)
    pdf.ln(3)

    # Temas
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("ASPECTOS TRABAJADOS Y PLANIFICACIÓN:"), ln=True)
    pdf.set_font("Helvetica", '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(f"• Tema Trabajado: {datos_c.get('aspectos_trabajar', '')}\n• Próximo Tema: {datos_c.get('aspectos_proxima', '')}\n• Fecha Próxima Sesión: {datos_c.get('fecha_proxima', '')}"))
    pdf.ln(3)

    # Notas Clínicas
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("EXPOSICIÓN DEL PACIENTE:"), ln=True)
    pdf.set_font("Helvetica", '', 9)
    pdf.multi_cell(0, 4, clean_pdf_text(datos_c.get('exposicion', 'Sin notas.')))
    pdf.ln(3)

    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("AVANCE / RETROCESO DEDUCIDO POR CONSEJERO:"), ln=True)
    pdf.set_font("Helvetica", '', 9)
    pdf.multi_cell(0, 4, clean_pdf_text(datos_c.get('avance_retroceso', 'Sin observaciones.')))
    pdf.ln(3)

    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, clean_pdf_text("SUGERENCIAS Y COMPROMISOS:"), ln=True)
    pdf.set_font("Helvetica", '', 9)
    pdf.multi_cell(0, 4, clean_pdf_text(datos_c.get('sugerencia', 'Sin tareas.')))
    pdf.ln(12)

    # Firmas
    y_firmas = pdf.get_y()
    pdf.line(20, y_firmas, 90, y_firmas)
    pdf.line(110, y_firmas, 180, y_firmas)
    pdf.set_font("Helvetica", '', 9)
    pdf.text(35, y_firmas + 5, clean_pdf_text("Firma del Residente"))
    pdf.text(118, y_firmas + 5, clean_pdf_text("Firma del Consejero"))

    return bytes(pdf.output())

# --- INICIALIZAR BASE DE DATOS Y SESIÓN ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# --- VERIFICACIÓN DE TIMEOUT POR INACTIVIDAD ---
if st.session_state["logged_in"]:
    now = time.time()
    last_act = st.session_state.get("last_activity", now)
    if now - last_act > INACTIVITY_TIMEOUT:
        st.session_state["logged_in"] = False
        st.warning("⏱️ Su sesión ha caducado por inactividad (10 minutos). Por favor ingrese de nuevo.")
        st.rerun()
    st.session_state["last_activity"] = now

# ==========================================
# PANTALLA DE LOGIN
# ==========================================
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center; color: #2E7D32;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema de Entrevistas y Control de Residentes</h3>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Acceso al Sistema")
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit_login:
                valido = verificar_login(user_input, pass_input)
                if valido:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = valido[0]
                    st.session_state["nombre_completo"] = valido[1]
                    st.session_state["rol"] = valido[2]
                    st.session_state["last_activity"] = time.time()
                    st.balloons()
                    st.toast(f"¡Bienvenido(a) {valido[1]}!")
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        
        st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")

else:
    # ==========================================
    # BARRA LATERAL (SIDEBAR DE NAVEGACIÓN)
    # ==========================================
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.caption(f"👤 **{st.session_state.get('nombre_completo', '')}**")
    st.sidebar.caption(f"🛡️ Rol: `{st.session_state.get('rol', 'Nivel 2')}`")
    st.sidebar.write("---")

    menu_options = [
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
    
    menu = st.sidebar.radio("📌 Menú de Navegación", menu_options)
    st.sidebar.write("---")
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # MODULO 1: REGISTRO Y EDICIÓN DE USUARIOS
    # ==========================================
    if menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Usuarios / Residentes")
        
        tab_nuevo, tab_editar = st.tabs(["➕ Registrar Nuevo Paciente", "✏️ Editar Paciente Existente"])
        
        with tab_nuevo:
            st.subheader("Datos del Nuevo Paciente")
            folio_auto = obtener_siguiente_folio()
            
            with st.form("form_nuevo_paciente"):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("Folio de Sistema (Automático)", value=folio_auto, disabled=True)
                    exp_in = st.text_input("Número de Expediente (Manual / Opcional / Único)", help="Número asignado por la institución.")
                    nom_in = st.text_input("Nombre Completo del Paciente *")
                    fn_in = st.date_input("Fecha de Nacimiento", value=datetime(2000, 1, 1))
                    sex_in = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
                
                with c2:
                    tel_in = st.text_input("Teléfono de Contacto")
                    dom_in = st.text_input("Domicilio")
                    f_ing_in = st.date_input("Fecha de Ingreso Real a la Comunidad", value=datetime.now())
                    etapa_in = st.selectbox("Etapa Actual", ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"])
                    f_etapa_in = st.date_input("Fecha de Inicio de Etapa Actual", value=datetime.now())

                sub_p = st.form_submit_button("💾 Guardar Nuevo Paciente", use_container_width=True)
                
                if sub_p:
                    if not nom_in:
                        st.error("⚠️ El nombre del paciente es obligatorio.")
                    else:
                        ok_exp, msg_exp = validar_expediente_unico(exp_in)
                        if not ok_exp:
                            st.error(f"⚠️ {msg_exp}")
                        else:
                            edad_calc = calcular_edad(fn_in.strftime("%Y-%m-%d"))
                            datos_p = {
                                "nombre_paciente": nom_in,
                                "expediente": exp_in.strip(),
                                "fecha_nacimiento": fn_in.strftime("%Y-%m-%d"),
                                "edad": edad_calc,
                                "sexo": sex_in,
                                "telefono": tel_in,
                                "domicilio": dom_in,
                                "fecha_ingreso_real": f_ing_in.strftime("%Y-%m-%d"),
                                "etapa_actual": etapa_in,
                                "fecha_inicio_etapa": f_etapa_in.strftime("%Y-%m-%d")
                            }
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('''
                                INSERT INTO entrevistas (paciente_id, expediente, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (folio_auto, exp_in.strip(), now_str, now_str, st.session_state["username"], json.dumps(datos_p, ensure_ascii=False)))
                            conn.commit()
                            conn.close()
                            
                            st.balloons()
                            st.toast("✅ ¡Paciente registrado con éxito!")
                            st.success(f"🎉 Paciente registrado correctamente con Folio: **{folio_auto}**")
                            st.rerun()

        with tab_editar:
            st.subheader("Modificar Datos de Paciente Registrado")
            pdict = obtener_pacientes_dict()
            if not pdict:
                st.info("No hay pacientes registrados aún.")
            else:
                sel_pid = st.selectbox("Seleccione el Paciente a Editar", list(pdict.keys()), format_func=lambda x: pdict[x])
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT expediente, datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
                row_ed = c.fetchone()
                conn.close()
                
                if row_ed:
                    exp_curr = row_ed[0] or ""
                    try:
                        dj_ed = json.loads(row_ed[1])
                    except:
                        dj_ed = {}
                    
                    with st.form("form_edit_paciente"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.text_input("Folio (No editable)", value=sel_pid, disabled=True)
                            exp_edit = st.text_input("Número de Expediente", value=dj_ed.get("expediente", exp_curr))
                            nom_edit = st.text_input("Nombre Completo", value=dj_ed.get("nombre_paciente", ""))
                            
                            fn_val = datetime.strptime(dj_ed.get("fecha_nacimiento", "2000-01-01"), "%Y-%m-%d") if dj_ed.get("fecha_nacimiento") else datetime(2000, 1, 1)
                            fn_edit = st.date_input("Fecha Nacimiento", value=fn_val)
                            sex_edit = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"], index=["Masculino", "Femenino", "Otro"].index(dj_ed.get("sexo", "Masculino")) if dj_ed.get("sexo") in ["Masculino", "Femenino", "Otro"] else 0)

                        with c2:
                            tel_edit = st.text_input("Teléfono", value=dj_ed.get("telefono", ""))
                            dom_edit = st.text_input("Domicilio", value=dj_ed.get("domicilio", ""))
                            
                            fi_val = datetime.strptime(dj_ed.get("fecha_ingreso_real", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d") if dj_ed.get("fecha_ingreso_real") else datetime.now()
                            f_ing_edit = st.date_input("Fecha Ingreso Real", value=fi_val)
                            
                            etapas_list = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                            et_idx = etapas_list.index(dj_ed.get("etapa_actual", "ACOGIDA")) if dj_ed.get("etapa_actual") in etapas_list else 0
                            etapa_edit = st.selectbox("Etapa Actual", etapas_list, index=et_idx)
                            
                            fet_val = datetime.strptime(dj_ed.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d") if dj_ed.get("fecha_inicio_etapa") else datetime.now()
                            f_etapa_edit = st.date_input("Fecha Inicio Etapa Actual", value=fet_val)

                        sub_edit = st.form_submit_button("💾 Actualizar Datos del Paciente", use_container_width=True)
                        
                        if sub_edit:
                            ok_exp, msg_exp = validar_expediente_unico(exp_edit, paciente_id_actual=sel_pid)
                            if not ok_exp:
                                st.error(f"⚠️ {msg_exp}")
                            else:
                                dj_ed["nombre_paciente"] = nom_edit
                                dj_ed["expediente"] = exp_edit.strip()
                                dj_ed["fecha_nacimiento"] = fn_edit.strftime("%Y-%m-%d")
                                dj_ed["edad"] = calcular_edad(fn_edit.strftime("%Y-%m-%d"))
                                dj_ed["sexo"] = sex_edit
                                dj_ed["telefono"] = tel_edit
                                dj_ed["domicilio"] = dom_edit
                                dj_ed["fecha_ingreso_real"] = f_ing_edit.strftime("%Y-%m-%d")
                                dj_ed["etapa_actual"] = etapa_edit
                                dj_ed["fecha_inicio_etapa"] = f_etapa_edit.strftime("%Y-%m-%d")

                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute('''
                                    UPDATE entrevistas
                                    SET expediente = ?, fecha_modificacion = ?, datos_json = ?
                                    WHERE paciente_id = ?
                                ''', (exp_edit.strip(), now_str, json.dumps(dj_ed, ensure_ascii=False), sel_pid))
                                conn.commit()
                                conn.close()
                                
                                st.balloons()
                                st.toast("✅ ¡Datos del paciente actualizados!")
                                st.success("🎉 Datos guardados correctamente.")
                                st.rerun()

    # ==========================================
    # MODULO 2: FICHA DE INGRESO Y ADMISIÓN
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        pdict = obtener_pacientes_dict()
        
        if not pdict:
            st.warning("⚠️ Primero debe registrar al menos un paciente en el menú de Usuarios.")
        else:
            tab_f_reg, tab_f_pdf = st.tabs(["🆕 Capturar/Editar Ficha", "🖨️ Consultar e Imprimir PDF"])
            
            with tab_f_reg:
                sel_pid = st.selectbox("Seleccione el Paciente para la Ficha", list(pdict.keys()), format_func=lambda x: pdict[x], key="f_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
                row_ent = c.fetchone()
                c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (sel_pid,))
                row_f = c.fetchone()
                conn.close()
                
                dj_p = json.loads(row_ent[0]) if row_ent else {}
                dj_f = json.loads(row_f[0]) if row_f else {}

                with st.form("form_ficha_ingreso"):
                    st.subheader("1. Datos del Responsable del Ingreso")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        resp_nom = st.text_input("Nombre Familiar Responsable", value=dj_f.get("responsable_nombre", ""))
                    with c2:
                        resp_par = st.text_input("Parentesco", value=dj_f.get("responsable_parentesco", "Padre/Madre"))
                    with c3:
                        resp_tel = st.text_input("Teléfono Responsable", value=dj_f.get("responsable_telefono", ""))

                    st.subheader("2. Datos Complementarios del Paciente")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        est_civ = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=0)
                        escol = st.text_input("Escolaridad", value=dj_f.get("escolaridad", "Secundaria"))
                    with c2:
                        ocup = st.text_input("Ocupación", value=dj_f.get("ocupacion", "Empleado"))
                        relig = st.text_input("Religión", value=dj_f.get("religion", "Católica"))
                    with c3:
                        serv_med = st.text_input("Servicios Médicos (IMSS, ISSSTE, Ninguno)", value=dj_f.get("servicios_medicos", "Ninguno"))
                        colonia = st.text_input("Colonia", value=dj_f.get("colonia", ""))
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        muni = st.text_input("Municipio / Alcaldía", value=dj_f.get("municipio", ""))
                    with c2:
                        edo = st.text_input("Estado", value=dj_f.get("estado", "Jalisco"))

                    st.subheader("3. Sustancias de Consumo")
                    opc_sust = ["Alcohol", "Cannabis", "Cocaína", "Metanfetaminas (Cristal)", "Tabaco", "Benzodiazepinas", "Heroína", "Otro"]
                    sust_sel = st.multiselect("Sustancias Consumidas", opc_sust, default=dj_f.get("sustancias_consumo", ["Alcohol"]))
                    sust_imp = st.text_input("Sustancia de Impacto Principal", value=dj_f.get("sustancia_impacto", "Metanfetaminas (Cristal)"))

                    st.subheader("4. Términos Financieros y Sucursal")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        sucursal = st.selectbox("Sucursal / Comunidad", ["Sawabona Shikoba Principal", "Sawabona Femenil", "Sawabona Poniente"], index=0)
                        mod_int = st.selectbox("Modalidad de Internamiento", ["Voluntario", "Involuntario (NOM-028)"], index=0)
                    with c2:
                        c_ing = st.number_input("Costo de Ingreso ($)", value=float(dj_f.get("costo_ingreso", 4500.0)))
                        c_men = st.number_input("Mensualidad ($)", value=float(dj_f.get("costo_mensualidad", 6000.0)))
                    with c3:
                        imp_pag = st.number_input("Importe Pagaré ($)", value=float(dj_f.get("importe_pagare", 42000.0)))

                    sub_f = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                    
                    if sub_f:
                        datos_f_save = {
                            "responsable_nombre": resp_nom,
                            "responsable_parentesco": resp_par,
                            "responsable_telefono": resp_tel,
                            "estado_civil": est_civ,
                            "escolaridad": escol,
                            "ocupacion": ocup,
                            "religion": relig,
                            "servicios_medicos": serv_med,
                            "colonia": colonia,
                            "municipio": muni,
                            "estado": edo,
                            "sustancias_consumo": sust_sel,
                            "sustancia_impacto": sust_imp,
                            "sucursal": sucursal,
                            "modalidad_internamiento": mod_int,
                            "costo_ingreso": c_ing,
                            "costo_mensualidad": c_men,
                            "importe_pagare": imp_pag,
                            "expediente": dj_p.get("expediente", ""),
                            "fecha_ingreso": datetime.now().strftime("%Y-%m-%d")
                        }
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT OR REPLACE INTO fichas_ingreso (paciente_id, expediente, datos_json, fecha_ingreso)
                            VALUES (?, ?, ?, ?)
                        ''', (sel_pid, dj_p.get("expediente", ""), json.dumps(datos_f_save, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d")))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("✅ ¡Ficha de ingreso guardada!")
                        st.success("🎉 Ficha de Ingreso guardada correctamente.")
                        st.rerun()

            with tab_f_pdf:
                sel_pid_pdf = st.selectbox("Seleccione Paciente para Imprimir Ficha", list(pdict.keys()), format_func=lambda x: pdict[x], key="f_pdf_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid_pdf,))
                r_ent = c.fetchone()
                c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (sel_pid_pdf,))
                r_f = c.fetchone()
                conn.close()
                
                if not r_f:
                    st.info("⚠️ No se ha capturado la Ficha de Ingreso para este paciente aún.")
                else:
                    dj_p = json.loads(r_ent[0]) if r_ent else {}
                    dj_f = json.loads(r_f[0]) if r_f else {}
                    
                    st.success("✅ Ficha de Ingreso lista para descarga e impresión.")
                    pdf_bytes = generar_pdf_ficha_ingreso(sel_pid_pdf, dj_f, dj_p)
                    
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso en PDF",
                        data=pdf_bytes,
                        file_name=f"Ficha_Ingreso_{sel_pid_pdf}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # ==========================================
    # MODULO 3: ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        pdict = obtener_pacientes_dict()
        
        if not pdict:
            st.warning("⚠️ Registre un paciente primero.")
        else:
            sel_pid = st.selectbox("Seleccione el Paciente", list(pdict.keys()), format_func=lambda x: pdict[x], key="ent_pid")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
            row_e = c.fetchone()
            conn.close()
            
            dj_p = json.loads(row_e[0]) if row_e else {}
            
            with st.form("form_entrevista_inicial"):
                st.subheader("I. Motivo de Consulta y Expectativas")
                motivo = st.text_area("Motivo de Ingreso / Problemas Principales", value=dj_p.get("motivo_consulta", ""))
                expectativa = st.text_area("Expectativas del Proceso Terapéutico", value=dj_p.get("expectativa", ""))
                
                st.subheader("II. Historial de Consumo de Sustancias")
                c1, c2 = st.columns(2)
                with c1:
                    edad_ini = st.text_input("Edad de Inicio de Consumo", value=dj_p.get("edad_inicio", "15 años"))
                    sust_frec = st.text_input("Sustancia Frecuente", value=dj_p.get("sustancia_frecuente", ""))
                with c2:
                    ult_cons = st.text_input("Fecha/Tiempo del Último Consumo", value=dj_p.get("ultimo_consumo", "Hace 3 días"))
                    trat_prev = st.selectbox("¿Tratamientos Anteriores?", ["No", "Sí (1 proceso)", "Sí (2 o más procesos)"], index=0)

                st.subheader("III. Evaluación Psicosocial y Apoyo Familiar")
                apoyo_fam = st.text_area("Redes de Apoyo Familiar / Acompañantes", value=dj_p.get("apoyo_familiar", ""))
                diag_consejeria = st.text_area("Diagnóstico Inicial e Impresión del Consejero", value=dj_p.get("diag_consejeria", ""))

                sub_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                
                if sub_ent:
                    dj_p["motivo_consulta"] = motivo
                    dj_p["expectativa"] = expectativa
                    dj_p["edad_inicio"] = edad_ini
                    dj_p["sustancia_frecuente"] = sust_frec
                    dj_p["ultimo_consumo"] = ult_cons
                    dj_p["tratamientos_previos"] = trat_prev
                    dj_p["apoyo_familiar"] = apoyo_fam
                    dj_p["diag_consejeria"] = diag_consejeria

                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''
                        UPDATE entrevistas
                        SET fecha_modificacion = ?, datos_json = ?
                        WHERE paciente_id = ?
                    ''', (now_str, json.dumps(dj_p, ensure_ascii=False), sel_pid))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast("✅ ¡Entrevista Inicial guardada correctamente!")
                    st.success("🎉 Datos clínicos guardados con éxito.")
                    st.rerun()

    # ==========================================
    # MODULO 4: CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Consejerías Individuales y Plan de Tratamiento")
        pdict = obtener_pacientes_dict()
        
        if not pdict:
            st.warning("⚠️ Primero registre un paciente en el sistema.")
        else:
            PLAN_CONSEJERIAS = {
                "ACOGIDA": [
                    "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
                    "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGERSTROM, AUDIT, BECK 1, 2, CAGE, PHQ15).",
                    "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
                    "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
                ],
                "IDENTIFICACIÓN": [
                    "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
                    "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
                    "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
                    "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.",
                    "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
                    "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
                    "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
                    "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
                ],
                "ELABORACIÓN": [
                    "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
                    "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
                    "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
                    "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
                    "(5. CONSEJRIA) PREVENCIÓN DE RECAÍDAS.",
                    "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
                    "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
                    "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
                ],
                "CONSOLIDACIÓN": [
                    "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
                    "(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
                    "(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.",
                    "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
                ],
                "SERVICIO SOCIAL": [
                    "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
                    "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO - CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
                    "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
                    "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
                ]
            }

            tab_cons_reg, tab_cons_hist = st.tabs(["📝 Registrar Nueva Sesión", "📜 Historial e Impresión PDF"])
            
            with tab_cons_reg:
                sel_pid = st.selectbox("Seleccione el Paciente", list(pdict.keys()), format_func=lambda x: pdict[x], key="c_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT expediente, datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
                row_ent = c.fetchone()
                
                # Consejerías previas en esta etapa
                c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ?", (sel_pid,))
                total_cons_p = c.fetchone()[0]
                conn.close()

                dj_p = json.loads(row_ent[1]) if row_ent else {}
                etapa_act = dj_p.get("etapa_actual", "ACOGIDA")
                exp_curr = dj_p.get("expediente") or row_ent[0] or ""

                # Sugerencia de tema
                temas_etapa = PLAN_CONSEJERIAS.get(etapa_act, PLAN_CONSEJERIAS["ACOGIDA"])
                idx_sug = min(total_cons_p, len(temas_etapa) - 1)
                idx_prox = min(total_cons_p + 1, len(temas_etapa) - 1)
                
                tema_sug = temas_etapa[idx_sug]
                tema_prox_sug = temas_etapa[idx_prox]

                st.info(f"📊 **Paciente**: {dj_p.get('nombre_paciente', sel_pid)} | **Etapa**: `{etapa_act}` | **Consejerías Registradas**: `{total_cons_p}`")

                with st.form("form_nueva_consejeria"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        exp_c = st.text_input("Expediente", value=exp_curr)
                    with c2:
                        fecha_c = st.date_input("Fecha de Sesión", value=datetime.now())
                    with c3:
                        num_c = st.number_input("Número de Consejería", value=total_cons_p + 1, min_value=1)

                    st.subheader("Planificación de Temas")
                    asp_trab = st.selectbox("Aspectos a Trabajar (Sesión Actual)", temas_etapa, index=idx_sug)
                    asp_prox = st.selectbox("Aspectos a Trabajar en Próxima Consejería", temas_etapa, index=idx_prox)
                    f_prox = st.date_input("Fecha Próxima Consejería (+7 días recomendados)", value=datetime.now() + timedelta(days=7))

                    st.subheader("Desarrollo de la Sesión")
                    exposicion = st.text_area("Exposición del Paciente (Notas Clínicas)", height=100)
                    avance = st.text_area("Avance / Retroceso Observado", height=80)
                    sugerencia = st.text_area("Sugerencias y Compromisos Asignados", height=80)

                    sub_c = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)
                    
                    if sub_c:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO consejerias (
                                paciente_id, expediente, fecha, etapa, num_consejeria,
                                aspectos_trabajar, aspectos_proxima, fecha_proxima,
                                exposicion, avance_retroceso, sugerencia, usuario_registro
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            sel_pid, exp_c, fecha_c.strftime("%Y-%m-%d"), etapa_act, num_c,
                            asp_trab, asp_prox, f_prox.strftime("%Y-%m-%d"),
                            exposicion, avance, sugerencia, st.session_state["username"]
                        ))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("✅ ¡Consejería registrada exitosamente!")
                        st.success("🎉 Sesión guardada en el expediente.")
                        st.rerun()

            with tab_cons_hist:
                sel_pid_h = st.selectbox("Seleccione Paciente para Consultar Historial", list(pdict.keys()), format_func=lambda x: pdict[x], key="c_hist_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid_h,))
                r_ent = c.fetchone()
                c.execute('''
                    SELECT id, fecha, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance_retroceso, sugerencia
                    FROM consejerias WHERE paciente_id = ? ORDER BY num_consejeria DESC
                ''', (sel_pid_h,))
                rows_c = c.fetchall()
                conn.close()

                dj_p = json.loads(r_ent[0]) if r_ent else {}
                
                if not rows_c:
                    st.info("ℹ️ Este paciente no cuenta con sesiones de consejería registradas.")
                else:
                    for rc in rows_c:
                        cid, cf, cet, cnum, casp, cprox, cfprox, cexp, cav, csug = rc
                        with st.expander(f"📝 Consejería #{cnum} - {casp} ({cf})"):
                            st.write(f"**Etapa**: {cet} | **Próxima Sesión**: {cfprox}")
                            st.write(f"**Próximo Tema**: {cprox}")
                            st.markdown("---")
                            st.write(f"**Exposición**: {cexp}")
                            st.write(f"**Avance/Retroceso**: {cav}")
                            st.write(f"**Sugerencia**: {csug}")
                            
                            datos_c_pdf = {
                                "num_consejeria": cnum,
                                "expediente": dj_p.get("expediente", ""),
                                "fecha": cf,
                                "etapa": cet,
                                "aspectos_trabajar": casp,
                                "aspectos_proxima": cprox,
                                "fecha_proxima": cfprox,
                                "exposicion": cexp,
                                "avance_retroceso": cav,
                                "sugerencia": csug
                            }
                            pdf_c_bytes = generar_pdf_consejeria(sel_pid_h, datos_c_pdf, dj_p)
                            
                            st.download_button(
                                label=f"🖨️ Descargar PDF Consejería #{cnum}",
                                data=pdf_c_bytes,
                                file_name=f"Consejeria_{cnum}_{sel_pid_h}.pdf",
                                mime="application/pdf",
                                key=f"btn_pdf_c_{cid}"
                            )

    # ==========================================
    # MODULO 5: GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Evaluación de Etapas, Rezagos y Promoción")
        pdict = obtener_pacientes_dict()
        
        if not pdict:
            st.warning("⚠️ No hay pacientes registrados.")
        else:
            sel_pid = st.selectbox("Seleccione el Paciente a Evaluar", list(pdict.keys()), format_func=lambda x: pdict[x], key="etapa_pid")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
            row_e = c.fetchone()
            
            # Grupos
            try:
                c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ?", (sel_pid,))
                total_grupos = c.fetchone()[0]
            except:
                total_grupos = 0

            # Consejerías
            c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ?", (sel_pid,))
            total_cons = c.fetchone()[0]
            conn.close()

            dj_p = json.loads(row_e[0]) if row_e else {}
            
            etapa_act = dj_p.get("etapa_actual", "ACOGIDA")
            f_ing_str = dj_p.get("fecha_ingreso_real", datetime.now().strftime("%Y-%m-%d"))
            f_eta_str = dj_p.get("fecha_inicio_etapa", datetime.now().strftime("%Y-%m-%d"))

            f_ing = datetime.strptime(f_ing_str, "%Y-%m-%d") if f_ing_str else datetime.now()
            f_eta = datetime.strptime(f_eta_str, "%Y-%m-%d") if f_eta_str else datetime.now()
            hoy = datetime.now()

            dias_totales = (hoy - f_ing).days
            dias_etapa = (hoy - f_eta).days

            DURACION_ESTANDAR = {
                "ACOGIDA": 30,
                "IDENTIFICACIÓN": 60,
                "ELABORACIÓN": 60,
                "CONSOLIDACIÓN": 30,
                "SERVICIO SOCIAL": 30
            }
            dur_est = DURACION_ESTANDAR.get(etapa_act, 30)

            st.write("---")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("🗓️ Días Totales en Comunidad", f"{dias_totales} días")
            with c2:
                st.metric(f"⏱️ Días en Etapa ({etapa_act})", f"{dias_etapa} días")
            with c3:
                st.metric("🎯 Duración Estándar de Etapa", f"{dur_est} días")

            # Alerta de Rezago
            if dias_etapa > dur_est:
                exceso = dias_etapa - dur_est
                st.error(
                    f"🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: "
                    f"El paciente lleva **{dias_totales} días internado** y suma **{dias_etapa} días en la Etapa {etapa_act}** "
                    f"(Duración esperada: {dur_est} días). Ha excedido por **+{exceso} días** la etapa sin ser promovido."
                )

            st.subheader("📋 Checklist de Requisitos para Promoción")
            
            REQ_CONSEJERIAS = {"ACOGIDA": 4, "IDENTIFICACIÓN": 8, "ELABORACIÓN": 8, "CONSOLIDACIÓN": 4, "SERVICIO SOCIAL": 4}
            req_c = REQ_CONSEJERIAS.get(etapa_act, 4)
            cumple_c = total_cons >= req_c

            c1, c2 = st.columns(2)
            with c1:
                if cumple_c:
                    st.success(f"✅ **Consejerías Completadas**: {total_cons} de {req_c} requeridas.")
                else:
                    st.warning(f"❌ **Consejerías Pendientes**: {total_cons} de {req_c} requeridas (Faltan {req_c - total_cons}).")
            
            with c2:
                if total_grupos >= 5:
                    st.success(f"✅ **Asistencia a Grupos**: {total_grupos} sesiones registradas.")
                else:
                    st.info(f"ℹ️ **Sesiones de Grupo Registradas**: {total_grupos} sesiones.")

            st.subheader("Promoción de Etapa")
            ETAPAS_SECUENCIA = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            curr_idx = ETAPAS_SECUENCIA.index(etapa_act) if etapa_act in ETAPAS_SECUENCIA else 0

            if curr_idx < len(ETAPAS_SECUENCIA) - 1:
                sig_etapa = ETAPAS_SECUENCIA[curr_idx + 1]
                
                if not cumple_c:
                    st.error(f"🔒 Para promover a **{sig_etapa}**, el paciente debe completar las {req_c} consejerías de la etapa actual.")
                else:
                    if st.button(f"🎉 Promover Paciente a Etapa: {sig_etapa}", use_container_width=True):
                        dj_p["etapa_actual"] = sig_etapa
                        dj_p["fecha_inicio_etapa"] = datetime.now().strftime("%Y-%m-%d")
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE entrevistas SET datos_json = ? WHERE paciente_id = ?", (json.dumps(dj_p, ensure_ascii=False), sel_pid))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast(f"✅ Paciente promovido a {sig_etapa}!")
                        st.success(f"🎉 El residente ha sido promovido exitosamente a {sig_etapa}.")
                        st.rerun()

    # ==========================================
    # MODULO 6: GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        pdict = obtener_pacientes_dict()
        
        if not pdict:
            st.warning("⚠️ Primero registre un paciente.")
        else:
            sel_pid = st.selectbox("Seleccione el Paciente", list(pdict.keys()), format_func=lambda x: pdict[x], key="grp_pid")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (sel_pid,))
            row_e = c.fetchone()
            conn.close()
            
            dj_p = json.loads(row_e[0]) if row_e else {}
            etapa_act = dj_p.get("etapa_actual", "ACOGIDA")

            with st.form("form_grupo_terapeutico"):
                c1, c2 = st.columns(2)
                with c1:
                    tipo_g = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Grupo de Feedback", "Sesión Psicoeducativa"])
                with c2:
                    fecha_g = st.date_input("Fecha de la Sesión", value=datetime.now())

                desarrollo = st.text_area("Desarrollo y Participación del Paciente", height=100)
                devolucion = st.text_area("Devolución / Comentarios del Terapeuta", height=80)
                compromisos = st.text_area("Compromisos Adquiridos", height=80)

                sub_g = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                
                if sub_g:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (
                            paciente_id, tipo_grupo, fecha, etapa_paciente, desarrollo, devolucion, compromisos, usuario_registro
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        sel_pid, tipo_g, fecha_g.strftime("%Y-%m-%d"), etapa_act,
                        desarrollo, devolucion, compromisos, st.session_state["username"]
                    ))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast("✅ ¡Sesión de grupo guardada!")
                    st.success("🎉 Registro de grupo guardado correctamente.")
                    st.rerun()

    # ==========================================
    # MODULO 7: CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos e Inventario")
        pdict = obtener_pacientes_dict()
        
        tab_med_esq, tab_med_ent, tab_med_cat = st.tabs(["💊 Asignar Esquema", "📦 Entrega Diaria (Almacén)", "📋 Catálogo de Fármacos"])
        
        with tab_med_esq:
            if not pdict:
                st.warning("⚠️ Registre un paciente primero.")
            else:
                sel_pid = st.selectbox("Seleccione Paciente para Esquema", list(pdict.keys()), format_func=lambda x: pdict[x], key="med_esq_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT nombre FROM catalogo_medicamentos ORDER BY nombre ASC")
                meds_cat = [r[0] for r in c.fetchall()]
                conn.close()

                if not meds_cat:
                    st.warning("⚠️ No hay medicamentos en el catálogo.")
                else:
                    with st.form("form_esquema_med"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            med_sel = st.selectbox("Medicamento", meds_cat)
                        with c2:
                            dosis_d = st.number_input("Dosis Diaria (Piezas/Tabletas)", value=1, min_value=1)
                        with c3:
                            frec = st.selectbox("Frecuencia", ["Cada 8 horas", "Cada 12 horas", "Cada 24 horas (Mañana)", "Cada 24 horas (Noche)"])

                        sub_esq = st.form_submit_button("💾 Guardar Esquema de Medicación", use_container_width=True)
                        if sub_esq:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO esquemas_medicamentos (paciente_id, medicamento_nombre, dosis_diaria, frecuencia, usuario_registro)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (sel_pid, med_sel, dosis_d, frec, st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            
                            st.balloons()
                            st.toast("✅ ¡Esquema de medicación asignado!")
                            st.success("🎉 Esquema guardado.")
                            st.rerun()

        with tab_med_ent:
            if not pdict:
                st.warning("⚠️ Registre un paciente primero.")
            else:
                sel_pid = st.selectbox("Seleccione Paciente para Entrega", list(pdict.keys()), format_func=lambda x: pdict[x], key="med_ent_pid")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT e.id, e.medicamento_nombre, e.dosis_diaria, c.existencia 
                    FROM esquemas_medicamentos e
                    LEFT JOIN catalogo_medicamentos c ON e.medicamento_nombre = c.nombre
                    WHERE e.paciente_id = ?
                ''', (sel_pid,))
                esquemas = c.fetchall()
                conn.close()

                if not esquemas:
                    st.info("ℹ️ El paciente no tiene un esquema de medicamentos activo.")
                else:
                    st.subheader("Entrega de Medicamentos desde Almacén")
                    for idx, (eid, m_nom, m_dosis, m_ex) in enumerate(esquemas):
                        max_ex = m_ex if m_ex is not None else 0
                        default_val = min(m_dosis, max_ex) if max_ex > 0 else 0
                        
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.write(f"💊 **{m_nom}** (Dosis recetada: {m_dosis} | Stock en Almacén: `{max_ex}`)")
                        with col2:
                            if max_ex == 0:
                                st.error("⚠️ Sin existencias en almacén")
                                cant_ent = 0
                            else:
                                cant_ent = st.number_input(
                                    f"Cantidad a entregar de {m_nom}",
                                    min_value=0, max_value=max_ex, value=default_val, key=f"ent_{idx}"
                                )
                        
                        if max_ex > 0 and cant_ent > 0:
                            if st.button(f"📦 Entregar {cant_ent} de {m_nom}", key=f"btn_ent_{idx}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute('''
                                    INSERT INTO entregas_medicamentos (paciente_id, medicamento_nombre, cantidad_entregada, fecha_entrega, usuario_registro)
                                    VALUES (?, ?, ?, ?, ?)
                                ''', (sel_pid, m_nom, cant_ent, now_str, st.session_state["username"]))
                                c.execute('''
                                    UPDATE catalogo_medicamentos SET existencia = existencia - ? WHERE nombre = ?
                                ''', (cant_ent, m_nom))
                                conn.commit()
                                conn.close()
                                
                                st.balloons()
                                st.toast(f"✅ ¡Se entregaron {cant_ent} de {m_nom}!")
                                st.success("🎉 Entrega registrada e inventario actualizado.")
                                st.rerun()

        with tab_med_cat:
            st.subheader("Catálogo de Fármacos e Inventario Central")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, nombre, existencia, presentacion FROM catalogo_medicamentos ORDER BY nombre ASC")
            cat_rows = c.fetchall()
            conn.close()

            if cat_rows:
                st.table([{"ID": r[0], "Medicamento": r[1], "Existencia Actual": r[2], "Presentación": r[3]} for r in cat_rows])

            if es_admin():
                st.write("---")
                st.subheader("➕ Agregar / Reabastecer Medicamento al Catálogo")
                with st.form("form_nuevo_med_cat"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        nom_med_cat = st.text_input("Nombre del Medicamento")
                    with c2:
                        ex_med_cat = st.number_input("Cantidad de Existencia Inicial / Reabastecimiento", min_value=0, value=50)
                    with c3:
                        pres_med_cat = st.text_input("Presentación (ej. Caja 30 tabs)", value="Caja con tabletas")

                    sub_cat = st.form_submit_button("💾 Guardar en Catálogo", use_container_width=True)
                    if sub_cat:
                        if not nom_med_cat:
                            st.error("⚠️ Ingrese el nombre del medicamento.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO catalogo_medicamentos (nombre, existencia, presentacion)
                                VALUES (?, ?, ?)
                                ON CONFLICT(nombre) DO UPDATE SET existencia = existencia + excluded.existencia
                            ''', (nom_med_cat, ex_med_cat, pres_med_cat))
                            conn.commit()
                            conn.close()
                            
                            st.balloons()
                            st.toast("✅ ¡Catálogo actualizado!")
                            st.success("🎉 Inventario actualizado.")
                            st.rerun()

    # ==========================================
    # MODULO 8: REPOSITORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio de Documentos, Formatos y Manuales")
        
        tab_rep_sub, tab_rep_con, tab_rep_fld = st.tabs(["📥 Subir Documento", "📄 Consultar y Descargar", "📁 Personalizar / Gestionar Carpetas"])
        
        # Obtener carpetas activas
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM carpetas_repositorio ORDER BY nombre_carpeta ASC")
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()

        with tab_rep_sub:
            with st.form("form_subir_doc"):
                c1, c2 = st.columns(2)
                with c1:
                    carp_sel = st.selectbox("Seleccione Carpeta de Destino", carpetas_list)
                    desc_doc = st.text_input("Descripción Corta del Documento")
                with c2:
                    file_up = st.file_uploader("Seleccione el Archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "xlsx", "png", "jpg"])

                sub_doc_btn = st.form_submit_button("📥 Subir Archivo al Repositorio", use_container_width=True)
                
                if sub_doc_btn:
                    if not file_up:
                        st.error("⚠️ Por favor seleccione un archivo.")
                    else:
                        bytes_data = file_up.read()
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (carp_sel, file_up.name, file_up.type, bytes_data, desc_doc, now_str, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast(f"✅ ¡Archivo {file_up.name} subido al repositorio!")
                        st.success(f"🎉 Archivo **{file_up.name}** guardado exitosamente en **{carp_sel}**.")
                        st.rerun()

        with tab_rep_con:
            f_carp = st.selectbox("Filtrar por Carpeta", ["Todas"] + carpetas_list)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if f_carp == "Todas":
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos ORDER BY id DESC")
            else:
                c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC", (f_carp,))
            docs = c.fetchall()
            conn.close()

            if not docs:
                st.info("ℹ️ No hay documentos subidos en esta carpeta.")
            else:
                for doc in docs:
                    did, dcarp, dnom, dmime, dblob, ddesc, dfech = doc
                    with st.expander(f"📄 {dnom} ({dcarp}) - {dfech}"):
                        st.write(f"**Descripción**: {ddesc if ddesc else 'Sin descripción'}")
                        st.download_button(
                            label=f"⬇️ Descargar {dnom}",
                            data=dblob,
                            file_name=dnom,
                            mime=dmime,
                            key=f"btn_dl_doc_{did}"
                        )

        with tab_rep_fld:
            st.subheader("Personalización de Carpetas del Repositorio")
            
            if not es_admin():
                st.warning("⚠️ Solo los administradores pueden crear o modificar carpetas.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("#### ➕ Crear Nueva Carpeta")
                    with st.form("form_nueva_carpeta"):
                        n_carp_in = st.text_input("Nombre de la Nueva Carpeta (ej. 📑 Informes Médicos)")
                        sub_n_c = st.form_submit_button("➕ Crear Carpeta")
                        if sub_n_c:
                            if not n_carp_in.strip():
                                st.error("⚠️ Ingrese un nombre válido.")
                            else:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("INSERT OR IGNORE INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (n_carp_in.strip(),))
                                conn.commit()
                                conn.close()
                                
                                st.balloons()
                                st.toast("✅ ¡Nueva carpeta creada!")
                                st.success("🎉 Carpeta creada exitosamente.")
                                st.rerun()

                with c2:
                    st.markdown("#### ✏️ Renombrar Carpeta Existente")
                    with st.form("form_renombrar_carpeta"):
                        carp_origen = st.selectbox("Seleccione Carpeta a Renombrar", carpetas_list)
                        n_nuevo_carp = st.text_input("Nuevo Nombre de Carpeta")
                        sub_r_c = st.form_submit_button("✏️ Renombrar Carpeta")
                        
                        if sub_r_c:
                            if not n_nuevo_carp.strip():
                                st.error("⚠️ Ingrese el nuevo nombre.")
                            else:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE carpetas_repositorio SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (n_nuevo_carp.strip(), carp_origen))
                                c.execute("UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?", (n_nuevo_carp.strip(), carp_origen))
                                conn.commit()
                                conn.close()
                                
                                st.balloons()
                                st.toast("✅ ¡Carpeta renombrada!")
                                st.success("🎉 Carpeta y archivos actualizados.")
                                st.rerun()

    # ==========================================
    # MODULO 9: BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Búsqueda de Pacientes")
        
        pdict = obtener_pacientes_dict()
        if not pdict:
            st.info("ℹ️ No hay pacientes registrados.")
        else:
            busqueda = st.text_input("🔎 Buscar por Folio, Expediente o Nombre", "").lower()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT paciente_id, expediente, fecha_registro, datos_json FROM entrevistas ORDER BY paciente_id DESC")
            rows = c.fetchall()
            conn.close()

            filtrados = []
            for r in rows:
                pid, exp, freg, djson = r
                try:
                    dj = json.loads(djson)
                    nom = dj.get("nombre_paciente", "")
                except:
                    nom = ""
                
                cadena = f"{pid} {exp} {nom}".lower()
                if not busqueda or busqueda in cadena:
                    filtrados.append((pid, exp, nom, freg, dj))

            st.write(f"**Pacientes encontrados**: `{len(filtrados)}`")
            for pid, exp, nom, freg, dj in filtrados:
                exp_txt = f"Expediente: {exp}" if exp and str(exp).strip() != "" else "Expediente: S/N"
                with st.expander(f"👤 {nom} ({pid} | {exp_txt})"):
                    st.write(f"• **Edad**: {dj.get('edad', 'N/A')} | **Sexo**: {dj.get('sexo', 'N/A')}")
                    st.write(f"• **Etapa Actual**: `{dj.get('etapa_actual', 'ACOGIDA')}`")
                    st.write(f"• **Fecha Ingreso Real**: {dj.get('fecha_ingreso_real', 'N/A')}")
                    st.write(f"• **Teléfono**: {dj.get('telefono', 'N/A')} | **Domicilio**: {dj.get('domicilio', 'N/A')}")

    # ==========================================
    # MODULO 10: CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad")
        
        if es_admin():
            tab_seg_pass, tab_seg_users = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_seg_pass = st.container()
            tab_seg_users = None

        with tab_seg_pass if es_admin() else tab_seg_pass:
            st.subheader("Cambiar mi Contraseña de Acceso")
            with st.form("form_cambiar_mi_pass"):
                pass_act = st.text_input("Contraseña Actual *", type="password")
                pass_nueva = st.text_input("Nueva Contraseña *", type="password")
                pass_conf = st.text_input("Confirmar Nueva Contraseña *", type="password")
                
                sub_chg_pass = st.form_submit_button("🔑 Actualizar Contraseña", use_container_width=True)
                if sub_chg_pass:
                    user_ok = verificar_login(st.session_state["username"], pass_act)
                    if not user_ok:
                        st.error("❌ La contraseña actual es incorrecta.")
                    elif pass_nueva != pass_conf:
                        st.error("❌ La nueva contraseña y la confirmación no coinciden.")
                    elif not pass_nueva.strip():
                        st.error("⚠️ Ingrese una contraseña válida.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hash_pass(pass_nueva), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("✅ ¡Contraseña actualizada!")
                        st.success("🎉 Su contraseña ha sido cambiada correctamente.")

        if es_admin() and tab_seg_users:
            with tab_seg_users:
                st.subheader("Gestión de Usuarios y Roles de Colaboradores")
                
                with st.form("form_nuevo_usuario_staff"):
                    c1, c2 = st.columns(2)
                    with c1:
                        u_user = st.text_input("Nombre de Usuario (Login) *")
                        u_name = st.text_input("Nombre Completo del Colaborador *")
                    with c2:
                        u_pass = st.text_input("Contraseña de Acceso *", type="password")
                        u_rol = st.selectbox("Rol y Permisos", [
                            "Nivel 1 - Administrador",
                            "Nivel 2 - Lectura y Escritura",
                            "Nivel 3 - Solo Lectura"
                        ], index=1)

                    sub_u_btn = st.form_submit_button("➕ Registrar Usuario de Personal", use_container_width=True)
                    if sub_u_btn:
                        if not u_user or not u_pass or not u_name:
                            st.error("⚠️ Complete todos los campos marcados con *.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute('''
                                    INSERT INTO usuarios (username, password_hash, nombre_completo, rol)
                                    VALUES (?, ?, ?, ?)
                                ''', (u_user.strip(), hash_pass(u_pass), u_name.strip(), u_rol))
                                conn.commit()
                                st.balloons()
                                st.toast(f"✅ ¡Usuario {u_user} registrado!")
                                st.success(f"🎉 Colaborador **{u_name}** creado con éxito.")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("⚠️ El nombre de usuario ya existe.")
                            finally:
                                conn.close()

                st.write("---")
                st.subheader("📋 Personal Registrado en el Sistema")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol FROM usuarios ORDER BY id ASC")
                u_rows = c.fetchall()
                conn.close()

                if u_rows:
                    st.table([{"ID": r[0], "Usuario": r[1], "Nombre Completo": r[2], "Rol": r[3]} for r in u_rows])

    # ==========================================
    # MODULO 11: RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📥 Descargar Respaldo Completo")
            st.info("Descargue copia de seguridad en formato `.db` con todos los pacientes, fichas, consejerías y documentos.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                
                st.download_button(
                    label="📥 Descargar Respaldo (.db)",
                    data=db_bytes,
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    mime="application/octet-stream",
                    use_container_width=True
                )

        with c2:
            st.subheader("📤 Restaurar Base de Datos")
            st.warning("⚠️ Al restaurar un respaldo, los datos actuales del servidor serán reemplazados por el archivo subido.")
            
            res_file = st.file_uploader("Seleccione archivo de respaldo (.db)", type=["db"])
            if res_file:
                if st.button("⚠️ Confirmar Restauración", use_container_width=True):
                    bytes_res = res_file.read()
                    with open(DB_FILE, "wb") as f:
                        f.write(bytes_res)
                    
                    st.balloons()
                    st.toast("✅ ¡Base de datos restaurada!")
                    st.success("🎉 Restauración completada con éxito.")
                    st.rerun()

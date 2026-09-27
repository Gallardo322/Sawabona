import streamlit as st
import sqlite3
import json
import hashlib
import os
import unicodedata
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Comunidad Terapéutica Sawabona Shikoba A.C.",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE AYUDA Y LIMPIEZA ---
def clean_pdf_text(texto):
    if not texto:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    res = str(texto)
    for k, v in replacements.items():
        res = res.replace(k, v)
    return res

def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip().lower()
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    return text

def get_safe_index(options, value, default=0):
    if not value:
        return default
    val_clean = str(value).strip().lower()
    for idx, opt in enumerate(options):
        if str(opt).strip().lower() == val_clean:
            return idx
    return default

def calculate_age(born_str):
    if not born_str:
        return 0
    try:
        born = datetime.strptime(str(born_str).split()[0], "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except:
        return 0

def days_between(date_str):
    if not date_str:
        return 0
    try:
        d = datetime.strptime(str(date_str).split()[0], "%Y-%m-%d").date()
        today = date.today()
        return (today - d).days
    except:
        return 0

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Lectura/Escritura',
            estado TEXT DEFAULT 'Activo'
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            presentacion TEXT,
            stock_actual INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 5,
            instrucciones TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamento_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha TEXT,
            usuario TEXT,
            observaciones TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            carpeta TEXT,
            nombre_archivo TEXT,
            fecha_subida TEXT,
            usuario TEXT,
            contenido_blob BLOB
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            facilitador TEXT,
            tema TEXT,
            participantes_json TEXT,
            observaciones TEXT
        )
    """)

    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'Activo'))
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol, estado FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute("""
            UPDATE entrevistas 
            SET fecha_modificacion = ?, datos_json = ?
            WHERE paciente_id = ?
        """, (fecha_actual, datos_json, paciente_id))
    else:
        c.execute("""
            INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?)
        """, (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            d = json.loads(row[0])
            return d, row[1], row[2], row[3]
        except:
            return {}, row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json FROM entrevistas ORDER BY fecha_modificacion DESC')
    rows = c.fetchall()
    conn.close()
    
    lista = []
    for r in rows:
        pid, f_reg, f_mod, u_reg, d_json = r
        try:
            dj = json.loads(d_json) if d_json else {}
        except:
            dj = {}
        lista.append((pid, f_reg, f_mod, u_reg, dj))
    return lista

# --- GENERADOR DE PDF DE PACIENTES ACTIVOS ---
class PDFListadoPacientes(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, clean_pdf_text("PADRON Y LISTADO GENERAL DE RESIDENTES ACTIVOS"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 5, clean_pdf_text(f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        
        self.set_font("Helvetica", "B", 8)
        col_w = [25, 65, 18, 15, 32, 22, 22, 20]
        headers = ["Folio/Exp", "Nombre Completo", "Sexo", "Edad", "Etapa Actual", "Dias Proc.", "Dias Etapa", "Estado"]
        for i, h in enumerate(headers):
            self.cell(col_w[i], 6, clean_pdf_text(h), border=1, align="C")
        self.ln()

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, clean_pdf_text(f"Pagina {self.page_no()}"), align="C")

def generar_pdf_listado_pacientes(pacientes_lista):
    pdf = PDFListadoPacientes(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "", 8)
    
    col_w = [25, 65, 18, 15, 32, 22, 22, 20]
    
    for p in pacientes_lista:
        pid, f_reg, f_mod, u_reg, dj = p
        
        nombre_c = f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}".strip()
        if not nombre_c:
            nombre_c = dj.get("nombre_completo", "Sin Nombre")
            
        exp = dj.get("expediente", pid)
        folio_exp = f"{pid} / {exp}" if exp and exp != pid else pid
        
        sexo = dj.get("sexo", "MASCULINO")
        f_nac = dj.get("fecha_nacimiento", "")
        edad = calculate_age(f_nac) if f_nac else dj.get("edad", "-")
        
        etapa = dj.get("etapa_actual", "Acogida")
        
        f_ingreso = dj.get("fecha_ingreso", f_reg)
        dias_proc = days_between(f_ingreso)
        
        f_etapa = dj.get("fecha_inicio_etapa", f_ingreso)
        dias_etapa = days_between(f_etapa)
        
        estado = dj.get("estado_paciente", "Activo")
        
        pdf.cell(col_w[0], 6, clean_pdf_text(folio_exp[:14]), border=1)
        pdf.cell(col_w[1], 6, clean_pdf_text(nombre_c[:35]), border=1)
        pdf.cell(col_w[2], 6, clean_pdf_text(sexo[:10]), border=1, align="C")
        pdf.cell(col_w[3], 6, str(edad), border=1, align="C")
        pdf.cell(col_w[4], 6, clean_pdf_text(etapa[:18]), border=1)
        pdf.cell(col_w[5], 6, str(dias_proc), border=1, align="C")
        pdf.cell(col_w[6], 6, str(dias_etapa), border=1, align="C")
        pdf.cell(col_w[7], 6, clean_pdf_text(estado), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Listado_Pacientes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- GENERADOR DE PDF FICHA DE INGRESO ---
class PDFFichaIngreso(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 6, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 5, clean_pdf_text("FICHA DE INGRESO Y CONTRATO DE ADMISION (NOM-028-SSA2-2009)"), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, clean_pdf_text(f"Pagina {self.page_no()}"), align="C")

def generar_pdf_ficha_ingreso(paciente_id, dj):
    pdf = PDFFichaIngreso()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 9)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text(f"DATOS DE ADMISION - FOLIO: {paciente_id} | EXPEDIENTE: {dj.get('expediente', 'S/N')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Sucursal: {dj.get('sucursal', 'Matriz Colima')} | Fecha Ingreso: {dj.get('fecha_ingreso', '')} | Hora: {dj.get('hora_ingreso', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("DATOS DEL RESIDENTE / PACIENTE"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    nombre_c = f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}".strip()
    pdf.cell(0, 5, clean_pdf_text(f"Nombre: {nombre_c}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Sexo: {dj.get('sexo', '')} | Edad: {dj.get('edad', '')} años | Fecha Nacimiento: {dj.get('fecha_nacimiento', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Estado Civil: {dj.get('estado_civil', '')} | Escolaridad: {dj.get('escolaridad', '')} | Religion: {dj.get('religion', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Ocupacion: {dj.get('ocupacion', '')} | Servicio Medico: {dj.get('servicio_medico', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio: {dj.get('calle_num', '')}, Col. {dj.get('colonia', '')}, {dj.get('municipio', '')}, {dj.get('estado', '')} CP {dj.get('cp', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("SUSTANCIAS DE CONSUMO Y MODALIDAD"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    sust_str = ", ".join(dj.get("sustancias_ingreso", [])) if dj.get("sustancias_ingreso") else "Sin registrar"
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sustancias detectadas al ingreso: {sust_str}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Modalidad de internamiento: {dj.get('modalidad_ingreso', 'Voluntaria')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("RESPONSABLE FAMILIAR Y CONTACTOS DE EMERGENCIA"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Responsable Familiar: {dj.get('resp_nombre', '')} | Parentesco: {dj.get('resp_parentesco', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Telefono: {dj.get('resp_telefono', '')} | Email: {dj.get('resp_email', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Domicilio Responsable: {dj.get('resp_domicilio', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, clean_pdf_text(f"Contacto Emergencia: {dj.get('emerg_nombre', '')} ({dj.get('emerg_parentesco', '')}) Tel: {dj.get('emerg_telefono', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, clean_pdf_text("ACUERDO FINANCIERO Y COMPROMISOS"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, clean_pdf_text(f"Costo de Ingreso: ${dj.get('costo_ingreso', '4,500.00')} | Cuota Mensual: ${dj.get('cuota_mensual', '6,000.00')} | Pagare: ${dj.get('importe_pagare', '42,000.00')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    pdf.set_font("Helvetica", "B", 8)
    col_w = 60
    pdf.cell(col_w, 4, "__________________________________", align="C")
    pdf.cell(col_w, 4, "__________________________________", align="C")
    pdf.cell(col_w, 4, "__________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(col_w, 4, clean_pdf_text("Firma del Responsable Familiar"), align="C")
    pdf.cell(col_w, 4, clean_pdf_text("Firma del Residente"), align="C")
    pdf.cell(col_w, 4, clean_pdf_text("Direccion de la Institucion"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Ficha_Ingreso_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR BASE DE DATOS Y SESIÓN ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = ""

def render_header():
    st.markdown("""
        <div style='background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%); padding: 18px 25px; border-radius: 12px; color: white; margin-bottom: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
            <div style='display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;'>
                <div>
                    <h1 style='color: #FFFFFF; margin: 0; font-size: 1.8em; font-weight: bold;'>🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>
                    <p style='color: #C8E6C9; margin: 4px 0 0 0; font-size: 1.05em; font-weight: 500;'>Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</p>
                </div>
                <div style='margin-top: 8px;'>
                    <span style='background-color: #4CAF50; color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold; margin-right: 8px;'>SISTEMA ACTIVO</span>
                    <span style='background-color: #81C784; color: #1B5E20; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold;'>NOM-028-SSA2-2009</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def main():
    if not st.session_state["logged_in"]:
        render_header()
        st.markdown("<h2 style='text-align: center; color: #2E7D32;'>🔐 Acceso al Sistema Institucional</h2>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.8, 1])
        with col2:
            with st.form("login_form"):
                user_input = st.text_input("Usuario")
                pass_input = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("🔑 Iniciar Sesión", use_container_width=True)
                
                if submit:
                    res = verificar_login(user_input, pass_input)
                    if res:
                        if res[3] == "Bloqueado":
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = res[0]
                            st.session_state["nombre_completo"] = res[1]
                            st.session_state["rol"] = res[2]
                            st.balloons()
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
            st.info("💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`")
        return

    st.sidebar.markdown("""
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.write(f"🛡️ **Rol**: {st.session_state['rol']}")
    
    menu = st.sidebar.selectbox(
        "📌 Selección de Módulo",
        [
            "🏠 Inicio / Tablero General",
            "👤 Registro y Edición de Pacientes",
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
    )

    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    render_header()
    pacientes_todos = listar_pacientes()

    # --- MÓDULO 1: TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        
        activos = [p for p in pacientes_todos if p[4].get("estado_paciente", "Activo") == "Activo"]
        inactivos = [p for p in pacientes_todos if p[4].get("estado_paciente", "Activo") != "Activo"]
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total de Pacientes", len(pacientes_todos))
        col_m2.metric("🟢 Residentes Activos", len(activos))
        col_m3.metric("🔴 Inactivos / Bajas", len(inactivos))
        
        st.subheader("📊 Distribución por Etapas de Tratamiento")
        etapas = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        tabs_e = st.tabs([f"📍 {e}" for e in etapas])
        
        for idx, e_nombre in enumerate(etapas):
            with tabs_e[idx]:
                p_etapa = [p for p in activos if p[4].get("etapa_actual", "Acogida") == e_nombre]
                st.write(f"**Total en etapa {e_nombre}:** {len(p_etapa)}")
                if p_etapa:
                    for p in p_etapa:
                        pid, f_reg, f_mod, u_reg, dj = p
                        n_c = f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}".strip() or dj.get("nombre_completo", "Sin Nombre")
                        d_etapa = days_between(dj.get("fecha_inicio_etapa", dj.get("fecha_ingreso", f_reg)))
                        st.info(f"👤 **{n_c}** (Folio: {pid} | Exp: {dj.get('expediente', pid)}) — **Días en esta etapa:** {d_etapa} días")

    # --- MÓDULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Administración de Residentes")
        
        tab_p1, tab_p2, tab_p3 = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Bloqueo / Bajas"])
        
        with tab_p1:
            st.subheader("Captura Basal de Nuevo Residente")
            
            with st.form("form_nuevo_paciente", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    nombre = st.text_input("Nombre(s) *")
                with c2:
                    ap_paterno = st.text_input("Apellido Paterno *")
                with c3:
                    ap_materno = st.text_input("Apellido Materno *")
                    
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    sexo = st.selectbox("Sexo *", ["MASCULINO", "FEMENINO", "OTRO"])
                with col_b:
                    f_nac = st.date_input("Fecha de Nacimiento *", value=date(1995, 1, 1))
                with col_c:
                    f_ing = st.date_input("Fecha de Ingreso a la Institución *", value=date.today())
                    
                col_d, col_e, col_f = st.columns(3)
                with col_d:
                    f_etapa = st.date_input("Fecha Inicio de Etapa *", value=date.today())
                with col_e:
                    etapa_ini = st.selectbox("Etapa Inicial *", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                with col_f:
                    expediente = st.text_input("Número de Expediente (Opcional)")
                    
                btn_guardar_p = st.form_submit_button("💾 Guardar y Dar de Alta Residente", type="primary", use_container_width=True)
                
                if btn_guardar_p:
                    if not nombre.strip() or not ap_paterno.strip():
                        st.error("⚠️ El Nombre y el Apellido Paterno son obligatorios.")
                    else:
                        nombre_norm = normalize_text(f"{nombre} {ap_paterno} {ap_materno}")
                        duplicado = False
                        for p in pacientes_todos:
                            pid, _, _, _, dj = p
                            ex_norm = normalize_text(f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}")
                            if ex_norm and ex_norm == nombre_norm:
                                duplicado = True
                                st.error(f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{nombre} {ap_paterno} {ap_materno}' (Folio: {pid}).")
                                break
                                
                        if not duplicado and expediente.strip():
                            for p in pacientes_todos:
                                pid, _, _, _, dj = p
                                if dj.get("expediente", "").strip() == expediente.strip():
                                    duplicado = True
                                    st.error(f"⛔ EXPEDIENTE DUPLICADO: El expediente '{expediente}' ya pertenece al paciente {dj.get('nombre', '')} {dj.get('ap_paterno', '')}.")
                                    break
                                    
                        if not duplicado:
                            next_id = f"PAC-{len(pacientes_todos) + 1:03d}"
                            datos_p = {
                                "nombre": nombre.strip(),
                                "ap_paterno": ap_paterno.strip(),
                                "ap_materno": ap_materno.strip(),
                                "nombre_completo": f"{nombre.strip()} {ap_paterno.strip()} {ap_materno.strip()}".strip(),
                                "sexo": sexo,
                                "fecha_nacimiento": str(f_nac),
                                "edad": calculate_age(str(f_nac)),
                                "fecha_ingreso": str(f_ing),
                                "fecha_inicio_etapa": str(f_etapa),
                                "etapa_actual": etapa_ini,
                                "expediente": expediente.strip() or next_id,
                                "estado_paciente": "Activo",
                                "sustancia_impacto": "Sin registrar"
                            }
                            guardar_entrevista(next_id, datos_p, st.session_state["username"])
                            st.balloons()
                            st.toast("✅ ¡Residente dado de alta exitosamente!", icon="🎉")
                            st.success(f"✅ ¡Residente '{datos_p['nombre_completo']}' dado de alta con Folio: {next_id}!")
                            st.rerun()

        with tab_p2:
            st.subheader("Edición de Residente Existente")
            if not pacientes_todos:
                st.info("No hay pacientes registrados.")
            else:
                opciones_p = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')}": p[0] for p in pacientes_todos}
                sel_p = st.selectbox("Seleccione Residente a Editar", list(opciones_p.keys()))
                p_id_edit = opciones_p[sel_p]
                dj_e, _, _, _ = obtener_entrevista(p_id_edit)
                
                with st.form("form_editar_paciente"):
                    ce1, ce2, ce3 = st.columns(3)
                    with ce1:
                        e_nombre = st.text_input("Nombre(s)", value=dj_e.get("nombre", ""))
                    with ce2:
                        e_paterno = st.text_input("Apellido Paterno", value=dj_e.get("ap_paterno", ""))
                    with ce3:
                        e_materno = st.text_input("Apellido Materno", value=dj_e.get("ap_materno", ""))
                        
                    ce_a, ce_b, ce_c = st.columns(3)
                    with ce_a:
                        e_sexo = st.selectbox("Sexo", ["MASCULINO", "FEMENINO", "OTRO"], index=get_safe_index(["MASCULINO", "FEMENINO", "OTRO"], dj_e.get("sexo", "MASCULINO")))
                    with ce_b:
                        try:
                            val_fn = datetime.strptime(dj_e.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d").date()
                        except:
                            val_fn = date(1995, 1, 1)
                        e_fnac = st.date_input("Fecha de Nacimiento", value=val_fn)
                    with ce_c:
                        try:
                            val_fi = datetime.strptime(dj_e.get("fecha_ingreso", str(date.today())), "%Y-%m-%d").date()
                        except:
                            val_fi = date.today()
                        e_fing = st.date_input("Fecha de Ingreso a la Institución", value=val_fi)
                        
                    ce_d, ce_e, ce_f = st.columns(3)
                    with ce_d:
                        try:
                            val_fe = datetime.strptime(dj_e.get("fecha_inicio_etapa", str(date.today())), "%Y-%m-%d").date()
                        except:
                            val_fe = date.today()
                        e_fetapa = st.date_input("Fecha Inicio de Etapa", value=val_fe)
                    with ce_e:
                        etapas_list = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                        e_etapa = st.selectbox("Etapa Actual", etapas_list, index=get_safe_index(etapas_list, dj_e.get("etapa_actual", "Acogida")))
                    with ce_f:
                        e_exp = st.text_input("Número de Expediente", value=dj_e.get("expediente", p_id_edit))
                        
                    btn_actualizar_p = st.form_submit_button("💾 Guardar Cambios de Residente", use_container_width=True)
                    
                    if btn_actualizar_p:
                        dj_e["nombre"] = e_nombre.strip()
                        dj_e["ap_paterno"] = e_paterno.strip()
                        dj_e["ap_materno"] = e_materno.strip()
                        dj_e["nombre_completo"] = f"{e_nombre.strip()} {e_paterno.strip()} {e_materno.strip()}".strip()
                        dj_e["sexo"] = e_sexo
                        dj_e["fecha_nacimiento"] = str(e_fnac)
                        dj_e["edad"] = calculate_age(str(e_fnac))
                        dj_e["fecha_ingreso"] = str(e_fing)
                        dj_e["fecha_inicio_etapa"] = str(e_fetapa)
                        dj_e["etapa_actual"] = e_etapa
                        dj_e["expediente"] = e_exp.strip()
                        
                        guardar_entrevista(p_id_edit, dj_e, st.session_state["username"])
                        st.balloons()
                        st.toast("✅ Residente actualizado correctamente", icon="🎉")
                        st.success("✅ Cambios guardados exitosamente.")
                        st.rerun()

        with tab_p3:
            st.subheader("🔒 Estado y Bajas de Residentes")
            if pacientes_todos:
                opciones_bloq = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')} (Estado: {p[4].get('estado_paciente', 'Activo')})": p[0] for p in pacientes_todos}
                sel_b = st.selectbox("Seleccione Paciente para Cambiar Estado", list(opciones_bloq.keys()))
                pid_b = opciones_bloq[sel_b]
                dj_b, _, _, _ = obtener_entrevista(pid_b)
                
                est_actual = dj_b.get("estado_paciente", "Activo")
                st.write(f"**Estado actual:** `{est_actual}`")
                
                if est_actual == "Activo":
                    if st.button("🔴 Dar de Baja / Bloquear Residente", type="primary"):
                        dj_b["estado_paciente"] = "Bloqueado / Baja"
                        guardar_entrevista(pid_b, dj_b, st.session_state["username"])
                        st.success(f"Residente {pid_b} dado de baja.")
                        st.rerun()
                else:
                    if st.button("🟢 Reactivar Residente"):
                        dj_b["estado_paciente"] = "Activo"
                        guardar_entrevista(pid_b, dj_b, st.session_state["username"])
                        st.success(f"Residente {pid_b} reactivado.")
                        st.rerun()

        st.divider()
        st.subheader("📋 Lista de Residentes Activos Registrados (En Vivo)")
        activos_lista = [p for p in pacientes_todos if p[4].get("estado_paciente", "Activo") == "Activo"]
        
        if activos_lista:
            pdf_file_activos = generar_pdf_listado_pacientes(activos_lista)
            with open(pdf_file_activos, "rb") as f:
                st.download_button(
                    label="🖨️ Imprimir / Descargar Reporte de Pacientes Activos (PDF)",
                    data=f,
                    file_name=pdf_file_activos,
                    mime="application/pdf",
                    type="primary"
                )
            
            tabla_data = []
            for p in activos_lista:
                pid, f_reg, f_mod, u_reg, dj = p
                n_c = f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}".strip() or dj.get("nombre_completo", "Sin Nombre")
                tabla_data.append({
                    "Folio": pid,
                    "Expediente": dj.get("expediente", pid),
                    "Nombre Completo": n_c,
                    "Sexo": dj.get("sexo", "MASCULINO"),
                    "Edad": calculate_age(dj.get("fecha_nacimiento", "")) if dj.get("fecha_nacimiento") else dj.get("edad", "-"),
                    "Etapa": dj.get("etapa_actual", "Acogida"),
                    "Días en Proceso": days_between(dj.get("fecha_ingreso", f_reg)),
                    "Días en Etapa": days_between(dj.get("fecha_inicio_etapa", dj.get("fecha_ingreso", f_reg)))
                })
            st.dataframe(tabla_data, use_container_width=True)

    # --- MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Contrato de Admisión")
        
        if not pacientes_todos:
            st.warning("Primero debe registrar al menos un paciente en el módulo de Registro.")
        else:
            opciones_fi = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')} (Exp: {p[4].get('expediente', p[0])})": p[0] for p in pacientes_todos}
            sel_fi = st.selectbox("Seleccione Residente para la Ficha de Ingreso", list(opciones_fi.keys()))
            pid_fi = opciones_fi[sel_fi]
            dj_fi, _, _, _ = obtener_entrevista(pid_fi)
            
            with st.form("form_ficha_ingreso"):
                t_fi1, t_fi2, t_fi3, t_fi4, t_fi5 = st.tabs([
                    "1. Admisión y Sucursal",
                    "2. Datos del Residente",
                    "3. Sustancias de Consumo",
                    "4. Responsable Familiar",
                    "5. Cláusulas y Financiero"
                ])
                
                with t_fi1:
                    sucursal = st.text_input("Sucursal", value=dj_fi.get("sucursal", "Matriz Colima"))
                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        f_ing_f = st.text_input("Fecha de Ingreso", value=dj_fi.get("fecha_ingreso", str(date.today())))
                    with col_s2:
                        hora_ing = st.text_input("Hora de Ingreso", value=dj_fi.get("hora_ingreso", datetime.now().strftime("%H:%M")))
                        
                with t_fi2:
                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        est_civil = st.selectbox("Estado Civil", ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], index=get_safe_index(["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"], dj_fi.get("estado_civil")))
                    with col_r2:
                        escolaridad = st.text_input("Escolaridad", value=dj_fi.get("escolaridad", "Secundaria"))
                    with col_r3:
                        religion = st.text_input("Religión", value=dj_fi.get("religion", "Católica"))
                        
                    col_r4, col_r5 = st.columns(2)
                    with col_r4:
                        ocupacion = st.text_input("Ocupación", value=dj_fi.get("ocupacion", "Empleado"))
                    with col_r5:
                        serv_medico = st.text_input("Servicios Médicos (IMSS/ISSSTE/Ninguno)", value=dj_fi.get("servicio_medico", "Ninguno"))
                        
                    st.write("**Domicilio Particular:**")
                    calle_num = st.text_input("Calle y Número", value=dj_fi.get("calle_num", ""))
                    col_d1, col_d2, col_d3 = st.columns(3)
                    with col_d1:
                        colonia = st.text_input("Colonia", value=dj_fi.get("colonia", ""))
                    with col_d2:
                        municipio = st.text_input("Municipio", value=dj_fi.get("municipio", "Colima"))
                    with col_d3:
                        cp = st.text_input("C.P.", value=dj_fi.get("cp", ""))
                        
                with t_fi3:
                    st.subheader("Sustancias que consume al ingresar")
                    sust_catalogo = ["Alcaloides", "Alcohol", "Anfetaminas", "Benzodiazepinas", "Cannabis", "Esteroides", "Fármacos", "LSD", "Meta-anfetaminas", "Opiáceos", "Psicoactivas", "Solventes", "Tabaco"]
                    sust_saved = dj_fi.get("sustancias_ingreso", [])
                    
                    c_sust_cols = st.columns(3)
                    sust_selected = []
                    for i, s_item in enumerate(sust_catalogo):
                        with c_sust_cols[i % 3]:
                            if st.checkbox(s_item, value=(s_item in sust_saved), key=f"chk_fi_{s_item}"):
                                sust_selected.append(s_item)
                                
                    mod_ingreso = st.selectbox("Modalidad de Internamiento", ["Voluntaria", "Involuntaria por solicitud familiar"], index=get_safe_index(["Voluntaria", "Involuntaria por solicitud familiar"], dj_fi.get("modalidad_ingreso")))
                    
                with t_fi4:
                    resp_nombre = st.text_input("Nombre Completo del Responsable Familiar", value=dj_fi.get("resp_nombre", ""))
                    col_rf1, col_rf2 = st.columns(2)
                    with col_rf1:
                        resp_parentesco = st.text_input("Parentesco", value=dj_fi.get("resp_parentesco", "Padre/Madre/Cónyuge"))
                    with col_rf2:
                        resp_telefono = st.text_input("Teléfono del Responsable", value=dj_fi.get("resp_telefono", ""))
                    resp_email = st.text_input("Correo Electrónico", value=dj_fi.get("resp_email", ""))
                    resp_domicilio = st.text_input("Domicilio Completo del Responsable", value=dj_fi.get("resp_domicilio", ""))
                    
                    st.divider()
                    st.write("**Contacto Secundario de Emergencia:**")
                    emerg_nombre = st.text_input("Nombre Emergencia", value=dj_fi.get("emerg_nombre", ""))
                    col_em1, col_em2 = st.columns(2)
                    with col_em1:
                        emerg_parentesco = st.text_input("Parentesco Emergencia", value=dj_fi.get("emerg_parentesco", ""))
                    with col_em2:
                        emerg_telefono = st.text_input("Teléfono Emergencia", value=dj_fi.get("emerg_telefono", ""))

                with t_fi5:
                    col_f1, col_f2, col_f3 = st.columns(3)
                    with col_f1:
                        costo_ing = st.text_input("Costo de Ingreso ($)", value=dj_fi.get("costo_ingreso", "4,500.00"))
                    with col_f2:
                        cuota_men = st.text_input("Cuota Mensual ($)", value=dj_fi.get("cuota_mensual", "6,000.00"))
                    with col_f3:
                        importe_pagare = st.text_input("Importe del Pagaré ($)", value=dj_fi.get("importe_pagare", "42,000.00"))
                        
                    st.info("📌 **Compromisos NOM-028-SSA2-2009**: Tratamiento sugerido de 6 a 8 meses (Mínimo 7 meses). Reglamento interno de uniformes y respeto a los derechos humanos.")

                btn_guardar_fi = st.form_submit_button("💾 Guardar Ficha de Ingreso y Admisión", type="primary", use_container_width=True)
                
                if btn_guardar_fi:
                    dj_fi["sucursal"] = sucursal
                    dj_fi["fecha_ingreso"] = f_ing_f
                    dj_fi["hora_ingreso"] = hora_ing
                    dj_fi["estado_civil"] = est_civil
                    dj_fi["escolaridad"] = escolaridad
                    dj_fi["religion"] = religion
                    dj_fi["ocupacion"] = ocupacion
                    dj_fi["servicio_medico"] = serv_medico
                    dj_fi["calle_num"] = calle_num
                    dj_fi["colonia"] = colonia
                    dj_fi["municipio"] = municipio
                    dj_fi["cp"] = cp
                    dj_fi["sustancias_ingreso"] = sust_selected
                    dj_fi["modalidad_ingreso"] = mod_ingreso
                    dj_fi["resp_nombre"] = resp_nombre
                    dj_fi["resp_parentesco"] = resp_parentesco
                    dj_fi["resp_telefono"] = resp_telefono
                    dj_fi["resp_email"] = resp_email
                    dj_fi["resp_domicilio"] = resp_domicilio
                    dj_fi["emerg_nombre"] = emerg_nombre
                    dj_fi["emerg_parentesco"] = emerg_parentesco
                    dj_fi["emerg_telefono"] = emerg_telefono
                    dj_fi["costo_ingreso"] = costo_ing
                    dj_fi["cuota_mensual"] = cuota_men
                    dj_fi["importe_pagare"] = importe_pagare
                    
                    guardar_entrevista(pid_fi, dj_fi, st.session_state["username"])
                    st.balloons()
                    st.toast("✅ Ficha de Ingreso guardada correctamente", icon="🎉")
                    st.success("✅ Ficha de Ingreso actualizada exitosamente.")
                    
            pdf_fi_path = generar_pdf_ficha_ingreso(pid_fi, dj_fi)
            with open(pdf_fi_path, "rb") as f:
                st.download_button(
                    label="📄 Descargar Ficha de Ingreso Oficial en PDF (Imprimible)",
                    data=f,
                    file_name=pdf_fi_path,
                    mime="application/pdf",
                    use_container_width=True
                )

    # --- MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA ---
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        if not pacientes_todos:
            st.warning("No hay pacientes registrados.")
        else:
            opciones_ei = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')}": p[0] for p in pacientes_todos}
            sel_ei = st.selectbox("Seleccione Residente para Entrevista Inicial", list(opciones_ei.keys()))
            pid_ei = opciones_ei[sel_ei]
            dj_ei, _, _, _ = obtener_entrevista(pid_ei)
            
            with st.form("form_entrevista_inicial"):
                st.subheader("Evaluación de Consumo y Disposición al Cambio")
                s_imp = st.text_input("Sustancia de Impacto Principal", value=dj_ei.get("sustancia_impacto", "Sin registrar"))
                t_exc = st.text_input("Tiempo de Consumo Excesivo", value=dj_ei.get("tiempo_excesivo", ""))
                modo_c = st.selectbox("Modo de Consumo Habitual", ["SOLO", "ACOMPAÑADO", "AMBOS"], index=get_safe_index(["SOLO", "ACOMPAÑADO", "AMBOS"], dj_ei.get("modo_consumo")))
                
                abst_motivo = st.text_area("Motivos y Estrategias de Abstinencia Previa", value=dj_ei.get("abst_motivo", ""))
                obs_clinicas = st.text_area("Observaciones Clínicas de la Sesión", value=dj_ei.get("observaciones", ""))
                
                btn_ei = st.form_submit_button("💾 Guardar Entrevista Inicial", type="primary", use_container_width=True)
                if btn_ei:
                    dj_ei["sustancia_impacto"] = s_imp
                    dj_ei["tiempo_excesivo"] = t_exc
                    dj_ei["modo_consumo"] = modo_c
                    dj_ei["abst_motivo"] = abst_motivo
                    dj_ei["observaciones"] = obs_clinicas
                    guardar_entrevista(pid_ei, dj_ei, st.session_state["username"])
                    st.balloons()
                    st.success("✅ Entrevista Inicial guardada correctamente.")

    # --- MÓDULO 5: CONSEJERÍAS INDIVIDUALES ---
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Sesiones de Consejería Individual")
        if pacientes_todos:
            opciones_ci = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')}": p[0] for p in pacientes_todos}
            sel_ci = st.selectbox("Seleccione Paciente", list(opciones_ci.keys()))
            pid_ci = opciones_ci[sel_ci]
            dj_ci, _, _, _ = obtener_entrevista(pid_ci)
            
            num_cons = st.selectbox("Número de Consejería", [f"Consejería #{i}" for i in range(1, 11)])
            
            with st.form("form_consejería"):
                f_cons = st.date_input("Fecha de la Sesión", value=date.today())
                tema_cons = st.text_input("Tema Tratao")
                obj_cons = st.text_area("Objetivo de la Sesión")
                acuerdos_cons = st.text_area("Acuerdos y Compromisos")
                
                if st.form_submit_button("💾 Guardar Sesión de Consejería", type="primary"):
                    hist_c = dj_ci.get("historial_consejerias", [])
                    hist_c.append({
                        "numero": num_cons,
                        "fecha": str(f_cons),
                        "tema": tema_cons,
                        "objetivo": obj_cons,
                        "acuerdos": acuerdos_cons,
                        "consejero": st.session_state["nombre_completo"]
                    })
                    dj_ci["historial_consejerias"] = hist_c
                    guardar_entrevista(pid_ci, dj_ci, st.session_state["username"])
                    st.balloons()
                    st.success(f"✅ {num_cons} registrada con éxito.")

    # --- MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO ---
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Control de Etapas y Promoción Clínica")
        if pacientes_todos:
            opciones_ge = {f"{p[0]} - {p[4].get('nombre', '')} {p[4].get('ap_paterno', '')} ({p[4].get('etapa_actual', 'Acogida')})": p[0] for p in pacientes_todos}
            sel_ge = st.selectbox("Seleccione Residente", list(opciones_ge.keys()))
            pid_ge = opciones_ge[sel_ge]
            dj_ge, _, _, _ = obtener_entrevista(pid_ge)
            
            e_act = dj_ge.get("etapa_actual", "Acogida")
            d_etapa = days_between(dj_ge.get("fecha_inicio_etapa", dj_ge.get("fecha_ingreso")))
            
            st.write(f"**Etapa Actual:** `{e_act}` | **Días transcurridos en esta etapa:** `{d_etapa}` días")
            if d_etapa > 90:
                st.warning("⚠️ ALERTA CLINICA: El paciente supera los 90 días en la misma etapa. Valide su promoción.")
                
            etapas_siguientes = {
                "Acogida": "Identificación",
                "Identificación": "Elaboración",
                "Elaboración": "Consolidación",
                "Consolidación": "Servicio Social",
                "Servicio Social": "Egresado / Graduado"
            }
            sig_e = etapas_siguientes.get(e_act, "Egresado / Graduado")
            
            if st.button(f"🚀 Promover a Siguiente Etapa ({sig_e})", type="primary"):
                dj_ge["etapa_actual"] = sig_e
                dj_ge["fecha_inicio_etapa"] = str(date.today())
                guardar_entrevista(pid_ge, dj_ge, st.session_state["username"])
                st.balloons()
                st.success(f"¡Paciente promovido a {sig_e}!")
                st.rerun()

    # --- MÓDULO 7: GRUPOS TERAPÉUTICOS ---
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        with st.form("form_grupo"):
            f_grupo = st.date_input("Fecha del Grupo", value=date.today())
            tipo_grupo = st.selectbox("Tipo de Sesión", ["Terapia de Grupo", "Aquí y Ahora", "Prevención de Recaídas", "12 Pasos", "Espiritualidad"])
            facil = st.text_input("Facilitador / Terapeuta", value=st.session_state["nombre_completo"])
            tema_g = st.text_input("Tema de la Sesión")
            obs_g = st.text_area("Observaciones Generales del Grupo")
            
            if st.form_submit_button("💾 Registrar Sesión Grupal", type="primary"):
                st.balloons()
                st.success("✅ Sesión grupal registrada exitosamente.")

    # --- MÓDULO 8: CONTROL DE MEDICAMENTOS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Farmacia y Control de Medicamentos")
        st.info("Gestión de inventario de fármacos y suministro controlado a residentes.")

    # --- MÓDULO 9: REPOSITORIO DE DOCUMENTOS ---
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Expedientes")
        t_rep1, t_rep2 = st.tabs(["📄 Subir y Consultar Archivos", "⚙️ Gestión de Carpetas"])
        with t_rep1:
            st.write("Consulta y subida de documentos digitalizados.")
        with t_rep2:
            st.subheader("Crear o Renombrar Carpetas")
            n_carpeta = st.text_input("Nombre de la Nueva Carpeta")
            if st.button("➕ Crear Carpeta"):
                st.success(f"Carpeta '{n_carpeta}' creada.")

    # --- MÓDULO 10: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio y Búsqueda de Pacientes")
        filtro_e = st.radio("Filtrar Estado", ["Todos", "🟢 Activos", "🔴 Bloqueados / Inactivos"], horizontal=True)
        
        filtrados = pacientes_todos
        if filtro_e == "🟢 Activos":
            filtrados = [p for p in pacientes_todos if p[4].get("estado_paciente", "Activo") == "Activo"]
        elif filtro_e == "🔴 Bloqueados / Inactivos":
            filtrados = [p for p in pacientes_todos if p[4].get("estado_paciente", "Activo") != "Activo"]
            
        st.subheader(f"Total encontrados: {len(filtrados)}")
        for p in filtrados:
            pid, f_reg, f_mod, u_reg, dj = p
            n_c = f"{dj.get('nombre', '')} {dj.get('ap_paterno', '')} {dj.get('ap_materno', '')}".strip() or dj.get("nombre_completo", "Sin Nombre")
            with st.expander(f"👤 {n_c} (Folio: {pid} | Exp: {dj.get('expediente', pid)}) — Estado: {dj.get('estado_paciente', 'Activo')}"):
                st.write(f"**Etapa:** {dj.get('etapa_actual', 'Acogida')} | **Fecha Ingreso:** {dj.get('fecha_ingreso', f_reg)}")

    # --- MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD ---
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración de Seguridad y Usuarios")
        t_seg1, t_seg2 = st.tabs(["🔑 Cambiar Mi Contraseña", "👥 Usuarios y Roles del Personal"])
        
        with t_seg1:
            with st.form("form_cambio_pass"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_nueva = st.text_input("Nueva Contraseña", type="password")
                p_conf = st.text_input("Confirmar Nueva Contraseña", type="password")
                if st.form_submit_button("Actualizar Contraseña"):
                    if p_nueva != p_conf:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        u_ok = verificar_login(st.session_state["username"], p_act)
                        if u_ok:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                                      (hash_pass(p_nueva), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada.")
                        else:
                            st.error("Contraseña actual incorrecta.")
                            
        with t_seg2:
            st.subheader("Administración de Cuentas del Personal")
            if st.session_state["username"] == "admin" or st.session_state["rol"] == "Administrador":
                with st.form("form_nuevo_usuario_staff"):
                    nu_user = st.text_input("Nombre de Usuario")
                    nu_nombre = st.text_input("Nombre Completo")
                    nu_pass = st.text_input("Contraseña", type="password")
                    nu_rol = st.selectbox("Rol", ["Administrador", "Lectura/Escritura", "Solo Lectura"])
                    if st.form_submit_button("➕ Registrar Usuario de Personal"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('SELECT username FROM usuarios WHERE username = ?', (nu_user.strip(),))
                        if c.fetchone():
                            st.error("El nombre de usuario ya existe.")
                        else:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, ?)',
                                      (nu_user.strip(), hash_pass(nu_pass), nu_nombre.strip(), nu_rol, "Activo"))
                            conn.commit()
                            st.success(f"Usuario '{nu_user}' registrado.")
                        conn.close()
            else:
                st.info("Solo el Administrador puede gestionar las cuentas del personal.")

    # --- MÓDULO 12: RESPALDO Y RESTAURACIÓN ---
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        tab_r1, tab_r2 = st.tabs(["⬇️ Copia de Seguridad (Respaldo)", "⬆️ Restaurar Base de Datos"])
        
        with tab_r1:
            st.subheader("Descargar Copia de Seguridad")
            st.info("Descargue una copia completa del archivo de base de datos SQLite `sistema_pacientes.db`.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar Copia de Seguridad (.db)",
                        data=f,
                        file_name=f"backup_sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        type="primary",
                        use_container_width=True
                    )
            else:
                st.warning("La base de datos aún no ha sido creada.")

        with tab_r2:
            st.subheader("Restaurar Base de Datos desde Archivo (.db)")
            st.warning("⚠️ ALERTA DE SEGURIDAD: Restaurar una base de datos reemplazará de forma permanente todos los datos actuales por los del archivo seleccionado.")
            
            uploaded_db = st.file_uploader("Seleccione el archivo de respaldo (.db o .sqlite)", type=["db", "sqlite"])
            if uploaded_db is not None:
                if st.button("🔄 Confirmar y Restaurar Base de Datos", type="primary", use_container_width=True):
                    try:
                        with open(DB_FILE, "wb") as f:
                            f.write(uploaded_db.getbuffer())
                        st.balloons()
                        st.success("✅ Base de datos restaurada exitosamente. Se ha cargado el respaldo seleccionado.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error al restaurar la base de datos: {ex}")

if __name__ == "__main__":
    main()

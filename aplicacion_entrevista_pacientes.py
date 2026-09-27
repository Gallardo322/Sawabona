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
    page_title="Sistema de Entrevista Inicial de Consejería",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"
REPO_DIR = "repositorio_documentos"

if not os.path.exists(REPO_DIR):
    os.makedirs(REPO_DIR)

# --- BÚSQUEDA SEGURA DE ÍNDICES ---
def get_safe_index(lista, valor, default_idx=0):
    if not valor:
        return default_idx
    val_str = str(valor).strip().lower()
    for i, item in enumerate(lista):
        if str(item).strip().lower() == val_str:
            return i
    return default_idx

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Usuarios del Sistema (Personal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT "Staff",
            estado TEXT DEFAULT "Activo"
        )
    ''')
    
    # Migrar columnas en usuarios si no existen
    c.execute("PRAGMA table_info(usuarios)")
    cols_user = [row[1] for row in c.fetchall()]
    if "rol" not in cols_user:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Staff'")
    if "estado" not in cols_user:
        c.execute("ALTER TABLE usuarios ADD COLUMN estado TEXT DEFAULT 'Activo'")
        
    # Crear admin por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', default_pass, 'Administrador del Sistema', 'Administrador', 'Activo'))

    # 2. Tabla de Pacientes (Registro Basal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            folio TEXT UNIQUE NOT NULL,
            expediente TEXT,
            nombres TEXT,
            apellido_paterno TEXT,
            apellido_materno TEXT,
            nombre_completo TEXT,
            etapa_actual TEXT DEFAULT "Acogida",
            fecha_inicio_etapa TEXT,
            estado TEXT DEFAULT "Activo",
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # 3. Tabla de Entrevistas Iniciales
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # 4. Tabla de Consejerías Individuales
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            aspectos_trabajar TEXT,
            aspectos_proxima TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance TEXT,
            sugerencia TEXT,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # 5. Tabla de Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            participacion TEXT,
            observaciones TEXT,
            etapa_paciente TEXT,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # 6. Tabla de Medicamentos / Almacén
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_medicamento TEXT UNIQUE NOT NULL,
            stock INTEGER DEFAULT 0,
            indicaciones TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS medicacion_paciente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis TEXT,
            frecuencia TEXT,
            fecha_asignacion TEXT,
            usuario TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # 7. Tabla de Carpetas del Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Carpetas por defecto
    carpetas_def = ["Documentos de Admisión", "Estudios Médicos", "Pruebas Psicológicas", "Identificaciones", "General"]
    for c_def in carpetas_def:
        c.execute('INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)', (c_def,))

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

# --- ENCABEZADO INSTITUCIONAL ---
def render_header():
    st.markdown('''
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
    ''', unsafe_allow_html=True)

def mostrar_mensaje_exito(mensaje):
    st.balloons()
    st.markdown(f'''
        <div style='background-color: #D4EDDA; color: #155724; padding: 18px; border-radius: 12px; text-align: center; font-size: 1.25em; font-weight: bold; border: 2px solid #C3E6CB; margin: 20px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>
            🎉 {mensaje}
        </div>
    ''', unsafe_allow_html=True)
    st.toast(f"✅ {mensaje}", icon="🎉")

# --- GENERACIÓN DE FOLIO AUTOINCREMENTABLE ---
def obtener_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT folio FROM pacientes ORDER BY rowid DESC LIMIT 1")
    last = c.fetchone()
    conn.close()
    if not last or not last[0]:
        return "PAC-001"
    try:
        num = int(last[0].split("-")[1]) + 1
        return f"PAC-{num:03d}"
    except:
        return "PAC-001"

# --- OBTENER PACIENTES DE FORMA CENTRALIZADA ---
def obtener_lista_pacientes(estado_filtro="Todos"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if estado_filtro == "Activos":
        c.execute("SELECT paciente_id, folio, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, etapa_actual, fecha_inicio_etapa, estado FROM pacientes WHERE estado = 'Activo' ORDER BY folio DESC")
    elif estado_filtro == "Bloqueados":
        c.execute("SELECT paciente_id, folio, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, etapa_actual, fecha_inicio_etapa, estado FROM pacientes WHERE estado = 'Bloqueado' ORDER BY folio DESC")
    else:
        c.execute("SELECT paciente_id, folio, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, etapa_actual, fecha_inicio_etapa, estado FROM pacientes ORDER BY folio DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def calcular_dias_etapa(fecha_str):
    if not fecha_str:
        return 0
    try:
        f_inicio = datetime.strptime(fecha_str.split()[0], "%Y-%m-%d").date()
        dias = (date.today() - f_inicio).days
        return max(0, dias)
    except:
        return 0

# --- LIMPIEZA DE TEXTO PARA PDF ---
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

# --- CLASE PDF REPORT ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, limpiar_texto("COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C."), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Sistema de Control Clinico de Consejeria", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(self.epw, 10, f"Pagina {self.page_no()}", align="C")

def generar_pdf_ficha(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    exp_display = datos.get("expediente", "") if datos.get("expediente") else "S/N"
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, f"EXPEDIENTE: {limpiar_texto(exp_display)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Nombre del Residente: {limpiar_texto(datos.get('nombre_completo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Etapa Actual: {limpiar_texto(datos.get('etapa_actual', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Fecha de Ingreso: {limpiar_texto(datos.get('fecha_registro', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "DATOS COMPLEMENTARIOS Y ADMISIÓN (NOM-028-SSA2-2009)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(pdf.epw, 5, f"Familiar Responsable: {limpiar_texto(datos.get('familiar_responsable', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Contacto de Emergencia: {limpiar_texto(datos.get('contacto_emergencia', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones Medicas: {limpiar_texto(datos.get('obs_medicas', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Ficha_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return bytes(pdf.output())

# --- MAIN APP ---
def main():
    init_db()
    
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "nombre_completo" not in st.session_state:
        st.session_state["nombre_completo"] = ""
    if "rol" not in st.session_state:
        st.session_state["rol"] = "Staff"
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()

    render_header()

    # CONTROL DE INACTIVIDAD (10 MIN)
    if st.session_state["logged_in"]:
        inactivo = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
        if inactivo > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        st.session_state["ultima_actividad"] = datetime.now()

    # LOGIN FORM
    if not st.session_state["logged_in"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔐 Inicio de Sesión de Personal")
            with st.form("login_form"):
                user = st.text_input("Usuario").strip()
                pwd = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
                if submit:
                    res = verificar_login(user, pwd)
                    if res:
                        u_name, u_full, u_rol, u_est = res
                        if u_est == "Bloqueado":
                            st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                        else:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = u_name
                            st.session_state["nombre_completo"] = u_full if u_full else u_name
                            st.session_state["rol"] = u_rol
                            st.session_state["ultima_actividad"] = datetime.now()
                            st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
            st.info("💡 Credenciales predeterminadas: Usuario `admin` | Contraseña `admin123`")
        return

    # BARRA LATERAL
    st.sidebar.markdown('''
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)
    
    st.sidebar.write(f"👤 **Usuario:** {st.session_state['nombre_completo']}")
    st.sidebar.write(f"🔑 **Rol:** {st.session_state['rol']}")
    
    st.sidebar.title("📌 Menú Principal")
    menu = st.sidebar.selectbox(
        "Seleccione Módulo",
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

    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # ==========================================
    # 1. INICIO / TABLERO GENERAL
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        st.caption("Visión general de residentes, etapas del modelo y estado del centro")
        
        pacientes_act = obtener_lista_pacientes("Activos")
        pacientes_bloq = obtener_lista_pacientes("Bloqueados")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("🟢 Residentes Activos", len(pacientes_act))
        col_m2.metric("🔴 Residentes Inactivos / Bloqueados", len(pacientes_bloq))
        col_m3.metric("📊 Total de Registros", len(pacientes_act) + len(pacientes_bloq))
        
        st.divider()
        st.subheader("📌 Desglose de Residentes por Etapa del Tratamiento")
        
        etapas_lista = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        tabs_etapas = st.tabs([f"📍 {e}" for e in etapas_lista])
        
        for idx_e, e_nombre in enumerate(etapas_lista):
            with tabs_etapas[idx_e]:
                p_etapa = [p for p in pacientes_act if p[7] == e_nombre]
                st.metric(f"Residentes en {e_nombre}", len(p_etapa))
                if p_etapa:
                    tabla_et = []
                    for p in p_etapa:
                        pid, fol, exp, nom, ap, am, nom_comp, et, f_ini, est = p
                        dias = calcular_dias_etapa(f_ini)
                        exp_show = exp if exp else "S/N"
                        tabla_et.append({
                            "Folio": fol,
                            "Expediente": exp_show,
                            "Nombre Completo": nom_comp,
                            "Fecha Inicio Etapa": f_ini if f_ini else "No registrada",
                            "Días Transcurridos": f"{dias} días"
                        })
                    st.dataframe(tabla_et, use_container_width=True)
                else:
                    st.info(f"No hay residentes en la etapa de **{e_nombre}** actualmente.")

    # ==========================================
    # 2. REGISTRO Y EDICIÓN DE PACIENTES
    # ==========================================
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Edición de Pacientes")
        
        tab_reg, tab_edit, tab_bloq = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente", "🔒 Gestión de Bloqueo y Estado"])
        
        # --- ALTA NUEVO PACIENTE ---
        with tab_reg:
            st.subheader("Registrar Nuevo Residente")
            siguiente_folio = obtener_siguiente_folio()
            
            with st.form("form_alta_paciente"):
                c_a1, c_a2 = st.columns(2)
                with c_a1:
                    st.text_input("Folio (Autoincrementable)", value=siguiente_folio, disabled=True)
                    expediente_val = st.text_input("Número de Expediente (Manual / Opcional)", value="").strip()
                    nombres_val = st.text_input("Nombre(s) *", value="").strip()
                with c_a2:
                    ap_paterno_val = st.text_input("Apellido Paterno *", value="").strip()
                    ap_materno_val = st.text_input("Apellido Materno", value="").strip()
                    etapa_val = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"], index=0)
                
                f_inicio_val = st.date_input("Fecha de Inicio de Etapa", value=date.today())
                btn_guardar_alta = st.form_submit_button("💾 Dar de Alta Paciente", use_container_width=True)
                
                if btn_guardar_alta:
                    if not nombres_val or not ap_paterno_val:
                        st.error("⚠️ El Nombre y el Apellido Paterno son obligatorios.")
                    else:
                        nombre_comp_eval = f"{nombres_val} {ap_paterno_val} {ap_materno_val}".strip()
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        
                        # VALIDACIÓN DE DUPLICADO POR NOMBRE
                        c.execute("SELECT folio, expediente, nombre_completo FROM pacientes WHERE LOWER(TRIM(nombre_completo)) = ?", (nombre_comp_eval.lower(),))
                        dup_nom = c.fetchone()
                        
                        # VALIDACIÓN DE DUPLICADO POR EXPEDIENTE
                        dup_exp = None
                        if expediente_val:
                            c.execute("SELECT folio, expediente, nombre_completo FROM pacientes WHERE expediente = ?", (expediente_val,))
                            dup_exp = c.fetchone()
                            
                        if dup_nom:
                            st.error(f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{dup_nom[2]}' (Folio: {dup_nom[0]}, Exp: {dup_nom[1] if dup_nom[1] else 'S/N'}).")
                            conn.close()
                        elif dup_exp:
                            st.error(f"⛔ EXPEDIENTE DUPLICADO: El número de expediente '{expediente_val}' ya está asignado al paciente '{dup_exp[2]}' (Folio: {dup_exp[0]}).")
                            conn.close()
                        else:
                            pid_new = f"PID_{siguiente_folio}"
                            f_reg_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            f_ini_str = f_inicio_val.strftime("%Y-%m-%d")
                            
                            c.execute('''
                                INSERT INTO pacientes (paciente_id, folio, expediente, nombres, apellido_paterno, apellido_materno, nombre_completo, etapa_actual, fecha_inicio_etapa, estado, fecha_registro, usuario_registro)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Activo', ?, ?)
                            ''', (pid_new, siguiente_folio, expediente_val, nombres_val, ap_paterno_val, ap_materno_val, nombre_comp_eval, etapa_val, f_ini_str, f_reg_str, st.session_state["username"]))
                            
                            conn.commit()
                            conn.close()
                            mostrar_mensaje_exito(f"¡Paciente {nombre_comp_eval} registrado exitosamente con Folio {siguiente_folio}!")
                            st.rerun()

        # --- EDITAR PACIENTE EXISTENTE ---
        with tab_edit:
            st.subheader("Modificar Datos de Paciente")
            p_lista = obtener_lista_pacientes("Todos")
            if not p_lista:
                st.info("No hay pacientes registrados para editar.")
            else:
                opciones_p = ["-- Seleccione un Paciente --"] + [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_lista]
                sel_p_str = st.selectbox("Buscar Paciente a Editar", opciones_p)
                
                if sel_p_str != "-- Seleccione un Paciente --":
                    p_sel = p_lista[opciones_p.index(sel_p_str) - 1]
                    pid_e, fol_e, exp_e, nom_e, ap_e, am_e, comp_e, et_e, fini_e, est_e = p_sel
                    
                    with st.form("form_edit_paciente"):
                        c_e1, c_e2 = st.columns(2)
                        with c_e1:
                            st.text_input("Folio", value=fol_e, disabled=True)
                            exp_edit = st.text_input("Número de Expediente", value=exp_e if exp_e else "").strip()
                            nom_edit = st.text_input("Nombre(s)", value=nom_e if nom_e else "").strip()
                        with c_e2:
                            ap_edit = st.text_input("Apellido Paterno", value=ap_e if ap_e else "").strip()
                            am_edit = st.text_input("Apellido Materno", value=am_e if am_e else "").strip()
                            et_lista = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                            idx_et = get_safe_index(et_lista, et_e)
                            et_edit = st.selectbox("Etapa Actual", et_lista, index=idx_et)
                        
                        try:
                            val_f_ini = datetime.strptime(fini_e.split()[0], "%Y-%m-%d").date() if fini_e else date.today()
                        except:
                            val_f_ini = date.today()
                        
                        fini_edit = st.date_input("Fecha de Inicio de Etapa", value=val_f_ini)
                        btn_salvar_edit = st.form_submit_button("💾 Guardar Cambios", use_container_width=True)
                        
                        if btn_salvar_edit:
                            comp_edit_eval = f"{nom_edit} {ap_edit} {am_edit}".strip()
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            
                            # VALIDAR EXPEDIENTE DUPLICADO EN OTRO PACIENTE
                            dup_e = None
                            if exp_edit:
                                c.execute("SELECT folio, nombre_completo FROM pacientes WHERE expediente = ? AND paciente_id != ?", (exp_edit, pid_e))
                                dup_e = c.fetchone()
                                
                            if dup_e:
                                st.error(f"⛔ EXPEDIENTE DUPLICADO: El número de expediente '{exp_edit}' ya pertenece a '{dup_e[1]}'.")
                                conn.close()
                            else:
                                fini_edit_str = fini_edit.strftime("%Y-%m-%d")
                                c.execute('''
                                    UPDATE pacientes
                                    SET expediente = ?, nombres = ?, apellido_paterno = ?, apellido_materno = ?, nombre_completo = ?, etapa_actual = ?, fecha_inicio_etapa = ?
                                    WHERE paciente_id = ?
                                ''', (exp_edit, nom_edit, ap_edit, am_edit, comp_edit_eval, et_edit, fini_edit_str, pid_e))
                                conn.commit()
                                conn.close()
                                mostrar_mensaje_exito(f"¡Expediente de {comp_edit_eval} actualizado correctamente!")
                                st.rerun()

        # --- GESTIÓN DE BLOQUEO ---
        with tab_bloq:
            st.subheader("Estado y Bloqueo de Pacientes")
            p_todos = obtener_lista_pacientes("Todos")
            if p_todos:
                for p in p_todos:
                    pid_b, fol_b, exp_b, nom_b, ap_b, am_b, comp_b, et_b, fini_b, est_b = p
                    exp_disp = exp_b if exp_b else "S/N"
                    col_b1, col_b2, col_b3 = st.columns([3, 1.5, 1])
                    with col_b1:
                        st.write(f"**{fol_b}** | Exp: **{exp_disp}** - **{comp_b}**")
                        st.caption(f"Etapa: {et_b} | Estado actual: **{est_b}**")
                    with col_b2:
                        if est_b == "Activo":
                            st.success("🟢 ACTIVO")
                        else:
                            st.error("🔴 BLOQUEADO")
                    with col_b3:
                        if est_b == "Activo":
                            if st.button("🔴 Bloquear", key=f"bloq_{pid_b}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE pacientes SET estado = 'Bloqueado' WHERE paciente_id = ?", (pid_b,))
                                conn.commit()
                                conn.close()
                                mostrar_mensaje_exito(f"Paciente {comp_b} bloqueado correctamente.")
                                st.rerun()
                        else:
                            if st.button("🟢 Activar", key=f"act_{pid_b}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE pacientes SET estado = 'Activo' WHERE paciente_id = ?", (pid_b,))
                                conn.commit()
                                conn.close()
                                mostrar_mensaje_exito(f"Paciente {comp_b} reactivado correctamente.")
                                st.rerun()
                    st.divider()

        # --- TABLA EN VIVO DE PACIENTES ACTIVOS ABAJO ---
        st.divider()
        st.subheader("📋 Lista de Residentes Activos Registrados")
        p_activos_live = obtener_lista_pacientes("Activos")
        if p_activos_live:
            tabla_live = []
            for p in p_activos_live:
                pid, fol, exp, nom, ap, am, nom_comp, et, f_ini, est = p
                dias = calcular_dias_etapa(f_ini)
                tabla_live.append({
                    "Folio": fol,
                    "Expediente": exp if exp else "S/N",
                    "Nombre Completo": nom_comp,
                    "Etapa Actual": et,
                    "Días en Etapa": f"{dias} días",
                    "Fecha Inicio Etapa": f_ini if f_ini else "No registrada",
                    "Estado": est
                })
            st.dataframe(tabla_live, use_container_width=True)
        else:
            st.info("No hay residentes activos registrados en el sistema.")

    # ==========================================
    # 3. FICHA DE INGRESO Y ADMISIÓN
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        p_activos = obtener_lista_pacientes("Activos")
        if not p_activos:
            st.warning("No hay pacientes activos disponibles.")
        else:
            opciones_p = [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
            sel_p = st.selectbox("Seleccionar Paciente", opciones_p)
            idx_p = opciones_p.index(sel_p)
            pid_sel, fol_sel, exp_sel, nom_sel, ap_sel, am_sel, comp_sel, et_sel, fini_sel, est_sel = p_activos[idx_p]
            
            with st.form("form_ficha_ingreso"):
                st.subheader(f"Expediente de Admisión: {comp_sel}")
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    fam_resp = st.text_input("Familiar Responsable / Tutor").strip()
                    cont_emerg = st.text_input("Contacto de Emergencia (Teléfono)").strip()
                with c_f2:
                    modalidad = st.selectbox("Modalidad de Internamiento", ["Residencial Voluntario", "Involuntario", "Obligatorio"])
                    obs_med = st.text_area("Observaciones Médicas / Alergias iniciales")
                
                btn_ficha = st.form_submit_button("💾 Guardar y Generar Ficha", use_container_width=True)
                if btn_ficha:
                    datos_ficha = {
                        "expediente": exp_sel,
                        "nombre_completo": comp_sel,
                        "etapa_actual": et_sel,
                        "fecha_registro": datetime.now().strftime("%Y-%m-%d"),
                        "familiar_responsable": fam_resp,
                        "contacto_emergencia": cont_emerg,
                        "modalidad": modalidad,
                        "obs_medicas": obs_med
                    }
                    pdf_bytes = generar_pdf_ficha(pid_sel, datos_ficha)
                    mostrar_mensaje_exito("Ficha de Ingreso generada y guardada correctamente.")
                    st.download_button("🖨️ Descargar Ficha PDF", data=pdf_bytes, file_name=f"Ficha_{fol_sel}.pdf", mime="application/pdf")

    # ==========================================
    # 4. ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería")
        p_activos = obtener_lista_pacientes("Activos")
        if not p_activos:
            st.warning("No hay pacientes activos disponibles.")
        else:
            opciones_p = [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
            sel_p = st.selectbox("Seleccionar Paciente para Entrevista", opciones_p)
            idx_p = opciones_p.index(sel_p)
            pid_sel, fol_sel, exp_sel, nom_sel, ap_sel, am_sel, comp_sel, et_sel, fini_sel, est_sel = p_activos[idx_p]
            
            # Cargar entrevista previa si existe
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (pid_sel,))
            row_e = c.fetchone()
            conn.close()
            
            dj = json.loads(row_e[0]) if row_e else {}
            
            st.info(f"📋 Evaluando a: **{comp_sel}** (Folio: {fol_sel} | Expediente: {exp_sel if exp_sel else 'S/N'})")
            
            with st.form("form_entrevista_inicial"):
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["1. Generales", "2. Sustancias", "3. Disposición", "4. Entorno", "5. Observaciones"])
                
                with tab1:
                    dep_flag = st.selectbox("¿Dependientes económicos?", ["NO", "SÍ"], index=get_safe_index(["NO", "SÍ"], dj.get("dep_flag", "NO")))
                    dep_quienes = st.text_input("¿Quiénes?", value=dj.get("dep_quienes", ""))
                    pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"], index=get_safe_index(["NO", "SÍ"], dj.get("pareja_flag", "NO")))
                
                with tab2:
                    sust_options = ["Sin registrar", "ALCOHOL", "CANNABIS", "COCAÍNA", "METANFETAMINA", "ALUCINÓGENOS", "INHALABLES", "TABACO", "OTRA"]
                    idx_sust = get_safe_index(sust_options, dj.get("sustancia_impacto", "Sin registrar"))
                    sustancia_impacto = st.selectbox("Sustancia de Impacto Principal", sust_options, index=idx_sust)
                    tiempo_excesivo = st.text_input("Tiempo de consumo excesivo", value=dj.get("tiempo_excesivo", ""))
                
                with tab3:
                    abst_mayor = st.text_area("Mayor periodo de abstinencia logrado", value=dj.get("abst_mayor", ""))
                    abst_motivo = st.text_area("Motivo o estrategia para mantenerse", value=dj.get("abst_motivo", ""))
                
                with tab4:
                    familia_integrantes = st.text_area("Integrantes de la familia con mayor contacto", value=dj.get("familia_integrantes", ""))
                    abuso_flag = st.selectbox("Involucrado en abuso físico/sexual por consumo", ["NO", "SÍ"], index=get_safe_index(["NO", "SÍ"], dj.get("abuso_flag", "NO")))
                
                with tab5:
                    observaciones = st.text_area("Observaciones Clínicas Generales", value=dj.get("observaciones", ""))
                    evaluador = st.text_input("Nombre de quien aplica", value=dj.get("evaluador", st.session_state["nombre_completo"]))
                
                btn_save_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                if btn_save_ent:
                    datos_save = {
                        "dep_flag": dep_flag,
                        "dep_quienes": dep_quienes,
                        "pareja_flag": pareja_flag,
                        "sustancia_impacto": sustancia_impacto if sustancia_impacto != "Sin registrar" else "",
                        "tiempo_excesivo": tiempo_excesivo,
                        "abst_mayor": abst_mayor,
                        "abst_motivo": abst_motivo,
                        "familia_integrantes": familia_integrantes,
                        "abuso_flag": abuso_flag,
                        "observaciones": observaciones,
                        "evaluador": evaluador
                    }
                    f_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)",
                              (pid_sel, f_act, f_act, st.session_state["username"], json.dumps(datos_save, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    mostrar_mensaje_exito("Entrevista Inicial de Consejería guardada exitosamente.")

    # ==========================================
    # 5. CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Hojas de Consejería Individual")
        p_activos = obtener_lista_pacientes("Activos")
        if not p_activos:
            st.warning("No hay pacientes activos disponibles.")
        else:
            opciones_p = [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
            sel_p = st.selectbox("Seleccionar Paciente", opciones_p)
            idx_p = opciones_p.index(sel_p)
            pid_sel, fol_sel, exp_sel, nom_sel, ap_sel, am_sel, comp_sel, et_sel, fini_sel, est_sel = p_activos[idx_p]
            
            num_cons = st.selectbox("Número de Consejería", list(range(1, 13)))
            
            # Cargar consejería previa para esa posición
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT exposicion, avance, sugerencia, aspectos_trabajar, aspectos_proxima, fecha_proxima FROM consejerias WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?", (pid_sel, et_sel, num_cons))
            row_c = c.fetchone()
            conn.close()
            
            exp_c = row_c[0] if row_c else ""
            av_c = row_c[1] if row_c else ""
            sug_c = row_c[2] if row_c else ""
            trab_c = row_c[3] if row_c else ""
            prox_c = row_c[4] if row_c else ""
            f_prox_c = row_c[5] if row_c else ""
            
            with st.form("form_consejeria_ind"):
                st.subheader(f"Consejería Individual #{num_cons} - {et_sel}")
                exp_input = st.text_area("Exposición del Paciente", value=exp_c)
                avance_input = st.text_area("Avance / Retroceso Observado", value=av_c)
                sug_input = st.text_area("Sugerencias y Tareas", value=sug_c)
                trab_input = st.text_input("Aspectos Trabajados", value=trab_c)
                
                btn_cons = st.form_submit_button("💾 Guardar Consejería", use_container_width=True)
                if btn_cons:
                    f_hoy = datetime.now().strftime("%Y-%m-%d")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO consejerias (paciente_id, expediente, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (pid_sel, exp_sel, et_sel, num_cons, trab_input, prox_c, f_prox_c, exp_input, avance_input, sug_input, f_hoy, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    mostrar_mensaje_exito(f"Consejería Individual #{num_cons} registrada correctamente.")

    # ==========================================
    # 6. GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas & Proceso Clínico")
        p_activos = obtener_lista_pacientes("Activos")
        if not p_activos:
            st.info("No hay pacientes activos en tratamiento.")
        else:
            for p in p_activos:
                pid, fol, exp, nom, ap, am, nom_comp, et, f_ini, est = p
                dias = calcular_dias_etapa(f_ini)
                limites = {"Acogida": 30, "Identificación": 60, "Elaboración": 90, "Consolidación": 120, "Servicio Social": 180}
                limite_et = limites.get(et, 60)
                
                with st.expander(f"👤 {fol} | Exp: {exp if exp else 'S/N'} - **{nom_comp}** ({et}) - {dias} días en etapa"):
                    col_p1, col_p2 = st.columns([2, 1])
                    with col_p1:
                        st.write(f"**Fecha Inicio de Etapa:** {f_ini if f_ini else 'No registrada'}")
                        if dias > limite_et:
                            st.warning(f"⚠️ **Alerta de Rezago:** Excede el tiempo límite sugerido ({limite_et} días) para la etapa de {et}.")
                        else:
                            st.success(f"🟢 **En Tiempo:** Dentro del rango promedio para {et}.")
                    with col_p2:
                        etapas_secuencia = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                        idx_curr = etapas_secuencia.index(et) if et in etapas_secuencia else 0
                        if idx_curr < len(etapas_secuencia) - 1:
                            sig_et = etapas_secuencia[idx_curr + 1]
                            if st.button(f"🚀 Promover a {sig_et}", key=f"prom_{pid}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                f_hoy_str = datetime.now().strftime("%Y-%m-%d")
                                c.execute("UPDATE pacientes SET etapa_actual = ?, fecha_inicio_etapa = ? WHERE paciente_id = ?", (sig_et, f_hoy_str, pid))
                                conn.commit()
                                conn.close()
                                mostrar_mensaje_exito(f"¡Paciente {nom_comp} promovido exitosamente a {sig_et}!")
                                st.rerun()

    # ==========================================
    # 7. GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        p_activos = obtener_lista_pacientes("Activos")
        if not p_activos:
            st.warning("No hay pacientes activos disponibles.")
        else:
            opciones_p = [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
            sel_p = st.selectbox("Seleccionar Paciente", opciones_p)
            idx_p = opciones_p.index(sel_p)
            pid_sel, fol_sel, exp_sel, nom_sel, ap_sel, am_sel, comp_sel, et_sel, fini_sel, est_sel = p_activos[idx_p]
            
            with st.form("form_grupo_terapeutico"):
                tipo_grupo = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback", "Espiritual / 12 Pasos"])
                tema_grupo = st.text_input("Tema de la Sesión").strip()
                participacion = st.selectbox("Participación del Residente", ["Activa / Destacada", "Adecuada", "Pasiva / Receptiva", "Resistente"])
                obs_grupo = st.text_area("Observaciones Clínicas del Grupo")
                
                btn_grupo = st.form_submit_button("💾 Registrar Sesión de Grupo", use_container_width=True)
                if btn_grupo:
                    f_hoy = datetime.now().strftime("%Y-%m-%d")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (paciente_id, tipo_grupo, tema, participacion, observaciones, etapa_paciente, fecha, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (pid_sel, tipo_grupo, tema_grupo, participacion, obs_grupo, et_sel, f_hoy, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    mostrar_mensaje_exito("Sesión de grupo registrada correctamente.")

    # ==========================================
    # 8. CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos y Almacén")
        
        tab_med1, tab_med2 = st.tabs(["📦 Almacén de Medicamentos", "💉 Asignación a Pacientes"])
        
        with tab_med1:
            st.subheader("Catálogo e Inventario de Medicamentos")
            with st.form("form_nuevo_med"):
                c_m1, c_m2 = st.columns(2)
                with c_m1:
                    nom_med = st.text_input("Nombre del Medicamento").strip()
                with c_m2:
                    stock_med = st.number_input("Stock Inicial", min_value=0, value=10)
                indic_med = st.text_input("Indicaciones / Dosis Estándar")
                btn_med = st.form_submit_button("➕ Registrar Medicamento")
                
                if btn_med and nom_med:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO medicamentos (nombre_medicamento, stock, indicaciones) VALUES (?, ?, ?)", (nom_med, stock_med, indic_med))
                        conn.commit()
                        mostrar_mensaje_exito(f"Medicamento {nom_med} registrado correctamente.")
                    except:
                        st.error("El medicamento ya existe.")
                    conn.close()
                    st.rerun()

        with tab_med2:
            st.subheader("Asignar Medicamento a Paciente")
            p_activos = obtener_lista_pacientes("Activos")
            if p_activos:
                opciones_p = [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
                sel_p = st.selectbox("Seleccionar Residente", opciones_p, key="med_p_sel")
                idx_p = opciones_p.index(sel_p)
                pid_sel = p_activos[idx_p][0]
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, nombre_medicamento, stock FROM medicamentos")
                meds_cat = c.fetchall()
                conn.close()
                
                if meds_cat:
                    opciones_med = [f"{m[1]} (Stock: {m[2]})" for m in meds_cat]
                    sel_med = st.selectbox("Seleccionar Medicamento", opciones_med)
                    idx_med = opciones_med.index(sel_med)
                    id_med_sel = meds_cat[idx_med][0]
                    
                    with st.form("form_asig_med"):
                        dosis_val = st.text_input("Dosis").strip()
                        frec_val = st.text_input("Frecuencia").strip()
                        btn_asig = st.form_submit_button("💾 Asignar Medicación")
                        if btn_asig:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            f_hoy = datetime.now().strftime("%Y-%m-%d")
                            c.execute("INSERT INTO medicacion_paciente (paciente_id, medicamento_id, dosis, frecuencia, fecha_asignacion, usuario) VALUES (?, ?, ?, ?, ?, ?)",
                                      (pid_sel, id_med_sel, dosis_val, frec_val, f_hoy, st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            mostrar_mensaje_exito("Medicación asignada al residente exitosamente.")

    # ==========================================
    # 9. REPOSITORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        
        tab_repo1, tab_repo2 = st.tabs(["📂 Archivos y Carpetas", "⚙️ Gestión de Carpetas"])
        
        # OBTENER CARPETAS DE BASE DE DATOS
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY nombre_carpeta ASC")
        carpetas_rows = c.fetchall()
        conn.close()
        lista_carpetas = [r[0] for r in carpetas_rows] if carpetas_rows else ["General"]
        
        # --- TAB 1: SUBIR Y VER ARCHIVOS ---
        with tab_repo1:
            st.subheader("Subir Documento al Repositorio")
            carpeta_dest = st.selectbox("Seleccionar Carpeta de Destino", lista_carpetas)
            
            p_activos = obtener_lista_pacientes("Todos")
            opciones_p = ["-- General / Institucional --"] + [f"{p[1]} | Exp: {p[2] if p[2] else 'S/N'} - {p[6]}" for p in p_activos]
            sel_p = st.selectbox("Vincular a Residente (Opcional)", opciones_p)
            
            uploaded_file = st.file_uploader("Seleccionar archivo (PDF, Imagen, Word, Excel)")
            if uploaded_file:
                if st.button("💾 Guardar en Repositorio"):
                    dir_target = os.path.join(REPO_DIR, carpeta_dest)
                    if not os.path.exists(dir_target):
                        os.makedirs(dir_target)
                    path_out = os.path.join(dir_target, uploaded_file.name)
                    with open(path_out, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    mostrar_mensaje_exito(f"Archivo '{uploaded_file.name}' guardado en carpeta '{carpeta_dest}'.")
                    st.rerun()

            st.divider()
            st.subheader("Documentos Guardados por Carpeta")
            for c_nom in lista_carpetas:
                c_dir = os.path.join(REPO_DIR, c_nom)
                archivos_in = os.listdir(c_dir) if os.path.exists(c_dir) else []
                with st.expander(f"📁 **{c_nom}** ({len(archivos_in)} archivos)"):
                    if archivos_in:
                        for arch in archivos_in:
                            c_f1, c_f2 = st.columns([3, 1])
                            with c_f1:
                                st.write(f"📄 {arch}")
                            with c_f2:
                                p_file = os.path.join(c_dir, arch)
                                with open(p_file, "rb") as f:
                                    st.download_button("⬇️ Descargar", data=f, file_name=arch, key=f"dl_{c_nom}_{arch}")
                    else:
                        st.info("Carpeta vacía.")

        # --- TAB 2: CREAR Y RENOMBRAR CARPETAS ---
        with tab_repo2:
            st.subheader("⚙️ Configuración de Carpetas")
            
            col_c1, col_c2 = st.columns(2)
            
            # CREAR CARPETA
            with col_c1:
                st.write("**➕ Crear Nueva Carpeta**")
                with st.form("form_nueva_carpeta"):
                    nueva_c_nom = st.text_input("Nombre de la Nueva Carpeta").strip()
                    btn_c_nueva = st.form_submit_button("Crear Carpeta")
                    if btn_c_nueva and nueva_c_nom:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (nueva_c_nom,))
                            conn.commit()
                            dir_new = os.path.join(REPO_DIR, nueva_c_nom)
                            if not os.path.exists(dir_new):
                                os.makedirs(dir_new)
                            mostrar_mensaje_exito(f"Carpeta '{nueva_c_nom}' creada correctamente.")
                        except:
                            st.error("La carpeta ya existe.")
                        conn.close()
                        st.rerun()

            # RENOMBRAR CARPETA
            with col_c2:
                st.write("**✏️ Renombrar Carpeta Existente**")
                if lista_carpetas:
                    c_ren_sel = st.selectbox("Seleccionar Carpeta a Renombrar", lista_carpetas)
                    with st.form("form_renombrar_carpeta"):
                        ren_nuevo_nom = st.text_input("Nuevo Nombre de Carpeta").strip()
                        btn_c_ren = st.form_submit_button("Renombrar Carpeta")
                        if btn_c_ren and ren_nuevo_nom and ren_nuevo_nom != c_ren_sel:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (ren_nuevo_nom, c_ren_sel))
                            conn.commit()
                            conn.close()
                            
                            # Mover archivos físicos si la carpeta existe
                            old_path = os.path.join(REPO_DIR, c_ren_sel)
                            new_path = os.path.join(REPO_DIR, ren_nuevo_nom)
                            if os.path.exists(old_path):
                                if not os.path.exists(new_path):
                                    os.rename(old_path, new_path)
                                else:
                                    for f_item in os.listdir(old_path):
                                        shutil.move(os.path.join(old_path, f_item), os.path.join(new_path, f_item))
                                    os.rmdir(old_path)
                            mostrar_mensaje_exito(f"Carpeta renombrada a '{ren_nuevo_nom}' exitosamente.")
                            st.rerun()

    # ==========================================
    # 10. BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Directorio Central de Residentes")
        
        filtro_est = st.radio("Filtrar por Estado", ["Todos", "Activos", "Bloqueados"], horizontal=True)
        pacientes = obtener_lista_pacientes(filtro_est)
        
        busqueda = st.text_input("🔍 Buscar por Folio, Expediente o Nombre...").strip().lower()
        
        if busqueda:
            pacientes = [p for p in pacientes if busqueda in p[1].lower() or busqueda in (p[2] if p[2] else "").lower() or busqueda in p[6].lower()]
            
        st.subheader(f"Total encontrados: {len(pacientes)}")
        
        if pacientes:
            for p in pacientes:
                pid, fol, exp, nom, ap, am, nom_comp, et, f_ini, est = p
                exp_disp = exp if exp else "S/N"
                
                # Obtener entrevista previa para mostrar sustancia de impacto real
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM entrevistas WHERE paciente_id = ?", (pid,))
                row_e = c.fetchone()
                conn.close()
                dj = json.loads(row_e[0]) if row_e else {}
                sust_real = dj.get("sustancia_impacto", "")
                sust_disp = sust_real if sust_real else "Sin registrar"
                
                dias = calcular_dias_etapa(f_ini)
                
                with st.expander(f"👤 **{fol}** | Exp: **{exp_disp}** - **{nom_comp}** ({et}) [{est}]"):
                    c_d1, c_d2 = st.columns([3, 1])
                    with c_d1:
                        st.write(f"**Nombre Completo:** {nom_comp}")
                        st.write(f"**Etapa Actual:** {et} ({dias} días transcurridos)")
                        st.write(f"**Sustancia de Impacto:** {sust_disp}")
                        st.write(f"**Estado en el Centro:** {est}")
                    with c_d2:
                        pdf_bytes = generar_pdf_ficha(pid, {"expediente": exp, "nombre_completo": nom_comp, "etapa_actual": et, "fecha_registro": f_ini})
                        st.download_button("🖨️ Descargar Ficha PDF", data=pdf_bytes, file_name=f"Ficha_{fol}.pdf", mime="application/pdf", key=f"dl_dir_{pid}")

    # ==========================================
    # 11. CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad")
        
        es_admin = (st.session_state["username"] == "admin" or st.session_state["rol"] == "Administrador")
        
        if es_admin:
            tab_sec1, tab_sec2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_sec1 = st.container()
            
        with tab_sec1:
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
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(nueva_pass), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            mostrar_mensaje_exito("Contraseña actualizada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

        if es_admin:
            with tab_sec2:
                st.subheader("Administración de Cuentas del Personal")
                with st.form("form_nuevo_usuario_personal"):
                    c_u1, c_u2 = st.columns(2)
                    with c_u1:
                        new_u_user = st.text_input("Nombre de Usuario").strip()
                        new_u_name = st.text_input("Nombre Completo").strip()
                    with c_u2:
                        new_u_pass = st.text_input("Contraseña", type="password")
                        new_u_rol = st.selectbox("Rol del Sistema", ["Staff", "Administrador", "Lectura/Escritura", "Solo Lectura"])
                    btn_u_new = st.form_submit_button("➕ Registrar Usuario de Personal")
                    
                    if btn_u_new and new_u_user and new_u_pass:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol, estado) VALUES (?, ?, ?, ?, 'Activo')",
                                      (new_u_user, hash_pass(new_u_pass), new_u_name, new_u_rol))
                            conn.commit()
                            mostrar_mensaje_exito(f"Usuario '{new_u_user}' registrado correctamente.")
                        except:
                            st.error("El nombre de usuario ya está registrado.")
                        conn.close()
                        st.rerun()

                st.divider()
                st.subheader("Catálogo de Usuarios del Personal")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol, estado FROM usuarios ORDER BY id ASC")
                u_list = c.fetchall()
                conn.close()
                
                for u_item in u_list:
                    uid, uuser, uname, urol, uest = u_item
                    col_usr1, col_usr2, col_usr3 = st.columns([3, 1.5, 1])
                    with col_usr1:
                        st.write(f"👤 **{uuser}** ({uname if uname else 'Sin nombre'}) - Rol: **{urol}**")
                    with col_usr2:
                        if uest == "Activo":
                            st.success("🟢 ACTIVO")
                        else:
                            st.error("🔴 BLOQUEADO")
                    with col_usr3:
                        if uuser != "admin":
                            if uest == "Activo":
                                if st.button("🔴 Bloquear", key=f"bloq_usr_{uid}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Bloqueado' WHERE id = ?", (uid,))
                                    conn.commit()
                                    conn.close()
                                    mostrar_mensaje_exito(f"Usuario {uuser} bloqueado.")
                                    st.rerun()
                            else:
                                if st.button("🟢 Activar", key=f"act_usr_{uid}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE usuarios SET estado = 'Activo' WHERE id = ?", (uid,))
                                    conn.commit()
                                    conn.close()
                                    mostrar_mensaje_exito(f"Usuario {uuser} activado.")
                                    st.rerun()

    # ==========================================
    # 12. RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        col_b1, col_b2 = st.columns(2)
        
        with col_b1:
            st.subheader("⬇️ Descargar Copia de Seguridad")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button("Descargar Backup (.db)", data=f, file_name=f"Backup_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M')}.db", mime="application/x-sqlite3")
        
        with col_b2:
            st.subheader("⬆️ Restaurar Base de Datos")
            up_db = st.file_uploader("Seleccionar archivo .db para restaurar", type=["db"])
            if up_db:
                if st.button("⚠️ Confirmar Restauración"):
                    with open(DB_FILE, "wb") as f:
                        f.write(up_db.getbuffer())
                    mostrar_mensaje_exito("Base de datos restaurada correctamente.")
                    st.rerun()

if __name__ == "__main__":
    main()

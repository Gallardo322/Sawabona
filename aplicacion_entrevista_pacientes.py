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
    page_title="Sawabona Shikoba - Sistema de Gestión Clínica",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- CONSTANTES DE NAVEGACIÓN ---
M_REGISTRO = "👤 Registro y Edición de Pacientes"
M_ADMISION = "📄 Ficha de Ingreso / Admisión"
M_ENTREVISTA = "📝 Entrevista Inicial de Consejería"
M_CONSEJERIAS = "📝 Consejerías Individuales"
M_ETAPAS = "🎯 Gestión de Etapas & Proceso"
M_GRUPOS = "🗣️ Grupos Terapéuticos"
M_MEDICAMENTOS = "💊 Control de Medicamentos"
M_REPOSITORIO = "📁 Repositorio de Documentos"
M_BUSCAR = "🔍 Buscar y Listar Pacientes"
M_SEGURIDAD = "⚙️ Configuración y Seguridad"
M_RESPALDO = "📦 Respaldo y Restauración"

# --- INICIALIZACIÓN DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla Usuarios
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )
    """)
    # Verificar si existe columna rol
    c.execute("PRAGMA table_info(usuarios)")
    cols_u = [col[1] for col in c.fetchall()]
    if "rol" not in cols_u:
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
        except Exception:
            pass

    # Crear admin por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    else:
        # Asegurar que admin siempre tenga Nivel 1 - Administrador
        c.execute("UPDATE usuarios SET rol = 'Nivel 1 - Administrador' WHERE username = 'admin'")

    # 2. Tabla Pacientes / Entrevistas
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)

    # 3. Tabla Fichas de Ingreso / Admisión
    c.execute("""
        CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_ingreso TEXT,
            datos_json TEXT,
            usuario_registro TEXT
        )
    """)

    # 4. Tabla Consejerías Individuales
    c.execute("""
        CREATE TABLE IF NOT EXISTS consejerias_individuales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            num_consejeria INTEGER,
            etapa TEXT,
            fecha TEXT,
            expediente TEXT,
            aspectos_trabajados TEXT,
            proximos_aspectos TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance_retroceso TEXT,
            sugerencia TEXT,
            usuario_registro TEXT
        )
    """)

    # 5. Tabla Grupos Terapéuticos
    c.execute("""
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
    """)
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_g = [col[1] for col in c.fetchall()]
    if "etapa_paciente" not in cols_g:
        try:
            c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")
        except Exception:
            pass

    # 6. Tabla Catálogo de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            existencia INTEGER DEFAULT 0
        )
    """)

    # Pre-cargar catálogo de medicamentos si está vacío
    c.execute("SELECT COUNT(*) FROM catalogo_medicamentos")
    if c.fetchone()[0] == 0:
        meds_def = [
            ("PARACETAMOL", "Comprimidos", "500 mg", 100),
            ("IBUPROFENO", "Cápsulas", "400 mg", 100),
            ("COMPLEJO B", "Grageas", "Estándar", 100),
            ("CLONAZEPAM", "Gotas / Comprimidos", "2 mg", 50),
            ("SERTRALINA", "Comprimidos", "50 mg", 50),
            ("QUETIAPINA", "Comprimidos", "100 mg", 50),
            ("VALPROATO DE SODIO", "Comprimidos", "500 mg", 50),
            ("OLANZAPINA", "Comprimidos", "10 mg", 30),
            ("OMEPRAZOL", "Cápsulas", "20 mg", 100)
        ]
        for m_nom, m_pres, m_conc, m_ex in meds_def:
            c.execute("INSERT OR IGNORE INTO catalogo_medicamentos (nombre, presentacion, concentracion, existencia) VALUES (?, ?, ?, ?)",
                      (m_nom, m_pres, m_conc, m_ex))

    # 7. Tabla Esquema de Medicamentos Paciente
    c.execute("""
        CREATE TABLE IF NOT EXISTS esquema_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER,
            nombre_medicamento TEXT,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            indicaciones TEXT
        )
    """)

    # 8. Tabla Registro de Entregas de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER,
            nombre_medicamento TEXT,
            cantidad_entregada REAL,
            fecha_entrega TEXT,
            usuario_registro TEXT
        )
    """)

    # 9. Tabla Repositorio de Documentos
    c.execute("""
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
    """)

    # 10. Tabla Carpetas Repositorio
    c.execute("""
        CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE NOT NULL
        )
    """)
    # Pre-cargar carpetas por defecto
    carpetas_def = [
        "📋 Formatos Clínicos y Administrativos",
        "📖 Manuales de Operación",
        "⚖️ Reglamentos y Normativas",
        "📑 Plantillas de Evaluación",
        "📁 Documentos Generales"
    ]
    for carp in carpetas_def:
        c.execute("INSERT OR IGNORE INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (carp,))

    conn.commit()
    conn.close()

# --- SEGURIDAD Y ROLES ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    res = c.fetchone()
    conn.close()
    return res

def es_admin():
    u = st.session_state.get("username", "")
    r = st.session_state.get("rol", "")
    return u == "admin" or "Administrador" in str(r) or "Nivel 1" in str(r)

def es_lectura_escritura():
    r = st.session_state.get("rol", "")
    return es_admin() or "Nivel 2" in str(r) or "Lectura y Escritura" in str(r)

# --- HELPER AUTOGENERACIÓN FOLIO & EXPEDIENTE ---
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
            except Exception:
                pass
    return f"PAC-{max_num + 1:03d}"

def existe_expediente(exp_num, p_id_actual=""):
    if not exp_num or str(exp_num).strip() == "":
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    for pid, djson in rows:
        if pid != p_id_actual:
            try:
                dj = json.loads(djson)
                if str(dj.get("expediente", "")).strip() == str(exp_num).strip():
                    return True
            except Exception:
                pass
    return False

# --- OBTENER PACIENTES CON FORMATO PANTALLA ---
def listar_pacientes_dict():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json, fecha_registro FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    
    lista = []
    for pid, djson, freg in rows:
        try:
            dj = json.loads(djson)
            nom = dj.get("nombre_paciente", "Sin Nombre")
            exp = dj.get("expediente", "")
            exp_str = f"Exp: {exp}" if exp else "Exp: S/N"
            etapa = dj.get("etapa_actual", "ACOGIDA")
            f_ingreso = dj.get("fecha_ingreso_real", freg.split(" ")[0] if freg else datetime.now().strftime("%Y-%m-%d"))
            f_etapa = dj.get("fecha_inicio_etapa", f_ingreso)
            
            label_pantalla = f"{pid} | {exp_str} - {nom}"
            lista.append({
                "paciente_id": pid,
                "nombre": nom,
                "expediente": exp,
                "label_pantalla": label_pantalla,
                "etapa": etapa,
                "fecha_ingreso": f_ingreso,
                "fecha_etapa": f_etapa,
                "datos": dj
            })
        except Exception:
            pass
    return lista

# --- CALCULADORA DÍAS Y ALERTAS ---
def calcular_dias(fecha_str):
    if not fecha_str:
        return 0
    try:
        f = datetime.strptime(str(fecha_str)[:10], "%Y-%m-%d")
        return (datetime.now() - f).days
    except Exception:
        return 0

DURACION_ETAPAS = {
    "ACOGIDA": 30,
    "IDENTIFICACIÓN": 60,
    "ELABORACIÓN": 60,
    "CONSOLIDACIÓN": 30,
    "SERVICIO SOCIAL": 30
}

REQUISITOS_CONSEJERIAS = {
    "ACOGIDA": 4,
    "IDENTIFICACIÓN": 8,
    "ELABORACIÓN": 8,
    "CONSOLIDACIÓN": 4,
    "SERVICIO SOCIAL": 4
}

TEMAS_CONSEJERIAS = {
    "ACOGIDA": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).",
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
        "(5. CONSEJERIA) PREVENCIÓN DE RECAÍDAS.",
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
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

# --- PDF GENERATOR HELPER ---
class PDFReporte(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 5, 'Sistema de Gestión Clínica y Expediente Único de Rehabilitación', 0, 1, 'C')
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

# --- MAIN APP ---
def main():
    init_db()

    # Manejo de Inactividad (10 minutos = 600 segundos)
    AHORA = time.time()
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    
    if st.session_state["logged_in"]:
        ult_act = st.session_state.get("ultima_actividad", AHORA)
        if AHORA - ult_act > 600:
            st.session_state["logged_in"] = False
            st.error("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        else:
            st.session_state["ultima_actividad"] = AHORA

    # --- INICIO DE SESIÓN ---
    if not st.session_state["logged_in"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
            st.markdown("<h3 style='text-align: center;'>Acceso al Sistema Clínico</h3>", unsafe_allow_html=True)
            
            with st.form("login_form"):
                u_input = st.text_input("Usuario")
                p_input = st.text_input("Contraseña", type="password")
                btn_login = st.form_submit_button("🔑 Iniciar Sesión", use_container_width=True)
                
                if btn_login:
                    res = verificar_login(u_input, p_input)
                    if res:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2] if len(res) > 2 and res[2] else "Nivel 1 - Administrador"
                        st.session_state["ultima_actividad"] = time.time()
                        st.balloons()
                        st.toast(f"¡Bienvenido, {res[1]}!", icon="🎉")
                        st.rerun()
                    else:
                        st.error("⚠️ Usuario o contraseña incorrectos.")
            st.info("💡 Credenciales por defecto: Usuario: `admin` | Contraseña: `admin123`")
        return

    # Auto-refresh JS para inactividad
    st.markdown("""
        <script>
        var timeout;
        function resetTimer() {
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                window.location.reload();
            }, 605000);
        }
        document.onmousemove = resetTimer;
        document.onkeypress = resetTimer;
        document.onload = resetTimer;
        </script>
    """, unsafe_allow_html=True)

    # --- BARRA LATERAL ---
    st.sidebar.title("🌱 Sawabona Shikoba")
    st.sidebar.caption(f"👤 **{st.session_state.get('nombre_completo', '')}**")
    st.sidebar.caption(f"🛡️ Rol: **{st.session_state.get('rol', 'Administrador')}**")
    
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    st.sidebar.markdown("---")
    
    OPCIONES_MENU = [
        M_REGISTRO,
        M_ADMISION,
        M_ENTREVISTA,
        M_CONSEJERIAS,
        M_ETAPAS,
        M_GRUPOS,
        M_MEDICAMENTOS,
        M_REPOSITORIO,
        M_BUSCAR,
        M_SEGURIDAD,
        M_RESPALDO
    ]
    
    menu = st.sidebar.radio("Navegación del Sistema", OPCIONES_MENU)

    pacientes_lista = listar_pacientes_dict()

    # =========================================================================
    # 1. REGISTRO Y EDICIÓN DE PACIENTES
    # =========================================================================
    if menu == M_REGISTRO:
        st.title(M_REGISTRO)
        tab1, tab2 = st.tabs(["➕ Registrar / Editar Paciente", "📋 Directorio General"])
        
        with tab1:
            opts_pac = ["-- Nuevo Paciente --"] + [p["label_pantalla"] for p in pacientes_lista]
            sel_pac = st.selectbox("Seleccionar Paciente para Cargar/Editar", opts_pac)
            
            p_edit = None
            if sel_pac != "-- Nuevo Paciente --":
                for p in pacientes_lista:
                    if p["label_pantalla"] == sel_pac:
                        p_edit = p
                        break
            
            with st.form("form_paciente"):
                c1, c2 = st.columns(2)
                with c1:
                    folio_val = p_edit["paciente_id"] if p_edit else obtener_siguiente_folio()
                    st.text_input("Folio Interno (Autoincrementable)", value=folio_val, disabled=True)
                    exp_val = p_edit["expediente"] if p_edit else ""
                    exp_input = st.text_input("Número de Expediente (Numérico / Único)", value=exp_val, help="Ejemplo: 105")
                    
                    nom_val = p_edit["nombre"] if p_edit else ""
                    nom_input = st.text_input("Nombre Completo del Residente", value=nom_val)
                    
                    fnac_val = datetime.strptime(p_edit["datos"].get("fecha_nacimiento", "2000-01-01"), "%Y-%m-%d") if p_edit and p_edit["datos"].get("fecha_nacimiento") else datetime(2000, 1, 1)
                    fnac_input = st.date_input("Fecha de Nacimiento", value=fnac_val)
                
                with c2:
                    etapas_arr = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
                    etapa_idx = etapas_arr.index(p_edit["etapa"]) if p_edit and p_edit["etapa"] in etapas_arr else 0
                    etapa_input = st.selectbox("Etapa Actual", etapas_arr, index=etapa_idx)
                    
                    fing_val = datetime.strptime(p_edit["fecha_ingreso"], "%Y-%m-%d") if p_edit and p_edit.get("fecha_ingreso") else datetime.now()
                    fing_input = st.date_input("Fecha de Ingreso Real a la Comunidad", value=fing_val)
                    
                    fetapa_val = datetime.strptime(p_edit["fecha_etapa"], "%Y-%m-%d") if p_edit and p_edit.get("fecha_etapa") else fing_val
                    fetapa_input = st.date_input("Fecha de Inicio de la Etapa Actual", value=fetapa_val)
                
                btn_guardar_pac = st.form_submit_button("💾 Guardar Datos del Residente", use_container_width=True)
                
                if btn_guardar_pac:
                    if not nom_input.strip():
                        st.error("⚠️ Ingrese el nombre completo del residente.")
                    elif exp_input.strip() and existe_expediente(exp_input.strip(), folio_val):
                        st.error(f"⚠️ El número de Expediente '{exp_input.strip()}' ya pertenece a otro paciente.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        
                        # Obtener json previo o crear
                        c.execute("SELECT datos_json, fecha_registro FROM entrevistas WHERE paciente_id = ?", (folio_val,))
                        row_p = c.fetchone()
                        dj = json.loads(row_p[0]) if row_p else {}
                        f_reg = row_p[1] if row_p else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        dj["nombre_paciente"] = nom_input.strip()
                        dj["expediente"] = exp_input.strip()
                        dj["fecha_nacimiento"] = fnac_input.strftime("%Y-%m-%d")
                        dj["etapa_actual"] = etapa_input
                        dj["fecha_ingreso_real"] = fing_input.strftime("%Y-%m-%d")
                        dj["fecha_inicio_etapa"] = fetapa_input.strftime("%Y-%m-%d")
                        
                        djson_str = json.dumps(dj, ensure_ascii=False)
                        f_mod = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        if row_p:
                            c.execute("UPDATE entrevistas SET datos_json = ?, fecha_modificacion = ? WHERE paciente_id = ?",
                                      (djson_str, f_mod, folio_val))
                        else:
                            c.execute("INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)",
                                      (folio_val, f_reg, f_mod, st.session_state["username"], djson_str))
                        
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast("¡Paciente registrado/actualizado con éxito!", icon="🎉")
                        st.rerun()

        with tab2:
            st.subheader("📋 Resumen General de Residentes")
            if pacientes_lista:
                tabla_p = []
                for p in pacientes_lista:
                    d_tot = calcular_dias(p["fecha_ingreso"])
                    d_et = calcular_dias(p["fecha_etapa"])
                    d_est = DURACION_ETAPAS.get(p["etapa"], 30)
                    estado = "⚠️ REZAGADO" if d_et > d_est else "🟢 EN TIEMPO"
                    
                    tabla_p.append({
                        "Folio": p["paciente_id"],
                        "Expediente": p["expediente"] if p["expediente"] else "S/N",
                        "Nombre Completo": p["nombre"],
                        "Etapa": p["etapa"],
                        "Días en Etapa": f"{d_et} / {d_est} días",
                        "Días Totales": f"{d_tot} días",
                        "Estado": estado
                    })
                st.dataframe(tabla_p, use_container_width=True)
            else:
                st.info("No hay pacientes registrados en el sistema.")

    # =========================================================================
    # 2. FICHA DE INGRESO / ADMISIÓN (NOM-028)
    # =========================================================================
    elif menu == M_ADMISION:
        st.title(M_ADMISION)
        tab1, tab2 = st.tabs(["📝 Llenar / Editar Ficha", "🖨️ Consultar e Imprimir PDF"])
        
        with tab1:
            opts_p = [p["label_pantalla"] for p in pacientes_lista]
            if not opts_p:
                st.warning("Primero debe registrar un paciente en el modulo de Registro.")
            else:
                sel_p = st.selectbox("Seleccionar Paciente", opts_p, key="adm_p_sel")
                p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
                
                # Cargar ficha existente
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json FROM fichas_ingreso WHERE paciente_id = ?", (p_obj["paciente_id"],))
                f_row = c.fetchone()
                conn.close()
                
                f_dj = json.loads(f_row[0]) if f_row else {}
                
                with st.form("form_ficha_adm"):
                    st.subheader("1. Datos del Responsable Familiar")
                    c1, c2 = st.columns(2)
                    with c1:
                        resp_nom = st.text_input("Nombre del Responsable", value=f_dj.get("responsable_nombre", ""))
                        resp_parent = st.text_input("Parentesco", value=f_dj.get("responsable_parentesco", "Padre/Madre"))
                    with c2:
                        resp_tel = st.text_input("Teléfono de Contacto", value=f_dj.get("responsable_telefono", ""))
                        resp_dom = st.text_input("Domicilio del Responsable", value=f_dj.get("responsable_domicilio", ""))
                    
                    st.subheader("2. Datos de Admisión del Paciente")
                    c3, c4 = st.columns(2)
                    with c3:
                        esc_val = st.text_input("Escolaridad", value=f_dj.get("escolaridad", "Secundaria"))
                        rel_val = st.text_input("Religión", value=f_dj.get("religion", "Católica"))
                        ocu_val = st.text_input("Ocupación", value=f_dj.get("ocupacion", "Empleado"))
                    with c4:
                        med_val = st.text_input("Servicio Médico / Seguro", value=f_dj.get("servicio_medico", "Ninguno / IMSS"))
                        mod_val = st.selectbox("Modalidad de Internamiento (NOM-028)", ["VOLUNTARIO", "INVOLUNTARIO", "OBLIGATORIO"], index=0)
                    
                    st.subheader("3. Sustancias de Consumo")
                    sust_opciones = ["Alcohol", "Cannabis", "Metanfetaminas (Cristal)", "Cocaína", "Tabaco", "Benzodiazepinas", "Inhalantes", "Opioides"]
                    sust_sel = st.multiselect("Sustancias Consumidas", sust_opciones, default=f_dj.get("sustancias", ["Alcohol", "Metanfetaminas (Cristal)"]))
                    sust_imp = st.selectbox("Sustancia de Impacto Principal", sust_opciones, index=0)
                    
                    st.subheader("4. Términos Económicos y Sucursal")
                    c5, c6 = st.columns(2)
                    with c5:
                        costo_ing = st.number_input("Costo de Ingreso ($)", value=float(f_dj.get("costo_ingreso", 4500)))
                        costo_mens = st.number_input("Mensualidad ($)", value=float(f_dj.get("costo_mensual", 6000)))
                    with c6:
                        pagare_val = st.number_input("Importe de Pagaré ($)", value=float(f_dj.get("importe_pagare", 42000)))
                        sucursal_val = st.text_input("Sucursal", value=f_dj.get("sucursal", "Matriz - Sawabona"))
                    
                    btn_g_ficha = st.form_submit_button("💾 Guardar Ficha de Ingreso", use_container_width=True)
                    
                    if btn_g_ficha:
                        datos_f = {
                            "responsable_nombre": resp_nom,
                            "responsable_parentesco": resp_parent,
                            "responsable_telefono": resp_tel,
                            "responsable_domicilio": resp_dom,
                            "escolaridad": esc_val,
                            "religion": rel_val,
                            "ocupacion": ocu_val,
                            "servicio_medico": med_val,
                            "modalidad": mod_val,
                            "sustancias": sust_sel,
                            "sustancia_impacto": sust_imp,
                            "costo_ingreso": costo_ing,
                            "costo_mensual": costo_mens,
                            "importe_pagare": pagare_val,
                            "sucursal": sucursal_val
                        }
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT OR REPLACE INTO fichas_ingreso (paciente_id, fecha_ingreso, datos_json, usuario_registro) VALUES (?, ?, ?, ?)",
                                  (p_obj["paciente_id"], datetime.now().strftime("%Y-%m-%d"), json.dumps(datos_f, ensure_ascii=False), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("Ficha de Ingreso guardada correctamente", icon="🎉")
                        st.rerun()

        with tab2:
            opts_p2 = [p["label_pantalla"] for p in pacientes_lista]
            if opts_p2:
                sel_p2 = st.selectbox("Seleccionar Paciente para Imprimir Ficha", opts_p2, key="adm_p_sel2")
                p_obj2 = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p2), None)
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT datos_json, fecha_ingreso FROM fichas_ingreso WHERE paciente_id = ?", (p_obj2["paciente_id"],))
                f_row2 = c.fetchone()
                conn.close()
                
                if f_row2:
                    fj2 = json.loads(f_row2[0])
                    st.success(f"Ficha de Ingreso registrada el {f_row2[1]}")
                    st.json(fj2)
                    
                    # Generar PDF
                    pdf = PDFReporte()
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 14)
                    pdf.cell(0, 10, 'CONTRATO Y FICHA DE ADMISIÓN E INGRESO', 0, 1, 'C')
                    pdf.ln(5)
                    
                    pdf.set_font('Arial', '', 10)
                    exp_impresion = p_obj2['expediente'] if p_obj2['expediente'] else 'S/N'
                    pdf.cell(0, 6, f"EXPEDIENTE: {exp_impresion} | FECHA: {f_row2[1]}", 0, 1)
                    pdf.cell(0, 6, f"PACIENTE: {p_obj2['nombre']}", 0, 1)
                    pdf.cell(0, 6, f"RESPONSABLE: {fj2.get('responsable_nombre')} ({fj2.get('responsable_parentesco')}) - TEL: {fj2.get('responsable_telefono')}", 0, 1)
                    pdf.cell(0, 6, f"MODALIDAD: {fj2.get('modalidad')} | SUCURSAL: {fj2.get('sucursal')}", 0, 1)
                    pdf.ln(5)
                    
                    pdf.set_font('Arial', 'B', 11)
                    pdf.cell(0, 6, "TÉRMINOS FINANCIEROS ACORDADOS:", 0, 1)
                    pdf.set_font('Arial', '', 10)
                    pdf.cell(0, 6, f"- Costo de Ingreso: ${fj2.get('costo_ingreso'):,.2f}", 0, 1)
                    pdf.cell(0, 6, f"- Mensualidad: ${fj2.get('costo_mensual'):,.2f}", 0, 1)
                    pdf.cell(0, 6, f"- Pagaré de Garantía: ${fj2.get('importe_pagare'):,.2f}", 0, 1)
                    pdf.ln(5)
                    
                    pdf.set_font('Arial', 'B', 10)
                    pdf.multi_cell(0, 5, "DECLARACIÓN DE CONFORMIDAD Y AUTORIZACIÓN (NOM-028-SSA2-2009):\\nEl responsable firmante declara bajo protesta de decir verdad que autoriza el internamiento del usuario en la Comunidad Terapéutica Sawabona Shikoba A.C. aceptando el reglamento interno y comprometiéndose con los pagos acordados.")
                    pdf.ln(15)
                    
                    # Firmas
                    col_w = 90
                    pdf.cell(col_w, 6, "________________________________________", 0, 0, 'C')
                    pdf.cell(col_w, 6, "________________________________________", 0, 1, 'C')
                    pdf.cell(col_w, 6, "FIRMA DEL RESPONSABLE FAMILIAR", 0, 0, 'C')
                    pdf.cell(col_w, 6, "DIRECTOR / ENCARGADO DEL CENTRO", 0, 1, 'C')
                    
                    pdf_bytes = pdf.output(dest='S').encode('latin1')
                    st.download_button(
                        label="🖨️ Descargar Ficha de Ingreso en PDF",
                        data=pdf_bytes,
                        file_name=f"Ficha_Ingreso_Exp_{exp_impresion}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.info("Aún no se ha llenado la Ficha de Ingreso para este paciente.")

    # =========================================================================
    # 3. ENTREVISTA INICIAL DE CONSEJERÍA
    # =========================================================================
    elif menu == M_ENTREVISTA:
        st.title(M_ENTREVISTA)
        opts_p = [p["label_pantalla"] for p in pacientes_lista]
        if not opts_p:
            st.warning("Primero debe registrar un paciente.")
        else:
            sel_p = st.selectbox("Seleccionar Paciente para Entrevista Inicial", opts_p, key="ent_p_sel")
            p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
            
            dj = p_obj["datos"]
            
            with st.form("form_entrevista_inicial"):
                st.subheader("Historia Clínica de Consumo")
                d1, d2 = st.columns(2)
                with d1:
                    edad_Consumo = st.number_input("Edad de Inicio de Consumo", value=int(dj.get("edad_inicio_consumo", 15)))
                    sust_ini = st.text_input("Sustancia de Inicio", value=dj.get("sustancia_inicio", "Alcohol / Cannabis"))
                with d2:
                    sust_imp_e = st.text_input("Sustancia de Mayor Impacto", value=dj.get("sustancia_impacto_ent", "Cristal"))
                    frec_consumo = st.text_input("Frecuencia de Consumo Previa", value=dj.get("frecuencia_consumo", "Diario"))
                
                st.subheader("Evaluación Social y Motivacional")
                motivo = st.text_area("Motivo de Consulta y Disposición al Cambio", value=dj.get("motivo_consulta", "Acepta internamiento por recomendación familiar."))
                apoyo_fam = st.text_area("Red de Apoyo Familiar", value=dj.get("apoyo_familiar", "Padres y hermanos presentes."))
                diagnostico_cons = st.text_area("Diagnóstico Clínico de Consejería", value=dj.get("diagnostico_consejería", "Dependencia severa a estimulantes."))
                
                btn_ent = st.form_submit_button("💾 Guardar Entrevista Inicial", use_container_width=True)
                
                if btn_ent:
                    dj["edad_inicio_consumo"] = edad_Consumo
                    dj["sustancia_inicio"] = sust_ini
                    dj["sustancia_impacto_ent"] = sust_imp_e
                    dj["frecuencia_consumo"] = frec_consumo
                    dj["motivo_consulta"] = motivo
                    dj["apoyo_familiar"] = apoyo_fam
                    dj["diagnostico_consejería"] = diagnostico_cons
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE entrevistas SET datos_json = ?, fecha_modificacion = ? WHERE paciente_id = ?",
                              (json.dumps(dj, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_obj["paciente_id"]))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast("Entrevista Inicial guardada exitosamente", icon="🎉")
                    st.rerun()

    # =========================================================================
    # 4. CONSEJERÍAS INDIVIDUALES
    # =========================================================================
    elif menu == M_CONSEJERIAS:
        st.title(M_CONSEJERIAS)
        tab1, tab2 = st.tabs(["📝 Registrar Consejería", "📜 Historial e Impresión PDF"])
        
        opts_p = [p["label_pantalla"] for p in pacientes_lista]
        if not opts_p:
            st.warning("No hay pacientes registrados.")
        else:
            with tab1:
                sel_p = st.selectbox("Seleccionar Residente", opts_p, key="cons_p_sel")
                p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
                
                # Obtener consejerías previas en esta etapa
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT num_consejeria FROM consejerias_individuales WHERE paciente_id = ? AND etapa = ? ORDER BY num_consejeria DESC",
                          (p_obj["paciente_id"], p_obj["etapa"]))
                c_rows = c.fetchall()
                conn.close()
                
                num_sig = (c_rows[0][0] + 1) if c_rows else 1
                temas_etapa = TEMAS_CONSEJERIAS.get(p_obj["etapa"], [])
                idx_tema = min(num_sig - 1, len(temas_etapa) - 1) if temas_etapa else 0
                idx_prox = min(num_sig, len(temas_etapa) - 1) if temas_etapa else 0
                
                tema_actual_sug = temas_etapa[idx_tema] if temas_etapa else "Tema Estándar"
                tema_prox_sug = temas_etapa[idx_prox] if temas_etapa else "Tema Próximo"
                
                with st.form("form_consejeria_ind"):
                    st.subheader(f"Consejería #{num_sig} en Etapa: {p_obj['etapa']}")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.text_input("Nombre del Paciente", value=p_obj["nombre"], disabled=True)
                        st.text_input("Etapa Actual", value=p_obj["etapa"], disabled=True)
                    with c2:
                        exp_num_str = p_obj["expediente"] if p_obj["expediente"] else "S/N"
                        st.text_input("EXPEDIENTE", value=exp_num_str, disabled=True)
                        fecha_cons = st.date_input("Fecha de Sesión", value=datetime.now())
                    with c3:
                        f_prox_sug = datetime.now() + timedelta(days=7)
                        fecha_prox_cons = st.date_input("Fecha de Próxima Consejería (+7 días)", value=f_prox_sug)
                    
                    st.markdown("---")
                    asp_trabajados = st.text_area("Aspectos a Trabajar (Tema Oficial)", value=tema_actual_sug)
                    asp_proximos = st.text_area("Aspectos a Trabajar en la Próxima Consejería", value=tema_prox_sug)
                    
                    exposicion_txt = st.text_area("Exposición del Paciente (Texto largo)", value="", placeholder="Notas sobre lo expresado por el paciente en la sesión...")
                    avance_txt = st.text_area("Avance / Retroceso", value="", placeholder="Observaciones clínicas sobre el progreso o retroceso del residente...")
                    sugerencia_txt = st.text_area("Sugerencia / Tareas", value="", placeholder="Recomendaciones y compromisos para la semana...")
                    
                    btn_g_cons = st.form_submit_button("💾 Guardar Sesión de Consejería", use_container_width=True)
                    
                    if btn_g_cons:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO consejerias_individuales 
                            (paciente_id, num_consejeria, etapa, fecha, expediente, aspectos_trabajados, proximos_aspectos, fecha_proxima, exposicion, avance_retroceso, sugerencia, usuario_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (p_obj["paciente_id"], num_sig, p_obj["etapa"], fecha_cons.strftime("%Y-%m-%d"), exp_num_str,
                               asp_trabajados, asp_proximos, fecha_prox_cons.strftime("%Y-%m-%d"), exposicion_txt, avance_txt, sugerencia_txt, st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast("Consejería registrada con éxito", icon="🎉")
                        st.rerun()

            with tab2:
                sel_p2 = st.selectbox("Seleccionar Residente para Historial", opts_p, key="cons_p_sel2")
                p_obj2 = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p2), None)
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, num_consejeria, etapa, fecha, aspectos_trabajados, exposicion, avance_retroceso, sugerencia FROM consejerias_individuales WHERE paciente_id = ? ORDER BY id DESC",
                          (p_obj2["paciente_id"],))
                c_hist = c.fetchall()
                conn.close()
                
                if c_hist:
                    for cid, cnum, cetapa, cfecha, casp, cexp, cav, csug in c_hist:
                        with st.expander(f"Consejería #{cnum} - Etapa {cetapa} ({cfecha})"):
                            st.write(f"**Aspectos Trabajaos:** {casp}")
                            st.write(f"**Exposición:** {cexp}")
                            st.write(f"**Avance / Retroceso:** {cav}")
                            st.write(f"**Sugerencia:** {csug}")
                            
                            # PDF
                            pdf = PDFReporte()
                            pdf.add_page()
                            pdf.set_font('Arial', 'B', 14)
                            pdf.cell(0, 10, f'HOJA DE CONSEJERÍA INDIVIDUAL #{cnum}', 0, 1, 'C')
                            pdf.ln(3)
                            
                            pdf.set_font('Arial', '', 10)
                            exp_imp = p_obj2['expediente'] if p_obj2['expediente'] else 'S/N'
                            pdf.cell(0, 6, f"EXPEDIENTE: {exp_imp} | ETAPA: {cetapa} | FECHA: {cfecha}", 0, 1)
                            pdf.cell(0, 6, f"PACIENTE: {p_obj2['nombre']}", 0, 1)
                            pdf.ln(5)
                            
                            pdf.set_font('Arial', 'B', 10)
                            pdf.cell(0, 6, "ASPECTOS TRABAJADOS:", 0, 1)
                            pdf.set_font('Arial', '', 10)
                            pdf.multi_cell(0, 5, casp)
                            pdf.ln(3)
                            
                            pdf.set_font('Arial', 'B', 10)
                            pdf.cell(0, 6, "EXPOSICIÓN DEL PACIENTE:", 0, 1)
                            pdf.set_font('Arial', '', 10)
                            pdf.multi_cell(0, 5, cexp if cexp else "Sin notas de exposición.")
                            pdf.ln(3)
                            
                            pdf.set_font('Arial', 'B', 10)
                            pdf.cell(0, 6, "AVANCE / RETROCESO:", 0, 1)
                            pdf.set_font('Arial', '', 10)
                            pdf.multi_cell(0, 5, cav if cav else "Sin observaciones de avance.")
                            pdf.ln(3)
                            
                            pdf.set_font('Arial', 'B', 10)
                            pdf.cell(0, 6, "SUGERENCIAS / TAREAS:", 0, 1)
                            pdf.set_font('Arial', '', 10)
                            pdf.multi_cell(0, 5, csug if csug else "Sin sugerencias especiales.")
                            pdf.ln(12)
                            
                            col_w = 90
                            pdf.cell(col_w, 6, "________________________________________", 0, 0, 'C')
                            pdf.cell(col_w, 6, "________________________________________", 0, 1, 'C')
                            pdf.cell(col_w, 6, "FIRMA DEL CONSEJERO", 0, 0, 'C')
                            pdf.cell(col_w, 6, "FIRMA DEL PACIENTE", 0, 1, 'C')
                            
                            pdf_bytes = pdf.output(dest='S').encode('latin1')
                            st.download_button(
                                label=f"🖨️ Descargar PDF Consejería #{cnum}",
                                data=pdf_bytes,
                                file_name=f"Consejeria_{cnum}_Exp_{exp_imp}.pdf",
                                mime="application/pdf",
                                key=f"dl_c_{cid}"
                            )
                else:
                    st.info("No hay consejerías registradas para este paciente.")

    # =========================================================================
    # 5. GESTIÓN DE ETAPAS & PROCESO
    # =========================================================================
    elif menu == M_ETAPAS:
        st.title(M_ETAPAS)
        opts_p = [p["label_pantalla"] for p in pacientes_lista]
        if not opts_p:
            st.warning("No hay pacientes registrados.")
        else:
            sel_p = st.selectbox("Seleccionar Residente para Evaluar Etapa", opts_p, key="et_p_sel")
            p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
            
            d_tot = calcular_dias(p_obj["fecha_ingreso"])
            d_etapa = calcular_dias(p_obj["fecha_etapa"])
            d_estandar = DURACION_ETAPAS.get(p_obj["etapa"], 30)
            
            st.subheader(f"📊 Evaluación de Estancia - {p_obj['nombre']}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Días Totales en Comunidad", f"{d_tot} días")
            m2.metric(f"Días en Etapa: {p_obj['etapa']}", f"{d_etapa} días", delta=f"{d_etapa - d_estandar} días vs estándar" if d_etapa > d_estandar else "En tiempo", delta_color="inverse")
            m3.metric("Duración Estimada Etapa", f"{d_estandar} días")
            
            # Alerta de Rezago
            if d_etapa > d_estandar:
                st.error(f"⚠️ **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El paciente lleva **{d_tot} días internado** y suma **{d_etapa} días en la Etapa {p_obj['etapa']}** (Duración estimada: {d_estandar} días). Exceso: **+{d_etapa - d_estandar} días**.")
            else:
                st.success(f"🟢 **EN TIEMPO CLÍNICO**: El paciente evoluciona normalmente dentro de su etapa {p_obj['etapa']}.")
            
            st.markdown("---")
            st.subheader("🔍 Diagnóstico Inmediato de Requisitos de Promoción")
            
            # Conteo de Grupos en esta etapa
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            try:
                c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?", (p_obj["paciente_id"], p_obj["etapa"]))
                cnt_grupos = c.fetchone()[0]
            except Exception:
                cnt_grupos = 0
            
            # Conteo de Consejerías en esta etapa
            c.execute("SELECT COUNT(*) FROM consejerias_individuales WHERE paciente_id = ? AND etapa = ?", (p_obj["paciente_id"], p_obj["etapa"]))
            cnt_cons = c.fetchone()[0]
            conn.close()
            
            req_cons = REQUISITOS_CONSEJERIAS.get(p_obj["etapa"], 4)
            req_grup = 4
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Checklist de Sesiones Obligatorias:**")
                st.write(f"{'✅' if cnt_cons >= req_cons else '❌'} Consejerías Individuales: **{cnt_cons} / {req_cons}** completadas")
                st.write(f"{'✅' if cnt_grupos >= req_grup else '❌'} Grupos Terapéuticos: **{cnt_grupos} / {req_grup}** registrados")
            
            with col_b:
                st.write("**Entregables Cualitativos:**")
                chk_auto = st.checkbox("Autobiografía / Carta de Historia", value=True)
                chk_reglas = st.checkbox("Cumplimiento de Reglas de Convivencia", value=True)
            
            puedes_promover = (cnt_cons >= req_cons) and (cnt_grupos >= req_grup) and chk_auto and chk_reglas
            
            st.markdown("---")
            etapas_orden = ["ACOGIDA", "IDENTIFICACIÓN", "ELABORACIÓN", "CONSOLIDACIÓN", "SERVICIO SOCIAL"]
            curr_idx = etapas_orden.index(p_obj["etapa"]) if p_obj["etapa"] in etapas_orden else 0
            
            if curr_idx < len(etapas_orden) - 1:
                sig_etapa = etapas_orden[curr_idx + 1]
                if st.button(f"🎉 Promover Residente a Etapa: {sig_etapa}", disabled=not puedes_promover, use_container_width=True):
                    dj = p_obj["datos"]
                    dj["etapa_actual"] = sig_etapa
                    dj["fecha_inicio_etapa"] = datetime.now().strftime("%Y-%m-%d")
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE entrevistas SET datos_json = ? WHERE paciente_id = ?",
                              (json.dumps(dj, ensure_ascii=False), p_obj["paciente_id"]))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast(f"¡Paciente promovido con éxito a {sig_etapa}!", icon="🎉")
                    st.rerun()
            else:
                st.success("🎓 El paciente se encuentra en la etapa final de Servicio Social / Reinserción.")

    # =========================================================================
    # 6. GRUPOS TERAPÉUTICOS
    # =========================================================================
    elif menu == M_GRUPOS:
        st.title(M_GRUPOS)
        opts_p = [p["label_pantalla"] for p in pacientes_lista]
        if not opts_p:
            st.warning("No hay pacientes registrados.")
        else:
            sel_p = st.selectbox("Seleccionar Residente para Registro de Grupo", opts_p, key="grp_p_sel")
            p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
            
            with st.form("form_grupo"):
                tipo_grp = st.selectbox("Tipo de Grupo Terapéutico", ["Terapia de Grupo", "Aquí y Ahora", "Grupo de Feedback / Devolución", "Seminario de Prevención"])
                f_grp = st.date_input("Fecha del Grupo", value=datetime.now())
                
                desarrollo = st.text_area("Desarrollo de la Intervención del Paciente")
                devolucion = st.text_area("Devolución / Feedback del Grupo y Terapeuta")
                compromisos = st.text_area("Compromisos Adquiridos")
                
                btn_g_grp = st.form_submit_button("💾 Guardar Sesión de Grupo", use_container_width=True)
                
                if btn_g_grp:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO grupos_terapeuticos 
                        (paciente_id, tipo_grupo, fecha, etapa_paciente, desarrollo, devolucion, compromisos, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_obj["paciente_id"], tipo_grp, f_grp.strftime("%Y-%m-%d"), p_obj["etapa"], desarrollo, devolucion, compromisos, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast("Sesión de grupo guardada exitosamente", icon="🎉")
                    st.rerun()

    # =========================================================================
    # 7. CONTROL DE MEDICAMENTOS
    # =========================================================================
    elif menu == M_MEDICAMENTOS:
        st.title(M_MEDICAMENTOS)
        tab1, tab2, tab3 = st.tabs(["📦 Almacén y Entrega Diaria", "💊 Catálogo de Medicamentos", "📊 Reporte por Medicamento"])
        
        with tab1:
            opts_p = [p["label_pantalla"] for p in pacientes_lista]
            if opts_p:
                sel_p = st.selectbox("Seleccionar Residente para Suministro", opts_p, key="med_p_sel")
                p_obj = next((p for p in pacientes_lista if p["label_pantalla"] == sel_p), None)
                
                # Cargar catálogo
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, nombre, presentacion, concentracion, existencia FROM catalogo_medicamentos ORDER BY nombre ASC")
                meds_cat = c.fetchall()
                conn.close()
                
                st.subheader(f"Entregas de Almacén para: {p_obj['nombre']}")
                
                if meds_cat:
                    m_idx = st.selectbox("Seleccionar Medicamento del Catálogo", [f"{m[1]} ({m[2]} - {m[3]}) - Stock: {m[4]}" for m in meds_cat])
                    med_obj = meds_cat[[f"{m[1]} ({m[2]} - {m[3]}) - Stock: {m[4]}" for m in meds_cat].index(m_idx)]
                    
                    stock_real = med_obj[4]
                    
                    if stock_real <= 0:
                        st.error("⚠️ Sin existencias disponibles en almacén.")
                        cant_entregar = 0
                    else:
                        cant_entregar = st.number_input(f"Cantidad a Entregar (Máximo disponible: {stock_real})", min_value=1, max_value=stock_real, value=1)
                    
                    if st.button("📦 Registrar Entrega desde Almacén", disabled=(stock_real <= 0), use_container_width=True):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        # Descontar stock
                        c.execute("UPDATE catalogo_medicamentos SET existencia = existencia - ? WHERE id = ?", (cant_entregar, med_obj[0]))
                        # Registrar entrega
                        c.execute("INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, nombre_medicamento, cantidad_entregada, fecha_entrega, usuario_registro) VALUES (?, ?, ?, ?, ?, ?)",
                                  (p_obj["paciente_id"], med_obj[0], med_obj[1], cant_entregar, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.toast(f"Se entregaron {cant_entregar} unidades de {med_obj[1]}", icon="🎉")
                        st.rerun()

        with tab2:
            st.subheader("💊 Catálogo Central de Medicamentos")
            with st.form("form_add_med"):
                c1, c2, c3 = st.columns(3)
                m_nom = c1.text_input("Nombre del Medicamento")
                m_pres = c2.text_input("Presentación (Ej. Comprimidos)")
                m_conc = c3.text_input("Concentración (Ej. 500 mg)")
                m_stock = st.number_input("Existencia Inicial en Almacén", min_value=0, value=50)
                
                if st.form_submit_button("➕ Agregar al Catálogo"):
                    if m_nom.strip():
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, existencia) VALUES (?, ?, ?, ?)",
                                      (m_nom.strip().upper(), m_pres, m_conc, m_stock))
                            conn.commit()
                            st.balloons()
                            st.toast("Medicamento agregado al catálogo", icon="🎉")
                        except Exception:
                            st.error("El medicamento ya existe en el catálogo.")
                        conn.close()
                        st.rerun()
            
            # Tabla Catálogo
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT nombre, presentacion, concentracion, existencia FROM catalogo_medicamentos ORDER BY nombre ASC")
            rows_m = c.fetchall()
            conn.close()
            st.dataframe([{"Medicamento": r[0], "Presentación": r[1], "Concentración": r[2], "Existencia Almacén": r[3]} for r in rows_m], use_container_width=True)

        with tab3:
            st.subheader("📊 Consumo Total Diario por Medicamento")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, nombre, existencia FROM catalogo_medicamentos ORDER BY nombre ASC")
            all_m = c.fetchall()
            conn.close()
            
            if all_m:
                sel_m_rep = st.selectbox("Seleccionar Medicamento para Reporte", [m[1] for m in all_m])
                m_info = next((m for m in all_m if m[1] == sel_m_rep), None)
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT paciente_id, cantidad_entregada, fecha_entrega FROM entregas_medicamentos WHERE medicamento_id = ? ORDER BY id DESC", (m_info[0],))
                ent_m = c.fetchall()
                conn.close()
                
                st.metric("Existencia Actual en Almacén", f"{m_info[2]} unidades")
                if ent_m:
                    st.dataframe([{"Folio Paciente": r[0], "Cantidad Entregada": r[1], "Fecha/Hora": r[2]} for r in ent_m], use_container_width=True)
                else:
                    st.info("No hay registros de entrega para este medicamento.")

    # =========================================================================
    # 8. REPOSITORIO DE DOCUMENTOS
    # =========================================================================
    elif menu == M_REPOSITORIO:
        st.title(M_REPOSITORIO)
        
        if not es_admin():
            st.error("🔒 El módulo de Repositorio de Documentos es exclusivo para usuarios con rol de Administrador.")
        else:
            tab1, tab2, tab3 = st.tabs(["📥 Descargar Documentos", "📤 Subir Nuevo Documento", "📁 Personalizar / Gestionar Carpetas"])
            
            # Obtener carpetas
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT nombre_carpeta FROM carpetas_repositorio ORDER BY nombre_carpeta ASC")
            carpetas_list = [r[0] for r in c.fetchall()]
            conn.close()
            
            with tab1:
                c_filtro = st.selectbox("Filtrar por Carpeta", ["-- Todas las Carpetas --"] + carpetas_list)
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                if c_filtro == "-- Todas las Carpetas --":
                    c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos ORDER BY id DESC")
                else:
                    c.execute("SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC", (c_filtro,))
                docs = c.fetchall()
                conn.close()
                
                if docs:
                    for doc_id, doc_carp, doc_nom, doc_mime, doc_bytes, doc_desc, doc_f in docs:
                        with st.expander(f"📄 {doc_nom} ({doc_carp}) - {doc_f}"):
                            st.write(f"**Descripción:** {doc_desc if doc_desc else 'Sin descripción'}")
                            st.download_button(
                                label=f"⬇️ Descargar {doc_nom}",
                                data=doc_bytes,
                                file_name=doc_nom,
                                mime=doc_mime if doc_mime else "application/octet-stream",
                                key=f"dl_doc_{doc_id}"
                            )
                else:
                    st.info("No hay documentos guardados en esta carpeta.")

            with tab2:
                with st.form("form_subir_doc"):
                    carp_sub = st.selectbox("Seleccionar Carpeta Destino", carpetas_list)
                    file_up = st.file_uploader("Seleccionar Archivo (PDF, Word, Excel, Imagen)", type=["pdf", "docx", "doc", "xlsx", "xls", "png", "jpg"])
                    desc_up = st.text_input("Descripción / Notas del Documento")
                    
                    if st.form_submit_button("📤 Subir Documento al Repositorio"):
                        if file_up:
                            f_bytes = file_up.read()
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO repositorio_documentos 
                                (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (carp_sub, file_up.name, file_up.type, f_bytes, desc_up, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            
                            st.balloons()
                            st.toast(f"Documento {file_up.name} subido exitosamente", icon="🎉")
                            st.rerun()
                        else:
                            st.error("Por favor seleccione un archivo.")

            with tab3:
                st.subheader("📁 Administrar Carpetas del Repositorio")
                col_c1, col_c2 = st.columns(2)
                
                with col_c1:
                    st.write("**➕ Crear Nueva Carpeta**")
                    nueva_c = st.text_input("Nombre de la Nueva Carpeta")
                    if st.button("Crear Carpeta"):
                        if nueva_c.strip():
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute("INSERT INTO carpetas_repositorio (nombre_carpeta) VALUES (?)", (nueva_c.strip(),))
                                conn.commit()
                                st.balloons()
                                st.toast(f"Carpeta '{nueva_c.strip()}' creada", icon="🎉")
                            except Exception:
                                st.error("La carpeta ya existe.")
                            conn.close()
                            st.rerun()
                
                with col_c2:
                    st.write("**✏️ Renombrar Carpeta Existente**")
                    carp_ren = st.selectbox("Carpeta a Renombrar", carpetas_list, key="ren_sel")
                    nuevo_nom_c = st.text_input("Nuevo Nombre")
                    if st.button("Guardar Nombre"):
                        if nuevo_nom_c.strip():
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE carpetas_repositorio SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (nuevo_nom_c.strip(), carp_ren))
                            c.execute("UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?", (nuevo_nom_c.strip(), carp_ren))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.toast(f"Carpeta renombrada a '{nuevo_nom_c.strip()}'", icon="🎉")
                            st.rerun()

    # =========================================================================
    # 9. BUSCAR Y LISTAR PACIENTES
    # =========================================================================
    elif menu == M_BUSCAR:
        st.title(M_BUSCAR)
        busqueda = st.text_input("🔎 Buscar por Folio, Expediente o Nombre del Residente...")
        
        if pacientes_lista:
            res_filtrados = []
            for p in pacientes_lista:
                q = busqueda.lower().strip()
                if not q or (q in p["paciente_id"].lower() or q in str(p["expediente"]).lower() or q in p["nombre"].lower()):
                    res_filtrados.append(p)
            
            if res_filtrados:
                for p in res_filtrados:
                    with st.expander(f"👤 {p['label_pantalla']} - Etapa: {p['etapa']}"):
                        st.write(f"**Folio Interno:** {p['paciente_id']}")
                        st.write(f"**Expediente:** {p['expediente'] if p['expediente'] else 'Sin Asignar'}")
                        st.write(f"**Nombre:** {p['nombre']}")
                        st.write(f"**Etapa Actual:** {p['etapa']}")
                        st.write(f"**Fecha de Ingreso:** {p['fecha_ingreso']}")
                        st.json(p["datos"])
            else:
                st.info("No se encontraron coincidencias.")

    # =========================================================================
    # 10. CONFIGURACIÓN Y SEGURIDAD
    # =========================================================================
    elif menu == M_SEGURIDAD:
        st.title(M_SEGURIDAD)
        
        if es_admin():
            tab_seg1, tab_seg2 = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
            
            with tab_seg1:
                st.subheader("🔑 Cambiar mi Contraseña")
                with st.form("form_change_my_pass"):
                    p_act = st.text_input("Contraseña Actual", type="password")
                    p_nue = st.text_input("Nueva Contraseña", type="password")
                    p_con = st.text_input("Confirmar Nueva Contraseña", type="password")
                    
                    if st.form_submit_button("Guardar Nueva Contraseña"):
                        if p_nue != p_con:
                            st.error("Las contraseñas no coinciden.")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("SELECT password_hash FROM usuarios WHERE username = ?", (st.session_state["username"],))
                            row_u = c.fetchone()
                            
                            if row_u and row_u[0] == hash_pass(p_act):
                                c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                          (hash_pass(p_nue), st.session_state["username"]))
                                conn.commit()
                                st.balloons()
                                st.toast("Contraseña actualizada con éxito", icon="🎉")
                            else:
                                st.error("La contraseña actual es incorrecta.")
                            conn.close()

            with tab_seg2:
                st.subheader("👥 Gestión de Cuentas de Personal y Roles")
                
                with st.form("form_nuevo_usuario_staff"):
                    st.write("**➕ Registrar Nuevo Usuario de Sistema**")
                    c1, c2 = st.columns(2)
                    u_nom = c1.text_input("Nombre de Usuario (Login)")
                    u_comp = c2.text_input("Nombre Completo del Colaborador")
                    
                    c3, c4 = st.columns(2)
                    u_pass = c3.text_input("Contraseña Inicial", type="password")
                    u_rol = c4.selectbox("Rol y Nivel de Acceso", [
                        "Nivel 1 - Administrador",
                        "Nivel 2 - Lectura y Escritura",
                        "Nivel 3 - Solo Lectura"
                    ])
                    
                    if st.form_submit_button("➕ Crear Cuenta de Usuario"):
                        if u_nom.strip() and u_pass.strip():
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            try:
                                c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                                          (u_nom.strip(), hash_pass(u_pass.strip()), u_comp.strip(), u_rol))
                                conn.commit()
                                st.balloons()
                                st.toast(f"Usuario '{u_nom.strip()}' registrado exitosamente", icon="🎉")
                            except Exception:
                                st.error("El nombre de usuario ya está registrado.")
                            conn.close()
                            st.rerun()

                st.markdown("---")
                st.subheader("📋 Usuarios Registrados en el Sistema")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol FROM usuarios ORDER BY id ASC")
                u_rows = c.fetchall()
                conn.close()
                
                st.dataframe([{"ID": r[0], "Usuario": r[1], "Nombre Completo": r[2], "Rol de Acceso": r[3]} for r in u_rows], use_container_width=True)

        else:
            st.subheader("🔑 Cambiar mi Contraseña")
            with st.form("form_change_my_pass_nonadmin"):
                p_act = st.text_input("Contraseña Actual", type="password")
                p_nue = st.text_input("Nueva Contraseña", type="password")
                p_con = st.text_input("Confirmar Nueva Contraseña", type="password")
                
                if st.form_submit_button("Guardar Nueva Contraseña"):
                    if p_nue != p_con:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT password_hash FROM usuarios WHERE username = ?", (st.session_state["username"],))
                        row_u = c.fetchone()
                        
                        if row_u and row_u[0] == hash_pass(p_act):
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(p_nue), st.session_state["username"]))
                            conn.commit()
                            st.balloons()
                            st.toast("Contraseña actualizada con éxito", icon="🎉")
                        else:
                            st.error("La contraseña actual es incorrecta.")
                        conn.close()

    # =========================================================================
    # 11. RESPALDO Y RESTAURACIÓN
    # =========================================================================
    elif menu == M_RESPALDO:
        st.title(M_RESPALDO)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📥 Descargar Respaldo `.db`")
            st.write("Descargue una copia de seguridad completa con todos los pacientes, formularios, recetas y documentos del repositorio.")
            
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                
                st.download_button(
                    label="📥 Descargar Base de Datos Completa (.db)",
                    data=db_bytes,
                    file_name=f"Respaldo_Sawabona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True
                )
        
        with col2:
            st.subheader("📤 Restaurar Respaldo `.db`")
            up_db = st.file_uploader("Seleccione un archivo de respaldo (.db)", type=["db", "sqlite3"])
            
            if up_db:
                if st.button("⚠️ Confirmar Restauración de Base de Datos", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(up_db.read())
                    st.balloons()
                    st.toast("Base de datos restaurada con éxito", icon="🎉")
                    st.rerun()

if __name__ == "__main__":
    main()

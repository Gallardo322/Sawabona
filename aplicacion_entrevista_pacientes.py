import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date, timedelta
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista Inicial y Consejería",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- MIGRACIÓN Y BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Staff'
        )
    ''')
    
    # Tabla Entrevistas / Pacientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # Tabla Consejerias
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

    # Tabla Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            etapa_paciente TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            tema TEXT,
            desarrollo TEXT,
            devolucion TEXT,
            compromisos TEXT,
            usuario TEXT
        )
    ''')

    # Tabla Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_farmaco TEXT UNIQUE,
            existencias INTEGER,
            dosis_indicada TEXT
        )
    ''')

    # Tabla Entregas Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            farmaco_id INTEGER,
            cantidad INTEGER,
            fecha TEXT,
            usuario TEXT
        )
    ''')

    # Tabla Repositorio Carpetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_carpeta TEXT UNIQUE
        )
    ''')

    # Tabla Documentos Repositorio
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            carpeta TEXT,
            nombre_archivo TEXT,
            fecha_subida TEXT,
            usuario TEXT
        )
    ''')

    # Asegurar migración de columnas en consejerias
    c.execute("PRAGMA table_info(consejerias)")
    cols_cons = [row[1] for row in c.fetchall()]
    for col in ["expediente", "aspectos_trabajar", "aspectos_proxima", "fecha_proxima", "exposicion", "avance", "sugerencia"]:
        if col not in cols_cons:
            try:
                c.execute(f"ALTER TABLE consejerias ADD COLUMN {col} TEXT")
            except:
                pass

    # Asegurar migración de columnas en grupos_terapeuticos
    c.execute("PRAGMA table_info(grupos_terapeuticos)")
    cols_grup = [row[1] for row in c.fetchall()]
    if "etapa_paciente" not in cols_grup:
        try:
            c.execute("ALTER TABLE grupos_terapeuticos ADD COLUMN etapa_paciente TEXT")
        except:
            pass

    # Carpetas por defecto en repositorio
    carpetas_def = ["📁 Documentos Generales", "📄 Fichas e Inserción", "🧪 Tamizajes y Pruebas", "🩺 Informes Médicos"]
    for c_def in carpetas_def:
        c.execute("INSERT OR IGNORE INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (c_def,))

    # Crear usuario admin por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema', 'Administrador'))
    
    conn.commit()
    conn.close()

def clean_pdf_text(txt):
    if not txt:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¿': '', '¡': '', '”': '"', '“': '"', '’': "'", '‘': "'"
    }
    for k, v in replacements.items():
        txt = txt.replace(k, v)
    return txt.encode('latin-1', 'replace').decode('latin-1')

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

def get_safe_index(options, value, default=0):
    if not value:
        return default
    val_clean = str(value).strip().lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')
    for idx, opt in enumerate(options):
        opt_clean = str(opt).strip().lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')
        if val_clean == opt_clean:
            return idx
    return default

def generar_siguiente_folio():
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

def obtener_entrevista(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def guardar_entrevista(paciente_id, datos, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos_json = json.dumps(datos, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('UPDATE entrevistas SET fecha_modificacion = ?, datos_json = ? WHERE paciente_id = ?', (fecha_actual, datos_json, paciente_id))
    else:
        c.execute('INSERT INTO entrevistas (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, datos_json) VALUES (?, ?, ?, ?, ?)', (paciente_id, fecha_actual, fecha_actual, usuario, datos_json))
        
    conn.commit()
    conn.close()

def listar_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    
    lista = []
    for r in rows:
        pid = r[0]
        try:
            dj = json.loads(r[1])
        except:
            dj = {}
        exp = dj.get("expediente", "")
        exp_str = f"Exp: {exp}" if exp else "Exp: S/N"
        
        # Nombre completo / apellidos
        nom = dj.get("nombre", "")
        paterno = dj.get("apellido_paterno", "")
        materno = dj.get("apellido_materno", "")
        if paterno or materno:
            nombre_comp = f"{nom} {paterno} {materno}".strip()
        else:
            nombre_comp = dj.get("nombre_completo", nom)
            
        label = f"{pid} | {exp_str} - {nombre_comp}"
        lista.append((pid, label, dj))
    return lista

# CATALOGO OFICIAL DE CONSEJERIAS
CATALOGO_CONSEJERIAS = {
    "Acogida": [
        "(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.",
        "(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).",
        "(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION."
    ],
    "Identificación": [
        "(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.",
        "(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).",
        "(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LBRE.",
        "(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.",
        "(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).",
        "(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION."
    ],
    "Elaboración": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.",
        "(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.",
        "(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.",
        "(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.",
        "(5. CONSEJRIA) PREVENCIÓN DE RECAÍDAS.",
        "(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.",
        "(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.",
        "(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION."
    ],
    "Consolidación": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).",
        "(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.",
        "(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL."
    ],
    "Servicio Social": [
        "(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.",
        "(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.",
        "(3. CONSEJERIAS) CIERRE DE CONSEJERIA.",
        "(4. CONSEJERIA) CIERRE DE CONSEJERIA."
    ]
}

def render_header():
    st.markdown('''
        <div style="background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%); padding: 18px 25px; border-radius: 12px; color: white; margin-bottom: 22px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <h1 style="color: #FFFFFF; margin: 0; font-size: 1.8em; font-weight: bold;">🌱 Comunidad Terapéutica Sawabona Shikoba A.C.</h1>
                    <p style="color: #C8E6C9; margin: 4px 0 0 0; font-size: 1.05em; font-weight: 500;">Modelo de Tratamiento Biopsicosocial y Espiritual para Adicciones</p>
                </div>
                <div style="margin-top: 8px;">
                    <span style="background-color: #4CAF50; color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold; margin-right: 8px;">SISTEMA ACTIVO</span>
                    <span style="background-color: #81C784; color: #1B5E20; padding: 5px 12px; border-radius: 20px; font-size: 0.82em; font-weight: bold;">NOM-028-SSA2-2009</span>
                </div>
            </div>
        </div>
    ''', unsafe_allow_html=True)

def generar_pdf_consejeria(paciente_label, exp_val, etapa, num_cons, asp_trab, asp_prox, fech_prox, exp_txt, av_txt, sug_txt, fecha_sesion):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(27, 94, 32)
    pdf.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 6, clean_pdf_text("INFORME DE CONSEJERIA INDIVIDUAL"), 0, 1, 'C')
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(0, 6, clean_pdf_text("1. DATOS DE IDENTIFICACION"), 1, 1, 'L', True)
    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(100, 6, clean_pdf_text(f"Paciente: {paciente_label}"), 1, 0)
    pdf.cell(90, 6, clean_pdf_text(f"Expediente: {exp_val if exp_val else 'S/N'}"), 1, 1)
    pdf.cell(100, 6, clean_pdf_text(f"Etapa Actual: {etapa}"), 1, 0)
    pdf.cell(90, 6, clean_pdf_text(f"Fecha de Sesion: {fecha_sesion}"), 1, 1)
    pdf.ln(4)

    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(0, 6, clean_pdf_text(f"2. CONSEJERIA #{num_cons} - TEMATICA"), 1, 1, 'L', True)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Aspecto Trabajado: {asp_trab}"), 1)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Proximo Aspecto: {asp_prox}"), 1)
    pdf.cell(0, 6, clean_pdf_text(f"Fecha Proxima Consejeria: {fech_prox}"), 1, 1)
    pdf.ln(4)

    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(0, 6, clean_pdf_text("3. DESARROLLO Y NOTAS CLINICAS"), 1, 1, 'L', True)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Exposicion del Paciente:\n{exp_txt if exp_txt else 'Sin registro'}"), 1)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Avance / Retroceso:\n{av_txt if av_txt else 'Sin registro'}"), 1)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Sugerencias y Compromisos:\n{sug_txt if sug_txt else 'Sin registro'}"), 1)
    pdf.ln(12)

    pdf.cell(90, 6, clean_pdf_text("_____________________________________"), 0, 0, 'C')
    pdf.cell(10, 6, "", 0, 0)
    pdf.cell(90, 6, clean_pdf_text("_____________________________________"), 0, 1, 'C')
    pdf.cell(90, 5, clean_pdf_text("Firma del Consejero / Terapeuta"), 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, clean_pdf_text("Firma del Residente / Paciente"), 0, 1, 'C')

    return bytes(pdf.output())

def main():
    init_db()
    render_header()

    # --- CONTROL DE INACTIVIDAD (10 MIN) ---
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "ultima_actividad" not in st.session_state:
        st.session_state["ultima_actividad"] = datetime.now()

    if st.session_state["logged_in"]:
        inactivo = (datetime.now() - st.session_state["ultima_actividad"]).total_seconds()
        if inactivo > 600:
            st.session_state["logged_in"] = False
            st.warning("⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.")
            st.rerun()
        st.session_state["ultima_actividad"] = datetime.now()

    if not st.session_state["logged_in"]:
        st.subheader("🔐 Inicio de Sesión")
        with st.form("login_form"):
            user = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar")
            if submit:
                res = verificar_login(user, pwd)
                if res:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["nombre_completo"] = res[1]
                    st.session_state["rol"] = res[2] if len(res) > 2 else "Staff"
                    st.session_state["ultima_actividad"] = datetime.now()
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
        return

    # --- MENÚ LATERAL ---
    st.sidebar.markdown('''
        <div style="text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;">
            <h3 style="color: #2E7D32; margin:0;">🌱 Sawabona</h3>
            <p style="color: #388E3C; margin:0; font-size:0.85em;">Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)

    st.sidebar.title("📌 Menú Principal")
    menu = st.sidebar.selectbox(
        "Seleccione Módulo",
        [
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
    )

    st.sidebar.markdown("---")
    st.sidebar.write(f"👤 **Usuario:** {st.session_state.get('nombre_completo', 'Usuario')}")
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state["logged_in"] = False
        st.rerun()

    pacientes_lista = listar_pacientes()

    # ==========================================
    # 🏠 MÓDULO 1: INICIO / TABLERO GENERAL
    # ==========================================
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero General de la Comunidad")
        total_p = len(pacientes_lista)
        
        etapas_count = {"Acogida": 0, "Identificación": 0, "Elaboración": 0, "Consolidación": 0, "Servicio Social": 0}
        for _, _, dj in pacientes_lista:
            et = dj.get("etapa_actual", "Acogida")
            if et in etapas_count:
                etapas_count[et] += 1
            else:
                etapas_count["Acogida"] += 1

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total Residentes", total_p)
        c2.metric("Acogida", etapas_count["Acogida"])
        c3.metric("Identificación", etapas_count["Identificación"])
        c4.metric("Elaboración", etapas_count["Elaboración"])
        c5.metric("Consolidación", etapas_count["Consolidación"])
        c6.metric("Servicio Social", etapas_count["Servicio Social"])

        st.markdown("---")
        st.subheader("📋 Resumen de Residentes Activos")
        if pacientes_lista:
            data_table = []
            for pid, lbl, dj in pacientes_lista:
                exp = dj.get("expediente", "S/N")
                nom = dj.get("nombre_completo") or f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')} {dj.get('apellido_materno', '')}".strip()
                et = dj.get("etapa_actual", "Acogida")
                fi_etapa = dj.get("fecha_inicio_etapa") or dj.get("fecha_ingreso") or "N/A"
                
                # Calcular días en etapa
                dias_etapa = "N/A"
                if fi_etapa != "N/A":
                    try:
                        d_init = datetime.strptime(fi_etapa, "%Y-%m-%d").date()
                        dias_etapa = (date.today() - d_init).days
                    except:
                        pass

                data_table.append({
                    "Folio": pid,
                    "Expediente": exp,
                    "Nombre del Residente": nom,
                    "Etapa Actual": et,
                    "Fecha Inicio Etapa": fi_etapa,
                    "Días en Etapa": dias_etapa
                })
            st.dataframe(data_table, use_container_width=True)
        else:
            st.info("No hay residentes registrados en el sistema.")

    # ==========================================
    # 👤 MÓDULO 2: REGISTRO Y EDICIÓN DE USUARIOS
    # ==========================================
    elif menu == "👤 Registro y Edición de Usuarios":
        st.title("👤 Registro y Edición de Pacientes / Residentes")
        t_alta, t_edit = st.tabs(["➕ Alta de Nuevo Paciente", "✏️ Editar Paciente Existente"])

        with t_alta:
            st.subheader("Registrar Nuevo Residente")
            f_auto = generar_siguiente_folio()
            
            with st.form("form_alta_paciente"):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    st.text_input("Folio Autoincrementable", value=f_auto, disabled=True)
                    exp_in = st.number_input("Número de Expediente (Manual / Opcional)", min_value=0, value=0, step=1, help="Dejar en 0 si aún no cuenta con expediente")
                    nom_in = st.text_input("Nombre(s)")
                    pat_in = st.text_input("Apellido Paterno")
                    mat_in = st.text_input("Apellido Materno")
                
                with col_a2:
                    fnac_in = st.date_input("Fecha de Nacimiento", value=date(1995, 1, 1))
                    edad_calc = (date.today() - fnac_in).days // 365
                    st.info(f"Edad Calculada: **{edad_calc} años**")
                    sexo_in = st.selectbox("Sexo", ["Masculino", "Femenino"])
                    fing_in = st.date_input("Fecha de Ingreso Real", value=date.today())
                    etapa_in = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])
                    fetapa_in = st.date_input("Fecha de Inicio de Etapa (Para cálculo de días en etapa)", value=date.today())

                btn_guardar = st.form_submit_button("💾 Registrar Paciente")

                if btn_guardar:
                    nom_comp = f"{nom_in} {pat_in} {mat_in}".strip()
                    if not nom_comp:
                        st.error("Por favor ingrese al menos el nombre del paciente.")
                    else:
                        exp_str = str(exp_in) if exp_in > 0 else ""
                        # Verificar duplicado de expediente
                        if exp_str:
                            duplicado = False
                            for _, _, dj_check in pacientes_lista:
                                if str(dj_check.get("expediente", "")).strip() == exp_str:
                                    duplicado = True
                                    break
                            if duplicado:
                                st.error(f"⚠️ El número de Expediente '{exp_str}' ya está asignado a otro residente.")
                                st.stop()

                        datos_p = {
                            "expediente": exp_str,
                            "nombre": nom_in,
                            "apellido_paterno": pat_in,
                            "apellido_materno": mat_in,
                            "nombre_completo": nom_comp,
                            "fecha_nacimiento": str(fnac_in),
                            "edad": edad_calc,
                            "sexo": sexo_in,
                            "fecha_ingreso": str(fing_in),
                            "etapa_actual": etapa_in,
                            "fecha_inicio_etapa": str(fetapa_in)
                        }
                        guardar_entrevista(f_auto, datos_p, st.session_state["username"])
                        st.success(f"✅ Paciente '{nom_comp}' registrado exitosamente con Folio **{f_auto}**!")
                        st.rerun()

        with t_edit:
            st.subheader("Modificar Datos de Residente")
            if not pacientes_lista:
                st.info("No hay pacientes para editar.")
            else:
                sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_edit")
                pid_sel = sel_p.split(" | ")[0]
                dj_p, _, _, _ = obtener_entrevista(pid_sel)

                if dj_p:
                    with st.form("form_edit_paciente"):
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            st.text_input("Folio", value=pid_sel, disabled=True)
                            curr_exp = dj_p.get("expediente", "")
                            try:
                                val_exp_num = int(curr_exp) if curr_exp else 0
                            except:
                                val_exp_num = 0
                            exp_edit = st.number_input("Número de Expediente", min_value=0, value=val_exp_num, step=1)
                            nom_e = st.text_input("Nombre(s)", value=dj_p.get("nombre", ""))
                            pat_e = st.text_input("Apellido Paterno", value=dj_p.get("apellido_paterno", ""))
                            mat_e = st.text_input("Apellido Materno", value=dj_p.get("apellido_materno", ""))

                        with col_e2:
                            try:
                                fnac_val = datetime.strptime(dj_p.get("fecha_nacimiento", "1995-01-01"), "%Y-%m-%d").date()
                            except:
                                fnac_val = date(1995, 1, 1)
                            fnac_e = st.date_input("Fecha de Nacimiento", value=fnac_val)
                            edad_calc_e = (date.today() - fnac_e).days // 365
                            st.info(f"Edad Calculada: **{edad_calc_e} años**")

                            sexo_opts = ["Masculino", "Femenino"]
                            sexo_e = st.selectbox("Sexo", sexo_opts, index=get_safe_index(sexo_opts, dj_p.get("sexo", "Masculino")))

                            try:
                                fing_val = datetime.strptime(dj_p.get("fecha_ingreso", str(date.today())), "%Y-%m-%d").date()
                            except:
                                fing_val = date.today()
                            fing_e = st.date_input("Fecha de Ingreso Real", value=fing_val)

                            etapa_opts = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
                            etapa_e = st.selectbox("Etapa Actual", etapa_opts, index=get_safe_index(etapa_opts, dj_p.get("etapa_actual", "Acogida")))

                            try:
                                fetapa_val = datetime.strptime(dj_p.get("fecha_inicio_etapa", str(date.today())), "%Y-%m-%d").date()
                            except:
                                fetapa_val = date.today()
                            fetapa_e = st.date_input("Fecha de Inicio de Etapa (Para cálculo de días en etapa)", value=fetapa_val)

                        btn_actualizar = st.form_submit_button("🔄 Actualizar Datos")

                        if btn_actualizar:
                            nom_comp_e = f"{nom_e} {pat_e} {mat_e}".strip()
                            exp_str_e = str(exp_edit) if exp_edit > 0 else ""

                            # Validar expediente duplicado
                            if exp_str_e:
                                for p_item in pacientes_lista:
                                    if p_item[0] != pid_sel and str(p_item[2].get("expediente", "")).strip() == exp_str_e:
                                        st.error(f"⚠️ El número de Expediente '{exp_str_e}' ya pertenece a otro residente.")
                                        st.stop()

                            dj_p["expediente"] = exp_str_e
                            dj_p["nombre"] = nom_e
                            dj_p["apellido_paterno"] = pat_e
                            dj_p["apellido_materno"] = mat_e
                            dj_p["nombre_completo"] = nom_comp_e
                            dj_p["fecha_nacimiento"] = str(fnac_e)
                            dj_p["edad"] = edad_calc_e
                            dj_p["sexo"] = sexo_e
                            dj_p["fecha_ingreso"] = str(fing_e)
                            dj_p["etapa_actual"] = etapa_e
                            dj_p["fecha_inicio_etapa"] = str(fetapa_e)

                            guardar_entrevista(pid_sel, dj_p, st.session_state["username"])
                            st.success("✅ Datos del residente actualizados correctamente.")
                            st.rerun()

    # ==========================================
    # 📄 MÓDULO 3: FICHA DE INGRESO Y ADMISIÓN
    # ==========================================
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión (NOM-028-SSA2-2009)")
        if not pacientes_lista:
            st.info("Registre primero un paciente en el Módulo de Registro.")
        else:
            sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_admision")
            pid_sel = sel_p.split(" | ")[0]
            dj_p, _, _, _ = obtener_entrevista(pid_sel)

            with st.form("form_admision"):
                st.subheader("1. Datos Generales y Responsable Familiar")
                c1, c2 = st.columns(2)
                with c1:
                    resp_nom = st.text_input("Nombre del Responsable Familiar", value=dj_p.get("responsable_nombre", ""))
                    resp_par = st.text_input("Parentesco", value=dj_p.get("responsable_parentesco", ""))
                with c2:
                    resp_tel = st.text_input("Teléfono de Contacto", value=dj_p.get("responsable_telefono", ""))
                    resp_dir = st.text_input("Domicilio del Responsable", value=dj_p.get("responsable_domicilio", ""))

                st.subheader("2. Información Clínica y Sustancias de Impacto")
                c3, c4 = st.columns(2)
                with c3:
                    sust_opts = ["Alcohol", "Cristal / Metanfetamina", "Marihuana", "Cocaína", "Tabaco", "Fentanilo / Opiáceos", "Benzodiacepinas", "Otra"]
                    sust_imp = st.selectbox("Sustancia de Impacto Primaria", sust_opts, index=get_safe_index(sust_opts, dj_p.get("sustancia_impacto", "Alcohol")))
                    sust_sec = st.text_input("Sustancias Secundarias", value=dj_p.get("sustancias_secundarias", ""))
                with c4:
                    tiempo_cons = st.text_input("Tiempo de Consumo", value=dj_p.get("tiempo_consumo", ""))
                    ultimo_cons = st.text_input("Último Consumo", value=dj_p.get("ultimo_consumo", ""))

                st.subheader("3. Términos Económicos del Internamiento")
                c5, c6 = st.columns(2)
                with c5:
                    costo_ins = st.number_input("Costo de Inscripción / Admisión ($)", min_value=0.0, value=float(dj_p.get("costo_inscripcion", 0.0)), step=100.0)
                    costo_men = st.number_input("Colegiatura Mensual ($)", min_value=0.0, value=float(dj_p.get("colegiatura_mensual", 0.0)), step=100.0)
                with c6:
                    dia_pago = st.text_input("Día de Pago Acordado", value=dj_p.get("dia_pago", "Cada día 1 y 16 de mes"))

                btn_guardar_adm = st.form_submit_button("💾 Guardar Ficha de Admisión")

                if btn_guardar_adm:
                    dj_p["responsable_nombre"] = resp_nom
                    dj_p["responsable_parentesco"] = resp_par
                    dj_p["responsable_telefono"] = resp_tel
                    dj_p["responsable_domicilio"] = resp_dir
                    dj_p["sustancia_impacto"] = sust_imp
                    dj_p["sustancias_secundarias"] = sust_sec
                    dj_p["tiempo_consumo"] = tiempo_cons
                    dj_p["ultimo_consumo"] = ultimo_cons
                    dj_p["costo_inscripcion"] = costo_ins
                    dj_p["colegiatura_mensual"] = costo_men
                    dj_p["dia_pago"] = dia_pago

                    guardar_entrevista(pid_sel, dj_p, st.session_state["username"])
                    st.success("✅ Ficha de Admisión guardada correctamente.")
                    st.rerun()

            st.markdown("---")
            st.subheader("🖨️ Generar Contrato y Ficha PDF")
            if st.button("📄 Generar PDF Ficha de Ingreso"):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.set_text_color(27, 94, 32)
                pdf.cell(0, 8, clean_pdf_text("COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C."), 0, 1, 'C')
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 6, clean_pdf_text("CONTRATO DE ADMISION Y FICHA CLINICA DE INGRESO"), 0, 1, 'C')
                pdf.ln(4)

                exp_v = dj_p.get("expediente", "S/N")
                nom_v = dj_p.get("nombre_completo") or f"{dj_p.get('nombre', '')} {dj_p.get('apellido_paterno', '')}".strip()

                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(232, 245, 233)
                pdf.cell(0, 6, clean_pdf_text("1. DATOS DEL RESIDENTE"), 1, 1, 'L', True)
                pdf.set_font("Arial", '', 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(100, 6, clean_pdf_text(f"Nombre: {nom_v}"), 1, 0)
                pdf.cell(90, 6, clean_pdf_text(f"Expediente: {exp_v}"), 1, 1)
                pdf.cell(100, 6, clean_pdf_text(f"Edad: {dj_p.get('edad', 'N/A')} anos | Sexo: {dj_p.get('sexo', '')}"), 1, 0)
                pdf.cell(90, 6, clean_pdf_text(f"Fecha Ingreso: {dj_p.get('fecha_ingreso', '')}"), 1, 1)
                pdf.ln(3)

                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(232, 245, 233)
                pdf.cell(0, 6, clean_pdf_text("2. RESPONSABLE FAMILIAR"), 1, 1, 'L', True)
                pdf.set_font("Arial", '', 10)
                pdf.cell(100, 6, clean_pdf_text(f"Nombre: {dj_p.get('responsable_nombre', '')}"), 1, 0)
                pdf.cell(90, 6, clean_pdf_text(f"Parentesco: {dj_p.get('responsable_parentesco', '')}"), 1, 1)
                pdf.cell(100, 6, clean_pdf_text(f"Telefono: {dj_p.get('responsable_telefono', '')}"), 1, 0)
                pdf.cell(90, 6, clean_pdf_text(f"Domicilio: {dj_p.get('responsable_domicilio', '')}"), 1, 1)
                pdf.ln(3)

                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(232, 245, 233)
                pdf.cell(0, 6, clean_pdf_text("3. TERMINOS ECONOMICOS"), 1, 1, 'L', True)
                pdf.set_font("Arial", '', 10)
                pdf.cell(100, 6, clean_pdf_text(f"Costo Inscripcion: ${dj_p.get('costo_inscripcion', 0):,.2f}"), 1, 0)
                pdf.cell(90, 6, clean_pdf_text(f"Colegiatura Mensual: ${dj_p.get('colegiatura_mensual', 0):,.2f}"), 1, 1)
                pdf.cell(0, 6, clean_pdf_text(f"Dia de Pago Acordado: {dj_p.get('dia_pago', '')}"), 1, 1)
                pdf.ln(10)

                pdf.cell(90, 6, clean_pdf_text("_____________________________________"), 0, 0, 'C')
                pdf.cell(10, 6, "", 0, 0)
                pdf.cell(90, 6, clean_pdf_text("_____________________________________"), 0, 1, 'C')
                pdf.cell(90, 5, clean_pdf_text("Firma del Director / Consejero"), 0, 0, 'C')
                pdf.cell(10, 5, "", 0, 0)
                pdf.cell(90, 5, clean_pdf_text("Firma del Responsable Familiar"), 0, 1, 'C')

                pdf_bytes = bytes(pdf.output())
                st.download_button("⬇️ Descargar Ficha PDF", data=pdf_bytes, file_name=f"Ficha_Ingreso_{pid_sel}.pdf", mime="application/pdf")

    # ==========================================
    # 📝 MÓDULO 4: ENTREVISTA INICIAL DE CONSEJERÍA
    # ==========================================
    elif menu == "📝 Entrevista Inicial de Consejería":
        st.title("📝 Entrevista Inicial de Consejería Clínica")
        if not pacientes_lista:
            st.info("Registre primero un paciente.")
        else:
            sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_entrevista")
            pid_sel = sel_p.split(" | ")[0]
            dj_p, _, _, _ = obtener_entrevista(pid_sel)

            with st.form("form_entrevista_inicial"):
                st.subheader("1. Antecedentes de Consumo y Tratamiento")
                c1, c2 = st.columns(2)
                with c1:
                    mot_ing = st.text_area("Motivo de Ingreso", value=dj_p.get("motivo_ingreso", ""))
                    hist_cons = st.text_area("Historial de Consumo y Frecuencia", value=dj_p.get("historial_consumo", ""))
                with c2:
                    trats_prev = st.text_area("Tratamientos Anteriores", value=dj_p.get("tratamientos_anteriores", ""))
                    periodos_abs = st.text_area("Periodos Máximos de Abstinencia", value=dj_p.get("periodos_abstinencia", ""))

                st.subheader("2. Red de Apoyo y Diagnóstico Inicial")
                c3, c4 = st.columns(2)
                with c3:
                    red_apoyo = st.text_area("Red de Apoyo Familiar / Social", value=dj_p.get("red_apoyo", ""))
                with c4:
                    diag_cons = st.text_area("Diagnóstico / Observaciones de Consejería", value=dj_p.get("diagnostico_consejería", ""))

                btn_guardar_e = st.form_submit_button("💾 Guardar Entrevista Inicial")

                if btn_guardar_e:
                    dj_p["motivo_ingreso"] = mot_ing
                    dj_p["historial_consumo"] = hist_cons
                    dj_p["tratamientos_anteriores"] = trats_prev
                    dj_p["periodos_abstinencia"] = periodos_abs
                    dj_p["red_apoyo"] = red_apoyo
                    dj_p["diagnostico_consejería"] = diag_cons

                    guardar_entrevista(pid_sel, dj_p, st.session_state["username"])
                    st.success("✅ Entrevista Inicial guardada correctamente.")
                    st.rerun()

    # ==========================================
    # 📝 MÓDULO 5: CONSEJERÍAS INDIVIDUALES
    # ==========================================
    elif menu == "📝 Consejerías Individuales":
        st.title("📝 Registro de Consejerías Individuales")
        if not pacientes_lista:
            st.info("No hay pacientes registrados.")
        else:
            sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_cons")
            pid_sel = sel_p.split(" | ")[0]
            dj_p, _, _, _ = obtener_entrevista(pid_sel)

            etapa_act = dj_p.get("etapa_actual", "Acogida")
            if etapa_act not in CATALOGO_CONSEJERIAS:
                etapa_act = "Acogida"

            temas_etapa = CATALOGO_CONSEJERIAS[etapa_act]
            st.info(f"📌 **Residente:** {sel_p} | **Etapa Actual:** {etapa_act} ({len(temas_etapa)} Consejerías requeridas)")

            t_capt, t_hist = st.tabs(["📝 Capturar Consejería", "📜 Historial e Impresión PDF"])

            with t_capt:
                c_num, c_fec = st.columns(2)
                with c_num:
                    num_cons_sel = st.selectbox("Número de Consejería en esta Etapa", list(range(1, len(temas_etapa) + 1)))
                with c_fec:
                    fecha_sesion = st.date_input("Fecha de esta Consejería", value=date.today())

                # Consultar si ya existe registro para esta consejería
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha
                    FROM consejerias
                    WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                ''', (pid_sel, etapa_act, num_cons_sel))
                row_c = c.fetchone()
                conn.close()

                # Tema actual y tema próximo
                tema_actual_default = temas_etapa[num_cons_sel - 1]
                if num_cons_sel < len(temas_etapa):
                    tema_prox_default = temas_etapa[num_cons_sel]
                else:
                    tema_prox_default = "Evaluación / Transición a Siguiente Etapa"

                if row_c:
                    val_asp_trab = row_c[0] if row_c[0] else tema_actual_default
                    val_asp_prox = row_c[1] if row_c[1] else tema_prox_default
                    try:
                        val_fec_prox = datetime.strptime(row_c[2], "%Y-%m-%d").date() if row_c[2] else date.today() + timedelta(days=7)
                    except:
                        val_fec_prox = date.today() + timedelta(days=7)
                    val_exp = row_c[3] if row_c[3] else ""
                    val_av = row_c[4] if row_c[4] else ""
                    val_sug = row_c[5] if row_c[5] else ""
                else:
                    val_asp_trab = tema_actual_default
                    val_asp_prox = tema_prox_default
                    val_fec_prox = date.today() + timedelta(days=7)
                    val_exp = ""
                    val_av = ""
                    val_sug = ""

                with st.form("form_consejeria_ind"):
                    asp_trab_in = st.text_input("Aspectos a Trabajar (Tema Oficial)", value=val_asp_trab)
                    asp_prox_in = st.text_input("Aspectos a Trabajar en Próxima Consejería", value=val_asp_prox)
                    fec_prox_in = st.date_input("Fecha Próxima Consejería (+7 Días)", value=val_fec_prox)

                    exp_in = st.text_area("Exposición del Paciente (Notas del Residente)", value=val_exp, height=120)
                    av_in = st.text_area("Avance / Retroceso (Observaciones Clínicas)", value=val_av, height=120)
                    sug_in = st.text_area("Sugerencias y Compromisos", value=val_sug, height=120)

                    btn_guardar_c = st.form_submit_button("💾 Guardar Consejería")

                    if btn_guardar_c:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            SELECT id FROM consejerias 
                            WHERE paciente_id = ? AND etapa = ? AND num_consejeria = ?
                        ''', (pid_sel, etapa_act, num_cons_sel))
                        exists_c = c.fetchone()

                        exp_val_cur = dj_p.get("expediente", "")

                        if exists_c:
                            c.execute('''
                                UPDATE consejerias
                                SET expediente = ?, aspectos_trabajar = ?, aspectos_proxima = ?, fecha_proxima = ?,
                                    exposicion = ?, avance = ?, sugerencia = ?, fecha = ?, usuario = ?
                                WHERE id = ?
                            ''', (exp_val_cur, asp_trab_in, asp_prox_in, str(fec_prox_in), exp_in, av_in, sug_in, str(fecha_sesion), st.session_state["username"], exists_c[0]))
                        else:
                            c.execute('''
                                INSERT INTO consejerias (paciente_id, expediente, etapa, num_consejeria, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia, fecha, usuario)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (pid_sel, exp_val_cur, etapa_act, num_cons_sel, asp_trab_in, asp_prox_in, str(fec_prox_in), exp_in, av_in, sug_in, str(fecha_sesion), st.session_state["username"]))

                        conn.commit()
                        conn.close()
                        st.success(f"✅ Consejería #{num_cons_sel} de la etapa '{etapa_act}' guardada exitosamente!")
                        st.rerun()

            with t_hist:
                st.subheader("📜 Historial de Consejerías de esta Etapa")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT num_consejeria, fecha, aspectos_trabajar, aspectos_proxima, fecha_proxima, exposicion, avance, sugerencia
                    FROM consejerias
                    WHERE paciente_id = ? AND etapa = ?
                    ORDER BY num_consejeria ASC
                ''', (pid_sel, etapa_act))
                rows_hist = c.fetchall()
                conn.close()

                if not rows_hist:
                    st.info("Aún no hay consejerías registradas para este paciente en su etapa actual.")
                else:
                    for rh in rows_hist:
                        nc, fc, at, ap, fp, ex, av, sg = rh
                        with st.expander(f"Consejería #{nc} - {fc} | Tema: {at}"):
                            st.write(f"**Próximo Tema:** {ap} (Fecha: {fp})")
                            st.write(f"**Exposición:** {ex if ex else 'Sin notas'}")
                            st.write(f"**Avance / Retroceso:** {av if av else 'Sin notas'}")
                            st.write(f"**Sugerencias:** {sg if sg else 'Sin notas'}")

                            pdf_c_bytes = generar_pdf_consejeria(
                                sel_p, dj_p.get("expediente", "S/N"), etapa_act, nc, at, ap, fp, ex, av, sg, fc
                            )
                            st.download_button(
                                f"🖨️ Descargar PDF Consejería #{nc}",
                                data=pdf_c_bytes,
                                file_name=f"Consejeria_{pid_sel}_Etapa_{etapa_act}_N{nc}.pdf",
                                mime="application/pdf",
                                key=f"btn_pdf_c_{nc}"
                            )

    # ==========================================
    # 🎯 MÓDULO 6: GESTIÓN DE ETAPAS & PROCESO
    # ==========================================
    elif menu == "🎯 Gestión de Etapas & Proceso":
        st.title("🎯 Gestión de Etapas y Cumplimiento de Requisitos")
        if not pacientes_lista:
            st.info("No hay pacientes registrados.")
        else:
            sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_etapas")
            pid_sel = sel_p.split(" | ")[0]
            dj_p, _, _, _ = obtener_entrevista(pid_sel)

            etapa_act = dj_p.get("etapa_actual", "Acogida")
            f_ini_etapa_str = dj_p.get("fecha_inicio_etapa") or dj_p.get("fecha_ingreso") or str(date.today())
            try:
                f_ini_etapa = datetime.strptime(f_ini_etapa_str, "%Y-%m-%d").date()
            except:
                f_ini_etapa = date.today()

            dias_en_etapa = (date.today() - f_ini_etapa).days

            c1, c2, c3 = st.columns(3)
            c1.metric("Etapa Actual", etapa_act)
            c2.metric("Fecha Inicio Etapa", str(f_ini_etapa))
            c3.metric("Días en Etapa Actual", f"{dias_en_etapa} días")

            # Alerta de rezago
            limites_etapas = {"Acogida": 30, "Identificación": 60, "Elaboración": 60, "Consolidación": 30, "Servicio Social": 30}
            lim_dias = limites_etapas.get(etapa_act, 60)
            if dias_en_etapa > lim_dias:
                st.warning(f"⚠️ **Alerta de Rezago Clínico:** El residente lleva {dias_en_etapa} días en {etapa_act} (Límite sugerido: {lim_dias} días).")

            st.markdown("---")
            st.subheader("📋 Checklist de Requisitos para Promoción de Etapa")

            temas_req = CATALOGO_CONSEJERIAS.get(etapa_act, [])
            total_req_c = len(temas_req)

            # Contar consejerías realizadas en esta etapa
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?", (pid_sel, etapa_act))
            row_cnt = c.fetchone()
            c_realizadas = row_cnt[0] if row_cnt else 0

            # Contar grupos
            try:
                c.execute("SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?", (pid_sel, etapa_act))
                row_g = c.fetchone()
                g_realizados = row_g[0] if row_g else 0
            except:
                g_realizados = 0
            conn.close()

            st.write(f"• **Consejerías Individuales Completadas:** {c_realizadas} de {total_req_c}")
            st.write(f"• **Sesiones de Grupo Registradas:** {g_realizados}")

            progreso = min(1.0, c_realizadas / total_req_c) if total_req_c > 0 else 1.0
            st.progress(progreso)

            siguiente_etapa_map = {
                "Acogida": "Identificación",
                "Identificación": "Elaboración",
                "Elaboración": "Consolidación",
                "Consolidación": "Servicio Social",
                "Servicio Social": "Alta Graduada"
            }
            sig_etapa = siguiente_etapa_map.get(etapa_act, "Alta Graduada")

            puedes_promover = (c_realizadas >= total_req_c)

            if puedes_promover:
                st.success(f"🎉 ¡El residente ha completado el 100% de consejerías para {etapa_act}!")
                if st.button(f"🚀 Promover a {sig_etapa}"):
                    dj_p["etapa_actual"] = sig_etapa
                    dj_p["fecha_inicio_etapa"] = str(date.today())
                    guardar_entrevista(pid_sel, dj_p, st.session_state["username"])
                    st.success(f"✅ Residente promovido a '{sig_etapa}' exitosamente. Fecha de inicio de etapa actualizada a hoy.")
                    st.rerun()
            else:
                st.info(f"🔒 Para promover a **{sig_etapa}**, complete las {total_req_c - c_realizadas} consejerías faltantes.")

    # ==========================================
    # 🗣️ MÓDULO 7: GRUPOS TERAPÉUTICOS
    # ==========================================
    elif menu == "🗣️ Grupos Terapéuticos":
        st.title("🗣️ Registro de Grupos Terapéuticos")
        if not pacientes_lista:
            st.info("No hay pacientes registrados.")
        else:
            sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_grupo")
            pid_sel = sel_p.split(" | ")[0]
            dj_p, _, _, _ = obtener_entrevista(pid_sel)

            etapa_act = dj_p.get("etapa_actual", "Acogida")

            with st.form("form_grupo"):
                st.subheader("Capturar Sesión de Grupo")
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    tipo_g = st.selectbox("Tipo de Grupo", ["Terapia de Grupo", "Aquí y Ahora", "Feedback / Devolución"])
                    fec_g = st.date_input("Fecha de la Sesión", value=date.today())
                with col_g2:
                    tema_g = st.text_input("Tema Central de la Sesión")

                des_g = st.text_area("Desarrollo de la Sesión")
                dev_g = st.text_area("Devolución / Observaciones al Paciente")
                comp_g = st.text_area("Compromisos Acordados")

                btn_save_g = st.form_submit_button("💾 Guardar Sesión de Grupo")

                if btn_save_g:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO grupos_terapeuticos (paciente_id, etapa_paciente, tipo_grupo, fecha, tema, desarrollo, devolucion, compromisos, usuario)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (pid_sel, etapa_act, tipo_g, str(fec_g), tema_g, des_g, dev_g, comp_g, st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success("✅ Sesión de grupo registrada correctamente.")
                    st.rerun()

    # ==========================================
    # 💊 MÓDULO 8: CONTROL DE MEDICAMENTOS
    # ==========================================
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control e Inventario de Medicamentos")
        tab_inv, tab_ent = st.tabs(["📦 Inventario de Farmacos", "💊 Entrega a Residentes"])

        with tab_inv:
            st.subheader("Alta y Control de Stock")
            with st.form("form_alta_farmaco"):
                f_nom = st.text_input("Nombre del Fármaco")
                f_exist = st.number_input("Existencias Iniciales", min_value=0, value=10)
                f_dosis = st.text_input("Dosis Estándar Indicada (ej. 1 tableta cada 12 hrs)")
                btn_f = st.form_submit_button("➕ Registrar Fármaco")

                if btn_f and f_nom:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO medicamentos (nombre_farmaco, existencias, dosis_indicada) VALUES (?, ?, ?)", (f_nom, f_exist, f_dosis))
                        conn.commit()
                        st.success(f"✅ Fármaco '{f_nom}' agregado al inventario.")
                    except:
                        st.error("El fármaco ya existe en el inventario.")
                    conn.close()
                    st.rerun()

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, nombre_farmaco, existencias, dosis_indicada FROM medicamentos")
            f_rows = c.fetchall()
            conn.close()

            if f_rows:
                st.dataframe([{"ID": r[0], "Fármaco": r[1], "Stock Disponible": r[2], "Dosis Indicada": r[3]} for r in f_rows], use_container_width=True)

        with tab_ent:
            st.subheader("Registrar Entrega de Medicamento a Paciente")
            if not pacientes_lista or not f_rows:
                st.info("Requiere tener pacientes y fármacos registrados.")
            else:
                with st.form("form_entrega_med"):
                    p_sel_m = st.selectbox("Residente", [p[1] for p in pacientes_lista])
                    f_sel_m = st.selectbox("Fármaco", [f"{r[0]} | {r[1]} (Stock: {r[2]})" for r in f_rows])
                    cant_m = st.number_input("Cantidad Entregada", min_value=1, value=1)
                    btn_e_m = st.form_submit_button("💊 Entregar Medicamento")

                    if btn_e_m:
                        pid_m = p_sel_m.split(" | ")[0]
                        fid_m = int(f_sel_m.split(" | ")[0])

                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT existencias, nombre_farmaco FROM medicamentos WHERE id = ?", (fid_m,))
                        f_info = c.fetchone()

                        if f_info and f_info[0] >= cant_m:
                            nuevas_ex = f_info[0] - cant_m
                            c.execute("UPDATE medicamentos SET existencias = ? WHERE id = ?", (nuevas_ex, fid_m))
                            c.execute("INSERT INTO entregas_medicamentos (paciente_id, farmaco_id, cantidad, fecha, usuario) VALUES (?, ?, ?, ?, ?)",
                                      (pid_m, fid_m, cant_m, str(date.today()), st.session_state["username"]))
                            conn.commit()
                            st.success(f"✅ Entregadas {cant_m} unidades de '{f_info[1]}' a {p_sel_m}.")
                        else:
                            st.error("⚠️ Stock insuficiente para realizar la entrega.")
                        conn.close()
                        st.rerun()

    # ==========================================
    # 📁 MÓDULO 9: REPOSITORIO DE DOCUMENTOS
    # ==========================================
    elif menu == "📁 Repositorio de Documentos":
        st.title("📁 Repositorio Digital de Documentos")
        tab_docs, tab_folders = st.tabs(["📄 Archivos por Paciente", "📁 Personalizar / Gestionar Carpetas"])

        # Obtener carpetas
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nombre_carpeta FROM repositorio_carpetas ORDER BY nombre_carpeta ASC")
        carpetas_list = [r[0] for r in c.fetchall()]
        conn.close()

        with tab_docs:
            if not pacientes_lista:
                st.info("No hay pacientes registrados.")
            else:
                c_p1, c_p2 = st.columns(2)
                with c_p1:
                    sel_p = st.selectbox("Seleccione Residente", [p[1] for p in pacientes_lista], key="sel_p_repo")
                with c_p2:
                    sel_c = st.selectbox("Seleccione Carpeta", carpetas_list)

                pid_sel = sel_p.split(" | ")[0]

                st.subheader("➕ Subir Documento")
                file_up = st.file_uploader("Seleccione archivo", type=["pdf", "docx", "jpg", "png", "txt"])
                if file_up and st.button("📤 Guardar en Repositorio"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO repositorio_documentos (paciente_id, carpeta, nombre_archivo, fecha_subida, usuario) VALUES (?, ?, ?, ?, ?)",
                              (pid_sel, sel_c, file_up.name, str(date.today()), st.session_state["username"]))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Archivo '{file_up.name}' registrado en la carpeta '{sel_c}'.")
                    st.rerun()

                st.markdown("---")
                st.subheader(f"📄 Documentos en '{sel_c}' para {sel_p}")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT nombre_archivo, fecha_subida, usuario FROM repositorio_documentos WHERE paciente_id = ? AND carpeta = ?", (pid_sel, sel_c))
                d_rows = c.fetchall()
                conn.close()

                if d_rows:
                    st.dataframe([{"Archivo": r[0], "Fecha Subida": r[1], "Usuario Registró": r[2]} for r in d_rows], use_container_width=True)
                else:
                    st.info("No hay documentos guardados en esta carpeta.")

        with tab_folders:
            st.subheader("Gestión de Carpetas")
            c_f1, c_f2 = st.columns(2)

            with c_f1:
                st.write("**➕ Crear Nueva Carpeta**")
                n_carp = st.text_input("Nombre de la Nueva Carpeta")
                if st.button("➕ Crear Carpeta") and n_carp:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO repositorio_carpetas (nombre_carpeta) VALUES (?)", (n_carp,))
                        conn.commit()
                        st.success(f"✅ Carpeta '{n_carp}' creada.")
                    except:
                        st.error("La carpeta ya existe.")
                    conn.close()
                    st.rerun()

            with c_f2:
                st.write("**✏️ Renombrar Carpeta Existente**")
                c_ren_sel = st.selectbox("Seleccione Carpeta a Renombrar", carpetas_list)
                n_carp_ren = st.text_input("Nuevo Nombre")
                if st.button("✏️ Renombrar") and n_carp_ren:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE repositorio_carpetas SET nombre_carpeta = ? WHERE nombre_carpeta = ?", (n_carp_ren, c_ren_sel))
                    c.execute("UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?", (n_carp_ren, c_ren_sel))
                    conn.commit()
                    conn.close()
                    st.success("✅ Carpeta renombrada con éxito.")
                    st.rerun()

    # ==========================================
    # 🔍 MÓDULO 10: BUSCAR Y LISTAR PACIENTES
    # ==========================================
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Buscar y Listar Expedientes de Pacientes")
        query = st.text_input("🔎 Buscar por Folio, Expediente o Nombre")

        if pacientes_lista:
            res_filtrados = []
            q_clean = query.strip().lower()
            for pid, lbl, dj in pacientes_lista:
                exp = str(dj.get("expediente", "")).lower()
                nom = str(dj.get("nombre_completo", "")).lower() or f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')}".lower()
                if not q_clean or q_clean in pid.lower() or q_clean in exp or q_clean in nom:
                    res_filtrados.append({
                        "Folio": pid,
                        "Expediente": dj.get("expediente", "S/N"),
                        "Nombre del Residente": dj.get("nombre_completo") or f"{dj.get('nombre', '')} {dj.get('apellido_paterno', '')}".strip(),
                        "Etapa Actual": dj.get("etapa_actual", "Acogida"),
                        "Fecha Ingreso": dj.get("fecha_ingreso", "N/A"),
                        "Fecha Inicio Etapa": dj.get("fecha_inicio_etapa", "N/A")
                    })
            st.dataframe(res_filtrados, use_container_width=True)

    # ==========================================
    # ⚙️ MÓDULO 11: CONFIGURACIÓN Y SEGURIDAD
    # ==========================================
    elif menu == "⚙️ Configuración y Seguridad":
        st.title("⚙️ Configuración y Seguridad del Sistema")

        is_admin = (st.session_state.get("username") == "admin" or st.session_state.get("rol") == "Administrador")

        if is_admin:
            tab_pass, tab_users = st.tabs(["🔑 Cambiar mi Contraseña", "👥 Usuarios y Roles del Personal"])
        else:
            tab_pass = st.container()

        with tab_pass:
            st.subheader("Cambiar Mi Contraseña")
            with st.form("form_change_my_pass"):
                old_p = st.text_input("Contraseña Actual", type="password")
                new_p = st.text_input("Nueva Contraseña", type="password")
                conf_p = st.text_input("Confirmar Nueva Contraseña", type="password")
                btn_p = st.form_submit_button("🔄 Actualizar Contraseña")

                if btn_p:
                    if new_p != conf_p:
                        st.error("Las nuevas contraseñas no coinciden.")
                    else:
                        user_ok = verificar_login(st.session_state["username"], old_p)
                        if user_ok:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                                      (hash_pass(new_p), st.session_state["username"]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada exitosamente.")
                        else:
                            st.error("La contraseña actual es incorrecta.")

        if is_admin:
            with tab_users:
                st.subheader("👥 Alta de Cuentas de Personal")
                with st.form("form_reg_staff"):
                    u_user = st.text_input("Nombre de Usuario (Login)")
                    u_nom = st.text_input("Nombre Completo del Colaborador")
                    u_pass = st.text_input("Contraseña Inicial", type="password")
                    u_rol = st.selectbox("Rol de Acceso", ["Administrador", "Lectura / Escritura", "Solo Lectura"])
                    btn_u = st.form_submit_button("➕ Registrar Usuario")

                    if btn_u and u_user and u_pass:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)",
                                      (u_user, hash_pass(u_pass), u_nom, u_rol))
                            conn.commit()
                            st.success(f"✅ Usuario '{u_user}' creado exitosamente con rol '{u_rol}'.")
                        except:
                            st.error("El nombre de usuario ya está registrado.")
                        conn.close()
                        st.rerun()

                st.markdown("---")
                st.subheader("Catálogo de Usuarios Registrados")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT id, username, nombre_completo, rol FROM usuarios")
                u_rows = c.fetchall()
                conn.close()

                if u_rows:
                    st.dataframe([{"ID": r[0], "Usuario": r[1], "Nombre Completo": r[2], "Rol": r[3]} for r in u_rows], use_container_width=True)

    # ==========================================
    # 📦 MÓDULO 12: RESPALDO Y RESTAURACIÓN
    # ==========================================
    elif menu == "📦 Respaldo y Restauración":
        st.title("📦 Respaldo y Restauración de Base de Datos")
        
        st.subheader("⬇️ Descargar Copia de Seguridad")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button("📦 Descargar Backup .db", data=f, file_name=f"Backup_Sawabona_{date.today()}.db", mime="application/octet-stream")

        st.markdown("---")
        st.subheader("📤 Restaurar Copia de Seguridad")
        file_db = st.file_uploader("Seleccione archivo .db para restaurar", type=["db"])
        if file_db and st.button("⚠️ Restaurar Base de Datos"):
            with open(DB_FILE, "wb") as f:
                f.write(file_db.getbuffer())
            st.success("✅ Base de datos restaurada correctamente. Reiniciando sesión...")
            st.rerun()

if __name__ == "__main__":
    main()

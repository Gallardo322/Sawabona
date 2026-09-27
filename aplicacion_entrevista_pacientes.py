import streamlit as st
import sqlite3
import json
import hashlib
import os
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

def clean_pdf_text(texto):
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
        born = datetime.strptime(born_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except:
        return 0

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios del Sistema
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Lectura/Escritura',
            activo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabla de Pacientes Base
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre TEXT,
            ap_paterno TEXT,
            ap_materno TEXT,
            nombre_completo TEXT,
            sexo TEXT,
            fecha_nacimiento TEXT,
            fecha_ingreso_inst TEXT,
            etapa_actual TEXT DEFAULT 'Acogida',
            fecha_inicio_etapa TEXT,
            activo INTEGER DEFAULT 1,
            fecha_registro TEXT,
            usuario_registro TEXT
        )
    ''')

    # Tabla de Ficha de Ingreso (ingreso AV Sawabona.pdf)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            sucursal TEXT,
            expediente TEXT,
            fecha_ingreso TEXT,
            hora_ingreso TEXT,
            costo_ingreso REAL,
            mensualidad REAL,
            pagare_importe REAL,
            nombre_usuario TEXT,
            edad INTEGER,
            fecha_nacimiento TEXT,
            estado_civil TEXT,
            escolaridad TEXT,
            religion TEXT,
            ocupacion TEXT,
            servicios_medicos TEXT,
            especifique_serv_med TEXT,
            domicilio_calle TEXT,
            domicilio_num TEXT,
            domicilio_colonia TEXT,
            domicilio_municipio TEXT,
            domicilio_estado TEXT,
            domicilio_cp TEXT,
            responsable_nombre TEXT,
            responsable_parentesco TEXT,
            responsable_telefono TEXT,
            responsable_email TEXT,
            responsable_domicilio TEXT,
            contacto2_nombre TEXT,
            contacto2_parentesco TEXT,
            contacto2_telefono TEXT,
            contacto2_email TEXT,
            sustancias_json TEXT,
            otra_sustancia TEXT,
            modalidad_internamiento TEXT,
            fecha_captura TEXT
        )
    ''')

    # Tabla de Entrevistas Iniciales
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')

    # Tabla de Consejerías
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            tema TEXT,
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

    # Crear Admin por defecto
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        pass_hash = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) VALUES (?, ?, ?, ?, 1)',
                  ('admin', pass_hash, 'Administrador del Sistema', 'Administrador'))

    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo, rol, activo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    user = c.fetchone()
    conn.close()
    return user

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

# Main System Init
init_db()

def main():
    render_header()
    
    # --- CONTROL DE INACTIVIDAD ---
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
            submit = st.form_submit_button("Ingresar", use_container_width=True)
            if submit:
                res = verificar_login(user, pwd)
                if res:
                    if res[3] == 0:
                        st.error("⛔ Esta cuenta se encuentra bloqueada. Contacte al administrador.")
                    else:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = res[0]
                        st.session_state["nombre_completo"] = res[1]
                        st.session_state["rol"] = res[2]
                        st.session_state["ultima_actividad"] = datetime.now()
                        st.balloons()
                        st.toast("¡Bienvenido al sistema!", icon="🎉")
                        st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
        return

    # --- NAVEGACIÓN Y MENÚ ---
    st.sidebar.markdown('''
        <div style='text-align: center; padding: 10px; background-color: #E8F5E9; border-radius: 8px; margin-bottom: 15px;'>
            <h3 style='color: #2E7D32; margin:0;'>🌱 Sawabona</h3>
            <p style='color: #388E3C; margin:0; font-size:0.85em;'>Comunidad Terapéutica</p>
        </div>
    ''', unsafe_allow_html=True)

    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    st.sidebar.write(f"🛡️ **Rol**: {st.session_state.get('rol', 'Lectura/Escritura')}")

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
            "⚙️ Configuración y Seguridad"
        ]
    )

    if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- MODULO 1: TABLERO GENERAL ---
    if menu == "🏠 Inicio / Tablero General":
        st.title("🏠 Tablero de Control y Estado Clínico")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM pacientes WHERE activo = 1')
        activos = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM pacientes WHERE activo = 0')
        inactivos = c.fetchone()[0]
        conn.close()

        m1, m2 = st.columns(2)
        m1.metric("🟢 Residentes Activos en Tratamiento", activos)
        m2.metric("🔴 Residentes Inactivos / Bajas", inactivos)

        st.subheader("📊 Desglose por Etapa Clínica")
        etapas = ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"]
        cols = st.columns(5)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for idx, et in enumerate(etapas):
            c.execute('SELECT COUNT(*) FROM pacientes WHERE etapa_actual = ? AND activo = 1', (et,))
            cant = c.fetchone()[0]
            cols[idx].metric(et, cant)
        conn.close()

    # --- MODULO 2: REGISTRO Y EDICIÓN DE PACIENTES ---
    elif menu == "👤 Registro y Edición de Pacientes":
        st.title("👤 Registro y Administración de Residentes")
        
        tab_nuevo, tab_editar, tab_estado = st.tabs([
            "➕ Alta de Nuevo Paciente",
            "✏️ Editar Paciente Existente",
            "🔒 Gestión de Estado (Activo/Bloqueado)"
        ])

        with tab_nuevo:
            st.subheader("Formulario de Alta de Paciente")
            with st.form("form_alta_paciente"):
                col_exp, col_nom, col_pat, col_mat = st.columns(4)
                expediente = col_exp.text_input("No. Expediente *").strip()
                nombre = col_nom.text_input("Nombre(s) *").strip()
                ap_paterno = col_pat.text_input("Apellido Paterno *").strip()
                ap_materno = col_mat.text_input("Apellido Materno").strip()

                col_f1, col_f2, col_f3, col_s = st.columns(4)
                fnac = col_f1.date_input("Fecha de Nacimiento", value=date(1995, 1, 1))
                fing_inst = col_f2.date_input("Fecha de Ingreso a la Institución", value=date.today())
                finic_etapa = col_f3.date_input("Fecha de Inicio de Etapa Actual", value=date.today())
                sexo = col_s.selectbox("Sexo", ["Masculino", "Femenino"])

                etapa_inicial = st.selectbox("Etapa Inicial", ["Acogida", "Identificación", "Elaboración", "Consolidación", "Servicio Social"])

                btn_alta = st.form_submit_button("💾 Dar de Alta Paciente", use_container_width=True)

                if btn_alta:
                    if not expediente or not nombre or not ap_paterno:
                        st.error("⚠️ Los campos Expediente, Nombre y Apellido Paterno son obligatorios.")
                    else:
                        full_name = f"{nombre} {ap_paterno} {ap_materno}".strip()
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        # Validar duplicados
                        c.execute('SELECT paciente_id, expediente, nombre_completo FROM pacientes WHERE LOWER(nombre_completo) = LOWER(?)', (full_name,))
                        dup_name = c.fetchone()
                        c.execute('SELECT paciente_id, expediente, nombre_completo FROM pacientes WHERE expediente = ? AND expediente != ""', (expediente,))
                        dup_exp = c.fetchone()

                        if dup_name:
                            st.error(f"⛔ REGISTRO DUPLICADO: Ya existe un paciente registrado con el nombre '{full_name}' (Folio: {dup_name[0]}, Exp: {dup_name[1]}).")
                            conn.close()
                        elif dup_exp:
                            st.error(f"⛔ EXPEDIENTE DUPLICADO: El No. de Expediente '{expediente}' ya pertenece al paciente '{dup_exp[2]}'.")
                            conn.close()
                        else:
                            # Autoincrementar PAC-XXX
                            c.execute('SELECT COUNT(*) FROM pacientes')
                            cnt = c.fetchone()[0] + 1
                            pac_id = f"PAC-{cnt:03d}"
                            f_reg = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            c.execute('''
                                INSERT INTO pacientes (
                                    paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo,
                                    sexo, fecha_nacimiento, fecha_ingreso_inst, etapa_actual, fecha_inicio_etapa,
                                    activo, fecha_registro, usuario_registro
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                            ''', (
                                pac_id, expediente, nombre, ap_paterno, ap_materno, full_name,
                                sexo, str(fnac), str(fing_inst), etapa_inicial, str(finic_etapa),
                                f_reg, st.session_state["username"]
                            ))
                            conn.commit()
                            conn.close()

                            st.balloons()
                            st.toast("✅ ¡Paciente registrado con éxito!", icon="🎉")
                            st.markdown(f"<div style='text-align: center; padding: 15px; background-color: #D4EDDA; color: #155724; border-radius: 8px; font-weight: bold; font-size: 1.2em;'>✅ ¡Paciente {full_name} (Folio: {pac_id}, Exp: {expediente}) registrado exitosamente!</div>", unsafe_allow_html=True)

        st.divider()
        st.subheader("📋 Lista de Residentes Activos Registrados")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, expediente, nombre_completo, fecha_nacimiento, fecha_ingreso_inst, etapa_actual, fecha_inicio_etapa FROM pacientes WHERE activo = 1 ORDER BY fecha_registro DESC')
        rows = c.fetchall()
        conn.close()
        if rows:
            table_data = []
            for r in rows:
                p_id, exp, name, fnac_s, fing_s, et, finic_s = r
                edad_calc = calculate_age(fnac_s)
                dias_etapa = 0
                if finic_s:
                    try:
                        dias_etapa = (date.today() - datetime.strptime(finic_s, "%Y-%m-%d").date()).days
                    except:
                        pass
                table_data.append({
                    "Folio": p_id,
                    "Expediente": exp,
                    "Nombre Completo": name,
                    "Edad": f"{edad_calc} años",
                    "F. Nacimiento": fnac_s or "Sin reg.",
                    "F. Ingreso Inst.": fing_s or "Sin reg.",
                    "Etapa Actual": et,
                    "Días en Etapa": dias_etapa
                })
            st.dataframe(table_data, use_container_width=True)

    # --- MODULO 3: FICHA DE INGRESO Y ADMISIÓN (ingreso AV Sawabona.pdf) ---
    elif menu == "📄 Ficha de Ingreso y Admisión":
        st.title("📄 Ficha de Ingreso y Admisión Oficial (Sawabona Shikoba A.C.)")
        st.caption("Formato oficial ajustado a la Norma Oficial Mexicana NOM-028-SSA2-2009")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT paciente_id, expediente, nombre_completo, fecha_nacimiento, fecha_ingreso_inst FROM pacientes WHERE activo = 1')
        pacs = c.fetchall()
        conn.close()

        if not pacs:
            st.warning("⚠️ No hay pacientes registrados aún. Por favor registre un paciente en el Módulo '👤 Registro y Edición de Pacientes'.")
        else:
            pac_options = [f"{p[0]} - {p[2]} (Exp: {p[1]})" for p in pacs]
            p_sel = st.selectbox("Seleccione el Paciente a Capturar/Consultar Ficha", pac_options)
            p_id_sel = p_sel.split(" - ")[0]

            # Cargar datos base del paciente
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, fecha_nacimiento, fecha_ingreso_inst FROM pacientes WHERE paciente_id = ?', (p_id_sel,))
            p_data = c.fetchone()

            # Cargar ficha previa si existe
            c.execute('SELECT * FROM ficha_ingreso WHERE paciente_id = ?', (p_id_sel,))
            ficha_prev = c.fetchone()
            conn.close()

            f_dict = {}
            if ficha_prev:
                # Map SQLite row to dict
                cols_f = ["paciente_id", "sucursal", "expediente", "fecha_ingreso", "hora_ingreso", "costo_ingreso", "mensualidad", "pagare_importe", "nombre_usuario", "edad", "fecha_nacimiento", "estado_civil", "escolaridad", "religion", "ocupacion", "servicios_medicos", "especifique_serv_med", "domicilio_calle", "domicilio_num", "domicilio_colonia", "domicilio_municipio", "domicilio_estado", "domicilio_cp", "responsable_nombre", "responsable_parentesco", "responsable_telefono", "responsable_email", "responsable_domicilio", "contacto2_nombre", "contacto2_parentesco", "contacto2_telefono", "contacto2_email", "sustancias_json", "otra_sustancia", "modalidad_internamiento", "fecha_captura"]
                for i_col, c_name in enumerate(cols_f):
                    if i_col < len(ficha_prev):
                        f_dict[c_name] = ficha_prev[i_col]

            st.info(f"📋 Ficha de Admisión para: **{p_data[5]}** | Folio: **{p_data[0]}** | Exp: **{p_data[1]}**")

            with st.form("form_ficha_ingreso"):
                f_tab1, f_tab2, f_tab3, f_tab4, f_tab5 = st.tabs([
                    "1. Admisión y Sucursal",
                    "2. Datos del Usuario / Residentes",
                    "3. Sustancias de Consumo",
                    "4. Responsable Familiar y Contactos",
                    "5. Cláusulas y Cuotas (NOM-028)"
                ])

                with f_tab1:
                    st.subheader("Datos de Admisión e Institución")
                    c_a1, c_a2, c_a3 = st.columns(3)
                    sucursal = c_a1.text_input("Sucursal a Referir *", value=f_dict.get("sucursal", "C. Corregidora #135 Col. Centro Colima C.P. 28000"))
                    expediente_f = c_a2.text_input("No. de Expediente", value=p_data[1] or f_dict.get("expediente", ""))
                    
                    f_ing_val = p_data[7] or f_dict.get("fecha_ingreso", str(date.today()))
                    try:
                        d_ing_date = datetime.strptime(f_ing_val, "%Y-%m-%d").date()
                    except:
                        d_ing_date = date.today()

                    fecha_ingreso_f = c_a3.date_input("Fecha de Ingreso", value=d_ing_date)

                    c_h1, c_h2, c_h3, c_h4 = st.columns(4)
                    hora_ingreso = c_h1.time_input("Hora de Ingreso", value=datetime.now().time())
                    costo_ingreso = c_h2.number_input("Costo de Ingreso ($)", value=float(f_dict.get("costo_ingreso", 4500.0)))
                    mensualidad = c_h3.number_input("Cuota Mensual ($)", value=float(f_dict.get("mensualidad", 6000.0)))
                    pagare_importe = c_h4.number_input("Pagaré Importe ($)", value=float(f_dict.get("pagare_importe", 42000.0)))

                with f_tab2:
                    st.subheader("Datos Generales del Usuario / Residente")
                    nombre_usuario = st.text_input("Nombre Completo del Usuario", value=p_data[5], disabled=True)
                    
                    fnac_val = p_data[6] or f_dict.get("fecha_nacimiento", "1995-01-01")
                    try:
                        d_fnac_date = datetime.strptime(fnac_val, "%Y-%m-%d").date()
                    except:
                        d_fnac_date = date(1995, 1, 1)

                    c_u1, c_u2, c_u3, c_u4 = st.columns(4)
                    fecha_nacimiento_f = c_u1.date_input("Fecha de Nacimiento", value=d_fnac_date)
                    edad_calc_f = calculate_age(str(fecha_nacimiento_f))
                    c_u2.text_input("Edad Calculada", value=f"{edad_calc_f} años", disabled=True)

                    est_civ_opts = ["Soltero(a)", "Casado(a)", "Unión Libre", "Divorciado(a)", "Viudo(a)"]
                    estado_civil = c_u3.selectbox("Estado Civil", est_civ_opts, index=get_safe_index(est_civ_opts, f_dict.get("estado_civil")))
                    
                    esc_opts = ["Primaria", "Secundaria", "Preparatoria / Bachillerato", "Licenciatura", "Postgrado", "Sin escolaridad"]
                    escolaridad = c_u4.selectbox("Escolaridad", esc_opts, index=get_safe_index(esc_opts, f_dict.get("escolaridad")))

                    c_u5, c_u6, c_u7, c_u8 = st.columns(4)
                    religion = c_u5.text_input("Religión", value=f_dict.get("religion", "Católica"))
                    ocupacion = c_u6.text_input("Ocupación", value=f_dict.get("ocupacion", "Empleado"))
                    servicios_medicos = c_u7.selectbox("¿Cuenta con Servicios Médicos?", ["Sí", "No"], index=0 if f_dict.get("servicios_medicos") == "Sí" else 1)
                    especifique_serv_med = c_u8.text_input("Especifique Servicio Médico", value=f_dict.get("especifique_serv_med", "IMSS / INSABI"))

                    st.markdown("**Domicilio Particular del Usuario:**")
                    c_d1, c_d2, c_d3 = st.columns([2, 1, 2])
                    domicilio_calle = c_d1.text_input("Calle", value=f_dict.get("domicilio_calle", ""))
                    domicilio_num = c_d2.text_input("No. Ext / Int", value=f_dict.get("domicilio_num", "S/N"))
                    domicilio_colonia = c_d3.text_input("Colonia / Población", value=f_dict.get("domicilio_colonia", ""))

                    c_d4, c_d5, c_d6 = st.columns(3)
                    domicilio_municipio = c_d4.text_input("Municipio", value=f_dict.get("domicilio_municipio", "Colima"))
                    domicilio_estado = c_d5.text_input("Estado", value=f_dict.get("domicilio_estado", "Colima"))
                    domicilio_cp = c_d6.text_input("Código Postal", value=f_dict.get("domicilio_cp", "28000"))

                with f_tab3:
                    st.subheader("Sustancias que Consume al Ingresar (ingreso AV Sawabona.pdf)")
                    st.caption("Marque todas las sustancias que el usuario consume actualmente:")

                    sust_guardadas = json.loads(f_dict.get("sustancias_json", "{}")) if f_dict.get("sustancias_json") else {}

                    lista_sustancias = [
                        "Alcaloides", "Alcohol", "Anfetaminas", "Benzodiazepinas",
                        "Cannabis", "Esteroides", "Fármacos", "LSD",
                        "Meta-anfetaminas", "Opiáceos", "Psicoactivas", "Solventes", "Tabaco"
                    ]

                    cols_s = st.columns(4)
                    sust_seleccionadas = {}
                    for idx_s, s_item in enumerate(lista_sustancias):
                        chk = cols_s[idx_s % 4].checkbox(s_item, value=sust_guardadas.get(s_item, False))
                        sust_seleccionadas[s_item] = chk

                    otra_sustancia = st.text_input("Otra Sustancia (Especifique):", value=f_dict.get("otra_sustancia", ""))
                    
                    st.divider()
                    modalidad_opts = ["Voluntaria (NOM-028-SSA2-2009)", "Involuntaria / Solicitud Familiar"]
                    modalidad_internamiento = st.radio("Modalidad de Internamiento", modalidad_opts, index=0 if "Voluntaria" in f_dict.get("modalidad_internamiento", "") else 1)

                with f_tab4:
                    st.subheader("Datos del Responsable Familiar / Tutor Legal")
                    st.caption("Persona responsable del internamiento y pagos:")

                    c_r1, c_r2 = st.columns(2)
                    responsable_nombre = c_r1.text_input("Nombre Completo del Responsable Familiar *", value=f_dict.get("responsable_nombre", ""))
                    responsable_parentesco = c_r2.text_input("Parentesco ('Desea internar a su...') *", value=f_dict.get("responsable_parentesco", "Padre / Madre / Cónyuge"))

                    c_r3, c_r4 = st.columns(2)
                    responsable_telefono = c_r3.text_input("Teléfono(s) del Responsable *", value=f_dict.get("responsable_telefono", ""))
                    responsable_email = c_r4.text_input("Email del Responsable", value=f_dict.get("responsable_email", ""))

                    responsable_domicilio = st.text_area("Domicilio Completo del Responsable", value=f_dict.get("responsable_domicilio", ""))

                    st.subheader("Contacto Emergencia Secundario")
                    c_c1, c_c2, c_c3 = st.columns(3)
                    contacto2_nombre = c_c1.text_input("Nombre Contacto 2", value=f_dict.get("contacto2_nombre", ""))
                    contacto2_parentesco = c_c2.text_input("Parentesco Contacto 2", value=f_dict.get("contacto2_parentesco", ""))
                    contacto2_telefono = c_c3.text_input("Teléfono Contacto 2", value=f_dict.get("contacto2_telefono", ""))
                    contacto2_email = st.text_input("Email Contacto 2", value=f_dict.get("contacto2_email", ""))

                with f_tab5:
                    st.subheader("Términos del Tratamiento y Compromiso del Usuario")
                    st.markdown('''
                        * **Duración**: Tratamiento residencial de 6 a 8 meses (mínimo obligatorio de 7 meses según contrato).
                        * **Costo de Ingreso**: $4,500.00 (Exámenes médicos, químicos, psicológicos y 2 playeras de uniforme).
                        * **Cuota Mensual**: $6,000.00 (Atención médica, psicológica, consejería, alimentación y talleres).
                        * **Pagaré de Garantía**: $42,000.00.
                        * **Uniforme por Etapa**: Playeras oficiales por color ($200 c/u): *Roja (Acogida), Naranja (Identificación), Morada (Elaboración), Azul Turquesa (Consolidación), Verde (Servicio Social)*.
                        * **Normativa**: Apego estricto a los derechos humanos y dignidad del paciente conforme a la **NOM-028-SSA2-2009**.
                    ''')

                btn_guardar_ficha = st.form_submit_button("💾 Guardar y Actualizar Ficha de Ingreso", use_container_width=True)

                if btn_guardar_ficha:
                    if not responsable_nombre:
                        st.error("⚠️ El campo 'Nombre Completo del Responsable Familiar' es obligatorio.")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        # Actualizar base de pacientes fecha de nacimiento e ingreso
                        c.execute('''
                            UPDATE pacientes
                            SET fecha_nacimiento = ?, fecha_ingreso_inst = ?
                            WHERE paciente_id = ?
                        ''', (str(fecha_nacimiento_f), str(fecha_ingreso_f), p_id_sel))

                        # Insert/Replace Ficha de Ingreso
                        c.execute('''
                            INSERT OR REPLACE INTO ficha_ingreso (
                                paciente_id, sucursal, expediente, fecha_ingreso, hora_ingreso,
                                costo_ingreso, mensualidad, pagare_importe, nombre_usuario, edad,
                                fecha_nacimiento, estado_civil, escolaridad, religion, ocupacion,
                                servicios_medicos, especifique_serv_med, domicilio_calle, domicilio_num,
                                domicilio_colonia, domicilio_municipio, domicilio_estado, domicilio_cp,
                                responsable_nombre, responsable_parentesco, responsable_telefono,
                                responsable_email, responsable_domicilio, contacto2_nombre,
                                contacto2_parentesco, contacto2_telefono, contacto2_email,
                                sustancias_json, otra_sustancia, modalidad_internamiento, fecha_captura
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            p_id_sel, sucursal, expediente_f, str(fecha_ingreso_f), str(hora_ingreso),
                            costo_ingreso, mensualidad, pagare_importe, p_data[5], edad_calc_f,
                            str(fecha_nacimiento_f), estado_civil, escolaridad, religion, ocupacion,
                            servicios_medicos, especifique_serv_med, domicilio_calle, domicilio_num,
                            domicilio_colonia, domicilio_municipio, domicilio_estado, domicilio_cp,
                            responsable_nombre, responsable_parentesco, responsable_telefono,
                            responsable_email, responsable_domicilio, contacto2_nombre,
                            contacto2_parentesco, contacto2_telefono, contacto2_email,
                            json.dumps(sust_seleccionadas), otra_sustancia, modalidad_internamiento,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))

                        conn.commit()
                        conn.close()

                        st.balloons()
                        st.toast("✅ Ficha de Ingreso guardada exitosamente", icon="🎉")
                        st.markdown(f"<div style='text-align: center; padding: 15px; background-color: #D4EDDA; color: #155724; border-radius: 8px; font-weight: bold; font-size: 1.2em;'>✅ ¡Ficha de Ingreso de {p_data[5]} guardada y sincronizada correctamente!</div>", unsafe_allow_html=True)

    # --- RESTO DE MÓDULOS Y NAVEGACIÓN ---
    else:
        st.info(f"Módulo '{menu}' seleccionado.")

if __name__ == "__main__":
    main()

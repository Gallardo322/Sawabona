import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Consejería y Control Médico",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    # Tabla de Pacientes / Entrevistas
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
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            meds_json TEXT,
            observaciones TEXT
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

def listar_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas ORDER BY fecha_modificacion DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamentos(paciente_id, lista_meds, observaciones, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(lista_meds, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    existe = c.fetchone()
    
    if existe:
        c.execute('''
            UPDATE medicamentos 
            SET fecha_modificacion = ?, meds_json = ?, observaciones = ?
            WHERE paciente_id = ?
        ''', (fecha_actual, meds_json, observaciones, paciente_id))
    else:
        c.execute('''
            INSERT INTO medicamentos (paciente_id, fecha_registro, fecha_modificacion, usuario_registro, meds_json, observaciones)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (paciente_id, fecha_actual, fecha_actual, usuario, meds_json, observaciones))
        
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
    c.execute('SELECT paciente_id, meds_json, observaciones, fecha_modificacion FROM medicamentos')
    rows = c.fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        p_id, m_json, obs, f_mod = r
        try:
            m_list = json.loads(m_json)
        except:
            m_list = []
        resultado.append({
            "paciente_id": p_id,
            "medicamentos": m_list,
            "observaciones": obs,
            "fecha_modificacion": f_mod
        })
    return resultado

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SISTEMA CLINICO DE CONSEJERIA Y CONTROL MEDICO", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Reporte Oficial de Expediente", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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
        'ñ': 'n', 'Ñ': 'N', '¿': '', '¡': ''
    }
    for k, v in replacements.items():
        texto = texto.replace(k, v)
    return str(texto)

def generar_pdf(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Datos Principales
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"NUMERO DE PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla de Consumo
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, "CONSUMO DE SUSTANCIAS", new_x="LMARGIN", new_y="NEXT")
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
        
    pdf.ln(4)
    
    # Sustancia de Impacto
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Normalmente consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Disposición al Cambio
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Situación Socio-Familiar
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "SITUACION SOCIAL-FAMILIAR Y RIESGO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Integrantes de la familia con mayor contacto: {limpiar_texto(datos.get('familia_integrantes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Relaciones sexuales tras consumir: {limpiar_texto(datos.get('relaciones_post_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Involucrado en abuso fisico/sexual por consumo: {limpiar_texto(datos.get('abuso_flag', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Observaciones y Firma
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION DE LA SESION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    # Firma
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.epw, 5, f"Nombre de quien aplica: {limpiar_texto(datos.get('evaluador_nombre', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 5, f"Cargo: {limpiar_texto(datos.get('evaluador_cargo', ''))}", new_x="LMARGIN", new_y="NEXT")
    
    pdf_filename = f"Entrevista_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_medicamentos(paciente_id, lista_meds, observaciones):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, f"HOJA DE CONTROL DE MEDICAMENTOS Y DOSIS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(pdf.epw, 7, f"PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Fecha de emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    # Tabla de Medicamentos
    pdf.set_font("Helvetica", "B", 9)
    col_widths = [45, 20, 20, 20, 22, 22, 41]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Dosis/Dia", "Existencia", "Indicaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    for m in lista_meds:
        m_nom = limpiar_texto(m.get("nombre", ""))
        m_man = float(m.get("manana", 0))
        m_tar = float(m.get("tarde", 0))
        m_noc = float(m.get("noche", 0))
        m_ext = float(m.get("existencia", 0))
        m_ind = limpiar_texto(m.get("indicaciones", ""))
        dosis_dia = m_man + m_tar + m_noc
        
        pdf.cell(col_widths[0], 6, m_nom[:24], border=1)
        pdf.cell(col_widths[1], 6, f"{m_man:g}", border=1, align="C")
        pdf.cell(col_widths[2], 6, f"{m_tar:g}", border=1, align="C")
        pdf.cell(col_widths[3], 6, f"{m_noc:g}", border=1, align="C")
        pdf.cell(col_widths[4], 6, f"{dosis_dia:g}", border=1, align="C")
        pdf.cell(col_widths[5], 6, f"{m_ext:g}", border=1, align="C")
        pdf.cell(col_widths[6], 6, m_ind[:22], border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(4)
    if observaciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, "Observaciones de la Medicacion:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_lista_compras(items_compra):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(pdf.epw, 8, "REPORTE DE REABASTECIMIENTO Y COMPRA DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(pdf.epw, 6, f"Pacientes con dosis insuficiente para la siguiente jornada - {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)
    
    pdf.set_font("Helvetica", "B", 9)
    col_widths = [30, 50, 25, 25, 30, 30]
    headers = ["Paciente Folio", "Medicamento", "Existencia", "Dosis Diaria", "Estatus", "Comp. Rec. (7d)"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 9)
    for item in items_compra:
        pdf.cell(col_widths[0], 6, limpiar_texto(item['paciente_id']), border=1, align="C")
        pdf.cell(col_widths[1], 6, limpiar_texto(item['medicamento'])[:28], border=1)
        pdf.cell(col_widths[2], 6, f"{item['existencia']:g}", border=1, align="C")
        pdf.cell(col_widths[3], 6, f"{item['dosis_diaria']:g}", border=1, align="C")
        pdf.cell(col_widths[4], 6, limpiar_texto(item['estatus']), border=1, align="C")
        pdf.cell(col_widths[5], 6, f"{item['compra_recomendada']:g} unid.", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

# --- INICIALIZAR DB Y ESTADO ---
init_db()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "nombre_completo" not in st.session_state:
    st.session_state["nombre_completo"] = ""

# --- PANTALLA DE LOGIN ---
if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Entrevistas y Control Médico</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales para continuar</p>", unsafe_allow_html=True)
    
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
    st.sidebar.title("📋 Control Clínico")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "📝 Nueva Entrevista / Editar",
            "🔍 Buscar y Listar Pacientes",
            "💊 Control de Medicamentos y Dosis",
            "🚨 Alertas de Existencia y Compras",
            "⚙️ Seguridad / Contraseña"
        ]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- SECCIÓN 1: FORMULARIO DE ENTREVISTA ---
    if menu == "📝 Nueva Entrevista / Editar":
        st.title("📋 Entrevista Inicial de Consejería")
        st.caption("Formulario de evaluación digital de consumo de sustancias")
        
        # Cargar paciente existente si se especifica
        paciente_id_input = st.text_input("🔑 NÚMERO DE PACIENTE / FOLIO *", value="").strip()
        
        datos_existentes = {}
        if paciente_id_input:
            datos_cargados, f_reg, f_mod, u_reg = obtener_entrevista(paciente_id_input)
            if datos_cargados:
                st.success(f"📌 Expediente cargado. Registrado el {f_reg} por {u_reg}. Última modificación: {f_mod}")
                datos_existentes = datos_cargados
            else:
                st.info("🆕 Folio nuevo. Complete los datos para registrar un nuevo expediente.")

        with st.form("formulario_entrevista"):
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "1. Datos Generales",
                "2. Consumo de Sustancias",
                "3. Disposición al Cambio",
                "4. Entorno y Riesgos",
                "5. Observaciones y Firma"
            ])
            
            # --- TAB 1: DATOS GENERALES ---
            with tab1:
                st.subheader("Datos Socio-Demográficos Basales")
                c1, c2 = st.columns(2)
                with c1:
                    dependientes_flag = st.selectbox("¿Alguien depende económicamente de usted?", ["NO", "SÍ"], 
                                                     index=1 if datos_existentes.get("dependientes_flag") == "SÍ" else 0)
                    dependientes_quienes = st.text_input("¿Quiénes o quiénes?", value=datos_existentes.get("dependientes_quienes", ""))
                with c2:
                    pareja_flag = st.selectbox("¿Tiene pareja?", ["NO", "SÍ"],
                                               index=1 if datos_existentes.get("pareja_flag") == "SÍ" else 0)
                    pareja_tiempo = st.text_input("Tiempo de relación", value=datos_existentes.get("pareja_tiempo", ""))

            # --- TAB 2: CONSUMO DE SUSTANCIAS ---
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

            # --- TAB 3: DISPOSICIÓN AL CAMBIO ---
            with tab3:
                st.subheader("Evaluación de la Disposición al Cambio")
                abst_mayor_tiempo = st.text_area("Mayor periodo de abstinencia logrado (Si nunca se ha abstenido marque 0)", value=datos_existentes.get("abst_mayor_tiempo", ""))
                abst_fecha = st.text_input("¿Cuándo ocurrió? (Mes y Año)", value=datos_existentes.get("abst_fecha", ""))
                abst_motivo = st.text_area("¿Por qué se abstuvo en esa ocasión y qué hizo para mantenerse?", value=datos_existentes.get("abst_motivo", ""))
                abst_6meses = st.text_area("En los últimos 6 meses, ¿cuánto es el mayor periodo sin consumir y cuándo ocurrió?", value=datos_existentes.get("abst_6meses", ""))
                
                importancia_options = [
                    "1. NADA IMPORTANTE",
                    "2. POCO IMPORTANTE",
                    "3. ALGO IMPORTANTE",
                    "4. IMPORTANTE",
                    "5. MUY IMPORTANTE"
                ]
                imp_saved = datos_existentes.get("importancia_cambio", "3. ALGO IMPORTANTE")
                imp_index = importancia_options.index(imp_saved) if imp_saved in importancia_options else 2
                importancia_cambio = st.select_slider("Actualmente, ¿qué tan importante es para usted dejar de consumir?", options=importancia_options, value=importancia_options[imp_index])

            # --- TAB 4: ENTORNO Y RIESGOS ---
            with tab4:
                st.subheader("Situación Social-Familiar")
                familia_integrantes = st.text_area("¿Quiénes integran su familia (con la que tiene mayor contacto)?", value=datos_existentes.get("familia_integrantes", ""))
                
                st.subheader("Factores de Riesgo")
                c_r1, c_r2 = st.columns(2)
                with c_r1:
                    relaciones_post_consumo = st.selectbox("¿Ha tenido relaciones sexuales después de consumir?", ["NO", "SÍ"],
                                                            index=1 if datos_existentes.get("relaciones_post_consumo") == "SÍ" else 0)
                with c_r2:
                    abuso_flag = st.selectbox("¿Se ha visto involucrado en abuso físico o sexual por el consumo?", ["NO", "SÍ"],
                                              index=1 if datos_existentes.get("abuso_flag") == "SÍ" else 0)

            # --- TAB 5: OBSERVACIONES Y FIRMA ---
            with tab5:
                st.subheader("Evaluación Clínica y Cierre")
                problemas_sesion = st.text_area("Problemas presentados durante la sesión (comunicación, actitud, ideas, comportamiento, ánimo)", value=datos_existentes.get("problemas_sesion", ""))
                observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    evaluador_nombre = st.text_input("Nombre de quien aplica la entrevista", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                with c_f2:
                    evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

            # BOTÓN GUARDAR
            guardar_btn = st.form_submit_button("💾 Guardar Expediente de Paciente", use_container_width=True)
            
            if guardar_btn:
                if not paciente_id_input:
                    st.error("⚠️ El NÚMERO DE PACIENTE / FOLIO es obligatorio.")
                else:
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
                    st.success(f"✅ ¡Expediente {paciente_id_input} guardado correctamente en la base de datos!")

    # --- SECCIÓN 2: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro de Pacientes")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("No hay pacientes registrados aún en el sistema.")
        else:
            st.subheader(f"Total de registros: {len(pacientes)}")
            
            # Tabla de resumen
            for pac in pacientes:
                p_id, f_reg, f_mod, u_reg = pac
                with st.expander(f"👤 Paciente Folio: **{p_id}** | Última Modificación: {f_mod}"):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.write(f"**Fecha de Registro:** {f_reg}")
                        st.write(f"**Registrado por:** {u_reg}")
                    with c_det2:
                        # Generar PDF Entrevista
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_file = generar_pdf(p_id, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar PDF Entrevista",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_e_{p_id}"
                                )

    # --- SECCIÓN 3: CONTROL DE MEDICAMENTOS Y EXISTENCIAS ---
    elif menu == "💊 Control de Medicamentos y Dosis":
        st.title("💊 Control y Registro de Medicación por Paciente")
        st.caption("Administra la dosificación diaria (mañana, tarde, noche) y control de existencias")
        
        pacientes_list = [p[0] for p in listar_pacientes()]
        
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            paciente_med_id = st.text_input("🔑 Escriba o seleccione el NÚMERO DE PACIENTE / FOLIO", value="").strip()
        with col_m2:
            if pacientes_list:
                selected_pac = st.selectbox("O elija de la lista de pacientes registrados:", ["-- Seleccionar --"] + pacientes_list)
                if selected_pac != "-- Seleccionar --":
                    paciente_med_id = selected_pac

        if paciente_med_id:
            meds_guardados, obs_guardadas, f_reg, f_mod, u_reg = obtener_medicamentos(paciente_med_id)
            if f_mod:
                st.success(f"📌 Esquema cargado para paciente **{paciente_med_id}**. Última modificación: {f_mod} por {u_reg}")
            else:
                st.info(f"🆕 Registrando nuevo esquema de medicamentos para el paciente **{paciente_med_id}**.")

            st.markdown("### Lista de Medicamentos, Dosificación y Stock")
            st.caption("Especifique las dosis por horario y la cantidad actual en existencia para calcular alertas automáticamente.")

            # Estado local para número de renglones de medicamentos
            num_meds_key = f"num_meds_{paciente_med_id}"
            if num_meds_key not in st.session_state:
                st.session_state[num_meds_key] = max(len(meds_guardados), 1)

            col_add1, col_add2 = st.columns([1, 4])
            with col_add1:
                if st.button("➕ Agregar Medicamento"):
                    st.session_state[num_meds_key] += 1
                    st.rerun()

            lista_meds_input = []
            
            with st.form("form_medicamentos"):
                for idx in range(st.session_state[num_meds_key]):
                    m_default = meds_guardados[idx] if idx < len(meds_guardados) else {}
                    
                    st.markdown(f"##### 💊 Medicamento #{idx+1}")
                    cm1, cm2, cm3, cm4, cm5, cm6 = st.columns([2.5, 1, 1, 1, 1.2, 2.3])
                    
                    with cm1:
                        nombre_m = st.text_input("Nombre del Medicamento", value=m_default.get("nombre", ""), key=f"m_nom_{paciente_med_id}_{idx}")
                    with cm2:
                        manana_m = st.number_input("☀️ Mañana", min_value=0.0, step=0.5, value=float(m_default.get("manana", 0)), key=f"m_man_{paciente_med_id}_{idx}")
                    with cm3:
                        tarde_m = st.number_input("🌤️ Tarde", min_value=0.0, step=0.5, value=float(m_default.get("tarde", 0)), key=f"m_tar_{paciente_med_id}_{idx}")
                    with cm4:
                        noche_m = st.number_input("🌙 Noche", min_value=0.0, step=0.5, value=float(m_default.get("noche", 0)), key=f"m_noc_{paciente_med_id}_{idx}")
                    with cm5:
                        existencia_m = st.number_input("📦 Existencia (Unid.)", min_value=0.0, step=1.0, value=float(m_default.get("existencia", 0)), key=f"m_ext_{paciente_med_id}_{idx}")
                    with cm6:
                        indic_m = st.text_input("Indicaciones / Notas", value=m_default.get("indicaciones", ""), key=f"m_ind_{paciente_med_id}_{idx}")

                    dosis_diaria = manana_m + tarde_m + noche_m
                    if nombre_m:
                        if existencia_m < dosis_diaria:
                            st.error(f"⚠️ **ALERTA CRÍTICA**: Existencia ({existencia_m:g}) es menor a la dosis diaria ({dosis_diaria:g}). ¡Falta medicamento para mañana!")
                        elif existencia_m < dosis_diaria * 3:
                            st.warning(f"🟡 **ADVERTENCIA**: Queda poca existencia ({existencia_m:g}). Alcanza solo para {int(existencia_m/dosis_diaria if dosis_diaria>0 else 0)} día(s).")
                        else:
                            st.success(f"🟢 Stock suficiente: {existencia_m:g} unidades (Cubre aprox {int(existencia_m/dosis_diaria if dosis_diaria>0 else 0)} días).")

                    if nombre_m:
                        lista_meds_input.append({
                            "nombre": nombre_m,
                            "manana": manana_m,
                            "tarde": tarde_m,
                            "noche": noche_m,
                            "existencia": existencia_m,
                            "indicaciones": indic_m
                        })
                    st.divider()

                obs_meds = st.text_area("Observaciones Generales de la Medicación (Alergias, indicaciones de resguardo, etc.)", value=obs_guardadas)
                
                btn_guardar_meds = st.form_submit_button("💾 Guardar Esquema y Existencias de Medicamentos", use_container_width=True)
                
                if btn_guardar_meds:
                    guardar_medicamentos(paciente_med_id, lista_meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos y stock guardados para el paciente **{paciente_med_id}**!")

            # Descargar PDF de Medicación
            if meds_guardados:
                st.markdown("#### 🖨️ Exportar Hoja de Medicación")
                pdf_m_file = generar_pdf_medicamentos(paciente_med_id, meds_guardados, obs_guardadas)
                with open(pdf_m_file, "rb") as f:
                    st.download_button(
                        label="📄 Descargar Hoja de Medicación (PDF)",
                        data=f,
                        file_name=f"Medicacion_{paciente_med_id}.pdf",
                        mime="application/pdf"
                    )

    # --- SECCIÓN 4: ALERTAS DE EXISTENCIA Y LISTA DE COMPRAS ---
    elif menu == "🚨 Alertas de Existencia y Compras":
        st.title("🚨 Lista de Compras y Reabastecimiento de Medicamentos")
        st.caption("Monitoreo automático de stock por paciente y generación de lista de reabastecimiento")
        
        todos_meds = listar_todos_medicamentos()
        
        items_compra = []
        sin_stock_critico = []
        stock_preventivo = []
        
        for reg in todos_meds:
            p_id = reg["paciente_id"]
            for m in reg["medicamentos"]:
                nom = m.get("nombre", "")
                if not nom:
                    continue
                man = float(m.get("manana", 0))
                tar = float(m.get("tarde", 0))
                noc = float(m.get("noche", 0))
                ext = float(m.get("existencia", 0))
                dosis_dia = man + tar + noc
                
                if dosis_dia <= 0:
                    continue
                
                # Alerta crítica: existencia no cubre 1 día entero
                if ext < dosis_dia:
                    item = {
                        "paciente_id": p_id,
                        "medicamento": nom,
                        "existencia": ext,
                        "dosis_diaria": dosis_dia,
                        "estatus": "CRÍTICO (Sin dosis para mañana)",
                        "compra_recomendada": max((dosis_dia * 7) - ext, dosis_dia)
                    }
                    sin_stock_critico.append(item)
                    items_compra.append(item)
                elif ext < (dosis_dia * 3):
                    item = {
                        "paciente_id": p_id,
                        "medicamento": nom,
                        "existencia": ext,
                        "dosis_diaria": dosis_dia,
                        "estatus": "PREVENTIVO (< 3 días)",
                        "compra_recomendada": max((dosis_dia * 7) - ext, dosis_dia)
                    }
                    stock_preventivo.append(item)
                    items_compra.append(item)

        col_k1, col_k2 = st.columns(2)
        with col_k1:
            st.metric("🚨 Pacientes con Alerta Crítica (Falta para mañana)", len(sin_stock_critico))
        with col_k2:
            st.metric("🟡 Pacientes con Alerta Preventiva (< 3 días stock)", len(stock_preventivo))

        st.divider()

        if not items_compra:
            st.balloons()
            st.success("🎉 ¡Excelente! Todos los pacientes tienen existencia suficiente de medicamentos para los próximos días.")
        else:
            if sin_stock_critico:
                st.error("### 🔴 PACIENTES A LOS QUE LES FALTA MEDICAMENTO PARA EL DÍA SIGUIENTE")
                st.caption("Requieren compra inmediata de reabastecimiento:")
                
                for item in sin_stock_critico:
                    st.markdown(f"📌 **Paciente Folio:** `{item['paciente_id']}` | **Medicamento:** `{item['medicamento']}`")
                    c_i1, c_i2, c_i3, c_i4 = st.columns(4)
                    c_i1.write(f"**Existencia Actual:** {item['existencia']:g} unid.")
                    c_i2.write(f"**Dosis Diaria:** {item['dosis_diaria']:g} unid.")
                    c_i3.write(f"**Estatus:** 🔴 Insuficiente para mañana")
                    c_i4.write(f"**Sugerencia Compra (7d):** {item['compra_recomendada']:g} unid.")
                    st.divider()

            if stock_preventivo:
                st.warning("### 🟡 PACIENTES EN ALERTA PREVENTIVA (Stock para menos de 3 días)")
                for item in stock_preventivo:
                    st.markdown(f"📌 **Paciente Folio:** `{item['paciente_id']}` | **Medicamento:** `{item['medicamento']}`")
                    c_i1, c_i2, c_i3, c_i4 = st.columns(4)
                    c_i1.write(f"**Existencia Actual:** {item['existencia']:g} unid.")
                    c_i2.write(f"**Dosis Diaria:** {item['dosis_diaria']:g} unid.")
                    c_i3.write(f"**Estatus:** 🟡 Alcanza para {int(item['existencia']/item['dosis_diaria'])} día(s)")
                    c_i4.write(f"**Sugerencia Compra (7d):** {item['compra_recomendada']:g} unid.")
                    st.divider()

            st.markdown("### 🖨️ Exportar Orden / Lista de Compras para Farmacia")
            pdf_compras_file = generar_pdf_lista_compras(items_compra)
            with open(pdf_compras_file, "rb") as f:
                st.download_button(
                    label="📄 Descargar Lista de Compras en PDF",
                    data=f,
                    file_name=f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # --- SECCIÓN 5: SEGURIDAD ---
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

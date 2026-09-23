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
        pac_id, meds_j, obs, f_mod = r
        resultado.append({
            "paciente_id": pac_id,
            "meds": json.loads(meds_j) if meds_j else [],
            "observaciones": obs,
            "fecha_modificacion": f_mod
        })
    return resultado

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(self.epw, 8, "SISTEMA CLINICO DE ATENCION A PACIENTES", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "Evaluacion Medica y Control de Tratamiento", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
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
    return texto

def generar_pdf(paciente_id, datos):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, f"ENTREVISTA INICIAL DE CONSEJERIA", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 7, f"NUMERO DE PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Dependientes economicos: {limpiar_texto(datos.get('dependientes_flag', ''))} - Quienes: {limpiar_texto(datos.get('dependientes_quienes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Tiene pareja: {limpiar_texto(datos.get('pareja_flag', ''))} - Tiempo de relacion: {limpiar_texto(datos.get('pareja_tiempo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
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
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, f"Sustancia de Impacto: {limpiar_texto(datos.get('sustancia_impacto', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, f"Tiempo de consumo excesivo: {limpiar_texto(datos.get('tiempo_excesivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Normalmente consume: {limpiar_texto(datos.get('modo_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "DISPOSICION AL CAMBIO Y ABSTINENCIA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Mayor periodo de abstinencia: {limpiar_texto(datos.get('abst_mayor_tiempo', ''))} | Fecha: {limpiar_texto(datos.get('abst_fecha', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Motivo / Estrategia de abstinencia: {limpiar_texto(datos.get('abst_motivo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Abstinencia ultimos 6 meses: {limpiar_texto(datos.get('abst_6meses', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Importancia actual de dejar de consumir (1-5): {limpiar_texto(datos.get('importancia_cambio', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "SITUACION SOCIAL-FAMILIAR Y RIESGO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Integrantes de la familia con mayor contacto: {limpiar_texto(datos.get('familia_integrantes', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Relaciones sexuales tras consumir: {limpiar_texto(datos.get('relaciones_post_consumo', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 6, f"Involucrado en abuso fisico/sexual por consumo: {limpiar_texto(datos.get('abuso_flag', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, "OBSERVACIONES Y EVALUACION DE LA SESION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(pdf.epw, 5, f"Problemas durante la sesion: {limpiar_texto(datos.get('problemas_sesion', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(pdf.epw, 5, f"Observaciones generales: {limpiar_texto(datos.get('observaciones', ''))}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
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
    pdf.cell(pdf.epw, 7, f"ESQUEMA Y CONTROL DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pdf.epw, 7, f"PACIENTE / FOLIO: {limpiar_texto(paciente_id)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [45, 20, 20, 20, 22, 22, 41]
    headers = ["Medicamento", "Manana", "Tarde", "Noche", "Diaria", "Stock", "Indicaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for m in lista_meds:
        med_nom = limpiar_texto(m.get("nombre", ""))
        m_m = float(m.get("dosis_manana", 0))
        m_t = float(m.get("dosis_tarde", 0))
        m_n = float(m.get("dosis_noche", 0))
        d_diaria = m_m + m_t + m_n
        exis = float(m.get("existencia", 0))
        ind = limpiar_texto(m.get("indicaciones", ""))
        
        pdf.cell(col_w[0], 6, med_nom, border=1)
        pdf.cell(col_w[1], 6, f"{m_m:g}", border=1, align="C")
        pdf.cell(col_w[2], 6, f"{m_t:g}", border=1, align="C")
        pdf.cell(col_w[3], 6, f"{m_n:g}", border=1, align="C")
        pdf.cell(col_w[4], 6, f"{d_diaria:g}", border=1, align="C")
        pdf.cell(col_w[5], 6, f"{exis:g}", border=1, align="C")
        pdf.cell(col_w[6], 6, ind, border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(6)
    if observaciones:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6, "Observaciones de Medicacion:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(pdf.epw, 5, limpiar_texto(observaciones), new_x="LMARGIN", new_y="NEXT")
        
    pdf_filename = f"Medicacion_Paciente_{paciente_id}.pdf"
    pdf.output(pdf_filename)
    return pdf_filename

def generar_pdf_compras(lista_compras):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, f"REPORTE DE COMPRAS Y REABASTECIMIENTO DE MEDICAMENTOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 9)
    col_w = [30, 50, 25, 25, 30, 30]
    headers = ["Folio Paciente", "Medicamento", "Stock Act.", "Dosis Diaria", "Cobertura", "Estatus"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_compras:
        pdf.cell(col_w[0], 6, limpiar_texto(item['paciente_id']), border=1, align="C")
        pdf.cell(col_w[1], 6, limpiar_texto(item['medicamento']), border=1)
        pdf.cell(col_w[2], 6, f"{item['existencia']:g}", border=1, align="C")
        pdf.cell(col_w[3], 6, f"{item['dosis_diaria']:g}", border=1, align="C")
        pdf.cell(col_w[4], 6, f"{item['dias_cobertura']:.1f} dias", border=1, align="C")
        pdf.cell(col_w[5], 6, limpiar_texto(item['nivel']), border=1, new_x="LMARGIN", new_y="NEXT")
        
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
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Consejería y Control Médico</h2>", unsafe_allow_html=True)
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
    st.sidebar.title("📋 Menú Principal")
    st.sidebar.write(f"👤 **Usuario**: {st.session_state['nombre_completo']}")
    
    menu = st.sidebar.radio(
        "Navegación",
        [
            "📝 Nueva Entrevista / Editar",
            "💊 Control de Medicamentos",
            "🚨 Alertas de Inventario y Compras",
            "🔍 Buscar y Listar Pacientes",
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
                    modo_consumo = st.selectbox("Normalmente consume:", ["SOLO", "ACOMPAÑADO", "AMBOS"],
                                               index=["SOLO", "ACOMPAÑADO", "AMBOS"].index(datos_existentes.get("modo_consumo", "SOLO")) if datos_existentes.get("modo_consumo") in ["SOLO", "ACOMPAÑADO", "AMBOS"] else 0)

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

            with tab5:
                st.subheader("Evaluación Clínica y Cierre")
                problemas_sesion = st.text_area("Problemas presentados durante la sesión (comunicación, actitud, ideas, comportamiento, ánimo)", value=datos_existentes.get("problemas_sesion", ""))
                observaciones = st.text_area("Observaciones Generales", value=datos_existentes.get("observaciones", ""))
                
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    evaluador_nombre = st.text_input("Nombre de quien aplica la entrevista", value=datos_existentes.get("evaluador_nombre", st.session_state["nombre_completo"]))
                with c_f2:
                    evaluador_cargo = st.text_input("Cargo del evaluador", value=datos_existentes.get("evaluador_cargo", "Consejero / Evaluador Clínico"))

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

    # --- SECCIÓN 2: CONTROL DE MEDICAMENTOS Y DOSIS ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Control de Medicamentos y Dosis por Paciente")
        st.caption("Administración de medicamentos, horarios, dosis diarias e inventario de existencias")
        
        pacientes_registrados = [p[0] for p in listar_pacientes()]
        
        col_med1, col_med2 = st.columns([2, 1])
        with col_med1:
            paciente_med_id = st.text_input("🔑 NÚMERO DE PACIENTE / FOLIO *", value="").strip()
        with col_med2:
            if pacientes_registrados:
                pac_sel = st.selectbox("O Seleccionar Paciente Existente:", ["-- Seleccionar --"] + pacientes_registrados)
                if pac_sel != "-- Seleccionar --":
                    paciente_med_id = pac_sel

        if paciente_med_id:
            meds_cargados, obs_cargadas, f_reg_m, f_mod_m, u_reg_m = obtener_medicamentos(paciente_med_id)
            if f_reg_m:
                st.success(f"📌 Esquema de medicación cargado. Última modificación: {f_mod_m} por {u_reg_m}")
            else:
                st.info("🆕 Folio sin esquema previo. Complete los datos de medicación a continuación.")

            if "num_meds" not in st.session_state:
                st.session_state["num_meds"] = max(len(meds_cargados), 1)

            st.subheader("Tratamiento Prescrito")
            
            with st.form("form_medicamentos"):
                meds_input = []
                
                # Iterar medicamentos
                for i in range(st.session_state["num_meds"]):
                    m_prev = meds_cargados[i] if i < len(meds_cargados) else {}
                    
                    st.markdown(f"##### 💊 Medicamento #{i+1}")
                    cm1, cm2, cm3, cm4, cm5 = st.columns([2.5, 1, 1, 1, 1.5])
                    
                    with cm1:
                        nom_m = st.text_input("Nombre / Presentación", value=m_prev.get("nombre", ""), key=f"med_nom_{i}")
                    with cm2:
                        d_man = st.number_input("☀️ Mañana", min_value=0.0, value=float(m_prev.get("dosis_manana", 0)), step=0.5, key=f"med_man_{i}")
                    with cm3:
                        d_tar = st.number_input("🌤️ Tarde", min_value=0.0, value=float(m_prev.get("dosis_tarde", 0)), step=0.5, key=f"med_tar_{i}")
                    with cm4:
                        d_noc = st.number_input("🌙 Noche", min_value=0.0, value=float(m_prev.get("dosis_noche", 0)), step=0.5, key=f"med_noc_{i}")
                    with cm5:
                        exis_m = st.number_input("📦 Existencia (Stock)", min_value=0.0, value=float(m_prev.get("existencia", 0)), step=1.0, key=f"med_exis_{i}")
                        
                    ind_m = st.text_input("Indicaciones (ej. con alimentos)", value=m_prev.get("indicaciones", ""), key=f"med_ind_{i}")
                    
                    d_diaria = d_man + d_tar + d_noc
                    if nom_m:
                        if d_diaria > 0:
                            dias_cobertura = exis_m / d_diaria
                            if exis_m < d_diaria:
                                st.error(f"🔴 **ALERTA CRÍTICA**: Existencia insuficiente para el siguiente día (Dosis diaria: {d_diaria:g} | Stock: {exis_m:g})")
                            elif dias_cobertura < 3:
                                st.warning(f"🟡 **ADVERTENCIA**: Queda stock para solo {dias_cobertura:.1f} días. Se requiere comprar pronto.")
                            else:
                                st.success(f"🟢 **Stock Suficiente**: Cobertura estimada para {dias_cobertura:.1f} días.")
                        else:
                            st.caption("Dosis diaria registrada en 0.")
                            
                    st.divider()

                    if nom_m:
                        meds_input.append({
                            "nombre": nom_m,
                            "dosis_manana": d_man,
                            "dosis_tarde": d_tar,
                            "dosis_noche": d_noc,
                            "existencia": exis_m,
                            "indicaciones": ind_m
                        })

                obs_meds = st.text_area("Observaciones de Medicación / Alergias", value=obs_cargadas)
                
                guardar_meds_btn = st.form_submit_button("💾 Guardar Esquema de Medicamentos e Inventario", use_container_width=True)
                
                if guardar_meds_btn:
                    guardar_medicamentos(paciente_med_id, meds_input, obs_meds, st.session_state["username"])
                    st.success(f"✅ ¡Esquema de medicamentos guardado exitosamente para el folio {paciente_med_id}!")
                    st.rerun()

            c_btn1, c_btn2 = st.columns(2)
            with c_btn1:
                if st.button("➕ Agregar otro medicamento"):
                    st.session_state["num_meds"] += 1
                    st.rerun()
            with c_btn2:
                if meds_cargados:
                    pdf_m = generar_pdf_medicamentos(paciente_med_id, meds_cargados, obs_cargadas)
                    with open(pdf_m, "rb") as f:
                        st.download_button(
                            label="🖨️ Descargar Hoja de Medicación (PDF)",
                            data=f,
                            file_name=f"Medicacion_{paciente_med_id}.pdf",
                            mime="application/pdf"
                        )

    # --- SECCIÓN 3: ALERTAS DE INVENTARIO Y COMPRAS ---
    elif menu == "🚨 Alertas de Inventario y Compras":
        st.title("🚨 Alertas de Existencias y Lista de Compras")
        st.caption("Consolidado de medicamentos con stock bajo o insuficiente para la dosis del siguiente día")
        
        todos_meds = listar_todos_medicamentos()
        
        lista_criticos = []
        lista_preventivos = []
        
        for reg in todos_meds:
            p_id = reg["paciente_id"]
            for m in reg["meds"]:
                d_m = float(m.get("dosis_manana", 0))
                d_t = float(m.get("dosis_tarde", 0))
                d_n = float(m.get("dosis_noche", 0))
                d_diaria = d_m + d_t + d_n
                exis = float(m.get("existencia", 0))
                
                if d_diaria > 0:
                    dias_cob = exis / d_diaria
                    item_data = {
                        "paciente_id": p_id,
                        "medicamento": m.get("nombre", ""),
                        "existencia": exis,
                        "dosis_diaria": d_diaria,
                        "dias_cobertura": dias_cob
                    }
                    if exis < d_diaria:
                        item_data["nivel"] = "CRÍTICO (<1 DÍA)"
                        lista_criticos.append(item_data)
                    elif dias_cob < 3:
                        item_data["nivel"] = "PREVENTIVO (<3 DÍAS)"
                        lista_preventivos.append(item_data)

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("🔴 Alertas Críticas (<1 día)", len(lista_criticos))
        col_m2.metric("🟡 Alertas Preventivas (<3 días)", len(lista_preventivos))
        col_m3.metric("📋 Total a Reabastecer", len(lista_criticos) + len(lista_preventivos))
        
        st.divider()
        
        total_compras = lista_criticos + lista_preventivos
        
        if not total_compras:
            st.success("🎉 ¡Excelente! Todos los pacientes cuentan con existencia suficiente para más de 3 días de tratamiento.")
        else:
            st.subheader("🛒 Lista de Personas y Medicamentos a Comprar")
            
            for item in total_compras:
                icono = "🔴" if "CRÍTICO" in item["nivel"] else "🟡"
                st.markdown(f"### {icono} Paciente / Folio: **{item['paciente_id']}**")
                c_a, c_b, c_c, c_d = st.columns(4)
                c_a.write(f"**Medicamento:** {item['medicamento']}")
                c_b.write(f"**Existencia Actual:** {item['existencia']:g}")
                c_c.write(f"**Dosis Diaria:** {item['dosis_diaria']:g}")
                c_d.write(f"**Cobertura:** {item['dias_cobertura']:.1f} días")
                st.divider()
                
            pdf_compras = generar_pdf_compras(total_compras)
            with open(pdf_compras, "rb") as f:
                st.download_button(
                    label="🖨️ Descargar Lista de Compras en PDF",
                    data=f,
                    file_name=f"Lista_Compras_Medicamentos_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # --- SECCIÓN 4: BUSCAR Y LISTAR PACIENTES ---
    elif menu == "🔍 Buscar y Listar Pacientes":
        st.title("🔍 Registro General de Pacientes")
        
        pacientes = listar_pacientes()
        if not pacientes:
            st.warning("No hay pacientes registrados aún en el sistema.")
        else:
            st.subheader(f"Total de registros: {len(pacientes)}")
            
            for pac in pacientes:
                p_id, f_reg, f_mod, u_reg = pac
                with st.expander(f"👤 Paciente Folio: **{p_id}** | Última Modificación: {f_mod}"):
                    c_det1, c_det2 = st.columns([2, 1])
                    with c_det1:
                        st.write(f"**Fecha de Registro:** {f_reg}")
                        st.write(f"**Registrado por:** {u_reg}")
                    with c_det2:
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_file = generar_pdf(p_id, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_ent_{p_id}"
                                )
                        
                        meds_p, obs_p, f_reg_m, _, _ = obtener_medicamentos(p_id)
                        if meds_p:
                            pdf_m_file = generar_pdf_medicamentos(p_id, meds_p, obs_p)
                            with open(pdf_m_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Medicación (PDF)",
                                    data=f,
                                    file_name=f"Medicacion_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_med_{p_id}"
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

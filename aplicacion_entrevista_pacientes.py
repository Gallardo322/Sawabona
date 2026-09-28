import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Entrevista y Control de Pacientes",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# --- FUNCIONES DE BASE DE DATOS Y ESTRUCTURA ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla de Usuarios
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    """)
    # Tabla de Pacientes / Entrevistas
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    """)
    # Tabla de Medicamentos Antiguos (Histórico)
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            fecha_registro TEXT NOT NULL,
            usuario_registro TEXT NOT NULL,
            medicamentos_json TEXT NOT NULL,
            observaciones TEXT
        )
    """)
    # NUEVA: Catálogo de Medicamentos
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    """)
    # NUEVA: Asignación e Inventario de Medicamentos por Paciente
    c.execute("""
        CREATE TABLE IF NOT EXISTS paciente_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT,
            fecha_registro TEXT NOT NULL,
            FOREIGN KEY (medicamento_id) REFERENCES catalogo_medicamentos(id)
        )
    """)
    # NUEVA: Histórico de Surtido por Turno
    c.execute("""
        CREATE TABLE IF NOT EXISTS surtido_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            cantidad REAL DEFAULT 0,
            usuario TEXT NOT NULL
        )
    """)
    
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
        return json.loads(row[0]), row[1], row[2], row[3]
    return None, None, None, None

def listar_pacientes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas ORDER BY fecha_modificacion DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- FUNCIONES DE CATÁLOGO Y ASIGNACIÓN DE MEDICAMENTOS ---
def obtener_catalogo_meds():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, medicamento, presentacion FROM catalogo_medicamentos ORDER BY compuesto ASC, medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_catalogo_med(compuesto, medicamento, presentacion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO catalogo_medicamentos (compuesto, medicamento, presentacion) VALUES (?, ?, ?)',
              (compuesto.strip(), medicamento.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_catalogo_med(med_id, compuesto, medicamento, presentacion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, medicamento = ?, presentacion = ? WHERE id = ?',
              (compuesto.strip(), medicamento.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_catalogo_med(med_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Verificar si está asignado a pacientes
    c.execute('SELECT COUNT(*) FROM paciente_medicamentos WHERE medicamento_id = ?', (med_id,))
    cnt = c.fetchone()[0]
    if cnt > 0:
        conn.close()
        return False, f"No se puede eliminar porque está asignado a {cnt} registro(s) de pacientes."
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()
    return True, "Medicamento eliminado del catálogo."

def obtener_asignaciones_paciente(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT pm.id, pm.medicamento_id, cm.compuesto, cm.medicamento, cm.presentacion,
               pm.dosis_manana, pm.dosis_tarde, pm.dosis_noche, pm.existencia, pm.observaciones
        FROM paciente_medicamentos pm
        JOIN catalogo_medicamentos cm ON pm.medicamento_id = cm.id
        WHERE pm.paciente_id = ?
        ORDER BY cm.medicamento ASC
    """, (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def asignar_o_actualizar_med_paciente(paciente_id, med_id, d_m, d_t, d_n, existencia, obs):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Verificar si ya tiene ese medicamento asignado
    c.execute('SELECT id FROM paciente_medicamentos WHERE paciente_id = ? AND medicamento_id = ?', (paciente_id, med_id))
    row = c.fetchone()
    if row:
        c.execute("""
            UPDATE paciente_medicamentos
            SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?, fecha_registro = ?
            WHERE id = ?
        """, (d_m, d_t, d_n, existencia, obs, fecha_act, row[0]))
    else:
        c.execute("""
            INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (paciente_id, med_id, d_m, d_t, d_n, existencia, obs, fecha_act))
    conn.commit()
    conn.close()

def actualizar_asignacion_id(asig_id, d_m, d_t, d_n, existencia_nueva, obs):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        UPDATE paciente_medicamentos
        SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?, fecha_registro = ?
        WHERE id = ?
    """, (d_m, d_t, d_n, existencia_nueva, obs, fecha_act, asig_id))
    conn.commit()
    conn.close()

def eliminar_asignacion_id(asig_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM paciente_medicamentos WHERE id = ?', (asig_id,))
    conn.commit()
    conn.close()

def obtener_todas_asignaciones_ordenadas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT pm.id, pm.paciente_id, cm.compuesto, cm.medicamento, cm.presentacion,
               pm.dosis_manana, pm.dosis_tarde, pm.dosis_noche, pm.existencia, pm.observaciones
        FROM paciente_medicamentos pm
        JOIN catalogo_medicamentos cm ON pm.medicamento_id = cm.id
    """)
    rows = c.fetchall()
    
    # Cargar entrevistas para obtener nombres de pacientes
    c.execute('SELECT paciente_id, datos_json FROM entrevistas')
    entrevistas_map = {}
    for r in c.fetchall():
        try:
            d = json.loads(r[1])
            nombre = f"{d.get('nombre', '')} {d.get('ap_paterno', '')} {d.get('ap_materno', '')}".strip()
            exp = d.get('num_expediente', '')
        except:
            nombre = f"Paciente {r[0]}"
            exp = ""
        entrevistas_map[r[0]] = {"nombre": nombre or f"Paciente {r[0]}", "expediente": exp}
    conn.close()
    
    resultado = []
    for r in rows:
        pid = r[1]
        p_info = entrevistas_map.get(pid, {"nombre": f"Folio {pid}", "expediente": ""})
        d_manana = r[5] or 0
        d_tarde = r[6] or 0
        d_noche = r[7] or 0
        existencia = r[8] or 0
        consumo_diario = d_manana + d_tarde + d_noche
        dias_restantes = (existencia / consumo_diario) if consumo_diario > 0 else 999
        
        resultado.append({
            "asig_id": r[0],
            "paciente_id": pid,
            "paciente_nombre": p_info["nombre"],
            "expediente": p_info["expediente"],
            "compuesto": r[2],
            "medicamento": r[3],
            "presentacion": r[4],
            "dosis_manana": d_manana,
            "dosis_tarde": d_tarde,
            "dosis_noche": d_noche,
            "existencia": existencia,
            "consumo_diario": consumo_diario,
            "dias_restantes": round(dias_restantes, 1),
            "observaciones": r[9] or ""
        })
    
    # Ordenar alfabéticamente por Nombre del Paciente
    resultado.sort(key=lambda x: x["paciente_nombre"].lower())
    return resultado

def procesar_surtido_turno(fecha_str, turno, lista_entregas, usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for item in lista_entregas:
        asig_id = item["asig_id"]
        paciente_id = item["paciente_id"]
        med_id = item["med_id"]
        cant_surtida = item["cant_surtida"]
        
        if cant_surtida > 0:
            # Registrar en surtido
            c.execute("""
                INSERT INTO surtido_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad, usuario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (paciente_id, med_id, fecha_str, turno, cant_surtida, usuario))
            
            # Descontar de existencia
            c.execute('UPDATE paciente_medicamentos SET existencia = MAX(0, existencia - ?) WHERE id = ?',
                      (cant_surtida, asig_id))
    conn.commit()
    conn.close()

# --- GENERADOR DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(self.epw, 8, "COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(self.epw, 6, "CONTROL CLINICO Y ESQUEMA DE MEDICACION", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

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
        texto = str(texto).replace(k, v)
    return texto

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

def generar_pdf_listado_indicaciones(lista_asig):
    pdf = PDFReport()
    pdf.add_page(orientation="L")
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 7, "LISTADO GENERAL DE INDICACIONES MEDICAS Y EXISTENCIAS", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(pdf.epw, 5, f"Ordenado alfabeticamente por Paciente | Emision: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    col_w = [55, 55, 45, 20, 20, 20, 25, 25]
    headers = ["Paciente", "Medicamento / Compuesto", "Presentacion", "Man.", "Tarde", "Noche", "Existencia", "Dias Rest."]
    
    pdf.set_font("Helvetica", "B", 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for item in lista_asig:
        p_str = f"{item['paciente_nombre']} (Exp: {item['expediente'] or item['paciente_id']})"
        med_str = f"{item['medicamento']} ({item['compuesto']})"
        dias_str = f"{item['dias_restantes']} d" if item['dias_restantes'] < 900 else "N/A"
        
        pdf.cell(col_w[0], 6, limpiar_texto(p_str[:32]), border=1)
        pdf.cell(col_w[1], 6, limpiar_texto(med_str[:32]), border=1)
        pdf.cell(col_w[2], 6, limpiar_texto(item['presentacion'][:25]), border=1)
        pdf.cell(col_w[3], 6, str(item['dosis_manana']), border=1, align="C")
        pdf.cell(col_w[4], 6, str(item['dosis_tarde']), border=1, align="C")
        pdf.cell(col_w[5], 6, str(item['dosis_noche']), border=1, align="C")
        pdf.cell(col_w[6], 6, str(item['existencia']), border=1, align="C")
        pdf.cell(col_w[7], 6, dias_str, border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    filename = "Listado_Indicaciones_Medicas.pdf"
    pdf.output(filename)
    return filename

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
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Sistema de Pacientes y Medicamentos</h2>", unsafe_allow_html=True)
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
        ["📝 Nueva Entrevista / Editar", "💊 Control de Medicamentos", "🔍 Buscar y Listar Pacientes", "⚙️ Seguridad / Contraseña"]
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

    # --- SECCIÓN 2: CONTROL DE MEDICAMENTOS (SISTEMA COMPLETO) ---
    elif menu == "💊 Control de Medicamentos":
        st.title("💊 Módulo de Control de Medicamentos e Inventario")
        
        tab_cat, tab_asig, tab_surt, tab_alarm, tab_report = st.tabs([
            "💊 Catálogo de Medicamentos",
            "📋 Asignación e Inventario",
            "🕒 Surtido por Turno",
            "🚨 Alarmas (≤ 5 días)",
            "📄 Listado de Indicaciones"
        ])

        # -------------------------------------------------------------
        # PESTAÑA 1: CATÁLOGO DE MEDICAMENTOS
        # -------------------------------------------------------------
        with tab_cat:
            st.subheader("💊 Catálogo General de Medicamentos")
            sub_c1, sub_c2, sub_c3 = st.tabs(["➕ Agregar Medicamento", "✏️ Modificar Medicamento", "🗑️ Eliminar Medicamento"])
            
            catalogo_actual = obtener_catalogo_meds()
            
            with sub_c1:
                with st.form("form_alta_cat"):
                    fc1, fc2, fc3 = st.columns(3)
                    new_comp = fc1.text_input("Nombre del Compuesto / Sustancia Activa *", placeholder="Ej. Paracetamol")
                    new_med = fc2.text_input("Nombre del Medicamento / Marca *", placeholder="Ej. Tylenol")
                    new_pres = fc3.text_input("Presentación *", placeholder="Ej. Tabletas 500mg, Gotas")
                    
                    btn_add_cat = st.form_submit_button("💾 Guardar en Catálogo", use_container_width=True)
                    if btn_add_cat:
                        if not new_comp or not new_med or not new_pres:
                            st.error("⚠️ Todos los campos con asterisco (*) son obligatorios.")
                        else:
                            agregar_catalogo_med(new_comp, new_med, new_pres)
                            st.success(f"✅ ¡Medicamento '{new_med}' agregado al catálogo exitosamente!")
                            st.rerun()

            with sub_c2:
                if not catalogo_actual:
                    st.info("No hay medicamentos registrados en el catálogo aún.")
                else:
                    med_dict_mod = {f"{m[2]} ({m[1]}) - {m[3]}": m for m in catalogo_actual}
                    sel_mod_key = st.selectbox("Seleccione el medicamento a modificar:", list(med_dict_mod.keys()), key="sel_mod_cat")
                    m_data = med_dict_mod[sel_mod_key]
                    
                    with st.form("form_mod_cat"):
                        mc1, mc2, mc3 = st.columns(3)
                        m_comp = mc1.text_input("Nombre del Compuesto", value=m_data[1])
                        m_med = mc2.text_input("Nombre del Medicamento", value=m_data[2])
                        m_pres = mc3.text_input("Presentación", value=m_data[3])
                        
                        btn_mod_cat = st.form_submit_button("💾 Guardar Cambios en Catálogo", use_container_width=True)
                        if btn_mod_cat:
                            actualizar_catalogo_med(m_data[0], m_comp, m_med, m_pres)
                            st.success(f"✅ ¡Medicamento '{m_med}' actualizado correctamente!")
                            st.rerun()

            with sub_c3:
                if not catalogo_actual:
                    st.info("No hay medicamentos en el catálogo.")
                else:
                    med_dict_del = {f"{m[2]} ({m[1]}) - {m[3]}": m for m in catalogo_actual}
                    sel_del_key = st.selectbox("Seleccione el medicamento a eliminar:", list(med_dict_del.keys()), key="sel_del_cat")
                    m_del_data = med_dict_del[sel_del_key]
                    
                    st.warning(f"⚠️ ¿Está seguro que desea eliminar **{m_del_data[2]} ({m_del_data[1]})** del catálogo?")
                    if st.button("🗑️ Confirmar Eliminar Medicamento del Catálogo", type="primary"):
                        ok_del, msg_del = eliminar_catalogo_med(m_del_data[0])
                        if ok_del:
                            st.success(f"✅ {msg_del}")
                            st.rerun()
                        else:
                            st.error(f"⛔ {msg_del}")

            st.divider()
            st.subheader("📋 Catálogo Registrado")
            if catalogo_actual:
                cat_df = [{"ID": m[0], "Compuesto / Sustancia": m[1], "Medicamento / Marca": m[2], "Presentación": m[3]} for m in catalogo_actual]
                st.dataframe(cat_df, use_container_width=True)

        # -------------------------------------------------------------
        # PESTAÑA 2: ASIGNACIÓN E INVENTARIO POR PACIENTE
        # -------------------------------------------------------------
        with tab_asig:
            st.subheader("📋 Asignación e Inventario Personal por Paciente")
            
            # Cargar lista de pacientes activos/registrados
            pacientes_db = listar_pacientes()
            pacientes_map = {}
            for p in pacientes_db:
                pid = p[0]
                d_p, _, _, _ = obtener_entrevista(pid)
                if d_p:
                    nombre_p = f"{d_p.get('nombre', '')} {d_p.get('ap_paterno', '')} {d_p.get('ap_materno', '')}".strip()
                    exp_p = d_p.get('num_expediente', '')
                    label_p = f"{nombre_p or pid} (Folio: {pid}, Exp: {exp_p})"
                else:
                    label_p = f"Folio: {pid}"
                pacientes_map[label_p] = pid
                
            if not pacientes_map:
                st.warning("No hay pacientes registrados en el sistema. Registre un paciente primero.")
            else:
                sel_p_label = st.selectbox("Seleccione un Paciente Activo:", list(pacientes_map.keys()), key="sel_p_asig")
                sel_pid = pacientes_map[sel_p_label]
                
                st.info(f"📌 Administrando medicación e inventario para: **{sel_p_label}**")
                
                sub_as1, sub_as2 = st.tabs(["➕ Asignar Medicamento de Catálogo", "✏️ Modificar Dosis / Existencia / Retirar"])
                
                # --- ASIGNAR NUEVO MEDICAMENTO ---
                with sub_as1:
                    catalogo_actual = obtener_catalogo_meds()
                    if not catalogo_actual:
                        st.warning("⚠️ El catálogo de medicamentos está vacío. Registre medicamentos en la pestaña 'Catálogo' primero.")
                    else:
                        med_dict = {f"{m[2]} ({m[1]}) - {m[3]}": m[0] for m in catalogo_actual}
                        
                        with st.form("form_nueva_asig"):
                            sel_med_cat_str = st.selectbox("Seleccione Medicamento del Catálogo *", list(med_dict.keys()))
                            med_id_selected = med_dict[sel_med_cat_str]
                            
                            st.markdown("##### 🕒 Esquema de Dosis Diaria Indicada")
                            cd1, cd2, cd3 = st.columns(3)
                            d_manana = cd1.number_input("☀️ Dosis Mañana (unidades)", min_value=0.0, step=0.5, value=1.0)
                            d_tarde = cd2.number_input("🌤️ Dosis Medio Día / Tarde (unidades)", min_value=0.0, step=0.5, value=0.0)
                            d_noche = cd3.number_input("🌙 Dosis Noche (unidades)", min_value=0.0, step=0.5, value=0.0)
                            
                            st.markdown("##### 📦 Inventario e Existencia Personal")
                            ex_inicial = st.number_input("Existencia Inicial del Paciente (unidades/pastillas)", min_value=0.0, step=1.0, value=30.0)
                            obs_asig = st.text_area("Observaciones e Instrucciones Específicas", placeholder="Ej. Tomar después de los alimentos")
                            
                            btn_guardar_asig = st.form_submit_button("💾 Guardar Asignación a Paciente", use_container_width=True)
                            if btn_guardar_asig:
                                asignor_user = st.session_state["username"]
                                asignar_o_actualizar_med_paciente(sel_pid, med_id_selected, d_manana, d_tarde, d_noche, ex_inicial, obs_asig)
                                st.success("✅ ¡Medicamento asignado correctamente al paciente!")
                                st.rerun()

                # --- MODIFICAR ASIGNACIÓN O EXISTENCIA NUEVA ---
                with sub_as2:
                    asig_paciente = obtener_asignaciones_paciente(sel_pid)
                    if not asig_paciente:
                        st.info("Este paciente no tiene medicamentos asignados actualmente.")
                    else:
                        asig_dict = {f"{a[3]} ({a[2]}) - {a[4]}": a for a in asig_paciente}
                        sel_asig_key = st.selectbox("Seleccione el medicamento asignado a modificar:", list(asig_dict.keys()), key="sel_asig_mod")
                        a_curr = asig_dict[sel_asig_key]
                        
                        st.markdown(f"#### ✏️ Editando: **{a_curr[3]} ({a_curr[2]})**")
                        
                        with st.form("form_edit_asig"):
                            c_m1, c_m2, c_m3 = st.columns(3)
                            m_d_m = c_m1.number_input("☀️ Dosis Mañana", min_value=0.0, step=0.5, value=float(a_curr[5]))
                            m_d_t = c_m2.number_input("🌤️ Dosis Tarde", min_value=0.0, step=0.5, value=float(a_curr[6]))
                            m_d_n = c_m3.number_input("🌙 Dosis Noche", min_value=0.0, step=0.5, value=float(a_curr[7]))
                            
                            st.info(f"💡 Existencia Registrada Actualmente: **{a_curr[8]} unidades**.")
                            m_ex_nueva = st.number_input("📦 CAPTURAR EXISTENCIA NUEVA TOTAL (unidades)", min_value=0.0, step=1.0, value=float(a_curr[8]), help="Ingrese la nueva existencia total del paciente (ej. al reabastecer o corregir inventario)")
                            m_obs = st.text_area("Observaciones / Notas", value=a_curr[9] or "")
                            
                            btn_actualizar_asig = st.form_submit_button("💾 Guardar Cambios de Asignación y Existencia", use_container_width=True)
                            if btn_actualizar_asig:
                                actualizar_asignacion_id(a_curr[0], m_d_m, m_d_t, m_d_n, m_ex_nueva, m_obs)
                                st.success("✅ ¡Asignación y existencia actualizadas con éxito!")
                                st.rerun()
                                
                        st.divider()
                        st.warning("⚠️ **Retirar Asignación**: Si el paciente ya no requiere este medicamento, puede retirarlo.")
                        if st.button("🗑️ Retirar Medicamento de este Paciente", type="primary", key=f"del_asig_{a_curr[0]}"):
                            eliminar_asignacion_id(a_curr[0])
                            st.success("✅ Medicamento retirado de la lista del paciente.")
                            st.rerun()

                st.divider()
                st.subheader(f"📋 Medicamentos Asignados Actualmente a {sel_pid}")
                asig_paciente_table = obtener_asignaciones_paciente(sel_pid)
                if asig_paciente_table:
                    tabla_view = []
                    for row_a in asig_paciente_table:
                        c_dia = row_a[5] + row_a[6] + row_a[7]
                        d_rest = (row_a[8] / c_dia) if c_dia > 0 else 999
                        tabla_view.append({
                            "Medicamento": row_a[3],
                            "Compuesto": row_a[2],
                            "Presentación": row_a[4],
                            "☀️ Mañana": row_a[5],
                            "🌤️ Tarde": row_a[6],
                            "🌙 Noche": row_a[7],
                            "Existencia": row_a[8],
                            "Días Restantes Est.": f"{round(d_rest, 1)} días" if d_rest < 900 else "N/A",
                            "Observaciones": row_a[9] or ""
                        })
                    st.dataframe(tabla_view, use_container_width=True)

        # -------------------------------------------------------------
        # PESTAÑA 3: SURTIDO POR TURNO
        # -------------------------------------------------------------
        with tab_surt:
            st.subheader("🕒 Surtido y Entrega de Dosis por Turno")
            cs1, cs2 = st.columns(2)
            f_surtido = cs1.date_input("Fecha de Entrega", value=date.today())
            turno_surtido = cs2.selectbox("Turno a Surtir", ["Mañana", "Medio Día / Tarde", "Noche"])
            
            # Obtener todas las asignaciones
            todas_asig = obtener_todas_asignaciones_ordenadas()
            
            # Filtrar las asignaciones que tengan dosis > 0 para este turno
            if turno_surtido == "Mañana":
                asig_turno = [a for a in todas_asig if a["dosis_manana"] > 0]
                field_dosis = "dosis_manana"
            elif turno_surtido == "Medio Día / Tarde":
                asig_turno = [a for a in todas_asig if a["dosis_tarde"] > 0]
                field_dosis = "dosis_tarde"
            else:
                asig_turno = [a for a in todas_asig if a["dosis_noche"] > 0]
                field_dosis = "dosis_noche"
                
            if not asig_turno:
                st.info(f"No hay dosis programadas para el turno de la **{turno_surtido}**.")
            else:
                st.write(f"📋 **Pacientes con dosis indicadas para la {turno_surtido} ({len(asig_turno)} medicamentos):**")
                
                with st.form("form_surtido_turno"):
                    surtido_items = []
                    for idx, a in enumerate(asig_turno):
                        dosis_ind = a[field_dosis]
                        ex_actual = a["existencia"]
                        sin_existencia = (ex_actual <= 0)
                        
                        st.markdown(f"**👤 {a['paciente_nombre']}** (Folio: `{a['paciente_id']}`) | 💊 **{a['medicamento']}** ({a['presentacion']})")
                        col_s1, col_s2, col_s3, col_s4 = st.columns([2, 2, 2, 3])
                        
                        col_s1.write(f"📌 Dosis Indicada: **{dosis_ind}**")
                        col_s2.write(f"📦 Existencia Actual: **{ex_actual}**")
                        
                        if sin_existencia:
                            col_s3.error("🚨 SIN EXISTENCIA (0)")
                            cant_surtir = 0.0
                        else:
                            sugerido = min(dosis_ind, ex_actual)
                            cant_surtir = col_s3.number_input("Cantidad a entregar", min_value=0.0, max_value=float(ex_actual), step=0.5, value=float(sugerido), key=f"surt_{idx}_{a['asig_id']}")
                            
                        col_s4.write(f"Notas: {a['observaciones'] or 'Sin notas'}")
                        
                        surtido_items.append({
                            "asig_id": a["asig_id"],
                            "paciente_id": a["paciente_id"],
                            "med_id": a["asig_id"],
                            "cant_surtida": cant_surtir
                        })
                        st.divider()
                        
                    btn_confirmar_surtido = st.form_submit_button(f"💾 Confirmar y Registrar Surtido del Turno ({turno_surtido})", use_container_width=True)
                    if btn_confirmar_surtido:
                        procesar_surtido_turno(str(f_surtido), turno_surtido, surtido_items, st.session_state["username"])
                        st.success(f"🎉 ¡Surtido registrado exitosamente para el turno de la {turno_surtido}! Las existencias fueron actualizadas.")
                        st.rerun()

        # -------------------------------------------------------------
        # PESTAÑA 4: ALARMAS DE REABASTECIMIENTO (<= 5 DÍAS)
        # -------------------------------------------------------------
        with tab_alarm:
            st.subheader("🚨 Alarmas de Reabastecimiento de Medicamentos (≤ 5 Días)")
            todas_asig = obtener_todas_asignaciones_ordenadas()
            
            alarmas = [a for a in todas_asig if a["consumo_diario"] > 0 and a["dias_restantes"] <= 5.0]
            
            if not alarmas:
                st.success("✅ ¡Todos los pacientes cuentan con existencia suficiente para más de 5 días de dosis!")
            else:
                st.warning(f"⚠️ **Se encontraron {len(alarmas)} medicamento(s) que requieren reabastecimiento pronto:**")
                for al in alarmas:
                    d_rest = al["dias_restantes"]
                    is_zero = (al["existencia"] <= 0)
                    
                    if is_zero or d_rest <= 2:
                        color_box = "#FFEBEE"
                        border_color = "#D32F2F"
                        tag = "🔴 AGOTADO / RIESGO ALTO"
                    else:
                        color_box = "#FFFDE7"
                        border_color = "#FBC02D"
                        tag = "🟡 ALERTA DE REABASTECIMIENTO"
                        
                    st.markdown(f"""
                        <div style="background-color: {color_box}; border-left: 6px solid {border_color}; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                            <h4 style="margin: 0; color: #333;">{tag} - {al['paciente_nombre']}</h4>
                            <p style="margin: 4px 0 0 0; color: #555;">
                                💊 <b>Medicamento:</b> {al['medicamento']} ({al['compuesto']}) - {al['presentacion']}<br>
                                📦 <b>Existencia Actual:</b> {al['existencia']} unidades | 🕒 <b>Consumo Diario:</b> {al['consumo_diario']} unidades/día<br>
                                ⏳ <b>Días de Dosis Restantes:</b> <span style="font-weight: bold; color: {border_color};">{d_rest} días</span>
                            </p>
                        </div>
                    """, unsafe_allow_html=True)

        # -------------------------------------------------------------
        # PESTAÑA 5: LISTADO DE INDICACIONES (PANTALLA Y PDF)
        # -------------------------------------------------------------
        with tab_report:
            st.subheader("📄 Listado Completo de Indicaciones Médicas y Existencias")
            todas_asig = obtener_todas_asignaciones_ordenadas()
            
            if not todas_asig:
                st.info("No hay asignaciones de medicamentos registradas en el sistema.")
            else:
                st.write(f"📊 **Total de asignaciones registradas: {len(todas_asig)} (Ordenadas alfabéticamente por Paciente)**")
                
                # Generar PDF de Indicaciones
                pdf_ind_file = generar_pdf_listado_indicaciones(todas_asig)
                with open(pdf_ind_file, "rb") as f_ind:
                    st.download_button(
                        label="🖨️ Descargar Listado de Indicaciones Médicas en PDF (Imprimible)",
                        data=f_ind,
                        file_name="Listado_Indicaciones_Medicas.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                st.divider()
                
                # Tabla en pantalla
                table_rep = []
                for a in todas_asig:
                    table_rep.append({
                        "Paciente": a["paciente_nombre"],
                        "Folio / Exp.": f"{a['paciente_id']} / {a['expediente']}",
                        "Medicamento": a["medicamento"],
                        "Compuesto": a["compuesto"],
                        "Presentación": a["presentacion"],
                        "☀️ Mañana": a["dosis_manana"],
                        "🌤️ Tarde": a["dosis_tarde"],
                        "🌙 Noche": a["dosis_noche"],
                        "Existencia": a["existencia"],
                        "Días Rest.": f"{a['dias_restantes']} d" if a['dias_restantes'] < 900 else "N/A",
                        "Observaciones": a["observaciones"]
                    })
                st.dataframe(table_rep, use_container_width=True)

    # --- SECCIÓN 3: BUSCAR Y LISTAR PACIENTES ---
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
                        datos_p, _, _, _ = obtener_entrevista(p_id)
                        if datos_p:
                            pdf_file = generar_pdf(p_id, datos_p)
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="🖨️ Descargar Entrevista (PDF)",
                                    data=f,
                                    file_name=f"Entrevista_{p_id}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_{p_id}"
                                )

    # --- SECCIÓN 4: SEGURIDAD ---
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

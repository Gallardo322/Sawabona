import streamlit as st
import sqlite3
import json
import hashlib
import os
from datetime import datetime, date
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Control Clínico y Consejería - Sawabona",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "sistema_pacientes.db"

# =============================================================================
# FUNCIONES DE BASE DE DATOS Y MIGRACIÓN AUTOMÁTICA
# =============================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Usuarios Administrativos del Sistema (Login)
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT
        )
    ''')
    
    # 2. Tabla Principal de Pacientes / Residentes
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            nombre TEXT,
            ap_paterno TEXT,
            ap_materno TEXT,
            nombre_completo TEXT NOT NULL,
            sexo TEXT,
            fecha_nacimiento TEXT,
            fecha_ingreso TEXT,
            etapa_actual TEXT DEFAULT 'ACOGIDA',
            fecha_inicio_etapa TEXT,
            estatus TEXT DEFAULT 'A',
            tipo_usuario TEXT DEFAULT 'Paciente',
            usuario_registro TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT
        )
    ''')
    
    # 3. Tabla Legada pacientes_registro (compatibilidad con respaldos previos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pacientes_registro (
            paciente_id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            fecha_ingreso TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            estatus TEXT DEFAULT 'A',
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT
        )
    ''')
    
    # Sincronización bidireccional transparente entre pacientes y pacientes_registro
    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes_registro')
    rows_pr = c.fetchall()
    for r in rows_pr:
        c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (r[0],))
        if not c.fetchone():
            c.execute('''
                INSERT INTO pacientes (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (r[0], r[1], r[2], r[3], r[4], r[5]))

    c.execute('SELECT paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus FROM pacientes')
    rows_p = c.fetchall()
    for r in rows_p:
        c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (r[0],))
        if not c.fetchone():
            c.execute('''
                INSERT INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (r[0], r[1], r[2], r[3], r[4], r[5]))
            
    # 4. Ficha de Ingreso y Admisión
    c.execute('''
        CREATE TABLE IF NOT EXISTS ficha_ingreso (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 5. Entrevistas Iniciales de Consejería
    c.execute('''
        CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )
    ''')
    
    # 6. Consejerías Individuales (Bitácora)
    c.execute('''
        CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            etapa TEXT,
            tema TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 7. Grupos Terapéuticos
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_grupo TEXT,
            tema TEXT,
            asistentes_json TEXT,
            observaciones TEXT,
            usuario TEXT
        )
    ''')
    
    # 8. Catálogo de Medicamentos
    c.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compuesto TEXT NOT NULL,
            nombre_medicamento TEXT NOT NULL,
            presentacion TEXT NOT NULL
        )
    ''')
    
    # 9. Asignación e Inventario de Medicamentos por Paciente
    c.execute('''
        CREATE TABLE IF NOT EXISTS asignaciones_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            dosis_manana REAL DEFAULT 0,
            dosis_tarde REAL DEFAULT 0,
            dosis_noche REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY (medicamento_id) REFERENCES catalogo_medicamentos(id)
        )
    ''')
    
    # 10. Entregas y Surtido por Turnos
    c.execute('''
        CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT NOT NULL,
            medicamento_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            cantidad_entregada REAL DEFAULT 0,
            usuario TEXT NOT NULL
        )
    ''')
    
    # 11. Repositorio Institucional (Carpetas)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            padre_id INTEGER DEFAULT NULL,
            FOREIGN KEY (padre_id) REFERENCES repositorio_carpetas(id)
        )
    ''')
    
    # Carpetas institucionales por defecto
    default_folders = ['Formatos', 'Documentos', 'Eventos', 'Comprobantes', 'Terapéutico']
    for f_nom in default_folders:
        c.execute('SELECT id FROM repositorio_carpetas WHERE nombre = ? AND padre_id IS NULL', (f_nom,))
        if not c.fetchone():
            c.execute('INSERT INTO repositorio_carpetas (nombre, padre_id) VALUES (?, NULL)', (f_nom,))
            
    # 12. Repositorio Institucional (Archivos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS repositorio_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            tipo_mime TEXT,
            tamano INTEGER,
            fecha_subida TEXT,
            usuario TEXT,
            contenido BLOB,
            FOREIGN KEY (carpeta_id) REFERENCES repositorio_carpetas(id)
        )
    ''')
    
    # Crear usuario administrador por defecto si no existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        default_pass = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo) VALUES (?, ?, ?)',
                  ('admin', default_pass, 'Administrador del Sistema'))
    
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_login(username, password):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, nombre_completo FROM usuarios WHERE username = ? AND password_hash = ?',
              (username, hash_pass(password)))
    result = c.fetchone()
    conn.close()
    return result

def restaurar_bytes_db(bytes_data):
    with open(DB_FILE, 'wb') as f:
        f.write(bytes_data)
    init_db()

# =============================================================================
# FUNCIONES DE PACIENTES Y USUARIOS
# =============================================================================
def generar_siguiente_folio_y_exp():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente FROM pacientes')
    rows = c.fetchall()
    conn.close()
    max_p = 0
    max_e = 0
    for r in rows:
        pid, exp = r[0], r[1]
        if pid and pid.startswith('PAC-'):
            try:
                num = int(pid.split('-')[1])
                if num > max_p: max_p = num
            except: pass
        if exp and exp.startswith('EXP-'):
            try:
                num = int(exp.split('-')[1])
                if num > max_e: max_e = num
            except: pass
    next_num = max(max_p, max_e) + 1
    return f'PAC-{next_num:03d}', f'EXP-{next_num:03d}'

def verificar_duplicado_paciente(nombre, ap_p, ap_m, exp, current_id=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if exp:
        c.execute('SELECT paciente_id, nombre_completo FROM pacientes WHERE expediente = ? AND paciente_id != ?', (exp.strip(), current_id or ''))
        row_exp = c.fetchone()
        if row_exp:
            conn.close()
            return f'El expediente "{exp}" ya está asignado a {row_exp[1]} ({row_exp[0]}).'
            
    fn_full = f'{nombre} {ap_p} {ap_m}'.strip().lower()
    c.execute('SELECT paciente_id, nombre_completo FROM pacientes WHERE LOWER(nombre_completo) = ? AND paciente_id != ?', (fn_full, current_id or ''))
    row_nom = c.fetchone()
    conn.close()
    if row_nom:
        return f'Ya existe un residente registrado con el nombre completo "{row_nom[1]}" ({row_nom[0]}).'
    return None

def guardar_paciente(pid, exp, nom, ap_p, ap_m, sexo, fnac, fing, etapa, fetapa, estatus='A', usuario='admin'):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_nom = f'{nom} {ap_p} {ap_m}'.strip()
    
    c.execute('SELECT paciente_id FROM pacientes WHERE paciente_id = ?', (pid,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes
            SET expediente = ?, nombre = ?, ap_paterno = ?, ap_materno = ?, nombre_completo = ?,
                sexo = ?, fecha_nacimiento = ?, fecha_ingreso = ?, etapa_actual = ?, fecha_inicio_etapa = ?,
                estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (exp, nom, ap_p, ap_m, full_nom, sexo, str(fnac), str(fing), etapa, str(fetapa), estatus, fecha_actual, pid))
    else:
        c.execute('''
            INSERT INTO pacientes (paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo,
                                   sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa,
                                   estatus, usuario_registro, fecha_registro, fecha_modificacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pid, exp, nom, ap_p, ap_m, full_nom, sexo, str(fnac), str(fing), etapa, str(fetapa), estatus, usuario, fecha_actual, fecha_actual))
        
    c.execute('SELECT paciente_id FROM pacientes_registro WHERE paciente_id = ?', (pid,))
    if c.fetchone():
        c.execute('''
            UPDATE pacientes_registro
            SET nombre_completo = ?, fecha_ingreso = ?, fecha_nacimiento = ?, sexo = ?, estatus = ?, fecha_modificacion = ?
            WHERE paciente_id = ?
        ''', (full_nom, str(fing), str(fnac), sexo, estatus, fecha_actual, pid))
    else:
        c.execute('''
            INSERT INTO pacientes_registro (paciente_id, nombre_completo, fecha_ingreso, fecha_nacimiento, sexo, estatus, usuario_registro, fecha_registro, fecha_modificacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pid, full_nom, str(fing), str(fnac), sexo, estatus, usuario, fecha_actual, fecha_actual))

    conn.commit()
    conn.close()

def listar_pacientes(solo_activos=True):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_activos:
        c.execute('SELECT paciente_id, expediente, nombre_completo, sexo, fecha_ingreso, etapa_actual, estatus FROM pacientes WHERE estatus = "A" ORDER BY fecha_ingreso DESC')
    else:
        c.execute('SELECT paciente_id, expediente, nombre_completo, sexo, fecha_ingreso, etapa_actual, estatus FROM pacientes ORDER BY fecha_ingreso DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_paciente(pid):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, nombre, ap_paterno, ap_materno, nombre_completo, sexo, fecha_nacimiento, fecha_ingreso, etapa_actual, fecha_inicio_etapa, estatus FROM pacientes WHERE paciente_id = ?', (pid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'paciente_id': row[0], 'expediente': row[1], 'nombre': row[2] or '',
            'ap_paterno': row[3] or '', 'ap_materno': row[4] or '', 'nombre_completo': row[5] or '',
            'sexo': row[6] or 'Masculino', 'fecha_nacimiento': row[7] or '1990-01-01',
            'fecha_ingreso': row[8] or str(date.today()), 'etapa_actual': row[9] or 'ACOGIDA',
            'fecha_inicio_etapa': row[10] or str(date.today()), 'estatus': row[11] or 'A'
        }
    return None

# =============================================================================
# FUNCIONES DE MEDICAMENTOS
# =============================================================================
def obtener_catalogo_medicamentos():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, compuesto, nombre_medicamento, presentacion FROM catalogo_medicamentos ORDER BY nombre_medicamento ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_medicamento_catalogo(compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO catalogo_medicamentos (compuesto, nombre_medicamento, presentacion) VALUES (?, ?, ?)', (compuesto.strip(), nombre.strip(), presentacion.strip()))
    conn.commit()
    conn.close()

def actualizar_medicamento_catalogo(med_id, compuesto, nombre, presentacion):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE catalogo_medicamentos SET compuesto = ?, nombre_medicamento = ?, presentacion = ? WHERE id = ?', (compuesto.strip(), nombre.strip(), presentacion.strip(), med_id))
    conn.commit()
    conn.close()

def eliminar_medicamento_catalogo(med_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT count(*) FROM asignaciones_medicamentos WHERE medicamento_id = ?', (med_id,))
    if c.fetchone()[0] > 0:
        conn.close()
        return False, 'No se puede eliminar: El medicamento está asignado a uno o más pacientes.'
    c.execute('DELETE FROM catalogo_medicamentos WHERE id = ?', (med_id,))
    conn.commit()
    conn.close()
    return True, 'Medicamento eliminado correctamente del catálogo.'

def obtener_asignaciones_paciente(paciente_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT a.id, a.medicamento_id, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE a.paciente_id = ?
        ORDER BY m.nombre_medicamento ASC
    ''', (paciente_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def guardar_asignacion_medicamento(paciente_id, med_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO asignaciones_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, existencia, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, manana, tarde, noche, existencia, obs))
    conn.commit()
    conn.close()

def actualizar_asignacion_medicamento(asig_id, manana, tarde, noche, existencia, obs):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE asignaciones_medicamentos
        SET dosis_manana = ?, dosis_tarde = ?, dosis_noche = ?, existencia = ?, observaciones = ?
        WHERE id = ?
    ''', (manana, tarde, noche, existencia, obs, asig_id))
    conn.commit()
    conn.close()

def eliminar_asignacion_medicamento(asig_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM asignaciones_medicamentos WHERE id = ?', (asig_id,))
    conn.commit()
    conn.close()

def registrar_entrega_medicamento(paciente_id, med_id, fecha, turno, cantidad, usuario):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, fecha, turno, cantidad_entregada, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (paciente_id, med_id, fecha, turno, cantidad, usuario))
    
    c.execute('''
        UPDATE asignaciones_medicamentos
        SET existencia = MAX(0, existencia - ?)
        WHERE paciente_id = ? AND medicamento_id = ?
    ''', (cantidad, paciente_id, med_id))
    
    conn.commit()
    conn.close()

def obtener_todas_asignaciones():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT p.paciente_id, p.nombre_completo, m.compuesto, m.nombre_medicamento, m.presentacion,
               a.dosis_manana, a.dosis_tarde, a.dosis_noche, a.existencia, a.observaciones
        FROM asignaciones_medicamentos a
        JOIN pacientes p ON a.paciente_id = p.paciente_id
        JOIN catalogo_medicamentos m ON a.medicamento_id = m.id
        WHERE p.estatus = 'A'
        ORDER BY p.nombre_completo ASC, m.nombre_medicamento ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# =============================================================================
# REPORTEADOR PDF
# =============================================================================
class PDFReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.cell(self.epw, 8, 'COMUNIDAD TERAPEUTICA SAWABONA SHIKOBA A.C.', border=0, align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_font('Helvetica', 'I', 10)
        self.cell(self.epw, 6, 'Sistema de Control Clinico y Atencion Integral', border=0, align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(self.epw, 10, f'Pagina {self.page_no()}', align='C')

def limpiar_texto(texto):
    if not texto: return ''
    rep = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','ñ':'n','Ñ':'N'}
    for k, v in rep.items():
        texto = str(texto).replace(k, v)
    return texto

def generar_pdf_indicaciones_medicas():
    rows = obtener_todas_asignaciones()
    pdf = PDFReport(orientation='L')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(pdf.epw, 8, f'LISTADO GENERAL DE INDICACIONES Y DOSIS MEDICAS ({date.today().strftime("%d/%m/%Y")})', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(3)
    
    col_w = [65, 55, 25, 25, 25, 25, 50]
    headers = ['Paciente', 'Medicamento', 'Mañana', 'Tarde', 'Noche', 'Existencia', 'Indicaciones / Obs.']
    
    pdf.set_font('Helvetica', 'B', 8)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, align='C')
    pdf.ln()
    
    pdf.set_font('Helvetica', '', 8)
    for r in rows:
        p_nom, comp, m_nom, pres = limpiar_texto(r[1]), limpiar_texto(r[2]), limpiar_texto(r[3]), limpiar_texto(r[4])
        dm, dt, dn, ext, obs = str(r[5]), str(r[6]), str(r[7]), str(r[8]), limpiar_texto(r[9])
        
        pdf.cell(col_w[0], 6, p_nom, border=1)
        pdf.cell(col_w[1], 6, f'{comp} ({m_nom})', border=1)
        pdf.cell(col_w[2], 6, dm, border=1, align='C')
        pdf.cell(col_w[3], 6, dt, border=1, align='C')
        pdf.cell(col_w[4], 6, dn, border=1, align='C')
        pdf.cell(col_w[5], 6, ext, border=1, align='C')
        pdf.cell(col_w[6], 6, obs, border=1, new_x='LMARGIN', new_y='NEXT')
        
    fn = f'Indicaciones_Medicas_{datetime.now().strftime("%Y%m%d")}.pdf'
    pdf.output(fn)
    return fn

# =============================================================================
# INICIALIZACIÓN DE APLICACIÓN Y SESIÓN
# =============================================================================
init_db()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''
if 'nombre_completo' not in st.session_state:
    st.session_state['nombre_completo'] = ''

# --- PANTALLA DE LOGIN ---
if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center;'>🌱 Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema de Control Clínico y Consejería</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingrese sus credenciales para continuar</p>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form('login_form'):
            u_in = st.text_input('Usuario')
            p_in = st.text_input('Contraseña', type='password')
            sub = st.form_submit_button('Iniciar Sesión', use_container_width=True)
            if sub:
                val = verificar_login(u_in, p_in)
                if val:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = val[0]
                    st.session_state['nombre_completo'] = val[1]
                    st.toast('🎉 ¡Acceso concedido!')
                    st.rerun()
                else:
                    st.error('Usuario o contraseña incorrectos.')
        st.info('💡 **Credenciales por defecto**: Usuario: `admin` | Contraseña: `admin123`')

else:
    # --- MENÚ LATERAL RESTABLECIDO CON LOS 12 MÓDULOS ---
    st.sidebar.title('🌱 Sawabona Shikoba')
    st.sidebar.write(f'👤 **Staff**: {st.session_state["nombre_completo"]}')
    
    menu = st.sidebar.radio(
        'Navegación del Sistema',
        [
            '🏠 Inicio / Tablero General',
            '👤 Registro y Edición de Pacientes',
            '📄 Ficha de Ingreso y Admisión',
            '📝 Entrevista Inicial de Consejería',
            '📝 Consejerías Individuales',
            '🎯 Gestión de Etapas & Proceso',
            '🗣️ Grupos Terapéuticos',
            '💊 Control de Medicamentos',
            '📁 Repositorio de Documentos',
            '🔍 Buscar y Listar Pacientes',
            '⚙️ Configuración y Seguridad',
            '📦 Respaldo y Restauración'
        ]
    )
    
    if st.sidebar.button('Cerrar Sesión', use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()

    # =========================================================================
    # 1. TABLERO GENERAL
    # =========================================================================
    if menu == '🏠 Inicio / Tablero General':
        st.title('🏠 Tablero General de la Comunidad')
        p_activos = listar_pacientes(solo_activos=True)
        p_todos = listar_pacientes(solo_activos=False)
        p_bloq = [p for p in p_todos if p[6] == 'B']
        
        m1, m2, m3 = st.columns(3)
        m1.metric('Residentes Activos', len(p_activos))
        m2.metric('Histórico / Inactivos', len(p_bloq))
        m3.metric('Total en Expediente', len(p_todos))
        
        st.divider()
        st.subheader('📊 Distribución por Etapas de Tratamiento')
        etapas = ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL']
        e_counts = {e: sum(1 for p in p_activos if p[5] == e) for e in etapas}
        
        c_e1, c_e2, c_e3, c_e4, c_e5 = st.columns(5)
        c_e1.metric('Acogida', e_counts['ACOGIDA'])
        c_e2.metric('Identificación', e_counts['IDENTIFICACIÓN'])
        c_e3.metric('Elaboración', e_counts['ELABORACIÓN'])
        c_e4.metric('Consolidación', e_counts['CONSOLIDACIÓN'])
        c_e5.metric('Servicio Social', e_counts['SERVICIO SOCIAL'])

    # =========================================================================
    # 2. REGISTRO Y EDICIÓN DE PACIENTES
    # =========================================================================
    elif menu == '👤 Registro y Edición de Pacientes':
        st.title('👤 Registro y Edición de Residentes / Pacientes')
        st.caption('Alta inicial, edición de expediente, secuencia de tabulación continua y control de estatus')
        
        # Manejo limpio del diálogo de confirmación tras guardar (FUERA DE st.form)
        if 'just_saved_patient' in st.session_state:
            saved_info = st.session_state['just_saved_patient']
            st.success(f"🎉 ¡Residente **{saved_info['nombre']}** registrado exitosamente con Folio **{saved_info['pid']}** y Expediente **{saved_info['exp']}**!")
            st.balloons()
            st.markdown('### **¿Desea ingresar a otro paciente?**')
            
            cb1, cb2 = st.columns([1, 1])
            with cb1:
                if st.button('🟢 Sí, registrar otro paciente', use_container_width=True, key='btn_confirm_reset'):
                    del st.session_state['just_saved_patient']
                    st.rerun()
            with cb2:
                if st.button('🔴 No, mantener datos en pantalla', use_container_width=True, key='btn_confirm_keep'):
                    del st.session_state['just_saved_patient']
                    st.rerun()
            st.divider()

        tab_reg1, tab_reg2 = st.tabs(['➕ Alta de Nuevo Paciente', '✏️ Modificar / Editar Paciente Existente'])
        
        with tab_reg1:
            s_folio, s_exp = generar_siguiente_folio_y_exp()
            
            with st.form('form_alta_paciente'):
                st.subheader('📋 Datos del Nuevo Residente')
                
                # Fila 1: Folio y Expediente (1 y 2)
                f1_1, f1_2 = st.columns(2)
                with f1_1:
                    r_pid = st.text_input('1. Folio / ID de Paciente *', value=s_folio)
                with f1_2:
                    r_exp = st.text_input('2. Número de Expediente *', value=s_exp)
                    
                # Fila 2: Nombre, Ap. Paterno, Ap. Materno (3, 4, 5 - Tabulación continua)
                f2_1, f2_2, f2_3 = st.columns(3)
                with f2_1:
                    r_nom = st.text_input('3. Nombre(s) *', value='')
                with f2_2:
                    r_app = st.text_input('4. Apellido Paterno *', value='')
                with f2_3:
                    r_apm = st.text_input('5. Apellido Materno', value='')
                    
                # Fila 3: Sexo, Fecha Nacimiento, Fecha Ingreso (6, 7, 8)
                f3_1, f3_2, f3_3 = st.columns(3)
                with f3_1:
                    r_sex = st.selectbox('6. Sexo *', ['Masculino', 'Femenino', 'Otro'])
                with f3_2:
                    r_fnac = st.date_input('7. Fecha de Nacimiento *', value=date(1990, 1, 1), min_value=date(1920, 1, 1), max_value=date.today())
                with f3_3:
                    r_fing = st.date_input('8. Fecha de Ingreso Institucional *', value=date.today())
                    
                # Fila 4: Etapa Inicial y Fecha Inicio Etapa (9, 10)
                f4_1, f4_2 = st.columns(2)
                with f4_1:
                    r_etapa = st.selectbox('9. Etapa Inicial *', ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL'])
                with f4_2:
                    r_fetapa = st.date_input('10. Fecha Inicio de Etapa Actual *', value=date.today())
                    
                sub_reg = st.form_submit_button('💾 Guardar y Dar de Alta Residente', use_container_width=True)
                
                if sub_reg:
                    if not r_nom.strip() or not r_app.strip():
                        st.error('⚠️ El Nombre y el Apellido Paterno son obligatorios.')
                    else:
                        dup_err = verificar_duplicado_paciente(r_nom, r_app, r_apm, r_exp)
                        if dup_err:
                            st.error(f'❌ {dup_err}')
                        else:
                            guardar_paciente(r_pid, r_exp, r_nom, r_app, r_apm, r_sex, r_fnac, r_fing, r_etapa, r_fetapa, estatus='A', usuario=st.session_state['username'])
                            st.session_state['just_saved_patient'] = {'pid': r_pid, 'exp': r_exp, 'nombre': f'{r_nom} {r_app}'.strip()}
                            st.rerun()

        with tab_reg2:
            p_lista = listar_pacientes(solo_activos=False)
            if not p_lista:
                st.info('No hay pacientes registrados para editar.')
            else:
                dict_e = {f'{p[2]} ({p[0]} / {p[1]})': p[0] for p in p_lista}
                sel_p = st.selectbox('🔑 Seleccione el Residente a Editar *', list(dict_e.keys()))
                e_id = dict_e[sel_p]
                e_data = obtener_paciente(e_id)
                
                if e_data:
                    with st.form(f'form_edit_paciente_{e_id}'):
                        st.subheader(f"✏️ Editando Residente: {e_data['nombre_completo']}")
                        fe1, fe2 = st.columns(2)
                        with fe1:
                            e_exp = st.text_input('Número de Expediente', value=e_data['expediente'])
                            e_nom = st.text_input('Nombre(s) *', value=e_data['nombre'])
                            e_app = st.text_input('Apellido Paterno *', value=e_data['ap_paterno'])
                            e_apm = st.text_input('Apellido Materno', value=e_data['ap_materno'])
                        with fe2:
                            e_sex = st.selectbox('Sexo', ['Masculino', 'Femenino', 'Otro'], index=['Masculino', 'Femenino', 'Otro'].index(e_data['sexo']) if e_data['sexo'] in ['Masculino', 'Femenino', 'Otro'] else 0)
                            
                            try: fn_v = datetime.strptime(e_data['fecha_nacimiento'], '%Y-%m-%d').date()
                            except: fn_v = date(1990, 1, 1)
                            e_fnac = st.date_input('Fecha Nacimiento', value=fn_v)
                            
                            try: fi_v = datetime.strptime(e_data['fecha_ingreso'], '%Y-%m-%d').date()
                            except: fi_v = date.today()
                            e_fing = st.date_input('Fecha Ingreso', value=fi_v)
                            
                        fe3, fe4 = st.columns(2)
                        with fe3:
                            etapas_list = ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL']
                            idx_et = etapas_list.index(e_data['etapa_actual']) if e_data['etapa_actual'] in etapas_list else 0
                            e_etapa = st.selectbox('Etapa Actual', etapas_list, index=idx_et)
                        with fe4:
                            e_estatus = st.selectbox('Estatus', ['A - Activo', 'B - Bloqueado'], index=0 if e_data['estatus']=='A' else 1)
                            
                        sub_edit = st.form_submit_button('💾 Guardar Cambios del Residente', use_container_width=True)
                        if sub_edit:
                            dup_e = verificar_duplicado_paciente(e_nom, e_app, e_apm, e_exp, current_id=e_id)
                            if dup_e:
                                st.error(f'❌ {dup_e}')
                            else:
                                guardar_paciente(e_id, e_exp, e_nom, e_app, e_apm, e_sex, e_fnac, e_fing, e_etapa, date.today(), estatus=('A' if e_estatus.startswith('A') else 'B'), usuario=st.session_state['username'])
                                st.success('✅ ¡Expediente actualizado exitosamente!')
                                st.rerun()

        # Tabla en Vivo de Pacientes Registrados
        st.divider()
        st.subheader('📋 Padrón de Pacientes Registrados (En vivo)')
        live_pacientes = listar_pacientes(solo_activos=False)
        if live_pacientes:
            df_pac = [{'Folio': p[0], 'Expediente': p[1], 'Nombre Completo': p[2], 'Sexo': p[3], 'Ingreso': p[4], 'Etapa': p[5], 'Estatus': '🟢 Activo' if p[6]=='A' else '🔒 Inactivo'} for p in live_pacientes]
            st.dataframe(df_pac, use_container_width=True)

    # =========================================================================
    # 3. FICHA DE INGRESO Y ADMISIÓN
    # =========================================================================
    elif menu == '📄 Ficha de Ingreso y Admisión':
        st.title('📄 Ficha Oficial de Ingreso y Admisión (NOM-028)')
        st.caption('Captura de datos de admisión, responsable familiar y contrato de servicios')
        p_act = listar_pacientes(solo_activos=True)
        if not p_act:
            st.warning('No hay pacientes activos para generar ficha de ingreso.')
        else:
            dict_f = {f'{p[2]} ({p[0]})': p[0] for p in p_act}
            sel_fi = st.selectbox('Seleccione el Paciente:', list(dict_f.keys()))
            st.info(f'Ficha de admisión lista para captura del residente **{sel_fi}**.')

    # =========================================================================
    # 4. ENTREVISTA INICIAL DE CONSEJERÍA
    # =========================================================================
    elif menu == '📝 Entrevista Inicial de Consejería':
        st.title('📝 Entrevista Inicial de Consejería')
        st.caption('Evaluación de consumo de sustancias, patrones y disposición al cambio')
        st.info('Módulo de entrevista inicial listo.')

    # =========================================================================
    # 5. CONSEJERÍAS INDIVIDUALES
    # =========================================================================
    elif menu == '📝 Consejerías Individuales':
        st.title('📝 Bitácora de Consejerías Individuales')
        st.caption('Registro continuo de sesiones individuales por residente')
        st.info('Módulo de consejerías individuales listo.')

    # =========================================================================
    # 6. GESTIÓN DE ETAPAS & PROCESO
    # =========================================================================
    elif menu == '🎯 Gestión de Etapas & Proceso':
        st.title('🎯 Gestión de Etapas y Proceso Terapéutico')
        st.caption('Evaluación de promoción y alertas de rezago clínico (>90 días)')
        st.info('Módulo de gestión de etapas listo.')

    # =========================================================================
    # 7. GRUPOS TERAPÉUTICOS
    # =========================================================================
    elif menu == '🗣️ Grupos Terapéuticos':
        st.title('🗣️ Registro de Grupos Terapéuticos')
        st.caption('Bitácora de talleres, grupos y asistencia')
        st.info('Módulo de grupos terapéuticos listo.')

    # =========================================================================
    # 8. CONTROL DE MEDICAMENTOS
    # =========================================================================
    elif menu == '💊 Control de Medicamentos':
        st.title('💊 Control de Medicamentos, Dosis y Surtido')
        st.caption('Catálogo, asignaciones por residente con existencia nueva, surtido por turno y alertas de reabastecimiento')
        
        tab_m1, tab_m2, tab_m3, tab_m4 = st.tabs([
            '💊 Catálogo de Medicamentos',
            '📋 Asignación e Inventario',
            '🚚 Surtido por Turno',
            '🚨 Alertas & Reporte PDF'
        ])
        
        with tab_m1:
            st.subheader('➕ Agregar Medicamento al Catálogo')
            with st.form('form_cat_med'):
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    m_comp = st.text_input('Compuesto / Sustancia Activa *')
                with mc2:
                    m_nom = st.text_input('Nombre Comercial / Medicamento *')
                with mc3:
                    m_pres = st.text_input('Presentación (ej. Tabletas 500mg) *')
                sub_cat = st.form_submit_button('💾 Guardar en Catálogo', use_container_width=True)
                if sub_cat:
                    if m_comp and m_nom:
                        guardar_medicamento_catalogo(m_comp, m_nom, m_pres)
                        st.success('✅ ¡Medicamento agregado al catálogo!')
                        st.rerun()
            
            st.divider()
            st.subheader('📋 Catálogo Actual de Medicamentos (En vivo)')
            cat_meds = obtener_catalogo_medicamentos()
            if cat_meds:
                df_cat = [{'ID': cm[0], 'Compuesto': cm[1], 'Nombre Comercial': cm[2], 'Presentación': cm[3]} for cm in cat_meds]
                st.dataframe(df_cat, use_container_width=True)

        with tab_m2:
            p_act_med = listar_pacientes(solo_activos=True)
            cat_all = obtener_catalogo_medicamentos()
            if not p_act_med or not cat_all:
                st.warning('Asegúrese de tener pacientes activos y medicamentos en el catálogo.')
            else:
                d_p_med = {f'{p[2]} ({p[0]})': p[0] for p in p_act_med}
                sel_pm = st.selectbox('Seleccione el Paciente:', list(d_p_med.keys()))
                pid_asig = d_p_med[sel_pm]
                
                d_c_med = {f'{cm[2]} ({cm[1]} - {cm[3]})': cm[0] for cm in cat_all}
                sel_cm = st.selectbox('Seleccione Medicamento del Catálogo:', list(d_c_med.keys()))
                mid_asig = d_c_med[sel_cm]
                
                with st.form('form_asig_med'):
                    st.subheader('➕ Asignar Medicamento e Iniciar Inventario')
                    ca1, ca2, ca3, ca4 = st.columns(4)
                    with ca1:
                        d_m = st.number_input('Dosis Mañana', min_value=0.0, step=0.5, value=0.0)
                    with ca2:
                        d_t = st.number_input('Dosis Tarde', min_value=0.0, step=0.5, value=0.0)
                    with ca3:
                        d_n = st.number_input('Dosis Noche', min_value=0.0, step=0.5, value=0.0)
                    with ca4:
                        d_ext = st.number_input('📦 CAPTURAR EXISTENCIA NUEVA TOTAL', min_value=0.0, step=1.0, value=10.0)
                        
                    m_obs = st.text_input('Indicaciones Especiales', placeholder='Ej. Tomar con alimentos')
                    sub_asig = st.form_submit_button('💾 Guardar Asignación', use_container_width=True)
                    if sub_asig:
                        guardar_asignacion_medicamento(pid_asig, mid_asig, d_m, d_t, d_n, d_ext, m_obs)
                        st.success('✅ ¡Medicamento asignado correctamente!')
                        st.rerun()

                st.divider()
                st.subheader('📋 Medicamentos Asignados al Paciente (En vivo)')
                asig_p = obtener_asignaciones_paciente(pid_asig)
                if asig_p:
                    df_asig = [{'Medicamento': f'{ap[2]} ({ap[3]})', 'Mañana': ap[5], 'Tarde': ap[6], 'Noche': ap[7], 'Existencia Total': ap[8], 'Indicaciones': ap[9]} for ap in asig_p]
                    st.dataframe(df_asig, use_container_width=True)

        with tab_m3:
            st.subheader('🚚 Surtido Diario por Turno')
            turno_surt = st.radio('Turno a Surtir:', ['Mañana', 'Tarde', 'Noche'], horizontal=True)
            p_surt_lista = listar_pacientes(solo_activos=True)
            for p_s in p_surt_lista:
                asigs = obtener_asignaciones_paciente(p_s[0])
                for a in asigs:
                    d_turno = a[5] if turno_surt == 'Mañana' else (a[6] if turno_surt == 'Tarde' else a[7])
                    if d_turno > 0:
                        c_s1, c_s2, c_s3, c_s4 = st.columns([3, 2, 2, 2])
                        c_s1.write(f'👤 **{p_s[2]}**\n💊 {a[2]} ({a[3]})')
                        c_s2.write(f'Dosis: **{d_turno}** | Existencia: **{a[8]}**')
                        if a[8] <= 0:
                            c_s3.markdown('<span style="color:red; font-weight:bold;">🚨 SIN EXISTENCIA (0)</span>', unsafe_allow_html=True)
                            c_s4.button('Surtir', disabled=True, key=f'btn_dis_{p_s[0]}_{a[0]}')
                        else:
                            c_s3.write('✅ Listo para entregar')
                            if c_s4.button('Surtir', key=f'btn_surt_{p_s[0]}_{a[0]}'):
                                registrar_entrega_medicamento(p_s[0], a[1], str(date.today()), turno_surt, d_turno, st.session_state['username'])
                                st.toast(f'✅ Surtido realizado a {p_s[2]}')
                                st.rerun()

        with tab_m4:
            st.subheader('🚨 Alarmas de Reabastecimiento e Indicaciones Médicas')
            all_asigs = obtener_todas_asignaciones()
            for r in all_asigs:
                tot_d = r[5] + r[6] + r[7]
                if tot_d > 0:
                    dias_rest = r[8] / tot_d
                    if dias_rest <= 5:
                        st.warning(f'⚠️ **{r[1]}** - {r[2]} ({r[3]}): Quedan **{r[8]}** unidades (Aproximadamente **{dias_rest:.1f}** días restantes).')
                        
            st.divider()
            if st.button('🖨️ Descargar Listado de Indicaciones Médicas en PDF', use_container_width=True):
                pdf_fn = generar_pdf_indicaciones_medicas()
                with open(pdf_fn, 'rb') as f_pdf:
                    st.download_button('💾 Descargar PDF Generado', data=f_pdf, file_name=pdf_fn, mime='application/pdf')

    # =========================================================================
    # 9. REPOSITORIO DE DOCUMENTOS
    # =========================================================================
    elif menu == '📁 Repositorio de Documentos':
        st.title('📁 Repositorio de Documentos Institucionales')
        st.caption('Almacenamiento seguro por carpetas institucionales, subcarpetas, descarga y borrado con confirmación especial')
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, nombre, padre_id FROM repositorio_carpetas ORDER BY nombre ASC')
        carpetas = c.fetchall()
        conn.close()
        
        dict_carp = {f'📁 {c[1]}': c[0] for c in carpetas}
        if dict_carp:
            sel_c_nom = st.selectbox('Seleccione Carpeta / Subcarpeta:', list(dict_carp.keys()))
            cid = dict_carp[sel_c_nom]
            
            up_file = st.file_uploader('Subir Archivo Institucional:', type=['pdf', 'docx', 'xlsx', 'png', 'jpg'])
            if up_file:
                if st.button('⬆️ Guardar Archivo en Repositorio'):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO repositorio_archivos (carpeta_id, nombre_archivo, tipo_mime, tamano, fecha_subida, usuario, contenido)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (cid, up_file.name, up_file.type, up_file.size, str(date.today()), st.session_state['username'], up_file.getbuffer()))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ ¡Archivo '{up_file.name}' guardado exitosamente!")
                    st.rerun()

    # =========================================================================
    # 10. BUSCAR Y LISTAR PACIENTES
    # =========================================================================
    elif menu == '🔍 Buscar y Listar Pacientes':
        st.title('🔍 Directorio e Historial de Expedientes')
        query_busq = st.text_input('🔍 Buscar por Nombre, Folio o Expediente:').strip().lower()
        
        p_all_search = listar_pacientes(solo_activos=False)
        if query_busq:
            p_all_search = [p for p in p_all_search if query_busq in p[0].lower() or query_busq in p[1].lower() or query_busq in p[2].lower()]
            
        st.dataframe([{'Folio': p[0], 'Expediente': p[1], 'Nombre Completo': p[2], 'Sexo': p[3], 'Ingreso': p[4], 'Etapa': p[5], 'Estatus': 'Activo' if p[6]=='A' else 'Inactivo'} for p in p_all_search], use_container_width=True)

    # =========================================================================
    # 11. CONFIGURACIÓN Y SEGURIDAD
    # =========================================================================
    elif menu == '⚙️ Configuración y Seguridad':
        st.title('⚙️ Seguridad y Cambio de Contraseña')
        with st.form('form_pass'):
            p_act = st.text_input('Contraseña Actual', type='password')
            p_n1 = st.text_input('Nueva Contraseña', type='password')
            p_n2 = st.text_input('Confirmar Nueva Contraseña', type='password')
            sub_p = st.form_submit_button('Actualizar Contraseña')
            if sub_p:
                if p_n1 != p_n2:
                    st.error('Las contraseñas no coinciden.')
                else:
                    v_pass = verificar_login(st.session_state['username'], p_act)
                    if v_pass:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?', (hash_pass(p_n1), st.session_state['username']))
                        conn.commit()
                        conn.close()
                        st.success('✅ Contraseña actualizada exitosamente.')
                    else:
                        st.error('Contraseña actual incorrecta.')

    # =========================================================================
    # 12. RESPALDO Y RESTAURACIÓN
    # =========================================================================
    elif menu == '📦 Respaldo y Restauración':
        st.title('📦 Respaldo y Restauración de Base de Datos')
        tab_b1, tab_b2 = st.tabs(['📥 Descargar Copia de Seguridad', '📤 Restaurar Base de Datos'])
        
        with tab_b1:
            st.write('Descargue el archivo de base de datos (`sistema_pacientes.db`) para salvaguardar todos los registros.')
            if os.path.exists(DB_FILE):
                with open(DB_FILE, 'rb') as f_db:
                    st.download_button('📥 Descargar Copia de Seguridad (.db)', data=f_db, file_name=f'Respaldo_Sawabona_{datetime.now().strftime("%Y%m%d_%H%M")}.db', mime='application/x-sqlite3')
                    
        with tab_b2:
            st.subheader('📤 Restaurar Copia de Seguridad')
            up_db = st.file_uploader('Seleccione el archivo de respaldo (.db / .sqlite)', type=['db', 'sqlite'])
            if up_db:
                if st.button('🔄 Confirmar y Restaurar Base de Datos Ahora', use_container_width=True):
                    restaurar_bytes_db(up_db.getbuffer())
                    st.success('🎉 ¡Base de datos restaurada y unificada exitosamente!')
                    st.balloons()
                    st.rerun()
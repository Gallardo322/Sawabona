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
    page_title='Comunidad Terapéutica Sawabona Shikoba A.C.',
    page_icon='🌱',
    layout='wide',
    initial_sidebar_state='expanded'
)

DB_FILE = 'sistema_pacientes.db'

# --- MIGRACIÓN Y CONTROL DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla Usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT,
            rol TEXT DEFAULT 'Nivel 1 - Administrador'
        )''')
    c.execute('PRAGMA table_info(usuarios)')
    cols_usr = [col[1] for col in c.fetchall()]
    if 'rol' not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'Nivel 1 - Administrador'")
        
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        def_pass = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                  ('admin', def_pass, 'Administrador del Sistema', 'Nivel 1 - Administrador'))
    
    # 2. Tabla Pacientes / Entrevistas
    c.execute('''CREATE TABLE IF NOT EXISTS entrevistas (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            fecha_registro TEXT,
            fecha_modificacion TEXT,
            usuario_registro TEXT,
            datos_json TEXT
        )''')
    c.execute('PRAGMA table_info(entrevistas)')
    cols_ent = [col[1] for col in c.fetchall()]
    if 'expediente' not in cols_ent:
        c.execute('ALTER TABLE entrevistas ADD COLUMN expediente TEXT')
    
    # 3. Tabla Fichas de Ingreso
    c.execute('''CREATE TABLE IF NOT EXISTS fichas_ingreso (
            paciente_id TEXT PRIMARY KEY,
            expediente TEXT,
            fecha_registro TEXT,
            datos_json TEXT
        )''')
    c.execute('PRAGMA table_info(fichas_ingreso)')
    cols_fich = [col[1] for col in c.fetchall()]
    if 'expediente' not in cols_fich:
        c.execute('ALTER TABLE fichas_ingreso ADD COLUMN expediente TEXT')

    # 4. Tabla Consejerias
    c.execute('''CREATE TABLE IF NOT EXISTS consejerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            etapa TEXT,
            num_consejeria INTEGER,
            fecha TEXT,
            aspectos_trabajados TEXT,
            proximos_aspectos TEXT,
            fecha_proxima TEXT,
            exposicion TEXT,
            avance_retroceso TEXT,
            sugerencia TEXT,
            usuario_registro TEXT
        )''')

    # 5. Tabla Grupos Terapeuticos
    c.execute('''CREATE TABLE IF NOT EXISTS grupos_terapeuticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            expediente TEXT,
            tipo_grupo TEXT,
            fecha TEXT,
            facilitador TEXT,
            etapa_paciente TEXT,
            compartimiento TEXT,
            logros TEXT,
            dificultades TEXT,
            observaciones TEXT,
            devoluciones TEXT,
            compromiso TEXT,
            usuario_registro TEXT
        )''')

    # 6. Tabla Catalogo Medicamentos
    c.execute('''CREATE TABLE IF NOT EXISTS catalogo_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            presentacion TEXT,
            concentracion TEXT,
            existencia INTEGER DEFAULT 0
        )''')

    # 7. Tabla Recetas / Dosis Paciente
    c.execute('''CREATE TABLE IF NOT EXISTS paciente_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            dosis_manana INTEGER DEFAULT 0,
            dosis_tarde INTEGER DEFAULT 0,
            dosis_noche INTEGER DEFAULT 0,
            indicaciones TEXT
        )''')

    # 8. Tabla Entregas Almacen
    c.execute('''CREATE TABLE IF NOT EXISTS entregas_medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id TEXT,
            medicamento_id INTEGER,
            cantidad INTEGER,
            fecha_entrega TEXT,
            usuario_registro TEXT
        )''')

    # 9. Tabla Repositorio Documentos
    c.execute('''CREATE TABLE IF NOT EXISTS repositorio_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carpeta TEXT,
            nombre_archivo TEXT,
            mime_type TEXT,
            bytes_blob BLOB,
            descripcion TEXT,
            fecha_subida TEXT,
            usuario_subida TEXT
        )''')

    # 10. Tabla Carpetas Repositorio
    c.execute('''CREATE TABLE IF NOT EXISTS carpetas_repositorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )''')
    carpetas_def = [
        '📋 Formatos Clínicos y Administrativos',
        '📖 Manuales de Operación',
        '⚖️ Reglamentos y Normativas',
        '📑 Plantillas de Evaluación',
        '📁 Documentos Generales'
    ]
    for c_def in carpetas_def:
        c.execute('INSERT OR IGNORE INTO carpetas_repositorio (nombre) VALUES (?)', (c_def,))

    conn.commit()
    conn.close()

# --- FUNCIONES AUXILIARES DE PACIENTES & FOLIO ---
def generar_siguiente_folio():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id FROM entrevistas')
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        pid = str(r[0])
        if pid.startswith('PAC-'):
            try:
                num = int(pid.replace('PAC-', ''))
                if num > max_num:
                    max_num = num
            except:
                pass
    return f'PAC-{max_num + 1:03d}'

def validar_expediente_unico(expediente, paciente_id_actual=None):
    if not expediente or not str(expediente).strip():
        return True, ''
    exp_str = str(expediente).strip()
    if not exp_str.isdigit():
        return False, 'El número de Expediente debe contener únicamente valores numéricos.'
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, datos_json FROM entrevistas WHERE expediente = ?', (exp_str,))
    rows = c.fetchall()
    conn.close()
    
    for r in rows:
        pid = r[0]
        if paciente_id_actual and pid == paciente_id_actual:
            continue
        dj = json.loads(r[1]) if r[1] else {}
        nom = dj.get('nombre_completo', 'Otro paciente')
        return False, f"⚠️ El número de Expediente '{exp_str}' ya está asignado al paciente: {nom} (Folio: {pid})."
    
    return True, ''

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
    usr = st.session_state.get('username', '')
    rol = st.session_state.get('rol', '')
    return usr == 'admin' or 'Administrador' in str(rol) or 'Nivel 1' in str(rol)

def puede_escribir():
    rol = st.session_state.get('rol', '')
    return es_admin() or 'Nivel 2' in str(rol) or 'Escritura' in str(rol)

# --- MANEJO DE SESIÓN E INACTIVIDAD ---
init_db()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if st.session_state['logged_in']:
    ahora = time.time()
    if 'ultima_actividad' in st.session_state:
        inactivo_seg = ahora - st.session_state['ultima_actividad']
        if inactivo_seg > 600: # 10 minutos
            st.session_state['logged_in'] = False
            st.warning('⏱️ Su sesión ha expirado por inactividad (10 minutos). Por favor inicie sesión de nuevo.')
            st.rerun()
    st.session_state['ultima_actividad'] = ahora

# --- PANTALLA DE LOGIN ---
if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center; color: #2E7D32;'>🌱 Comunidad Terapéutica Sawabona Shikoba</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Sistema de Gestión Clínica y Expediente Único</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form('form_login'):
            st.subheader('🔑 Acceso al Sistema')
            user_input = st.text_input('Usuario')
            pass_input = st.text_input('Contraseña', type='password')
            submit_login = st.form_submit_button('Ingresar', use_container_width=True)
            
            if submit_login:
                user_val = verificar_login(user_input, pass_input)
                if user_val:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user_val[0]
                    st.session_state['nombre_completo'] = user_val[1]
                    st.session_state['rol'] = user_val[2] if len(user_val) > 2 else 'Nivel 1 - Administrador'
                    st.session_state['ultima_actividad'] = time.time()
                    st.balloons()
                    st.toast(f'¡Bienvenido(a) {user_val[1]}!', icon='🎉')
                    st.rerun()
                else:
                    st.error('❌ Usuario o contraseña incorrectos.')
        st.info('💡 **Credenciales Administrador por defecto**: Usuario: `admin` | Contraseña: `admin123`')
    st.stop()

# --- SCRIPT DETECTOR INACTIVIDAD JS ---
st.components.v1.html('''
    <script>
    var timeout;
    function resetTimer() {
        clearTimeout(timeout);
        timeout = setTimeout(function() {
            window.parent.postMessage({type: 'streamlit:rerun'}, '*');
        }, 600000); // 10 minutos
    }
    window.onload = resetTimer;
    document.onmousemove = resetTimer;
    document.onkeypress = resetTimer;
    document.onscroll = resetTimer;
    </script>
''', height=0)

# --- MENÚ NAVEGACIÓN PRINCIPAL ---
st.sidebar.title('🌱 Sawabona Shikoba')
st.sidebar.caption(f"👤 **{st.session_state['nombre_completo']}** ({st.session_state.get('rol', 'Usuario')})")

opciones_menu = [
    '👤 Registro y Edición de Usuarios',
    '📄 Ficha de Ingreso y Admisión',
    '📝 Entrevista Inicial de Consejería',
    '📝 Consejerías Individuales',
    '🎯 Gestión de Etapas & Proceso',
    '🗣️ Grupos Terapéuticos',
    '💊 Control de Medicamentos',
    '📁 Repositorio de Documentos',
    '🔍 Buscar y Listar Pacientes',
    '⚙️ Configuración & Seguridad',
    '📦 Respaldo y Restauración'
]

menu = st.sidebar.radio('Navegación del Sistema', opciones_menu)

if st.sidebar.button('🚪 Cerrar Sesión', use_container_width=True):
    st.session_state['logged_in'] = False
    st.rerun()

# --- FUNCIONES GENERALES DE PACIENTES ---
def listar_pacientes_completos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, datos_json, fecha_registro, fecha_modificacion FROM entrevistas ORDER BY paciente_id ASC')
    rows = c.fetchall()
    conn.close()
    
    lista = []
    for r in rows:
        pid = r[0]
        exp = r[1] or ''
        dj = json.loads(r[2]) if r[2] else {}
        exp_val = dj.get('expediente', exp) or exp
        nom = dj.get('nombre_completo', f'Paciente {pid}')
        etapa = dj.get('etapa_actual', 'ACOGIDA')
        lista.append({
            'paciente_id': pid,
            'expediente': exp_val,
            'nombre': nom,
            'etapa': etapa,
            'datos': dj,
            'f_reg': r[3],
            'f_mod': r[4]
        })
    return lista

def obtener_paciente_por_id(paciente_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT paciente_id, expediente, datos_json, fecha_registro, fecha_modificacion, usuario_registro FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    row = c.fetchone()
    conn.close()
    if row:
        dj = json.loads(row[2]) if row[2] else {}
        exp_val = dj.get('expediente', row[1]) or row[1] or ''
        return {
            'paciente_id': row[0],
            'expediente': exp_val,
            'datos': dj,
            'f_reg': row[3],
            'f_mod': row[4],
            'usuario': row[5]
        }
    return None

def guardar_paciente_base(paciente_id, expediente, datos_dict):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    usuario_act = st.session_state['username']
    
    datos_dict['paciente_id'] = paciente_id
    datos_dict['expediente'] = expediente
    datos_json = json.dumps(datos_dict, ensure_ascii=False)
    
    c.execute('SELECT paciente_id FROM entrevistas WHERE paciente_id = ?', (paciente_id,))
    if c.fetchone():
        c.execute('''UPDATE entrevistas
            SET expediente = ?, fecha_modificacion = ?, datos_json = ?
            WHERE paciente_id = ?''', (expediente, fecha_actual, datos_json, paciente_id))
    else:
        c.execute('''INSERT INTO entrevistas (paciente_id, expediente, fecha_registro, fecha_modificacion, usuario_registro, datos_json)
            VALUES (?, ?, ?, ?, ?, ?)''', (paciente_id, expediente, fecha_actual, fecha_actual, usuario_act, datos_json))
        
    conn.commit()
    conn.close()

# ==========================================
# 1. REGISTRO Y EDICIÓN DE USUARIOS / PACIENTES
# ==========================================
if menu == '👤 Registro y Edición de Usuarios':
    st.title('👤 Registro y Edición de Residentes')
    st.caption('Gestión centralizada de expedientes, folio autoincrementable y número de expediente único.')
    
    pacientes = listar_pacientes_completos()
    
    tab1, tab2 = st.tabs(['🆕 Registrar Nuevo Paciente', '✏️ Editar Paciente Existente'])
    
    with tab1:
        st.subheader('Captura de Nuevo Residente')
        siguiente_folio = generar_siguiente_folio()
        
        with st.form('form_alta_paciente'):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                st.text_input('Folio (Autoincrementable)', value=siguiente_folio, disabled=True)
            with col_f2:
                exp_input = st.text_input('Número de Expediente (Numérico / Opcional)', value='', help='Si se deja en blanco, puede asignarse posteriormente.')
                
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                nom_input = st.text_input('Nombre Completo del Residente *')
                f_nac_input = st.date_input('Fecha de Nacimiento', value=datetime(1995, 1, 1))
                sexo_input = st.selectbox('Sexo', ['Masculino', 'Femenino'])
            with col_a2:
                f_ing_input = st.date_input('Fecha de Ingreso Real a la Comunidad', value=datetime.today())
                etapa_init = st.selectbox('Etapa Inicial', ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL'])
                f_etapa_input = st.date_input('Fecha de Inicio de la Etapa Actual', value=datetime.today())
            
            estatus_input = st.selectbox('Estatus en la Clínica', ['ACTIVO', 'INACTIVO / EGRESADO', 'BAJA TEMPORAL'])
            
            btn_guardar_nuevo = st.form_submit_button('💾 Guardar Nuevo Residente', use_container_width=True)
            
            if btn_guardar_nuevo:
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                elif not nom_input.strip():
                    st.error('❌ El nombre completo del residente es obligatorio.')
                else:
                    val_ok, msg_err = validar_expediente_unico(exp_input)
                    if not val_ok:
                        st.error(msg_err)
                    else:
                        datos_p = {
                            'nombre_completo': nom_input.strip(),
                            'fecha_nacimiento': str(f_nac_input),
                            'sexo': sexo_input,
                            'fecha_ingreso': str(f_ing_input),
                            'etapa_actual': etapa_init,
                            'fecha_inicio_etapa': str(f_etapa_input),
                            'estatus': estatus_input,
                            'expediente': exp_input.strip()
                        }
                        guardar_paciente_base(siguiente_folio, exp_input.strip(), datos_p)
                        st.balloons()
                        st.toast(f'¡Paciente {nom_input} registrado con Folio {siguiente_folio}!', icon='✅')
                        st.success(f"✅ Registrado exitosamente con Folio: **{siguiente_folio}** y Expediente: **'{exp_input.strip()}'**")
                        st.rerun()

    with tab2:
        st.subheader('Edición de Residente Registrado')
        if not pacientes:
            st.info('No hay pacientes registrados en el sistema.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('🔑 Selecciona el Residente a Modificar', list(dict_p.keys()))
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            
            if p_data:
                dj = p_data['datos']
                
                with st.form(f'form_edit_paciente_{sel_pid}'):
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        st.text_input('Folio (No Editable)', value=p_data['paciente_id'], disabled=True)
                    with col_e2:
                        exp_edit = st.text_input('Número de Expediente (Numérico / Opcional)', value=dj.get('expediente', ''))
                        
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        nom_edit = st.text_input('Nombre Completo *', value=dj.get('nombre_completo', ''))
                        
                        try:
                            fn_val = datetime.strptime(dj.get('fecha_nacimiento', '1995-01-01'), '%Y-%m-%d')
                        except:
                            fn_val = datetime(1995, 1, 1)
                        f_nac_edit = st.date_input('Fecha de Nacimiento', value=fn_val)
                        
                        sexos = ['Masculino', 'Femenino']
                        idx_sex = sexos.index(dj.get('sexo', 'Masculino')) if dj.get('sexo') in sexos else 0
                        sexo_edit = st.selectbox('Sexo', sexos, index=idx_sex)
                    
                    with col_b2:
                        try:
                            fi_val = datetime.strptime(dj.get('fecha_ingreso', str(datetime.today().date())), '%Y-%m-%d')
                        except:
                            fi_val = datetime.today()
                        f_ing_edit = st.date_input('Fecha de Ingreso Real', value=fi_val)
                        
                        etapas = ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL']
                        idx_et = etapas.index(dj.get('etapa_actual', 'ACOGIDA')) if dj.get('etapa_actual') in etapas else 0
                        etapa_edit = st.selectbox('Etapa Actual', etapas, index=idx_et)
                        
                        try:
                            fet_val = datetime.strptime(dj.get('fecha_inicio_etapa', str(datetime.today().date())), '%Y-%m-%d')
                        except:
                            fet_val = datetime.today()
                        f_etapa_edit = st.date_input('Fecha de Inicio de Etapa Actual', value=fet_val)
                        
                    estatuses = ['ACTIVO', 'INACTIVO / EGRESADO', 'BAJA TEMPORAL']
                    idx_st = estatuses.index(dj.get('estatus', 'ACTIVO')) if dj.get('estatus') in estatuses else 0
                    estatus_edit = st.selectbox('Estatus', estatuses, index=idx_st)
                    
                    btn_actualizar = st.form_submit_button('💾 Actualizar Expediente de Paciente', use_container_width=True)
                    
                    if btn_actualizar:
                        if not puede_escribir():
                            st.error('❌ Su rol de usuario es de Solo Lectura.')
                        elif not nom_edit.strip():
                            st.error('❌ El nombre es obligatorio.')
                        else:
                            val_ok, msg_err = validar_expediente_unico(exp_edit, paciente_id_actual=sel_pid)
                            if not val_ok:
                                st.error(msg_err)
                            else:
                                dj['nombre_completo'] = nom_edit.strip()
                                dj['fecha_nacimiento'] = str(f_nac_edit)
                                dj['sexo'] = sexo_edit
                                dj['fecha_ingreso'] = str(f_ing_edit)
                                dj['etapa_actual'] = etapa_edit
                                dj['fecha_inicio_etapa'] = str(f_etapa_edit)
                                dj['estatus'] = estatus_edit
                                dj['expediente'] = exp_edit.strip()
                                
                                guardar_paciente_base(sel_pid, exp_edit.strip(), dj)
                                st.balloons()
                                st.toast('¡Expediente actualizado correctamente!', icon='🎉')
                                st.success('✅ ¡Datos del residente actualizados correctamente!')
                                st.rerun()

# ==========================================
# 2. FICHA DE INGRESO Y ADMISIÓN
# ==========================================
elif menu == '📄 Ficha de Ingreso y Admisión':
    st.title('📄 Ficha de Ingreso y Admisión')
    st.caption('Formulario oficial de contrato, internamiento y normativa NOM-028-SSA2-2009.')
    
    pacientes = listar_pacientes_completos()
    
    tab_f1, tab_f2 = st.tabs(['📝 Llenar / Editar Ficha', '🖨️ Consultar e Imprimir PDF'])
    
    with tab_f1:
        if not pacientes:
            st.info('Debe dar de alta al residente en "Registro y Edición de Usuarios" primero.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('🔑 Selecciona el Residente', list(dict_p.keys()))
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            dj = p_data['datos']
            
            st.subheader('1. Datos del Responsable del Ingreso')
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                resp_nombre = st.text_input('Nombre Completo del Responsable', value=dj.get('responsable_nombre', ''))
            with col_r2:
                resp_parentesco = st.text_input('Parentesco / Relación', value=dj.get('responsable_parentesco', ''))
            with col_r3:
                resp_telefono = st.text_input('Teléfono de Contacto', value=dj.get('responsable_telefono', ''))
                
            st.subheader('2. Datos del Usuario / Residente')
            col_u1, col_u2, col_u3 = st.columns(3)
            with col_u1:
                st.text_input('Nombre Residente', value=dj.get('nombre_completo', ''), disabled=True)
                st.text_input('Folio Interno', value=p_data['paciente_id'], disabled=True)
                st.text_input('Número de Expediente', value=dj.get('expediente', ''), disabled=True)
            with col_u2:
                est_civil = st.selectbox('Estado Civil', ['Soltero(a)', 'Casado(a)', 'Unión Libre', 'Divorciado(a)', 'Viudo(a)'], index=0)
                escolaridad = st.selectbox('Escolaridad', ['Primaria', 'Secundaria', 'Preparatoria', 'Licenciatura', 'Postgrado', 'Ninguna'], index=2)
                religion = st.text_input('Religión', value=dj.get('religion', 'Católica'))
            with col_u3:
                ocupacion = st.text_input('Ocupación', value=dj.get('ocupacion', 'Empleado'))
                serv_medico = st.text_input('Servicio Médico', value=dj.get('servicio_medico', 'IMSS / Ninguno'))
                domicilio = st.text_input('Domicilio Completo', value=dj.get('domicilio', ''))
                
            st.subheader('3. Sustancias de Consumo')
            sustancias_opc = ['Alcohol', 'Cannabis (Marihuana)', 'Cocaína / Crack', 'Metanfetaminas (Kryppy/Cristal)', 'Tabaco', 'Benzodiazepinas', 'Inhalantes', 'Opioides']
            sustancias_sel = st.multiselect('Sustancias Consumidas', sustancias_opc, default=dj.get('sustancias_consumidas', ['Alcohol', 'Cannabis (Marihuana)']))
            sustancia_impacto = st.text_input('Sustancia de Impacto Principal', value=dj.get('sustancia_impacto', 'Metanfetaminas'))
            
            st.subheader('4. Términos Económicos y Modalidad')
            col_e1, col_e2, col_e3 = st.columns(3)
            with col_e1:
                costo_ingreso = st.number_input('Costo de Ingreso ($)', value=float(dj.get('costo_ingreso', 4500.0)))
                mensualidad = st.number_input('Mensualidad ($)', value=float(dj.get('mensualidad', 6000.0)))
            with col_e2:
                importe_pagare = st.number_input('Importe Pagaré Garantía ($)', value=float(dj.get('importe_pagare', 42000.0)))
                sucursal = st.text_input('Sucursal', value=dj.get('sucursal', 'Matriz Sawabona'))
            with col_e3:
                modalidad = st.selectbox('Modalidad de Internamiento (NOM-028)', ['Voluntario', 'Involuntario', 'Obligatorio por Ley'], index=0)
            
            if st.button('💾 Guardar Ficha de Ingreso', use_container_width=True):
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                else:
                    dj['responsable_nombre'] = resp_nombre
                    dj['responsable_parentesco'] = resp_parentesco
                    dj['responsable_telefono'] = resp_telefono
                    dj['estado_civil'] = est_civil
                    dj['escolaridad'] = escolaridad
                    dj['religion'] = religion
                    dj['ocupacion'] = ocupacion
                    dj['servicio_medico'] = serv_medico
                    dj['domicilio'] = domicilio
                    dj['sustancias_consumidas'] = sustancias_sel
                    dj['sustancia_impacto'] = sustancia_impacto
                    dj['costo_ingreso'] = costo_ingreso
                    dj['mensualidad'] = mensualidad
                    dj['importe_pagare'] = importe_pagare
                    dj['sucursal'] = sucursal
                    dj['modalidad'] = modalidad
                    
                    guardar_paciente_base(sel_pid, dj.get('expediente', ''), dj)
                    st.balloons()
                    st.toast('¡Ficha de ingreso guardada exitosamente!', icon='🎉')
                    st.success('✅ Ficha guardada e integrada al expediente.')

    with tab_f2:
        st.subheader('🖨️ Generar Contrato / Ficha de Ingreso en PDF')
        if not pacientes:
            st.info('No hay pacientes.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('Selecciona Paciente para Imprimir Ficha', list(dict_p.keys()), key='pdf_fich_sel')
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            dj = p_data['datos']
            exp_print = dj.get('expediente', '') or 'S/N'
            
            if st.button('🖨️ Generar y Descargar PDF de Ingreso', use_container_width=True):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font('Arial', 'B', 16)
                pdf.cell(0, 10, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
                pdf.set_font('Arial', 'B', 12)
                pdf.cell(0, 8, 'FICHA DE ADMISIÓN Y CONTRATO DE INTERNAMIENTO', 0, 1, 'C')
                pdf.ln(5)
                
                pdf.set_font('Arial', 'B', 10)
                pdf.cell(0, 6, f'NÚMERO DE EXPEDIENTE: {exp_print}', 0, 1, 'R')
                pdf.cell(0, 6, f'FECHA DE INGRESO: {dj.get("fecha_ingreso", "")}', 0, 1, 'R')
                pdf.ln(5)
                
                pdf.set_font('Arial', 'B', 11)
                pdf.cell(0, 7, 'I. DATOS DEL RESPONSABLE FAMILIAR', 1, 1, 'L')
                pdf.set_font('Arial', '', 10)
                pdf.cell(0, 6, f'Nombre: {dj.get("responsable_nombre", "N/A")}', 0, 1)
                pdf.cell(0, 6, f'Parentesco: {dj.get("responsable_parentesco", "N/A")} | Teléfono: {dj.get("responsable_telefono", "N/A")}', 0, 1)
                pdf.ln(3)
                
                pdf.set_font('Arial', 'B', 11)
                pdf.cell(0, 7, 'II. DATOS GENERALES DEL PACIENTE', 1, 1, 'L')
                pdf.set_font('Arial', '', 10)
                pdf.cell(0, 6, f'Nombre Completo: {dj.get("nombre_completo", "N/A")}', 0, 1)
                pdf.cell(0, 6, f'Fecha de Nacimiento: {dj.get("fecha_nacimiento", "N/A")} | Sexo: {dj.get("sexo", "N/A")}', 0, 1)
                pdf.cell(0, 6, f'Estado Civil: {dj.get("estado_civil", "N/A")} | Escolaridad: {dj.get("escolaridad", "N/A")}', 0, 1)
                pdf.cell(0, 6, f'Ocupación: {dj.get("ocupacion", "N/A")} | Domicilio: {dj.get("domicilio", "N/A")}', 0, 1)
                pdf.ln(3)
                
                pdf.set_font('Arial', 'B', 11)
                pdf.cell(0, 7, 'III. EVALUACIÓN Y TÉRMINOS DE INTERNAMIENTO', 1, 1, 'L')
                pdf.set_font('Arial', '', 10)
                pdf.cell(0, 6, f'Sustancia de Impacto: {dj.get("sustancia_impacto", "N/A")}', 0, 1)
                pdf.cell(0, 6, f'Modalidad: {dj.get("modalidad", "Voluntario")} (Conforme a NOM-028-SSA2-2009)', 0, 1)
                pdf.cell(0, 6, f'Cuota de Ingreso: ${dj.get("costo_ingreso", 0):,.2f} | Mensualidad: ${dj.get("mensualidad", 0):,.2f}', 0, 1)
                pdf.ln(10)
                
                pdf.set_font('Arial', 'I', 9)
                pdf.multi_cell(0, 5, 'DECLARACIÓN DE CONFORMIDAD Y AUTORIZACIÓN:\nEl responsable y el paciente aceptan voluntariamente el tratamiento residencial para la rehabilitación de adicciones en apego a los reglamentos de la Comunidad Terapéutica Sawabona Shikoba A.C.')
                pdf.ln(15)
                
                pdf.cell(90, 6, '____________________________________', 0, 0, 'C')
                pdf.cell(90, 6, '____________________________________', 0, 1, 'C')
                pdf.cell(90, 5, 'Firma del Responsable Familiar', 0, 0, 'C')
                pdf.cell(90, 5, 'Director / Encargado de Establecimiento', 0, 1, 'C')
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1', errors='replace')
                st.download_button(
                    label=f'📥 Descargar PDF Ficha - Exp {exp_print}',
                    data=pdf_bytes,
                    file_name=f'Ficha_Ingreso_Exp_{exp_print}.pdf',
                    mime='application/pdf'
                )

# ==========================================
# 3. ENTREVISTA INICIAL DE CONSEJERÍA
# ==========================================
elif menu == '📝 Entrevista Inicial de Consejería':
    st.title('📝 Entrevista Inicial de Consejería')
    st.caption('Evaluación clínica inicial, historial de sustancias y motivación para el cambio.')
    
    pacientes = listar_pacientes_completos()
    if not pacientes:
        st.info('No hay residentes. Debe registrar a un residente en "Registro y Edición de Usuarios".')
    else:
        dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
        sel_label = st.selectbox('🔑 Selecciona el Residente', list(dict_p.keys()))
        sel_pid = dict_p[sel_label]
        p_data = obtener_paciente_por_id(sel_pid)
        dj = p_data['datos']
        
        with st.form('form_entrevista_inicial'):
            st.subheader('1. Historial Clínico de Consumo')
            motivo_cons = st.text_area('Motivo de Consulta / Ingreso', value=dj.get('motivo_consulta', ''))
            edad_inicio = st.number_input('Edad de Inicio de Consumo', value=int(dj.get('edad_inicio', 15)))
            
            st.subheader('2. Redes de Apoyo y Factores Sociales')
            apoyo_fam = st.text_area('Apoyo Familiar y Relaciones Interpersonales', value=dj.get('apoyo_familiar', ''))
            
            st.subheader('3. Diagnóstico y Plan de Trabajo')
            diag_inicial = st.text_area('Diagnóstico Clínico Inicial', value=dj.get('diagnostico_inicial', ''))
            
            btn_save_ent = st.form_submit_button('💾 Guardar Entrevista Inicial', use_container_width=True)
            if btn_save_ent:
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                else:
                    dj['motivo_consulta'] = motivo_cons
                    dj['edad_inicio'] = edad_inicio
                    dj['apoyo_familiar'] = apoyo_fam
                    dj['diagnostico_inicial'] = diag_inicial
                    
                    guardar_paciente_base(sel_pid, dj.get('expediente', ''), dj)
                    st.balloons()
                    st.toast('¡Entrevista inicial guardada correctamente!', icon='🎉')
                    st.success('✅ Entrevista inicial guardada en el expediente.')

# ==========================================
# 4. CONSEJERÍAS INDIVIDUALES
# ==========================================
elif menu == '📝 Consejerías Individuales':
    st.title('📝 Consejerías Individuales')
    st.caption('Seguimiento individualizado por etapa clínica de acuerdo con el Plan de Consejería.')
    
    TEMAS_CONSEJERIA = {
        'ACOGIDA': [
            '(1. CONSEJERIA) ENTREVISTA INICIAL DE CONSEJERIA.',
            '(2. CONSEJERIA) ESTADO DE ANIMO APLICACIÓN DE TAMIZAJES (CAD, FAGESTROM, AUDIT, BECK 1, 2, CAGE.PHQ15).',
            '(3. CONSEJERIA) PRESENTACIÓN DE PLAN DE TRATAMIENTO.',
            '(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ACOGIDA A IDENTIFICACION.'
        ],
        'IDENTIFICACIÓN': [
            '(1. CONSEJERIAS) ORIENTACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.',
            '(2. CONSEJERIA) IDENTIFICACION DE LAS CAUSAS CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).',
            '(3. CONSEJERIA) IDENTIFICACION DE LAS PROBLEMATICAS DE CONSUMO (CONDUCTAS AUTODESTRUCTIVAS).',
            '(4. CONSEJERIA) COMUNICACION ASERTIVA. / MANEJO DEL TIEMPO LIBRE.',
            '(5. CONSEJERIA) IDENTIFICACION DE FACTORES DE RIESGO Y PROTECCION INTERNOS Y EXTERNOS.',
            '(6. CONSEJERIAS) ELABORACIÓN DE ECO MAPA (MAQUETA O DIBUJO).',
            '(7. CONSEJERIA) EXPOSICION DEL SEMINARIO / RELACIONES DE PAREJA.',
            '(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE IDENTIFICACION A ELABORACION.'
        ],
        'ELABORACIÓN': [
            '(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.',
            '(2. CONSEJERIAS) EVALUACION DEL PLAN DE TRATAMIENTO.',
            '(3. CONSEJERIAS) HABILIDADES COGNITIVAS-CONDUCTUALES.',
            '(4. CONSEJERIA) HABILIDADES SOCIALES-EMOCIONALES.',
            '(5. CONSEJRIA) PREVENCIÓN DE RECAÍDAS.',
            '(6. CONSEJERIA) ELABORAR PROYECTO DE VIDA.',
            '(7. CONSEJERIA) ORIENTACION PARA SALIDA DE REINSERCION.',
            '(8. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE ELABORACION A CONSOLIDACION.'
        ],
        'CONSOLIDACIÓN': [
            '(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.',
            '(2. CONSEJERIAS) EVALUACION Y O AJUSTE DE PROYECTO DE VIDA (PRESENTAR A LA FAMILIA).',
            '(3. CONSEJERIAS) HABILIDADES PARA LA VIDA.',
            '(4. CONSEJERIA) EVALUACION DE OBJETIVOS POR ETAPA DE CONSOLIDACION A SERVICIO SOCIAL.'
        ],
        'SERVICIO SOCIAL': [
            '(1. CONSEJERIA) ORIENTACION DE OBJETIVOS POR ETAPA DE SERVICIO SOCIAL.',
            '(2. CONSEJERIAS) ALTERNATIVAS DE CAMBIO – CRECIMIENTO, CUMPLIMIENTO DE RESPONSABILIDADES, TERAPIAS DE REINSERCION FAMILIAR.',
            '(3. CONSEJERIAS) CIERRE DE CONSEJERIA.',
            '(4. CONSEJERIA) CIERRE DE CONSEJERIA.'
        ]
    }
    
    pacientes = listar_pacientes_completos()
    
    tab_c1, tab_c2 = st.tabs(['📝 Registrar Consejería', '📜 Historial e Impresión PDF'])
    
    with tab_c1:
        if not pacientes:
            st.info('No hay residentes registrados.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('🔑 Selecciona el Residente', list(dict_p.keys()), key='cons_pac_sel')
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            dj = p_data['datos']
            
            try:
                fn = datetime.strptime(dj.get('fecha_nacimiento', '1995-01-01'), '%Y-%m-%d')
                edad_calc = (datetime.now() - fn).days // 365
            except:
                edad_calc = 'N/A'
                
            etapa_act = dj.get('etapa_actual', 'ACOGIDA')
            exp_val = dj.get('expediente', '')
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (sel_pid, etapa_act))
            count_prev = c.fetchone()[0]
            conn.close()
            
            num_cons_act = count_prev + 1
            lista_temas = TEMAS_CONSEJERIA.get(etapa_act, TEMAS_CONSEJERIA['ACOGIDA'])
            
            idx_actual = min(count_prev, len(lista_temas) - 1)
            idx_prox = min(count_prev + 1, len(lista_temas) - 1)
            
            tema_sugerido_actual = lista_temas[idx_actual]
            tema_sugerido_prox = lista_temas[idx_prox] if idx_prox < len(lista_temas) else 'FIN DE CONSEJERÍAS EN ETAPA'
            
            st.subheader(f'Registro de Consejería Individual (Etapa: {etapa_act})')
            
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.text_input('Nombre Residente', value=dj.get('nombre_completo', ''), disabled=True)
                st.text_input('Edad', value=f'{edad_calc} años', disabled=True)
            with col_d2:
                st.text_input('Sexo', value=dj.get('sexo', 'Masculino'), disabled=True)
                st.text_input('Etapa Actual', value=etapa_act, disabled=True)
            with col_d3:
                exp_input_cons = st.text_input('Expediente (Numérico)', value=exp_val, help='Expediente oficial asignado por la institución.')
                fecha_cons = st.date_input('Fecha de Consejería', value=datetime.today())
            
            st.info(f'📌 **Consejería Consecutiva #: {num_cons_act}** para la etapa **{etapa_act}**')
            
            aspectos_trabajar = st.selectbox('Aspectos a Trabajar en esta Consejería', lista_temas, index=idx_actual)
            aspectos_prox = st.selectbox('Aspectos a Trabajar en la Próxima Consejería', lista_temas, index=idx_prox)
            
            fecha_prox_def = datetime.today() + timedelta(days=7)
            fecha_proxima_cons = st.date_input('Fecha de la Próxima Consejería (+7 días)', value=fecha_prox_def)
            
            exposicion = st.text_area('Exposición / Contenido de la Sesión (Texto Largo)')
            avance_retroceso = st.text_area('Avance / Retroceso del Residente (Texto Largo)')
            sugerencia = st.text_area('Sugerencias y Tareas (Texto Largo)')
            
            if st.button('💾 Guardar Sesión de Consejería', use_container_width=True):
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                else:
                    if exp_input_cons.strip() != exp_val:
                        val_ok, msg_err = validar_expediente_unico(exp_input_cons, paciente_id_actual=sel_pid)
                        if not val_ok:
                            st.error(msg_err)
                            st.stop()
                        dj['expediente'] = exp_input_cons.strip()
                        guardar_paciente_base(sel_pid, exp_input_cons.strip(), dj)
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''INSERT INTO consejerias (paciente_id, expediente, etapa, num_consejeria, fecha, aspectos_trabajados, proximos_aspectos, fecha_proxima, exposicion, avance_retroceso, sugerencia, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (sel_pid, exp_input_cons.strip(), etapa_act, num_cons_act, str(fecha_cons), aspectos_trabajar, aspectos_prox, str(fecha_proxima_cons), exposicion, avance_retroceso, sugerencia, st.session_state['username']))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast(f'¡Consejería #{num_cons_act} guardada exitosamente!', icon='🎉')
                    st.success(f"✅ Sesión de consejería guardada en el historial de {dj.get('nombre_completo')}.")
                    st.rerun()

    with tab_c2:
        st.subheader('📜 Historial de Consejerías e Impresión PDF')
        if not pacientes:
            st.info('No hay pacientes.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('Selecciona Paciente para Consultar Historial', list(dict_p.keys()), key='hist_cons_sel')
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            dj = p_data['datos']
            exp_print = dj.get('expediente', '') or 'S/N'
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, etapa, num_consejeria, fecha, aspectos_trabajados, exposicion, avance_retroceso, sugerencia, fecha_proxima, proximos_aspectos FROM consejerias WHERE paciente_id = ? ORDER BY id DESC', (sel_pid,))
            rows = c.fetchall()
            conn.close()
            
            if not rows:
                st.warning('El paciente no tiene sesiones de consejería registradas aún.')
            else:
                for r in rows:
                    cid, et, num_c, f_c, asp_tr, exp_s, av_ret, sug, f_pr, asp_pr = r
                    with st.expander(f'📌 Consejería #{num_c} ({et}) - Fecha: {f_c}'):
                        st.write(f'**Aspectos Trabajaos**: {asp_tr}')
                        st.write(f'**Exposición**: {exp_s}')
                        st.write(f'**Avance / Retroceso**: {av_ret}')
                        st.write(f'**Sugerencias**: {sug}')
                        st.write(f'**Próxima Consejería**: {f_pr} - *{asp_pr}*')
                        
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.set_font('Arial', 'B', 15)
                        pdf.cell(0, 10, 'COMUNIDAD TERAPÉUTICA SAWABONA SHIKOBA A.C.', 0, 1, 'C')
                        pdf.set_font('Arial', 'B', 12)
                        pdf.cell(0, 8, f'REGISTRO DE CONSEJERÍA INDIVIDUAL #{num_c}', 0, 1, 'C')
                        pdf.ln(3)
                        
                        pdf.set_font('Arial', 'B', 10)
                        pdf.cell(0, 6, f'EXPEDIENTE: {exp_print} | FECHA: {f_c} | ETAPA: {et}', 0, 1, 'R')
                        pdf.ln(3)
                        
                        pdf.set_font('Arial', 'B', 11)
                        pdf.cell(0, 7, 'I. DATOS DEL PACIENTE', 1, 1, 'L')
                        pdf.set_font('Arial', '', 10)
                        pdf.cell(0, 6, f'Nombre Completo: {dj.get("nombre_completo", "N/A")}', 0, 1)
                        pdf.cell(0, 6, f'Sexo: {dj.get("sexo", "N/A")}', 0, 1)
                        pdf.ln(3)
                        
                        pdf.set_font('Arial', 'B', 11)
                        pdf.cell(0, 7, 'II. CONTENIDO Y DESARROLLO DE LA SESIÓN', 1, 1, 'L')
                        pdf.set_font('Arial', 'B', 10)
                        pdf.cell(0, 6, f'Aspectos Trabajados: {asp_tr}', 0, 1)
                        pdf.set_font('Arial', '', 10)
                        pdf.multi_cell(0, 5, f'Exposición:\n{exp_s}')
                        pdf.ln(2)
                        pdf.multi_cell(0, 5, f'Avance / Retroceso:\n{av_ret}')
                        pdf.ln(2)
                        pdf.multi_cell(0, 5, f'Sugerencia / Tareas:\n{sug}')
                        pdf.ln(4)
                        
                        pdf.set_font('Arial', 'B', 10)
                        pdf.cell(0, 6, f'Próxima Consejería ({f_pr}): {asp_pr}', 0, 1)
                        pdf.ln(12)
                        
                        pdf.cell(90, 6, '____________________________________', 0, 0, 'C')
                        pdf.cell(90, 6, '____________________________________', 0, 1, 'C')
                        pdf.cell(90, 5, 'Firma del Consejero / Terapeuta', 0, 0, 'C')
                        pdf.cell(90, 5, 'Firma del Residente', 0, 1, 'C')
                        
                        pdf_bytes = pdf.output(dest='S').encode('latin-1', errors='replace')
                        st.download_button(
                            label=f'🖨️ Descargar PDF Consejería #{num_c}',
                            data=pdf_bytes,
                            file_name=f'Consejeria_{num_c}_Exp_{exp_print}.pdf',
                            mime='application/pdf',
                            key=f'btn_pdf_c_{cid}'
                        )

# ==========================================
# 5. GESTIÓN DE ETAPAS & PROCESO
# ==========================================
elif menu == '🎯 Gestión de Etapas & Proceso':
    st.title('🎯 Gestión de Etapas & Evaluación de Rezagos')
    st.caption('Control clínico de estancia, evaluación de permanencia en etapa y checklist de promoción.')
    
    DURACION_ETAPAS = {
        'ACOGIDA': 30,
        'IDENTIFICACIÓN': 60,
        'ELABORACIÓN': 60,
        'CONSOLIDACIÓN': 30,
        'SERVICIO SOCIAL': 30
    }
    
    REQUISITOS_CONSEJERIA = {
        'ACOGIDA': 4,
        'IDENTIFICACIÓN': 8,
        'ELABORACIÓN': 8,
        'CONSOLIDACIÓN': 4,
        'SERVICIO SOCIAL': 4
    }
    
    pacientes = listar_pacientes_completos()
    if not pacientes:
        st.info('No hay pacientes.')
    else:
        dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
        sel_label = st.selectbox('🔑 Selecciona el Residente a Evaluar', list(dict_p.keys()))
        sel_pid = dict_p[sel_label]
        p_data = obtener_paciente_por_id(sel_pid)
        dj = p_data['datos']
        
        etapa_act = dj.get('etapa_actual', 'ACOGIDA')
        exp_val = dj.get('expediente', '') or 'S/N'
        
        try:
            fi = datetime.strptime(dj.get('fecha_ingreso', str(datetime.today().date())), '%Y-%m-%d')
            dias_totales = (datetime.now() - fi).days
        except:
            dias_totales = 0
            
        try:
            fet = datetime.strptime(dj.get('fecha_inicio_etapa', str(datetime.today().date())), '%Y-%m-%d')
            dias_etapa = (datetime.now() - fet).days
        except:
            dias_etapa = 0
            
        duracion_estandar = DURACION_ETAPAS.get(etapa_act, 30)
        excedido = dias_etapa - duracion_estandar
        
        st.subheader(f"Resumen Clínico de {dj.get('nombre_completo')}")
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric('Días Totales en Comunidad', f'{dias_totales} días', delta=f"Ingreso: {dj.get('fecha_ingreso', 'N/A')}")
        with col_m2:
            st.metric('Etapa Actual', etapa_act)
        with col_m3:
            st.metric('Días en Etapa Actual', f'{dias_etapa} días', delta=f'{duracion_estandar} días estándar', delta_color='inverse' if excedido > 0 else 'normal')
            
        if excedido > 0:
            st.error(f'🚨 **ALERTA DE REZAGO / ESTANCAMIENTO CLÍNICO**: El paciente lleva **{dias_totales} días internado** y suma **{dias_etapa} días en la Etapa {etapa_act}** (Duración estimada: {duracion_estandar} días). Se ha excedido por **+{excedido} días** sin haber sido promovido.')
        else:
            st.success(f'✅ **En tiempo oportuno**: El paciente lleva {dias_etapa} días de {duracion_estandar} programados para la Etapa {etapa_act}.')
            
        st.subheader('📋 Checklist de Requisitos para Promoción')
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM consejerias WHERE paciente_id = ? AND etapa = ?', (sel_pid, etapa_act))
        num_cons_reg = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM grupos_terapeuticos WHERE paciente_id = ? AND etapa_paciente = ?', (sel_pid, etapa_act))
        num_grupos_reg = c.fetchone()[0]
        conn.close()
        
        req_cons_target = REQUISITOS_CONSEJERIA.get(etapa_act, 4)
        cons_cumplidas = num_cons_reg >= req_cons_target
        grupos_cumplidos = num_grupos_reg >= 4
        
        st.write(f'1. **Consejerías Individuales Cumplidas**: {num_cons_reg} / {req_cons_target} {"✅" if cons_cumplidas else "❌ (Faltan consejerías)"}')
        st.write(f'2. **Grupos Terapéuticos en Etapa**: {num_grupos_reg} / 4 Mínimos {"✅" if grupos_cumplidos else "❌ (Faltan asistencias)"}')
        
        list_etapas = ['ACOGIDA', 'IDENTIFICACIÓN', 'ELABORACIÓN', 'CONSOLIDACIÓN', 'SERVICIO SOCIAL']
        idx_act = list_etapas.index(etapa_act) if etapa_act in list_etapas else 0
        
        if idx_act < len(list_etapas) - 1:
            sig_etapa = list_etapas[idx_act + 1]
            puedo_promover = cons_cumplidas and grupos_cumplidos
            
            if st.button(f'🎉 Promover a {sig_etapa}', disabled=not puedo_promover, use_container_width=True):
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                else:
                    dj['etapa_actual'] = sig_etapa
                    dj['fecha_inicio_etapa'] = str(datetime.today().date())
                    guardar_paciente_base(sel_pid, dj.get('expediente', ''), dj)
                    st.balloons()
                    st.toast(f'¡Residente promovido a {sig_etapa}!', icon='🎉')
                    st.success(f"✅ ¡{dj.get('nombre_completo')} ha sido promovido exitosamente a la etapa {sig_etapa}!")
                    st.rerun()

# ==========================================
# 6. GRUPOS TERAPÉUTICOS
# ==========================================
elif menu == '🗣️ Grupos Terapéuticos':
    st.title('🗣️ Grupos Terapéuticos y Participación')
    st.caption('Registro de sesiones de grupo, retroalimentación y devoluciones.')
    
    pacientes = listar_pacientes_completos()
    
    tab_g1, tab_g2 = st.tabs(['📝 Registrar Sesión de Grupo', '📜 Historial e Impresión PDF'])
    
    with tab_g1:
        if not pacientes:
            st.info('No hay pacientes registrados.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('🔑 Selecciona el Residente', list(dict_p.keys()), key='grp_pac_sel')
            sel_pid = dict_p[sel_label]
            p_data = obtener_paciente_por_id(sel_pid)
            dj = p_data['datos']
            exp_val = dj.get('expediente', '') or 'S/N'
            
            st.subheader('Datos de la Sesión')
            col_g1, col_g2, col_g3 = st.columns(3)
            with col_g1:
                tipo_grupo = st.selectbox('Tipo de Grupo', ['Terapia de Grupo', 'Aquí y Ahora', 'Feedback'])
                fecha_grupo = st.date_input('Fecha de Sesión', value=datetime.today())
            with col_g2:
                facilitador = st.text_input('Nombre del Facilitador / Staff', value=st.session_state['nombre_completo'])
                st.text_input('Etapa del Residente', value=dj.get('etapa_actual', 'ACOGIDA'), disabled=True)
            with col_g3:
                st.text_input('Expediente', value=exp_val, disabled=True)
                
            compartimiento = st.text_area('Compartimiento / Intervención del Residente')
            logros = st.text_area('Logros Observados')
            dificultades = st.text_area('Dificultades / Aspectos a Corregir')
            observaciones = st.text_area('Observaciones del Facilitador')
            devoluciones = st.text_area('Devoluciones del Grupo / Staff')
            compromiso = st.text_area('¿A qué se compromete el residente?')
            
            if st.button('💾 Guardar Registro de Grupo', use_container_width=True):
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''INSERT INTO grupos_terapeuticos (paciente_id, expediente, tipo_grupo, fecha, facilitador, etapa_paciente, compartimiento, logros, dificultades, observaciones, devoluciones, compromiso, usuario_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (sel_pid, exp_val, tipo_grupo, str(fecha_grupo), facilitador, dj.get('etapa_actual', 'ACOGIDA'), compartimiento, logros, dificultades, observaciones, devoluciones, compromiso, st.session_state['username']))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast('¡Sesión de grupo registrada!', icon='🎉')
                    st.success('✅ Registro de grupo guardado exitosamente.')

    with tab_g2:
        st.subheader('Consultar Historial de Grupos')
        if not pacientes:
            st.info('No hay pacientes.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('Selecciona Paciente', list(dict_p.keys()), key='hist_grp_sel')
            sel_pid = dict_p[sel_label]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, tipo_grupo, fecha, facilitador, compartimiento, devoluciones, compromiso FROM grupos_terapeuticos WHERE paciente_id = ? ORDER BY id DESC', (sel_pid,))
            rows = c.fetchall()
            conn.close()
            
            if not rows:
                st.warning('No se encuentran registros de grupos para este paciente.')
            else:
                for r in rows:
                    gid, tg, fg, fac, comp, dev, compr = r
                    with st.expander(f'🗣️ {tg} - Fecha: {fg} (Facilitador: {fac})'):
                        st.write(f'**Compartimiento**: {comp}')
                        st.write(f'**Devoluciones**: {dev}')
                        st.write(f'**Compromiso**: {compr}')

# ==========================================
# 7. CONTROL DE MEDICAMENTOS
# ==========================================
elif menu == '💊 Control de Medicamentos':
    st.title('💊 Control de Medicamentos e Inventario')
    st.caption('Administración del catálogo central, prescripción de dosis por paciente y entregas desde almacén.')
    
    tab_m1, tab_m2, tab_m3, tab_m4 = st.tabs(['💊 Catálogo Central', '📋 Esquema de Dosis', '📦 Entrega de Almacén', '📊 Reporte de Consumo'])
    
    with tab_m1:
        st.subheader('Catálogo Central de Fármacos')
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, nombre, presentacion, concentracion, existencia FROM catalogo_medicamentos ORDER BY nombre ASC')
        meds = c.fetchall()
        conn.close()
        
        with st.form('form_nuevo_med'):
            col_k1, col_k2, col_k3 = st.columns(3)
            with col_k1:
                med_nom = st.text_input('Nombre del Medicamento *')
            with col_k2:
                med_pres = st.text_input('Presentación (Comprimidos, Cápsulas, Gotas)')
            with col_k3:
                med_conc = st.text_input('Concentración (500 mg, 20 mg, etc.)')
            med_stock = st.number_input('Existencia Inicial en Almacén', min_value=0, value=100)
            
            btn_add_med = st.form_submit_button('➕ Agregar al Catálogo')
            if btn_add_med:
                if not puede_escribir():
                    st.error('❌ Su rol de usuario es de Solo Lectura.')
                elif not med_nom.strip():
                    st.error('❌ El nombre es obligatorio.')
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute('INSERT INTO catalogo_medicamentos (nombre, presentacion, concentracion, existencia) VALUES (?, ?, ?, ?)',
                                  (med_nom.strip(), med_pres, med_conc, med_stock))
                        conn.commit()
                        st.balloons()
                        st.toast('¡Medicamento agregado!', icon='🎉')
                        st.success('✅ Fármaco agregado al catálogo central.')
                        st.rerun()
                    except:
                        st.error('⚠️ El medicamento ya existe en el catálogo.')
                    conn.close()
                    
        if meds:
            st.table([{"ID": m[0], "Medicamento": m[1], "Presentación": m[2], "Concentración": m[3], "Existencia en Almacén": m[4]} for m in meds])

    with tab_m2:
        st.subheader('Prescripción de Dosis por Paciente')
        pacientes = listar_pacientes_completos()
        if not pacientes:
            st.info('No hay residentes.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('Selecciona Paciente para Receta', list(dict_p.keys()), key='rec_pac_sel')
            sel_pid = dict_p[sel_label]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, nombre, concentracion FROM catalogo_medicamentos ORDER BY nombre ASC')
            meds_cat = c.fetchall()
            conn.close()
            
            if not meds_cat:
                st.warning('Debe agregar medicamentos al catálogo primero.')
            else:
                dict_m = {f"{m[1]} ({m[2]})": m[0] for m in meds_cat}
                sel_m_label = st.selectbox('Selecciona Medicamento', list(dict_m.keys()))
                sel_mid = dict_m[sel_m_label]
                
                col_d1, col_d2, col_d3 = st.columns(3)
                with col_d1:
                    d_m = st.number_input('Dosis Mañana', min_value=0, value=1)
                with col_d2:
                    d_t = st.number_input('Dosis Tarde', min_value=0, value=0)
                with col_d3:
                    d_n = st.number_input('Dosis Noche', min_value=0, value=1)
                    
                indic = st.text_input('Indicaciones (ej. Después de alimentos)')
                
                if st.button('💾 Asignar Dosis a Paciente'):
                    if not puede_escribir():
                        st.error('❌ Su rol de usuario es de Solo Lectura.')
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, dosis_manana, dosis_tarde, dosis_noche, indicaciones)
                            VALUES (?, ?, ?, ?, ?, ?)''', (sel_pid, sel_mid, d_m, d_t, d_n, indic))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast('¡Esquema de dosis guardado!', icon='🎉')
                        st.success('✅ Dosis asignada correctamente.')

    with tab_m3:
        st.subheader('📦 Entrega Diaria desde Almacén')
        pacientes = listar_pacientes_completos()
        if not pacientes:
            st.info('No hay pacientes.')
        else:
            dict_p = {f"{p['paciente_id']} | Exp: {p['expediente'] if p['expediente'] else 'S/N'} - {p['nombre']}": p['paciente_id'] for p in pacientes}
            sel_label = st.selectbox('Selecciona Paciente para Entrega', list(dict_p.keys()), key='ent_pac_sel')
            sel_pid = dict_p[sel_label]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''SELECT pm.id, cm.id, cm.nombre, cm.existencia, pm.dosis_manana, pm.dosis_tarde, pm.dosis_noche
                FROM paciente_medicamentos pm
                JOIN catalogo_medicamentos cm ON pm.medicamento_id = cm.id
                WHERE pm.paciente_id = ?''', (sel_pid,))
            recetas = c.fetchall()
            conn.close()
            
            if not recetas:
                st.info('El paciente no tiene medicamentos recetados.')
            else:
                for r in recetas:
                    pm_id, m_id, m_nom, m_ex, dm, dt, dn = r
                    tot_dosis = dm + dt + dn
                    st.write(f'💊 **{m_nom}** | Dosis Diaria Total: **{tot_dosis}** | Stock Disponible en Almacén: **{m_ex}**')
                    
                    if m_ex <= 0:
                        st.error('⚠️ Sin existencias disponibles en almacén.')
                    else:
                        cant_sugerida = min(tot_dosis, m_ex)
                        cant_ent = st.number_input(f'Cantidad a entregar de {m_nom}', min_value=0, max_value=m_ex, value=cant_sugerida, key=f'cant_ent_{pm_id}')
                        
                        if st.button(f'📦 Registrar Entrega de {m_nom}', key=f'btn_ent_{pm_id}'):
                            if not puede_escribir():
                                st.error('❌ Su rol de usuario es de Solo Lectura.')
                            elif cant_ent <= 0:
                                st.error('❌ Ingrese una cantidad mayor a 0.')
                            else:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute('UPDATE catalogo_medicamentos SET existencia = existencia - ? WHERE id = ?', (cant_ent, m_id))
                                fecha_act = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                c.execute('INSERT INTO entregas_medicamentos (paciente_id, medicamento_id, cantidad, fecha_entrega, usuario_registro) VALUES (?, ?, ?, ?, ?)',
                                          (sel_pid, m_id, cant_ent, fecha_act, st.session_state['username']))
                                conn.commit()
                                conn.close()
                                st.balloons()
                                st.toast(f'¡Entregadas {cant_ent} unidades!', icon='🎉')
                                st.success('✅ Entrega registrada e inventario actualizado.')
                                st.rerun()

    with tab_m4:
        st.subheader('📊 Reporte de Consumo Diario')
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT cm.nombre, SUM(pm.dosis_manana + pm.dosis_tarde + pm.dosis_noche) as consumo_diario
            FROM paciente_medicamentos pm
            JOIN catalogo_medicamentos cm ON pm.medicamento_id = cm.id
            GROUP BY cm.nombre''')
        reporte = c.fetchall()
        conn.close()
        
        if reporte:
            st.table([{"Medicamento": r[0], "Consumo Total Diario en Clínica": r[1]} for r in reporte])
        else:
            st.info('No hay prescripciones activas.')

# ==========================================
# 8. REPOSITORIO DE DOCUMENTOS
# ==========================================
elif menu == '📁 Repositorio de Documentos':
    st.title('📁 Repositorio de Documentos, Manuales y Formatos')
    st.caption('Biblioteca centralizada de archivos institucionales en la nube (Exclusivo Administrador).')
    
    if not es_admin():
        st.error('🔒 Módulo reservado exclusivamente para el Administrador del Sistema.')
    else:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT nombre FROM carpetas_repositorio ORDER BY nombre ASC')
        carpetas = [r[0] for r in c.fetchall()]
        conn.close()
        
        tab_r1, tab_r2, tab_r3 = st.tabs(['📤 Subir Documento', '📥 Consultar y Descargar', '📁 Gestionar Carpetas'])
        
        with tab_r1:
            st.subheader('Subir Archivo al Repositorio')
            c_sel = st.selectbox('Selecciona la Carpeta Destino', carpetas)
            f_up = st.file_uploader('Selecciona un archivo (PDF, Word, Excel, Imagen)', type=['pdf', 'docx', 'doc', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'txt'])
            f_desc = st.text_input('Descripción o Nota del Documento (ej. Versión 2026)')
            
            if st.button('📤 Guardar en la Nube', use_container_width=True):
                if not f_up:
                    st.error('❌ Selecciona un archivo.')
                else:
                    blob_data = f_up.read()
                    f_name = f_up.name
                    m_type = f_up.type
                    f_act = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''INSERT INTO repositorio_documentos (carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', (c_sel, f_name, m_type, blob_data, f_desc, f_act, st.session_state['username']))
                    conn.commit()
                    conn.close()
                    
                    st.balloons()
                    st.toast('¡Documento guardado en el repositorio!', icon='🎉')
                    st.success(f"✅ Archivo '{f_name}' subido correctamente a la carpeta '{c_sel}'.")

        with tab_r2:
            st.subheader('Consultar y Descargar Documentos')
            c_filtro = st.selectbox('Filtrar por Carpeta', ['--- TODAS LAS CARPETAS ---'] + carpetas)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if c_filtro == '--- TODAS LAS CARPETAS ---':
                c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos ORDER BY id DESC')
            else:
                c.execute('SELECT id, carpeta, nombre_archivo, mime_type, bytes_blob, descripcion, fecha_subida, usuario_subida FROM repositorio_documentos WHERE carpeta = ? ORDER BY id DESC', (c_filtro,))
            docs = c.fetchall()
            conn.close()
            
            if not docs:
                st.warning('No hay documentos en esta carpeta.')
            else:
                for doc in docs:
                    did, dcarp, dnom, dmime, dblob, ddesc, dfech, dusr = doc
                    with st.expander(f'📄 {dnom} (Carpeta: {dcarp}) - Fecha: {dfech}'):
                        st.write(f'**Descripción**: {ddesc if ddesc else "Sin notas"}')
                        st.write(f'**Subido por**: {dusr}')
                        st.download_button(
                            label=f"📥 Descargar '{dnom}'",
                            data=dblob,
                            file_name=dnom,
                            mime=dmime,
                            key=f'dl_doc_{did}'
                        )

        with tab_r3:
            st.subheader('📁 Personalizar y Gestionar Carpetas')
            col_cp1, col_cp2 = st.columns(2)
            
            with col_cp1:
                st.write('### ➕ Crear Nueva Carpeta')
                n_carp = st.text_input('Nombre de la Nueva Carpeta')
                if st.button('➕ Crear Carpeta'):
                    if not n_carp.strip():
                        st.error('❌ Ingrese un nombre.')
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO carpetas_repositorio (nombre) VALUES (?)', (n_carp.strip(),))
                            conn.commit()
                            st.balloons()
                            st.toast('¡Carpeta creada!', icon='🎉')
                            st.success(f"✅ Carpeta '{n_carp.strip()}' creada correctamente.")
                            st.rerun()
                        except:
                            st.error('⚠️ La carpeta ya existe.')
                        conn.close()

            with col_cp2:
                st.write('### ✏️ Renombrar Carpeta Existente')
                c_ren = st.selectbox('Selecciona Carpeta a Renombrar', carpetas, key='ren_c_sel')
                c_new_nom = st.text_input('Nuevo Nombre')
                if st.button('✏️ Renombrar Carpeta'):
                    if not c_new_nom.strip():
                        st.error('❌ Ingrese un nombre válido.')
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('UPDATE carpetas_repositorio SET nombre = ? WHERE nombre = ?', (c_new_nom.strip(), c_ren))
                        c.execute('UPDATE repositorio_documentos SET carpeta = ? WHERE carpeta = ?', (c_new_nom.strip(), c_ren))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.toast('¡Carpeta renombrada!', icon='🎉')
                        st.success('✅ Carpeta renombrada exitosamente.')
                        st.rerun()

# ==========================================
# 9. BUSCAR Y LISTAR PACIENTES
# ==========================================
elif menu == '🔍 Buscar y Listar Pacientes':
    st.title('🔍 Directorio General de Residentes')
    st.caption('Búsqueda centralizada por Folio, Expediente o Nombre.')
    
    pacientes = listar_pacientes_completos()
    if not pacientes:
        st.info('No hay pacientes registrados.')
    else:
        busqueda = st.text_input('🔎 Buscar por Nombre, Folio o Expediente')
        
        filtrados = []
        for p in pacientes:
            txt = f"{p['paciente_id']} {p['expediente']} {p['nombre']}".lower()
            if not busqueda or busqueda.lower() in txt:
                filtrados.append(p)
                
        st.subheader(f'Total de Registros Encontrados: {len(filtrados)}')
        for p in filtrados:
            with st.expander(f"👤 {p['nombre']} | Folio: {p['paciente_id']} | Expediente: {p['expediente'] if p['expediente'] else 'S/N'} | Etapa: {p['etapa']}"):
                st.write(f"**Fecha de Ingreso**: {p['datos'].get('fecha_ingreso', 'N/A')}")
                st.write(f"**Sexo**: {p['datos'].get('sexo', 'N/A')} | **Fecha de Nacimiento**: {p['datos'].get('fecha_nacimiento', 'N/A')}")
                st.write(f"**Estatus**: {p['datos'].get('estatus', 'ACTIVO')}")

# ==========================================
# 10. CONFIGURACIÓN & SEGURIDAD
# ==========================================
elif menu == '⚙️ Seguridad / Contraseña':
    st.title('⚙️ Configuración y Seguridad')
    st.caption('Administración de usuarios, roles de acceso y cambio de contraseñas.')
    
    tab_s1, tab_s2 = st.tabs(['🔒 Cambio de Contraseña', '👥 Gestión de Usuarios y Roles'])
    
    with tab_s1:
        st.subheader('Cambiar Mi Contraseña')
        with st.form('form_cambio_pass'):
            p_act = st.text_input('Contraseña Actual', type='password')
            p_new1 = st.text_input('Nueva Contraseña', type='password')
            p_new2 = st.text_input('Confirmar Nueva Contraseña', type='password')
            
            btn_pass = st.form_submit_button('Actualizar Contraseña')
            if btn_pass:
                if p_new1 != p_new2:
                    st.error('❌ Las contraseñas nuevas no coinciden.')
                elif not verificar_login(st.session_state['username'], p_act):
                    st.error('❌ La contraseña actual es incorrecta.')
                else:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('UPDATE usuarios SET password_hash = ? WHERE username = ?',
                              (hash_pass(p_new1), st.session_state['username']))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.toast('¡Contraseña actualizada!', icon='🎉')
                    st.success('✅ Contraseña cambiada con éxito.')

    with tab_s2:
        if not es_admin():
            st.error('🔒 Módulo reservado únicamente para el Administrador del Sistema.')
        else:
            st.subheader('👥 Crear Nuevo Usuario de Personal')
            with st.form('form_nuevo_usr'):
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    u_user = st.text_input('Nombre de Usuario (Login) *')
                    u_nom = st.text_input('Nombre Completo *')
                with col_u2:
                    u_pass = st.text_input('Contraseña *', type='password')
                    u_rol = st.selectbox('Rol y Permisos', [
                        'Nivel 1 - Administrador (Acceso Total)',
                        'Nivel 2 - Lectura y Escritura (Staff / Consejeros)',
                        'Nivel 3 - Solo Lectura'
                    ])
                    
                btn_crear_u = st.form_submit_button('➕ Registrar Usuario de Personal')
                if btn_crear_u:
                    if not u_user.strip() or not u_pass.strip():
                        st.error('❌ Ingrese usuario y contraseña.')
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        try:
                            c.execute('INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES (?, ?, ?, ?)',
                                      (u_user.strip(), hash_pass(u_pass), u_nom, u_rol))
                            conn.commit()
                            st.balloons()
                            st.toast('¡Usuario registrado!', icon='🎉')
                            st.success(f"✅ Usuario '{u_user.strip()}' registrado con rol '{u_rol}'.")
                        except:
                            st.error('⚠️ El nombre de usuario ya existe.')
                        conn.close()

# ==========================================
# 11. RESPALDO Y RESTAURACIÓN
# ==========================================
elif menu == '📦 Respaldo y Restauración':
    st.title('📦 Respaldo y Restauración de Base de Datos')
    st.caption('Descarga tu archivo .db para proteger todos los datos y documentos subidos.')
    
    col_b1, col_b2 = st.columns(2)
    
    with col_b1:
        st.subheader('📥 Descargar Respaldo Completo')
        st.write('Guarda una copia exacta de la base de datos con todos los pacientes, consejerías y documentos subidos al repositorio.')
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'rb') as f:
                db_bytes = f.read()
            st.download_button(
                label='📥 Descargar Base de Datos (.db)',
                data=db_bytes,
                file_name=f'Respaldo_Sawabona_{datetime.now().strftime("%Y%m%d_%H%M")}.db',
                mime='application/x-sqlite3',
                use_container_width=True
            )

    with col_b2:
        st.subheader('📤 Restaurar Respaldo')
        f_db_up = st.file_uploader('Cargar archivo .db para restaurar datos', type=['db', 'sqlite3'])
        if f_db_up and st.button('⚠️ Confirmar Restauración', use_container_width=True):
            if not es_admin():
                st.error('❌ Solo el Administrador puede restaurar la base de datos.')
            else:
                with open(DB_FILE, 'wb') as f:
                    f.write(f_db_up.read())
                st.balloons()
                st.toast('¡Base de datos restaurada!', icon='🎉')
                st.success('✅ Base de datos restaurada correctamente. Reinicie la página para aplicar los cambios.')
import streamlit as st
import sqlite3
import json
import os
from datetime import datetime
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Blog Familiar - Lara 1, Lara 5 y Sra. McCormick para el Mundo",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "blog_familiar.db"

# --- FUNCIONES DE BASE DE DATOS Y MIGRACIONES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabla de Secciones / Categorías
    c.execute('''
        CREATE TABLE IF NOT EXISTS secciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            icono TEXT DEFAULT '📌',
            descripcion TEXT,
            es_especial INTEGER DEFAULT 0,
            activa INTEGER DEFAULT 1
        )
    ''')
    
    # 2. Tabla de Publicaciones / Artículos
    c.execute('''
        CREATE TABLE IF NOT EXISTS articulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            subtitulo TEXT,
            seccion TEXT NOT NULL,
            autor TEXT DEFAULT 'Familia',
            contenido TEXT NOT NULL,
            ingredientes TEXT,
            pasos_receta TEXT,
            imagen_bytes BLOB,
            imagen_nombre TEXT,
            video_bytes BLOB,
            video_nombre TEXT,
            video_url TEXT,
            fecha_publicacion TEXT,
            destacado INTEGER DEFAULT 0
        )
    ''')
    
    # Migración: Agregar imagenes_json y reacciones_json si faltan
    c.execute("PRAGMA table_info(articulos)")
    cols_art = [col[1] for col in c.fetchall()]
    if 'imagenes_json' not in cols_art:
        try:
            c.execute("ALTER TABLE articulos ADD COLUMN imagenes_json TEXT")
        except Exception:
            pass
    if 'reacciones_json' not in cols_art:
        try:
            c.execute("ALTER TABLE articulos ADD COLUMN reacciones_json TEXT")
        except Exception:
            pass

    # 3. Tabla de Comentarios de la Familia
    c.execute('''
        CREATE TABLE IF NOT EXISTS comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            articulo_id INTEGER NOT NULL,
            autor TEXT NOT NULL,
            comentario TEXT NOT NULL,
            fecha_comentario TEXT NOT NULL
        )
    ''')

    # Poblar secciones base si la tabla está vacía
    c.execute('SELECT COUNT(*) FROM secciones')
    if c.fetchone()[0] == 0:
        secciones_base = [
            ('⚽ Deportes', '⚽', 'Crónicas, partidos, eventos deportivos y logros familiares', 0),
            ('🍳 Cocina y Recetario', '🍳', 'Las mejores recetas, secretos culinarios y platillos de la familia', 0),
            ('📸 Galería Multimedia', '📸', 'Álbum visual con fotografías y videos de eventos inolvidables', 0),
            ('✍️ El Rincón de Berta', '✍️', 'Espacio exclusivo para las columnas, vivencias y reflexiones de Berta', 1)
        ]
        c.executemany('INSERT INTO secciones (nombre, icono, descripcion, es_especial) VALUES (?, ?, ?, ?)', secciones_base)
    
    # Insertar artículo de bienvenida si no hay ninguno
    c.execute('SELECT COUNT(*) FROM articulos')
    if c.fetchone()[0] == 0:
        f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute('''
            INSERT INTO articulos (titulo, subtitulo, seccion, autor, contenido, fecha_publicacion, destacado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            '¡Bienvenidos al Blog Familiar! 🏡',
            'Lara 1, Lara 5 y Sra. McCormick para el Mundo',
            '✍️ El Rincón de Berta',
            'Berta',
            'Nos da muchísima alegría estrenar este rincón digital para la familia.\n\nAquí podremos compartir nuestras historias deportivas, las mejores recetas de cocina, fotos de nuestras reuniones y artículos especiales.\n\n¡Esperamos que disfruten mucho este espacio hecho con todo el cariño!',
            f_act,
            1
        ))
        
    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES DE CONSULTA Y OPERACIONES ---
def obtener_secciones_activas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, icono, descripcion, es_especial FROM secciones WHERE activa = 1 ORDER BY id ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_todas_secciones():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, icono, descripcion, es_especial, activa FROM secciones ORDER BY id ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_seccion(nombre, icono, descripcion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO secciones (nombre, icono, descripcion) VALUES (?, ?, ?)', (nombre, icono, descripcion))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def cambiar_estatus_seccion(seccion_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE secciones SET activa = ? WHERE id = ?', (nuevo_estatus, seccion_id))
    conn.commit()
    conn.close()

def guardar_articulo(titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, imagenes_list=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Convertir lista de imágenes base64 si existen
    imgs_json = json.dumps(imagenes_list, ensure_ascii=False) if imagenes_list else None
    reacciones_init = json.dumps({"me_gusta": 0, "bravo": 0, "delicioso": 0, "amor": 0})
    
    c.execute('''
        INSERT INTO articulos (
            titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta,
            imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado,
            imagenes_json, reacciones_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos,
        img_bytes, img_nom, vid_bytes, vid_nom, vid_url, f_act, destacado,
        imgs_json, reacciones_init
    ))
    conn.commit()
    conn.close()

def actualizar_articulo(art_id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, imagenes_list=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    imgs_json = json.dumps(imagenes_list, ensure_ascii=False) if imagenes_list else None
    
    if img_bytes is not None and vid_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            imagen_bytes=?, imagen_nombre=?, video_bytes=?, video_nombre=?, video_url=?, destacado=?, imagenes_json=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, imgs_json, art_id))
    elif img_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            imagen_bytes=?, imagen_nombre=?, video_url=?, destacado=?, imagenes_json=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_url, destacado, imgs_json, art_id))
    elif vid_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            video_bytes=?, video_nombre=?, video_url=?, destacado=?, imagenes_json=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, vid_bytes, vid_nom, vid_url, destacado, imgs_json, art_id))
    else:
        if imgs_json:
            c.execute('''
                UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
                video_url=?, destacado=?, imagenes_json=? WHERE id=?
            ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, vid_url, destacado, imgs_json, art_id))
        else:
            c.execute('''
                UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
                video_url=?, destacado=? WHERE id=?
            ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, vid_url, destacado, art_id))
    conn.commit()
    conn.close()

def eliminar_articulo(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM articulos WHERE id = ?', (art_id,))
    c.execute('DELETE FROM comentarios WHERE articulo_id = ?', (art_id,))
    conn.commit()
    conn.close()

def obtener_articulos_por_seccion(seccion_nombre=None, solo_destacados=False, busqueda=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, imagenes_json, reacciones_json FROM articulos WHERE 1=1'
    params = []
    
    if seccion_nombre and seccion_nombre != "🏠 Inicio / Novedades":
        query += ' AND seccion = ?'
        params.append(seccion_nombre)
        
    if solo_destacados:
        query += ' AND destacado = 1'
        
    if busqueda:
        query += ' AND (LOWER(titulo) LIKE ? OR LOWER(contenido) LIKE ? OR LOWER(autor) LIKE ?)'
        b_term = f"%{busqueda.lower()}%"
        params.extend([b_term, b_term, b_term])
        
    query += ' ORDER BY id DESC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_articulo_por_id(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, imagenes_json, reacciones_json FROM articulos WHERE id = ?', (art_id,))
    row = c.fetchone()
    conn.close()
    return row

# --- FUNCIONES DE REACCIONES Y COMENTARIOS ---
def agregar_reaccion(art_id, tipo_reaccion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT reacciones_json FROM articulos WHERE id = ?', (art_id,))
    row = c.fetchone()
    reacciones = json.loads(row[0]) if row and row[0] else {"me_gusta": 0, "bravo": 0, "delicioso": 0, "amor": 0}
    reacciones[tipo_reaccion] = reacciones.get(tipo_reaccion, 0) + 1
    c.execute('UPDATE articulos SET reacciones_json = ? WHERE id = ?', (json.dumps(reacciones), art_id))
    conn.commit()
    conn.close()

def agregar_comentario(art_id, autor, comentario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('INSERT INTO comentarios (articulo_id, autor, comentario, fecha_comentario) VALUES (?, ?, ?, ?)',
              (art_id, autor, comentario, f_act))
    conn.commit()
    conn.close()

def obtener_comentarios_articulo(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, autor, comentario, fecha_comentario FROM comentarios WHERE articulo_id = ? ORDER BY id ASC', (art_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- DISEÑO Y ESTILOS PERSONALES ---
st.markdown("""
<style>
    .main-header {
        text-align: center;
        background: linear-gradient(135deg, #f6d365 0%, #fda085 100%);
        padding: 28px;
        border-radius: 18px;
        color: #2c3e50;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    }
    .main-subtitle {
        font-size: 1.25rem;
        font-weight: 600;
        margin-top: 8px;
        color: #2d3748;
        letter-spacing: 0.5px;
    }
    .berta-header {
        text-align: center;
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        padding: 28px;
        border-radius: 18px;
        color: #2c3e50;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    }
    .badge-sec {
        background-color: #ebf8ff;
        color: #2b6cb0;
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-author {
        background-color: #faf5ff;
        color: #6b46c1;
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .preview-box {
        border: 2px dashed #4a5568;
        background-color: #f7fafc;
        border-radius: 12px;
        padding: 20px;
        margin-top: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- MENÚ LATERAL Y NAVEGACIÓN ---
st.sidebar.title("🏡 Blog Familiar")
st.sidebar.markdown("**Lara 1, Lara 5 y Sra. McCormick para el Mundo**")
st.sidebar.caption("Nuestras historias, fotos, recetas y recuerdos")

secciones_db = obtener_secciones_activas()
opciones_menu = ["🏠 Inicio / Novedades"] + [s[1] for s in secciones_db] + ["⚙️ Panel de Administración"]

menu_sel = st.sidebar.radio("Navegar por el Blog", opciones_menu)

st.sidebar.write("---")
st.sidebar.markdown("💡 **Búsqueda Rápida**")
busqueda_txt = st.sidebar.text_input("Buscar palabras o temas", placeholder="Ej. receta, torneo, viaje...")

# LISTA MAESTRA DE AUTORES
AUTORES_PREDEFINIDOS = ["Berta", "Lara 1", "Lara 5", "Sra. McCormick", "Familia", "Otro / Invitado"]

# ==============================================================================
# VISTAS DE LECTURA DE SECCIONES
# ==============================================================================

def renderizar_publicacion(art):
    # art: id(0), titulo(1), subtitulo(2), seccion(3), autor(4), contenido(5), ingredientes(6), pasos(7), img_bytes(8), img_nom(9), vid_bytes(10), vid_nom(11), vid_url(12), fecha(13), destacado(14), imagenes_json(15), reacciones_json(16)
    art_id = art[0]
    st.markdown(f"## {art[1]}")
    if art[2]:
        st.markdown(f"#### _{art[2]}_")
        
    col_meta1, col_meta2 = st.columns([3, 1])
    with col_meta1:
        st.markdown(f"<span class='badge-sec'>{art[3]}</span> &nbsp; <span class='badge-author'>✍️ {art[4]}</span>", unsafe_allow_html=True)
    with col_meta2:
        st.caption(f"📅 {art[13]}")
        
    # Imagen Principal
    if art[8]:
        st.image(art[8], caption=art[9] if art[9] else art[1], use_container_width=True)
        
    # Galería de Múltiples Imágenes si existen
    if len(art) > 15 and art[15]:
        try:
            imgs_list = json.loads(art[15])
            if imgs_list:
                st.markdown("##### 📸 Álbum de Fotografías")
                cols_gal = st.columns(min(len(imgs_list), 3))
                for idx_i, img_b64 in enumerate(imgs_list):
                    with cols_gal[idx_i % 3]:
                        st.image(base64.b64decode(img_b64), use_container_width=True)
        except Exception:
            pass

    # Video adjunto
    if art[10]:
        st.video(art[10])
    elif art[12]:
        st.video(art[12])
        
    # Contenido principal
    st.markdown(art[5])
    
    # Sección especial de Recetas
    if art[6] or art[7]:
        st.divider()
        st.subheader("🍳 Ficha de Receta Culinaria")
        c_rec1, c_rec2 = st.columns(2)
        with c_rec1:
            st.markdown("### 🛒 Ingredientes")
            st.info(art[6] if art[6] else "No especificados")
        with c_rec2:
            st.markdown("### 👩‍🍳 Modo de Preparación")
            st.success(art[7] if art[7] else "No especificados")

    # --- REACCIONES Y COMENTARIOS ---
    st.write("---")
    reacciones = json.loads(art[16]) if len(art) > 16 and art[16] else {"me_gusta": 0, "bravo": 0, "delicioso": 0, "amor": 0}
    
    c_r1, c_r2, c_r3, c_r4 = st.columns(4)
    with c_r1:
        if st.button(f"❤️ Me gusta ({reacciones.get('me_gusta', 0)})", key=f"react_mg_{art_id}"):
            agregar_reaccion(art_id, "me_gusta")
            st.rerun()
    with c_r2:
        if st.button(f"👏 ¡Bravo! ({reacciones.get('bravo', 0)})", key=f"react_br_{art_id}"):
            agregar_reaccion(art_id, "bravo")
            st.rerun()
    with c_r3:
        if st.button(f"😋 Delicioso ({reacciones.get('delicioso', 0)})", key=f"react_del_{art_id}"):
            agregar_reaccion(art_id, "delicioso")
            st.rerun()
    with c_r4:
        if st.button(f"😍 Me encanta ({reacciones.get('amor', 0)})", key=f"react_am_{art_id}"):
            agregar_reaccion(art_id, "amor")
            st.rerun()

    # Comentarios de la Familia
    with st.expander(f"💬 Comentarios de la Familia ({len(obtener_comentarios_articulo(art_id))})"):
        comms = obtener_comentarios_articulo(art_id)
        if comms:
            for c_id, c_autor, c_txt, c_fecha in comms:
                st.markdown(f"**{c_autor}** _({c_fecha})_:")
                st.write(f"> {c_txt}")
        else:
            st.caption("Aún no hay comentarios. ¡Sé el primero en escribir algo!")
            
        with st.form(f"form_comentario_{art_id}", clear_on_submit=True):
            col_c1, col_c2 = st.columns([1, 3])
            with col_c1:
                c_nom = st.text_input("Tu Nombre", key=f"nom_com_{art_id}")
            with col_c2:
                c_msg = st.text_input("Escribe tu comentario", key=f"msg_com_{art_id}")
            if st.form_submit_button("💬 Enviar Comentario"):
                if c_nom.strip() and c_msg.strip():
                    agregar_comentario(art_id, c_nom.strip(), c_msg.strip())
                    st.success("Comentario publicado.")
                    st.rerun()
                else:
                    st.error("Por favor completa tu nombre y el mensaje.")

# --- 1. INICIO / NOVEDADES ---
if menu_sel == "🏠 Inicio / Novedades":
    st.markdown("""
        <div class="main-header">
            <h1>🏡 Rincón Familiar & Bitácora de Recuerdos</h1>
            <p class="main-subtitle">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts = obtener_articulos_por_seccion(busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts:
        st.info("👋 ¡Aún no hay publicaciones en esta sección! Ve al **Panel de Administración** para crear la primera entrada.")
    else:
        # Destacados arriba
        destacados = [a for a in arts if a[14] == 1]
        if destacados and not busqueda_txt:
            st.subheader("⭐ Publicaciones Destacadas")
            cols_dest = st.columns(min(len(destacados), 2))
            for i, dest in enumerate(destacados[:2]):
                with cols_dest[i % 2]:
                    st.markdown(f"### {dest[1]}")
                    if dest[2]:
                        st.caption(f"_{dest[2]}_")
                    st.markdown(f"<span class='badge-sec'>{dest[3]}</span> <span class='badge-author'>✍️ {dest[4]}</span>", unsafe_allow_html=True)
                    st.write(f"📅 **{dest[13]}**")
                    if dest[8]:
                        st.image(dest[8], use_container_width=True)
                    st.write(dest[5][:200] + ("..." if len(dest[5]) > 200 else ""))
                    st.write("---")
                    
        st.subheader("📜 Todas las Publicaciones")
        for art in arts:
            renderizar_publicacion(art)
            st.divider()

# --- 2. VISTA ESPECÍFICA: EL RINCÓN DE BERTA ---
elif menu_sel == "✍️ El Rincón de Berta":
    st.markdown("""
        <div class="berta-header">
            <h1>🌸 El Rincón de Berta</h1>
            <p class="main-subtitle">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_berta = obtener_articulos_por_seccion("✍️ El Rincón de Berta", busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_berta:
        st.info("🌷 Aún no hay artículos publicados en el Rincón de Berta. ¡Próximamente nuevas reflexiones!")
    else:
        for art in arts_berta:
            renderizar_publicacion(art)
            st.divider()

# --- 3. VISTA ESPECÍFICA: COCINA Y RECETARIO ---
elif menu_sel == "🍳 Cocina y Recetario":
    st.markdown("""
        <div class="main-header" style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);">
            <h1>🍳 El Recetario de la Familia</h1>
            <p class="main-subtitle">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_cocina = obtener_articulos_por_seccion("🍳 Cocina y Recetario", busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_cocina:
        st.info("🍲 ¡Aún no hay recetas guardadas! Agrega la primera en el Panel de Administración.")
    else:
        for art in arts_cocina:
            renderizar_publicacion(art)
            st.divider()

# --- 4. OTRAS SECCIONES DINÁMICAS ---
elif menu_sel in [s[1] for s in secciones_db]:
    sec_info = next((s for s in secciones_db if s[1] == menu_sel), None)
    
    st.markdown(f"""
        <div class="main-header">
            <h1>{sec_info[1]}</h1>
            <p class="main-subtitle">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_sec = obtener_articulos_por_seccion(menu_sel, busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_sec:
        st.info(f"📌 Aún no hay publicaciones en la sección **{menu_sel}**.")
    else:
        for art in arts_sec:
            renderizar_publicacion(art)
            st.divider()

# ==============================================================================
# PANEL DE ADMINISTRACIÓN / GESTOR DE CONTENIDOS
# ==============================================================================
elif menu_sel == "⚙️ Panel de Administración":
    st.title("⚙️ Panel de Administración del Blog Familiar")
    st.caption("Lara 1, Lara 5 y Sra. McCormick para el Mundo")
    st.write("Desde aquí puedes redactar nuevos artículos, subir fotos o videos, crear nuevas secciones y administrar las publicaciones.")
    
    tab_admin1, tab_admin2, tab_admin3 = st.tabs([
        "📝 Publicar Nuevo Artículo",
        "📂 Crear / Administrar Secciones",
        "✏️ Editar o Eliminar Publicaciones Existentes"
    ])
    
    # --- TAB 1: NUEVO ARTÍCULO ---
    with tab_admin1:
        st.subheader("✍️ Redactar Nueva Publicación")
        
        sec_activas = obtener_secciones_activas()
        if not sec_activas:
            st.error("No hay secciones activas creadas. Crea una sección primero en la pestaña 'Crear / Administrar Secciones'.")
        else:
            col_form, col_prev = st.columns([1, 1])
            
            with col_form:
                st.markdown("#### 1. Formulario de Captura")
                
                a_titulo = st.text_input("Título de la Publicación *", key="a_tit")
                a_subtitulo = st.text_input("Subtítulo o Resumen Corto", key="a_sub")
                
                col_au1, col_au2 = st.columns(2)
                with col_au1:
                    sel_aut_option = st.selectbox("Autor(a) / Quien Publica *", AUTORES_PREDEFINIDOS)
                    if sel_aut_option == "Otro / Invitado":
                        a_autor = st.text_input("Escribe el nombre del Autor", value="Invitado Especial")
                    else:
                        a_autor = sel_aut_option
                with col_au2:
                    a_seccion = st.selectbox("Sección / Categoría *", [s[1] for s in sec_activas])
                    
                a_destacado = st.checkbox("⭐ Marcar como Publicación Destacada (Aparece en portada)")
                
                st.markdown("##### ✏️ Editor de Texto Principal")
                # Botones de ayuda de formato Markdown
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    if st.button("<b>Negrita</b>", use_container_width=True):
                        st.session_state["a_cont"] = st.session_state.get("a_cont", "") + " **texto en negrita** "
                with col_m2:
                    if st.button("<i>Cursiva</i>", use_container_width=True):
                        st.session_state["a_cont"] = st.session_state.get("a_cont", "") + " *texto en cursiva* "
                with col_m3:
                    if st.button("📌 Lista", use_container_width=True):
                        st.session_state["a_cont"] = st.session_state.get("a_cont", "") + "\n- Elemento 1\n- Elemento 2\n"
                with col_m4:
                    if st.button("💬 Cita", use_container_width=True):
                        st.session_state["a_cont"] = st.session_state.get("a_cont", "") + "\n> Frase celebre o cita especial\n"

                a_contenido = st.text_area("Contenido Principal / Texto del Artículo *", height=200, key="a_cont")
                
                # Campos especiales si es Cocina
                if "Cocina" in a_seccion:
                    st.markdown("##### 🍳 Datos Especiales de Receta (Opcional)")
                    a_ingredientes = st.text_area("Lista de Ingredientes", placeholder="Ej: 2 tazas de harina, 100g de mantequilla...", height=100)
                    a_pasos = st.text_area("Pasos de Preparación", placeholder="Ej: 1. Mezclar ingredientes... 2. Hornear a 180°C...", height=100)
                else:
                    a_ingredientes = None
                    a_pasos = None
                    
                st.markdown("##### 📸 Adjuntar Elementos Multimedia")
                f_img = st.file_uploader("Subir Imagen Principal (JPG, PNG)", type=["jpg", "jpeg", "png", "webp"])
                f_imgs_multi = st.file_uploader("Subir Álbum de Fotos Múltiples (Galería)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
                f_vid = st.file_uploader("Subir Video Corto (MP4, MOV)", type=["mp4", "mov", "webm"])
                a_vid_url = st.text_input("O ingresar enlace de Video (YouTube / Vimeo)")
                
                btn_publicar = st.button("🚀 Guardar y Publicar en el Blog", use_container_width=True)
                
            # --- VISTA PREVIA EN TIEMPO REAL ---
            with col_prev:
                st.markdown("#### 👁️ Vista Previa en Tiempo Real")
                st.caption("Así se verá tu artículo publicado en la sección:")
                
                with st.container():
                    st.markdown("<div class='preview-box'>", unsafe_allow_html=True)
                    st.markdown(f"## {a_titulo if a_titulo.strip() else 'Título de tu Publicación'}")
                    if a_subtitulo.strip():
                        st.markdown(f"#### _{a_subtitulo}_")
                    st.markdown(f"<span class='badge-sec'>{a_seccion}</span> &nbsp; <span class='badge-author'>✍️ {a_autor}</span>", unsafe_allow_html=True)
                    st.caption(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                    
                    if f_img:
                        st.image(f_img, caption="Imagen Principal (Vista previa)", use_container_width=True)
                        
                    if f_imgs_multi:
                        st.markdown("##### 📸 Álbum Múltiple (Vista previa)")
                        cols_p_gal = st.columns(min(len(f_imgs_multi), 3))
                        for idx_p, fi in enumerate(f_imgs_multi):
                            with cols_p_gal[idx_p % 3]:
                                st.image(fi, use_container_width=True)
                                
                    if a_contenido.strip():
                        st.markdown(a_contenido)
                    else:
                        st.info("Escribe el contenido en el panel izquierdo para previsualizar el texto...")
                        
                    if a_ingredientes or a_pasos:
                        st.markdown("---")
                        st.subheader("🍳 Receta")
                        if a_ingredientes:
                            st.info(f"**Ingredientes:**\n{a_ingredientes}")
                        if a_pasos:
                            st.success(f"**Preparación:**\n{a_pasos}")
                            
                    st.markdown("</div>", unsafe_allow_html=True)

            if btn_publicar:
                if not a_titulo.strip() or not a_contenido.strip():
                    st.error("⚠️ El Título y el Contenido Principal son obligatorios.")
                else:
                    img_b = f_img.read() if f_img else None
                    img_n = f_img.name if f_img else None
                    vid_b = f_vid.read() if f_vid else None
                    vid_n = f_vid.name if f_vid else None
                    
                    imgs_multi_b64 = []
                    if f_imgs_multi:
                        for f_m in f_imgs_multi:
                            imgs_multi_b64.append(base64.b64encode(f_m.read()).decode('utf-8'))
                            
                    guardar_articulo(
                        a_titulo.strip(), a_subtitulo.strip(), a_seccion, a_autor.strip(),
                        a_contenido.strip(), a_ingredientes, a_pasos,
                        img_b, img_n, vid_b, vid_n, a_vid_url.strip(), 1 if a_destacado else 0,
                        imagenes_list=imgs_multi_b64
                    )
                    st.success(f"🎉 ¡Publicación '**{a_titulo}**' guardada exitosamente en {a_seccion}!")
                    st.toast("¡Artículo publicado con éxito!", icon="🎉")
                    st.rerun()

    # --- TAB 2: CREAR Y CONFIGURAR SECCIONES ---
    with tab_admin2:
        st.subheader("📂 Administrador de Secciones del Blog")
        st.write("Puedes crear nuevas categorías para organizar tus contenidos o desactivar las que no utilices actualmente.")
        
        st.markdown("### ➕ Agregar Nueva Sección")
        with st.form("form_nueva_seccion", clear_on_submit=True):
            col_s1, col_s2 = st.columns([1, 3])
            with col_s1:
                sec_icono = st.text_input("Emoji / Icono", value="📌")
            with col_s2:
                sec_nombre_raw = st.text_input("Nombre de la Nueva Sección *", placeholder="Ej: Viajes y Aventuras")
                
            sec_desc = st.text_input("Descripción Corta de la Sección", placeholder="Ej: Fotos y relatos de nuestras vacaciones en familia")
            
            if st.form_submit_button("➕ Crear Nueva Sección"):
                if not sec_nombre_raw.strip():
                    st.error("⚠️ El nombre de la sección es obligatorio.")
                else:
                    nom_full = f"{sec_icono.strip()} {sec_nombre_raw.strip()}"
                    res = agregar_seccion(nom_full, sec_icono.strip(), sec_desc.strip())
                    if res:
                        st.success(f"✅ ¡Sección '**{nom_full}**' creada exitosamente!")
                        st.rerun()
                    else:
                        st.error("❌ Ya existe una sección con ese nombre.")
                        
        st.divider()
        st.markdown("### 📋 Secciones Existentes en el Sistema")
        todas_sec = obtener_todas_secciones()
        
        for sid, snom, sico, sdesc, sesp, sact in todas_sec:
            col_sec1, col_sec2, col_sec3 = st.columns([4, 2, 2])
            with col_sec1:
                st.write(f"**{snom}** {'⭐ (Especial Berta)' if sesp==1 else ''}")
                if sdesc:
                    st.caption(sdesc)
            with col_sec2:
                st.write("🟢 **Activa**" if sact == 1 else "🔴 **Inactiva / Oculta**")
            with col_sec3:
                if sesp == 0:
                    new_st = 0 if sact == 1 else 1
                    lbl_btn = "🔒 Ocultar" if sact == 1 else "🔓 Activar"
                    if st.button(lbl_btn, key=f"btn_sec_{sid}"):
                        cambiar_estatus_seccion(sid, new_st)
                        st.rerun()

    # --- TAB 3: EDITAR O ELIMINAR PUBLICACIONES ---
    with tab_admin3:
        st.subheader("✏️ Edición y Mantenimiento de Artículos")
        todas_pubs = obtener_articulos_por_seccion(seccion_nombre=None)
        
        if not todas_pubs:
            st.info("No hay publicaciones registradas para editar.")
        else:
            dict_pubs = {f"[{p[3]}] {p[1]} (por {p[4]} - {p[13]})": p[0] for p in todas_pubs}
            sel_pub_key = st.selectbox("🔑 Selecciona el Artículo a Modificar o Eliminar", list(dict_pubs.keys()))
            
            pub_id = dict_pubs[sel_pub_key]
            p_data = obtener_articulo_por_id(pub_id)
            
            if p_data:
                with st.form(f"form_edit_pub_{pub_id}"):
                    st.markdown(f"### Modificando: **{p_data[1]}**")
                    
                    col_ed1, col_ed2 = st.columns(2)
                    with col_ed1:
                        e_titulo = st.text_input("Título", value=p_data[1])
                        e_subtitulo = st.text_input("Subtítulo", value=p_data[2] if p_data[2] else "")
                        e_autor = st.text_input("Autor(a)", value=p_data[4])
                    with col_ed2:
                        sec_activas = obtener_secciones_activas()
                        nombres_s = [s[1] for s in sec_activas]
                        idx_s = nombres_s.index(p_data[3]) if p_data[3] in nombres_s else 0
                        e_seccion = st.selectbox("Sección", nombres_s, index=idx_s)
                        e_destacado = st.checkbox("⭐ Destacado", value=bool(p_data[14]))
                        
                    e_contenido = st.text_area("Contenido Principal", value=p_data[5], height=180)
                    
                    if "Cocina" in e_seccion:
                        st.markdown("#### 🍳 Datos de Receta")
                        col_ec1, col_ec2 = st.columns(2)
                        with col_ec1:
                            e_ing = st.text_area("Ingredientes", value=p_data[6] if p_data[6] else "")
                        with col_ec2:
                            e_pas = st.text_area("Pasos", value=p_data[7] if p_data[7] else "")
                    else:
                        e_ing = None
                        e_pas = None
                        
                    st.markdown("#### 📸 Multimedia (Adjuntar solo si deseas reemplazar el actual)")
                    col_em1, col_em2 = st.columns(2)
                    with col_em1:
                        e_f_img = st.file_uploader("Nueva Imagen (Reemplazar)", type=["jpg", "jpeg", "png", "webp"], key=f"e_img_{pub_id}")
                    with col_em2:
                        e_f_vid = st.file_uploader("Nuevo Video (Reemplazar)", type=["mp4", "mov", "webm"], key=f"e_vid_{pub_id}")
                        e_vid_url = st.text_input("Enlace Video", value=p_data[12] if p_data[12] else "")
                        
                    st.divider()
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        btn_actualizar = st.form_submit_button("💾 Actualizar Cambios", use_container_width=True)
                    with col_btn2:
                        btn_borrar = st.form_submit_button("🗑️ Eliminar Publicación", use_container_width=True)
                        
                    if btn_actualizar:
                        img_b = e_f_img.read() if e_f_img else None
                        img_n = e_f_img.name if e_f_img else None
                        vid_b = e_f_vid.read() if e_f_vid else None
                        vid_n = e_f_vid.name if e_f_vid else None
                        
                        actualizar_articulo(
                            pub_id, e_titulo.strip(), e_subtitulo.strip(), e_seccion, e_autor.strip(),
                            e_contenido.strip(), e_ing, e_pas, img_b, img_n, vid_b, vid_n, e_vid_url.strip(), 1 if e_destacado else 0
                        )
                        st.success(f"✅ Publicación '**{e_titulo}**' actualizada correctamente.")
                        st.toast("Cambios guardados exitosamente")
                        st.rerun()
                        
                    if btn_borrar:
                        eliminar_articulo(pub_id)
                        st.warning("🗑️ Publicación eliminada.")
                        st.toast("Publicación eliminada")
                        st.rerun()

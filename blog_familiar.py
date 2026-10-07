import streamlit as st
import sqlite3
import json
import os
from datetime import datetime
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Blog Familiar - Recuerdos y Historias",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "blog_familiar.db"

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de Secciones / Categorías
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
    
    # Tabla de Publicaciones / Artículos
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
            destacado INTEGER DEFAULT 0,
            archivo_bytes BLOB,
            archivo_nombre TEXT
        )
    ''')
    
    # Auto-migración por si la tabla articulos ya existía sin archivo_bytes
    c.execute("PRAGMA table_info(articulos)")
    cols_art = [row[1] for row in c.fetchall()]
    if "archivo_bytes" not in cols_art:
        try:
            c.execute("ALTER TABLE articulos ADD COLUMN archivo_bytes BLOB")
        except Exception:
            pass
    if "archivo_nombre" not in cols_art:
        try:
            c.execute("ALTER TABLE articulos ADD COLUMN archivo_nombre TEXT")
        except Exception:
            pass

    # Tabla de Comentarios y Reacciones
    c.execute('''
        CREATE TABLE IF NOT EXISTS comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            articulo_id INTEGER NOT NULL,
            nombre_usuario TEXT NOT NULL,
            comentario TEXT NOT NULL,
            fecha TEXT NOT NULL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS reacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            articulo_id INTEGER NOT NULL,
            tipo_reaccion TEXT NOT NULL
        )
    ''')
    
    # Poblar secciones por defecto si la tabla está vacía
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
            'Nos da muchísima alegría estrenar este rincón digital para la familia.\n\nAquí podremos compartir nuestras historias deportivas, las mejores recetas de cocina, fotos de nuestras reuniones, presentaciones y artículos especiales.\n\n¡Esperamos que disfruten mucho este espacio hecho con todo el cariño!',
            f_act,
            1
        ))
        
    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES AUXILIARES DE CONSULTA ---
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

def guardar_articulo(titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, doc_bytes=None, doc_nom=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('''
        INSERT INTO articulos (
            titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta,
            imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado,
            archivo_bytes, archivo_nombre
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, f_act, destacado, doc_bytes, doc_nom))
    conn.commit()
    conn.close()

def actualizar_articulo(art_id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, doc_bytes=None, doc_nom=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('SELECT imagen_bytes, imagen_nombre, video_bytes, video_nombre, archivo_bytes, archivo_nombre FROM articulos WHERE id = ?', (art_id,))
    prev = c.fetchone()
    
    final_img_b = img_bytes if img_bytes is not None else (prev[0] if prev else None)
    final_img_n = img_nom if img_nom is not None else (prev[1] if prev else None)
    final_vid_b = vid_bytes if vid_bytes is not None else (prev[2] if prev else None)
    final_vid_n = vid_nom if vid_nom is not None else (prev[3] if prev else None)
    final_doc_b = doc_bytes if doc_bytes is not None else (prev[4] if prev else None)
    final_doc_n = doc_nom if doc_nom is not None else (prev[5] if prev else None)

    c.execute('''
        UPDATE articulos SET 
            titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            imagen_bytes=?, imagen_nombre=?, video_bytes=?, video_nombre=?, video_url=?, destacado=?,
            archivo_bytes=?, archivo_nombre=?
        WHERE id=?
    ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, final_img_b, final_img_n, final_vid_b, final_vid_n, vid_url, destacado, final_doc_b, final_doc_n, art_id))
    conn.commit()
    conn.close()

def eliminar_articulo(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM articulos WHERE id = ?', (art_id,))
    c.execute('DELETE FROM comentarios WHERE articulo_id = ?', (art_id,))
    c.execute('DELETE FROM reacciones WHERE articulo_id = ?', (art_id,))
    conn.commit()
    conn.close()

def obtener_articulos_por_seccion(seccion_nombre=None, solo_destacados=False, busqueda=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, archivo_bytes, archivo_nombre FROM articulos WHERE 1=1'
    params = []
    
    if seccion_nombre and seccion_nombre != "🏠 Inicio / Novedades":
        query += ' AND seccion = ?'
        params.append(seccion_nombre)
        
    if solo_destacados:
        query += ' AND destacado = 1'
        
    if busqueda:
        query += ' AND (LOWER(titulo) LIKE ? OR LOWER(contenido) LIKE ? OR LOWER(autor) LIKE ? OR LOWER(archivo_nombre) LIKE ?)'
        b_term = f"%{busqueda.lower()}%"
        params.extend([b_term, b_term, b_term, b_term])
        
    query += ' ORDER BY id DESC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_articulo_por_id(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, archivo_bytes, archivo_nombre FROM articulos WHERE id = ?', (art_id,))
    row = c.fetchone()
    conn.close()
    return row

# Funciones de Comentarios y Reacciones
def agregar_comentario(art_id, usuario, texto):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('INSERT INTO comentarios (articulo_id, nombre_usuario, comentario, fecha) VALUES (?, ?, ?, ?)', (art_id, usuario, texto, f_act))
    conn.commit()
    conn.close()

def obtener_comentarios(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT nombre_usuario, comentario, fecha FROM comentarios WHERE articulo_id = ? ORDER BY id ASC', (art_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def agregar_reaccion(art_id, tipo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO reacciones (articulo_id, tipo_reaccion) VALUES (?, ?)', (art_id, tipo))
    conn.commit()
    conn.close()

def obtener_conteo_reacciones(art_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT tipo_reaccion, COUNT(*) FROM reacciones WHERE articulo_id = ? GROUP BY tipo_reaccion', (art_id,))
    rows = c.fetchall()
    conn.close()
    res = {"❤️": 0, "👏": 0, "😋": 0, "😍": 0}
    for r in rows:
        if r[0] in res:
            res[r[0]] = r[1]
    return res

# --- DISEÑO Y ESTILOS PERSONALES ---
st.markdown("""
<style>
    .main-header {
        text-align: center;
        background: linear-gradient(135deg, #f6d365 0%, #fda085 100%);
        padding: 25px;
        border-radius: 15px;
        color: #2c3e50;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .berta-header {
        text-align: center;
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        padding: 25px;
        border-radius: 15px;
        color: #2c3e50;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .card-post {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .badge-sec {
        background-color: #ebf8ff;
        color: #2b6cb0;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-author {
        background-color: #faf5ff;
        color: #6b46c1;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# --- MENÚ LATERAL Y NAVEGACIÓN ---
st.sidebar.title("🏡 Blog Familiar")
st.sidebar.markdown("### *Lara 1, Lara 5 y Sra. McCormick para el Mundo*")
st.sidebar.caption("Nuestras historias, fotos, recetas y recuerdos")

secciones_db = obtener_secciones_activas()
opciones_menu = ["🏠 Inicio / Novedades"] + [s[1] for s in secciones_db] + ["⚙️ Panel de Administración"]

menu_sel = st.sidebar.radio("Navegar por el Blog", opciones_menu)

st.sidebar.write("---")
st.sidebar.markdown("💡 **Búsqueda Rápida**")
busqueda_txt = st.sidebar.text_input("Buscar palabras, archivos o temas", placeholder="Ej. presentación, receta, viaje...")

# Función auxiliar para renderizar un artículo completo en lectura
def renderizar_articulo(art):
    art_id = art[0]
    art_titulo = art[1]
    art_subtitulo = art[2]
    art_seccion = art[3]
    art_autor = art[4]
    art_contenido = art[5]
    art_ing = art[6]
    art_pasos = art[7]
    art_img_b = art[8]
    art_img_n = art[9]
    art_vid_b = art[10]
    art_vid_n = art[11]
    art_vid_url = art[12]
    art_fecha = art[13]
    art_destacado = art[14]
    art_doc_b = art[15] if len(art) > 15 else None
    art_doc_n = art[16] if len(art) > 16 else None

    st.markdown(f"## {art_titulo}")
    if art_subtitulo:
        st.markdown(f"#### _{art_subtitulo}_")
    
    col_meta1, col_meta2 = st.columns([3, 1])
    with col_meta1:
        st.markdown(f"<span class='badge-sec'>{art_seccion}</span> &nbsp; <span class='badge-author'>✍️ {art_autor}</span>", unsafe_allow_html=True)
    with col_meta2:
        st.caption(f"📅 {art_fecha}")
    
    # Imagen adjunta
    if art_img_b:
        st.image(art_img_b, caption=art_img_n if art_img_n else art_titulo, use_container_width=True)
        
    # Video adjunto
    if art_vid_b:
        st.video(art_vid_b)
    elif art_vid_url:
        st.video(art_vid_url)
        
    # Contenido principal
    st.markdown(art_contenido)
    
    # DOCUMENTO / PRESENTACIÓN ADJUNTA (PowerPoint, PDF, Word, etc.)
    if art_doc_b:
        st.markdown("---")
        st.info(f"📊 **Documento / Presentación Adjunta**: `{art_doc_n if art_doc_n else 'Presentacion.pptx'}`")
        
        mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if art_doc_n:
            if art_doc_n.endswith(".pdf"):
                mime_type = "application/pdf"
            elif art_doc_n.endswith(".docx"):
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif art_doc_n.endswith(".zip"):
                mime_type = "application/zip"

        st.download_button(
            label=f"📥 Descargar {art_doc_n if art_doc_n else 'Presentación PowerPoint'}",
            data=art_doc_b,
            file_name=art_doc_n if art_doc_n else "presentacion.pptx",
            mime=mime_type,
            use_container_width=True,
            key=f"dl_btn_{art_id}"
        )
    
    # Sección de Recetas
    if art_ing or art_pasos:
        st.divider()
        st.subheader("🍳 Ficha de Receta Culinary")
        c_rec1, c_rec2 = st.columns(2)
        with c_rec1:
            st.markdown("### 🛒 Ingredientes")
            st.info(art_ing if art_ing else "No especificados")
        with c_rec2:
            st.markdown("### 👩‍🍳 Modo de Preparación")
            st.success(art_pasos if art_pasos else "No especificados")
            
    # REACCIONES Y COMENTARIOS
    st.write("")
    col_react, col_comm = st.columns([1, 1])
    
    conteo_r = obtener_conteo_reacciones(art_id)
    with col_react:
        st.markdown("**Reacciones de la Familia:**")
        c_r1, c_r2, c_r3, c_r4 = st.columns(4)
        if c_r1.button(f"❤️ {conteo_r['❤️']}", key=f"react_love_{art_id}"):
            agregar_reaccion(art_id, "❤️")
            st.rerun()
        if c_r2.button(f"👏 {conteo_r['👏']}", key=f"react_bravo_{art_id}"):
            agregar_reaccion(art_id, "👏")
            st.rerun()
        if c_r3.button(f"😋 {conteo_r['😋']}", key=f"react_yummy_{art_id}"):
            agregar_reaccion(art_id, "😋")
            st.rerun()
        if c_r4.button(f"😍 {conteo_r['😍']}", key=f"react_like_{art_id}"):
            agregar_reaccion(art_id, "😍")
            st.rerun()

    with col_comm:
        comments = obtener_comentarios(art_id)
        with st.expander(f"💬 Comentarios ({len(comments)})"):
            for c_nom, c_txt, c_fec in comments:
                st.markdown(f"**{c_nom}** <span style='font-size:0.8rem; color:gray;'>({c_fec})</span>: {c_txt}", unsafe_allow_html=True)
            
            with st.form(key=f"form_comm_{art_id}", clear_on_submit=True):
                c_autor = st.text_input("Tu Nombre", value="Familiar", key=f"c_aut_{art_id}")
                c_texto = st.text_input("Escribe un comentario...", key=f"c_txt_{art_id}")
                if st.form_submit_button("Enviar Comentario"):
                    if c_texto.strip():
                        agregar_comentario(art_id, c_autor.strip(), c_texto.strip())
                        st.toast("Comentario enviado!")
                        st.rerun()

    st.write("---")

# ==============================================================================
# VISTAS DE LECTURA DE SECCIONES
# ==============================================================================

# --- 1. INICIO / NOVEDADES ---
if menu_sel == "🏠 Inicio / Novedades":
    st.markdown("""
        <div class="main-header">
            <h1>🏡 Rincón Familiar & Bitácora de Recuerdos</h1>
            <p style="font-size:1.2rem; font-weight:bold; margin-top:5px; color:#2c3e50;">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
            <p style="font-size:1.0rem; margin-top:5px;">El espacio para reunir nuestras vivencias, deportes, cocina y el rincón de Berta.</p>
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
                    renderizar_articulo(dest)
                    
        st.subheader("📜 Todas las Publicaciones")
        for art in arts:
            renderizar_articulo(art)

# --- 2. VISTA ESPECÍFICA: EL RINCÓN DE BERTA ---
elif menu_sel == "✍️ El Rincón de Berta":
    st.markdown("""
        <div class="berta-header">
            <h1>🌸 El Rincón de Berta</h1>
            <p style="font-size:1.15rem; font-weight:bold; margin-top:5px; color:#2c3e50;">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
            <p style="font-size:1.0rem; margin-top:5px;">Pensamientos, reflexiones, memorias y las columnas especiales escritas por Berta.</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_berta = obtener_articulos_por_seccion("✍️ El Rincón de Berta", busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_berta:
        st.info("🌷 Aún no hay artículos publicados en el Rincón de Berta. ¡Próximamente nuevas reflexiones!")
    else:
        for art in arts_berta:
            renderizar_articulo(art)

# --- 3. VISTA ESPECÍFICA: COCINA Y RECETARIO ---
elif menu_sel == "🍳 Cocina y Recetario":
    st.markdown("""
        <div class="main-header" style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 99%, #fecfef 100%);">
            <h1>🍳 El Recetario de la Familia</h1>
            <p style="font-size:1.15rem; margin-top:5px;">Nuestros platillos favoritos, postres, secretos de cocina y tradiciones culinarias.</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_cocina = obtener_articulos_por_seccion("🍳 Cocina y Recetario", busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_cocina:
        st.info("🍲 ¡Aún no hay recetas guardadas! Agrega la primera en el Panel de Administración.")
    else:
        for art in arts_cocina:
            renderizar_articulo(art)

# --- 4. OTRAS SECCIONES DINÁMICAS (Deportes, Galería, Personalizadas) ---
elif menu_sel in [s[1] for s in secciones_db]:
    sec_info = next((s for s in secciones_db if s[1] == menu_sel), None)
    
    st.markdown(f"""
        <div class="main-header">
            <h1>{sec_info[1]}</h1>
            <p style="font-size:1.15rem; margin-top:5px;">{sec_info[3] if sec_info[3] else 'Espacio de publicaciones compartidas'}</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_sec = obtener_articulos_por_seccion(menu_sel, busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_sec:
        st.info(f"📌 Aún no hay publicaciones en la sección **{menu_sel}**.")
    else:
        for art in arts_sec:
            renderizar_articulo(art)

# ==============================================================================
# PANEL DE ADMINISTRACIÓN / GESTOR DE CONTENIDOS
# ==============================================================================
elif menu_sel == "⚙️ Panel de Administración":
    st.title("⚙️ Panel de Administración del Blog Familiar")
    st.caption("Lara 1, Lara 5 y Sra. McCormick para el Mundo")
    st.write("Desde aquí puedes redactar nuevos artículos, subir fotos, videos, archivos PowerPoint/PDF, crear secciones y administrar publicaciones.")
    
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
            with st.form("form_nuevo_articulo", clear_on_submit=True):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    a_titulo = st.text_input("Título de la Publicación *")
                    a_subtitulo = st.text_input("Subtítulo o Resumen Corto", value="Lara 1, Lara 5 y Sra. McCormick para el Mundo")
                    a_autor_sel = st.selectbox("Autor(a) / Quien Publica *", ["Berta", "Lara 1", "Lara 5", "Sra. McCormick", "Familia", "Otro (Escribir)"])
                    if a_autor_sel == "Otro (Escribir)":
                        a_autor = st.text_input("Escribe el nombre del autor:", value="Berta")
                    else:
                        a_autor = a_autor_sel
                
                with col_a2:
                    a_seccion = st.selectbox("Sección / Categoría *", [s[1] for s in sec_activas])
                    a_destacado = st.checkbox("⭐ Marcar como Publicación Destacada (Aparece en la portada)")
                    
                a_contenido = st.text_area("Contenido Principal / Texto del Artículo *", height=200, help="Puedes usar formato Markdown (negritas, listas, etc.)")
                
                # Campos dinámicos si es sección de Cocina
                if "Cocina" in a_seccion:
                    st.markdown("### 🍳 Datos Especiales de Receta (Opcional)")
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        a_ingredientes = st.text_area("Lista de Ingredientes", placeholder="Ej: 2 tazas de harina, 100g de mantequilla...", height=120)
                    with col_c2:
                        a_pasos = st.text_area("Pasos de Preparación", placeholder="Ej: 1. Mezclar ingredientes dry... 2. Hornear a 180°C...", height=120)
                else:
                    a_ingredientes = None
                    a_pasos = None
                    
                st.markdown("### 📸 Adjuntar Fotografías, Videos o Documentos")
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    f_img = st.file_uploader("Subir Fotografía (JPG, PNG)", type=["jpg", "jpeg", "png", "webp"])
                with col_m2:
                    f_vid = st.file_uploader("Subir Video Corto (MP4, MOV)", type=["mp4", "mov", "webm"])
                    a_vid_url = st.text_input("O enlace de Video (YouTube/Vimeo)")
                with col_m3:
                    f_doc = st.file_uploader("Subir PowerPoint / Documento (PPTX, PDF, DOCX)", type=["pptx", "ppt", "pdf", "docx", "xlsx", "zip"])
                    
                btn_publicar = st.form_submit_button("🚀 Guardar y Publicar en el Blog", use_container_width=True)
                
                if btn_publicar:
                    if not a_titulo.strip() or not a_contenido.strip():
                        st.error("⚠️ El Título y el Contenido Principal son obligatorios.")
                    else:
                        img_b = f_img.read() if f_img else None
                        img_n = f_img.name if f_img else None
                        vid_b = f_vid.read() if f_vid else None
                        vid_n = f_vid.name if f_vid else None
                        doc_b = f_doc.read() if f_doc else None
                        doc_n = f_doc.name if f_doc else None
                        
                        guardar_articulo(
                            a_titulo.strip(), a_subtitulo.strip(), a_seccion, a_autor.strip(),
                            a_contenido.strip(), a_ingredientes, a_pasos,
                            img_b, img_n, vid_b, vid_n, a_vid_url.strip(), 1 if a_destacado else 0,
                            doc_b, doc_n
                        )
                        st.success(f"🎉 ¡Publicación '**{a_titulo}**' guardada exitosamente en la sección {a_seccion}!")
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
                        
                    st.markdown("#### 📸 Multimedia y Adjuntos (Reemplazar si deseas)")
                    col_em1, col_em2, col_em3 = st.columns(3)
                    with col_em1:
                        e_f_img = st.file_uploader("Nueva Imagen", type=["jpg", "jpeg", "png", "webp"], key=f"e_img_{pub_id}")
                    with col_em2:
                        e_f_vid = st.file_uploader("Nuevo Video", type=["mp4", "mov", "webm"], key=f"e_vid_{pub_id}")
                        e_vid_url = st.text_input("Enlace Video", value=p_data[12] if p_data[12] else "")
                    with col_em3:
                        e_f_doc = st.file_uploader("Nuevo PowerPoint / Doc", type=["pptx", "ppt", "pdf", "docx", "xlsx", "zip"], key=f"e_doc_{pub_id}")
                        
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
                        doc_b = e_f_doc.read() if e_f_doc else None
                        doc_n = e_f_doc.name if e_f_doc else None
                        
                        actualizar_articulo(
                            pub_id, e_titulo.strip(), e_subtitulo.strip(), e_seccion, e_autor.strip(),
                            e_contenido.strip(), e_ing, e_pas, img_b, img_n, vid_b, vid_n, e_vid_url.strip(), 1 if e_destacado else 0,
                            doc_b, doc_n
                        )
                        st.success(f"✅ Publicación '**{e_titulo}**' actualizada correctamente.")
                        st.toast("Cambios guardados exitosamente")
                        st.rerun()
                        
                    if btn_borrar:
                        eliminar_articulo(pub_id)
                        st.warning(f"🗑️ Publicación eliminada.")
                        st.toast("Publicación eliminada")
                        st.rerun()

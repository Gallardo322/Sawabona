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
            destacado INTEGER DEFAULT 0
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
            'Un espacio especial para guardar nuestros mejores momentos, recetas y vivencias.',
            '✍️ El Rincón de Berta',
            'Berta',
            'Nos da muchísima alegría estrenar este rincón digital para la familia.\n\nAquí podremos compartir nuestras historias deportivas, las mejores recetas de cocina, fotos de nuestras reuniones y artículos especiales.\n\n¡Esperamos que disfruten mucho este espacio hecho con todo el cariño!',
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

def guardar_articulo(titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('''
        INSERT INTO articulos (
            titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta,
            imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, f_act, destacado))
    conn.commit()
    conn.close()

def actualizar_articulo(art_id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if img_bytes is not None and vid_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            imagen_bytes=?, imagen_nombre=?, video_bytes=?, video_nombre=?, video_url=?, destacado=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, art_id))
    elif img_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            imagen_bytes=?, imagen_nombre=?, video_url=?, destacado=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_url, destacado, art_id))
    elif vid_bytes is not None:
        c.execute('''
            UPDATE articulos SET titulo=?, subtitulo=?, seccion=?, autor=?, contenido=?, ingredientes=?, pasos_receta=?,
            video_bytes=?, video_nombre=?, video_url=?, destacado=? WHERE id=?
        ''', (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, vid_bytes, vid_nom, vid_url, destacado, art_id))
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
    conn.commit()
    conn.close()

def obtener_articulos_por_seccion(seccion_nombre=None, solo_destacados=False, busqueda=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado FROM articulos WHERE 1=1'
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
    c.execute('SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado FROM articulos WHERE id = ?', (art_id,))
    row = c.fetchone()
    conn.close()
    return row

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
st.sidebar.caption("Nuestras historias, fotos, recetas y recuerdos")

secciones_db = obtener_secciones_activas()
opciones_menu = ["🏠 Inicio / Novedades"] + [s[1] for s in secciones_db] + ["⚙️ Panel de Administración"]

menu_sel = st.sidebar.radio("Navegar por el Blog", opciones_menu)

st.sidebar.write("---")
st.sidebar.markdown("💡 **Búsqueda Rápida**")
busqueda_txt = st.sidebar.text_input("Buscar palabras o temas", placeholder="Ej. receta, torneo, viaje...")

# ==============================================================================
# VISTAS DE LECTURA DE SECCIONES
# ==============================================================================

# --- 1. INICIO / NOVEDADES ---
if menu_sel == "🏠 Inicio / Novedades":
    st.markdown("""
        <div class="main-header">
            <h1>🏡 Rincón Familiar & Bitácora de Recuerdos</h1>
            <p style="font-size:1.15rem; margin-top:5px;">El espacio para reunir nuestras vivencias, deportes, cocina y el rincón de Berta.</p>
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
                    
                    if dest[8]: # Imagen
                        st.image(dest[8], use_container_width=True)
                        
                    st.write(dest[5][:200] + ("..." if len(dest[5]) > 200 else ""))
                    st.write("---")
                    
        st.subheader("📜 Todas las Publicaciones")
        for art in arts:
            with st.container():
                st.markdown(f"## {art[1]}")
                if art[2]:
                    st.markdown(f"#### _{art[2]}_")
                
                col_meta1, col_meta2 = st.columns([3, 1])
                with col_meta1:
                    st.markdown(f"<span class='badge-sec'>{art[3]}</span> &nbsp; <span class='badge-author'>✍️ {art[4]}</span>", unsafe_allow_html=True)
                with col_meta2:
                    st.caption(f"📅 {art[13]}")
                
                # Imagen adjunta
                if art[8]:
                    st.image(art[8], caption=art[9] if art[9] else art[1], use_container_width=True)
                    
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
                    st.subheader("🍳 Ficha de Receta Culinary")
                    c_rec1, c_rec2 = st.columns(2)
                    with c_rec1:
                        st.markdown("### 🛒 Ingredientes")
                        st.info(art[6] if art[6] else "No especificados")
                    with c_rec2:
                        st.markdown("### 👩‍🍳 Modo de Preparación")
                        st.success(art[7] if art[7] else "No especificados")
                        
                st.write("---")

# --- 2. VISTA ESPECÍFICA: EL RINCÓN DE BERTA ---
elif menu_sel == "✍️ El Rincón de Berta":
    st.markdown("""
        <div class="berta-header">
            <h1>🌸 El Rincón de Berta</h1>
            <p style="font-size:1.15rem; margin-top:5px;">Pensamientos, reflexiones, memorias y las columnas especiales escritas por Berta.</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts_berta = obtener_articulos_por_seccion("✍️ El Rincón de Berta", busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts_berta:
        st.info("🌷 Aún no hay artículos publicados en el Rincón de Berta. ¡Próximamente nuevas reflexiones!")
    else:
        for art in arts_berta:
            st.markdown(f"## 📖 {art[1]}")
            if art[2]:
                st.markdown(f"### _{art[2]}_")
            st.caption(f"Escrito por **{art[4]}** el 📅 {art[13]}")
            
            if art[8]:
                st.image(art[8], use_container_width=True)
            if art[10]:
                st.video(art[10])
            elif art[12]:
                st.video(art[12])
                
            st.markdown(art[5])
            st.divider()

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
            st.markdown(f"## 🥘 {art[1]}")
            if art[2]:
                st.caption(f"_{art[2]}_ | Compartido por **{art[4]}** el {art[13]}")
            
            if art[8]:
                st.image(art[8], use_container_width=True)
                
            st.markdown(art[5])
            
            col_i, col_p = st.columns(2)
            with col_i:
                st.markdown("### 🛒 Ingredientes")
                st.info(art[6] if art[6] else "Consultar en el texto principal")
            with col_p:
                st.markdown("### 👩‍🍳 Paso a Paso")
                st.success(art[7] if art[7] else "Consultar en el texto principal")
            st.divider()

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
            st.markdown(f"## {art[1]}")
            if art[2]:
                st.markdown(f"#### _{art[2]}_")
            st.caption(f"Publicado por **{art[4]}** | 📅 {art[13]}")
            
            if art[8]:
                st.image(art[8], use_container_width=True)
            if art[10]:
                st.video(art[10])
            elif art[12]:
                st.video(art[12])
                
            st.markdown(art[5])
            st.divider()

# ==============================================================================
# PANEL DE ADMINISTRACIÓN / GESTOR DE CONTENIDOS
# ==============================================================================
elif menu_sel == "⚙️ Panel de Administración":
    st.title("⚙️ Panel de Administración del Blog Familiar")
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
            with st.form("form_nuevo_articulo", clear_on_submit=True):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    a_titulo = st.text_input("Título de la Publicación *")
                    a_subtitulo = st.text_input("Subtítulo o Resumen Corto")
                    a_autor = st.text_input("Autor(a) / Quien Publica *", value="Berta")
                
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
                    
                st.markdown("### 📸 Adjuntar Elementos Multimedia (Opcional)")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    f_img = st.file_uploader("Subir Fotografía / Imagen (JPG, PNG)", type=["jpg", "jpeg", "png", "webp"])
                with col_m2:
                    f_vid = st.file_uploader("Subir Video Corto (MP4, MOV)", type=["mp4", "mov", "webm"])
                    a_vid_url = st.text_input("O ingresar enlace de Video (YouTube / Vimeo)")
                    
                btn_publicar = st.form_submit_button("🚀 Guardar y Publicar en el Blog", use_container_width=True)
                
                if btn_publicar:
                    if not a_titulo.strip() or not a_contenido.strip():
                        st.error("⚠️ El Título y el Contenido Principal son obligatorios.")
                    else:
                        img_b = f_img.read() if f_img else None
                        img_n = f_img.name if f_img else None
                        vid_b = f_vid.read() if f_vid else None
                        vid_n = f_vid.name if f_vid else None
                        
                        guardar_articulo(
                            a_titulo.strip(), a_subtitulo.strip(), a_seccion, a_autor.strip(),
                            a_contenido.strip(), a_ingredientes, a_pasos,
                            img_b, img_n, vid_b, vid_n, a_vid_url.strip(), 1 if a_destacado else 0
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
                if sesp == 0: # Las especiales no se desactivan para proteger el Rincón de Berta
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
                # p_data: id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_b, img_n, vid_b, vid_n, vid_url, fecha, destacado
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
                        st.warning(f"🗑️ Publicación eliminada.")
                        st.toast("Publicación eliminada")
                        st.rerun()

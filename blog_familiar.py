import streamlit as st
import sqlite3
import json
import os
from datetime import datetime
import base64
import urllib.parse

st.set_page_config(
    page_title="Blog Familiar - Lara 1, Lara 5 y Sra. McCormick para el Mundo",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "blog_familiar.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS secciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            icono TEXT DEFAULT '📌',
            descripcion TEXT,
            es_especial INTEGER DEFAULT 0,
            activa INTEGER DEFAULT 1
        )
    """)
    c.execute("""
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
            doc_bytes BLOB,
            doc_nombre TEXT
        )
    """)
    c.execute("PRAGMA table_info(articulos)")
    cols_art = [col[1] for col in c.fetchall()]
    if 'doc_bytes' not in cols_art:
        try:
            c.execute("ALTER TABLE articulos ADD COLUMN doc_bytes BLOB")
            c.execute("ALTER TABLE articulos ADD COLUMN doc_nombre TEXT")
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS galerias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT,
            fecha_creacion TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS galeria_fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            galeria_id INTEGER NOT NULL,
            imagen_bytes BLOB NOT NULL,
            imagen_nombre TEXT,
            comentario TEXT,
            likes INTEGER DEFAULT 0,
            FOREIGN KEY (galeria_id) REFERENCES galerias(id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS mensajes_interesados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            foto_id INTEGER,
            obra_titulo TEXT,
            nombre_interesado TEXT,
            contacto TEXT,
            mensaje TEXT,
            fecha TEXT,
            atendido INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS config_blog (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)

    c.execute('SELECT COUNT(*) FROM secciones')
    if c.fetchone()[0] == 0:
        secciones_base = [
            ('⚽ Deportes', '⚽', 'Crónicas, partidos, eventos deportivos y logros familiares', 0),
            ('🍳 Cocina y Recetario', '🍳', 'Las mejores recetas, secretos culinarios y platillos de la familia', 0),
            ('📸 Galería Multimedia', '📸', 'Álbum visual con fotografías y videos de eventos inolvidables', 0),
            ('✍️ El Rincón de Berta', '✍️', 'Espacio exclusivo para las columnas, vivencias y reflexiones de Berta', 1)
        ]
        c.executemany('INSERT INTO secciones (nombre, icono, descripcion, es_especial) VALUES (?, ?, ?, ?)', secciones_base)
    
    c.execute('SELECT COUNT(*) FROM articulos')
    if c.fetchone()[0] == 0:
        f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
            INSERT INTO articulos (titulo, subtitulo, seccion, autor, contenido, fecha_publicacion, destacado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            '¡Bienvenidos al Blog Familiar! 🏡',
            'Lara 1, Lara 5 y Sra. McCormick para el Mundo',
            '✍️ El Rincón de Berta',
            'Berta',
            """Nos da muchísima alegría estrenar este rincón digital para la familia.

Aquí podremos compartir nuestras historias deportivas, las mejores recetas de cocina, fotos de nuestras reuniones y nuestras artesanías.

¡Esperamos que disfruten mucho este espacio hecho con todo el cariño!""",
            f_act,
            1
        ))
        
    conn.commit()
    conn.close()

init_db()

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

def editar_seccion(seccion_id, nombre_viejo, nombre_nuevo, icono, descripcion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('UPDATE secciones SET nombre = ?, icono = ?, descripcion = ? WHERE id = ?',
                  (nombre_nuevo, icono, descripcion, seccion_id))
        if nombre_viejo != nombre_nuevo:
            c.execute('UPDATE articulos SET seccion = ? WHERE seccion = ?', (nombre_nuevo, nombre_viejo))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def eliminar_seccion_y_articulos(seccion_id, nombre_seccion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM articulos WHERE seccion = ?', (nombre_seccion,))
    c.execute('DELETE FROM secciones WHERE id = ?', (seccion_id,))
    conn.commit()
    conn.close()

def cambiar_estatus_seccion(seccion_id, nuevo_estatus):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE secciones SET activa = ? WHERE id = ?', (nuevo_estatus, seccion_id))
    conn.commit()
    conn.close()


# --- FUNCIONES DE ARTÍCULOS ---
def guardar_articulo(titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, doc_bytes=None, doc_nom=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
        INSERT INTO articulos (
            titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta,
            imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado,
            doc_bytes, doc_nombre
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, f_act, destacado, doc_bytes, doc_nom))
    conn.commit()
    conn.close()

def actualizar_articulo(art_id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, img_bytes, img_nom, vid_bytes, vid_nom, vid_url, destacado, doc_bytes=None, doc_nom=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    fields = ["titulo=?", "subtitulo=?", "seccion=?", "autor=?", "contenido=?", "ingredientes=?", "pasos_receta=?", "video_url=?", "destacado=?"]
    params = [titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos, vid_url, destacado]
    
    if img_bytes is not None:
        fields.extend(["imagen_bytes=?", "imagen_nombre=?"])
        params.extend([img_bytes, img_nom])
        
    if vid_bytes is not None:
        fields.extend(["video_bytes=?", "video_nombre=?"])
        params.extend([vid_bytes, vid_nom])

    if doc_bytes is not None:
        fields.extend(["doc_bytes=?", "doc_nombre=?"])
        params.extend([doc_bytes, doc_nom])
        
    params.append(art_id)
    sql = f"UPDATE articulos SET {', '.join(fields)} WHERE id=?"
    c.execute(sql, params)
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
    query = 'SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, doc_bytes, doc_nombre FROM articulos WHERE 1=1'
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
    c.execute('SELECT id, titulo, subtitulo, seccion, autor, contenido, ingredientes, pasos_receta, imagen_bytes, imagen_nombre, video_bytes, video_nombre, video_url, fecha_publicacion, destacado, doc_bytes, doc_nombre FROM articulos WHERE id = ?', (art_id,))
    row = c.fetchone()
    conn.close()
    return row

# --- FUNCIONES DE GALERÍAS Y ARTESANÍAS ---
def crear_galeria(nombre, descripcion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        c.execute('INSERT INTO galerias (nombre, descripcion, fecha_creacion) VALUES (?, ?, ?)', (nombre, descripcion, f_act))
        gid = c.lastrowid
        conn.commit()
        res = gid
    except sqlite3.IntegrityError:
        res = None
    conn.close()
    return res

def editar_galeria(galeria_id, nuevo_nombre, nueva_descripcion):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('UPDATE galerias SET nombre = ?, descripcion = ? WHERE id = ?', (nuevo_nombre, nueva_descripcion, galeria_id))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def eliminar_galeria_completa(galeria_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM galeria_fotos WHERE galeria_id = ?', (galeria_id,))
    c.execute('DELETE FROM galerias WHERE id = ?', (galeria_id,))
    conn.commit()
    conn.close()

def obtener_galerias():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, descripcion, fecha_creacion FROM galerias ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def obtener_galeria_por_id(galeria_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, nombre, descripcion, fecha_creacion FROM galerias WHERE id = ?', (galeria_id,))
    row = c.fetchone()
    conn.close()
    return row

def agregar_foto_galeria(galeria_id, img_bytes, img_nom, comentario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO galeria_fotos (galeria_id, imagen_bytes, imagen_nombre, comentario) VALUES (?, ?, ?, ?)',
              (galeria_id, img_bytes, img_nom, comentario))
    conn.commit()
    conn.close()

def obtener_fotos_galeria(galeria_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, galeria_id, imagen_bytes, imagen_nombre, comentario, likes FROM galeria_fotos WHERE galeria_id = ? ORDER BY id DESC', (galeria_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def actualizar_comentario_foto(foto_id, nuevo_comentario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE galeria_fotos SET comentario = ? WHERE id = ?', (nuevo_comentario, foto_id))
    conn.commit()
    conn.close()

def eliminar_foto_galeria(foto_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM galeria_fotos WHERE id = ?', (foto_id,))
    conn.commit()
    conn.close()

def incrementar_like_foto(foto_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE galeria_fotos SET likes = likes + 1 WHERE id = ?', (foto_id,))
    conn.commit()
    conn.close()

def guardar_mensaje_interesado(foto_id, obra_titulo, nombre, contacto, mensaje):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    f_act = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
        INSERT INTO mensajes_interesados (foto_id, obra_titulo, nombre_interesado, contacto, mensaje, fecha)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (foto_id, obra_titulo, nombre, contacto, mensaje, f_act))
    conn.commit()
    conn.close()

def obtener_mensajes_interesados():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, foto_id, obra_titulo, nombre_interesado, contacto, mensaje, fecha, atendido FROM mensajes_interesados ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def marcar_mensaje_atendido(msg_id, estatus=1):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE mensajes_interesados SET atendido = ? WHERE id = ?', (estatus, msg_id))
    conn.commit()
    conn.close()

def guardar_config(clave, valor):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO config_blog (clave, valor) VALUES (?, ?)', (clave, valor))
    conn.commit()
    conn.close()

def obtener_config(clave, default=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT valor FROM config_blog WHERE clave = ?', (clave,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


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
    .artesania-header {
        text-align: center;
        background: linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%);
        padding: 25px;
        border-radius: 15px;
        color: #2c3e50;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
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

st.sidebar.title("🏡 Blog Familiar")
st.sidebar.markdown("**Lara 1, Lara 5 y Sra. McCormick para el Mundo**")
st.sidebar.caption("Nuestras historias, fotos, recetas y artesanías")

secciones_db = obtener_secciones_activas()
opciones_menu = ["🏠 Inicio / Novedades"] + [s[1] for s in secciones_db] + ["🎨 Exposición y Artesanías", "⚙️ Panel de Administración"]

menu_sel = st.sidebar.radio("Navegar por el Blog", opciones_menu)

st.sidebar.write("---")
st.sidebar.markdown("💡 **Búsqueda Rápida**")
busqueda_txt = st.sidebar.text_input("Buscar palabras o temas", placeholder="Ej. receta, torneo, artesanía...")

def renderizar_articulo(art, key_prefix="art"):
    art_id = art[0]
    with st.container():
        st.markdown(f"## {art[1]}")
        if art[2]:
            st.markdown(f"#### _{art[2]}_" )
        
        col_meta1, col_meta2 = st.columns([3, 1])
        with col_meta1:
            st.markdown(f"<span class='badge-sec'>{art[3]}</span> &nbsp; <span class='badge-author'>✍️ {art[4]}</span>", unsafe_allow_html=True)
        with col_meta2:
            st.caption(f"📅 {art[13]}")
        
        if art[8]:
            st.image(art[8], caption=art[9] if art[9] else art[1], use_container_width=True)
            
        if art[10]:
            st.video(art[10])
        elif art[12]:
            st.video(art[12])
            
        if len(art) > 15 and art[15]:
            doc_b = art[15]
            doc_n = art[16] if art[16] else "Presentacion_Documento.pptx"
            st.info(f"📄 **Archivo adjunto**: ")
            st.download_button(
                label=f"📥 Descargar Presentación / Documento ({doc_n})",
                data=doc_b,
                file_name=doc_n,
                mime="application/octet-stream",
                key=f"{key_prefix}_dl_{art_id}"
            )

        st.markdown(art[5])
        
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

if menu_sel == "🏠 Inicio / Novedades":
    st.markdown("""
        <div class="main-header">
            <h1>🏡 Rincón Familiar & Bitácora de Recuerdos</h1>
            <p style="font-size:1.15rem; margin-top:5px;">Lara 1, Lara 5 y Sra. McCormick para el Mundo</p>
        </div>
    """, unsafe_allow_html=True)
    
    arts = obtener_articulos_por_seccion(busqueda=busqueda_txt if busqueda_txt else None)
    
    if not arts:
        st.info("👋 ¡Aún no hay publicaciones en esta sección! Ve al **Panel de Administración** para crear la primera entrada.")
    else:
        destacados = [a for a in arts if a[14] == 1]
        if destacados and not busqueda_txt:
            st.subheader("⭐ Publicaciones Destacadas")
            cols_dest = st.columns(min(len(destacados), 2))
            for i, dest in enumerate(destacados[:2]):
                with cols_dest[i % 2]:
                    renderizar_articulo(dest, key_prefix=f"dest_{i}")
                    
        st.subheader("📜 Todas las Publicaciones")
        for art in arts:
            renderizar_articulo(art, key_prefix="inicio")

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
            renderizar_articulo(art, key_prefix="berta")

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
            renderizar_articulo(art, key_prefix="cocina")

elif menu_sel == "🎨 Exposición y Artesanías":
    st.markdown("""
        <div class="artesania-header">
            <h1>🎨 Exposición Virtual & Galería de Artesanías</h1>
            <p style="font-size:1.15rem; margin-top:5px;">Exposición de piezas únicas, artesanías, cuadros y colecciones hechas con dedicado talento.</p>
        </div>
    """, unsafe_allow_html=True)
    
    galerias_list = obtener_galerias()
    
    if not galerias_list:
        st.info("🖼️ ¡Aún no hay galerías creadas para la Exposición de Artesanías! Puedes crear la primera en el **Panel de Administración** > **Gestor de Artesanías & Mensajes**.")
    else:
        nombres_g = ["🌟 Todas las Galerías"] + [g[1] for g in galerias_list]
        sel_g_filtro = st.selectbox("📂 Selecciona una Galería / Colección Temática", nombres_g)
        
        galerias_mostrar = galerias_list if sel_g_filtro == "🌟 Todas las Galerías" else [g for g in galerias_list if g[1] == sel_g_filtro]
        num_tel_wa = obtener_config("num_whatsapp", "5210000000000")
        
        for gal in galerias_mostrar:
            gid, gnom, gdesc, gfecha = gal
            st.subheader(f"🎨 {gnom}")
            if gdesc:
                st.write(f"_{gdesc}_")
            st.caption(f"📅 Creada el {gfecha}")
            
            fotos = obtener_fotos_galeria(gid)
            if not fotos:
                st.warning("Esta galería aún no contiene fotografías.")
            else:
                st.markdown("##### 🖼️ Fotografías en la Galería (Haz clic para ampliar y ver comentarios)")
                
                cols_thumb = st.columns(3)
                for idx_f, f_item in enumerate(fotos):
                    fid, f_gid, f_bytes, f_nom, f_com, f_likes = f_item
                    col_target = cols_thumb[idx_f % 3]
                    
                    with col_target:
                        st.image(f_bytes, use_container_width=True)
                        st.write(f"**{f_com if f_com else 'Artesanía'}**")
                        st.caption(f"❤️ {f_likes} Me gusta")
                        
                        with st.expander(f"🔍 Ver a tamaño real / Detalles"):
                            st.image(f_bytes, caption=f_com if f_com else gnom, use_container_width=True)
                            if f_com:
                                st.info(f"📝 **Descripción**: {f_com}")
                                
                            col_act1, col_act2 = st.columns(2)
                            with col_act1:
                                if st.button(f"❤️ Me gusta ({f_likes})", key=f"btn_like_f_{fid}"):
                                    incrementar_like_foto(fid)
                                    st.toast("¡Gracias por dar Me Gusta! ❤️")
                                    st.rerun()
                                    
                            with col_act2:
                                chk_int = st.checkbox("🛍️ Me interesa esta pieza", key=f"chk_int_{fid}")
                                
                            if chk_int:
                                st.divider()
                                st.markdown("### 💌 Opciones de Contacto con el Artista (Opción C)")
                                
                                tab_c1, tab_c2 = st.tabs(["✉️ Enviar Mensaje en el Blog", "💬 Chat Directo por WhatsApp"])
                                
                                with tab_c1:
                                    with st.form(f"form_msg_int_{fid}"):
                                        m_nombre = st.text_input("Tu Nombre Completo *")
                                        m_contacto = st.text_input("Teléfono o Correo de Contacto *")
                                        m_texto = st.text_area("Mensaje o Consulta", value=f"Hola, me interesa la pieza '{f_com if f_com else gnom}'. Quisiera más información.")
                                        
                                        if st.form_submit_button("🚀 Enviar Consulta al Artista"):
                                            if not m_nombre.strip() or not m_contacto.strip():
                                                st.error("⚠️ Por favor ingresa tu nombre y datos de contacto.")
                                            else:
                                                guardar_mensaje_interesado(fid, f_com if f_com else gnom, m_nombre.strip(), m_contacto.strip(), m_texto.strip())
                                                st.success("✅ ¡Tu mensaje ha sido enviado al artista! Te responderá muy pronto.")
                                                st.balloons()
                                                
                                with tab_c2:
                                    msg_wa_text = f"Hola, vi en el blog la artesanía '{f_com if f_com else gnom}' y me interesa obtener información para adquirirla."
                                    wa_base = base64.b64decode('aHR0cHM6Ly93YS5tZS8=').decode('utf-8')
                                    wa_url = f"{wa_base}{num_tel_wa}?text={urllib.parse.quote(msg_wa_text)}"
                                    st.markdown(f"""
                                        <a href="{wa_url}" target="_blank" style="text-decoration:none;">
                                            <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:8px; font-weight:bold; font-size:1rem; cursor:pointer; width:100%;">
                                                💬 Contactar por WhatsApp
                                            </button>
                                        </a>
                                    """, unsafe_allow_html=True)
                                    
            st.divider()

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
            renderizar_articulo(art, key_prefix=f"sec_{sec_info[0]}")


elif menu_sel == "⚙️ Panel de Administración":
    st.title("⚙️ Panel de Administración del Blog Familiar")
    st.write("Desde aquí puedes redactar publicaciones, administrar tus secciones, crear galerías de artesanías y revisar mensajes.")
    
    tab_admin1, tab_admin2, tab_admin3, tab_admin4 = st.tabs([
        "📝 Publicar Nuevo Artículo",
        "📂 Crear / Administrar Secciones",
        "✏️ Editar o Eliminar Publicaciones",
        "🎨 Gestor de Artesanías & Mensajes"
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
                    a_autor = st.selectbox("Autor(a) / Quien Publica *", ["Berta", "Lara 1", "Lara 5", "Sra. McCormick", "Familia", "Otro (Especificar)"])
                    if a_autor == "Otro (Especificar)":
                        a_autor = st.text_input("Nombre del Autor Personalizado", value="Familia")
                
                with col_a2:
                    a_seccion = st.selectbox("Sección / Categoría *", [s[1] for s in sec_activas])
                    a_destacado = st.checkbox("⭐ Marcar como Publicación Destacada (Aparece en la portada)")
                    
                a_contenido = st.text_area("Contenido Principal / Texto del Artículo *", height=200, help="Puedes usar formato Markdown (negritas, listas, etc.)")
                
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
                    
                st.markdown("### 📸 Adjuntar Elementos Multimedia y Documentos (Opcional)")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    f_img = st.file_uploader("Subir Fotografía / Imagen (JPG, PNG)", type=["jpg", "jpeg", "png", "webp"])
                    f_doc = st.file_uploader("Subir PowerPoint / Documento (PPTX, PDF, DOCX)", type=["pptx", "ppt", "pdf", "docx"])
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
                        doc_b = f_doc.read() if f_doc else None
                        doc_n = f_doc.name if f_doc else None
                        
                        guardar_articulo(
                            a_titulo.strip(), a_subtitulo.strip(), a_seccion, a_autor,
                            a_contenido.strip(), a_ingredientes, a_pasos,
                            img_b, img_n, vid_b, vid_n, a_vid_url.strip(), 1 if a_destacado else 0,
                            doc_b, doc_n
                        )
                        st.success(f"🎉 ¡Publicación '**{a_titulo}**' guardada exitosamente en la sección {a_seccion}!")
                        st.toast("¡Artículo publicado con éxito!", icon="🎉")
                        st.rerun()

    # --- TAB 2: CREAR / ADMINISTRAR SECCIONES ---
    with tab_admin2:
        st.subheader("📂 Administrador de Secciones del Blog")
        st.write("Crea nuevas secciones, cambia nombres o elimina secciones completas.")
        
        # 1. Crear Nueva Sección
        st.markdown("### ➕ Crear Nueva Sección")
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

        # 2. Editar Nombre de Sección
        st.markdown("### ✏️ Editar Nombre de la Sección")
        st.caption("Al cambiar el nombre de una sección, todas las publicaciones asociadas a ella se actualizarán automáticamente al nuevo nombre.")
        todas_sec = obtener_todas_secciones()
        if todas_sec:
            dict_s = {s[1]: s for s in todas_sec}
            sel_s_edit_name = st.selectbox("Selecciona la Sección a Editar", list(dict_s.keys()))
            s_obj = dict_s[sel_s_edit_name]
            
            with st.form(f"form_edit_sec_{s_obj[0]}"):
                col_es1, col_es2 = st.columns([1, 3])
                with col_es1:
                    e_sec_ico = st.text_input("Emoji / Icono", value=s_obj[2] if s_obj[2] else "📌")
                with col_es2:
                    e_sec_nom_raw = st.text_input("Nuevo Nombre de Sección *", value=s_obj[1])
                e_sec_desc = st.text_input("Descripción Corta", value=s_obj[3] if s_obj[3] else "")
                
                if st.form_submit_button("💾 Guardar Cambios de Sección"):
                    if not e_sec_nom_raw.strip():
                        st.error("⚠️ El nombre es obligatorio.")
                    else:
                        e_nom_full = e_sec_nom_raw.strip()
                        if e_sec_ico.strip() and not e_nom_full.startswith(e_sec_ico.strip()):
                            e_nom_full = f"{e_sec_ico.strip()} {e_nom_full}"
                            
                        res_ed = editar_seccion(s_obj[0], s_obj[1], e_nom_full, e_sec_ico.strip(), e_sec_desc.strip())
                        if res_ed:
                            st.success(f"✅ ¡Sección actualizada a '**{e_nom_full}**'! Las publicaciones anteriores se actualizaron.")
                            st.rerun()
                        else:
                            st.error("❌ Ya existe otra sección con ese nombre.")

        st.divider()

        # 3. Eliminar Sección con confirmación
        st.markdown("### 🗑️ Eliminar Sección")
        st.caption("⚠️ Al eliminar una sección, se eliminarán definitivamente todas las publicaciones asociadas a ella.")
        if todas_sec:
            dict_s_del = {s[1]: s for s in todas_sec if s[4] == 0} # Proteger especiales
            if not dict_s_del:
                st.info("No hay secciones personalizadas disponibles para borrar.")
            else:
                sel_s_del = st.selectbox("Selecciona la Sección a Eliminar", list(dict_s_del.keys()))
                s_del_obj = dict_s_del[sel_s_del]
                
                confirm_del_sec = st.checkbox(f"⚠️ Estoy seguro de eliminar la sección '{s_del_obj[1]}' y TODAS sus publicaciones definitivamente.", key=f"chk_del_s_{s_del_obj[0]}")
                if st.button(f"🗑️ Confirmar Eliminación de '{s_del_obj[1]}'", disabled=not confirm_del_sec):
                    eliminar_seccion_y_articulos(s_del_obj[0], s_del_obj[1])
                    st.warning(f"🗑️ La sección '{s_del_obj[1]}' y sus publicaciones han sido eliminadas.")
                    st.rerun()

    # --- TAB 3: EDITAR O ELIMINAR PUBLICACIONES EXISTENTES ---
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
                        
                    st.markdown("#### 📸 Multimedia y Documentos (Adjuntar solo si deseas reemplazar el actual)")
                    col_em1, col_em2 = st.columns(2)
                    with col_em1:
                        e_f_img = st.file_uploader("Nueva Imagen (Reemplazar)", type=["jpg", "jpeg", "png", "webp"], key=f"e_img_{pub_id}")
                        e_f_doc = st.file_uploader("Nuevo Documento PowerPoint / PDF (Reemplazar)", type=["pptx", "ppt", "pdf", "docx"], key=f"e_doc_{pub_id}")
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

    # --- TAB 4: GESTOR DE ARTESANÍAS, GALERÍAS Y MENSAJES ---
    with tab_admin4:
        st.subheader("🎨 Gestor de Artesanías, Galerías & Mensajes")
        
        subtab_g1, subtab_g2, subtab_g3, subtab_g4, subtab_g5 = st.tabs([
            "🖼️ Crear Nueva Galería",
            "✏️ Editar Galería",
            "🗑️ Eliminar Galería",
            "📩 Mensajes de Interesados",
            "💬 Configurar WhatsApp"
        ])
        
        # 1. Crear Nueva Galería
        with subtab_g1:
            st.markdown("### 🖼️ Crear Nueva Galería de Artesanías")
            with st.form("form_crear_galeria", clear_on_submit=True):
                g_nombre = st.text_input("Nombre de la Galería / Colección *", placeholder="Ej: Talla en Madera 2026")
                g_desc = st.text_area("Descripción General de la Galería", placeholder="Ej: Colección de piezas talladas a mano en maderas nobles...")
                
                st.markdown("### 📸 Subir Fotografías Múltiples a esta Galería")
                f_imgs_gal = st.file_uploader("Selecciona una o varias imágenes (JPG, PNG)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
                g_coment_gen = st.text_input("Breve texto / Descripción individual para las fotos subidas", placeholder="Ej: Pieza tallada a mano")
                
                if st.form_submit_button("🚀 Crear Galería y Guardar Fotos", use_container_width=True):
                    if not g_nombre.strip():
                        st.error("⚠️ El Nombre de la Galería es obligatorio.")
                    else:
                        gid_new = crear_galeria(g_nombre.strip(), g_desc.strip())
                        if gid_new is None:
                            st.error("❌ Ya existe una galería con ese nombre.")
                        else:
                            count_uploaded = 0
                            if f_imgs_gal:
                                for file_img in f_imgs_gal:
                                    agregar_foto_galeria(gid_new, file_img.read(), file_img.name, g_coment_gen.strip())
                                    count_uploaded += 1
                            st.success(f"🎉 ¡Galería '**{g_nombre}**' creada exitosamente con {count_uploaded} fotos!")
                            st.rerun()

        # 2. Editar Galería
        with subtab_g2:
            st.markdown("### ✏️ Editar Galería Existente")
            gal_all = obtener_galerias()
            if not gal_all:
                st.info("No hay galerías creadas para editar.")
            else:
                dict_gal = {g[1]: g for g in gal_all}
                sel_gal_edit = st.selectbox("Selecciona la Galería a Editar", list(dict_gal.keys()))
                g_obj_e = dict_gal[sel_gal_edit]
                
                st.markdown(f"#### 1. Editar Datos Generales de '{g_obj_e[1]}'")
                with st.form(f"form_e_gal_{g_obj_e[0]}"):
                    eg_nom = st.text_input("Nombre de Galería", value=g_obj_e[1])
                    eg_desc = st.text_area("Descripción General", value=g_obj_e[2] if g_obj_e[2] else "")
                    if st.form_submit_button("💾 Guardar Datos de Galería"):
                        res_eg = editar_galeria(g_obj_e[0], eg_nom.strip(), eg_desc.strip())
                        if res_eg:
                            st.success("✅ Galería actualizada.")
                            st.rerun()
                        else:
                            st.error("❌ Ya existe otra galería con ese nombre.")
                            
                st.divider()
                st.markdown(f"#### 2. Agregar Más Fotografías a la Galería '{g_obj_e[1]}'")
                with st.form(f"form_add_photos_{g_obj_e[0]}"):
                    f_imgs_more = st.file_uploader("Selecciona imágenes adicionales", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key=f"add_imgs_{g_obj_e[0]}")
                    g_coment_more = st.text_input("Descripción individual para estas fotos", placeholder="Ej: Nueva pieza de la colección")
                    if st.form_submit_button("➕ Subir Fotos A la Galería"):
                        if f_imgs_more:
                            cnt = 0
                            for fi in f_imgs_more:
                                agregar_foto_galeria(g_obj_e[0], fi.read(), fi.name, g_coment_more.strip())
                                cnt += 1
                            st.success(f"✅ Se agregaron {cnt} nuevas fotos a la galería.")
                            st.rerun()
                            
                st.divider()
                st.markdown(f"#### 3. Editar Texto o Eliminar Fotos de '{g_obj_e[1]}'")
                fotos_eg = obtener_fotos_galeria(g_obj_e[0])
                if not fotos_eg:
                    st.caption("Esta galería aún no tiene imágenes.")
                else:
                    for f_item in fotos_eg:
                        fid_e, _, fbytes_e, fnom_e, fcom_e, flikes_e = f_item
                        col_fe1, col_fe2 = st.columns([1, 3])
                        with col_fe1:
                            st.image(fbytes_e, use_container_width=True)
                        with col_fe2:
                            with st.form(f"form_foto_item_{fid_e}"):
                                new_fcom = st.text_input("Descripción / Texto de la Foto", value=fcom_e if fcom_e else "")
                                col_fb1, col_fb2 = st.columns(2)
                                with col_fb1:
                                    btn_sub_f = st.form_submit_button("💾 Guardar Texto")
                                with col_fb2:
                                    btn_del_f = st.form_submit_button("🗑️ Eliminar Foto")
                                    
                                if btn_sub_f:
                                    actualizar_comentario_foto(fid_e, new_fcom.strip())
                                    st.success("✅ Texto actualizado.")
                                    st.rerun()
                                if btn_del_f:
                                    eliminar_foto_galeria(fid_e)
                                    st.warning("🗑️ Foto eliminada.")
                                    st.rerun()

        # 3. Eliminar Galería
        with subtab_g3:
            st.markdown("### 🗑️ Eliminar Galería Completa")
            gal_all_del = obtener_galerias()
            if not gal_all_del:
                st.info("No hay galerías creadas.")
            else:
                dict_gal_d = {g[1]: g for g in gal_all_del}
                sel_gal_del = st.selectbox("Selecciona la Galería a Eliminar", list(dict_gal_d.keys()))
                g_obj_d = dict_gal_d[sel_gal_del]
                
                st.warning(f"⚠️ Atención: Al eliminar la galería '**{g_obj_d[1]}**', se borrarán definitivamente todas las fotografías contenidas en ella.")
                confirm_del_g = st.checkbox(f"⚠️ Estoy seguro de eliminar definitivamente la galería '{g_obj_d[1]}' y todo su contenido.", key=f"chk_del_g_{g_obj_d[0]}")
                
                if st.button(f"🗑️ Confirmar Eliminación Definitiva de '{g_obj_d[1]}'", disabled=not confirm_del_g):
                    eliminar_galeria_completa(g_obj_d[0])
                    st.warning(f"🗑️ Galería '{g_obj_d[1]}' eliminada completamente.")
                    st.rerun()

        # 4. Mensajes de Interesados
        with subtab_g4:
            st.markdown("### 📩 Mensajes de Personas Interesadas en Artesanías")
            msgs = obtener_mensajes_interesados()
            if not msgs:
                st.info("Aún no has recibido mensajes de interesados desde el blog.")
            else:
                for m in msgs:
                    mid, fid, obra, nom_int, cont_int, txt_m, f_m, at_m = m
                    with st.expander(f"{ '🔴 Pendiente' if at_m==0 else '🟢 Atendido' } | {obra} - de {nom_int} ({f_m})"):
                        st.write(f"**Interesado(a)**: {nom_int}")
                        st.write(f"**Contacto (Teléfono/Correo)**: ")
                        st.write(f"**Obra de Interés**: {obra}")
                        st.info(f"💬 **Mensaje**: {txt_m}")
                        
                        col_m_a1, col_m_a2 = st.columns(2)
                        with col_m_a1:
                            if at_m == 0:
                                if st.button("🟢 Marcar como Atendido", key=f"btn_at_{mid}"):
                                    marcar_mensaje_atendido(mid, 1)
                                    st.rerun()
                            else:
                                if st.button("🔴 Marcar como Pendiente", key=f"btn_pend_{mid}"):
                                    marcar_mensaje_atendido(mid, 0)
                                    st.rerun()

        # 5. Configurar WhatsApp
        with subtab_g5:
            st.markdown("### 💬 Configuración del Número de WhatsApp para Artesanías")
            curr_wa = obtener_config("num_whatsapp", "5210000000000")
            with st.form("form_cfg_wa"):
                new_wa = st.text_input("Número de WhatsApp (con clave de país, ej. 521XXXXXXXXXX)", value=curr_wa)
                if st.form_submit_button("💾 Guardar Número de WhatsApp"):
                    guardar_config("num_whatsapp", new_wa.strip())
                    st.success("✅ Número de WhatsApp guardado correctamente.")
                    st.rerun()

# -*- coding: utf-8 -*-
"""
Genera docs/MANUAL_ADMINISTRACION_PAGINA_WEB_PUBLICA.docx

Manual NO técnico para la persona encargada de administrar el contenido
de la página web pública de A&C Logística y Producción de Eventos LTDA.

Basado EXCLUSIVAMENTE en la versión actual del sistema:
  - Página pública:  backend/app/templates/landing/home.html  (ruta "/")
  - Login:           /admin/login  (Número de Documento + Contraseña)
  - Admin contenido: /admin/contenido (9 paneles, rol web_admin)
  - Imágenes: JPG/PNG/WebP, máx 5 MB, cuota total 50, drag & drop con preview
  - Guardado: inmediato en base de datos, sin paso de "publicar"

Uso:  python scripts/generar_manual_publico.py
"""
import os
from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ── Paleta de la marca A&C ────────────────────────────────────────────────
GOLD = RGBColor(0xB4, 0x84, 0x50)      # dorado oscuro (legible en blanco)
GOLD_HEX = "B48450"
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x6E, 0x6E, 0x6E)
RED = RGBColor(0xB0, 0x3A, 0x2E)
BOX_BG = "F7F2EC"                      # crema suave para recuadros
CAP_BG = "EFEFEF"                      # gris para marcadores de captura

FECHA = "Agosto de 2026"
VERSION = "Versión 1.0"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "docs", "MANUAL_ADMINISTRACION_PAGINA_WEB_PUBLICA.docx")
LOGO = os.path.join(BASE, "logo", "logo.jpeg")


# ═══════════════════════════ HELPERS ══════════════════════════════════════
def set_font(run, size=11, bold=False, color=BLACK, name="Segoe UI"):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def para(doc, text="", size=11, bold=False, color=BLACK, align=None,
         space_after=6, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_font(r, size, bold, color)
    r.font.italic = italic
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def h1(doc, text, page_break=True):
    if page_break:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    p = doc.add_paragraph(style="Heading 1")
    r = p.add_run(text)
    set_font(r, 20, True, GOLD)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    return p


def h2(doc, text):
    p = doc.add_paragraph(style="Heading 2")
    r = p.add_run(text)
    set_font(r, 14, True, BLACK)
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    return p


def h3(doc, text):
    p = doc.add_paragraph(style="Heading 3")
    r = p.add_run(text)
    set_font(r, 12, True, GOLD)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    return p


def bullet(doc, text, bold_prefix=None, size=11):
    p = doc.add_paragraph(style="List Bullet")
    if bold_prefix:
        r1 = p.add_run(bold_prefix)
        set_font(r1, size, True, BLACK)
    r = p.add_run(text)
    set_font(r, size, False, BLACK)
    p.paragraph_format.space_after = Pt(3)
    return p


def step(doc, n, text):
    p = doc.add_paragraph()
    r = p.add_run(f"Paso {n}. ")
    set_font(r, 11, True, GOLD)
    r2 = p.add_run(text)
    set_font(r2, 11)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Cm(0.4)
    return p


def shade(p_or_cell, hex_color):
    """Aplica color de fondo a un párrafo o celda."""
    if hasattr(p_or_cell, "_tc"):
        pr = p_or_cell._tc.get_or_add_tcPr()
    else:
        pr = p_or_cell._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    pr.append(shd)


def box(doc, title, lines, title_color=GOLD):
    """Recuadro crema con borde para notas importantes."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.rows[0].cells[0]
    shade(cell, BOX_BG)
    first = cell.paragraphs[0]
    r = first.add_run(title)
    set_font(r, 11, True, title_color)
    first.paragraph_format.space_after = Pt(4)
    for ln in lines:
        p = cell.add_paragraph()
        r = p.add_run(ln)
        set_font(r, 10.5)
        p.paragraph_format.space_after = Pt(2)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def capture(doc, text):
    """Marcador gris indicando dónde insertar una captura de pantalla."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shade(cell, CAP_BG)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("[ CAPTURA DE PANTALLA — insertar aquí: " + text + " ]")
    set_font(r, 10, True, GRAY)
    r.font.italic = True
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, htxt in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        r = p.add_run(htxt)
        set_font(r, 10.5, True, RGBColor(0xFF, 0xFF, 0xFF))
        shade(hdr[i], GOLD_HEX)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            r = p.add_run(val)
            set_font(r, 10)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def field_toc(doc):
    """Tabla de contenido de Word (se actualiza con clic derecho → Actualizar campo)."""
    p = doc.add_paragraph()
    run = p.add_run()
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = ("Tabla de contenido: haz clic derecho sobre este texto y elige "
              "«Actualizar campo» para generar el índice.")
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar)
    run._r.append(instr)
    run._r.append(fldChar2)
    run._r.append(t)
    run._r.append(fldChar3)
    return p


# ═══════════════════════════ DOCUMENTO ════════════════════════════════════
doc = Document()

# Márgenes
for s in doc.sections:
    s.top_margin = Cm(2.2)
    s.bottom_margin = Cm(2.2)
    s.left_margin = Cm(2.4)
    s.right_margin = Cm(2.4)

# Estilos base
st = doc.styles["Normal"]
st.font.name = "Segoe UI"
st.font.size = Pt(11)
st.element.rPr.rFonts.set(qn("w:ascii"), "Segoe UI")
st.element.rPr.rFonts.set(qn("w:hAnsi"), "Segoe UI")

# ─────────────────────────── PORTADA ──────────────────────────────────────
for _ in range(4):
    doc.add_paragraph()
if os.path.exists(LOGO):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(LOGO, width=Cm(4.2))
para(doc, "A&C Logística, Producción y Personal para Eventos LTDA",
     16, True, BLACK, WD_ALIGN_PARAGRAPH.CENTER, 4)
para(doc, "MANUAL DE ADMINISTRACIÓN DE LA", 24, True, GOLD,
     WD_ALIGN_PARAGRAPH.CENTER, 2)
para(doc, "PÁGINA WEB PÚBLICA", 24, True, GOLD,
     WD_ALIGN_PARAGRAPH.CENTER, 14)
para(doc, "Guía práctica para administrar y actualizar el contenido "
          "que ven los visitantes del sitio web", 12, False, GRAY,
     WD_ALIGN_PARAGRAPH.CENTER, 30)
para(doc, VERSION, 12, True, BLACK, WD_ALIGN_PARAGRAPH.CENTER, 2)
para(doc, FECHA, 12, False, GRAY, WD_ALIGN_PARAGRAPH.CENTER, 2)
para(doc, "Documento interno — Área de contenido web", 10, False, GRAY,
     WD_ALIGN_PARAGRAPH.CENTER)

# ─────────────────────── TABLA DE CONTENIDO ───────────────────────────────
doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
h2(doc, "Tabla de contenido")
field_toc(doc)
box(doc, "Cómo actualizar el índice", [
    "Al abrir el documento en Microsoft Word, haz clic derecho sobre el texto "
    "de la tabla de contenido y selecciona «Actualizar campo» → «Actualizar toda la tabla».",
])

# ─────────────────────────── 1. INTRODUCCIÓN ──────────────────────────────
h1(doc, "1. Introducción")
h2(doc, "Objetivo del manual")
para(doc, "Este manual explica, paso a paso y sin términos técnicos, cómo "
          "administrar y actualizar el contenido que ven los visitantes en la "
          "página web pública de A&C Logística y Producción de Eventos: textos, "
          "imágenes, servicios, escenarios, noticias, galería y la atención de "
          "las solicitudes que envían las personas desde la página.")
h2(doc, "Para quién está escrito")
para(doc, "Está dirigido a la persona encargada de actualizar el contenido del "
          "sitio web. No se necesitan conocimientos de programación ni de "
          "bases de datos: todo se administra desde una pantalla cómoda con "
          "formularios y botones.")
h2(doc, "Antes de empezar")
bullet(doc, "Un computador con conexión a internet y un navegador actualizado (Chrome, Edge o Firefox).")
bullet(doc, "Tu número de documento y tu contraseña de acceso al panel administrativo.")
bullet(doc, "Si no tienes credenciales o olvidaste tu contraseña, solicítalas al área de soporte de la empresa.")
box(doc, "Alcance de este manual", [
    "Este manual cubre ÚNICAMENTE la administración de la página web pública.",
    "No cubre eventos, operadores, nómina, personal, check-in ni otras "
    "funcionalidades internas del sistema; esas se administran en módulos "
    "distintos con sus propios manuales.",
])

# ─────────────────── 2. CÓMO INGRESAR AL ADMINISTRADOR ────────────────────
h1(doc, "2. Cómo ingresar al administrador de contenido")
h2(doc, "Iniciar sesión")
step(doc, 1, "Abre tu navegador e ingresa a la dirección del panel administrativo de la empresa.")
step(doc, 2, "Añade al final de la dirección lo siguiente: /admin/login "
             "(por ejemplo: www.ayceventos.com.co/admin/login). Verás la pantalla "
             "de acceso con el logo de la empresa y el título «Panel de Administración».")
step(doc, 3, "Escribe tu Número de Documento (ej.: 1234567890) y tu Contraseña.")
step(doc, 4, "Si deseas verificar la contraseña escrita, presiona el ícono del ojo "
             "que está a la derecha del campo para mostrarla u ocultarla.")
step(doc, 5, "Presiona el botón «Iniciar Sesión».")
step(doc, 6, "Si tus datos son correctos, entrarás al panel. Las personas con perfil "
             "de administrador de contenido llegan directamente a la pantalla "
             "«Administrador de contenido».")
capture(doc, "Pantalla de acceso /admin/login con los campos Número de Documento y Contraseña.")
h2(doc, "Qué ves al entrar")
para(doc, "La pantalla «Administrador de contenido» se divide en tres zonas:")
bullet(doc, "Barra superior: muestra el título de la sección en la que te encuentras "
            "(por ejemplo «Resumen del sitio»).", "• ")
bullet(doc, "Menú lateral (izquierda): contiene los nueve apartados para administrar "
            "el contenido: Resumen, Inicio (Hero), Nosotros, Servicios, Escenarios, "
            "Noticias, Galería, Solicitudes y PQRSF. En celulares este menú se abre "
            "con el botón «☰ Menú».", "• ")
bullet(doc, "Zona central: muestra el formulario o la lista de la sección "
            "seleccionada en el menú.", "• ")
para(doc, "En la parte superior derecha está el botón «⏻» para cerrar sesión "
          "cuando termines tu trabajo.")
capture(doc, "Pantalla principal del administrador de contenido, señalando el menú "
             "lateral, el título de la sección y el botón de cerrar sesión.")
box(doc, "Recomendación de seguridad", [
    "Al terminar tu jornada, siempre cierra sesión con el botón «⏻», "
    "especialmente si usas un computador compartido.",
])

# ─────────────────── 3. MAPA DE LA PÁGINA PÚBLICA ─────────────────────────
h1(doc, "3. Mapa de la página web pública")
para(doc, "La página pública se abre en la dirección principal del sitio (por "
          "ejemplo www.ayceventos.com.co). De arriba hacia abajo, el visitante "
          "ve las siguientes secciones. La última columna indica desde qué "
          "apartado del administrador se modifica cada una:")
table(doc,
      ["Sección de la página", "Qué ve el visitante", "Dónde se administra"],
      [
          ["Barra superior", "Logo y nombre de la empresa siempre visible al hacer scroll.",
           "No se edita desde este panel (diseño fijo)."],
          ["Inicio (Hero)", "Gran imagen de fondo con frase principal, descripción "
           "y dos botones.", "Pestaña «★ Inicio (Hero)»."],
          ["Servicios", "Tarjetas con los servicios que ofrece la empresa "
           "(imagen, título y descripción).", "Pestaña «◆ Servicios»."],
          ["Nosotros", "Fotografías de la empresa, título, descripción y puntos fuertes.",
           "Pestaña «✎ Nosotros»."],
          ["Grandes Escenarios", "Dos filas de tarjetas en movimiento continuo con "
           "eventos y artistas con los que se ha trabajado.",
           "Pestaña «★ Escenarios»."],
          ["Experiencia (Galería)", "Cuatro fotografías del trabajo de la empresa.",
           "Pestaña «▧ Galería»."],
          ["Noticias", "Hasta tres noticias; la primera aparece destacada con "
           "imagen grande.", "Pestaña «📰 Noticias»."],
          ["Contacto", "Formulario donde el visitante solicita una cotización.",
           "Se revisa en la pestaña «✉ Solicitudes»."],
          ["PQRSF", "Formulario de peticiones, quejas, reclamos, sugerencias y "
           "felicitaciones, con consulta de estado.", "Se revisa en la pestaña «⚖ PQRSF»."],
          ["Pie de página", "Navegación, contacto y datos de la empresa.",
           "No se edita desde este panel (diseño fijo)."],
      ],
      widths=[4.2, 6.6, 5.0])
capture(doc, "Página pública completa, con cada sección señalada con flechas y números.")

# ─────────────────────────── 4. RESUMEN ───────────────────────────────────
h1(doc, "4. Panel «▦ Resumen»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Es la pantalla de inicio del administrador. Muestra de un vistazo el "
          "estado general del contenido visible en la página pública.")
h2(doc, "¿Qué información muestra?")
bullet(doc, "Servicios activos: cantidad de tarjetas de servicios publicadas.")
bullet(doc, "Noticias publicadas: noticias con estado «Publicada».")
bullet(doc, "Escenarios activos: tarjetas del carrusel de grandes escenarios.")
bullet(doc, "Imágenes en galería: fotografías publicadas en la galería.")
bullet(doc, "Solicitudes nuevas: solicitudes de contacto pendientes de revisión.")
bullet(doc, "PQRSF nuevas: peticiones, quejas, reclamos, sugerencias o "
            "felicitaciones sin atender.")
h2(doc, "Botón «🧹 Limpiar imágenes no usadas»")
para(doc, "Con el uso del panel quedan en el servidor imágenes que fueron "
          "reemplazadas o cuyas noticias/galerías fueron eliminadas. Este botón "
          "las borra para liberar espacio. Pide confirmación antes de ejecutarse "
          "y muestra cuántas imágenes eliminó. Úsalo de vez en cuando, "
          "por ejemplo una vez al mes, o cuando el sistema avise que la cuota "
          "de imágenes está llena.")
capture(doc, "Panel Resumen con las seis tarjetas de estadísticas y el botón "
             "«Limpiar imágenes no usadas».")

# ─────────────────────────── 5. INICIO (HERO) ─────────────────────────────
h1(doc, "5. Sección «★ Inicio (Hero)»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Es la primera impresión del sitio: la franja grande con imagen de "
          "fondo, una frase corta arriba, el título principal con una parte "
          "en color dorado, un párrafo descriptivo y dos botones.")
h2(doc, "¿Dónde se modifica?")
para(doc, "En el administrador de contenido, menú lateral → «★ Inicio (Hero)».")
h2(doc, "¿Qué se puede modificar?")
table(doc,
      ["Campo del formulario", "Qué es", "Aparece en la página como"],
      [
          ["Texto pequeño (eyebrow)", "Frase corta en mayúsculas sobre el título "
           "(ej.: «LOGÍSTICA Y PRODUCCIÓN DE EVENTOS»).", "Texto dorado pequeño sobre el título."],
          ["Título principal", "La frase grande de bienvenida (ej.: «Hacemos posible»).",
           "Título gigante en la parte central."],
          ["Resaltado dorado", "Palabras finales del título que se pintan en dorado "
           "(ej.: «grandes eventos»).", "Parte dorada del título grande."],
          ["Descripción", "Párrafo que explica qué hace la empresa.", "Texto bajo el título."],
          ["Botón primario", "Texto del botón dorado (ej.: «Solicitar una cotización»).",
           "Botón principal; lleva al formulario de contacto."],
          ["Botón secundario", "Texto del segundo botón (ej.: «Conocer nuestros servicios»).",
           "Botón transparente; lleva a la sección de servicios."],
          ["URL imagen de fondo (opcional)", "Fotografía grande detrás del texto.",
           "Fondo de toda la franja inicial."],
      ],
      widths=[4.6, 6.4, 4.8])
h2(doc, "¿Cómo modificarla?")
step(doc, 1, "Entra a la pestaña «★ Inicio (Hero)». El formulario se carga con la información actual.")
step(doc, 2, "Corrige los textos que desees cambiar.")
step(doc, 3, "Si quieres cambiar la imagen de fondo: arrastra la foto nueva hasta la "
             "zona punteada «Arrastra o haz clic para subir», o haz clic sobre ella y "
             "selecciona el archivo. La imagen se sube sola y verás la vista previa.")
step(doc, 4, "Presiona el botón «Guardar sección Hero».")
step(doc, 5, "Verifica el aviso verde flotante que confirma: «Sección “hero” guardada».")
step(doc, 6, "Abre la página pública y actualízala (F5) para ver el resultado.")
box(doc, "Importante sobre los botones del Hero", [
    "En esta versión, los campos «Botón primario» y «Botón secundario» cambian "
    "ÚNICAMENTE el texto visible del botón.",
    "El destino de cada botón ya está definido por diseño: el primario baja al "
    "formulario de contacto y el secundario a la sección de servicios. "
    "No es posible cambiar hacia dónde llevan desde este panel.",
])

# ─────────────────────────── 6. NOSOTROS ──────────────────────────────────
h1(doc, "6. Sección «✎ Nosotros»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Presenta a la empresa con dos fotografías (una grande y una pequeña "
          "superpuesta), un sello circular dorado, un título y una descripción.")
h2(doc, "¿Dónde se modifica?")
para(doc, "Menú lateral → «✎ Nosotros».")
h2(doc, "¿Qué se puede modificar?")
table(doc,
      ["Campo del formulario", "Qué es", "Aparece en la página como"],
      [
          ["Texto pequeño (eyebrow)", "Frase corta en mayúsculas (ej.: «QUIÉNES SOMOS»).",
           "Texto dorado pequeño sobre el título."],
          ["Texto del badge circular", "Frase corta del sello dorado redondo "
           "(ej.: «Operación humana, técnica y confiable»).",
           "Sello dorado circular sobre la fotografía."],
          ["Título", "Título de la sección (ej.: «Un equipo preparado para cuidar cada detalle»).",
           "Título grande a la derecha de las fotos."],
          ["Descripción", "Párrafo que describe a la empresa.", "Texto bajo el título."],
          ["URL imagen principal", "Fotografía grande.", "Imagen principal de la sección."],
          ["URL imagen detalle", "Fotografía pequeña superpuesta.",
           "Imagen pequeña en la esquina inferior derecha."],
      ],
      widths=[4.6, 6.4, 4.8])
h2(doc, "¿Cómo modificarla?")
step(doc, 1, "Entra a la pestaña «✎ Nosotros».")
step(doc, 2, "Modifica los textos o sube las fotografías arrastrándolas a la zona "
             "punteada (se suben automáticamente y muestran vista previa).")
step(doc, 3, "Presiona «Guardar sección Nosotros» y espera el aviso verde de confirmación.")
step(doc, 4, "Actualiza la página pública (F5) y revisa la sección «Nosotros».")
box(doc, "Consejo de imagen", [
    "Usa una foto horizontal de buena calidad para la imagen principal; la "
    "pequeña se recorta en cuadrado. Ambas se ajustan automáticamente al espacio, "
    "por eso conviene que el motivo principal quede centrado.",
])

# ─────────────────────────── 7. SERVICIOS ─────────────────────────────────
h1(doc, "7. Sección «◆ Servicios»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Muestra en cuadrículas los servicios de la empresa (logística, "
          "brigadas, seguridad, montaje, protocolo, etc.). Cada tarjeta tiene "
          "imagen de fondo, título y descripción.")
h2(doc, "¿Dónde se modifica?")
para(doc, "Menú lateral → «◆ Servicios». Arriba está el formulario para crear o "
          "editar; abajo, la lista «Servicios actuales».")
h2(doc, "¿Qué se puede modificar?")
table(doc,
      ["Campo", "Obligatorio", "Descripción"],
      [
          ["Título", "Sí", "Nombre del servicio (ej.: «Brigadas y prevención»)."],
          ["Descripción", "Sí", "Texto corto que se lee sobre la tarjeta."],
          ["Orden", "No", "Número de posición: 1 aparece primero, 2 después, y así."],
          ["URL imagen de fondo", "No", "Foto de fondo de la tarjeta. Si se deja "
           "vacía, la tarjeta se ve oscura con el texto."],
      ],
      widths=[4.4, 2.6, 8.8])
h2(doc, "¿Cómo crear un servicio nuevo?")
step(doc, 1, "Entra a «◆ Servicios» y completa el formulario: Título, Descripción "
             "y, si lo deseas, Orden e Imagen de fondo.")
step(doc, 2, "Para la imagen, arrástrala a la zona punteada o haz clic para elegirla; "
             "se sube sola y verás la vista previa.")
step(doc, 3, "Presiona «Crear servicio» y espera el aviso verde «Servicio creado».")
step(doc, 4, "El servicio aparece en la lista inferior y de inmediato en la página pública.")
h2(doc, "¿Cómo editar un servicio existente?")
step(doc, 1, "En la lista «Servicios actuales», busca el servicio y presiona el "
             "botón de lápiz «✎» de su fila.")
step(doc, 2, "El formulario superior se llenará con los datos del servicio y el "
             "botón dirá «Guardar cambios».")
step(doc, 3, "Realiza los ajustes y presiona «Guardar cambios».")
step(doc, 4, "Si te arrepientes, presiona «Cancelar edición» para volver al modo de creación.")
h2(doc, "¿Cómo eliminar un servicio?")
para(doc, "En la lista, presiona el botón «×» rojo de la fila. Confirma en la "
          "ventana emergente. La eliminación es inmediata y la tarjeta desaparece "
          "de la página pública.")
box(doc, "Sobre el orden de las tarjetas", [
    "El campo «Orden» define la posición: números menores aparecen primero.",
    "Ejemplo: con órdenes 1, 2 y 3 las tarjetas se muestran en ese orden; "
    "si dos tienen el mismo número, se ordena por fecha de creación.",
])

# ─────────────────────────── 8. ESCENARIOS ────────────────────────────────
h1(doc, "8. Sección «★ Escenarios»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Es el carrusel en movimiento continuo con eventos y artistas de gran "
          "formato: dos filas que se desplazan en direcciones opuestas. Cada "
          "tarjeta muestra una etiqueta pequeña, el título del evento y, "
          "opcionalmente, la fecha o periodo.")
h2(doc, "¿Dónde se modifica?")
para(doc, "Menú lateral → «★ Escenarios».")
h2(doc, "¿Qué se puede modificar?")
table(doc,
      ["Campo", "Obligatorio", "Descripción"],
      [
          ["Etiqueta (eyebrow)", "Sí", "Texto dorado pequeño sobre el título "
           "(ej.: «ARTISTA INTERNACIONAL»)."],
          ["Título", "Sí", "Nombre del evento o artista (ej.: «Shakira»)."],
          ["Fecha / Periodo", "No", "Texto libre (ej.: «2025» o «Marzo 2026»)."],
          ["Orden", "No", "Posición en el carrusel."],
          ["URL imagen de fondo", "Sí", "Fotografía de la tarjeta (es obligatoria)."],
      ],
      widths=[4.4, 2.6, 8.8])
h2(doc, "¿Cómo crear un escenario nuevo?")
step(doc, 1, "Completa el formulario: Etiqueta, Título y la Imagen de fondo "
             "(obligatoria). Fecha/Periodo y Orden son opcionales.")
step(doc, 2, "Presiona «Crear escenario» y confirma con el aviso verde.")
h2(doc, "¿Cómo editar o eliminar?")
para(doc, "Igual que en Servicios: botón «✎» para editar (el botón cambia a "
          "«Guardar cambios») y «×» para eliminar con confirmación previa.")
box(doc, "Cómo se reparten las tarjetas en las dos filas", [
    "Los escenarios con orden impar (1.º, 3.º, 5.º…) se muestran en la fila "
    "superior y los de orden par (2.º, 4.º…) en la fila inferior.",
])

# ─────────────────────────── 9. NOTICIAS ──────────────────────────────────
h1(doc, "9. Sección «📰 Noticias»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Muestra las novedades de la empresa en la página pública: hasta tres "
          "noticias; la primera aparece como destacada con imagen grande. Solo "
          "las noticias en estado «Publicada» son visibles para los visitantes.")
h2(doc, "¿Dónde se modifica?")
para(doc, "Menú lateral → «📰 Noticias».")
h2(doc, "¿Qué se puede modificar?")
table(doc,
      ["Campo", "Obligatorio", "Descripción"],
      [
          ["Título", "Sí", "Titular de la noticia."],
          ["Categoría", "Sí", "Una de: Actualidad, Equipo, Eventos o Capacitación. "
           "Aparece como etiqueta en la tarjeta."],
          ["Resumen", "Sí", "Texto corto de la noticia."],
          ["Estado", "Sí", "«Publicada» (visible en la página) o «Borrador» "
           "(solo visible en el administrador)."],
          ["Orden", "No", "La noticia con menor orden aparece como destacada."],
          ["URL imagen", "No", "Foto de la noticia. Si está vacía, la destacada "
           "usa una imagen predeterminada."],
      ],
      widths=[4.4, 2.6, 8.8])
h2(doc, "¿Cómo crear una noticia?")
step(doc, 1, "Completa Título, Categoría, Resumen y Estado.")
step(doc, 2, "Si quieres imagen, arrástrala a la zona punteada.")
step(doc, 3, "Presiona «Guardar noticia» y espera el aviso verde «Noticia creada».")
h2(doc, "¿Cómo editar, publicar o eliminar?")
bullet(doc, "Editar: botón «✎» de la fila; el formulario se llena y el botón pasa "
            "a decir «Guardar cambios». «Cancelar edición» deshace la selección.")
bullet(doc, "Cambiar estado rápido: en la lista, cada noticia tiene una lista "
            "desplegable de estado (Publicada / Borrador); al cambiarla verás "
            "«Estado actualizado». Es la forma rápida de publicar un borrador.")
bullet(doc, "Eliminar: botón «×» con confirmación. La noticia desaparece de la página.")
box(doc, "¿Por qué mi noticia no se ve en la página?", [
    "Causa 1: está en estado «Borrador». Cámbiala a «Publicada».",
    "Causa 2: hay más de tres noticias publicadas: la página muestra solo las "
    "tres primeras según el campo «Orden».",
    "La primera de la lista aparece como noticia destacada (imagen grande).",
])

# ─────────────────────────── 10. GALERÍA ──────────────────────────────────
h1(doc, "10. Sección «▧ Galería»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Muestra cuatro fotografías del trabajo de la empresa en la sección "
          "«Experiencia» de la página. La primera imagen ocupa un espacio más "
          "grande que las demás.")
h2(doc, "¿Dónde se modifica?")
para(doc, "Menú lateral → «▧ Galería». El proceso tiene dos pasos: primero subir "
          "la imagen y después registrar sus datos.")
h2(doc, "¿Cómo agregar una imagen nueva?")
step(doc, 1, "En «Agregar imagen», arrastra la fotografía a la zona punteada o haz "
             "clic para seleccionarla. Verás el nombre del archivo.")
step(doc, 2, "Presiona «Subir imagen» y espera el aviso verde: «Imagen subida. "
             "Ahora asigna título y guarda».")
step(doc, 3, "Completa los campos: Título (obligatorio), Descripción corta "
             "(opcional) y Orden (opcional).")
step(doc, 4, "Presiona «Agregar a galería». La imagen aparecerá en «Galería actual».")
h2(doc, "¿Cómo eliminar una imagen?")
para(doc, "En «Galería actual», pasa el cursor sobre la miniatura y presiona el "
          "botón «×». Confirma en la ventana emergente. La imagen desaparece de "
          "la página pública de inmediato.")
box(doc, "¿Cuántas imágenes se ven en la página?", [
    "La página pública muestra las primeras cuatro imágenes según el campo «Orden».",
    "Puedes tener más imágenes guardadas y rotarlas cambiando los números de orden.",
])

# ─────────────────── 11. BANDEJA DE SOLICITUDES ───────────────────────────
h1(doc, "11. Pestaña «✉ Solicitudes»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Aquí llegan todas las solicitudes de cotización que los visitantes "
          "envían desde el formulario de contacto de la página pública. Cada "
          "solicitud muestra los datos de la persona, el servicio de interés y "
          "su mensaje. Es la bandeja de entrada comercial del sitio.")
h2(doc, "Estados de una solicitud")
table(doc,
      ["Estado", "Significado"],
      [
          ["Nueva", "Recién llegada, sin revisar."],
          ["En curso", "Ya fue vista y está siendo atendida."],
          ["Atendida", "Gestionada y cerrada."],
      ],
      widths=[4.0, 11.8])
h2(doc, "¿Cómo se usa?")
step(doc, 1, "Entra a «✉ Solicitudes». Arriba hay un filtro: Todas, Nuevas, "
             "En curso o Atendidas.")
step(doc, 2, "Lee la solicitud en la lista.")
step(doc, 3, "Presiona «En curso» cuando empiece a atenderla (el botón solo "
             "aparece si la solicitud está en otro estado).")
step(doc, 4, "Al finalizar, presiona «Atendida» para archivarla.")
step(doc, 5, "«Eliminar» borra la solicitud definitivamente (pide confirmación).")
box(doc, "No hay respuesta automática por correo", [
    "En esta versión, las solicitudes de contacto NO envían respuesta automática "
    "al visitante. El seguimiento se hace manualmente (teléfono o correo) usando "
    "los datos que la persona dejó en el formulario.",
])

# ─────────────────────────── 12. BANDEJA PQRSF ────────────────────────────
h1(doc, "12. Pestaña «⚖ PQRSF»")
h2(doc, "¿Qué es esta sección?")
para(doc, "Bandeja de Peticiones, Quejas, Reclamos, Sugerencias y Felicitaciones "
          "que envían los visitantes desde la sección PQRSF de la página pública. "
          "Incluye el código de seguimiento, los datos del solicitante y el "
          "historial de respuestas enviadas. Si el correo del sistema no está "
          "configurado, verás un aviso naranja indicándolo: en ese caso las "
          "respuestas se guardan pero no se envían por correo.")
h2(doc, "Estados y prioridades")
table(doc,
      ["Estado", "Significado"],
      [
          ["Recibida", "Recién radicada por el visitante."],
          ["En estudio", "Siendo analizada por el equipo."],
          ["Resuelta", "Con respuesta enviada al solicitante."],
          ["Cerrada", "Caso finalizado."],
      ],
      widths=[4.0, 11.8])
table(doc,
      ["Prioridad", "Uso sugerido"],
      [
          ["Baja", "Felicitaciones o sugerencias sin urgencia."],
          ["Media", "Peticiones informativas."],
          ["Alta", "Quejas y reclamos que requieren atención prioritaria "
           "(recuerde: máximo 15 días hábiles de respuesta)."],
      ],
      widths=[4.0, 11.8])
h2(doc, "¿Cómo responder una PQRSF?")
step(doc, 1, "Entra a «⚖ PQRSF» y ubica la solicitud (usa el filtro: Todas, "
             "Recibidas, En estudio, Resueltas o Cerradas).")
step(doc, 2, "Si lo deseas, ajusta la Prioridad con la lista desplegable de la fila.")
step(doc, 3, "Presiona el botón «Responder» de la fila. Se abrirá la ventana "
             "«Responder PQRSF» con los datos del solicitante y el historial de "
             "respuestas anteriores.")
step(doc, 4, "Escribe el Asunto del correo (mínimo 5 caracteres) y la Respuesta "
             "(mínimo 10 caracteres).")
step(doc, 5, "Presiona «Enviar respuesta». Verás el aviso verde «✓ Respuesta "
             "enviada al correo del solicitante» y la PQRSF pasará automáticamente "
             "al estado «Resuelta».")
step(doc, 6, "Para cerrar la ventana sin enviar, presiona «Cancelar», la «✕» o haz "
             "clic fuera de la ventana.")
box(doc, "Si el aviso dice «Guardar respuesta (sin envío real)»", [
    "Ese texto indica que el correo electrónico del sistema no está configurado "
    "o está deshabilitado. La respuesta se guarda en el historial y el estado "
    "cambia, pero el solicitante NO recibe correo.",
    "En ese caso: 1) notifique al área de soporte técnico para configurar el "
    "envío de correos y 2) comuníquese manualmente con el solicitante usando los "
    "datos de contacto registrados.",
])
h2(doc, "Cambiar estado y eliminar")
bullet(doc, "Estado: cada fila tiene una lista desplegable (Recibida, En estudio, "
            "Resuelta, Cerrada). El cambio se aplica al elegir la opción.")
bullet(doc, "Eliminar: botón «Eliminar» de la fila, con confirmación. Acción "
            "definitiva; elimina también el historial de respuestas.")

# ───────────────────── 13. CATÁLOGO DE BOTONES ────────────────────────────
h1(doc, "13. Catálogo completo de botones")
para(doc, "Lista de todos los botones que existen realmente en el administrador "
          "de contenido, incluidos los que solo muestran un ícono.")

h3(doc, "Acceso y navegación")
table(doc,
      ["Botón", "Función", "Qué sucede al presionarlo"],
      [
          ["Iniciar Sesión", "Entrar al panel.", "Valida documento y contraseña; "
           "entra al administrador de contenido."],
          ["Ojo (en la contraseña)", "Mostrar u ocultar la contraseña escrita.",
           "Alterna el texto entre visible y puntos."],
          ["☰ Menú (solo celulares)", "Abrir el menú lateral.", "Despliega las "
           "nueve secciones del administrador."],
          ["⏻ (cerrar sesión)", "Salir del panel.", "Cierra la sesión y regresa a "
           "la pantalla de acceso."],
          ["▦ / ★ / ✎ / ◆ / ★ / 📰 / ▧ / ✉ / ⚖ (menú lateral)", "Moverse entre las "
           "secciones: Resumen, Inicio (Hero), Nosotros, Servicios, Escenarios, "
           "Noticias, Galería, Solicitudes y PQRSF.", "Cambia el formulario o lista "
           "central y el título de la barra superior."],
      ],
      widths=[4.4, 4.8, 6.6])

h3(doc, "Botones de guardado y formularios")
table(doc,
      ["Botón", "Dónde está", "Función"],
      [
          ["Guardar sección Hero", "Pestaña Inicio (Hero).", "Guarda todos los "
           "textos y la imagen de fondo de la franja inicial."],
          ["Guardar sección Nosotros", "Pestaña Nosotros.", "Guarda textos, sello "
           "y las dos fotografías de la sección."],
          ["Crear servicio", "Pestaña Servicios (modo creación).", "Crea la tarjeta "
           "de un servicio nuevo."],
          ["Guardar cambios", "Servicios / Escenarios / Noticias (modo edición).",
           "Actualiza el elemento seleccionado. Aparece tras presionar «✎»."],
          ["Cancelar edición", "Servicios / Escenarios / Noticias.", "Abandona la "
           "edición y limpia el formulario sin guardar."],
          ["Crear escenario", "Pestaña Escenarios (modo creación).", "Crea una "
           "tarjeta nueva para el carrusel."],
          ["Guardar noticia", "Pestaña Noticias (modo creación).", "Crea una "
           "noticia nueva."],
          ["Subir imagen", "Pestaña Galería, paso 1.", "Sube la fotografía al "
           "servidor; luego se habilita el formulario de datos."],
          ["Agregar a galería", "Pestaña Galería, paso 2.", "Publica la imagen "
           "subida con su título, descripción y orden."],
      ],
      widths=[4.4, 5.2, 6.2])

h3(doc, "Botones por fila (listas)")
table(doc,
      ["Botón", "Dónde está", "Función"],
      [
          ["✎ (lápiz)", "Servicios, Escenarios y Noticias.", "Abre el elemento en "
           "el formulario superior para editarlo."],
          ["× (rojo)", "Servicios, Escenarios, Noticias y Galería.", "Elimina el "
           "elemento tras pedir confirmación."],
          ["En curso", "Solicitudes.", "Marca la solicitud como en atención."],
          ["Atendida", "Solicitudes.", "Marca la solicitud como gestionada/archivada."],
          ["Eliminar", "Solicitudes y PQRSF.", "Borra definitivamente el registro "
           "tras confirmación."],
          ["Responder", "PQRSF.", "Abre la ventana de respuesta con historial."],
      ],
      widths=[4.4, 5.2, 6.2])

h3(doc, "Ventana de respuesta PQRSF")
table(doc,
      ["Botón", "Función"],
      [
          ["Enviar respuesta / Guardar respuesta (sin envío real)", "Registra la "
           "respuesta y la envía al correo del solicitante. Si el correo del "
           "sistema no está configurado, solo la guarda y el botón cambia de nombre."],
          ["Cancelar", "Cierra la ventana sin guardar la respuesta."],
          ["✕", "Cierra la ventana (igual que Cancelar)."],
      ],
      widths=[6.6, 9.2])

h3(doc, "Listas desplegables y filtros")
table(doc,
      ["Control", "Dónde está", "Opciones"],
      [
          ["Estado de noticia", "Lista de noticias.", "Publicada / Borrador."],
          ["Filtro de solicitudes", "Pestaña Solicitudes.", "Todas, Nuevas, En "
           "curso, Atendidas."],
          ["Filtro de PQRSF", "Pestaña PQRSF.", "Todas, Recibidas, En estudio, "
           "Resueltas, Cerradas."],
          ["Estado de PQRSF", "Cada fila de la bandeja.", "Recibida, En estudio, "
           "Resuelta, Cerrada."],
          ["Prioridad de PQRSF", "Cada fila de la bandeja.", "Baja, Media, Alta."],
          ["Categoría de noticia", "Formulario de noticias.", "Actualidad, Equipo, "
           "Eventos, Capacitación."],
      ],
      widths=[4.6, 4.4, 6.8])

# ─────────────────────────── 14. IMÁGENES ─────────────────────────────────
h1(doc, "14. Gestión de imágenes")
h2(doc, "Formatos y límites")
table(doc,
      ["Regla", "Valor"],
      [
          ["Formatos aceptados", "JPG, PNG y WebP."],
          ["Tamaño máximo por imagen", "5 MB (megabytes)."],
          ["Cuota total de imágenes", "50 imágenes entre noticias y galería. "
           "Al llegar al límite, el sistema pedirá eliminar imágenes antes de "
           "subir nuevas."],
          ["Compresión automática", "El sistema no comprime ni recorta las "
           "imágenes: se publican tal cual se suben. Por eso se recomienda subir "
           "fotografías ya optimizadas."],
      ],
      widths=[6.0, 9.8])
h2(doc, "Cómo subir o reemplazar una imagen")
para(doc, "Todos los campos de imagen funcionan igual (Hero, Nosotros, Servicios, "
          "Escenarios, Noticias y Galería):")
step(doc, 1, "Arrastra la fotografía hasta la zona punteada «Arrastra o haz clic "
             "para subir», o haz clic sobre la zona y elige el archivo en tu computador.")
step(doc, 2, "La imagen se sube automáticamente y aparece una vista previa. "
             "Si la sube otra persona o usas una imagen ya publicada, también "
             "puedes pegar la dirección (URL) directamente en el campo de texto.")
step(doc, 3, "Presiona el botón de guardar de ese formulario.")
step(doc, 4, "Verás el aviso verde de confirmación y la imagen quedará publicada.")
h2(doc, "Cómo eliminar una imagen")
bullet(doc, "Galería: botón «×» sobre la miniatura.")
bullet(doc, "Hero, Nosotros, Servicios, Escenarios o Noticias: borra el contenido "
            "del campo de imagen y guarda; el elemento volverá a su fondo oscuro "
            "o a la imagen predeterminada del diseño.")
para(doc, "Las imágenes reemplazadas quedan guardadas en el servidor como "
          "«no usadas». Para liberar ese espacio usa el botón «🧹 Limpiar imágenes "
          "no usadas» del panel Resumen.")
h2(doc, "Recomendaciones de dimensiones")
bullet(doc, "Hero: imagen horizontal amplia, tipo panorámica (se recomienda de al "
            "menos 1600 píxeles de ancho). El sistema recorta al centro según la "
            "pantalla del visitante.")
bullet(doc, "Servicios, Escenarios y Noticias: formato horizontal (por ejemplo "
            "1200 × 800 píxeles).")
bullet(doc, "Nosotros: la imagen principal horizontal y la pequeña en cuadrado.")
bullet(doc, "Galería: horizontal; la primera imagen de la lista se muestra más grande.")
box(doc, "No hay versiones separadas para computador y celular", [
    "El sistema usa una única imagen por elemento y la adapta automáticamente al "
    "tamaño de pantalla (recorte centrado). Por eso el motivo principal de la "
    "fotografía debe quedar al centro para que no se pierda en celulares.",
])
capture(doc, "Zona de carga de imágenes con drag & drop y vista previa, "
             "señalando «Arrastra o haz clic para subir».")

# ─────────────────────────── 15. TEXTOS ───────────────────────────────────
h1(doc, "15. Gestión de textos")
para(doc, "Todos los textos visibles de la página se editan desde las pestañas "
          "ya descritas. Resumen de dónde está cada texto:")
table(doc,
      ["Texto de la página", "Dónde se cambia"],
      [
          ["Frase superior y título del Hero (con su parte dorada)", "Pestaña «★ Inicio (Hero)»."],
          ["Descripción del Hero y texto de sus dos botones", "Pestaña «★ Inicio (Hero)»."],
          ["Título, descripción y sello de «Nosotros»", "Pestaña «✎ Nosotros»."],
          ["Título y descripción de cada servicio", "Pestaña «◆ Servicios»."],
          ["Etiqueta y título de cada escenario", "Pestaña «★ Escenarios»."],
          ["Título, categoría y resumen de cada noticia", "Pestaña «📰 Noticias»."],
          ["Título y descripción de cada imagen de galería", "Pestaña «▧ Galería»."],
          ["Textos de la barra superior y del pie de página", "Diseño fijo: no se "
           "editan desde el panel."],
      ],
      widths=[8.2, 7.6])
h2(doc, "Reglas prácticas")
bullet(doc, "Los campos marcados con asterisco (*) son obligatorios: no se puede "
            "guardar sin completarlos.")
bullet(doc, "Los campos largos (descripciones, resúmenes) aceptan saltos de línea "
            "y signos normales (¡!, ¿?, tildes, ñ).")
bullet(doc, "Escribe frases completas y revisa la ortografía antes de guardar: "
            "el texto se publica exactamente como lo escribas.")
bullet(doc, "En «Resaltado dorado» escribe solo las palabras finales del título; "
            "se mostrarán en color dorado junto al título principal.")
bullet(doc, "Evita textos demasiado largos en títulos: en celulares el texto muy "
            "largo se corta o ocupa varias líneas.")

# ─────────────────────── 16. ENLACES Y BOTONES ────────────────────────────
h1(doc, "16. Enlaces y botones de la página")
para(doc, "Qué se puede y qué no se puede configurar desde el panel en esta versión:")
bullet(doc, "Texto de los botones del Hero: SÍ se cambia (campos «Botón primario» "
            "y «Botón secundario»).", "• ")
bullet(doc, "Destino de los botones del Hero: NO. El botón primario siempre baja al "
            "formulario de contacto y el secundario a la sección de servicios.", "• ")
bullet(doc, "Enlaces del menú de navegación y del pie de página: NO se editan desde "
            "el panel (son internos y fijos por diseño).", "• ")
bullet(doc, "Redes sociales, WhatsApp o enlaces externos: NO existen campos para "
            "configurarlos en esta versión.", "• ")
bullet(doc, "Correos y teléfonos visibles en la página: forman parte del diseño fijo "
            "(contacto@ empresa y pie de página); su actualización requiere soporte técnico.", "• ")
box(doc, "Cómo comprobar un botón", [
    "Después de cambiar el texto de un botón del Hero: 1) guarda, 2) abre la "
    "página pública, 3) actualiza con F5 y 4) haz clic en el botón para confirmar "
    "que sigue llevando a su sección (contacto o servicios).",
])

# ──────────────────── 17. ORDEN Y VISIBILIDAD ─────────────────────────────
h1(doc, "17. Orden y visibilidad de los elementos")
h2(doc, "Cambiar el orden")
para(doc, "Los campos «Orden» (Servicios, Escenarios, Noticias y Galería) "
          "funcionan igual: un número por elemento; los números menores aparecen "
          "primero en la página. Ejemplo: para que una noticia sea la destacada "
          "(la grande), asígnale el número más bajo, por ejemplo 1.")
h2(doc, "Mostrar u ocultar")
bullet(doc, "Noticias: usa el estado «Borrador» para ocultar una noticia sin "
            "eliminarla y «Publicada» para mostrarla.")
bullet(doc, "Servicios, Escenarios y Galería: no existe la opción de ocultar; "
            "para quitarlos de la página hay que eliminarlos.")
bullet(doc, "Secciones completas (Hero, Nosotros, etc.): no se pueden activar ni "
            "desactivar; siempre están visibles.")
h2(doc, "Crear y eliminar elementos")
bullet(doc, "Se pueden crear elementos nuevos en Servicios, Escenarios, Noticias y Galería.")
bullet(doc, "Todos los elementos se pueden eliminar con su botón «×» (siempre pide "
            "confirmación; la eliminación no se puede deshacer).")
box(doc, "Antes de eliminar", [
    "La eliminación es definitiva. Si solo quieres quitar algo de la página por "
    "un tiempo, en Noticias usa «Borrador»; en los demás módulos copia los datos "
    "(título, descripción y URL de imagen) en un documento antes de eliminar.",
])

# ─────────────────── 18. GUARDADO Y PUBLICACIÓN ───────────────────────────
h1(doc, "18. Guardado y publicación de cambios")
h2(doc, "¿Cómo funciona realmente el guardado?")
para(doc, "Cuando presionas un botón de guardar, la información viaja "
          "inmediatamente al servidor de la página y queda almacenada en su base "
          "de datos. La página pública lee esa base de datos cada vez que un "
          "visitante la abre. En otras palabras:")
box(doc, "Flujo real de publicación", [
    "Administrador → presiona Guardar → aviso verde de confirmación → la "
    "información queda almacenada en el servidor → la página pública la muestra "
    "de inmediato.",
])
h2(doc, "¿Tengo que «publicar» algo más?")
para(doc, "No. No existe un botón de «publicar», ni borradores globales, ni pasos "
          "adicionales. Con el aviso verde de confirmación el cambio ya quedó "
          "publicado. La única excepción son las noticias en estado «Borrador», "
          "que permanecen ocultas hasta que cambies su estado a «Publicada».")
h2(doc, "Confirmaciones y avisos")
bullet(doc, "Aviso verde flotante (esquina): la acción se completó correctamente.")
bullet(doc, "Aviso rojo flotante: ocurrió un error; lee el mensaje (indica el "
            "problema, por ejemplo un campo obligatorio vacío).")
bullet(doc, "Ventanas emergentes de confirmación: aparecen antes de eliminar "
            "algo; presiona «Aceptar» solo si estás seguro.")

# ─────────────────── 19. VERIFICACIÓN DE CAMBIOS ──────────────────────────
h1(doc, "19. ¿Cómo verificar que mi cambio se realizó correctamente?")
step(doc, 1, "Guarda el cambio y espera el aviso verde de confirmación (si aparece "
             "rojo, corrige lo que indica el mensaje).")
step(doc, 2, "Abre la página pública en una pestaña nueva del navegador.")
step(doc, 3, "Si ya estaba abierta, actualízala con la tecla F5 (o Ctrl+F5 si "
             "sigue mostrando lo anterior).")
step(doc, 4, "Ve a la sección que modificaste (usa el menú de navegación de la página).")
step(doc, 5, "Comprueba textos, imágenes y botones. En imágenes, revisa que se vean "
             "bien; en celulares también (puedes abrir la página en tu teléfono).")
h2(doc, "¿Qué hacer si el cambio no aparece?")
bullet(doc, "Confirma que viste el aviso verde al guardar; si no, guarda de nuevo.")
bullet(doc, "Actualiza con Ctrl+F5 (fuerza refrescar todo el contenido).")
bullet(doc, "Si es una noticia: verifica que su estado sea «Publicada» y que esté "
            "entre las tres primeras por orden.")
bullet(doc, "Si es una imagen: vuelve a entrar al administrador y confirma que la "
             "vista previa del campo muestra la imagen correcta.")
bullet(doc, "Si sigue sin verse, cierra sesión, vuelve a iniciar y repite el cambio; "
             "si persiste, repórtalo a soporte técnico indicando la sección, "
             "el campo y la hora del intento.")

# ─────────────────────── 20. PROBLEMAS FRECUENTES ─────────────────────────
h1(doc, "20. Problemas frecuentes y soluciones")
table(doc,
      ["Problema", "Causa probable", "Solución"],
      [
          ["El cambio no aparece en la página.", "Navegador mostrando versión "
           "anterior, o noticia en Borrador.",
           "Actualiza con Ctrl+F5. En noticias, cambia el estado a «Publicada»."],
          ["La imagen no sube.", "Formato no permitido, archivo mayor a 5 MB o "
           "cuota de 50 imágenes llena.",
           "Usa JPG, PNG o WebP de menos de 5 MB. Si la cuota está llena, elimina "
           "imágenes y usa «🧹 Limpiar imágenes no usadas»."],
          ["La imagen se ve recortada o deformada.", "La plantilla ajusta la foto "
           "al espacio disponible (recorte centrado).",
           "Usa fotos horizontales con el motivo principal al centro."],
          ["No puedo guardar (aparece aviso rojo).", "Falta un campo obligatorio (*) "
           "o perdiste la sesión.",
           "Completa los campos marcados con * y guarda de nuevo. Si el problema "
           "continúa, cierra sesión, vuelve a entrar y reintenta."],
          ["El texto sale cortado en celulares.", "Título o texto demasiado largo.",
           "Usa títulos cortos y directos."],
          ["La noticia aparece en el administrador pero no en la página.",
           "Está en estado «Borrador» o no está entre las tres primeras por orden.",
           "Publícala y revisa el campo «Orden»."],
          ["«Cuota máxima de imágenes alcanzada».", "Ya hay 50 imágenes entre "
           "noticias y galería.",
           "Elimina imágenes que no uses y ejecuta «Limpiar imágenes no usadas»."],
          ["La respuesta de PQRSF dice «guardada pero NO enviada».", "El envío de "
           "correos del sistema no está configurado.",
           "Contacta manualmente al solicitante y notifica a soporte técnico para "
           "configurar el correo."],
          ["Se borró un elemento por error.", "La eliminación fue confirmada y es "
           "definitiva.", "Recréalo con los datos que recuerdes. Antes de eliminar, "
           "copia siempre la información."],
      ],
      widths=[4.6, 5.0, 6.2])

# ─────────────────────────── 21. BUENAS PRÁCTICAS ─────────────────────────
h1(doc, "21. Buenas prácticas para el administrador de contenido")
bullet(doc, "Revisa la ortografía y redacción antes de guardar; el texto se publica tal cual.")
bullet(doc, "Usa imágenes optimizadas (JPG o WebP, menos de 5 MB) para que la "
            "página cargue rápido.")
bullet(doc, "Mantén títulos claros y cortos; piensa en cómo se verán en un celular.")
bullet(doc, "No elimines información sin verificar antes que no sea necesaria.")
bullet(doc, "Verifica cada cambio en la página pública después de guardar.")
bullet(doc, "Revisa la página también desde un celular de vez en cuando.")
bullet(doc, "Usa el estado «Borrador» para preparar noticias sin publicarlas aún.")
bullet(doc, "Atiende la bandeja de Solicitudes y PQRSF con frecuencia; recuerda el "
            "plazo máximo legal de 15 días hábiles para responder PQRSF.")
bullet(doc, "No modifiques campos cuyo funcionamiento no conozcas; consulta este "
            "manual o a soporte técnico.")
bullet(doc, "Haz los cambios de forma ordenada: una sección a la vez, guardando y "
            "verificando antes de pasar a la siguiente.")
bullet(doc, "Cierra sesión al terminar, sobre todo en computadores compartidos.")
bullet(doc, "Copia la información (título, descripción, URL de imagen) en un "
            "documento aparte antes de eliminar cualquier elemento.")

# ─────────────────────────── 22. CAPTURAS ─────────────────────────────────
h1(doc, "22. Guía para incorporar las capturas de pantalla")
para(doc, "A lo largo del documento se marcaron con recuadros grises los puntos "
          "donde deben insertarse capturas reales de la versión actual del "
          "sistema. Lista completa y sugerencia de anotación:")
table(doc,
      ["N.º", "Captura pendiente", "Anotaciones sugeridas"],
      [
          ["1", "Pantalla de acceso /admin/login.", "[1] Campo Número de Documento, "
           "[2] Campo Contraseña, [3] Botón Iniciar Sesión."],
          ["2", "Pantalla principal del administrador de contenido.",
           "[1] Menú lateral, [2] Título de sección, [3] Botón cerrar sesión."],
          ["3", "Página pública completa.", "Flechas numerando cada sección del capítulo 3."],
          ["4", "Panel Resumen.", "[1] Tarjetas de estadísticas, [2] Botón Limpiar imágenes."],
          ["5", "Formulario del Hero.", "[1] Título principal, [2] Resaltado dorado, "
           "[3] Zona de imagen, [4] Botón Guardar."],
          ["6", "Formulario Nosotros.", "[1] Badge circular, [2] Imagen principal, "
           "[3] Imagen detalle."],
          ["7", "Pestaña Servicios.", "[1] Formulario, [2] Lista con botones ✎ y ×."],
          ["8", "Pestaña Escenarios.", "[1] Campos obligatorios, [2] Lista actual."],
          ["9", "Pestaña Noticias.", "[1] Estado Publicada/Borrador, [2] Selector "
           "de estado en la lista."],
          ["10", "Pestaña Galería.", "[1] Zona de arrastre, [2] Botón Subir imagen, "
           "[3] Botón Agregar a galería."],
          ["11", "Bandeja Solicitudes.", "[1] Filtro, [2] Botones En curso/Atendida/Eliminar."],
          ["12", "Bandeja PQRSF.", "[1] Filtro, [2] Selector de estado y prioridad, "
           "[3] Botón Responder."],
          ["13", "Ventana Responder PQRSF.", "[1] Asunto, [2] Respuesta, "
           "[3] Botón Enviar respuesta."],
          ["14", "Página pública mostrando un cambio real aplicado.", "Antes y "
           "después del cambio."],
      ],
      widths=[1.2, 7.0, 7.6])
box(doc, "Cómo insertarlas", [
    "Abre el documento en Word, ubica cada recuadro gris, elimina su texto y "
    "usa Insertar → Imágenes. Añade las anotaciones con cuadros de texto o "
    "flechas, y actualiza la tabla de contenido al final (clic derecho → "
    "Actualizar campo).",
])

# ─────────────────────────── GUARDAR ──────────────────────────────────────
os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc.save(OUT)
print("Manual generado:", OUT)
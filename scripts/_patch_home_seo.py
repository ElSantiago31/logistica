# -*- coding: utf-8 -*-
"""Parche SEO para home.html (aplicación atómica de los cambios restantes).

Se ejecuta UNA vez. Verifica que cada patrón exista exactamente 1 vez antes
de reemplazar; si alguno falla, NO escribe nada (transaccional).
"""
import io
import sys

PATH = r"backend/app/templates/landing/home.html"

FAQ_SECTION = u'''  <!-- ===== FAQ (SEO: contenido visible espejo del FAQPage JSON-LD) ===== -->
  <section class="section" id="faq" style="background: var(--ayc-black); border-top: 1px solid rgba(207,155,98,.12);">
    <div class="container-ayc">
      <span class="eyebrow reveal">Preguntas frecuentes</span>
      <h2 class="section-title reveal">Resolvemos tus dudas antes de tu evento.</h2>

      <div class="faq-list reveal">
        <details class="faq-item">
          <summary>&iquest;Qu&eacute; servicios ofrece A&C Log&iacute;stica y Producci&oacute;n de Eventos?</summary>
          <p>Ofrecemos personal log&iacute;stico, brigadas y prevenci&oacute;n, seguridad y control, montaje y producci&oacute;n,
            protocolo y atenci&oacute;n, y personal especializado para eventos de cualquier escala en Bogot&aacute; y su &aacute;rea
            metropolitana.</p>
        </details>
        <details class="faq-item">
          <summary>&iquest;C&oacute;mo solicito una cotizaci&oacute;n para mi evento?</summary>
          <p>Completa el formulario de contacto de esta p&aacute;gina indicando fecha, ciudad, tipo de evento y
            necesidades principales, o escr&iacute;benos a info@ayceventos.com.co. Nuestro equipo te contactar&aacute; con una
            propuesta inicial.</p>
        </details>
        <details class="faq-item">
          <summary>&iquest;C&oacute;mo puedo trabajar o vincularme como operador de A&C?</summary>
          <p>Ingresa a la secci&oacute;n Trabaja con nosotros y completa tu registro. All&iacute; podr&aacute;s crear tu perfil para
            ser tenido en cuenta en las convocatorias de personal para eventos.</p>
        </details>
        <details class="faq-item">
          <summary>&iquest;C&oacute;mo presento una PQRSF y en cu&aacute;nto tiempo responden?</summary>
          <p>Puedes radicar tu petici&oacute;n, queja, reclamo, sugerencia o felicitaci&oacute;n en el formulario PQRSF de esta
            p&aacute;gina. Recibir&aacute;s un c&oacute;digo de seguimiento y la respuesta se enviar&aacute; a tu correo en m&aacute;ximo 15 d&iacute;as
            h&aacute;biles, conforme a la Ley 1755 de 2015.</p>
        </details>
      </div>
    </div>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "\u00bfQu\u00e9 servicios ofrece A&C Log\u00edstica y Producci\u00f3n de Eventos?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Ofrecemos personal log\u00edstico, brigadas y prevenci\u00f3n, seguridad y control, montaje y producci\u00f3n, protocolo y atenci\u00f3n, y personal especializado para eventos de cualquier escala en Bogot\u00e1 y su \u00e1rea metropolitana."
          }
        },
        {
          "@type": "Question",
          "name": "\u00bfC\u00f3mo solicito una cotizaci\u00f3n para mi evento?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Completa el formulario de contacto de esta p\u00e1gina indicando fecha, ciudad, tipo de evento y necesidades principales, o escr\u00edbenos a info@ayceventos.com.co. Nuestro equipo te contactar\u00e1 con una propuesta inicial."
          }
        },
        {
          "@type": "Question",
          "name": "\u00bfC\u00f3mo puedo trabajar o vincularme como operador de A&C?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Ingresa a la secci\u00f3n Trabaja con nosotros y completa tu registro. All\u00ed podr\u00e1s crear tu perfil para ser tenido en cuenta en las convocatorias de personal para eventos."
          }
        },
        {
          "@type": "Question",
          "name": "\u00bfC\u00f3mo presento una PQRSF y en cu\u00e1nto tiempo responden?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Puedes radicar tu petici\u00f3n, queja, reclamo, sugerencia o felicitaci\u00f3n en el formulario PQRSF de esta p\u00e1gina. Recibir\u00e1s un c\u00f3digo de seguimiento y la respuesta se enviar\u00e1 a tu correo en m\u00e1ximo 15 d\u00edas h\u00e1biles, conforme a la Ley 1755 de 2015."
          }
        }
      ]
    }
    </script>
  </section>

'''

# (nombre, buscar, reemplazar) — usar Marcadores abajo; se adaptan a \r\n si aplica.
EDITS = []

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    content = f.read()

nl = "\r\n" if "\r\n" in content else "\n"


def n(s):
    return s.replace("\n", nl)


def add(name, old, new):
    EDITS.append((name, n(old), n(new)))


# 1) FAQ antes de la sección contacto
add(
    "faq_section",
    '  <section class="section" id="contacto">',
    FAQ_SECTION.rstrip("\n").replace("\n", nl) + nl + nl + '  <section class="section" id="contacto">',
)

# 2) Footer: enlaces de navegación ampliados
add(
    "footer_nav",
    '''        <a href="#noticias">Noticias</a>
        <a href="#contacto">Contacto</a>
        <a href="#pqrsf">PQRSF</a>
      </div>''',
    '''        <a href="#noticias">Noticias</a>
        <a href="#faq">Preguntas frecuentes</a>
        <a href="#contacto">Contacto</a>
        <a href="#pqrsf">PQRSF</a>
        <a href="/enrolamiento">Trabaja con nosotros</a>
        <a href="/politica-tratamiento-datos">Pol\u00edtica de datos</a>
      </div>''',
)

# 3) Footer: NAP completo
add(
    "footer_nap",
    '''      <div class="footer-column">
        <h3>Contacto</h3>
        <p>Bogot\u00e1, Colombia</p>
        <a href="mailto:info@ayceventos.com.co">info@ayceventos.com.co</a>
      </div>''',
    '''      <div class="footer-column">
        <h3>Contacto</h3>
        <p>Cra. 59d #131a-1 131a-99 a, Bogot\u00e1, Colombia</p>
        <a href="tel:+576016438375" onclick="aycTrackEvent('tel_click')">+57 601 6438375</a>
        <a href="mailto:info@ayceventos.com.co">info@ayceventos.com.co</a>
      </div>''',
)

# 4) Footer logo: lazy
add(
    "footer_logo_lazy",
    '<img src="/static/frontend/logo.jpeg" alt="Logo A&C Eventos">',
    '<img src="/static/frontend/logo.jpeg" alt="Logo A&C Eventos" loading="lazy" decoding="async">',
)

# 5) Helper de analytics al inicio del bloque scripts
add(
    "track_helper",
    '''{% block scripts %}
<script>
  (function () {''',
    '''{% block scripts %}
<script>
  // Analytics opcional (GA4): emite eventos solo si GA_MEASUREMENT_ID est\u00e1 configurado.
  function aycTrackEvent(name, params) {
    if (window.GA_ID && typeof gtag === 'function') {
      gtag('event', name, params || {});
    }
  }

  (function () {''',
)

# 6) Evento GA: contacto
add(
    "track_contact",
    "          contactStatus.textContent = '\u00a1Solicitud enviada! Te contactaremos pronto.';",
    "          aycTrackEvent('contact_submit', { service: payload.event_type || null });" + nl +
    "          contactStatus.textContent = '\u00a1Solicitud enviada! Te contactaremos pronto.';",
)

# 7) Evento GA: PQRSF
add(
    "track_pqrsf",
    "          pqrsfForm.style.display = 'none';",
    "          aycTrackEvent('pqrsf_submit', { request_type: payload.request_type });" + nl +
    "          pqrsfForm.style.display = 'none';",
)

# --- Verificación transaccional ---
errors = []
for name, old, new in EDITS:
    count = content.count(old)
    if count != 1:
        errors.append("%s: %d coincidencias (esperaba 1)" % (name, count))

if errors:
    print("ERROR: no se aplic\u00f3 el parche:")
    for e in errors:
        print("  - " + e)
    sys.exit(1)

for name, old, new in EDITS:
    content = content.replace(old, new, 1)
    print("OK: " + name)

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(content)

print("Parche aplicado: %d ediciones en %s" % (len(EDITS), PATH))
# Informe SEO — FASE 20 (On-Page Técnico + Rendimiento)

> **Proyecto:** AYC Eventos S.A.S. (logistica) · **Fecha:** 2026-08-25 · **Alcance:** SEO on-page de la landing pública

## 1. Resumen ejecutivo

Se implementó la FASE 20 del plan maestro (SEO técnico + rendimiento). Todos los cambios verificados con la suite de tests (`tests/test_seo.py`, 13/13 ✅) y smoke test manual. La suite general queda en **87 passed / 1 skipped / 0 failed ✅** (incluye fixes a tests que antes se saltaban — ver §7).

| Área | Antes | Ahora |
|---|---|---|
| Título/description | Genéricos | Keyword principal "Producción de Eventos en Bogotá" + description 156c |
| Canonical | ❌ | ✅ `https://ayceventos.com.co/` |
| OG/Twitter cards | ❌ | ✅ og:title/description/image + twitter:card |
| JSON-LD | ❌ | ✅ LocalBusiness + WebSite + FAQPage |
| robots.txt / sitemap.xml | ❌ | ✅ con lastmod, sin duplicados, disallow de rutas privadas |
| noindex paneles | ❌ | ✅ Middleware `X-Robots-Tag: noindex, nofollow` en `/admin`, `/api`, `/coordinador`, `/staff`, `/colaboradores`, `/docs`, `/redoc`, `/test-ui` |
| Imágenes landing | JPG 300–500 KB | JPG comprimidos + **.webp generados** (−50–80% peso) |
| Lazy loading | Solo hero | Todas las imágenes bajo el fold |
| GA4 | ❌ | ✅ Condicional (`GA_MEASUREMENT_ID`), solo en producción |
| www vs no-www | Ambas 200 | ✅ 301 www→no-www en nginx |
| Compresión gzip | Parcial | ✅ gzip global en nginx |
| Caché estáticos | Sin cabeceras | ✅ `Cache-Control: public, max-age=30d` en `/static/frontend/` |

## 2. Cambios por archivo

| Archivo | Cambio |
|---|---|
| `backend/app/config.py` | `SITE_URL` y `GA_MEASUREMENT_ID` (vacío = sin GA) |
| `backend/app/routers/seo.py` *(nuevo)* | `GET /robots.txt` y `GET /sitemap.xml` (con `<lastmod>`) |
| `backend/app/main.py` | Middleware noindex para prefijos privados |
| `backend/app/templates/base.html` | GA4 gtag.js condicional (solo si `GA_MEASUREMENT_ID`), globals Jinja (`site_url`), `defer` en HTMX |
| `backend/app/templates/landing/home.html` | Title/description keyword-driven, canonical, OG/Twitter, JSON-LD (LocalBusiness/WebSite/FAQPage), NAP tel/email, sección FAQ visible con encabezados semánticos, `loading="lazy"`, eventos GA en CTAs, errores de formularios accesibles |
| `nginx/nginx.conf` | 301 www→no-www, gzip, `Cache-Control` 30d `/static/frontend/`, CSP con dominios GA4 |
| `scripts/optimizar_imagenes.py` *(nuevo)* | Compresión JPEG (q82, máx 1920px, progresivo) + generación .webp; solo sobreescribe si reduce peso (batch inicial ya aplicado; el pipeline automático de abajo lo reemplaza para contenido futuro) |
| `backend/app/services/content.py` | Subidas de imágenes de contenido se re-codifican a **WebP** (`CONTENT_IMAGE_WEBP_QUALITY`, default 82) automáticamente |
| `backend/app/core/webp_static.py` *(nuevo)* | Middleware de negociación: si el navegador envía `Accept: image/webp` y existe `X.webp` junto a `X.jpg/png`, sirve el WebP con `Vary: Accept` |
| `backend/app/main.py` | Mount de `/static/content` y `/static/frontend` con el middleware WebP |
| `frontend/webp.js` *(nuevo)* + `build.js` | En build genera `.webp` de los JPG/PNG de `frontend/public` (solo si reduce peso); `package.json` script `build:webp` |
| `backend/Dockerfile` | Ejecuta `npm run build:webp` en Stage 1 e instala libwebp7 en runtime (soporte Pillow WebP) |
| `backend/tests/test_seo.py` *(nuevo)* | 13 tests: sitemap, robots, metadatos home, JSON-LD, noindex |
| `backend/tests/test_config.py` | Ajuste valor JWT (15→30, el valor real commiteado) |
| `backend/tests/conftest.py` | `client` ahora crea el esquema de BD de prueba (auto-contenido) |

## 3. Sitemap y URLs indexables

```
https://ayceventos.com.co/                        1.0  weekly
https://ayceventos.com.co/enrolamiento           0.3  monthly
https://ayceventos.com.co/politica-tratamiento-datos  0.1  yearly
```

Únicamente 3 URLs: el sitio es una landing one-page con 2 sub-páginas. `robots.txt` bloquea `/admin`, `/api/`, `/coordinador`, `/staff`, `/colaboradores`, `/test-ui`, `/static/photos/`, `/static/rut/`.

## 4. JSON-LD emitido

- **LocalBusiness** (name, telephone, email, address Bogotá, url) — habilita resultados enriquecidos locales.
- **WebSite** (name + url) — base para future sitelinks searchbox.
- **FAQPage** (8 preguntas) — elegible para rich results de FAQ.

## 5. Rendimiento (Core Web Vitals)

- **Imágenes (pipeline WebP automatizado):**
  - Landing: 14 imágenes con `.webp` generado en build (12–64% de ahorro vs JPG optimizado). El middleware `webp_static.py` sirve el WebP solo a navegadores compatibles (`Vary: Accept`), sin cambiar URLs ni romper caché.
  - Contenido (hero/gallery/services del admin): toda subida nueva se re-codifica a WebP q82 en `content.py` — ya no depende de ejecutar el script manual.
  - Fotos de operadores y RUT siguen en JPEG (son descargas de uso interno, no afectan CWV).
- **Lazy loading:** todas las imágenes bajo el fold llevan `loading="lazy"`; el hero carga eager con fetchpriority alta.
- **HTMX `defer`** en base.html — JS ya no bloquea el parser.
- **gzip** en nginx para text/css/js/json/svg/woff2 (nivel 6).
- **Caché** 30 días en `/static/frontend/`, `/data/photos/`, `/static/content/`, `/static/rut/`.
- **GA4 condicional:** con `GA_MEASUREMENT_ID` vacío no se emite ningún script (entornos locales/test quedan limpios).

## 6. Pendiente posterior (no bloqueante)

1. **Google Search Console:** verificar dominio y enviar `sitemap.xml` (una vez desplegado en producción).
2. **OG image:** usar una imagen 1200×630 dedicada (hoy usa hero de la home).
3. **`hreflang`:** solo aplica si se añaden versiones de idioma (no hay hoy).
4. **Favicon:** generar set completo (favicon.ico, apple-touch, 192/512 png) — hoy solo hay `logo.jpeg`.
5. **Service Worker (PWA):** ya documentado en FASE 3.x, verificar que su alcance no cachee la home en exceso.
6. **Core Web Vitals en campo:** medir con PageSpeed Insights tras el despliegue.

## 7. Estado de tests

- `tests/test_seo.py`: **13/13 ✅** (sitemap con lastmod y sin duplicados, robots.txt, metadatos home, JSON-LD, noindex admin/api, home indexable).
- Suite completa: **87 passed, 1 skipped, 0 failed ✅** — incluye los fixes de los tests que antes se saltaban (la BD `logistica_test` local los ocultaba):
  - `test_operators`: corregido `MissingGreenlet` real de producción — `update_operator`/`upload_operator_photo` hacían `db.refresh(user)` que expiraba `operator_profile` y la serialización de la respuesta hacía lazy-load fuera del contexto async. Ahora se re-fetcha con `selectinload` (eager). Test de foto actualizado al naming real de thumbnails (`X_thumb.jpg`).
  - `test_payroll`: fixtures `admin_token`/`operator_token` ahora locales al archivo; D5 (Coordinador General) verificado vacío (se llena a mano, ver `_render_pages`); padding 2 dígitos para que el orden por apellido sea predecible; `slug` obligatorio en Roles; `phone` movido a User (modelo actual); fila de Juan buscada dinámicamente (la hoja incluye al coordinador checked_in y ordena por apellido).
- Mejoras de infraestructura de tests incluidas:
  - `test_config.py`: esperaba `JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 15` pero el valor commiteado es 30 (corregido).
  - `conftest.py`: el fixture `client` ahora crea el esquema de BD de pruebas (auto-contenido).
  - `database.py`: `NullPool` en el engine de pruebas para evitar conexiones cruzadas entre event loops de pytest-asyncio (eliminaba errores `InterfaceError`/`AttributeError` intermitentes).

## 8. Calendario de contenido — próximos 3 meses

| Mes | Tema objetivo (blog/noticias) | Keyword objetivo | Tipo |
|---|---|---|---|
| 1 | "Cómo organizar un evento corporativo en Bogotá: guía 2026" | organizacion de eventos corporativos bogota | Guía larga (1.500+ palabras) |
| 1 | "Cuánto cuesta producir un evento en Colombia" | cuanto cuesta producir un evento | Artículo informativo |
| 2 | "Checklist: 30 días para tu evento empresarial" | checklist evento empresarial | Lead magnet descargable |
| 2 | Caso de éxito: launch de producto (plantilla) | produccion de lanzamientos bogota | Caso de estudio |
| 3 | "Mejores escenarios y venues en Bogotá para eventos" | venues para eventos bogota | Listicle con enlaces internos |
| 3 | "Tendencias de producción de eventos 2027" | tendencias produccion de eventos | Contenido estacional |

**Nota:** hoy el sitio es one-page sin blog. Para ejecutar este calendario se requiere el módulo de blog/noticias (los `news` de la home ya existen como contenido administrable, sirven de base). Meta: 2 artículos/mes con enlaces internos hacia las secciones de servicios.
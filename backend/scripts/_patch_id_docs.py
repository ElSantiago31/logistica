"""Agrega carga obligatoria de cédula (frente y dorso) al registro de operadores.

Idempotente: cada cambio verifica si ya está aplicado. Verifica escritura
con readback inmediato. Cambios:

1. config.py            → ID_DOC_DIR/ID_DOC_MAX_SIZE_MB/ID_DOC_MAX_DIM/ID_DOC_WEBP_QUALITY
2. models/operators.py → id_document_front_path / id_document_back_path
3. services/documents.py → save_id_document_photo (WebP color) + delete_id_document_photos
4. schemas/auth.py     → id_document_front_data / id_document_back_data (obligatorios)
5. routers/auth.py     → validar roles ANTES de guardar archivos + guardar cédula
6. schemas/operators.py → exponer rut_path + id_document_* en OperatorResponse (bugfix RUT)
7. routers/operators.py → /pending expone cédulas + reject limpia archivos
8. main.py             → mkdir + mount /static/id_docs
9. templates/landing/index.html → UI cédula (2 subidas, preview, compresión canvas) + submitForm
10. templates/admin/operator_detail.html → botones ver cédula (lightbox existente)
"""
import io
import sys

RESULTS = []


def patch(path, replacements=(), appends=(), marker=None):
    """Apply ordered replacements + appended blocks to a text file."""
    c = io.open(path, encoding='utf-8').read()
    orig = c
    for old, new in replacements:
        if new in c and old not in c:
            RESULTS.append((path, 'SKIP (already applied)', old[:50]))
            continue
        if old not in c:
            RESULTS.append((path, 'FAIL anchor', old[:60]))
            continue
        c = c.replace(old, new, 1)
    for block in appends:
        if marker and marker in c:
            RESULTS.append((path, 'SKIP append (marker present)', marker))
            continue
        c = c + block
    if c != orig:
        io.open(path, 'w', encoding='utf-8', newline='').write(c)
    back = io.open(path, encoding='utf-8').read()
    ok = all((new in back) for _, new in replacements) and all(((marker or '###NEVER###') in back) for _ in appends if marker)
    RESULTS.append((path, 'OK' if (c == orig or ok or not replacements) else 'VERIFY', '%d repl, %d app' % (len(replacements), len(appends))))


# ---------------------------------------------------------------- 1. config.py
patch('app/config.py', replacements=[(
    "    # pgAdmin — password vacío por defecto (fail-safe)",
    """    # Cédula (documento de identidad) — fotos frente/dorso obligatorias en el registro
    ID_DOC_DIR: str = "./data/id_docs"
    ID_DOC_MAX_SIZE_MB: int = 5
    # Compresión: WebP color (mantiene tintas de la cédula) — mínimo espacio en disco
    ID_DOC_MAX_DIM: int = 1400
    ID_DOC_WEBP_QUALITY: int = 70

    # pgAdmin — password vacío por defecto (fail-safe)""",
)])

# ------------------------------------------------------- 2. models/operators.py
patch('app/models/operators.py', replacements=[(
    """    rut_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta del PDF del RUT comprimido (/static/rut/...)",
    )""",
    """    rut_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta del PDF del RUT comprimido (/static/rut/...)",
    )
    # Fotos de la cédula (frente y dorso) — obligatorias en registro, WebP comprimido
    id_document_front_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta de la foto del documento de identidad, frente (/static/id_docs/...)",
    )
    id_document_back_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta de la foto del documento de identidad, dorso (/static/id_docs/...)",
    )""",
)])

# ----------------------------------------------------- 3. services/documents.py
patch('app/services/documents.py', replacements=[(
    "from PIL import Image",
    "from PIL import Image, ImageOps",
)], appends=['''

# ---------------------------------------------------------------------------
# Cédula (documento de identidad) — fotos frente/dorso obligatorias
# ---------------------------------------------------------------------------

_ID_DOC_ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp", "image/jpg")


def _decode_image_data_url(data_url: str, field_label: str) -> bytes:
    """Extrae bytes de un data URL de imagen, validando tipo y tamaño."""
    if not data_url or not isinstance(data_url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La foto de la cédula ({field_label}) es obligatoria",
        )

    mime = ""
    raw_b64 = data_url.strip()
    m = re.match(r"^data:([^;]+);base64,(.+)$", raw_b64, re.DOTALL)
    if m:
        mime = m.group(1).lower()
        raw_b64 = m.group(2)

    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de cédula enviado no es válido (base64 corrupto)",
        )

    if len(raw) > settings.ID_DOC_MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La foto de la cédula supera el máximo de {settings.ID_DOC_MAX_SIZE_MB}MB",
        )

    if mime and mime not in _ID_DOC_ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. La cédula debe ser una imagen JPG, PNG o WEBP.",
        )
    return raw


def save_id_document_photo(data_url: str, operator_user_id, side: str) -> str:
    """Guarda una foto (frente|dorso) del documento de identidad del operador.

    Valida la imagen y la re-codifica a WebP color con dimensión máxima
    ID_DOC_MAX_DIM y calidad ID_DOC_WEBP_QUALITY: mínimo espacio en disco
    (~100-250KB por lado) manteniendo la cédula legible para revisión admin
    (incluye tintas de color).

    Returns URL path '/static/id_docs/idoc_<uid>_<side>.webp'.
    """
    if side not in ("front", "back"):
        raise ValueError("side must be 'front' or 'back'")
    label = "frente" if side == "front" else "dorso"
    raw = _decode_image_data_url(data_url, label)

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo leer la imagen de la cédula ({label}). Asegúrate de que sea válida.",
        )

    img = ImageOps.exif_transpose(img) or img
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    max_dim = settings.ID_DOC_MAX_DIM
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=settings.ID_DOC_WEBP_QUALITY, method=6)

    base_name = f"idoc_{str(operator_user_id).replace('-', '')[:16]}_{side}"
    file_name = f"{base_name}.webp"
    os.makedirs(settings.ID_DOC_DIR, exist_ok=True)
    with open(os.path.join(settings.ID_DOC_DIR, file_name), "wb") as f:
        f.write(buf.getvalue())

    return f"/static/id_docs/{file_name}"


def delete_id_document_photos(front_url: str | None, back_url: str | None) -> None:
    """Elimina archivos de cédula por URL. Seguro llamar con None."""
    for url in (front_url, back_url):
        if not url:
            continue
        filename = url.split("/")[-1]
        full_path = os.path.join(settings.ID_DOC_DIR, filename)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass
'''], marker='save_id_document_photo')

# ---------------------------------------------------------- 4. schemas/auth.py
patch('app/schemas/auth.py', replacements=[(
    """    # RUT obligatorio — Data URL (data:application/pdf;base64,...) o base64 puro
    rut_data: str = Field(..., min_length=100, description="PDF del RUT en base64 (data URL)")""",
    """    # RUT obligatorio — Data URL (data:application/pdf;base64,...) o base64 puro
    rut_data: str = Field(..., min_length=100, description="PDF del RUT en base64 (data URL)")
    # Cédula obligatoria — fotos frente y dorso (data URL de imagen)
    id_document_front_data: str = Field(..., min_length=100, description="Foto de la cédula (frente) en base64 (data URL)")
    id_document_back_data: str = Field(..., min_length=100, description="Foto de la cédula (dorso) en base64 (data URL)")""",
)])

# ---------------------------------------------------------- 5. routers/auth.py
patch('app/routers/auth.py', replacements=[
    # 5a. mover validación de roles ANTES de guardar archivos (anti-huérfanos)
    (
        """    # Process and save the mandatory photo (validates + normalizes)
    photo_name, thumb_name = save_operator_photo(body.photo_data, user.id)

    # Process and save the mandatory RUT PDF (validates + compresses)
    rut_path = save_rut_pdf(body.rut_data, user.id)

    # Security: filtrar roles event-only de experience_roles (aunque el frontend
    # no los muestre, un usuario malicioso podría enviarlos por API).""",
        """    # Security: filtrar roles event-only de experience_roles (aunque el frontend
    # no los muestre, un usuario malicioso podría enviarlos por API).
    # Se valida ANTES de guardar archivos para no dejar huérfanos en disco.""",
    ),
    # 5b. guardar archivos (foto + RUT + cédula) después de validar roles
    (
        """    # Create operator profile
    operator = Operator(""",
        """    # Process and save the mandatory photo (validates + normalizes)
    photo_name, thumb_name = save_operator_photo(body.photo_data, user.id)

    # Process and save the mandatory RUT PDF (validates + compresses)
    rut_path = save_rut_pdf(body.rut_data, user.id)

    # Cédula: fotos obligatorias frente y dorso (valida + comprime a WebP)
    id_doc_front_path = save_id_document_photo(body.id_document_front_data, user.id, "front")
    id_doc_back_path = save_id_document_photo(body.id_document_back_data, user.id, "back")

    # Create operator profile
    operator = Operator(""",
    ),
    # 5c. constructor del perfil
    (
        """        photo_path=photo_name,
        photo_thumbnail_path=thumb_name,
        rut_path=rut_path,
    )""",
        """        photo_path=photo_name,
        photo_thumbnail_path=thumb_name,
        rut_path=rut_path,
        id_document_front_path=id_doc_front_path,
        id_document_back_path=id_doc_back_path,
    )""",
    ),
])

# import en auth.py (línea flexible: buscar patrón)
_auth = io.open('app/routers/auth.py', encoding='utf-8').read()
if 'save_id_document_photo' in _auth and 'from app.services.documents import' in _auth:
    import re as _re
    m = _re.search(r"from app\.services\.documents import ([^\n]+)", _auth)
    if m and 'save_id_document_photo' not in m.group(1):
        _old = m.group(0)
        _new = _old.rstrip() + ', save_id_document_photo'
        patch('app/routers/auth.py', replacements=[(_old, _new)])
elif 'save_id_document_photo' not in _auth:
    patch('app/routers/auth.py', replacements=[(
        "from app.services.photos import",
        "from app.services.documents import save_id_document_photo\nfrom app.services.photos import",
    )])

# ------------------------------------------------------ 6. schemas/operators.py
patch('app/schemas/operators.py', replacements=[
    (
        """    photo_path: Optional[str]
    photo_thumbnail_path: Optional[str]
""",
        """    photo_path: Optional[str]
    photo_thumbnail_path: Optional[str]
    rut_path: Optional[str] = None
    id_document_front_path: Optional[str] = None
    id_document_back_path: Optional[str] = None
""",
    ),
    (
        "                    'photo_thumbnail_path': profile.photo_thumbnail_path,",
        """                    'photo_thumbnail_path': profile.photo_thumbnail_path,
                    'rut_path': profile.rut_path,
                    'id_document_front_path': profile.id_document_front_path,
                    'id_document_back_path': profile.id_document_back_path,""",
    ),
    (
        "'photo_thumbnail_path': None, 'birth_date': None, 'gender': None,",
        "'photo_thumbnail_path': None, 'rut_path': None, 'id_document_front_path': None, "
        "'id_document_back_path': None, 'birth_date': None, 'gender': None,",
    ),
])

# ------------------------------------------------------ 7. routers/operators.py
patch('app/routers/operators.py', replacements=[
    (
        "from app.services.documents import delete_rut_pdf",
        "from app.services.documents import delete_rut_pdf, delete_id_document_photos",
    ),
    (
        '''                "rut_path": op.rut_path,''',
        '''                "rut_path": op.rut_path,
                "id_document_front_path": op.id_document_front_path,
                "id_document_back_path": op.id_document_back_path,''',
    ),
    (
        """        delete_operator_photos(operator.photo_path, operator.photo_thumbnail_path)
        delete_rut_pdf(operator.rut_path)
        operator.photo_path = None
        operator.photo_thumbnail_path = None
        operator.rut_path = None""",
        """        delete_operator_photos(operator.photo_path, operator.photo_thumbnail_path)
        delete_rut_pdf(operator.rut_path)
        delete_id_document_photos(operator.id_document_front_path, operator.id_document_back_path)
        operator.photo_path = None
        operator.photo_thumbnail_path = None
        operator.rut_path = None
        operator.id_document_front_path = None
        operator.id_document_back_path = None""",
    ),
])

# ------------------------------------------------------------------ 8. main.py
patch('app/main.py', replacements=[
    (
        "    os.makedirs(settings.RUT_DIR, exist_ok=True)\n    yield",
        "    os.makedirs(settings.RUT_DIR, exist_ok=True)\n    os.makedirs(settings.ID_DOC_DIR, exist_ok=True)\n    yield",
    ),
    (
        "for _d in (settings.PHOTOS_DIR, settings.PHOTOS_THUMBNAIL_DIR, settings.RUT_DIR):",
        "for _d in (settings.PHOTOS_DIR, settings.PHOTOS_THUMBNAIL_DIR, settings.RUT_DIR, settings.ID_DOC_DIR):",
    ),
    (
        'app.mount("/static/rut", StaticFiles(directory=settings.RUT_DIR), name="rut")',
        'app.mount("/static/rut", StaticFiles(directory=settings.RUT_DIR), name="rut")\n'
        'app.mount("/static/id_docs", StaticFiles(directory=settings.ID_DOC_DIR), name="id_docs")',
    ),
])

# --------------------------------------------------- 9. landing/index.html
_ID_DOC_HTML = """
            <!-- Cédula obligatoria (frente y dorso) -->
            <div class="border border-gray-200 rounded-lg p-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">🪪 Tu Cédula (Obligatorio) *</label>
                <p class="text-xs text-gray-500 mb-3">Sube la foto de tu documento de identidad por ambos lados (frente y dorso). El administrador la verificará antes de aprobar tu cuenta.</p>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <button type="button" onclick="document.getElementById('iddoc-front-input').click()"
                            class="w-full py-4 rounded-lg font-semibold transition text-center cursor-pointer"
                            style="background:rgba(207,155,98,0.1);border:2px dashed rgba(207,155,98,0.3);color:#cf9b62">
                            🪪 Frente<br>
                            <span class="text-xs" style="color:rgba(207,155,98,0.5)">Toca aquí · JPG, PNG</span>
                        </button>
                        <input type="file" id="iddoc-front-input" accept="image/*" capture="user" class="hidden">
                        <div id="iddoc-front-preview" class="hidden mt-2 text-center">
                            <img id="iddoc-front-img" class="w-full h-24 object-cover rounded-lg mx-auto" style="border:2px solid rgba(207,155,98,0.3)">
                            <button type="button" onclick="document.getElementById('iddoc-front-input').click()" class="block mx-auto mt-1 text-xs" style="color:#cf9b62">↻ Cambiar frente</button>
                        </div>
                        <p id="iddoc-front-error" class="text-red-500 text-xs mt-1 hidden">⚠️ La foto del frente es obligatoria</p>
                    </div>
                    <div>
                        <button type="button" onclick="document.getElementById('iddoc-back-input').click()"
                            class="w-full py-4 rounded-lg font-semibold transition text-center cursor-pointer"
                            style="background:rgba(207,155,98,0.1);border:2px dashed rgba(207,155,98,0.3);color:#cf9b62">
                            🪪 Dorso<br>
                            <span class="text-xs" style="color:rgba(207,155,98,0.5)">Toca aquí · JPG, PNG</span>
                        </button>
                        <input type="file" id="iddoc-back-input" accept="image/*" capture="user" class="hidden">
                        <div id="iddoc-back-preview" class="hidden mt-2 text-center">
                            <img id="iddoc-back-img" class="w-full h-24 object-cover rounded-lg mx-auto" style="border:2px solid rgba(207,155,98,0.3)">
                            <button type="button" onclick="document.getElementById('iddoc-back-input').click()" class="block mx-auto mt-1 text-xs" style="color:#cf9b62">↻ Cambiar dorso</button>
                        </div>
                        <p id="iddoc-back-error" class="text-red-500 text-xs mt-1 hidden">⚠️ La foto del dorso es obligatoria</p>
                    </div>
                </div>
            </div>
"""

_ID_DOC_JS = """
// ===== ID DOCUMENT UPLOAD (Step 3 - mandatory front/back) =====
window._operatorIdFrontData = null;
window._operatorIdBackData = null;

function handleIdDocFile(file, side) {
    const errEl = document.getElementById('iddoc-' + side + '-error');
    if (!file.type.startsWith('image/')) { showToast('Solo se permiten imágenes', 'error'); errEl.classList.remove('hidden'); return; }
    if (file.size > 5 * 1024 * 1024) { showToast('La imagen supera 5MB', 'error'); errEl.classList.remove('hidden'); return; }
    const reader = new FileReader();
    reader.onload = function(ev) {
        const img = new Image();
        img.onload = function() {
            // Compresión client-side: 1600px JPEG (el servidor la re-comprime a WebP)
            const maxDim = 1600;
            let w = img.width, h = img.height;
            if (w > maxDim || h > maxDim) {
                if (w > h) { h = Math.round(h * maxDim / w); w = maxDim; }
                else { w = Math.round(w * maxDim / h); h = maxDim; }
            }
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);
            const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
            if (side === 'front') window._operatorIdFrontData = dataUrl;
            else window._operatorIdBackData = dataUrl;
            document.getElementById('iddoc-' + side + '-img').src = dataUrl;
            document.getElementById('iddoc-' + side + '-preview').classList.remove('hidden');
            errEl.classList.add('hidden');
        };
        img.src = ev.target.result;
    };
    reader.onerror = function() { showToast('Error leyendo la imagen. Intenta con otra.', 'error'); };
    reader.readAsDataURL(file);
}

document.getElementById('iddoc-front-input').addEventListener('change', function(e) {
    if (e.target.files && e.target.files[0]) handleIdDocFile(e.target.files[0], 'front');
});
document.getElementById('iddoc-back-input').addEventListener('change', function(e) {
    if (e.target.files && e.target.files[0]) handleIdDocFile(e.target.files[0], 'back');
});
"""

patch('app/templates/landing/index.html', replacements=[
    # HTML del bloque de cédula (después del bloque RUT)
    (
        '''                <p id="rut-error" class="text-red-500 text-xs mt-2 hidden">⚠️ El RUT en PDF es obligatorio para registrarte</p>
            </div>
''',
        '''                <p id="rut-error" class="text-red-500 text-xs mt-2 hidden">⚠️ El RUT en PDF es obligatorio para registrarte</p>
            </div>
''' + _ID_DOC_HTML,
    ),
    # validación temprana (antes de deshabilitar el botón)
    (
        """    // Validate RUT is present (before disabling button)
    if (!window._operatorRutData) {
        showToast('Debes subir tu RUT en PDF para registrarte', 'error');
        goToStep(3);
        return;
    }
""",
        """    // Validate RUT is present (before disabling button)
    if (!window._operatorRutData) {
        showToast('Debes subir tu RUT en PDF para registrarte', 'error');
        goToStep(3);
        return;
    }

    // Validate ID document photos (before disabling button)
    if (!window._operatorIdFrontData || !window._operatorIdBackData) {
        showToast('Debes subir tu cédula por ambos lados (frente y dorso)', 'error');
        goToStep(3);
        return;
    }
""",
    ),
    # payload
    (
        """        photo_data: window._operatorPhotoData || undefined,
        rut_data: window._operatorRutData || undefined,
    };""",
        """        photo_data: window._operatorPhotoData || undefined,
        rut_data: window._operatorRutData || undefined,
        id_document_front_data: window._operatorIdFrontData || undefined,
        id_document_back_data: window._operatorIdBackData || undefined,
    };""",
    ),
    # reemplaza la doble validación muerta por la validación de cédula
    (
        """    // Validate photo is present
    if (!data.photo_data) {
        showToast('Debes subir tu foto para registrarte', 'error');
        goToStep(3);
        return;
    }

    // Validate RUT is present
    if (!data.rut_data) {
        showToast('Debes subir tu RUT en PDF para registrarte', 'error');
        goToStep(3);
        return;
    }
""",
        """    // Validate ID document (both sides) is present
    if (!data.id_document_front_data || !data.id_document_back_data) {
        showToast('Debes subir tu cédula por ambos lados (frente y dorso)', 'error');
        goToStep(3);
        return;
    }
""",
    ),
    # JS handlers al final del script
    (
        "    reader.readAsDataURL(file);\n}\n</script>",
        "    reader.readAsDataURL(file);\n}\n" + _ID_DOC_JS + "</script>",
    ),
])

# ------------------------------------------- 10. admin/operator_detail.html
patch('app/templates/admin/operator_detail.html', replacements=[
    (
        '''                ${o.rut_path?`
                    <a href="${o.rut_path}" target="_blank" download class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium inline-flex items-center">📄 Descargar RUT</a>
                `:`<span class="text-xs text-gray-400 self-center">Sin RUT</span>`}''',
        '''                ${o.rut_path?`
                    <a href="${o.rut_path}" target="_blank" download class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium inline-flex items-center">📄 Descargar RUT</a>
                `:`<span class="text-xs text-gray-400 self-center">Sin RUT</span>`}
                ${o.id_document_front_path?`
                    <button onclick="openPhotoViewer('${o.id_document_front_path}')" class="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg text-sm font-medium">🪪 Ver Cédula (Frente)</button>
                `:`<span class="text-xs text-gray-400 self-center">Sin cédula (frente)</span>`}
                ${o.id_document_back_path?`
                    <button onclick="openPhotoViewer('${o.id_document_back_path}')" class="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg text-sm font-medium">🪪 Ver Cédula (Dorso)</button>
                `:`<span class="text-xs text-gray-400 self-center">Sin cédula (dorso)</span>`}''',
    ),
])

# ------------------------------------------------------------------ reporte
print('=' * 70)
fails = 0
for path, status, info in RESULTS:
    line = f'{status:28} {path}  [{info}]'
    print(line)
    if 'FAIL' in status:
        fails += 1
print('=' * 70)

# verificación final de marcadores
checks = {
    'app/config.py': 'ID_DOC_DIR',
    'app/models/operators.py': 'id_document_front_path',
    'app/services/documents.py': 'save_id_document_photo',
    'app/schemas/auth.py': 'id_document_front_data',
    'app/routers/auth.py': 'save_id_document_photo(body.id_document_front_data',
    'app/schemas/operators.py': "'rut_path': profile.rut_path",
    'app/routers/operators.py': 'delete_id_document_photos',
    'app/main.py': '/static/id_docs',
    'app/templates/landing/index.html': 'iddoc-front-input',
    'app/templates/admin/operator_detail.html': 'Ver Cédula (Frente)',
}
print('FINAL CHECKS:')
for p, marker in checks.items():
    c = io.open(p, encoding='utf-8').read()
    print(('PASS' if marker in c else '!!!! MISS'), p, '->', marker)
    if marker not in c:
        fails += 1

sys.exit(1 if fails else 0)
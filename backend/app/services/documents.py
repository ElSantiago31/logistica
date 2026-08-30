"""Document handling service — RUT PDF validation + compression.

Single source of truth for operator RUT PDF uploads (registration).

Compression strategy (PyMuPDF + Pillow):
- Rasterize each PDF page at 150 DPI in grayscale (fitz.csGRAY).
- Encode each page as JPEG quality 75 (via Pillow).
- Rebuild a compact PDF from the JPEG images.

Typical result: a 5MB scanned RUT → ~200-400KB (~90% reduction).
The grayscale + 150 DPI keeps the text perfectly legible for admin review.
"""
import base64
import binascii
import io
import os
import re

import fitz  # PyMuPDF
from PIL import Image, ImageOps
from fastapi import HTTPException, status

from app.config import settings


# --- Configuration ---
_MAX_RAW_BYTES = settings.RUT_MAX_SIZE_MB * 1024 * 1024
_ALLOWED_MIME = ("application/pdf",)
_PDF_MAGIC = b"%PDF"


# --- Validation helpers ---

def _decode_data_url(data_url: str) -> bytes:
    """Extract raw bytes from a 'data:application/pdf;base64,...' string.

    Raises HTTPException(400) on invalid format/size/type.
    """
    if not data_url or not isinstance(data_url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El RUT es obligatorio",
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
            detail="El archivo enviado no es válido (base64 corrupto)",
        )

    if len(raw) > _MAX_RAW_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El RUT supera el tamaño máximo de {settings.RUT_MAX_SIZE_MB}MB",
        )

    if mime and mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. El RUT debe ser un archivo PDF.",
        )

    # Validate PDF magic bytes
    if not raw[:4] == _PDF_MAGIC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es un PDF válido",
        )

    return raw


# --- PDF compression ---

def _compress_pdf(raw: bytes) -> bytes:
    """Compress PDF: rasterize each page to grayscale JPEG, rebuild PDF.

    Returns compressed PDF bytes.
    """
    try:
        src = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo leer el PDF del RUT. Asegúrate de que sea un archivo válido.",
        )

    if src.page_count == 0:
        src.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El PDF del RUT no contiene páginas",
        )

    images: list[Image.Image] = []
    dpi = settings.RUT_COMPRESS_DPI
    quality = settings.RUT_COMPRESS_QUALITY

    for page in src:
        # Render page at target DPI, grayscale, no alpha
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        images.append(img)

    src.close()

    # Rebuild PDF from JPEG-compressed grayscale images
    compressed_jpegs: list[bytes] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed_jpegs.append(buf.getvalue())

    # Build final PDF from JPEG images
    pdf_buf = io.BytesIO()
    pil_images: list[Image.Image] = []
    for jpg in compressed_jpegs:
        pil_images.append(Image.open(io.BytesIO(jpg)))

    pil_images[0].save(
        pdf_buf,
        format="PDF",
        save_all=True,
        append_images=pil_images[1:],
        resolution=float(dpi),
    )

    return pdf_buf.getvalue()


# --- Storage helpers ---

def _build_url(rut_name: str) -> str:
    """Build public URL path for the stored RUT."""
    return f"/static/rut/{rut_name}"


def _persist_file(rut_name: str, data: bytes) -> None:
    """Write RUT file to disk (creates dir if needed)."""
    os.makedirs(settings.RUT_DIR, exist_ok=True)
    full_path = os.path.join(settings.RUT_DIR, rut_name)
    with open(full_path, "wb") as f:
        f.write(data)


# --- Public API ---

def save_rut_pdf(data_url: str, operator_user_id) -> str:
    """Save operator RUT PDF from a base64 data URL (registration flow).

    Validates the PDF, compresses it (grayscale 150 DPI JPEG q75),
    and stores it in RUT_DIR.

    Returns the URL path '/static/rut/rut_....pdf'.
    """
    raw = _decode_data_url(data_url)
    compressed = _compress_pdf(raw)

    base_name = f"rut_{str(operator_user_id).replace('-', '')[:16]}"
    rut_name = f"{base_name}.pdf"

    _persist_file(rut_name, compressed)

    return _build_url(rut_name)


def delete_rut_pdf(rut_url: str | None) -> None:
    """Delete stored RUT file by its URL path. Safe to call with None."""
    if not rut_url:
        return
    filename = rut_url.split("/")[-1]
    full_path = os.path.join(settings.RUT_DIR, filename)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass

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

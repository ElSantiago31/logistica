"""Photo handling service — compress photos + generate thumbnails (centralized).

Single source of truth for ALL operator photo uploads (registration + profile).

Entry points:
- save_operator_photo(data_url, user_id): for base64 data URLs (public registration)
- save_operator_photo_bytes(raw, user_id): for raw bytes (authenticated UploadFile)

Both return (photo_url, thumbnail_url) as '/static/photos/...'.
All images are normalized to JPEG, max 1024×1024, quality 88, with EXIF correction.
"""
import base64
import binascii
import io
import os
import re

from PIL import Image, ImageOps
from fastapi import HTTPException, status

from app.config import settings


# --- Configuration ---
_MAX_RAW_BYTES = settings.PHOTO_MAX_SIZE_MB * 1024 * 1024
_ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp")
_PHOTO_MAX_DIM = 1024   # full photo max dimension
_THUMB_SIZE = (256, 256)  # square thumbnail
_FULL_QUALITY = 88
_THUMB_QUALITY = 80


# --- Validation helpers ---

def _decode_data_url(data_url: str) -> bytes:
    """Extract raw bytes from a 'data:image/jpeg;base64,...' string.

    Raises HTTPException(400) on invalid format/size/type.
    """
    if not data_url or not isinstance(data_url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La foto es obligatoria",
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
            detail="La imagen enviada no es válida (base64 corrupto)",
        )

    if len(raw) > _MAX_RAW_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La imagen supera el tamaño máximo de {settings.PHOTO_MAX_SIZE_MB}MB",
        )

    if mime and mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagen no permitido. Use JPG, PNG o WebP.",
        )
    return raw


def _validate_raw(raw: bytes, mime: str | None = None) -> bytes:
    """Validate raw bytes (size + optional MIME). Used for UploadFile uploads."""
    if len(raw) > _MAX_RAW_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La imagen supera el tamaño máximo de {settings.PHOTO_MAX_SIZE_MB}MB",
        )
    if mime and mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagen no permitido. Use JPG, PNG o WebP.",
        )
    return raw


# --- Image processing ---

def _process_image(raw: bytes) -> tuple[bytes, bytes]:
    """Validate, normalize (RGB + EXIF), compress. Returns (full_bytes, thumb_bytes)."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # honor orientation metadata
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo leer la imagen. Asegúrate de que sea una foto válida.",
        )

    # Convert to RGB (drop alpha/transparency)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Resize full image if too large (keep aspect ratio)
    img.thumbnail((_PHOTO_MAX_DIM, _PHOTO_MAX_DIM), Image.LANCZOS)

    # Full photo -> JPEG
    full_buf = io.BytesIO()
    img.save(full_buf, format="JPEG", quality=_FULL_QUALITY, optimize=True)
    full_bytes = full_buf.getvalue()

    # Thumbnail (square center-crop, biased toward face area)
    thumb = ImageOps.fit(img, _THUMB_SIZE, method=Image.LANCZOS, bleed=0.0, centering=(0.5, 0.4))
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=_THUMB_QUALITY, optimize=True)
    thumb_bytes = thumb_buf.getvalue()

    return full_bytes, thumb_bytes


# --- Storage helpers ---

def _build_urls(photo_name: str, thumb_name: str) -> tuple[str, str]:
    """Build public URL paths for the stored photo and thumbnail."""
    return (
        f"/static/photos/{photo_name}",
        f"/static/photos/thumbnails/{thumb_name}",
    )


def _persist_files(photo_name: str, thumb_name: str, full_bytes: bytes, thumb_bytes: bytes) -> None:
    """Write photo + thumbnail files to disk (creates dirs if needed)."""
    os.makedirs(settings.PHOTOS_DIR, exist_ok=True)
    os.makedirs(settings.PHOTOS_THUMBNAIL_DIR, exist_ok=True)

    photo_full_path = os.path.join(settings.PHOTOS_DIR, photo_name)
    thumb_full_path = os.path.join(settings.PHOTOS_THUMBNAIL_DIR, thumb_name)

    with open(photo_full_path, "wb") as f:
        f.write(full_bytes)
    with open(thumb_full_path, "wb") as f:
        f.write(thumb_bytes)


# --- Public API ---

def save_operator_photo(data_url: str, operator_user_id) -> tuple[str, str]:
    """Save operator photo from a base64 data URL (registration flow).

    Returns (photo_url, thumbnail_url) as '/static/photos/...'.
    """
    raw = _decode_data_url(data_url)
    return save_operator_photo_bytes(raw, operator_user_id)


def save_operator_photo_bytes(raw: bytes, operator_user_id) -> tuple[str, str]:
    """Save operator photo from raw bytes (UploadFile / profile flow).

    Returns (photo_url, thumbnail_url) as '/static/photos/...'.
    """
    _validate_raw(raw)
    full_bytes, thumb_bytes = _process_image(raw)

    base_name = f"op_{str(operator_user_id).replace('-', '')[:16]}"
    photo_name = f"{base_name}.jpg"
    thumb_name = f"{base_name}_thumb.jpg"

    _persist_files(photo_name, thumb_name, full_bytes, thumb_bytes)

    return _build_urls(photo_name, thumb_name)


def delete_operator_photos(photo_url: str | None, thumb_url: str | None = None) -> None:
    """Delete stored photo + thumbnail files by their URL paths.

    Safe to call with None or already-deleted files.
    """
    targets = [
        (photo_url, settings.PHOTOS_DIR),
        (thumb_url, settings.PHOTOS_THUMBNAIL_DIR),
    ]
    for url, base_dir in targets:
        if not url:
            continue
        filename = url.split("/")[-1]
        full_path = os.path.join(base_dir, filename)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass
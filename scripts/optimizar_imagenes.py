# -*- coding: utf-8 -*-
"""Optimiza las imágenes públicas de la landing (SEO / Core Web Vitals).

- Comprime JPEG > 300 KB (calidad 82, max-width 1920px, progresivo).
- Genera versiones .webp junto a cada imagen.
- Solo sobreescribe el original si el resultado es más liviano.
- No elimina originales (los templates siguen apuntando a .jpg).

Uso:
    python scripts/optimizar_imagenes.py            # optimiza frontend/public/landing
    python scripts/optimizar_imagenes.py --dry-run  # solo reporta
"""
import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Falta Pillow. Instala con: pip install Pillow")
    sys.exit(1)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "public", "landing")
MAX_WIDTH = 1920
JPEG_THRESHOLD = 300 * 1024  # solo recomprimir jpg mayores a 300 KB
JPEG_QUALITY = 82
WEBP_QUALITY = 80


def fmt(n):
    return "%.1f KB" % (n / 1024.0)


def process(path, dry):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    out = []

    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        print("  SKIP %s (%s)" % (name, e))
        return out

    # Rotación EXIF correcta
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    w, h = img.size
    if w > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, int(h * MAX_WIDTH / w)), Image.LANCZOS)

    orig_size = os.path.getsize(path)

    if ext in (".jpg", ".jpeg"):
        if orig_size > JPEG_THRESHOLD and not dry:
            tmp = path + ".tmp"
            img.convert("RGB").save(tmp, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            new_size = os.path.getsize(tmp)
            if new_size < orig_size:
                os.replace(tmp, path)
                out.append("%s: %s -> %s" % (name, fmt(orig_size), fmt(new_size)))
            else:
                os.remove(tmp)
                out.append("%s: ya optimizada (%s)" % (name, fmt(orig_size)))

        webp = os.path.splitext(path)[0] + ".webp"
        if not dry:
            img.convert("RGB").save(webp, "WEBP", quality=WEBP_QUALITY, method=6)
            out.append("%s.webp: %s" % (os.path.splitext(name)[0], fmt(os.path.getsize(webp))))

    elif ext == ".png":
        webp = os.path.splitext(path)[0] + ".webp"
        if not dry:
            img.save(webp, "WEBP", quality=WEBP_QUALITY, method=6)
            out.append("%s.webp: %s" % (os.path.splitext(name)[0], fmt(os.path.getsize(webp))))

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = os.path.normpath(BASE)
    if not os.path.isdir(base):
        print("No existe: %s" % base)
        sys.exit(1)

    print("Optimizando imágenes en %s%s\n" % (base, " (dry-run)" if args.dry_run else ""))
    total, cambios = 0, 0
    for root, _, files in os.walk(base):
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png"):
                continue
            total += 1
            res = process(os.path.join(root, f), args.dry_run)
            for line in res:
                print("  " + line)
                cambios += 1

    print("\nProcesadas: %d imágenes, %d cambios." % (total, cambios))


if __name__ == "__main__":
    main()
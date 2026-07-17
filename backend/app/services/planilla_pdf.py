"""Servicio para generar la planilla de pago en PDF.

ESTRATEGIA
==========
Genera el Excel con la MISMA plantilla corporativa que el botón de Excel
(``generate_planilla_xlsx``), le aplica configuración de impresión
(horizontal, Legal, ajustar columnas a 1 página de ancho) y lo convierte
a PDF.

Así el PDF es IDÉNTICO al Excel porque proviene del mismo archivo: mismo
logo, mismos encabezados, mismas columnas, mismos anchos y colores.

CADENA DE CONVERSIÓN (con fallback automático)
----------------------------------------------
El módulo intenta varios motores de conversión en orden:

1. **LibreOffice local** (Linux/Docker/Windows): ``soffice --headless``
2. **LibreOffice vía Docker**: usa imagen ``linuxserver/libreoffice``
   (útil cuando LibreOffice local está corrupto en Windows).

Si todos fallan, lanza ``RuntimeError`` con instrucciones claras.
"""
import io
import os
import shutil
import platform
import logging
import subprocess
import tempfile

from app.services.planilla_excel import generate_planilla_xlsx

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURACIÓN DE IMPRESIÓN DEL EXCEL
# ============================================================
def _apply_print_setup(wb) -> None:
    """Aplica el setup de impresión a todas las hojas del workbook.

    Configura cada hoja para que al imprimir/exportar a PDF salga:
    - Orientación **horizontal** (landscape).
    - Tamaño de papel **Legal** (8.5 x 14 in) — igual a la planilla física.
    - **Ajustar todas las columnas a 1 página de ancho** (fitToWidth=1),
      con alto ilimitado (fitToHeight=0) para que pagine por filas.
    - Márgenes estrechos para aprovechar el espacio.
    - Centrado horizontal.
    - Área de impresión limitada a las columnas B:M (las que usa la plantilla).
    """
    from openpyxl.worksheet.properties import PageSetupProperties
    from openpyxl.worksheet.page import PageMargins

    for ws in wb.worksheets:
        # Orientación horizontal + papel Legal
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = 5  # 5 = Legal (8.5 x 14 in)
        # Ajustar columnas a 1 página de ancho; paginar por filas
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        # Márgenes estrechos (en pulgadas)
        ws.page_margins = PageMargins(
            left=0.3, right=0.3, top=0.4, bottom=0.4,
            header=0.2, footer=0.2,
        )
        # Centrado horizontal en la página
        ws.print_options.horizontalCentered = True
        # Área de impresión: columnas B:M (las que usa la plantilla),
        # desde la fila 1 hasta el final del contenido.
        last_row = max(ws.max_row, 28)
        ws.print_area = f"B1:M{last_row}"


# ============================================================
# ESTRATEGIA 1: LibreOffice LOCAL
# ============================================================
def _find_libreoffice() -> str | None:
    """Localiza el ejecutable de LibreOffice (Linux, macOS o Windows).

    Busca en el PATH y, en Windows, en las rutas de instalación típicas.
    """
    # 1. Buscar en PATH
    for cmd in ("libreoffice", "soffice", "soffice.exe"):
        path = shutil.which(cmd)
        if path:
            return path
    # 2. Rutas comunes en Windows
    win_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in win_paths:
        if os.path.exists(p):
            return p
    return None


def _libreoffice_works(lo_bin: str) -> bool:
    """Verifica que LibreOffice realmente funciona (no está corrupto).

    En Windows algunas instalaciones quedan corruptas (bootstrap.ini roto)
    y ``soffice`` crashea con STATUS_STACK_BUFFER_OVERRUN. Esta función
    ejecuta ``soffice --version`` para validar antes de intentar convertir.
    """
    try:
        r = subprocess.run(
            [lo_bin, "--version"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _convert_xlsx_to_pdf_libreoffice(
    xlsx_path: str, out_dir: str
) -> str | None:
    """Convierte XLSX → PDF con LibreOffice headless (local).

    Returns:
        Ruta al PDF generado, o ``None`` si LibreOffice no está disponible
        o falla (para que el llamador intente la siguiente estrategia).
    """
    lo_bin = _find_libreoffice()
    if not lo_bin:
        logger.info("[planilla-pdf] LibreOffice no encontrado localmente")
        return None

    if not _libreoffice_works(lo_bin):
        logger.warning(
            "[planilla-pdf] LibreOffice local encontrado pero NO funciona "
            "(instalación corrupta). Se intentará Docker."
        )
        return None

    # Perfil de usuario aislado en out_dir para evitar conflictos si hay
    # conversiones concurrentes (cada llamada usa su propio tmpdir).
    profile_uri = "file://" + os.path.join(out_dir, "lo_profile").replace("\\", "/")

    cmd = [
        lo_bin,
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation={profile_uri}",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        xlsx_path,
    ]

    # LibreOffice necesita un HOME escribible para su perfil
    env = os.environ.copy()
    env.setdefault("HOME", out_dir)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, env=env,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[planilla-pdf] LibreOffice timeout (120s)")
        return None
    except Exception as exc:
        logger.warning("[planilla-pdf] LibreOffice excepción: %s", exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "[planilla-pdf] LibreOffice falló (código %s): %s",
            result.returncode, result.stderr[:200],
        )
        return None

    base = os.path.splitext(os.path.basename(xlsx_path))[0]
    pdf_path = os.path.join(out_dir, f"{base}.pdf")
    if not os.path.exists(pdf_path):
        logger.warning("[planilla-pdf] LibreOffice no generó el PDF esperado")
        return None
    return pdf_path


# ============================================================
# ESTRATEGIA 2: LibreOffice VÍA DOCKER (fallback Windows)
# ============================================================
def _docker_available() -> bool:
    """Verifica si Docker está disponible y funcionando."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        r = subprocess.run(
            ["docker", "ps"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _convert_xlsx_to_pdf_docker(
    xlsx_path: str, out_dir: str
) -> str | None:
    """Convierte XLSX → PDF usando LibreOffice dentro de un contenedor Docker.

    Útil cuando LibreOffice local está corrupto (común en Windows).

    Usa la imagen ``linuxserver/libreoffice`` (o ``lscr.io/linuxserver/libreoffice``).
    Si la imagen no existe localmente, intenta hacer ``docker pull``.
    """
    if not _docker_available():
        logger.info("[planilla-pdf] Docker no disponible")
        return None

    # Imágenes candidatas (en orden de preferencia)
    images = [
        "linuxserver/libreoffice:latest",
        "lscr.io/linuxserver/libreoffice:latest",
    ]

    image_to_use = None
    for img in images:
        try:
            r = subprocess.run(
                ["docker", "image", "inspect", img],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                image_to_use = img
                break
        except Exception:
            continue

    if not image_to_use:
        # Intentar pull de la primera imagen
        logger.info("[planilla-pdf] Haciendo docker pull de LibreOffice...")
        try:
            r = subprocess.run(
                ["docker", "pull", images[0]],
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode == 0:
                image_to_use = images[0]
        except Exception as exc:
            logger.warning("[planilla-pdf] docker pull falló: %s", exc)
            return None

    if not image_to_use:
        logger.warning("[planilla-pdf] No hay imagen de LibreOffice en Docker")
        return None

    # Convertir rutas Windows → formato Docker
    # Docker Desktop en Windows monta automáticamente los volúmenes usando
    # la ruta absoluta de Windows directamente.
    abs_xlsx = os.path.abspath(xlsx_path)
    abs_out = os.path.abspath(out_dir)

    # Montar el directorio de salida en /data del contenedor.
    # Tanto el xlsx (entrada) como el pdf (salida) viven ahí.
    mount_src = abs_out
    rel_xlsx = os.path.basename(abs_xlsx)

    # La imagen linuxserver/libreoffice usa s6-overlay como entrypoint,
    # por lo que debemos sobreescribirlo con --entrypoint soffice.
    # El usuario interno es 'abc' (UID 1000); usamos --user root para
    # garantizar permisos de escritura en el volumen montado en Windows.
    cmd = [
        "docker", "run", "--rm",
        "--user", "root",
        "-e", "HOME=/tmp",
        "-v", f"{mount_src}:/data",
        "--entrypoint", "soffice",
        image_to_use,
        "--headless", "--norestore", "--nolockcheck",
        "-env:UserInstallation=file:///tmp/lo_profile",
        "--convert-to", "pdf",
        "--outdir", "/data",
        f"/data/{rel_xlsx}",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[planilla-pdf] Docker LibreOffice timeout (180s)")
        return None
    except Exception as exc:
        logger.warning("[planilla-pdf] Docker excepción: %s", exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "[planilla-pdf] Docker LibreOffice falló (código %s): %s",
            result.returncode, result.stderr[:300],
        )
        return None

    base = os.path.splitext(rel_xlsx)[0]
    pdf_path = os.path.join(abs_out, f"{base}.pdf")
    if not os.path.exists(pdf_path):
        logger.warning("[planilla-pdf] Docker no generó el PDF esperado")
        return None
    return pdf_path


# ============================================================
# ORQUESTADOR DE CONVERSIÓN (cadena con fallback)
# ============================================================
def _convert_xlsx_to_pdf(xlsx_path: str, out_dir: str) -> str:
    """Convierte XLSX → PDF intentando varios motores en orden.

    Orden de intento:
      1. LibreOffice local (si funciona).
      2. LibreOffice vía Docker (fallback).

    Raises:
        RuntimeError: Si todos los motores fallan, con instrucciones claras.
    """
    # Estrategia 1: LibreOffice local
    pdf = _convert_xlsx_to_pdf_libreoffice(xlsx_path, out_dir)
    if pdf:
        logger.info("[planilla-pdf] Conversión exitosa vía LibreOffice local")
        return pdf

    # Estrategia 2: Docker
    pdf = _convert_xlsx_to_pdf_docker(xlsx_path, out_dir)
    if pdf:
        logger.info("[planilla-pdf] Conversión exitosa vía Docker")
        return pdf

    # Todas fallaron
    raise RuntimeError(
        "No se pudo convertir el Excel a PDF. Se intentaron todas las "
        "estrategias disponibles:\n"
        "  1. LibreOffice local: no encontrado o corrupto.\n"
        "  2. Docker: no disponible o sin imagen de LibreOffice.\n\n"
        "Soluciones:\n"
        "  • Reinstale LibreOffice desde https://www.libreoffice.org/\n"
        "  • O ejecute: docker pull linuxserver/libreoffice:latest\n"
        "  • En el servidor (Docker) funcionará automáticamente."
    )


# ============================================================
# FUNCIÓN PÚBLICA
# ============================================================
def generate_planilla_pdf(
    *,
    event_name: str,
    event_date,
    event_location: str,
    operators: list[dict],
    group_by: str = "coordinator",
    sort_by: str = "lastname",
    with_signatures: bool = False,
) -> bytes:
    """Genera la planilla de pago en PDF, **idéntica al Excel**.

    Proceso (3 pasos):

    1. Genera el ``.xlsx`` con la plantilla corporativa usando
       :func:`generate_planilla_xlsx` (la MISMA que el botón de Excel).
    2. Aplica configuración de impresión (horizontal, Legal, fit-to-width)
       para que el PDF salga bien paginado y legible.
    3. Convierte el ``.xlsx`` a PDF (LibreOffice local → Docker como fallback).

    Args:
        event_name: Nombre del evento.
        event_date: Fecha/hora de inicio del evento.
        event_location: Lugar del evento.
        operators: Lista plana de operadores (mismas claves que el Excel).
        group_by: ``"coordinator"``, ``"role"``, ``"coordinator_role"`` o ``"none"``.
        sort_by: ``"lastname"`` o ``"document"``.

    Returns:
        bytes con el contenido del PDF.

    Raises:
        RuntimeError: Si ningún motor de conversión está disponible.
    """
    import openpyxl

    # --- 1. Generar el Excel (idéntico al botón de descarga Excel) ---
    xlsx_bytes = generate_planilla_xlsx(
        event_name=event_name,
        event_date=event_date,
        event_location=event_location,
        operators=operators,
        group_by=group_by,
        sort_by=sort_by,
        with_signatures=with_signatures,
    )

    # --- 2. Aplicar setup de impresión ---
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    _apply_print_setup(wb)

    # --- 3. Convertir a PDF (con fallback) ---
    with tempfile.TemporaryDirectory(prefix="planilla_pdf_") as tmpdir:
        xlsx_path = os.path.join(tmpdir, "planilla.xlsx")
        wb.save(xlsx_path)

        pdf_path = _convert_xlsx_to_pdf(xlsx_path, tmpdir)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    logger.info(
        "Planilla PDF generada (vía Excel → LibreOffice/Docker): evento=%r, "
        "group_by=%s, sort_by=%s, operadores=%d, tamaño=%d bytes",
        event_name, group_by, sort_by, len(operators), len(pdf_bytes),
    )
    return pdf_bytes
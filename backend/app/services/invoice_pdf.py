"""Servicio para generar facturas individuales en PDF.

Usa ``reportlab`` (platypus) para construir un PDF tamaño carta con:
- Encabezado: A&C Eventos (empresa)
- Datos del evento y del operador
- Número de factura, fecha de pago
- Monto pagado (formato moneda COP)
- Imagen de la firma embebida (base64 PNG decodificado con Pillow)

La función ``generate_invoice_pdf(data)`` devuelve ``bytes`` listos para
usar en ``StreamingResponse`` o empaquetar en un ZIP.
"""
import base64
import io
import logging
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)

# Colores corporativos (marrón/dorado del tema del proyecto)
COLOR_PRIMARY = colors.HexColor("#5d4224")   # marrón oscuro
COLOR_ACCENT = colors.HexColor("#8b6f3f")    # dorado/marrón medio
COLOR_LIGHT = colors.HexColor("#f5f0e8")     # beige claro
COLOR_TEXT = colors.HexColor("#2c2c2c")      # gris oscuro
COLOR_MUTED = colors.HexColor("#6b6b6b")     # gris medio


def _format_cop(amount) -> str:
    """Formatea un número como moneda colombiana: $100.000."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0.0
    # Formato: punto como separador de miles (convención CO)
    return f"${n:,.0f}".replace(",", ".")


def _format_date(dt_str: Optional[str]) -> str:
    """Convierte un ISO string (con o sin tz) a DD/MM/YYYY."""
    if not dt_str:
        return "—"
    try:
        # Manejar el formato ISO con offset Bogotá (....-05:00)
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(dt_str)[:10] if dt_str else "—"


def _decode_signature(signature_data: str) -> Optional[bytes]:
    """Decodifica base64 PNG/JPG de la firma a bytes crudos.

    El frontend guarda la firma como data URL o base64 puro.
    Retorna None si no se puede decodificar.
    """
    if not signature_data:
        return None
    try:
        raw = signature_data.strip()
        # Quitar prefijo data:image/png;base64, si existe
        if "," in raw and raw.startswith("data:image"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw)
    except Exception as exc:
        logger.warning("No se pudo decodificar la firma: %s", exc)
        return None


def _build_signature_image(sig_bytes: bytes, max_width: float = 3.0 * inch,
                           max_height: float = 1.2 * inch) -> Optional[Image]:
    """Convierte bytes de imagen en un Image de reportlab con tamaño ajustado.

    Usa Pillow para dimensionar correctamente sin distorsionar (aspect ratio).
    """
    try:
        from PIL import Image as PILImage

        pil_img = PILImage.open(io.BytesIO(sig_bytes))
        orig_w, orig_h = pil_img.size
        if orig_w == 0 or orig_h == 0:
            return None

        aspect = orig_w / orig_h
        w = max_width
        h = w / aspect
        if h > max_height:
            h = max_height
            w = h * aspect

        return Image(io.BytesIO(sig_bytes), width=w, height=h)
    except Exception as exc:
        logger.warning("No se pudo procesar imagen de firma: %s", exc)
        return None


def generate_invoice_pdf(data: dict) -> bytes:
    """Genera una factura PDF individual.

    Args:
        data: dict con las claves (mismo formato que /api/payroll/invoices/{id}):
            - invoice_number: str | None
            - paid_at: ISO str | None
            - payment_amount: float
            - role_name: str | None
            - signature_data: str (base64 PNG)
            - operator_name: str
            - operator_document: str
            - operator_phone: str
            - event_name: str
            - event_location: str
            - event_date: ISO str | None
            - company: str (default "A&C Eventos")

    Returns:
        bytes con el contenido del PDF.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"Factura {data.get('invoice_number') or ''}",
        author=data.get("company", "A&C Eventos"),
    )

    # --- Estilos ---
    styles = getSampleStyleSheet()
    style_company = ParagraphStyle(
        "Company", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=22,
        textColor=COLOR_PRIMARY, alignment=TA_LEFT, spaceAfter=2,
    )
    style_subtitle = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9,
        textColor=COLOR_MUTED, alignment=TA_LEFT, spaceAfter=0,
    )
    style_h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=12,
        textColor=COLOR_PRIMARY, spaceBefore=10, spaceAfter=6,
    )
    style_label = ParagraphStyle(
        "Label", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=9,
        textColor=COLOR_MUTED, spaceAfter=1,
    )
    style_value = ParagraphStyle(
        "Value", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10,
        textColor=COLOR_TEXT, spaceAfter=6,
    )
    style_amount = ParagraphStyle(
        "Amount", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=16,
        textColor=COLOR_PRIMARY, alignment=TA_RIGHT,
    )
    style_invoice_no = ParagraphStyle(
        "InvNo", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=11,
        textColor=COLOR_ACCENT, alignment=TA_RIGHT,
    )
    style_footer = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontName="Helvetica-Oblique", fontSize=8,
        textColor=COLOR_MUTED, alignment=TA_CENTER,
    )

    story = []

    # --- Encabezado: empresa a la izquierda, factura # a la derecha ---
    company = data.get("company") or "A&C Eventos"
    invoice_no = data.get("invoice_number") or "SIN NÚMERO"

    header_left = [
        Paragraph(company, style_company),
        Paragraph("Servicios de Logística y Personal", style_subtitle),
        Paragraph("NIT: En proceso · Bogotá, Colombia", style_subtitle),
    ]
    header_right = [
        Paragraph("FACTURA", style_invoice_no),
        Paragraph(f"<b>No. {invoice_no}</b>", style_invoice_no),
    ]

    header_table = Table(
        [[header_left, header_right]],
        colWidths=[3.8 * inch, 3.3 * inch],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY))
    story.append(Spacer(1, 10))

    # --- Datos del evento ---
    story.append(Paragraph("Información del Evento", style_h2))

    event_date = _format_date(data.get("event_date"))
    paid_date = _format_date(data.get("paid_at"))

    event_rows = [
        [Paragraph("Evento:", style_label),
         Paragraph(str(data.get("event_name") or "—"), style_value)],
        [Paragraph("Lugar:", style_label),
         Paragraph(str(data.get("event_location") or "—"), style_value)],
        [Paragraph("Fecha del evento:", style_label),
         Paragraph(event_date, style_value)],
        [Paragraph("Fecha de pago:", style_label),
         Paragraph(paid_date, style_value)],
    ]
    event_table = Table(event_rows, colWidths=[1.5 * inch, 5.6 * inch])
    event_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(event_table)
    story.append(Spacer(1, 8))

    # --- Datos del operador ---
    story.append(Paragraph("Datos del Operador", style_h2))

    op_rows = [
        [Paragraph("Nombre:", style_label),
         Paragraph(str(data.get("operator_name") or "—"), style_value),
         Paragraph("Cédula:", style_label),
         Paragraph(str(data.get("operator_document") or "—"), style_value)],
        [Paragraph("Cargo:", style_label),
         Paragraph(str(data.get("role_name") or "Operador"), style_value),
         Paragraph("Teléfono:", style_label),
         Paragraph(str(data.get("operator_phone") or "—"), style_value)],
    ]
    op_table = Table(op_rows, colWidths=[0.9 * inch, 2.6 * inch, 0.9 * inch, 2.0 * inch])
    op_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(op_table)
    story.append(Spacer(1, 14))

    # --- Monto pagado (destacado) ---
    amount_str = _format_cop(data.get("payment_amount"))

    amount_box = Table(
        [[Paragraph("VALOR PAGADO", style_label),
          Paragraph(amount_str, style_amount)]],
        colWidths=[2.5 * inch, 4.6 * inch],
    )
    amount_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT),
        ("BOX", (0, 0), (-1, -1), 1, COLOR_ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 12),
        ("RIGHTPADDING", (1, 0), (1, 0), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(amount_box)
    story.append(Spacer(1, 18))

    # --- Firma del operador ---
    story.append(Paragraph("Firma del Operador", style_h2))

    sig_bytes = _decode_signature(data.get("signature_data", ""))
    sig_image = _build_signature_image(sig_bytes) if sig_bytes else None

    sig_label_style = ParagraphStyle(
        "SigLabel", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9,
        textColor=COLOR_MUTED, alignment=TA_CENTER,
    )

    if sig_image:
        sig_cell = [sig_image, Spacer(1, 4),
                    Paragraph(f"{data.get('operator_name', '—')}", sig_label_style)]
    else:
        sig_cell = [Spacer(1, 60),
                    Paragraph("(Sin firma registrada)", sig_label_style),
                    Spacer(1, 4),
                    Paragraph(f"{data.get('operator_name', '—')}", sig_label_style)]

    firma_table = Table([[sig_cell]], colWidths=[7.1 * inch])
    firma_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, -1), 1, COLOR_MUTED),
        ("LEFTPADDING", (0, 0), (-1, -1), 40),
        ("RIGHTPADDING", (0, 0), (-1, -1), 40),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(firma_table)
    story.append(Spacer(1, 20))

    # --- Pie de página ---
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_LIGHT))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"{company} · Documento generado el "
        f"{datetime.now().strftime('%d/%m/%Y a las %H:%M')}",
        style_footer,
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def generate_invoices_zip(invoices_data: list[dict], event_name: str = "Evento") -> bytes:
    """Genera un ZIP con múltiples facturas PDF.

    Args:
        invoices_data: lista de dicts (mismo formato que generate_invoice_pdf).
        event_name: nombre del evento (para el nombre de archivos internos).

    Returns:
        bytes con el contenido del archivo .zip.
    """
    import zipfile
    import unicodedata
    import re

    def _sanitize(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^A-Za-z0-9_\-]", "_", text.strip().replace(" ", "_"))
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "evento"

    safe_event = _sanitize(event_name)
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, inv in enumerate(invoices_data, 1):
            try:
                pdf = generate_invoice_pdf(inv)
                # Nombre: Factura_Nombre_Operador_001.pdf
                op_name = _sanitize(inv.get("operator_name", "operador"))
                inv_no = _sanitize(inv.get("invoice_number", ""))
                fname = f"Factura_{op_name}_{inv_no or idx:03d}.pdf"
                zf.writestr(fname, pdf)
            except Exception as exc:
                logger.error("Error generando PDF #%d (%s): %s",
                             idx, inv.get("operator_name"), exc)

    zip_bytes = buf.getvalue()
    buf.close()
    return zip_bytes
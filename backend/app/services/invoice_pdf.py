"""Servicio para generar facturas individuales en PDF — formato TÉRMICO 80mm.

Replica fielmente el recibo térmico monocromático que aparece en
``payroll.html`` (#invoice-print-area), pensado para impresoras térmicas
EPSON / Xprinter / SAT de papel de 80mm.

- Tamaño de página: 80mm de ancho × alto variable (calculado en 2 pasadas).
- Tipografía monoespaciada (Courier / Courier-Bold), monocromática.
- Incluye firma del operador embebida (PNG/JPG desde base64).
- La función ``generate_invoice_pdf(data)`` devuelve ``bytes``.
"""
import base64
import io
import logging
import re
import unicodedata
import zipfile
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# --- Constantes de página (80mm térmico) ---
PAGE_WIDTH = 80 * mm
MARGIN = 3 * mm

BLACK = colors.HexColor("#000000")

# Zona horaria Bogotá (UTC-5) para fechas/horas del recibo
BOGOTA_TZ = timezone(timedelta(hours=-5))


# ============================================================
# HELPERS DE FORMATO
# ============================================================
def _format_cop(amount) -> str:
    """Formatea un número como moneda colombiana: $100.000."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"${n:,.0f}".replace(",", ".")


def _parse_bogota(dt_str: Optional[str]) -> Optional[datetime]:
    """Convierte un ISO string a datetime en zona Bogotá.

    El backend guarda ``utcnow()`` naive → lo asumimos UTC y convertimos.
    """
    if not dt_str:
        return None
    s = str(dt_str).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BOGOTA_TZ)


def _fmt_date(dt_str: Optional[str]) -> str:
    dt = _parse_bogota(dt_str)
    return dt.strftime("%d/%m/%Y") if dt else "—"


def _fmt_time(dt_str: Optional[str]) -> str:
    dt = _parse_bogota(dt_str)
    if not dt:
        return "—"
    return dt.strftime("%I:%M %p").lstrip("0")


def _decode_signature(signature_data: Optional[str]) -> Optional[bytes]:
    """Decodifica base64 PNG/JPG de la firma a bytes crudos."""
    if not signature_data:
        return None
    try:
        raw = signature_data.strip()
        if "," in raw and raw.startswith("data:image"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw)
    except Exception as exc:
        logger.warning("No se pudo decodificar la firma: %s", exc)
        return None


# ============================================================
# NÚMERO A LETRAS (formato colombiano)
# ============================================================
_UNIDADES = [
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE",
    "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO", "VEINTIDOS", "VEINTITRES",
    "VEINTICUATRO", "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE",
]
_DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_CENTENAS = [
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
]


def _grupo(n: int) -> str:
    if n == 100:
        return "CIEN"
    if n == 0:
        return ""
    partes: List[str] = []
    h = n // 100
    resto = n % 100
    if h > 0:
        partes.append(_CENTENAS[h])
    if resto > 0:
        if resto < 30:
            partes.append(_UNIDADES[resto])
        else:
            d = resto // 10
            u = resto % 10
            if u == 0:
                partes.append(_DECENAS[d])
            else:
                partes.append(f"{_DECENAS[d]} Y {_UNIDADES[u]}")
    return " ".join(partes)


def numero_a_letras(num) -> str:
    """Ej: 150000 -> 'CIENTO CINCUENTA MIL PESOS M/CTE'."""
    num = int(round(abs(float(num or 0))))
    if num == 0:
        return "CERO PESOS M/CTE"
    if num == 1:
        return "UN PESO M/CTE"

    millones = num // 1_000_000
    miles = (num % 1_000_000) // 1000
    resto = num % 1000

    partes: List[str] = []
    if millones > 0:
        partes.append("UN MILLON" if millones == 1 else f"{_grupo(millones)} MILLONES")
    if miles > 0:
        partes.append("MIL" if miles == 1 else f"{_grupo(miles)} MIL")
    if resto > 0:
        partes.append(_grupo(resto))

    return " ".join(p for p in partes if p).strip() + " PESOS M/CTE"


# ============================================================
# RENDERIZADOR TÉRMICO (canvas directo, alto variable)
# ============================================================
class _ThermalRenderer:
    """Dibuja el recibo térmico sobre un canvas de reportlab."""

    def __init__(self, c: canvas.Canvas, data: dict):
        self.c = c
        self.data = data
        self.width = PAGE_WIDTH
        self.inner = PAGE_WIDTH - 2 * MARGIN
        self.y = 0.0  # cursor vertical (en puntos); se decrementa

    # --- primitivas ---
    def _wrap(self, text: str, font: str, size: float, max_w: Optional[float] = None) -> List[str]:
        max_w = self.inner if max_w is None else max_w
        text = str(text) if text is not None else ""
        words = re.split(r"\s+", text.strip())
        if not words or words == [""]:
            return [""]
        lines: List[str] = []
        cur = ""
        for w in words:
            trial = w if not cur else f"{cur} {w}"
            if self.c.stringWidth(trial, font, size) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                # palabra más larga que el ancho: partir por caracteres
                while self.c.stringWidth(w, font, size) > max_w and len(w) > 1:
                    cut = len(w)
                    while cut > 1 and self.c.stringWidth(w[:cut], font, size) > max_w:
                        cut -= 1
                    lines.append(w[:cut])
                    w = w[cut:]
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    def _lh(self, size: float) -> float:
        return size * 1.35

    def center(self, text, font="Courier", size=8, gap=None):
        self.c.setFont(font, size)
        self.c.setFillColor(BLACK)
        self.c.drawCentredString(self.width / 2, self.y, str(text))
        self.y -= self._lh(size) + (gap or 0.5)

    def left(self, text, font="Courier", size=8, indent=0.0, gap=None):
        self.c.setFont(font, size)
        self.c.setFillColor(BLACK)
        self.c.drawString(MARGIN + indent, self.y, str(text))
        self.y -= self._lh(size) + (gap or 0.3)

    def paragraph(self, text, font="Courier", size=7.5, gap=1.0):
        for ln in self._wrap(text, font, size):
            self.c.setFont(font, size)
            self.c.setFillColor(BLACK)
            self.c.drawString(MARGIN, self.y, ln)
            self.y -= self._lh(size)
        self.y -= gap

    def bullet(self, text, font="Courier", size=7.5, gap=0.8):
        bullet_w = self.c.stringWidth("- ", font, size)
        for i, ln in enumerate(self._wrap(text, font, size, max_w=self.inner - bullet_w)):
            self.c.setFont(font, size)
            self.c.setFillColor(BLACK)
            self.c.drawString(MARGIN, self.y, ("- " + ln) if i == 0 else ("  " + ln))
            self.y -= self._lh(size)
        self.y -= gap

    def row(self, label, value, size=8, gap=0.3):
        """Fila label (izq) + value (der, envuelve si es necesario)."""
        self.c.setFont("Courier", size)
        self.c.setFillColor(BLACK)
        label = str(label)
        label_w = self.c.stringWidth(label, "Courier", size)
        val_w_max = self.inner - label_w - 2.0
        lines = self._wrap(value, "Courier", size, max_w=val_w_max)
        for i, ln in enumerate(lines):
            self.c.setFont("Courier", size)
            if i == 0:
                self.c.drawString(MARGIN, self.y, label)
            self.c.drawRightString(self.width - MARGIN, self.y, ln)
            self.y -= self._lh(size)
        self.y -= gap

    def divider(self, solid=False, gap_before=1.0, gap_after=2.0):
        self.y -= gap_before
        self.c.setStrokeColor(BLACK)
        if solid:
            self.c.setLineWidth(0.8)
            self.c.setDash()
            self.c.line(MARGIN, self.y, self.width - MARGIN, self.y)
        else:
            self.c.setLineWidth(0.5)
            self.c.setDash(1.2, 1.2)
            self.c.line(MARGIN, self.y, self.width - MARGIN, self.y)
            self.c.setDash()  # reset
        self.y -= gap_after

    def section_title(self, title, size=8.5):
        self.center(title.upper(), font="Courier-Bold", size=size, gap=1.0)

    def signature_block(self, sig_bytes: Optional[bytes]):
        # espacio reservado + imagen centrada
        if sig_bytes:
            try:
                from PIL import Image as PILImage

                pil = PILImage.open(io.BytesIO(sig_bytes))
                ow, oh = pil.size
                if ow and oh:
                    max_w = 48 * mm
                    max_h = 18 * mm
                    scale = min(max_w / ow, max_h / oh)
                    w = ow * scale
                    h = oh * scale
                    x = (self.width - w) / 2
                    self.c.drawImage(
                        ImageReader(io.BytesIO(sig_bytes)),
                        x, self.y - h, width=w, height=h, mask="auto",
                    )
                    self.y -= h + 1.0
                    return
            except Exception as exc:
                logger.warning("No se pudo dibujar la firma: %s", exc)
        # sin firma → espacio en blanco
        self.y -= 16 * mm

    def sign_line(self):
        self.c.setStrokeColor(BLACK)
        self.c.setLineWidth(0.6)
        self.c.setDash()
        self.c.line(self.width * 0.15, self.y, self.width * 0.85, self.y)
        self.y -= self._lh(8) + 1.0

    # --- render completo ---
    def render(self, top_y: float) -> float:
        """Dibuja todo el recibo. Devuelve la Y final (inferior)."""
        self.y = top_y
        d = self.data

        inv_no = str(d.get("invoice_number") or "—")
        op_name = str(d.get("operator_name") or "—")
        op_doc = str(d.get("operator_document") or "—")
        role = str(d.get("role_name") or "Operador")
        amount = _format_cop(d.get("payment_amount"))
        event_name = str(d.get("event_name") or "—")
        event_loc = str(d.get("event_location") or "—")
        paid_date = _fmt_date(d.get("paid_at"))
        event_date = _fmt_date(d.get("event_date"))
        sign_date = _fmt_date(d.get("paid_at"))
        sign_time = _fmt_time(d.get("paid_at"))

        # 1. ENCABEZADO EMPRESA
        self.center("A&C LOGISTICA & PRODUCCION", "Courier-Bold", 9)
        self.center("DE EVENTOS LTDA", "Courier-Bold", 9)
        for line in ("NIT: 900.227.354", "Direccion: KR 59 D # 131 - 72",
                     "Bogota - Suba", "Tel: [TELEFONO]",
                     "Email: Facturacion@ayceventos.com.co"):
            self.center(line, "Courier", 7.5)
        self.y -= 1.0

        self.divider()

        # 2. RECIBO
        self.section_title("Recibo de Pago de Servicios")
        self.row("Consecutivo:", inv_no)
        self.row("Fecha:", paid_date)

        self.divider()

        # 3. DATOS DEL EVENTO
        self.section_title("Datos del Evento")
        self.row("Evento:", event_name)
        self.row("Lugar:", event_loc)
        self.row("Fecha Evento:", event_date)

        self.divider()

        # 4. DATOS DEL OPERADOR
        self.section_title("Datos del Operador")
        self.row("Nombre:", op_name)
        self.row("Cedula:", op_doc)
        self.row("Cargo:", role)

        self.divider()

        # 5. VALOR CANCELADO
        self.section_title("Valor Cancelado")
        self.center("TOTAL PAGADO", "Courier-Bold", 10, gap=0.5)
        self.center(amount, "Courier-Bold", 11, gap=0.5)
        self.center(f"({numero_a_letras(d.get('payment_amount'))})",
                    "Courier-Oblique", 7, gap=1.0)

        self.divider()

        # 6. DECLARACIÓN
        self.section_title("Declaracion del Operador")
        self.paragraph(
            '"Declaro haber recibido a satisfaccion de A&C LOGISTICA & '
            'PRODUCCION DE EVENTOS LTDA la suma anteriormente indicada, '
            "correspondiente a los servicios prestados durante el evento "
            'relacionado en este documento.'
        )
        self.paragraph(
            '"Manifiesto que el valor recibido corresponde a la totalidad de '
            "los honorarios pactados por mis servicios y otorgo paz y salvo por "
            'todo concepto relacionado con esta actividad."'
        )

        self.divider()

        # 7. FIRMA DEL OPERADOR
        self.section_title("Firma del Operador")
        sig_bytes = _decode_signature(d.get("signature_data", ""))
        self.signature_block(sig_bytes)
        self.sign_line()
        self.row("Nombre:", op_name)
        self.row("C.C.:", op_doc)
        self.row("Fecha firma:", sign_date)
        self.row("Hora firma:", sign_time)

        self.divider()

        # 8. NOTAS LEGALES
        self.section_title("Notas Legales")
        self.bullet("Este documento constituye soporte interno de pago por prestacion de servicios ocasionales.")
        self.bullet("La firma plasmada en este documento constituye aceptacion expresa del pago recibido.")
        self.bullet("El operador declara haber prestado efectivamente los servicios relacionados.")
        self.bullet("Este comprobante podra ser utilizado como soporte documental ante procesos administrativos, contables y legales.")

        self.divider()

        # 9. PIE
        self.center("Documento generado electronicamente", "Courier", 7, gap=0.3)
        self.center("por el sistema de gestion de", "Courier", 7, gap=0.3)
        self.center("personal eventual.", "Courier", 7, gap=1.0)

        self.divider(solid=True, gap_after=0)

        return self.y


# ============================================================
# API PÚBLICA
# ============================================================
def generate_invoice_pdf(data: dict) -> bytes:
    """Genera una factura PDF individual en formato TÉRMICO 80mm.

    El alto de página se calcula dinámicamente en dos pasadas para que el
    PDF mida exactamente lo que ocupa el contenido (sin espacio en blanco
    sobrante), ideal para impresión en papel térmico EPSON/Xprinter/SAT.
    """
    TALL = 4000.0  # canvas de medición (suficientemente alto)

    # --- Pasada 1: medir altura usada ---
    probe = io.BytesIO()
    c_probe = canvas.Canvas(probe, pagesize=(PAGE_WIDTH, TALL))
    final_y = _ThermalRenderer(c_probe, data).render(top_y=TALL - MARGIN)
    used_height = (TALL - MARGIN) - final_y + MARGIN
    used_height = max(used_height, 60 * mm)  # mínimo razonable

    # --- Pasada 2: render real con altura exacta ---
    buf = io.BytesIO()
    c = canvas.Canvas(
        buf,
        pagesize=(PAGE_WIDTH, used_height),
        title=f"Factura {data.get('invoice_number') or ''}",
        author=data.get("company") or "A&C Eventos",
    )
    _ThermalRenderer(c, data).render(top_y=used_height - MARGIN)
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def generate_invoices_zip(invoices_data: list[dict], event_name: str = "Evento") -> bytes:
    """Genera un ZIP con múltiples facturas PDF (formato térmico).

    Si TODAS las facturas fallan, lanza ``RuntimeError`` con el primer error,
    para que el endpoint devuelva 500 con el traceback real (en vez de un
    ZIP vacío silencioso).
    """
    def _sanitize(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^A-Za-z0-9_\-]", "_", str(text).strip().replace(" ", "_"))
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "evento"

    safe_event = _sanitize(event_name)
    buf = io.BytesIO()

    generated = 0
    failed = 0
    first_error: Optional[Exception] = None
    first_error_op: Optional[str] = None

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, inv in enumerate(invoices_data, 1):
            op_label = inv.get("operator_name") or inv.get("invoice_number") or f"#{idx}"
            try:
                pdf = generate_invoice_pdf(inv)
                if not pdf:
                    raise RuntimeError("generate_invoice_pdf devolvió bytes vacíos")
                op_name = _sanitize(inv.get("operator_name", "operador"))
                inv_no = _sanitize(inv.get("invoice_number", ""))
                # El formato :03d solo aplica al índice (int), nunca al string.
                suffix = inv_no if inv_no else f"{idx:03d}"
                fname = f"Factura_{op_name}_{suffix}.pdf"
                zf.writestr(fname, pdf)
                generated += 1
            except Exception as exc:
                failed += 1
                if first_error is None:
                    first_error = exc
                    first_error_op = str(op_label)
                # Traceback completo para diagnóstico (no solo el mensaje)
                logger.exception(
                    "Error generando PDF #%d (%s): %s", idx, op_label, exc
                )

    # Si TODOS fallaron, no devolver un ZIP vacío: lanzar el error real.
    if generated == 0 and invoices_data:
        msg = (
            f"No se pudo generar NINGÚN PDF de {len(invoices_data)} facturas. "
            f"Primer error (operador '{first_error_op}'): "
            f"{type(first_error).__name__}: {first_error}"
        )
        raise RuntimeError(msg) from first_error

    logger.info(
        "ZIP facturas '%s': %d OK, %d fallidos de %d total",
        safe_event, generated, failed, len(invoices_data),
    )

    zip_bytes = buf.getvalue()
    buf.close()
    return zip_bytes

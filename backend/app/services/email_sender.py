"""SMTP email sender — envío de respuestas a PQRSF.

Arquitectura:
    - send_email()  → envía via SMTP async (aiosmtplib). Respeta SMTP_ENABLED
                      (fail-safe: en dev solo loggea).
    - render_pqrsf_response_email() → genera HTML con Jinja2 embebido.

Este servicio es desacoplado del sistema de templates de FastAPI para
poder usarse desde workers/scripts futuros sin depender del app context.
"""
import logging
from email.message import EmailMessage
from html import escape
from typing import Optional

import aiosmtplib
from jinja2 import Template

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email HTML template (PQRSF response)
# ---------------------------------------------------------------------------
_PQRSF_EMAIL_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ subject }}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <tr>
            <td style="background-color:#b8860b;padding:24px 32px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">AyC Logística y Producción de Eventos LTDA</h1>
              <p style="margin:4px 0 0 0;color:#fef3c7;font-size:13px;">Respuesta a su solicitud PQRSF</p>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <p style="margin:0 0 16px 0;font-size:15px;">Estimado/a <strong>{{ recipient_name }}</strong>,</p>
              <p style="margin:0 0 16px 0;font-size:15px;">Hemos recibido y revisado su solicitud registrada con el código de seguimiento:</p>
              <p style="margin:0 0 16px 0;text-align:center;">
                <span style="display:inline-block;background-color:#f3f4f6;color:#b8860b;font-weight:bold;font-size:18px;padding:8px 16px;border-radius:4px;letter-spacing:1px;">{{ tracking_code }}</span>
              </p>
              <hr style="border:0;border-top:1px solid #e5e7eb;margin:24px 0;">
              <div style="font-size:15px;line-height:1.6;color:#374151;">
                {{ body_html }}
              </div>
              <hr style="border:0;border-top:1px solid #e5e7eb;margin:24px 0;">
              <p style="margin:0;font-size:13px;color:#6b7280;">
                Si tiene inquietudes adicionales, responda este correo indicando su código de seguimiento.
              </p>
              <p style="margin:8px 0 0 0;font-size:12px;color:#9ca3af;">
                — Equipo AyC Eventos · Este es un correo automatizado.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""")


_CONTACT_NOTIFY_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nueva solicitud de contacto</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <tr>
            <td style="background-color:#b8860b;padding:24px 32px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">AyC Logística y Producción de Eventos LTDA</h1>
              <p style="margin:4px 0 0 0;color:#fef3c7;font-size:13px;">Nueva solicitud de contacto recibida</p>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;line-height:1.6;color:#374151;border:1px solid #e5e7eb;">
                <tr>
                  <td style="padding:10px 16px;background-color:#f9fafb;font-weight:bold;width:160px;border-bottom:1px solid #e5e7eb;">Nombre</td>
                  <td style="padding:10px 16px;border-bottom:1px solid #e5e7eb;">{{ full_name }}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;background-color:#f9fafb;font-weight:bold;border-bottom:1px solid #e5e7eb;">Email</td>
                  <td style="padding:10px 16px;border-bottom:1px solid #e5e7eb;">{{ email }}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;background-color:#f9fafb;font-weight:bold;border-bottom:1px solid #e5e7eb;">Teléfono</td>
                  <td style="padding:10px 16px;border-bottom:1px solid #e5e7eb;">{{ phone }}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;background-color:#f9fafb;font-weight:bold;border-bottom:1px solid #e5e7eb;">Empresa</td>
                  <td style="padding:10px 16px;border-bottom:1px solid #e5e7eb;">{{ company }}</td>
                </tr>
                <tr>
                  <td style="padding:10px 16px;background-color:#f9fafb;font-weight:bold;border-bottom:1px solid #e5e7eb;">Tipo de evento</td>
                  <td style="padding:10px 16px;border-bottom:1px solid #e5e7eb;">{{ event_type }}</td>
                </tr>
              </table>
              <p style="margin:24px 0 8px 0;font-size:14px;font-weight:bold;color:#1f2937;">Mensaje:</p>
              <div style="font-size:15px;line-height:1.6;color:#374151;background-color:#f9fafb;border-left:4px solid #b8860b;padding:16px;">
                {{ message_html }}
              </div>
              <hr style="border:0;border-top:1px solid #e5e7eb;margin:24px 0;">
              <p style="margin:0;font-size:13px;color:#6b7280;">
                Puede responder directamente a este correo; el Reply-To apunta al email del solicitante.
                También puede gestionar la solicitud en el panel de administración (Contenido → Solicitudes).
              </p>
              <p style="margin:8px 0 0 0;font-size:12px;color:#9ca3af;">
                — Equipo AyC Eventos · Este es un correo automatizado.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""")


def render_contact_notification_email(
    *,
    full_name: str,
    email: str,
    phone: Optional[str],
    company: Optional[str],
    event_type: Optional[str],
    message: str,
) -> str:
    """Renderiza el HTML del email interno de notificación de solicitud de contacto.

    Todos los campos se escapan y el mensaje convierte saltos de línea a <br>.
    """
    message_html = escape(message).replace("\n", "<br>\n")
    return _CONTACT_NOTIFY_TEMPLATE.render(
        full_name=escape(full_name),
        email=escape(email),
        phone=escape(phone or "No indicado"),
        company=escape(company or "No indicada"),
        event_type=escape(event_type or "General"),
        message_html=message_html,
    )


async def notify_contact_request(
    *,
    full_name: str,
    email: str,
    phone: Optional[str],
    company: Optional[str],
    event_type: Optional[str],
    message: str,
) -> None:
    """Envía la notificación interna de una nueva solicitud de contacto.

    Envía a cada destinatario de settings.contact_notify_list un email con todos
    los datos del solicitante. Reply-To = email del solicitante para poder
    responder directo.

    Fail-safe: nunca propaga excepciones — un error SMTP no debe romper el
    flujo público del formulario de contacto (el endpoint siempre responde 201).
    """
    recipients = settings.contact_notify_list
    if not recipients:
        logger.debug(
            "[CONTACT-NOTIFY] CONTACT_NOTIFY_EMAILS vacío: se omite la notificación."
        )
        return

    subject = f"[Contacto] Nueva solicitud de {full_name} — {event_type or 'General'}"
    html_body = render_contact_notification_email(
        full_name=full_name,
        email=email,
        phone=phone,
        company=company,
        event_type=event_type,
        message=message,
    )

    try:
        for to_email in recipients:
            try:
                await send_email(
                    to_email=to_email,
                    subject=subject,
                    html_body=html_body,
                    reply_to=email,
                )
            except Exception as exc:
                # Un destinatario fallido no impide los demás
                logger.error(
                    "[CONTACT-NOTIFY] Error enviando a %s: %s", to_email, exc
                )
        logger.info(
            "[CONTACT-NOTIFY] Notificación de contacto de %s procesada (%d destinatario/s).",
            full_name, len(recipients),
        )
    except Exception as exc:
        logger.error("[CONTACT-NOTIFY] Error inesperado: %s", exc)


def render_pqrsf_response_email(
    *,
    tracking_code: str,
    recipient_name: str,
    subject: str,
    body: str,
) -> str:
    """Renderiza el HTML del email de respuesta a una PQRSF.

    El `body` se escapacomo texto plano y se convierten saltos de línea a <br>.
    """
    # Convertir texto plano a HTML seguro (escapar + preservar saltos de línea)
    body_html = escape(body).replace("\n", "<br>\n")
    return _PQRSF_EMAIL_TEMPLATE.render(
        tracking_code=escape(tracking_code),
        recipient_name=escape(recipient_name),
        subject=escape(subject),
        body_html=body_html,
    )


async def send_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    reply_to: Optional[str] = None,
) -> bool:
    """Envía un email HTML vía SMTP.

    Args:
        to_email: Email del destinatario.
        subject: Asunto del email.
        html_body: Cuerpo en HTML.
        reply_to: Dirección Reply-To (opcional; default: settings.PQRSF_REPLY_TO).

    Returns:
        True si el email se envió (o si SMTP_ENABLED=False, simulación OK).

    Raises:
        Exception: Si el envío falla en producción.
    """
    # Fail-safe: en dev (SMTP_ENABLED=False), solo loggear.
    if not settings.SMTP_ENABLED:
        logger.info(
            "[EMAIL-DEV] SMTP deshabilitado. Simulando envío:\n"
            "  To: %s\n  Subject: %s\n  Reply-To: %s\n"
            "  Body length: %d chars",
            to_email, subject, reply_to or settings.PQRSF_REPLY_TO,
            len(html_body),
        )
        return True

    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning(
            "[EMAIL] SMTP_ENABLED=true pero falta SMTP_HOST/SMTP_USER. "
            "No se puede enviar el email a %s.", to_email,
        )
        raise RuntimeError("Configuración SMTP incompleta (HOST/USER vacíos).")

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = reply_to or settings.PQRSF_REPLY_TO
    msg.set_content("Su cliente de correo no soporta HTML. Por favor use uno moderno.")
    msg.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
        )
        logger.info("[EMAIL] Enviado OK a %s | Subject: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("[EMAIL] Error enviando a %s: %s", to_email, exc)
        raise
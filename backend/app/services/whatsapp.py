"""WhatsApp service — Zenvia API v2 + simulation fallback + webhook handling."""
import uuid
import json
from datetime import datetime
from typing import Optional, List

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.whatsapp import WhatsAppOutboundQueue
from app.models.events import EventAssignment, EventStaffNeed, Event
from app.models.operators import Operator
from app.models.users import User


# ============================================================
# HELPERS
# ============================================================

def _is_configured() -> bool:
    """Check if Zenvia API credentials are configured."""
    return bool(settings.ZENVIA_API_KEY and settings.ZENVIA_CHANNEL_ID)


async def _send_template_message(
    phone_number: str,
    template_name: str,
    parameters: list[str],
) -> dict:
    """Send a template message via Zenvia WhatsApp API v2."""
    url = f"{settings.ZENVIA_API_URL}/channels/whatsapp/messages"
    headers = {
        "X-API-TOKEN": settings.ZENVIA_API_KEY,
        "Content-Type": "application/json",
    }

    # Build template fields from positional parameters
    template_fields = {}
    for i, param in enumerate(parameters, start=1):
        template_fields[str(i)] = param

    payload = {
        "from": settings.ZENVIA_CHANNEL_ID,
        "to": phone_number,
        "contents": [
            {
                "type": "template",
                "templateName": template_name,
                "templateFields": template_fields,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=headers)
        data = response.json()

    if response.status_code in (200, 201, 202):
        return {"success": True, "message_id": data.get("id", str(uuid.uuid4()))}
    else:
        error_msg = data.get("message", data.get("error", str(data)))
        return {"success": False, "error": error_msg}


async def _send_text_message(
    phone_number: str,
    text: str,
) -> dict:
    """Send a plain text message via Zenvia WhatsApp API v2."""
    url = f"{settings.ZENVIA_API_URL}/channels/whatsapp/messages"
    headers = {
        "X-API-TOKEN": settings.ZENVIA_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "from": settings.ZENVIA_CHANNEL_ID,
        "to": phone_number,
        "contents": [
            {
                "type": "text",
                "text": text,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=headers)
        data = response.json()

    if response.status_code in (200, 201, 202):
        return {"success": True, "message_id": data.get("id", str(uuid.uuid4()))}
    else:
        error_msg = data.get("message", data.get("error", str(data)))
        return {"success": False, "error": error_msg}


# ============================================================
# QUEUE INVITATIONS
# ============================================================

async def queue_invitations(
    db: AsyncSession, event_id: uuid.UUID, assignment_ids: Optional[List[uuid.UUID]] = None
) -> List[WhatsAppOutboundQueue]:
    """Queue (and send if configured) WhatsApp invitation messages."""
    query = select(EventAssignment).where(
        EventAssignment.event_id == event_id,
        EventAssignment.status == "invited",
    )
    if assignment_ids:
        query = query.where(EventAssignment.id.in_(assignment_ids))

    result = await db.execute(query)
    assignments = result.scalars().all()

    event = await db.get(Event, event_id)
    if not event:
        return []

    messages = []
    for assignment in assignments:
        op_result = await db.execute(
            select(Operator).where(Operator.id == assignment.operator_id)
        )
        operator = op_result.scalar_one_or_none()
        if not operator:
            continue

        user_result = await db.execute(select(User).where(User.id == operator.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.phone:
            continue

        # Avoid duplicates
        existing = await db.execute(
            select(WhatsAppOutboundQueue).where(
                WhatsAppOutboundQueue.assignment_id == assignment.id,
                WhatsAppOutboundQueue.message_type == "invitation",
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Get role name for the template
        role_name = "Operador"
        if assignment.role_id:
            from app.models.roles import Role
            role_r = await db.execute(select(Role).where(Role.id == assignment.role_id))
            role = role_r.scalar_one_or_none()
            if role:
                role_name = role.name

        template_params = json.dumps({
            "operator_name": f"{user.first_name} {user.last_name}",
            "event_name": event.name,
            "date": event.start_date.strftime("%d/%m/%Y %H:%M"),
            "location": event.location,
            "role_name": role_name,
        })

        phone = user.phone
        if not phone.startswith("+"):
            phone = "+57" + phone

        msg = WhatsAppOutboundQueue(
            event_id=event_id,
            assignment_id=assignment.id,
            phone_number=phone,
            template_name=settings.ZENVIA_TEMPLATE_INVITATION,
            template_params=template_params,
            message_type="invitation",
            status="pending",
        )
        db.add(msg)
        await db.flush()

        # Send immediately if Zenvia API is configured
        if _is_configured():
            params = [
                f"{user.first_name} {user.last_name}",
                event.name,
                event.start_date.strftime("%d/%m/%Y %H:%M"),
                event.location,
                role_name,
            ]
            result_send = await _send_template_message(phone, settings.ZENVIA_TEMPLATE_INVITATION, params)
            if result_send["success"]:
                msg.status = "sent"
                msg.sent_at = datetime.utcnow().isoformat()
                msg.meta_message_id = result_send.get("message_id", "")
            else:
                msg.status = "failed"
                msg.error_message = result_send.get("error", "Unknown error")
            msg.attempts += 1

        messages.append(msg)

    await db.commit()
    return messages


# ============================================================
# QUEUE REMINDERS
# ============================================================

async def queue_reminder(
    db: AsyncSession, event_id: uuid.UUID, message_type: str = "reminder_1d"
) -> List[WhatsAppOutboundQueue]:
    """Queue reminder messages for confirmed operators."""
    result = await db.execute(
        select(EventAssignment).where(
            EventAssignment.event_id == event_id,
            EventAssignment.status == "confirmed",
        )
    )
    assignments = result.scalars().all()

    event = await db.get(Event, event_id)
    if not event:
        return []

    messages = []
    for assignment in assignments:
        op_result = await db.execute(
            select(Operator).where(Operator.id == assignment.operator_id)
        )
        operator = op_result.scalar_one_or_none()
        if not operator:
            continue

        user_result = await db.execute(select(User).where(User.id == operator.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.phone:
            continue

        # Get role name
        role_name = "Operador"
        if assignment.role_id:
            from app.models.roles import Role
            role_r = await db.execute(select(Role).where(Role.id == assignment.role_id))
            role = role_r.scalar_one_or_none()
            if role:
                role_name = role.name

        template_params = json.dumps({
            "operator_name": f"{user.first_name} {user.last_name}",
            "event_name": event.name,
            "date": event.start_date.strftime("%d/%m/%Y %H:%M"),
            "location": event.location,
            "role_name": role_name,
        })

        phone = user.phone
        if not phone.startswith("+"):
            phone = "+57" + phone

        # Map message_type to configurable template name
        template_name_map = {
            "reminder_1d": settings.ZENVIA_TEMPLATE_REMINDER_1D,
            "reminder_5d": settings.ZENVIA_TEMPLATE_REMINDER_5D,
        }
        template_name = template_name_map.get(message_type, message_type)

        msg = WhatsAppOutboundQueue(
            event_id=event_id,
            assignment_id=assignment.id,
            phone_number=phone,
            template_name=template_name,
            template_params=template_params,
            message_type=message_type,
            status="pending",
        )
        db.add(msg)
        await db.flush()

        if _is_configured():
            params = [
                f"{user.first_name} {user.last_name}",
                event.name,
                event.start_date.strftime("%d/%m/%Y %H:%M"),
                event.location,
                role_name,
            ]
            result_send = await _send_template_message(phone, template_name, params)
            if result_send["success"]:
                msg.status = "sent"
                msg.sent_at = datetime.utcnow().isoformat()
                msg.meta_message_id = result_send.get("message_id", "")
            else:
                msg.status = "failed"
                msg.error_message = result_send.get("error", "Unknown error")
            msg.attempts += 1

        messages.append(msg)

    await db.commit()
    return messages


# ============================================================
# SEND PENDING (simulation fallback)
# ============================================================

async def simulate_send_pending(db: AsyncSession) -> dict:
    """Simulate sending pending messages (used when Zenvia API is NOT configured)."""
    result = await db.execute(
        select(WhatsAppOutboundQueue).where(
            WhatsAppOutboundQueue.status == "pending",
            WhatsAppOutboundQueue.attempts < WhatsAppOutboundQueue.max_attempts,
        ).limit(50)
    )
    pending = result.scalars().all()

    sent = 0
    for msg in pending:
        msg.attempts += 1
        msg.status = "sent"
        msg.sent_at = datetime.utcnow().isoformat()
        msg.meta_message_id = f"sim_{uuid.uuid4().hex[:12]}"
        sent += 1

    await db.commit()
    return {"sent": sent, "total": len(pending), "mode": "simulation"}


async def send_pending_real(db: AsyncSession) -> dict:
    """Send pending messages via Zenvia API."""
    result = await db.execute(
        select(WhatsAppOutboundQueue).where(
            WhatsAppOutboundQueue.status == "pending",
            WhatsAppOutboundQueue.attempts < WhatsAppOutboundQueue.max_attempts,
        ).limit(50)
    )
    pending = result.scalars().all()

    sent = 0
    failed = 0
    for msg in pending:
        params_data = json.loads(msg.template_params) if msg.template_params else {}
        params = [
            params_data.get("operator_name", ""),
            params_data.get("event_name", ""),
            params_data.get("date", ""),
            params_data.get("location", ""),
            params_data.get("role_name", ""),
        ]
        result_send = await _send_template_message(msg.phone_number, msg.template_name, params)
        msg.attempts += 1
        if result_send["success"]:
            msg.status = "sent"
            msg.sent_at = datetime.utcnow().isoformat()
            msg.meta_message_id = result_send.get("message_id", "")
            sent += 1
        else:
            msg.error_message = result_send.get("error", "Unknown error")
            if msg.attempts >= msg.max_attempts:
                msg.status = "failed"
            failed += 1

    await db.commit()
    return {"sent": sent, "failed": failed, "total": len(pending), "mode": "zenvia"}


# ============================================================
# GET QUEUE
# ============================================================

async def get_queue(
    db: AsyncSession,
    event_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[List[dict], int]:
    """Get WhatsApp message queue with filters."""
    query = select(WhatsAppOutboundQueue)
    count_query = select(func.count()).select_from(WhatsAppOutboundQueue)

    if event_id:
        query = query.where(WhatsAppOutboundQueue.event_id == event_id)
        count_query = count_query.where(WhatsAppOutboundQueue.event_id == event_id)
    if status_filter:
        query = query.where(WhatsAppOutboundQueue.status == status_filter)
        count_query = count_query.where(WhatsAppOutboundQueue.status == status_filter)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(WhatsAppOutboundQueue.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    messages = result.scalars().all()

    items = []
    for m in messages:
        items.append({
            "id": str(m.id),
            "event_id": str(m.event_id) if m.event_id else None,
            "phone_number": m.phone_number,
            "template_name": m.template_name,
            "message_type": m.message_type,
            "status": m.status,
            "attempts": m.attempts,
            "max_attempts": m.max_attempts,
            "sent_at": m.sent_at,
            "zenvia_message_id": m.meta_message_id,
            "error_message": m.error_message,
            "created_at": str(m.created_at) if m.created_at else None,
        })
    return items, total


# ============================================================
# UPDATE ASSIGNMENT STATUS
# ============================================================

async def update_assignment_status(
    db: AsyncSession, assignment_id: uuid.UUID, new_status: str
) -> Optional[EventAssignment]:
    """Update assignment status (confirmed/rejected/no_show/etc).

    Mantiene quantity_confirmed del EventStaffNeed coherente:
    - Solo cuenta como 'confirmado' si el nuevo estado es 'confirmed'.
    - Si el operador PASÓ de confirmed a otro estado (rejected, no_show...),
      se decrementa el contador.
    - Evita doble conteo si se confirma varias veces.
    """
    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        return None

    old_status = assignment.status

    # Evitar trabajo innecesario si el estado no cambia
    if old_status == new_status:
        return assignment

    assignment.status = new_status
    now = datetime.utcnow()
    if new_status == "confirmed":
        assignment.confirmed_at = now
    elif new_status == "rejected":
        assignment.rejected_at = now

    # Ajustar quantity_confirmed del EventStaffNeed según la transición
    if assignment.role_id:
        sn_result = await db.execute(
            select(EventStaffNeed).where(
                EventStaffNeed.event_id == assignment.event_id,
                EventStaffNeed.role_id == assignment.role_id,
            )
        )
        sn = sn_result.scalar_one_or_none()
        if sn:
            was_confirmed = old_status == "confirmed"
            is_confirmed = new_status == "confirmed"

            if is_confirmed and not was_confirmed:
                # Ganó un confirmado
                sn.quantity_confirmed = max(sn.quantity_confirmed + 1, 0)
            elif was_confirmed and not is_confirmed:
                # Perdió un confirmado (se retractó / no_show / rechazó)
                sn.quantity_confirmed = max(sn.quantity_confirmed - 1, 0)

    await db.commit()
    return assignment


# ============================================================
# WEBHOOK: process incoming messages (Zenvia format)
# ============================================================

async def process_webhook_payload(db: AsyncSession, payload: dict) -> Optional[str]:
    """Process incoming Zenvia webhook payload.

    Zenvia sends:
    {
      "id": "evt-uuid",
      "timestamp": "...",
      "type": "MESSAGE",
      "contact": {
        "name": "Juan",
        "phoneNumber": "+573001234567"
      },
      "message": {
        "id": "msg-uuid",
        "direction": "IN",
        "contents": [
          {"type": "text", "text": "CONFIRMAR"}
        ]
      }
    }
    """
    try:
        event_type = payload.get("type", "")

        # Handle message events
        if event_type == "MESSAGE":
            contact = payload.get("contact", {})
            phone = contact.get("phoneNumber", "")
            message_data = payload.get("message", {})
            contents = message_data.get("contents", [])

            if not contents or not phone:
                return "empty"

            # Get the first content item
            content = contents[0]
            content_type = content.get("type", "")

            # Parse configurable keywords from settings
            confirm_keywords = set(k.strip().upper() for k in settings.ZENVIA_CONFIRM_KEYWORDS.split(","))
            reject_keywords = set(k.strip().upper() for k in settings.ZENVIA_REJECT_KEYWORDS.split(","))

            if content_type == "text":
                text = content.get("text", "").upper().strip()
                assignment = await _find_assignment_by_phone(db, phone)
                if assignment:
                    if text in confirm_keywords:
                        await update_assignment_status(db, assignment.id, "confirmed")
                        return "confirmed"
                    elif text in reject_keywords:
                        await update_assignment_status(db, assignment.id, "rejected")
                        return "rejected"

            elif content_type == "reply":
                # Quick reply button
                reply_text = content.get("text", "").upper().strip()
                assignment = await _find_assignment_by_phone(db, phone)
                if assignment:
                    if reply_text in confirm_keywords:
                        await update_assignment_status(db, assignment.id, "confirmed")
                        return "confirmed"
                    elif reply_text in reject_keywords:
                        await update_assignment_status(db, assignment.id, "rejected")
                        return "rejected"

            return "unhandled_text"

        # Handle message status updates (delivered, read, etc.)
        elif event_type == "MESSAGE_STATUS":
            message_status = payload.get("message", {}).get("status", "")
            message_id = payload.get("message", {}).get("id", "")
            if message_id and message_status:
                result = await db.execute(
                    select(WhatsAppOutboundQueue).where(
                        WhatsAppOutboundQueue.meta_message_id == message_id
                    )
                )
                msg = result.scalar_one_or_none()
                if msg:
                    # Map Zenvia status to our status
                    status_map = {
                        "delivered": "delivered",
                        "read": "read",
                        "failed": "failed",
                    }
                    msg.status = status_map.get(message_status, msg.status)
                    await db.commit()
            return "status_updated"

        return "unhandled_event"

    except (IndexError, KeyError) as e:
        return f"error: {str(e)}"


async def _find_assignment_by_phone(db: AsyncSession, phone: str) -> Optional[EventAssignment]:
    """Find the most recent invitation assignment for a phone number."""
    # Normalize phone
    clean_phone = phone.lstrip("+")
    if clean_phone.startswith("57"):
        clean_phone = clean_phone[2:]

    # Find user by phone
    user_result = await db.execute(
        select(User).where(User.phone.contains(clean_phone))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    # Find operator
    op_result = await db.execute(
        select(Operator).where(Operator.user_id == user.id)
    )
    operator = op_result.scalar_one_or_none()
    if not operator:
        return None

    # Get most recent invited assignment
    assignment_result = await db.execute(
        select(EventAssignment)
        .where(EventAssignment.operator_id == operator.id, EventAssignment.status == "invited")
        .order_by(EventAssignment.invited_at.desc())
        .limit(1)
    )
    return assignment_result.scalar_one_or_none()
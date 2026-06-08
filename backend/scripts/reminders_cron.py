"""
Automatic reminders cron — run periodically to send reminders for upcoming events.
Usage: python -m scripts.reminders_cron
Or via cron: 0 8 * * * cd /app && python -m scripts.reminders_cron
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.services import whatsapp as svc
from sqlalchemy import select, and_
from app.models.events import Event, EventAssignment
from app.models.whatsapp import WhatsAppOutboundQueue


async def send_automatic_reminders():
    """Send reminders for events happening in 1 day and 5 days."""
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        
        # --- 1 day reminder ---
        target_1d = now + timedelta(days=1)
        window_start_1d = target_1d - timedelta(hours=2)
        window_end_1d = target_1d + timedelta(hours=2)
        
        events_1d = await db.execute(
            select(Event).where(
                Event.status.in_(["published", "in_progress"]),
                Event.start_date >= window_start_1d,
                Event.start_date <= window_end_1d,
            )
        )
        
        sent_1d = 0
        for event in events_1d.scalars().all():
            # Check if we already sent a 1d reminder for this event
            existing = await db.execute(
                select(WhatsAppOutboundQueue).where(
                    WhatsAppOutboundQueue.event_id == event.id,
                    WhatsAppOutboundQueue.message_type == "reminder_1d",
                    WhatsAppOutboundQueue.status.in_(["sent", "pending"]),
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            messages = await svc.queue_reminder(db, event.id, "reminder_1d")
            sent_1d += len(messages)
            print(f"📅 Recordatorio 1d para '{event.name}': {len(messages)} mensajes")
        
        # --- 5 days reminder ---
        target_5d = now + timedelta(days=5)
        window_start_5d = target_5d - timedelta(hours=12)
        window_end_5d = target_5d + timedelta(hours=12)
        
        events_5d = await db.execute(
            select(Event).where(
                Event.status.in_(["published", "in_progress"]),
                Event.start_date >= window_start_5d,
                Event.start_date <= window_end_5d,
            )
        )
        
        sent_5d = 0
        for event in events_5d.scalars().all():
            existing = await db.execute(
                select(WhatsAppOutboundQueue).where(
                    WhatsAppOutboundQueue.event_id == event.id,
                    WhatsAppOutboundQueue.message_type == "reminder_5d",
                    WhatsAppOutboundQueue.status.in_(["sent", "pending"]),
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            messages = await svc.queue_reminder(db, event.id, "reminder_5d")
            sent_5d += len(messages)
            print(f"📅 Recordatorio 5d para '{event.name}': {len(messages)} mensajes")
        
        # --- Auto-send pending if configured ---
        pending_count = 0
        if svc._is_configured():
            result = await svc.send_pending_real(db)
            pending_count = result.get("sent", 0)
        else:
            result = await svc.simulate_send_pending(db)
            pending_count = result.get("sent", 0)
        
        print(f"\n✅ Resumen:")
        print(f"   Recordatorios 1d: {sent_1d}")
        print(f"   Recordatorios 5d: {sent_5d}")
        print(f"   Mensajes enviados: {pending_count}")


if __name__ == "__main__":
    print(f"🕐 Ejecutando cron de recordatorios — {datetime.utcnow().isoformat()}")
    asyncio.run(send_automatic_reminders())
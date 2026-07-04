"""All SQLAlchemy models — import this to register all tables with Base.metadata."""

# Base model (must be first)
from app.models.base import BaseModel

# Catalogs
from app.models.roles import Role
from app.models.eps import EPS
from app.models.pension_fund import PensionFund

# Core
from app.models.users import User
from app.models.operators import Operator

# Events
from app.models.events import Event, EventStaffNeed, EventAssignment, EventStaffAssignment, EventAuditLog, EventCoordinatorQuota

# WhatsApp
from app.models.whatsapp import WhatsAppOutboundQueue

# Sync / PWA
from app.models.sync import SyncSession, AttendanceLog

# Payroll
from app.models.payroll import Evaluation, PayrollRecord

# Security / Audit
from app.models.audit import AuditLog, RevokedToken
from app.models.blocked_document import BlockedDocument
from app.models.password_reset import PasswordResetToken

__all__ = [
    "BaseModel",
    "Role", "EPS", "PensionFund",
    "User", "Operator",
    "Event", "EventStaffNeed", "EventAssignment", "EventStaffAssignment",
    "EventAuditLog", "EventCoordinatorQuota",
    "WhatsAppOutboundQueue",
    "SyncSession", "AttendanceLog",
    "Evaluation", "PayrollRecord",
    "AuditLog", "RevokedToken",
    "BlockedDocument",
    "PasswordResetToken",
]

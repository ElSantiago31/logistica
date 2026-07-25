"""Centralized authorization constants and helpers.

Single source of truth for user roles (user_type) and permission checks.
Replaces the scattered inline checks like ``user.user_type not in (...)``.

NOTE on terminology:
  - ``user_type`` is the SYSTEM role of a user account (who can log in):
      ``superadmin``, ``admin``, ``checkin``, ``operator``, ``web_admin``.
  - ``coordinator`` as a *concept* (event area leader, planilla grouping,
    EventCoordinatorQuota, /coordinador module) is NOT a user_type and is
    kept intact. It lives as data inside events, not as a login role.
"""
from __future__ import annotations

from typing import Iterable

from app.models.users import User

# ------------------------------------------------------------------
#  Role constants (user_type values)
# ------------------------------------------------------------------
SUPERADMIN = "superadmin"
ADMIN = "admin"
CHECKIN = "checkin"
OPERATOR = "operator"
WEB_ADMIN = "web_admin"

ALL_ROLES: frozenset[str] = frozenset({SUPERADMIN, ADMIN, CHECKIN, OPERATOR, WEB_ADMIN})

# Management = users who run the back-office (dashboard, events, operators).
MANAGEMENT_ROLES: frozenset[str] = frozenset({SUPERADMIN, ADMIN})

# All staff (non-operator) accounts that may appear in admin views.
ALL_STAFF: frozenset[str] = frozenset({SUPERADMIN, ADMIN, CHECKIN, WEB_ADMIN})

# Roles allowed to be CREATED from /admin/superadmin (depending on caller).
CREATABLE_BY_ADMIN: frozenset[str] = frozenset({CHECKIN})
CREATABLE_BY_SUPERADMIN: frozenset[str] = frozenset({ADMIN, CHECKIN, WEB_ADMIN})


# ------------------------------------------------------------------
#  Role predicates
# ------------------------------------------------------------------
def _roles(user: User | None) -> str:
    return getattr(user, "user_type", "") or ""


def is_superadmin(user: User | None) -> bool:
    return _roles(user) == SUPERADMIN


def is_admin(user: User | None) -> bool:
    return _roles(user) == ADMIN


def is_checkin(user: User | None) -> bool:
    return _roles(user) == CHECKIN


def is_operator(user: User | None) -> bool:
    return _roles(user) == OPERATOR


def is_web_admin(user: User | None) -> bool:
    """Web content editor. Can only manage site content (homepage, news, gallery)."""
    return _roles(user) == WEB_ADMIN


# Roles allowed to manage site content (web admin panel /admin/contenido).
CONTENT_MANAGEMENT_ROLES: frozenset[str] = frozenset({SUPERADMIN, ADMIN, WEB_ADMIN})


# ------------------------------------------------------------------
#  Capability helpers
# ------------------------------------------------------------------
def can_manage_backoffice(user: User | None) -> bool:
    """Access the admin dashboard, operators list, events CRUD."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_events(user: User | None) -> bool:
    """Create/edit/delete events, assign operators, generate planillas."""
    return _roles(user) in MANAGEMENT_ROLES


def can_approve_operators(user: User | None) -> bool:
    """Approve / reject pending operator registrations."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_operators(user: User | None) -> bool:
    """View full operator list + edit operator profiles."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_payroll(user: User | None) -> bool:
    """Generate payroll, reports, exports."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_whatsapp(user: User | None) -> bool:
    """Queue/send WhatsApp invitations & reminders."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_incidents(user: User | None) -> bool:
    """Novelties & bans (incidents)."""
    return _roles(user) in MANAGEMENT_ROLES


def can_manage_users(user: User | None) -> bool:
    """Full /admin/superadmin: create/edit/deactivate admin users.

    ONLY superadmin. Admins can still approve pending operators but
    cannot create/edit other admin or checkin accounts.
    """
    return _roles(user) == SUPERADMIN


def can_create_checkin(user: User | None) -> bool:
    """Create a new checkin user. Admin & superadmin."""
    return _roles(user) in MANAGEMENT_ROLES


def can_create_admin(user: User | None) -> bool:
    """Create a new admin user. ONLY superadmin."""
    return _roles(user) == SUPERADMIN


def can_checkin(user: User | None) -> bool:
    """Perform event check-in (staff & operators with staff assignment)."""
    return _roles(user) in ALL_STAFF


def can_manage_content(user: User | None) -> bool:
    """Manage site content (sections, services, news, gallery, contact inbox).

    Allowed for superadmin, admin and web_admin. Web admins can ONLY access
    this module (no operators, events, payroll, etc.).
    """
    return _roles(user) in CONTENT_MANAGEMENT_ROLES


def creatable_roles_for(user: User | None) -> list[str]:
    """Which user_types this caller is allowed to create."""
    if is_superadmin(user):
        return sorted(CREATABLE_BY_SUPERADMIN)
    if is_admin(user):
        return sorted(CREATABLE_BY_ADMIN)
    return []


def normalize_user_type(value: str | None, default: str = CHECKIN) -> str:
    """Sanitize a user_type value coming from the client.

    Unknown / legacy values (e.g. ``coordinator``) collapse to ``default``.
    """
    if value in ALL_ROLES:
        return value
    return default


def user_has_any_role(user: User | None, allowed: Iterable[str]) -> bool:
    return _roles(user) in set(allowed)
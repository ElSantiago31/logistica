"""add concurrency constraints (unique attendance + partial unique uniform)

Revision ID: add_concurrency_constraints
Revises: add_programmed_by
Create Date: 2026-06-25

Añade constraints a nivel de base de datos para prevenir duplicados bajo
concurrencia (TOCTOU race conditions):

1. attendance_log: UNIQUE(event_id, operator_id) — un operador no puede
   tener dos registros de check-in en el mismo evento.

2. event_assignments: partial unique indexes por evento para
   shirt_number, jacket_number, cap_number — cada número de indumentaria
   solo puede asignarse a un operador por evento.

Antes de crear los constraints, se ejecuta deduplicación de datos
existentes para que la migración no falle si ya hay duplicados.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'add_concurrency_constraints'
down_revision = 'add_programmed_by'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. Deduplicar attendance_log antes del constraint ---
    # Mantener el registro más antiguo (DISTINCT ON + ORDER BY created_at)
    # DISTINCT ON es idiomatico de PostgreSQL; (MIN no soporta UUID)
    op.execute("""
        DELETE FROM attendance_log
        WHERE id NOT IN (
            SELECT DISTINCT ON (event_id, operator_id) id
            FROM attendance_log
            ORDER BY event_id, operator_id, created_at ASC
        )
    """)

    # --- 2. Crear constraint único en attendance_log ---
    op.create_unique_constraint(
        'uq_attendance_event_operator',
        'attendance_log',
        ['event_id', 'operator_id'],
    )

    # --- 3. Deduplicar uniform en event_assignments ---
    # Resetear a NULL los duplicados, manteniendo solo el primero (DISTINCT ON)
    op.execute("""
        UPDATE event_assignments ea
        SET shirt_number = NULL
        WHERE shirt_number IS NOT NULL
          AND id NOT IN (
            SELECT DISTINCT ON (event_id, shirt_number) id
            FROM event_assignments
            WHERE shirt_number IS NOT NULL
            ORDER BY event_id, shirt_number, created_at ASC
          )
    """)
    op.execute("""
        UPDATE event_assignments ea
        SET jacket_number = NULL
        WHERE jacket_number IS NOT NULL
          AND id NOT IN (
            SELECT DISTINCT ON (event_id, jacket_number) id
            FROM event_assignments
            WHERE jacket_number IS NOT NULL
            ORDER BY event_id, jacket_number, created_at ASC
          )
    """)
    op.execute("""
        UPDATE event_assignments ea
        SET cap_number = NULL
        WHERE cap_number IS NOT NULL
          AND id NOT IN (
            SELECT DISTINCT ON (event_id, cap_number) id
            FROM event_assignments
            WHERE cap_number IS NOT NULL
            ORDER BY event_id, cap_number, created_at ASC
          )
    """)

    # --- 4. Crear partial unique indexes para uniform ---
    # CREATE UNIQUE INDEX con WHERE funciona en PostgreSQL y SQLite
    op.execute("""
        CREATE UNIQUE INDEX uq_assignment_shirt_event
        ON event_assignments (event_id, shirt_number)
        WHERE shirt_number IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_assignment_jacket_event
        ON event_assignments (event_id, jacket_number)
        WHERE jacket_number IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_assignment_cap_event
        ON event_assignments (event_id, cap_number)
        WHERE cap_number IS NOT NULL
    """)


def downgrade() -> None:
    # --- Eliminar partial unique indexes ---
    op.execute("DROP INDEX IF EXISTS uq_assignment_cap_event")
    op.execute("DROP INDEX IF EXISTS uq_assignment_jacket_event")
    op.execute("DROP INDEX IF EXISTS uq_assignment_shirt_event")

    # --- Eliminar constraint único de attendance_log ---
    op.drop_constraint(
        'uq_attendance_event_operator',
        'attendance_log',
        type_='unique',
    )
"""Jobs en background para la importación masiva de operadores desde Excel.

¿Por qué este módulo?
  La importación de archivos grandes (1000+ filas) tarda varios minutos:
  bcrypt cuesta ~350ms por operador nuevo y, aunque se paralelice, el
  procesamiento completo puede superar los timeouts de nginx (120s) y de
  Cloudflare (~100s). El resultado era que el loader desaparecía y no
  pasaba nada (conexión cortada a mitad del POST).

  Con este módulo el POST /import-operators responde 202 de inmediato con
  un job_id; el Excel se procesa en background y el frontend consulta el
  progreso con polling GET /api/events/import/status/{job_id}.

Alcance / limitaciones:
  - Registro EN MEMORIA: válido porque producción corre uvicorn con
    workers=1 (obligatorio para WebSockets). Si algún día se escala a
    múltiples workers, esto debe migrarse a Redis/DB.
  - Los jobs completados se conservan 1h (o hasta un máximo de 50) para
    que el frontend pueda consultar el resultado.
"""
import asyncio
import time
import uuid as uuid_module

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import AsyncSessionLocal
from app.schemas.events import ImportJobStatus
from app.services import operator_import as imp_svc

# Session factory por defecto (producción). En tests se re-configura con
# set_session_factory() apuntando a la BD de prueba (ver tests/conftest.py).
_session_factory: async_sessionmaker = AsyncSessionLocal

_MAX_JOBS = 50
_TTL_SECONDS = 3600.0


def set_session_factory(factory: async_sessionmaker) -> None:
    """Sobreescribe la factory de sesiones (usado por los tests)."""
    global _session_factory
    _session_factory = factory


def reset_session_factory() -> None:
    """Restaura la factory de producción (usado por los tests)."""
    global _session_factory
    _session_factory = AsyncSessionLocal


class _ImportJob:
    """Estado mutable de un job de importación (no se persiste)."""

    __slots__ = (
        "id", "event_id", "status", "stage", "processed", "total",
        "error", "summary", "created_at", "completed_at",
    )

    def __init__(self, event_id):
        self.id = str(uuid_module.uuid4())
        self.event_id = event_id
        self.status = "queued"          # queued | running | completed | failed
        self.stage: str | None = None   # hashing | processing
        self.processed = 0
        self.total = 0
        self.error: str | None = None
        self.summary = None
        self.created_at = time.time()
        self.completed_at: float | None = None


# job_id -> _ImportJob (acceso desde el event loop único; sin lock)
_jobs: dict[str, _ImportJob] = {}


def _cleanup_old_jobs() -> None:
    """Expulsa jobs terminados expirados (TTL) o excedentes (MAX_JOBS)."""
    now = time.time()
    # 1) TTL: terminados hace más de 1h
    expired = [
        jid for jid, j in _jobs.items()
        if j.completed_at is not None and now - j.completed_at > _TTL_SECONDS
    ]
    for jid in expired:
        del _jobs[jid]
    # 2) Tope de jobs retenidos: borra los terminados más viejos
    finished = sorted(
        ((j.completed_at, jid) for jid, j in _jobs.items() if j.completed_at),
    )
    overflow = len(_jobs) - _MAX_JOBS
    for _, jid in finished[:max(0, overflow)]:
        del _jobs[jid]


async def _run_job(job: _ImportJob, file_bytes: bytes) -> None:
    """Ejecuta la importación con su propia sesión de BD."""
    job.status = "running"
    try:

        def on_progress(processed: int, total: int, stage: str) -> None:
            job.processed = processed
            job.total = total
            job.stage = stage

        async with _session_factory() as db:
            summary = await imp_svc.import_operators_from_excel(
                db, file_bytes, job.event_id, progress_cb=on_progress,
            )
        job.status = "completed"
        job.summary = summary
        job.stage = None
    except Exception as exc:  # noqa: BLE001 — el job nunca debe romper el loop
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.completed_at = time.time()
        _cleanup_old_jobs()


def start_import_job(event_id, file_bytes: bytes) -> str:
    """Crea el job y lanza la tarea en background. Retorna el job_id."""
    job = _ImportJob(event_id)
    _jobs[job.id] = job
    # create_task queda adjunta al event loop actual (uvicorn, workers=1)
    asyncio.create_task(_run_job(job, file_bytes))
    return job.id


def get_job_status(job_id: str) -> ImportJobStatus | None:
    """Snapshot del estado del job como schema serializable."""
    job = _jobs.get(job_id)
    if job is None:
        return None
    return ImportJobStatus(
        job_id=job.id,
        event_id=job.event_id,
        status=job.status,
        stage=job.stage,
        processed=job.processed,
        total=job.total,
        error=job.error,
        summary=job.summary,
    )
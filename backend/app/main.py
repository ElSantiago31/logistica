import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.dependencies.rate_limit import limiter
from app.routers import auth as auth_router
from app.routers import operators as operators_router
from app.routers import catalogs as catalogs_router
from app.routers import events as events_router
from app.routers import whatsapp as whatsapp_router
from app.routers import sync as sync_router
from app.routers import payroll as payroll_router
from app.routers import reports as reports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle events."""
    os.makedirs(settings.PHOTOS_DIR, exist_ok=True)
    os.makedirs(settings.PHOTOS_THUMBNAIL_DIR, exist_ok=True)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Rate limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register routers
app.include_router(auth_router.router)
app.include_router(operators_router.router)
app.include_router(catalogs_router.router)
app.include_router(events_router.router)
app.include_router(whatsapp_router.router)
app.include_router(sync_router.router)
app.include_router(payroll_router.router)
app.include_router(reports_router.router)

# Templates Jinja2
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Frontend static dirs
FRONTEND_PUBLIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "public")
FRONTEND_JS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "js")
os.makedirs(FRONTEND_PUBLIC, exist_ok=True)
os.makedirs(FRONTEND_JS, exist_ok=True)

# Mount static files for photos
app.mount("/static/photos", StaticFiles(directory=settings.PHOTOS_DIR), name="photos")
app.mount("/static/frontend", StaticFiles(directory=FRONTEND_PUBLIC), name="frontend_static")
app.mount("/static/js", StaticFiles(directory=FRONTEND_JS), name="frontend_js")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(self)"
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# --- HTML Routes ---

@app.get("/test-ui", response_class=HTMLResponse)
async def test_ui(request: Request):
    return templates.TemplateResponse("test.html", {"request": request})


@app.get("/enrolamiento", response_class=HTMLResponse)
async def enrollment_page(request: Request):
    return templates.TemplateResponse("landing/index.html", {"request": request})


@app.get("/politica-tratamiento-datos", response_class=HTMLResponse)
async def data_treatment_policy(request: Request):
    """Pública: Política de tratamiento de datos personales (Ley 1581 de 2012)."""
    return templates.TemplateResponse("landing/politica_datos.html", {"request": request})


@app.get("/enrolamiento/success", response_class=HTMLResponse)
async def enrollment_success(request: Request):
    return templates.TemplateResponse("landing/success.html", {"request": request})


@app.get("/enrolamiento/login", response_class=HTMLResponse)
async def operator_login(request: Request):
    return templates.TemplateResponse("landing/operator_login.html", {"request": request})


@app.get("/enrolamiento/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("landing/forgot_password.html", {"request": request})


@app.get("/enrolamiento/perfil", response_class=HTMLResponse)
async def operator_profile(request: Request):
    return templates.TemplateResponse("landing/operator_profile.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin/index.html", {"request": request})


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@app.get("/admin/operators", response_class=HTMLResponse)
async def admin_operators(request: Request):
    return templates.TemplateResponse("admin/operators.html", {"request": request})


@app.get("/admin/operator/{op_id}", response_class=HTMLResponse)
async def admin_operator_detail(request: Request, op_id: str):
    return templates.TemplateResponse("admin/operator_detail.html", {"request": request})


@app.get("/admin/superadmin", response_class=HTMLResponse)
async def admin_superadmin(request: Request):
    return templates.TemplateResponse("admin/superadmin.html", {"request": request})


@app.get("/admin/events", response_class=HTMLResponse)
async def admin_events(request: Request):
    return templates.TemplateResponse("admin/events.html", {"request": request})


@app.get("/admin/events/create", response_class=HTMLResponse)
async def admin_event_create(request: Request):
    return templates.TemplateResponse("admin/event_create.html", {"request": request})


@app.get("/admin/events/{event_id}", response_class=HTMLResponse)
async def admin_event_detail(request: Request, event_id: str):
    return templates.TemplateResponse("admin/event_detail.html", {"request": request, "event_id": event_id})


@app.get("/admin/events/{event_id}/edit", response_class=HTMLResponse)
async def admin_event_edit(request: Request, event_id: str):
    return templates.TemplateResponse("admin/event_edit.html", {"request": request, "event_id": event_id})


@app.get("/admin/events/{event_id}/checkin", response_class=HTMLResponse)
async def admin_checkin(request: Request, event_id: str):
    return templates.TemplateResponse("admin/checkin.html", {"request": request, "event_id": event_id})


@app.get("/admin/events/{event_id}/payroll", response_class=HTMLResponse)
async def admin_payroll(request: Request, event_id: str):
    return templates.TemplateResponse("admin/payroll.html", {"request": request, "event_id": event_id})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root — Página de próximamente (la landing principal se construirá después)."""
    return templates.TemplateResponse("landing/coming_soon.html", {"request": request})


@app.get("/colaboradores", response_class=HTMLResponse)
async def collaborators_landing(request: Request):
    """Sub-landing de colaboradores/operadores."""
    return templates.TemplateResponse("landing/home.html", {"request": request})

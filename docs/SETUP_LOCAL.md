# 🚀 Guía de Instalación Local — A&C Logística y Producción de Eventos

Esta guía explica cómo levantar el proyecto en una máquina de desarrollo nueva (Windows, macOS o Linux).

---

## 📋 Requisitos previos

Antes de empezar, instala estas herramientas:

| Herramienta | Versión mínima | Para qué sirve |
|---|---|---|
| **Python** | 3.11+ | Backend (FastAPI) |
| **Docker Desktop** | reciente | Levantar PostgreSQL + pgAdmin |
| **Git** | reciente | Clonar el repositorio |
| **Editor** | VS Code recomendado | Editar código |

> En Windows, asegúrate de marcar "Add Python to PATH" durante la instalación de Python.

---

## 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/ElSantiago31/logistica.git
cd logistica
```

---

## 2️⃣ Levantar la base de datos (Docker)

El proyecto usa PostgreSQL 16. El archivo `docker-compose.yml` (modo desarrollo) levanta **solo** Postgres + pgAdmin, sin el backend (el backend lo correrás tú a mano para tener hot-reload).

```bash
docker compose up -d
```

Esto levantará:
- **PostgreSQL** → expuesto en `localhost:5433` (mapeado del 5432 interno)
- **pgAdmin** → en `http://localhost:5050` (gestor visual de la BD)

Verifica que estén corriendo:
```bash
docker compose ps
```

---

## 3️⃣ Crear los archivos `.env`

⚠️ **Importante:** Los archivos `.env` **NO vienen en el repositorio** (están en `.gitignore`). Debes crearlos a mano. Hay **dos** archivos que crear:

### 3.1. `.env` en la raíz del proyecto

```bash
# En la raíz del proyecto (donde está docker-compose.yml)
cp .env.example .env        # macOS/Linux
copy .env.example .env      # Windows cmd
```

Luego edítalo y ajusta estos valores clave (el puerto **debe ser 5433** para coincidir con el mapeo de Docker):

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=logistica
POSTGRES_USER=logistica
POSTGRES_PASSWORD=logistica_dev_2024
DATABASE_URL=postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5433/logistica
TEST_DATABASE_URL=postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5433/logistica_test
```

Para el `JWT_SECRET_KEY`, genera uno aleatorio:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Los campos de Zenvia (WhatsApp) déjalos vacíos por ahora — solo se necesitan si vas a probar los envíos de WhatsApp.

### 3.2. `backend/.env` (copia idéntica)

El backend lee su configuración desde `backend/.env` (porque ahí es donde ejecutas uvicorn). La forma más simple es copiar el mismo contenido:

```bash
cp .env backend/.env        # macOS/Linux
copy .env backend\.env      # Windows cmd
```

---

## 4️⃣ Crear entorno virtual de Python e instalar dependencias

```bash
cd backend

# Crear entorno virtual
python -m venv venv

# Activarlo
# Windows (cmd):
venv\Scripts\activate
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

Verifica que se instaló FastAPI:
```bash
python -c "import fastapi; print(fastapi.__version__)"
```

---

## 5️⃣ Ejecutar las migraciones de base de datos

Las migraciones crean todas las tablas (users, operators, events, etc.):

```bash
# Asegúrate de estar en backend/ con el venv activado
alembic upgrade head
```

✅ Debes ver un flujo de migraciones aplicadas sin errores. La última migración aplicada debería ser `add_operator_gender` (head).

Verifica:
```bash
alembic current
# Salida esperada: add_operator_gender (head)
```

---

## 6️⃣ Cargar datos iniciales (seed)

El seed crea el usuario administrador, roles, ARLs y datos base:

```bash
python -m scripts.seed
```

Esto creará:
- Usuario admin: `admin@logistica.com` / `Admin123!`
- Roles (coordinador_general, coordinador_grupos, etc.)
- ARLs y EPSs base

---

## 7️⃣ Levantar el servidor backend

Tienes dos opciones:

**Opción A — Script helper (recomendado):**
```bash
python run_server.py
```

**Opción B — Uvicorn directo:**
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

El servidor quedará corriendo en **http://localhost:8000**

---

## 8️⃣ Verificar que todo funciona

| URL | Qué deberías ver |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/docs | Documentación Swagger de la API |
| http://localhost:8000/ | Landing page de registro de operadores |
| http://localhost:8000/admin/login | Login del panel admin |
| http://localhost:5050 | pgAdmin (con las credenciales del `.env`) |

Login de admin:
- Email: `admin@logistica.com`
- Password: `Admin123!`

---

## 🔄 Flujo de trabajo diario

Una vez configurado, para volver a trabajar al día siguiente solo necesitas:

```bash
# 1. Levantar la BD (si la apagaste)
docker compose up -d

# 2. Activar el venv y correr el server
cd backend
venv\Scripts\activate          # Windows
python run_server.py
```

No necesitas repetir migraciones ni seed (la BD persiste en el volumen de Docker).

---

## 🧪 Ejecutar los tests

```bash
cd backend
venv\Scripts\activate
pytest -v
```

> Los tests usan una base de datos separada (`logistica_test`), que se crea automáticamente.

---

## 🛠️ Solución de problemas comunes

### ❌ "No module named 'app'"
Estás ejecutando el comando desde el directorio equivocado. Debes estar dentro de `backend/` y con el `venv` activado.

### ❌ "Could not connect to PostgreSQL"
- Verifica que Docker esté corriendo: `docker compose ps`
- Confirma que el puerto en tu `.env` sea **5433** (no 5432). Docker mapea `5433:5432`.

### ❌ "alembic upgrade head" falla con "target database is not up to date"
Puede que tengas una BD vieja. Para empezar limpio:
```bash
docker compose down -v   # ⚠️ Borra los datos de la BD
docker compose up -d
alembic upgrade head
python -m scripts.seed
```

### ❌ El puerto 8000 ya está en uso
Cambia el puerto en `run_server.py` o ejecuta:
```bash
uvicorn app.main:app --port 8001 --reload
```

### ❌ Permisos PowerShell al activar venv
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## 📁 Estructura del proyecto (resumen)

```
logistica/
├── backend/
│   ├── app/                    # Código principal (modelos, routers, servicios, plantillas)
│   ├── alembic/                # Migraciones de base de datos
│   ├── scripts/                # Seeds y utilidades
│   ├── tests/                  # Tests automatizados
│   ├── requirements.txt        # Dependencias Python
│   ├── run_server.py           # Script para levantar uvicorn
│   └── .env                    # ← LO CREAS TÚ (copia de .env.example)
├── .env                        # ← LO CREAS TÚ (copia de .env.example)
├── .env.example                # Plantilla de variables de entorno
├── docker-compose.yml          # Postgres + pgAdmin (desarrollo)
└── docker-compose.prod.yml     # Despliegue completo en VPS
```

---

## 📞 Credenciales por defecto

| Servicio | Usuario | Contraseña |
|---|---|---|
| Admin web | `admin@logistica.com` | `Admin123!` |
| PostgreSQL | `logistica` | *(la que pongas en .env)* |
| pgAdmin | `admin@logistica.com` | *(la que pongas en .env)* |

> 🔒 **Cambia la contraseña del admin** después del primer login en producción.
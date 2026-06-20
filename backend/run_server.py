"""Launch uvicorn server with correct working directory.

Este script fuerza el directorio de trabajo al directorio donde reside el
propio archivo (backend/), sin importar desde dónde se invoque. Así funciona
para cualquier desarrollador sin rutas absolutas hardcodeadas.
"""
import os
import sys

# Cambiar al directorio que contiene este archivo (backend/)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
sys.path.insert(0, os.getcwd())

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

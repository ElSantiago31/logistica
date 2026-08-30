#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inserta enlace a /admin/referrals en superadmin.html (run una vez)."""
import io, sys

PATH = r"app\templates\admin\superadmin.html"

with io.open(PATH, "r", encoding="utf-8") as f:
    c = f.read()

anchor = '<div id="adminsTable"'
if "/admin/referrals" in c:
    print("SKIP: ya contiene el enlace")
    sys.exit(0)

idx = c.find(anchor)
if idx == -1:
    print("ERROR: anchor no encontrado")
    sys.exit(1)

# Insertar el bloque de acceso directo ANTES del div adminsTable
block = (
    "        <!-- Acceso directo: gestión de referidos -->\n"
    "        <div class=\"bg-blue-50 border border-blue-200 rounded-xl px-6 py-4 mb-6 text-sm text-blue-800\">\n"
    "            🤝 Los códigos de referido y sus métricas se gestionan en\n"
    "            <a href=\"/admin/referrals\" class=\"font-semibold underline hover:text-blue-900\">Referidos</a>.\n"
    "        </div>\n\n"
)

# Alinear con la indentación real del anchor (busca inicio de línea)
line_start = c.rfind("\n", 0, idx) + 1
indent = c[line_start:idx]
block = block.replace("        ", indent, 10)

c = c[:line_start] + block + c[line_start:]

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(c)

print("OK: enlace a referidos insertado")
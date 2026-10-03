# -*- coding: utf-8 -*-
"""Parche home.html:
1. Repara el final truncado del template (falta debounce/marquee/</script>/{% endblock %})
   recuperandolo desde git HEAD.
2. Cambia la direccion a "CR 59D #131-72, Bogota D.C" en las 3 apariciones
   (JSON-LD streetAddress, seccion contacto, footer).
Idempotente.
"""
import io
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # backend/
F = BASE / "app" / "templates" / "landing" / "home.html"
MARKER = "// ===== INFINITE MARQUEE DE ESCENARIOS: duplicaci\u00f3n autom\u00e1tica ====="

REPLACEMENTS = [
    ('"streetAddress": "Cra. 59d #131a-1 131a-99 a",',
     '"streetAddress": "CR 59D #131-72",'),
    ('<span>Cra. 59d #131a-1 131a-99 a, Bogot\u00e1, Colombia</span>',
     '<span>CR 59D #131-72, Bogot\u00e1 D.C</span>'),
    ('<p>Cra. 59d #131a-1 131a-99 a, Bogot\u00e1, Colombia</p>',
     '<p>CR 59D #131-72, Bogot\u00e1 D.C</p>'),
]


def main():
    src = io.open(F, "r", encoding="utf-8").read()

    # --- 1. Reparar final truncado ---
    if "{% endblock %}" not in src:
        git = subprocess.run(
            ["git", "show", "HEAD:backend/app/templates/landing/home.html"],
            capture_output=True, cwd=str(BASE.parent),
        ).stdout.decode("utf-8", errors="replace")
        if MARKER not in git:
            print("[home] ERROR: marker no encontrado en git HEAD")
            sys.exit(1)
        if MARKER not in src:
            print("[home] ERROR: marker no encontrado en archivo actual")
            sys.exit(1)
        tail = git[git.index(MARKER):]
        src = src[:src.index(MARKER)] + tail
        print("[home] ok: final truncado reparado desde git HEAD")
    else:
        print("[home] ya aplicado: {% endblock %} presente")

    # --- 2. Direccion ---
    for old, new in REPLACEMENTS:
        if new in src:
            print("[home] ya aplicado:", old[:40])
            continue
        if old not in src:
            print("[home] ERROR: no se encontro:", old[:60])
            sys.exit(1)
        src = src.replace(old, new, 1)
        print("[home] ok:", old[:40], "->", new[:40])

    io.open(F, "w", encoding="utf-8", newline="").write(src)

    # --- 3. Verificaciones ---
    final = io.open(F, "r", encoding="utf-8").read()
    checks = {
        "{% endblock %} presente": "{% endblock %}" in final,
        "direccion vieja eliminada": "131a-1" not in final,
        "nueva direccion x3": final.count("CR 59D #131-72") == 3,
        "script cerrado": final.rstrip().endswith("{% endblock %}"),
    }
    for name, ok in checks.items():
        print(("[OK] " if ok else "[FAIL] ") + name)
    if not all(checks.values()):
        sys.exit(1)
    print("PATCH HOME COMPLETO")


if __name__ == "__main__":
    main()
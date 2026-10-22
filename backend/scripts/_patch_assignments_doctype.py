# -*- coding: utf-8 -*-
"""get_assignments: agrega operator_document_type al payload de asignaciones.

Idempotente: si ya está aplicado, no hace nada. El template
event_detail.html usa operator_document_type + operator_document_number
para mostrar el documento del operador asignado.
"""
import io

P = r"app\services\events.py"

OLD = '''            "operator_document_number": user.document_number if user else None,
            "shirt_number": a.shirt_number,'''
NEW = '''            "operator_document_number": user.document_number if user else None,
            "operator_document_type": user.document_type if user else None,
            "shirt_number": a.shirt_number,'''


def main():
    s = io.open(P, encoding="utf-8").read()
    if "operator_document_type" in s:
        print("Ya parcheado — sin cambios.")
        return
    n = s.count(OLD)
    assert n == 1, "bloque encontrado %d veces" % n
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW))
    # Verificar en disco
    s2 = io.open(P, encoding="utf-8").read()
    assert "operator_document_type" in s2, "verificacion post-escritura fallo"
    print("PATCH OK")


if __name__ == "__main__":
    main()
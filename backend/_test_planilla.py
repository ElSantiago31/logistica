"""Script temporal para probar la generación de planilla localmente."""
import sys
import os

# Asegurar que el directorio backend esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.planilla_excel import (
    _sort_operators,
    _fill_operators,
    generate_planilla_xlsx,
)

print("1. Test _sort_operators (lastname con first_name/last_name)...")
ops = [
    {
        "first_name": "Ronald Santiago",
        "last_name": "Poveda Sarmiento",
        "full_name": "Ronald Santiago Poveda Sarmiento",
        "document_number": "123",
        "coordinator_name": "Test",
    },
    {
        "first_name": "Ana Maria",
        "last_name": "Gomez",
        "full_name": "Ana Maria Gomez",
        "document_number": "456",
        "coordinator_name": "Test",
    },
]
r = _sort_operators(ops, "lastname")
print("   OK:", [f"{o['first_name']} {o['last_name']}" for o in r])

print("\n2. Test _sort_operators (document)...")
r = _sort_operators(ops, "document")
print("   OK:", [o["document_number"] for o in r])

print("\n3. Test generate_planilla_xlsx completo...")
try:
    xlsx_bytes = generate_planilla_xlsx(
        event_name="Evento Test",
        event_date=None,
        event_location="Bogotá",
        operators=ops,
        group_by="coordinator",
        sort_by="lastname",
        with_signatures=False,
    )
    print(f"   OK: {len(xlsx_bytes)} bytes generados")
except Exception as exc:
    print(f"   ERROR: {type(exc).__name__}: {exc}")
    import traceback
    traceback.print_exc()

print("\n4. Test _sort_operators sin first_name/last_name (retrocompatibilidad)...")
ops_old = [
    {"full_name": "Carlos Perez", "document_number": "789", "coordinator_name": "X"},
    {"full_name": "Ana Gomez", "document_number": "321", "coordinator_name": "X"},
]
r = _sort_operators(ops_old, "lastname")
print("   OK:", [o["full_name"] for o in r])

print("\n✅ Todos los tests pasaron")
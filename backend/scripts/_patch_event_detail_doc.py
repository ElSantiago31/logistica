# -*- coding: utf-8 -*-
"""En /admin/events/{id}: muestra tipo + número de documento en lugar del
teléfono en la lista de operadores asignados (tabla + cards móvil).

El backend (get_assignments) ya envía operator_document_number y ahora
también operator_document_type. El selector de operadores disponibles
(línea con o.phone) NO se toca: ahí el teléfono es útil para contactar.
"""
import io

P = r"app\templates\admin\event_detail.html"

# Expresión compacta: "CC 123456789", "123456789" (sin tipo) o "-"
DOC_EXPR = "${a.operator_document_number?((a.operator_document_type||'')+' '+a.operator_document_number).trim():'-'}"

OLD_TD = """<td class="px-4 py-2 text-sm">${a.operator_phone||'-'}</td>"""
NEW_TD = """<td class="px-4 py-2 text-sm">""" + DOC_EXPR + """</td>"""

OLD_MOBILE = """<div class="text-xs text-gray-500">${a.operator_phone||'-'}</div>"""
NEW_MOBILE = """<div class="text-xs text-gray-500">""" + DOC_EXPR + """</div>"""

OLD_TH = ">Teléfono</th>"
NEW_TH = ">Documento</th>"


def main():
    s = io.open(P, encoding="utf-8").read()

    if "operator_document_type" in s:
        print("Ya parcheado — sin cambios.")
        return

    for old, name in ((OLD_TD, "TD"), (OLD_MOBILE, "MOBILE"), (OLD_TH, "TH")):
        n = s.count(old)
        assert n == 1, "%s encontrada %d veces" % (name, n)

    s = s.replace(OLD_TD, NEW_TD)
    s = s.replace(OLD_MOBILE, NEW_MOBILE)
    s = s.replace(OLD_TH, NEW_TH)

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("PATCH OK")


if __name__ == "__main__":
    main()
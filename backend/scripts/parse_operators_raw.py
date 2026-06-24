#!/usr/bin/env python
"""Convierte texto crudo de operadores (formato formulario) a JSON para import_operators.py.

Uso:
    python parse_operators_raw.py input.txt output.json
"""
import json
import re
import sys
from pathlib import Path

# Forzar UTF-8 en stdout/stderr (Windows cp1252 falla con emojis/acentos)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_phone(raw: str) -> str:
    """Extrae solo digitos de un string de telefono (ignora letras, espacios, guiones, +57)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    # Quitar prefijo colombiano 57 si esta al inicio y el numero es largo
    if len(digits) > 10 and digits.startswith("57"):
        digits = digits[2:]
    return digits


def split_contact(raw: str):
    """Intenta separar nombre y telefono de un contacto de emergencia."""
    raw = raw.strip()
    if not raw:
        return "", ""
    # Buscar un numero de telefono (7+ digitos consecutivos)
    match = re.search(r"(\d[\d\s\-\(\)]{6,}\d)", raw)
    phone = ""
    name = raw
    if match:
        phone = parse_phone(match.group(1))
        name = raw[: match.start()].strip(" -—:")
    # Si no hay match de numero, verificar si todo son digitos
    if not phone:
        digits_only = parse_phone(raw)
        if digits_only and len(digits_only) >= 6:
            return "", digits_only
    # Limpiar nombre
    name = name.strip(" -—:,.")
    if not name:
        name = ""
    return name, phone


def normalize_date(raw: str) -> str:
    """Normaliza fecha a DD/MM/YYYY."""
    raw = raw.strip()
    # Ya esta en formato DD/MM/YYYY
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", raw):
        return raw
    # Formato con un solo digito de dia/mes
    parts = raw.split("/")
    if len(parts) == 3:
        d, m, y = parts
        return f"{int(d):02d}/{int(m):02d}/{y.strip()}"
    return raw


def parse_block(block: str) -> dict | None:
    """Parsea un bloque de texto en un dict de operador."""
    lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
    if not lines:
        return None

    data = {
        "full_name": "",
        "document_number": "",
        "birth_date": "",
        "role_name": "",
        "gender": "",
        "eps_name": "",
        "address": "",
        "phone": "",
        "emergency_contact_name": "",
        "emergency_contact_phone": "",
        "coordinator": "",
    }

    # La primera linea sin etiqueta es el nombre
    full_block = "\n".join(lines)
    name = lines[0]
    # Si la primera linea tiene etiqueta, no es nombre
    if ":" in name and any(k in name.upper() for k in ["TIPO DE DOCUMENTO", "NUMERO CEDULA"]):
        return None
    data["full_name"] = re.sub(r"\s+", " ", name).strip()

    for line in lines[1:]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        value = value.strip()

        if "TIPO DE DOCUMENTO" in key:
            pass  # No lo usamos por ahora
        elif "NUMERO CEDULA" in key:
            # Limpiar puntos de miles
            data["document_number"] = value.replace(".", "").replace(" ", "").strip()
        elif "FECHA DE NACIMIENTO" in key:
            data["birth_date"] = normalize_date(value)
        elif "ROL ASIGNADO" in key:
            data["role_name"] = value
        elif "GENERO" in key:
            g = value.lower()
            if "fem" in g:
                data["gender"] = "Femenino"
            elif "masc" in g:
                data["gender"] = "Masculino"
            else:
                data["gender"] = value
        elif "EPS" in key and "DIRECCION" not in key:
            data["eps_name"] = value
        elif "DIRECCION DE VIVIENDA" in key:
            data["address"] = value
        elif "NUMERO DE CELULAR" in key:
            data["phone"] = parse_phone(value)
        elif "CONTACTO EN CASO DE EMERGENCIA" in key:
            cname, cphone = split_contact(value)
            data["emergency_contact_name"] = cname
            data["emergency_contact_phone"] = cphone
        elif "COORDINADOR" in key:
            data["coordinator"] = value

    # Validar que tenga cedula
    if not data["document_number"]:
        return None

    return data


def main():
    if len(sys.argv) < 3:
        print("Uso: python parse_operators_raw.py input.txt output.json")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    text = input_path.read_text(encoding="utf-8")

    # Separar por lineas de guiones
    blocks = re.split(r"-{5,}", text)

    operators = []
    seen_cedulas = set()
    duplicates = 0
    skipped = 0

    for block in blocks:
        op = parse_block(block)
        if op is None:
            skipped += 1
            continue
        if op["document_number"] in seen_cedulas:
            duplicates += 1
            continue
        seen_cedulas.add(op["document_number"])
        operators.append(op)

    output_path.write_text(
        json.dumps(operators, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"✅ {len(operators)} operadores unicos parseados")
    print(f"   {duplicates} duplicados saltados")
    print(f"   {skipped} bloques invalidos saltados")
    print(f"📁 Output: {output_path}")


if __name__ == "__main__":
    main()
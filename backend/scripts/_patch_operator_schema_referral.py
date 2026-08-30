#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anade referral_code a OperatorRegisterRequest en schemas/auth.py."""
import io

PATH = "app/schemas/auth.py"
c = io.open(PATH, encoding="utf-8").read()

if "experience_roles" in c and c.count("referral_code") < 2:
    lines = c.split("\n")
    for i, l in enumerate(lines):
        if "experience_roles" in l:
            indent = l[: len(l) - len(l.lstrip())]
            ins = [
                indent + "referral_code: Optional[str] = Field(",
                indent + "    default=None, max_length=30,",
                indent + '    description="Codigo de referido opcional, ej: AC-SANTIAGO-8F3K",',
                indent + ")",
            ]
            lines[i + 1:i + 1] = ins
            break
    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
    print("OK: referral_code anadido")
else:
    print("SKIP: ya presente o anchor no encontrado")

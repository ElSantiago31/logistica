# -*- coding: utf-8 -*-
"""Parche temporal: reemplaza _login por tokens JWT directos en test_operator_approvals.py."""
import io

PATH = "test_operator_approvals.py"

with io.open(PATH, encoding="utf-8") as f:
    s = f.read()

# 1) import
old_import = "from app.services.auth import hash_password"
new_import = "from app.services.auth import create_access_token, hash_password"

# 2) _login -> _token_for
old_login = '''async def _login(client, doc):
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "password",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]'''
new_login = '''def _token_for(user) -> str:
    """Token JWT directo (evita rate limit de /api/auth/login: 20/min)."""
    return create_access_token(
        user_id=user.id, email=user.email, user_type=user.user_type,
    )["token"]'''

# 3) fixture tokens
old_tokens = '''        "tokens": {
            "superadmin": await _login(client, "91001"),
            "admin": await _login(client, "91002"),
            "checkin": await _login(client, "91003"),
            "operator": await _login(client, "91004"),
        },'''
new_tokens = '''        # Tokens JWT directos: 4 logins x 6 tests excedian el rate limit
        "tokens": {
            "superadmin": _token_for(superadmin),
            "admin": _token_for(admin),
            "checkin": _token_for(checkin),
            "operator": _token_for(operator_ok),
        },'''

assert old_import in s, "import no encontrado"
assert old_login in s, "_login no encontrado"
assert old_tokens in s, "bloque tokens no encontrado"

s = s.replace(old_import, new_import)
s = s.replace(old_login, new_login)
s = s.replace(old_tokens, new_tokens)

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(s)

print("OK - parche aplicado")
print("_login restante:", s.count("_login("))
print("_token_for:", s.count("_token_for("))
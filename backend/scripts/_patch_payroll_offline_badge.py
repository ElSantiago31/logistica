"""Parche one-off: en payroll.html el badge '📴 Offline' aparecía SIEMPRE.

Dos causas:
1) CSS: .status-pill { display:inline-block } en <style> inline (cargado tras
   tailwind.css) pisa .hidden { display:none } de Tailwind -> badges con clase
   'hidden' (offline-badge y viewers-badge) se mostraban igual.
2) JS: nadie alternaba el offline-badge (solo online-badge vía WS).

Fix:
- Regla .status-pill.hidden { display:none } para que Tailwind gane.
- _updateNetBadge(): offline-badge visible solo cuando navigator.onLine sea
  false, con listeners online/offline y estado inicial.
"""
import io

PATH = r"backend/app/templates/admin/payroll.html"

REPLACEMENTS = [
    (
        """    .status-pill {
        font-size: 0.65rem; padding: 2px 10px; border-radius: 999px;
        font-weight: 600; display: inline-block;
    }""",
        """    .status-pill {
        font-size: 0.65rem; padding: 2px 10px; border-radius: 999px;
        font-weight: 600; display: inline-block;
    }
    /* Fix: .hidden (Tailwind) debe ganar sobre .status-pill aunque cargue antes */
    .status-pill.hidden { display: none; }""",
    ),
    (
        """    _wsClient.connect();
    window.addEventListener('beforeunload', () => { if (_wsClient) _wsClient.disconnect(); });
}""",
        """    _wsClient.connect();
    window.addEventListener('beforeunload', () => { if (_wsClient) _wsClient.disconnect(); });
}

// Badge de red real (📴 Offline): visible solo cuando navigator.onLine === false.
// Antes quedaba siempre visible: .status-pill pisaba .hidden de Tailwind y
// nadie alternaba la clase.
function _updateNetBadge() {
    const off = document.getElementById('offline-badge');
    if (off) off.classList.toggle('hidden', navigator.onLine);
}
window.addEventListener('online', _updateNetBadge);
window.addEventListener('offline', _updateNetBadge);
_updateNetBadge();""",
    ),
]


def main():
    s = io.open(PATH, encoding="utf-8").read()
    if ".status-pill.hidden" in s and "_updateNetBadge" in s:
        print("YA APLICADO")
        return
    for old, new in REPLACEMENTS:
        if old not in s:
            raise SystemExit("ERROR: bloque SEARCH no encontrado:\n" + old[:120])
        s = s.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    t = io.open(PATH, encoding="utf-8").read()
    ok = ".status-pill.hidden" in t and "_updateNetBadge" in t
    print("APLICADO" if ok else "FALLO VERIFICACION")


if __name__ == "__main__":
    main()
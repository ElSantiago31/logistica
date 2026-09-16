# -*- coding: utf-8 -*-
"""
Parche: alerta de progreso de check-in ROJA y solo al 90% del cupo.

Feedback del usuario:
  1) El banner debe marcar en ROJO (antes: ámbar 90-94% / naranja 95-99%).
  2) El mensaje debe aparecer SOLO cuando el check-in alcanza el 90% del
     cupo (se elimina la lógica de "zona del 90%" que anticipaba la alerta
     cuando faltaba <=10% aunque el porcentaje fuera <90%).

Solo toca backend/app/templates/admin/checkin.html (banner, CSS y JS inline).
Crea un respaldo .bak antes de escribir. Idempotente: si ya está aplicado,
no hace nada (exit 0).
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.normpath(os.path.join(HERE, "..", "app", "templates", "admin", "checkin.html"))

# (buscar, reemplazar)
REPLACEMENTS = [
    # --- CSS: variantes ámbar/naranja fuera; rojo 90-99% + verde completo ---
    (
        "    /* Alerta persistente de progreso de check-in (>= 90% del personal) */\n"
        "    .progress-alert { position:sticky; top:8px; z-index:30; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 14px; border-radius:12px; color:#fff; box-shadow:0 6px 18px rgba(0,0,0,.25); margin-bottom:12px; font-size:.95rem; }\n"
        "    .progress-alert.pa-warn { background:#f59e0b; animation:pa-pulse 1.6s ease-in-out infinite; }\n"
        "    .progress-alert.pa-near { background:#ea580c; animation:pa-pulse 1.2s ease-in-out infinite; }\n"
        "    .progress-alert.pa-complete { background:#22c55e; }\n",
        "    /* Alerta persistente de progreso de check-in (solo al 90% del cupo) */\n"
        "    .progress-alert { position:sticky; top:8px; z-index:30; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 14px; border-radius:12px; color:#fff; box-shadow:0 6px 18px rgba(0,0,0,.25); margin-bottom:12px; font-size:.95rem; }\n"
        "    /* 90-99% del cupo -> ROJO (aparece solo al alcanzar el 90%) */\n"
        "    .progress-alert.pa-danger { background:#dc2626; animation:pa-pulse 1.4s ease-in-out infinite; }\n"
        "    .progress-alert.pa-complete { background:#22c55e; }\n",
    ),
    # --- Comentario HTML del banner ---
    (
        "    <!-- Alerta persistente de check-in: 90% del personal REQUERIDO (no se puede cerrar) -->\n",
        "    <!-- Alerta persistente de check-in: ROJA al 90% del cupo (no se puede cerrar) -->\n",
    ),
    # --- Comentario del bloque JS ---
    (
        "// Se activa al entrar en la \"zona del 90%\" del PERSONAL REQUERIDO\n"
        "// (staff_needs / quantity_needed, no los asignados) y permanece visible\n",
        "// Se activa SOLO al alcanzar el 90% del cupo del PERSONAL REQUERIDO\n"
        "// (staff_needs / quantity_needed, no los asignados) y permanece visible\n",
    ),
    # --- Estado de nivel ---
    (
        "let _alertLastLevel = null;     // 'below' | 'warn' | 'near' | 'complete' (transiciones)\n",
        "let _alertLastLevel = null;     // 'below' | 'danger' | 'complete' (transiciones)\n",
    ),
    # --- Lógica de nivel: fuera la "zona del 90%", solo pct >= 0.9 en ROJO ---
    (
        "    // \"Zona del 90%\": el último 10% del personal (mínimo 1 persona). Así la\n"
        "    // alerta aparece ANTES de completar aunque el total no dé un 90% exacto\n"
        "    // (p. ej. con 5 confirmados aparece al 4/5, cuando solo falta 1;\n"
        "    // antes saltaba directo de 80% a 100% y nunca se veía la alerta).\n"
        "    const missing = total - checked;\n"
        "    const zone = Math.max(1, Math.round(total * 0.1));\n"
        "    const inZone = checked > 0 && (pct >= CHECKIN_ALERT_THRESHOLD || missing <= zone);\n"
        "\n"
        "    let level = 'below';\n"
        "    if (total > 0 && checked >= total) level = 'complete';\n"
        "    else if (inZone) level = (pct >= 0.95 || missing === 1) ? 'near' : 'warn';\n",
        "    // La alerta aparece SOLO al alcanzar el 90% del cupo (pct >= 0.9) y se\n"
        "    // marca en ROJO hasta completarlo. Si el cupo no permite un 90% exacto\n"
        "    // (p. ej. total 5 -> 4/5 = 80%), pasa directo de oculto a COMPLETO.\n"
        "    const missing = total - checked;\n"
        "\n"
        "    let level = 'below';\n"
        "    if (total > 0 && checked >= total) level = 'complete';\n"
        "    else if (total > 0 && pct >= CHECKIN_ALERT_THRESHOLD) level = 'danger';\n",
    ),
    # --- Clases CSS aplicadas al banner ---
    (
        "    // Color del banner (clases pa-warn / pa-near / pa-complete)\n"
        "    // La alerta NO se puede ocultar: permanece mientras se esté en la zona\n"
        "    // del 90% o completo (solo el sonido se puede silenciar).\n"
        "    banner.classList.remove('hidden');\n"
        "    banner.classList.remove('pa-warn', 'pa-near', 'pa-complete');\n"
        "    banner.classList.add('pa-' + level);\n",
        "    // Color del banner: ROJO (pa-danger) del 90% al 99%, verde al completar.\n"
        "    // La alerta NO se puede ocultar: permanece mientras pct >= 90% o hasta\n"
        "    // completar el cupo (solo el sonido se puede silenciar).\n"
        "    banner.classList.remove('hidden');\n"
        "    banner.classList.remove('pa-danger', 'pa-complete');\n"
        "    banner.classList.add('pa-' + level);\n",
    ),
    # --- Beep: kind 'warn' -> 'danger' ---
    (
        "        if (level === 'complete') _playProgressBeep('complete');\n"
        "        else _playProgressBeep('warn');\n",
        "        if (level === 'complete') _playProgressBeep('complete');\n"
        "        else _playProgressBeep('danger');\n",
    ),
    # --- Comentario de _playProgressBeep ---
    (
        "// Beep corto con WebAudio (sin assets). 'warn' = tono único al cruzar 90%;\n"
        "// 'complete' = doble tono ascendente al llegar al 100%.\n",
        "// Beep corto con WebAudio (sin assets). 'danger' = tono único al cruzar 90%;\n"
        "// 'complete' = doble tono ascendente al llegar al 100%.\n",
    ),
]


def main() -> int:
    if not os.path.isfile(TARGET):
        print(f"ERROR: no existe {TARGET}")
        return 1

    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    crlf = "\r\n" in text
    applied = 0
    for old, new in REPLACEMENTS:
        if crlf:
            old = old.replace("\n", "\r\n")
            new = new.replace("\n", "\r\n")
        count = text.count(old)
        if count == 0:
            if new.replace("\r\n", "\n") in text.replace("\r\n", "\n"):
                print("OK (ya aplicado):", old.strip().splitlines()[0][:60])
                continue
            print("ERROR: no se encontró el bloque:", old.strip().splitlines()[0][:60])
            return 1
        if count > 1:
            print(f"ERROR: bloque ambiguo ({count} coincidencias):", old.strip().splitlines()[0][:60])
            return 1
        text = text.replace(old, new)
        applied += 1

    if applied == 0:
        print("Nada que hacer — el parche ya estaba aplicado.")
        return 0

    # Respaldo y escritura preservando finales de línea originales
    with io.open(TARGET + ".bak", "w", encoding="utf-8", newline="") as f:
        f.write(text if not crlf else text)  # text aún contiene \r\n si crlf
    # Nota: text nunca fue normalizado, conserva los finales originales.
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"Aplicados {applied} reemplazos en {TARGET} (respaldo: checkin.html.bak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
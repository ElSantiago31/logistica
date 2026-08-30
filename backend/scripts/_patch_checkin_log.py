#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parche: log de ingresos del check-in — fecha en registros + botón Descargar CSV.

Restaura la UI que existía como parche local y se perdió en el re-write de
checkin.html (commit 8059a69):

1. Fecha + hora en cada registro del log local (antes solo hora).
2. Fecha + hora en los registros compartidos de otros dispositivos.
3. Botón "Descargar" en el header del log → GET /api/sync/events/{id}/attendance-log.csv
   (endpoint que ya existe en app/routers/sync.py).
4. Poblar el log compartido de inmediato tras cargar datos (antes había que
   esperar el primer polling de 30s para ver algo).

Uso: python backend/scripts/_patch_checkin_log.py
"""
import io
import sys

PATH = "backend/app/templates/admin/checkin.html"


def apply(content, old, new, label):
    if old not in content:
        print(f"[SKIP] {label}: no encontrado (¿ya aplicado?)")
        return content
    if content.count(old) > 1:
        print(f"[FAIL] {label}: patrón ambiguo ({content.count(old)} ocurrencias)")
        sys.exit(1)
    print(f"[OK] {label}")
    return content.replace(old, new, 1)


def main():
    with io.open(PATH, "r", encoding="utf-8") as f:
        c = f.read()

    # 1) Header del log: añadir botón Descargar junto al contador
    c = apply(
        c,
        """            <h4 class="text-sm font-semibold" style="color:#5d4224;">🕒 Últimos ingresos</h4>
            <span class="text-xs text-gray-400" id="checkin-log-count">0 registros</span>
        </div>""",
        """            <h4 class="text-sm font-semibold" style="color:#5d4224;">🕒 Últimos ingresos</h4>
            <div class="flex items-center gap-2">
                <span class="text-xs text-gray-400" id="checkin-log-count">0 registros</span>
                <button id="btn-download-log" onclick="downloadAttendanceLog()"
                    class="px-2 py-1 rounded-lg text-xs font-medium border transition hover:bg-amber-50"
                    style="border-color:#cf9b62; color:#5d4224;" title="Descargar el log completo de ingresos en CSV">
                    📥 Descargar
                </button>
            </div>
        </div>""",
        label="header log + boton descargar",
    )

    # 2) Registro local: fecha + hora (antes solo hora)
    c = apply(
        c,
        """    const time = new Date(entry.created_at).toLocaleTimeString();""",
        """    const dt = new Date(entry.created_at);
    const time = dt.toLocaleDateString() + ' ' + dt.toLocaleTimeString();""",
        label="fecha en registro local",
    )

    # 3) Registro compartido: fecha + hora (antes solo hora)
    c = apply(
        c,
        """            const time = act.check_in_time ? new Date(act.check_in_time).toLocaleTimeString() : '';""",
        """            const tAct = act.check_in_time ? new Date(act.check_in_time) : null;
            const time = tAct ? tAct.toLocaleDateString() + ' ' + tAct.toLocaleTimeString() : '';""",
        label="fecha en registro compartido",
    )

    # 4) Función downloadAttendanceLog (antes de _renderSharedActivity)
    c = apply(
        c,
        """function _renderSharedActivity(activities) {""",
        """// Descarga el log completo de ingresos del evento en CSV desde el backend
// (GET /api/sync/events/{id}/attendance-log.csv).
async function downloadAttendanceLog() {
    const btn = document.getElementById('btn-download-log');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Descargando...'; }
    try {
        const resp = await Auth.apiFetch(`/api/sync/events/${EVENT_ID}/attendance-log.csv`, {
            headers: authHeaders()
        });
        if (!resp.ok) throw new Error('Servidor respondió ' + resp.status);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `log_ingresos_${EVENT_ID.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        if (btn) btn.textContent = '✅ Descargado';
    } catch(e) {
        console.error('downloadAttendanceLog error:', e);
        alert('❌ No se pudo descargar el log: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            setTimeout(() => { btn.textContent = '📥 Descargar'; }, 2500);
        }
    }
}

function _renderSharedActivity(activities) {""",
        label="funcion downloadAttendanceLog",
    )

    # 5) Tras cargar datos online, poblar el log compartido de inmediato
    c = apply(
        c,
        """                try { await _cacheEventData(EVENT_ID, data); } catch(e) {}
                await updateSyncCount();
                return;""",
        """                try { await _cacheEventData(EVENT_ID, data); } catch(e) {}
                await updateSyncCount();
                pollCheckinStatus();  // poblar log compartido de inmediato (sin esperar 30s)
                return;""",
        label="poll inmediato tras loadEventData",
    )

    with io.open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(c)
    print("[DONE] parche aplicado a", PATH)


if __name__ == "__main__":
    sys.exit(main())
"""Parche one-off: en doCheckIn(), rama 409 "Ya estaba registrado",
persistir la indumentaria diligenciada via PATCH /assignments/{id}/uniform
(best-effort, silencioso). El backend ya guarda uniform en el camino
reconcile (HTTP 200), pero el 409 de carrera concurrente no lo hace.
El botón manual "Guardar Indumentaria" (saveUniform) queda intacto.
"""
import io

PATH = r"backend/app/templates/admin/checkin.html"

OLD = """                } else {
                    showCheckInResult('✅ Ya estaba registrado', true);
                    currentOperator.status = 'checked_in';
                    currentOperator.shirt_number = shirt || null;
                    currentOperator.jacket_number = jacket || null;
                    currentOperator.cap_number = cap || null;
                    const checked = eventAssignments.filter(a => a.status === 'checked_in').length;
                    updateStats(countRelevantForCheckin(eventAssignments), checked);
                    document.getElementById('btn-save-uniform').classList.toggle('hidden', !_canManageUniform());
                }"""

NEW = """                } else {
                    showCheckInResult('✅ Ya estaba registrado', true);
                    currentOperator.status = 'checked_in';
                    currentOperator.shirt_number = shirt || null;
                    currentOperator.jacket_number = jacket || null;
                    currentOperator.cap_number = cap || null;
                    const checked = eventAssignments.filter(a => a.status === 'checked_in').length;
                    updateStats(countRelevantForCheckin(eventAssignments), checked);
                    document.getElementById('btn-save-uniform').classList.toggle('hidden', !_canManageUniform());
                    // Persistir la indumentaria diligenciada (best-effort): el 409
                    // de carrera concurrente no guarda uniform en el backend, así
                    // que se envía por el endpoint dedicado sin bloquear al usuario.
                    if (canUniform && (shirt || jacket || cap)) {
                        try {
                            await Auth.apiFetch(`/api/sync/assignments/${currentOperator.id}/uniform`, {
                                method: 'PATCH',
                                headers: authHeaders(),
                                body: JSON.stringify({
                                    shirt_number: shirt || null,
                                    jacket_number: jacket || null,
                                    cap_number: cap || null
                                })
                            });
                        } catch (e) {
                            console.warn('Ya registrado: no se pudo persistir uniform:', e);
                        }
                    }
                }"""


def main():
    s = io.open(PATH, encoding="utf-8").read()
    if "Ya registrado: no se pudo persistir uniform" in s:
        print("YA APLICADO")
        return
    if OLD not in s:
        raise SystemExit("ERROR: bloque SEARCH no encontrado en checkin.html")
    io.open(PATH, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW, 1))
    ok = "Ya registrado: no se pudo persistir uniform" in io.open(PATH, encoding="utf-8").read()
    print("APLICADO" if ok else "FALLO VERIFICACION")


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""Patch [ETAPAS]: UI de etapa en checkin.html + stage en sync batch.

Añade al check-in:
  1. Selector "Etapa del check-in" en el panel del operador (pre-seleccionado
     con la etapa del filtro activo o la de la asignación).
  2. Envío de `stage` en el check-in online y offline (Dexie).
  3. Botón "🏷️ Cambiar Etapa" post-checkin (PATCH /assignments/{id}/stage).
  4. WebSocket: refresca contadores ante evento `stage_change`.
  5. Quick-add: selector de etapa (pre-seleccionado con el filtro activo).
  6. Backend: sync_attendance aplica `stage` del record offline.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]  # backend/
CHECKIN = ROOT / "app" / "templates" / "admin" / "checkin.html"
SYNC = ROOT / "app" / "routers" / "sync.py"


def patch(path, replacements):
    text = path.read_text(encoding="utf-8")
    missing = 0
    for old, new in replacements:
        if old not in text:
            print(f"  [SKIP] no encontrado: {old.strip().splitlines()[0][:70]}")
            missing += 1
            continue
        if new in text:
            print(f"  [OK*] ya aplicado: {old.strip().splitlines()[0][:70]}")
            continue
        text = text.replace(old, new, 1)
        print(f"  [OK ] {old.strip().splitlines()[0][:70]}")
    path.write_text(text, encoding="utf-8", newline="\n")
    return missing


def main():
    print(f"== {CHECKIN.name} ==")
    r = []

    # 1. Selector de etapa del check-in (después del selector de rol)
    r.append((
        """                    <p class="text-[11px] text-gray-400 mt-1">Se envía con el check-in y se puede cambiar después</p>
                </div>
""",
        """                    <p class="text-[11px] text-gray-400 mt-1">Se envía con el check-in y se puede cambiar después</p>
                </div>

                <!-- [ETAPAS] Etapa del check-in: en qué etapa hace el ingreso -->
                <div id="stage-section" class="mb-4">
                    <label class="text-xs font-semibold text-gray-500 uppercase mb-1 block">
                        🏷️ Etapa del check-in
                    </label>
                    <select id="stage-select"
                        class="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-amber-400 bg-white">
                        <option value="previa">Previa</option>
                        <option value="avanzada">Avanzada</option>
                        <option value="evento">Evento</option>
                        <option value="desmontaje">Desmontaje</option>
                    </select>
                    <p class="text-[11px] text-gray-400 mt-1">Define en qué etapa hace el ingreso; se puede cambiar después</p>
                </div>
"""))

    # 2. Botón Cambiar Etapa (post-checkin)
    r.append((
        """                        🔁 Cambiar Coordinador
                    </button>
""",
        """                        🔁 Cambiar Coordinador
                    </button>
                    <button id="btn-change-stage" onclick="changeStage()"
                        class="w-full py-2 rounded-lg text-sm font-medium border border-teal-400 bg-teal-50 text-teal-700">
                        🏷️ Cambiar Etapa
                    </button>
"""))

    # 3. Quick-add: selector de etapa
    r.append((
        """                <input type="text" id="qaDocNumber" placeholder="Número de documento *" class="border rounded-lg px-3 py-2 text-sm">
            </div>
""",
        """                <input type="text" id="qaDocNumber" placeholder="Número de documento *" class="border rounded-lg px-3 py-2 text-sm">
                <select id="qaStage" class="border rounded-lg px-3 py-2 text-sm">
                    <option value="previa">Etapa: Previa</option>
                    <option value="avanzada">Etapa: Avanzada</option>
                    <option value="evento">Etapa: Evento</option>
                    <option value="desmontaje">Etapa: Desmontaje</option>
                </select>
            </div>
"""))

    # 4. showQuickAddModal: pre-seleccionar etapa del filtro
    r.append((
        """    document.getElementById('qaDocType').value = 'CC';
    document.getElementById('quickAddModal').classList.remove('hidden');
""",
        """    document.getElementById('qaDocType').value = 'CC';
    // [ETAPAS] pre-seleccionar la etapa del filtro activo (o 'evento')
    document.getElementById('qaStage').value = _stageFilter() || 'evento';
    document.getElementById('quickAddModal').classList.remove('hidden');
"""))

    # 5. submitQuickAdd: enviar stage
    r.append((
        """                    document_type: document.getElementById('qaDocType').value,
                    document_number: document_number,
                })
""",
        """                    document_type: document.getElementById('qaDocType').value,
                    document_number: document_number,
                    stage: document.getElementById('qaStage').value || null,
                })
"""))

    # 6. WebSocket: reaccionar a stage_change
    r.append((
        """        case 'reassign':
        case 'role_change':
""",
        """        case 'reassign':
        case 'role_change':
        case 'stage_change':
"""))

    # 7. showOperator: pre-seleccionar etapa del check-in
    r.append((
        """        stageEl.classList.toggle('hidden', !eventAssignments.some(a =>
            a.operator_id === operator.operator_id && (a.stage || 'evento') !== st));
    }
""",
        """        stageEl.classList.toggle('hidden', !eventAssignments.some(a =>
            a.operator_id === operator.operator_id && (a.stage || 'evento') !== st));
    }

    // [ETAPAS] pre-seleccionar etapa del check-in: filtro activo > etapa actual
    const stageSel = document.getElementById('stage-select');
    if (stageSel) stageSel.value = _stageFilter() || (operator.stage || 'evento');
"""))

    # 8. doCheckIn: enviar stage
    r.append((
        """                    coordinator: (document.getElementById('coordinator-select') || {}).value || null,
                    role_id: selRoleId,
                    force_overquota: _retryingOverquota,
""",
        """                    coordinator: (document.getElementById('coordinator-select') || {}).value || null,
                    role_id: selRoleId,
                    stage: (document.getElementById('stage-select') || {}).value || null,
                    force_overquota: _retryingOverquota,
"""))

    # 9. doCheckIn ok: aplicar etapa localmente
    r.append((
        """                showCheckInResult('✅ Check-in registrado', true);
                currentOperator.status = 'checked_in';
                _applySelectedRoleToLocal();  // FASE 2: rol enviado con el check-in
""",
        """                showCheckInResult('✅ Check-in registrado', true);
                currentOperator.status = 'checked_in';
                _applySelectedRoleToLocal();  // FASE 2: rol enviado con el check-in
                const selStageVal = (document.getElementById('stage-select') || {}).value || null;
                if (selStageVal) currentOperator.stage = selStageVal;  // [ETAPAS]
"""))

    # 10. offlineCheckIn: guardar stage en Dexie + aplicarlo local
    r.append((
        """            coordinator: selCoord,
            role_id: selRole,
            shirt_number: shirt || null,
""",
        """            coordinator: selCoord,
            role_id: selRole,
            stage: (document.getElementById('stage-select') || {}).value || null,
            shirt_number: shirt || null,
"""))
    r.append((
        """        if (selCoord) {
            currentOperator.admitted_by = selCoord;
            currentOperator.programmed_by = currentOperator.programmed_by || selCoord;
        }
""",
        """        if (selCoord) {
            currentOperator.admitted_by = selCoord;
            currentOperator.programmed_by = currentOperator.programmed_by || selCoord;
        }
        const offStage = (document.getElementById('stage-select') || {}).value || null;
        if (offStage) currentOperator.stage = offStage;  // [ETAPAS]
"""))

    # 11. changeStage(): nueva función tras _applySelectedRoleToLocal
    r.append((
        """    if (sel.selectedIndex > 0) {
        const label = sel.options[sel.selectedIndex].textContent.split(' — ')[0].trim();
        currentOperator.role_name = label || currentOperator.role_name;
        document.getElementById('op-role').textContent = currentOperator.role_name;
    }
}
""",
        """    if (sel.selectedIndex > 0) {
        const label = sel.options[sel.selectedIndex].textContent.split(' — ')[0].trim();
        currentOperator.role_name = label || currentOperator.role_name;
        document.getElementById('op-role').textContent = currentOperator.role_name;
    }
}

// [ETAPAS] Cambia la etapa vía PATCH /api/sync/assignments/{id}/stage.
// Funciona antes y después del check-in (si ya hay ingreso, el backend
// anota el cambio en el AttendanceLog → log de ingresos y CSV).
async function changeStage() {
    if (!currentOperator) return;
    const sel = document.getElementById('stage-select');
    if (!sel) { alert('Selector de etapa no disponible'); return; }
    const newStage = sel.value;
    const oldStage = currentOperator.stage || 'evento';
    if (newStage === oldStage) {
        alert('La etapa seleccionada ya es la actual.');
        return;
    }
    if (!confirm(`¿Cambiar la etapa de "${currentOperator.full_name}"?\\n\\n` +
        `De: ${STAGE_LABELS[oldStage] || oldStage}\\nA: ${STAGE_LABELS[newStage] || newStage}`)) return;
    try {
        const resp = await Auth.apiFetch(`/api/sync/assignments/${currentOperator.id}/stage`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({ stage: newStage })
        });
        if (resp.ok) {
            currentOperator.stage = newStage;
            const stageEl = document.getElementById('op-stage');
            if (stageEl) stageEl.textContent = '🏷️ Etapa: ' + (STAGE_LABELS[newStage] || newStage);
            const box = document.getElementById('op-status-box');
            box.className = 'rounded-lg p-3 mb-4 text-center bg-teal-50 text-teal-700';
            document.getElementById('op-status-text').textContent =
                `🏷️ Etapa cambiada a ${STAGE_LABELS[newStage] || newStage}`;
            updateStats();  // los contadores respetan el filtro de etapa
            pollQuotas();
        } else {
            const errData = await resp.json().catch(() => ({}));
            const msg = (errData && errData.detail) || resp.status;
            alert('No se pudo cambiar la etapa: ' + msg);
        }
    } catch (e) {
        console.error('changeStage error:', e);
        alert('📴 Sin conexión: no se pudo cambiar la etapa');
    }
}
"""))

    miss = patch(CHECKIN, r)

    print(f"== {SYNC.name} ==")
    r2 = [(
        """                        rec_role_id = _to_uuid(rec.get("role_id"))
                        if rec_role_id and str(rec_role_id) != str(assignment.role_id or ""):
                            assignment.role_id = rec_role_id
""",
        """                        rec_role_id = _to_uuid(rec.get("role_id"))
                        if rec_role_id and str(rec_role_id) != str(assignment.role_id or ""):
                            assignment.role_id = rec_role_id
                        # [ETAPAS] etapa del check-in offline
                        rec_stage = str(rec.get("stage") or "").strip().lower()
                        if rec_stage and rec_stage in EVENT_STAGES:
                            assignment.stage = rec_stage
""")]
    miss += patch(SYNC, r2)

    if miss:
        print(f"⚠️  {miss} reemplazo(s) no aplicados — revisar")
        sys.exit(1)
    print("✅ Patch aplicado completo")


if __name__ == "__main__":
    main()
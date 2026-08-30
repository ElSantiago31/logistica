# -*- coding: utf-8 -*-
"""Parche FASE 2/3: selector de rol en check-in.

Aplica de forma idempotente los cambios de UI de checkin.html:
- <select> de rol (role-select) en el panel del operador
- botón "Cambiar Rol" post-checkin (changeRole)
- envío de role_id con el check-in (online y offline)
- sincronización de rol en polling/caché/log compartido
- helpers populateRoleSelect / _collectEventRoles / _applySelectedRoleToLocal
"""
import io
import sys

PATH = "app/templates/admin/checkin.html"


def apply(content, old, new, count=1, label=""):
    n = content.count(old)
    if n == 0:
        print(f"[SKIP] no encontrado: {label or old[:60]!r}")
        return content
    if n != count:
        print(f"[WARN] {label}: {n} ocurrencias (esperaba {count}) — parcheando todas")
    return content.replace(old, new)


def main():
    with io.open(PATH, encoding="utf-8") as f:
        c = f.read()

    if "role-select" in c and "changeRole" in c:
        print("[OK] parche ya aplicado")
        return

    # 1) HTML: selector de rol antes de checkin-actions
    c = apply(c,
        '                <div id="checkin-actions" class="space-y-2">',
        '''                <!-- Selector de rol (rol del operador en el evento) -->
                <div id="role-section" class="mb-4">
                    <label class="text-xs font-semibold text-gray-500 uppercase mb-1 block">
                        🎭 Rol en el evento
                    </label>
                    <select id="role-select"
                        class="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-amber-400 bg-white">
                        <option value="">— Sin rol —</option>
                    </select>
                    <p class="text-[11px] text-gray-400 mt-1">Se envía con el check-in y se puede cambiar después</p>
                </div>

                <div id="checkin-actions" class="space-y-2">''',
        label="role-section html")

    # 2) HTML: botón Cambiar Rol en post-checkin
    c = apply(c,
        '''                <div id="post-checkin-actions" class="space-y-2 hidden">
                    <button id="btn-change-coord" onclick="changeCoordinator()"''',
        '''                <div id="post-checkin-actions" class="space-y-2 hidden">
                    <button id="btn-change-role" onclick="changeRole()"
                        class="w-full py-2 rounded-lg text-sm font-medium border border-purple-400 bg-purple-50 text-purple-700">
                        🎭 Cambiar Rol
                    </button>
                    <button id="btn-change-coord" onclick="changeCoordinator()"''',
        label="btn-change-role html")

    # 3) WS: caso role_change
    c = apply(c,
        """        case 'checkin':
        case 'uniform':
        case 'reassign':""",
        """        case 'checkin':
        case 'uniform':
        case 'reassign':
        case 'role_change':""",
        label="ws role_change")

    # 4) loadEventData: llenar selector de rol
    c = apply(c,
        "                populateCoordinatorSelect();  // Llenar selector con coordinadores",
        """                populateCoordinatorSelect();  // Llenar selector con coordinadores
                populateRoleSelect();         // FASE 2: selector de rol""",
        label="loadEventData populateRoleSelect")

    # 5) showOperator: pre-seleccionar rol del operador
    c = apply(c,
        """        if (!matched) sel.value = '';
    }

    document.getElementById('operator-panel').classList.remove('hidden');""",
        """        if (!matched) sel.value = '';
    }

    // FASE 2: llenar el selector de rol y pre-seleccionar el actual
    populateRoleSelect();

    document.getElementById('operator-panel').classList.remove('hidden');""",
        label="showOperator populateRoleSelect")

    # 6) doCheckIn: capturar rol elegido
    c = apply(c,
        """    const cap = canUniform ? document.getElementById('uniform-cap').value.trim() : '';
    const btn = document.getElementById('btn-checkin');""",
        """    const cap = canUniform ? document.getElementById('uniform-cap').value.trim() : '';
    const selRoleId = (document.getElementById('role-select') || {}).value || null;  // FASE 2: rol elegido
    const btn = document.getElementById('btn-checkin');""",
        label="doCheckIn selRoleId")

    # 7) doCheckIn: enviar role_id
    c = apply(c,
        """                    method: 'manual',
                    coordinator: (document.getElementById('coordinator-select') || {}).value || null,
                    force_overquota: _retryingOverquota,""",
        """                    method: 'manual',
                    coordinator: (document.getElementById('coordinator-select') || {}).value || null,
                    role_id: selRoleId,
                    force_overquota: _retryingOverquota,""",
        label="doCheckIn body role_id")

    # 8) doCheckIn: aplicar rol al local tras éxito
    c = apply(c,
        """                );
                currentOperator.status = 'checked_in';
                currentOperator.shirt_number = shirt || null;""",
        """                );
                currentOperator.status = 'checked_in';
                _applySelectedRoleToLocal();  // FASE 2: rol enviado con el check-in
                currentOperator.shirt_number = shirt || null;""",
        label="doCheckIn applyRole")

    # 9) offlineCheckIn: guardar rol en Dexie
    c = apply(c,
        """        const selCoord = (document.getElementById('coordinator-select') || {}).value || null;
        await db.attendance.add({""",
        """        const selCoord = (document.getElementById('coordinator-select') || {}).value || null;
        const selRole = (document.getElementById('role-select') || {}).value || null;
        await db.attendance.add({""",
        label="offlineCheckIn selRole")
    c = apply(c,
        """            sync_status: 'pending',
            coordinator: selCoord,
            shirt_number: shirt || null,""",
        """            sync_status: 'pending',
            coordinator: selCoord,
            role_id: selRole,
            shirt_number: shirt || null,""",
        label="offlineCheckIn role_id")
    c = apply(c,
        """            currentOperator.programmed_by = currentOperator.programmed_by || selCoord;
        }
        showCheckInResult('📴 Guardado offline""",
        """            currentOperator.programmed_by = currentOperator.programmed_by || selCoord;
        }
        _applySelectedRoleToLocal();  // FASE 2: rol elegido offline
        showCheckInResult('📴 Guardado offline""",
        label="offlineCheckIn applyRole")

    # 10) syncPendingRecords: incluir role_id
    c = apply(c,
        """                coordinator: r.coordinator || null,
                shirt_number: r.shirt_number,""",
        """                coordinator: r.coordinator || null,
                role_id: r.role_id || null,
                shirt_number: r.shirt_number,""",
        label="sync role_id")

    # 11) _cacheEventData: persistir role_id
    c = apply(c,
        """                role_name: a.role_name, status: a.status, photo_url: a.photo_url,""",
        """                role_name: a.role_name, role_id: a.role_id ? String(a.role_id) : null,
                status: a.status, photo_url: a.photo_url,""",
        label="cache role_id")

    # 12) pollCheckinStatus: detectar cambios de rol
    c = apply(c,
        """            if (srv.status !== local.status ||
                (srv.shirt_number || null) !== (local.shirt_number || null) ||""",
        """            if (srv.status !== local.status ||
                (srv.role_id || null) !== (local.role_id || null) ||
                (srv.shirt_number || null) !== (local.shirt_number || null) ||""",
        label="poll diff role")
    c = apply(c,
        """            if (local && srv) {
                local.status = srv.status;
                local.shirt_number = srv.shirt_number;""",
        """            if (local && srv) {
                local.status = srv.status;
                local.role_id = srv.role_id || null;
                if (srv.role_name) local.role_name = srv.role_name;
                local.shirt_number = srv.shirt_number;""",
        label="poll apply role")

    # 13) _refreshOperatorPanelFromPoll: refrescar rol visible
    c = apply(c,
        """        document.getElementById('op-status-text').textContent = '✅ Ya registrado (actualizado)';
        document.getElementById('checkin-actions').classList.add('hidden');
        document.getElementById('btn-save-uniform')""",
        """        document.getElementById('op-status-text').textContent = '✅ Ya registrado (actualizado)';
        document.getElementById('checkin-actions').classList.add('hidden');
        // Rol actualizado desde otro dispositivo (WS/polling)
        document.getElementById('op-role').textContent = op.role_name || 'Operador';
        const roleSelPoll = document.getElementById('role-select');
        if (roleSelPoll && op.role_id) {
            if (!Array.from(roleSelPoll.options).some(o => o.value === String(op.role_id))) populateRoleSelect();
            roleSelPoll.value = String(op.role_id);
        }
        document.getElementById('btn-save-uniform')""",
        label="panel refresh role")

    # 14) _syncCacheFromPolling: persistir rol en caché
    c = apply(c,
        """                await db.operators.put({ ...cached, status: srv.status,
                    shirt_number: srv.shirt_number, jacket_number: srv.jacket_number, cap_number: srv.cap_number });""",
        """                await db.operators.put({ ...cached, status: srv.status,
                    role_id: srv.role_id || null,
                    shirt_number: srv.shirt_number, jacket_number: srv.jacket_number, cap_number: srv.cap_number });""",
        label="cache sync role")

    # 15) _renderSharedActivity: badge de cambio de rol
    c = apply(c,
        """                : '';
            item.innerHTML = `
                <div class="flex justify-between">
                    <span><strong>✅</strong> ${act.operator_name || '—'}${overBadge}</span>""",
        """                : '';
            const roleBadge = act.role_change
                ? `<span class="ml-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700">🎭 ${act.role_change}</span>`
                : '';
            item.innerHTML = `
                <div class="flex justify-between">
                    <span><strong>✅</strong> ${act.operator_name || '—'}${overBadge}${roleBadge}</span>""",
        label="shared activity role badge")

    # 16) Nuevas funciones antes del bloque de cupos por coordinador
    HELPERS = '''
// ============================================================
//  SELECTOR DE ROL (FASE 2/3)
// ============================================================
// Recolecta los roles conocidos del evento: los requeridos en el plan
// de personal (staff_needs) + los presentes en las asignaciones.
function _collectEventRoles() {
    const map = new Map();
    for (const n of (staffNeeds || [])) {
        if (n.role_id) map.set(String(n.role_id), (n.role_name || 'Rol').trim() || 'Rol');
    }
    for (const a of (eventAssignments || [])) {
        if (a.role_id) map.set(String(a.role_id), (a.role_name || 'Rol').trim() || 'Rol');
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
}

// Llena el <select> de roles y pre-selecciona el del operador actual.
// Si hay plan de personal, muestra el progreso: "Brigadista — 3/10".
function populateRoleSelect() {
    const sel = document.getElementById('role-select');
    if (!sel) return;
    const roles = _collectEventRoles();
    const curId = currentOperator && currentOperator.role_id ? String(currentOperator.role_id) : '';
    // Asegurar que el rol actual del operador siempre esté en las opciones
    if (curId && !roles.some(r => r.id === curId) && currentOperator.role_name) {
        roles.push({ id: curId, name: currentOperator.role_name });
    }
    sel.innerHTML = '<option value="">— Sin rol —</option>';
    for (const r of roles) {
        const opt = document.createElement('option');
        opt.value = r.id;
        const need = (staffNeeds || []).find(n => String(n.role_id) === r.id);
        opt.textContent = (need && need.quantity_needed)
            ? `${r.name} — ${need.checked_in || 0}/${need.quantity_needed}`
            : r.name;
        sel.appendChild(opt);
    }
    if (curId) sel.value = curId;
}

// Sincroniza currentOperator con el rol elegido en el selector (tras check-in).
function _applySelectedRoleToLocal() {
    if (!currentOperator) return;
    const sel = document.getElementById('role-select');
    if (!sel) return;
    currentOperator.role_id = sel.value || null;
    if (sel.selectedIndex > 0) {
        const label = sel.options[sel.selectedIndex].textContent.split(' — ')[0].trim();
        currentOperator.role_name = label || currentOperator.role_name;
        document.getElementById('op-role').textContent = currentOperator.role_name;
    }
}

// Cambia el rol del operador vía PATCH /api/sync/assignments/{id}/role.
// Funciona tanto antes como después del check-in (si ya hay ingreso,
// el backend anota el cambio en el log de asistencia).
async function changeRole() {
    if (!currentOperator) return;
    const sel = document.getElementById('role-select');
    if (!sel) { alert('Selector de rol no disponible'); return; }
    const newRoleId = sel.value;
    if (!newRoleId) {
        alert('Selecciona un rol en el desplegable "Rol en el evento".');
        return;
    }
    if (String(currentOperator.role_id || '') === newRoleId) {
        alert('El rol seleccionado ya es el actual.');
        return;
    }
    const oldRoleName = currentOperator.role_name || 'Sin rol';
    const opt = sel.options[sel.selectedIndex];
    const newRoleName = opt ? opt.textContent.split(' — ')[0].trim() : 'Nuevo rol';
    if (!confirm(`¿Cambiar el rol de "${currentOperator.full_name}"?\\n\\n` +
        `De: ${oldRoleName}\\nA: ${newRoleName}`)) return;

    try {
        const resp = await Auth.apiFetch(`/api/sync/assignments/${currentOperator.id}/role`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({
                role_id: newRoleId,
                reason: 'Cambio manual en check-in'
            })
        });
        if (resp.ok) {
            const data = await resp.json();
            const oldName = data.old_role || oldRoleName;
            currentOperator.role_id = newRoleId;
            currentOperator.role_name = data.new_role || newRoleName;
            document.getElementById('op-role').textContent = currentOperator.role_name;
            _showToast(`✅ Rol: ${oldName} → ${currentOperator.role_name}`, 'success');
            _addCheckinLog(
                `${currentOperator.full_name} — Rol: ${oldName} → ${currentOperator.role_name}`,
                currentOperator.id,
                true
            ).catch(() => {});
            renderRoleCards();  // contadores por rol en vivo
        } else {
            const err = await resp.json().catch(() => ({}));
            const errMsg = (err.detail && err.detail.message) || err.detail || ('error ' + resp.status);
            alert('No se pudo cambiar el rol: ' + errMsg);
        }
    } catch(e) {
        console.error('changeRole network error:', e);
        alert('📴 Sin conexión: no se pudo cambiar el rol');
    }
}

// ============================================================
//  FASE 3: TARJETAS DE CUPOS POR COORDINADOR'''
    c = apply(c,
        """// ============================================================
//  FASE 3: TARJETAS DE CUPOS POR COORDINADOR""",
        HELPERS,
        label="helpers js")

    with io.open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(c)
    print("[OK] parche aplicado a", PATH)


if __name__ == "__main__":
    sys.exit(main())
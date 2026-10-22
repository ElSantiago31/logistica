# -*- coding: utf-8 -*-
"""[ETAPAS] Fase 4: quitar el dropdown de etapa del modal de asignación.

La etapa se define en el check-in (no al asignar operadores). Este parche:
  - Elimina el <select id="assignStage"> del modal (deja nota informativa).
  - Elimina onAssignStageChange y toda referencia JS a #assignStage.
  - Búsqueda: excluye solo asignados a 'evento' (etapa por defecto de nuevas
    asignaciones); los de otras etapas siguen visibles con badge DOBLE TURNO.
  - Coordinadores: se listan TODOS los cupos con su etapa en el label.
  - POST /assign sin stage (backend aplica default 'evento').
Idempotente: si ya aplicó, no hace nada.
"""
import io
import os
import sys

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "app", "templates", "admin", "event_detail.html")

REPLACES = [
    # --- A. Quitar el <select> de etapa; dejar nota informativa -------------
    (
        """                    <select id="assignStage" class="border rounded-lg px-3 py-2 text-sm" onchange="onAssignStageChange()">
                        <option value="previa"> ◽ Previa</option>
                        <option value="avanzada"> ◽ Avanzada</option>
                        <option value="evento" selected> ⭐ Evento</option>
                        <option value="desmontaje"> ◽ Desmontaje</option>
                    </select>
""",
        """                    <p class="text-xs text-gray-400 whitespace-nowrap self-center">ℹ️ La etapa se define en el check-in</p>
""",
    ),
    # --- B. showAssignModal: quitar reset del select ------------------------
    (
        """    document.getElementById('searchOps').value='';
    document.getElementById('assignStage').value='evento';
    _smartFilter = { role: '', edu: '' };
""",
        """    document.getElementById('searchOps').value='';
    _smartFilter = { role: '', edu: '' };
""",
    ),
    # --- C. Chips: onclick sin stage ----------------------------------------
    (
        """applySmartFilter('${n.role_id||''}','${n.education_level||''}','${stage}')""",
        """applySmartFilter('${n.role_id||''}','${n.education_level||''}')""",
    ),
    # --- D. applySmartFilter sin stage --------------------------------------
    (
        """function applySmartFilter(roleId,edu,stage){
    _smartFilter.role = roleId;
    _smartFilter.edu = edu;
    document.getElementById('assignRole').value = roleId;
    if(stage&&STAGES.includes(stage)){
        document.getElementById('assignStage').value=stage;
        refreshCoordinatorOptions();
    }
    searchOperators(true);
}
""",
        """function applySmartFilter(roleId,edu){
    _smartFilter.role = roleId;
    _smartFilter.edu = edu;
    document.getElementById('assignRole').value = roleId;
    searchOperators(true);
}
""",
    ),
    # --- E. Coordinadores: todos los cupos, con etapa en el label -----------
    (
        """// Repoblar selector de coordinadores según la etapa seleccionada en el modal.
function refreshCoordinatorOptions(){
    const stage=document.getElementById('assignStage').value||'evento';
    const coordSel=document.getElementById('assignCoordinator');
    const quotas=currentCoordinatorQuotas.filter(q=>(q.stage||'evento')===stage);
""",
        """// Repoblar selector de coordinadores: TODOS los cupos, con su etapa.
function refreshCoordinatorOptions(){
    const coordSel=document.getElementById('assignCoordinator');
    const quotas=currentCoordinatorQuotas;
""",
    ),
    (
        """                const name=(q.coordinator||'').replace(/"/g,'"');
                return `<option value="${opId}" data-name="${name}">📋 ${q.coordinator} — cupo ${q.quota} (uso ${used})${warn}</option>`;
""",
        """                const name=(q.coordinator||'').replace(/"/g,'"');
                const stg=STAGE_LABELS[q.stage]||'Evento';
                return `<option value="${opId}" data-name="${name}">📋 ${q.coordinator} (${stg}) — cupo ${q.quota} (uso ${used})${warn}</option>`;
""",
    ),
    # --- F. Eliminar onAssignStageChange ------------------------------------
    (
        """function onAssignStageChange(){refreshCoordinatorOptions();updateSelectionCounter();searchOperators(true)}
function closeAssignModal(){""",
        """function closeAssignModal(){""",
    ),
    # --- G. searchOperators: excluir solo etapa 'evento' --------------------
    (
        """    // Excluir solo los ya asignados a ESTA etapa: operadores en otras etapas
    // siguen disponibles (reasignarlos = doble turno permitido).
    const _stageSel=document.getElementById('assignStage');
    const _curStage=_stageSel?(_stageSel.value||'evento'):'evento';
    let url=`/api/operators/?skip=${skip}&limit=${opsPageSize}&is_approved=true&exclude_event_id=${encodeURIComponent(EVENT_ID)}&exclude_stage=${encodeURIComponent(_curStage)}`;
""",
        """    // [ETAPAS] Las nuevas asignaciones nacen en 'evento': se excluye solo a
    // los ya asignados a esa etapa; los de otras etapas siguen disponibles
    // (reasignarlos = doble turno permitido, avisado con badge).
    let url=`/api/operators/?skip=${skip}&limit=${opsPageSize}&is_approved=true&exclude_event_id=${encodeURIComponent(EVENT_ID)}&exclude_stage=evento`;
""",
    ),
    # --- H. opRow: badge DOBLE TURNO con etapa fija 'evento' -----------------
    (
        """    // ¿Ya está en otra etapa del evento? → asignarlo a esta = DOBLE TURNO
    const stageSel=document.getElementById('assignStage');
    const curStage=stageSel?(stageSel.value||'evento'):'evento';
    const stages=assignedStagesByUser.get(String(o.id));
    const others=stages?[...stages].filter(s=>s!==curStage).map(s=>STAGE_LABELS[s]||s):[];
""",
        """    // ¿Ya está en otra etapa del evento? → asignarlo = DOBLE TURNO
    const stages=assignedStagesByUser.get(String(o.id));
    const others=stages?[...stages].filter(s=>s!=='evento').map(s=>STAGE_LABELS[s]||s):[];
""",
    ),
    # --- I. getRemainingForRole: etapa fija 'evento' -------------------------
    (
        """    const stage=document.getElementById('assignStage')?document.getElementById('assignStage').value||'evento':'evento';
    const need=currentStaffNeeds.find(n=>n.role_id===roleId&&(n.stage||'evento')===stage)
""",
        """    const need=currentStaffNeeds.find(n=>n.role_id===roleId&&(n.stage||'evento')==='evento')
""",
    ),
    # --- J. assignSelected: sin stage en el body -----------------------------
    (
        """    const stage=document.getElementById('assignStage')?document.getElementById('assignStage').value||'evento':'evento';
    const body={operator_ids:Array.from(selectedOps),role_id:roleId,programmed_by_operator_id:coordId,programmed_by_name:coordName,stage:stage};
""",
        """    // [ETAPAS] Sin stage: el backend asigna 'evento' por defecto; la etapa
    // final de cada operador se define en el check-in del evento.
    const body={operator_ids:Array.from(selectedOps),role_id:roleId,programmed_by_operator_id:coordId,programmed_by_name:coordName};
""",
    ),
]


def main() -> int:
    p = os.path.abspath(PATH)
    src = io.open(p, encoding="utf-8", newline="").read()
    changed = 0
    for old, new in REPLACES:
        if new in src and old not in src:
            continue  # ya aplicado
        if old not in src:
            print("NO ENCONTRADO:\n%s" % old[:160])
            return 1
        src = src.replace(old, new, 1)
        changed += 1
    if changed:
        io.open(p, "w", encoding="utf-8", newline="").write(src)
    print("OK: %d/%d reemplazos aplicados" % (changed, len(REPLACES)))
    # Verificación: no debe quedar ninguna referencia al dropdown
    resto = [l for l in src.splitlines() if "assignStage" in l or "onAssignStageChange" in l]
    if resto:
        print("ADVERTENCIA: referencias restantes:")
        for l in resto:
            print("  ", l.strip()[:120])
        return 1
    print("Sin referencias restantes a #assignStage ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
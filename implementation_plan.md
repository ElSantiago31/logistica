# Implementation Plan

[Overview]
Agregar un botón "✍️ Planilla con Firmas" en el menú de descargas de la nómina que genera el Excel de la planilla con las firmas de los operadores embebidas y **centradas** en la columna L (FIRMA), a un tamaño ligeramente menor al de la celda para que se noten los bordes.

La planilla actual tiene una columna L etiquetada "FIRMA" que queda vacía al generarse. Las firmas ya existen en el sistema: se capturan en el flujo de nómina (`PayrollRecord.signature_data`, base64 PNG) cuando el operador firma en el pad. Esta implementación las recupera y las inserta como imágenes en la celda correspondiente, escaladas y centradas.

El PDF no requiere cambios porque se genera a partir del Excel (las imágenes embebidas en el XLSX aparecen automáticamente en el PDF al convertirlo con LibreOffice/Docker).

---

[Types]

No hay cambios en el esquema de la base de datos ni en los modelos ORM. Las firmas ya existen en `PayrollRecord.signature_data` (columna `Text`, base64 PNG).

Estructura de datos extendida para los dicts de operadores que circulan internamente entre el router y el servicio de Excel:

```python
# Clave nueva opcional en cada dict de operador (backend/app/routers/payroll.py):
op = {
    "full_name": str,           # existente
    "document_number": str,     # existente
    "address": str,             # existente
    "phone": str,               # existente
    "coordinator_name": str,    # existente
    "role_name": str,           # existente
    "jacket_number": str,       # existente
    "cap_number": str,          # existente
    "is_banned": bool,          # existente
    "has_incident": bool,       # existente
    "signature_data": str | None,  # NUEVO: base64 PNG de PayrollRecord (o None)
    "operator_id": str,         # NUEVO: para hacer match con PayrollRecord
}
```

---

[Files]

Modificaciones en archivos existentes (no se crean archivos nuevos):

1. **`backend/app/services/planilla_excel.py`** — Lógica de embebido de firmas
2. **`backend/app/routers/payroll.py`** — Inyección de datos de firma en el endpoint
3. **`backend/app/templates/admin/payroll.html`** — Nuevo botón en el dropdown
4. **`backend/app/services/planilla_pdf.py`** — Propagar `with_signatures` (sin cambios funcionales, el PDF hereda las imágenes del Excel automáticamente)

---

[Functions]

**Nuevas funciones (en `backend/app/services/planilla_excel.py`):**

- `_decode_signature(signature_data: str | None) -> bytes | None`
  - Decodifica base64 PNG/JPG. Maneja el prefijo `data:image/png;base64,`. Retorna `None` si la entrada es inválida o vacía.
  - Reutiliza el patrón de `backend/app/services/invoice_pdf.py::_decode_signature`.

- `_get_image_size(img_bytes: bytes) -> tuple[int, int]`
  - Devuelve `(width_px, height_px)` usando `PIL.Image.open(BytesIO(img_bytes)).size`.
  - Retorna `(0, 0)` si falla.

- `_add_centered_signature(ws, row: int, col: int, signature_data: str, fill_ratio: float = 0.8) -> None`
  - Embebe la firma centrada en la celda `(row, col)`.
  - Lógica de centrado:
    1. Ancho de columna en píxeles: `int(ws.column_dimensions[chr(64+col)].width or 8.43) * 7 + 5`.
    2. Alto de fila en píxeles: `int((ws.row_dimensions[row].height or 15) * 96 / 72)`.
    3. Dimensiones objetivo: `target_w = col_w_px * fill_ratio`, `target_h = row_h_px * fill_ratio`.
    4. Escalar firma manteniendo aspect ratio: `scale = min(target_w/img_w, target_h/img_h)`.
    5. Tamaño final en EMU (1 px = 9525 EMU).
    6. Offsets de centrado en EMU.
    7. Crear `OneCellAnchor` con `AnchorMarker` y `Extents`.
    8. `img.anchor = anchor`; `ws.add_image(img)`.

**Funciones modificadas:**

- `_fill_operators(ws, operators, with_signatures=False)` — cuando `with_signatures=True`, aumenta la altura de fila a **50pt** (solo en filas con firma) y llama a `_add_centered_signature()`.
- `_render_pages(...)` — aceptar y propagar `with_signatures`.
- `generate_planilla_xlsx(...)` — nuevo parámetro `with_signatures: bool = False`.
- `download_planilla_coordinador(...)` — nuevo parámetro `with_signatures: bool = False`; consulta firmas y las incluye en los dicts.
- `generate_planilla_pdf(...)` — propagar `with_signatures`.
- `downloadPlanillaCoordinador(groupBy, sortBy, format, withSignatures)` (JS) — 4to parámetro.

---

[Classes]

No se crean ni eliminan clases. Las clases existentes (`PayrollRecord`, `Evaluation`) no se modifican.

---

[Dependencies]

Sin cambios en `requirements.txt`. Las dependencias necesarias ya están instaladas:
- `openpyxl` (ya en uso) — incluye `openpyxl.drawing.image.Image`, `OneCellAnchor`, `AnchorMarker`, `Extents`.
- `Pillow` (PIL) — ya es dependencia de `reportlab` (usado en `invoice_pdf.py`).

---

[Testing]

1. **Test de decodificación base64**: Crear un PNG de prueba, codificarlo en base64 y verificar que `_decode_signature()` retorna bytes válidos.
2. **Test de embebido**: Llamar `generate_planilla_xlsx(..., with_signatures=True)` con un operador con firma y verificar que `ws._images` contiene la imagen.
3. **Test de centrado**: Generar Excel, convertir a PDF vía Docker y verificar visualmente que la firma está centrada y más pequeña que la celda.
4. **Test de endpoint**: Llamar `GET /api/payroll/events/{id}/planilla-coordinador?with_signatures=true&format=xlsx`.
5. **Test de frontend**: Hacer clic en el nuevo botón "✍️ Con Firmas".

Validación de regresión:
- El botón de planilla normal (sin firmas) debe seguir funcionando idéntico.
- Operadores sin firma deben dejar la celda L vacía (sin error).

---

[Implementation Order]

El plan se divide en **4 fases secuenciales**. Cada fase es funcionalmente independiente y puede probarse por separado.

## FASE 1 — Funciones auxiliares y lógica de centrado (backend/app/services/planilla_excel.py)

**Objetivo**: Implementar toda la lógica de decodificación y centrado de firmas como funciones puras, sin tocar aún el flujo principal.

**Cambios:**
1. Agregar imports al inicio del archivo:
   ```python
   import base64
   from io import BytesIO
   from openpyxl.drawing.image import Image as XlImage
   from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
   from openpyxl.drawing.xdr import XDRPositiveSize
   from openpyxl.utils.units import pixels_to_EMU, DefaultColumnWidth
   ```

2. Agregar constante de columna de firma (después de `COL_GORRA = 10`):
   ```python
   COL_FIRMA = 12  # L — columna donde van las firmas
   ```

3. Agregar funciones auxiliares (después de `_fmt_date`):
   - `_decode_signature(signature_data) -> bytes | None`
   - `_get_image_size(img_bytes) -> tuple[int, int]`
   - `_add_centered_signature(ws, row, col, signature_data, fill_ratio=0.8) -> None`

**Verificación de la fase:**
```bash
python -c "
import sys; sys.path.insert(0, 'backend')
from app.services.planilla_excel import _decode_signature, _get_image_size, _add_centered_signature
# Crear PNG de prueba con PIL
from PIL import Image, ImageDraw
img = Image.new('RGBA', (300, 100), (255,255,255,0))
d = ImageDraw.Draw(img); d.line([(10,50),(290,50)], fill='black', width=3)
import io, base64
buf = io.BytesIO(); img.save(buf, 'PNG'); b64 = base64.b64encode(buf.getvalue()).decode()
decoded = _decode_signature(b64)
print('Decoded bytes:', len(decoded) if decoded else 0)
w,h = _get_image_size(decoded)
print('Size:', w, h)
print('FASE 1 OK')
"
```

## FASE 2 — Integración en el flujo de generación de Excel (backend/app/services/planilla_excel.py)

**Objetivo**: Conectar las funciones de la Fase 1 con el flujo existente para que `generate_planilla_xlsx(with_signatures=True)` produzca un Excel con firmas.

**Cambios:**
1. Modificar `_fill_operators(ws, operators, with_signatures=False)`:
   - Si `with_signatures` y el operador tiene `signature_data`: subir altura de fila a **50pt** y llamar `_add_centered_signature(ws, row, COL_FIRMA, op["signature_data"])`.

2. Modificar `_render_pages(...)`:
   - Agregar parámetro `with_signatures: bool = False`.
   - Pasarlo a `_fill_operators(new_ws, page_ops, with_signatures=with_signatures)`.

3. Modificar `generate_planilla_xlsx(...)`:
   - Agregar parámetro `with_signatures: bool = False` (keyword-only).
   - Pasar `with_signatures=with_signatures` en las 4 llamadas a `_render_pages()` (bloques coordinator, role, coordinator_role, none).

**Verificación de la fase:**
```bash
python -c "
import sys; sys.path.insert(0, 'backend')
from app.services.planilla_excel import generate_planilla_xlsx
from PIL import Image, ImageDraw
import io, base64
img = Image.new('RGBA', (300,100), (255,255,255,0))
d = ImageDraw.Draw(img); d.line([(10,50),(290,50)], fill='black', width=3)
buf = io.BytesIO(); img.save(buf, 'PNG'); b64 = base64.b64encode(buf.getvalue()).decode()
ops = [{'full_name':'TEST','document_number':'123','address':'x','phone':'300','coordinator_name':'PEDRO','jacket_number':'1','cap_number':'2','is_banned':False,'has_incident':False,'signature_data':b64}]
xb = generate_planilla_xlsx(event_name='TEST', event_date=__import__('datetime').datetime(2026,7,16), event_location='BOG', operators=ops, with_signatures=True)
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(xb))
ws = wb.worksheets[0]
print('Imagenes en hoja:', len(ws._images))
print('Altura fila 9:', ws.row_dimensions[9].height)
print('FASE 2 OK' if len(ws._images) >= 1 else 'FALLO')
"
```

## FASE 3 — Backend: endpoint y propagación al PDF (backend/app/routers/payroll.py + backend/app/services/planilla_pdf.py)

**Objetivo**: Que el endpoint `/planilla-coordinador?with_signatures=true` consulte las firmas de la BD y las inyecte en el Excel/PDF.

**Cambios en `payroll.py` (`download_planilla_coordinador`):**
1. Agregar parámetro: `with_signatures: bool = False`.
2. Cuando `with_signatures=True`, consultar firmas:
   ```python
   sig_result = await db.execute(
       select(PayrollRecord.operator_id, PayrollRecord.signature_data)
       .where(
           PayrollRecord.event_id == event_id,
           PayrollRecord.signature_data.is_not(None),
       )
   )
   sig_map = {str(oid): sig for oid, sig in sig_result.all()}
   ```
3. Incluir en cada dict de operador (en el bucle de construcción):
   ```python
   "operator_id": str(operator.id),
   "signature_data": sig_map.get(str(operator.id)) if with_signatures else None,
   ```
4. Pasar `with_signatures=with_signatures` a `generate_planilla_xlsx()` y `generate_planilla_pdf()`.

**Cambios en `planilla_pdf.py` (`generate_planilla_pdf`):**
1. Agregar parámetro `with_signatures: bool = False`.
2. Pasarlo a `generate_planilla_xlsx(with_signatures=with_signatures)`.

**Verificación de la fase:**
- Reiniciar el backend y probar el endpoint con curl/browser:
  `GET /api/payroll/events/{id}/planilla-coordinador?with_signatures=true&format=xlsx`
- El archivo descargado debe contener imágenes (verificar abriendo en Excel).

## FASE 4 — Frontend: botón "✍️ Planilla con Firmas" (backend/app/templates/admin/payroll.html)

**Objetivo**: Agregar el botón visible al usuario final.

**Cambios en el dropdown `#planilla-menu`:**
1. Agregar un separador y una sección nueva al final del menú:
   ```html
   <div class="border-t border-gray-200 my-2"></div>
   <div class="px-3 py-2 text-xs font-semibold text-indigo-700">✍️ CON FIRMAS</div>
   <div class="px-3 py-2 flex justify-between items-center">
       <span class="text-sm">Excel con firmas embebidas</span>
       <button onclick="downloadPlanillaCoordinador('coordinator','lastname','xlsx', true)"
               class="px-3 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700"
               title="Excel con firmas">✍️ Excel</button>
   </div>
   ```

2. Modificar la función JS `downloadPlanillaCoordinador`:
   - Agregar 4to parámetro: `withSignatures = false`.
   - Incluirlo en los `URLSearchParams`:
     ```javascript
     const params = new URLSearchParams({
         group_by: groupBy,
         sort_by: sortBy,
         format: format,
     });
     if (withSignatures) params.set('with_signatures', 'true');
     ```

**Verificación de la fase:**
- Abrir la página de nómina en el navegador.
- Abrir el dropdown "📄 Planilla ▾".
- Ver el botón "✍️ Excel" en la sección "CON FIRMAS".
- Hacer clic → debe descargar un Excel con las firmas embebidas y centradas.

---

## Resumen de fases

| Fase | Archivo | Qué hace | Verificable |
|------|---------|----------|-------------|
| 1 | `planilla_excel.py` | Funciones puras (`_decode_signature`, `_get_image_size`, `_add_centered_signature`) | Script Python |
| 2 | `planilla_excel.py` | Integración en `_fill_operators`/`_render_pages`/`generate_planilla_xlsx` | Script Python |
| 3 | `payroll.py` + `planilla_pdf.py` | Endpoint + consulta BD + propagación PDF | curl/endpoint |
| 4 | `payroll.html` | Botón visible al usuario | Navegador |

## Prueba final end-to-end (después de las 4 fases)

Generar un Excel con firmas reales (o de prueba), convertirlo a PDF vía Docker y verificar visualmente que:
- ✅ La firma está **centrada** en la celda L (horizontal y vertical).
- ✅ La firma es **más pequeña** que la celda (~80% del tamaño, se ven los bordes).
- ✅ La firma mantiene **aspect ratio** (no se deforma).
- ✅ Los operadores **sin firma** dejan la celda vacía.
- ✅ El botón de planilla normal (sin firmas) sigue funcionando igual.
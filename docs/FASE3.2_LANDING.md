# FASE 3.2 — Landing Page Móvil para Registro de Operadores (HU05)

> **Instrucción para la IA:** Lee `docs/FASE3.0_CONTEXT.md` PRIMERO. Luego lee `docs/FASE3.1_FRONTEND_BASE.md` para entender la configuración base del frontend. Finalmente implementa lo descrito aquí.

---

## Estado: ⬜ Pendiente

**Pre-requisitos:** FASE 3.1 y 3.1T completadas (frontend base configurado y probado).

---

## Objetivo

Crear la Landing Page móvil donde los operadores pueden registrarse en el sistema. Esta es la **HU05: Landing Page móvil para registro**.

---

## Historia de Usuario (HU05)

**Como** operador eventual,
**Quiero** poder registrarme desde mi celular en una página web sencilla,
**Para** que mi información quede en el sistema y me puedan contactar para eventos.

---

## Funcionalidad

1. Formulario de registro mobile-first con los campos de `OperatorRegisterRequest`
2. Validación client-side de los campos (longitud, formato email, contraseñas coinciden)
3. Submit via HTMX al endpoint `POST /api/auth/register`
4. Subida de foto posterior al registro exitoso via `POST /api/operators/{id}/photo`
5. Mensaje de éxito con instrucciones ("Pendiente de verificación y aprobación")
6. Manejo de errores (email duplicado, documento duplicado, errores de validación)

---

## Archivos a Crear/Modificar

### 1. Crear `frontend/public/landing/index.html`
Página principal de registro (reemplaza el placeholder).

### 2. Crear `frontend/public/landing/success.html`
Página de confirmación post-registro exitoso (con subida de foto opcional).

### 3. Modificar `backend/app/main.py`
- Actualizar la ruta `/landing` para servir el template completo

---

## Detalle de Implementación

### `frontend/public/landing/index.html`

Formulario mobile-first con las siguientes secciones:

**Sección 1 — Datos Personales:**
- Email (`email`) — tipo email, requerido
- Contraseña (`password`) — tipo password, min 8 caracteres
- Confirmar contraseña (`confirm_password`) — debe coincidir
- Nombres (`first_name`) — texto, min 2 caracteres
- Apellidos (`last_name`) — texto, min 2 caracteres
- Teléfono (`phone`) — tel, min 7 caracteres
- Tipo de documento (`document_type`) — select: CC, CE, TI, PP
- Número de documento (`document_number`) — texto, min 5 caracteres

**Sección 2 — Datos Laborales (colapsable/opcional):**
- EPS (`eps_id`) — select cargado desde API
- ARL (`arl_id`) — select cargado desde API
- Ciudad (`city`) — texto
- Tipo de sangre (`blood_type`) — select: A+, A-, B+, B-, AB+, AB-, O+, O-
- Contacto de emergencia — nombre (`emergency_contact_name`) y teléfono (`emergency_contact_phone`)

**UX Features:**
- Progress steps visual (Datos Personales → Datos Laborales → Confirmación)
- Validación inline con feedback visual (rojo/verde)
- Loading state durante el submit
- Toast de error si el registro falla
- Redirección a página de éxito

**Endpoints API que consume:**
- `GET /api/auth/register` — No existe, el registro es POST
- `POST /api/auth/register` — Registro del operador
- `POST /api/operators/{id}/photo` — Subida de foto (después del registro)

### `frontend/public/landing/success.html`

- Mensaje de "Registro exitoso ✅"
- ID del usuario registrado
- Sección opcional para subir foto (drag & drop o selector)
- Botón para ir al login (futuro) o cerrar la página

### Estructura visual:

```
┌─────────────────────────────┐
│      📦 Logística           │
│   Registro de Operadores    │
├─────────────────────────────┤
│                             │
│  ── Paso 1 de 3 ──         │
│  ● Datos Personales         │
│                             │
│  [ Email            ]       │
│  [ Contraseña       ]       │
│  [ Confirmar        ]       │
│  [ Nombres          ]       │
│  [ Apellidos        ]       │
│  [ Teléfono         ]       │
│  [ Tipo Doc  ▼] [Número ]  │
│                             │
│      [ Siguiente → ]       │
│                             │
├─────────────────────────────┤
│  ¿Ya tienes cuenta? Login   │
└─────────────────────────────┘
```

---

## Detalle JavaScript (vanilla + HTMX)

El formulario usará HTMX para el submit:

```html
<form hx-post="/api/auth/register" 
      hx-swap="none"
      hx-ext="json-enc"
      hx-indicator="#submit-spinner"
      _="on htmx:afterRequest 
         if event.detail.xhr.status === 201 
         then window.location.href = '/landing/success?id=' + JSON.parse(event.detail.xhr.responseText).id">
```

Notas:
- Se necesita `json-enc` extension de HTMX para enviar JSON
- O se puede hacer con vanilla JS fetch si HTMX es limitado para este caso
- Los selects de EPS/ARL se cargan dinámicamente o se hardcodean en el template

### Alternativa con Vanilla JS:

```javascript
async function submitRegistration(formData) {
    const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
    });
    if (response.ok) {
        const data = await response.json();
        window.location.href = `/landing/success?id=${data.id}`;
    } else {
        const error = await response.json();
        showToast(error.detail, 'error');
    }
}
```

---

## Consideraciones de Seguridad

- Contraseñas NO se envían en claro (van por HTTPS en producción)
- Validación client-side es UX, NO seguridad (el backend valida todo)
- No se expone información sensible en los mensajes de error
- Rate limiting ya configurado en backend con slowapi

---

## Cómo Verificar

1. Visitar `http://localhost:8000/landing` en un navegador
2. Verificar que el formulario se ve bien en móvil (DevTools responsive)
3. Llenar el formulario y enviar
4. Verificar que el registro se crea en la base de datos
5. Verificar redirección a página de éxito
6. Probar con email duplicado → debe mostrar error
7. Probar con contraseñas que no coinciden → validación inline

---

## Criterios de Aceptación

- [ ] Formulario de registro mobile-first funcionando
- [ ] Todos los campos de `OperatorRegisterRequest` están en el formulario
- [ ] Validación client-side funciona (email, passwords, longitudes)
- [ ] Submit al endpoint `POST /api/auth/register` funciona correctamente
- [ ] Página de éxito muestra mensaje y permite subir foto
- [ ] Manejo de errores (email duplicado, documento duplicado)
- [ ] Responsive en móvil y desktop
- [ ] Selects de EPS y ARL cargados (dinámicos o hardcodeados)
- [ ] UX fluida con feedback visual (loading, errores, éxito)

---

## ➡️ Siguiente: `docs/FASE3.2_TEST.md`

Una vez completada, actualizar este documento y proceder a las pruebas automatizadas.
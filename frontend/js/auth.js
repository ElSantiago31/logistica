/**
 * auth.js — Centraliza la autenticación del frontend.
 *
 * Resuelve el bug del "token expirado" durante eventos:
 *   - apiFetch(): wrapper de fetch que RENUEVA el access_token
 *     automáticamente (vía refresh_token) cuando recibe 401,
 *     y reintenta la petición original sin expulsar al usuario.
 *   - Refresh proactivo en background antes de que expire.
 *   - Cola anti-bucle: si hay un refresh en curso, las demás
 *     peticiones esperan a que termine (no se lanza más de uno).
 *
 * Cierre de sesión por inactividad (idle timeout):
 *   - Tras 15 min sin actividad, se cierra la sesión.
 *   - Aviso previo a los 13 min con botón "Seguir activo".
 *   - Sliding session: el refresh proactivo NO renueva si el
 *     usuario está inactivo, para que los 15 min realmente cierren.
 *
 * Uso (reemplaza fetch en las páginas):
 *   const res = await Auth.apiFetch('/api/sync/events/.../check-in', {
 *       method: 'POST',
 *       headers: Auth.authHeaders(),  // opcional, apiFetch ya lo añade
 *       body: JSON.stringify(payload)
 *   });
 *
 * Cargar con:
 *   <script src="/static/js/auth.js"></script>
 */
(function () {
    'use strict';

    const ACCESS_KEY = 'access_token';
    const REFRESH_KEY = 'refresh_token';
    const USER_KEY = 'user';
    const TOKEN_TTL_MS = 30 * 60 * 1000;          // 30 min (debe coincidir con backend)
    const REFRESH_AHEAD_MS = 25 * 60 * 1000;      // refrescar a los 25 min
    const REFRESH_ENDPOINT = '/api/auth/refresh';

    // --- Cierre de sesión por inactividad (idle timeout) ---
    // PRODUCCIÓN: 15 min de inactividad → cierre de sesión.
    // Aviso a los 13 min (2 min antes) con countdown.
    const IDLE_LIMIT_MS = 15 * 60 * 1000;          // PRODUCCIÓN: 15 min
    const IDLE_WARNING_MS = 13 * 60 * 1000;        // PRODUCCIÓN: 13 min (aviso 2 min antes)
    const IDLE_CHECK_INTERVAL_MS = 15 * 1000;      // PRODUCCIÓN: 15s
    const IDLE_ACTIVITY_KEY = 'auth_last_activity';
    const IDLE_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart', 'pointerdown'];

    // --- Estado interno del refresh (singleton anti-bucle) ---
    let refreshPromise = null;        // Promise en curso (o null)
    let proactiveTimer = null;        // id del setTimeout de refresh proactivo
    let lastTokenIssuedAt = null;     // ms (Date.now()) del último login/refresh

    // --- Estado interno del idle timeout ---
    let idleTimer = null;             // id del setInterval de chequeo
    let warningCountdownTimer = null; // id del setInterval del countdown
    let lastTouchWriteAt = 0;         // throttle de escritura a localStorage
    let warningVisible = false;       // si el modal de aviso está en pantalla
    let idleTrackingStarted = false;  // idempotencia de startIdleTracking

    // ----------------------------------------------------------------
    //  Utilidades de almacenamiento
    // ----------------------------------------------------------------
    function getAccessToken() {
        return localStorage.getItem(ACCESS_KEY);
    }

    function getRefreshToken() {
        return localStorage.getItem(REFRESH_KEY);
    }

    function saveTokens(access, refresh) {
        if (access) {
            localStorage.setItem(ACCESS_KEY, access);
            lastTokenIssuedAt = Date.now();
            scheduleProactiveRefresh();
            // Iniciar el control de inactividad (idempotente).
            startIdleTracking();
        }
        if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    }

    function clearSession() {
        localStorage.removeItem(ACCESS_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
        // 🐛 FIX: limpiar la marca de actividad para que la próxima sesión
        // arranque con un contador fresco y no herede inactividad vieja.
        localStorage.removeItem(IDLE_ACTIVITY_KEY);
        lastTouchWriteAt = 0;
        if (proactiveTimer) {
            clearTimeout(proactiveTimer);
            proactiveTimer = null;
        }
        stopIdleTracking();
    }

    /**
     * Cabeceras de autorización listas para fetch.
     * Mantiene compatibilidad con authHeaders()/authH()/getToken() existentes.
     */
    function authHeaders(extra) {
        const h = Object.assign({}, extra || {});
        const t = getAccessToken();
        if (t) h['Authorization'] = 'Bearer ' + t;
        return h;
    }

    // ----------------------------------------------------------------
    //  Redirección de login (decide según la ruta actual)
    // ----------------------------------------------------------------
    function redirectToLogin() {
        const path = window.location.pathname || '';
        // Determinar si el usuario actual es operador (por user_type guardado)
        let isOperator = false;
        try {
            const user = JSON.parse(localStorage.getItem(USER_KEY) || '{}');
            isOperator = user && user.user_type === 'operator';
        } catch (e) { /* noop */ }

        let target;
        if (path.indexOf('/enrolamiento') === 0 || path.indexOf('/coordinator') === 0 || isOperator) {
            target = '/enrolamiento/login';
        } else {
            target = '/admin/login';
        }
        // Evitar bucle si ya estamos en el login
        if (path.indexOf(target) !== 0) {
            window.location.href = target;
        }
    }

    // ----------------------------------------------------------------
    //  Refresh del access_token (con cola anti-bucle)
    // ----------------------------------------------------------------
    /**
     * Renueva el access_token usando el refresh_token.
     * Si ya hay un refresh en curso, retorna la MISMA promesa (cola),
     * evitando peticiones duplicadas cuando varias llamadas fallan a la vez.
     * Devuelve true si se renovó, false si hay que re-loguear.
     */
    function doRefresh() {
        if (refreshPromise) return refreshPromise;

        const refreshToken = getRefreshToken();
        if (!refreshToken) {
            return Promise.resolve(false);
        }

        refreshPromise = fetch(REFRESH_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('refresh_failed_' + resp.status);
                return resp.json();
            })
            .then(function (data) {
                saveTokens(data.access_token, data.refresh_token);
                return true;
            })
            .catch(function (err) {
                console.warn('[auth] refresh fallido:', err && err.message);
                clearSession();
                return false;
            })
            .then(function (ok) {
                refreshPromise = null;
                return ok;
            });

        return refreshPromise;
    }

    // ----------------------------------------------------------------
    //  Refresh proactivo en background (con sliding session)
    // ----------------------------------------------------------------
    function scheduleProactiveRefresh() {
        if (proactiveTimer) clearTimeout(proactiveTimer);
        // Refrescar un poco antes de que expire
        const delay = REFRESH_AHEAD_MS + Math.floor(Math.random() * 10000); // jitter 0-10s
        proactiveTimer = setTimeout(function () {
            // SLIDING SESSION: solo renovar si el usuario está activo.
            // Si lleva inactivo cerca del límite de idle, NO refrescamos:
            // dejaremos que expire su token y el idle timeout cierre sesión.
            if (!isUserActive()) {
                console.info('[auth] refresh proactivo omitido por inactividad (sliding session)');
                return;
            }
            doRefresh().then(function (ok) {
                if (!ok) {
                    console.warn('[auth] refresh proactivo no pudo renovar; se reintentará en el próximo 401');
                }
            });
        }, delay);
    }

    // ----------------------------------------------------------------
    //  Cierre de sesión por inactividad (idle timeout)
    // ----------------------------------------------------------------
    /**
     * Marca de tiempo (ms) de la última actividad del usuario.
     * Se guarda en localStorage para sincronizar entre pestañas.
     */
    function getLastActivity() {
        const stored = parseInt(localStorage.getItem(IDLE_ACTIVITY_KEY), 10);
        return isNaN(stored) ? Date.now() : stored;
    }

    function touchActivity() {
        const now = Date.now();
        // Throttle: escribir a localStorage cada 5s como mucho
        if (now - lastTouchWriteAt > 5000) {
            localStorage.setItem(IDLE_ACTIVITY_KEY, String(now));
            lastTouchWriteAt = now;
        }
        // Si el aviso estaba visible y el usuario vuelve a interactuar, ocultarlo
        if (warningVisible) {
            hideIdleWarning();
        }
    }

    /**
     * Sliding session: ¿el usuario ha estado activo en los últimos minutos?
     * Consideramos "activo" si su última interacción es < IDLE_WARNING_MS.
     */
    function isUserActive() {
        return (Date.now() - getLastActivity()) < IDLE_WARNING_MS;
    }

    /**
     * ¿La página actual soporta modo offline?
     * Las páginas offline-capable declaran `window.OFFLINE_CAPABLE = true`.
     * En esas páginas, el idle timeout NO cierra sesión si no hay internet,
     * para no bloquear al coordinador en medio de un evento sin señal.
     */
    function isOfflineCapablePage() {
        return window.OFFLINE_CAPABLE === true;
    }

    /**
     * ¿Estamos actualmente sin conexión a internet?
     */
    function isOffline() {
        return navigator.onLine === false;
    }

    /**
     * Listener de actividad (registrado con {passive:true} para no bloquear scroll).
     */
    function activityListener() {
        touchActivity();
    }

    function startIdleTracking() {
        // Idempotente: si ya está corriendo, no duplicar listeners ni resetear
        // actividad. Esto es clave porque saveTokens() se llama en cada refresh.
        if (idleTrackingStarted) return;
        idleTrackingStarted = true;

        // 🐛 FIX: Si no hay marca de actividad previa (primera vez tras login)
        // O si la marca existente es stale (más vieja que el límite de idle,
        // producto de una sesión anterior que no limpió localStorage),
        // inicializarla AHORA para arrancar con contador fresco.
        const storedActivity = parseInt(localStorage.getItem(IDLE_ACTIVITY_KEY), 10);
        const isStale = isNaN(storedActivity) || (Date.now() - storedActivity) > IDLE_WARNING_MS;
        if (isStale) {
            const now = Date.now();
            localStorage.setItem(IDLE_ACTIVITY_KEY, String(now));
            lastTouchWriteAt = now;
        }

        // Listeners de actividad (passive para rendimiento móvil)
        IDLE_EVENTS.forEach(function (evt) {
            window.addEventListener(evt, activityListener, { passive: true });
        });

        // Chequeo periódico
        if (idleTimer) clearInterval(idleTimer);
        idleTimer = setInterval(checkIdle, IDLE_CHECK_INTERVAL_MS);

        // Sincronización entre pestañas: si otra pestaña cierra sesión, esta también
        window.addEventListener('storage', function (e) {
            if (e.key === ACCESS_KEY && !e.newValue) {
                // El access_token se eliminó en otra pestaña -> cerrar aquí también
                stopIdleTracking();
                redirectToLogin();
            }
        });
    }

    function stopIdleTracking() {
        idleTrackingStarted = false;
        if (idleTimer) {
            clearInterval(idleTimer);
            idleTimer = null;
        }
        if (warningCountdownTimer) {
            clearInterval(warningCountdownTimer);
            warningCountdownTimer = null;
        }
        IDLE_EVENTS.forEach(function (evt) {
            window.removeEventListener(evt, activityListener);
        });
        hideIdleWarning();
    }

    /**
     * Chequeo del estado de inactividad. Se ejecuta cada IDLE_CHECK_INTERVAL_MS.
     *  - Si inactivo >= IDLE_LIMIT_MS  -> cerrar sesión.
     *  - Si inactivo >= IDLE_WARNING_MS -> mostrar aviso (con countdown).
     */
    function checkIdle() {
        // No chequear si no hay sesión activa
        if (!getAccessToken()) return;

        const idleMs = Date.now() - getLastActivity();

        // 🛡️ PROTECCIÓN OFFLINE: si no hay internet y la página soporta
        // modo offline (check-in, nómina, intendencia), NO cerrar sesión.
        // El coordinador podría estar en medio de un evento sin señal y
        // un logout lo dejaría bloqueado sin poder re-loguearse.
        if (idleMs >= IDLE_WARNING_MS && isOffline() && isOfflineCapablePage()) {
            if (warningVisible) hideIdleWarning();
            console.info('[auth] idle pausado: offline + página offline-capable (' + Math.round(idleMs / 1000) + 's)');
            return;
        }

        if (idleMs >= IDLE_LIMIT_MS) {
            // Antes de cerrar, última verificación offline (por si acaba de caer la red)
            if (isOffline() && isOfflineCapablePage()) {
                if (warningVisible) hideIdleWarning();
                console.info('[auth] logout evitado por offline (' + Math.round(idleMs / 1000) + 's)');
                return;
            }
            // Tiempo agotado: cerrar sesión
            hideIdleWarning();
            console.info('[auth] cierre de sesión por inactividad (' + Math.round(idleMs / 1000) + 's)');
            logout();
            return;
        }

        if (idleMs >= IDLE_WARNING_MS && !warningVisible) {
            // No mostrar aviso si estamos offline en página offline-capable
            if (isOffline() && isOfflineCapablePage()) return;
            showIdleWarning();
        }
    }

    // ----------------------------------------------------------------
    //  Modal de aviso de inactividad
    // ----------------------------------------------------------------
    function showIdleWarning() {
        if (warningVisible) return;
        // No mostrar en páginas de login (no tendría sentido)
        const path = window.location.pathname || '';
        if (path.indexOf('/login') !== -1) return;

        warningVisible = true;

        // Conteo regresivo inicial (desde el límite hasta ahora)
        const secondsLeft = Math.max(1, Math.round((IDLE_LIMIT_MS - (Date.now() - getLastActivity())) / 1000));

        // Construir el modal
        const overlay = document.createElement('div');
        overlay.id = 'auth-idle-overlay';
        overlay.style.cssText = [
            'position:fixed', 'inset:0', 'z-index:99999',
            'background:rgba(0,0,0,0.5)', 'display:flex',
            'align-items:center', 'justify-content:center',
            'padding:1rem'
        ].join(';');

        const modal = document.createElement('div');
        modal.style.cssText = [
            'background:#fff', 'border-radius:0.75rem', 'padding:1.5rem',
            'max-width:24rem', 'width:100%', 'text-align:center',
            'box-shadow:0 20px 25px -5px rgba(0,0,0,0.2)',
            'font-family:inherit'
        ].join(';');

        modal.innerHTML =
            '<div style="font-size:2.25rem;margin-bottom:0.5rem;">⏰</div>' +
            '<h3 style="font-size:1.125rem;font-weight:700;color:#111827;margin:0 0 0.5rem;">¿Sigues ahí?</h3>' +
            '<p style="color:#6B7280;font-size:0.875rem;margin:0 0 1rem;">Tu sesión se cerrará por inactividad en</p>' +
            '<div id="auth-idle-countdown" style="font-size:2rem;font-weight:700;color:#DC2626;margin-bottom:1rem;">' + secondsLeft + 's</div>' +
            '<button id="auth-idle-extend" type="button" style="width:100%;background:#2563EB;color:#fff;font-weight:600;border:none;border-radius:0.5rem;padding:0.625rem 1rem;cursor:pointer;font-size:0.875rem;">Seguir activo</button>';

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // Botón "Seguir activo": extiende la sesión
        document.getElementById('auth-idle-extend').addEventListener('click', function () {
            extendSession();
        });

        // Countdown cada 1s
        let remaining = secondsLeft;
        warningCountdownTimer = setInterval(function () {
            remaining--;
            const el = document.getElementById('auth-idle-countdown');
            if (el) el.textContent = Math.max(0, remaining) + 's';
            // Cuando llegue a 0, el checkIdle cerrará la sesión en el próximo tick
        }, 1000);
    }

    function hideIdleWarning() {
        if (warningCountdownTimer) {
            clearInterval(warningCountdownTimer);
            warningCountdownTimer = null;
        }
        const overlay = document.getElementById('auth-idle-overlay');
        if (overlay && overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
        warningVisible = false;
    }

    /**
     * Extiende la sesión: marca actividad y refresca el token si conviene.
     */
    function extendSession() {
        const now = Date.now();
        localStorage.setItem(IDLE_ACTIVITY_KEY, String(now));
        lastTouchWriteAt = now;
        hideIdleWarning();
        // Renovar el access token para asegurar 30 min frescos
        doRefresh();
    }

    // ----------------------------------------------------------------
    //  apiFetch — el wrapper principal
    // ----------------------------------------------------------------
    /**
     * Como fetch, pero:
     *   1. Inyecta Authorization automáticamente (si no se pasó).
     *   2. Si recibe 401, intenta UN refresh y reintenta la petición.
     *   3. Si el refresh también falla, limpia sesión y redirige a login.
     *
     * @param {string} url
     * @param {object} options - igual que fetch
     * @param {boolean} [options._retried] - uso interno (evita loop infinito)
     */
    function apiFetch(url, options) {
        options = options || {};
        // Inyectar Authorization si no está
        if (!options.headers || !options.headers['Authorization']) {
            options.headers = authHeaders(options.headers);
        }
        // flag para no reintentar más de una vez
        const retried = options._retried === true;
        const cleanOptions = Object.assign({}, options);
        delete cleanOptions._retried;

        return fetch(url, cleanOptions).then(function (resp) {
            if (resp.status !== 401) return resp;

            // 401 -> intentar refresh y reintentar una sola vez
            if (retried) {
                // Ya reintentamos antes y volvió a dar 401: sesión muerta
                clearSession();
                redirectToLogin();
                // Devolvemos el resp original para que no rompa quien no usa await
                return resp;
            }

            return doRefresh().then(function (ok) {
                if (!ok) {
                    clearSession();
                    redirectToLogin();
                    return resp;
                }
                // Refresh OK: reintentar con el nuevo token
                const retryOpts = Object.assign({}, cleanOptions, {
                    headers: authHeaders(cleanOptions.headers),
                    _retried: true,
                });
                return apiFetch(url, retryOpts);
            });
        });
    }

    // ----------------------------------------------------------------
    //  Interceptor GLOBAL de window.fetch
    // ----------------------------------------------------------------
    /**
     * Monkey-patch de window.fetch para que TODA llamada a /api/...
     * (hecha con fetch normal) tenga el mismo comportamiento que apiFetch:
     *   - inyecta Authorization automáticamente
     *   - si recibe 401, refresca el token y reintenta UNA vez
     *
     * Esto arregla de golpe las ~68 llamadas fetch existentes en las
     * plantillas sin tener que refactorizar cada una.
     *
     * Exclusiones:
     *   - El propio endpoint de refresh (evita bucle infinito)
     *   - Endpoints públicos de auth (login, register, forgot-password)
     *   - Llamadas que ya incluyen Authorization (no se duplica)
     *   - Llamadas marcadas con { _skipInterceptor: true }
     */
    function shouldIntercept(url) {
        if (typeof url !== 'string') return false;
        // Solo rutas internas /api/...
        if (url.indexOf('/api/') !== 0 && url.indexOf(window.location.origin + '/api/') !== 0) {
            return false;
        }
        // Excluir el propio refresh (y logout para no encajar en 401)
        const lower = url.toLowerCase();
        if (lower.indexOf('/api/auth/refresh') !== -1) return false;
        if (lower.indexOf('/api/auth/login') !== -1) return false;
        if (lower.indexOf('/api/auth/register') !== -1) return false;
        if (lower.indexOf('/api/auth/forgot-password') !== -1) return false;
        if (lower.indexOf('/api/auth/reset-password') !== -1) return false;
        return true;
    }

    function installFetchInterceptor() {
        if (window.__authFetchPatched) return;   // idempotente
        const originalFetch = window.fetch.bind(window);
        window.__authFetchPatched = true;

        window.fetch = function (input, init) {
            init = init || {};
            const url = (typeof input === 'string') ? input : (input && input.url) || '';
            const skip = init._skipInterceptor === true;

            // Si no es ruta a interceptar, pasar de largo sin tocar
            if (!shouldIntercept(url) || skip) {
                // Limpiar flag interna para no enviarla al backend
                if (init._skipInterceptor !== undefined) {
                    const c = Object.assign({}, init);
                    delete c._skipInterceptor;
                    return originalFetch(input, c);
                }
                return originalFetch(input, init);
            }

            // Inyectar Authorization si no está presente
            const headers = new Headers(init.headers || (input && input.headers) || {});
            if (!headers.has('Authorization')) {
                const t = getAccessToken();
                if (t) headers.set('Authorization', 'Bearer ' + t);
            }
            // Normalizar init con las cabeceras nuevas
            const newInit = Object.assign({}, init, { headers: headers });
            delete newInit._skipInterceptor;

            const retried = init._retried === true;

            return originalFetch(input, newInit).then(function (resp) {
                if (resp.status !== 401) return resp;

                if (retried) {
                    clearSession();
                    redirectToLogin();
                    return resp;
                }

                // 401 -> refresh + un reintento
                return doRefresh().then(function (ok) {
                    if (!ok) {
                        clearSession();
                        redirectToLogin();
                        return resp;
                    }
                    // Reintentar con el nuevo token
                    const retryHeaders = new Headers(init.headers || {});
                    retryHeaders.set('Authorization', 'Bearer ' + getAccessToken());
                    const retryInit = Object.assign({}, init, {
                        headers: retryHeaders,
                        _retried: true,
                    });
                    return window.fetch(input, retryInit);
                });
            });
        };
    }

    // ----------------------------------------------------------------
    //  Logout seguro (revoca en backend antes de limpiar)
    // ----------------------------------------------------------------
    function logout() {
        // El backend revoca por jti; intentamos best-effort y siempre limpiamos.
        const access = getAccessToken();
        const refresh = getRefreshToken();
        clearSession();

        // Best-effort: revocar el refresh_token (no bloquea el logout local)
        try {
            if (refresh) {
                fetch(REFRESH_ENDPOINT.replace('/refresh', '/logout'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                }).catch(function () { /* noop */ });
            }
        } catch (e) { /* noop */ }

        redirectToLogin();
    }

    // ----------------------------------------------------------------
    //  Inicialización al cargar el módulo
    // ----------------------------------------------------------------
    function init() {
        // Instalar el interceptor global ANTES de que carguen los scripts
        // de las páginas (que usan fetch). Debe ir lo antes posible.
        installFetchInterceptor();

        // Si hay sesión activa, programar el refresh proactivo
        if (getAccessToken()) {
            // No sabemos cuándo se emitió el token exactamente; asumir "recién"
            // para no rearmar un timer equivocado. El refresh reactivo (401)
            // cubre cualquier desfase.
            lastTokenIssuedAt = Date.now();
            scheduleProactiveRefresh();
            // Iniciar el control de inactividad (cierre a los 15 min)
            startIdleTracking();
        }

        // 🛡️ Listeners de conectividad: al volver internet, refrescar el
        // token silenciosamente (pudo expirar durante el offline) y reanudar
        // el control de inactividad normal.
        window.addEventListener('online', function () {
            console.info('[auth] conexión restablecida — refrescando sesión');
            if (getAccessToken()) {
                // Marcar actividad para no disparar el idle justo al volver
                touchActivity();
                // Refrescar silenciosamente (best-effort, no bloquea)
                doRefresh().then(function (ok) {
                    if (ok) console.info('[auth] token refrescado tras reconexión');
                });
            }
        });

        window.addEventListener('offline', function () {
            console.info('[auth] sin conexión — protección offline activa en páginas offline-capable');
        });
    }

    // --- API pública ---
    window.Auth = {
        apiFetch: apiFetch,
        authHeaders: authHeaders,
        getToken: getAccessToken,
        getRefreshToken: getRefreshToken,
        saveTokens: saveTokens,
        clearSession: clearSession,
        doRefresh: doRefresh,
        logout: logout,
        redirectToLogin: redirectToLogin,
        scheduleProactiveRefresh: scheduleProactiveRefresh,
        startIdleTracking: startIdleTracking,
        extendSession: extendSession,
    };

    init();
})();
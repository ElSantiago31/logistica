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

    // --- Estado interno del refresh (singleton anti-bucle) ---
    let refreshPromise = null;        // Promise en curso (o null)
    let proactiveTimer = null;        // id del setTimeout de refresh proactivo
    let lastTokenIssuedAt = null;     // ms (Date.now()) del último login/refresh

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
        }
        if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    }

    function clearSession() {
        localStorage.removeItem(ACCESS_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
        if (proactiveTimer) {
            clearTimeout(proactiveTimer);
            proactiveTimer = null;
        }
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
        let target;
        if (path.indexOf('/enrolamiento') === 0 || path.indexOf('/coordinator') === 0) {
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
    //  Refresh proactivo en background
    // ----------------------------------------------------------------
    function scheduleProactiveRefresh() {
        if (proactiveTimer) clearTimeout(proactiveTimer);
        // Refrescar un poco antes de que expire
        const delay = REFRESH_AHEAD_MS + Math.floor(Math.random() * 10000); // jitter 0-10s
        proactiveTimer = setTimeout(function () {
            doRefresh().then(function (ok) {
                if (!ok) {
                    // No redirigir automáticamente aquí: el siguiente apiFetch
                    // lo hará si realmente hace falta. Así evitamos expulsar
                    // a quien tiene la pestaña abierta sin estar activo.
                    console.warn('[auth] refresh proactivo no pudo renovar; se reintentará en el próximo 401');
                }
            });
        }, delay);
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
        }
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
    };

    init();
})();
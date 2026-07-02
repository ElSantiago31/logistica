/**
 * ws.js — Cliente WebSocket en tiempo real para el panel logístico.
 *
 * Reemplaza el polling cada 5s por una conexión WebSocket persistente que
 * recibe push notifications del servidor cuando hay cambios (check-in,
 * devolución de indumentaria, firma/pago de nómina, etc.).
 *
 * Características:
 *   - Reconexión automática con backoff exponencial (1s → 30s).
 *   - Heartbeat: responde "pong" al "ping" del servidor cada 25s.
 *   - Reanuda al volver a la pestaña (visibilitychange).
 *   - Dispatcher de eventos por tipo (handlers callback).
 *   - Fallback graceful: si WS falla, no rompe la página.
 *
 * Uso típico (en checkin.html / intendencia.html / payroll.html):
 *
 *   const rt = new RealTimeClient(eventId, 'checkin', {
 *     onMessage: (msg) => {
 *       if (msg.type === 'checkin') actualizarFila(msg.data);
 *     },
 *     onStatusChange: (online) => mostrarIndicador(online),
 *   });
 *   rt.connect();
 *   // ...al salir de la página:
 *   rt.disconnect();
 *
 * Endpoint backend: /ws/{event_id}?token=<jwt>&channel=<checkin|intendencia|payroll>
 */
(function () {
  'use strict';

  /** Obtiene el access_token de cualquiera de los dos orígenes posibles. */
  function getToken() {
    try {
      // auth.js expone window.Auth.getToken()
      if (window.Auth && typeof window.Auth.getToken === 'function') {
        return window.Auth.getToken();
      }
    } catch (_) { /* noop */ }
    try {
      return localStorage.getItem('access_token');
    } catch (_) {
      return null;
    }
  }

  /**
   * Construye la URL WebSocket absoluta.
   * - Mismo host que la página (http→ws, https→wss).
   * - Soporta dev local con Vite en otro puerto (VITE_WS_URL).
   */
  function buildWsUrl(eventId, channel) {
    const token = getToken();
    const params = new URLSearchParams({
      channel: channel || 'checkin',
    });
    if (token) params.set('token', token);

    // Override explícito (dev local con proxy/Vite)
    const override = (window.VITE_WS_URL || window.WS_BASE_URL || '').trim();
    if (override) {
      return `${override.replace(/\/$/, '')}/ws/${eventId}?${params.toString()}`;
    }

    // Mismo origen que la página actual
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/ws/${eventId}?${params.toString()}`;
  }

  /**
   * Cliente WebSocket con reconexión automática.
   */
  class RealTimeClient {
    /**
     * @param {string} eventId   UUID del evento.
     * @param {string} channel   'checkin' | 'intendencia' | 'payroll'.
     * @param {object} handlers  { onMessage(msg), onStatusChange(online), onConnect(), onDisconnect() }
     */
    constructor(eventId, channel, handlers) {
      this.eventId = String(eventId);
      this.channel = channel || 'checkin';
      this.handlers = handlers || {};

      this.ws = null;
      this.isManualClose = false;
      this.isConnected = false;

      // Backoff exponencial
      this.retryCount = 0;
      this.retryTimer = null;
      this.maxRetry = 30000; // tope de 30s entre reintentos

      // Heartbeat
      this.pongTimer = null;

      // Reconnect on visibility
      this._onVisibility = this._onVisibility.bind(this);
    }

    /** Conecta al servidor WS. Idempotente. */
    connect() {
      if (this.ws && (this.ws.readyState === WebSocket.OPEN ||
                      this.ws.readyState === WebSocket.CONNECTING)) {
        return;
      }
      this.isManualClose = false;

      let url;
      try {
        url = buildWsUrl(this.eventId, this.channel);
      } catch (exc) {
        console.error('[ws] no se pudo construir URL:', exc);
        this._scheduleRetry();
        return;
      }

      try {
        this.ws = new WebSocket(url);
      } catch (exc) {
        console.error('[ws] no se pudo crear WebSocket:', exc);
        this._scheduleRetry();
        return;
      }

      this.ws.onopen = this._onOpen.bind(this);
      this.ws.onmessage = this._onMessage.bind(this);
      this.ws.onclose = this._onClose.bind(this);
      this.ws.onerror = this._onError.bind(this);
    }

    /** Desconexión definitiva (no reintenta). */
    disconnect() {
      this.isManualClose = true;
      this._clearRetry();
      this._clearPong();
      document.removeEventListener('visibilitychange', this._onVisibility);
      if (this.ws) {
        try { this.ws.close(1000, 'bye'); } catch (_) { /* noop */ }
        this.ws = null;
      }
      this._setStatus(false);
    }

    /** Envía un texto por el socket (si está abierto). */
    send(text) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try { this.ws.send(text); } catch (_) { /* noop */ }
      }
    }

    // --------------------------------------------------------------
    // Handlers internos
    // --------------------------------------------------------------

    _onOpen() {
      console.info('[ws] conectado event=%s channel=%s', this.eventId, this.channel);
      this.retryCount = 0;
      this._setStatus(true);
      if (typeof this.handlers.onConnect === 'function') {
        try { this.handlers.onConnect(); } catch (exc) { console.error('[ws] onConnect:', exc); }
      }
      // Escuchar visibilidad para reconectar al volver a la pestaña
      document.removeEventListener('visibilitychange', this._onVisibility);
      document.addEventListener('visibilitychange', this._onVisibility);
    }

    _onMessage(event) {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (exc) {
        // Mensaje no-JSON (raro): ignorar
        return;
      }

      // Heartbeat del servidor
      if (msg.type === 'ping') {
        this.send('pong');
        this._clearPong();
        // Si no llega otro ping en ~35s, forzar reconexión
        this.pongTimer = setTimeout(() => {
          console.warn('[ws] heartbeat perdido, reconectando...');
          try { this.ws.close(); } catch (_) { /* noop */ }
        }, 35000);
        return;
      }

      // Mensaje de cualquier otro tipo → dispatch
      if (typeof this.handlers.onMessage === 'function') {
        try { this.handlers.onMessage(msg); } catch (exc) {
          console.error('[ws] error en onMessage:', exc);
        }
      }
    }

    _onClose(event) {
      this._clearPong();
      this._setStatus(false);
      if (typeof this.handlers.onDisconnect === 'function') {
        try { this.handlers.onDisconnect(event); } catch (_) { /* noop */ }
      }
      // 4401 = token inválido → no reintentar (la página debe redirigir a login)
      if (event.code === 4401) {
        console.warn('[ws] token inválido/expirado (4401). No se reconecta.');
        this.isManualClose = true;
        // auth.js detectará el 401 en el siguiente fetch y limpiará sesión
        return;
      }
      // 4400 = canal/event_id inválido → no reintentar
      if (event.code === 4400) {
        console.warn('[ws] parámetros inválidos (4400). No se reconecta.');
        this.isManualClose = true;
        return;
      }
      if (!this.isManualClose) {
        this._scheduleRetry();
      }
    }

    _onError(event) {
      console.warn('[ws] error de conexión:', event);
      // onclose se invocará a continuación y agendará reintento
    }

    _onVisibility() {
      if (document.visibilityState === 'visible' && !this.isConnected) {
        console.info('[ws] pestaña visible, reconectando...');
        this.retryCount = 0;
        this._clearRetry();
        this.connect();
      }
    }

    // --------------------------------------------------------------
    // Utilidades internas
    // --------------------------------------------------------------

    _scheduleRetry() {
      this._clearRetry();
      // Backoff exponencial: 1s, 2s, 4s, 8s, 16s, 30s, 30s...
      const delay = Math.min(1000 * Math.pow(2, this.retryCount), this.maxRetry);
      this.retryCount += 1;
      console.info('[ws] reintentando en %dms (intento #%d)', delay, this.retryCount);
      this.retryTimer = setTimeout(() => this.connect(), delay);
    }

    _clearRetry() {
      if (this.retryTimer) {
        clearTimeout(this.retryTimer);
        this.retryTimer = null;
      }
    }

    _clearPong() {
      if (this.pongTimer) {
        clearTimeout(this.pongTimer);
        this.pongTimer = null;
      }
    }

    _setStatus(online) {
      this.isConnected = !!online;
      if (typeof this.handlers.onStatusChange === 'function') {
        try { this.handlers.onStatusChange(this.isConnected); } catch (_) { /* noop */ }
      }
    }
  }

  // Exportar globalmente
  window.RealTimeClient = RealTimeClient;
  // Helper rápido para no instanciar a mano en cada página
  window.RealTime = {
    /**
     * Crea y conecta un cliente en una sola llamada.
     * @returns {RealTimeClient}
     */
    connect: function (eventId, channel, handlers) {
      const client = new RealTimeClient(eventId, channel, handlers);
      client.connect();
      return client;
    },
  };
})();
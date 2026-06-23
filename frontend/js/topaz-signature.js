/**
 * ============================================================
 * TopazSignaturePad — Wrapper configurable para pad de firmas Topaz
 * ============================================================
 *
 * Diseñado para conectar el modal de nómina con un pad de firmas
 * físico (Topaz SignatureGem / SigLite) vía un puente local.
 *
 * El puente por defecto es SigPlus Ext Lite (WebSocket en localhost).
 * Cuando se defina el modelo/software exacto del pad, solo se ajusta
 * TOPAZ_CONFIG y/o el método _buildUrl() / _handleMessage() — la UI
 * no necesita cambios.
 *
 * USO:
 *   const pad = new TopazSignaturePad({
 *       onStatus: (state, msg) => { ... },
 *       onSign: (base64Png) => { ... },
 *   });
 *   await pad.connect();      // intenta conectar al puente
 *   pad.startCapture();       // pide al pad empezar a capturar
 *   const sig = await pad.captureDone();  // lee la firma → base64 PNG
 *   pad.clearPad();           // limpia pantalla del pad físico
 *   pad.disconnect();
 *
 * ESTADOS (state):
 *   - 'idle'        : sin inicializar
 *   - 'connecting'  : intentando conectar al puente
 *   - 'ready'       : pad conectado y listo para firmar
 *   - 'signing'     : el operador está firmando (trazo en vivo)
 *   - 'captured'    : firma capturada, lista para confirmar
 *   - 'error'       : error de conexión o del pad
 *   - 'disconnected': se desconectó el puente/pad
 * ============================================================
 */

// ============================================================
// CONFIGURACIÓN — AJUSTAR cuando se tenga el modelo Topaz definitivo
// ============================================================
const TOPAZ_CONFIG = {
    enabled: true,                   // false = desactiva el pad, la UI usará canvas
    protocol: window.location.protocol === 'https:' ? 'wss' : 'ws',
    host: '127.0.0.1',               // puente local SigPlus Ext Lite
    port: 9000,                      // puerto por defecto SigPlus Ext Lite
    endpoint: '/signatures',         // endpoint del puente
    model: 'SignatureGem_LCD_1x5',   // placeholder — ajustar al modelo real
    autoReconnect: true,
    reconnectDelayMs: 3000,
    connectTimeoutMs: 3000,          // si no conecta en 3s → la UI ofrece canvas
    // Comandos del protocolo SigPlus (se ajustan según el software real)
    commands: {
        startCapture: { action: 'startCapture' },
        stopCapture: { action: 'stopCapture' },
        getSignature: { action: 'getSignature', format: 'png' },
        clearPad: { action: 'clear' },
        getPadInfo: { action: 'getInfo' },
    },
};


class TopazSignaturePad {
    /**
     * @param {Object} callbacks
     * @param {Function} [callbacks.onStatus]  (state: string, message: string) => void
     * @param {Function} [callbacks.onPoint]    (point: {x,y,pressure,isStart}) => void  — trazo en vivo
     * @param {Function} [callbacks.onSign]     (base64Png: string) => void  — firma completa
     * @param {Function} [callbacks.onError]    (error: string) => void
     */
    constructor(callbacks = {}) {
        this.callbacks = callbacks;
        this.ws = null;
        this.state = 'idle';
        this._reconnectTimer = null;
        this._connectTimeout = null;
        this._pendingRequests = new Map();
        this._reqId = 0;
        this._lastSignature = null;

        this._setStatus('idle', 'Pad no inicializado');
    }

    // ============================================================
    // CONEXIÓN
    // ============================================================

    /**
     * Intenta conectar al puente local del pad Topaz.
     * @returns {Promise<boolean>} true si conectó, false si timeout/error
     */
    connect() {
        return new Promise((resolve) => {
            if (!TOPAZ_CONFIG.enabled) {
                this._setStatus('error', 'Pad Topaz desactivado en configuración');
                resolve(false);
                return;
            }

            // Si ya está conectado, resolver inmediatamente
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this._setStatus('ready', 'Pad listo');
                resolve(true);
                return;
            }

            // Limpiar conexión previa
            this._cleanupSocket();

            const url = this._buildUrl();
            this._setStatus('connecting', `Conectando a ${url}...`);

            // Timeout: si no conecta en X segundos, fallar y ofrecer canvas
            this._connectTimeout = setTimeout(() => {
                if (this.state === 'connecting') {
                    this._setStatus('error', 'Pad no detectado — usa Dibujar (canvas)');
                    this._cleanupSocket();
                    resolve(false);
                }
            }, TOPAZ_CONFIG.connectTimeoutMs);

            try {
                this.ws = new WebSocket(url);
            } catch (err) {
                this._setStatus('error', 'No se pudo crear conexión WebSocket');
                clearTimeout(this._connectTimeout);
                resolve(false);
                return;
            }

            this.ws.onopen = () => {
                clearTimeout(this._connectTimeout);
                this._setStatus('ready', '🟢 Pad conectado — listo para firmar');
                resolve(true);
            };

            this.ws.onmessage = (event) => {
                this._handleMessage(event);
            };

            this.ws.onerror = () => {
                clearTimeout(this._connectTimeout);
                if (this.state !== 'error') {
                    this._setStatus('error', 'Error de conexión con el pad');
                }
                resolve(false);
            };

            this.ws.onclose = () => {
                if (this.state !== 'error' && this.state !== 'disconnected') {
                    this._setStatus('disconnected', 'Pad desconectado');
                    // Auto-reconectar si está habilitado
                    if (TOPAZ_CONFIG.autoReconnect) {
                        this._scheduleReconnect();
                    }
                }
            };
        });
    }

    /**
     * Cierra la conexión con el pad.
     */
    disconnect() {
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        this._cleanupSocket();
        this._setStatus('disconnected', 'Desconectado');
    }

    _cleanupSocket() {
        if (this._connectTimeout) {
            clearTimeout(this._connectTimeout);
            this._connectTimeout = null;
        }
        if (this.ws) {
            this.ws.onopen = null;
            this.ws.onmessage = null;
            this.ws.onerror = null;
            this.ws.onclose = null;
            try { this.ws.close(); } catch (e) { /* ignore */ }
            this.ws = null;
        }
    }

    _scheduleReconnect() {
        if (this._reconnectTimer) return;
        this._setStatus('connecting', `Reconectando en ${TOPAZ_CONFIG.reconnectDelayMs / 1000}s...`);
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, TOPAZ_CONFIG.reconnectDelayMs);
    }

    /**
     * Construye la URL del WebSocket del puente local.
     * Ajustar si el software del pad usa otro esquema.
     */
    _buildUrl() {
        return `${TOPAZ_CONFIG.protocol}://${TOPAZ_CONFIG.host}:${TOPAZ_CONFIG.port}${TOPAZ_CONFIG.endpoint}`;
    }

    // ============================================================
    // CAPTURA DE FIRMA
    // ============================================================

    /**
     * Pide al pad empezar a capturar la firma del operador.
     * A partir de aquí, el operador firma en el pad físico.
     */
    startCapture() {
        if (!this._isReady()) return;
        this._setStatus('signing', 'Firme en el pad...');
        this._lastSignature = null;
        this._send(TOPAZ_CONFIG.commands.startCapture);
    }

    /**
     * Lee la firma capturada del pad y la retorna como base64 PNG.
     * Se llama cuando el operador termina de firmar (botón check).
     * @returns {Promise<string|null>} base64 PNG o null si no hay firma
     */
    captureDone() {
        return new Promise((resolve) => {
            if (!this._isReady()) {
                resolve(null);
                return;
            }

            const reqId = ++this._reqId;
            const payload = { ...TOPAZ_CONFIG.commands.getSignature, reqId };

            this._pendingRequests.set(reqId, (data) => {
                this._send(TOPAZ_CONFIG.commands.stopCapture);
                if (data && data.signature) {
                    // El puente retorna la firma como base64
                    let sig = data.signature;
                    if (!sig.startsWith('data:image')) {
                        sig = 'data:image/png;base64,' + sig;
                    }
                    this._lastSignature = sig;
                    this._setStatus('captured', '✅ Firma capturada');
                    if (this.callbacks.onSign) this.callbacks.onSign(sig);
                    resolve(sig);
                } else {
                    this._setStatus('ready', 'No se detectó firma en el pad');
                    resolve(null);
                }
            });

            this._send(payload);

            // Timeout de seguridad: si el pad no responde en 10s
            setTimeout(() => {
                if (this._pendingRequests.has(reqId)) {
                    this._pendingRequests.delete(reqId);
                    this._setStatus('error', 'Timeout esperando firma del pad');
                    resolve(null);
                }
            }, 10000);
        });
    }

    /**
     * Limpia la pantalla del pad físico para la siguiente firma.
     */
    clearPad() {
        if (!this._isReady()) return;
        this._lastSignature = null;
        this._send(TOPAZ_CONFIG.commands.clearPad);
        this._setStatus('ready', 'Pad limpiado — listo para firmar');
    }

    /**
     * Retorna la última firma capturada (base64 PNG) sin releer el pad.
     */
    getLastSignature() {
        return this._lastSignature;
    }

    // ============================================================
    // MANEJO DE MENSAJES DEL PUENTE
    // ============================================================

    /**
     * Procesa los mensajes entrantes del WebSocket del puente.
     * Formato esperado (SigPlus Ext Lite / configurable):
     *   { "type": "point", "x": 123, "y": 45, "pressure": 0.8 }
     *   { "type": "signature", "reqId": 1, "signature": "<base64>" }
     *   { "type": "info", "model": "SignatureGem LCD 1x5", "firmware": "1.0" }
     *
     * Cuando se conozca el protocolo exacto del pad, ajustar aquí.
     */
    _handleMessage(event) {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            // Si no es JSON, podría ser un mensaje binario (bitmap crudo)
            // — manejar según el software del pad real
            return;
        }

        if (!data || !data.type) return;

        switch (data.type) {
            case 'point':
                // Trazo en vivo — el operador está firmando
                if (this.callbacks.onPoint) {
                    this.callbacks.onPoint({
                        x: data.x,
                        y: data.y,
                        pressure: data.pressure || 1.0,
                        isStart: !!data.isStart,
                    });
                }
                if (this.state !== 'signing') {
                    this._setStatus('signing', 'Firmando...');
                }
                break;

            case 'signature':
                // Respuesta a getSignature
                if (data.reqId && this._pendingRequests.has(data.reqId)) {
                    const cb = this._pendingRequests.get(data.reqId);
                    this._pendingRequests.delete(data.reqId);
                    cb(data);
                }
                break;

            case 'info':
                // Información del pad (modelo, firmware)
                if (data.model) {
                    this._setStatus(this.state, `Pad: ${data.model}`);
                }
                break;

            case 'error':
                this._setStatus('error', data.message || 'Error del pad');
                if (this.callbacks.onError) this.callbacks.onError(data.message);
                break;
        }
    }

    // ============================================================
    // UTILIDADES
    // ============================================================

    _isReady() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this._setStatus('error', 'Pad no conectado');
            return false;
        }
        return true;
    }

    _send(payload) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        try {
            this.ws.send(JSON.stringify(payload));
        } catch (e) {
            this._setStatus('error', 'Error enviando comando al pad');
        }
    }

    _setStatus(state, message) {
        this.state = state;
        if (this.callbacks.onStatus) {
            this.callbacks.onStatus(state, message);
        }
    }

    /**
     * Verifica si el pad está conectado y listo.
     */
    isReady() {
        return this.state === 'ready' || this.state === 'signing' || this.state === 'captured';
    }

    /**
     * Verifica si hubo un error de conexión (para que la UI ofrezca canvas).
     */
    hasError() {
        return this.state === 'error' || this.state === 'disconnected';
    }
}


// Exportar para uso global (no-module, compatible con Jinja2 templates)
window.TOPAZ_CONFIG = TOPAZ_CONFIG;
window.TopazSignaturePad = TopazSignaturePad;
/**
 * signature.js — Digital signature pad for AyC Eventos PWA
 * Canvas-based signature capture with SHA-256 hash for integrity.
 */
/* global crypto */

class SignaturePad {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.isDrawing = false;
        this.isEmpty = true;
        this.lineWidth = options.lineWidth || 2;
        this.strokeColor = options.strokeColor || '#1a1a1a';
        this.bgColor = options.bgColor || '#ffffff';
        
        this._init();
    }
    
    _init() {
        // Resize canvas to container
        this._resize();
        window.addEventListener('resize', () => this._resize());
        
        // Mouse events
        this.canvas.addEventListener('mousedown', e => this._startDraw(e));
        this.canvas.addEventListener('mousemove', e => this._draw(e));
        this.canvas.addEventListener('mouseup', () => this._endDraw());
        this.canvas.addEventListener('mouseleave', () => this._endDraw());
        
        // Touch events
        this.canvas.addEventListener('touchstart', e => { e.preventDefault(); this._startDraw(e.touches[0]); });
        this.canvas.addEventListener('touchmove', e => { e.preventDefault(); this._draw(e.touches[0]); });
        this.canvas.addEventListener('touchend', () => this._endDraw());
        
        this.clear();
    }
    
    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = 200;
        this.clear();
    }
    
    _startDraw(e) {
        this.isDrawing = true;
        const pos = this._getPos(e);
        this.ctx.beginPath();
        this.ctx.moveTo(pos.x, pos.y);
    }
    
    _draw(e) {
        if (!this.isDrawing) return;
        this.isEmpty = false;
        const pos = this._getPos(e);
        this.ctx.lineWidth = this.lineWidth;
        this.ctx.lineCap = 'round';
        this.ctx.strokeStyle = this.strokeColor;
        this.ctx.lineTo(pos.x, pos.y);
        this.ctx.stroke();
    }
    
    _endDraw() {
        this.isDrawing = false;
    }
    
    _getPos(e) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: (e.clientX || e.pageX) - rect.left,
            y: (e.clientY || e.pageY) - rect.top
        };
    }
    
    // Clear the pad
    clear() {
        this.ctx.fillStyle = this.bgColor;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        this.isEmpty = true;
    }
    
    // Get signature as base64 PNG
    toDataURL() {
        return this.canvas.toDataURL('image/png');
    }
    
    // Get signature as Blob
    async toBlob() {
        return new Promise(resolve => {
            this.canvas.toBlob(blob => resolve(blob), 'image/png');
        });
    }
    
    // Generate SHA-256 hash of signature data for integrity
    async getHash() {
        const data = this.toDataURL();
        const encoder = new TextEncoder();
        const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    // Validate signature is not empty
    isValid() {
        return !this.isEmpty;
    }
}

// Export
window.SignaturePad = SignaturePad;
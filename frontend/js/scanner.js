/**
 * scanner.js — QR/PDF417 scanner for AyC Eventos PWA
 * Uses html5-qrcode library for camera-based scanning.
 */
/* global Html5Qrcode */

let scannerInstance = null;
let isScanning = false;

function initScanner(containerId, onResult, onError) {
    if (scannerInstance) scannerInstance.clear();
    
    scannerInstance = new Html5Qrcode(containerId);
    
    const config = {
        fps: 10,
        qrbox: { width: 250, height: 250 },
        formatsToSupport: [
            Html5QrcodeSupportedFormats.QR_CODE,
            Html5QrcodeSupportedFormats.PDF_417
        ]
    };
    
    scannerInstance.start(
        { facingMode: "environment" },
        config,
        (decodedText, decodedResult) => {
            if (navigator.vibrate) navigator.vibrate(100);
            if (onResult) onResult(decodedText, decodedResult);
        },
        () => {}
    ).catch(err => {
        if (onError) onError(err);
    });
    isScanning = true;
}

function stopScanner() {
    if (scannerInstance && isScanning) {
        scannerInstance.stop().then(() => {
            scannerInstance.clear();
            isScanning = false;
        }).catch(() => {});
    }
}

function parseScanResult(text) {
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (uuidRegex.test(text.trim())) {
        return { type: 'assignment_id', value: text.trim() };
    }
    const ccMatch = text.match(/(\d{8,12})/);
    if (ccMatch) return { type: 'document_number', value: ccMatch[1], raw: text };
    return { type: 'unknown', value: text };
}

async function manualSearch(eventId, query) {
    if (window.OfflineDB) {
        const r = await OfflineDB.searchOperators(eventId, query);
        if (r.length > 0) return r;
    }
    try {
        const resp = await fetch(`/api/events/${eventId}/operators/search?q=${encodeURIComponent(query)}`);
        if (resp.ok) return await resp.json();
    } catch (e) {}
    return [];
}

window.Scanner = { init: initScanner, stop: stopScanner, parse: parseScanResult, manualSearch };

if (typeof Html5Qrcode === 'undefined') {
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
    document.head.appendChild(s);
}
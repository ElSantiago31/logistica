/**
 * db.js — Dexie.js offline database for AyC Eventos PWA
 * Stores events, operators, and attendance data for offline use.
 */
/* global Dexie */

const DB_NAME = 'ayc_events';

let db = null;
let _dbRecovering = false;

function initDB() {
    if (db) return db;
    
    // Dynamically load Dexie if not present
    if (typeof Dexie === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/dexie@3.2.7/dist/dexie.js';
        script.onload = () => { db = _createDB(); };
        document.head.appendChild(script);
        return null;
    }
    db = _createDB();
    return db;
}

function _createDB() {
    const database = new Dexie(DB_NAME);
    // Versión 1 original
    database.version(1).stores({
        // Events downloaded for offline access
        events: 'id, name, status, start_date, location',
        // Operators assigned to events
        operators: 'id, event_id, full_name, document_number, role_name, status, *search_terms',
        // Attendance logs (created offline)
        attendance: '++local_id, event_id, operator_id, check_in_time, sync_status, photo_blob',
        // Sync metadata
        sync_meta: 'key, last_sync, etag'
    });
    // Versión 2: agrega uniform_pending
    database.version(2).stores({
        uniform_pending: '++local_id, assignment_id, event_id, sync_status'
    });
    // Versión 3: agrega checkin_log
    database.version(3).stores({
        checkin_log: '++local_id, event_id, assignment_id, created_at'
    });
    // Versión 4: compatibilidad — navegadores que abrieron v4 en dev
    database.version(4).stores({});

    // Auto-recuperación: si el navegador tiene una versión mayor a la definida,
    // Dexie lanza VersionError. Borramos y reconstruimos.
    database.open().catch(err => {
        if (err && (err.name === 'VersionError' || err.name === 'DatabaseClosedError')) {
            console.warn('⚠️ IndexedDB version mismatch — wiping and rebuilding...', err.message);
            _dbRecovering = true;
            db = null;
            Dexie.delete(DB_NAME).then(() => {
                _dbRecovering = false;
                console.log('✅ IndexedDB reconstruida.');
            }).catch(() => { _dbRecovering = false; });
        } else {
            console.error('IndexedDB open error:', err);
        }
    });

    return database;
}

// ============================================================
// DOWNLOAD: Cache event data for offline use
// ============================================================

async function cacheEventData(eventId, eventData) {
    const database = initDB();
    if (!database) return;
    
    await database.transaction('rw', [database.events, database.operators], async () => {
        await database.events.put({
            id: eventData.id,
            name: eventData.name,
            status: eventData.status,
            start_date: eventData.start_date,
            end_date: eventData.end_date,
            location: eventData.location,
            description: eventData.description,
            downloaded_at: new Date().toISOString()
        });
        
        // Clear old operators for this event
        await database.operators.where('event_id').equals(eventId).delete();
        
        // Add new operators
        if (eventData.assignments) {
            for (const a of eventData.assignments) {
                const searchTerms = [
                    a.full_name || '',
                    a.document_number || '',
                    a.role_name || ''
                ].filter(Boolean);
                
                await database.operators.put({
                    id: a.id,
                    event_id: eventId,
                    full_name: a.full_name,
                    document_number: a.document_number,
                    role_name: a.role_name,
                    status: a.status,
                    photo_url: a.photo_url,
                    search_terms: searchTerms
                });
            }
        }
    });
    
    // Update sync meta
    await database.sync_meta.put({
        key: `event_${eventId}`,
        last_sync: new Date().toISOString(),
        etag: eventData._etag || ''
    });
}

// ============================================================
// SEARCH: Find operators offline
// ============================================================

async function searchOperators(eventId, query) {
    const database = initDB();
    if (!database) return [];
    
    const q = query.toLowerCase().trim();
    const operators = await database.operators
        .where('event_id').equals(eventId)
        .toArray();
    
    return operators.filter(op => {
        const name = (op.full_name || '').toLowerCase();
        const doc = (op.document_number || '').toLowerCase();
        return name.includes(q) || doc.includes(q);
    });
}

// ============================================================
// ATTENDANCE: Log check-in/check-out offline
// ============================================================

async function logAttendance(eventId, operatorId, photoBlob) {
    const database = initDB();
    if (!database) return null;
    
    const record = {
        event_id: eventId,
        operator_id: operatorId,
        check_in_time: new Date().toISOString(),
        photo_blob: photoBlob || null,
        sync_status: 'pending',  // pending | synced | failed
        created_at: new Date().toISOString()
    };
    
    const localId = await database.attendance.add(record);
    return { ...record, local_id: localId };
}

async function getPendingAttendance() {
    const database = initDB();
    if (!database) return [];
    return database.attendance.where('sync_status').equals('pending').toArray();
}

async function markAttendanceSynced(localId) {
    const database = initDB();
    if (!database) return;
    await database.attendance.update(localId, { sync_status: 'synced' });
}

// ============================================================
// UTILS
// ============================================================

async function getCachedEvents() {
    const database = initDB();
    if (!database) return [];
    return database.events.toArray();
}

async function getEventOperators(eventId) {
    const database = initDB();
    if (!database) return [];
    return database.operators.where('event_id').equals(eventId).toArray();
}

async function getLastSync(key) {
    const database = initDB();
    if (!database) return null;
    const meta = await database.sync_meta.get(key);
    return meta ? meta.last_sync : null;
}

// Export
window.OfflineDB = {
    init: initDB,
    cacheEventData,
    searchOperators,
    logAttendance,
    getPendingAttendance,
    markAttendanceSynced,
    getCachedEvents,
    getEventOperators,
    getLastSync,
    get db() { return db; }
};
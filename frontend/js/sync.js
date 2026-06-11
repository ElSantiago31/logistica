/**
 * sync.js — Batch sync for AyC Eventos PWA
 * Syncs offline attendance records when connection is restored.
 */
/* global OfflineDB */

const SYNC_BATCH_SIZE = 20;
const SYNC_RETRY_MS = 30000; // 30 seconds

let syncing = false;
let syncInterval = null;

// --- Auth helpers ---
function _getToken() { return localStorage.getItem('access_token'); }
function _authHeaders() {
    const t = _getToken();
    const h = { 'Content-Type': 'application/json' };
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
}

// ============================================================
// MAIN SYNC FUNCTION
// ============================================================

async function syncPendingRecords() {
    if (syncing) return { syncing: true };
    if (!navigator.onLine) return { offline: true };

    syncing = true;
    const results = { synced: 0, failed: 0, total: 0 };

    try {
        const pending = await OfflineDB.getPendingAttendance();
        results.total = pending.length;

        if (pending.length === 0) {
            syncing = false;
            return results;
        }

        // Process in batches
        for (let i = 0; i < pending.length; i += SYNC_BATCH_SIZE) {
            const batch = pending.slice(i, i + SYNC_BATCH_SIZE);
            const records = batch.map(r => ({
                local_id: r.local_id,
                event_id: r.event_id,
                operator_id: r.operator_id,
                check_in_time: r.check_in_time,
                check_in_method: r.check_in_method || 'manual',
                photo_blob: r.photo_blob
            }));

            try {
                const response = await fetch('/api/sync/attendance', {
                    method: 'POST',
                    headers: _authHeaders(),
                    body: JSON.stringify({ records })
                });

                if (response.ok) {
                    const data = await response.json();
                    // Mark synced
                    for (const r of batch) {
                        await OfflineDB.markAttendanceSynced(r.local_id);
                        results.synced++;
                    }
                } else {
                    results.failed += batch.length;
                }
            } catch (err) {
                console.error('Sync batch failed:', err);
                results.failed += batch.length;
            }
        }
    } catch (err) {
        console.error('Sync error:', err);
    }

    syncing = false;

    // Dispatch event for UI updates
    window.dispatchEvent(new CustomEvent('sync-complete', { detail: results }));
    return results;
}

// ============================================================
// AUTO-SYNC: Watch connectivity
// ============================================================

function startAutoSync() {
    // Sync when coming back online
    window.addEventListener('online', () => {
        console.log('📡 Connection restored — starting sync');
        setTimeout(syncPendingRecords, 2000);
    });

    // Periodic sync while online
    syncInterval = setInterval(() => {
        if (navigator.onLine) {
            syncPendingRecords();
        }
    }, SYNC_RETRY_MS);
}

function stopAutoSync() {
    if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
    }
}

// ============================================================
// DOWNLOAD: Cache event for offline
// ============================================================

async function downloadEventOffline(eventId) {
    try {
        const response = await fetch(`/api/sync/events/${eventId}/offline-data`, {
            headers: _authHeaders()
        });
        if (!response.ok) throw new Error(`Failed to fetch event data: ${response.status}`);

        const eventData = await response.json();
        await OfflineDB.cacheEventData(eventId, eventData);

        window.dispatchEvent(new CustomEvent('event-cached', { detail: { eventId } }));
        return { success: true, operators: eventData.assignments?.length || 0 };
    } catch (err) {
        console.error('Download failed:', err);
        return { success: false, error: err.message };
    }
}

// ============================================================
// STATUS
// ============================================================

async function getSyncStatus() {
    const pending = await OfflineDB.getPendingAttendance();
    const cached = await OfflineDB.getCachedEvents();
    return {
        pending_count: pending.length,
        cached_events: cached.length,
        online: navigator.onLine,
        syncing: syncing
    };
}

// Export
window.SyncManager = {
    sync: syncPendingRecords,
    startAutoSync,
    stopAutoSync,
    downloadEvent: downloadEventOffline,
    getStatus: getSyncStatus
};

// Auto-start
if (typeof OfflineDB !== 'undefined') {
    OfflineDB.init();
    startAutoSync();
}
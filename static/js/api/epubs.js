/**
 * EPUB list, download and delete API calls.
 * This module only talks to the server – it has no direct DOM access.
 */
import { fetchBlob, fetchJSON, requestOK } from './client.js';

/** @returns {Promise<{epubs: string[], total: number}>} */
export async function listEpubs(limit = 500) {
    const data = await fetchJSON(`/epubs?offset=0&limit=${limit}`);
    const payload = data?.data ?? {};
    const total = typeof payload.total === 'number' ? payload.total : 0;
    if (total > limit) {
        console.warn(`Library contains ${total} files but UI requested limit=${limit}. Increase limit to fetch all items.`);
    }
    return {
        epubs: Array.isArray(payload.epubs) ? payload.epubs : [],
        total,
    };
}

/**
 * Download a single local EPUB by filename.
 * Triggers a browser file-save dialog.
 * @param {string} name – the epub filename
 */
export async function downloadSingle(name) {
    const blob = await fetchBlob('/epub/download?name=' + encodeURIComponent(name), { timeoutMs: 60_000 });
    triggerDownload(blob, name);
}

/**
 * Download multiple local EPUBs zipped together.
 * @param {string[]} names
 */
export async function downloadMany(names) {
    const blob = await fetchBlob('/epub/download-many', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names }),
        timeoutMs: 120_000,
    });
    triggerDownload(blob, 'epubs.zip');
}

/** Download every EPUB as a zip. */
export async function downloadAll() {
    const blob = await fetchBlob('/epub/download-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
        timeoutMs: 180_000,
    });
    triggerDownload(blob, 'all_epubs.zip');
}

/**
 * Delete a list of EPUBs by filename.
 * @param {string[]} names
 */
export async function deleteEpubs(names) {
    await requestOK('/epubs', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(names),
        timeoutMs: 30_000,
    });
}

/** Delete ALL EPUBs. */
export async function deleteAllEpubs() {
    await requestOK('/epubs/all', { method: 'DELETE', timeoutMs: 30_000 });
}

// ─── Internal helpers ────────────────────────────────────────────────────────
function triggerDownload(blob, filename) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

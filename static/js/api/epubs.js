/**
 * EPUB list, download and delete API calls.
 * This module only talks to the server – it has no direct DOM access.
 */
import { fetchJSON } from './client.js';

/** @returns {Promise<{epubs: string[], total: number}>} */
export async function listEpubs(limit = 500) {
    const data = await fetchJSON(`/epubs?offset=0&limit=${limit}`);
    const payload = data?.data ?? {};
    return {
        epubs: Array.isArray(payload.epubs) ? payload.epubs : [],
        total: typeof payload.total === 'number' ? payload.total : 0,
    };
}

/**
 * Download a single local EPUB by filename.
 * Triggers a browser file-save dialog.
 * @param {string} name – the epub filename
 */
export async function downloadSingle(name) {
    const r = await fetch('/epub/download?name=' + encodeURIComponent(name));
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const blob = await r.blob();
    triggerDownload(blob, name);
}

/**
 * Download multiple local EPUBs zipped together.
 * @param {string[]} names
 */
export async function downloadMany(names) {
    const r = await fetch('/epub/download-many', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    triggerDownload(await r.blob(), 'epubs.zip');
}

/** Download every EPUB as a zip. */
export async function downloadAll() {
    const r = await fetch('/epub/download-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    triggerDownload(await r.blob(), 'all_epubs.zip');
}

/**
 * Delete a list of EPUBs by filename.
 * @param {string[]} names
 */
export async function deleteEpubs(names) {
    const r = await fetch('/epubs', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(names),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
}

/** Delete ALL EPUBs. */
export async function deleteAllEpubs() {
    const r = await fetch('/epubs/all', { method: 'DELETE' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
}

// ─── Internal helpers ────────────────────────────────────────────────────────
function triggerDownload(blob, filename) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

/**
 * Generate, append, cancel, and stop API calls.
 * No DOM access – callers handle UI state.
 */
import { fetchJSON } from './client.js';

/**
 * @typedef {Object} GeneratePayload
 * @property {string} url
 * @property {number} chapters_per_book
 * @property {number} chapter_workers
 * @property {number} chapter_limit
 * @property {number} start_chapter
 */

/**
 * Kick off a full EPUB generation from the first chapter.
 * @param {GeneratePayload} payload
 * @returns {Promise<Object>} – server response data
 */
export async function generateEpub(payload) {
    const res = await fetchJSON('/epub/generate', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
    return res?.data ?? {};
}

/**
 * Append new chapters to an existing novel (starts from start_chapter).
 * @param {{ url: string, start_chapter: number, chapters_per_book?: number, chapter_workers?: number, chapter_limit?: number }} payload
 * @returns {Promise<Object>}
 */
export async function appendChapters(payload) {
    const res = await fetchJSON('/epub/append', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
    return res?.data ?? {};
}

/** Cancel the currently running generation job. */
export async function cancelGeneration() {
    await fetchJSON('/epub/cancel', { method: 'POST', body: '{}' });
}

/** Gracefully stop (saves partial EPUB) the running generation job. */
export async function stopGeneration() {
    await fetchJSON('/epub/stop', { method: 'POST', body: '{}' });
}

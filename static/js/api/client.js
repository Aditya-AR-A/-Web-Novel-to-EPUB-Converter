/** Thin fetch wrapper – all API calls go through here. */

const DEFAULT_TIMEOUT_MS = 30_000;

function withTimeoutSignal(opts = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const signal = opts.signal ?? controller.signal;
    return {
        merged: Object.assign({}, opts, { signal }),
        clear: () => clearTimeout(timer),
    };
}

async function readErrorMessage(response) {
    const txt = await response.text();
    return txt || response.statusText || 'Request failed';
}

/**
 * Fetch a URL, parse the JSON body, and throw a descriptive error on
 * non-2xx responses.
 *
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<any>}
 */
export async function fetchJSON(url, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const { timeoutMs: _ignored, ...requestOpts } = opts;
    const { merged, clear } = withTimeoutSignal(
        Object.assign({ headers: { 'Content-Type': 'application/json' } }, requestOpts),
        timeoutMs
    );

    try {
        const r = await fetch(url, merged);
        if (!r.ok) {
            const message = await readErrorMessage(r);
            throw new Error(`HTTP ${r.status}: ${message}`);
        }
        return r.json();
    } catch (e) {
        if (e.name === 'AbortError') {
            throw new Error(`Request timed out after ${timeoutMs}ms`);
        }
        throw e;
    } finally {
        clear();
    }
}

export async function fetchBlob(url, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const { timeoutMs: _ignored, ...requestOpts } = opts;
    const { merged, clear } = withTimeoutSignal(requestOpts, timeoutMs);

    try {
        const r = await fetch(url, merged);
        if (!r.ok) {
            const message = await readErrorMessage(r);
            throw new Error(`HTTP ${r.status}: ${message}`);
        }
        return r.blob();
    } catch (e) {
        if (e.name === 'AbortError') {
            throw new Error(`Request timed out after ${timeoutMs}ms`);
        }
        throw e;
    } finally {
        clear();
    }
}

export async function requestOK(url, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const { timeoutMs: _ignored, ...requestOpts } = opts;
    const { merged, clear } = withTimeoutSignal(requestOpts, timeoutMs);

    try {
        const r = await fetch(url, merged);
        if (!r.ok) {
            const message = await readErrorMessage(r);
            throw new Error(`HTTP ${r.status}: ${message}`);
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            throw new Error(`Request timed out after ${timeoutMs}ms`);
        }
        throw e;
    } finally {
        clear();
    }
}

/**
 * Load the server-side config (storage backend, etc.).
 * @returns {Promise<{storage_backend: string}>}
 */
export async function fetchConfig() {
    const cfg = await fetchJSON('/config');
    return cfg?.data ?? {};
}

/** Thin fetch wrapper – all API calls go through here. */

/**
 * Fetch a URL, parse the JSON body, and throw a descriptive error on
 * non-2xx responses.
 *
 * @param {string} url
 * @param {RequestInit} [opts]
 * @returns {Promise<any>}
 */
export async function fetchJSON(url, opts = {}) {
    const r = await fetch(url, Object.assign(
        { headers: { 'Content-Type': 'application/json' } },
        opts
    ));
    if (!r.ok) {
        const txt = await r.text();
        throw new Error(`HTTP ${r.status}: ${txt}`);
    }
    return r.json();
}

/**
 * Load the server-side config (storage backend, etc.).
 * @returns {Promise<{storage_backend: string}>}
 */
export async function fetchConfig() {
    const cfg = await fetchJSON('/config');
    return cfg?.data ?? {};
}

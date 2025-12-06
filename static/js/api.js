export async function fetchJSON(url, options = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    const response = await fetch(url, Object.assign({}, options, { headers }));
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
    }
    return response.json();
}

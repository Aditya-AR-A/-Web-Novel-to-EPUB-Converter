/** Shared pure utility functions. No DOM access here. */

/** HTML-escape a string to safely insert it into innerHTML. */
export function escapeHTML(str = '') {
    return String(str).replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
}

/**
 * Extract the numeric start of a chapter range from a filename like
 * "my_novel-ch-501-1000.epub" → 501.  Falls back to 0.
 */
export function chStart(name) {
    const m = name.match(/ch-(\d+)/i);
    return m ? parseInt(m[1]) : 0;
}

/** "my_cool_novel" → "My Cool Novel" */
export function humanTitle(base) {
    return base.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).trim();
}

/** "my_novel-ch-1-500.epub" → "Vol Ch.1–500" */
export function volLabel(name) {
    const m = name.match(/ch-(\d+)-(\d+)/i);
    if (m) return `Vol Ch.${m[1]}–${m[2]}`;
    return name.replace(/\.epub$/i, '');
}

/**
 * Group a flat array of filenames by novel base title.
 * Within each group, volumes are sorted by chapter-start number ascending.
 *
 * @param {string[]} items – filenames (local storage mode)
 * @returns {Map<string, string[]>}
 */
export function groupByNovel(items) {
    const map = new Map();
    for (const name of items) {
        const base = name
            .replace(/\.epub$/i, '')
            .replace(/-ch-\d+[-\d]*/i, '')
            .replace(/-[ivxlcdm]+$/i, '')
            .replace(/_+$/, '');
        if (!map.has(base)) map.set(base, []);
        map.get(base).push(name);
    }
    for (const vols of map.values()) {
        vols.sort((a, b) => chStart(a) - chStart(b));
    }
    return map;
}

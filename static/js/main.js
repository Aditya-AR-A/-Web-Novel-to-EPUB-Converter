/**
 * Main entry point – wires together all UI modules and API calls.
 * Imported via <script type="module"> in index.html.
 */
import { initTheme, watchHeaderHeight } from './ui/theme.js';
import { initSidebar } from './ui/sidebar.js';
import { initLogs, log, showProgress } from './ui/logs.js';
import { initLibrary, refreshViews, selectedNames, clearSelection } from './ui/library.js';
import { fetchConfig } from './api/client.js';
import { listEpubs, downloadMany, downloadAll, deleteEpubs, deleteAllEpubs } from './api/epubs.js';
import { generateEpub, appendChapters, cancelGeneration, stopGeneration } from './api/generate.js';

// ─── Init UI modules ─────────────────────────────────────────────────────────
initTheme();
watchHeaderHeight();
initSidebar();
initLibrary();
initLogs();

// ─── Storage backend (affects download/delete routing) ───────────────────────
let storageBackend = 'local';

// ─── Load EPUB library ───────────────────────────────────────────────────────
async function loadList(page = 1) {
    try {
        const { epubs } = await listEpubs();
        refreshViews(epubs, page);
    } catch (e) {
        log('List error: ' + e.message);
    }
}

// ─── Generation state ────────────────────────────────────────────────────────
const genBtn = document.getElementById('genBtn');
const appendBtn = document.getElementById('appendBtn');
const cancelBtn = document.getElementById('cancelBtn');
const stopBtn = document.getElementById('stopBtn');

function setGenerating(active) {
    genBtn.disabled = active;
    appendBtn.disabled = active;
    cancelBtn.disabled = !active;
    stopBtn.disabled = !active;
    showProgress(active);
}

async function runJob(apiFn, payload, label) {
    setGenerating(true);
    log(`Starting ${label}…`);
    try {
        const data = await apiFn(payload);
        const files = data.filenames ?? data.new_filenames ?? [];
        const chCount = data.chapters ?? data.new_chapters ?? '?';
        log(`✅ ${label} complete. ${chCount} chapters. Files: ${files.slice(0, 5).join(', ')}${files.length > 5 ? '…' : ''}`);
        await loadList();
    } catch (e) {
        if (/cancel/i.test(e.message)) log('Generation cancelled.', 'warn');
        else log(`${label} failed: ` + e.message);
    } finally {
        setGenerating(false);
    }
}

// ─── Form helpers ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const intVal = (id, fallback = 0) => parseInt($('').value ?? '', 10) || fallback;
// Inline helper to read specific field by id:
function fieldInt(id, fallback = 0) {
    return parseInt(document.getElementById(id).value, 10) || fallback;
}

// ─── Generate form ────────────────────────────────────────────────────────────
document.getElementById('genForm').addEventListener('submit', e => {
    e.preventDefault();
    runJob(generateEpub, {
        url: document.getElementById('url').value.trim(),
        chapters_per_book: fieldInt('chapters_per_book', 500),
        chapter_workers: fieldInt('chapter_workers', 1),
        chapter_limit: fieldInt('chapter_limit', 0),
        start_chapter: fieldInt('start_chapter', 1),
    }, 'Generate');
});

// ─── Append button ────────────────────────────────────────────────────────────
appendBtn.addEventListener('click', () => {
    const startCh = fieldInt('start_chapter', 0);
    if (!startCh || startCh < 1) {
        alert('Set "Start Chapter" to the first NEW chapter number to append.');
        return;
    }
    runJob(appendChapters, {
        url: document.getElementById('url').value.trim(),
        start_chapter: startCh,
        chapters_per_book: fieldInt('chapters_per_book', 500),
        chapter_workers: fieldInt('chapter_workers', 1),
        chapter_limit: fieldInt('chapter_limit', 0),
    }, 'Append');
});

// ─── Cancel / Stop ────────────────────────────────────────────────────────────
cancelBtn.addEventListener('click', async () => {
    try { await cancelGeneration(); log('Cancellation requested…'); }
    catch (e) { log('Cancel failed: ' + e.message); }
});
stopBtn.addEventListener('click', async () => {
    try { await stopGeneration(); log('Stop requested — finishing current chapter then building.'); }
    catch (e) { log('Stop failed: ' + e.message); }
});

// ─── Download selected ────────────────────────────────────────────────────────
document.getElementById('downloadSelBtn').addEventListener('click', async () => {
    const names = [...selectedNames];
    if (!names.length) return;
    log(`Downloading ${names.length} selected as zip…`);
    try { await downloadMany(names); }
    catch (e) { log('Multi-download failed: ' + e.message); }
});

// ─── Download all ─────────────────────────────────────────────────────────────
document.getElementById('downloadAllBtn').addEventListener('click', async () => {
    log('Downloading ALL as zip…');
    try { await downloadAll(); }
    catch (e) { log('Download-all failed: ' + e.message); }
});

// ─── Delete selected ──────────────────────────────────────────────────────────
document.getElementById('deleteSelBtn').addEventListener('click', async () => {
    const names = [...selectedNames];
    if (!names.length) return;
    if (!confirm(`Delete ${names.length} file(s)?`)) return;
    try {
        await deleteEpubs(names);
        clearSelection();
        log('Deleted selected.');
        await loadList();
    } catch (e) { log('Delete failed: ' + e.message); }
});

// ─── Delete all ───────────────────────────────────────────────────────────────
document.getElementById('deleteAllBtn').addEventListener('click', async () => {
    if (!confirm('Delete ALL EPUB files?')) return;
    try {
        await deleteAllEpubs();
        clearSelection();
        log('Deleted all EPUBs.');
        await loadList(1);
    } catch (e) { log('Delete all failed: ' + e.message); }
});

// ─── Refresh button ───────────────────────────────────────────────────────────
document.getElementById('refreshBtn').addEventListener('click', () => loadList());

// ─── Bootstrap ────────────────────────────────────────────────────────────────
fetchConfig()
    .then(cfg => {
        storageBackend = cfg.storage_backend ?? 'local';
        log(`Storage backend: ${storageBackend}`);
    })
    .catch(e => log('Config load failed: ' + e.message))
    .finally(() => loadList());

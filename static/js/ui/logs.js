/**
 * Log panel – WebSocket streaming, HTTP polling fallback,
 * progress-bar updates driven by [PROGRESS] log lines.
 */

const logBox = document.getElementById('logBox');
const showAccessCb = document.getElementById('showAccess');
const showPollingCb = document.getElementById('showPolling');

// ─── Progress bar refs ────────────────────────────────────────────────────────
const progressWrap = document.getElementById('progressWrap');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const progressCount = document.getElementById('progressCount');

// ─── Log sequencing ───────────────────────────────────────────────────────────
let logSeq = 0;
let wsActive = false;

// ─── Line classification ──────────────────────────────────────────────────────
function classify(line) {
    if (/\bGET \/logs\?since=/i.test(line)) return 'polling';
    if (/(GET|POST|DELETE|PUT|HEAD) \/[^ ]* HTTP\//.test(line)) return 'access';
    if (/error|traceback/i.test(line)) return 'error';
    if (/warn/i.test(line)) return 'warn';
    if (/\[PROGRESS\]|\[APPEND\]/.test(line)) return 'progress';
    return 'info';
}

// ─── Progress bar logic ───────────────────────────────────────────────────────
function updateProgressFromLine(line) {
    // "Chapter X processed (Y/Z)"
    const m = line.match(/\[PROGRESS\] Chapter \d+ processed \((\d+)\/(\d+)\)/);
    if (m) {
        const done = parseInt(m[1]), total = parseInt(m[2]);
        const pct = total > 0 ? Math.round((done / total) * 100) : 0;
        progressFill.style.width = pct + '%';
        progressText.textContent = `Building EPUB — ch ${done}/${total}`;
        progressCount.textContent = pct + '%';
        return;
    }
    const m2 = line.match(/\[PROGRESS\] Fetched (\d+) valid chapters/);
    if (m2) {
        progressText.textContent = `Fetched ${m2[1]} chapters — building…`;
        progressFill.style.width = '40%';
        return;
    }
    if (line.includes('[PROGRESS] Fetching chapters')) {
        progressText.textContent = 'Scraping chapters…';
        progressFill.style.width = '5%';
    }
}

// ─── Public: append one line to the log panel ─────────────────────────────────
export function log(msg) {
    const type = classify(msg);
    if (type === 'access' && !showAccessCb.checked) return;
    if (type === 'polling' && !showPollingCb.checked) return;

    updateProgressFromLine(msg);

    const ts = new Date().toISOString().split('T')[1].replace('Z', '');
    const div = document.createElement('div');
    const cls = type === 'error' ? 'err'
        : type === 'warn' ? 'warn'
            : type === 'progress' ? 'progress'
                : 'info';
    div.className = 'log-' + cls;
    div.textContent = `[${ts}] ${msg}`;
    logBox.appendChild(div);

    // Cap at 1 200 lines to keep DOM lean
    while (logBox.childNodes.length > 1200) logBox.removeChild(logBox.firstChild);
    logBox.scrollTop = logBox.scrollHeight;
}

// ─── Progress bar visibility ──────────────────────────────────────────────────
export function showProgress(visible) {
    progressWrap.classList.toggle('visible', visible);
    if (!visible) {
        progressFill.style.width = '0%';
        progressText.textContent = '';
        progressCount.textContent = '';
    }
}

// ─── WebSocket ────────────────────────────────────────────────────────────────
function initWebSocket() {
    try {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);
        ws.onopen = () => { wsActive = true; log('WebSocket log stream connected'); };
        ws.onclose = () => {
            wsActive = false;
            log('WebSocket closed; falling back to polling');
            setTimeout(() => { if (!wsActive) initWebSocket(); }, 4000);
        };
        ws.onerror = () => { };
        ws.onmessage = evt => {
            try {
                const d = JSON.parse(evt.data);
                if (Array.isArray(d.lines)) {
                    d.lines.forEach(o => { logSeq = Math.max(logSeq, o.seq); log(o.line); });
                } else if (d.seq && d.line) {
                    logSeq = Math.max(logSeq, d.seq); log(d.line);
                }
            } catch { /* ignore malformed */ }
        };
    } catch (e) {
        log('WebSocket init failed: ' + e.message);
    }
}

// ─── HTTP polling fallback ────────────────────────────────────────────────────
async function pollLogs() {
    if (wsActive) { setTimeout(pollLogs, 5000); return; }
    try {
        const r = await fetch(`/logs?since=${logSeq}`);
        if (r.ok) {
            const j = await r.json();
            if (j.ok && j.data?.lines) {
                for (const { seq, line } of j.data.lines) {
                    logSeq = Math.max(logSeq, seq);
                    log(line);
                }
                if (j.data.next) logSeq = j.data.next;
            }
        }
    } catch { /* silent */ }
    finally { setTimeout(pollLogs, 1000); }
}

// ─── Initialise ───────────────────────────────────────────────────────────────
export function initLogs() {
    showAccessCb.checked = false;
    showPollingCb.checked = false;
    initWebSocket();
    pollLogs();
}

import { $ } from './dom.js';

/* ------------------------------
   Helper functions
--------------------------------*/
function applyLogsCollapsed(rootEl, collapsed) {
    if (!rootEl) return; // ✅ Prevent crash if missing element
    rootEl.classList.toggle('logs-collapsed', collapsed);
    localStorage.setItem('logs-collapsed', collapsed ? '1' : '0');
}

function setSidebarWidth(px) {
    const min = 260;
    const max = Math.max(min, Math.floor(window.innerWidth * 0.6));
    const clamped = Math.max(min, Math.min(max, px));
    document.documentElement.style.setProperty('--sidebar-width', `${clamped}px`);
    localStorage.setItem('logs-sidebar-width', String(clamped));
}

function classifyLogLine(line = '') {
    if (/\bGET\s+\/logs\?since=/i.test(line)) return 'polling';
    if (/(GET|POST|DELETE|PUT|HEAD)\s+\/[^ ]*\s+HTTP\//i.test(line)) return 'access';
    if (/error|traceback/i.test(line)) return 'error';
    if (/warn/i.test(line)) return 'warn';
    return 'info';
}

/* ------------------------------
   Main init function
--------------------------------*/
export function initLogs({ rootEl }) {
    const logBox = $('#logBox');
    const logsToggle = $('#logsToggle');
    const resizer = $('#sidebarResizer');
    const showAccessCb = $('#showAccess');
    const showPollingCb = $('#showPolling');

    // Default filter states
    if (showAccessCb) showAccessCb.checked = false;
    if (showPollingCb) showPollingCb.checked = false;

    // Restore collapse state
    const savedLogsState = localStorage.getItem('logs-collapsed');
    const defaultCollapse = window.matchMedia?.('(max-width: 980px)').matches ?? false;
    applyLogsCollapsed(rootEl, savedLogsState === null ? defaultCollapse : savedLogsState === '1');

    logsToggle?.addEventListener('click', () => {
        const nowCollapsed = !rootEl.classList.contains('logs-collapsed');
        applyLogsCollapsed(rootEl, nowCollapsed);
    });

    // Restore width if stored
    const savedWidth = parseInt(localStorage.getItem('logs-sidebar-width') || '0', 10);
    if (savedWidth > 0) {
        document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
    }

    /* ------------------------------
       Sidebar drag resizing
    --------------------------------*/
    let dragging = false;
    let startWidth = 0;
    let startX = 0;

    function handleMove(event) {
        if (!dragging) return;
        const clientX = event.touches?.[0]?.clientX ?? event.clientX;
        const delta = startX - clientX;
        const newWidth = startWidth + delta;
        setSidebarWidth(newWidth);
    }

    function stopDragging() {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove('resizing');
        window.removeEventListener('mousemove', handleMove);
        window.removeEventListener('mouseup', stopDragging);
        window.removeEventListener('touchmove', handleMove);
        window.removeEventListener('touchend', stopDragging);
    }

    function startDragging(event) {
        if (rootEl.classList.contains('logs-collapsed')) return;
        dragging = true;
        document.body.classList.add('resizing');
        startWidth = parseInt(getComputedStyle(document.documentElement)
            .getPropertyValue('--sidebar-width'), 10) || 380;
        startX = event.touches?.[0]?.clientX ?? event.clientX;
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', stopDragging);
        window.addEventListener('touchmove', handleMove, { passive: false });
        window.addEventListener('touchend', stopDragging);
        event.preventDefault();
    }

    resizer?.addEventListener('mousedown', startDragging);
    resizer?.addEventListener('touchstart', startDragging, { passive: false });

    /* ------------------------------
       Logging logic
    --------------------------------*/
    let logSeq = 0;
    let ws;
    let wsActive = false;

    const log = (message, _type = 'info', rawTypeHint = null) => {
        const effectiveType = rawTypeHint || classifyLogLine(message);
        if (effectiveType === 'access' && showAccessCb && !showAccessCb.checked) return;
        if (effectiveType === 'polling' && showPollingCb && !showPollingCb.checked) return;

        const timestamp = new Date().toISOString().split('T')[1].replace('Z', '');
        if (logBox) {
            const entry = document.createElement('div');
            const level = effectiveType === 'error' ? 'err' :
                          effectiveType === 'warn' ? 'warn' : 'info';
            entry.className = `log-${level}`;
            entry.textContent = `[${timestamp}] ${message}`;
            logBox.appendChild(entry);
            // Limit log count to prevent memory growth
            while (logBox.childNodes.length > 1200) {
                logBox.removeChild(logBox.firstChild);
            }
            logBox.scrollTop = logBox.scrollHeight;
        } else {
            console.log(`[${timestamp}] ${message}`);
        }
    };

    /* ------------------------------
       WebSocket connection
    --------------------------------*/
    const initWebSocket = () => {
        if (!('WebSocket' in window)) {
            log('WebSocket unsupported; using HTTP polling', 'warn');
            return;
        }
        try {
            const proto = location.protocol === 'https:' ? 'wss' : 'ws';
            ws = new WebSocket(`${proto}://${location.host}/ws/logs`);

            ws.onopen = () => {
                wsActive = true;
                log('WebSocket log stream connected');
            };

            ws.onclose = () => {
                if (wsActive) log('WebSocket closed; attempting reconnect…', 'warn');
                wsActive = false;
                // ✅ Retry after a short delay (exponential backoff can be added)
                setTimeout(() => {
                    if (!wsActive) initWebSocket();
                }, 4000);
            };

            ws.onerror = (err) => {
                log(`WebSocket error: ${err.message || err}`, 'warn');
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    const lines = data?.lines || (data.seq && data.line ? [data] : []);
                    for (const obj of lines) {
                        if (!obj?.line) continue;
                        logSeq = Math.max(logSeq, obj.seq ?? logSeq);
                        log(obj.line);
                    }
                } catch (error) {
                    console.error('Malformed log payload', error);
                }
            };
        } catch (error) {
            log(`WebSocket init failed: ${error.message}`, 'warn');
        }
    };

    /* ------------------------------
       Polling fallback
    --------------------------------*/
    async function pollLogs() {
        if (wsActive) {
            setTimeout(pollLogs, 5000);
            return;
        }
        try {
            const response = await fetch(`/logs?since=${logSeq}`);
            if (response.ok) {
                const payload = await response.json();
                const lines = payload?.data?.lines || [];
                for (const { seq, line } of lines) {
                    logSeq = Math.max(logSeq, seq);
                    log(line);
                }
                if (payload?.data?.next) {
                    logSeq = payload.data.next;
                }
            }
        } catch {
            /* ignore polling errors silently */
        } finally {
            setTimeout(pollLogs, 1000);
        }
    }

    initWebSocket();
    pollLogs();

    return { log };
}

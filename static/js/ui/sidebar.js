/**
 * Logs sidebar – collapse toggle and drag-to-resize handle.
 */

const rootEl = document.documentElement;
const logsToggle = document.getElementById('logsToggle');
const resizer = document.getElementById('sidebarResizer');

// ─── Collapse toggle ──────────────────────────────────────────────────────────
function applyCollapsed(collapsed) {
    rootEl.classList.toggle('logs-collapsed', collapsed);
    localStorage.setItem('logs-collapsed', collapsed ? '1' : '0');
}

export function initSidebar() {
    // Restore from localStorage; default collapsed on small screens
    const saved = localStorage.getItem('logs-collapsed');
    const defaultCollapsed = saved === null
        ? window.matchMedia('(max-width:980px)').matches
        : saved === '1';
    applyCollapsed(defaultCollapsed);

    logsToggle.addEventListener('click', () => {
        applyCollapsed(!rootEl.classList.contains('logs-collapsed'));
    });

    initResizer();
}

// ─── Drag-to-resize ───────────────────────────────────────────────────────────
function setSidebarWidth(px) {
    const clamped = Math.max(260, Math.min(Math.floor(window.innerWidth * 0.6), px));
    document.documentElement.style.setProperty('--sidebar-width', clamped + 'px');
    localStorage.setItem('logs-sidebar-width', String(clamped));
}

function initResizer() {
    // Restore saved width
    const saved = parseInt(localStorage.getItem('logs-sidebar-width') || '0', 10);
    if (saved > 0) {
        document.documentElement.style.setProperty('--sidebar-width', saved + 'px');
    }

    let dragging = false;
    let startWidth = 0;

    function onMove(e) {
        if (!dragging) return;
        const cx = e.touches ? e.touches[0].clientX : e.clientX;
        const lr = document.querySelector('.layout').getBoundingClientRect();
        setSidebarWidth(startWidth - (cx - (lr.right - startWidth)));
    }

    function onUp() {
        dragging = false;
        document.body.classList.remove('resizing');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        window.removeEventListener('touchmove', onMove);
        window.removeEventListener('touchend', onUp);
    }

    function onDown(e) {
        if (rootEl.classList.contains('logs-collapsed')) return;
        dragging = true;
        document.body.classList.add('resizing');
        startWidth = parseInt(
            getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width')
        ) || 380;
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        window.addEventListener('touchmove', onMove, { passive: false });
        window.addEventListener('touchend', onUp);
        e.preventDefault();
    }

    resizer.addEventListener('mousedown', onDown);
    resizer.addEventListener('touchstart', onDown, { passive: false });
}

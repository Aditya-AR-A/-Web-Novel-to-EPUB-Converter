/**
 * Theme toggle and header-height CSS variable watcher.
 */

const rootEl = document.documentElement;
const themeBtn = document.getElementById('themeToggle');

function applyTheme() {
    const isLight = rootEl.classList.contains('light');
    themeBtn.textContent = isLight ? '🌙 Dark' : '🌞 Light';
    localStorage.setItem('theme-mode', isLight ? 'light' : 'dark');
}

/** Initialise theme from localStorage and wire up the toggle button. */
export function initTheme() {
    if (localStorage.getItem('theme-mode') === 'light') {
        rootEl.classList.add('light');
    }
    applyTheme();
    themeBtn.addEventListener('click', () => {
        rootEl.classList.toggle('light');
        applyTheme();
    });
}

/** Keep the --header-height CSS variable in sync with the real header height. */
export function watchHeaderHeight() {
    const header = document.querySelector('header');
    function update() {
        const h = Math.round(header.getBoundingClientRect().height);
        document.documentElement.style.setProperty('--header-height', h + 'px');
    }
    update();
    window.addEventListener('resize', update);
}

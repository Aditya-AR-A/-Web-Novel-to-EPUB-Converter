import { $ } from './dom.js';

function applyThemeState(rootEl, themeBtn) {
    const iconSpan = themeBtn?.querySelector('.icon');
    const labelSpan = themeBtn?.querySelector('.label');

    if (rootEl.classList.contains('light')) {
        localStorage.setItem('theme-mode', 'light');
        if (iconSpan) iconSpan.textContent = '🌙';
        themeBtn?.setAttribute('aria-label', 'Switch to dark theme');
        themeBtn?.setAttribute('title', 'Switch to dark theme');
    } else {
        localStorage.setItem('theme-mode', 'dark');
        if (iconSpan) iconSpan.textContent = '🌞';
        themeBtn?.setAttribute('aria-label', 'Switch to light theme');
        themeBtn?.setAttribute('title', 'Switch to light theme');
    }
}

function updateHeaderHeight() {
    const headerEl = document.querySelector('header');
    if (!headerEl) return;
    const height = Math.round(headerEl.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--header-height', `${height}px`);
}

export function initLayout() {
    const rootEl = document.documentElement;
    const themeBtn = $('#themeToggle');

    if (localStorage.getItem('theme-mode') === 'light') {
        rootEl.classList.add('light');
    }

    applyThemeState(rootEl, themeBtn);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            rootEl.classList.toggle('light');
            applyThemeState(rootEl, themeBtn);
        });
    }

    updateHeaderHeight();
    window.addEventListener('resize', updateHeaderHeight);

    return { rootEl };
}

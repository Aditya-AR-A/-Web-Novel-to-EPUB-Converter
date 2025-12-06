import { $, $$ } from './dom.js';
import { fetchJSON } from './api.js';

const viewStateKey = 'epub-view-mode';
const expandedStateKey = 'epub-expanded-novels';
const searchStateKey = 'epub-search-query';

function escapeDatasetValue(value) {
    const strValue = String(value);
    if (window.CSS && typeof CSS.escape === 'function') {
        return CSS.escape(strValue);
    }
    return strValue.replace(/[^a-zA-Z0-9\-_.:]/g, '\\$&');
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function truncate(text, maxLength = 220) {
    if (!text) return '';
    const str = String(text);
    return str.length > maxLength ? `${str.slice(0, maxLength - 1)}…` : str;
}

function formatDate(iso) {
    if (!iso) return '—';
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return '—';
    return dt.toLocaleString();
}

function formatSize(bytes) {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function persistExpanded(expandedNovels) {
    try {
        localStorage.setItem(expandedStateKey, JSON.stringify([...expandedNovels]));
    } catch (error) {
        console.warn('Failed to persist expansion state', error);
    }
}

export function initEpubSection({ log }) {
    const epubList = $('#epubList');
    const epubGrid = $('#epubGrid');
    const listCard = $('#listCard');
    const gridCard = $('#gridCard');
    const selectAll = $('#selectAll');
    const searchInput = $('#searchInput');
    const downloadSelBtn = $('#downloadSelBtn');
    const refreshBtn = $('#refreshBtn');
    const viewToggleBtn = $('#viewToggleBtn');
    const viewToggleIcon = viewToggleBtn?.querySelector('img.icon');
    const viewToggleLabel = viewToggleBtn?.querySelector('.label');
    const pager = $('#pager');
    const pageSizeSelect = $('#pageSize');
    const downloadIconHtml = "<img src='/static/images/download.svg' alt='' class='icon' aria-hidden='true'>";

    const expandedNovels = new Set();
    let currentSearch = '';
    let currentPage = 1;

    let viewMode = localStorage.getItem(viewStateKey);
    if (viewMode !== 'list' && viewMode !== 'grid') {
        viewMode = 'grid';
    }

    try {
        const storedExpanded = JSON.parse(localStorage.getItem(expandedStateKey) || '[]');
        if (Array.isArray(storedExpanded)) {
            storedExpanded.forEach((key) => expandedNovels.add(key));
        }
    } catch (error) {
        expandedNovels.clear();
    }

    if (searchInput) {
        const savedQuery = localStorage.getItem(searchStateKey) || '';
        if (savedQuery) {
            currentSearch = savedQuery;
            searchInput.value = savedQuery;
        }
    }

    function selectedNames() {
        const set = new Set();
        $$('.sel-file:checked').forEach((cb) => {
            if (cb.dataset.name) set.add(cb.dataset.name);
        });
        return [...set];
    }

    function refreshNovelCheckboxes() {
        $$('.novel-card').forEach((card) => {
            const novelBox = card.querySelector('input.sel-novel');
            if (!novelBox) return;
            const fileBoxes = card.querySelectorAll('input.sel-file');
            if (!fileBoxes.length) {
                novelBox.indeterminate = false;
                novelBox.checked = false;
                return;
            }
            const allChecked = [...fileBoxes].every((cb) => cb.checked);
            const someChecked = [...fileBoxes].some((cb) => cb.checked);
            novelBox.checked = allChecked;
            novelBox.indeterminate = someChecked && !allChecked;
        });
    }

    function refreshSelectAllControl() {
        if (!selectAll) return;
        const fileBoxes = $$('.sel-file');
        if (!fileBoxes.length) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
            return;
        }
        const allChecked = fileBoxes.every((cb) => cb.checked);
        const someChecked = fileBoxes.some((cb) => cb.checked);
        selectAll.checked = allChecked;
        selectAll.indeterminate = someChecked && !allChecked;
    }

    function updateSelectionState() {
        const anySelected = selectedNames().length > 0;
        if (downloadSelBtn) downloadSelBtn.disabled = !anySelected;
        refreshNovelCheckboxes();
        refreshSelectAllControl();
    }

    function syncCheckboxes(source) {
        const name = source.dataset.name;
        if (!name) return;
        const selector = `input.sel-file[data-name="${escapeDatasetValue(name)}"]`;
        $$(selector).forEach((cb) => {
            if (cb === source) return;
            if (cb.disabled) return;
            cb.checked = source.checked;
        });
    }

    function updateViewToggleButton(targetMode) {
        if (!viewToggleBtn) return;
        const isGridTarget = targetMode === 'grid';
        const labelText = isGridTarget ? 'Grid View' : 'List View';
        const iconSrc = isGridTarget ? '/static/images/grid.svg' : '/static/images/list.svg';
        if (viewToggleIcon) viewToggleIcon.src = iconSrc;
        if (viewToggleIcon) viewToggleIcon.alt = '';
        if (viewToggleLabel) viewToggleLabel.textContent = labelText;
        const aria = `Switch to ${labelText.toLowerCase()}`;
        viewToggleBtn.setAttribute('aria-label', aria);
        viewToggleBtn.setAttribute('title', aria);
        viewToggleBtn.dataset.targetMode = targetMode;
    }

    function setViewMode(mode, { skipSave = false } = {}) {
        viewMode = mode === 'grid' ? 'grid' : 'list';
        if (viewMode === 'grid') {
            listCard?.classList.add('hidden');
            gridCard?.classList.remove('hidden');
            updateViewToggleButton('list');
        } else {
            gridCard?.classList.add('hidden');
            listCard?.classList.remove('hidden');
            updateViewToggleButton('grid');
        }
        if (!skipSave) {
            localStorage.setItem(viewStateKey, viewMode);
        }
        updateSelectionState();
    }

    async function downloadOne(name) {
        if (!name) return false;
        log(`Downloading ${name}...`);
        try {
            const response = await fetch(`/epub/download?name=${encodeURIComponent(name)}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = name;
            link.click();
            setTimeout(() => URL.revokeObjectURL(link.href), 10000);
        } catch (error) {
            log(`Download failed: ${error.message}`, 'error');
        }
        return false;
    }

    async function downloadSelected() {
        const names = selectedNames();
        if (!names.length) return;
        log(`Downloading ${names.length} selected as zip...`);
        try {
            const response = await fetch('/epubs/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ names })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'epubs.zip';
            link.click();
            setTimeout(() => URL.revokeObjectURL(link.href), 10000);
        } catch (error) {
            log(`Multi-download failed: ${error.message}`, 'error');
        }
    }

    function bindNovelCardEvents(card, previouslySelected) {
        const key = card.dataset.novel || '';
        const toggle = card.querySelector('.toggle-files');
        const wrapper = card.querySelector('.files-wrapper');
        const novelCheckbox = card.querySelector('input.sel-novel');

        if (toggle && wrapper) {
            toggle.addEventListener('click', (event) => {
                event.preventDefault();
                const nowOpen = !wrapper.classList.contains('open');
                if (nowOpen) {
                    wrapper.classList.add('open');
                    if (key) expandedNovels.add(key);
                } else {
                    wrapper.classList.remove('open');
                    if (key) expandedNovels.delete(key);
                }
                persistExpanded(expandedNovels);
            });
            if (key && expandedNovels.has(key)) {
                wrapper.classList.add('open');
            } else {
                wrapper.classList.remove('open');
            }
        }

        if (novelCheckbox) {
            novelCheckbox.addEventListener('change', () => {
                const checked = novelCheckbox.checked;
                card.querySelectorAll('input.sel-file').forEach((cb) => {
                    if (cb.disabled) return;
                    cb.checked = checked;
                    syncCheckboxes(cb);
                });
                updateSelectionState();
            });
        }

        card.querySelectorAll('input.sel-file').forEach((cb) => {
            if (previouslySelected.has(cb.dataset.name)) {
                cb.checked = true;
            }
            if (cb.checked) syncCheckboxes(cb);
            cb.addEventListener('change', () => {
                syncCheckboxes(cb);
                updateSelectionState();
            });
        });

        card.querySelectorAll('.download-file-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.preventDefault();
                const name = btn.dataset.name;
                if (name) downloadOne(name);
            });
        });

        const downloadLatestBtn = card.querySelector('.download-latest-btn');
        if (downloadLatestBtn?.dataset.name) {
            downloadLatestBtn.addEventListener('click', (event) => {
                event.preventDefault();
                const name = downloadLatestBtn.dataset.name;
                if (name) downloadOne(name);
            });
        }
    }

    function bindGridCardEvents(card, previouslySelected) {
        card.querySelectorAll('input.sel-file').forEach((cb) => {
            if (previouslySelected.has(cb.dataset.name)) {
                cb.checked = true;
            }
            if (cb.checked) syncCheckboxes(cb);
            cb.addEventListener('change', () => {
                syncCheckboxes(cb);
                updateSelectionState();
            });
        });

        card.querySelectorAll('.download-file-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.preventDefault();
                const name = btn.dataset.name;
                if (name) downloadOne(name);
            });
        });
    }

    function renderList(items, previouslySelected) {
        if (!epubList) return;
        if (!items.length) {
            epubList.innerHTML = "<div class='empty-state'>No EPUBs found.</div>";
            return;
        }

        epubList.innerHTML = items.map((item) => {
            const key = item.novel_key || '';
            const safeKey = escapeHtml(key);
            const baseTitle = item.title || key || 'Untitled';
            const title = escapeHtml(baseTitle);
            const safeAlt = escapeHtml(`${baseTitle} cover`);
            const fallbackInitial = escapeHtml(baseTitle.trim().charAt(0).toUpperCase() || '#');
            const author = item.author ? `<p class='author'>${escapeHtml(item.author)}</p>` : '';
            const description = item.description ? `<p class='description'>${escapeHtml(truncate(item.description, 320))}</p>` : '';
            const cover = item.cover_image
                ? `<div class='cover-frame'><img class='cover-img' src='${escapeHtml(item.cover_image)}' alt='${safeAlt}' loading='lazy' decoding='async' width='240' height='320'></div>`
                : `<div class='cover-frame placeholder' role='img' aria-label='No cover available'>${fallbackInitial}</div>`;
            const latest = formatDate(item.latest_created);
            const fileCount = item.file_count || 0;
            const isExpanded = expandedNovels.has(key);
            const filesHtml = (item.files || []).map((file) => {
                const fileName = escapeHtml(file.file_name || '');
                const size = formatSize(file.file_size);
                const created = formatDate(file.created_at);
                const downloadUrl = file.download_url || file.api_download_url || `/epub/download?name=${encodeURIComponent(file.file_name || '')}`;
                const directLink = escapeHtml(downloadUrl);
                return `<div class='file-row'>
                    <div class='file-top'>
                        <label><input type='checkbox' class='sel-file' data-name='${fileName}'></label>
                        <strong title='${fileName}'>${fileName}</strong>
                    </div>
                    <div class='file-meta'>
                        <span>${size}</span>
                        <span>Updated: ${created}</span>
                    </div>
                    <div class='file-actions'>
                        <button class='secondary download-file-btn' data-name='${fileName}'>${downloadIconHtml}<span class='label'>Download</span></button>
                        <a class='dl' href='${directLink}' target='_blank' rel='noopener'>Direct link</a>
                    </div>
                </div>`;
            }).join('');

            const expandedClass = isExpanded ? 'open' : '';
            const expandLabel = isExpanded ? 'Hide files' : `Show files (${fileCount})`;
            const newestFileName = item.files && item.files.length ? item.files[0].file_name || '' : '';
            const safeNewestFileName = escapeHtml(newestFileName);

            return `<article class='novel-card' data-novel='${safeKey}'>
                <label class='select-box'>
                    <input type='checkbox' class='sel-novel' data-novel='${safeKey}'>
                    <span>${fileCount}</span>
                </label>
                <div class='novel-header'>
                    ${cover}
                    <div class='meta'>
                        <h3>${title}</h3>
                        ${author}
                        ${description}
                        <div class='quick-meta'>
                            <span>Files: ${fileCount}</span>
                            <span>Latest: ${latest}</span>
                        </div>
                        <div class='novel-actions'>
                            <button class='toggle-files' data-novel='${safeKey}'>${expandLabel}</button>
                            <button class='secondary download-latest-btn' data-name='${safeNewestFileName}' ${item.files && item.files.length ? '' : 'disabled'}>${downloadIconHtml}<span class='label'>Download newest</span></button>
                        </div>
                    </div>
                </div>
                <div class='files-wrapper ${expandedClass}'>
                    <div class='files-list'>
                        ${filesHtml || "<div class='empty-state'>No files yet.</div>"}
                    </div>
                </div>
            </article>`;
        }).join('');

        $$('.novel-card').forEach((card) => bindNovelCardEvents(card, previouslySelected));
    }

    function renderGrid(items, previouslySelected) {
        if (!epubGrid) return;
        if (!items.length) {
            epubGrid.innerHTML = "<div class='empty-state'>No EPUBs found.</div>";
            return;
        }

        epubGrid.innerHTML = items.map((item) => {
            const key = item.novel_key || '';
            const safeKey = escapeHtml(key);
            const baseTitle = item.title || key || 'Untitled';
            const title = escapeHtml(baseTitle);
            const safeAlt = escapeHtml(`${baseTitle} cover`);
            const fallbackInitial = escapeHtml(baseTitle.trim().charAt(0).toUpperCase() || '#');
            const author = item.author ? `<p class='author'>${escapeHtml(item.author)}</p>` : '';
            const description = item.description ? `<p class='desc'>${escapeHtml(truncate(item.description, 200))}</p>` : '';
            const cover = item.cover_image
                ? `<img class='cover-img' src='${escapeHtml(item.cover_image)}' alt='${safeAlt}' loading='lazy' decoding='async' width='360' height='480'>`
                : `<div class='cover-placeholder' role='img' aria-label='No cover available'>${fallbackInitial}</div>`;
            const latest = formatDate(item.latest_created);
            const fileCount = item.file_count || 0;
            const latestFile = item.files && item.files.length ? item.files[0] : null;
            const latestSize = latestFile ? formatSize(latestFile.file_size) : '—';
            const latestFileName = latestFile && latestFile.file_name ? latestFile.file_name : '';
            const safeLatestFileName = escapeHtml(latestFileName);
            const latestDownloadUrlRaw = latestFile ? (latestFile.download_url || latestFile.api_download_url || `/epub/download?name=${encodeURIComponent(latestFile.file_name)}`) : '';
            const directLink = latestDownloadUrlRaw ? escapeHtml(latestDownloadUrlRaw) : '#';
            const selectAttrs = latestFileName ? `data-name='${safeLatestFileName}'` : 'disabled';
            const downloadControls = latestFile
                ? `<button class='secondary download-file-btn' data-name='${safeLatestFileName}'>${downloadIconHtml}<span class='label'>Download</span></button><a class='dl' href='${directLink}' target='_blank' rel='noopener'>Direct link</a>`
                : `<span class='no-files'>No files</span>`;

            return `<article class='epub-card' data-novel='${safeKey}'>
                <label class='select-box'><input type='checkbox' class='sel-novel sel-file' data-novel='${safeKey}' ${selectAttrs}><span>${fileCount}</span></label>
                <div class='cover-wrap'>
                    ${cover}
                    <span class='size-badge'>${latestSize}</span>
                </div>
                <div class='card-body'>
                    <h3 title='${title}'>${title}</h3>
                    ${author}
                    ${description}
                    <div class='meta-line'>
                        <span>Files: ${fileCount}</span>
                        <span>Latest: ${latest}</span>
                    </div>
                    <div class='card-actions'>
                        ${downloadControls}
                    </div>
                </div>
            </article>`;
        }).join('');

        $$('.epub-card').forEach((card) => bindGridCardEvents(card, previouslySelected));
    }

    function setupPagination(total, pageSize) {
        if (!pager) return;
        const pages = Math.max(1, Math.ceil(total / pageSize));
        currentPage = Math.min(currentPage, pages);
        const button = (p, label = undefined) => `<button class='secondary' data-page='${p}' ${p === currentPage ? 'disabled' : ''}>${label || p}</button>`;
        let html = '';
        if (pages > 1) {
            html += button(Math.max(1, currentPage - 1), '‹');
            const windowSize = 5;
            let start = Math.max(1, currentPage - 2);
            let end = Math.min(pages, start + windowSize - 1);
            if (end - start < windowSize - 1) {
                start = Math.max(1, end - windowSize + 1);
            }
            if (start > 1) {
                html += button(1, '1');
                if (start > 2) html += '<span style="opacity:.5;">…</span>';
            }
            for (let p = start; p <= end; p += 1) {
                html += button(p);
            }
            if (end < pages) {
                if (end < pages - 1) html += '<span style="opacity:.5;">…</span>';
                html += button(pages, String(pages));
            }
            html += button(Math.min(pages, currentPage + 1), '›');
        }
        pager.innerHTML = html;
        pager.querySelectorAll('button[data-page]').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.preventDefault();
                const targetPage = parseInt(btn.dataset.page, 10);
                if (!Number.isNaN(targetPage)) {
                    loadList(targetPage);
                }
            });
        });
    }

    async function loadList(page = 1, { preserveExpansion = true } = {}) {
        try {
            const previouslySelected = new Set(selectedNames());
            const pageSize = parseInt(pageSizeSelect?.value || '20', 10) || 20;
            const offset = (page - 1) * pageSize;
            const params = new URLSearchParams({ offset, limit: pageSize });
            if (currentSearch) params.set('search', currentSearch);
            const data = await fetchJSON(`/epubs/details?${params.toString()}`);
            const items = data?.data?.items || [];
            const total = data?.data?.total ?? items.length;

            if (preserveExpansion) {
                try {
                    const storedExpanded = JSON.parse(localStorage.getItem(expandedStateKey) || '[]');
                    expandedNovels.clear();
                    if (Array.isArray(storedExpanded)) storedExpanded.forEach((key) => expandedNovels.add(key));
                } catch (error) {
                    expandedNovels.clear();
                }
            }

            renderList(items, previouslySelected);
            renderGrid(items, previouslySelected);

            document.querySelectorAll('.files-wrapper.open').forEach(() => {
                // ensure class is consistent with persisted state; already handled in bind
            });

            setupPagination(total, pageSize);
            currentPage = page;
            updateSelectionState();
            setViewMode(viewMode, { skipSave: true });
        } catch (error) {
            log(`List error: ${error.message}`, 'error');
        }
    }

    refreshBtn?.addEventListener('click', (event) => {
        event.preventDefault();
        loadList(currentPage);
    });

    pageSizeSelect?.addEventListener('change', () => {
        loadList(1);
    });

    downloadSelBtn?.addEventListener('click', (event) => {
        event.preventDefault();
        downloadSelected();
    });

    selectAll?.addEventListener('change', () => {
        const checked = selectAll.checked;
        selectAll.indeterminate = false;
        $$('.sel-file').forEach((cb) => {
            cb.checked = checked;
        });
        updateSelectionState();
    });

    searchInput?.addEventListener('input', () => {
        const value = searchInput.value.trim();
        currentSearch = value;
        try {
            localStorage.setItem(searchStateKey, value);
        } catch (error) {
            console.warn('Failed to persist search query', error);
        }
        loadList(1, { preserveExpansion: true });
    });

    viewToggleBtn?.addEventListener('click', (event) => {
        event.preventDefault();
        const targetMode = viewToggleBtn.dataset.targetMode === 'list' ? 'list' : viewToggleBtn.dataset.targetMode === 'grid' ? 'grid' : (viewMode === 'list' ? 'grid' : 'list');
        setViewMode(targetMode);
    });

    setViewMode(viewMode, { skipSave: true });
    loadList();

    return { loadList };
}

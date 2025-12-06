import { $, $$ } from './dom.js';
import { fetchJSON } from './api.js';

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function truncate(text, maxLength = 150) {
    if (!text) return '';
    const str = String(text);
    return str.length > maxLength ? `${str.slice(0, maxLength - 1)}…` : str;
}

export function initMangaSection({ log }) {
    const mangaList = $('#mangaList');
    const mangaGrid = $('#mangaGrid');
    const mangaForm = $('#mangaForm');
    const mangaUrl = $('#mangaUrl');
    const mangaLang = $('#mangaLang');
    const mangaLimit = $('#mangaLimit');
    const mangaSplit = $('#mangaSplit');
    const mangaGenBtn = $('#mangaGenBtn');
    const mangaRefreshBtn = $('#mangaRefreshBtn');
    const mangaSearchInput = $('#mangaSearchInput');
    const mangaViewToggle = $('#mangaViewToggle');
    const mangaGridCard = $('.manga-grid-card');
    const mangaListCard = $('.manga-list-card');

    let currentSearch = '';
    let isGenerating = false;
    let viewMode = 'grid'; // 'grid' or 'list'

    // Tab switching
    const tabBtns = $$('.tab-btn');
    const tabPanels = $$('.tab-panel');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;
            tabBtns.forEach(b => b.classList.toggle('active', b === btn));
            tabPanels.forEach(p => p.classList.toggle('active', p.id === target));
        });
    });

    // View toggle
    if (mangaViewToggle) {
        mangaViewToggle.addEventListener('click', () => {
            viewMode = viewMode === 'grid' ? 'list' : 'grid';
            if (mangaGridCard) mangaGridCard.classList.toggle('hidden', viewMode !== 'grid');
            if (mangaListCard) mangaListCard.classList.toggle('hidden', viewMode !== 'list');
        });
    }

    async function loadMangaList() {
        if (!mangaList && !mangaGrid) return;

        try {
            const params = new URLSearchParams({ offset: 0, limit: 100 });
            if (currentSearch) params.set('search', currentSearch);

            const res = await fetchJSON(`/manga?${params}`);
            if (!res.ok || !res.data) {
                log?.(`Failed to load manga list: ${res.error || 'Unknown error'}`);
                return;
            }

            const items = res.data.items || [];
            renderMangaList(items);
        } catch (err) {
            log?.(`Error loading manga: ${err.message}`);
        }
    }

    function renderMangaList(items) {
        if (!mangaList && !mangaGrid) return;

        if (items.length === 0) {
            const emptyHtml = `
                <div class="empty-state">
                    <p>No manga found. Add one using the form above!</p>
                </div>
            `;
            if (mangaList) mangaList.innerHTML = emptyHtml;
            if (mangaGrid) mangaGrid.innerHTML = emptyHtml;
            return;
        }

        // Grid view with description, file sizes, and collapsible downloads
        const gridHtml = items.map(m => `
            <div class="manga-card" data-key="${escapeHtml(m.manga_key)}">
                <div class="manga-cover">
                    ${m.cover_image 
                        ? `<img src="${escapeHtml(m.cover_image)}" alt="${escapeHtml(m.title)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" /><div class="no-cover" style="display:none">📚</div>`
                        : `<div class="no-cover">📚</div>`
                    }
                </div>
                <div class="manga-info">
                    <h3 class="manga-title" title="${escapeHtml(m.title)}">${escapeHtml(truncate(m.title, 40))}</h3>
                    <p class="manga-meta">
                        ${m.author ? `<span class="author">👤 ${escapeHtml(m.author)}</span>` : ''}
                        ${m.status ? `<span class="status">${escapeHtml(m.status)}</span>` : ''}
                    </p>
                    ${m.description ? `<p class="manga-desc" title="${escapeHtml(m.description)}">${escapeHtml(truncate(m.description, 80))}</p>` : ''}
                    <p class="manga-stats">
                        📖 ${m.chapter_count || 0} chapters · 🖼️ ${m.total_pages || 0} pages
                        ${m.cbz_size_formatted ? `<br>💾 CBZ: ${escapeHtml(m.cbz_size_formatted)}` : ''}
                    </p>
                    <details class="manga-downloads">
                        <summary class="downloads-toggle">📥 Downloads</summary>
                        <div class="manga-actions">
                            <button class="btn-small primary download-cbz" data-key="${escapeHtml(m.manga_key)}" title="Download complete CBZ">
                                📦 ${m.cbz_size_formatted ? `CBZ (${m.cbz_size_formatted})` : 'CBZ'}
                            </button>
                            <button class="btn-small secondary download-pdf" data-key="${escapeHtml(m.manga_key)}" title="Download as PDF (slow)">
                                📄 PDF
                            </button>
                            <button class="btn-small secondary show-files" data-key="${escapeHtml(m.manga_key)}" title="Show all download options">
                                📁 More
                            </button>
                            <button class="btn-small danger delete-manga" data-key="${escapeHtml(m.manga_key)}" title="Delete manga">
                                🗑️
                            </button>
                        </div>
                        <div class="file-list" id="files-${escapeHtml(m.manga_key)}" style="display:none"></div>
                    </details>
                </div>
            </div>
        `).join('');

        // List view
        const listHtml = `
            <table class="manga-table">
                <thead>
                    <tr>
                        <th>Cover</th>
                        <th>Title</th>
                        <th>Author</th>
                        <th>Chapters</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map(m => `
                        <tr data-key="${escapeHtml(m.manga_key)}">
                            <td class="cover-cell">
                                ${m.cover_image 
                                    ? `<img src="${escapeHtml(m.cover_image)}" alt="" class="cover-thumb" loading="lazy" onerror="this.style.display='none'" />`
                                    : `<span class="no-cover-small">📚</span>`
                                }
                            </td>
                            <td class="title-cell">
                                <a href="${escapeHtml(m.source_url || '#')}" target="_blank" rel="noopener" title="${escapeHtml(m.title)}">
                                    ${escapeHtml(truncate(m.title, 50))}
                                </a>
                                ${m.description ? `<small class="desc-preview">${escapeHtml(truncate(m.description, 50))}</small>` : ''}
                            </td>
                            <td>${escapeHtml(m.author || '—')}</td>
                            <td>${m.chapter_count || 0}</td>
                            <td>${m.cbz_size_formatted || '—'}</td>
                            <td><span class="status-badge ${escapeHtml(m.status || '')}">${escapeHtml(m.status || '—')}</span></td>
                            <td class="actions-cell">
                                <button class="btn-icon download-cbz" data-key="${escapeHtml(m.manga_key)}" title="Download CBZ">📦</button>
                                <button class="btn-icon download-pdf" data-key="${escapeHtml(m.manga_key)}" title="Download PDF">📄</button>
                                <button class="btn-icon danger delete-manga" data-key="${escapeHtml(m.manga_key)}" title="Delete">🗑️</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        if (mangaGrid) mangaGrid.innerHTML = gridHtml;
        if (mangaList) mangaList.innerHTML = listHtml;

        // Attach event listeners
        attachMangaEventListeners();
    }

    function attachMangaEventListeners() {
        // Download CBZ
        $$('.download-cbz').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const key = btn.dataset.key;
                log?.(`Starting CBZ download for: ${key}`);
                const origText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '⏳...';
                // Open in new tab - the server will generate if not cached
                window.open(`/manga/${key}/download/cbz`, '_blank');
                setTimeout(() => {
                    btn.disabled = false;
                    btn.textContent = origText;
                }, 2000);
            });
        });

        // Download PDF
        $$('.download-pdf').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const key = btn.dataset.key;
                if (!confirm('PDF generation can take several minutes for large manga. Continue?')) return;
                log?.(`Starting PDF download for: ${key}`);
                window.open(`/manga/${key}/download/pdf`, '_blank');
            });
        });

        // Show more files
        $$('.show-files').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const key = btn.dataset.key;
                const fileListEl = document.getElementById(`files-${key}`);
                
                if (fileListEl.style.display === 'none') {
                    fileListEl.style.display = 'block';
                    fileListEl.innerHTML = '<span class="loading">Loading files...</span>';
                    
                    try {
                        const res = await fetchJSON(`/manga/${key}/files`);
                        if (res.ok && res.data.files) {
                            const files = res.data.files;
                            let html = '';
                            
                            if (files.length === 0) {
                                html = '<span class="no-files">No cached files yet.</span>';
                            } else {
                                html = files.map(f => `
                                    <a href="${f.url}" class="file-item" download>
                                        📁 ${escapeHtml(f.label)} <small>(${escapeHtml(f.size_formatted)})</small>
                                    </a>
                                `).join('');
                            }
                            
                            // Add split generation button
                            html += `
                                <div class="split-actions" style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--border);">
                                    <label style="font-size: 0.65rem; margin-right: 0.5rem;">Split every:</label>
                                    <select class="split-select" data-key="${escapeHtml(key)}" style="font-size: 0.65rem; padding: 0.25rem;">
                                        <option value="10">10 chapters</option>
                                        <option value="20">20 chapters</option>
                                        <option value="30">30 chapters</option>
                                        <option value="50">50 chapters</option>
                                    </select>
                                    <button class="btn-small generate-splits" data-key="${escapeHtml(key)}" style="margin-left: 0.35rem;">
                                        ✂️ Generate Splits
                                    </button>
                                </div>
                            `;
                            
                            fileListEl.innerHTML = html;
                            
                            // Attach split generation event
                            const splitBtn = fileListEl.querySelector('.generate-splits');
                            const splitSelect = fileListEl.querySelector('.split-select');
                            
                            if (splitBtn && splitSelect) {
                                splitBtn.addEventListener('click', async () => {
                                    const chaptersPerFile = parseInt(splitSelect.value, 10);
                                    splitBtn.disabled = true;
                                    splitBtn.textContent = '⏳ Generating...';
                                    
                                    try {
                                        const splitRes = await fetchJSON(`/manga/${key}/split?chapters_per_file=${chaptersPerFile}`, {
                                            method: 'POST'
                                        });
                                        
                                        if (splitRes.ok) {
                                            log?.(`✅ Generated ${splitRes.data.total_files} split CBZ files`);
                                            // Refresh the file list
                                            btn.click(); // close
                                            setTimeout(() => btn.click(), 100); // reopen
                                        } else {
                                            log?.(`❌ Split generation failed: ${splitRes.error}`);
                                        }
                                    } catch (err) {
                                        log?.(`❌ Error: ${err.message}`);
                                    } finally {
                                        splitBtn.disabled = false;
                                        splitBtn.textContent = '✂️ Generate Splits';
                                    }
                                });
                            }
                        } else {
                            fileListEl.innerHTML = '<span class="error">Failed to load files</span>';
                        }
                    } catch (err) {
                        fileListEl.innerHTML = '<span class="error">Error loading files</span>';
                    }
                } else {
                    fileListEl.style.display = 'none';
                }
            });
        });

        // Delete manga
        $$('.delete-manga').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const key = btn.dataset.key;
                if (!confirm(`Delete manga "${key}"? This cannot be undone.`)) return;

                try {
                    const res = await fetchJSON(`/manga/${key}`, { method: 'DELETE' });
                    if (res.ok) {
                        log?.(`Deleted manga: ${key}`);
                        loadMangaList();
                    } else {
                        log?.(`Failed to delete: ${res.error || 'Unknown error'}`);
                    }
                } catch (err) {
                    log?.(`Error deleting manga: ${err.message}`);
                }
            });
        });
    }

    // Form submission
    if (mangaForm) {
        mangaForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (isGenerating) return;

            const url = mangaUrl?.value?.trim();
            if (!url) {
                log?.('Please enter a manga URL');
                return;
            }

            isGenerating = true;
            if (mangaGenBtn) {
                mangaGenBtn.disabled = true;
                mangaGenBtn.textContent = 'Generating...';
            }

            try {
                log?.(`Starting manga generation for: ${url}`);
                const body = {
                    url,
                    translated_language: mangaLang?.value || null,
                    chapter_limit: mangaLimit?.value ? parseInt(mangaLimit.value, 10) : null,
                    use_data_saver: true,
                    page_workers: 4
                };

                const res = await fetchJSON('/manga/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (res.ok) {
                    const data = res.data;
                    log?.(`✅ Manga generated: ${data.metadata?.title || 'Unknown'} (${data.chapters} chapters)`);
                    
                    // Check if split CBZ generation was requested
                    const splitValue = parseInt(mangaSplit?.value || '0', 10);
                    if (splitValue > 0 && data.saved?.manga_key) {
                        log?.(`📦 Split CBZ option selected (${splitValue} chapters each) - use "More" button to generate splits`);
                    }
                    
                    loadMangaList();
                    if (mangaUrl) mangaUrl.value = '';
                } else {
                    log?.(`❌ Failed: ${res.error || 'Unknown error'}`);
                }
            } catch (err) {
                log?.(`❌ Error: ${err.message}`);
            } finally {
                isGenerating = false;
                if (mangaGenBtn) {
                    mangaGenBtn.disabled = false;
                    mangaGenBtn.textContent = 'Generate Manga';
                }
            }
        });
    }

    // Search
    if (mangaSearchInput) {
        let debounceTimer;
        mangaSearchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                currentSearch = mangaSearchInput.value.trim();
                loadMangaList();
            }, 300);
        });
    }

    // Refresh
    if (mangaRefreshBtn) {
        mangaRefreshBtn.addEventListener('click', loadMangaList);
    }

    // Initial load
    loadMangaList();

    return { loadList: loadMangaList };
}

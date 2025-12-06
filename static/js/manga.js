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

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '—';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
}

export function initMangaSection({ log }) {
    const mangaGrid = $('#mangaGrid');
    const mangaForm = $('#mangaForm');
    const mangaUrl = $('#mangaUrl');
    const mangaLang = $('#mangaLang');
    const mangaLimit = $('#mangaLimit');
    const mangaGenBtn = $('#mangaGenBtn');
    const mangaCancelBtn = $('#mangaCancelBtn');
    const mangaStopBtn = $('#mangaStopBtn');
    const mangaRefreshBtn = $('#mangaRefreshBtn');
    const mangaSearchInput = $('#mangaSearchInput');
    const mangaAutoUpload = $('#mangaAutoUpload');
    const mangaAutoDownload = $('#mangaAutoDownload');

    let currentSearch = '';
    let isGenerating = false;
    let mangaData = []; // Store manga data for popup

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

    // Create modal container
    const modalContainer = document.createElement('div');
    modalContainer.id = 'mangaModal';
    modalContainer.className = 'manga-modal';
    modalContainer.innerHTML = `
        <div class="manga-modal-backdrop"></div>
        <div class="manga-modal-content">
            <button class="manga-modal-close" aria-label="Close">&times;</button>
            <div class="manga-modal-body"></div>
        </div>
    `;
    document.body.appendChild(modalContainer);

    const modal = $('#mangaModal');
    const modalBackdrop = modal?.querySelector('.manga-modal-backdrop');
    const modalContent = modal?.querySelector('.manga-modal-content');
    const modalBody = modal?.querySelector('.manga-modal-body');
    const modalClose = modal?.querySelector('.manga-modal-close');

    function openModal(mangaKey) {
        const manga = mangaData.find(m => m.manga_key === mangaKey);
        if (!manga || !modal) return;

        modalBody.innerHTML = renderMangaModalContent(manga);
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        
        // Attach modal event listeners
        attachModalEventListeners(mangaKey, manga);
    }

    function closeModal() {
        if (!modal) return;
        modal.classList.remove('open');
        document.body.style.overflow = '';
    }

    // Close modal events
    modalBackdrop?.addEventListener('click', closeModal);
    modalClose?.addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    function renderMangaModalContent(manga) {
        const m = manga;
        return `
            <div class="modal-manga-header">
                <div class="modal-cover">
                    ${m.cover_image 
                        ? `<img src="${escapeHtml(m.cover_image)}" alt="${escapeHtml(m.title)}" />`
                        : `<div class="no-cover-large">📚</div>`
                    }
                </div>
                <div class="modal-info">
                    <h2 class="modal-title">${escapeHtml(m.title)}</h2>
                    <div class="modal-meta">
                        ${m.author ? `<span class="meta-item"><strong>Author:</strong> ${escapeHtml(m.author)}</span>` : ''}
                        ${m.artist ? `<span class="meta-item"><strong>Artist:</strong> ${escapeHtml(m.artist)}</span>` : ''}
                        ${m.status ? `<span class="meta-item"><span class="status-badge">${escapeHtml(m.status)}</span></span>` : ''}
                    </div>
                    <div class="modal-stats">
                        <span class="stat-item">📖 ${m.chapter_count || 0} chapters</span>
                        <span class="stat-item">🖼️ ${m.total_pages || 0} pages</span>
                        ${m.cbz_size_formatted ? `<span class="stat-item">💾 ${m.cbz_size_formatted}</span>` : ''}
                    </div>
                    ${m.genre && m.genre.length ? `
                        <div class="modal-genres">
                            ${(Array.isArray(m.genre) ? m.genre : [m.genre]).map(g => `<span class="genre-tag">${escapeHtml(g)}</span>`).join('')}
                        </div>
                    ` : ''}
                    ${m.source_url ? `<a href="${escapeHtml(m.source_url)}" target="_blank" rel="noopener" class="source-link">🔗 View Source</a>` : ''}
                </div>
            </div>
            
            ${m.description ? `
                <div class="modal-section">
                    <h3>Description</h3>
                    <p class="modal-description">${escapeHtml(m.description)}</p>
                </div>
            ` : ''}

            <div class="modal-section">
                <h3>📥 Downloads</h3>
                <div class="download-section">
                    <div class="download-range-controls">
                        <div class="range-inputs">
                            <label>
                                <span>From Chapter</span>
                                <input type="number" id="modal-range-from" value="1" min="1" />
                            </label>
                            <label>
                                <span>To Chapter</span>
                                <input type="number" id="modal-range-to" value="${m.chapter_count || 1}" min="1" />
                            </label>
                        </div>
                        <div class="download-buttons">
                            <button class="btn primary modal-download-range" data-key="${escapeHtml(m.manga_key)}">
                                📦 Download CBZ (Range)
                            </button>
                            <button class="btn secondary modal-download-all" data-key="${escapeHtml(m.manga_key)}">
                                📦 Download All
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="modal-section">
                <h3>☁️ Cloud Storage</h3>
                <div class="cloud-section">
                    ${m.mega_cbz_enabled 
                        ? `<button class="btn primary modal-open-mega" data-key="${escapeHtml(m.manga_key)}">☁️ Open MEGA Folder</button>`
                        : `<button class="btn secondary modal-upload-mega" data-key="${escapeHtml(m.manga_key)}">☁️ Upload to MEGA</button>`
                    }
                    <p class="cloud-hint">${m.mega_cbz_enabled ? 'Your manga is uploaded to MEGA cloud storage.' : 'Upload chapter CBZ files to your MEGA account for permanent storage.'}</p>
                </div>
            </div>

            <div class="modal-section">
                <h3>📖 Chapters</h3>
                <div class="chapters-list" id="modal-chapters-${escapeHtml(m.manga_key)}">
                    <div class="loading-chapters">Loading chapters...</div>
                </div>
            </div>

            <div class="modal-actions">
                <button class="btn danger modal-delete" data-key="${escapeHtml(m.manga_key)}">🗑️ Delete Manga</button>
            </div>
        `;
    }

    async function attachModalEventListeners(mangaKey, manga) {
        // Download range
        const rangeBtn = modalBody?.querySelector('.modal-download-range');
        rangeBtn?.addEventListener('click', () => {
            const from = document.getElementById('modal-range-from')?.value || '1';
            const to = document.getElementById('modal-range-to')?.value || '';
            const url = `/manga/${mangaKey}/download/range?from_chapter=${from}&to_chapter=${to}`;
            log?.(`📦 Downloading chapters ${from} to ${to}...`);
            window.location.href = url;
        });

        // Download all
        const allBtn = modalBody?.querySelector('.modal-download-all');
        allBtn?.addEventListener('click', () => {
            const url = `/manga/${mangaKey}/download/range`;
            log?.(`📦 Downloading all chapters...`);
            window.location.href = url;
        });

        // MEGA upload
        const megaUploadBtn = modalBody?.querySelector('.modal-upload-mega');
        megaUploadBtn?.addEventListener('click', async () => {
            if (!confirm(`Upload "${manga.title}" to MEGA?\n\nThis will create CBZ files for each chapter and upload them.`)) return;
            
            megaUploadBtn.disabled = true;
            megaUploadBtn.innerHTML = '☁️ Uploading...';
            log?.(`☁️ Starting MEGA upload for: ${mangaKey}`);
            
            try {
                const res = await fetchJSON(`/manga/${mangaKey}/upload-cbz-to-mega`, { method: 'POST' });
                if (res.ok) {
                    log?.(`☁️ ✅ Uploaded ${res.data.uploaded} chapters to MEGA`);
                    megaUploadBtn.innerHTML = '☁️ Open MEGA Folder';
                    megaUploadBtn.classList.remove('secondary');
                    megaUploadBtn.classList.add('primary');
                    megaUploadBtn.classList.remove('modal-upload-mega');
                    megaUploadBtn.classList.add('modal-open-mega');
                    loadMangaList();
                } else {
                    log?.(`☁️ ❌ Upload failed: ${res.error}`);
                    megaUploadBtn.innerHTML = '☁️ Upload to MEGA';
                }
            } catch (err) {
                log?.(`☁️ ❌ Error: ${err.message}`);
                megaUploadBtn.innerHTML = '☁️ Upload to MEGA';
            } finally {
                megaUploadBtn.disabled = false;
            }
        });

        // MEGA open folder
        const megaOpenBtn = modalBody?.querySelector('.modal-open-mega');
        megaOpenBtn?.addEventListener('click', async () => {
            try {
                const res = await fetchJSON(`/manga/${mangaKey}/mega-folder`);
                if (res.ok && res.data.folder_url) {
                    window.open(res.data.folder_url, '_blank');
                }
            } catch (err) {
                log?.(`☁️ Error: ${err.message}`);
            }
        });

        // Delete
        const deleteBtn = modalBody?.querySelector('.modal-delete');
        deleteBtn?.addEventListener('click', async () => {
            if (!confirm(`Delete "${manga.title}"?\n\nThis cannot be undone.`)) return;
            
            try {
                const res = await fetchJSON(`/manga/${mangaKey}`, { method: 'DELETE' });
                if (res.ok) {
                    log?.(`🗑️ Deleted: ${manga.title}`);
                    closeModal();
                    loadMangaList();
                } else {
                    log?.(`❌ Delete failed: ${res.error}`);
                }
            } catch (err) {
                log?.(`❌ Error: ${err.message}`);
            }
        });

        // Load chapters
        await loadChaptersInModal(mangaKey);
    }

    async function loadChaptersInModal(mangaKey) {
        const chaptersList = document.getElementById(`modal-chapters-${mangaKey}`);
        if (!chaptersList) return;

        try {
            const res = await fetchJSON(`/manga/${mangaKey}/chapters-info`);
            if (res.ok && res.data.chapters) {
                const chapters = res.data.chapters;
                
                // Update the range input max values
                const toInput = document.getElementById('modal-range-to');
                if (toInput && chapters.length > 0) {
                    toInput.value = res.data.last_chapter || chapters.length;
                    toInput.max = res.data.last_chapter || chapters.length;
                }
                
                if (chapters.length === 0) {
                    chaptersList.innerHTML = '<p class="no-chapters">No chapters found.</p>';
                    return;
                }

                chaptersList.innerHTML = `
                    <div class="chapters-grid">
                        ${chapters.map(ch => `
                            <div class="chapter-row">
                                <div class="chapter-info">
                                    <span class="chapter-num">Ch. ${escapeHtml(ch.chapter)}</span>
                                    ${ch.title ? `<span class="chapter-title">${escapeHtml(truncate(ch.title, 40))}</span>` : ''}
                                </div>
                                <div class="chapter-meta">
                                    <span class="page-count">${ch.pages} pages</span>
                                    ${ch.mega_url 
                                        ? `<a href="${escapeHtml(ch.mega_url)}" target="_blank" class="btn-mini cloud">☁️</a>`
                                        : `<a href="/manga/${escapeHtml(mangaKey)}/download/chapter/${escapeHtml(ch.chapter)}" class="btn-mini">📦</a>`
                                    }
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } else {
                chaptersList.innerHTML = '<p class="error">Failed to load chapters</p>';
            }
        } catch (err) {
            chaptersList.innerHTML = '<p class="error">Error loading chapters</p>';
        }
    }

    async function loadMangaList() {
        if (!mangaGrid) return;

        try {
            const params = new URLSearchParams({ offset: 0, limit: 100 });
            if (currentSearch) params.set('search', currentSearch);

            const res = await fetchJSON(`/manga?${params}`);
            if (!res.ok || !res.data) {
                log?.(`Failed to load manga list: ${res.error || 'Unknown error'}`);
                return;
            }

            mangaData = res.data.items || [];
            renderMangaGrid(mangaData);
        } catch (err) {
            log?.(`Error loading manga: ${err.message}`);
        }
    }

    function renderMangaGrid(items) {
        if (!mangaGrid) return;

        if (items.length === 0) {
            mangaGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📚</div>
                    <p>No manga found</p>
                    <span>Add a manga using the form above!</span>
                </div>
            `;
            return;
        }

        mangaGrid.innerHTML = items.map(m => `
            <div class="manga-card" data-key="${escapeHtml(m.manga_key)}">
                <div class="manga-cover">
                    ${m.cover_image 
                        ? `<img src="${escapeHtml(m.cover_image)}" alt="${escapeHtml(m.title)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" /><div class="no-cover" style="display:none">📚</div>`
                        : `<div class="no-cover">📚</div>`
                    }
                    <div class="card-overlay">
                        <span class="view-details">View Details</span>
                    </div>
                </div>
                <div class="manga-info">
                    <h3 class="manga-title" title="${escapeHtml(m.title)}">${escapeHtml(truncate(m.title, 35))}</h3>
                    <p class="manga-meta">
                        ${m.author ? `<span class="author">${escapeHtml(m.author)}</span>` : ''}
                    </p>
                    <div class="manga-stats">
                        <span>📖 ${m.chapter_count || 0}</span>
                        <span>🖼️ ${m.total_pages || 0}</span>
                        ${m.mega_cbz_enabled ? '<span class="cloud-badge">☁️</span>' : ''}
                    </div>
                </div>
            </div>
        `).join('');

        // Attach click events to cards
        $$('.manga-card').forEach(card => {
            card.addEventListener('click', () => {
                const key = card.dataset.key;
                openModal(key);
            });
        });
    }

    // Cancel generation
    if (mangaCancelBtn) {
        mangaCancelBtn.addEventListener('click', async () => {
            try {
                const res = await fetchJSON('/manga/cancel', { method: 'POST' });
                if (res.ok) {
                    log?.('⚠️ Manga generation cancelled');
                } else {
                    log?.(`Cancel failed: ${res.error}`);
                }
            } catch (err) {
                log?.(`Cancel error: ${err.message}`);
            }
        });
    }

    // Stop generation (graceful)
    if (mangaStopBtn) {
        mangaStopBtn.addEventListener('click', async () => {
            try {
                const res = await fetchJSON('/manga/stop', { method: 'POST' });
                if (res.ok) {
                    log?.('⏸️ Manga generation will stop after current chapter');
                } else {
                    log?.(`Stop failed: ${res.error}`);
                }
            } catch (err) {
                log?.(`Stop error: ${err.message}`);
            }
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
            updateGeneratingUI(true);

            try {
                log?.(`🚀 Starting manga generation for: ${url}`);
                const body = {
                    url,
                    translated_language: mangaLang?.value || null,
                    chapter_limit: mangaLimit?.value ? parseInt(mangaLimit.value, 10) : null,
                    use_data_saver: true,
                    page_workers: 4,
                    auto_upload_mega: mangaAutoUpload?.checked || false,
                    auto_download: mangaAutoDownload?.checked || false
                };

                const res = await fetchJSON('/manga/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (res.ok) {
                    const data = res.data;
                    log?.(`✅ Manga generated: ${data.metadata?.title || 'Unknown'} (${data.chapters} chapters)`);
                    
                    if (data.mega_upload && data.mega_upload.uploaded > 0) {
                        log?.(`☁️ Auto-uploaded ${data.mega_upload.uploaded} chapters to MEGA`);
                    }
                    
                    // Auto-download if checked
                    if (mangaAutoDownload?.checked && data.saved?.manga_key) {
                        log?.('📦 Starting auto-download...');
                        window.location.href = `/manga/${data.saved.manga_key}/download/range`;
                    }
                    
                    loadMangaList();
                    if (mangaUrl) mangaUrl.value = '';
                } else {
                    if (res.code === 'cancelled') {
                        log?.('⚠️ Generation was cancelled');
                    } else {
                        log?.(`❌ Failed: ${res.error || 'Unknown error'}`);
                    }
                }
            } catch (err) {
                log?.(`❌ Error: ${err.message}`);
            } finally {
                isGenerating = false;
                updateGeneratingUI(false);
            }
        });
    }

    function updateGeneratingUI(generating) {
        if (mangaGenBtn) {
            mangaGenBtn.disabled = generating;
            mangaGenBtn.textContent = generating ? 'Generating...' : 'Generate Manga';
        }
        if (mangaCancelBtn) {
            mangaCancelBtn.style.display = generating ? 'inline-flex' : 'none';
        }
        if (mangaStopBtn) {
            mangaStopBtn.style.display = generating ? 'inline-flex' : 'none';
        }
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

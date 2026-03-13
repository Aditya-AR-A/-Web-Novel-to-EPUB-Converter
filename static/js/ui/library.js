/**
 * EPUB library – grid & list rendering, view toggle, search, selection tracking.
 */
import { escapeHTML, groupByNovel, humanTitle, volLabel, chStart } from '../utils.js';
import { downloadSingle } from '../api/epubs.js';

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const gridViewBtn = document.getElementById('gridViewBtn');
const listViewBtn = document.getElementById('listViewBtn');
const gridView = document.getElementById('gridView');
const listView = document.getElementById('listView');
const epubBody = document.getElementById('epubBody');
const totalBadge = document.getElementById('totalBadge');
const searchBox = document.getElementById('searchBox');
const selectAllCb = document.getElementById('selectAll');
const pager = document.getElementById('pager');
const pageSizeSel = document.getElementById('pageSize');

// ─── Mutable state ────────────────────────────────────────────────────────────
export let allItems = [];               // raw flat filename list from server
export const selectedNames = new Set(); // cross-view selection

// ─── View toggle ──────────────────────────────────────────────────────────────
let viewMode = localStorage.getItem('epub-view') || 'grid';

export function setView(v) {
    viewMode = v;
    localStorage.setItem('epub-view', v);
    gridView.style.display = v === 'grid' ? 'grid' : 'none';
    listView.style.display = v === 'list' ? 'block' : 'none';
    gridViewBtn.classList.toggle('active', v === 'grid');
    listViewBtn.classList.toggle('active', v === 'list');
}

// ─── Selection helpers ────────────────────────────────────────────────────────
export function toggleSel(name, checked) {
    checked ? selectedNames.add(name) : selectedNames.delete(name);
    updateSelState();
}

export function clearSelection() {
    selectedNames.clear();
    updateSelState();
}

function updateSelState() {
    const any = selectedNames.size > 0;
    document.getElementById('downloadSelBtn').disabled = !any;
    document.getElementById('deleteSelBtn').disabled = !any;
}

// ─── Grid rendering ───────────────────────────────────────────────────────────
export function renderGrid(items) {
    const q = searchBox.value.trim().toLowerCase();
    const filtered = items.filter(n => !q || n.toLowerCase().includes(q));
    const grouped = groupByNovel(filtered);
    totalBadge.textContent = `(${filtered.length})`;

    if (grouped.size === 0) {
        gridView.innerHTML = `<div style='opacity:.5;padding:1rem;'>No EPUBs found.</div>`;
        return;
    }
    gridView.innerHTML = '';

    for (const [base, vols] of grouped) {
        const card = document.createElement('div');
        card.className = 'novel-card';

        const header = document.createElement('div');
        header.className = 'novel-card-header';

        const titleEl = document.createElement('div');
        titleEl.className = 'novel-card-title';
        titleEl.textContent = humanTitle(base);

        header.appendChild(titleEl);

        const metaRow = document.createElement('div');
        metaRow.style.display = 'flex';
        metaRow.style.alignItems = 'center';

        const meta = document.createElement('div');
        meta.className = 'novel-card-meta';
        meta.textContent = `${vols.length} volume${vols.length !== 1 ? 's' : ''}`;

        const expandBtn = document.createElement('button');
        expandBtn.className = 'novel-card-expand-btn';
        expandBtn.textContent = vols.length <= 3 ? 'Collapse' : 'Expand';

        metaRow.appendChild(meta);
        metaRow.appendChild(expandBtn);

        const volContainer = document.createElement('div');
        volContainer.className = 'volume-container' + (vols.length <= 3 ? ' expanded' : '');

        expandBtn.addEventListener('click', () => {
            const isExpanded = volContainer.classList.toggle('expanded');
            expandBtn.textContent = isExpanded ? 'Collapse' : 'Expand';
        });

        const volList = document.createElement('div');
        volList.className = 'volume-list';

        vols.forEach((name, i) => {
            const row = document.createElement('div');
            row.className = 'volume-row';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = selectedNames.has(name);
            cb.addEventListener('change', () => toggleSel(name, cb.checked));

            const lbl = document.createElement('span');
            lbl.className = 'volume-label' + (i === 0 ? ' vol1' : '');
            lbl.textContent = (i === 0 ? '★ ' : '') + volLabel(name);
            lbl.title = name;

            const dlBtn = document.createElement('button');
            dlBtn.className = 'secondary sm volume-dl-btn';
            dlBtn.textContent = '⬇';
            dlBtn.title = `Download ${name}`;
            dlBtn.addEventListener('click', () => downloadSingle(name));

            row.append(cb, lbl, dlBtn);
            volList.appendChild(row);
        });

        volContainer.appendChild(volList);
        card.append(header, metaRow, volContainer);
        gridView.appendChild(card);
    }
}

// ─── List rendering ───────────────────────────────────────────────────────────
export function renderList(items, page, pageSize) {
    const q = searchBox.value.trim().toLowerCase();
    const filtered = [...items]
        .filter(n => !q || n.toLowerCase().includes(q))
        .sort((a, b) => chStart(a) - chStart(b));

    const total = filtered.length;
    totalBadge.textContent = `(${total})`;

    const start = (page - 1) * pageSize;
    const pageItems = filtered.slice(start, start + pageSize);
    const grouped = groupByNovel(pageItems);

    if (grouped.size === 0) {
        epubBody.innerHTML = `<tr><td colspan='3' style='padding:1rem;opacity:.5;'>No EPUBs found.</td></tr>`;
    } else {
        epubBody.innerHTML = '';
        let groupId = 0;
        for (const [base, vols] of grouped) {
            groupId++;
            const expanded = vols.length <= 3;

            const trGroup = document.createElement('tr');
            trGroup.className = 'list-group-header';
            const trGroupTd = document.createElement('td');
            trGroupTd.setAttribute('colspan', '3');

            const trGroupDiv = document.createElement('div');
            trGroupDiv.style.display = 'flex';
            trGroupDiv.style.justifyContent = 'space-between';
            trGroupDiv.style.alignItems = 'center';

            const trGroupStrong = document.createElement('strong');
            trGroupStrong.textContent = escapeHTML(humanTitle(base));

            const trGroupSpan = document.createElement('span');
            trGroupSpan.style.fontSize = '0.75rem';
            trGroupSpan.style.opacity = '0.7';
            trGroupSpan.style.fontWeight = 'normal';
            trGroupSpan.textContent = ` (${vols.length} vol)`;
            trGroupStrong.appendChild(trGroupSpan);

            const trGroupBtn = document.createElement('button');
            trGroupBtn.className = 'secondary sm list-expand-btn';
            trGroupBtn.dataset.group = groupId;
            trGroupBtn.textContent = expanded ? 'Collapse' : 'Expand';

            trGroupDiv.appendChild(trGroupStrong);
            trGroupDiv.appendChild(trGroupBtn);
            trGroupTd.appendChild(trGroupDiv);
            trGroup.appendChild(trGroupTd);

            epubBody.appendChild(trGroup);

            vols.forEach(name => {
                const tr = document.createElement('tr');
                tr.className = `list-group-item group-${groupId}`;
                tr.style.display = expanded ? '' : 'none';

                const td1 = document.createElement('td');
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'sel';
                cb.dataset.name = name;
                cb.checked = selectedNames.has(name);
                td1.appendChild(cb);

                const td2 = document.createElement('td');
                td2.textContent = name;

                const td3 = document.createElement('td');
                const btn = document.createElement('button');
                btn.className = 'secondary sm list-dl-btn';
                btn.dataset.name = name;
                btn.textContent = '⬇ Download';
                td3.appendChild(btn);

                tr.appendChild(td1);
                tr.appendChild(td2);
                tr.appendChild(td3);
                epubBody.appendChild(tr);
            });
        }
    }

    epubBody.querySelectorAll('.list-expand-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const gid = btn.dataset.group;
            const rows = epubBody.querySelectorAll(`.group-${gid}`);
            if (!rows.length) return;

            const shouldExpand = rows[0].style.display === 'none';
            rows.forEach(r => {
                r.style.display = shouldExpand ? '' : 'none';
            });

            btn.textContent = shouldExpand ? 'Collapse' : 'Expand';
        });
    });

    epubBody.querySelectorAll('input.sel').forEach(cb =>
        cb.addEventListener('change', () => toggleSel(cb.dataset.name, cb.checked))
    );
    epubBody.querySelectorAll('.list-dl-btn').forEach(btn =>
        btn.addEventListener('click', () => downloadSingle(btn.dataset.name))
    );

    // Pagination
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const cur = Math.min(page, pages);
    const btn = (p, label) =>
        `<button class='secondary' style='padding:.35rem .55rem;font-size:.75rem;'
            data-page='${p}' ${p === cur ? 'disabled' : ''}>${label ?? p}</button>`;

    let html = '';
    if (pages > 1) {
        html += btn(Math.max(1, cur - 1), '‹');
        let s = Math.max(1, cur - 2), e = Math.min(pages, s + 4);
        if (e - s < 4) s = Math.max(1, e - 4);
        if (s > 1) html += btn(1, '1') + (s > 2 ? '<span style="opacity:.5;"> … </span>' : '');
        for (let p = s; p <= e; p++) html += btn(p);
        if (e < pages) html += (e < pages - 1 ? '<span style="opacity:.5;"> … </span>' : '') + btn(pages, String(pages));
        html += btn(Math.min(pages, cur + 1), '›');
    }
    pager.innerHTML = html;
    pager.querySelectorAll('button[data-page]').forEach(b =>
        b.addEventListener('click', () => {
            renderList(allItems, parseInt(b.dataset.page), parseInt(pageSizeSel.value) || 20);
        })
    );
}

// ─── Public: refresh both views ───────────────────────────────────────────────
/**
 * @param {string[]} items – flat filename list
 * @param {number} [page]
 */
export function refreshViews(items, page = 1) {
    allItems = items;
    renderGrid(items);
    renderList(items, page, parseInt(pageSizeSel.value) || 20);
}

// ─── Wiring ───────────────────────────────────────────────────────────────────
export function initLibrary() {
    setView(viewMode);

    gridViewBtn.addEventListener('click', () => setView('grid'));
    listViewBtn.addEventListener('click', () => setView('list'));

    searchBox.addEventListener('input', () => {
        renderGrid(allItems);
        renderList(allItems, 1, parseInt(pageSizeSel.value) || 20);
    });

    pageSizeSel.addEventListener('change', () =>
        renderList(allItems, 1, parseInt(pageSizeSel.value) || 20)
    );

    selectAllCb.addEventListener('change', function () {
        document.querySelectorAll('tbody input.sel').forEach(cb => {
            cb.checked = this.checked;
            toggleSel(cb.dataset.name, this.checked);
        });
    });
}

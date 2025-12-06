import { initLayout } from './layout.js';
import { initLogs } from './logs.js';
import { initEpubSection } from './epubs.js';
import { initForm } from './form.js';
import { initMangaSection } from './manga.js';

document.addEventListener('DOMContentLoaded', () => {
    const layout = initLayout();
    const logs = initLogs({ rootEl: layout.rootEl });
    const epubs = initEpubSection({ log: logs.log });
    const manga = initMangaSection({ log: logs.log });
    initForm({ log: logs.log, refreshList: epubs.loadList });
});

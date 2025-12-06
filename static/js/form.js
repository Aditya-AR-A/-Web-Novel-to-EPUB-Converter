import { $ } from './dom.js';
import { fetchJSON } from './api.js';

export function initForm({ log, refreshList }) {
    const form = $('#genForm');
    const generateBtn = $('#genBtn');
    const cancelBtn = $('#cancelBtn');
    const stopBtn = $('#stopBtn');

    if (!form || !generateBtn || !cancelBtn || !stopBtn) {
        return;
    }

    async function generate(event) {
        event.preventDefault();

        const originalLabel = generateBtn.innerHTML;
        generateBtn.disabled = true;
        generateBtn.innerHTML = "<span class='spinner'></span> Generating...";
        cancelBtn.disabled = false;
        stopBtn.disabled = true;
        log('Starting generation...');

        try {
            const payload = {
                url: $('#url')?.value.trim() || '',
                chapters_per_book: parseInt($('#chapters_per_book')?.value || '500', 10) || 500,
                chapter_workers: parseInt($('#chapter_workers')?.value || '0', 10) || 0,
                chapter_limit: parseInt($('#chapter_limit')?.value || '0', 10) || 0,
                start_chapter: parseInt($('#start_chapter')?.value || '1', 10) || 1
            };

            stopBtn.disabled = false;
            const response = await fetchJSON('/epub/generate', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            const filenames = response?.data?.filenames;
            log(`Generation complete. Files: ${Array.isArray(filenames) ? filenames.join(', ') : 'n/a'}`);

            if (response?.data?.log_lines) {
                response.data.log_lines.forEach((line) => log(line));
            } else if (response?.data?.summary) {
                log('--- Chapter Summary ---');
                response.data.summary.forEach((line) => log(line));
            }

            await refreshList();
        } catch (error) {
            if (/cancel/i.test(error.message)) {
                log('Generation cancelled by user.', 'warn');
            } else {
                log(`Generation failed: ${error.message}`, 'error');
            }
        } finally {
            generateBtn.disabled = false;
            generateBtn.innerHTML = originalLabel;
            cancelBtn.disabled = true;
            stopBtn.disabled = true;
        }
    }

    form.addEventListener('submit', generate);

    cancelBtn.addEventListener('click', async (event) => {
        event.preventDefault();
        try {
            await fetchJSON('/epub/cancel', { method: 'POST', body: JSON.stringify({}) });
            log('Cancellation requested...', 'warn');
            cancelBtn.disabled = true;
        } catch (error) {
            log(`Cancel failed: ${error.message}`, 'error');
        }
    });

    stopBtn.addEventListener('click', async (event) => {
        event.preventDefault();
        try {
            await fetchJSON('/epub/stop', { method: 'POST', body: JSON.stringify({}) });
            log('Stop requested — will finish current chapter and build partial EPUB.', 'warn');
            stopBtn.disabled = true;
        } catch (error) {
            log(`Stop failed: ${error.message}`, 'error');
        }
    });
}

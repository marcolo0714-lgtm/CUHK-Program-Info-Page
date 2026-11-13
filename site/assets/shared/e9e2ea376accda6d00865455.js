
(() => {
    const source = document.getElementById('course-detail-source');
    if (!source) return;
    let payload;
    function getPayload() {
        if (!payload) {
            payload = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = source.dataset.src;
                script.onload = () => {
                    const data = script.courseDetails;
                    script.remove();
                    if (data) resolve(data);
                    else reject(new Error('Course details unavailable'));
                };
                script.onerror = () => { script.remove(); reject(new Error('Course details unavailable')); };
                document.head.append(script);
            }).catch(error => { payload = null; throw error; });
        }
        return payload;
    }
    async function load(container) {
        const cells = Array.from(container.querySelectorAll('[data-course-detail]'));
        if (!cells.length || container.dataset.loading) return;
        container.dataset.loading = 'true';
        try {
            const data = await getPayload();
            for (const cell of cells) {
                if (!(cell.dataset.courseDetail in data)) throw new Error('Missing course detail');
                cell.outerHTML = data[cell.dataset.courseDetail];
            }
            const applySettings = window.applyTableSettings;
            if (typeof applySettings === 'function') applySettings();
            if (window.rewriteLocalPageLinks) window.rewriteLocalPageLinks(container);
            container.querySelector('.course-detail-error')?.remove();
        } catch (error) {
            cells.forEach(cell => { if (cell.dataset.courseDetail) cell.textContent = 'Unavailable'; });
            if (!container.querySelector('.course-detail-error')) {
                const message = document.createElement('p');
                message.className = 'course-detail-error';
                const retry = document.createElement('button');
                retry.type = 'button';
                retry.textContent = 'Retry loading course details';
                retry.addEventListener('click', () => load(container));
                const fallback = document.createElement('a');
                fallback.href = source.dataset.fallback;
                fallback.textContent = 'Open course details';
                message.append(retry, ' · ', fallback);
                container.append(message);
            }
        } finally {
            delete container.dataset.loading;
        }
    }
    document.querySelectorAll('details.course-details').forEach(details => {
        details.addEventListener('toggle', () => { if (details.open) load(details); });
        if (details.open) load(details);
    });
    document.querySelectorAll('table').forEach(table => {
        if (!table.closest('details') && table.querySelector('[data-course-detail]')) load(table.parentElement);
    });
})();

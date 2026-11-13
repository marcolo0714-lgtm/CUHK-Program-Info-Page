
(() => {
    const local = location.protocol === 'file:' ||
        ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    window.publicationLink = value => {
        if (!local || !value || value.startsWith('#')) return value;
        const url = new URL(value, document.baseURI);
        if (!['file:', 'http:', 'https:'].includes(url.protocol) || url.origin !== location.origin) return value;
        if (url.pathname.endsWith('/')) url.pathname += 'index.html';
        else if (!url.pathname.endsWith('.html') &&
            /\/(?:majors|minors)\/[^/]+$|\/\d{4}_\d{2}\/checker$/.test(url.pathname))
            url.pathname += '.html';
        return url.href;
    };
    window.rewriteLocalPageLinks = root => {
        if (!local) return;
        root.querySelectorAll('a[href], option[value], [data-url]').forEach(element => {
            if (element.hasAttribute('href')) element.setAttribute('href', window.publicationLink(element.getAttribute('href')));
            if (element.hasAttribute('data-url')) element.setAttribute('data-url', window.publicationLink(element.getAttribute('data-url')));
            else if (element.tagName === 'OPTION') element.value = window.publicationLink(element.value);
        });
    };
    document.addEventListener('DOMContentLoaded', () => window.rewriteLocalPageLinks(document));
    document.addEventListener('click', event => {
        const anchor = event.target.closest('a[href]');
        if (anchor) anchor.setAttribute('href', window.publicationLink(anchor.getAttribute('href')));
    }, true);
    document.addEventListener('change', event => {
        if (event.target.tagName === 'SELECT') window.rewriteLocalPageLinks(event.target);
    }, true);
})();

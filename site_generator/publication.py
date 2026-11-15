"""Publish compact, canonical static pages without changing their layout."""

from hashlib import sha256
import html
import json
import os
import posixpath
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from uuid import uuid4


SITE = Path(__file__).resolve().parents[1] / "site"


def relative_site_url(url, page_path):
    """Resolve a site-root URL relative to its physical HTML file."""
    path = Path(page_path)
    relative = path.relative_to(SITE).as_posix() if path.is_relative_to(SITE) else path.name
    result = posixpath.relpath(url.lstrip("/"), posixpath.dirname(relative) or ".")
    return result if result.startswith(".") else "./" + result


def canonical_link(value):
    """Normalize only local HTML links, preserving query strings and fragments."""
    parts = urlsplit(html.unescape(value))
    if parts.scheme or parts.netloc or not parts.path.endswith(".html"):
        return value
    path = parts.path[:-10] if parts.path.endswith("index.html") else parts.path[:-5]
    path = path or "./"
    if parts.query:
        path += "?" + parts.query
    if parts.fragment:
        path += "#" + parts.fragment
    return html.escape(path, quote=True)


def asset(content, suffix, folder="shared"):
    payload = content.encode("utf-8")
    name = sha256(payload).hexdigest()[:24] + suffix
    target = SITE / "assets" / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return "/" + target.relative_to(SITE).as_posix()


def prune_assets(site_root=SITE):
    """Remove only unreferenced content-addressed assets owned by this generator."""
    pattern = re.compile(r"/assets/(?:shared|course-details)/[a-f0-9]{24}\.(?:css|json|js|html)\b")
    referenced = set()
    for page in site_root.rglob("*.html"):
        if "assets" not in page.relative_to(site_root).parts:
            referenced.update(pattern.findall(page.read_text(encoding="utf-8")))
    pending = list(referenced)
    while pending:
        url = pending.pop()
        path = site_root / url.lstrip("/")
        if path.exists():
            for child in pattern.findall(path.read_text(encoding="utf-8")):
                if child not in referenced:
                    referenced.add(child)
                    pending.append(child)
    for folder in ("shared", "course-details"):
        directory = site_root / "assets" / folder
        if not directory.exists():
            continue
        if not directory.resolve().is_relative_to(site_root.resolve()):
            raise ValueError(f"Asset directory escaped the site: {directory}")
        for path in directory.iterdir():
            if not re.fullmatch(r"[a-f0-9]{24}\.(?:css|js|json|html)", path.name):
                continue
            if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
                raise ValueError(f"Asset escaped its generated directory: {path}")
            url = "/" + path.relative_to(site_root).as_posix()
            if url not in referenced:
                path.unlink()


def prepare_page(content, page_path=None):
    """Keep the course overview in HTML and defer only its lengthy details."""
    content = re.sub(
        r'\b(href|value|data-url)="([^"]*)"',
        lambda match: f'{match[1]}="{canonical_link(match[2])}"',
        content,
    )
    content = re.sub(
        r'(content="0;\s*url=)([^"]+)',
        lambda match: match[1] + canonical_link(match[2]),
        content, flags=re.I,
    )
    def search_links(match):
        entries = json.loads(match[1])
        for entry in entries:
            entry[1] = html.unescape(canonical_link(entry[1]))
        payload = json.dumps(entries, ensure_ascii=False).replace("<", "\\u003c")
        return f'<script id="programme-search-data" type="application/json">{payload}</script>'

    content = re.sub(
        r'<script id="programme-search-data" type="application/json">(.*?)</script>',
        search_links, content, flags=re.S,
    )
    local_script = asset(LOCAL_SCRIPT, ".js")
    # Run before programme search and scheme-selection scripts. Only local
    # browsing uses physical filenames; hosted links retain their clean URLs.
    local_tag = f'<script src="{local_script}"></script>'
    if "<head>" in content:
        content = content.replace("<head>", "<head>" + local_tag, 1)
    elif "<body>" in content:
        content = content.replace("<body>", "<body>" + local_tag, 1)
    # Root redirect documents need an actual filename when opened via file://.
    content = re.sub(r'(content="0;\s*url=)([^"?#]+/)(")', r'\1\2index.html\3', content, flags=re.I)
    details = {}

    def defer_row(match):
        body = match[0]
        key = sha256(body.encode("utf-8")).hexdigest()[:24]
        details[key] = body
        return f'<td colspan="4" data-course-detail="{key}">Loading…</td>'

    content = re.sub(
        r'<td class="col-t1-schedule">.*?</td>\s*<td class="col-t2-schedule">.*?</td>'
        r'\s*<td class="col-prereq">.*?</td>\s*<td class="col-minors">.*?</td>',
        defer_row, content, flags=re.S,
    )
    if details:
        payload = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        # A deferred script works over file:// as well as HTTP; fetch(JSON) is
        # blocked by browsers for local files.
        url = asset("document.currentScript.courseDetails=" + payload + ";", ".js", "course-details")
        fallback = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,follow"><title>Course schedules and enrolment information</title>'
            + local_tag + '<h1>Course schedules and enrolment information</h1>'
        )
        fallback += "".join(re.findall(r"<style>.*?</style>", content, re.S))
        # A complete standalone table view remains available without JavaScript.
        tables = re.findall(r'<table\b[^>]*--course-.*?</table>', content, re.S)
        fallback += "".join(tables)
        fallback = re.sub(
            r'<td colspan="4" data-course-detail="([^"]+)">.*?</td>',
            lambda match: details[match[1]],
            fallback, flags=re.S,
        )
        if page_path:
            path = Path(page_path)
            base = "/" + (path.relative_to(SITE).as_posix() if path.is_relative_to(SITE) else path.name)
            fallback = re.sub(
                r'href="([^"]+)"',
                lambda match: f'href="{html.escape(urljoin(base, html.unescape(match[1])), quote=True)}"',
                fallback,
            )
        # The fallback lives in assets/course-details, rather than alongside
        # the programme page, and must also work without a web server.
        fallback_path = SITE / "assets/course-details/fallback.html"
        fallback = re.sub(
            r'\b(href|src)="(/[^/"][^"]*)"',
            lambda match: f'{match[1]}="{relative_site_url(match[2], fallback_path)}"', fallback,
        )
        fallback_url = asset(fallback + "</html>", ".html", "course-details")
        content = content.replace("</body>", (
            f'<div id="course-detail-source" data-src="{url}" data-fallback="{fallback_url}"></div>'
            '<noscript><p>For full teaching schedules and enrolment information, '
            f'<a href="{fallback_url}">open course details</a>.</p></noscript></body>'
        ))
        content = content.replace("</body>", f'<script src="{asset(DETAIL_SCRIPT, ".js")}"></script></body>')

    def external_style(match):
        return f'<link rel="stylesheet" href="{asset(match[1], ".css")}">'

    def external_script(match):
        attrs, body = match[1], match[2]
        if "src=" in attrs or re.search(r'type=["\'](?!application/javascript|text/javascript)', attrs):
            return match[0]
        if not body.strip():
            return match[0]
        return f'<script src="{asset(body, ".js")}"></script>'

    content = re.sub(r"<style>(.*?)</style>", external_style, content, flags=re.S)
    content = re.sub(r"<script([^>]*)>(.*?)</script>", external_script, content, flags=re.S)
    if page_path:
        content = re.sub(
            r'\b(href|src|data-src|data-fallback)="(/assets/[^"]+)"',
            lambda match: f'{match[1]}="{relative_site_url(match[2], page_path)}"', content,
        )
    if len(content.encode("utf-8")) > 1_500_000:
        raise ValueError(f"{page_path}: generated HTML is {len(content.encode('utf-8'))} bytes, exceeding the 1.5 MB publication budget")
    return content


LOCAL_SCRIPT = r"""
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
"""


DETAIL_SCRIPT = r"""
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
"""

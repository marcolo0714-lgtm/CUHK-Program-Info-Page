"""Shared header controls and information dialog for the generated site pages."""

import json
from html import escape

INFO_CSS = """
.site-info-actions { display:flex; justify-content:flex-end; gap:8px; margin-bottom:16px; }
.programme-toolbar { display:flex; flex-wrap:wrap; align-items:flex-start; gap:8px; margin-bottom:16px; }
.programme-toolbar .site-info-actions { margin:0 0 0 auto; }
.programme-search { position:relative; flex:1 1 11rem; min-width:0; max-width:28rem; }
.programme-search input { width:100%; height:32px; padding:4px 9px; font:inherit; font-size:.9rem;
    color:var(--text); background:var(--card); border:1px solid var(--border); border-radius:6px; }
.programme-suggestions { position:absolute; z-index:60; top:100%; left:0; right:0;
    max-height:min(18rem,45vh); overflow:auto; list-style:none; margin:4px 0 0; padding:4px;
    background:var(--card); border:1px solid var(--border); border-radius:6px; box-shadow:0 4px 14px #0002; }
.programme-suggestions li { padding:6px 8px; overflow-wrap:anywhere; }
.programme-suggestions [role=option] { cursor:pointer; }
.programme-suggestions [role=option]:hover,
.programme-suggestions [aria-selected=true] { background:#e8f0fe; }
.site-info-actions .year-select { margin:0; }
.site-info-actions > * { min-height:32px; }
.bar-controls > :is(.bar-year-select, .site-info-button, .settings-toggle) {
    height:32px; padding:4px 10px; border:1px solid var(--border); border-radius:6px;
    background:var(--card); color:var(--text); font:inherit; font-size:.85rem; }
.bar-controls > :is(.bar-year-select, .site-info-button, .settings-toggle):hover {
    border-color:var(--accent); background:#e8f0fe; color:var(--text); }
.site-info-actions .site-info-button { display:inline-flex; align-items:center; justify-content:center;
    gap:4px; padding:4px 8px; border:1px solid var(--border); border-radius:6px;
    background:var(--card); color:var(--accent); cursor:pointer;
    font:inherit; font-size:.85rem; white-space:nowrap; }
.site-info-actions .site-info-button:hover, .site-info-close:hover { border-color:var(--accent); }
.site-info-dialog { position:fixed; inset:0; margin:auto; width:min(38rem, calc(100% - 32px));
    max-height:calc(100vh - 32px); max-height:calc(100dvh - 32px); overflow:auto;
    overscroll-behavior:contain; padding:clamp(14px, 4vw, 24px);
    border:1px solid var(--border); border-radius:12px;
    background:var(--card); color:var(--text); box-shadow:0 12px 40px #0004; }
.site-info-dialog::backdrop { background:#0008; }
.site-info-dialog header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.site-info-dialog h2 { margin:0; padding:0; border:0; color:inherit; }
.site-info-dialog h3, .site-info-dialog p { margin:12px 0 6px; }
.site-info-dialog ul, .site-info-dialog ol { margin:6px 0; padding-left:1.4em; }
.site-info-dialog a { overflow-wrap:anywhere; }
.site-info-dialog .site-info-contact { display:flex; flex-wrap:wrap; gap:12px 32px; }
.site-info-close { padding:4px 10px; border:1px solid var(--border); border-radius:6px;
    background:var(--card); color:inherit; font:inherit; cursor:pointer; }
@media (max-width:768px) {
    .bar-controls > :is(.bar-year-select, .site-info-button, .settings-toggle) { padding-inline:6px; }
}
"""


def information_button(label="Information"):
    return (
        '<button type="button" class="site-info-button" aria-haspopup="dialog" '
        'aria-controls="site-information" onclick="document.getElementById(\'site-information\').showModal()">'
        f'<span aria-hidden="true">&#9432;</span> {label}</button>'
    )


SEARCH_SCRIPT = r"""
<script>
(() => {
    const input = document.getElementById('programme-search');
    const list = document.getElementById('programme-suggestions');
    const entries = JSON.parse(document.getElementById('programme-search-data').textContent);
    const normalize = value => value.toLowerCase().replace(/\./g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const compact = value => value.replace(/ /g, '');
    const names = entries.map(([label, target]) => ({label, target, name: normalize(label)}));
    let matches = [];
    let active = -1;

    function distance(a, b) {
        let previous = Array.from({length: b.length + 1}, (_, i) => i);
        for (let i = 1; i <= a.length; i++) {
            const row = [i];
            for (let j = 1; j <= b.length; j++) {
                row[j] = Math.min(row[j - 1] + 1, previous[j] + 1,
                    previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
            }
            previous = row;
        }
        return previous[b.length];
    }

    function score(query, name) {
        const key = compact(query);
        const full = compact(name);
        if (key === full) return 0;
        if (full.startsWith(key)) return 1;
        if (name.includes(query) || full.includes(key)) return 2;
        if (key.length < 3) return Infinity;
        const tolerance = key.length >= 6 ? 3 : key.length >= 4 ? 2 : 1;
        let best = Infinity;
        for (const candidate of [...name.split(' '), full]) {
            for (let size = Math.max(1, key.length - tolerance);
                 size <= Math.min(candidate.length, key.length + tolerance); size++) {
                best = Math.min(best, distance(key, candidate.slice(0, size)));
            }
        }
        return best <= tolerance ? 3 + best : Infinity;
    }

    function setOpen(open) {
        list.hidden = !open;
        input.setAttribute('aria-expanded', String(open));
        if (!open) input.removeAttribute('aria-activedescendant');
    }

    function update() {
        const query = normalize(input.value);
        active = -1;
        input.removeAttribute('aria-activedescendant');
        list.replaceChildren();
        matches = query ? names.map(entry => ({entry, rank: score(query, entry.name)}))
            .filter(item => Number.isFinite(item.rank))
            .sort((a, b) => a.rank - b.rank || a.entry.label.localeCompare(b.entry.label))
            .slice(0, 8).map(item => item.entry) : [];
        matches.forEach((entry, index) => {
            const option = document.createElement('li');
            option.id = 'programme-option-' + index;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', 'false');
            option.textContent = entry.label;
            option.addEventListener('pointerdown', event => event.preventDefault());
            option.addEventListener('click', () => select(index));
            list.append(option);
        });
        setOpen(matches.length > 0);
    }

    function select(index) {
        const entry = matches[index];
        if (!entry) return;
        input.value = entry.label;
        setOpen(false);
        if (input.dataset.action === 'check') {
            input.dispatchEvent(new CustomEvent('programme-selected', {detail: entry.target}));
        } else {
            window.location.assign(entry.target);
        }
    }

    input.addEventListener('input', update);
    input.addEventListener('focus', update);
    input.addEventListener('blur', () => setOpen(false));
    input.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            setOpen(false);
        } else if (event.key === 'Enter' && !list.hidden) {
            event.preventDefault();
            select(Math.max(0, active));
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            if (list.hidden) update();
            if (!matches.length) return;
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            active = active < 0 ? (direction === 1 ? 0 : matches.length - 1)
                : (active + direction + matches.length) % matches.length;
            Array.from(list.children).forEach((option, index) => {
                option.setAttribute('aria-selected', String(index === active));
            });
            input.setAttribute('aria-activedescendant', list.children[active].id);
            list.children[active].scrollIntoView({block: 'nearest'});
        }
    });
})();
</script>
"""


def information_actions(year_selector, programme_type, entries, *, check_progress=False):
    payload = json.dumps(list(entries), ensure_ascii=False).replace("<", "\\u003c")
    label = escape(f"Search {programme_type} programmes", quote=True)
    action = "check" if check_progress else "navigate"
    return (
        '<div class="programme-toolbar"><div class="programme-search">'
        f'<input id="programme-search" type="search" role="combobox" aria-label="{label}" '
        f'placeholder="{label}…" autocomplete="off" aria-autocomplete="list" '
        f'aria-controls="programme-suggestions" aria-expanded="false" data-action="{action}">'
        '<ul id="programme-suggestions" class="programme-suggestions" role="listbox" hidden></ul>'
        '</div>'
        f'<div class="site-info-actions">{year_selector}{information_button()}</div></div>'
        f'<script id="programme-search-data" type="application/json">{payload}</script>{SEARCH_SCRIPT}'
    )


INFO_DIALOG = """
<dialog id="site-information" class="site-info-dialog" aria-labelledby="site-information-title"
  onclick="const bounds = this.getBoundingClientRect(); if (event.target === this &amp;&amp; (event.clientX &lt; bounds.left || event.clientX &gt; bounds.right || event.clientY &lt; bounds.top || event.clientY &gt; bounds.bottom)) this.close()">
  <header>
    <h2 id="site-information-title">About this website</h2>
    <form method="dialog"><button class="site-info-close" autofocus>Close</button></form>
  </header>
  <p><strong>This is an unofficial website.</strong> For the latest information, check these official CUHK sources:</p>
  <ul>
    <li><a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx">CUHK programme information</a></li>
    <li><a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/public/handbook/Default.aspx?id=1840&amp;tv=F&amp;lang=en">CUHK student handbook</a></li>
    <li><a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx">CUHK course catalogue</a></li>
  </ul>
  <p>The site brings together all undergraduate major and minor programme information published by CUHK and includes a minor progress checker. Updates are irregular, but the author aims to refresh the site before course registration periods.</p>
  <p><strong>Check your admission year and study scheme.</strong> Choose your year of admission and, where available, the study scheme that applies to you to see the correct requirements.</p>
  <h3>Why this site exists</h3>
  <ol>
    <li>Gather scattered minor requirements in one place.</li>
    <li>Show essential course information alongside major and minor requirements in one view, which CUSIS does not provide, so students can choose suitable courses more easily.</li>
    <li>Help people outside CUHK explore majors they might want to pursue by browsing course titles and programme requirements.</li>
  </ol>
  <p class="site-info-contact"><a href="https://github.com/marcolo0714-lgtm/CUHK-Program-Info-Page">Project on GitHub</a>
    <a href="mailto:marcolo0714@outlook.com">Contact author by email</a></p>
</dialog>
"""

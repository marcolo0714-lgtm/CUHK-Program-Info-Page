"""Shared information dialog for the generated site pages."""

INFO_CSS = """
.site-info-actions { display:flex; justify-content:flex-end; gap:8px; margin-bottom:16px; }
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


def information_actions(year_selector):
    return f'<div class="site-info-actions">{year_selector}{information_button()}</div>'


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

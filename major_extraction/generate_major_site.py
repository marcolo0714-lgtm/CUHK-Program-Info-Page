"""Generate a CUHK-minor-style static site for CUHK majors."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
from minor_extraction.minor_course_index import (
    load_minor_course_index,
    minor_applies_to_major,
    minor_matches_major_name,
)
from minor_extraction.course_schedule_metadata import course_schedule_update_date

COURSE_INFO = ROOT.parent / "course_extraction" / "course_info"
PUBLIC = ROOT.parent / "site" / "major"
SITE_ORIGIN = "https://cuhk-minor.coffeebreak.work"
SITE_NAME = "CUHK Programme Information"
MINOR_COURSE_MEMBERSHIPS: dict[str, list[dict[str, object]]] = {}
CURRENT_MAJOR: dict[str, object] | None = None
CURRENT_YEAR = ""


def write_generated(path: Path, content: str) -> None:
    """Atomically replace generated text, including OneDrive placeholders."""
    path = Path(path)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = content.encode("utf-8")
    last_error = None
    try:
        for attempt in range(8):
            temporary.write_bytes(payload)
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                last_error = error
                try:
                    path.write_bytes(payload)
                    return
                except OSError as direct_error:
                    last_error = direct_error
                time.sleep(0.1 * (attempt + 1))
        raise last_error
    finally:
        temporary.unlink(missing_ok=True)

CSS = r"""
:root { --bg:#f8f9fa; --card:#fff; --border:#dee2e6; --accent:#2563eb;
  --text:#212529; --muted:#6c757d; --warn-bg:#fff8f0; --warn:#b45309;
  --tbl-border:#868a90; --tbl-border-light:#d5d8dc; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg); color:var(--text); line-height:1.6; }
body.sidebar-visible { overflow:hidden; }
h1 { font-size:1.7em; }
h2 { font-size:1.2em; margin:1.4em 0 .5em; padding-bottom:4px;
  border-bottom:1px solid var(--border); color:#333; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.breadcrumb { margin-bottom:0; color:var(--muted); font-size:.9em; flex:1; min-width:0;
  white-space:normal; overflow-wrap:anywhere; }
.meta,.admit-year { color:var(--muted); font-size:.85em; }
.admit-year { margin-top:-4px; margin-bottom:8px; }
.section { background:var(--card); padding:14px 18px; border-radius:8px;
  border:1px solid var(--border); margin-bottom:10px; }
.section p + p { margin-top:8px; }
.section-marker { color:var(--accent); margin-right:6px; }
.unit-tag { display:inline-block; background:#e8f0fe; color:var(--accent); border-radius:4px;
  padding:1px 7px; font-size:.72em; margin-left:7px; vertical-align:2px; font-weight:500; }
.description-heading { margin:16px 0 5px; font-size:1.08rem; color:var(--text); }
.course-pattern { width:100%; margin:12px 0 22px; }
.course-pattern th,.course-pattern td { padding:9px 11px; text-align:left; vertical-align:top; }
.subsections { margin:10px 0 18px 28px; padding-left:18px; border-left:3px solid #e8f0fe; }
.subsection { margin:14px 0 20px; }
.subsection h3 { margin:0 0 7px; color:#333; font-size:1em; line-height:1.5; }
.subsection h4 { margin:0 0 7px; color:#444; font-size:.94em; line-height:1.5; }
.subsection-copy { background:var(--card); padding:10px 14px; border:1px solid var(--border);
  border-radius:8px; margin-bottom:8px; }
.subsection-copy p + p { margin-top:7px; }
.nested-subsections { margin:10px 0 4px 16px; padding-left:14px; border-left:2px solid #d5e2f8; }
.marker-inline { display:grid; grid-template-columns:auto minmax(0,1fr); gap:8px; align-items:start; }
.marker-inline > .section-marker { padding-top:10px; margin-right:0; font-weight:600; }
.marker-inline-content { min-width:0; }
.marker-inline-content .subsection-copy:first-child { margin-top:0; }
.flat-additional > .subsections { margin-left:0; padding-left:0; border-left:0; }
table { width:100%; border-collapse:collapse; background:var(--card); border-radius:8px;
  overflow:hidden; border:1px solid var(--border); margin-bottom:16px; }
.course-details { overflow-x:auto; -webkit-overflow-scrolling:touch; }
.course-details table { table-layout:fixed; min-width:1300px; }
.course-details th,.course-details td { overflow-wrap:anywhere; word-break:normal; }
body.table-scroll-disabled .course-details { overflow-x:visible; }
body.table-scroll-disabled .course-details table { min-width:0; width:100%; }
body.table-scroll-disabled .course-code-main,
body.table-scroll-disabled .course-code-unit { white-space:normal; }
th,td { padding:9px 13px; text-align:left; border-bottom:1px solid var(--tbl-border); font-size:.92em; vertical-align:top; }
th { background:#fafafa; font-weight:600; color:#555; }
thead th { height:auto; vertical-align:bottom; line-height:1.3; overflow:visible; }
.col-code { width:var(--course-code-width, 10%); }
.col-title { width:var(--course-title-width, 22%); overflow-wrap:anywhere; }
.col-term-1,.col-term-2 { width:var(--course-term-width, 5%); text-align:center; white-space:nowrap;
  border-left:1px solid var(--tbl-border); }
th.col-term-1,th.col-term-2 { padding-left:6px; padding-right:6px; }
.col-term-2 { border-right:1px solid var(--tbl-border); }
.col-t1-schedule,.col-t2-schedule { width:var(--course-schedule-width, auto); overflow-wrap:anywhere; }
body:not(.hide-t1-schedule):not(.hide-t2-schedule) .col-t1-schedule,
body:not(.hide-t1-schedule):not(.hide-t2-schedule) .col-t2-schedule {
  width:calc(var(--course-schedule-width, 0%) / 2); }
.col-prereq { width:var(--course-prereq-width, auto); overflow-wrap:anywhere; }
.col-minors { width:var(--course-minors-width, 16%); overflow-wrap:anywhere; }
.minor-memberships { display:flex; flex-wrap:wrap; gap:2px 8px; align-items:flex-start; }
.minor-memberships a { line-height:1.35; }
body.hide-term-1 .col-term-1,body.hide-term-2 .col-term-2,
body.hide-t1-schedule .col-t1-schedule,body.hide-t2-schedule .col-t2-schedule,
body.hide-enrolment .col-prereq,body.hide-minors .col-minors { display:none; }
body.hide-unavailable table tbody tr.course-unavailable { display:none; }
tr:hover { background:#f9f9f9; }
.term-yes { background:#d4edda; }
.schedule-section { line-height:1.35; min-width:0; overflow-wrap:anywhere; }
.schedule-section + .schedule-section { margin-top:4px; padding-top:4px; border-top:1px solid var(--tbl-border-light); }
.schedule-section-name { display:inline; font-weight:600; color:#374151; }
.schedule-lead,.schedule-time-extra { display:inline-block; max-width:100%; }
.schedule-time { white-space:normal; }
.schedule-time-extra::before { content:" · "; color:var(--muted); }
.schedule-empty { color:var(--muted); }
.course-code-main,.course-code-unit { white-space:nowrap; }
.nf { background:var(--warn-bg); color:var(--warn); }
.course-group-row td { background:var(--panel); color:var(--text); text-align:left; font-size:.92em; font-weight:700; }
.course-details { margin:0 0 16px 28px; }
.course-details summary { cursor:pointer; padding:6px 0; color:var(--accent); font-size:.9em; font-weight:500; }
.course-details summary:hover { text-decoration:underline; }
.course-details table { margin-top:8px; }
.enrol { font-size:.94em; }
.enrol summary { cursor:pointer; color:var(--accent); font-size:.9em; white-space:nowrap; }
.enrol summary:hover { text-decoration:underline; }
.enrol-text { margin:0; color:#454b50; min-width:0; }
.prereq-sentence { display:block; padding-left:1.5em; text-indent:-1.5em; }
.prereq-indent { text-indent:0; }
.notes-section { background:var(--card); border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.notes-point { display:flex; gap:10px; padding:10px 14px; border-bottom:1px solid var(--border); }
.notes-point:last-child { border-bottom:0; }
.notes-point:hover { background:#f0f4ff; }
.point-idx { font-weight:600; color:var(--accent); min-width:22px; }
.note-content { flex:1; min-width:0; }
.note-subsections { margin-top:6px; }
.note-content.subpoints-only > .note-subsections { margin-top:0; }
.note-subsection { padding:3px 0; border-top:0; }
.note-subsection.marker-inline { grid-template-columns:32px minmax(0,1fr); gap:0; }
.note-subsection.marker-inline > .section-marker { padding-top:0; }
.note-subsection h3 { margin:0 0 5px; font-size:.96em; color:#333; }
.note-subsection p + p { margin-top:6px; }
.note-subsection .course-details { margin-bottom:0; }
.note-course-list { color:#454b50; font-size:.9em; }
.note-rows { margin:10px 0 0; }
.note-rows td { background:var(--card); }
.sidebar { width:min(620px,calc(100vw - 20px)); height:100vh; position:fixed; left:0; top:0;
  z-index:99; overflow:auto; transform:translateX(-100%); transition:transform .25s ease;
  background:var(--card); border-right:1px solid var(--border); padding:12px 0; font-size:.88em; }
.sidebar.open { transform:translateX(0); box-shadow:2px 0 16px rgba(0,0,0,.18); }
.sidebar nav { min-width:max-content; }
.sidebar-header { padding:6px 18px 10px; font-weight:600; color:var(--muted); border-bottom:1px solid var(--border); margin-bottom:6px; }
.sidebar-faculty { padding:12px 18px 4px; color:var(--muted); font-size:.82em;
  font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
.sidebar a { display:block; padding:5px 16px 5px 22px; color:var(--text); text-decoration:none;
  border-left:3px solid transparent; white-space:nowrap; }
.sidebar a:hover { background:#f0f4ff; color:var(--accent); }
.sidebar a.active { font-weight:600; color:var(--accent); background:#e8f0fe; border-left-color:var(--accent); }
.sidebar-toggle { display:block; border:1px solid var(--border); border-radius:6px; background:var(--card); padding:4px 8px; font-size:1.1em; cursor:pointer; }
.sidebar-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.25); z-index:98; }
.sidebar-overlay.open { display:block; }
.content { width:100%; min-width:0; }
.content-inner { width:100%; max-width:1800px; margin:0 auto; padding:16px clamp(42px,6vw,96px); }
.page-index .container { width:100%; max-width:1800px; margin:0 auto; padding:16px clamp(42px,6vw,96px); }
.card-grid { display:flex; flex-wrap:wrap; gap:8px; align-items:stretch; }
.card-grid > a { flex:1 0 400px; max-width:100%; text-decoration:none; display:flex; }
.card { width:100%; background:var(--card); border-radius:8px; padding:12px 18px;
  border:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
.card:hover { border-color:var(--accent); }
.card-code { font-weight:600; color:var(--accent); }
.card-admission { color:var(--muted); font-size:.8em; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }
.year-select,.bar-year-select { font-size:.85rem; padding:4px 10px; border:1px solid var(--border);
  border-radius:6px; background:var(--card); color:var(--text); cursor:pointer; }
.year-select { margin-bottom:16px; }
.top-bar { position:sticky; top:0; z-index:50; background:var(--bg); padding:8px 0 6px;
  margin:-8px 0 0; border-bottom:1px solid var(--border); }
.bar-row { display:flex; align-items:center; gap:12px; width:100%; }
.bar-controls { display:flex; align-items:center; gap:8px; font-size:.85em; white-space:nowrap; }
.page-nav { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  align-items:center; gap:8px; width:100%; margin-top:7px; font-size:.85em; }
.page-nav a { display:inline-flex; align-items:center; max-width:100%; min-height:30px; padding:4px 10px;
  border:1px solid var(--accent); border-radius:6px; background:var(--card);
  color:var(--accent); font-weight:600; line-height:1.3; overflow-wrap:anywhere; text-decoration:none; }
.page-nav-prev { justify-self:start; }
.page-nav-next { justify-self:end; text-align:right; }
.page-nav a:hover { background:#e8f0fe; text-decoration:none; }
.top-bar + h1 { margin-top:18px; }
.settings-toggle { display:inline-flex; align-items:center; gap:5px; font-size:.85rem; padding:4px 10px;
  border:1px solid var(--accent); border-radius:6px; background:var(--card); color:var(--accent); cursor:pointer; }
.settings-toggle:hover { background:#e8f0fe; }
.settings-overlay { position:fixed; inset:0; background:rgba(0,0,0,.25); z-index:108;
  opacity:0; visibility:hidden; pointer-events:none; transition:opacity .2s,visibility .2s; }
.settings-overlay.open { opacity:1; visibility:visible; pointer-events:auto; }
.settings-panel { position:fixed; inset:0 0 0 auto; z-index:109; width:min(360px,calc(100vw - 60px));
  height:100vh; padding:18px; overflow:auto; background:var(--card); border-left:1px solid var(--border);
  transform:translateX(100%); transition:transform .25s,box-shadow .25s; }
.settings-panel.open { transform:translateX(0); box-shadow:-2px 0 12px rgba(0,0,0,.15); }
.settings-header { display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding-bottom:12px; border-bottom:1px solid var(--border); }
.settings-header h2 { margin:0; padding:0; border:0; font-size:1.15em; }
.settings-close { border:1px solid var(--border); border-radius:6px; background:var(--card);
  padding:3px 9px; font-size:1.25em; line-height:1; cursor:pointer; }
.settings-description { margin:14px 0 10px; color:var(--muted); font-size:.88em; }
.setting-option { display:flex; align-items:flex-start; gap:10px; padding:9px 4px;
  cursor:pointer; border-bottom:1px solid var(--tbl-border-light); }
.setting-option input { margin-top:.3em; flex:none; }
body.settings-open { overflow:hidden; }
.site-footer { margin-top:32px; padding-top:12px; border-top:1px solid var(--border);
  font-size:.82em; color:var(--muted); text-align:center; }
@media (max-width:768px) {
  body { max-width:100vw; } html { overflow-x:hidden; }
  .sidebar { width:calc(100vw - 100px); font-size:.82em; }
  .content-inner { padding:0 30px 12px; }
  .page-index .container { padding:12px 30px; }
  .top-bar { margin:0; border-radius:0; padding:6px 0 4px; }
  .bar-row { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:6px 8px; }
  .breadcrumb { overflow:visible; white-space:normal; overflow-wrap:anywhere; }
  .bar-controls { grid-column:1 / -1; width:100%; min-width:0; justify-content:flex-end;
    flex-wrap:wrap; white-space:normal; }
  .page-nav { margin-top:6px; }
  h1 { font-size:1.4em; } .meta { white-space:normal; }
  .course-details { margin-left:0; overflow-x:auto; }
  .subsections { margin-left:8px; padding-left:12px; }
  th,td { padding:6px 8px; font-size:.82em; }
  .card-grid > a { flex-basis:100%; }
}
@media (max-width:1200px) {
  .course-details th,.course-details td { padding-left:9px; padding-right:9px; }
  .course-code-unit { display:block; }
}
"""

SCRIPT = r"""<script>
function setSidebarVisibility(open){
 var sidebar=document.querySelector('.sidebar'),overlay=document.querySelector('.sidebar-overlay'),button=document.querySelector('.sidebar-toggle');
 if(!sidebar||!overlay)return;
 if(open)setSettingsVisibility(false);
 sidebar.classList.toggle('open',open);overlay.classList.toggle('open',open);document.body.classList.toggle('sidebar-visible',open);
 sidebar.setAttribute('aria-hidden',String(!open));if(button)button.setAttribute('aria-expanded',String(open));
}
function toggleSidebar(){var sidebar=document.querySelector('.sidebar');if(sidebar)setSidebarVisibility(!sidebar.classList.contains('open'))}
function setSettingsVisibility(open){
 var panel=document.querySelector('.settings-panel'),overlay=document.querySelector('.settings-overlay'),button=document.querySelector('.settings-toggle');
 if(!panel||!overlay)return;
 if(open)setSidebarVisibility(false);
 panel.classList.toggle('open',open);overlay.classList.toggle('open',open);document.body.classList.toggle('settings-open',open);
 panel.setAttribute('aria-hidden',String(!open));if(button)button.setAttribute('aria-expanded',String(open));
}
function toggleSettings(){var panel=document.querySelector('.settings-panel');if(panel)setSettingsVisibility(!panel.classList.contains('open'))}
function applyTableSettings(){
 var classes={term1:'hide-term-1',term2:'hide-term-2',prerequisites:'hide-enrolment',schedule:'hide-t1-schedule',schedule2:'hide-t2-schedule',minors:'hide-minors',unavailable:'hide-unavailable',scroll:'table-scroll-disabled'};
 var settings={};
 Object.keys(classes).forEach(function(key){
  var checkbox=document.querySelector('[data-table-setting="'+key+'"]'),shown=checkbox?checkbox.checked:true;
 settings[key]=shown;document.body.classList.toggle(classes[key],!shown);
 });
 var visibleColumns=2+['term1','term2','prerequisites','schedule','schedule2','minors'].filter(function(key){return settings[key]}).length;
 document.querySelectorAll('.course-group-row td[colspan]').forEach(function(cell){cell.colSpan=visibleColumns});
 document.querySelectorAll('tr.nf td[colspan]').forEach(function(cell){cell.colSpan=Math.max(1,visibleColumns-1)});
 localStorage.setItem('majorTableSettings',JSON.stringify(settings));
}
(function(){
 var sidebar=document.querySelector('.sidebar'); if(!sidebar)return;
 var saved=localStorage.getItem('majorSidebarScroll'); if(saved!==null)sidebar.scrollTop=+saved;
 sidebar.addEventListener('scroll',function(){localStorage.setItem('majorSidebarScroll',sidebar.scrollTop)});
 document.querySelectorAll('.sidebar a.active').forEach(function(a){a.addEventListener('click',function(e){e.preventDefault()})});
 document.addEventListener('keydown',function(e){if(e.key==='Escape'){setSidebarVisibility(false);setSettingsVisibility(false)}});
 var saved;try{saved=JSON.parse(localStorage.getItem('majorTableSettings')||'{}')}catch(e){saved={}};
 if(saved.prerequisites===undefined){var legacyPrereq=localStorage.getItem('majorPrerequisites');saved.prerequisites=legacyPrereq?legacyPrereq!=='hidden':!window.matchMedia('(max-width:768px)').matches}
 if(saved.unavailable===undefined){saved.unavailable=localStorage.getItem('majorUnavailable')!=='hidden'}
 var defaults={term1:true,term2:true,prerequisites:true,schedule:false,schedule2:true,minors:false,unavailable:true,scroll:true};
 Object.keys(defaults).forEach(function(key){var checkbox=document.querySelector('[data-table-setting="'+key+'"]');if(!checkbox)return;checkbox.checked=saved[key]===undefined?defaults[key]:!!saved[key];checkbox.addEventListener('change',applyTableSettings)});
 applyTableSettings();
})();
</script>"""

FOOTER = f"""<div class="site-footer">Source: <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx" target="_blank" rel="noopener">CUHK programme information</a> &middot; <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx" target="_blank" rel="noopener">CUHK course catalogue</a> &middot; Latest course teaching schedule update: {course_schedule_update_date()}</div>"""


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def linked_text(value: object) -> str:
    """Escape prose and make every explicit web address safely clickable."""
    escaped = esc(value)
    pattern = re.compile(r"(?P<url>https?://[^\s<>]+|www\.[^\s<>]+)", re.I)
    def replace(match):
        shown = match.group("url").rstrip(".,;:)")
        trailing = match.group("url")[len(shown):]
        href = shown if shown.lower().startswith(("http://", "https://")) else "https://" + shown
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{shown}</a>{trailing}'
    return pattern.sub(replace, escaped)


def unit_tag(value: object) -> str:
    value = str(value or "")
    if not value:
        return ""
    suffix = "" if value.upper() == "N/A" else " units"
    return f'<span class="unit-tag">{esc(value)}{suffix}</span>'


def absolute_url(path: str) -> str:
    return SITE_ORIGIN + "/" + path.lstrip("/")


def seo_head(title: str, description: str, canonical_path: str, structured_data=None) -> str:
    canonical = absolute_url(canonical_path)
    blocks = [
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(description)}">',
        '<meta name="robots" content="index,follow">',
        f'<link rel="canonical" href="{esc(canonical)}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(canonical)}">',
        f'<meta property="og:site_name" content="{esc(SITE_NAME)}">',
        '<meta property="og:type" content="website">',
        '<meta name="twitter:card" content="summary">',
    ]
    if structured_data:
        payload = json.dumps(structured_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        blocks.append(f'<script type="application/ld+json">{payload}</script>')
    return "".join(blocks)


def breadcrumb_data(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": absolute_url(path),
            }
            for position, (name, path) in enumerate(items, start=1)
        ],
    }


def load_course_index() -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for path in sorted(COURSE_INFO.glob("*.json")):
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if entry.get("code"):
                index[entry["code"]] = entry
    return index


def format_info(value: str) -> str:
    if not value:
        return '<span class="meta">—</span>'
    text = value
    separator = "@@BRK@@"

    # 1. Sentence-ending periods only. The word before the period must contain
    # at least two characters, avoiding single-letter abbreviations.
    text = re.sub(r"(\b\w{2,}\.)\s+(?=[A-Z])", r"\1" + separator, text)
    # A period after a four-digit course code also ends the current line.
    text = re.sub(r"(?<=\d{4})\.\s+", "." + separator, text)

    # 2. Numbered items such as "1." and "2)" start separate lines. The
    # negative digit lookbehind prevents matching suffixes inside course codes.
    text = re.sub(
        r"(?<!" + separator + r")(?<!\d)(\d{1,3}[.)])\s*(?=[A-Z])",
        separator + r"\1 ",
        text,
    )

    # 3. Requirement keywords start new lines, with guards matching the minor
    # formatter so labels and slash-separated expressions remain together.
    text = re.sub(
        r"(?<!" + separator + r")(?<!\bExclusion[=:\s])(?<!\d[.)]\s)(?=\bNot for students?\b)",
        separator, text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<!" + separator + r")(?<!\d[.)]\s)(?=\bCourse Exclusion\b)",
        separator, text,
    )
    text = re.sub(
        r"(?<!" + separator + r")(?<!\d[.)]\s)(?<!\/)(?=\b(?:Pre[- ]?requisite|Prerequisite)s?\b)",
        separator, text,
    )
    text = re.sub(
        r"(?<!" + separator + r")(?<!\d[.)]\s)(?<!\/)(?=\b(?:Co[- ]?requisite|Corequisite)s?\b)",
        separator, text,
    )
    text = re.sub(
        r"(?<!" + separator + r")(?<!\d[.)]\s)(?<!\bCourse\s)(?=\bExclusion[=:])",
        separator, text,
    )
    # Split a semicolon only when its next clause begins with uppercase text;
    # lowercase continuations such as "; or" and "; but" stay on one line.
    text = re.sub(
        r"(?<!" + separator + r");(?=\s*[A-Z])",
        separator,
        text,
    )

    lines = []
    for part in text.split(separator):
        part = part.strip().lstrip(";").strip()
        if not part:
            continue
        if part[-1] not in ".!?:;":
            part += "."
        classes = "prereq-sentence"
        if part.startswith("["):
            classes += " prereq-indent"
        lines.append(f'<span class="{classes}">{linked_text(part)}</span>')

    body = "".join(lines)
    return f'<div class="enrol-text">{body}</div>'


def group_schedule(
    sections: list[dict[str, object]], term_number: int
) -> list[tuple[str, list[str]]]:
    """Return ``[(section_name, meeting_times)]`` for one teaching term."""
    grouped: list[tuple[str, list[str]]] = []
    positions: dict[str, int] = {}
    for section in sections or []:
        if not re.search(
            rf"\bTerm\s*{term_number}\b", str(section.get("term", "")), re.I
        ):
            continue
        name = str(section.get("section") or "Section TBA").strip()
        if name not in positions:
            positions[name] = len(grouped)
            grouped.append((name, []))
        times = grouped[positions[name]][1]
        timetable = section.get("timetable", [])
        if not isinstance(timetable, list):
            timetable = []
        for meeting in timetable:
            if not isinstance(meeting, dict):
                continue
            day_time = str(meeting.get("day_time") or "").strip()
            if day_time and day_time not in times:
                times.append(day_time)
    return grouped


def format_schedule(sections: list[dict[str, object]], term_number: int) -> str:
    """Group unique meeting times by section for one teaching term."""
    grouped = group_schedule(sections, term_number)
    if not grouped:
        return '<span class="schedule-empty">—</span>'
    parts = []
    for name, times in grouped:
        section_times = times or ["Time TBA"]
        lead = (
            f'<span class="schedule-lead"><span class="schedule-section-name">'
            f'{esc(name)}:</span> <span class="schedule-time">'
            f'{esc(section_times[0])}</span></span>'
        )
        extra_times = "".join(
            f' <span class="schedule-time schedule-time-extra">{esc(value)}</span>'
            for value in section_times[1:]
        )
        parts.append(
            f'<div class="schedule-section">{lead}{extra_times}</div>'
        )
    return "".join(parts)


@lru_cache(maxsize=None)
def estimated_wrapped_lines(text: object, width: int) -> int:
    """Estimate browser word wrapping using character-width units."""
    words = re.findall(r"\S+", re.sub(r"<[^>]*>", " ", str(text or "—")))
    if not words:
        return 1
    lines = 1
    used = 0
    for word in words:
        length = len(word)
        if used and used + 1 + length <= width:
            used += 1 + length
        elif length <= width:
            if used:
                lines += 1
            used = length
        else:
            if used:
                lines += 1
            lines += (length - 1) // width
            used = length % width or width
    return lines


def course_code_label(code: str, course: dict[str, object]) -> str:
    unit = str(course.get("unit", ""))
    try:
        return code if float(unit or 3) == 3 else f"{code} [{float(unit):g}]"
    except ValueError:
        return code


def course_code_html(code: str, course: dict[str, object]) -> str:
    """Keep a course code intact while allowing its optional units to wrap."""
    label = course_code_label(code, course)
    match = re.fullmatch(r"(.+?)\s+(\[[^]]+\])", label)
    if not match:
        return f'<span class="course-code-main">{esc(label)}</span>'
    return (
        f'<span class="course-code-main">{esc(match.group(1))}</span> '
        f'<span class="course-code-unit">{esc(match.group(2))}</span>'
    )


def minor_membership_records(code: str) -> list[dict[str, object]]:
    return [
        item for item in MINOR_COURSE_MEMBERSHIPS.get(code, [])
        if minor_applies_to_major(item, CURRENT_MAJOR)
        and not minor_matches_major_name(item, CURRENT_MAJOR)
    ]


def format_minor_memberships(code: str) -> str:
    records = minor_membership_records(code)
    if not records:
        return '<span class="schedule-empty">—</span>'
    links = [
        f'<a href="../../../{esc(CURRENT_YEAR)}/minors/{esc(item["stem"])}.html">'
        f'{esc(item["title"])}</a>'
        for item in records
    ]
    return '<div class="minor-memberships">' + '<span>·</span>'.join(links) + '</div>'


def course_table_style(courses: list[tuple[str, dict[str, object] | None]]) -> str:
    """Search for the lowest estimated total row height for this table."""
    usable = [(code, course) for code, course in courses if course]
    code_weight = max(
        12,
        min(18, max((len(course_code_label(code, course)) for code, course in usable), default=12) + 1),
    )
    term_weight = 6
    minor_weight = max(
        14,
        min(
            28,
            max(
                (max((len(str(item["title"])) for item in minor_membership_records(code)), default=0)
                 for code, _ in usable),
                default=0,
            ) + 2,
        ),
    )
    total_weight = 140 + minor_weight
    flexible = total_weight - code_weight - 2 * term_weight - minor_weight
    content_rows = []
    for _, course in usable:
        schedule_lines = [
            f'{name}: {" · ".join(times or ["Time TBA"])}'
            for name, times in group_schedule(course.get("sections", []), 1)
        ] or ["—"]
        content_rows.append((
            str(course.get("title") or "—"),
            schedule_lines,
            str(course.get("info") or "—"),
        ))

    best = None
    for title_width in range(10, min(42, flexible - 20) + 1, 2):
        for schedule_width in range(10, min(76, flexible - title_width - 10) + 1, 2):
            prereq_width = flexible - title_width - schedule_width
            if prereq_width < 10:
                continue
            row_total = 0
            cell_total = 0
            schedule_extra_lines = 0
            for title, schedule, prereq in content_rows:
                title_lines = estimated_wrapped_lines(title, title_width)
                schedule_count = sum(
                    estimated_wrapped_lines(line, schedule_width) for line in schedule
                )
                prereq_lines = estimated_wrapped_lines(prereq, prereq_width)
                row_total += max(title_lines, schedule_count, prereq_lines)
                cell_total += title_lines + schedule_count + prereq_lines
                schedule_extra_lines += schedule_count - len(schedule)
            score = (
                row_total + 2 * schedule_extra_lines,
                row_total,
                cell_total,
                abs(title_width - 20) + abs(prereq_width - 36),
                -schedule_width,
            )
            if best is None or score < best[0]:
                best = (score, title_width, schedule_width, prereq_width)

    _, title_weight, schedule_weight, prereq_weight = best or (
        (), 22, 35, flexible - 57
    )
    percent = lambda value: f"{100 * value / total_weight:.2f}%"
    return (
        f"--course-code-width:{percent(code_weight)};"
        f"--course-term-width:{percent(term_weight)};"
        f"--course-title-width:{percent(title_weight)};"
        f"--course-schedule-width:{percent(schedule_weight)};"
        f"--course-prereq-width:{percent(prereq_weight)};"
        f"--course-minors-width:{percent(minor_weight)}"
    )


def course_table(codes: list[str], course_index: dict[str, dict[str, object]], groups=None) -> str:
    rows = []
    entries = []
    if groups:
        for item in groups:
            entries.append(("__group__", item.get("label", item.get("title", ""))))
            entries.extend((code, course_index.get(code)) for code in item.get("codes", []))
    else:
        entries = [(code, course_index.get(code)) for code in codes]
    courses = [(code, course) for code, course in entries if code != "__group__"]
    for code, course in entries:
        if code == "__group__":
            rows.append(f'<tr class="course-group-row"><td colspan="8">{esc(course)}</td></tr>')
            continue
        if not course:
            rows.append(f'<tr class="nf"><td>{esc(code)}</td><td colspan="7"><em>(not found in course_info)</em></td></tr>')
            continue
        code_unit = course_code_html(code, course)
        t1 = " term-yes" if course.get("term_1") else ""
        t2 = " term-yes" if course.get("term_2") else ""
        row_class = ' class="course-unavailable"' if not course.get("term_1") and not course.get("term_2") else ""
        rows.append(
            f'<tr{row_class}><td class="col-code">{code_unit}</td>'
            f'<td class="col-title">{esc(course.get("title"))}</td>'
            f'<td class="col-term-1{t1}"></td><td class="col-term-2{t2}"></td>'
            f'<td class="col-t1-schedule">{format_schedule(course.get("sections", []), 1)}</td>'
            f'<td class="col-t2-schedule">{format_schedule(course.get("sections", []), 2)}</td>'
            f'<td class="col-prereq">{format_info(str(course.get("info", "")))}</td>'
            f'<td class="col-minors">{format_minor_memberships(code)}</td></tr>'
        )
    return (
        f'<table style="{course_table_style(courses)}"><thead><tr>'
        '<th class="col-code">Course</th><th class="col-title">Title</th>'
        '<th class="col-term-1" title="Term 1 availability">T1</th>'
        '<th class="col-term-2" title="Term 2 availability">T2</th>'
        '<th class="col-t1-schedule" title="Term 1 teaching schedule">T1 Teaching schedule</th>'
        '<th class="col-t2-schedule" title="Term 2 teaching schedule">T2 Teaching schedule</th>'
        '<th class="col-prereq">Enrolment information</th>'
        '<th class="col-minors" title="Minor programmes whose requirements accept this course">Also in minor</th>'
        '</tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>"
    )


def sidebar(programmes: list[dict[str, object]], active: str) -> str:
    links = []
    current_faculty = None
    for item in programmes:
        faculty = str(item.get("faculty") or "Other")
        if faculty != current_faculty:
            links.append(f'<div class="sidebar-faculty">{esc(faculty)}</div>')
            current_faculty = faculty
        stem = item["source_file"]
        cls = "active" if stem == active else ""
        prefix = "&#9654; " if cls else ""
        labels = {"Engineering_ELITE_Stream": "ELITE Stream", "Science_STAR_Stream": "STAR Stream"}
        label = labels.get(stem, item["title"])
        links.append(f'<a href="{esc(stem)}.html" class="{cls}">{prefix}{esc(label)}</a>')
    return "".join(links)


def course_details(codes: list[str], course_index: dict[str, dict[str, object]], extra: str = "", groups=None) -> str:
    count = sum(len(item.get("codes", [])) for item in groups) if groups else len(codes)
    if not count:
        return extra
    label = f'{count} course{"s" if count != 1 else ""}'
    return f'<details class="course-details"><summary>Show {label}</summary>{course_table(codes, course_index, groups)}{extra}</details>'


def render_embedded_group(group: dict[str, object], course_index: dict[str, dict[str, object]]) -> str:
    units = unit_tag(group.get("units"))
    paragraphs = "".join(f'<p>{linked_text(value)}</p>' for value in group.get("text", []))
    copy = f'<div class="subsection-copy">{paragraphs}</div>' if paragraphs else ""
    codes = group.get("codes", [])
    if group.get("collapse_course_table"):
        table = course_details(codes, course_index)
    else:
        table = course_table(codes, course_index) if codes else ""
    return f'<div class="nested-subsections"><div class="subsection"><h4>{esc(group.get("title"))}{units}</h4>{copy}{table}</div></div>'


def render_subsection(group: dict[str, object], course_index: dict[str, dict[str, object]], depth: int = 0) -> str:
    marker = f'<span class="section-marker">{esc(group.get("marker"))}</span>' if group.get("marker") else ""
    units = unit_tag(group.get("units"))
    title = esc(group.get("title"))
    heading_tag = "h3" if depth == 0 else "h4"
    marker_only = bool(marker and not title and not units and group.get("text"))
    heading = "" if marker_only else (f'<{heading_tag}>{marker}{title}{units}</{heading_tag}>' if marker or title or units else "")
    text_parts = [f'<p>{linked_text(value)}</p>' for value in group.get("text", [])]
    body = f'<div class="subsection-copy">{"".join(text_parts)}</div>' if text_parts else ""
    if marker_only:
        body = f'<div class="marker-inline">{marker}<div class="marker-inline-content">{body}</div></div>'
    embedded = [child for child in group.get("subsections", []) if child.get("embed_in_parent_table")]
    regular = [child for child in group.get("subsections", []) if not child.get("embed_in_parent_table")]
    embedded_html = "".join(render_embedded_group(child, course_index) for child in embedded)
    if not group.get("hide_course_table"):
        body += course_details(group.get("codes", []), course_index, embedded_html, group.get("course_groups"))
    children = "".join(render_subsection(child, course_index, depth + 1) for child in regular)
    if children:
        body += f'<div class="nested-subsections">{children}</div>'
    return f'<div class="subsection depth-{depth}">{heading}{body}</div>'


def render_note_group(group: dict[str, object], course_index: dict[str, dict[str, object]]) -> str:
    marker = f'<span class="section-marker">{esc(group.get("marker"))}</span>' if group.get("marker") else ""
    title = esc(group.get("title"))
    heading = f'<h3>{marker}{title}</h3>' if title else ""
    paragraphs = "".join(f'<p>{linked_text(value)}</p>' for value in group.get("text", []))
    # Note sub-points are compact inline prose, not separate boxed cards.
    copy = paragraphs
    codes = group.get("codes", [])
    courses = course_details(codes, course_index, groups=group.get("course_groups")) if (group.get("course_groups") or (codes and (group.get("force_course_table") or len(codes) > 10))) else ""
    children = "".join(render_note_group(child, course_index) for child in group.get("subsections", []))
    nested = f'<div class="note-subsections">{children}</div>' if children else ""
    if marker and not title:
        return f'<div class="note-subsection marker-inline">{marker}<div class="marker-inline-content">{copy}{courses}{nested}</div></div>'
    return f'<div class="note-subsection">{heading}{copy}{courses}{nested}</div>'


def render_note(note: dict[str, object], course_index: dict[str, dict[str, object]]) -> str:
    marker = note.get("marker") or "•"
    paragraphs = note.get("paragraphs") or ([note.get("text", "")] if note.get("text") else [])
    parts = [f'<p>{linked_text(value)}</p>' for value in paragraphs]
    groups = [render_note_group(group, course_index) for group in note.get("subsections", [])]
    if groups:
        parts.append(f'<div class="note-subsections">{"".join(groups)}</div>')

    rows = note.get("rows", [])
    if rows:
        width = max(len(row) for row in rows)
        rendered_rows = []
        for row in rows:
            cells = list(row) + [""] * (width - len(row))
            rendered_rows.append("<tr>" + "".join(f'<td>{linked_text(cell)}</td>' for cell in cells) + "</tr>")
        parts.append(f'<table class="note-rows"><tbody>{"".join(rendered_rows)}</tbody></table>')
    content_class = "note-content subpoints-only" if groups and not paragraphs and not rows else "note-content"
    return f'<div class="notes-point"><span class="point-idx">{esc(marker)}</span><div class="{content_class}">{"".join(parts)}</div></div>'


def nav(programmes: list[dict[str, object]], position: int) -> str:
    """Return named previous/next links for the second row of the persistent top bar."""
    previous = programmes[position - 1] if position else None
    following = programmes[position + 1] if position + 1 < len(programmes) else None
    previous_link = (
        f'<a class="page-nav-prev" href="{esc(previous["source_file"])}.html" '
        f'aria-label="Previous major: {esc(previous["title"])}">&larr; {esc(previous["title"])}</a>'
        if previous else '<span aria-hidden="true"></span>'
    )
    following_link = (
        f'<a class="page-nav-next" href="{esc(following["source_file"])}.html" '
        f'aria-label="Next major: {esc(following["title"])}">{esc(following["title"])} &rarr;</a>'
        if following else '<span aria-hidden="true"></span>'
    )
    return f'<nav class="page-nav" aria-label="Major programme pagination">{previous_link}{following_link}</nav>'


def render_course_pattern(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    body = "".join(
        f'<tr><td>{esc(row.get("year"))}</td><td>{esc(row.get("period"))}</td>'
        f'<td>{esc(row.get("requirements"))}</td></tr>' for row in rows
    )
    return (f'<h2>Recommended Course Pattern</h2><table class="course-pattern">'
            f'<thead><tr><th>Year</th><th>Period</th><th>Recommended courses</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


INDEX_ACTION_CSS = """
.index-actions { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 24px; }
.index-action { display:inline-flex; align-items:center; padding:9px 14px;
  background:#e8f0fe; color:var(--accent); border:1px solid #c7d8f7;
  border-radius:6px; font-weight:600; font-size:.9em; text-decoration:none;
  box-shadow:0 1px 2px rgba(37,99,235,.08);
  transition:background .15s,border-color .15s,box-shadow .15s; }
.index-action:hover { background:#dbe8fd; border-color:var(--accent);
  box-shadow:0 2px 5px rgba(37,99,235,.15); text-decoration:none; }
"""


def page_shell(
    title: str,
    body: str,
    sidebar_html: str = "",
    extra_css: str = "",
    description: str = "",
    canonical_path: str = "/major/2026_27/",
    structured_data=None,
) -> str:
    if sidebar_html:
        settings = '''<div class="settings-overlay" onclick="setSettingsVisibility(false)" aria-hidden="true"></div><aside id="tableSettings" class="settings-panel" aria-hidden="true" aria-label="Course table settings"><div class="settings-header"><h2>Course table settings</h2><button type="button" class="settings-close" onclick="setSettingsVisibility(false)" aria-label="Close settings">&times;</button></div><p class="settings-description">Choose the columns and rows shown in course information tables.</p><label class="setting-option"><input type="checkbox" data-table-setting="term1" checked> <span>Show Term 1 availability</span></label><label class="setting-option"><input type="checkbox" data-table-setting="term2" checked> <span>Show Term 2 availability</span></label><label class="setting-option"><input type="checkbox" data-table-setting="prerequisites" checked> <span>Show prerequisites</span></label><label class="setting-option"><input type="checkbox" data-table-setting="schedule"> <span>Show Term 1 teaching schedule</span></label><label class="setting-option"><input type="checkbox" data-table-setting="schedule2" checked> <span>Show Term 2 teaching schedule</span></label><label class="setting-option"><input type="checkbox" data-table-setting="minors"> <span>Show minors using this course</span></label><label class="setting-option"><input type="checkbox" data-table-setting="unavailable" checked> <span>Show unavailable courses</span></label><label class="setting-option"><input type="checkbox" data-table-setting="scroll" checked> <span>Allow horizontal table scrolling</span></label></aside>'''
        body_html = f'''<div class="sidebar-overlay" onclick="setSidebarVisibility(false)"></div><aside id="majorSidebar" class="sidebar" aria-hidden="true"><div class="sidebar-header">CUHK Majors</div><nav>{sidebar_html}</nav></aside>{settings}<main class="content"><div class="content-inner">{body}{FOOTER}</div></main>{SCRIPT}'''
        body_class = ""
        favicon = "/favicon.ico"
    else:
        body_html = f'<div class="container">{body}{FOOTER}</div>'
        body_class = ' class="page-index"'
        favicon = "/favicon.ico"
    analytics = '<script defer src="/_vercel/insights/script.js"></script>'
    metadata = seo_head(title, description, canonical_path, structured_data)
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="prefetch-src 'none'"><link rel="icon" href="{favicon}" sizes="any">{metadata}<style>{CSS}{extra_css}</style>{analytics}</head><body{body_class}>{body_html}</body></html>'''


def programme_has_faculty(programme: dict[str, object], faculty: str) -> bool:
    """Return whether a programme is affiliated with the requested faculty."""
    primary = str(programme.get("faculty") or "")
    affiliations = {str(value) for value in programme.get("faculties", []) if value}
    return primary == faculty or faculty in affiliations


def discover_available_years() -> list[str]:
    """Return admission years that have parsed major programme data."""
    source = ROOT / "major_json"
    return sorted(
        directory.name
        for directory in source.iterdir()
        if directory.is_dir() and any(directory.glob("*.json"))
    )


def detail_year_selector(year: str, source_file: str, available_years: list[str]) -> str:
    """Build a selector containing each year in which this programme exists."""
    options = []
    for candidate in available_years:
        programme_json = ROOT / "major_json" / candidate / f"{source_file}.json"
        if not programme_json.exists() and candidate != year:
            continue
        selected = " selected" if candidate == year else ""
        label = candidate.replace("_", "–")
        options.append(
            f'<option value="../../{candidate}/majors/{esc(source_file)}.html"{selected}>{label}</option>'
        )
    if len(options) <= 1:
        return ""
    return '<select onchange="window.location=this.value" class="bar-year-select">' + "".join(options) + "</select>"


def generate(year: str, output_root: Path = PUBLIC, faculty_filter: str | None = None) -> None:
    global MINOR_COURSE_MEMBERSHIPS, CURRENT_MAJOR, CURRENT_YEAR
    json_dir = ROOT / "major_json" / year
    site_dir = output_root / year
    major_dir = site_dir / "majors"
    major_dir.mkdir(parents=True, exist_ok=True)
    programmes = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(json_dir.glob("*.json"))]
    if faculty_filter:
        programmes = [item for item in programmes if programme_has_faculty(item, faculty_filter)]
    faculty_order = {"Arts": 0, "Business Administration": 1, "Education": 2,
                     "Engineering": 3, "Law": 4, "Medicine": 5, "Science": 6,
                     "Social Science": 7, "Others": 99}
    programmes.sort(key=lambda item: (faculty_order.get(str(item.get("faculty") or "Others"), 90), item["title"]))
    course_index = load_course_index()
    CURRENT_YEAR = year
    MINOR_COURSE_MEMBERSHIPS = load_minor_course_index(year)
    available_years = discover_available_years()
    expected_pages = {f'{item["source_file"]}.html' for item in programmes}
    for stale in major_dir.glob("*.html"):
        if stale.name not in expected_pages:
            stale.unlink()

    display_year = year.replace("_", "–")

    for position, data in enumerate(programmes):
        CURRENT_MAJOR = data
        def render_additional_block(block):
            units = unit_tag(block.get("total_units"))
            description_box = f'<div class="section"><p>{linked_text(block["description"])}</p></div>' if block.get("description") else ""
            contents = "".join(render_subsection(section, course_index) for section in block["sections"])
            block_notes = ""
            if block.get("notes"):
                note_rows = "".join(render_note(note, course_index) for note in block["notes"])
                block_notes = f'<h3>Explanatory Notes</h3><div class="notes-section">{note_rows}</div>'
            flat = " flat-additional" if block["title"].startswith("2nd Degree:") else ""
            return f'<section class="additional-requirements{flat}"><h2>{esc(block["title"])}{units}</h2>{description_box}<div class="subsections">{contents}</div>{block_notes}</section>'

        requirement_blocks = data.get("additional_requirements", [])
        after_section_2 = [block for block in requirement_blocks if block.get("placement") == "after_section_2"]
        before_notes = [block for block in requirement_blocks if block.get("placement", "before_notes") == "before_notes"]
        after_notes = [block for block in requirement_blocks if block.get("placement") == "after_notes"]
        sections_html = []
        for section in data.get("sections", []):
            marker = f'<span class="section-marker">{esc(section.get("marker"))}</span>' if section.get("marker") else ""
            units = unit_tag(section.get("units"))
            title = esc(section.get("title"))
            text_parts = [f'<p>{linked_text(text)}</p>' for text in section.get("text", [])]
            section_box = f'<h2>{marker}{title}{units}</h2>'
            if text_parts:
                section_box += f'<div class="section">{"".join(text_parts)}</div>'
            section_box += course_details(section.get("codes", []), course_index)
            subsections = [render_subsection(subsection, course_index) for subsection in section.get("subsections", [])]
            if subsections:
                section_box += f'<div class="subsections">{"".join(subsections)}</div>'
            sections_html.append(section_box)
            if section.get("marker") == "2." and data.get("recommended_course_pattern"):
                sections_html.append(render_course_pattern(data["recommended_course_pattern"]))
            if section.get("marker") == "2.":
                sections_html.extend(render_additional_block(block) for block in after_section_2)

        notes = ""
        if data.get("notes"):
            note_rows = [render_note(note, course_index) for note in data["notes"]]
            notes = f'<h2>Explanatory Notes</h2><div class="notes-section">{"".join(note_rows)}</div>'

        programme_description = data.get("description") or "Students are required to complete the following programme requirements."
        description_lines = data.get("description_lines") or [programme_description]
        description = "".join(
            f'<h2 class="description-heading">{esc(line)}</h2>'
            if line in {"Pre-clinical Programme", "Clinical Programme"}
            else f'<p>{linked_text(line)}</p>'
            for line in description_lines
        )
        total = f' &middot; {esc(data.get("total_units"))} units' if data.get("total_units") else ""
        affiliations = [str(value) for value in data.get("faculties", []) if value]
        faculty = ", ".join(affiliations) or str(data.get("faculty") or "CUHK")
        requirement_title = f'<h2>{esc(data.get("requirement_title"))}</h2>' if data.get("requirement_title") else ""
        year_selector = detail_year_selector(year, data["source_file"], available_years)
        top = f'''<div class="top-bar"><div class="bar-row"><button class="sidebar-toggle" onclick="toggleSidebar()" aria-label="Open major navigation" aria-controls="majorSidebar" aria-expanded="false">☰</button><div class="breadcrumb"><a href="../index.html">CUHK Majors</a> / {esc(faculty)} / {esc(data["title"])}</div><div class="bar-controls">{year_selector}<button type="button" class="settings-toggle" onclick="toggleSettings()" aria-label="Open course table settings" aria-controls="tableSettings" aria-expanded="false">&#9881; Settings</button></div></div>{nav(programmes, position)}</div><h1>{esc(data["title"])} &mdash; CUHK Major Requirements ({display_year})</h1><p class="admit-year">Faculty: {esc(faculty)} &middot; Admission code: {esc(data["admission_code"])}{total} &middot; For students admitted in {display_year}</p>{requirement_title}<div class="section">{description}</div>'''
        supplementary_notes = []
        for block in data.get("supplementary_note_sections", []):
            copy = "".join(f'<div class="section"><p>{linked_text(text)}</p></div>' for text in block.get("text", []))
            children = "".join(render_subsection(item, course_index) for item in block.get("subsections", []))
            supplementary_notes.append(f'<h2>{esc(block["title"])}</h2>{copy}<div class="subsections">{children}</div>')
        intro_sections = "".join(
            f'<h2>{esc(item.get("title"))}</h2><div class="section">'
            + "".join(f'<p>{linked_text(line)}</p>' for line in item.get("text", [])) + '</div>'
            for item in data.get("intro_sections", [])
        )
        full_body = (top + intro_sections + "".join(sections_html)
                     + "".join(render_additional_block(block) for block in before_notes)
                     + notes
                     + "".join(render_additional_block(block) for block in after_notes)
                     + "".join(supplementary_notes))
        output = major_dir / f'{data["source_file"]}.html'
        canonical_path = f'/major/{year}/majors/{data["source_file"]}'
        page_title = f'{data["title"]} Requirements {display_year} | CUHK'
        meta_description = (
            f'View the {data["title"]} major programme requirements for CUHK {faculty} '
            f'students admitted in {display_year}, including courses, units and enrolment information.'
        )
        structured_data = breadcrumb_data([
            ("CUHK Major Programme List", f"/major/{year}/"),
            (data["title"], canonical_path),
        ])
        write_generated(
            output,
            page_shell(
                page_title,
                full_body,
                sidebar(programmes, data["source_file"]),
                description=meta_description,
                canonical_path=canonical_path,
                structured_data=structured_data,
            ),
        )

    faculty_sections = []
    faculties = sorted({str(item.get("faculty") or "Others") for item in programmes},
                       key=lambda faculty: (faculty_order.get(faculty, 90), faculty))
    for faculty in faculties:
        faculty_programmes = [item for item in programmes if str(item.get("faculty") or "Other") == faculty]
        cards = "".join(
            f'<a href="majors/{esc(item["source_file"])}.html"><div class="card"><span class="card-code">{esc(item["title"])}</span><span class="card-admission">{esc(item["admission_code"])}</span></div></a>'
            for item in faculty_programmes
        )
        faculty_sections.append(f'<h2>{esc(faculty)}</h2><div class="card-grid">{cards}</div>')
    scope = f"{faculty_filter} " if faculty_filter else ""
    index_title = f"CUHK {scope}Major Programme List {display_year}"
    index_description = (
        f"Browse all {len(programmes)} CUHK {scope.lower()}major programmes for {display_year} "
        "and view programme requirements, courses, units and enrolment information."
    )
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": index_title,
        "numberOfItems": len(programmes),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": item["title"],
                "url": absolute_url(f'/major/{year}/majors/{item["source_file"]}'),
            }
            for position, item in enumerate(programmes, start=1)
        ],
    }
    faculty_summary = (
        f'{len(programmes)} programmes'
        if faculty_filter
        else f'{len(programmes)} programmes across {len(faculties)} faculties'
    )
    year_options = "".join(
        f'<option value="../{candidate}/index.html"{" selected" if candidate == year else ""}>'
        f'{candidate.replace("_", "–")}</option>'
        for candidate in available_years
    )
    index_year_selector = (
        '<select onchange="window.location=this.value" class="year-select">'
        + year_options
        + "</select>"
        if len(available_years) > 1
        else ""
    )
    index_body = f'{index_year_selector}<h1>CUHK {scope}Major Programme List ({display_year})</h1><p class="meta">{faculty_summary} &middot; For students admitted in {display_year}</p><div class="index-actions"><a href="../../index.html" class="index-action">View Minor Programmes &rarr;</a></div>{"".join(faculty_sections)}'
    write_generated(
        site_dir / "index.html",
        page_shell(
            index_title,
            index_body,
            extra_css=INDEX_ACTION_CSS,
            description=index_description,
            canonical_path=f"/major/{year}/",
            structured_data=item_list,
        ),
    )
    write_generated(
        output_root / "index.html",
        f'<!doctype html><meta http-equiv="refresh" content="0;url={year}/index.html"><title>CUHK Major Programmes</title>',
    )
    print(f"Generated {len(programmes)} major pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2026_27")
    parser.add_argument("--faculty", default=None, help="Only include programmes affiliated with this faculty")
    parser.add_argument("--output-root", type=Path, default=PUBLIC)
    cli_args = parser.parse_args()
    generate(cli_args.year, cli_args.output_root, cli_args.faculty)

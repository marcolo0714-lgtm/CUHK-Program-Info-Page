import json
import re
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--year", default=None, help="Admission year (e.g. 2025_26). If omitted, processes all years.")
args = parser.parse_args()

BASE_DIR = Path(__file__).parent
MINOR_JSON_BASE = BASE_DIR / "minor_json"
COURSE_INFO_DIR = Path(__file__).parent.parent / "course_extraction" / "course_info"

def _detect_years():
    """Return sorted list of year directory names (excluding *_copy backups)."""
    years = []
    for d in MINOR_JSON_BASE.iterdir():
        if d.is_dir() and d.name != d.name.rstrip('_copy'):
            # Skip directories ending in _copy
            if d.name.endswith('_copy'):
                continue
        if d.is_dir() and not d.name.endswith('_copy'):
            years.append(d.name)
    return sorted(years)

TARGET_YEARS = [args.year] if args.year else _detect_years()
if not TARGET_YEARS:
    print("No year directories found in minor_json/. Run generate_minor_json.py first.")
    sys.exit(1)
print(f"Processing years: {', '.join(TARGET_YEARS)}")

MINOR_JSON_DIR = None   # set per-year in generate()
SITE_DIR = None
OVERRIDE_FILE = None


# ── course resolution ─────────────────────────────────────────────────

def load_course_index():
    """Build ``{ 'DEPT 1234': {title, unit, prereq} }`` from course_info."""
    index = {}
    for jp in sorted(COURSE_INFO_DIR.glob("*.json")):
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            code = entry.get("code", "")
            if code:
                index[code] = {
                    "title": entry.get("title", ""),
                    "unit": entry.get("unit", ""),
                    "prereq": entry.get("info", ""),
                    "term_1": entry.get("term_1", False),
                    "term_2": entry.get("term_2", False),
                }
    return index


def resolve_courses(codes, course_index):
    """Convert a list of 'DEPT 1234' strings into course objects."""
    return [
        {
            "code": code,
            "title": course_index.get(code, {}).get("title", ""),
            "unit": course_index.get(code, {}).get("unit", ""),
            "prereq": course_index.get(code, {}).get("prereq", ""),
            "term_1": course_index.get(code, {}).get("term_1", False),
            "term_2": course_index.get(code, {}).get("term_2", False),
        }
        for code in codes
    ]


CSS = """\
:root { --bg: #f8f9fa; --card: #fff; --border: #dee2e6; --accent: #2563eb;
        --text: #212529; --muted: #6c757d; --warn-bg: #fff8f0; --warn: #b45309;
        --tbl-border: #868a90; --tbl-border-light: #d5d8dc; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:var(--bg); color:var(--text); line-height:1.6; display:flex; }
.title-row { display:flex; justify-content:space-between; align-items:baseline; }
h1 { font-size:1.7em; }
h2 { font-size:1.2em; margin:1.4em 0 .5em; padding-bottom:4px;
     border-bottom:1px solid var(--border); color:#333; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.breadcrumb { margin-bottom:1em; color:var(--muted); font-size:.9em; min-width:0;
    white-space:normal; overflow-wrap:anywhere; }
.section { background:var(--card); padding:14px 18px; border-radius:8px;
           border:1px solid var(--border); margin-bottom:16px; }
.section pre { white-space:pre-wrap; font-family:inherit; margin:0; }
table { width:100%; border-collapse:collapse; background:var(--card);
        border-radius:8px; overflow:hidden; border:1px solid var(--border); margin-bottom:16px; }
th,td { padding:9px 13px; text-align:left; border-bottom:1px solid var(--tbl-border); font-size:.92em; }
th:first-child, td:first-child { white-space:nowrap; }
th:nth-child(3), td:nth-child(3) { white-space:nowrap; text-align:center;
    border-left:1px solid var(--tbl-border); }
th:nth-child(4), td:nth-child(4) { white-space:nowrap; text-align:center;
    border-right:1px solid var(--tbl-border); }
td:nth-child(5) { word-break:normal; overflow-wrap:anywhere; }
th { background:#fafafa; font-weight:600; color:#555; }
tr:hover { background:#f9f9f9; }
.eq-row td { border-bottom-color: var(--tbl-border-light); }
.nf { background:var(--warn-bg); color:var(--warn); }
.nf:hover { background:#fff5eb; }
.term-yes { background:#d4edda; }
.prereq-sentence { display:block; padding-left:1.5em; text-indent:-1.5em; }
.prereq-indent { text-indent:0; }
.card { background:var(--card); border-radius:8px; padding:12px 18px;
        border:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
.card:hover { border-color:var(--accent); }
.card-code { font-weight:600; color:var(--accent); }
.card-grid { display:flex; flex-wrap:wrap; gap:8px; align-items:stretch; }
.card-grid > a { flex:1 0 400px; max-width:100%; text-decoration:none; display:flex; }
.card-grid .card { width:100%; justify-content:flex-start; }
.meta { color:var(--muted); font-size:.85em; white-space:nowrap; }
.tag { display:inline-block; background:#e8f0fe; color:var(--accent); border-radius:4px;
       padding:2px 8px; font-size:.8em; margin-right:6px; }
.req-row { display:flex; justify-content:space-between; align-items:baseline; padding:4px 0; }
.req-row:first-child { padding-top:0; }
.req-row:last-child { padding-bottom:0; }
.section-stream { margin-left: 28px; }
.section-stream + .course-details { margin-left: 28px; }
.nav-bar { display:flex; justify-content:space-between; padding:12px 0;
           border-top:1px solid var(--border); margin-top:12px; margin-bottom:12px; }
.nav-bar a { font-size:.9em; }
.nav-bar-bottom { border-top:none; margin-top:0; padding-top:4px;
                  border-bottom:none; margin-bottom:0; padding-bottom:12px; }
.course-details { margin-bottom:16px; }
.course-details summary { cursor:pointer; padding:6px 0; color:var(--accent);
    font-size:.9em; font-weight:500; }
.course-details summary:hover { text-decoration:underline; }
.course-details table { margin-top:8px; }
.notes-section, .notes-section p, .notes-section span, .notes-section td {
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif !important;
    font-size:.95em; line-height:1.6; }
.notes-point { display:flex; align-items:flex-start; gap:10px; padding:10px 14px;
    cursor:default; transition:background .15s; }
.notes-point:hover { background:#f0f4ff; }
.point-idx { font-weight:600; color:var(--accent); min-width:22px; flex-shrink:0; }
.point-text { flex:1; }
.point-text p { margin:0; }
.notes-table-section table { background:var(--card); border-collapse:collapse;
    border-radius:8px; overflow:hidden; }
.notes-table-section td { padding:9px 13px; border-bottom:1px solid var(--tbl-border); }
.notes-table-section tr:hover { background:#f9f9f9; }
.checker-link { display:inline-block; font-size:.85em; color:var(--accent);
    margin-left:12px; }

/* ── Sidebar ── */
.sidebar { width:max-content; min-width:280px; max-width:calc(100vw - 100px);
    height:100vh; position:fixed; inset:0 auto 0 0; z-index:99;
    overflow:auto; background:var(--card); border-right:1px solid var(--border);
    padding:12px 0; font-size:.88em; transform:translateX(-100%);
    transition:transform .25s; box-shadow:none; }
.sidebar.open { transform:translateX(0); box-shadow:2px 0 12px rgba(0,0,0,.15); }
.sidebar nav { min-width:max-content; }
.sidebar-header { padding:6px 18px 10px; font-weight:600; color:var(--muted);
    border-bottom:1px solid var(--border); margin-bottom:6px; }
.fac-group { margin:0; }
.fac-group summary { padding:6px 16px; font-weight:600; font-size:.92em;
    cursor:pointer; color:#555; white-space:nowrap; overflow:visible; text-overflow:clip; }
.fac-group summary:hover { color:var(--accent); }
.sidebar a { display:block; padding:3px 16px 3px 22px; color:var(--text);
    text-decoration:none; border-left:3px solid transparent;
    white-space:nowrap; overflow:visible; text-overflow:clip; }
.sidebar a:hover { background:#f0f4ff; color:var(--accent); }
.sidebar a.active { font-weight:600; color:var(--accent);
    background:#e8f0fe; border-left-color:var(--accent); }
.sidebar-toggle { display:block; flex-shrink:0; border:1px solid var(--border);
    border-radius:6px; background:var(--card); padding:4px 8px; font-size:1.1em;
    cursor:pointer; line-height:1; }
.sidebar-toggle:hover { background:var(--accent); color:#fff; border-color:var(--accent); }
.sidebar-overlay { position:fixed; inset:0; background:rgba(0,0,0,.25); z-index:98;
    opacity:0; visibility:hidden; pointer-events:none; transition:opacity .25s,visibility .25s; }
.sidebar-overlay.open { opacity:1; visibility:visible; pointer-events:auto; }
body.sidebar-open { overflow:hidden; }
.content { flex:1; min-width:0; }
.content-inner { max-width:1800px; margin:0 auto;
    padding:20px clamp(42px, 6vw, 96px); }

/* ── Index page (no sidebar) ── */
.page-index .container { max-width:1800px; margin:0 auto;
    padding:20px clamp(42px, 6vw, 96px); }

/* ── Footer ── */
.site-footer { margin-top:32px; padding-top:12px; border-top:1px solid var(--border);
    font-size:0.82em; color:var(--muted); text-align:center; }
.site-footer a { color:var(--muted); }
.site-footer a:hover { color:var(--accent); }

@media (max-width:768px) {
    body { display:block; max-width:100vw; }
    html { overflow-x:hidden; }
    .sidebar { width:calc(100vw - 100px); min-width:0;
        max-width:calc(100vw - 100px); }
    .sidebar.open .sidebar-header { padding-top:42px; }
    .content-inner { padding:0 30px 12px; }
    .page-index .container { padding:20px 30px; }
    .top-bar { position:sticky; top:0; z-index:50; margin:0; border-radius:0;
        flex-direction:column; align-items:stretch; gap:4px; padding:6px 0 4px; }
    h1 { font-size:1.4em; }
    .meta { white-space:normal; }
    .card { flex-wrap:wrap; }
    th:first-child, td:first-child { white-space:normal; max-width:6em; }
    th:nth-child(3), td:nth-child(3) { white-space:normal; }
    th, td { padding:6px 8px; font-size:0.82em; }
    .notes-table-section { overflow-x:auto; -webkit-overflow-scrolling:touch; }
    .notes-table-section table { width:auto !important; max-width:none; }
    .notes-table-section td { white-space:normal; overflow-wrap:break-word; }
}
.year-select {
    font-size: 0.9rem; padding: 4px 10px; border: 1px solid var(--border);
    border-radius: 6px; background: var(--card); color: var(--text);
    margin-bottom: 16px; cursor: pointer;
}
/* ── Sticky top bar ── */
.top-bar { position:sticky; top:0; z-index:50; background:var(--bg);
    padding:8px 0 6px; margin:-8px 0 0;
    border-bottom:1px solid var(--border); }
.top-bar .bar-row { display:flex; align-items:center; gap:12px; width:100%; }
.top-bar .breadcrumb { margin-bottom:0; flex:1; min-width:0; white-space:normal;
    overflow:visible; overflow-wrap:anywhere; }
.top-bar .bar-controls { display:flex; align-items:center; gap:8px;
    font-size:.85em; white-space:nowrap; }
.bar-year-select { font-size:.85em; padding:4px 10px; border:1px solid var(--border);
    border-radius:6px; background:var(--card); color:var(--text); cursor:pointer; font-family:inherit; }
.bar-year-select:hover { border-color:var(--accent); }
#prereq-toggle { font-size:.85em; padding:5px 12px; border:1px solid var(--border);
    border-radius:6px; background:var(--card); color:var(--text); cursor:pointer;
    font-family:inherit; transition:background .15s,color .15s,border-color .15s; }
#prereq-toggle:hover { background:var(--accent); color:#fff; border-color:var(--accent); }
body.prereq-hidden table th:nth-child(5),
body.prereq-hidden table td:nth-child(5) { display:none; }
@media (max-width:768px) {
    .top-bar .bar-row { display:grid; grid-template-columns:auto minmax(0, 1fr);
        align-items:center; gap:6px 8px; }
    .top-bar .bar-controls { grid-column:1 / -1; width:100%; min-width:0;
        justify-content:flex-end; flex-wrap:wrap; white-space:normal; }
    .top-bar .breadcrumb { min-width:0; font-size:.85em; overflow:visible;
        white-space:normal; overflow-wrap:anywhere; }
    .bar-year-select, #prereq-toggle { max-width:100%; white-space:normal; }
}
/* ── Admission year ── */
.admit-year { color:var(--muted); font-size:.85em; margin-top:-4px; margin-bottom:8px; }
/* ── Remove nav-bar top border when directly after top-bar ── */
.top-bar + .nav-bar { border-top:none; padding-top:4px; margin-top:0; }
"""


JS = """\
<script>
(function(){
  var sidebar = document.querySelector('.sidebar');
  if(!sidebar) return;
  var timer;
  sidebar.addEventListener('scroll', function(){
    clearTimeout(timer);
    timer = setTimeout(function(){ localStorage.setItem('sidebarScroll', sidebar.scrollTop); }, 100);
  });
  var groups = document.querySelectorAll('.fac-group');
  for(var i=0; i<groups.length; i++){
    groups[i].addEventListener('toggle', function(){
      var closed=[];
      var all=document.querySelectorAll('.fac-group');
      for(var j=0; j<all.length; j++){
        if(!all[j].open) closed.push(all[j].getAttribute('data-fac'));
      }
      localStorage.setItem('sidebarCollapsed', JSON.stringify(closed));
    });
  }
  // Prerequisite toggle
  var prereqBtn = document.getElementById('prereq-toggle');
  if (prereqBtn) {
    if (localStorage.getItem('hidePrereq') === 'true') {
      document.body.classList.add('prereq-hidden');
      prereqBtn.textContent = 'Show Prerequisites';
    }
    prereqBtn.addEventListener('click', function(){
      var hidden = document.body.classList.toggle('prereq-hidden');
      localStorage.setItem('hidePrereq', hidden);
      prereqBtn.textContent = hidden ? 'Show Prerequisites' : 'Hide Prerequisites';
    });
  }
})();

// Prevent sidebar from navigating when clicking the already-active minor
document.querySelectorAll('.sidebar a').forEach(function(link) {
  link.addEventListener('click', function(e) {
    if (this.classList.contains('active')) {
      e.preventDefault();
    }
  });
});

function toggleSidebar() {
  var sidebar = document.querySelector('.sidebar');
  setSidebarOpen(!sidebar.classList.contains('open'));
}

function closeSidebar() {
  setSidebarOpen(false);
}

function setSidebarOpen(open) {
  var sidebar = document.querySelector('.sidebar');
  var overlay = document.querySelector('.sidebar-overlay');
  if (!sidebar || !overlay) return;
  sidebar.classList.toggle('open', open);
  overlay.classList.toggle('open', open);
  document.body.classList.toggle('sidebar-open', open);
  sidebar.setAttribute('aria-hidden', String(!open));
  document.querySelectorAll('.sidebar-toggle').forEach(function(button) {
    button.setAttribute('aria-expanded', String(open));
  });
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeSidebar();
});
</script>"""

FOOTER_HTML = """\
<div class="site-footer">
  <span>Sources: </span>
  <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx" target="_blank" rel="noopener">CUHK program info</a>
  <span> &middot; </span>
  <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/public/handbook/Default.aspx?id=1840&tv=F&lang=en" target="_blank" rel="noopener">CUHK student handbook</a>
  <span> &middot; </span>
  <a href="https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx" target="_blank" rel="noopener">CUHK course catalog</a>
</div>"""


def minor_page(page_title, body, sidebar_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="prefetch-src 'none'">
<script type="speculationrules">
{{ "prefetch": [{{ "source": "list", "urls": [] }}] }}
</script>
<script defer src="/_vercel/insights/script.js"></script>
<link rel="icon" href="../favicon.ico" sizes="any">
<title>{page_title}</title>
<style>{CSS}</style>
</head>
<body>
<div class="sidebar-overlay" onclick="closeSidebar()" aria-hidden="true"></div>
<aside class="sidebar" id="minor-sidebar" aria-hidden="true">
  <div class="sidebar-header">Minor Programmes</div>
  <nav>{sidebar_html}</nav>
  <script>
(function(){{var closed=JSON.parse(localStorage.getItem('sidebarCollapsed')||'[]');
var groups=document.querySelectorAll('.fac-group');
for(var i=0;i<groups.length;i++){{if(closed.indexOf(groups[i].getAttribute('data-fac'))!==-1)groups[i].removeAttribute('open');}}
var st=localStorage.getItem('sidebarScroll');
if(st!==null)document.querySelector('.sidebar').scrollTop=+st;}})();
</script>
</aside>
<main class="content">
  <div class="content-inner">
{body}
{FOOTER_HTML}
  </div>
</main>
{JS}
</body>
</html>"""


INDEX_ACTION_CSS = """
.index-actions { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 24px; }
.index-action { display:inline-flex; align-items:center; padding:9px 14px;
    background:#e8f0fe; color:var(--accent); border:1px solid #c7d8f7;
    border-radius:6px; font-weight:600; font-size:.9em; text-decoration:none;
    box-shadow:0 1px 2px rgba(37,99,235,.08);
    transition:background .15s,border-color .15s,box-shadow .15s; }
.index-action:hover { background:#dbe8fd; border-color:var(--accent);
    box-shadow:0 2px 5px rgba(37,99,235,.15); text-decoration:none; }
.index-action-primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.index-action-primary:hover { background:#1d4ed8; color:#fff; }
"""


def index_page(page_title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="prefetch-src 'none'">
<script type="speculationrules">
{{ "prefetch": [{{ "source": "list", "urls": [] }}] }}
</script>
<script defer src="/_vercel/insights/script.js"></script>
<link rel="icon" href="favicon.ico" sizes="any">
<title>{page_title}</title>
<style>{CSS}{INDEX_ACTION_CSS}</style>
</head>
<body class="page-index">
<div class="container">
{body}
{FOOTER_HTML}
</div>
</body>
</html>"""


# ── page builders ────────────────────────────────────────────────────

def _format_prereq(prereq):
    """Split prerequisite text into sentence-like <span> blocks with hanging indent.
    Splits on periods, index numbers, semicolons, and key keywords."""
    if prereq == "\u2014":
        return "\u2014"

    text = prereq
    S = "@@BRK@@"

    # 1. Sentence-ending periods only
    #    "word." + space + uppercase = sentence end (word must be >= 2 chars
    #    to skip single-letter abbreviations like "M.A.", "B.Sc.")
    text = re.sub(r"(\b\w{2,}\.)\s+(?=[A-Z])", r"\1" + S, text)
    #    Period after a 4-digit course code (e.g. "1028.")
    text = re.sub(r"(?<=\d{4})\.\s+", "." + S, text)
    #    NOTE: semicolons are NOT blindly split any more – only via step 3 below

    # 2. Numbered items – "1.Something", "1)Something", spaced or not
    #    (?<!\d) ensures we match the full number, not a substring like
    #    "040)" within "CSCI2040)".  Insert break before the index.
    text = re.sub(
        r"(?<!" + S + r")(?<!\d)(\d{1,3}[.)])\s*(?=[A-Z])",
        S + r"\1 ", text,
    )

    # 3. Keywords / semicolons that begin a new section
    #    "Not for student(s)" – unless immediately after "Exclusion" / numbers
    text = re.sub(
        r"(?<!" + S + r")(?<!\bExclusion[=:\s])(?<!\d[.)]\s)(?=\bNot for students?\b)",
        S, text, flags=re.IGNORECASE,
    )
    #    "Course Exclusion" (catch before bare "Exclusion")
    text = re.sub(
        r"(?<!" + S + r")(?<!\d[.)]\s)(?=\bCourse Exclusion\b)",
        S, text,
    )
    #    "Prerequisite(s)" / "Pre-requisite(s)" – case-sensitive, not after slash
    text = re.sub(
        r"(?<!" + S + r")(?<!\d[.)]\s)(?<!\/)(?=\b(?:Pre[- ]?requisite|Prerequisite)s?\b)",
        S, text,
    )
    #    "Corequisite(s)" / "Co-requisite(s)" – case-sensitive, not after slash
    text = re.sub(
        r"(?<!" + S + r")(?<!\d[.)]\s)(?<!\/)(?=\b(?:Co[- ]?requisite|Corequisite)s?\b)",
        S, text,
    )
    #    "Exclusion" (= or :) – case-sensitive, not after "Course "
    text = re.sub(
        r"(?<!" + S + r")(?<!\d[.)]\s)(?<!\bCourse\s)(?=\bExclusion[=:])", S, text,
    )
    #    Semicolon only before an uppercase letter (sentence-like continuation)
    #    "; but", "; or" (lowercase) stay on the same line
    text = re.sub(r"(?<!" + S + r");(?=\s*[A-Z])", S, text)

    # Split, clean, and wrap
    sentences = []
    for s in text.split(S):
        s = s.strip().lstrip(";").strip()
        if not s:
            continue
        if s[-1] not in ".!?:;":
            s += "."
        cls = "prereq-sentence" if not s.startswith("[") else "prereq-sentence prereq-indent"
        sentences.append(f'<span class="{cls}">{s}</span>')

    return "".join(sentences) if sentences else "\u2014"


def _format_code_unit(code, unit):
    """Combine code and unit: 'ANTH 1010' for 3u, 'MUSC 1001 [1]' otherwise."""
    try:
        u = float(unit) if unit else 3.0
    except (ValueError, TypeError):
        u = 3.0
    if u == 3:
        return code
    if u == int(u):
        return f"{code} [{int(u)}]"
    return f"{code} [{u:.1f}]"


def _format_term_cell(available):
    """Return a <td> with green background if the course is available in that term."""
    if available:
        return '<td class="term-yes"></td>'
    return "<td></td>"


def build_course_table(courses, eq_pairs=None):
    """Return HTML <tbody> rows for a list of course objects.
    eq_pairs: set of (code1, code2) tuples that are slash-separated equivalents."""
    eq_pairs = eq_pairs or set()
    rows = ""
    for i, c in enumerate(courses):
        eq_cls = ""
        # Check if this row is the FIRST of an equivalent pair
        if i + 1 < len(courses):
            next_code = courses[i + 1]["code"]
            if (c["code"], next_code) in eq_pairs:
                eq_cls = "eq-row"
        if c.get("title"):
            prereq = c["prereq"] if c["prereq"] else "\u2014"
            prereq = _format_prereq(prereq)
            code_unit = _format_code_unit(c["code"], c.get("unit", ""))
            t1_cell = _format_term_cell(c.get("term_1", False))
            t2_cell = _format_term_cell(c.get("term_2", False))
            tr_open = f'<tr class="{eq_cls}">' if eq_cls else '<tr>'
            rows += (
                f"{tr_open}"
                f"<td>{code_unit}</td>"
                f"<td>{c['title']}</td>"
                f"{t1_cell}"
                f"{t2_cell}"
                f"<td>{prereq}</td>"
                f"</tr>\n"
            )
        else:
            nf_cls = f"nf {eq_cls}".strip()
            rows += (
                f'<tr class="{nf_cls}">'
                f"<td>{c['code']}</td>"
                f'<td colspan="4"><em>(not found in course_info)</em></td>'
                f"</tr>\n"
            )
    return rows


STREAM_PATTERN = re.compile(r'^\(\d+\)\s|^\(i[ivxlcdm]*\)\s', re.IGNORECASE)


def _or_connected(prev_text, curr_text):
    """True if two consecutive row texts are joined by 'OR'."""
    p = prev_text.strip().upper()
    c = curr_text.strip().upper()
    return p.endswith("OR") or p.endswith("; OR") or c.startswith("OR") or c == "OR"


def build_section_html(sec, course_index, eq_pairs=None, is_single=False, desc_units=""):
    """Return HTML for a required / elective section from JSON (row-based)."""
    lines = []
    label = sec.get("label", "")
    # Sum unit counts from rows
    total = 0
    for r in sec.get("rows", []):
        u = r.get("units", "")
        if u and u.strip():
            try:
                total += int(u.strip())
            except ValueError:
                pass
    # For single-section minors, use description total if larger than row sum
    if is_single and desc_units:
        try:
            desc_val = int(desc_units)
            if desc_val > total:
                sec_units = desc_units
            else:
                sec_units = str(total) if total > 0 else ""
        except ValueError:
            sec_units = str(total) if total > 0 else ""
    elif total > 0:
        sec_units = str(total)
        # If section has an explicit units field larger than row sum, use it
        sec_explicit = sec.get("units", "").strip()
        if sec_explicit:
            try:
                sec_explicit_val = float(sec_explicit)
                if sec_explicit_val > total:
                    sec_units = sec_explicit
            except ValueError:
                pass
    else:
        sec_units = sec.get("units", "").strip()
    # Append unit count to heading if not already shown as a unit suffix
    if sec_units:
        # Check if label already ends with a unit-like pattern
        already_shown = re.search(
            r'\b\d+\s*(?:or\s+\d+)?\s*units?\s*$'
            r'|\b:\s*\d+\s*(?:or\s+\d+)?\s*$'
            r'|\s+\d+\s*(?:or\s+\d+)?\s*$',
            label, re.IGNORECASE
        )
        if not already_shown:
            sec_units_max = sec.get("units_max", "")
            if sec_units_max:
                label = label.strip().rstrip(':') + f": {sec_units} to {sec_units_max} units"
            else:
                label = label.strip().rstrip(':') + f": {sec_units} units"
    eq_pairs = set(tuple(p) for p in (eq_pairs or []))
    lines.append(f"<h2>{label}</h2>")

    rows = sec.get("rows", [])
    if not rows:
        return "\n".join(lines)

    # Helper: skip unit-only rows (text is just a bare digit with no codes)
    def _is_unit_only(row):
        t = row["text"].strip()
        return re.match(r'^\d{1,2}\s*$', t) and not row.get("codes")

    # Helper: render a sequence of rows into one section box + course table
    def _flush_block(block, is_stream=False):
        if not block:
            return
        cls_suffix = ' section-stream' if is_stream else ''
        row_cls = 'req-row'
        html_parts = []
        all_courses = []
        for r in block:
            text = r["text"].strip()
            if not text or _is_unit_only(r):
                all_courses.extend(resolve_courses(r.get("codes", []), course_index))
                continue
            rh = f'<div class="{row_cls}">'
            rh += f'<span class="row-text">{text}</span>'
            if r.get("units"):
                if r.get("units_max"):
                    rh += f'<span class="meta">({r["units"]} to {r["units_max"]} units)</span>'
                else:
                    rh += f'<span class="meta">({r["units"]} units)</span>'
            rh += '</div>'
            html_parts.append(rh)
            all_courses.extend(resolve_courses(r.get("codes", []), course_index))
        if not html_parts and not all_courses:
            return
        lines.append(
            f'<div class="section{cls_suffix}">' + "".join(html_parts) + '</div>'
        )
        if all_courses:
            tbody = build_course_table(all_courses, eq_pairs)
            lines.append(
                f'<details class="course-details">'
                f'<summary>Show {len(all_courses)} course(s) →</summary>'
                f"<table><thead><tr>"
                f'<th title="Course code — [units] shown only when not 3">Code</th>'
                f'<th title="Course title">Title</th>'
                f'<th title="Available in 2026-27 Term 1">T1</th>'
                f'<th title="Available in 2026-27 Term 2">T2</th>'
                f'<th title="Enrollment requirements">Prerequisites</th>'
                f"</tr></thead><tbody>\n{tbody}</tbody></table>"
                f'</details>'
            )

    buf = []
    i = 0
    while i < len(rows):
        row = rows[i]
        text = row["text"].strip()
        # Skip entirely empty rows
        if not text:
            i += 1
            continue
        is_stream = bool(STREAM_PATTERN.match(text))

        if is_stream:
            # Flush current buffer before the stream row
            _flush_block(buf)
            buf = []
            # Stream rows may be OR-connected among themselves
            stream_block = [row]
            j = i + 1
            while j < len(rows):
                next_text = rows[j]["text"].strip()
                next_is_stream = bool(STREAM_PATTERN.match(next_text))
                if next_is_stream and _or_connected(stream_block[-1]["text"], next_text):
                    stream_block.append(rows[j])
                    j += 1
                else:
                    break
            _flush_block(stream_block, is_stream=True)
            i = j
            continue

        # Non-stream row: add to buffer
        buf.append(row)

        codes = row.get("codes", [])
        has_courses = bool(codes)

        if has_courses:
            # Check if the NEXT row is OR-connected → extend buffer instead of flushing
            j = i + 1
            while j < len(rows):
                next_row = rows[j]
                next_text = next_row["text"].strip()
                next_is_stream = bool(STREAM_PATTERN.match(next_text))
                if next_is_stream:
                    break
                if _or_connected(buf[-1]["text"], next_text):
                    buf.append(next_row)
                    j += 1
                else:
                    break
            # Flush OR-extended buffer
            _flush_block(buf)
            buf = []
            i = j
        else:
            i += 1

    # Flush any remaining buffer
    _flush_block(buf)

    return "\n".join(lines)


def _render_note_group(rows, is_point):
    """Render a group of consecutive note rows as point cards or a data table."""
    if is_point:
        # Render each point as a white card
        out = []
        for r in rows:
            # Extract first <td> (index) and rest (content)
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
            if not tds:
                continue
            idx_cell = tds[0]
            content_cell = ''.join(tds[1:]) if len(tds) > 1 else ''
            idx_text = re.sub(r'<[^>]+>', '', idx_cell).replace('\xa0', ' ').strip()
            # Remove index text from content cell if duplicated
            content_html = re.sub(r'<[^>]+>', ' ', content_cell).replace('\xa0', ' ').strip()
            # Strip trailing empty <p>/<td> tags from right column of original table
            content_html = re.sub(r'\s*(<td[^>]*>)?\s*<p[^>]*>(?:\s|&nbsp;)*</p>\s*(</td>)?\s*$',
                '', content_html, flags=re.IGNORECASE
            )
            # Strip leading &nbsp; entities and whitespace from Word HTML
            content_html = re.sub(r'^(&nbsp;|\s)+', '', content_html)
            out.append(
                f'<div class="section notes-point">'
                f'<span class="point-idx">{idx_text}</span>'
                f'<span class="point-text">{content_html}</span>'
                f'</div>'
            )
        return '\n'.join(out)
    else:
        # Render as a data table
        # Flatten: if a row's HTML contains nested <tr> elements (wrapper
        # rows from the source), extract just the inner trs.
        flat_rows = []
        for r in rows:
            if '<tr' in r.lower():
                inner = re.findall(r'<tr[^>]*>(.*?)</tr>', r, re.DOTALL)
                flat_rows.extend(inner)
            else:
                flat_rows.append(r)
        rows = flat_rows
        # Strip leading spacer row (empty after tag removal)
        if rows:
            first_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', rows[0]).replace('\xa0', ' ')).strip()
            if not first_norm:
                rows = rows[1:]
        # Now apply existing dedup/header-reorder logic
        if len(rows) >= 2:
            first_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', rows[0]).replace('\xa0', ' ')).strip()
            last_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', rows[-1]).replace('\xa0', ' ')).strip()
            if first_norm and first_norm == last_norm:
                rows = rows[:-1]
            else:
                is_header = lambda t: 'courses' in t.lower() and 'equivalent' in t.lower()
                if is_header(last_norm) and not is_header(first_norm):
                    rows = [rows[-1]] + rows[:-1]
        tbl = ''.join(f'<tr>{r}</tr>' for r in rows)
        return f'<div class="notes-table-section"><table>{tbl}</table></div>'


def build_nav(prev_stem, prev_title, next_stem, next_title, bottom=False):
    cls = 'nav-bar nav-bar-bottom' if bottom else 'nav-bar'
    left = f'<a href="{prev_stem}.html">← {prev_title}</a>' if prev_stem else "<span></span>"
    right = f'<a href="{next_stem}.html">{next_title} →</a>' if next_stem else "<span></span>"
    return f'<div class="{cls}">{left}{right}</div>'


def _normalize_override_entry(raw_code):
    """Normalize a raw override code entry (may be no-space or have bracket
    notation). Returns (code_str, alt_code_str) or (code_str, None).
    'ANTH2370'       -> ('ANTH 2370', None)
    'CURE3409 [#CUMT3009]' -> ('CURE 3409', 'CUMT 3009')  # cross-dept eq
    'CURE2001[1001]' -> ('CURE 2001', 'CURE 1001')  # same-dept eq
    'CURE2006 [1006]' -> ('CURE 2006', 'CURE 1006')  # same-dept eq with space
    'CURE4008[3008]' -> ('CURE 4008', 'CURE 3008')  # same-dept eq"""
    s = raw_code.strip()
    # Cross-dept bracket equivalence: CODE [#DEPT CODE]
    m = re.match(r'^([A-Z]{2,5})(\d{4})\s*\[#([A-Z]{2,5})(\d{4})\]$', s)
    if m:
        return (f"{m.group(1)} {m.group(2)}", f"{m.group(3)} {m.group(4)}")
    # Same-dept bracket equivalence: CODE[*CODE] or CODE[CODE]
    m = re.match(r'^([A-Z]{2,5})(\d{4})\s*\[\*?(\d{4})\]$', s)
    if m:
        return (f"{m.group(1)} {m.group(2)}", f"{m.group(1)} {m.group(3)}")
    # Same-dept bracket equivalence with space: CODE [*CODE] or CODE [CODE]
    m = re.match(r'^([A-Z]{2,5})\s*(\d{4})\s*\[\*?(\d{4})\]$', s)
    if m:
        return (f"{m.group(1)} {m.group(2)}", f"{m.group(1)} {m.group(3)}")
    # Plain code without space: DEPT1234
    m = re.match(r'^([A-Z]{2,5})(\d{4})$', s)
    if m:
        return (f"{m.group(1)} {m.group(2)}", None)
    # Already normalized "DEPT 1234"
    return (s, None)


def apply_overrides(data, overrides):
    """Apply course code overrides to a minor's section rows in-place.
    For each row whose text matches an override entry, replace the codes."""
    stem = data.get("source_file", "")
    minor_overrides = overrides.get(stem, {})
    if not minor_overrides:
        return
    extra_eq_pairs = []
    for section_name in ("required", "elective"):
        for r in data.get(section_name, {}).get("rows", []):
            text = r.get("text", "").strip()
            if text in minor_overrides:
                raw_codes = minor_overrides[text]
                normalized = []
                for entry in raw_codes:
                    code_a, code_b = _normalize_override_entry(entry)
                    if code_a:
                        normalized.append(code_a)
                    if code_b:
                        normalized.append(code_b)
                        extra_eq_pairs.append([code_a, code_b])
                r["codes"] = normalized
    if extra_eq_pairs:
        existing = data.setdefault("eq_pairs", [])
        for p in extra_eq_pairs:
            if p not in existing:
                existing.append(p)


def build_detail_page(data, course_index, overrides, year, available_years,
                      prev_stem=None, prev_title=None, next_stem=None, next_title=None):
    """Build the complete HTML body for one minor programme detail page."""
    title = data["title"]
    stem = data.get("source_file", "")

    # Apply course overrides before rendering sections
    apply_overrides(data, overrides)

    # ── Top bar (sticky) ──
    year_display = year.replace("_", "-")
    yr_items = []
    for yr in available_years:
        sel = ' selected' if yr == year else ''
        yt = yr.replace("_", "-")
        yr_site = SITE_DIR.parent / yr / "minors" / f"{stem}.html"
        if yr_site.exists():
            yr_items.append(f'<option value="../../{yr}/minors/{stem}.html"{sel}>{yt}</option>')
        elif yr == year:
            yr_items.append(f'<option value="../../{yr}/minors/{stem}.html"{sel}>{yt}</option>')
    yr_select = '<select onchange="window.location=this.value" class="bar-year-select">' + ''.join(yr_items) + '</select>' if len(available_years) > 1 else ""

    top_bar = (
        f'<div class="top-bar">'
        f'<div class="bar-row">'
        f'<button type="button" class="sidebar-toggle" onclick="toggleSidebar()" '
        f'aria-label="Toggle sidebar" aria-controls="minor-sidebar" aria-expanded="false">&#9776;</button>'
        f'<div class="breadcrumb"><a href="../index.html">All Minors</a> &rsaquo; {title}</div>'
        f'<div class="bar-controls">'
        f'{yr_select}'
        f'<button id="prereq-toggle">Hide Prerequisites</button>'
        f'</div>'
        f'</div>'
        f'</div>'
    )

    body = [
        top_bar,
        build_nav(prev_stem, prev_title, next_stem, next_title),
    ]
    faculty = data.get("faculty", "")
    title_html = f"<h1>{title}</h1>"
    if faculty and faculty != "Unknown":
        title_html += f'<span class="meta">{faculty}</span>'
    body.append(f'<div class="title-row">{title_html}</div>')
    body.append(f'<div class="admit-year">Applicable to students admitted in {year_display}.</div>')

    desc = data.get("description", "")
    if desc:
        body.append("<h2>Description</h2>")
        body.append(f'<div class="section"><pre>{desc}</pre></div>')

    eq_pairs = data.get("eq_pairs", [])
    # Parse description total for single-section minors
    desc_units = ""
    has_req = data.get("required", {}).get("label")
    has_ele = data.get("elective", {}).get("label")
    is_single_section = bool(has_req) != bool(has_ele)  # exactly one section
    if is_single_section:
        desc = data.get("description", "")
        dm = re.search(r'minimum\s+of\s+(\d+)\s+units?', desc, re.IGNORECASE)
        if dm:
            desc_units = dm.group(1)

    if data.get("required", {}).get("label"):
        body.append(build_section_html(data["required"], course_index, eq_pairs, is_single_section, desc_units))

    if data.get("elective", {}).get("label"):
        body.append(build_section_html(data["elective"], course_index, eq_pairs, is_single_section, desc_units))

    notes = data.get("explanatory_notes", "")
    if notes:
        # Strip the "Explanatory Note(s):" row or text.
        # If the first row is a standalone header (no point index like "1." or "[a]"),
        # remove the entire <tr>. Otherwise, strip just the label text.
        row_pat = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
        first_tr_m = row_pat.search(notes)
        strip_entire_row = False
        if first_tr_m:
            first_tr_content = first_tr_m.group(1)
            clean_tr = re.sub(r'<[^>]+>', '', first_tr_content).replace('\xa0', ' ').strip()
            clean_tr = re.sub(r'\s+', ' ', clean_tr)
            has_header = bool(re.search(r'Explanatory\s+Note[s]?\s*:', clean_tr, re.IGNORECASE))
            has_point = bool(re.search(r'(?:\d{1,2}\.)|(?:\[[a-z\s*#]*\])', clean_tr))
            if has_header and not has_point:
                strip_entire_row = True

        if strip_entire_row:
            notes = row_pat.sub('', notes, count=1)
        else:
            notes = re.sub(
                r'<p[^>]*>\s*(?:<[^>]+>)*\s*Explanatory\s+Note[s]?\s*:?\s*(?:</[^>]+>)*\s*</p>',
                '', notes, count=1, flags=re.IGNORECASE | re.DOTALL
            )
            notes = re.sub(
                r'(?:<p[^>]*>)?\s*(?:<[^>]+>)*\s*Explanatory\s+Note[s]?\s*:\s*(?:</[^>]+>)*\s*(?:</p>)?',
                '', notes, count=1, flags=re.IGNORECASE
            )
        body.append("<h2>Explanatory Notes</h2>")

        # ── Flatten nested table/tbody tags to avoid duplicate rows ──
        notes = re.sub(r'</?(?:table|tbody|thead|tfoot)\b[^>]*>', '', notes, flags=re.IGNORECASE)

        # ── Parse notes into point rows vs data rows ──
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', notes, re.DOTALL)
        point_idx_pat = re.compile(r'^\s*(\d{1,2}\.|\[[a-z\s*#]*\])')
        find_idx_pat = re.compile(r'(?<!\d)(\d{1,2}\.)(?!\d)|(\[[a-z\s*#]*\])')

        def _has_point_label(row_html):
            """Check if ANY <td> in the row starts with a point index like 1. or [a]."""
            for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
                if point_idx_pat.match(td_text):
                    return True
            return False

        def _collect_indices(row_html):
            """Return labels for point indices found in index-column <td>s only."""
            indices = []
            seen = set()
            for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
                # Only collect from tds that are index columns (start with a point label)
                if not point_idx_pat.match(td_text):
                    continue
                for m in find_idx_pat.finditer(td_text):
                    label = m.group(1) or m.group(2)
                    if label and label not in seen:
                        indices.append(label)
                        seen.add(label)
            return indices

        # Classify: point if any td has index; data otherwise
        # For point rows, try to split into separate point cards using <p> structure
        classified = []
        for row_html in rows:
            clean = re.sub(r'<[^>]+>', '', row_html).replace('\xa0', ' ').strip()
            if not clean:
                continue
            if _has_point_label(row_html):
                indices = _collect_indices(row_html)

                # ── Extract content <p> texts from non-index <td>s ──
                content_paragraphs = []
                for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                    td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
                    # Skip tds that contain only index labels (or are empty)
                    if not td_text or point_idx_pat.match(td_text):
                        continue
                    # Extract non-empty <p> texts from this td
                    for p_html in re.findall(r'<p[^>]*>(.*?)</p>', td_html, re.DOTALL):
                        p_text = re.sub(r'<[^>]+>', '', p_html).replace('\xa0', ' ').strip()
                        p_text = re.sub(r'\s+', ' ', p_text).strip()
                        if p_text:
                            content_paragraphs.append(p_text)

                # ── Pair indices with content paragraphs ──
                if content_paragraphs and len(content_paragraphs) >= len(indices):
                    # One content paragraph per index (pair by position)
                    for idx_label, cp in zip(indices, content_paragraphs):
                        classified.append(('point', idx_label, cp))
                    # Extra content paragraphs (beyond index count) go under the last index
                    for extra in content_paragraphs[len(indices):]:
                        if classified and classified[-1][0] == 'point':
                            prev = classified[-1]
                            classified[-1] = ('point', prev[1], prev[2] + ' ' + extra)
                else:
                    # No content paragraphs to pair — use <p> structure from index tds
                    # to split multi-point rows (e.g. "1." and "2." in same cell)
                    if len(indices) > 1:
                        # Extract <p> texts from index tds and pair with point labels
                        p_texts = []
                        for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                            for p_html in re.findall(r'<p[^>]*>(.*?)</p>', td_html, re.DOTALL):
                                pt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', p_html).replace('\xa0', ' ')).strip()
                                if pt:
                                    p_texts.append(pt)
                        # Walk through p texts: each time we hit a point label, start a new card
                        current_label = None
                        current_buf = []
                        for pt in p_texts:
                            m = point_idx_pat.match(pt)
                            if m:
                                # Flush previous card
                                if current_label and current_buf:
                                    classified.append(('point', current_label, ' '.join(current_buf)))
                                current_label = m.group(1)
                                # Strip the label from the first p
                                pt = re.sub(r'^' + re.escape(m.group(1)) + r'\s*', '', pt)
                                current_buf = [pt] if pt else []
                            elif current_label:
                                current_buf.append(pt)
                        if current_label and current_buf:
                            classified.append(('point', current_label, ' '.join(current_buf)))
                    else:
                        # Single index: give it the full row text
                        plain_text = re.sub(r'\s+', ' ', clean).strip()
                        for idx_label in indices:
                            classified.append(('point', idx_label, plain_text))
            else:
                # Skip data rows that are just whitespace / &nbsp;
                data_norm = re.sub(r'<[^>]+>', '', row_html)
                data_norm = data_norm.replace('&nbsp;', ' ').replace('\xa0', ' ')
                data_norm = re.sub(r'\s+', ' ', data_norm).strip()
                if data_norm:
                    classified.append(('data', '', row_html))

        # ── Deduplicate: remove repeating data blocks (source HTML artifact) ──
        deduped = []
        block_seen = set()
        skipping = False
        for item in classified:
            if item[0] == 'point':
                block_seen.clear()
                skipping = False
                deduped.append(item)
            elif not skipping:
                norm = re.sub(r'\s+', ' ', item[2]).strip()
                if norm in block_seen:
                    skipping = True  # reached duplicate block — skip rest
                else:
                    block_seen.add(norm)
                    deduped.append(item)
        classified = deduped

        # ── Render: group consecutive same-type items ──
        buf = []
        buf_type = None
        for item in classified:
            if item[0] == 'point':
                # Each point is rendered as its own card immediately
                if buf_type == 'data' and buf:
                    body.append(_render_note_group(buf, False))
                    buf = []
                buf_type = 'point'
                # Render single point as a card
                _, label, content = item
                idx_text = label
                # Strip leading repeated index from content (source HTML artifact)
                prefix = re.escape(label.strip()) + r'\s*'
                content = re.sub(r'^' + prefix, '', content, count=1)
                # Strip leading &nbsp; entities and whitespace from Word HTML
                content = re.sub(r'^(&nbsp;|\s)+', '', content)
                body.append(
                    f'<div class="section notes-point">'
                    f'<span class="point-idx">{idx_text}</span>'
                    f'<span class="point-text">{content}</span>'
                    f'</div>'
                )
            else:
                if buf_type == 'point' and buf:
                    # Points already rendered individually above; nothing to flush
                    buf = []
                buf_type = 'data'
                buf.append(item[2])
        if buf:
            body.append(_render_note_group(buf, False))
    else:
        body.append("<h2>Explanatory Notes</h2>")
        body.append('<div class="section notes-point"><span class="point-text">No explanatory notes are provided.</span></div>')

    # Bottom nav
    body.append(build_nav(prev_stem, prev_title, next_stem, next_title, bottom=True))

    result = "\n".join(body)

    # ── Add bidirectional [a]/[b]/[x] anchor links ──
    for letter in "abcdefghijklmnopqrstuvwxyz":
        ref = f"[{letter}]"
        if ref not in result:
            continue
        note_id = f"note_{letter}"
        body_id = f"ref_{letter}"
        notes_start = result.find('<h2>Explanatory Notes</h2>')
        if notes_start == -1:
            continue
        body_part = result[:notes_start]
        notes_part = result[notes_start:]

        # Body: first [x] gets span id (for notes→body); rest get links to notes
        first_body_pos = body_part.find(ref)
        if first_body_pos != -1:
            body_part = (body_part[:first_body_pos] +
                         f'<span id="{body_id}">{ref}</span>' +
                         body_part[first_body_pos + len(ref):])
            body_part = body_part.replace(ref, f'<a href="#{note_id}">{ref}</a>')

        # Notes: first [x] gets span id (anchor target); rest link back to body
        first_notes_pos = notes_part.find(ref)
        if first_notes_pos != -1:
            notes_part = (notes_part[:first_notes_pos] +
                          f'<span id="{note_id}">{ref}</span>' +
                          notes_part[first_notes_pos + len(ref):])
            notes_part = notes_part.replace(ref, f'<a href="#{body_id}">{ref}</a>')

        result = body_part + notes_part

    # ── Clean up section labels ──
    def clean_label(m):
        label = m.group(0)
        inner = re.sub(r'</?h2>', '', label).strip()
        # If unit number present, add "units"
        inner = re.sub(r'(Required|Elective)\s+Course[s]?\s*:?\s*(\d+)\s*$',
                       r'\1 Courses: \2 units', inner, flags=re.IGNORECASE)
        # If no unit number, strip trailing colon
        inner = re.sub(r'(Required|Elective)\s+Course[s]?\s*:\s*$',
                       r'\1 Courses', inner, flags=re.IGNORECASE)
        return f'<h2>{inner}</h2>'
    result = re.sub(r'<h2>.*?</h2>', clean_label, result, flags=re.DOTALL)

    return result


def build_sidebar_html(index_order, active_stem):
    """Build the sidebar navigation HTML grouped by faculty."""
    last_fac = None
    parts = []
    for c in index_order:
        fac = c["faculty"]
        stem = c["stem"]
        title = c["title"]
        if fac != last_fac:
            if last_fac is not None:
                parts.append('</details>')
            parts.append(f'<details class="fac-group" data-fac="{fac}" open>')
            parts.append(f'<summary>{fac}</summary>')
            last_fac = fac
        cls = 'active' if stem == active_stem else ''
        prefix = '&#9654; ' if stem == active_stem else ''
        parts.append(f'<a href="{stem}.html" class="{cls}">{prefix}{title}</a>')
    if last_fac is not None:
        parts.append('</details>')
    return '\n'.join(parts)

def generate(year):
    global MINOR_JSON_DIR, SITE_DIR, OVERRIDE_FILE, YEAR
    YEAR = year
    MINOR_JSON_DIR = MINOR_JSON_BASE / year
    SITE_DIR = Path(__file__).parent.parent / "site" / year
    OVERRIDE_FILE = BASE_DIR / "course_overrides" / f"{year}.json"

    print(f"\n--- {year} ---")

    site_minors_dir = SITE_DIR / "minors"
    site_minors_dir.mkdir(parents=True, exist_ok=True)

    course_index = load_course_index()

    # Load course overrides (optional)
    overrides = {}
    if OVERRIDE_FILE.exists():
        try:
            overrides = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
            print(f"Loaded course overrides: {len(overrides)} minor(s)")
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    json_files = sorted(MINOR_JSON_DIR.glob("*.json"))
    if not json_files:
        print("No JSON files found. Run generate_minor_json.py first.")
        return

    index_cards = []
    not_found_acc = set()

    # ── First pass: load all data into cards ──
    for json_path in json_files:
        stem = json_path.stem
        data = json.loads(json_path.read_text(encoding="utf-8"))
        apply_overrides(data, overrides)
        req_codes = [c for r in data.get("required", {}).get("rows", []) for c in r.get("codes", [])]
        ele_codes = [c for r in data.get("elective", {}).get("rows", []) for c in r.get("codes", [])]
        req_resolved = resolve_courses(req_codes, course_index)
        ele_resolved = resolve_courses(ele_codes, course_index)
        for c in req_resolved + ele_resolved:
            if not c["title"]:
                not_found_acc.add(c["code"])
        index_cards.append({
            "stem": stem,
            "data": data,
            "title": data["title"],
            "faculty": data.get("faculty", "Unknown"),
            "req_count": len(req_resolved),
            "req_found": sum(1 for c in req_resolved if c.get("title")),
            "ele_count": len(ele_resolved),
            "ele_found": sum(1 for c in ele_resolved if c.get("title")),
        })

    # ── Sort into index-page order (faculty groups, "Other" last, alpha by title within faculty) ──
    by_faculty = {}
    for c in index_cards:
        by_faculty.setdefault(c["faculty"], []).append(c)
    fac_keys = sorted(k for k in by_faculty if k != "Other")
    if "Other" in by_faculty:
        fac_keys.append("Other")
    index_order = []
    for fac in fac_keys:
        # Sort cards within faculty by title (case-insensitive)
        for c in sorted(by_faculty[fac], key=lambda c: c["title"].lower()):
            index_order.append(c)

    # ── Determine available years before building detail pages ──
    site_base = SITE_DIR.parent
    all_years = sorted(
        [d.name for d in site_base.iterdir() if d.is_dir() and "_" in d.name]
    ) or [year]

    # ── Second pass: build pages in index order ──
    for i, card in enumerate(index_order):
        stem = card["stem"]
        data = card["data"]
        prev_info = None
        next_info = None
        if i > 0:
            prev_info = (index_order[i - 1]["stem"], index_order[i - 1]["title"])
        if i < len(index_order) - 1:
            next_info = (index_order[i + 1]["stem"], index_order[i + 1]["title"])

        body = build_detail_page(data, course_index, overrides, year, all_years,
                                 prev_stem=prev_info[0] if prev_info else None,
                                 prev_title=prev_info[1] if prev_info else None,
                                 next_stem=next_info[0] if next_info else None,
                                 next_title=next_info[1] if next_info else None)
        sidebar_html = build_sidebar_html(index_order, stem)
        page = minor_page(f"Minor: {data['title']}", body, sidebar_html)
        (site_minors_dir / f"{stem}.html").write_text(page, encoding="utf-8")

    # ── Index page ──
    # cards already in index order (faculty groups, Other last, alpha within)
    cards_html = ""
    last_fac = None
    for c in index_order:
        fac = c["faculty"]
        if fac != last_fac:
            if last_fac is not None:
                cards_html += '</div>\n'
            cards_html += f'<h2>{fac}</h2>\n<div class="card-grid">\n'
            last_fac = fac
        cards_html += (
            f'<a href="minors/{c["stem"]}.html">'
            f'<div class="card">'
            f'<span class="card-code">{c["title"]}</span>'
            f'</div></a>\n'
        )
    cards_html += '</div>\n'

    year_display = year.replace("_", "-")

    # Determine available years for index-page dropdown (must have checker.html)
    checker_years = sorted(
        [d.name for d in site_base.iterdir() if d.is_dir() and "_" in d.name and (d / "checker.html").exists()]
    )
    year_options = "".join(
        f'<option value="../{y}/index.html" {"selected" if y == year else ""}>{y.replace("_","-")}</option>'
        for y in checker_years
    )

    index_body = (
        f'<select onchange="window.location=this.value" class="year-select">'
        f'{year_options}</select>\n'
        f"<h1>CUHK Minor Programmes</h1>"
        f'<p class="meta">{len(index_order)} minor programmes &middot; '
        f'For students admitted in {year_display}</p>\n'
        f'<div class="index-actions">\n'
        f'<a href="checker.html" class="index-action index-action-primary">Check Your Minor Progress &rarr;</a>\n'
        f'<a href="../major/index.html" class="index-action">View Major Programmes &rarr;</a>\n'
        f'</div>\n'
        f"{cards_html}"
    )
    (SITE_DIR / "index.html").write_text(
        index_page("CUHK Minor Programmes", index_body), encoding="utf-8"
    )

    # Keep the site root pointed at the latest generated minor-programme year.
    latest_year = checker_years[-1] if checker_years else year
    latest_label = latest_year.replace("_", "-")
    (site_base / "index.html").write_text(
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head><meta charset="UTF-8">'
        f'<meta http-equiv="refresh" content="0;url={latest_year}/index.html">'
        '<title>CUHK Minor Programmes</title></head>\n'
        f'<body><p>Redirecting to <a href="{latest_year}/index.html">'
        f'{latest_label} Minor Programmes</a>...</p></body>\n'
        '</html>\n',
        encoding="utf-8",
    )

    # ── Report ──
    total_req = sum(c["req_count"] for c in index_order)
    total_ele = sum(c["ele_count"] for c in index_order)
    found_req = sum(c["req_found"] for c in index_order)
    found_ele = sum(c["ele_found"] for c in index_order)
    print(f"{len(index_order)} minor programmes rendered")
    print(f"Required courses: {found_req}/{total_req} matched")
    print(f"Elective courses: {found_ele}/{total_ele} matched")
    print(f"\nSite generated: site/{year}/index.html")


if __name__ == "__main__":
    for yr in TARGET_YEARS:
        generate(yr)

import json
import re
from pathlib import Path


MINOR_JSON_DIR = Path(__file__).parent / "minor_json"
SITE_DIR = Path(__file__).parent / "site"


CSS = """\
:root { --bg: #f8f9fa; --card: #fff; --border: #dee2e6; --accent: #2563eb;
        --text: #212529; --muted: #6c757d; --warn-bg: #fff8f0; --warn: #b45309; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:var(--bg); color:var(--text); line-height:1.6; display:flex; }
.title-row { display:flex; justify-content:space-between; align-items:baseline; }
h1 { font-size:1.7em; }
h2 { font-size:1.2em; margin:1.4em 0 .5em; padding-bottom:4px;
     border-bottom:1px solid var(--border); color:#333; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.breadcrumb { margin-bottom:1em; color:var(--muted); font-size:.9em; }
.section { background:var(--card); padding:14px 18px; border-radius:8px;
           border:1px solid var(--border); margin-bottom:16px; }
.section pre { white-space:pre-wrap; font-family:inherit; margin:0; }
table { width:100%; border-collapse:collapse; background:var(--card);
        border-radius:8px; overflow:hidden; border:1px solid var(--border); margin-bottom:16px; }
th,td { padding:9px 13px; text-align:left; border-bottom:1px solid var(--border); font-size:.92em; }
th { background:#fafafa; font-weight:600; color:#555; }
tr:hover { background:#f9f9f9; }
.nf { background:var(--warn-bg); color:var(--warn); }
.nf:hover { background:#fff5eb; }
.card { background:var(--card); border-radius:8px; padding:12px 18px; margin-bottom:8px;
        border:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
.card:hover { border-color:var(--accent); }
.card-code { font-weight:600; color:var(--accent); }
.meta { color:var(--muted); font-size:.85em; }
.tag { display:inline-block; background:#e8f0fe; color:var(--accent); border-radius:4px;
       padding:2px 8px; font-size:.8em; margin-right:6px; }
.req-row { display:flex; justify-content:space-between; align-items:baseline; padding:8px 0; }
.nav-bar { display:flex; justify-content:space-between; padding:12px 0;
           border-top:1px solid var(--border); margin-top:12px; margin-bottom:12px; }
.nav-bar a { font-size:.9em; }
.nav-bar-bottom { border-bottom:1px solid var(--border); margin-bottom:20px;
                  border-top:none; margin-top:0; padding-bottom:12px; }
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
.notes-table-section td { padding:9px 13px; border-bottom:1px solid var(--border); }
.notes-table-section tr:hover { background:#f9f9f9; }

/* ── Sidebar ── */
.sidebar { width:280px; flex-shrink:0; height:100vh; position:sticky; top:0;
    overflow-y:auto; background:var(--card); border-right:1px solid var(--border);
    padding:12px 0; font-size:.88em; }
.sidebar-header { padding:6px 18px 10px; font-weight:600; color:var(--muted);
    border-bottom:1px solid var(--border); margin-bottom:6px; }
.fac-group { margin:0; }
.fac-group summary { padding:6px 16px; font-weight:600; font-size:.92em;
    cursor:pointer; color:#555; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fac-group summary:hover { color:var(--accent); }
.sidebar a { display:block; padding:3px 16px 3px 22px; color:var(--text);
    text-decoration:none; border-left:3px solid transparent;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.sidebar a:hover { background:#f0f4ff; color:var(--accent); }
.sidebar a.active { font-weight:600; color:var(--accent);
    background:#e8f0fe; border-left-color:var(--accent); }
.sidebar-toggle { display:none; position:fixed; top:8px; left:8px; z-index:100;
    background:var(--card); border:1px solid var(--border); border-radius:6px;
    padding:6px 10px; font-size:1.2em; cursor:pointer; }
.sidebar-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.25);
    z-index:98; }
.content { flex:1; min-width:0; }
.content-inner { max-width:960px; margin:0 auto; padding:20px; }

/* ── Index page (no sidebar) ── */
.page-index .container { max-width:960px; margin:0 auto; padding:20px; }

@media (max-width:768px) {
    body { display:block; }
    .sidebar { position:fixed; left:-300px; top:0; z-index:99;
        transition:left .25s; box-shadow:none; }
    .sidebar.open { left:0; box-shadow:2px 0 12px rgba(0,0,0,.15); }
    .sidebar-toggle { display:block; }
    .sidebar-overlay.open { display:block; }
    .content-inner { padding:12px; }
    h1 { font-size:1.4em; }
}
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
})();

function toggleSidebar() {
  document.querySelector('.sidebar').classList.toggle('open');
  document.querySelector('.sidebar-overlay').classList.toggle('open');
}
</script>"""


def minor_page(page_title, body, sidebar_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<style>{CSS}</style>
</head>
<body>
<button class="sidebar-toggle" onclick="toggleSidebar()" aria-label="Toggle sidebar">&#9776;</button>
<div class="sidebar-overlay" onclick="toggleSidebar()"></div>
<aside class="sidebar">
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
  </div>
</main>
{JS}
</body>
</html>"""


def index_page(page_title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<style>{CSS}</style>
</head>
<body class="page-index">
<div class="container">
{body}
</div>
</body>
</html>"""


# ── page builders ────────────────────────────────────────────────────

def build_course_table(courses):
    """Return HTML <tbody> rows for a list of course objects."""
    rows = ""
    for c in courses:
        if c.get("title"):
            prereq = c["prereq"] if c["prereq"] else "\u2014"
            rows += (
                f"<tr>"
                f"<td>{c['code']}</td>"
                f"<td>{c['title']}</td>"
                f"<td>{c['unit']}</td>"
                f"<td>{prereq}</td>"
                f"</tr>\n"
            )
        else:
            rows += (
                f'<tr class="nf">'
                f"<td>{c['code']}</td>"
                f'<td colspan="3"><em>(not found in course_info)</em></td>'
                f"</tr>\n"
            )
    return rows


def build_section_html(sec):
    """Return HTML for a required / elective section from JSON (row-based)."""
    lines = []
    label = sec.get("label", "")
    lines.append(f"<h2>{label}</h2>")

    # Buffer consecutive row texts into one white box; flush at course tables
    section_buf = ""

    for row in sec.get("rows", []):
        row_html = '<div class="req-row">'
        row_html += f'<span class="row-text">{row["text"]}</span>'
        if row.get("units"):
            row_html += f'<span class="meta">({row["units"]} units)</span>'
        row_html += '</div>'

        courses = row.get("courses", [])
        section_buf += row_html

        if courses:
            lines.append(f'<div class="section">{section_buf}</div>')
            section_buf = ""
            tbody = build_course_table(courses)
            lines.append(
                f'<details class="course-details">'
                f'<summary>Show {len(courses)} course(s) →</summary>'
                f"<table><thead><tr>"
                f"<th>Code</th><th>Title</th><th>Units</th><th>Prerequisites</th>"
                f"</tr></thead><tbody>\n{tbody}</tbody></table>"
                f'</details>'
            )

    # Flush remaining buffer
    if section_buf:
        lines.append(f'<div class="section">{section_buf}</div>')

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
            content_html = re.sub(
                r'\s*(<td[^>]*>)?\s*<p[^>]*>(?:\s|&nbsp;)*</p>\s*(</td>)?\s*$',
                '', content_html, flags=re.IGNORECASE
            )
            out.append(
                f'<div class="section notes-point">'
                f'<span class="point-idx">{idx_text}</span>'
                f'<span class="point-text">{content_html}</span>'
                f'</div>'
            )
        return '\n'.join(out)
    else:
        # Render as a data table
        tbl = ''.join(f'<tr>{r}</tr>' for r in rows)
        return f'<div class="notes-table-section"><table>{tbl}</table></div>'


def build_nav(prev_stem, prev_title, next_stem, next_title, bottom=False):
    cls = 'nav-bar nav-bar-bottom' if bottom else 'nav-bar'
    left = f'<a href="{prev_stem}.html">← {prev_title}</a>' if prev_stem else "<span></span>"
    right = f'<a href="{next_stem}.html">{next_title} →</a>' if next_stem else "<span></span>"
    return f'<div class="{cls}">{left}{right}</div>'


def build_detail_page(data, prev_stem=None, prev_title=None, next_stem=None, next_title=None):
    """Build the complete HTML body for one minor programme detail page."""
    title = data["title"]

    # Title row with faculty right-aligned on same line
    body = [
        f'<div class="breadcrumb"><a href="../index.html">All Minors</a> &rsaquo; {title}</div>',
        build_nav(prev_stem, prev_title, next_stem, next_title),
    ]
    faculty = data.get("faculty", "")
    title_html = f"<h1>{title}</h1>"
    if faculty and faculty != "Unknown":
        title_html += f'<span class="meta">{faculty}</span>'
    body.append(f'<div class="title-row">{title_html}</div>')

    desc = data.get("description", "")
    if desc:
        body.append("<h2>Description</h2>")
        body.append(f'<div class="section"><pre>{desc}</pre></div>')

    if data.get("required", {}).get("label"):
        body.append(build_section_html(data["required"]))

    if data.get("elective", {}).get("label"):
        body.append(build_section_html(data["elective"]))

    notes = data.get("explanatory_notes", "")
    if notes:
        # Strip leading "Explanatory Note(s):" row
        notes = re.sub(
            r'<tr[^>]*>.*?Explanatory\s+Note[s]?\s*:?.*?</tr>',
            '', notes, count=1, flags=re.IGNORECASE | re.DOTALL
        )
        body.append("<h2>Explanatory Notes</h2>")

        # ── Parse notes into point rows vs data rows ──
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', notes, re.DOTALL)
        points = []  # list of (html, is_point)

        for row_html in rows:
            # Extract first <td> text to classify
            first_td = re.search(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
            idx_text = ""
            if first_td:
                idx_text = re.sub(r'<[^>]+>', '', first_td.group(1)).replace('\xa0', ' ').strip()
            # Point row if first td has an index like "1.", "[a]", etc.
            is_point = bool(re.match(r'^(\d+\.|\[[a-z]\])', idx_text))
            points.append((row_html, is_point))

        # ── Render: group consecutive same-type rows ──
        buf = []
        buf_is_point = None
        for row_html, is_point in points:
            # Skip empty spacer rows
            clean = re.sub(r'<[^>]+>', '', row_html).replace('\xa0', ' ').strip()
            if not clean:
                continue
            if buf_is_point is None:
                buf_is_point = is_point
                buf.append(row_html)
            elif is_point == buf_is_point:
                buf.append(row_html)
            else:
                # Flush buffer
                body.append(_render_note_group(buf, buf_is_point))
                buf = [row_html]
                buf_is_point = is_point
        if buf:
            body.append(_render_note_group(buf, buf_is_point))

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

def generate():
    if not MINOR_JSON_DIR.exists():
        print(f"Directory not found: {MINOR_JSON_DIR}")
        print("Run generate_minor_json.py first.")
        return

    site_minors_dir = SITE_DIR / "minors"
    site_minors_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(MINOR_JSON_DIR.glob("*.json"))
    if not json_files:
        print("No JSON files found. Run generate_minor_json.py first.")
        return

    index_cards = []

    # ── First pass: load all data into cards ──
    for json_path in json_files:
        stem = json_path.stem
        data = json.loads(json_path.read_text(encoding="utf-8"))
        req_courses = [c for r in data.get("required", {}).get("rows", []) for c in r.get("courses", [])]
        ele_courses = [c for r in data.get("elective", {}).get("rows", []) for c in r.get("courses", [])]
        index_cards.append({
            "stem": stem,
            "data": data,
            "title": data["title"],
            "faculty": data.get("faculty", "Unknown"),
            "req_count": len(req_courses),
            "req_found": sum(1 for c in req_courses if c.get("title")),
            "ele_count": len(ele_courses),
            "ele_found": sum(1 for c in ele_courses if c.get("title")),
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

        body = build_detail_page(data, 
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
            cards_html += f'<h2>{fac}</h2>\n'
            last_fac = fac
        tags = ""
        if c["req_count"]:
            tags += f'<span class="tag">{c["req_found"]}/{c["req_count"]} req</span>'
        if c["ele_count"]:
            tags += f'<span class="tag">{c["ele_found"]}/{c["ele_count"]} ele</span>'
        cards_html += (
            f'<a href="minors/{c["stem"]}.html">'
            f'<div class="card">'
            f'<div><span class="card-code">{c["title"]}</span></div>'
            f'<div class="meta">{tags}</div>'
            f'</div></a>\n'
        )

    index_body = (
        f"<h1>CUHK Minor Programmes</h1>"
        f'<p class="meta">{len(index_order)} minor programmes &middot; '
        f'Course info from CUHK course catalog</p>\n'
        f"{cards_html}"
    )
    (SITE_DIR / "index.html").write_text(
        index_page("CUHK Minor Programmes", index_body), encoding="utf-8"
    )

    # ── Report ──
    total_req = sum(c["req_count"] for c in index_order)
    total_ele = sum(c["ele_count"] for c in index_order)
    found_req = sum(c["req_found"] for c in index_order)
    found_ele = sum(c["ele_found"] for c in index_order)
    print(f"{len(index_order)} minor programmes rendered")
    print(f"Required courses: {found_req}/{total_req} matched")
    print(f"Elective courses: {found_ele}/{total_ele} matched")
    print(f"\nSite generated: site/index.html")


if __name__ == "__main__":
    generate()

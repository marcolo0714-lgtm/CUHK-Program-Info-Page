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
       background:var(--bg); color:var(--text); line-height:1.6; }
.container { max-width:960px; margin:0 auto; padding:20px; }
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
.row-text { }
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
    line-height:1.6; }
.notes-section table { background:var(--card); border-collapse:collapse;
    border-radius:8px; overflow:hidden; }
.notes-section td { padding:9px 13px; border-bottom:1px solid var(--border); }
.notes-section tr:hover { background:#f9f9f9; }
:target { background:#fff3cd; border-radius:4px; padding:2px 4px;
          scroll-margin-top:20px; }
"""


def html_page(page_title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<style>{CSS}</style>
</head>
<body>
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


def clean_label(label, units):
    """Clean section label: remove trailing colon & unit number, append units."""
    label = label.strip()
    # Remove " : N" or " :" at end
    if units:
        label = re.sub(rf'\s*:\s*{re.escape(units)}\s*$', '', label)
        label += f' ({units} units)'
    else:
        label = re.sub(r'\s*:\s*$', '', label)
    label = re.sub(r'\s+', ' ', label)
    return label


def build_section_html(sec):
    """Return HTML for a required / elective section from JSON (row-based)."""
    lines = []
    label = sec.get("label", "")
    units = sec.get("units", "")
    lines.append(f"<h2>{clean_label(label, units)}</h2>")

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
        # Strip leading "Explanatory Note(s):" row (first <tr> containing it)
        notes = re.sub(
            r'<tr[^>]*>.*?Explanatory\s+Note[s]?\s*:?.*?</tr>',
            '', notes, count=1, flags=re.IGNORECASE | re.DOTALL
        )
        body.append("<h2>Explanatory Notes</h2>")
        body.append(f'<div class="section notes-section">{notes}</div>')

    # Bottom nav
    body.append(build_nav(prev_stem, prev_title, next_stem, next_title, bottom=True))

    result = "\n".join(body)

    # ── Add [a]/[b]/[x] anchor links: body ↔ notes bidirectional ──
    for letter in "abcdefghijklmnopqrstuvwxyz":
        ref = f"[{letter}]"
        if ref not in result:
            continue
        note_id = f"note_{letter}"
        ref_id = f"ref_{letter}"
        notes_start = result.find('<div class="section notes-section">')
        if notes_start == -1:
            continue
        body_part = result[:notes_start]
        notes_part = result[notes_start:]

        # Body: first [x] gets id, rest link to notes (use split on first find)
        idx = body_part.find(ref)
        if idx != -1:
            before = body_part[:idx]
            after = body_part[idx + len(ref):]
            after = after.replace(ref, f'<a href="#{note_id}" class="ref-link">{ref}</a>')
            body_part = before + f'<span id="{ref_id}" class="ref-anchor">{ref}</span>' + after

        # Notes: first [x] gets id, rest link to body
        idx = notes_part.find(ref)
        if idx != -1:
            before = notes_part[:idx]
            after = notes_part[idx + len(ref):]
            after = after.replace(ref, f'<a href="#{ref_id}" class="ref-link">{ref}</a>')
            notes_part = before + f'<span id="{note_id}" class="ref-anchor">{ref}</span>' + after

        result = body_part + notes_part

    return result


# ── main ─────────────────────────────────────────────────────────────

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
        page = html_page(f"Minor: {data['title']}", body)
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
        html_page("CUHK Minor Programmes", index_body), encoding="utf-8"
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

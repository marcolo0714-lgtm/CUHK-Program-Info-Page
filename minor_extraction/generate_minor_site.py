import json
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
h1 { font-size:1.7em; margin-bottom:.3em; }
h2 { font-size:1.2em; margin:1.4em 0 .5em; padding-bottom:4px;
     border-bottom:1px solid var(--border); color:#333; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.breadcrumb { margin-bottom:1em; color:var(--muted); font-size:.9em; }
.section { background:var(--card); padding:14px 18px; border-radius:8px;
           border:1px solid var(--border); margin-bottom:16px; }
.section pre { white-space:pre-wrap; font-family:inherit; }
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
.req-row { padding: 8px 0; }
.row-num { font-weight:600; color:var(--accent); display:inline; }
.row-text { margin-left:6px; }
.nav-bar { display:flex; justify-content:space-between; padding:12px 0; margin-top:20px;
           border-top:1px solid var(--border); }
.nav-bar a { font-size:.9em; }
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


def build_section_html(sec):
    """Return HTML for a required / elective section from JSON (row-based)."""
    lines = []
    label = sec.get("label", "")
    lines.append(f"<h2>{label}</h2>")

    for row in sec.get("rows", []):
        # Row text line (no sequential index number displayed)
        row_html = f'<div class="row-text">{row["text"]}</div>'
        if row.get("units"):
            row_html += f' <span class="meta">({row["units"]} units)</span>'

        courses = row.get("courses", [])
        if courses:
            tbody = build_course_table(courses)
            lines.append(
                f'<div class="req-row">'
                f'{row_html}'
                f'</div>'
                f"<table><thead><tr>"
                f"<th>Code</th><th>Title</th><th>Units</th><th>Prerequisites</th>"
                f"</tr></thead><tbody>\n{tbody}</tbody></table>"
            )
        elif row.get("text"):
            lines.append(
                f'<div class="req-row">'
                f'{row_html}'
                f'</div>'
            )
        else:
            # Row with codes but no text — still show table
            if courses:
                tbody = build_course_table(courses)
                lines.append(
                    f"<table><thead><tr>"
                    f"<th>Code</th><th>Title</th><th>Units</th><th>Prerequisites</th>"
                    f"</tr></thead><tbody>\n{tbody}</tbody></table>"
                )

    return "\n".join(lines)


def build_detail_page(data, prev_stem=None, prev_title=None, next_stem=None, next_title=None):
    """Build the complete HTML body for one minor programme detail page."""
    title = data["title"]

    body = [
        f'<div class="breadcrumb"><a href="../index.html">All Minors</a> &rsaquo; {title}</div>',
        f"<h1>{title}</h1>",
    ]

    # Prev / Next navigation
    nav = []
    if prev_stem:
        nav.append(f'<a href="{prev_stem}.html">← {prev_title}</a>')
    else:
        nav.append("<span></span>")
    if next_stem:
        nav.append(f'<a href="{next_stem}.html">{next_title} →</a>')
    else:
        nav.append("<span></span>")
    body.append(f'<div class="nav-bar">{nav[0]}{nav[1]}</div>')

    faculty = data.get("faculty", "")
    if faculty and faculty != "Unknown":
        body.append(f'<p class="meta">Faculty: {faculty}</p>')

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
        body.append("<h2>Explanatory Notes</h2>")
        body.append(f'<div class="section">{notes}</div>')

    return "\n".join(body)


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

    for i, json_path in enumerate(json_files):
        stem = json_path.stem
        data = json.loads(json_path.read_text(encoding="utf-8"))

        # Prev / Next in the index-sorted order
        prev_info = None
        next_info = None
        if i > 0:
            prev_path = json_files[i - 1]
            prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
            prev_info = (prev_path.stem, prev_data["title"])
        if i < len(json_files) - 1:
            next_path = json_files[i + 1]
            next_data = json.loads(next_path.read_text(encoding="utf-8"))
            next_info = (next_path.stem, next_data["title"])

        body = build_detail_page(data, 
                                 prev_stem=prev_info[0] if prev_info else None,
                                 prev_title=prev_info[1] if prev_info else None,
                                 next_stem=next_info[0] if next_info else None,
                                 next_title=next_info[1] if next_info else None)
        page = html_page(f"Minor: {data['title']}", body)
        (site_minors_dir / f"{stem}.html").write_text(page, encoding="utf-8")

        req_courses = [c for r in data.get("required", {}).get("rows", []) for c in r.get("courses", [])]
        ele_courses = [c for r in data.get("elective", {}).get("rows", []) for c in r.get("courses", [])]
        index_cards.append({
            "stem": stem,
            "title": data["title"],
            "faculty": data.get("faculty", "Unknown"),
            "req_count": len(req_courses),
            "req_found": sum(1 for c in req_courses if c.get("title")),
            "ele_count": len(ele_courses),
            "ele_found": sum(1 for c in ele_courses if c.get("title")),
        })

    # ── Index page ──
    # Group cards by faculty
    by_faculty = {}
    for c in index_cards:
        fac = c.get("faculty", "Unknown")
        by_faculty.setdefault(fac, []).append(c)

    cards_html = ""
    for fac in sorted(by_faculty.keys()):
        cards_html += f'<h2>{fac}</h2>\n'
        for c in by_faculty[fac]:
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
        f'<p class="meta">{len(index_cards)} minor programmes &middot; '
        f'Course info from CUHK course catalog</p>\n'
        f"{cards_html}"
    )
    (SITE_DIR / "index.html").write_text(
        html_page("CUHK Minor Programmes", index_body), encoding="utf-8"
    )

    # ── Report ──
    total_req = sum(c["req_count"] for c in index_cards)
    total_ele = sum(c["ele_count"] for c in index_cards)
    found_req = sum(c["req_found"] for c in index_cards)
    found_ele = sum(c["ele_found"] for c in index_cards)
    print(f"{len(index_cards)} minor programmes rendered")
    print(f"Required courses: {found_req}/{total_req} matched")
    print(f"Elective courses: {found_ele}/{total_ele} matched")
    print(f"\nSite generated: site/index.html")


if __name__ == "__main__":
    generate()

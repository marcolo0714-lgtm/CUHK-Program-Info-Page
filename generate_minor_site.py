import json
import os
import re
from pathlib import Path


MINOR_HTML_DIR = Path(__file__).parent / "minor_html"
COURSE_INFO_DIR = Path(__file__).parent / "course_info"
SITE_DIR = Path(__file__).parent / "site"


def load_course_index():
    """Build a dict mapping 'DEPT 1234' -> {title, unit, info} across all json files."""
    index = {}
    for json_path in COURSE_INFO_DIR.glob("*.json"):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, list):
            continue
        for entry in data:
            code = entry.get("code", "")
            if code:
                index[code] = {
                    "title": entry.get("title", ""),
                    "unit": entry.get("unit", ""),
                    "info": entry.get("info", ""),
                }
    return index


def strip_html(html):
    """Return visible text from an HTML snippet."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(p|tr|td)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(li|div|table|tbody|thead|th|colgroup)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&#39;", "'").replace("&quot;", '"')
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_course_codes(text):
    """Extract all course-code-like patterns from text.

    Returns (resolved_codes, wildcards) where:
      resolved_codes : set('DEPT 1234X')
      wildcards      : set('DEPT 12xx')   -- patterns that cannot be resolved
    """
    codes = set()
    wildcards = set()

    # 1) Wildcard patterns  (e.g.  MATH32xx,  MATH 32xx)
    for m in re.finditer(r"([A-Z]{4})\s*(\d{2})xx", text):
        wildcards.add(f"{m.group(1)} {m.group(2)}xx")

    # 2) Fully-qualified codes  (e.g. CSCI2100, ENGG1110, CSCI 2100, CSCI2100A)
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z])?", text):
        dept = m.group(1)
        num = m.group(2)
        suffix = m.group(3) or ""
        codes.add(f"{dept} {num}{suffix}")

    # 3) Alternatives  shared department  (MATH1010/1018  ->  MATH1010, MATH1018)
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z]?)\s*/\s*(\d{4})([A-Za-z]?)", text):
        dept = m.group(1)
        codes.add(f"{dept} {m.group(2)}{m.group(3) or ''}")
        codes.add(f"{dept} {m.group(4)}{m.group(5) or ''}")

    # 4) Implicit-department comma lists  ("AIST2010, 3110, 3120")
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z]?)\s*,\s+([\d,\s/]+)", text):
        dept = m.group(1)
        codes.add(f"{dept} {m.group(2)}{m.group(3) or ''}")
        tail = m.group(4)
        for nm in re.finditer(r"(\d{4})([A-Za-z]?)\s*(/\s*(\d{4})([A-Za-z]?)\s*)?", tail):
            if nm.group(1):
                codes.add(f"{dept} {nm.group(1)}{nm.group(2) or ''}")
            if nm.group(4):
                codes.add(f"{dept} {nm.group(4)}{nm.group(5) or ''}")

    # ---- manual-review markers: patterns we cannot resolve ----
    # "XX units from YYYY courses at 3000+ level"  (no specific code)
    # Already handled as wildcards above.

    return sorted(codes), sorted(wildcards)


def build_course_table(codes, course_index):
    """Return (html_rows, table_rows) for given course codes."""
    rows_html = ""
    table_data = []
    for code in codes:
        info = course_index.get(code)
        if info:
            prereq = info["info"] if info["info"] else "—"
            rows_html += (
                f"<tr>"
                f"<td>{code}</td>"
                f"<td>{info['title']}</td>"
                f"<td>{info['unit']}</td>"
                f"<td>{prereq}</td>"
                f"</tr>\n"
            )
            table_data.append({
                "code": code,
                "title": info["title"],
                "unit": info["unit"],
                "prereq": prereq,
                "found": True,
            })
        else:
            rows_html += (
                f"<tr class=\"not-found\">"
                f"<td>{code}</td>"
                f"<td colspan=\"3\"><em>(not found in course_info)</em></td>"
                f"</tr>\n"
            )
            table_data.append({
                "code": code,
                "title": "",
                "unit": "",
                "prereq": "",
                "found": False,
            })
    return rows_html, table_data


def parse_minor_html(html):
    """Extract title, requirement text, and notes from a minor box HTML."""
    text = strip_html(html)

    # Build a "searchable" version where all whitespace is collapsed to single
    # spaces — this lets us find section markers regardless of word-wrap.
    flat = re.sub(r"\s+", " ", text)

    # --- Title: between "Minor Programme Title" and the next marker ---
    title = ""
    title_start = flat.find("Minor Programme Title")
    if title_start != -1:
        title_start += len("Minor Programme Title")
    req_marker_pos = flat.find("Minor Programme Requirement", title_start)
    if req_marker_pos == -1:
        req_marker_pos = flat.find("Programme Requirement", title_start)

    if title_start != -1 and req_marker_pos != -1:
        title = flat[title_start:req_marker_pos].strip(" :")
    elif title_start != -1:
        title = flat[title_start:].strip(" :")

    # --- Requirement ---
    notes_marker_pos = flat.find("Explanatory Notes", req_marker_pos if req_marker_pos != -1 else 0)
    if req_marker_pos != -1 and notes_marker_pos != -1:
        requirement = flat[req_marker_pos:notes_marker_pos].strip()
    elif notes_marker_pos != -1:
        requirement = flat[:notes_marker_pos].strip()
    else:
        requirement = flat

    # Strip "Minor Programme Requirement" heading prefix
    requirement = re.sub(r"^Minor Programme Requirement\s*:?\s*", "", requirement)

    if title and requirement.lower().startswith(title.lower()):
        requirement = requirement[len(title):].strip(" :")

    # --- Notes ---
    notes = flat[notes_marker_pos:].strip() if notes_marker_pos != -1 else ""
    notes = re.sub(r"^Explanatory Notes\s*:?\s*", "", notes)

    return {
        "title": title,
        "requirement": requirement,
        "notes": notes,
    }


CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f5f5; color: #333; line-height: 1.6; }
.container { max-width: 960px; margin: 0 auto; padding: 20px; }
h1 { font-size: 1.8em; margin-bottom: 0.3em; color: #1a1a1a; }
h2 { font-size: 1.3em; margin: 1.2em 0 0.4em; color: #444; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
.breadcrumb { margin-bottom: 1em; color: #666; font-size: 0.9em; }
.requirement { background: #fff; padding: 15px 20px; border-radius: 8px; white-space: pre-wrap;
               font-size: 0.95em; border: 1px solid #e5e5e5; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
        overflow: hidden; border: 1px solid #e5e5e5; margin-bottom: 20px; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.93em; }
th { background: #fafafa; font-weight: 600; color: #555; }
tr:hover { background: #f9f9f9; }
.not-found { background: #fff8f0; color: #b45309; }
.not-found:hover { background: #fff5eb; }
.card { background: #fff; border-radius: 8px; padding: 12px 20px; margin-bottom: 10px;
        border: 1px solid #e5e5e5; display: flex; justify-content: space-between; align-items: center; }
.card:hover { border-color: #2563eb; }
.card-code { font-weight: 600; color: #2563eb; }
.card-title { color: #666; font-size: 0.9em; }
.meta { color: #888; font-size: 0.85em; }
.search-box { width: 100%; padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px;
              font-size: 1em; margin-bottom: 20px; outline: none; }
.search-box:focus { border-color: #2563eb; }
"""


def html_page(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>"""


def generate():
    if not MINOR_HTML_DIR.exists():
        print(f"Directory not found: {MINOR_HTML_DIR}")
        return

    course_index = load_course_index()

    site_minors_dir = SITE_DIR / "minors"
    site_minors_dir.mkdir(parents=True, exist_ok=True)

    # Track manual-review items
    not_found_codes = set()
    manual_requirements = []

    minor_files = sorted(MINOR_HTML_DIR.glob("*.html"))
    if not minor_files:
        print("No minor HTML files found. Run extract_minor_sections.py first.")
        return

    index_cards = []

    for html_path in minor_files:
        with open(html_path, "r", encoding="utf-8") as f:
            raw_html = f.read()

        parsed = parse_minor_html(raw_html)
        title = parsed["title"]
        requirement = parsed["requirement"]
        notes = parsed["notes"]

        stem = html_path.stem  # e.g. AISTN  or  AISTN_01
        codes, wildcards = extract_course_codes(raw_html)

        # Also extract from the visible text (catches any missed codes)
        visible_text = strip_html(raw_html)
        codes2, wildcards2 = extract_course_codes(visible_text)
        codes = sorted(set(codes + codes2))
        wildcards = sorted(set(wildcards + wildcards2))

        rows_html, table_data = build_course_table(codes, course_index)

        # Record manual review items
        for cd in codes:
            info = course_index.get(cd)
            if not info:
                not_found_codes.add(cd)

        # Identify text-only requirements (no specific course codes found
        # inside the requirement text itself, beyond the wildcards)
        req_codes, _ = extract_course_codes(requirement)
        if (not req_codes and not wildcards and
                re.search(r"\b\d+\s*units\b", requirement, re.IGNORECASE)):
            manual_requirements.append({"file": html_path.name, "text": requirement[:200]})

        # Build the detail page
        body = f"""
<div class="breadcrumb"><a href="../index.html">All Minors</a> &rsaquo; {title or stem}</div>
<h1>{title or stem}</h1>

<h2>Requirement</h2>
<div class="requirement">{requirement}</div>

<h2>Courses</h2>
<table>
<thead><tr><th>Code</th><th>Title</th><th>Units</th><th>Prerequisites</th></tr></thead>
<tbody>
{rows_html or '<tr><td colspan="4">No specific course codes found in requirement.</td></tr>'}
</tbody>
</table>
{('<p class="meta">Wildcard codes: ' + ', '.join(wildcards) + '</p>') if wildcards else ''}

<h2>Explanatory Notes</h2>
<div class="requirement">{notes or 'None'}</div>
"""
        page_html = html_page(f"Minor: {title or stem}", body)

        out_path = site_minors_dir / f"{stem}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_html)

        # Build index card
        n_found = sum(1 for td in table_data if td["found"])
        n_total = len(table_data)
        index_cards.append({
            "stem": stem,
            "title": title or stem,
            "total_courses": n_total,
            "found_courses": n_found,
        })

    # ── Index page ──────────────────────────────────────────────
    cards_html = ""
    for card in index_cards:
        cards_html += f"""<a href="minors/{card['stem']}.html">
<div class="card">
  <div><span class="card-code">{card['title']}</span></div>
  <div class="meta">{card['found_courses']}/{card['total_courses']} courses matched</div>
</div></a>\n"""

    index_body = f"""
<h1>CUHK Minor Programmes</h1>
<p class="meta">{len(index_cards)} minor programmes &middot; Course info from CUHK course catalog</p>

<h2>Minors</h2>
{cards_html}
"""
    index_html = html_page("CUHK Minor Programmes", index_body)
    with open(SITE_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    # ── Manual review report ────────────────────────────────────
    print("\n" + "=" * 60)
    print("MANUAL REVIEW NEEDED")
    print("=" * 60)

    unreviewed = 0

    if not_found_codes:
        unreviewed += len(not_found_codes)
        print(f"\nCourses not found in course_info ({len(not_found_codes)}):")
        for c in sorted(not_found_codes):
            print(f"  {c}")

    if manual_requirements:
        unreviewed += len(manual_requirements)
        print(f"\nText-only requirements to review ({len(manual_requirements)}):")
        for mr in manual_requirements:
            print(f"  {mr['file']}: {mr['text'][:120]}...")

    if unreviewed == 0:
        print("\n  (none)")

    print(f"\nSite generated: site/index.html")

    found_ok = sum(c["found_courses"] for c in index_cards)
    total = sum(c["total_courses"] for c in index_cards)
    print(f"Course matching: {found_ok}/{total} found in course_info")


if __name__ == "__main__":
    generate()

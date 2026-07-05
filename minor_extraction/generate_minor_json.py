import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


MINOR_HTML_DIR = Path(__file__).parent / "minor_html"
COURSE_INFO_DIR = Path(__file__).parent.parent / "course_extraction" / "course_info"
MINOR_JSON_DIR = Path(__file__).parent / "minor_json"
FACULTIES_PATH = MINOR_HTML_DIR / "_faculties.json"


# ── helpers ──────────────────────────────────────────────────────────

def load_course_index():
    """Build ``{ 'DEPT 1234': {title, unit, info} }`` from all JSON files."""
    index = {}
    for json_path in sorted(COURSE_INFO_DIR.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
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
                    "info": entry.get("info", ""),
                }
    return index


def parse_unit_count(text):
    """Return the unit count string from a row, e.g. '6' or '12'."""
    m = re.search(r"(\d+)", str(text))
    return m.group(1) if m else ""


def extract_course_codes(text):
    """Return a sorted list of 'DEPT 1234' codes found in *text*."""
    codes = set()
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z])?", text):
        codes.add(f"{m.group(1)} {m.group(2)}{m.group(3) or ''}")
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z]?)\s*/\s*(\d{4})([A-Za-z]?)", text):
        codes.add(f"{m.group(1)} {m.group(2)}{m.group(3) or ''}")
        codes.add(f"{m.group(1)} {m.group(4)}{m.group(5) or ''}")
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})([A-Za-z]?)\s*,\s+([\d,\s/]+)", text):
        dept = m.group(1)
        codes.add(f"{dept} {m.group(2)}{m.group(3) or ''}")
        tail = m.group(4)
        for nm in re.finditer(r"(\d{4})([A-Za-z]?)\s*(/\s*(\d{4})([A-Za-z]?)\s*)?", tail):
            if nm.group(1):
                codes.add(f"{dept} {nm.group(1)}{nm.group(2) or ''}")
            if nm.group(4):
                codes.add(f"{dept} {nm.group(4)}{nm.group(5) or ''}")
    # "or 1700", "and 2760" after a known department
    for m in re.finditer(r"([A-Z]{4})\s*\d{4}[A-Za-z]?\s+(?:or|and|/)\s+(\d{4})([A-Za-z]?)", text):
        codes.add(f"{m.group(1)} {m.group(2)}{m.group(3) or ''}")
    return sorted(codes)


# ── HTML parsing ─────────────────────────────────────────────────────

def get_minor_title(soup):
    table = soup.find("table")
    if table:
        full_flat = re.sub(r"\s+", " ", table.get_text().replace("\xa0", " "))
        m = re.search(r"Min\s*or\s*Programme\s*Title\s*", full_flat, re.IGNORECASE)
        if m:
            after = full_flat[m.end():].strip()
            title = re.split(
                r"\s*(?:Minor Programme Requirement|Explanatory Notes|Required Course|Elective Course|Units|Total)\b",
                after, maxsplit=1, flags=re.IGNORECASE
            )[0].strip(" :\xa0\n")
            if title:
                return clean_title(title)

    # Fallback: search the full soup text (title may be outside any <table>)
    full_text = re.sub(r"\s+", " ", soup.get_text().replace("\xa0", " "))
    m = re.search(r"Minor\s+Programme\s+Title\s*", full_text, re.IGNORECASE)
    if m:
        after = full_text[m.end():].strip()
        title = re.split(
            r"\s*(?:Minor Programme Requirement|Explanatory Notes|Required Course|Elective Course|Units|Total)\b",
            after, maxsplit=1, flags=re.IGNORECASE
        )[0].strip(" :\xa0\n")
        if title:
            return clean_title(title)

    return fallback_title(soup)


def fallback_title(soup):
    """For handbook minors: title is the first <b> tag's text (e.g. 'Korean')."""
    b_tags = soup.find_all("b")
    for b in b_tags:
        txt = b.get_text(" ", strip=True).replace("\xa0", " ").strip()
        txt = re.sub(r"\s+", " ", txt)
        if not txt:
            continue
        # Filter out section markers, boilerplate, and &nbsp;
        skip_patterns = [
            r"^Minor Programme Title$", r"^Minor Programme Requirement($|\s)",
            r"^&nbsp;$", r"^Total\s*:", r"^Units\s*$",
            r"^Explanatory Note", r"^Required Courses?\s*:?$",
            r"^Elective Courses?\s*:?$", r"^Applicable to students",
            r"^Course Code$", r"^Course Title$", r"^Course List$",
        ]
        if any(re.match(p, txt, re.IGNORECASE) for p in skip_patterns):
            continue
        if len(txt) > 3:
            return clean_title(txt)
    return "Unknown"


def clean_title(title):
    """Strip common boilerplate prefixes from minor titles."""
    title = re.sub(r"^Minor\s+Programme\s+in\s+", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip()


def _find_requirement_rows(soup):
    """Find the innermost <table> containing both 'Minor Programme Requirement'
    and course code patterns.  Returns list of <tr> elements, or []."""
    all_tables = soup.find_all("table")
    candidates = []
    for tbl in all_tables:
        flat = re.sub(r"\s+", " ", tbl.get_text().replace("\xa0", " "))
        if "Minor Programme Requirement" in flat and re.search(r"[A-Z]{4}\s*\d{4}", flat):
            candidates.append(tbl)
    if candidates:
        candidates.sort(key=lambda t: len(t.get_text()))
        return candidates[0].find_all("tr")

    # Fallback: tables with the requirement marker but no course codes
    fallback = []
    for tbl in all_tables:
        flat = re.sub(r"\s+", " ", tbl.get_text().replace("\xa0", " "))
        if "Minor Programme Requirement" in flat:
            fallback.append(tbl)
    if fallback:
        fallback.sort(key=lambda t: len(t.get_text()))
        return fallback[0].find_all("tr")

    # Last resort: scan all trs of the first table after the marker
    outer_table = soup.find("table")
    if outer_table:
        all_rows = outer_table.find_all("tr")
        start = 0
        for i, tr in enumerate(all_rows):
            flat = re.sub(r"\s+", " ", tr.get_text().replace("\xa0", " "))
            if "Minor Programme Requirement" in flat:
                start = i
                break
        return all_rows[start:]
    return []


def _try_split_multi_p_row(tr):
    """If a <tr> has multiple <p> tags in its first column that are sub-point
    labels like (a), (b), etc., split into a list of (index_cell, text_cell,
    units_cell, tr_html) tuples.  Returns None if splitting is not applicable."""
    tds = tr.find_all("td")
    if len(tds) < 2:
        return None

    # Get per-column p-texts
    col_ps = []
    for td in tds:
        ps = td.find_all("p")
        col_ps.append([re.sub(r"\s+", " ", p.get_text().replace("\xa0", " ")).strip() for p in ps])

    first_col = col_ps[0]
    # Need at least 2 p-tags, and at least one should be a sub-point label
    if len(first_col) < 2:
        return None
    label_pattern = re.compile(r"^\([a-z]\)", re.IGNORECASE)
    has_label = any(label_pattern.match(p) for p in first_col if p)
    if not has_label:
        return None

    # Determine how many logical sub-rows we have
    n = max(len(pl) for pl in col_ps)
    sub_rows = []
    for i in range(n):
        idx = col_ps[0][i] if i < len(col_ps[0]) else ""
        # Collect middle column texts
        mid_texts = []
        for j in range(1, len(col_ps)):
            if i < len(col_ps[j]):
                mid_texts.append(col_ps[j][i])
        mid_texts = [t for t in mid_texts if t]
        text_cell = " ".join(mid_texts) if len(col_ps) > 2 else (mid_texts[0] if mid_texts else "")
        unit = col_ps[-1][i] if i < len(col_ps[-1]) else ""
        sub_rows.append((idx, text_cell, unit, str(tr)))

    return sub_rows


def parse_minor_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    title = get_minor_title(soup)

    required = {"label": "", "units": "", "rows": []}
    elective = {"label": "", "units": "", "rows": []}
    description = ""
    notes_html = ""

    rows = _find_requirement_rows(soup)

    if not rows:
        return dict(title=title, description="(No requirement data found.)",
                    required=required, elective=elective, notes_html=notes_html)

    current_section = "init"
    sections = {"req": required, "ele": elective}
    desc_parts = []
    notes_parts = []
    row_index = 0  # sequential counter per section

    for tr in rows:
        # ── Detect multi-p sub-points and split ──
        split_rows = _try_split_multi_p_row(tr)
        sub_rows = split_rows if split_rows else [(None, None, None, str(tr))]

        for sub_idx, sub_text_cell, sub_units, tr_html in sub_rows:
            # If this is a sub-row from _try_split_multi_p_row, use the per-p values
            if split_rows:
                index_cell = sub_idx
                text_cell = sub_text_cell
                units_cell = sub_units
                row_text = tr.get_text(" ", strip=True).replace("\xa0", " ")
                # Reconstruct row_text for the sub-row
                row_text_flat_parts = [p for p in (index_cell, text_cell, units_cell) if p]
                row_text_flat = " ".join(row_text_flat_parts)
            else:
                # Standard cell extraction
                tds_in_row = tr.find_all("td")
                cell_clean = []
                for td in tds_in_row:
                    ct = re.sub(r"\s+", " ", td.get_text().replace("\xa0", " ")).strip()
                    cell_clean.append(ct)

                index_cell = cell_clean[0] if cell_clean else ""
                text_cell = " ".join(cell_clean[1:-1]) if len(cell_clean) >= 3 else (cell_clean[1] if len(cell_clean) == 2 else "")
                units_cell = cell_clean[-1] if len(cell_clean) >= 3 else (cell_clean[1] if len(cell_clean) == 2 and cell_clean[0] and not re.search(r"\d", cell_clean[0]) else "")

                if len(cell_clean) == 2 and re.search(r"\d", cell_clean[0]):
                    text_cell = cell_clean[0]
                    units_cell = cell_clean[1]
                    index_cell = ""
                if len(cell_clean) == 1:
                    text_cell = cell_clean[0]
                    index_cell = ""
                    units_cell = ""

                row_text = tr.get_text(" ", strip=True).replace("\xa0", " ").strip()
                row_text_flat = re.sub(r"\s+", " ", row_text)

            lower = row_text_flat.lower()

            # ── "Explanatory Notes" boundary ──
            if re.match(r"^\s*(?:\d+\.\s*)?explanatory\s+note", lower):
                current_section = "notes"
                notes_parts.append(tr_html)
                continue

            if current_section == "notes":
                notes_parts.append(tr_html)
                continue

            # ── Section marker detection ──
            stripped = re.sub(r"^\d+\.\s*", "", text_cell).strip()
            stripped_lower = stripped.lower()

            if stripped_lower.startswith("required course"):
                current_section = "req"
                row_index = 0
                required["label"] = row_text_flat
                required["units"] = parse_unit_count(units_cell) or parse_unit_count(text_cell)
                codes_in_row = extract_course_codes(text_cell)
                if codes_in_row:
                    display_text = re.sub(r"\s+", " ", text_cell)
                    row_index += 1
                    required["rows"].append({
                        "index": row_index,
                        "text": display_text,
                        "codes": sorted(set(codes_in_row)),
                        "units": required["units"] if len(codes_in_row) == 1 else "",
                    })
                continue

            if stripped_lower.startswith("elective course"):
                current_section = "ele"
                row_index = 0
                elective["label"] = row_text_flat
                elective["units"] = parse_unit_count(units_cell) or parse_unit_count(text_cell)
                codes_in_row = extract_course_codes(text_cell)
                if codes_in_row:
                    display_text = re.sub(r"\s+", " ", text_cell)
                    row_index += 1
                    elective["rows"].append({
                        "index": row_index,
                        "text": display_text,
                        "codes": sorted(set(codes_in_row)),
                        "units": elective["units"] if len(codes_in_row) == 1 else "",
                    })
                continue

            # ── Description rows ──
            if current_section == "init":
                desc_parts.append(text_cell)
                continue

            # ── Course rows ──
            if current_section in ("req", "ele"):
                if not text_cell or re.search(r"\bTotal\s*:", text_cell, re.IGNORECASE):
                    continue

                sec = sections[current_section]
                codes_in_row = extract_course_codes(text_cell)
                row_units = parse_unit_count(units_cell) or ""
                row_index += 1

                display_text = re.sub(r"\s+", " ", text_cell)
                if index_cell and index_cell not in (" ",):
                    display_text = f"{index_cell} {display_text}".strip()

                sec["rows"].append({
                    "index": row_index,
                    "text": display_text,
                    "codes": sorted(set(codes_in_row)),
                    "units": row_units,
                })

    description = " ".join(desc_parts).strip()
    description = re.sub(r"\s+", " ", description)
    description = re.sub(r"Minor Programme Requirement\s*", "", description, flags=re.IGNORECASE).strip()
    description = re.sub(r"Minor Programme Title\s+([\w\s,]+?)\s*(?=Students|$)", "", description, flags=re.IGNORECASE).strip()
    description = re.sub(r"\s+Units\s*$", "", description).strip()
    description = re.sub(r"\s+Total\s*:?\s*\d*\s*$", "", description).strip()
    # Strip extraneous major-programme content that may precede the real description
    m = re.search(r"Students are required to complete\b", description, re.IGNORECASE)
    if m and m.start() > 10:
        description = description[m.start():]

    # Wrap explanatory notes in a table tag if it contains <tr> elements
    notes_html = "\n".join(notes_parts).strip()
    if notes_html:
        if "<tr" in notes_html and not notes_html.strip().startswith("<table"):
            notes_html = "<table>" + notes_html + "</table>"

    # Fallback: notes may be in a separate table or as plain <p> elements
    # outside the requirement rows.  Search the raw HTML for "Explanatory Note"
    # and capture the surrounding block.
    if not notes_html:
        # First, try finding a standalone table whose text starts with the notes header
        for tbl in soup.find_all("table"):
            flat = re.sub(r"\s+", " ", tbl.get_text().replace("\xa0", " ")).strip()
            if re.match(r"^\s*Explanatory\s+Note", flat, re.IGNORECASE):
                tbl_str = str(tbl)
                if "<tr" in tbl_str:
                    notes_html = tbl_str
                    break
        # Second: find the position of "Explanatory Note" in the raw HTML,
        # then extract from the nearest preceding <table> or <p> to the next
        # closing </td> or </table> after the notes content.
        if not notes_html:
            m = re.search(r"Explanatory\s+Note", html_text, re.IGNORECASE)
            if m:
                pos = m.start()
                # Find the last opening tag before the notes
                tag_start = max(
                    html_text.rfind("<table", 0, pos),
                    html_text.rfind("<p ", 0, pos),
                    html_text.rfind("<p>", 0, pos),
                )
                if tag_start >= 0:
                    # Find the closing tag after notes content
                    # Look for </td> or </table> after the notes
                    note_end_td = html_text.find("</td>", pos)
                    note_end_table = html_text.find("</table>", pos)
                    if note_end_td >= 0 and (note_end_table < 0 or note_end_td < note_end_table):
                        tag_end = note_end_td
                    elif note_end_table >= 0:
                        tag_end = note_end_table
                    else:
                        tag_end = len(html_text)
                    raw_block = html_text[tag_start:tag_end].strip()
                    if raw_block:
                        # Wrap each <p> element as a separate <tr><td> so
                        # the site generator's header-stripping only removes
                        # the "Explanatory Notes:" row, not the note content.
                        ps = re.findall(r'<p\b[^>]*>(.*?)</p>', raw_block, re.DOTALL)
                        if ps:
                            trs = "".join(f"<tr><td>{p}</td></tr>" for p in ps)
                            notes_html = f"<table>{trs}</table>"
                        else:
                            notes_html = f"<table><tr><td>{raw_block}</td></tr></table>"

    return dict(title=title, description=description,
                required=required, elective=elective, notes_html=notes_html)


# ── JSON builder ─────────────────────────────────────────────────────

def resolve_courses(codes, course_index):
    """Convert a list of 'DEPT 1234' strings into course objects."""
    return [
        {
            "code": code,
            "title": course_index.get(code, {}).get("title", ""),
            "unit": course_index.get(code, {}).get("unit", ""),
            "prereq": course_index.get(code, {}).get("info", ""),
        }
        for code in codes
    ]


def load_faculties():
    """Return dict mapping minor_html/{stem} -> faculty short name."""
    if not FACULTIES_PATH.exists():
        return {}
    try:
        return json.loads(FACULTIES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_json(html_path, course_index, faculties):
    """Parse one minor HTML file and return a JSON-serialisable dict."""
    stem = html_path.stem
    raw_html = html_path.read_text(encoding="utf-8")
    parsed = parse_minor_html(raw_html)

    def resolve_rows(rows):
        out = []
        for r in rows:
            out.append({
                "index": r["index"],
                "text": r["text"],
                "codes": r["codes"],
                "units": r["units"],
                "courses": resolve_courses(r["codes"], course_index),
            })
        return out

    return {
        "_auto_generated": True,
        "title": parsed["title"],
        "faculty": "Other" if stem.startswith("HB_") else faculties.get(stem, "Unknown"),
        "source_file": stem,
        "description": parsed["description"],
        "required": {
            "label": parsed["required"]["label"],
            "units": parsed["required"]["units"],
            "rows": resolve_rows(parsed["required"]["rows"]),
        },
        "elective": {
            "label": parsed["elective"]["label"],
            "units": parsed["elective"]["units"],
            "rows": resolve_rows(parsed["elective"]["rows"]),
        },
        "explanatory_notes": parsed["notes_html"],
    }


# ── main ─────────────────────────────────────────────────────────────

def generate():
    if not MINOR_HTML_DIR.exists():
        print(f"Directory not found: {MINOR_HTML_DIR}")
        return

    course_index = load_course_index()
    faculties = load_faculties()
    MINOR_JSON_DIR.mkdir(parents=True, exist_ok=True)

    minor_files = sorted(MINOR_HTML_DIR.glob("*.html"))
    if not minor_files:
        print("No minor HTML files found. Run extract_minor_sections.py first.")
        return

    not_found_acc = set()
    skipped = 0
    written = 0

    for html_path in minor_files:
        stem = html_path.stem
        json_path = MINOR_JSON_DIR / f"{stem}.json"

        if json_path.exists():
            try:
                existing = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
            if not existing.get("_auto_generated", True):
                print(f"  Skipping {stem} — manually edited (_auto_generated: false)")
                skipped += 1
                continue

        data = build_json(html_path, course_index, faculties)
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written += 1

        # Track not-found courses
        for sec_name in ("required", "elective"):
            for row in data[sec_name]["rows"]:
                for c in row["courses"]:
                    if not c["title"]:
                        not_found_acc.add(c["code"])

    # ── Report ──
    print("\n" + "=" * 60)
    print(f"JSON files written: {written}")
    if skipped:
        print(f"JSON files skipped (manually edited): {skipped}")
    if not_found_acc:
        print(f"\nCourses not found in course_info ({len(not_found_acc)}):")
        for cd in sorted(not_found_acc):
            print(f"  {cd}")
    else:
        print("\n  (all course codes matched)")

    print(f"\nDone. JSON output: minor_json/")


if __name__ == "__main__":
    generate()

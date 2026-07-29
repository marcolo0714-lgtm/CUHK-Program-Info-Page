import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


MINOR_HTML_DIR = Path(__file__).parent / "minor_html"
MINOR_JSON_DIR = Path(__file__).parent / "minor_json"
FACULTIES_PATH = MINOR_HTML_DIR / "_faculties.json"


# ── helpers ──────────────────────────────────────────────────────────


def parse_unit_count(text):
    """Return the unit count string from a row, e.g. '6' or '12'."""
    m = re.search(r"(\d+)", str(text))
    return m.group(1) if m else ""


def parse_range_units(units_cell, text_cell):
    """Detect range patterns like '3 to 6', '9-11', '9−11', '13 or 14' and return (min, max) or None.
    Checks both the units cell and the text cell. Only accepts numbers ≤ 100
    (actual unit counts, not course-level numbers like '3000')."""
    for source in [units_cell, text_cell]:
        s = str(source)
        m = re.search(r'(\d+)\s*[–\-−to]+\s*(\d+)\s+units?', s, re.IGNORECASE)
        if not m:
            m = re.search(r'(\d+)\s+or\s+(\d+)\s+units?', s, re.IGNORECASE)
        if not m:
            m = re.search(r'(\d+)\s*[–\-−to]+\s*(\d+)', s)
        if not m:
            m = re.search(r'(\d+)\s+or\s+(\d+)', s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= 100 and b <= 100:
                return (str(a), str(b))
    return None


def extract_course_codes(text):
    """Return a list of 'DEPT 1234' codes in text order (deduplicated)."""
    clean = re.sub(r'\[[a-z]\]', '', text)
    clean = re.sub(r'(\d{4})\^', r'\1', clean)
    seen = set()
    codes = []
    def add(code):
        if code not in seen:
            seen.add(code)
            codes.append(code)
    # Scan the text left to right, tracking the current department.
    # Find each candidate (either DEPT+num or implicit num) and add it.
    cur_dept = ""
    for m in re.finditer(r'([A-Z]{4})\s*(\d{4})|(\d{4})', clean):
        if m.group(1):  # explicit DEPT + NUM
            dept = m.group(1)
            num = m.group(2)
            cur_dept = dept
            add(f"{dept} {num}")
        else:  # implicit NUM
            num = m.group(3)
            if cur_dept:
                # Only accept if preceded by comma, slash, or/or in the text
                start = m.start()
                before = clean[max(0, start - 10):start]
                if re.search(r'(?:,|/|or|and)\s*$', before):
                    add(f"{cur_dept} {num}")
    return codes


def _strip_trailing_unit(text):
    """Remove trailing unit counts like ' 4' or ' 12' from text."""
    return re.sub(r'\s+\d{1,2}\s*$', '', text)


def _clean_section_label(text):
    """Remove trailing course codes from a section label so it reads
    cleanly as a heading (e.g. 'Required Courses: CSCI1510 3' →
    'Required Courses:').  Returns (heading, description) where
    description is extra text that belongs in a text box below."""
    text = text.strip()
    # Strip trailing course code lists: "GPAD1020, 1030, 1095 3" etc.
    text = re.sub(
        r'\s*[A-Z]{4}\s*\d{4}'
        r'(?:\s*[,/]\s*(?:[A-Z]{4}\s*)?\d{4})*'
        r'(?:\s+\d{1,2}\s*)?$',
        '', text
    )
    text = text.strip()
    # Remove leading "N. " prefix if present
    heading = re.sub(r'^\d+\.\s*', '', text)
    # Identify the core heading: "Required Courses" or "Elective Courses"
    m = re.match(r'(?i)(required\s+courses?|elective\s+courses?)(?:\s*\[[a-z]\])?\s*:?\s*', heading)
    if not m:
        return text, ""
    prefix = m.group()
    remainder = heading[m.end():].strip()
    # Strip leading footnote refs like "[a]:" or "[b] " — these belong in
    # the heading, not as descriptive text.
    remainder = re.sub(r'^\[[a-z]\](?:\s*:\s*)?\s*', '', remainder).strip()
    # If the remainder is just a unit count (e.g. "3" or "6"), keep it
    # in the heading — it's not descriptive text.
    unit_suffix = ""
    if re.match(r'^\d{1,2}(\s*or\s*\d{1,2})?\s*(?:units?)?$', remainder, re.IGNORECASE):
        unit_suffix = " " + remainder
        if not re.search(r'units?', unit_suffix, re.IGNORECASE):
            unit_suffix += " units"
        remainder = ""
    # Reconstruct heading with original prefix number
    num_prefix = re.match(r'^\d+\.\s*', text)
    num = num_prefix.group(0) if num_prefix else ""
    clean_heading = (num + prefix.strip() + unit_suffix).strip().rstrip(':')
    return clean_heading, remainder


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
                if len(cell_clean) >= 3:
                    # Join middle cells, skipping any that are substrings of a
                    # sibling (handles Cantonese-style duplicate columns).
                    middle = []
                    for i in range(1, len(cell_clean) - 1):
                        c = cell_clean[i]
                        if middle and c and (
                            c in middle[-1] or middle[-1] in c or c in ' '.join(middle)
                        ):
                            continue
                        if c:
                            middle.append(c)
                    text_cell = " ".join(middle)
                    units_cell = cell_clean[-1]
                else:
                    text_cell = cell_clean[1] if len(cell_clean) == 2 else ""
                    units_cell = cell_clean[1] if len(cell_clean) == 2 and cell_clean[0] and not re.search(r"\d", cell_clean[0]) else ""

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
                heading, desc = _clean_section_label(row_text_flat)
                required["label"] = heading
                required["units"] = parse_unit_count(units_cell) or parse_unit_count(text_cell)
                if desc:
                    row_index += 1
                    required["rows"].append({
                        "index": row_index,
                        "text": _strip_trailing_unit(desc),
                        "codes": [],
                        "units": "",
                    })
                codes_in_row = extract_course_codes(text_cell)
                if codes_in_row:
                    display_text = ", ".join(list(dict.fromkeys(codes_in_row)))
                    row_index += 1
                    required["rows"].append({
                        "index": row_index,
                        "text": display_text,
                        "codes": list(dict.fromkeys(codes_in_row)),
                        "units": required["units"] if len(codes_in_row) == 1 else "",
                    })
                continue

            if stripped_lower.startswith("elective course"):
                current_section = "ele"
                row_index = 0
                heading, desc = _clean_section_label(row_text_flat)
                elective["label"] = heading
                elective["units"] = parse_unit_count(units_cell) or parse_unit_count(text_cell)
                if desc:
                    row_index += 1
                    elective["rows"].append({
                        "index": row_index,
                        "text": _strip_trailing_unit(desc),
                        "codes": [],
                        "units": "",
                    })
                codes_in_row = extract_course_codes(text_cell)
                if codes_in_row:
                    display_text = ", ".join(list(dict.fromkeys(codes_in_row)))
                    row_index += 1
                    elective["rows"].append({
                        "index": row_index,
                        "text": display_text,
                        "codes": list(dict.fromkeys(codes_in_row)),
                        "units": elective["units"] if len(codes_in_row) == 1 else "",
                    })
                continue

            # ── Description rows ──
            if current_section == "init":
                desc_parts.append(text_cell)
                continue

            # ── Course rows ──
            if current_section in ("req", "ele"):
                if not text_cell or not text_cell.strip():
                    continue
                # Skip total-unit summary rows
                if re.search(r"\bTotal\s*:", text_cell, re.IGNORECASE) or re.search(r"\bTotal\s*:", row_text_flat, re.IGNORECASE):
                    continue

                sec = sections[current_section]
                codes_in_row = extract_course_codes(text_cell)
                row_units = parse_unit_count(units_cell) or ""
                range_units = parse_range_units(units_cell, text_cell)
                row_index += 1

                display_text = re.sub(r"\s+", " ", text_cell)
                if index_cell and index_cell not in (" ",):
                    display_text = f"{index_cell} {display_text}".strip()
                display_text = _strip_trailing_unit(display_text)

                row_entry = {
                    "index": row_index,
                    "text": display_text,
                    "codes": list(dict.fromkeys(codes_in_row)),
                    "units": row_units,
                }
                if range_units:
                    row_entry["units"] = range_units[0]  # min
                    row_entry["units_max"] = range_units[1]  # max

                sec["rows"].append(row_entry)

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
    # Strip table content that leaked into description (unit headers, course codes).
    # Only match "Units" when followed by a digit (table column, not normal text).
    description = re.sub(
        r'\s+Units\s+\d+.*$|\s+\d+\.\s*Required\s+Course.*$|\s+\d+\.\s*Elective\s+Course.*$',
        '', description, flags=re.IGNORECASE
    )
    description = description.strip()

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

    required["rows"] = _merge_duplicate_rows(required["rows"])
    elective["rows"] = _merge_duplicate_rows(elective["rows"])
    return dict(title=title, description=description,
                required=required, elective=elective, notes_html=notes_html)


def _merge_duplicate_rows(rows):
    """Remove rows whose codes duplicate a prior row, and merge text-only
    rows into adjacent rows (source-HTML split-cell artifacts)."""
    if len(rows) <= 1:
        return rows
    seen_codes = {}  # frozenset(codes) -> text of first row with those codes
    merged = []
    for row in rows:
        codes = row.get("codes", [])
        text = row.get("text", "").strip()
        # Skip rows with identical codes AND identical/similar text
        if codes:
            key = frozenset(codes)
            if key in seen_codes:
                # Only skip if this row's text is a substring of the previous
                # one (true duplicate), not a different row with coincidental codes
                prev_text = seen_codes.get(key, "")
                if not text or text in prev_text or prev_text in text:
                    continue
            seen_codes[key] = text
        # Skip pure spacer rows
        if not text and not codes and not row.get("units", "").strip():
            continue
        merged.append(row)
    # Pass 2: merge text-only rows (no codes) into adjacent rows.
    if len(merged) > 1:
        cleaned = []
        for i, row in enumerate(merged):
            codes = row.get("codes", [])
            text = row.get("text", "").strip()
            if not codes:
                # Check if next row has codes and texts are related
                if i + 1 < len(merged):
                    nr = merged[i + 1]
                    if nr.get("codes") and (text in nr["text"] or nr["text"].strip() in text):
                        continue
                # Check if previous row has codes and this text is in it
                if i > 0 and merged[i - 1].get("codes"):
                    prev_text = merged[i - 1]["text"]
                    if text in prev_text:
                        continue
                # Text-only row with no relation to neighbors → keep it
            cleaned.append(row)
        merged = cleaned
    return merged


# ── equivalent pair detection ──────────────────────────────────────────

def detect_eq_pairs(rows):
    """Return a list of [code1, code2] pairs for /-or-or-connected courses
    across all rows in a section."""
    all_texts = [r["text"] for r in rows if r["text"].strip()]
    if not all_texts:
        return []
    eq_pairs = set()

    def _last_dept(t, pos):
        best = ""
        for dm in re.finditer(r'([A-Z]{4})\s*\d{4}', t):
            if dm.start() < pos:
                best = dm.group(1)
        return best

    for t in all_texts:
        t = re.sub(r'\[[a-z]\]', '', t)
        t = re.sub(r'(\d{4})\^', r'\1', t)
        # Find all code occurrences with departments
        code_positions = []
        for cm in re.finditer(r'([A-Z]{4})\s*(\d{4})\b', t):
            code_positions.append((cm.start(), cm.group(1), cm.group(2)))
        for cm in re.finditer(r'(?<![A-Z])(\d{4})(?![A-Za-z])', t):
            start = cm.start()
            before = t[max(0, start - 10):start]
            if re.search(r'(?:,|/|or)\s*$', before) or re.search(r'\s\s+$', before):
                dept = _last_dept(t, start)
                if dept:
                    code_positions.append((start, dept, cm.group(1)))
        code_positions.sort()

        def _pair(pos_list):
            for pos in pos_list:
                before_code = None
                for cp in reversed(code_positions):
                    if cp[0] < pos:
                        before_code = cp; break
                after_code = None
                for cp in code_positions:
                    if cp[0] > pos:
                        after_code = cp; break
                if before_code and after_code:
                    c1 = f"{before_code[1]} {before_code[2]}"
                    c2 = f"{after_code[1]} {after_code[2]}"
                    eq_pairs.add((c1, c2))

        _pair([sm.start() for sm in re.finditer(r'/(?![/*])', t)])

        # For "or" patterns, create eq_pairs:
        # - Cross-department: always include (e.g. "EPIN1020 or MGNT1070")
        # - Same-department: include unless preceded by a comma
        #   (", or X" = group separator like "KORE2001 and 3000, or 3050";
        #    "X or Y" without comma = inline equivalent like "EDUC2120 or 4110")
        or_positions = [om.start() for om in re.finditer(r'\s+or\s+', t, re.IGNORECASE)]
        for pos in or_positions:
            before_code = None
            for cp in reversed(code_positions):
                if cp[0] < pos:
                    before_code = cp; break
            after_code = None
            for cp in code_positions:
                if cp[0] > pos:
                    after_code = cp; break
            if before_code and after_code:
                dept1, dept2 = before_code[1], after_code[1]
                if dept1 != dept2:
                    # Guard: check for substantive words between "or" and after_code.
                    # If present, this "or" is a choice ("or one course from..."), not equivalence.
                    or_match = re.match(r'\s+or\s+', t[pos:], re.IGNORECASE)
                    or_end = pos + len(or_match.group(0)) if or_match else pos + 3
                    between = t[or_end : after_code[0]].strip()
                    if re.search(r'[a-zA-Z]{3,}', between):
                        continue
                    c1 = f"{dept1} {before_code[2]}"
                    c2 = f"{dept2} {after_code[2]}"
                    eq_pairs.add((c1, c2))
                else:
                    # Same dept: only include if "or" is NOT preceded by a comma
                    before_or = t[max(0, pos - 5):pos].strip()
                    if not before_or.endswith(','):
                        c1 = f"{dept1} {before_code[2]}"
                        c2 = f"{dept2} {after_code[2]}"
                        eq_pairs.add((c1, c2))

    return [[c1, c2] for c1, c2 in sorted(eq_pairs)]


# ── JSON builder ─────────────────────────────────────────────────────


def load_faculties():
    """Return dict mapping minor_html/{stem} -> faculty short name."""
    if not FACULTIES_PATH.exists():
        return {}
    try:
        return json.loads(FACULTIES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_json(html_path, faculties):
    """Parse one minor HTML file and return a JSON-serialisable dict."""
    stem = html_path.stem
    raw_html = html_path.read_text(encoding="utf-8")
    parsed = parse_minor_html(raw_html)

    def _just_codes(rows):
        out = []
        for r in rows:
            entry = {"text": r["text"], "codes": r["codes"], "units": r["units"]}
            if r.get("units_max"):
                entry["units_max"] = r["units_max"]
            out.append(entry)
        return out

    req_rows = _just_codes(parsed["required"]["rows"])
    ele_rows = _just_codes(parsed["elective"]["rows"])
    eq_pairs = detect_eq_pairs(parsed["required"]["rows"] + parsed["elective"]["rows"])

    # Detect range units in section labels (e.g. "13 or 14 units")
    req_units = parsed["required"]["units"]
    ele_units = parsed["elective"]["units"]
    req_units_max = ""
    ele_units_max = ""
    for sec_name in ("required", "elective"):
        sec = parsed[sec_name]
        label = sec.get("label", "")
        range_match = parse_range_units(sec.get("units", ""), label)
        if range_match:
            if sec_name == "required":
                req_units = range_match[0]
                req_units_max = range_match[1]
            else:
                ele_units = range_match[0]
                ele_units_max = range_match[1]

    result = {
        "_auto_generated": True,
        "title": parsed["title"],
        "faculty": "Other" if stem.startswith("HB_") else faculties.get(stem, "Unknown"),
        "source_file": stem,
        "description": parsed["description"],
        "required": {
            "label": parsed["required"]["label"],
            "units": req_units,
            "rows": req_rows,
        },
        "elective": {
            "label": parsed["elective"]["label"],
            "units": ele_units,
            "rows": ele_rows,
        },
        "explanatory_notes": parsed["notes_html"],
        "eq_pairs": eq_pairs,
    }

    if req_units_max:
        result["required"]["units_max"] = req_units_max
    if ele_units_max:
        result["elective"]["units_max"] = ele_units_max

    # If exactly one section exists, use description's total_units as section units
    desc = parsed.get("description", "")
    total_m = re.search(r'minimum\s+of\s+(\d+)\s+units?', desc, re.IGNORECASE)
    if total_m:
        total_units = total_m.group(1)
        has_req = parsed["required"].get("label") and parsed["required"].get("rows")
        has_ele = parsed["elective"].get("label") and parsed["elective"].get("rows")
        if has_req and not has_ele:
            result["required"]["units"] = total_units
        elif has_ele and not has_req:
            result["elective"]["units"] = total_units

    return result


# ── main ─────────────────────────────────────────────────────────────

def generate():
    if not MINOR_HTML_DIR.exists():
        print(f"Directory not found: {MINOR_HTML_DIR}")
        return

    faculties = load_faculties()
    MINOR_JSON_DIR.mkdir(parents=True, exist_ok=True)

    minor_files = sorted(MINOR_HTML_DIR.glob("*.html"))
    if not minor_files:
        print("No minor HTML files found. Run extract_minor_sections.py first.")
        return

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

        data = build_json(html_path, faculties)
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written += 1

    # ── Report ──
    print("\n" + "=" * 60)
    print(f"JSON files written: {written}")
    if skipped:
        print(f"JSON files skipped (manually edited): {skipped}")

    print(f"\nDone. JSON output: minor_json/")


if __name__ == "__main__":
    generate()

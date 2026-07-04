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
    return sorted(codes)


# ── HTML parsing ─────────────────────────────────────────────────────

def get_minor_title(soup):
    table = soup.find("table")
    if not table:
        return fallback_title(soup)
    full_flat = re.sub(r"\s+", " ", table.get_text().replace("\xa0", " "))
    m = re.search(r"Min\s*or\s*Programme\s*Title\s*", full_flat, re.IGNORECASE)
    if not m:
        return fallback_title(soup)
    after = full_flat[m.end():].strip()
    title = re.split(
        r"\s*(?:Minor Programme Requirement|Explanatory Notes|Required Course|Elective Course|Units|Total)\b",
        after, maxsplit=1, flags=re.IGNORECASE
    )[0].strip(" :\xa0\n")
    if not title:
        return fallback_title(soup)
    return clean_title(title)


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


def parse_minor_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    title = get_minor_title(soup)

    required = {"label": "", "description": "", "codes": [], "units": ""}
    elective = {"label": "", "description": "", "codes": [], "units": ""}
    description = ""
    notes_html = ""

    rows = []
    all_tables = soup.find_all("table")
    candidate_tables = []
    for tbl in all_tables:
        flat = re.sub(r"\s+", " ", tbl.get_text().replace("\xa0", " "))
        if "Minor Programme Requirement" in flat:
            candidate_tables.append(tbl)
    if candidate_tables:
        candidate_tables.sort(key=lambda t: len(t.get_text()))
        inner_table = None
        for tbl in candidate_tables:
            rows = tbl.find_all("tr")
            tbl_text = re.sub(r"\s+", " ", tbl.get_text())
            if re.search(r"[A-Z]{4}\s*\d{4}", tbl_text):
                inner_table = tbl
                break
        if not inner_table:
            inner_table = candidate_tables[0]
            rows = inner_table.find_all("tr")
    if not rows:
        outer_table = soup.find("table")
        if outer_table:
            all_rows = outer_table.find_all("tr")
            start = 0
            for i, tr in enumerate(all_rows):
                flat = re.sub(r"\s+", " ", tr.get_text().replace("\xa0", " "))
                if "Minor Programme Requirement" in flat:
                    start = i
                    break
            rows = all_rows[start:]

    if not rows:
        return dict(title=title, description="(No requirement data found.)",
                    required=required, elective=elective, notes_html=notes_html)

    current_section = "init"
    sections = {"req": required, "ele": elective}
    desc_parts = []
    notes_parts = []

    for tr in rows:
        tds_in_row = tr.find_all("td")
        row_text = tr.get_text(" ", strip=True).replace("\xa0", " ").strip()
        row_text_flat = re.sub(r"\s+", " ", row_text)
        lower = row_text_flat.lower()

        if "explanatory note" in lower:
            current_section = "notes"
            notes_parts.append(str(tr))
            continue

        if current_section == "notes":
            notes_parts.append(str(tr))
            continue

        stripped = re.sub(r"^\d+\.\s*", "", row_text_flat).strip()
        stripped_lower = stripped.lower()

        if stripped_lower.startswith("required course"):
            current_section = "req"
            required["label"] = row_text_flat
            required["codes"].extend(extract_course_codes(row_text_flat))
            if len(tds_in_row) >= 3:
                required["units"] = parse_unit_count(tds_in_row[-1].get_text())
            continue

        if stripped_lower.startswith("elective course"):
            current_section = "ele"
            elective["label"] = row_text_flat
            elective["codes"].extend(extract_course_codes(row_text_flat))
            if len(tds_in_row) >= 3:
                elective["units"] = parse_unit_count(tds_in_row[-1].get_text())
            continue

        if current_section == "init":
            desc_parts.append(row_text)
            continue

        if current_section in ("req", "ele"):
            sec = sections[current_section]
            codes_in_row = extract_course_codes(row_text)
            if codes_in_row:
                sec["codes"].extend(codes_in_row)
            elif row_text and not re.search(r"\bTotal\s*:", row_text, re.IGNORECASE):
                sec["description"] = (sec["description"] + " " + row_text).strip()

    description = " ".join(desc_parts).strip()
    description = re.sub(r"\s+", " ", description)
    description = re.sub(r"Minor Programme Requirement\s*", "", description, flags=re.IGNORECASE).strip()
    description = re.sub(r"Minor Programme Title\s+([\w\s,]+?)\s*(?=Students|$)", "", description, flags=re.IGNORECASE).strip()
    description = re.sub(r"\s+Units\s*$", "", description).strip()
    description = re.sub(r"\s+Total\s*:?\s*\d*\s*$", "", description).strip()

    required["codes"] = sorted(set(required["codes"]))
    elective["codes"] = sorted(set(elective["codes"]))
    notes_html = "\n".join(notes_parts).strip()

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

    return {
        "_auto_generated": True,
        "title": parsed["title"],
        "faculty": "Other" if stem.startswith("HB_") else faculties.get(stem, "Unknown"),
        "source_file": stem,
        "description": parsed["description"],
        "required": {
            "label": parsed["required"]["label"],
            "description": parsed["required"]["description"],
            "units": parsed["required"]["units"],
            "courses": resolve_courses(parsed["required"]["codes"], course_index),
        },
        "elective": {
            "label": parsed["elective"]["label"],
            "description": parsed["elective"]["description"],
            "units": parsed["elective"]["units"],
            "courses": resolve_courses(parsed["elective"]["codes"], course_index),
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
            for c in data[sec_name]["courses"]:
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

    total_req = sum(len(data["required"]["courses"]) for html_path in minor_files
                    if (MINOR_JSON_DIR / f"{html_path.stem}.json").exists()
                    for data in [json.loads((MINOR_JSON_DIR / f"{html_path.stem}.json").read_text(encoding="utf-8"))])
    print(f"\nDone. JSON output: minor_json/")


if __name__ == "__main__":
    generate()

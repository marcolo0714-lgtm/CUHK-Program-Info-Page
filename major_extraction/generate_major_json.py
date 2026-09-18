"""Parse saved CUHK major programme pages into section-preserving JSON."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent

try:
    from .major_readability import improve_readability
except ImportError:
    from major_readability import improve_readability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2026_27")
    return parser.parse_args()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def normalize_source_text(value: str) -> str:
    """Repair harmless word splits introduced by the catalogue's Word HTML."""
    text = clean_text(value)
    return re.sub(r"\bM\s+ajor\b", "Major", text, flags=re.IGNORECASE)


def expose_web_links(root: Tag) -> None:
    """Keep links whose source pages use labels such as “website” or “here”."""
    for anchor in root.select("a[href]"):
        href = clean_text(anchor.get("href", ""))
        if not re.match(r"https?://", href, re.I):
            continue
        visible = clean_text(anchor.get_text(" ", strip=True))
        comparable = re.sub(r"^https?://", "", href, flags=re.I).rstrip("/").lower()
        if comparable and comparable not in visible.rstrip("/").lower():
            anchor.append(f" ({href})")


def extract_course_codes(text: str) -> list[str]:
    """Resolve explicit and abbreviated codes in source order."""
    clean = re.sub(r"\[[a-z]\]", "", text, flags=re.IGNORECASE)
    clean = re.sub(r"(\d{4})[\^#]", r"\1", clean)
    clean = re.sub(r"\b([A-Z]{4})\s*,\s*(?=\d{4})", r"\1", clean)
    clean = re.sub(r"\b([A-Z])\s*([A-Z])\s*([A-Z])\s*([A-Z])\s*(\d{4})", r"\1\2\3\4\5", clean)
    seen: set[str] = set()
    codes: list[str] = []
    current_department = ""
    for match in re.finditer(r"([A-Z]{4})\s*(\d{4})|(\d{4})", clean):
        if match.group(1):
            current_department = match.group(1)
            code = f"{current_department} {match.group(2)}"
        else:
            if not current_department:
                continue
            # A parenthesized “or DEPT…” alternative is temporary. Once it
            # closes, subsequent abbreviated numbers resume the outer list's
            # department (for example BIOL ... (or FNSC...), 3710, 4120).
            prefix = clean[:match.start()]
            opening = prefix.rfind("(")
            if opening >= 0 and re.match(r"\(\s*or\s+[A-Z]{4}\s*\d{4}", prefix[opening:], re.I) \
                    and re.search(r"\)\s*,?\s*$", prefix[opening:]):
                outer_codes = re.findall(r"\b([A-Z]{4})\s*\d{4}", prefix[:opening])
                if outer_codes:
                    current_department = outer_codes[-1]
            if re.match(r"\s*(?:(?:or|and)\s+above\s+)?level\b", clean[match.end():], re.IGNORECASE):
                continue
            before = clean[max(0, match.start() - 12):match.start()]
            if not re.search(r"(?:,|/|\bor\b|\band\b)\s*$", before, re.IGNORECASE):
                continue
            code = f"{current_department} {match.group(3)}"
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def expected_subjects(admission_code: str) -> list[str]:
    first = admission_code.split("_", 1)[0]
    first = re.sub(r"[NX]$", "", first)
    return [first[:4]] if len(first) >= 4 else []


def choose_requirement_table(soup: BeautifulSoup, admission_code: str) -> Tag:
    candidates: list[tuple[int, Tag, str]] = []
    for position, table in enumerate(soup.find_all("table")):
        text = normalize_source_text(table.get_text(" ", strip=True))
        if "Major Programme Requirement" in text and re.search(r"[A-Z]{4}\s*\d{4}", text):
            candidates.append((position, table, text))
    if not candidates:
        # MBChB publishes its numbered requirement table beside, rather than
        # inside, the prose headed “Medicine Programme (MBChB)”.
        medicine_tables = [
            table for position, table in enumerate(soup.find_all("table"))
            if not table.find("table")
            and "Faculty Package" in normalize_source_text(table.get_text(" ", strip=True))
            and "Required Courses" in normalize_source_text(table.get_text(" ", strip=True))
            and re.search(r"[A-Z]{4}\s*\d{4}", normalize_source_text(table.get_text(" ", strip=True)))
        ]
        if medicine_tables:
            return medicine_tables[0]
        raise ValueError("No major requirement table found")

    # Container tables repeat the text of every nested scheme. Work only with
    # innermost requirement tables so later double-major or senior-entry boxes
    # cannot outweigh the first standard programme box by containing more codes.
    candidate_ids = {id(table) for _, table, _ in candidates}
    innermost = [
        item for item in candidates
        if not any(id(descendant) in candidate_ids for descendant in item[1].find_all("table"))
    ]
    if innermost:
        candidates = innermost

    non_senior = [
        item for item in candidates
        if "senior-year places" not in item[2][:350].lower()
    ]
    if non_senior:
        candidates = non_senior

    # Prefer a normal requirement box over recommended patterns and degree-two
    # boxes, while retaining those variants when they are the only publication.
    standard = [
        item for item in candidates
        if re.match(r"Major Programme Requirement(?!\s+of\b)", item[2], re.IGNORECASE)
    ]
    if standard:
        candidates = standard
    without_course_pattern = [
        item for item in candidates if "Recommended Course Pattern" not in item[2]
    ]
    if without_course_pattern:
        candidates = without_course_pattern

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def direct_rows(table: Tag) -> list[Tag]:
    body = table.find("tbody", recursive=False) or table
    return body.find_all("tr", recursive=False)


def row_cells(row: Tag) -> list[str]:
    # Inline formatting fragments often split a single word or sentence.
    return [clean_text(cell.get_text("", strip=False)) for cell in row.find_all("td", recursive=False)]


MARKER_PATTERN = re.compile(
    r"(?:\d+\.?|\([a-z]\)|\([ivxlcdm]+\)|\(\d+\)|[ivxlcdm]+\)|[a-z]\)|\[[^]]+\]|[*^#@]+)",
    re.IGNORECASE,
)


def cell_blocks(cell: Tag) -> list[str]:
    blocks = [
        clean_text(block.get_text(" ", strip=False))
        for block in cell.find_all(["p", "div"], recursive=False)
    ]
    return [block for block in blocks if block]


def logical_row_cells(row: Tag) -> list[list[str]]:
    """Unmerge parallel Word-HTML paragraphs that represent separate rows."""
    cells = row.find_all("td", recursive=False)
    if not cells:
        return []
    block_columns = [cell_blocks(cell) for cell in cells]
    marker_index = next((
        index for index, blocks in enumerate(block_columns)
        if len(blocks) >= 2 and all(
            MARKER_PATTERN.fullmatch(re.sub(r"\s+", "", marker)) for marker in blocks
        )
    ), None)
    if marker_index is None:
        return [row_cells(row)]
    markers = block_columns[marker_index]
    if not any(len(blocks) == len(markers) for blocks in block_columns[marker_index + 1:]):
        return [row_cells(row)]

    logical: list[list[str]] = []
    for position in range(len(markers)):
        values = []
        for blocks in block_columns:
            if len(blocks) == len(markers):
                values.append(blocks[position])
            elif len(blocks) == 1:
                values.append(blocks[0] if position == 0 else "")
            else:
                values.append("")
        logical.append(values)
    return logical


def parse_unit_cell(text: str) -> str | None:
    """Return a displayable unit value, or None when the cell is prose."""
    value = clean_text(text)
    value = re.sub(r"\[[a-z]\d*\]", "", value, flags=re.IGNORECASE).strip()
    if value in {"---", "–", "—"}:
        return ""
    number = r"\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?"
    if re.fullmatch(rf"{number}\s*\((?:with|without)\s+[^)]+\)", value, re.IGNORECASE):
        return value
    if re.fullmatch(rf"{number}(?:\s+or\s+{number})?(?:\s+{number})*", value, re.IGNORECASE):
        return value
    return None


def looks_like_units(text: str) -> bool:
    return parse_unit_cell(text) is not None


def split_inline_roman_items(body: str, units: str) -> tuple[str, list[dict[str, object]]]:
    matches = list(re.finditer(r"\(([ivxlcdm]+)\)", body, re.IGNORECASE))
    if len(matches) < 2:
        return body, []
    prefix = body[:matches[0].start()].rstrip(" :;-–—")
    unit_values = re.findall(r"\d+(?:\.\d+)?", units)
    children = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        item_text = body[match.end():end].strip(" ,;:–—-")
        if not item_text or item_text.lower() == "or":
            return body, []
        children.append({
            "marker": f"({match.group(1).lower()})",
            "title": concise_heading(item_text),
            "units": unit_values[index] if len(unit_values) == len(matches) else "",
            "text": [],
            "codes": extract_course_codes(item_text),
            "subsections": [],
        })
    if not any(child["codes"] for child in children):
        return body, []
    return prefix, children


def split_block_heading(row: Tag, marker: str, body: str) -> tuple[str, str]:
    """Keep a Word-HTML label separate from the course list below it.

    The catalogue frequently stores a label and its list as two paragraphs in
    one cell. Treating their concatenation as a heading makes long course codes
    appear twice: once in the heading and again in the injected table.
    """
    first_cell_blocks = cell_blocks(row.find_all("td", recursive=False)[0])
    if len(first_cell_blocks) > 1 and all(
        MARKER_PATTERN.fullmatch(re.sub(r"\s+", "", block)) for block in first_cell_blocks
    ):
        return "", body
    for cell in row.find_all("td", recursive=False):
        blocks = cell_blocks(cell)
        if len(blocks) < 2:
            continue
        heading = blocks[0].rstrip(" :")
        remainder = clean_text(" ".join(blocks[1:]))
        if heading and not extract_course_codes(heading) and extract_course_codes(remainder):
            combined = clean_text(f"{heading} {remainder}")
            if combined == body:
                return heading, remainder
    return "", body


def subsection_heading(text: str, codes: list[str], bold: bool) -> bool:
    lower = text.lower()
    if lower.startswith(("required courses", "elective courses", "elective course")):
        return True
    if "stream" in lower and not codes:
        return True
    if bold and not codes and len(text) < 180 and not lower.startswith(("choose ", "remaining units")):
        return True
    return not codes and text.endswith(":") and len(text) < 160


def concise_heading(text: str) -> str:
    first_code = re.search(r"\b[A-Z]{4}\s*\d{4}\b", text)
    if first_code:
        prefix = text[:first_code.start()].rstrip(" :,;-")
        if prefix and (":" in text[:first_code.start()] or prefix.lower().startswith(("required courses", "elective courses", "elective course"))):
            return prefix
    return text.rstrip(":")


def heading_remainder(text: str, heading: str) -> str:
    """Return the course-list portion without repeating its heading label."""
    if heading and text.lower().startswith(heading.lower()):
        return text[len(heading):].lstrip(" :;-–—")
    return text


def parse_recommended_course_pattern(table: Tag) -> list[dict[str, object]]:
    """Create readable period sections for programmes published only as a pattern."""
    sections: list[dict[str, object]] = []
    current_year = ""
    current_term = ""
    current_section: dict[str, object] | None = None

    for row in direct_rows(table):
        cells = [cell for cell in row_cells(row) if cell]
        if not cells:
            continue
        combined = clean_text(" ".join(cells))
        year_match = re.search(r"(?:First|Second|Third|Fourth|Fifth|Sixth) Year of Attendance", combined, re.IGNORECASE)
        term_match = re.search(r"[12](?:st|nd) term", combined, re.IGNORECASE)
        if year_match:
            current_year = year_match.group(0)
            current_term = term_match.group(0) if term_match else ""
            current_section = None
        elif term_match and len(cells) <= 3:
            current_term = term_match.group(0)
            current_section = None

        codes = extract_course_codes(combined)
        if not codes:
            continue
        title = " — ".join(part for part in (current_year, current_term) if part) or "Programme Courses"
        if current_section is None or current_section["title"] != title:
            current_section = {
                "marker": f"{len(sections) + 1}.",
                "title": title,
                "units": "",
                "text": [],
                "codes": [],
                "subsections": [],
            }
            sections.append(current_section)
        current_section["text"].append(combined)
        for code in codes:
            if code not in current_section["codes"]:
                current_section["codes"].append(code)
    return sections


def parse_flat_requirement_text(table: Tag) -> list[dict[str, object]]:
    """Recover numbered requirements embedded in one large source-table cell."""
    text = clean_text(table.get_text(" ", strip=True))
    sections: list[dict[str, object]] = []
    pattern = re.compile(
        r"(?:^|\s)(\d+)\.\s+([^:]{2,120}):\s*(\d+(?:\s*(?:-|–|to)\s*\d+)?)?\s*(.*?)"
        r"(?=(?:\s+\d+\.\s+[^:]{2,120}:)|(?:\s+Total\s*:)|$)",
        re.IGNORECASE,
    )
    for marker, title, units, body in pattern.findall(text):
        clean_body = clean_text(body)
        sections.append({
            "marker": f"{marker}.",
            "title": clean_text(title),
            "units": clean_text(units),
            "text": [clean_body] if clean_body else [],
            "codes": extract_course_codes(clean_body),
            "subsections": [],
        })
    return sections


def parse_flat_explanatory_notes(table: Tag) -> list[dict[str, object]]:
    """Recover notes from catalogue pages collapsed into one outer table cell."""
    text = clean_text(table.get_text(" ", strip=True))
    match = re.search(r"Explanatory Notes?\s*:\s*(.*)", text, re.IGNORECASE)
    if not match:
        return []
    notes_text = re.split(r"\b(?:Recommended Course Pattern|Minor Programme)\b", match.group(1), maxsplit=1)[0]
    markers = list(re.finditer(r"(?:^|\s)(\d+\.|\[[a-z]\])\s+", notes_text, re.IGNORECASE))
    notes = []
    for position, marker in enumerate(markers):
        end = markers[position + 1].start() if position + 1 < len(markers) else len(notes_text)
        body = clean_text(notes_text[marker.end():end])
        if body:
            notes.append({"marker": marker.group(1), "text": body, "subsections": [], "rows": []})
    return notes


def parse_programme(record: dict[str, str], full_path: Path, requirement_table: Tag | None = None) -> dict[str, object]:
    soup = BeautifulSoup(full_path.read_text(encoding="utf-8"), "html.parser")
    table = requirement_table if requirement_table is not None else choose_requirement_table(soup, record["admission_code"])
    expose_web_links(table)
    description: list[str] = []
    sections: list[dict[str, object]] = []
    notes: list[dict[str, str]] = []
    supplementary: list[str] = []
    current_section: dict[str, object] | None = None
    current_subsection: dict[str, object] | None = None
    current_nested: dict[str, object] | None = None
    current_level3: dict[str, object] | None = None
    current_leaf: dict[str, object] | None = None
    started = False
    notes_mode = False
    current_note: dict[str, object] | None = None
    current_note_group: dict[str, object] | None = None
    note_context = ""
    after_total = False
    total_units = ""

    source_rows = [
        (row, cells)
        for row in direct_rows(table)
        for cells in logical_row_cells(row)
    ]
    for row, cells in source_rows:
        if not cells or not any(cells):
            continue
        flat = normalize_source_text(" ".join(cell for cell in cells if cell))
        flat = re.sub(r"^Major Programme Requirement(?:\s*\([^)]*\))?\s*", "", flat, flags=re.IGNORECASE)
        if not flat or flat == "Units":
            continue
        note_heading = re.search(r"\bExplanatory Notes?\s*:\s*", flat, re.IGNORECASE)
        if note_heading:
            prefix = clean_text(flat[:note_heading.start()])
            notes_mode = True
            current_note = None
            current_note_group = None
            note_context = ""
            current_section = None
            current_subsection = None
            current_nested = None
            current_level3 = None
            current_leaf = None
            # Some catalogue tables put a symbol footnote immediately before
            # the Explanatory Notes label in the same physical row.
            symbol_note = re.match(r"^([*^#@]+)\s*(.+)$", prefix)
            if symbol_note:
                current_note = {"marker": symbol_note.group(1), "text": symbol_note.group(2), "subsections": [], "rows": []}
                notes.append(current_note)
            continue

        nonempty = [cell for cell in cells if cell]
        compact_first = re.sub(r"\s+", "", nonempty[0]) if nonempty else ""
        marker = compact_first if MARKER_PATTERN.fullmatch(compact_first) else ""
        row_title_hint = ""
        if not marker and nonempty:
            leading_marker = re.match(
                r"^(\([a-z]\)|\([ivxlcdm]+\)|\(\d+\)|[ivxlcdm]+\)|[a-z]\))\s+(.+)$",
                nonempty[0],
                re.IGNORECASE,
            )
            if leading_marker:
                marker = re.sub(r"\s+", "", leading_marker.group(1))
                row_title_hint = clean_text(leading_marker.group(2))
                nonempty[0] = row_title_hint
        parenthesized_roman = bool(re.fullmatch(r"\([ivxlcdm]+\)", marker, re.IGNORECASE))
        parenthesized_numeric = bool(re.fullmatch(r"\(\d+\)", marker))
        bare_letter_marker = bool(re.fullmatch(r"[a-h]\)", marker, re.IGNORECASE))
        if bare_letter_marker:
            marker = f"({marker[0].lower()})"
        body_cells = nonempty[:] if row_title_hint else (nonempty[1:] if marker else nonempty[:])
        units = ""
        if len(body_cells) > 1:
            parsed_units = parse_unit_cell(body_cells[-1])
            if parsed_units is not None:
                units = parsed_units
                body_cells.pop()
        body = clean_text(" ".join(body_cells))
        if not body:
            continue
        codes = extract_course_codes(body)
        block_heading, block_remainder = split_block_heading(row, marker, body)
        bold = bool(row.find(["b", "strong"]))
        numeric_marker = bool(re.fullmatch(r"\d+\.?", marker))

        if re.search(r"\bTotal\s*:", body, re.IGNORECASE):
            if after_total:
                supplementary.append(flat)
                continue
            unit_match = re.search(r"(\d+(?:\s*(?:-|–|to)\s*\d+)?)", body)
            total_units = units or (unit_match.group(1) if unit_match else "")
            current_section = None
            current_subsection = None
            current_nested = None
            current_level3 = None
            current_leaf = None
            after_total = True
            continue
        if not started and not after_total and body.lower().startswith("students are required to complete"):
            description.append(body)
            continue
        if notes_mode or marker.startswith("[") or bool(re.fullmatch(r"[*^#@]+", marker)):
            notes_mode = True
            note_marker = marker if marker.startswith("[") or numeric_marker or re.fullmatch(r"[*^#@]+", marker) else ""
            if note_marker:
                current_note = {
                    "marker": note_marker,
                    "text": body,
                    "subsections": [],
                    "rows": [],
                }
                notes.append(current_note)
                current_note_group = None
                note_context = ""
            elif current_note is None:
                current_note = {"marker": "", "text": body, "subsections": [], "rows": []}
                notes.append(current_note)
            elif parenthesized_roman or bool(re.fullmatch(r"[ivxlcdm]+\)", marker, re.IGNORECASE)):
                group = {
                    "marker": marker if marker.startswith("(") else f"({marker[:-1].lower()})",
                    "title": block_heading or concise_heading(body),
                    "units": units,
                    "text": [block_remainder] if block_heading and not codes else [],
                    "codes": codes,
                    "subsections": [],
                    "force_course_table": "concentration" in note_context.lower(),
                }
                current_note["subsections"].append(group)
                current_note_group = group
            elif len(nonempty) >= 2 and not marker:
                current_note["rows"].append(nonempty)
            elif not codes and body.endswith(":") and len(body) < 180:
                group = {
                    "marker": "",
                    "title": body.rstrip(":"),
                    "units": units,
                    "text": [],
                    "codes": [],
                    "subsections": [],
                    "note_heading": True,
                }
                current_note["subsections"].append(group)
                current_note_group = group
                note_context = body
            elif current_note_group is not None:
                if codes:
                    for code in codes:
                        if code not in current_note_group["codes"]:
                            current_note_group["codes"].append(code)
                else:
                    current_note_group["text"].append(body)
            else:
                # Adjacent source rows may split a sentence. Do not inject a
                # separator that was absent from the catalogue source.
                current_note["text"] += clean_text(f"{marker} {body}") if marker else body
            continue
        if after_total:
            supplementary.append(clean_text(f"{marker} {body}") if marker else body)
            continue

        child_marker = bool(re.fullmatch(r"\([a-z]\)", marker, re.IGNORECASE))
        roman_marker = bool(re.fullmatch(r"[ivxlcdm]+\)", marker, re.IGNORECASE))
        leftover = clean_text(re.sub(r"[A-Z]{4}\s*\d{4}|\d{4}|\[[a-z]\]|[,/;#^]", "", body, flags=re.IGNORECASE)).lower().strip("()[] ")
        pure_code_row = bool(codes) and leftover in {"", "or", "and"}

        if not started and not numeric_marker:
            description.append(body)
            continue
        if numeric_marker:
            started = True
            current_subsection = None
            current_nested = None
            current_level3 = None
            current_leaf = None
            title = block_heading or concise_heading(body)
            remainder = block_remainder if block_heading else heading_remainder(body, title)
            section_label = re.match(
                r"^((?:Faculty Package|Required Courses|Elective Courses)(?:\[[^]]+\])?(?:\s*\([^:]+\))?)\s*:\s*(.+)$",
                body,
                re.IGNORECASE,
            )
            if section_label:
                title = clean_text(section_label.group(1))
                remainder = clean_text(section_label.group(2))
            current_section = {
                "marker": marker,
                "title": title,
                "units": units,
                "text": [remainder] if codes and remainder else [],
                "codes": codes,
                "subsections": [],
            }
            sections.append(current_section)
            continue

        started = True
        if current_section is None:
            description.append(clean_text(f"{marker} {body}") if marker else body)
            continue

        is_subheading = child_marker or roman_marker or parenthesized_roman or parenthesized_numeric or bool(block_heading) or subsection_heading(body, codes, bold)
        if is_subheading:
            inline_title, inline_children = split_inline_roman_items(body, units) if child_marker else (body, [])
            title = row_title_hint or block_heading or concise_heading(inline_title)
            if not inline_children and (pure_code_row or (codes and re.match(r"[A-Z]{4}\s*\d{4}", body))):
                title = ""
            remainder = "" if inline_children else (block_remainder if block_heading else heading_remainder(body, title))
            group = {
                "marker": marker,
                "title": title,
                "units": "" if inline_children and len(re.findall(r"\d+(?:\.\d+)?", units)) > 1 else units,
                "text": [remainder] if codes and remainder else [],
                "codes": [] if inline_children else codes,
                "subsections": inline_children,
            }
            lower = body.lower()
            current_marker = str(current_subsection.get("marker", "")) if current_subsection else ""
            sequential_letter = bool(
                child_marker
                and current_subsection
                and re.fullmatch(r"\([a-z]\)", current_marker, re.IGNORECASE)
                and ord(marker[1].lower()) == ord(current_marker[1].lower()) + 1
            )

            if (parenthesized_roman or parenthesized_numeric) and (current_nested or current_subsection) is not None and not sequential_letter:
                parent = current_nested or current_subsection
                parent["subsections"].append(group)
                current_level3 = group
                current_leaf = None
            elif (bare_letter_marker or roman_marker) and current_subsection is not None:
                current_subsection["subsections"].append(group)
                current_nested = group
                current_level3 = None
                current_leaf = None
            elif not marker and lower.startswith(("required courses", "elective courses", "elective course")) and current_subsection is not None:
                current_subsection["subsections"].append(group)
                current_nested = group
                current_level3 = None
                current_leaf = None
            elif not marker and lower.startswith(("choose ", "remaining units")) and (current_nested or current_subsection):
                parent = current_nested or current_subsection
                parent["subsections"].append(group)
                current_level3 = group
                current_leaf = None
            elif not marker and re.fullmatch(r"group\s+[a-z]:?", body, re.IGNORECASE) and (current_nested or current_subsection):
                parent = current_nested or current_subsection
                parent["subsections"].append(group)
                current_level3 = group
                current_leaf = None
            elif not marker and lower.startswith(("courses offered", "course offered", "students can also")) and (current_level3 or current_nested or current_subsection):
                parent = current_level3 or current_nested or current_subsection
                parent["subsections"].append(group)
                current_leaf = group
            elif not marker and block_heading and current_level3 is not None:
                current_level3["subsections"].append(group)
                current_leaf = group
            elif (
                not marker
                and block_heading
                and current_subsection is not None
                and re.fullmatch(r"\([a-z]\)|[ivxlcdm]+\)", str(current_subsection.get("marker", "")), re.IGNORECASE)
                and "(b)" not in str(current_subsection.get("title", ""))
            ):
                current_subsection["subsections"].append(group)
                current_nested = group
                current_level3 = None
                current_leaf = None
            else:
                current_section["subsections"].append(group)
                current_subsection = group
                current_nested = None
                current_level3 = None
                current_leaf = None
            continue

        target = current_leaf or current_level3 or current_nested or current_subsection or current_section
        text = clean_text(f"{marker} {body}") if marker else body
        target["text"].append(text)
        for code in codes:
            if code not in target["codes"]:
                target["codes"].append(code)
        if units and not target["units"]:
            target["units"] = units

    if not sections and "Recommended Course Pattern" in clean_text(table.get_text(" ", strip=True)):
        sections = parse_recommended_course_pattern(table)
        if sections:
            description = [
                "The official programme information presents these requirements as a recommended course pattern."
            ]
    if not sections:
        sections = parse_flat_requirement_text(table)
        if sections:
            description = [
                "Students are required to complete the following programme requirements."
            ]
            if not notes:
                notes = parse_flat_explanatory_notes(table)
            if not total_units:
                total_match = re.search(r"\bTotal\s*:\s*(\d+(?:\s*(?:-|–|to)\s*\d+)?)", clean_text(table.get_text(" ", strip=True)), re.I)
                total_units = clean_text(total_match.group(1)) if total_match else ""

    return {
        "title": record["title"],
        "admission_code": record["admission_code"],
        "faculty": record.get("faculty", ""),
        "faculties": record.get("faculties", [record.get("faculty", "")]),
        "description": " ".join(description),
        "total_units": total_units,
        "sections": sections,
        "notes": notes,
        "supplementary": supplementary,
        "source_file": record["stem"],
        "parse_status": "parsed" if sections else "review",
    }


def walk_groups(groups: list[dict[str, object]]):
    for group in groups:
        yield group
        yield from walk_groups(group.get("subsections", []))


def available_course_codes() -> list[str]:
    codes = set()
    for path in (ROOT.parent / "course_extraction" / "course_info").glob("*.json"):
        entries = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(entries, list):
            codes.update(entry["code"] for entry in entries if entry.get("code"))
    return sorted(codes)


def numeric_units(value: object) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", str(value or ""))
    return float(match.group(1)) if match else None


def format_units(value: float) -> str:
    return f"{value:g}"


def unit_interval(value: object) -> tuple[float, float] | None:
    text = re.sub(r"\s*\((?:with|without)\s+[^)]+\)\s*$", "", str(value or ""), flags=re.IGNORECASE)
    exact = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", text)
    if exact:
        number = float(exact.group(1))
        return number, number
    span = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*", text, re.IGNORECASE)
    if span:
        return float(span.group(1)), float(span.group(2))
    return None


def aggregate_units(values: list[object]) -> str:
    """Add explicit sibling values while preserving ranges and `or` choices."""
    alternatives: list[list[tuple[float, float]]] = []
    for value in values:
        parts = re.split(r"\s+or\s+", str(value), flags=re.IGNORECASE)
        parsed = [unit_interval(part) for part in parts]
        if not parsed or any(item is None for item in parsed):
            return ""
        alternatives.append([item for item in parsed if item is not None])
    totals = [(0.0, 0.0)]
    for choices in alternatives:
        totals = [(low + choice[0], high + choice[1]) for low, high in totals for choice in choices]
    totals = sorted(set(totals))
    if len(totals) > 1 and all(low == high for low, high in totals):
        return " or ".join(format_units(low) for low, _ in totals)
    low = min(item[0] for item in totals)
    high = max(item[1] for item in totals)
    return format_units(low) if low == high else f"{format_units(low)}-{format_units(high)}"


def declared_units(text: str) -> str:
    """Return a unit value stated in prose, without deriving it from courses."""
    patterns = (
        r"\bchoose\s+(?:at\s+least\s+)?(\d+(?:\.\d+)?)\s+units\b",
        r"\bat\s+least\s+(\d+(?:\.\d+)?)\s+units\b",
        r"\ba\s+(?:minimum|total)\s+of\s+(\d+(?:\.\d+)?)\s+units\b",
        r"\b(\d+(?:\.\d+)?)\s+units\s+(?:chosen|from|of)\b",
        r"\bat\s+most\s+(\d+(?:\.\d+)?)\s+units\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def assign_declared_heading_units(group: dict[str, object]) -> None:
    """Add badges only where a heading (or its own elective instruction) states units."""
    for child in group.get("subsections", []):
        assign_declared_heading_units(child)

    if group.get("units"):
        return
    title = str(group.get("title", ""))
    value = declared_units(title)
    if not value and "elective" in title.lower():
        value = declared_units(" ".join(str(row) for row in group.get("text", [])))
    if value:
        group["units"] = value
        parenthetical = re.search(r"\((?:Choose\s+)?(?:at\s+least\s+)?\d+(?:\.\d+)?\s+units[^)]*\)", title, re.IGNORECASE)
        if parenthetical and title.lower().startswith(("required courses", "elective courses", "elective course")):
            group["title"] = clean_text(title[:parenthetical.start()] + title[parenthetical.end():]).rstrip(":")


def assign_choice_and_stream_units(data: dict[str, object]) -> None:
    """Propagate catalogue-stated option totals; never total their component rows."""
    for section in data["sections"]:
        section_units = str(section.get("units", ""))
        groups = section.get("subsections", [])

        # Each alternative fulfils the complete enclosing elective requirement.
        if section_units and "choose any one" in str(section.get("title", "")).lower():
            for option in groups:
                if re.fullmatch(r"\([a-z]\)", str(option.get("marker", "")), re.IGNORECASE):
                    option["units"] = section_units

        # The prose immediately before named specialization streams states the
        # requirement that applies to every following stream heading.
        for index, intro in enumerate(groups):
            intro_prose = " ".join([
                str(intro.get("title", "")),
                *(str(row) for row in intro.get("text", [])),
            ])
            if not re.match(r"streams?(?:\s+of\s+specialization)?\b", intro_prose, re.IGNORECASE):
                continue
            stream_units = declared_units(intro_prose)
            if stream_units:
                intro["units"] = stream_units
            elif re.search(r"\bat\s+least\s+(?:six|6)\s+courses\b", intro_prose, re.IGNORECASE):
                stream_units = section_units
            if stream_units:
                for stream in groups[index + 1:]:
                    stream["units"] = stream_units
            break

    # Biomedical Engineering streams comprise 12 units of prescribed stream
    # courses plus the compulsory 6-unit BMEG4998/4999 research component.
    if data["source_file"] == "B.Eng._in_Biomedical_Engineering":
        elective = next(section for section in data["sections"] if str(section["marker"]).startswith("4"))
        stream_groups = elective.get("subsections", [])
        intro_index = next(
            (index for index, group in enumerate(stream_groups) if group.get("title") == "Streams"),
            None,
        )
        if intro_index is not None:
            for stream in stream_groups[intro_index:]:
                stream["units"] = "18"


def assign_elective_group_units(group: dict[str, object]) -> None:
    """Use one direct declared elective requirement for its named wrapper."""
    for child in group.get("subsections", []):
        assign_elective_group_units(child)
    if group.get("units") or "elective" not in str(group.get("title", "")).lower():
        return
    candidates = [
        str(child.get("units"))
        for child in group.get("subsections", [])
        if child.get("units") and declared_units(str(child.get("title", "")))
    ]
    unit_children = [child for child in group.get("subsections", []) if child.get("units")]
    if len(candidates) == 1 and len(unit_children) == 1:
        group["units"] = candidates[0]


def populate_missing_units(group: dict[str, object]) -> None:
    for child in group.get("subsections", []):
        populate_missing_units(child)

    if not group.get("units"):
        title = str(group.get("title", ""))
        parenthetical = re.search(r"\((?:Choose\s+)?(?:at least\s+)?(\d+(?:\.\d+)?)\s+units[^)]*\)", title, re.IGNORECASE)
        prefixed = re.match(r"(\d+(?:\.\d+)?)\s+units\s+of\s+", title, re.IGNORECASE)
        if parenthetical and title.lower().startswith(("required courses", "elective courses", "elective course")):
            group["units"] = parenthetical.group(1)
            group["title"] = clean_text(title[:parenthetical.start()] + title[parenthetical.end():]).rstrip(":")
        elif prefixed:
            group["units"] = prefixed.group(1)
            group["title"] = title[prefixed.end():].rstrip(":")

    children = group.get("subsections", [])
    if group.get("units") or not children:
        return
    lower_title = str(group.get("title", "")).lower()
    is_numbered_section = bool(re.fullmatch(r"\d+\.?", str(group.get("marker", ""))))
    if ("elective" in lower_title and not is_numbered_section) or any(term in lower_title for term in ("choose any", "option", "stream", "areas", "2nd major")):
        return
    # A declared wrapper followed by its lettered alternatives states the
    # section total; the alternatives must not be added to that wrapper.
    first = children[0]
    if (
        is_numbered_section
        and not first.get("marker")
        and first.get("units")
        and declared_units(str(first.get("title", "")))
        and all(re.fullmatch(r"\([a-z]\)", str(child.get("marker", "")), re.IGNORECASE) for child in children[1:])
    ):
        group["units"] = first["units"]
        return
    values = [child.get("units") for child in children]
    combined = aggregate_units(values) if values and all(value not in {None, ""} for value in values) else ""
    if combined:
        group["units"] = combined
        group["units_computed"] = True


def add_biomed_csci_groups(data: dict[str, object], course_codes: list[str]) -> None:
    if data["source_file"] != "B.Eng._in_Biomedical_Engineering":
        return
    csci_codes = [code for code in course_codes if re.fullmatch(r"CSCI [1-9]\d{3}", code)]
    elective = next(section for section in data["sections"] if str(section["marker"]).startswith("4"))
    note = "Students may take a maximum of 3 units of CSCI courses at 1000 or above level."
    elective["subsections"].insert(0, {
        "marker": "",
        "title": "CSCI Courses",
        "units": "max. 3",
        "text": [note],
        "codes": csci_codes,
        "subsections": [],
    })
    for group in elective["subsections"]:
        if group.get("title") == "Streams":
            group["hide_course_table"] = True
        for child in group.get("subsections", []):
            if "elective course" in str(child.get("title", "")).lower():
                child["subsections"].append({
                    "marker": "",
                    "title": "CSCI Courses",
                    "units": "max. 3",
                    "text": [note],
                    "codes": csci_codes,
                    "subsections": [],
                    "embed_in_parent_table": True,
                    "collapse_course_table": True,
                })


def add_computer_engineering_remaining_groups(data: dict[str, object], course_codes: list[str]) -> None:
    if data["source_file"] != "B.Eng._in_Computer_Engineering":
        return
    broad_codes = [
        code for code in course_codes
        if re.fullmatch(r"(?:AIST|CENG|CSCI|ELEG) [2-9]\d{3}", code)
    ]
    for group in list(walk_groups(data["sections"])):
        remaining_rows = [text for text in group.get("text", []) if text.lower().startswith("remaining units can be chosen")]
        if not remaining_rows:
            continue
        primary_rows = [text for text in group["text"] if text not in remaining_rows]
        primary_codes = {code for text in primary_rows for code in extract_course_codes(text)}
        explicit_remaining = {code for text in remaining_rows for code in extract_course_codes(text)}
        group["text"] = primary_rows
        group["codes"] = [code for code in group["codes"] if code in primary_codes]
        resolved = sorted((set(broad_codes) | explicit_remaining) - set(group["codes"]))
        group["subsections"].append({
            "marker": "",
            "title": "Courses Eligible for Remaining Units",
            "units": "",
            "text": remaining_rows,
            "codes": resolved,
            "subsections": [],
        })

    # The resolved set is an alternative source for remaining units, parallel
    # to the prescribed Elective Courses rather than a child of that list.
    options = data["sections"][3].get("subsections", [])
    for option in options:
        for elective in list(option.get("subsections", [])):
            remaining = [child for child in elective.get("subsections", []) if child["title"] == "Courses Eligible for Remaining Units"]
            if remaining:
                elective["subsections"] = [child for child in elective["subsections"] if child not in remaining]
                option["subsections"].extend(remaining)


def promote_remaining_unit_headings(data: dict[str, object]) -> None:
    if data["source_file"] != "B.Eng._in_Artificial_Intelligence_Systems_and_Technologies":
        return
    section = data["sections"][3]
    for option in list(section.get("subsections", [])):
        candidates = [option, *option.get("subsections", [])]
        for group in candidates:
            remaining = [text for text in group.get("text", []) if text.lower().startswith("remaining units can be chosen")]
            if not remaining:
                continue
            group["text"] = [text for text in group["text"] if text not in remaining]
            new_groups = [{
                "marker": "",
                "title": text.rstrip("."),
                "units": "",
                "text": [],
                "codes": [],
                "subsections": [],
            } for text in remaining]
            option["subsections"].extend(new_groups)


def promote_computational_data_science_remaining_headings(data: dict[str, object]) -> None:
    if data["source_file"] != "B.Sc._in_Computational_Data_Science":
        return
    section = next(section for section in data["sections"] if str(section["marker"]).startswith("5"))
    for option in section.get("subsections", []):
        remaining_rows: list[str] = []
        for group in walk_groups(option.get("subsections", [])):
            matches = [
                text for text in group.get("text", [])
                if str(text).lower().startswith("remaining units can be chosen")
            ]
            if matches:
                group["text"] = [text for text in group["text"] if text not in matches]
                remaining_rows.extend(matches)
        option["subsections"].extend({
            "marker": "",
            "title": text.rstrip("."),
            "units": "",
            "text": [],
            "codes": [],
            "subsections": [],
        } for text in remaining_rows)


def resolve_department_rule(text: str, course_codes: list[str]) -> list[str]:
    """Expand department/level prose while respecting explicit exclusions."""
    rules = re.findall(
        r"((?:[A-Z]{4}/)*[A-Z]{4})\s+(?:course\(s\)|courses?)\s+at\s+(\d)000\s+(?:or|and)\s+above",
        text,
        re.IGNORECASE,
    )
    if not rules:
        return []
    thresholds = {subject: int(level) for subjects, level in rules for subject in subjects.upper().split("/")}
    exclusions = set(extract_course_codes(text[text.lower().find("exclud"):])) if "exclud" in text.lower() else set()
    return [
        code for code in course_codes
        if code[:4] in thresholds and int(code[5]) >= thresholds[code[:4]] and code not in exclusions
    ]


def resolve_broad_course_groups(data: dict[str, object], course_codes: list[str]) -> None:
    """Resolve broad department references already represented as groups."""
    for group in walk_groups(data["sections"]):
        if re.fullmatch(r"\d+\.?", str(group.get("marker", ""))) and group.get("subsections"):
            continue
        prose = " ".join([str(group.get("title", "")), *group.get("text", [])])
        resolved = resolve_department_rule(prose, course_codes)
        if not resolved:
            continue
        exclusions = set(extract_course_codes(prose[prose.lower().find("exclud"):])) if "exclud" in prose.lower() else set()
        group["codes"] = sorted((set(group.get("codes", [])) | set(resolved)) - exclusions)


def resolve_computer_science_remaining_groups(data: dict[str, object], course_codes: list[str]) -> None:
    if data["source_file"] != "B.Sc._in_Computer_Science":
        return
    for group in walk_groups(data["sections"]):
        if not str(group.get("title", "")).lower().startswith("remaining units"):
            continue
        prose = " ".join(group.get("text", []))
        broad = [
            code for code in course_codes
            if re.fullmatch(r"(?:AIST|CENG|CSCI) [2-9]\d{3}", code)
        ]
        group["codes"] = sorted(set(group.get("codes", [])) | set(broad) | set(extract_course_codes(prose)))

    general = data["sections"][3]["subsections"][0]
    general_pool = [code for code in course_codes if code[:4] in {"AIST", "CENG", "CSCI"}]
    general["codes"] = []
    elective = next(group for group in general.get("subsections", []) if group["title"] == "Elective Courses")
    elective["subsections"].append({
        "marker": "",
        "title": "AIST/CENG/CSCI Courses",
        "units": "",
        "text": [],
        "codes": general_pool,
        "subsections": [],
    })


def structure_mathematics_information_engineering_areas(data: dict[str, object], course_codes: list[str]) -> None:
    if data["source_file"] != "B.Sc._in_Mathematics_and_Information_Engineering":
        return
    section = data["sections"][3]
    extras: list[str] = []
    if section["text"]:
        source = section["text"][0]
        extras = list(section["text"][1:])
    elif len(section.get("subsections", [])) == 1:
        source_group = section["subsections"][0]
        source_rows = list(source_group.get("text", []))
        source = clean_text(f"{source_group.get('title', '')} {source_rows[0] if source_rows else ''}")
        extras = source_rows[1:]
    else:
        return
    area_names = [
        "Artificial Intelligence, Machine Learning, Computer Vision",
        "Theoretical Topics in Information Sciences",
        "Theoretical Mathematics",
        "Applied Mathematics",
        "Communications",
        "Software Engineering and Data Science",
        "Cyber Security and Applied Cryptography",
        "Internet Engineering and Networks",
        "Hardware",
        "Software and Professional Practice",
    ]
    positions = [(name, source.find(name)) for name in area_names]
    if any(position < 0 for _, position in positions):
        return
    groups = []
    for index, (name, position) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(source)
        body = source[position + len(name):end].strip(" :")
        groups.append({"marker": "", "title": name, "units": "", "text": [body], "codes": extract_course_codes(body), "subsections": []})
    for extra in extras:
        resolved = resolve_department_rule(extra, course_codes)
        groups.append({"marker": "", "title": "Additional Eligible Courses", "units": "", "text": [extra], "codes": resolved, "subsections": []})
    section["text"] = []
    section["codes"] = []
    section["subsections"] = groups


def add_information_engineering_remaining_group(data: dict[str, object], course_codes: list[str]) -> None:
    if data["source_file"] != "B.Eng._in_Information_Engineering":
        return
    elective = data["sections"][3]
    primary = elective["subsections"][0]
    remaining_rows = [text for text in primary["text"] if text.lower().startswith("the remaining units")]
    if not remaining_rows:
        return
    primary["text"] = [text for text in primary["text"] if text not in remaining_rows]
    eligible = [
        code for code in course_codes
        if re.fullmatch(r"(?:AIST|BMEG|CENG|CSCI|EEEN|ELEG|ENGG|ESTR|FTEC|MAEG|SEEM) [3-9]\d{3}", code)
        and code not in primary["codes"]
    ]
    elective["subsections"].insert(1, {
        "marker": "",
        "title": "The Remaining Units",
        "units": "",
        "text": remaining_rows,
        "codes": eligible,
        "subsections": [],
    })


def nest_area_lists(data: dict[str, object]) -> None:
    for section in data["sections"]:
        groups = section.get("subsections", [])
        for index, group in list(enumerate(groups)):
            if str(group.get("title", "")).rstrip(":").lower() != "areas":
                continue
            parent = next(
                (candidate for candidate in reversed(groups[:index]) if str(candidate.get("title", "")).lower().startswith("elective courses")),
                None,
            )
            if parent:
                groups.remove(group)
                parent["subsections"].append(group)


def flatten_area_wrapper_and_set_second_major_units(data: dict[str, object]) -> None:
    if data["source_file"] not in {
        "B.Eng._in_Materials_Science_and_Engineering_X_Double_Major_Programme",
        "B.Sc._in_Aerospace_Science_and_Earth_Informatics_X_Double_Major_Programme",
        "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme",
    }:
        return
    first_major = data["sections"][1]
    elective = next(group for group in first_major["subsections"] if group["title"].startswith("Elective Courses"))
    areas = next((group for group in elective["subsections"] if group["title"] == "Areas"), None)
    if areas:
        position = elective["subsections"].index(areas)
        elective["subsections"][position:position + 1] = areas["subsections"]
    # Every named double-major area carries the 27-unit option requirement.
    for area in elective.get("subsections", []):
        if re.fullmatch(r"[ivxlcdm]+\)", str(area.get("marker", "")), re.IGNORECASE):
            area["units"] = "27"
    requirement_text = " ".join(elective.get("text", []))
    ranges = re.search(
        r"(\d+\s*[-–]\s*\d+)\s+units\s+to\s+be\s+taken\s+from\s+Group\s+A.*?(\d+\s*[-–]\s*\d+)\s+units\s+from\s+Group\s+B",
        requirement_text,
        re.IGNORECASE,
    )
    if ranges:
        group_units = {"group a": re.sub(r"\s+", "", ranges.group(1)), "group b": re.sub(r"\s+", "", ranges.group(2))}
        for group in walk_groups(elective.get("subsections", [])):
            key = str(group.get("title", "")).rstrip(":").lower()
            if key in group_units:
                group["units"] = group_units[key]
    data["sections"][2]["units"] = "33"


def promote_double_major_additional_course_headings(data: dict[str, object]) -> None:
    if data["source_file"] != "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme":
        return
    elective = next(group for group in data["sections"][1]["subsections"] if group["title"].startswith("Elective Courses"))
    for area in elective.get("subsections", []):
        for group in area.get("subsections", []):
            additions: list[dict[str, object]] = []
            for course_group in group.get("subsections", []):
                rows = [
                    text for text in course_group.get("text", [])
                    if re.match(r"students?\s+can\s+also\s+take\b", str(text), re.IGNORECASE)
                ]
                course_group["text"] = [text for text in course_group.get("text", []) if text not in rows]
                for row in rows:
                    heading, separator, course_text = str(row).partition(":")
                    additions.append({
                        "marker": "",
                        "title": heading.rstrip("."),
                        "units": "",
                        "text": [course_text.strip()] if separator and course_text.strip() else [],
                        "codes": extract_course_codes(course_text if separator else ""),
                        "subsections": [],
                    })
            group.get("subsections", []).extend(additions)


def nest_mae_streams(data: dict[str, object]) -> None:
    if data["source_file"] != "B.Eng._in_Mechanical_and_Automation_Engineering":
        return
    groups = data["sections"][3]["subsections"]
    stream_titles = {"Design and Manufacturing", "Mechatronics", "Robotics and Automation"}
    rebuilt = []
    current_stream = None
    for group in groups:
        if group["title"] in stream_titles:
            current_stream = group
            rebuilt.append(group)
        elif current_stream is not None and group.get("marker") in {"(a)", "(b)"}:
            current_stream["subsections"].append(group)
        else:
            rebuilt.append(group)
    data["sections"][3]["subsections"] = rebuilt


def structure_history_elective_minima(data: dict[str, object]) -> None:
    """Recover the two parallel minima merged into one Word-table row."""
    if data["source_file"] != "B.A._in_History":
        return
    section = data["sections"][2]
    groups = section.get("subsections", [])
    if len(groups) != 1:
        return
    source = " ".join(str(row) for row in groups[0].get("text", []))
    match = re.match(
        r"(Complete 45 units.*?with:)\s*at least 6 units from:\s*(.*?)\s*at least 9 units from:\s*(.*)",
        source,
        re.IGNORECASE,
    )
    if not match:
        return
    section["text"] = [clean_text(match.group(1))]
    section["codes"] = []
    section["subsections"] = [
        {
            "marker": "(a)",
            "title": "At least 6 units from",
            "units": "6",
            "text": [clean_text(match.group(2))],
            "codes": extract_course_codes(match.group(2)),
            "subsections": [],
        },
        {
            "marker": "(b)",
            "title": "At least 9 units from",
            "units": "9",
            "text": [clean_text(match.group(3))],
            "codes": extract_course_codes(match.group(3)),
            "subsections": [],
        },
    ]


def structure_chinese_language_education_degree(data: dict[str, object]) -> None:
    """Restore the discipline and methodology layers in the combined degree."""
    if data["source_file"] != "B.A._(Chinese_Language_Studies)_and_B.Ed._(Chinese_Language_Education)":
        return
    required = data["sections"][1]
    malformed = required.get("subsections", [None])[0]
    if not malformed or "(b)" not in str(malformed.get("title", "")):
        return

    methodology_text = " ".join(str(row) for row in malformed.get("text", []))
    methodology_text = re.sub(r"^Language Teaching Methodology\s*", "", methodology_text)
    code_chunks = re.split(r"(?=CLED(?:3510|4510|2640|4630)\b)", methodology_text)
    code_chunks = [clean_text(chunk) for chunk in code_chunks if clean_text(chunk)]
    if len(code_chunks) != 5:
        return
    methodology = {
        "marker": "",
        "title": "Language Teaching Methodology",
        "units": "17",
        "text": [],
        "codes": [],
        "subsections": [
            {
                "marker": f"({chr(97 + index)})",
                "title": "",
                "units": "",
                "text": [chunk],
                "codes": extract_course_codes(chunk),
                "subsections": [],
            }
            for index, chunk in enumerate(code_chunks)
        ],
    }
    education_groups = [methodology, *required.get("subsections", [])[1:]]
    literature_codes = list(required.get("codes", []))
    literature_text = [
        row for row in required.get("text", [])
        if row not in {"Chinese Language and Literature", "Chinese Language Education"}
    ]
    required["units"] = "80"
    required["text"] = []
    required["codes"] = []
    required["subsections"] = [
        {
            "marker": "",
            "title": "Chinese Language and Literature",
            "units": "33",
            "text": literature_text,
            "codes": literature_codes,
            "subsections": [],
        },
        {
            "marker": "",
            "title": "Chinese Language Education",
            "units": "47",
            "text": [],
            "codes": [],
            "subsections": education_groups,
        },
    ]

    elective = data["sections"][2]
    groups = elective.get("subsections", [])
    if len(groups) == 3:
        for group in walk_groups(groups):
            group["text"] = [row for row in group.get("text", []) if row != "Chinese Language Education"]
        elective["text"] = []
        elective["subsections"] = [
            {
                "marker": "",
                "title": "Chinese Language and Literature",
                "units": "24",
                "text": [],
                "codes": [],
                "subsections": groups[:2],
            },
            {
                "marker": "",
                "title": "Chinese Language Education",
                "units": "4",
                "text": [],
                "codes": [],
                "subsections": groups[2:],
            },
        ]


def assign_labeled_alternative_units(data: dict[str, object]) -> None:
    """Surface `with/without stream` alternatives as one section value."""
    for section in data["sections"]:
        if section.get("units"):
            continue
        labelled = []
        for group in section.get("subsections", []):
            match = re.fullmatch(
                r"(\d+(?:\.\d+)?)\s*\((?:with|without)\s+[^)]+\)",
                str(group.get("units", "")),
                re.IGNORECASE,
            )
            if match:
                labelled.append(match.group(1))
        if len(labelled) >= 2:
            section["units"] = " or ".join(dict.fromkeys(labelled))


def structure_chinese_studies(data: dict[str, object]) -> None:
    if data["source_file"] != "B.A._in_Chinese_Studies":
        return
    required = data["sections"][1]
    groups = required.get("subsections", [])
    if len(groups) < 5:
        return
    a_group, b_group = groups[:2]
    native = next((group for group in groups if str(group.get("title", "")).startswith("Chinese Native Stream")), None)
    c_group = next((group for group in walk_groups(groups) if group.get("marker") == "(c)"), None)
    d_group = next((group for group in walk_groups(groups) if group.get("marker") == "(d)"), None)
    choices = [group for group in groups if str(group.get("title", "")).startswith("Any one course")]
    if not all((native, c_group, d_group)) or len(choices) != 2:
        return
    native["subsections"] = []
    international = {
        "marker": "",
        "title": "International Stream (IS)",
        "units": "",
        "text": list(b_group.get("text", [])),
        "codes": list(b_group.get("codes", [])),
        "subsections": [],
    }
    b_group["text"] = []
    b_group["codes"] = []
    b_group["subsections"] = [international, native]
    c_group["subsections"] = choices
    for choice in choices:
        choice["units"] = ""
        choice["subsections"] = []
        choice.pop("units_computed", None)
    d_group["subsections"] = []
    required["subsections"] = [a_group, b_group, c_group, d_group]
    required["units"] = "27"

    elective = data["sections"][2]
    if len(elective.get("subsections", [])) == 1:
        source = elective["subsections"][0]
        joined = " ".join(str(row) for row in source.get("text", []))
        split = re.split(r"\s*Chinese Native Stream \(CNSS\)\s*", joined, maxsplit=1)
        if len(split) == 2:
            international_text = clean_text(split[0])
            native_text = clean_text(split[1])
            elective["subsections"] = [
                {
                    "marker": "",
                    "title": "International Stream (IS)",
                    "units": "30",
                    "text": [international_text],
                    "codes": extract_course_codes(international_text),
                    "subsections": [],
                },
                {
                    "marker": "",
                    "title": "Chinese Native Stream (CNSS)",
                    "units": "30",
                    "text": [native_text],
                    "codes": extract_course_codes(native_text),
                    "subsections": [],
                },
            ]


def structure_japanese_studies_streams(data: dict[str, object]) -> None:
    if data["source_file"] != "B.A._in_Japanese_Studies":
        return
    section = data["sections"][2]
    groups = list(section.get("subsections", []))
    with_index = next((i for i, group in enumerate(groups) if "with stream" in str(group.get("units", "")).lower() or "Students choosing a stream" in str(group.get("title", ""))), None)
    if with_index is None or with_index < 4:
        return
    without_intro = groups[0]
    without_instruction = groups[1]
    without_stream = {
        "marker": "",
        "title": "Without Stream",
        "units": (re.search(r"take (\d+) units", str(without_instruction.get("title", ""))).group(1) if re.search(r"take (\d+) units", str(without_instruction.get("title", ""))) else "6"),
        "text": [without_intro.get("title", ""), without_instruction.get("title", "")],
        "codes": [],
        "subsections": groups[2:with_index],
    }
    with_intro = groups[with_index]
    first_roman = next((child for child in with_intro.get("subsections", []) if re.fullmatch(r"\([ivxlcdm]+\)", str(child.get("marker", "")), re.IGNORECASE)), None)
    if first_roman is None:
        return
    streams = [first_roman]
    first_roman["subsections"] = []
    current = first_roman
    for item in groups[with_index + 1:]:
        nested_romans = [
            child for child in item.get("subsections", [])
            if re.fullmatch(r"\([ivxlcdm]+\)", str(child.get("marker", "")), re.IGNORECASE)
        ]
        item["subsections"] = [child for child in item.get("subsections", []) if child not in nested_romans]
        current["subsections"].append(item)
        for roman in nested_romans:
            roman["subsections"] = []
            streams.append(roman)
            current = roman
    with_stream = {
        "marker": "",
        "title": "With Stream",
        "units": (re.search(r"take (\d+) units", str(with_intro.get("title", ""))).group(1) if re.search(r"take (\d+) units", str(with_intro.get("title", ""))) else "12"),
        "text": [with_intro.get("title", "")],
        "codes": [],
        "subsections": streams,
    }
    section["units"] = " or ".join(dict.fromkeys([without_stream["units"], with_stream["units"]]))
    section["subsections"] = [without_stream, with_stream]


def structure_natural_sciences_lists(data: dict[str, object]) -> None:
    if data["source_file"] != "B.Sc._in_Natural_Sciences":
        return
    section = data["sections"][1]
    section["title"] = re.sub(r"\s*:\s*.*$", "", str(section.get("title", "")))
    rows = list(section.get("text", []))
    intro_rows: list[str] = []
    groups: list[dict[str, object]] = []
    labels = ["Concentration Area Courses", "Other Science Courses"]
    for row in rows:
        matched = next((label for label in labels if row.startswith(f"{label}:")), None)
        if matched:
            course_text = row[len(matched) + 1:].strip()
            groups.append({
                "marker": "",
                "title": matched,
                "units": "",
                "text": [course_text],
                "codes": extract_course_codes(course_text),
                "subsections": [],
            })
        else:
            intro_rows.append(row)
    if groups:
        section["text"] = intro_rows
        section["codes"] = [code for row in intro_rows for code in extract_course_codes(row)]
        section["subsections"] = groups


def remove_chll_second_major_material(data: dict[str, object]) -> None:
    # The first standard requirement box includes explanatory notes about
    # permitted double-major exemptions. They are part of the selected major
    # scheme and must not be confused with the separate second-major table.
    return


def fill_single_missing_section_from_total(data: dict[str, object]) -> None:
    """Derive the sole omitted section badge from the published programme total."""
    total = unit_interval(data.get("total_units", ""))
    missing = [section for section in data["sections"] if not section.get("units")]
    known = [unit_interval(section.get("units")) for section in data["sections"] if section.get("units")]
    if total is None or len(missing) != 1 or any(value is None for value in known):
        return
    minimum_used = sum(value[0] for value in known if value is not None)
    maximum_used = sum(value[1] for value in known if value is not None)
    low = total[0] - maximum_used
    high = total[1] - minimum_used
    if low < 0 or high < low:
        return
    missing[0]["units"] = format_units(low) if low == high else f"{format_units(low)}-{format_units(high)}"
    missing[0]["units_computed"] = True


def normalize_programme(data: dict[str, object], course_codes: list[str]) -> None:
    structure_history_elective_minima(data)
    structure_chinese_language_education_degree(data)
    structure_chinese_studies(data)
    structure_japanese_studies_streams(data)
    structure_natural_sciences_lists(data)
    remove_chll_second_major_material(data)
    assign_labeled_alternative_units(data)
    add_biomed_csci_groups(data, course_codes)
    add_computer_engineering_remaining_groups(data, course_codes)
    promote_remaining_unit_headings(data)
    promote_computational_data_science_remaining_headings(data)
    add_information_engineering_remaining_group(data, course_codes)
    resolve_computer_science_remaining_groups(data, course_codes)
    structure_mathematics_information_engineering_areas(data, course_codes)
    resolve_broad_course_groups(data, course_codes)
    nest_area_lists(data)
    flatten_area_wrapper_and_set_second_major_units(data)
    promote_double_major_additional_course_headings(data)
    nest_mae_streams(data)
    for section in data["sections"]:
        assign_declared_heading_units(section)
    assign_choice_and_stream_units(data)
    for section in data["sections"]:
        assign_elective_group_units(section)
    for section in data["sections"]:
        populate_missing_units(section)
    fill_single_missing_section_from_total(data)


def build_elite_programme(source: dict[str, object], eligible_titles: list[str]) -> dict[str, object]:
    codes = available_course_codes()
    estr_lower = [code for code in codes if re.fullmatch(r"ESTR [12]\d{3}", code)]
    estr_upper = [code for code in codes if re.fullmatch(r"ESTR [34]\d{3}", code)]
    pg_subjects = "AIST|BMEG|CENG|CSCI|EEEN|ELEG|ENGG|IERG|MAEG|SEEM"
    postgraduate = [code for code in codes if re.fullmatch(rf"(?:{pg_subjects}) 5\d{{3}}", code)]
    research_component = [code for code in codes if code in {"ESTR 4998", "ESTR 4999"}]
    clean_supplementary = [re.sub(r"\s*\[[a-z]\]", "", text) for text in source.get("supplementary", [])]
    elite_notes = [note for note in source.get("notes", []) if note["marker"] in {"[e]", "[f]", "[g]", "[h]"}]
    normalized_notes = [
        {"marker": f"[{chr(97 + index)}]", "text": re.sub(
            r"items?\s+1\s+to\s+4\s+above", "the ELITE Stream requirements", note["text"], flags=re.I
        )}
        for index, note in enumerate(elite_notes)
    ]
    if len(normalized_notes) > 1:
        normalized_notes[1]["text"] = (
            "Students may count up to 9 units completed for their underlying Major Programme "
            "toward the ELITE Stream elective requirements. Research Component Courses in "
            "section 3 are excluded from this 9-unit overlap. A full list of ESTR courses is "
            "available at the ELITE website."
        )
    return {
        "title": "Engineering Leadership, Innovation, Technology and Entrepreneurship (ELITE) Stream",
        "admission_code": "Optional Faculty Stream",
        "faculty": "Engineering",
        "description": ("Engineering students in the eligible major programmes may challenge "
                        "themselves by taking this optional faculty stream."),
        "total_units": "15",
        "intro_sections": [{"title": "Eligible Engineering Major Programmes", "text": eligible_titles}],
        "sections": [
            {
                "marker": "1.",
                "title": "ESTR Courses",
                "units": "12",
                "text": [clean_supplementary[3]] if len(clean_supplementary) > 3 else [],
                "codes": [],
                "subsections": [
                    {"marker": "(a)", "title": "1000- and 2000-level ESTR Courses (at most 6 units)", "units": "", "text": [], "codes": estr_lower, "subsections": []},
                    {"marker": "(b)", "title": "3000- and 4000-level ESTR Courses (at least 6 units)", "units": "", "text": [], "codes": estr_upper, "subsections": []},
                ],
            },
            {
                "marker": "2.",
                "title": "Research Postgraduate Courses",
                "units": "3",
                "text": [clean_supplementary[4]] if len(clean_supplementary) > 4 else [],
                "codes": postgraduate,
                "subsections": [],
            },
            {
                "marker": "3.",
                "title": "Research Component Courses",
                "units": "6",
                "text": ["ESTR4998 and ESTR4999 replace the corresponding Major Programme research component courses for students who declare the ELITE Stream."],
                "codes": research_component,
                "subsections": [],
            },
        ],
        "notes": normalized_notes,
        "supplementary": [],
        "source_file": "Engineering_ELITE_Stream",
    }


def parse_mbchb_programme(record: dict[str, object], path: Path) -> dict[str, object]:
    """Parse the MBChB box, whose prose, requirements and pattern are separate tables."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    flat_tables = [table for table in soup.find_all("table") if not table.find("table")]
    requirement = next(table for table in flat_tables if "Faculty Package" in clean_text(table.get_text(" ", strip=True))
                       and "Required Courses" in clean_text(table.get_text(" ", strip=True)))
    pattern_table = next(table for table in flat_tables if clean_text(table.get_text(" ", strip=True)).startswith("Recommended Course Pattern"))
    notes_table = next(table for table in flat_tables if clean_text(table.get_text(" ", strip=True)).startswith("1. Students who have completed"))
    outer = next(table for table in soup.find_all("table") if len(table.find_all("table")) == 3
                 and "Global Physician-Leadership Stream" in clean_text(table.get_text(" ", strip=True)))
    outer_rows = direct_rows(outer)
    initial = clean_text(outer_rows[1].find_all("td", recursive=False)[0].get_text(" ", strip=True))
    description = initial[:initial.find("Units 1.")].strip()

    sections = []
    for row in direct_rows(requirement):
        cells = row_cells(row)
        marker = next((cell for cell in cells if re.fullmatch(r"[12]\.", cell)), "")
        if not marker:
            if sections:
                body = next((cell for cell in cells if extract_course_codes(cell)), "")
                if body:
                    sections[-1]["text"].append(body)
                    sections[-1]["codes"].extend(code for code in extract_course_codes(body) if code not in sections[-1]["codes"])
            continue
        marker_position = cells.index(marker)
        title = cells[marker_position + 1].rstrip(":")
        unit = cells[marker_position + 2] if marker_position + 2 < len(cells) else ""
        sections.append({"marker": marker, "title": title, "units": unit, "text": [], "codes": [], "subsections": []})

    pattern = []
    current_year = ""
    for row in direct_rows(pattern_table)[1:]:
        cells = [cell for cell in row_cells(row) if cell]
        if not cells:
            continue
        if cells[0].startswith("Year "):
            current_year = cells.pop(0)
        body = clean_text(" ".join(cells))
        term = ""
        term_match = re.match(r"(1st term|2nd term|Academic year)\s+(.*)", body, re.I)
        if term_match:
            term, body = term_match.groups()
        pattern.append({"year": current_year, "period": term, "requirements": body})

    notes = []
    current_note = None
    current_roman = None
    for row in direct_rows(notes_table):
        cells = [cell for cell in row_cells(row) if cell]
        if not cells:
            continue
        marker = cells[0]
        body = clean_text(" ".join(cells[1:]))
        if re.fullmatch(r"\d+\.", marker):
            current_note = {"marker": marker, "text": body, "subsections": [], "rows": []}
            notes.append(current_note)
            current_roman = None
        elif re.fullmatch(r"\([ivxlcdm]+\)", marker, re.I) and current_note:
            current_roman = {"marker": marker, "title": "", "units": "", "text": [body],
                             "codes": extract_course_codes(body), "subsections": []}
            current_note["subsections"].append(current_roman)
        elif re.fullmatch(r"\([a-z]\)", marker, re.I) and current_roman:
            current_roman["subsections"].append({"marker": marker, "title": "", "units": "", "text": [body],
                                                  "codes": extract_course_codes(body), "subsections": []})

    gps_text = clean_text(outer_rows[3].find_all("td", recursive=False)[0].get_text(" ", strip=True))
    gps_body = gps_text.split("All GPS students have to complete", 1)[1]
    gps_body = "All GPS students have to complete" + gps_body.split("Explanatory Notes:", 1)[0]
    points = list(re.finditer(r"\(([123])\)\s*", gps_body))
    gps_children = []
    gps_codes = {
        "1": ["GPSU 2000", "GPSU 3000", "GPSU 4000", "GPSU 4200"],
        "2": ["GPSU 3100"],
        "3": ["GPSU 4100"],
    }
    intro = gps_body[:points[0].start()].strip()
    for position, match in enumerate(points):
        end = points[position + 1].start() if position + 1 < len(points) else len(gps_body)
        body = gps_body[match.end():end].strip()
        gps_children.append({"marker": f"({match.group(1)})", "title": "", "units": "", "text": [body],
                             "codes": gps_codes[match.group(1)], "subsections": []})
    sections.append({"marker": "3.", "title": "MBChB Global Physician-Leadership Stream (GPS)",
                     "units": "", "text": [intro], "codes": [], "subsections": gps_children})
    description_lines = [part.strip() for part in re.split(
        r"(?=Besides the essential|Students learn a wide range|In the clinical years|Medical students are required|Graduates are required|Students are required to complete 11 units)",
        description,
    ) if part.strip()]
    return {
        "title": record["title"], "admission_code": record["admission_code"],
        "faculty": record.get("faculty", ""), "faculties": record.get("faculties", [record.get("faculty", "")]),
        "description": description, "description_lines": description_lines,
        "total_units": "", "sections": sections, "notes": notes,
        "supplementary": [], "recommended_course_pattern": pattern, "source_file": record["stem"],
    }


def build_star_programme(block: dict[str, object], source: dict[str, object], eligible_titles: list[str]) -> dict[str, object]:
    """Publish the faculty-wide STAR scheme once instead of repeating it in every Science major."""
    notes = deepcopy([note for note in source.get("notes", []) if note.get("marker") in {"[b]", "[c]"}])
    for note, marker in zip(notes, ("[a]", "[b]")):
        note["marker"] = marker
    sections = deepcopy(block.get("sections", []))
    for item in walk_groups(sections):
        for key in ("title",):
            item[key] = item.get(key, "").replace("[b]", "[a]").replace("[c]", "[b]")
        item["text"] = [text.replace("[b]", "[a]").replace("[c]", "[b]") for text in item.get("text", [])]
    return {
        "title": "Science, Technology and Research (STAR) Stream",
        "admission_code": "Optional Faculty Stream",
        "faculty": "Science", "faculties": ["Science"],
        "description": (block.get("description") or "An optional stream offered by the Faculty of Science."),
        "total_units": block.get("total_units", "12"),
        "intro_sections": [{"title": "Eligible Science Major Programmes", "text": eligible_titles}],
        "sections": sections,
        "additional_requirements": [], "source_file": "Science_STAR_Stream",
    }


def additional_requirement_blocks(record: dict, path: Path, course_codes: list[str]) -> list[dict]:
    """Recover optional schemes after the main total, retaining their unit cells."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    table = choose_requirement_table(soup, record["admission_code"])
    rows = direct_rows(table)
    blocks = []
    for position, row in enumerate(rows):
        title = clean_text(row.get_text("", strip=False))
        professional_streams = {
            "Global Tax and Governance Stream", "Finance for Accountants Stream",
            "Accounting Analytics Stream", "Global Accounting Stream",
        }
        is_second_degree = title == "2nd Degree: Juris Doctor"
        is_admission_variant = title.startswith("For students admitted via the Faculty of Science")
        if not (re.fullmatch(r"Science,? Technology [Aa]nd Research Stream|Local Study Scheme", title)
                or title in professional_streams or is_second_degree or is_admission_variant):
            continue
        selected = []
        for following in rows[position + 1:]:
            text = clean_text(following.get_text("", strip=False))
            if re.search(r"Explanatory Notes?", text, re.IGNORECASE) and not is_second_degree:
                break
            selected.append(str(following))
            if re.search(r"\bTotal\s*:", text) and not is_second_degree:
                break
        fragment = BeautifulSoup("<table><tr><td>Major Programme Requirement</td></tr>" + "".join(selected) + "</table>", "html.parser")
        parsed = parse_programme(record, path, requirement_table=fragment.table)
        if title == "Local Study Scheme":
            structure_japanese_studies_streams(parsed)
        if is_admission_variant:
            structure_mathematics_information_engineering_areas(parsed, course_codes)
            resolve_broad_course_groups(parsed, course_codes)
        for section in parsed["sections"]:
            populate_missing_units(section)
        blocks.append({"title": title, "description": parsed["description"],
                       "total_units": parsed["total_units"], "sections": parsed["sections"],
                       "notes": parsed.get("notes", [])})
    return blocks


def named_stream_requirement_blocks(record: dict, path: Path) -> list[dict]:
    """Recover complete programme-specific stream/concentration schemes.

    These schemes sit after the main programme total in the source table.  They
    are intentionally source-driven here rather than copied into JSON by hand.
    """
    configurations = {
        "B.Sc._in_Earth_and_Environmental_Sciences": (
            ["Atmospheric Science Stream", "Geology and Geophysics Stream",
             "Environmental Science and Technology Stream"], "before_notes", ""),
        "B.Sc._in_Food_and_Nutritional_Sciences": (
            ["Nutritionist Stream"], "before_notes", "previous"),
        "B.Sc._in_Natural_Sciences": (
            ["Biotechnology", "Environmental Studies", "Food and Nutrition", "Data Science",
             "Chemical and Testing Sciences", "Physical Sciences"], "after_section_2", ""),
        "B.Sc._in_Risk_Management_Science": (
            ["Risk Analytics Stream"], "after_notes", ""),
        "B.Sc._in_Statistics": (
            ["Statistical Learning and Data Mining Stream", "Data Analytics Stream"],
            "after_notes", ""),
        "B.Sc._in_Mathematics": (
            ["For students who specialize in Enrichment Stream"], "before_notes", ""),
    }
    configured = configurations.get(record["stem"])
    if not configured:
        return []
    titles, placement, description_mode = configured
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    table = choose_requirement_table(soup, record["admission_code"])
    rows = direct_rows(table)

    starts: list[tuple[int, str, str]] = []
    for position, row in enumerate(rows):
        text = clean_text(row.get_text(" ", strip=True))
        for title in titles:
            if text == title or text.startswith(title + " "):
                starts.append((position, title, text[len(title):].strip()))
                break
    boundaries = [position for position, _, _ in starts]
    boundaries += [
        position for position, row in enumerate(rows)
        if clean_text(row.get_text(" ", strip=True)).startswith(
            "In addition to fulfilling the above Major Programme Requirement"
        )
    ]
    if placement != "after_notes":
        boundaries += [position for position, row in enumerate(rows)
                       if clean_text(row.get_text(" ", strip=True)).startswith("Explanatory Note")]

    blocks = []
    for position, title, inline_description in starts:
        end = min((value for value in boundaries if value > position), default=len(rows))
        selected = rows[position + 1:end]
        description = inline_description
        if description_mode == "previous" and position:
            previous = clean_text(rows[position - 1].get_text(" ", strip=True))
            if previous:
                description = previous
        prefix = "<tr><td>Major Programme Requirement</td></tr>"
        if description:
            prefix += f"<tr><td>{description}</td></tr>"
        fragment = BeautifulSoup(
            "<table>" + prefix + "".join(str(row) for row in selected) + "</table>",
            "html.parser",
        )
        parsed = parse_programme(record, path, requirement_table=fragment.table)
        for section in parsed["sections"]:
            populate_missing_units(section)
        display_title = "Enrichment Stream" if record["stem"] == "B.Sc._in_Mathematics" else title
        blocks.append({
            "title": display_title,
            "description": parsed.get("description") or description,
            "total_units": parsed.get("total_units", ""),
            "sections": parsed.get("sections", []),
            "notes": parsed.get("notes", []),
            "placement": placement,
        })
    return blocks


def generate(year: str) -> None:
    html_dir = ROOT / "major_html" / year
    output = ROOT / "major_json" / year
    output.mkdir(parents=True, exist_ok=True)
    records = json.loads((html_dir / "_programmes.json").read_text(encoding="utf-8"))
    expected_files = {f'{record["stem"]}.json' for record in records}
    expected_files.add("Engineering_ELITE_Stream.json")
    expected_files.add("Science_STAR_Stream.json")
    for stale in output.glob("*.json"):
        if stale.name not in expected_files:
            stale.unlink()
    course_codes = available_course_codes()
    course_index = {}
    for course_file in sorted((ROOT.parent / "course_extraction" / "course_info").glob("*.json")):
        entries = json.loads(course_file.read_text(encoding="utf-8"))
        if isinstance(entries, list):
            course_index.update({entry["code"]: entry for entry in entries if entry.get("code")})
    summary = []
    elite_source = None
    star_source = None
    star_block = None
    engineering_eligible = []
    star_eligible = []
    for record in records:
        has_elite_section = False
        try:
            source_path = html_dir / record["full_page_file"]
            data = (parse_mbchb_programme(record, source_path)
                    if record["stem"] == "M.B.,_Ch.B"
                    else parse_programme(record, source_path))
            normalize_programme(data, course_codes)
            data["additional_requirements"] = additional_requirement_blocks(
                record, source_path, course_codes
            ) + named_stream_requirement_blocks(record, source_path)
            raw_star = next((block for block in data["additional_requirements"]
                             if re.fullmatch(r"Science,? Technology [Aa]nd Research Stream", block.get("title", ""))), None)
            has_elite_section = bool(re.search(r"\bELITE Stream\b", source_path.read_text(encoding="utf-8"), re.I))
            if raw_star:
                star_eligible.append(data["title"])
                if star_block is None:
                    star_block, star_source = deepcopy(raw_star), deepcopy(data)
            improve_readability(data, source_path, course_index, extract_course_codes)
            for block in list(data.get("additional_requirements", [])):
                if re.fullmatch(r"Science,? Technology [Aa]nd Research Stream", block.get("title", "")):
                    data["additional_requirements"].remove(block)
        except ValueError as error:
            data = {
                "title": record["title"],
                "admission_code": record["admission_code"],
                "faculty": record.get("faculty", ""),
                "faculties": record.get("faculties", [record.get("faculty", "")]),
                "description": (
                    "The official programme page does not publish its curriculum in the standard "
                    "Major Programme Requirement table format."
                ),
                "total_units": "",
                "sections": [],
                "notes": [],
                "supplementary": [],
                "source_file": record["stem"],
                "parse_status": "unavailable",
                "parse_message": str(error),
            }
        if record["stem"] == "B.Eng._in_Artificial_Intelligence_Systems_and_Technologies":
            elite_source = data
        if has_elite_section:
            engineering_eligible.append(data["title"])
        path = output / f"{record['stem']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        all_codes = set()
        for group in walk_groups(data["sections"]):
            all_codes.update(group["codes"])
        course_count = len(all_codes)
        summary.append({"title": data["title"], "sections": len(data["sections"]), "courses": course_count})
        print(f"{data['title']}: {len(data['sections'])} sections, {course_count} courses")
    if elite_source:
        elite = build_elite_programme(elite_source, engineering_eligible)
        (output / "Engineering_ELITE_Stream.json").write_text(
            json.dumps(elite, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append({"title": elite["title"], "sections": len(elite["sections"])})
    if star_block and star_source:
        star = build_star_programme(star_block, star_source, star_eligible)
        (output / "Science_STAR_Stream.json").write_text(
            json.dumps(star, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append({"title": star["title"], "sections": len(star["sections"])})
    print(f"Generated {len(summary)} programme JSON files")


if __name__ == "__main__":
    generate(parse_args().year)

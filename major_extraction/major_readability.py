"""Source-backed presentation and eligibility refinements, never manual JSON edits."""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def walk(groups):
    for group in groups:
        yield group
        yield from walk(group.get("subsections", []))


def group(title, text=(), codes=(), units="", marker="", children=()):
    return dict(title=title, text=list(text), codes=list(dict.fromkeys(codes)),
                units=units, marker=marker, subsections=list(children))


def source_areas(path, extract):
    """Read only the course-list table, not other degree schemes on the page."""
    if not path.exists():
        return []
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    candidates = [table for table in soup.find_all("table")
                  if "Course Code" in clean(table.get_text(" ", strip=True))
                  and "Major Programme Requirement" not in clean(table.get_text(" ", strip=True))]
    areas = []
    for table in candidates:
        current = None
        body = table.find("tbody", recursive=False) or table
        for row in body.find_all("tr", recursive=False):
            cells = [clean(cell.get_text("", strip=False)) for cell in row.find_all("td", recursive=False)]
            nonempty = [cell for cell in cells if cell]
            if not nonempty:
                continue
            if re.match(r"^(?:[A-Za-z ]+ )?Area\s*\d+[A-C]?\s*:", nonempty[0]):
                current = group(nonempty[0])
                areas.append(current)
            elif current is not None and re.match(r"^[A-Z]{4}\s*\d{4}", nonempty[0]):
                current["codes"].extend(extract(nonempty[0]))
    if areas:
        return areas
    # The compact extraction file contains requirement boxes only in recent
    # years; the complete course-area catalogue remains in full_pages/.
    full_page = path.parent / "full_pages" / path.name
    if path.parent.name != "full_pages" and full_page.exists():
        return source_areas(full_page, extract)
    return []


def explicit_exclusions(text, extract):
    codes = []
    for match in re.finditer(r"\b(?:excluding|except|other than)\s*:?\s*\(?([A-Z]{4}\s*\d{4}[^.;]*)", text):
        # A subsequent positive clause is not part of the exclusion list.
        clause = re.split(r"\b(?:and all|are elective|offered|from)\b", match.group(1), maxsplit=1)[0]
        codes.extend(extract(clause))
    return set(codes)


def split_english(data, extract):
    section = next((section for section in data.get("sections", [])
                    if "Creative Writing in English" in clean(" ".join(section.get("text", [])))), None)
    if not section:
        return
    text = " ".join(section["text"])
    match = re.fullmatch(r"(.*?) Stream (.*?) Creative Writing in English Required Courses:\s*(.*?) Elective Courses:\s*(.*)", text)
    if not match:
        return
    main, intro, required, elective = match.groups()
    section["text"] = [main]
    section["codes"] = extract(main)
    section["subsections"] = [group("Creative Writing in English Stream", [intro], units="18", children=[
        group("Required Courses", [required], extract(required)),
        group("Elective Courses", [elective], extract(elective)),
    ])]


def split_fine_arts(data, extract):
    section = next((section for section in data.get("sections", [])
                    if section.get("title", "").startswith("Elective Courses")
                    and "Art History Stream" in clean(" ".join(
                        [*section.get("text", []), *(
                            part for child in section.get("subsections", [])
                            for part in [child.get("title", ""), *child.get("text", [])]
                        )]
                    ))), None)
    if not section:
        return
    source_rows = list(section.get("text", []))
    for child in section.get("subsections", []):
        source_rows.append(clean(" ".join([child.get("title", ""), *child.get("text", [])])))
    combined = clean(" ".join(source_rows))
    stream_pattern = re.compile(
        r"(?:^|(?<=\s))(Art History and Studio Art Stream|Art History Stream|Studio Art Stream)(?:\[[a-z]\])?(?=\s|$)"
    )
    stream_matches = list(stream_pattern.finditer(combined))
    streams = []
    for position, match in enumerate(stream_matches):
        title = match.group(1)
        end = stream_matches[position + 1].start() if position + 1 < len(stream_matches) else len(combined)
        rest = combined[match.end():end].strip()
        headings = list(re.finditer(r"Art History Courses|Studio Art Courses", rest))
        intro = rest[:headings[0].start()].strip() if headings else rest
        children = []
        for i, heading in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(rest)
            content = rest[heading.end():end].strip(" :")
            # The two Art History minima are distinct lists, not one union.
            chunks = [chunk.strip() for chunk in re.split(r"(?=At least \d+ units)", content) if chunk.strip()]
            if len(chunks) > 1:
                child = group(heading.group(), children=[group(
                    "",
                    [chunk],
                    extract(chunk),
                    (re.search(r"At least (\d+) units", chunk).group(1)
                     if re.search(r"At least (\d+) units", chunk) else ""),
                ) for chunk in chunks])
            else:
                units = re.search(r"At least (\d+) units", content)
                child = group(heading.group(), [content], extract(content), units.group(1) if units else ("18" if "18 units from each" in intro else ""))
            children.append(child)
        streams.append(group(title, [intro] if intro else [], units=section["units"], children=children))
    if streams:
        section["text"], section["codes"], section["subsections"] = [], [], streams


def format_fine_arts_description(data):
    """Give every Fine Arts scheme the same readable six-line introduction."""
    description = data.get("description", "").replace("Major Programme Requirement ", "", 1)
    description = re.sub(
        r"^\(for (?:Associate Degree|Higher Diploma) holders admitted to senior-year places\)\s*",
        "",
        description,
        flags=re.IGNORECASE,
    )
    match = re.match(
        r"(Studies in Fine Arts are divided into THREE main streams:)\s*"
        r"\(1\)\s*(.*?);\s*\(2\)\s*(.*?);\s*and\s*\(3\)\s*(.*?)\.\s*(Students must.*?attendance\.)\s*(Students are required.*)$",
        description,
    )
    if match:
        data["description_lines"] = [
            match.group(1), f"(1) {match.group(2)}", f"(2) {match.group(3)}",
            f"(3) {match.group(4)}.", match.group(5), match.group(6),
        ]
        data["description_lines"] = [
            re.sub(r"\s*([–—])\s*", r" \1 ", line.replace("�", "—"))
            for line in data["description_lines"]
        ]


def refine_fine_arts(data, extract):
    format_fine_arts_description(data)
    required = data["sections"][1]
    groups = required.get("subsections", [])
    if len(groups) == 2 and len(groups[1].get("text", [])) > 1:
        combined = groups[1]["text"].pop()
        heading, _, body = combined.partition(" ")
        stream_match = re.match(r"Art History and Studio Art Stream\[c\]\s+(.*)", combined)
        if stream_match:
            text = stream_match.group(1)
            groups.append(group("Art History and Studio Art Stream[c]", [text], extract(text)))


def structure_fine_arts_required_streams(data, extract):
    """Recover the three peer stream headings in senior-entry requirements."""
    required = next((section for section in data.get("sections", [])
                     if section.get("title", "").startswith("Required Courses")), None)
    if not required:
        return
    combined = clean(" ".join(
        part for item in required.get("subsections", [])
        for part in [item.get("title", ""), *item.get("text", [])] if part
    ))
    pattern = re.compile(
        r"(?:^|(?<=\s))(Art History and Studio Art Stream|Art History Stream|Studio Art Stream)"
        r"(?:\[[a-z]\])?(?=\s|$)"
    )
    matches = list(pattern.finditer(combined))
    if len(matches) != 3:
        return
    streams = []
    for position, match in enumerate(matches):
        stop = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
        body = combined[match.end():stop].strip()
        body = re.sub(r"^(?:\([a-z]\)\s*)+", "", body, flags=re.IGNORECASE)
        streams.append(group(match.group(1), [body] if body else [], extract(body), required.get("units", "")))
    required["text"], required["codes"], required["subsections"] = [], [], streams


def promote_instruction_heading(data):
    """Promote a leading unlabelled alternative instruction to a visible heading."""
    if data.get("source_file") != "B.A._in_Anthropology":
        return
    for section in data.get("sections", []):
        children = section.get("subsections", [])
        if not children:
            continue
        first = children[0]
        if (not first.get("title") and not first.get("marker") and first.get("text")
                and not first.get("codes") and any(child.get("marker") for child in children[1:])):
            first["title"] = first["text"].pop(0)
            first["keep_heading"] = True


MAJOR_LABEL_RE = re.compile(r"\b([12](?:st|nd))\s+Major\s*:\s*", re.IGNORECASE)


def split_major_label(value):
    """Return a double-major heading and its following prose."""
    match = MAJOR_LABEL_RE.search(value)
    if not match:
        return None
    ordinal = match.group(1).lower()
    rest = value[match.end():].strip()
    next_label = MAJOR_LABEL_RE.search(rest)
    if next_label:
        rest = rest[:next_label.start()].strip()
    boundary = re.search(
        r"\s+(?=(?:[A-Z]{4}\s*\d{4}|Students?\b|At least\b|Any\b|\d+\s+units?\b))",
        rest,
    )
    name = rest[:boundary.start()].strip() if boundary else rest
    body = rest[boundary.end():].strip() if boundary else ""
    return ordinal, f"{match.group(1)} Major: {name}", body


def _partition_major_text(rows, extract):
    leading = []
    majors = []
    current = None
    for row in rows:
        starts = list(MAJOR_LABEL_RE.finditer(row))
        if not starts:
            (current["text"] if current else leading).append(row)
            continue
        prefix = row[:starts[0].start()].strip()
        if prefix:
            (current["text"] if current else leading).append(prefix)
        for position, start in enumerate(starts):
            stop = starts[position + 1].start() if position + 1 < len(starts) else len(row)
            parsed = split_major_label(row[start.start():stop])
            if not parsed:
                continue
            _, title, body = parsed
            current = group(title, [body] if body else [])
            current["keep_heading"] = True
            majors.append(current)
    for major in majors:
        major["codes"] = extract(" ".join(major["text"]))
    return leading, majors


def _strip_embedded_second_major(item):
    """Remove a trailing 2nd Major label while preserving content before it."""
    value = str(item.get("title", ""))
    match = re.search(r"\b2nd\s+Major\s*:\s*", value, re.IGNORECASE)
    if match:
        parsed = split_major_label(value[match.start():])
        item["title"] = value[:match.start()].strip()
        return parsed
    rebuilt = []
    for value in item.get("text", []):
        match = re.search(r"\b2nd\s+Major\s*:\s*", value, re.IGNORECASE)
        if not match:
            rebuilt.append(value)
            continue
        before = value[:match.start()].strip()
        if before:
            rebuilt.append(before)
        item["text"] = rebuilt
        return split_major_label(value[match.start():])
    item["text"] = rebuilt
    for child in item.get("subsections", []):
        found = _strip_embedded_second_major(child)
        if found:
            return found
    return None


def _has_content(item):
    return bool(item.get("title") or item.get("text") or item.get("codes") or item.get("subsections"))


def structure_double_major_headings(data, extract):
    """Make 1st/2nd Major labels peer headings throughout alternate schemes."""
    for section in data.get("sections", []):
        children = section.get("subsections", [])

        # Some source tables already produce peer groups, but leave an
        # instruction attached to the heading itself.
        for child in children:
            parsed = split_major_label(str(child.get("title", "")))
            if parsed and MAJOR_LABEL_RE.match(str(child.get("title", ""))):
                _, title, body = parsed
                child["title"] = title
                if body:
                    child["text"] = [body, *child.get("text", [])]
                child["keep_heading"] = True

        if children and re.match(r"^1st\s+Major\s*:", str(children[0].get("title", "")), re.IGNORECASE):
            second = _strip_embedded_second_major(children[0])
            if second:
                _, second_title, second_body = second
                children[0]["marker"] = ""
                second_group = group(
                    second_title,
                    [second_body] if second_body else [],
                    extract(second_body),
                    children=children[1:],
                )
                children[0]["keep_heading"] = second_group["keep_heading"] = True
                section["subsections"] = children = [children[0], second_group]

        leading, text_majors = _partition_major_text(section.get("text", []), extract)
        if len(text_majors) >= 2 and not children:
            section["text"], section["codes"], section["subsections"] = leading, [], text_majors
            continue

        # Arts double-major tables commonly put the first label in the
        # section row and the second label at the end of the first major's
        # final nested course row.
        if len(text_majors) == 1 and children:
            split_at = None
            second = None
            for position, child in enumerate(children):
                second = _strip_embedded_second_major(child)
                if second:
                    split_at = position
                    break
            if second and split_at is not None:
                first = text_majors[0]
                first["subsections"] = [child for child in children[:split_at + 1] if _has_content(child)]
                _, second_title, second_body = second
                second_group = group(
                    second_title,
                    [second_body] if second_body else [],
                    extract(second_body),
                    children=children[split_at + 1:],
                )
                first["keep_heading"] = second_group["keep_heading"] = True
                section["text"], section["codes"], section["subsections"] = leading, [], [first, second_group]
                continue

        # A few tables put both labels inside the first direct child. Their
        # labels are still row boundaries, so later children belong to the
        # second major.
        if not text_majors and children:
            first_child = children[0]
            leading_child, child_majors = _partition_major_text(first_child.get("text", []), extract)
            if len(child_majors) >= 2:
                first, second = child_majors[:2]
                first["text"] = [*leading_child, *first.get("text", [])]
                first["codes"] = extract(" ".join(first["text"]))
                second["subsections"] = children[1:]
                section["text"], section["codes"], section["subsections"] = [], [], [first, second]


def structure_translation_clusters(data, extract):
    """Recover peer Translation elective-cluster headings from merged prose."""
    labels = (
        "Elective Cluster A: Translation Studies",
        "Electives Cluster A: Translation Studies",
        "Elective Cluster B: Interpreting",
        "Electives Cluster B: Interpreting",
        "Elective Cluster C: Literary Translation",
        "Electives Cluster C: Literary Translation",
        "Other electives",
        "Other Electives",
    )
    label_re = re.compile("|".join(map(re.escape, labels)), re.IGNORECASE)
    for item in walk(data.get("sections", [])):
        rows = list(item.get("text", []))
        combined = clean(" ".join(rows))
        matches = list(label_re.finditer(combined))
        if len(matches) < 2 or item.get("subsections"):
            continue
        intro = combined[:matches[0].start()].strip()
        clusters = []
        for position, match in enumerate(matches):
            stop = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
            body = combined[match.end():stop].strip(" :")
            clusters.append(group(match.group(0), [body] if body else [], extract(body)))
        item["text"] = [intro] if intro else []
        item["codes"] = extract(intro)
        item["subsections"] = clusters


def structure_inline_named_course_groups(data, extract):
    """Split inline non-language/language lists into visible course groups."""
    pattern = re.compile(r"\(([ab])\)\s+(Non-language Courses|Language Courses)\s*:", re.IGNORECASE)
    for item in walk(data.get("sections", [])):
        if item.get("subsections"):
            continue
        combined = clean(" ".join(item.get("text", [])))
        matches = list(pattern.finditer(combined))
        if len(matches) != 2:
            continue
        intro = combined[:matches[0].start()].strip()
        children = []
        for position, match in enumerate(matches):
            stop = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
            body = combined[match.end():stop].strip()
            children.append(group(match.group(2), [body] if body else [], extract(body), marker=f"({match.group(1).lower()})"))
        item["text"] = [intro] if intro else []
        item["codes"] = extract(intro)
        item["subsections"] = children


def structure_chinese_speciality_categories(data, extract):
    """Split merged Chinese speciality lists into the four published areas."""
    names = {
        "1": "Language and Linguistics",
        "2": "Ancient Documents",
        "3": "Classical Literature",
        "4": "Modern Chinese Literature",
    }
    pattern = re.compile(
        r"\(([1-4])\)\s+(Language and Linguistics|Ancient Documents|Classical Literature|Modern Chinese Literature)",
        re.IGNORECASE,
    )
    for item in walk(data.get("sections", [])):
        if item.get("title", "").lower() not in {"speciality courses", "specialty courses"}:
            continue
        children = item.get("subsections", [])
        if len(children) != 1 or children[0].get("subsections"):
            continue
        source = clean(" ".join(children[0].get("text", [])))
        if source.startswith("Language and Linguistics"):
            source = "(1) " + source
        matches = list(pattern.finditer(source))
        if len(matches) != 4:
            continue
        rebuilt = []
        for position, match in enumerate(matches):
            stop = matches[position + 1].start() if position + 1 < len(matches) else len(source)
            body = source[match.end():stop].strip(" :")
            rebuilt.append(group(names[match.group(1)], [body] if body else [], extract(body), marker=f"({match.group(1)})"))
        item["subsections"] = rebuilt


def promote_nested_legacy_notes(data):
    """Restore a standalone [ ] old-course-code footnote from nested rows."""
    rebuilt = []
    for note in data.get("notes", []):
        promoted = []
        retained = []
        for row in note.get("rows", []):
            if (len(row) >= 2 and re.sub(r"\s+", "", str(row[0])) == "[]"
                    and "old course code" in str(row[1]).lower()):
                promoted.append({"marker": "[ ]", "text": clean(" ".join(map(str, row[1:]))),
                                 "subsections": [], "rows": []})
            else:
                retained.append(row)
        note["rows"] = retained
        rebuilt.append(note)
        rebuilt.extend(promoted)
    data["notes"] = rebuilt


def _department_pool(index, subject):
    return sorted(code for code in index if code.startswith(subject + " "))


def add_broad_department_course_tables(data, index):
    """Show the catalogue pool behind broad 'complete N units' rules."""
    pattern = re.compile(
        r"(?:complete|required to complete|take)\s+\d+\s+units?\s+(?:of\s+)?([A-Z]{4})\s+courses?",
        re.IGNORECASE,
    )
    sections = data.get("sections", [])
    for section in sections:
        outside = {
            code for other in sections if other is not section
            for item in walk([other]) for code in item.get("codes", [])
        }
        for item in list(walk([section])):
            prose = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
            match = pattern.search(prose)
            if not match or re.search(r"from\s+\([a-z]\)|as listed below", prose, re.IGNORECASE):
                continue
            subject = match.group(1).upper()
            if any(child.get("title", "").startswith(("Other Eligible", "Eligible "))
                   for child in item.get("subsections", [])):
                continue
            explicit = {code for nested in walk([item]) for code in nested.get("codes", [])}
            eligible = [code for code in _department_pool(index, subject)
                        if code not in outside and code not in explicit]
            if not eligible:
                continue
            item.setdefault("subsections", []).append(group(
                f"Other Eligible {subject} Courses",
                [f"Other {subject} courses may be used to complete this requirement; the stated minimum course rules still apply."],
                eligible,
            ))


def structure_history_streams(data, index, extract, source_text=""):
    """Recover the two senior-entry History streams and their course pools."""
    if data.get("source_file") != "B.A._in_History":
        return
    section = next((item for item in data.get("sections", [])
                    if item.get("title", "").startswith("Streams:")), None)
    if not section:
        return
    children = section.get("subsections", [])
    history_at = next((i for i, item in enumerate(children) if item.get("title") == "History Stream"), None)
    public_at = next((i for i, item in enumerate(children) if item.get("title") == "Public History Stream"), None)
    if history_at is None or public_at is None:
        return

    intro = section["title"].partition(":")[2].strip()
    section["title"] = "Streams"
    section["text"] = [intro] if intro else []

    history_rule = deepcopy(children[history_at + 1])
    history_title = history_rule.get("title", "")
    if ":" in history_title:
        label, instruction = history_title.split(":", 1)
        history_rule["title"] = label
        history_rule["text"] = [instruction.strip(), *history_rule.get("text", [])]
    history_rule["marker"] = ""

    public_rule = deepcopy(children[public_at + 1])
    public_match = re.search(
        r"Public History Stream\s+Required Course\s*:\s*(.*?)\s+Elective Courses(?:\[a\])?\s*:\s*(.*?)\s+\(i\)",
        source_text,
        re.IGNORECASE,
    )
    required_text = public_match.group(1).strip() if public_match else "HIST1700, 1701"
    elective_text = public_match.group(2).strip() if public_match else "Complete 42 units of HIST courses, with:"
    public_required = group("Required Course", [required_text], extract(required_text))
    public_elective = group(
        "Elective Courses[a]",
        [elective_text],
        units="42",
        children=deepcopy(public_rule.get("subsections", [])),
    )

    section["codes"] = []
    section["subsections"] = [
        group("History Stream", units="48", children=[history_rule]),
        group("Public History Stream", units="48", children=[public_required, public_elective]),
    ]
    add_broad_department_course_tables(data, index)


def refine_anthropology_notes(data):
    if any(
        not note.get("marker") and not note.get("text")
        and any(item.get("title") == "Voluntary Concentrations" for item in note.get("subsections", []))
        for note in data.get("notes", [])
    ):
        return
    for note in data.get("notes", []):
        concentrations = [item for item in note.get("subsections", []) if item.get("title") == "Voluntary Concentrations"]
        if concentrations:
            heading = concentrations[0]
            roman = [
                item for item in note.get("subsections", [])
                if re.fullmatch(r"\([ivxlcdm]+\)", item.get("marker", ""), re.I)
            ]
            children = list(heading.get("subsections", [])) or roman
            note["subsections"] = [
                item for item in note.get("subsections", [])
                if item is not heading and item not in children and item not in roman
            ]
            concentration_heading = group(
                "Voluntary Concentrations",
                heading.get("text", []),
                children=children,
            )
            concentration_heading["keep_heading"] = True
            for item in concentration_heading["subsections"]:
                if item.get("codes"):
                    item["text"] = [", ".join(code.replace(" ", "") for code in item["codes"])]
            data.setdefault("notes", []).append({
                "marker": "",
                "text": "",
                "subsections": [concentration_heading],
                "rows": [],
            })
            data["supplementary_note_sections"] = [
                block for block in data.get("supplementary_note_sections", [])
                if block.get("title") != "Voluntary Concentrations"
            ]
            return


def split_inline_note_points(data):
    if data["source_file"] != "B.A._in_Bimodal_Bilingual_Studies":
        return
    for note in data.get("notes", []):
        text = note.get("text", "")
        split_at = text.rfind(": (")
        if split_at < 0:
            continue
        intro, choices = text[:split_at + 1], text[split_at + 2:]
        points = [clean(part).rstrip(";") for part in re.split(r";\s*(?=\((?:[ivx]+|[a-z])\)\s)", choices) if clean(part)]
        if len(points) > 1:
            note["paragraphs"] = [intro, *points]


def refine_chinese_studies(data, extract):
    required = data["sections"][1]
    stream_group = next((item for item in required.get("subsections", [])
                         if item.get("marker") == "(b)" or item.get("title", "").startswith("Stream Courses")), None)
    if not stream_group:
        return

    labels = ("International Stream (IS)", "Chinese Native Stream (CNSS)")

    def normalized_variant(source, label, units=""):
        combined = clean(" ".join([source.get("title", ""), *source.get("text", [])]))
        start = combined.find(label)
        body = combined[start + len(label):].strip(" :") if start >= 0 else combined
        codes = extract(body) or source.get("codes", [])
        return group(label, [body] if body else [], codes, units)

    top_level = required.get("subsections", [])
    native_source = next((item for item in top_level
                          if item is not stream_group and labels[1] in item.get("title", "")), None)
    trailing = []
    if native_source:
        trailing = list(native_source.get("subsections", []))
        top_level.remove(native_source)

    existing = list(stream_group.get("subsections", []))
    international_source = next((item for item in existing if labels[0] in item.get("title", "")), None)
    native_child = next((item for item in existing if labels[1] in item.get("title", "")), None)
    if not international_source:
        international_source = group("", stream_group.get("text", []), stream_group.get("codes", []))
    native_source = native_child or native_source
    streams = [normalized_variant(international_source, labels[0], stream_group.get("units", ""))]
    if native_source:
        streams.append(normalized_variant(native_source, labels[1], stream_group.get("units", "")))
    if len(streams) == 2:
        stream_group["text"], stream_group["codes"], stream_group["subsections"] = [], [], streams
        if trailing:
            position = top_level.index(stream_group) + 1
            top_level[position:position] = trailing

    elective = data["sections"][2]
    combined = clean(" ".join(
        text for item in elective.get("subsections", [])
        for text in [item.get("title", ""), *item.get("text", [])] if text
    ))
    matches = [(label, combined.find(label)) for label in labels]
    if all(position >= 0 for _, position in matches):
        matches.sort(key=lambda entry: entry[1])
        variants = []
        for position, (label, start) in enumerate(matches):
            end = matches[position + 1][1] if position + 1 < len(matches) else len(combined)
            body = combined[start + len(label):end].strip(" :")
            variants.append(group(label, [body] if body else [], extract(body), elective.get("units", "")))
        elective["text"], elective["codes"], elective["subsections"] = [], [], variants


def refine_japanese(data):
    required = data["sections"][1]
    a = required["subsections"][0]
    if a.get("text"):
        pieces = re.split(r"\s+(?=Capstone courses:)", a["text"][0], maxsplit=1)
        if len(pieces) == 2:
            a["text"] = pieces
            a["preserve_colon_lines"] = True
    elective = data["sections"][2]
    without, with_stream = elective["subsections"][:2]
    if without.get("text"):
        elective["text"].append(without["text"].pop(0))
    business = next((item for item in with_stream.get("subsections", []) if item.get("title") == "Business and Management"), None)
    if business:
        for item in business.get("subsections", []):
            optional = [text for text in item.get("text", []) if text == "Non-credit bearing internship programme (optional)"]
            if optional:
                item["text"] = [text for text in item["text"] if text not in optional]
                business["subsections"].append(group(optional[0]))


def refine_linguistics(data):
    required = data["sections"][1]
    groups = required.get("subsections", [])
    if len(groups) == 3 and groups[2].get("subsections"):
        c = groups[2]["subsections"][0]
        c["title"] = groups[2].get("title", "")
        groups[2] = c


def refine_philosophy(data, areas):
    elective = data["sections"][2]
    elective["subsections"] = [area for area in areas if not area["title"].startswith("Area 4:") or area["codes"]]
    for area in elective["subsections"]:
        if re.match(r"Area [123]:", area["title"]):
            area["units"] = "min. 6"
            area["text"] = ["Take at least 6 units from this area."]
        elif area["title"].startswith("Area 5:"):
            area["units"] = "max. 6"
            area["text"] = ["Final-year students may take up to 6 units from this area."]


def nest_concentrations(data):
    if data["source_file"] not in {"B.A._in_Public_Humanities", "B.A._in_Religious_Studies"}:
        return
    section = data["sections"][2]
    groups = section.get("subsections", [])
    if data["source_file"] == "B.A._in_Public_Humanities":
        split_at = next((i for i, item in enumerate(groups) if item.get("title") == "Cultural Management"), None)
        if split_at is None:
            return
        base, remainder = groups[:split_at], groups[split_at:]
        intro = []
        if base[-1].get("text") and base[-1]["text"][0].startswith("Concentrations"):
            source = base[-1]["text"].pop(0)
            intro = [source.removeprefix("Concentrations ")]
    else:
        split_at = next((i for i, item in enumerate(groups) if item.get("title") == "Religion and Culture"), None)
        if split_at is None:
            return
        base, remainder = groups[:split_at], groups[split_at:]
        intro_group = base.pop() if base and not base[-1].get("marker") and (
            not base[-1].get("title") or str(base[-1].get("title", "")).startswith("Students may choose")
        ) else None
        intro = ([intro_group.get("title", "")] if intro_group and intro_group.get("title") else [])
        intro += list(intro_group.get("text", [])) if intro_group else []
        if base[-1].get("text") == ["Concentrations"]:
            base[-1]["text"] = []
    concentrations = group("Concentrations", intro)
    current = None
    for item in remainder:
        if not item.get("marker") and item.get("title"):
            current = item
            current["subsections"] = []
            concentrations["subsections"].append(current)
        elif current is not None:
            current["subsections"].append(item)
    section["subsections"] = [*base, concentrations]


def refine_theology(data, areas):
    required = data["sections"][1]
    if len(required.get("text", [])) >= 2:
        if len(required["text"]) >= 3:
            required["text"] = [required["text"][0], clean(" ".join(required["text"][1:]))]
        required["combine_text_boxes"] = True
        required["preserve_colon_lines"] = True
    elective = data["sections"][2]
    a = elective["subsections"][0]
    a["subsections"] = [group(area["title"], codes=area["codes"]) for area in areas if re.match(r"Area [245]:", area["title"])]
    used = {code for item in walk([required, elective["subsections"][0], elective["subsections"][1]]) for code in item["codes"]}
    options = next((item for item in walk(elective["subsections"]) if item.get("title") == "THEO Course Options"), None)
    if options:
        options["codes"] = [code for code in options["codes"] if code not in used]


def repair_integrated_bba_concentrations(data):
    # Detect the published concentration section by its contents rather than
    # by the outer programme filename.  The same Integrated BBA requirement is
    # embedded as the second degree of several double-degree programmes.
    section = next((item for item in data["sections"] if "Elective Courses (Concentration)" in item["title"]), None)
    if not section:
        return
    groups = section["subsections"]
    h_index = next((i for i, item in enumerate(groups) if item.get("marker") == "(h)"), None)
    if h_index is None or h_index + 1 >= len(groups):
        return
    h_group, first_choice = groups[h_index], groups[h_index + 1]
    if first_choice.get("marker") != "(i)" or first_choice.get("title"):
        return
    nested = first_choice.get("subsections", [])
    general_index = next((i for i, item in enumerate(nested)
                          if item.get("marker") == "(i)" and item.get("title") == "General Business"), None)
    if general_index is None:
        return
    general = nested[general_index]
    h_choices = nested[:general_index]
    general_choices = nested[general_index + 1:]
    first_choice["subsections"] = []
    h_group["subsections"] = [first_choice, *h_choices]
    general["subsections"] = general_choices
    section["subsections"] = groups[:h_index + 1] + [general] + groups[h_index + 2:]


def structure_accountancy_streams(data):
    if data["source_file"] != "B.B.A._in_Professional_Accountancy":
        return
    if data.get("additional_requirements"):
        data["sections"][2]["title"] = "Elective Courses (Without Stream)"


def structure_behm_concentrations(data, extract):
    if data["source_file"] != "B.Sc._in_Biotechnology,_Entrepreneurship_and_Healthcare_Management":
        return
    section = data["sections"][2]
    for area in section.get("subsections", []):
        combined = clean(" ".join([area.get("title", ""), *area.get("text", [])]))
        match = re.match(r"(.*?)\s+Required Courses:\s*\(([^)]*?units?)\)\s*(.*?)\s+Elective Courses:\s*(.*)$", combined)
        if not match:
            continue
        area_title, required_units, required_text, elective_text = match.groups()
        area["title"], area["text"], area["codes"] = area_title, [], []
        elective_units = re.search(r"Choose\s+([\d-]+)\s+units", elective_text, re.I)
        area["subsections"] = [
            group("Required Courses", [required_text], extract(required_text), required_units.replace(" units", "")),
            group("Elective Courses", [elective_text], extract(elective_text), elective_units.group(1) if elective_units else ""),
        ]


def promote_offering_labels(data):
    for item in walk(data["sections"]):
        if item.get("title", "").startswith("Students can also take the following elective courses offered by"):
            item["keep_heading"] = True
        elif not item.get("title") and item.get("text") and item["text"][0].startswith("Students can also take the following elective courses offered by"):
            item["title"] = item["text"].pop(0)
            item["keep_heading"] = True


def refine_quantitative_finance(data):
    if data["source_file"] != "B.Sc._in_Quantitative_Finance":
        return
    required_e = next(item for item in data["sections"][2]["subsections"] if item.get("marker") == "(e)")
    if required_e.get("title"):
        required_e["text"].insert(0, required_e["title"])
        required_e["title"] = ""
    business = next(item for item in data["sections"][3]["subsections"] if item.get("marker") == "(b)")
    if business.get("title", "").startswith("At least 12 units of Business courses"):
        business["keep_heading"] = True
    elif business.get("text") and business["text"][0].startswith("At least 12 units of Business courses"):
        business["title"] = business["text"].pop(0)
        business["keep_heading"] = True


def separate_second_degree(data):
    if data["source_file"] != "B.B.A._(Integrated_BBA_Programme)_and_Juris_Doctor":
        return
    split_at = next((i for i, note in enumerate(data.get("notes", []))
                     if note.get("marker") == "1." and note.get("text", "").startswith("Required Courses:")), None)
    if split_at is not None:
        data["notes"] = data["notes"][:split_at]
    for note in data.get("notes", []):
        note["text"] = note.get("text", "").split("2nd Degree: Juris Doctor", 1)[0].strip()
    for block in data.get("additional_requirements", []):
        if block["title"] == "2nd Degree: Juris Doctor":
            block["description"] = re.sub(r"^Programme Requirement\s*", "", block.get("description", ""))
            if block.get("total_units"):
                first_degree = str(data.get("total_units", ""))
                data["total_units"] = f"{first_degree} + {block['total_units']}" if first_degree else block["total_units"]


def split_merged_english_education_notes(data):
    if data["source_file"] != "B.A._(English_Studies)_and_B.Ed._(English_Language_Education)":
        return
    for position, note in enumerate(data.get("notes", [])):
        text = note.get("text", "")
        if note.get("marker") or not text.startswith("1. 2. "):
            continue
        text = text.removeprefix("1. 2. ")
        boundary = text.find("classification.")
        if boundary < 0:
            return
        boundary += len("classification.")
        data["notes"][position:position + 1] = [
            {"marker": "1.", "text": text[:boundary], "subsections": [], "rows": []},
            {"marker": "2.", "text": text[boundary:].strip(), "subsections": [], "rows": []},
        ]
        return


def structure_inline_note_points(data):
    """Turn merged i)/ii) note prose into the same nested layout as CS notes."""
    point_pattern = re.compile(r"(?<![A-Za-z])(?:\(([ivxlcdm]+)\)|([ivxlcdm]+)\))\s*", re.IGNORECASE)
    for note in data.get("notes", []):
        for point in note.get("subsections", []):
            if point.get("title", "").startswith("Other admittees except those specified above"):
                point["text"] = [clean(" ".join([point["title"], *point.get("text", [])]))]
                point["title"] = ""
                point["heading_as_text"] = True
        text = note.get("text", "")
        matches = list(point_pattern.finditer(text))
        if not matches:
            continue
        first = matches[0]
        prefix = text[:first.start()].strip()
        if prefix and not prefix.endswith(":"):
            continue
        points = []
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            body = clean(text[match.end():end])
            if body:
                numeral = (match.group(1) or match.group(2)).lower()
                points.append(group("", [body], marker=f"({numeral})"))
        if points:
            note["text"] = prefix
            existing = note.get("subsections", [])
            existing_markers = {item.get("marker") for item in existing}
            note["subsections"] = points + [item for item in existing if item.get("marker") not in {p["marker"] for p in points}]


def structure_early_childhood_required(data, extract):
    if data["source_file"] != "B.Ed._in_Early_Childhood_Education":
        return
    section = data["sections"][1]
    source = section.get("subsections", [])[0]
    if source.get("title") != "Core Courses in Early Childhood Education":
        return
    rebuilt = [group(source["title"], [source["text"][0]], extract(source["text"][0]), "40")]
    for text, title, units in zip(source["text"][1:], ("Research Experience", "Teaching Practice"), ("6", "10")):
        body = re.sub(rf"^{re.escape(title)}\s*", "", text)
        rebuilt.append(group(title, [body], extract(body), units))
    section["subsections"] = rebuilt
    section["units"] = "56"


def subject_codes(index, subjects, *, minimum=1000, maximum=4999, excluded=()):
    excluded = set(excluded)
    return sorted(code for code in index if code[:4] in subjects
                  and minimum <= int(code[5:]) <= maximum and code not in excluded)


def structure_mathematics_education(data, index, extract):
    if data["source_file"] != "B.Ed._in_Mathematics_and_Mathematics_Education":
        return
    package = data["sections"][0]
    if package.get("text", [])[:3:2] == ["Faculty of Education", "Faculty of Science"]:
        package["text"], package["codes"] = [], []
        # The two alternatives have different published unit values; the
        # programme total uses the package applicable to the admitting faculty.
        education_courses, science_courses = "EDUC2120, 3330", "MATH1010/1018"
        package["subsections"] = [
            group("Faculty of Education", [education_courses], extract(education_courses), "6"),
            group("Faculty of Science", [science_courses], extract(science_courses), "3"),
        ]
    elective = data["sections"][2]
    if elective.get("text") == ["Subject Knowledge"]:
        elective["text"] = []
        elective["subsections"] = [group("Subject Knowledge", units=elective.get("units", "15"),
                                                  children=elective["subsections"])]
    # Older Word exports place alternatives (A)/(B) beside 3(a), although
    # their text explicitly says they belong under 3(a)(ii).
    for container in walk([elective]):
        children = container.get("subsections", [])
        parent = next((item for item in children if item.get("marker") == "(a)"), None)
        roman_ii = next((item for item in parent.get("subsections", [])
                         if item.get("marker", "").lower() == "(ii)"), None) if parent else None
        alternatives = [item for item in children if item.get("marker") in {"(A)", "(B)"}]
        if roman_ii and alternatives:
            roman_ii["subsections"].extend(alternatives)
            container["subsections"] = [item for item in children if item not in alternatives]

    groups = [
        ("Group 1: CHEM, EESC, LSCI, PHYS", subject_codes(index, {"CHEM", "EESC", "PHYS"}, excluded={
            "EESC 2009", "EESC 2019", "EESC 2119", "EESC 2129", "EESC 2517", "EESC 2909",
            "EESC 3130", "EESC 3417", "EESC 3522", "EESC 3530", "EESC 3900", "EESC 4119",
            "EESC 4129", "EESC 4810", "EESC 4820", "EESC 4909",
        }) + [code for code in ("LSCI 1001", "LSCI 1002", "LSCI 2003") if code in index]),
        ("Group 2: DSPS, RMSC, STAT", subject_codes(index, {"DSPS", "RMSC", "STAT"}, excluded={
            "DSPS 3801", "DSPS 4801", "DSPS 4802",
        })),
        ("Group 3: DOTE, ECON", subject_codes(index, {"DOTE", "ECON"})),
        ("Group 4: AIST, CSCI, IERG", subject_codes(index, {"CSCI", "IERG"}) +
         subject_codes(index, {"AIST"}, minimum=2000)),
    ]
    option = next((item for item in walk([elective]) if item.get("marker") in {"(II)", "(B)"}), None)
    if option and not option.get("subsections"):
        option["text"], option["codes"] = [], []
        option["subsections"] = [group(title, codes=codes) for title, codes in groups]

    # The 2024 scheme publishes the same idea directly as four named subject
    # areas instead of wrapping it in alternatives (A)/(B).
    legacy = next((item for item in walk([elective])
                   if item.get("marker", "").lower() == "(ii)"
                   and "one of the following subject areas" in item.get("title", "").lower()), None)
    if legacy and not legacy.get("subsections"):
        subjects = re.findall(r"\b(?:CSCI|ECON|PHYS|STAT)\b", legacy.get("title", ""))
        legacy["codes"] = []
        legacy["subsections"] = [
            group(subject, codes=subject_codes(index, {subject})) for subject in dict.fromkeys(subjects)
        ]


def structure_science_course_choices(data, extract):
    labels = re.compile(r"^(Chemistry|Life Science|Physics) Courses?(?:\[[^]]+\])?:$", re.IGNORECASE)
    for item in walk(data["sections"]):
        texts = item.get("text", [])
        if len(texts) < 4:
            continue
        children = []
        position = 0
        while position + 1 < len(texts) and labels.fullmatch(texts[position]):
            title = texts[position].rstrip(":")
            course_text = texts[position + 1]
            if not re.search(r"[A-Z]{4}\s*\d{4}", course_text):
                break
            children.append(group(title, [course_text], extract(course_text)))
            position += 2
        if len(children) >= 2 and position == len(texts):
            item["text"], item["codes"] = [], []
            item["subsections"] = children


def structure_stream_introductions(data):
    for item in walk(data["sections"]):
        if item.get("title") or not item.get("text"):
            continue
        first = item["text"][0]
        for label in ("Streams", "Computational Data Science"):
            if first.startswith(label + " "):
                item["title"] = label
                item["text"][0] = first[len(label):].strip()
                item["keep_heading"] = True
                break


def structure_electronic_engineering_guidance(data, extract):
    if data["source_file"] != "B.Eng._in_Electronic_Engineering":
        return
    note = next((item for item in data.get("notes", []) if item.get("marker") == "3."), None)
    if not note:
        return
    text = note.get("text", "")
    matches = list(re.finditer(r"(Professional Engineering|Research|Entrepreneurship)\(a\)\s*", text))
    if len(matches) != 3:
        return
    note["text"] = text[:matches[0].start()].strip()
    sections = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        body = text[match.end():end]
        first, separator, second = body.partition("(b)")
        rows = [f"(a) {clean(first)}"]
        if separator:
            rows.append(f"(b) {clean(second)}")
        sections.append(group(match.group(1), rows, extract(body)))
    note["subsections"] = sections


def structure_diplomacy_labels(data, extract):
    if data["source_file"] != "B.S.Sc._in_Diplomacy_and_International_Studies":
        return
    core = data["sections"][1]["subsections"][0]
    core_children = []
    for position in range(0, len(core.get("text", [])), 2):
        pair = core["text"][position:position + 2]
        if len(pair) == 2 and not extract(pair[0]) and extract(pair[1]):
            core_children.append(group(pair[0], [pair[1]], extract(pair[1])))
    if core_children:
        core["text"], core["codes"], core["subsections"] = [], [], core_children
    elective = data["sections"][2]
    rows = elective.get("text", [])
    children = []
    if rows and not extract(rows[0]):
        children.append(group(rows[0]))
        rows = rows[1:]
    for position in range(0, len(rows), 2):
        pair = rows[position:position + 2]
        if len(pair) == 2 and not extract(pair[0]) and extract(pair[1]):
            children.append(group(pair[0], [pair[1]], extract(pair[1])))
    if children:
        elective["text"], elective["codes"], elective["subsections"] = [], [], children


def nest_law_streams(data):
    if data["source_file"] != "LL.B._-_Bachelor_of_Laws_Programme":
        return
    elective = data["sections"][1]
    groups = elective.get("subsections", [])
    stream = next((item for item in groups if item.get("title") == "Streams"), None)
    chinese = next((item for item in groups if item.get("title") == "Chinese Law"), None)
    global_law = next((item for item in groups if item.get("title") == "Global Law"), None)
    if not stream or not chinese or not global_law:
        return
    intro = groups[groups.index(stream) + 1:groups.index(chinese)]
    chinese_index, global_index = groups.index(chinese), groups.index(global_law)
    chinese["subsections"] = groups[chinese_index + 1:global_index]
    global_law["subsections"] = groups[global_index + 1:]
    stream["text"] = [text for item in intro for text in item.get("text", [])]
    stream["subsections"] = [chinese, global_law]
    elective["subsections"] = groups[:groups.index(stream)] + [stream]


def resolve_history(data, index, extract):
    section = data["sections"][2]
    # Some older Word exports merge the (a) and (b) minima into one row.
    # Recover the two published rules from their own unit phrases instead of
    # relying on the exported cell boundaries.
    merged = next((item for item in section.get("subsections", [])
                   if item.get("marker") == "(a)" and item.get("title") == "(b)"), None)
    if merged:
        combined = clean(" ".join(merged.get("text", [])))
        matches = list(re.finditer(r"at least\s+(\d+)\s+units\s+from\s*:\s*", combined, re.I))
        if len(matches) >= 2:
            intro = combined[:matches[0].start()].strip()
            rebuilt = []
            for position, match in enumerate(matches[:2]):
                stop = matches[position + 1].start() if position + 1 < 2 else len(combined)
                body = combined[match.end():stop].strip(" ;")
                rebuilt.append(group(
                    f"At least {match.group(1)} units from the following",
                    [body] if body else [], extract(body), match.group(1),
                    marker=f"({chr(97 + position)})",
                ))
            section["text"] = ([intro] if intro else []) + section.get("text", [])
            position = section["subsections"].index(merged)
            section["subsections"][position:position + 1] = rebuilt
    used = {code for earlier in data["sections"][:2] for item in walk([earlier]) for code in item["codes"]}
    minima = {code for item in walk(section["subsections"]) for code in item["codes"]}
    remaining = [code for code in index if code.startswith("HIST ") and code not in used | minima]
    section["subsections"].append(group("Other Eligible History Courses", [
        "These additional HIST courses may count towards the 45-unit elective requirement. The minimum requirements in (a) and (b) still apply; courses listed in sections 1 and 2 are excluded."
    ], remaining))


def resolve_linguistics(data, areas, index, extract):
    a, b = data["sections"][2]["subsections"]
    excluded = {"LING 3405", "LING 3406"}
    a["excluded_codes"] = sorted(excluded)
    a["codes"] = []
    for area in areas:
        # The course-list row has BMLB3003, but both degree schemes on the same
        # source page and the course catalogue identify it as BMBL3003.
        area["codes"] = [code.replace("BMLB ", "BMBL ") for code in area["codes"] if code not in excluded]
    a["subsections"] = areas
    b["excluded_codes"] = extract(" ".join(b["text"]))
    b["codes"] = []
    # Only language-subject offerings qualify, not courses merely about language.
    languages = {"ARAB", "FREN", "GERM", "HKSL", "ITAL", "JASP", "KORE", "RUSS", "SPAN", "THAI"}
    for subject in sorted(languages):
        codes = [code for code, info in index.items() if code[:4] == subject
                 and code not in b["excluded_codes"] and int(code[5:]) < 5000
                 and not re.fullmatch(r"1(?:\.0+)?", str(info.get("unit", "")))
                 and re.search(r"(?:Arabic|French|German|Hong Kong Sign Language|Italian|Japanese|Korean|Russian|Spanish|Thai) (?:[IVX]+\b|Conversation|Reading|Writing|Composition|Communication)|(?:Spoken|Business|Comprehensive|Practical) Japanese", str(info.get("title", "")))]
        if codes:
            b["subsections"].append(group(f"{subject} Language Courses", codes=codes))
    b["text"].append("The tables show identifiable undergraduate language-learning options, not an exhaustive approved list. Choose courses in only one or two languages and check eligibility with the programme. Culture-only courses and 1-unit tasters are not included. Students whose first language is not Chinese should also see Explanatory Note 3.")


def resolve_music(data, areas, extract):
    required = data["sections"][1]
    mandatory = {code for item in required["subsections"] if item["marker"] in {"(a)", "(c)", "(d)"} for code in item["codes"]}
    section = data["sections"][2]
    section["text"].append("The lists below exclude universally required courses. Courses that are alternatives in section 2 remain listed, but cannot also count here if you use them to fulfil section 2.")
    for area in areas:
        area["codes"] = [code for code in area["codes"] if code not in mandatory]
        if area["title"].startswith("Area 3:"):
            area["text"] = ["Take at least one course from this area."]
        elif area["title"].startswith("Area 4:"):
            area["text"] = ["Take at least two courses from this area."]
        elif area["title"].startswith("Area 2C:"):
            area["text"] = ["Up to six units from this area may count towards the elective requirement."]
            area["units"] = "max. 6"
    section["subsections"] = [area for area in areas if area["codes"] and not area["title"].startswith("Area 1:")]
    option = required["subsections"][-1]
    text = " ".join(option["text"])
    matches = list(re.finditer(r"\((\d)\) (Composition|Performance|Research) Supporting courses:\s*", text))
    if len(matches) == 3:
        children = []
        for i, match in enumerate(matches):
            content = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
            supporting, capstone = content.split("Capstone courses:", 1)
            children.append(group(match.group(2), units="11" if match.group(2) == "Composition" else "10", marker=f"({match.group(1)})", children=[
                group("Supporting Courses", [supporting.strip()], extract(supporting)),
                group("Capstone Courses", [capstone.strip()], extract(capstone)),
            ]))
        option["text"], option["codes"], option["subsections"] = [], [], children


def structure_medicine_group_lists(data, extract):
    """Recover Group A/B lists that Word exported as one continuous cell."""
    if data["source_file"] not in {"B.Sc._in_Community_Health_Practice", "B.Sc._in_Public_Health"}:
        return
    section = data["sections"][1 if data["source_file"].endswith("Community_Health_Practice") else 2]
    combined = clean(" ".join([*section.get("text", []), *[
        text for child in section.get("subsections", []) for text in child.get("text", [])
    ]]))
    a_labels = list(re.finditer(r"Group A(?:\s*\(([^)]*)\))?:", combined))
    b_labels = list(re.finditer(r"Group B:", combined))
    if not a_labels or not b_labels:
        return
    a_match, b_match = a_labels[-1], b_labels[-1]
    if b_match.start() < a_match.end():
        return
    intro = combined[:a_match.start()].strip()
    a_text, b_text = combined[a_match.end():b_match.start()].strip(), combined[b_match.end():].strip()
    group_a = group("Group A" + (f" ({a_match.group(1)})" if a_match.group(1) else ""), [a_text], extract(a_text))
    group_b = group("Group B", [b_text], extract(b_text))
    # Public Health publishes two alternative capstone combinations inside B.
    roman = list(re.finditer(r"(?<![A-Za-z])([ivxlcdm]+)\)\s*", b_text, re.I))
    if len(roman) >= 2:
        group_b["text"] = [b_text[:roman[0].start()].strip()]
        group_b["codes"] = []
        for position, match in enumerate(roman):
            end = roman[position + 1].start() if position + 1 < len(roman) else len(b_text)
            body = b_text[match.end():end].strip(" ;")
            group_b["subsections"].append(group("", [body], extract(body), marker=f"({match.group(1).lower()})"))
    section["text"], section["codes"], section["subsections"] = ([intro] if intro else []), [], [group_a, group_b]


def structure_medicine_concentrations(data, extract):
    """Nest concentration labels above their alternatives for Medicine degrees."""
    stem = data["source_file"]
    if stem == "B.Sc._in_Biomedical_Sciences":
        section = data["sections"][2]
        choice = section.get("subsections", [])[0]
        children = choice.get("subsections", [])
        if len(children) != 6:
            return
        labels = ["Biomedical Research[d]", "Strategic Management and Entrepreneurship", "Health Services and Consultation"]
        areas = []
        for position, label in enumerate(labels):
            pair = children[position * 2:position * 2 + 2]
            for child in pair:
                child["text"] = [re.sub(r"\s*Concentration Area [A-C]:.*$", "", text).strip() for text in child.get("text", [])]
                child["text"] = [text for text in child["text"] if text]
            units = "15" if position == 1 else "14"
            areas.append(group(f"Concentration Area {chr(65 + position)}: {label}", units=units, children=pair))
        choice["text"] = [text for text in choice.get("text", []) if not text.startswith("Concentration Area")]
        choice["codes"], choice["subsections"], choice["units"] = [], areas, "14-15"
        section["units"] = "32"
    elif stem == "Bachelor_of_Pharmacy":
        choice = data["sections"][2].get("subsections", [])[0]
        children = choice.get("subsections", [])
        if len(children) != 3:
            return
        clerkship = children[:2]
        research = [children[2]]
        for child in clerkship + research:
            child["text"] = [re.sub(r"\s*Area of Concentration:.*$", "", text).strip() for text in child.get("text", [])]
            child["text"] = [text for text in child["text"] if text]
        choice["text"] = [text for text in choice.get("text", []) if not text.startswith("Area of Concentration:")]
        choice["subsections"] = [
            group("Area of Concentration: Pharmacy Clerkship", units="6", children=clerkship),
            group("Area of Concentration: Research", units="6", children=research),
        ]


def structure_science_faculty_package(data, extract):
    if data.get("faculty") != "Science" or not data.get("sections"):
        return
    def split_groups(item):
        original_children = list(item.get("subsections", []))
        source_parts = [item.get("title", ""), *item.get("text", [])]
        consumed = []
        retained = []
        for child in original_children:
            if (not child.get("marker") and
                    (child.get("title", "").lower().startswith(("a course from", "one course from"))
                     or re.search(r"Group [A-E]", " ".join(child.get("text", []))))):
                consumed.extend([child.get("title", ""), *child.get("text", [])])
            else:
                retained.append(child)
        combined = clean(" ".join([*source_parts, *consumed]))
        matches = list(re.finditer(r"\bGroup\s+([A-E])\s*:?​?", combined, re.I))
        if len(matches) < 2:
            return False
        choice = re.search(r"\b(?:A|One) course from the following\s*:?​?", combined, re.I)
        first = matches[0]
        prefix = combined[:first.start()].strip(" :")
        # A parent title such as “Two courses from the following” remains the
        # parent heading; the generic Faculty Package title does not.
        old_title = item.get("title", "")
        if old_title and old_title != "Faculty Package" and prefix.startswith(old_title):
            prefix = old_title
        children = []
        alternative_children = []
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
            body = combined[match.end():end].strip()
            body = re.sub(r"(?:A|One) course from the following\s*:?​?", "", body, flags=re.I).strip()
            target = group(f"Group {match.group(1).upper()}", [body] if body else [], extract(body))
            if choice and match.start() > choice.start():
                alternative_children.append(target)
            else:
                children.append(target)
        if alternative_children:
            label = clean(choice.group(0)).rstrip(":") if choice else "A course from the following"
            children.append(group(label, children=alternative_children))
        item["title"] = prefix if item is not section else section.get("title", "")
        item["text"], item["codes"], item["subsections"] = [], [], children + retained
        return True

    candidates = [item for item in data["sections"] if "Faculty Package" in item.get("title", "")]
    candidates += [item for block in data.get("additional_requirements", [])
                   for item in block.get("sections", []) if "Faculty Package" in item.get("title", "")]
    for section in candidates:
        if not split_groups(section):
            for child in section.get("subsections", []):
                split_groups(child)


def structure_biochemistry_lists(data, extract):
    if data["source_file"] != "B.Sc._in_Biochemistry":
        return
    item = data["sections"][2].get("subsections", [])[1]
    combined = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
    all_matches = list(re.finditer(r"List ([ABC])\s*:?", combined))
    b_position = next((i for i, match in enumerate(all_matches) if match.group(1) == "B"), None)
    c_position = next((i for i, match in enumerate(all_matches) if match.group(1) == "C"), None)
    if b_position is None or c_position is None:
        return
    a_candidates = [match for match in all_matches[:b_position] if match.group(1) == "A"]
    if not a_candidates:
        return
    matches = [a_candidates[-1], all_matches[b_position], all_matches[c_position]]
    intro = combined[:matches[0].start()].strip()
    children = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
        body = combined[match.end():end].strip()
        children.append(group(f"List {match.group(1)}", [body], extract(body)))
    item["title"], item["text"], item["codes"], item["subsections"] = "", [intro], [], children


def structure_campus_course_labels(data, extract):
    if data["source_file"] != "B.Sc._in_Mathematical_Sciences_and_Artificial_Intelligence_Double_Major_Programme":
        return
    label_pattern = re.compile(r"(?:Courses\s+)?offered by CUHK(?:\(SZ\))?:", re.I)
    for item in walk(data["sections"]):
        rebuilt = []
        children = list(item.get("subsections", []))
        pending = None
        for text in item.get("text", []):
            if pending is not None and not label_pattern.search(text):
                pending["text"].append(text)
                pending["codes"] = list(dict.fromkeys(pending["codes"] + extract(text)))
                pending = None
                continue
            matches = list(label_pattern.finditer(text))
            if not matches:
                rebuilt.append(text)
                continue
            prefix = text[:matches[0].start()].strip()
            if prefix:
                rebuilt.append(prefix)
            for position, match in enumerate(matches):
                end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
                body = text[match.end():end].strip()
                campus = "CUHK(SZ)" if "(SZ)" in match.group(0).upper() else "CUHK"
                child = group(f"Courses offered by {campus}", [body] if body else [], extract(body))
                children.append(child)
                if not body:
                    pending = child
        if children != item.get("subsections", []):
            item["text"], item["codes"], item["subsections"] = rebuilt, [], children


def refine_chinese_medicine_description(data, path):
    if data["source_file"] != "Bachelor_of_Chinese_Medicine":
        return
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    start = text.find("The Programme consists")
    end = text.find("Students are required to complete a minimum", start)
    if start < 0 or end < 0:
        return
    end_sentence = re.search(r"Students are required to complete a minimum of 157 units of courses as follows:", text[start:])
    if not end_sentence:
        return
    description = text[start:start + end_sentence.end()].strip()
    pre = description.find("Pre-clinical Programme")
    clinical = description.find("Clinical Programme", pre + 1)
    data["description_lines"] = [
        description[:pre].strip(),
        "Pre-clinical Programme",
        description[pre + len("Pre-clinical Programme"):clinical].strip(),
        "Clinical Programme",
        description[clinical + len("Clinical Programme"):].strip(),
    ]


def refine_articulated_mathematics(data, path, extract):
    if data["source_file"] != "Articulated_Bachelor_of_Science_Ph.D._Programme_in_Mathematical_Sciences":
        return
    data["requirement_title"] = "Bachelor of Science in Mathematical Sciences"
    data["description"] = re.sub(r"^Bachelor of Science in Mathematical Sciences\s*", "", data["description"])
    item_i = data["sections"][2]["subsections"][0]["subsections"][0]
    parent = data["sections"][2]["subsections"][0]
    numbered = [child for child in parent["subsections"] if re.fullmatch(r"\(\d+\)", child.get("marker", ""))]
    parent["subsections"] = [child for child in parent["subsections"] if child not in numbered]
    for child in numbered:
        if child.get("title"):
            child["text"].insert(0, child["title"])
            child["title"] = ""
    item_i["subsections"] = numbered

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    table = next(table for table in soup.find_all("table") if not table.find("table") and
                 "Doctor of Philosophy in Mathematical Sciences" in clean(table.get_text(" ", strip=True)) and
                 "Pre-candidacy" in clean(table.get_text(" ", strip=True)))
    body = table.find("tbody", recursive=False) or table
    rows = body.find_all("tr", recursive=False)
    values = [[clean(cell.get_text("", strip=False)) for cell in row.find_all("td", recursive=False)] for row in rows]

    def scheme(start_title, end_title, total):
        start = next(i for i, cells in enumerate(values) if start_title in " ".join(cells)) + 1
        end = next((i for i in range(start, len(values)) if end_title and end_title in " ".join(values[i])), len(values))
        roots, stack = [], {}
        description = []
        for cells in values[start:end]:
            nonempty = [value for value in cells if value]
            if not nonempty:
                continue
            marker = next((value for value in nonempty if re.fullmatch(r"\d+\.|\([a-z]\)|\([ivxlcdm]+\)", value, re.I)), "")
            if "Total:" in " ".join(nonempty):
                break
            if nonempty[0] in {"Units", "Remarks:"}:
                continue
            unit = next((value for value in reversed(nonempty) if re.fullmatch(r"\d+(?:-\d+)?", value)), "")
            body_parts = [value for value in nonempty if value not in {marker, unit}]
            body = clean(" ".join(body_parts))
            if not marker:
                target = stack.get(3) or stack.get(2) or stack.get(1)
                if target:
                    target["text"].append(body)
                    target["codes"] = list(dict.fromkeys(target["codes"] + extract(body)))
                elif body and body != "Units":
                    description.append(body)
                continue
            level = 1 if re.fullmatch(r"\d+\.", marker) else (2 if re.fullmatch(r"\([a-hj-uw-z]\)", marker, re.I) else 3)
            node = group(body.rstrip(":"), units=unit, marker=marker)
            if level == 1:
                roots.append(node)
            else:
                parent_node = stack.get(level - 1)
                if parent_node:
                    parent_node["subsections"].append(node)
                else:
                    roots.append(node)
            stack[level] = node
            for deeper in range(level + 1, 4):
                stack.pop(deeper, None)
        block_notes = []
        if start_title == "Pre-candidacy":
            remarks = next((i for i in range(start, end) if "Remarks:" in " ".join(values[i])), None)
            if remarks is not None:
                for cells in values[remarks + 1:end]:
                    nonempty = [value for value in cells if value]
                    if len(nonempty) >= 2 and re.fullmatch(r"\d+\.", nonempty[0]):
                        block_notes.append({"marker": nonempty[0], "text": clean(" ".join(nonempty[1:])),
                                            "subsections": [], "rows": []})
        return {"title": f"Doctor of Philosophy in Mathematical Sciences — {start_title}",
                "description": " ".join(description), "total_units": total, "sections": roots, "notes": block_notes}

    data["notes"] = data.get("notes", [])[:8]
    data["additional_requirements"] = [
        scheme("Pre-candidacy", "Post-candidacy", "27"),
        scheme("Post-candidacy", "", "78"),
    ]


def clean_presentation(data):
    roots = list(data["sections"])
    roots += [item for block in data.get("additional_requirements", []) for item in block["sections"]]
    roots += [item for note in data.get("notes", []) for item in note.get("subsections", [])]
    for item in walk(roots):
        title = item.get("title", "")
        contains_course_code = bool(re.search(r"\b[A-Z]{3,4}\s*\d{4}\b", title))
        if not item.get("keep_heading") and (contains_course_code or len(title) > 160 or (re.match(r"^(?:Students? |Any |At least |Choose |Remaining |The remaining |Six courses|Nine courses)", title) and len(title) > 80)):
            item["text"].insert(0, title)
            item["title"] = ""
            item["heading_as_text"] = True
        separated = []
        for text in item.get("text", []):
            # Preserve the original course expression and punctuation, but put
            # the leading instruction in a separate visual box.
            match = re.match(r"^(.{3,}?[:])\s*((?:\(?[A-Z]{4}\s*\d{4}).*)$", text)
            if match and not item.get("preserve_colon_lines") and not re.search(r"[A-Z]{4}\s*\d{4}", match.group(1)):
                separated.extend([match.group(1), match.group(2)])
            else:
                separated.append(text)
        item["text"] = list(dict.fromkeys(text for text in separated if text.strip()))


def resolve_named_areas(data, path, areas, index, extract):
    stem = data["source_file"]
    if stem not in {"B.A._in_Public_Humanities", "B.A._in_Religious_Studies", "B.A._in_Theology"}:
        return
    shared = list(areas)
    if stem != "B.A._in_Public_Humanities":
        shared += source_areas(path.parent / "B.A._in_Public_Humanities.html", extract)
    if stem == "B.A._in_Public_Humanities":
        shared += source_areas(path.parent / "B.A._in_Religious_Studies.html", extract)
    for item in list(walk(data["sections"])):
        text = " ".join([item["title"], *item["text"]])
        names = [name for name in ("Cultural Studies", "Cultural Management", "Religious Studies") if f"{name} Areas" in text]
        if names and not re.search(r"[A-Z]{4}\s*\d{4}", re.split(r"except|excluding", text)[0]) and not item["subsections"]:
            selected = [area for area in shared if any(area["title"].startswith(name + " Area") for name in names)]
            excluded = explicit_exclusions(text, extract)
            lower = 2000 if "2000" in text else 0
            if selected:
                item["codes"] = []
                item["excluded_codes"] = sorted(excluded)
                item["subsections"] = [group(area["title"], codes=[code for code in area["codes"] if code not in excluded and int(code[5:]) >= lower]) for area in selected]
        if "Theological Studies Areas 1 and 3" in text:
            item["codes"] = []
            item["subsections"] = [group(area["title"], codes=[code for code in area["codes"] if int(code[5:]) >= 2000]) for area in areas if re.match(r"Area [13]:", area["title"])]
        if "All THEO courses other than" in text:
            cultural = {code for area in shared if area["title"].startswith("Cultural Studies Area") for code in area["codes"]}
            item["codes"] = []
            item["subsections"] = [group("THEO Course Options", ["Only courses not used in sections 2, 3(a), or 3(b) can count here."], [code for code in index if code.startswith("THEO ")]),
                group("CURE Courses Outside Cultural Studies Areas", codes=[code for code in index if code.startswith("CURE ") and code not in cultural])]


def resolve_level_rules(data, index, extract):
    pattern = re.compile(r"((?:[A-Z]{4}(?:/| and ))*[A-Z]{4})\s+courses?\s+at\s+(\d000)(?:\s+(or|and)\s+(\d000))?\s*(or above|and above)?\s*level(?:\s*(or above|and above))?")
    for item in list(walk(data["sections"])):
        if item["subsections"]:
            continue
        text = " ".join([item["title"], *item["text"]])
        if re.search(r"from .*Areas|from Educational Core", text):
            continue
        resolved = set()
        for match in pattern.finditer(text):
            subjects = re.split(r"/| and ", match.group(1))
            levels = {int(match.group(2)) // 1000}
            if match.group(4):
                levels.add(int(match.group(4)) // 1000)
            above = bool(match.group(5) or match.group(6))
            resolved.update(code for code in index if code[:4] in subjects and ((int(code[5]) >= min(levels)) if above else (int(code[5]) in levels)))
        if resolved:
            excluded = explicit_exclusions(text, extract)
            item["codes"] = sorted((set(item["codes"]) | resolved) - excluded)
            if excluded:
                item["excluded_codes"] = sorted(excluded)


def structure_science_named_headings(data, extract):
    stem = data["source_file"]
    if stem == "B.Sc._in_Chemistry":
        item = data["sections"][2].get("subsections", [])[1]
        combined = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
        labels = ["Undergraduate electives", "CHEM courses at 5000 level (with approval from the Department)",
                  "Non-CHEM courses"]
        matches = [(label, re.search(re.escape(label) + r"\s*:?​?", combined, re.I)) for label in labels]
        if all(match for _, match in matches):
            intro = combined[:matches[0][1].start()].strip()
            children = []
            for position, (label, match) in enumerate(matches):
                end = matches[position + 1][1].start() if position + 1 < len(matches) else len(combined)
                body = combined[match.end():end].strip()
                children.append(group(label, [body] if body else [], extract(body)))
            item["title"], item["text"], item["codes"], item["subsections"] = intro, [], [], children
            item["keep_heading"] = True
    elif stem == "B.Sc._in_Earth_and_Environmental_Sciences":
        item = data["sections"][2].get("subsections", [])[0]
        combined = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
        matches = list(re.finditer(r"Category\s+([ABC])\s*:", combined, re.I))
        if len(matches) == 3:
            intro = combined[:matches[0].start()].strip()
            children = []
            for position, match in enumerate(matches):
                end = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
                body = combined[match.end():end].strip()
                children.append(group(f"Category {match.group(1).upper()}", [body], extract(body)))
            item["title"], item["text"], item["codes"], item["subsections"] = intro, [], [], children
            item["keep_heading"] = True
    elif stem == "B.Sc._in_Physics":
        item = data["sections"][1].get("subsections", [])[0]
        combined = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
        if re.match(r"Physics\s+courses\s+", combined, re.I):
            item["title"] = "Physics courses"
            item["text"] = [re.sub(r"^Physics\s+courses\s+", "", combined, flags=re.I)]
            item["keep_heading"] = True


def flatten_misnested_roman_groups(data):
    stems = {
        "B.S.Sc._in_Global_Communication": (2, "(i)"),
        "B.S.Sc._in_Government_and_Public_Administration": (2, "(i)"),
    }
    configured = stems.get(data["source_file"])
    if not configured:
        return
    section = data["sections"][configured[0]]
    parents = section.get("subsections", [])
    first = next((item for item in parents if item.get("marker") == configured[1]), None)
    if first and first.get("subsections"):
        roman = [item for item in first["subsections"] if re.fullmatch(r"\([ivxlcdm]+\)", item.get("marker", ""), re.I)]
        first["subsections"] = [item for item in first["subsections"] if item not in roman]
        insertion = parents.index(first) + 1
        parents[insertion:insertion] = roman


def refine_social_science_sections(data, index, extract):
    stem = data["source_file"]
    if data.get("faculty") == "Social Science" and data.get("sections"):
        package = data["sections"][0]
        package["text"] = [clean(text) for text in package.get("text", [])]
        package["combine_text_boxes"] = True
    if stem == "B.S.Sc._in_Geography_and_Resource_Management":
        item = next((x for x in data["sections"][2].get("subsections", []) if x.get("marker") == "(d)"), None)
        if item:
            if item.get("text") and not item.get("title"):
                item["text"].pop(0)
            item["title"] = ("At least nine courses chosen from the GRMD Major course list as below[a], "
                             "with at least five courses at 3000 level or above")
            item["keep_heading"] = True
        for position, note in enumerate(list(data.get("notes", []))):
            if note.get("marker") == "[a]" and note.get("text", "").startswith("[b]"):
                body = note["text"][3:].strip()
                sentences = re.split(r"(?<=\.)\s+(?=The courses to be used)", body, maxsplit=1)
                if len(sentences) == 2:
                    data["notes"][position:position + 1] = [
                        {"marker": "[a]", "text": sentences[0], "subsections": [], "rows": []},
                        {"marker": "[b]", "text": sentences[1], "subsections": [], "rows": []},
                    ]
    elif stem == "B.S.Sc._in_Global_Studies":
        item = next((x for x in data["sections"][1].get("subsections", []) if x.get("marker") == "(c)"), None)
        if item:
            subjects = {"ARAB", "FREN", "GERM", "HKSL", "ITAL", "JASP", "KORE", "RUSS", "SPAN", "THAI"}
            item["codes"] = sorted(code for code in index if code[:4] in subjects and 1000 <= int(code[5:]) < 5000)
            item["force_course_table"] = True
    elif stem == "B.S.Sc._in_Government_and_Public_Administration":
        elective = data["sections"][2]
        groups = elective.get("subsections", [])
        a = next((x for x in groups if x.get("marker") == "(a)"), None)
        b = next((x for x in groups if x.get("marker") == "(b)"), None)
        c = next((x for x in groups if x.get("marker") == "(c)"), None)
        for item in (a, b, c):
            if item and not item.get("title") and item.get("text"):
                item["title"] = item["text"].pop(0)
            if item:
                item["keep_heading"] = True
        if a:
            details = re.match(r"^(Field Electives(?:\[[a-z]\]\s*)*)(\(.*\))$", a.get("title", ""), re.I)
            if details:
                a["title"] = clean(details.group(1))
                a["text"].insert(0, details.group(2))
        if b:
            details = re.match(r"^(Free Major Electives)\s*(\(.*\))$", b.get("title", ""), re.I)
            if details:
                b["title"] = details.group(1)
                b["text"].insert(0, details.group(2))
        if c:
            details = re.match(r"^(Capstone Courses)\s*(\(.*\))$", c.get("title", ""), re.I)
            if details:
                c["title"] = details.group(1)
                c["text"].insert(0, details.group(2))
        if a:
            vi = next((x for x in a.get("subsections", []) if x.get("marker") == "(vi)"), None)
            if vi and not vi.get("title") and vi.get("text"):
                vi["title"] = vi["text"].pop(0)
            if vi:
                vi["keep_heading"] = True
        if b:
            b["codes"] = sorted(code for code in index if code.startswith("GPAD ")
                                and 1000 <= int(code[5:]) < 5000 and code not in {"GPAD 1076", "GPAD 1077"})
            b["force_course_table"] = True
    elif stem == "B.S.Sc._in_Journalism_and_Communication":
        item = data["sections"][1].get("subsections", [])[1]
        combined = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
        matches = list(re.finditer(r"(?:Either\s+|;\s*or\s+)(Chinese Journalism|English Journalism|Integrated Strategic Communication|Creative Media Laboratory)\s+", combined))
        if len(matches) == 4:
            children = []
            for position, match in enumerate(matches):
                end = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
                body = combined[match.end():end].strip(" ;")
                children.append(group(match.group(1), [body], extract(body)))
            item["title"], item["text"], item["codes"], item["subsections"] = "", [], [], children
    elif stem == "B.S.Sc._in_Psychology":
        item = data["sections"][2].get("subsections", [])[0]
        if not item.get("title") and item.get("text"):
            item["title"] = item["text"].pop(0)
        if item:
            item["keep_heading"] = True
    elif stem == "B.A._in_English":
        for item in walk(data["sections"]):
            item["text"] = [text.replace("declare the following stream", "declare this stream") for text in item.get("text", [])]


def source_requirement_rows(path, admission_code=""):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    candidates = []
    for position, table in enumerate(soup.find_all("table")):
        text = clean(table.get_text(" ", strip=True))
        if "Major Programme Requirement" not in text or not re.search(r"[A-Z]{4}\s*\d{4}", text):
            continue
        candidates.append((position, table, text))
    if not candidates:
        return []
    candidate_ids = {id(table) for _, table, _ in candidates}
    innermost = [item for item in candidates
                 if not any(id(descendant) in candidate_ids for descendant in item[1].find_all("table"))]
    if innermost:
        candidates = innermost
    non_senior = [item for item in candidates if "senior-year places" not in item[2][:350].lower()]
    if non_senior:
        candidates = non_senior
    standard = [item for item in candidates if re.match(r"Major Programme Requirement(?!\s+of\b)", item[2], re.I)]
    if standard:
        candidates = standard
    candidates.sort(key=lambda item: item[0])
    table = candidates[0][1]
    body = table.find("tbody", recursive=False) or table
    result = []
    for row in body.find_all("tr", recursive=False):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all("td", recursive=False)]
        result.append((clean(" ".join(cell for cell in cells if cell)), cells))
    return result


def add_social_concentrations(data, path, extract):
    configs = {
        "B.S.Sc._in_Economics": ("Concentration Area", ["Economic Theory", "Financial Economics", "Business Economics", "Chinese Economy", "Data Analytics"]),
        "B.S.Sc._in_Geography_and_Resource_Management": ("Concentration Area", ["Geo-spatial Data Science", "Physical Environment and Resource Management", "Urban and Regional Development", "Smart Cities and Sustainability Governance", "Environmental Science and Management"]),
        "B.S.Sc._in_Psychology": ("Concentration Area", ["Cognitive Science", "Education and Human Development", "Social and Industrial-Organizational Psychology", "Clinical and Health Psychology", "Training in Guided Self-Help for Low Intensity Psychological Interventions", "Computational Psychology and Artificial Intelligence"]),
        "B.S.Sc._in_Sociology": ("Concentration Area", ["Research Methods and Data Analytics", "Human Security and Social Governance", "Sociology and Social Policy", "Society, Sustainability and Technology"]),
        "B.S.Sc._in_Urban_Studies": ("Concentration Areas", ["Urban Planning and Design", "Urban Environment", "Urban Policy and Governance", "Smart Sustainable Cities"]),
    }
    configured = configs.get(data["source_file"])
    if not configured:
        return
    block_title, titles = configured
    rows = source_requirement_rows(path, data.get("admission_code", ""))
    start = next((i for i, (text, _) in enumerate(rows) if text.startswith(block_title)), None)
    end = next((i for i, (text, _) in enumerate(rows) if start is not None and i > start and text.startswith("Explanatory Note")), len(rows))
    if start is None:
        return
    intro = []
    found = []
    positions = []
    for i in range(start + 1, end):
        text = rows[i][0]
        for title in titles:
            if re.match(rf"^(?:(?:\([a-z0-9]+\)|[A-F]\.)\s*)?{re.escape(title)}(?:\s|$)", text, re.I):
                positions.append((i, title))
                break
    if not positions:
        return
    intro = [rows[i][0] for i in range(start + 1, positions[0][0]) if rows[i][0]]
    for position, (row_index, title) in enumerate(positions):
        stop = positions[position + 1][0] if position + 1 < len(positions) else end
        values = [rows[i][0] for i in range(row_index, stop) if rows[i][0]]
        first = re.sub(rf"^(?:(?:\([a-z0-9]+\)|[A-F]\.)\s*)?{re.escape(title)}\s*", "", values[0], flags=re.I).strip()
        body = ([first] if first else []) + values[1:]
        codes = extract(" ".join(body))
        found.append(group(title, body, codes, children=[]))
    if found:
        trailing = []
        last_body = found[-1]["text"]
        if last_body and last_body[-1].startswith("For students taking two concentration"):
            trailing.append(last_body.pop())
        data.setdefault("additional_requirements", []).append({
            "title": block_title, "description": " ".join(intro + trailing), "total_units": "",
            "sections": found, "notes": [], "placement": "before_notes",
        })


def add_physics_streams(data, path, extract):
    if data["source_file"] != "B.Sc._in_Physics":
        return
    rows = source_requirement_rows(path, data.get("admission_code", ""))
    start = next((i for i, (text, _) in enumerate(rows) if text.startswith("Streams :")), None)
    end = next((i for i, (text, _) in enumerate(rows) if start is not None and i > start and text.startswith("In addition to fulfilling")), len(rows))
    if start is None:
        return
    titles = ["Enrichment Stream in Theoretical Physics", "Astrophysics and Particle Physics Stream",
              "Computational and Data Physics Stream",
              "Artificial Intelligence and Computational Physics Stream", "Quantum Science and Technology Stream"]
    positions = [(i, title) for i, (text, _) in enumerate(rows[start + 1:end], start + 1)
                 for title in titles if text == title]
    streams = []
    for position, (row_index, title) in enumerate(positions):
        stop = positions[position + 1][0] if position + 1 < len(positions) else end
        children = []
        for text, _ in rows[row_index + 1:stop]:
            match = re.match(r"^(\([ab]\))\s+(Required courses|Elective courses)\s*:\s*(.*?)(?:\s+(\d+(?:\s+or\s+\d+)?(?:\[[^]]+\])?))?$", text, re.I)
            if match:
                marker, heading, body, units = match.groups()
                children.append(group(heading.title(), [body] if body else [], extract(body), units or "", marker))
            elif text and children:
                children[-1]["text"].append(text)
                children[-1]["codes"] = list(dict.fromkeys(children[-1]["codes"] + extract(text)))
        streams.append(group(title, children=children))
    if streams:
        description = rows[start][0].split(":", 1)[1].strip()
        data.setdefault("additional_requirements", []).append({
            "title": "Streams", "description": description, "total_units": "", "sections": streams,
            "notes": [], "placement": "after_section_2",
        })


def trim_stream_material_from_notes(data):
    if data["source_file"] == "B.Sc._in_Risk_Management_Science":
        prefixes = {
            "1.": "RMSC courses at 2000", "2.": "Students admitted to the Dual Undergraduate",
            "[a]": "Students may take ECON1010", "[b]": "Students may take RMSC3001",
            "[c]": "Students may take CSCI2100",
        }
        retained = {}
        for note in data.get("notes", []):
            marker, text = note.get("marker"), note.get("text", "")
            if marker in prefixes and text.startswith(prefixes[marker]):
                retained.setdefault(marker, note)
        data["notes"] = [retained[marker] for marker in ("1.", "2.", "[a]", "[b]", "[c]") if marker in retained]
    elif data["source_file"] == "B.Sc._in_Statistics":
        retained = {}
        for note in data.get("notes", []):
            marker, text = note.get("marker"), note.get("text", "")
            if marker == "1." and text.startswith("STAT courses at 2000"):
                retained.setdefault("1.", note)
            elif marker == "2." and text.startswith("Students admitted to the Dual Undergraduate"):
                note["subsections"] = []
                retained.setdefault("2.", note)
            elif marker in {"[a]", "[b]"}:
                retained.setdefault(marker, note)
        data["notes"] = [retained[marker] for marker in ("1.", "2.", "[a]", "[b]") if marker in retained]


def structure_mathematics_streams(data):
    if data["source_file"] != "B.Sc._in_Mathematics" or len(data.get("sections", [])) < 3:
        return
    faculty_package, required, elective = data["sections"][:3]
    common = next((item for item in elective.get("subsections", []) if item.get("marker") == "(a)"), None)
    stream_groups = [item for item in elective.get("subsections", [])
                     if item.get("title", "").startswith("For students")]
    if not common or len(stream_groups) < 5:
        return
    rebuilt = [faculty_package]
    ordinary_description = "For students who specialize in streams other than the Enrichment Stream."
    # This source sentence was previously rendered as a stray child of the
    # Faculty Package; it describes all five ordinary streams instead.
    faculty_package["subsections"] = [item for item in faculty_package.get("subsections", [])
                                      if not item.get("title", "").startswith("For students who specialize")]
    for position, stream in enumerate(stream_groups, start=2):
        title = re.sub(r"^For students (?:who specialize in|in the|in)\s+", "", stream["title"], flags=re.I)
        title = re.sub(r"^the\s+", "", title, flags=re.I)
        title = re.sub(r"\[a\]$", "", title).strip()
        req = deepcopy(required)
        req["marker"] = ""
        elec = group("Elective Courses", units=elective.get("units", "33"), children=[deepcopy(common), deepcopy(stream)])
        elec["subsections"][1]["title"] = "Stream-specific Courses"
        rebuilt.append(group(title, [ordinary_description], units="62", marker=f"{position}.", children=[req, elec]))
    enrichment = next((block for block in data.get("additional_requirements", [])
                       if block.get("title") == "Enrichment Stream"), None)
    if enrichment:
        children = [deepcopy(section) for section in enrichment.get("sections", [])
                    if "Faculty Package" not in section.get("title", "")]
        for child in children:
            child["marker"] = ""
        description = re.sub(r"^\s*\[[a-z]\]\s*:?​?\s*$", "", enrichment.get("description", ""), flags=re.I)
        rebuilt.append(group("Enrichment Stream", [description] if description else [],
                             units="62", marker=f"{len(rebuilt) + 1}.", children=children))
        data["additional_requirements"].remove(enrichment)
    data["sections"] = rebuilt


def _collapse_labelled_course_children(parent):
    """Render adjacent named course lists as one table with labelled dividers."""
    children = parent.get("subsections", [])
    labelled = [child for child in children if child.get("title") and child.get("codes")]
    if len(labelled) < 2 or len(labelled) != len(children):
        return
    parent["course_groups"] = [
        {"label": child["title"], "codes": child["codes"]} for child in labelled
    ]
    parent["codes"] = list(dict.fromkeys(
        code for child in labelled for code in child.get("codes", [])
    ))
    parent["subsections"] = []


def _group_area_tables(data):
    if data["source_file"] not in {
        "B.A._in_Public_Humanities", "B.A._in_Religious_Studies", "B.A._in_Theology"
    }:
        return
    for item in list(walk(data.get("sections", []))):
        children = item.get("subsections", [])
        if len(children) > 1 and all(
            (" Area " in child.get("title", "") or child.get("title", "").startswith("Area "))
            and child.get("codes") for child in children
        ):
            _collapse_labelled_course_children(item)

    # Religious Studies and Public Humanities deliberately repeat their area
    # catalogues in each applicable option.  Removing duplicate tables made
    # those options incomplete when read independently.
    if data["source_file"] in {"B.A._in_Public_Humanities", "B.A._in_Religious_Studies"}:
        return
    seen_catalogues = {}
    for item in walk(data.get("sections", [])):
        groups = item.get("course_groups")
        if not groups:
            continue
        fingerprint = tuple((entry.get("label"), tuple(entry.get("codes", []))) for entry in groups)
        if fingerprint in seen_catalogues:
            item.pop("course_groups", None)
            item["codes"] = []
            item.setdefault("text", []).append(f"See the course catalogue under {seen_catalogues[fingerprint]} above.")
        else:
            seen_catalogues[fingerprint] = item.get("title") or "the corresponding areas"


def _merge_japanese_local_scheme(data):
    if data["source_file"] != "B.A._in_Japanese_Studies":
        return
    block = next((b for b in data.get("additional_requirements", [])
                  if b.get("title") == "Local Study Scheme"), None)
    if not block:
        return
    local_elective = next((s for s in block.get("sections", []) if s.get("marker") == "3."), None)
    main_elective = next((s for s in data["sections"] if s.get("marker") == "3."), None)
    if main_elective and local_elective:
        local_text = " ".join(local_elective.get("text", []))
        local_options = [" ".join(child.get("text", [])) for child in local_elective.get("subsections", [])]
        local_text = " ".join([local_text, *local_options]).strip()
        if local_text:
            main_elective.setdefault("text", []).append("Local Study Scheme: " + local_text)
    data["additional_requirements"] = [b for b in data.get("additional_requirements", []) if b is not block]


def _translation_note_tables(data, extract):
    if data["source_file"] != "B.A._in_Translation":
        return
    note = next((n for n in data.get("notes", []) if n.get("marker") == "2."), None)
    if not note:
        return
    text = note.get("text", "")
    specifications = [
        ("Course for writing skills in Chinese", "Course for oral expression skills in Cantonese"),
        ("Course for oral expression skills in Cantonese", "Courses for oral expression skills in Putonghua"),
        ("Courses for oral expression skills in Putonghua", "Courses for writing skills in English"),
        ("Courses for writing skills in English", "Courses for oral expression skills in English"),
        ("Courses for oral expression skills in English", None),
    ]
    groups = []
    first = len(text)
    for title, following in specifications:
        start = text.find(title)
        if start < 0:
            continue
        first = min(first, start)
        end = text.find(following, start + len(title)) if following else len(text)
        body = text[start + len(title):end].strip(" :;-")
        groups.append(group(title, [body], extract(body)))
        groups[-1]["force_course_table"] = True
    if groups:
        note["text"] = text[:first].strip()
        note["subsections"] = groups


def _integrated_bba_and_jd(data, extract):
    stem = data["source_file"]
    if "Integrated_BBA_Programme" not in stem:
        return
    if len(data.get("sections", [])) >= 3:
        for concentration in data["sections"][2].get("subsections", []):
            for child in concentration.get("subsections", []):
                if child.get("marker") in {"(i)", "(ii)"} and not child.get("title") and child.get("text"):
                    sentence = child["text"].pop(0)
                    child["title"] = re.split(r"(?=[A-Z]{4}\s*\d{4})", sentence, maxsplit=1)[0].rstrip(" :;")
                    remainder = sentence[len(child["title"]):].strip(" :;")
                    child["text"] = ([remainder] if remainder else []) + child["text"]
    for block in data.get("additional_requirements", []):
        if block.get("title") != "2nd Degree: Juris Doctor":
            continue
        block["placement"] = "after_notes"
        elective = next((s for s in block.get("sections", []) if s.get("marker") == "2."), None)
        if not elective:
            continue
        source_lines = [line for child in elective.get("subsections", []) for line in child.get("text", [])]
        if source_lines and source_lines[0].startswith("Students are required to take at least 54 or 57 units"):
            intro = source_lines[0]
            first_body = source_lines[2] if len(source_lines) > 2 else ""
            elective["text"] = []
            elective["codes"] = []
            heading = group(intro, children=[
                group("Elective courses which are pre-requisites for subsequent admission to the Postgraduate Certificate in Laws (PCLL) Programme",
                      [first_body] if first_body else [], extract(first_body), marker="(i)"),
                group("Other elective courses offered under the JD programme", marker="(ii)"),
                group("Elective courses offered under the Master of Laws programmes", marker="(iii)"),
            ])
            heading["keep_heading"] = True
            elective["subsections"] = [heading]
            continue
        combined = " ".join(elective.get("text", []))
        if elective.get("subsections"):
            combined += " " + " ".join(" ".join(x.get("text", [])) for x in elective["subsections"])
        intro = re.search(r"Students are required to take at least 54 or 57 units.*?(?=(?:\(i\)|Courses offered by))", combined)
        points = list(re.finditer(r"(?:\(([ivx]+)\)\s*)?(Courses offered by.*?)(?=(?:\([ivx]+\)\s*)?Courses offered by|$)", combined))
        if intro:
            elective["text"] = []
            elective["subsections"] = [group(intro.group(0).strip(), children=[
                group(match.group(2).split(":", 1)[0].strip(),
                      [match.group(2).split(":", 1)[1].strip()] if ":" in match.group(2) else [],
                      extract(match.group(2)), marker=f"({match.group(1) or ['i','ii','iii'][i]})")
                for i, match in enumerate(points[:3])
            ])]


def _merge_accountancy_streams(data):
    if data["source_file"] != "B.B.A._in_Professional_Accountancy":
        return
    required, elective = data["sections"][1], data["sections"][2]
    original_required = deepcopy(required)
    has_required_variant = any(
        any(section.get("marker") == "2." for section in block.get("sections", []))
        for block in data.get("additional_requirements", [])
        if block.get("title", "").endswith("Stream")
    )
    if has_required_variant:
        required["text"], required["codes"] = [], []
        required["subsections"] = [group(
            "Students not in the Global Accounting Stream",
            original_required.get("text", []), original_required.get("codes", []),
            original_required.get("units"),
            children=deepcopy(original_required.get("subsections", [])),
        )]
    elective_options = [group("Without Stream", elective.get("text", []), elective.get("codes", []), elective.get("units"), children=deepcopy(elective.get("subsections", [])))]
    for block in list(data.get("additional_requirements", [])):
        if not block.get("title", "").endswith("Stream"):
            continue
        req = next((s for s in block.get("sections", []) if s.get("marker") == "2."), None)
        elec = next((s for s in block.get("sections", []) if s.get("marker") == "3."), None)
        if req and block["title"] == "Global Accounting Stream":
            required["subsections"].append(group("Global Accounting Stream", req.get("text", []), req.get("codes", []), req.get("units"), children=deepcopy(req.get("subsections", []))))
        if elec:
            elective_options.append(group(block["title"], elec.get("text", []), elec.get("codes", []), elec.get("units"), children=deepcopy(elec.get("subsections", []))))
    elective["text"], elective["codes"], elective["subsections"] = [], [], elective_options
    if has_required_variant:
        required["units"] = " or ".join(dict.fromkeys(
            child.get("units", "") for child in required.get("subsections", []) if child.get("units")
        ))
    elective["title"] = "Elective Courses"
    elective["units"] = " or ".join(dict.fromkeys(
        child.get("units", "") for child in elective_options if child.get("units")
    ))
    totals = [data.get("total_units", "")]
    totals.extend(
        block.get("total_units", "") for block in data.get("additional_requirements", [])
        if block.get("title", "").endswith("Stream")
    )
    totals = [value for value in dict.fromkeys(totals) if value]
    if totals:
        data["total_units"] = " or ".join(totals)
    data["additional_requirements"] = [b for b in data.get("additional_requirements", [])
                                       if not b.get("title", "").endswith("Stream")]


def _small_programme_repairs(data, extract):
    stem = data["source_file"]
    if stem == "B.Sc._in_Biotechnology,_Entrepreneurship_and_Healthcare_Management":
        section = data["sections"][2]
        section["subsections"] = [x for x in section.get("subsections", [])
                                  if not (x.get("units") == "17" and not x.get("title") and not x.get("codes"))]
    elif stem == "B.A._(Chinese_Language_Studies)_and_B.Ed._(Chinese_Language_Education)":
        target = next((x for x in data["sections"][2].get("subsections", []) if x.get("marker") == "(b)"), None)
        if target:
            target["text"] = [target.get("title", "")] + target.get("text", [])
            target["title"] = "Specialty Courses"
    elif stem == "B.Ed._in_Early_Childhood_Education":
        section = data["sections"][2]
        retained = []
        for item in section.get("subsections", []):
            if item.get("units") == "46" and not item.get("codes") and "46 units of courses" in item.get("title", ""):
                section["text"].append(item["title"])
            else:
                retained.append(item)
        section["subsections"] = retained
    elif stem == "B.Ed._in_Mathematics_and_Mathematics_Education":
        for item in walk(data["sections"]):
            if item.get("marker", "") == "(I)" and not item.get("title"):
                item["title"] = "Option I: Mathematics Courses"
    elif stem == "B.Sc._in_Exercise_Science_and_Health_Education":
        item = next((x for x in data["sections"][1].get("subsections", []) if x.get("marker") == "(a)"), None)
        if item and "One course chosen" in item.get("title", ""):
            title, instruction = item["title"].split("One course chosen", 1)
            item["title"] = title.strip()
            item["text"].insert(0, "One course chosen" + instruction)


def _engineering_note_repairs(data, extract):
    stem = data["source_file"]
    if stem == "B.Eng._in_Electronic_Engineering":
        note3 = next((n for n in data.get("notes", []) if n.get("marker") == "3."), None)
        if note3:
            rows = note3.get("rows", [])
            note3["rows"] = [[clean(" ".join(row))] for row in rows]
            for subsection in note3.get("subsections", []):
                lines = subsection.get("text", [])
                if len(lines) >= 2 and re.match(r"\(a\) Elective courses?:$", lines[0], re.I):
                    subsection["text"] = [f"{lines[0]} {lines[1]}", *lines[2:]]
        note4 = next((n for n in data.get("notes", []) if n.get("marker") == "4."), None)
        if note4:
            note4["paragraphs"] = [x.strip() for x in re.split(r"(?=This Programme is eligible)", note4.get("text", "")) if x.strip()]
    if stem in {"B.Eng._in_Energy_and_Environmental_Engineering", "B.Eng._in_Mechanical_and_Automation_Engineering"}:
        note = next((n for n in data.get("notes", []) if n.get("marker") == "[a]"), None)
        if note and len(note.get("subsections", [])) >= 3 and len(note.get("rows", [])) >= 5:
            rows = [clean(" ".join(row)) for row in note["rows"]]
            point_ii = next((item for item in note["subsections"] if item.get("marker") == "(ii)"), None)
            point_iii = next((item for item in note["subsections"] if item.get("marker") == "(iii)"), None)
            if point_ii:
                point_ii.setdefault("text", []).extend(rows[:2])
            if point_iii:
                point_iii.setdefault("text", []).extend(rows[2:5])
            note["rows"] = note["rows"][5:]
    if stem == "B.Eng._in_Information_Engineering":
        for item in walk(data["sections"]):
            if item.get("title") == "Networked Systems and Applications":
                rebuilt = []
                for text in item.get("text", []):
                    parts = re.split(r"(?=The remaining units from)", text)
                    for part in parts:
                        m = re.match(r"(At least 3 units from:|The remaining units from:?)(.*)", part.strip())
                        if m: rebuilt.append(group(m.group(1).rstrip(":"), [m.group(2).strip()], extract(m.group(2))))
                if rebuilt: item["text"], item["subsections"] = [], rebuilt


def _law_and_health_repairs(data, index):
    stem = data["source_file"]
    if stem == "LL.B._-_Bachelor_of_Laws_Programme":
        required = data["sections"][0]
        required["text"] = [re.sub(r"(?<=\d)r(?=\W|$)", "△", text) for text in required.get("text", [])]
        elective = data["sections"][1]
        required_codes = {code for item in walk([required]) for code in item.get("codes", [])}
        elective["codes"] = [code for code in index if code.startswith("LAWS ") and code not in required_codes]
        elective["force_course_table"] = True
    elif stem == "B.Sc._in_Public_Health":
        section = data["sections"][2]
        sentence = "22 units of courses chosen from the following, with 15 units of courses chosen from Group A and 7 units of courses chosen from Group B:"
        if sentence not in section.get("text", []): section["text"].insert(0, sentence)
        for child in section.get("subsections", []):
            if "Group A" in child.get("title", ""): child["units"] = "15"
            if "Group B" in child.get("title", ""): child["units"] = "7"


def _restore_mathematics_source_structure(data):
    if data["source_file"] != "B.Sc._in_Mathematics" or len(data.get("sections", [])) < 7:
        return
    faculty = data["sections"][0]
    streams = data["sections"][1:]
    # Empty recommended-pattern shells must not create a duplicate stream.
    streams = [stream for stream in streams if stream.get("subsections")]
    required_sources = [(stream["title"], stream["subsections"][0]) for stream in streams]
    required_fingerprints = {
        (source.get("units", ""), repr(source.get("text", [])), repr(source.get("subsections", [])))
        for _, source in required_sources
    }
    if len(required_fingerprints) == 1:
        source = deepcopy(required_sources[0][1])
        required = group("Required Courses", source.get("text", []), source.get("codes", []),
                         source.get("units", ""), marker="2.", children=source.get("subsections", []))
    else:
        variants = []
        seen = set()
        for title, source in required_sources:
            fingerprint = (source.get("units", ""), repr(source.get("text", [])), repr(source.get("subsections", [])))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            label = "Enrichment Stream" if title == "Enrichment Stream" else "Streams other than the Enrichment Stream"
            variants.append(group(label, source.get("text", []), source.get("codes", []),
                                  source.get("units", ""), children=deepcopy(source.get("subsections", []))))
        units = " or ".join(dict.fromkeys(x.get("units", "") for x in variants if x.get("units")))
        required = group("Required Courses", units=units, marker="2.", children=variants)

    common = deepcopy(streams[0]["subsections"][1]["subsections"][0])
    choices = []
    for stream in streams:
        elective = stream["subsections"][1]
        if stream.get("title") == "Enrichment Stream" and len(elective.get("subsections", [])) > 2:
            choices.append(group(stream["title"], elective.get("text", []), elective.get("codes", []),
                                 elective.get("units"), children=deepcopy(elective.get("subsections", []))))
            continue
        specific = deepcopy(elective["subsections"][1])
        choices.append(group(stream["title"], specific.get("text", []), specific.get("codes", []),
                             elective.get("units"), children=specific.get("subsections", [])))
    elective_units = " or ".join(dict.fromkeys(
        choice.get("units", "") for choice in choices if choice.get("units")
    ))
    stream_choice = group("Choose the requirements for the student's declared stream.",
                          marker="(b)", children=choices)
    elective = group("Elective Courses", units=elective_units, marker="3.",
                     children=[common, stream_choice])
    data["sections"] = [faculty, required, elective]


def _natural_science_stream_headings(data, extract):
    if data["source_file"] != "B.Sc._in_Natural_Sciences":
        return
    streams = [group("Biological Sciences", units="51", marker="1.", children=deepcopy(data["sections"]))]
    for block in data.get("additional_requirements", []):
        children = deepcopy(block.get("sections", []))
        streams.append(group(block["title"], [block.get("description", "")] if block.get("description") else [],
                             units=block.get("total_units", "51"), marker=f"{len(streams)+1}.", children=children))
    for stream in streams:
        for child in stream.get("subsections", []):
            child["marker"] = ""
            if not child.get("title", "").startswith("Elective Courses"):
                continue
            # The catalogue publishes these two pools inline.  Split by their
            # actual labels rather than by row position, since Word may merge
            # the introductory sentence and first label in a future edition.
            combined = " ".join(child.get("text", []))
            concentration_labels = list(re.finditer(r"\bConcentration Area Courses\s*:\s*", combined))
            other_labels = list(re.finditer(r"\bOther Science Courses\s*:\s*", combined))
            other = other_labels[-1] if other_labels else None
            concentration = next((match for match in reversed(concentration_labels)
                                  if other and match.start() < other.start()), None)
            labels = [concentration, other] if concentration and other else []
            if len(labels) == 2:
                intro = combined[:labels[0].start()].strip()
                children = []
                for position, match in enumerate(labels):
                    stop = labels[position + 1].start() if position + 1 < len(labels) else len(combined)
                    body = combined[match.end():stop].strip()
                    title = "Concentration Area Courses" if position == 0 else "Other Science Courses"
                    children.append(group(title, [body] if body else [], extract(body)))
                child["text"] = [intro] if intro else []
                child["codes"] = []
                child["subsections"] = children
    data["sections"] = streams
    data["additional_requirements"] = []


def _social_science_repairs(data):
    stem = data["source_file"]
    if stem == "B.S.Sc._in_Government_and_Public_Administration":
        section = data["sections"][2]
        sentence = "Of the Elective Courses, at least nine courses (27 units), including the two (6 units) capstone courses, should be at 2000 or above level."
        for item in walk([section]):
            item["text"] = [text for text in item.get("text", []) if text != sentence]
        section["text"].insert(0, sentence)
    elif stem == "B.S.Sc._in_Psychology":
        data["sections"][2]["subsections"][0]["units"] = ""
        block = next((b for b in data.get("additional_requirements", []) if b.get("title") == "Concentration Area"), None)
        if block:
            for letter, item in zip("ABCDEF", block.get("sections", [])):
                if not re.match(r"^[A-F][.)]", item.get("title", "")):
                    item["title"] = f"{letter}. {item['title']}"
    elif stem == "B.S.Sc._in_Urban_Studies":
        item = next((x for x in walk(data["sections"]) if x.get("marker") == "(b)"), None)
        if item:
            item["title"] = "Methodology and Statistics Courses"
            joined = " ".join(item.get("text", []))
            parts = re.split(r"(?=Statistics course:)", joined, maxsplit=1)
            item["text"] = ["Methodology course (choose one of the following): " + parts[0].replace("Methodology course (choose one of the following)", "").strip(" :")]
            if len(parts) > 1: item["text"].append(parts[1])


def _merge_simple_stream_variants(data):
    configurations = {
        "B.Sc._in_Risk_Management_Science": "Risk Analytics Stream",
        "B.Sc._in_Statistics": None,
    }
    if data["source_file"] not in configurations:
        return
    blocks = list(data.get("additional_requirements", []))
    if not blocks:
        return
    if data["source_file"] == "B.Sc._in_Risk_Management_Science":
        group_d = next((item for item in walk([data["sections"][0]]) if item.get("title") == "Group D"), None)
        if group_d and group_d.get("text"):
            text = " ".join(group_d["text"])
            marker = "Courses from Faculty Package of the Faculty of Business Administration:"
            if marker in text:
                physics, business = text.split(marker, 1)
                group_d["text"] = [physics.rstrip(" ,or")]
                group_d["codes"] = [code for code in group_d.get("codes", []) if code.startswith("PHYS ")]
                business_group = group(marker.rstrip(":"), [business.strip()],
                                       ("DOTE 1031", "DOTE 1040", "HTMG 1010", "MGNT 1020"))
                # This is an alternative to Group D, not a subdivision of it.
                # Locate the published container instead of relying on a fixed
                # depth so the rule survives changes to the Faculty Package.
                for parent in walk([data["sections"][0]]):
                    children = parent.get("subsections", [])
                    if group_d in children:
                        position = children.index(group_d)
                        children.insert(position + 1, business_group)
                        break
    main_required, main_elective = data["sections"][1], data["sections"][2]
    main_label = "Without Stream" if data["source_file"].endswith("Risk_Management_Science") else "Standard Programme"
    required_options = [group(main_label, main_required.get("text", []), main_required.get("codes", []), main_required.get("units"), children=deepcopy(main_required.get("subsections", [])))]
    elective_options = [group(main_label, main_elective.get("text", []), main_elective.get("codes", []), main_elective.get("units"), children=deepcopy(main_elective.get("subsections", [])))]
    for block in blocks:
        req = next((x for x in block.get("sections", []) if x.get("marker") == "2."), None)
        elec = next((x for x in block.get("sections", []) if x.get("marker") == "3."), None)
        if req: required_options.append(group(block["title"], req.get("text", []), req.get("codes", []), req.get("units"), children=deepcopy(req.get("subsections", []))))
        if elec: elective_options.append(group(block["title"], elec.get("text", []), elec.get("codes", []), elec.get("units"), children=deepcopy(elec.get("subsections", []))))
    main_required["text"], main_required["codes"], main_required["subsections"] = [], [], required_options
    main_elective["text"], main_elective["codes"], main_elective["subsections"] = [], [], elective_options
    data["additional_requirements"] = []


def _physics_and_medicine_repairs(data):
    stem = data["source_file"]
    if stem == "B.Sc._in_Physics":
        for block in data.get("additional_requirements", []):
            if block.get("title") == "Streams": block["placement"] = "before_notes"
        note = next((n for n in data.get("notes", []) if n.get("marker") == "[b]"), None)
        if note and note.get("rows"):
            note["table"] = True
    elif stem == "M.B.,_Ch.B":
        gps = next((x for x in data.get("sections", []) if "Global Physician" in x.get("title", "")), None)
        if gps:
            for child in gps.get("subsections", []):
                if child.get("marker") in {"(2)", "(3)"}: child["hide_course_table"] = True
            if gps.get("subsections"):
                first = gps["subsections"][0]
                first["text"] = [x.strip() for x in re.split(r"(?=GPS students admitted in)", " ".join(first.get("text", []))) if x.strip()]
        note = next((n for n in data.get("notes", []) if n.get("marker") == "3."), None)
        if note:
            roman = next((x for x in note.get("subsections", []) if x.get("marker") == "(v)"), None)
            if roman and len(roman.get("subsections", [])) >= 4:
                # All four lettered alternatives are peers under 3(v).
                pass


def _double_major_grouping(data):
    if data["source_file"] not in {
        "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme",
        "B.Eng._in_Materials_Science_and_Engineering_X_Double_Major_Programme",
        "B.Sc._in_Aerospace_Science_and_Earth_Informatics_X_Double_Major_Programme",
    } or len(data.get("sections", [])) < 3:
        return
    first, second = data["sections"][1], data["sections"][2]
    options = second.get("subsections", [])
    elective = next((x for x in first.get("subsections", []) if x.get("marker") == "(b)"), None)
    choice_nodes = elective.get("subsections", []) if elective else []
    grouped = []
    for position, option in enumerate(options):
        first_children = [deepcopy(x) for x in first.get("subsections", []) if x is not elective]
        if elective:
            matched = choice_nodes[position] if position < len(choice_nodes) else None
            first_children.append(group(elective.get("title", "Elective Courses"), elective.get("text", []),
                                        units=elective.get("units", "27"), marker="(b)",
                                        children=[deepcopy(matched)] if matched else []))
        grouped.append(group(option.get("title", f"Major Choice {position+1}"), units="81", children=[
            group("First Major Requirements", units="48", children=first_children),
            group("Second Major Requirements", option.get("text", []), option.get("codes", []), "33", children=deepcopy(option.get("subsections", []))),
        ]))
    data["sections"] = [data["sections"][0], group("Major Choices", units="81", marker="2.", children=grouped)]


def _split_labelled_concentration_parts(data, extract):
    stem = data["source_file"]
    if stem not in {"B.S.Sc._in_Economics", "B.S.Sc._in_Sociology"}:
        return
    for block in data.get("additional_requirements", []):
        if not block.get("title", "").startswith("Concentration"):
            continue
        for area in block.get("sections", []):
            lines = list(area.get("text", []))
            starts = []
            pattern = re.compile(r"^(\([a-z]\)|\([ivx]+\)|Optional Interdisciplinary Cluster:|Capstone Project / Internship / Field Studies in Human Security:)", re.I)
            for position, line in enumerate(lines):
                if pattern.match(line): starts.append(position)
            if not starts:
                continue
            intro = lines[:starts[0]]
            children = []
            for position, start in enumerate(starts):
                stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
                segment = lines[start:stop]
                match = pattern.match(segment[0])
                marker = match.group(1) if match.group(1).startswith("(") else ""
                heading = segment[0][match.end():].strip(" :") if marker else match.group(1).rstrip(":")
                unit_match = re.search(r"(?:Courses|Cluster).*?\b(\d+(?:-\d+)?)\s*$", heading, re.I)
                range_match = re.match(r"(?:At least|up to)\s+(\d+(?:-\d+)?)\s+units", heading, re.I)
                units = (unit_match.group(1) if unit_match else
                         (range_match.group(1) if range_match else ""))
                if unit_match: heading = heading[:unit_match.start()].rstrip(" :")
                body = segment[1:]
                if not heading and body:
                    heading = body.pop(0)
                children.append(group(heading, body, extract(" ".join(body)), units, marker))
            if stem == "B.S.Sc._in_Economics":
                nested = []
                for child in children:
                    if child.get("marker") in {"(i)", "(ii)"} and nested and nested[-1].get("marker") == "(b)":
                        nested[-1]["subsections"].append(child)
                    else:
                        nested.append(child)
                children = nested
            area["text"], area["codes"], area["subsections"] = intro, [], children
    if stem == "B.S.Sc._in_Economics":
        note = next((n for n in data.get("notes", []) if n.get("marker") == "[a]"), None)
        if note:
            note["paragraphs"] = [x.strip() for x in re.split(r"(?=Students who have obtained)", note.get("text", "")) if x.strip()]


def _diplomacy_language_table(data, index):
    if data["source_file"] != "B.S.Sc._in_Diplomacy_and_International_Studies":
        return
    language_names = {
        "ARAB": "Arabic", "FREN": "French", "GERM": "German", "ITAL": "Italian",
        "JASP": "Japanese", "KORE": "Korean", "RUSS": "Russian", "SPAN": "Spanish", "THAI": "Thai",
    }
    language = next((x for x in data["sections"][1].get("subsections", []) if x.get("marker") == "(b)"), None)
    if language:
        language["course_groups"] = [
            {"label": name, "codes": [code for code in index if code.startswith(subject + " ")]}
            for subject, name in language_names.items()
            if any(code.startswith(subject + " ") for code in index)
        ]
        language["codes"] = [code for entry in language["course_groups"] for code in entry["codes"]]


def _merge_math_information_engineering_routes(data):
    if data["source_file"] != "B.Sc._in_Mathematics_and_Information_Engineering":
        return
    block = next((b for b in data.get("additional_requirements", []) if b.get("title", "").startswith("For students admitted via")), None)
    if not block:
        return
    science = {s.get("marker"): s for s in block.get("sections", [])}
    faculty = data["sections"][0]
    direct_faculty = deepcopy(faculty)
    faculty["text"], faculty["codes"] = [], []
    faculty["subsections"] = [
        group("Direct Admission", direct_faculty.get("text", []), direct_faculty.get("codes", []),
              children=direct_faculty.get("subsections", [])),
        group("Admission via the Faculty of Science", children=deepcopy(science.get("1.", {}).get("subsections", [])),
              text=science.get("1.", {}).get("text", []), codes=science.get("1.", {}).get("codes", [])),
    ]
    foundation = data["sections"][1]
    direct_parts = deepcopy(foundation.get("subsections", []))
    science_parts = deepcopy(science.get("2.", {}).get("subsections", []))
    foundation["subsections"] = [
        group("Direct Admission", units=foundation.get("units"), children=direct_parts),
        group("Admission via the Faculty of Science", units=science.get("2.", {}).get("units", "9"), children=science_parts),
    ]
    elective = data["sections"][3]
    elective["units"] = "6 or 9"
    elective["text"].insert(0, "Direct-admission students complete 9 units; students admitted via the Faculty of Science complete 6 units.")
    data["description"] = re.sub(r"\s*For students admitted to the programme directly\.?\s*$", "", data.get("description", ""))
    data["additional_requirements"] = [b for b in data.get("additional_requirements", []) if b is not block]


def _earth_stream_differences(data, extract):
    if data["source_file"] != "B.Sc._in_Earth_and_Environmental_Sciences":
        return
    blocks = [block for block in data.get("additional_requirements", [])
              if block.get("title") != "Science, Technology and Research Stream"]
    if len(blocks) != 3:
        return
    labels = ["Without Stream", *[block["title"] for block in blocks]]
    main_required, main_elective = data["sections"][1:3]
    block_sections = [{section.get("marker"): section for section in block.get("sections", [])} for block in blocks]

    def option(label, source):
        copy = deepcopy(source)
        copy["marker"] = ""
        copy["title"] = label
        return copy

    # Preserve the CUHK 2(a)-2(e) and 3(a)-3(d) hierarchy. Only requirements
    # that vary by stream receive a nested set of stream choices.
    required_common = deepcopy(main_required.get("subsections", [])[:3])
    for marker, title in (("(d)", "Stream Core Courses"), ("(e)", "Supporting Science and Mathematics")):
        choices = [group("Without Stream", ["No additional stream-specific requirement."])]
        for label, sections in zip(labels[1:], block_sections):
            source = next((x for x in sections["2."].get("subsections", []) if x.get("marker") == marker), None)
            if source: choices.append(option(label, source))
        required_common.append(group(title, marker=marker, children=choices))
    main_required["subsections"] = required_common
    main_required["units"] = "16-18 or 30-33"

    rebuilt_elective = []
    main_parts = {x.get("marker"): x for x in main_elective.get("subsections", [])}
    for marker in ("(a)", "(b)"):
        choices = [option("Without Stream", main_parts[marker])]
        choices[0]["text"] = [main_parts[marker].get("title", ""), *choices[0].get("text", [])]
        choices[0]["text"] = [text for text in choices[0]["text"] if text]
        for label, sections in zip(labels[1:], block_sections):
            source = next((x for x in sections["3."].get("subsections", []) if x.get("marker") == marker), None)
            if source: choices.append(option(label, source))
        # Put the letter marker on the ordinary route and keep every named
        # stream as its peer.  This renders “(a)/(b) Without Stream” on one
        # line without indenting the other stream alternatives differently.
        choices[0]["marker"] = marker
        rebuilt_elective.extend(choices)
    capstone = deepcopy(main_parts["(c)"])
    option_three = next((x for x in capstone.get("subsections", []) if x.get("marker") == "(iii)"), None)
    if option_three:
        option_three["title"] = ""
        option_three["units"] = "6"
        option_three["text"] = ["6 units from 3(b) section of the stream chosen"]
        option_three["codes"], option_three["subsections"] = [], []
        option_three["heading_as_text"] = True

    without_other = main_parts["(d)"]
    stream_other = next((
        next((x for x in sections["3."].get("subsections", []) if x.get("marker") == "(d)"), None)
        for sections in block_sections
        if next((x for x in sections["3."].get("subsections", []) if x.get("marker") == "(d)"), None)
    ), None)
    course_list_text = [text for text in without_other.get("text", []) if extract(text)]
    other_electives = group("Other electives", marker="(d)", children=[
        group("Without Stream", ["Choose at least three courses from the following list."],
              units=without_other.get("units", "")),
        group("With Stream", [
            "Choose two courses from the following list. Note that courses used to fulfill the above "
            "requirements cannot also be used to fulfill this requirement."
        ], units=(stream_other or {}).get("units", "")),
        group("Course list for Other electives", course_list_text,
              without_other.get("codes", [])),
    ])
    rebuilt_elective.extend([capstone, other_electives])
    main_elective["subsections"] = rebuilt_elective
    main_elective["units"] = "28-30 or 42-44"
    data["additional_requirements"] = []


def _latest_review_fixes(data, index, extract):
    stem = data["source_file"]
    if stem == "B.A._in_Japanese_Studies":
        required_b = next(x for x in data["sections"][1]["subsections"] if x.get("marker") == "(b)")
        published_requirement = required_b.get("title", "")
        required_b["title"] = "For Standard Scheme Only — Not for Local Study Scheme"
        if published_requirement and not published_requirement.startswith("For Standard Scheme"):
            required_b["text"].insert(0, published_requirement)
        elective = data["sections"][2]
        local = next((text for text in elective["text"] if text.startswith("Local Study Scheme:")), "")
        elective["text"] = [text for text in elective["text"] if not text.startswith("Local Study Scheme:")]
        without, with_stream = elective["subsections"][:2]
        local_without = re.search(r"Students not specializing.*?(?=Students choosing|$)", local)
        local_with = re.search(r"Students choosing.*$", local)
        standard_without = without["text"][-1] if without.get("text") else ""
        standard_with = with_stream["text"][-1] if with_stream.get("text") else ""
        without["text"] = []
        without["subsections"] = [
            group("Standard Scheme", [standard_without], units="6"),
            group("Local Study Scheme", [local_without.group(0)] if local_without else [], units="24"),
            *without.get("subsections", []),
        ]
        without["units"] = " or ".join(dict.fromkeys(
            child.get("units", "") for child in without["subsections"] if child.get("units")
        ))
        with_stream["text"] = []
        with_stream["subsections"] = [
            group("Standard Scheme", [standard_with], units="12"),
            group("Local Study Scheme", [local_with.group(0)] if local_with else [], units="24"),
            *with_stream.get("subsections", []),
        ]
        with_stream["units"] = " or ".join(dict.fromkeys(
            child.get("units", "") for child in with_stream["subsections"] if child.get("units")
        ))
        elective["units"] = "6 or 12 (Standard); 24 (Local)"
    elif stem == "B.A._in_Linguistics":
        for parent in (data["sections"][2]["subsections"][0], data["sections"][2]["subsections"][1]):
            children = [x for x in parent.get("subsections", []) if x.get("codes")]
            if len(children) > 1:
                parent["course_groups"] = [{"label": x["title"], "codes": x["codes"]} for x in children]
                parent["codes"] = list(dict.fromkeys(code for x in children for code in x["codes"]))
                parent["subsections"] = []
    elif stem == "B.A._in_Public_Humanities":
        section = data["sections"][2]
        standard = section["subsections"][:3]
        concentrations = section["subsections"][3]["subsections"]
        rebuilt = []
        for position, base in enumerate(standard):
            if base.get("marker") == "(c)":
                rebuilt.append(base)
                continue
            parent = group("Standard Scheme", marker=base["marker"])
            standard_rule = option_group(base.get("title", ""), base)
            parent["subsections"] = [standard_rule]
            for concentration in concentrations:
                source = next((x for x in concentration.get("subsections", []) if x.get("marker") == base["marker"]), None)
                if source:
                    rule = option_group(source.get("title", ""), source)
                    # The concentration heading and its rule share one node,
                    # so its text box aligns with the Standard Scheme rule.
                    published_rule = rule.get("title", "")
                    rule["title"] = f"{concentration['title']} Concentration"
                    if published_rule:
                        rule["text"] = [published_rule, *rule.get("text", [])]
                    parent["subsections"].append(rule)
            rebuilt.append(parent)
        section["subsections"] = rebuilt
    elif stem == "B.A._in_Religious_Studies":
        section = data["sections"][2]
        for item in section["subsections"][:2]:
            item["subsections"].insert(0, group("Without Concentrations"))
        catalogues = {}
        for item in walk([section]):
            if item.get("course_groups"):
                catalogues[tuple(entry["label"].split(":", 1)[0] for entry in item["course_groups"])] = deepcopy(item["course_groups"])
        religious = next((groups for labels, groups in catalogues.items() if any("Religious Studies Area" in label for label in labels)), None)
        for item in walk([section]):
            if religious and "Religious Studies Areas" in (item.get("title", "") + " " + " ".join(item.get("text", []))) and not item.get("course_groups"):
                item["course_groups"] = deepcopy(religious)
                item["codes"] = list(dict.fromkeys(code for entry in religious for code in entry["codes"]))
                item["text"] = [text for text in item.get("text", []) if "course catalogue" not in text]
    elif stem == "B.B.A._(Integrated_BBA_Programme)_and_Juris_Doctor":
        data["requirement_title"] = "1st Degree: Bachelor of Business Administration (Integrated BBA Programme)"
        data["notes"] = [n for n in data.get("notes", []) if "minimum of 72 units" not in n.get("text", "")]
        note_b = next((n for n in data.get("notes", []) if n.get("marker") == "[b]"), None)
        if note_b and note_b.get("subsections"):
            note_b["text"] = " ".join([note_b.get("text", ""), *[" ".join(x.get("text", [])) for x in note_b["subsections"]]]).strip()
            note_b["subsections"] = []
    elif stem == "B.B.A._in_Professional_Accountancy":
        required = data["sections"][1]
        ordinary = required["subsections"][0]
        if ordinary.get("subsections"):
            ordinary["codes"] = ordinary["subsections"][0].get("codes", [])
            ordinary["text"] = ordinary["subsections"][0].get("text", [])
            ordinary["subsections"] = []
    elif stem == "B.A._(Chinese_Language_Studies)_and_B.Ed._(Chinese_Language_Education)":
        try:
            candidates = data["sections"][2]["subsections"][0]["subsections"]
        except (IndexError, KeyError):
            candidates = []
        target = next((x for x in candidates if x.get("marker") == "(b)"), None)
        if target:
            target["title"] = "Specialty Courses"
    elif stem == "B.Sc._in_Exercise_Science_and_Health_Education":
        section_children = data["sections"][1]["subsections"]
        item = section_children[0]
        instruction = next((text for text in item.get("text", []) if text.startswith("One course chosen")), "One course chosen from the following")
        item["subsections"] = [group(instruction, item.get("text", [])[1:] if item.get("text") else [], item.get("codes", []))]
        item["text"], item["codes"] = [], []
        required_b = next((x for x in section_children if x.get("marker") == "(b)"), None)
        trailing = next((x for x in section_children if not x.get("marker") and x is not item), None)
        if required_b and trailing:
            required_b["subsections"].append(trailing)
            section_children.remove(trailing)
    elif stem == "B.Eng._in_Artificial_Intelligence_Systems_and_Technologies":
        for position, item in enumerate(data["sections"][3].get("subsections", [])):
            if position == 0 and item.get("text"):
                item["subsections"].insert(0, group("Choose at least 18 units from the following courses", item["text"], item["codes"]))
                item["text"], item["codes"] = [], []
            for child in item.get("subsections", []):
                if child.get("title", "").startswith("Remaining units") or any(text.startswith("Remaining units") for text in child.get("text", [])):
                    child["keep_heading"] = True
    elif stem == "B.Eng._in_Information_Engineering":
        streams = next((x for x in data["sections"][3]["subsections"]
                        if x.get("title") == "Streams"
                        or any(text.startswith("Students may choose not to specialize") for text in x.get("text", []))), None)
        if not streams:
            return
        streams["title"], streams["keep_heading"] = "Streams", True
        stream_names = {"Big Data: Systems and Applications", "Telecommunications", "Cyber Security", "Networked Systems and Applications", "Information Science"}
        stream_items = [x for x in data["sections"][3]["subsections"] if x.get("title") in stream_names]
        data["sections"][3]["subsections"] = [x for x in data["sections"][3]["subsections"] if x not in stream_items]
        streams["subsections"] = stream_items
        network = next((x for x in stream_items if x["title"] == "Networked Systems and Applications"), None)
        if network:
            network["codes"] = []
    elif stem == "B.Eng._in_Systems_Engineering_and_Engineering_Management":
        item = next((x for x in data["sections"][3]["subsections"] if "Streams of Specialization" in (x.get("title", "") + " ".join(x.get("text", [])))), None)
        if item: item["title"], item["keep_heading"] = "Streams of Specialization", True
    elif stem == "B.Sc._in_Computational_Data_Science":
        section = data["sections"][4]
        section["title"] = "Elective Courses"
        section["text"].insert(0, "Choose any ONE from the following four options")
        for item in walk(section.get("subsections", [])):
            if item.get("title", "").startswith("Remaining units"):
                item["keep_heading"] = True
    elif stem in {
        "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme",
        "B.Eng._in_Materials_Science_and_Engineering_X_Double_Major_Programme",
        "B.Sc._in_Aerospace_Science_and_Earth_Informatics_X_Double_Major_Programme",
    }:
        choices = data["sections"][1]
        first_example = choices["subsections"][0]["subsections"][0]
        required = deepcopy(next(x for x in first_example["subsections"] if x.get("title") == "Required Courses"))
        required["marker"] = "2."
        required["title"] = "1st Major Required Courses"
        required["units"] = required.get("units") or "21"
        choices["marker"], choices["title"] = "3.", "Major Choices"
        for choice in choices["subsections"]:
            first, second = choice["subsections"]
            choice["_second_major_units"] = second.get("units", "")
            elective = deepcopy(next(x for x in first["subsections"] if x.get("title", "").startswith("Elective Courses")))
            elective["title"] = "1st Major Elective Courses"
            flattened = [elective, *deepcopy(second.get("subsections", []))]
            for item in flattened:
                if item.get("marker") == "": item["marker"] = ""
            choice["subsections"] = flattened
        data["sections"] = [data["sections"][0], required, choices]
    elif stem == "B.Sc._in_Mathematics_and_Information_Engineering":
        faculty, foundation, required, elective = data["sections"]
        direct_faculty, science_faculty = faculty["subsections"]
        direct_foundation, science_foundation = foundation["subsections"]
        common_b = deepcopy(next(x for x in direct_foundation["subsections"] if x.get("marker") == "(b)"))
        direct_a = deepcopy(next(x for x in direct_foundation["subsections"] if x.get("marker") == "(a)"))
        direct_c = deepcopy(next(x for x in direct_foundation["subsections"] if x.get("marker") == "(c)"))
        direct_a["marker"], direct_c["marker"] = "(i)", "(ii)"
        combined = group("Faculty Package and Foundation Courses", units="18 or 21", marker="1.", children=[
            group("", direct_faculty.get("text", []), direct_faculty.get("codes", []), marker="(a)"),
            common_b,
            group("For Direct Admission Only", marker="(c)", children=[direct_a, direct_c]),
            group("For Admission via the Faculty of Science Only", marker="(d)", children=[
                option_group("Science Faculty Package", science_faculty),
            ]),
        ])
        # Each child is one three-unit choice in the published direct-entry
        # route, so this adapts if that route gains or loses a component.
        combined["subsections"][2]["units"] = str(3 * len(combined["subsections"][2]["subsections"]))
        combined["subsections"][3]["units"] = science_faculty.get("units", "") or "9"
        common_b["marker"] = "(b)"
        required["marker"], elective["marker"] = "2.", "3."
        data["sections"] = [combined, required, elective]
    elif stem == "LL.B._-_Bachelor_of_Laws_Programme":
        stream = next((x for x in walk(data["sections"]) if x.get("title") == "Streams"), None)
        if stream:
            stream["text"] = ["Students may choose to declare the Chinese Law Stream and/or the Global Law Stream within the LLB Programme by taking the following courses:"]
    elif stem == "Bachelor_of_Chinese_Medicine":
        lines = data.get("description_lines", [])
        combined = " ".join(lines)
        intro_end = combined.find("Pre-clinical Programme In the Pre-clinical")
        clinical = combined.find("Clinical Programme The Clinical Programme", intro_end + 1)
        if intro_end > 0 and clinical > 0:
            intro = combined[:intro_end].replace("The Programme consists of two parts: the Pre-clinical Programme (4.5 years) and the Clinical Programme (1.5 years).", "The Programme consists of two parts: the Pre-clinical Programme (4.5 years) and the Clinical Programme (1.5 years).").strip()
            pre = combined[intro_end + len("Pre-clinical Programme"):clinical].strip()
            clinic = combined[clinical + len("Clinical Programme"):].strip()
            data["description_lines"] = [intro, "Pre-clinical Programme", pre, "Clinical Programme", clinic]
    elif stem == "M.B.,_Ch.B":
        note = next((n for n in data.get("notes", []) if n.get("marker") == "3."), None)
        if note:
            roman = next((x for x in note.get("subsections", []) if x.get("marker") == "(v)"), None)
            trailing = [x for x in note.get("subsections", []) if x.get("marker") in {"(c)", "(d)"}]
            if roman and trailing:
                roman["subsections"].extend(trailing)
                note["subsections"] = [x for x in note["subsections"] if x not in trailing]
    elif stem == "Articulated_Bachelor_of_Science_Ph.D._Programme_in_Mathematical_Sciences":
        bachelor = group("Bachelor of Science in Mathematical Sciences", units="71", marker="1.", children=deepcopy(data["sections"]))
        for child in bachelor["subsections"]: child["marker"] = ""
        data["sections"] = [bachelor]
        data["total_units"] = "71 + 27 + 78"
    elif stem == "B.Sc._in_Mathematics":
        if len(data.get("sections", [])) < 3:
            return
        elective = data["sections"][2]
        stream_choice = next(
            (x for x in elective.get("subsections", []) if x.get("marker") == "(b)"),
            None,
        )
        stream_items = stream_choice.get("subsections", []) if stream_choice else elective.get("subsections", [])
        streams = {x.get("title"): x for x in stream_items}
        def eligible(subject, minimum):
            return [code for code in index if code.startswith(subject + " ") and int(code.split()[1][0]) >= minimum]
        computational_stream = streams.get("Computational and Applied Mathematics Stream", {})
        computational = next(
            (x for x in computational_stream.get("subsections", []) if x.get("marker") == "(ii)"),
            computational_stream or None,
        )
        math_levels = [code for code in index if re.fullmatch(r"MATH (?:32|33|42|43)\d{2}", code)]
        if computational:
            computational["codes"] = list(dict.fromkeys([*math_levels, *computational.get("codes", [])]))

        categories = []
        area_note = next((note for note in data.get("notes", [])
                          if "Subject Area Code" in note.get("text", "") and note.get("rows")), None)
        if area_note:
            labels = {
                "science": "Science Courses",
                "engineering": "Engineering Courses",
                "economics/finance": "Economics and Finance Courses",
            }
            for row in area_note.get("rows", []):
                if len(row) < 2:
                    continue
                label = labels.get(clean(str(row[0])).lower())
                subjects = re.findall(r"\b[A-Z]{4}\b", clean(" ".join(str(cell) for cell in row[1:])))
                if label and subjects:
                    categories.append((label, subjects))
        for title, marker in (("Mathematics Stream", "(ii)"), ("Mathematics-Multidisciplinary Stream", "(i)")):
            stream = streams.get(title, {})
            target = next(
                (x for x in stream.get("subsections", []) if x.get("marker") == marker),
                stream or None,
            )
            if not target:
                continue
            target.pop("course_groups", None)
            target["codes"] = []
            target["subsections"] = []
            if title == "Mathematics Stream":
                target["subsections"].append(group("BMED Courses at 3000 or above level",
                                                   codes=eligible("BMED", 3)))
            for category, subjects in categories:
                category_codes = []
                for subject in subjects:
                    category_codes.extend(eligible(subject, 2))
                target["subsections"].append(group(category, codes=category_codes))
        enrichment_stream = streams.get("Enrichment Stream", {})
        enrichment_e = next(
            (x for x in enrichment_stream.get("subsections", []) if x.get("marker") == "(e)"),
            None,
        )
        if enrichment_e:
            enrichment_e["codes"] = eligible("MATH", 3)
        for stream in streams.values():
            for item in stream.get("subsections", []):
                if item.get("marker") in {"(i)", "(ii)", "(iii)"}:
                    item["heading_as_text"] = True
    elif stem == "B.Sc._in_Natural_Sciences":
        for stream in data["sections"]:
            required = next((x for x in stream.get("subsections", []) if x.get("title") == "Required Courses"), None)
            elective = next((x for x in stream.get("subsections", []) if x.get("title", "").startswith("Elective Courses")), None)
            if elective:
                for child in elective.get("subsections", []):
                    if child.get("title") in {"Concentration Area Courses", "Other Science Courses"}:
                        child["keep_heading"] = True
            if stream.get("title") == "Physical Sciences" and required and required.get("subsections"):
                required["subsections"][0]["title"] = "9 units of courses shall be taken from the following courses"
    elif stem == "B.Sc._in_Physics":
        block = next((b for b in data.get("additional_requirements", []) if b.get("title") == "Streams"), None)
        if block:
            for stream in block["sections"]:
                if stream["title"] == "Enrichment Stream in Theoretical Physics":
                    req = stream["subsections"][0]
                    if len(req.get("text", [])) > 1:
                        text = req["text"].pop()
                        heading, body = text.split(":", 1)
                        req["subsections"].append(group(heading, [body], extract(body), "15 or 12", "(b)"))
                    stream["units"] = "22 or 25"
                else:
                    stream["units"] = "12"
                if stream["title"] == "Astrophysics and Particle Physics Stream":
                    elective_part = next(
                        (x for x in stream["subsections"] if x.get("marker") == "(b)"),
                        None,
                    )
                    if elective_part:
                        elective_part["units"] = "6"
                        elective_part["text"] = [x for x in elective_part["text"] if x != "6"]
        note_b = next((n for n in data.get("notes", []) if n.get("marker") == "[b]"), None)
        if note_b:
            note_b["text"] = "Students can be exempted from taking PHYS courses by taking the closely related course listed below. Units earned can be counted towards the Major Programme."
            note_b["rows"] = [["PHYS course", "Closely related course"], ["PHYS2051 Quantitative Methods for Basic Physics", "MATH2020/2028 Advanced Calculus II/Honours Advanced Calculus II"], ["PHYS2061 Basic Computational Physics", "MATH3230 Numerical Analysis"]]
    elif stem == "B.Sc._in_Risk_Management_Science":
        data["sections"][1]["units"] = "42 or 48"
        data["sections"][2]["units"] = "21 or 15"
        minimum_sentence = re.compile(
            r"\s*Students are required to complete a minimum of 72 units of courses as follows\.?\s*$",
            re.I,
        )
        for note in data.get("notes", []):
            note["text"] = minimum_sentence.sub("", note.get("text", ""))
            note["text"] = re.sub(r"\s*Risk Analytics Stream\s*$", "", note.get("text", "")).strip()
    elif stem == "B.Sc._in_Statistics":
        required, elective = data["sections"][1:3]
        required["subsections"] = [x for x in required["subsections"] if "Science, Technology" not in x.get("title", "")]
        required["units"] = "27 or 30 or 33"
        elective["units"] = "24 or 27"
        analytics = next(x for x in elective["subsections"] if x.get("title") == "Data Analytics Stream")
        first = analytics["subsections"][0]
        if first.get("text"):
            first["_published_data_analytics_text"] = " ".join(first["text"])
            heading, body = first["text"][0].split(":", 1)
            first["title"], first["text"], first["codes"] = heading, [body.strip()], extract(body)
            first["keep_heading"] = True
    elif stem == "B.S.Sc._in_Sociology":
        block = next((b for b in data.get("additional_requirements", []) if b.get("title") == "Concentration Area"), None)
        if block:
            sustainability = next(x for x in block["sections"] if x["title"] == "Society, Sustainability and Technology")
            sustainability["units"] = "18"
            sustainability["text"] = [re.sub(r"\s*18$", "", text) for text in sustainability.get("text", [])]
            for module in sustainability.get("subsections", []):
                lines = module.get("text", [])
                children, current = [], None
                for line in lines:
                    if line.rstrip(":") in {"Required Course", "Required Course(s)", "Elective Course(s)", "Elective Courses"}:
                        current = group(line.rstrip(":"))
                        children.append(current)
                    elif current:
                        current["text"].append(line)
                        current["codes"] = list(dict.fromkeys(current["codes"] + extract(line)))
                if children: module["text"], module["codes"], module["subsections"] = [], [], children


def option_group(title, source):
    copy = deepcopy(source)
    copy["marker"] = ""
    copy["title"] = title
    return copy


def _post_clean_review_fixes(data, index, extract):
    """Re-assert source-backed hierarchy after generic presentation cleanup."""
    stem = data["source_file"]
    if stem == "B.A._in_Japanese_Studies":
        item = next((x for x in data["sections"][1].get("subsections", []) if x.get("marker") == "(b)"), None)
        if item:
            item["title"] = "For Standard Scheme Only. Not for Local Study Scheme"
    elif stem == "B.A._in_Religious_Studies":
        section = data["sections"][2]
        ordinary_rules = []
        for item in section.get("subsections", [])[:2]:
            without = next((x for x in item.get("subsections", []) if x.get("title") == "Without Concentrations"), None)
            if without:
                rule = deepcopy(item)
                rule["subsections"] = []
                rule["codes"] = deepcopy(without.get("codes", []))
                if without.get("course_groups"):
                    rule["course_groups"] = deepcopy(without["course_groups"])
                ordinary_rules.append(rule)
        concentration = next((x for x in section.get("subsections", []) if x.get("title") == "Concentrations"), None)
        if ordinary_rules and concentration:
            section["subsections"] = [group("Without Concentrations", children=ordinary_rules), concentration]
        if concentration:
            for area in concentration.get("subsections", []):
                non_headings = {
                    "Religious Education": {"(a)", "(d)"},
                    "Religion and Health": {"(c)"},
                }.get(area.get("title"), set())
                for item in area.get("subsections", []):
                    if item.get("marker") in non_headings and item.get("title"):
                        item["text"] = [item["title"], *item.get("text", [])]
                        item["title"] = ""
                        item["heading_as_text"] = True
    elif stem == "B.B.A._(Integrated_BBA_Programme)_and_Juris_Doctor":
        heading = data.get("requirement_title", "")
        if heading:
            data["description"] = re.sub(rf"^{re.escape(heading)}\s*", "", data.get("description", "")).strip()
            data["description_lines"] = [line for line in data.get("description_lines", []) if clean(line) != clean(heading)]
    elif stem == "B.B.A._in_Professional_Accountancy":
        section = data["sections"][1]
        ordinary = next((x for x in section.get("subsections", []) if x.get("title") == "Students not in the Global Accounting Stream"), None)
        if ordinary and section.get("codes"):
            ordinary["text"], ordinary["codes"] = deepcopy(section.get("text", [])), deepcopy(section.get("codes", []))
            section["text"], section["codes"] = [], []
    elif stem in {
        "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme",
        "B.Eng._in_Materials_Science_and_Engineering_X_Double_Major_Programme",
        "B.Sc._in_Aerospace_Science_and_Earth_Informatics_X_Double_Major_Programme",
    }:
        choices = data["sections"][2]
        choice_totals = []
        for choice in choices.get("subsections", []):
            second_units = str(choice.pop("_second_major_units", "") or "33")
            elective = next((x for x in choice.get("subsections", []) if x.get("title") == "1st Major Elective Courses"), None)
            second_parts = [x for x in choice.get("subsections", []) if x is not elective]
            if elective:
                nested_choice = elective.get("subsections", [])
                if len(nested_choice) == 1 and nested_choice[0].get("subsections"):
                    nested = nested_choice[0]
                    elective["units"] = nested.get("units") or elective.get("units", "")
                    elective["subsections"] = deepcopy(nested["subsections"])
                    if not elective.get("text"):
                        elective["text"] = deepcopy(nested.get("text", []))
                elective["marker"] = "(a)"
            second = group("2nd Major Requirements", units=second_units, marker="(b)", children=second_parts)
            elective_units = re.fullmatch(r"\d+", str((elective or {}).get("units", "")))
            second_value = re.fullmatch(r"\d+", second_units)
            total = str(int(elective_units.group()) + int(second_value.group())) if elective_units and second_value else ""
            choice["units"] = total
            if total:
                choice_totals.append(total)
            choice["subsections"] = [elective, second] if elective else [second]
        unique_totals = list(dict.fromkeys(choice_totals))
        choices["units"] = " or ".join(unique_totals)
    elif stem == "B.Eng._in_Information_Engineering":
        section = data["sections"][3]
        streams = next((x for x in section.get("subsections", []) if x.get("title") == "Streams"), None)
        names = {"Big Data: Systems and Applications", "Telecommunications", "Cyber Security",
                 "Networked Systems and Applications", "Information Science"}
        if streams:
            variants = [x for x in section["subsections"] if x.get("title") in names]
            section["subsections"] = [x for x in section["subsections"] if x not in variants]
            streams["subsections"] = variants
            network = next((x for x in variants if x.get("title") == "Networked Systems and Applications"), None)
            if network:
                network["codes"] = []
    elif stem == "B.Sc._in_Mathematics_and_Information_Engineering":
        route = next((x for x in data["sections"][0].get("subsections", []) if x.get("marker") == "(d)"), None)
        package = route.get("subsections", [None])[0] if route else None
        if package:
            package["text"], package["codes"] = [], []
            package["subsections"] = [
                group("Group C", ["MATH1010/1018"], extract("MATH1010/1018")),
                group("Group E", ["STAT1011"], extract("STAT1011")),
                group("A course from the following", children=[
                    group("Group A", ["LSCI1001 or 1002"], extract("LSCI1001 or 1002")),
                    group("Group B", ["CHEM1070 or 1072 or 1280"], extract("CHEM1070 or 1072 or 1280")),
                    group("Group D", ["PHYS1001 or 1002 or 1111 or 1113"], extract("PHYS1001 or 1002 or 1111 or 1113")),
                ]),
            ]
    elif stem == "B.Sc._in_Natural_Sciences":
        for stream in data["sections"]:
            elective = next((x for x in stream.get("subsections", []) if x.get("title", "").startswith("Elective Courses")), None)
            if not elective:
                continue
            if len(elective.get("text", [])) >= 3 and (not elective.get("subsections") or not any(x.get("codes") for x in elective["subsections"])):
                intro, concentration, other = elective["text"][:3]
                intro = re.sub(r"\s*Concentration Area Courses\s*:\s*$", "", intro).strip()
                elective["text"], elective["codes"] = [intro], []
                elective["subsections"] = [
                    group("Concentration Area Courses", [concentration], extract(concentration)),
                    group("Other Science Courses", [other], extract(other)),
                ]
                continue
            if elective.get("subsections"):
                continue
            children, intro = [], []
            for text in elective.get("text", []):
                match = re.match(r"^(Concentration Area Courses|Other Science Courses)\s*:\s*(.*)$", text)
                if match:
                    body = match.group(2).strip()
                    children.append(group(match.group(1), [body] if body else [], extract(body)))
                else:
                    intro.append(text)
            if children:
                elective["text"], elective["codes"], elective["subsections"] = intro, [], children
        physical = next((x for x in data["sections"] if x.get("title") == "Physical Sciences"), None)
        if physical:
            required = next((x for x in physical.get("subsections", []) if x.get("title") == "Required Courses"), None)
            if required and required.get("subsections"):
                required["subsections"][0]["title"] = "9 units of courses shall be taken from the following courses"
    elif stem == "B.Sc._in_Mathematics":
        for item in walk(data["sections"][2].get("subsections", [])):
            if item.get("marker") in {"(i)", "(ii)", "(iii)", "(e)"} and item.get("title"):
                item["text"] = [item["title"], *item.get("text", [])]
                item["title"] = ""
                item["heading_as_text"] = True
    elif stem == "B.Sc._in_Risk_Management_Science":
        unwanted = clean("Students are required to complete a minimum of 72 units of courses as follows")

        def remove_trailing_requirement(groups):
            kept = []
            for item in groups:
                if clean(item.get("title", "")).rstrip(".") == unwanted.rstrip("."):
                    continue
                item["subsections"] = remove_trailing_requirement(item.get("subsections", []))
                kept.append(item)
            return kept

        for note in data.get("notes", []):
            note["text"] = re.sub(
                r"\s*Students are required to complete a minimum of 72 units of courses as follows\.?\s*$",
                "", note.get("text", ""), flags=re.I,
            ).strip()
            note["subsections"] = remove_trailing_requirement(note.get("subsections", []))
    elif stem == "B.Sc._in_Physics":
        block = next((b for b in data.get("additional_requirements", []) if b.get("title") == "Streams"), None)
        if block:
            enrichment = next((x for x in block.get("sections", []) if x.get("title") == "Enrichment Stream in Theoretical Physics"), None)
            if enrichment:
                required = next((x for x in enrichment.get("subsections", []) if x.get("marker") == "(a)"), None)
                nested_b = next((x for x in required.get("subsections", []) if x.get("marker") == "(b)"), None) if required else None
                if nested_b:
                    required["subsections"].remove(nested_b)
                    nested_b["title"] = "Elective courses (of which at least two courses from MATH4030, PHYS4011, 4021[j], 4041[j], 4460)"
                    nested_b["text"] = [re.sub(r"^\(b\)\s*Elective courses \(of which at least two courses from MATH4030, PHYS4011, 4021\[j\], 4041\[j\], 4460\)\s*:?\s*", "", text).strip()
                                        for text in nested_b.get("text", [])]
                    nested_b["text"] = [text for text in nested_b["text"] if text]
                    enrichment["subsections"].append(nested_b)
    elif stem == "B.Sc._in_Statistics":
        analytics = next((x for x in data["sections"][2].get("subsections", []) if x.get("title") == "Data Analytics Stream"), None)
        first = analytics.get("subsections", [None])[0] if analytics else None
        if first:
            source_texts = list(first.get("text", []))
            first["title"] = ("Eight courses from the following (with at least one from STAT3006 or STAT4001, "
                              "at least three from STAT or RMSC courses, at least two from AIST or CSCI or ENGG courses, "
                              "and at least three courses coded at 4000 or above level)")
            published = first.pop("_published_data_analytics_text", "")
            if ":" in published:
                published = published.split(":", 1)[1].strip()
            retained = []
            for text in source_texts:
                if clean(text).startswith(clean(first["title"])):
                    # clean_presentation may have moved the complete source
                    # row into prose because the instruction is long.  Keep
                    # the course expression following its first colon.
                    if ":" in text:
                        body = text.split(":", 1)[1].strip()
                        if body:
                            retained.append(body)
                else:
                    retained.append(text)
            first["text"] = retained or ([published] if published else [])
    elif stem == "B.S.Sc._in_Sociology":
        block = next((b for b in data.get("additional_requirements", []) if b.get("title") == "Concentration Area"), None)
        human = next((x for x in block.get("sections", []) if x.get("title") == "Human Security and Social Governance"), None) if block else None
        if human:
            modules = {x.get("marker"): x for x in human.get("subsections", [])}
            source = {
                "(a)": ("Any 6-9 units from SOCI2106, 3001, 3207, 3230, 3241",
                         "ECON3250, 3310, 3320, 3350, 3370, 3380, 3610, 3630, GLSD2501, 3501, 4102, 4104, GRMD2321, 3402, URSP2010, 2200"),
                "(b)": ("Any 6-9 units from SOCI2116, 2220, 3204, 3234, 3242",
                         "ANTH2530, 3540, COMM3600, 3710, GDRS5210, GLSD3301, 4401, 4402, GPAD1100, 2070, 2085, 2300, 2345, PSYC3370, SOWK4350"),
                "(c)": ("Any 6-9 units from SOCI2208, 2219, 3224, 3236, 3244, 4205",
                         "ARCH3321, 3721, DSPS2301, 3310, 3340, 3790, 3803, GDRS3005, 3006, 3007, 3008, 3024, 4006, 4007, 4008, 4011, 4012, GLSD3105, GRMD2303, 2401, 2404, 2501, 3202, 3203, 3302, 3323, 3404, 4403, 4503, PSYC3630, SOWK3340, URSP2010, 2020, 2030, 2040, 2050, 2060, 2070, 2100, 2300, 2400, 2800, 2900, 3100, 3200, 3300, 3400, 3600, 3700, 4100"),
            }
            for marker, (base, optional) in source.items():
                item = modules.get(marker)
                if item:
                    item["text"], item["codes"] = [base], extract(base)
                    item["subsections"] = [group("Optional Interdisciplinary Cluster",
                        ["A maximum of 3 units from one of the following courses can be counted towards the fulfillment of 3 units in this cluster:", optional], extract(optional))]
            capstone = next((x for x in human.get("subsections", []) if x.get("title") == "Capstone Project / Internship / Field Studies in Human Security"), None)
            if capstone:
                sentence = "A maximum of 3 units from one of the following can be counted towards the fulfillment of 3 units in any one of the clusters of the concentration listed above:"
                courses = "SOCI3245[a]/4211[b], 4020[c], 4202"
                capstone["text"], capstone["codes"] = [sentence, courses], extract(courses)
        if block:
            for area in block.get("sections", []):
                if not area.get("units"):
                    joined = " ".join(area.get("text", []))
                    stated = re.search(r"At least\s+(\d+(?:-\d+)?)\s+units", joined, re.I)
                    if stated:
                        area["units"] = stated.group(1)
                    else:
                        values = [int(item["units"]) for item in area.get("subsections", [])
                                  if str(item.get("units", "")).isdigit()]
                        if values:
                            area["units"] = str(sum(values))
                for item in area.get("subsections", []):
                    stated = re.search(r"at least\s+(\d+(?:-\d+)?)\s+units", item.get("title", ""), re.I)
                    if stated and not item.get("units"):
                        item["units"] = stated.group(1)

    # Exact or prefix duplicates are presentation artefacts caused by a
    # source row carrying both its instruction and its course expression.
    # Apply this to every programme so a changed future-year row is handled
    # without another programme-specific edit.
    roots = data.get("sections", []) + [section for block in data.get("additional_requirements", [])
                                        for section in block.get("sections", [])]
    for item in walk(roots):
        title = clean(item.get("title", "")).rstrip(":")
        if not title:
            continue
        item["text"] = [text for text in item.get("text", [])
                        if clean(text).rstrip(":") != title
                        and not clean(text).startswith(title + ":")]


def _attach_area_catalogue(item, areas):
    """Attach source-derived area lists as one labelled course table."""
    selected = [area for area in areas if area.get("codes")]
    if not selected:
        return
    excluded = set(item.get("excluded_codes", []))
    item["course_groups"] = [
        {"label": area["title"], "codes": [code for code in area["codes"] if code not in excluded]}
        for area in selected
    ]
    item["codes"] = list(dict.fromkeys(
        code for area in selected for code in area.get("codes", []) if code not in excluded
    ))


def _repair_legacy_notes(data):
    """Recover footnote rows that Word appended to the preceding note table."""
    rebuilt = []
    for note in data.get("notes", []):
        text = clean(note.get("text", ""))
        if text.startswith("[ ] Old course code"):
            note["marker"] = "[ ]"
            note["text"] = text[3:].strip()
        extra = []
        rows = []
        for row in note.get("rows", []):
            cells = [clean(str(cell)) for cell in row]
            if len(cells) >= 2 and re.fullmatch(r"\[\s*\]", cells[0]) and clean(" ".join(cells[1:])):
                extra.append({"marker": "[ ]", "text": clean(" ".join(cells[1:])),
                              "subsections": [], "rows": []})
            else:
                rows.append(row)
        note["rows"] = rows
        rebuilt.append(note)
        rebuilt.extend(extra)
    # Avoid duplicate legend rows when Word exposed the same line twice.
    seen = set()
    data["notes"] = []
    for note in rebuilt:
        fingerprint = (note.get("marker", ""), clean(note.get("text", "")))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        data["notes"].append(note)

    for note in data.get("notes", []):
        text = note.get("text", "")
        matches = list(re.finditer(r"(?<!\w)(?:and\s+)?([ivxlcdm]+)\.\s+", text, re.I))
        if len(matches) >= 2 and ":" in text[:matches[0].start() + 1]:
            paragraphs = [text[:matches[0].start()].strip()]
            for position, match in enumerate(matches):
                stop = matches[position + 1].start() if position + 1 < len(matches) else len(text)
                body = text[match.end():stop].strip(" ;")
                paragraphs.append(f"{match.group(1).lower()}. {body}")
            note["paragraphs"] = [paragraph for paragraph in paragraphs if paragraph]

        # Keep roman alternatives as peer subpoints.  The notes renderer puts
        # the first one on the bracketed note's first line, so (i), (ii), ...
        # retain identical styling and indentation.


def _cross_year_source_repairs(data, path, index, extract):
    """Normalize equivalent requirements whose Word layout varies by year."""
    stem = data["source_file"]
    _repair_legacy_notes(data)

    if stem == "B.A._in_Cultural_Management":
        areas = source_areas(path, extract)
        wanted = {"(a)": "Area 1:", "(b)": "Area 3:", "(c)": "Area 4:"}
        for item in data["sections"][2].get("subsections", []):
            prefix = wanted.get(item.get("marker"))
            if prefix:
                _attach_area_catalogue(item, [area for area in areas if area["title"].startswith(prefix)])

    elif stem == "B.A._in_Cultural_Studies":
        section = data["sections"][2]
        own_areas = source_areas(path, extract)
        religious_areas = source_areas(path.parent / "B.A._in_Religious_Studies.html", extract)
        item_a = next((item for item in section.get("subsections", []) if item.get("marker") == "(a)"), None)
        item_c = next((item for item in section.get("subsections", []) if item.get("marker") == "(c)"), None)
        if item_a:
            _attach_area_catalogue(item_a, religious_areas)
        if item_c:
            used = {code for earlier in data["sections"][:2] for node in walk([earlier]) for code in node.get("codes", [])}
            for sibling in section.get("subsections", []):
                if sibling is not item_c:
                    used.update(sibling.get("codes", []))
            eligible = [
                code for code in index
                if code.startswith("CURE ") and int(code.split()[1]) >= 2000
                and not re.fullmatch(r"CURE [2-5][45]\d{2}", code)
                and code not in used
            ]
            cultural = {code for area in own_areas for code in area.get("codes", []) if code in eligible}
            other = [code for code in eligible if code not in cultural]
            item_c["codes"] = eligible
            item_c["excluded_codes"] = sorted(
                code for code in index if re.fullmatch(r"CURE [2-5][45]\d{2}", code)
            )
            item_c["course_groups"] = [
                {"label": area["title"], "codes": [code for code in area["codes"] if code in cultural]}
                for area in own_areas if any(code in cultural for code in area["codes"])
            ]
            if other:
                item_c["course_groups"].append({"label": "Other Eligible CURE Courses", "codes": other})

    elif stem in {"B.A._in_Religious_Studies", "B.A._in_Theology"}:
        religious = source_areas(
            path if stem == "B.A._in_Religious_Studies" else path.parent / "B.A._in_Religious_Studies.html",
            extract,
        )
        cultural = source_areas(path.parent / "B.A._in_Cultural_Studies.html", extract)
        if not cultural:
            cultural = [
                area for area in source_areas(
                    path.parent / "B.A._in_Public_Humanities.html", extract
                )
                if area.get("title", "").startswith("Cultural Studies Area")
            ]
        for item in walk(data.get("sections", [])):
            prose = clean(" ".join([item.get("title", ""), *item.get("text", [])]))
            outside_cultural = bool(re.search(
                r"(?:outside\s+(?:the\s+)?|except\s+those\s+listed\s+under\s+)Cultural Studies Areas",
                prose, re.I,
            ))
            if outside_cultural:
                item.pop("course_groups", None)
                if any(child.get("title") == "CURE Courses Outside Cultural Studies Areas"
                       for child in item.get("subsections", [])):
                    item["codes"] = []
            elif "Religious Studies Area" in prose and "Cultural Studies Area" in prose:
                _attach_area_catalogue(item, [*cultural, *religious])
            elif "Religious Studies Area" in prose:
                _attach_area_catalogue(item, religious)
            elif "Cultural Studies Area" in prose:
                _attach_area_catalogue(item, cultural)
            if item.get("title") == "CURE Courses Outside Cultural Studies Areas":
                excluded = {code for area in cultural for code in area.get("codes", [])}
                item["codes"] = [code for code in index if code.startswith("CURE ") and code not in excluded]
                item.pop("course_groups", None)

    elif stem == "B.A._(Chinese_Language_Studies)_and_B.Ed._(Chinese_Language_Education)":
        heading = "Major Programme Requirement"
        data["description"] = re.sub(rf"^{heading}\s*", "", data.get("description", ""), flags=re.I)
        data["description_lines"] = [
            line for line in data.get("description_lines", []) if clean(line).lower() != heading.lower()
        ]
        elective = data["sections"][2]
        groups = elective.get("subsections", [])
        if len(groups) >= 4:
            first, second = groups[:2], groups[2:]
            for item in walk(first + second):
                item["text"] = [text for text in item.get("text", [])
                                if clean(text) not in {"Chinese Language and Literature", "Chinese Language Education"}]
                title = clean(item.get("title", ""))
                if title:
                    item["text"] = [re.sub(rf"^{re.escape(title)}\s+", "", text).strip()
                                    for text in item.get("text", [])]
            elective["text"] = [text for text in elective.get("text", [])
                                if clean(text) not in {"Chinese Language and Literature", "Chinese Language Education"}]
            elective["subsections"] = [
                group("Chinese Language and Literature", children=first),
                group("Chinese Language Education", children=second),
            ]

    elif stem == "B.Ed._in_Mathematics_and_Mathematics_Education":
        section = data["sections"][2]
        parent_b = next((item for item in section.get("subsections", []) if item.get("marker") == "(b)"), None)
        if parent_b:
            position = section["subsections"].index(parent_b)
            trailing = []
            for item in section["subsections"][position + 1:]:
                if item.get("marker"):
                    break
                trailing.append(item)
            parent_b["subsections"].extend(trailing)
            section["subsections"] = [item for item in section["subsections"] if item not in trailing]

    elif stem == "B.Ed._in_Physical_Education,_Exercise_Science_and_Health":
        section = data["sections"][2]
        roots = []
        current = None
        for item in section.get("subsections", []):
            nested_markers = [child for child in item.get("subsections", []) if child.get("marker") == "(c)"]
            item["subsections"] = [child for child in item.get("subsections", []) if child not in nested_markers]
            if item.get("marker"):
                roots.append(item)
                current = item
            elif current is not None:
                current["subsections"].append(item)
            else:
                roots.append(item)
            for nested in nested_markers:
                roots.append(nested)
                current = nested
        section["subsections"] = roots

    elif stem == "B.Sc._in_Earth_and_Environmental_Sciences":
        section = data["sections"][2]
        children = section.get("subsections", [])
        rebuilt = []
        cursor = 0
        labels = {"(a)": "Intermediate-level Earth and Environmental Sciences",
                  "(b)": "Advanced Earth and Environmental Sciences"}
        while cursor < len(children):
            item = children[cursor]
            marker = item.get("marker")
            if marker not in labels:
                rebuilt.append(item)
                cursor += 1
                continue
            variants = []
            while cursor < len(children) and (not variants or not children[cursor].get("marker")):
                variant = children[cursor]
                variant["marker"] = ""
                variants.append(variant)
                cursor += 1
            rebuilt.append(group(labels[marker], marker=marker, children=variants))
        section["subsections"] = rebuilt

    elif stem == "B.Sc._in_Natural_Sciences":
        data["description"] = re.sub(r"\s+Biological Sciences\s*$", "", data.get("description", "")).strip()

    elif stem == "B.Sc._in_Physics":
        for block in data.get("additional_requirements", []):
            if block.get("title") != "Streams":
                continue
            for item in walk(block.get("sections", [])):
                item["text"] = [
                    re.sub(r"\s+\d+\s+or\s+\d+\s*\[[^]]+\]\s*$", "", text).strip()
                    for text in item.get("text", [])
                ]

    elif stem == "B.Sc._in_Statistics":
        elective = data["sections"][2]
        for stream in elective.get("subsections", []):
            first = next((item for item in stream.get("subsections", []) if item.get("marker") == "(a)"), None)
            if not first:
                continue
            combined = clean(" ".join(first.get("text", [])))
            match = re.search(r"\bOne capstone/research course from\b", combined, re.I)
            if not match:
                continue
            body, capstone = combined[:match.start()].strip(), combined[match.start():].strip()
            first["text"], first["codes"] = ([body] if body else []), extract(body)
            stream["subsections"].append(group("", [capstone], extract(capstone), marker="(b)"))

    if stem == "B.A._in_Japanese_Studies":
        elective = data["sections"][2]
        for route in elective.get("subsections", [])[:2]:
            for scheme in route.get("subsections", []):
                if scheme.get("title") != "Local Study Scheme":
                    continue
                stated = re.search(r"(?:take|complete)\s+(\d+)\s+units", " ".join(scheme.get("text", [])), re.I)
                if stated:
                    scheme["units"] = stated.group(1)
            route["units"] = " or ".join(dict.fromkeys(
                child.get("units", "") for child in route.get("subsections", []) if child.get("units")
            ))
        standard = list(dict.fromkeys(
            child.get("units", "") for route in elective.get("subsections", [])[:2]
            for child in route.get("subsections", []) if child.get("title") == "Standard Scheme" and child.get("units")
        ))
        local = list(dict.fromkeys(
            child.get("units", "") for route in elective.get("subsections", [])[:2]
            for child in route.get("subsections", []) if child.get("title") == "Local Study Scheme" and child.get("units")
        ))
        if standard or local:
            parts = []
            if standard: parts.append(f"{' or '.join(standard)} (Standard)")
            if local: parts.append(f"{' or '.join(local)} (Local)")
            elective["units"] = "; ".join(parts)

    if stem in {"B.S.Sc._in_Economics", "B.S.Sc._in_Geography_and_Resource_Management", "B.S.Sc._in_Psychology"}:
        block = next((item for item in data.get("additional_requirements", [])
                      if item.get("title") == "Concentration Area"), None)
        if block:
            values = re.findall(r"(?:at least\s+)?(\d+)\s+units", block.get("description", ""), re.I)
            if values:
                block["total_units"] = " or ".join(dict.fromkeys(values))

    # A heading such as “Streams” or “Concentration Areas” introduces the
    # choices that follow it.  Some Word exports flatten those choices into
    # siblings; restore the semantic parent in every programme/year.
    choice_headings = {"Streams", "Streams of Specialization", "Concentration Area", "Concentration Areas"}
    for container in walk(data.get("sections", [])):
        children = container.get("subsections", [])
        for position, heading in enumerate(list(children)):
            if heading.get("title") not in choice_headings or heading.get("subsections"):
                continue
            variants = children[position + 1:]
            if not variants:
                continue
            heading["subsections"] = variants
            heading["keep_heading"] = True
            del children[position + 1:]
            break

    if stem == "B.A._(English_Studies)_and_B.Ed._(English_Language_Education)":
        subject = next((item for item in data["sections"][2].get("subsections", [])
                        if item.get("marker") == "(a)"), None)
        if subject:
            match = re.match(r"^(Subject Knowledge)\s+(\d+\s+units of courses chosen from the following)\s*$",
                             clean(subject.get("title", "")), re.I)
            if match:
                subject["title"] = match.group(1)
                instruction = match.group(2) + ":"
                if instruction not in subject.get("text", []):
                    subject["text"].insert(0, instruction)

    elif stem == "B.Ed._in_Early_Childhood_Education":
        for item in data["sections"][2].get("subsections", []):
            match = re.search(r"maximum of\s+(\d+)\s+units", item.get("title", ""), re.I)
            if item.get("marker") == "(c)" and match:
                item["units"] = f"max. {match.group(1)}"

    elif stem == "B.Ed._in_Mathematics_and_Mathematics_Education":
        package = data["sections"][0]
        component_units = [int(item["units"]) for item in package.get("subsections", [])
                           if re.fullmatch(r"\d+", str(item.get("units", "")))]
        if component_units and len(component_units) == len(package.get("subsections", [])):
            package["units"] = str(sum(component_units))


def apply_revision_fixes(data, path, index, extract):
    _merge_japanese_local_scheme(data)
    _group_area_tables(data)
    _translation_note_tables(data, extract)
    _integrated_bba_and_jd(data, extract)
    _merge_accountancy_streams(data)
    _small_programme_repairs(data, extract)
    _engineering_note_repairs(data, extract)
    _law_and_health_repairs(data, index)
    _restore_mathematics_source_structure(data)
    _natural_science_stream_headings(data, extract)
    _social_science_repairs(data)
    _merge_simple_stream_variants(data)
    _physics_and_medicine_repairs(data)
    _double_major_grouping(data)
    _split_labelled_concentration_parts(data, extract)
    _diplomacy_language_table(data, index)
    _merge_math_information_engineering_routes(data)
    _earth_stream_differences(data, extract)
    _latest_review_fixes(data, index, extract)


def improve_readability(data, path, index, extract):
    stem = data["source_file"]
    areas = source_areas(path, extract)
    if stem == "B.A._in_English":
        split_english(data, extract)
        data["sections"][2]["combine_text_boxes"] = True
    elif stem == "B.A._in_Fine_Arts":
        split_fine_arts(data, extract)
        refine_fine_arts(data, extract)
    elif stem == "B.A._in_History":
        resolve_history(data, index, extract)
    elif stem == "B.A._in_Linguistics":
        resolve_linguistics(data, areas, index, extract)
    elif stem == "B.A._in_Music":
        resolve_music(data, areas, extract)
    elif stem == "B.A._in_Philosophy":
        required = {code for item in walk([data["sections"][1]]) for code in item["codes"]} | {"PHIL 1110"}
        for area in areas:
            area["codes"] = [code for code in area["codes"] if code not in required]
        data["sections"][2]["codes"] = []
        refine_philosophy(data, areas)
    if stem == "B.A._in_Anthropology":
        refine_anthropology_notes(data)
    elif stem == "B.A._in_Bimodal_Bilingual_Studies":
        split_inline_note_points(data)
    elif stem == "B.A._in_Chinese_Studies":
        refine_chinese_studies(data, extract)
    elif stem == "B.A._in_Japanese_Studies":
        refine_japanese(data)
    elif stem == "B.A._in_Linguistics":
        refine_linguistics(data)
    repair_integrated_bba_concentrations(data)
    structure_accountancy_streams(data)
    structure_behm_concentrations(data, extract)
    structure_early_childhood_required(data, extract)
    structure_mathematics_education(data, index, extract)
    structure_science_course_choices(data, extract)
    structure_stream_introductions(data)
    structure_electronic_engineering_guidance(data, extract)
    structure_diplomacy_labels(data, extract)
    nest_law_streams(data)
    promote_offering_labels(data)
    refine_quantitative_finance(data)
    separate_second_degree(data)
    split_merged_english_education_notes(data)
    structure_inline_note_points(data)
    structure_medicine_group_lists(data, extract)
    structure_medicine_concentrations(data, extract)
    structure_science_faculty_package(data, extract)
    structure_science_named_headings(data, extract)
    structure_biochemistry_lists(data, extract)
    structure_campus_course_labels(data, extract)
    refine_chinese_medicine_description(data, path)
    refine_articulated_mathematics(data, path, extract)
    resolve_named_areas(data, path, areas, index, extract)
    if stem == "B.A._in_Theology":
        refine_theology(data, areas)
    nest_concentrations(data)
    resolve_level_rules(data, index, extract)
    flatten_misnested_roman_groups(data)
    refine_social_science_sections(data, index, extract)
    add_social_concentrations(data, path, extract)
    add_physics_streams(data, path, extract)
    trim_stream_material_from_notes(data)
    structure_mathematics_streams(data)
    apply_revision_fixes(data, path, index, extract)
    for item in walk(data["sections"]):
        prose = " ".join([item["title"], *item["text"]])
        excluded = explicit_exclusions(prose, extract)
        if excluded:
            item["excluded_codes"] = sorted(set(item.get("excluded_codes", [])) | excluded)
            item["codes"] = [code for code in item["codes"] if code not in excluded]
    if stem in {
        "B.A._in_Chinese_Language_and_Literature", "B.A._in_Chinese_Studies",
        "B.A._in_Japanese_Studies", "B.A._in_Linguistics",
        "B.A._in_Public_Humanities", "B.A._in_Religious_Studies",
        "B.A._in_Translation",
    }:
        data["sections"][0]["combine_text_boxes"] = True
    clean_presentation(data)
    # Some Word-table labels become visible only after clean_presentation
    # separates a label ending in a colon from its following course list.
    structure_science_course_choices(data, extract)
    structure_stream_introductions(data)
    structure_campus_course_labels(data, extract)
    # A few source labels are deliberately headings even though the generic
    # presentation cleanup would normally split them at a colon or treat a
    # long instruction as prose. Re-assert those source-backed structures.
    _integrated_bba_and_jd(data, extract)
    _engineering_note_repairs(data, extract)
    if stem == "B.Eng._in_Electronic_Engineering":
        note3 = next((note for note in data.get("notes", []) if note.get("marker") == "3."), None)
        if note3:
            for subsection in note3.get("subsections", []):
                subsection["preserve_colon_lines"] = True
    if stem == "B.Ed._in_Mathematics_and_Mathematics_Education":
        option_i = next((item for item in walk(data["sections"]) if item.get("marker", "") == "(I)"), None)
        if option_i:
            option_i["title"] = "Option I: Mathematics Courses"
            option_i.pop("heading_as_text", None)
    _post_clean_review_fixes(data, index, extract)
    _cross_year_source_repairs(data, path, index, extract)
    _integrated_bba_variant_headings(data)
    _nest_leading_instruction_choices(data)
    _restore_course_expression_boxes(data)
    _final_attached_review_fixes(data, index, extract)


def _nest_leading_instruction_choices(data):
    """Make a published choice instruction the parent of its alternatives."""
    for section in data.get("sections", []):
        children = section.get("subsections", [])
        if len(children) < 2:
            continue
        first = children[0]
        prose = clean(" ".join([first.get("title", ""), *first.get("text", [])]))
        if (
            not first.get("marker")
            and re.match(r"Students? (?:must|(?:are )?required to) (?:choose|complete)", prose, re.I)
            and any(child.get("marker") for child in children[1:])
        ):
            first["title"] = prose.rstrip(":")
            first["text"] = []
            first["subsections"] = children[1:]
            first["keep_heading"] = True
            section["subsections"] = [first]
            children = section["subsections"]

        choice_titles = {"Streams", "Streams of Specialization", "Concentration Area", "Concentration Areas"}
        for position, heading in enumerate(list(children)):
            if heading.get("title") not in choice_titles or heading.get("subsections"):
                continue
            alternatives = children[position + 1:]
            if alternatives:
                heading["subsections"] = alternatives
                heading["keep_heading"] = True
                del children[position + 1:]
            break


def _structure_japanese_senior_routes(data):
    if data.get("source_file") != "B.A._in_Japanese_Studies":
        return
    elective = next((section for section in data.get("sections", []) if section.get("marker") == "3."), None)
    if not elective:
        return
    children = elective.get("subsections", [])
    if len(children) < 5 or not clean(" ".join(children[0].get("text", []))).startswith("Students may choose"):
        return
    with_index = next((
        position for position, item in enumerate(children)
        if "Students choosing a stream" in clean(" ".join([item.get("title", ""), *item.get("text", [])]))
    ), None)
    if with_index is None or with_index <= 1:
        return
    overview = children[0]
    overview["title"] = overview["text"].pop(0)
    overview["keep_heading"] = True
    without = children[1]
    without["title"] = "Without Stream"
    without["keep_heading"] = True
    without["subsections"] = children[2:with_index]
    with_stream = children[with_index]
    with_stream["title"] = "With Stream"
    with_stream["keep_heading"] = True
    with_stream["subsections"] = children[with_index + 1:]

    # Word places the next roman-numbered stream heading inside the final
    # requirement row of the preceding stream.  Recover those boundaries and
    # restore the first heading, which is lost entirely by that export shape.
    raw_requirements = with_stream["subsections"]
    current = group("Business and Management", marker="(i)")
    streams = [current]
    for requirement in raw_requirements:
        boundaries = [
            child for child in requirement.get("subsections", [])
            if re.fullmatch(r"\([ivxlcdm]+\)", child.get("marker", ""), re.IGNORECASE)
        ]
        requirement["subsections"] = [
            child for child in requirement.get("subsections", []) if child not in boundaries
        ]
        current["subsections"].append(requirement)
        for boundary in boundaries:
            boundary["subsections"] = []
            boundary["keep_heading"] = True
            streams.append(boundary)
            current = boundary
    if [stream.get("marker") for stream in streams] == ["(i)", "(ii)", "(iii)"]:
        with_stream["subsections"] = streams
    overview["subsections"] = [without, with_stream]
    elective["subsections"] = [overview]


def repair_reviewed_variant_labels(data):
    """Correct source labels that Word's merged unit/heading cells distort."""
    stem = data.get("source_file")
    if stem == "B.A._in_Chinese_Language_and_Literature":
        for item in walk(data.get("sections", [])):
            prose = clean(" ".join(item.get("text", [])))
            if item.get("marker") == "(ii)" and re.search(r"complete 15 units", prose, re.I):
                item["units"] = "15"

    if stem == "B.A._in_Translation":
        for item in walk(data.get("sections", [])):
            if item.get("marker") == "(a)" and item.get("codes") == [
                "TRAN 1010", "TRAN 1030", "TRAN 2070", "TRAN 2610"
            ]:
                item["units"] = ""

    if stem == "B.A._in_Linguistics":
        for item in walk(data.get("sections", [])):
            if item.get("marker") != "(i)" or not item.get("text"):
                continue
            match = re.match(r"Core Linguistics\s+(.*)", clean(item["text"][0]), re.I)
            if match:
                item["title"] = "Core Linguistics"
                item["text"][0] = match.group(1)
                item.pop("heading_as_text", None)
                item["keep_heading"] = True


def _promote_first_text(item, *, clear_units=False):
    """Turn a published leading instruction into the item's visible heading."""
    if item.get("title") or not item.get("text"):
        return False
    item["title"] = clean(item["text"].pop(0)).rstrip(":")
    item["keep_heading"] = True
    if clear_units:
        item["units"] = ""
    return True


def _compact_science_faculty_packages(data):
    """Render Science Faculty Package groups as one source-like box and table."""
    if data.get("faculty") != "Science":
        return
    candidates = list(data.get("sections", []))
    candidates.extend(
        section
        for block in data.get("additional_requirements", [])
        for section in block.get("sections", [])
    )
    for section in candidates:
        if section.get("title") != "Faculty Package":
            continue
        group_count = sum(
            bool(re.match(r"^Group\s+[A-Z]\b", item.get("title", ""), re.I))
            for item in walk(section.get("subsections", []))
        )
        if group_count < 2:
            continue
        lines = list(section.get("text", []))
        codes = list(section.get("codes", []))

        def flatten(items):
            for item in items:
                title = clean(item.get("title", "")).rstrip(":")
                body = clean(" ".join(item.get("text", [])))
                if title:
                    lines.append(f"{title}: {body}" if body else title)
                elif body:
                    lines.append(body)
                codes.extend(item.get("codes", []))
                flatten(item.get("subsections", []))

        flatten(section.get("subsections", []))
        section["text"] = list(dict.fromkeys(line for line in lines if clean(line)))
        section["codes"] = list(dict.fromkeys(codes))
        section["subsections"] = []
        section.pop("course_groups", None)


def _compact_subject_course_choices(data):
    """Keep short Chemistry/Life Science/Physics choices in one compact box."""
    for item in walk(data.get("sections", [])):
        children = item.get("subsections", [])
        if len(children) < 2:
            continue
        labels = [clean(child.get("title", "")) for child in children]
        if not all(re.match(r"^(?:Chemistry|Life Science|Physics) Courses(?:\[[^]]+\])?$", label, re.I) for label in labels):
            continue
        lines = []
        codes = []
        for child in children:
            body = clean(" ".join(child.get("text", [])))
            lines.append(f"{clean(child.get('title', '')).rstrip(':')}: {body}".rstrip())
            codes.extend(child.get("codes", []))
        item["text"] = lines
        item["codes"] = list(dict.fromkeys(codes))
        item["subsections"] = []


def _promote_reviewed_instruction_headings(data):
    """Restore headings explicitly identified in the final page review."""
    stem = data.get("source_file")
    targets = {
        "B.A._in_Theology": ("At least two courses at 2000 or above level",),
        "B.Sc._in_Biochemistry": ("Of the 17 units of elective courses",),
        "B.Sc._in_Biology": ("At least 5 units chosen from the following",),
        "B.Sc._in_Chemistry": ("At least 5 units chosen from the following",),
        "B.S.Sc._in_Geography_and_Resource_Management": ("At least five courses chosen",),
        "B.S.Sc._in_Psychology": (
            "At least four courses chosen from the following",
            "At least 4 courses chosen from the following",
        ),
        "B.A._in_Linguistics": ("At least four courses chosen from the following",),
    }
    prefixes = targets.get(stem, ())
    if not prefixes:
        return
    for item in walk(data.get("sections", [])):
        if item.get("title") or not item.get("text"):
            continue
        first = clean(item["text"][0])
        if any(first.startswith(prefix) for prefix in prefixes):
            clear_units = (
                stem in {"B.A._in_Linguistics", "B.S.Sc._in_Psychology"}
                and not item.get("marker")
                and bool(item.get("subsections"))
            )
            _promote_first_text(item, clear_units=clear_units)


def _promote_secondary_note_sections(data):
    """Lift named note blocks to the same heading level as Explanatory Notes."""
    notes = data.get("notes", [])
    for position, note in enumerate(list(notes)):
        heading = next((
            item for item in note.get("subsections", [])
            if re.match(
                r"^(?:Explanatory Notes? on Mutual Recognition or Exclusion|"
                r"Explanatory Note on mutual recognition or exclusion|"
                r"Note on Double Major Linguistics-Translation)$",
                clean(item.get("title", "")),
                re.I,
            )
        ), None)
        if not heading:
            continue
        note["subsections"] = [item for item in note.get("subsections", []) if item is not heading]
        title = clean(heading.get("title", ""))
        if title.lower().startswith("explanatory note on mutual"):
            title = "Explanatory Notes on Mutual Recognition or Exclusion"
        trailing = notes[position + 1:]
        block = {
            "title": title,
            "text": list(heading.get("text", [])),
            "subsections": list(heading.get("subsections", [])),
            "notes": trailing,
        }
        data.setdefault("supplementary_note_sections", []).append(block)
        del notes[position + 1:]
        break


def _repair_biomedical_note_markers(data):
    if data.get("source_file") != "B.Eng._in_Biomedical_Engineering":
        return
    source_text = " ".join(
        " ".join([item.get("title", ""), *item.get("text", [])])
        for item in walk(data.get("sections", []))
    )
    if "[d]" not in source_text and "[e]" not in source_text:
        return
    notes = data.get("notes", [])
    if any(note.get("marker") == "[d]" for note in notes):
        return
    insert_at = next((i + 1 for i, note in enumerate(notes) if note.get("marker") == "[c]"), len(notes))
    notes[insert_at:insert_at] = [
        {
            "marker": "[d]",
            "text": (
                "Students are strongly advised to take either LSCI1001 or 1002 if they have not "
                "attained Level 3 or above in HKDSE Biology, or other equivalent qualifications. "
                "LSCI1001 is only for students who have not taken science courses with Biology "
                "component in HKDSE."
            ),
            "subsections": [], "rows": [],
        },
        {
            "marker": "[e]",
            "text": (
                "Students who fail ENGG1125 in Term 1 will have to retake the course in Term 2. "
                "The pre-assigned ENGG1130 in Term 2 will therefore be dropped."
            ),
            "subsections": [], "rows": [],
        },
    ]


def _nest_accountancy_stream_requirements(data):
    if data.get("source_file") != "B.B.A._in_Professional_Accountancy":
        return
    for stream in walk(data.get("sections", [])):
        children = stream.get("subsections", [])
        instruction = next((
            item for item in children
            if not item.get("marker") and re.match(r"12 units from the following", item.get("title", ""), re.I)
        ), None)
        if not instruction:
            continue
        position = children.index(instruction)
        following = [item for item in children[position + 1:] if item.get("marker") in {"(a)", "(b)", "(c)"}]
        if following:
            instruction["subsections"] = following
            stream["subsections"] = [item for item in children if item not in following]


def _nest_flat_stream_requirements(data):
    """Ensure lettered requirements sit below, not beside, each stream title."""
    for streams in [item for item in walk(data.get("sections", [])) if item.get("title") == "Streams"]:
        children = streams.get("subsections", [])
        if not children:
            continue
        rebuilt = []
        current = None
        changed = False
        for child in children:
            if not child.get("marker"):
                rebuilt.append(child)
                current = child
            elif current is not None and child.get("marker") in {"(a)", "(b)", "(c)"}:
                current.setdefault("subsections", []).append(child)
                changed = True
            else:
                rebuilt.append(child)
        if changed:
            streams["subsections"] = rebuilt


def _repair_translation_review_items(data, extract):
    if data.get("source_file") != "B.A._in_Translation":
        return
    for item in walk(data.get("sections", [])):
        if item.get("title") or not item.get("text"):
            continue
        match = re.match(r"^(Other Electives)\s+(?=[A-Z]{4}\s*\d{4})(.*)$", clean(item["text"][0]), re.I)
        if match:
            item["title"] = "Other Electives"
            item["text"][0] = match.group(2)
            item["keep_heading"] = True

    # The Linguistics/Translation table exports section 4 as the final child
    # of section 3. Restore it as a peer top-level requirement.
    for section in list(data.get("sections", [])):
        found = next((
            item for item in walk(section.get("subsections", []))
            if re.match(r"^4\.\s*\(a\)\s*\(b\)\s*Research Component", item.get("title", ""), re.I)
        ), None)
        if not found:
            continue
        for parent in walk([section]):
            if found in parent.get("subsections", []):
                parent["subsections"].remove(found)
                break
        expression = clean(" ".join(found.get("text", [])))
        first, second = "TRAN4900", "TRAN4510 or 4520"
        if expression:
            match = re.search(r"(TRAN\s*4900)\s+(TRAN\s*4510\s+or\s+4520)", expression, re.I)
            if match:
                first, second = match.group(1), match.group(2)
        rebuilt = group(
            "Research Component/ Capstone Course/ Final Year Project",
            units=found.get("units", "6"), marker="4.",
            children=[
                group("", [first], extract(first), "3", "(a)"),
                group("", [second], extract(second), "3", "(b)"),
            ],
        )
        insert_at = data["sections"].index(section) + 1
        data["sections"].insert(insert_at, rebuilt)
        break

    elective = next((section for section in data.get("sections", []) if section.get("marker") == "2."), None)
    if elective:
        source_items = [elective, *elective.get("subsections", [])]
        combined_lines = [
            clean(line)
            for item in source_items
            for line in item.get("text", [])
        ]
        joined = " ".join([
            *(clean(item.get("title", "")) for item in source_items),
            *combined_lines,
        ])
        if "pre-requisites for subsequent admission to the Postgraduate Certificate in Laws" in joined:
            intro = next((line for line in combined_lines if line.startswith("Students are required to take at least")), "")
            pcll = next((line for line in combined_lines if line.startswith("LAWS")), "")
            elective["text"] = [intro] if intro else []
            elective["codes"] = []
            elective["subsections"] = [
                group(
                    "Elective courses which are pre-requisites for subsequent admission to the Postgraduate Certificate in Laws (PCLL) Programme",
                    [pcll] if pcll else [], extract(pcll),
                ),
                group("Other elective courses offered under the Juris Doctor Programme"),
                group("Elective courses offered under the Master of Laws Programmes"),
            ]


def _format_sociology_jd_electives(data, extract):
    """Match the Sociology/JD elective hierarchy used by Integrated BBA/JD."""
    if data.get("source_file") != "B.S.Sc._in_Sociology":
        return
    elective = next((
        section for section in data.get("sections", [])
        if section.get("marker") == "2." and section.get("title") == "Elective Courses"
    ), None)
    if not elective:
        return
    items = list(walk([elective]))
    prose = [
        clean(value)
        for item in items
        for value in [item.get("title", ""), *item.get("text", [])]
        if clean(value)
    ]
    if not any("Postgraduate Certificate in Laws (PCLL) Programme" in value for value in prose):
        return
    if any(item.get("marker") == "(i)" for item in items):
        return

    intro = next((
        value for value in prose
        if value.startswith("Students are required to take at least 54 or 57 units")
    ), "")
    pcll_courses = next((value.lstrip("- ") for value in prose if value.startswith("LAWS")), "")
    if not intro:
        return
    heading = group(intro, children=[
        group(
            "Elective courses which are pre-requisites for subsequent admission to the Postgraduate Certificate in Laws (PCLL) Programme",
            [pcll_courses] if pcll_courses else [],
            extract(pcll_courses),
            marker="(i)",
        ),
        group("Other elective courses offered under the JD programme", marker="(ii)"),
        group("Elective courses offered under the Master of Laws programmes", marker="(iii)"),
    ])
    heading["keep_heading"] = True
    elective["text"], elective["codes"], elective["subsections"] = [], [], [heading]


def _repair_information_engineering_review(data, extract):
    if data.get("source_file") != "B.Eng._in_Information_Engineering":
        return
    elective = next((section for section in data.get("sections", []) if section.get("marker") == "4."), None)
    if not elective:
        return
    for position, item in enumerate(list(elective.get("subsections", []))):
        remaining = next((text for text in item.get("text", []) if text.startswith("The remaining units, if any")), None)
        if remaining:
            explicit_text = [text for text in item.get("text", []) if text is not remaining]
            explicit_codes = extract(" ".join(explicit_text))
            remaining_codes = [code for code in item.get("codes", []) if code not in explicit_codes]
            item["text"], item["codes"] = explicit_text, explicit_codes
            heading = group(remaining.rstrip("."), codes=remaining_codes)
            heading["keep_heading"] = True
            elective["subsections"].insert(position + 1, heading)
            elective["subsections"] = [
                child for child in elective["subsections"]
                if child is heading
                or clean(child.get("title", "")).lower() != "the remaining units"
                or child.get("text") or child.get("codes") or child.get("subsections")
            ]
            break
    streams = next((item for item in elective.get("subsections", []) if item.get("title") == "Streams"), None)
    if streams:
        line = next((text for text in streams.get("text", []) if text.startswith("Big Data: Systems and Applications")), None)
        if line:
            body = line[len("Big Data: Systems and Applications"):].strip(" :")
            streams["text"].remove(line)
            streams["subsections"].insert(0, group(
                "Big Data: Systems and Applications", [body], extract(body), "12"
            ))


def _repair_government_review(data, index, extract):
    if data.get("source_file") != "B.S.Sc._in_Government_and_Public_Administration":
        return
    elective = next((section for section in data.get("sections", []) if section.get("marker") == "3."), None)
    if not elective:
        return
    for item in elective.get("subsections", []):
        if not item.get("title") and item.get("text"):
            first = clean(item["text"][0])
            match = re.match(r"^(Field Electives\[a\]\s*\[b\]|Free Electives|Capstone Courses|Professional Practicum)\s*(.*)$", first)
            if match:
                item["title"] = match.group(1)
                remainder = match.group(2).strip()
                item["text"] = ([remainder] if remainder else []) + item["text"][1:]
                item["keep_heading"] = True
        if item.get("title") in {"Free Electives", "Free Major Electives"} and not item.get("codes"):
            item["codes"] = [
                code for code in index
                if code.startswith("GPAD ") and code not in {"GPAD 1076", "GPAD 1077"}
            ]
        if item.get("title") != "Capstone Courses":
            continue
        choices = [child for child in item.get("subsections", []) if child.get("marker") in {"(i)", "(ii)", "(iii)", "(iv)", "(v)"}]
        if len(choices) == 5:
            expressions = [clean(" ".join(child.get("text", []))) for child in choices]
            codes = list(dict.fromkeys(code for child in choices for code in child.get("codes", [])))
            combined = group("Capstone course options", [", ".join(expressions)], codes, marker="(i)–(v)")
            first_at = min(item["subsections"].index(child) for child in choices)
            item["subsections"] = [child for child in item["subsections"] if child not in choices]
            item["subsections"].insert(first_at, combined)
    for item in walk(elective.get("subsections", [])):
        if item.get("marker") != "(vi)" or item.get("title") or not item.get("text"):
            continue
        match = re.match(r"^(Professional Practicum)\s*(.*)$", clean(item["text"][0]))
        if match:
            item["title"] = match.group(1)
            item["text"] = ([match.group(2)] if match.group(2) else []) + item["text"][1:]
            item["keep_heading"] = True
    level_rule = (
        "Of the Elective Courses, at least nine courses (27 units), including the two (6 units) "
        "capstone courses, should be at 2000 or above level."
    )
    for item in walk(elective.get("subsections", [])):
        if level_rule in item.get("text", []):
            item["text"].remove(level_rule)
            if level_rule not in elective.get("text", []):
                elective.setdefault("text", []).insert(0, level_rule)


def _repair_journalism_senior_review(data, extract):
    if data.get("source_file") != "B.S.Sc._in_Journalism_and_Communication":
        return
    elective = next((section for section in data.get("sections", []) if section.get("marker") == "2."), None)
    if not elective:
        return
    items = list(walk(elective.get("subsections", [])))
    communication = next((item for item in items if item.get("marker") == "(iv)" and item.get("title") == "Communication Studies"), None)
    global_item = next((item for item in items if item.get("marker") == "(v)" and not item.get("title")), None)
    if not communication or not global_item:
        return
    combined = clean(" ".join(global_item.get("text", [])))
    split = re.split(r"\s+Global Communication\s+", combined, maxsplit=1)
    if len(split) != 2:
        return
    communication["text"], communication["codes"] = [split[0]], extract(split[0])
    global_item["title"] = "Global Communication"
    global_item["text"], global_item["codes"] = [split[1]], extract(split[1])
    global_item["keep_heading"] = True


def _repair_double_major_elective_review(data, extract):
    stem = data.get("source_file")
    if stem not in {
        "B.S.Sc._in_Journalism_and_Communication",
        "B.S.Sc._in_Psychology",
        "B.S.Sc._in_Sociology",
    }:
        return
    section = next((section for section in data.get("sections", []) if section.get("marker") == "3."), None)
    if not section or len(section.get("subsections", [])) < 2:
        return
    major_titles = " ".join(item.get("title", "") for item in section.get("subsections", []))
    journalism_psychology = "Journalism and Communication" in major_titles and "Psychology" in major_titles
    journalism_sociology = "Journalism and Communication" in major_titles and "Sociology" in major_titles
    if journalism_psychology:
        section["units"] = "24"
        labels = re.compile(
            r"At least 6 units chosen from the following:?|"
            r"Remaining units chosen from the following:?|"
            r"At least 6 units of courses at 3000 or above level:?",
            re.I,
        )
        for major in section.get("subsections", []):
            combined = clean(" ".join(major.get("text", [])))
            matches = list(labels.finditer(combined))
            if not matches:
                continue
            children = []
            for position, match in enumerate(matches):
                stop = matches[position + 1].start() if position + 1 < len(matches) else len(combined)
                body = combined[match.end():stop].strip(" :")
                children.append(group(match.group(0).rstrip(":"), [body] if body else [], extract(body)))
            major["text"], major["codes"], major["subsections"] = [], [], children
        if "[a]" not in section.get("title", ""):
            section["title"] += "[a][b]"
    elif journalism_sociology:
        section["units"] = "30 or 33"
        if "[a]" not in section.get("title", ""):
            section["title"] += "[a][b]"


def _final_attached_review_fixes(data, index, extract):
    """Apply the final, source-backed formatting review to every scheme."""
    refine_anthropology_notes(data)
    _compact_science_faculty_packages(data)
    _compact_subject_course_choices(data)
    _promote_reviewed_instruction_headings(data)
    _repair_biomedical_note_markers(data)
    _nest_accountancy_stream_requirements(data)
    _nest_flat_stream_requirements(data)
    _repair_translation_review_items(data, extract)
    _repair_information_engineering_review(data, extract)
    _repair_government_review(data, index, extract)
    _repair_journalism_senior_review(data, extract)
    _repair_double_major_elective_review(data, extract)
    _format_sociology_jd_electives(data, extract)

    if data.get("source_file") == "B.Sc._in_Physics":
        required = next((section for section in data.get("sections", []) if section.get("marker") == "2."), None)
        mathematics = next((
            item for item in (required or {}).get("subsections", [])
            if item.get("marker") == "(b)" and item.get("title") == "Mathematics and Chemistry courses"
        ), None)
        if mathematics and not mathematics.get("subsections"):
            mathematics["subsections"] = [
                group("One course from", ["MATH2010, 2530"], extract("MATH2010, 2530"), marker="(i)"),
                group("One course from", ["CHEM1070, 1072[g]"], extract("CHEM1070, 1072"), marker="(ii)"),
            ]

    # The Law/Translation second degree publishes 18 required units, of which
    # item 1(a) accounts for 12 units.
    if data.get("source_file") == "LL.B._-_Bachelor_of_Laws_Programme":
        required = next((section for section in data.get("sections", []) if section.get("marker") == "1."), None)
        if required and any(code.startswith("TRAN ") for item in walk([required]) for code in item.get("codes", [])):
            required["units"] = "18"
            first = next((item for item in required.get("subsections", []) if item.get("marker") == "(a)"), None)
            if first:
                first["units"] = "12"

    _promote_secondary_note_sections(data)


def _variant_area_tables(data, path, index, extract):
    """Give senior-entry rules the same published area catalogues as standard rules."""
    stem = data.get("source_file")
    areas = source_areas(path, extract)
    if (stem == "B.A._in_Linguistics" and len(data.get("sections", [])) >= 3
            and len(data["sections"][2].get("subsections", [])) == 2
            and not any("Major:" in child.get("title", "")
                        for child in data["sections"][2].get("subsections", []))):
        resolve_linguistics(data, areas, index, extract)
        refine_linguistics(data)
        for item in data["sections"][2].get("subsections", []):
            _collapse_labelled_course_children(item)
    elif stem == "B.A._in_Music" and len(data.get("sections", [])) >= 3:
        elective = data["sections"][2]
        prose = clean(" ".join(elective.get("text", [])))
        used = {code for section in data["sections"][:2] for item in walk([section]) for code in item.get("codes", [])}
        rebuilt = []
        for area in deepcopy(areas):
            if "excluding" in prose.lower() and area.get("title", "").startswith("Area 2A:"):
                continue
            area["codes"] = [code for code in area.get("codes", []) if code not in used]
            if area.get("codes"):
                rebuilt.append(area)
        elective["codes"], elective["subsections"] = [], rebuilt
    elif stem == "B.A._in_Philosophy" and len(data.get("sections", [])) >= 3:
        elective = data["sections"][2]
        used = {code for section in data["sections"][:2] for item in walk([section]) for code in item.get("codes", [])}
        minimum = re.search(r"at least\s+(\d+)\s+units each from Areas 1, 2 and 3", " ".join(elective.get("text", [])), re.I)
        maximum = re.search(r"maximum of\s+(\d+)\s+units.*Area 5", " ".join(elective.get("text", [])), re.I)
        rebuilt = []
        for area in deepcopy(areas):
            area["codes"] = [code for code in area.get("codes", []) if code not in used]
            if not area.get("codes") and area.get("title", "").startswith("Area 4:"):
                continue
            if minimum and re.match(r"Area [123]:", area.get("title", "")):
                area["units"] = f"min. {minimum.group(1)}"
                area["text"] = [f"Take at least {minimum.group(1)} units from this area."]
            elif maximum and area.get("title", "").startswith("Area 5:"):
                area["units"] = f"max. {maximum.group(1)}"
                area["text"] = [f"Final-year students may take up to {maximum.group(1)} units from this area."]
            rebuilt.append(area)
        elective["codes"], elective["subsections"] = [], rebuilt
    elif stem in {"B.A._in_Public_Humanities", "B.A._in_Religious_Studies"}:
        resolve_named_areas(data, path, areas, index, extract)
        _group_area_tables(data)


def _restore_course_expression_boxes(data):
    """Keep the source course expression visible before a resolved course table."""
    for item in walk(data.get("sections", [])):
        if (
            not item.get("text")
            and item.get("codes")
            and re.match(r"At least\s+\d+\s+units from", item.get("title", ""), re.I)
        ):
            item["text"] = [", ".join(code.replace(" ", "") for code in item["codes"])]


def _integrated_bba_variant_headings(data):
    for section in data.get("sections", []):
        if "Elective Courses (Concentration)" not in section.get("title", ""):
            continue
        for concentration in section.get("subsections", []):
            if concentration.get("title") != "General Business":
                continue
            for item in concentration.get("subsections", []):
                if item.get("marker") in {"(i)", "(ii)"} and not item.get("title") and item.get("text"):
                    item["title"] = item["text"].pop(0)
                    item["keep_heading"] = True


def improve_requirement_variant_readability(data, path, index, extract, source_text=""):
    """Apply structure-safe presentation cleanup to an alternate full scheme.

    Programme-specific primary-table repairs often assume fixed section
    positions and cannot safely be replayed on shorter senior-entry schemes.
    These passes are content-driven, so they give alternate schemes the same
    headings, broad course resolution and explanatory-note layout without
    imposing the standard scheme's section counts.
    """
    promote_nested_legacy_notes(data)
    promote_instruction_heading(data)
    format_fine_arts_description(data)
    split_english(data, extract)
    structure_fine_arts_required_streams(data, extract)
    split_fine_arts(data, extract)
    structure_history_streams(data, index, extract, source_text)
    structure_double_major_headings(data, extract)
    structure_chinese_speciality_categories(data, extract)
    structure_translation_clusters(data, extract)
    structure_inline_named_course_groups(data, extract)
    repair_integrated_bba_concentrations(data)
    _variant_area_tables(data, path, index, extract)
    _structure_japanese_senior_routes(data)
    repair_reviewed_variant_labels(data)
    _translation_note_tables(data, extract)
    _merge_accountancy_streams(data)
    _engineering_note_repairs(data, extract)
    structure_science_course_choices(data, extract)
    structure_stream_introductions(data)
    promote_offering_labels(data)
    structure_inline_note_points(data)
    structure_science_faculty_package(data, extract)
    resolve_level_rules(data, index, extract)
    clean_presentation(data)

    # Word-export labels ending in a colon become separable only after the
    # generic cleanup above. Re-run the content-driven structure passes, just
    # as the primary readability pipeline does.
    structure_science_course_choices(data, extract)
    structure_stream_introductions(data)
    promote_instruction_heading(data)
    structure_double_major_headings(data, extract)
    structure_chinese_speciality_categories(data, extract)
    structure_translation_clusters(data, extract)
    structure_inline_named_course_groups(data, extract)
    repair_integrated_bba_concentrations(data)
    _integrated_bba_variant_headings(data)
    _structure_japanese_senior_routes(data)
    repair_reviewed_variant_labels(data)
    resolve_level_rules(data, index, extract)
    add_broad_department_course_tables(data, index)
    _nest_leading_instruction_choices(data)
    _restore_course_expression_boxes(data)
    _final_attached_review_fixes(data, index, extract)

    for item in walk(data["sections"]):
        prose = " ".join([item.get("title", ""), *item.get("text", [])])
        excluded = explicit_exclusions(prose, extract)
        if excluded:
            item["excluded_codes"] = sorted(set(item.get("excluded_codes", [])) | excluded)
            item["codes"] = [code for code in item.get("codes", []) if code not in excluded]

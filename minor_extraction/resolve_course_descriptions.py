"""
Resolve course descriptions in minor JSON files against course_info/.

Usage:
  python resolve_course_descriptions.py                   # diagnostic mode
  python resolve_course_descriptions.py --apply            # generate overrides
  python resolve_course_descriptions.py --apply --year X   # specific year
"""

import json
import re
import sys
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true", help="Generate override file")
parser.add_argument("--year", default="2025_26", help="Admission year (e.g. 2025_26)")
args = parser.parse_args()
YEAR = args.year

BASE = Path(__file__).parent.parent
MINOR_JSON_DIR = Path(__file__).parent / "minor_json" / YEAR
COURSE_INFO_DIR = BASE / "course_extraction" / "course_info"
OVERRIDE_FILE = Path(__file__).parent / "course_overrides" / f"{YEAR}.json"


# ── course index ──────────────────────────────────────────────────────

def load_course_index():
    """Build {DEPT XXXX: {title, unit, prereq}} and set of valid subject codes."""
    index = {}
    valid_subjects = set()
    for jp in sorted(COURSE_INFO_DIR.glob("*.json")):
        stem = jp.stem
        if stem.startswith("EX_"):
            continue
        valid_subjects.add(stem)
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
                }
    return index, valid_subjects


# ── pattern extraction ────────────────────────────────────────────────

def extract_level_constraint(text):
    """Parse level filter from text.
    Returns (min_level, max_level) where max_level may be None.
    Returns None if no level constraint found, or if the constraint is
    a selection guideline (not a hard filter on eligible courses).

    Hard filter:  "ECON course at 3000 or above level"  (level qualifies 'course')
    Guideline:    "... with at least 2 courses at 3000 or above level"
                  "... out of which at least 6 units ... at 3000 to 5000 level"
    """
    # Guideline patterns that make a level constraint non-restrictive
    GUIDELINE_PATTERN = re.compile(
        r"(?:with|out\s+of\s+which|should\s+include|take|complete|include)\s+at\s+least",
        re.IGNORECASE,
    )

    # "at 3000 to 5000 level"
    m = re.search(r"at\s+(\d{4})\s+to\s+(\d{4})\s+level", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            return int(m.group(1)), int(m.group(2))

    # "at 3000 or above level" / "at 3000 and above level" / "at 3000 or above"
    m = re.search(r"at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            return int(m.group(1)), None

    # "at 3000 or above" (no "level")
    m = re.search(r"at\s+(\d{4})\s+or\s+above(?!\s+level)", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            return int(m.group(1)), None

    # "3000 or above level" (no "at") — only if "courses at" nearby
    m = re.search(r"(\d{4})\s+(?:or|and)\s+above(?:\s+level)?", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            # Check if this is a hard filter: "courses at NNNN" pattern
            near = text[max(0, m.start() - 40): m.start()]
            if re.search(r"(?:courses?|subjects?)\s+at\s+\d{4}", near, re.IGNORECASE):
                return int(m.group(1)), None
            # Also return if "any X course" precedes
            if re.search(r"any\s+[A-Z]{4}\s+course", before, re.IGNORECASE):
                return int(m.group(1)), None

    # "at 4000 level" (exact)
    m = re.search(r"at\s+(\d{4})\s+level", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            return int(m.group(1)), int(m.group(1))

    # "4000 level"
    m = re.search(r"(?:^|[^a-zA-Z])(\d{4})\s+level\b", text, re.IGNORECASE)
    if m:
        before = text[: m.start()]
        if not GUIDELINE_PATTERN.search(before):
            return int(m.group(1)), None

    return None


def _extract_codes_with_prefix(text_segment, valid_subjects):
    """Extract DEPT XXXX codes from a segment, handling omitted prefix.
    E.g., 'MUSC1012, 1022, 1051' -> {MUSC 1012, MUSC 1022, MUSC 1051}"""
    # First, strip out level-constraint patterns to avoid extracting
    # numbers like "3000" from "at 3000 level" as course codes
    cleaned = text_segment
    cleaned = re.sub(r"at\s+\d{4}\s+to\s+\d{4}\s+level", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"at\s+\d{4}\s+(?:or|and)\s+above(?:\s+level)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"at\s+\d{4}\s+level", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d{4}\s+(?:or|and)\s+above(?:\s+level)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"at\s+least\s+\d+\s+units?\s+(?:of\s+courses?\s+)?at\s+\d{4}", "", cleaned, flags=re.IGNORECASE)

    codes = set()
    last_dept = None
    for token in re.finditer(r"([A-Z]{4})?\s*(\d{4})", cleaned):
        dept, num = token.group(1), token.group(2)
        if dept:
            last_dept = dept
        if last_dept and last_dept in valid_subjects:
            codes.add(f"{last_dept} {num}")
    return codes


def _extract_exclusion_clause(text, keyword):
    """Extract the clause after a keyword like 'excluding' or 'other than'.
    Stops at: period, 'Courses taken', ', with', 'should include'."""
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return None
    clause = text[idx + len(keyword):]

    # Cut at sentence-ending punctuation
    m = re.search(r"[.;]\s*(?:Courses\s+taken|Students\s+are|No\s+more|\Z)", clause)
    if m:
        clause = clause[: m.start()]

    # Cut at common constraint phrases
    m = re.search(r",\s*with\s+at\s+least", clause, re.IGNORECASE)
    if m:
        clause = clause[: m.start()]

    m = re.search(r"\.\s*Courses\s+taken", clause, re.IGNORECASE)
    if m:
        clause = clause[: m.start()]

    m = re.search(r"\.\s*Students\s+are", clause, re.IGNORECASE)
    if m:
        clause = clause[: m.start()]

    return clause.strip()


def extract_exclusion_codes(text, valid_subjects):
    """Extract course codes from 'excluding X' or 'other than X' clauses."""
    excluded = set()

    for keyword in ("excluding", "excludes", "other than", "except"):
        clause = _extract_exclusion_clause(text, keyword)
        if clause:
            excluded |= _extract_codes_with_prefix(clause, valid_subjects)

    return excluded


def extract_course_codes_from_text(text, valid_subjects):
    """Extract all DEPT XXXX codes from a string."""
    codes = set()
    for m in re.finditer(r"([A-Z]{4})\s*(\d{4})", text):
        dept, num = m.group(1), m.group(2)
        if dept in valid_subjects:
            codes.add(f"{dept} {num}")
    return codes


def has_any_pattern(text):
    """Check if text uses 'any X courses' pattern."""
    return bool(re.search(r"any\s+[A-Z]{4}\s+courses?", text, re.IGNORECASE))


def is_label_row(text):
    """Check if a row is purely a label/header (not a resolvable description).
    These rows introduce the next row(s) which contain actual course codes."""
    text = text.strip()

    # "from the following" patterns — always labels introducing the next row
    if re.search(r"(?:from|of|in)\s+the\s+following", text, re.IGNORECASE):
        return True

    # "listed below" / "areas below" / "shown below" — references to rows below
    if re.search(r"(?:listed|shown|areas?|courses?)\s+below", text, re.IGNORECASE):
        return True

    # References to other rows in the same section: "from (a) and (b)"
    if re.search(r"from\s+\(\w\)\s+and\s+\(\w\)", text, re.IGNORECASE):
        return True

    # "Choose N units of courses from ..." / "Any N courses from ..."
    if re.match(
        r"^(?:\([a-z0-9]+\)\s+)?(?:Any|At\s+least|Choose|Select)\s*"
        r"(?:\d+\s+)?(?:units?\s+of\s+)?(?:courses?\s+)?"
        r"(?:from\s+the\s+following|of\s+the\s+following)",
        text, re.IGNORECASE,
    ):
        return True

    # Bracketed selection instructions (standalone)
    if re.match(r"^\([a-z0-9]+\)\s*$", text):
        return True

    # "(one course chosen from the following):"
    if re.match(r"^\(one\s+course\s+chosen\s+from", text, re.IGNORECASE):
        return True

    # "(a) ... from the following:" with bracketed prefix
    if re.match(
        r"^\([a-z0-9]+\)\s*(?:Any\s+|At\s+least\s+)?"
        r"(?:one\s+course\s+chosen\s+from|"
        r"courses?\s+from|"
        r"\d+\s+courses?\s+from)",
        text, re.IGNORECASE,
    ):
        return True

    # "Choose N units of courses from ..."
    if re.match(r"^choose\s+\d+\s+units?\s+of\s+courses", text, re.IGNORECASE):
        return True

    # Bare category labels: "Language Requirement:", "Basic courses:", "(a) Basic courses"
    if re.match(
        r"^(?:\([a-z]+\)\s+)?(Language|Basic|Speciality|Anthropology|History|Elective)\s+"
        r"(Requirement|courses?)\s*:?\s*$",
        text, re.IGNORECASE,
    ):
        return True

    # Bracket + topic area: "(a) Environment and Sustainability", "(b) Mental Health..."
    if re.match(
        r"^\([a-z]+\)\s+(Environment|Mental Health|Social and Economic|Social Inequality|"
        r"Physical Education|Data Analytics|Entrepreneurship)\b",
        text, re.IGNORECASE,
    ):
        return True

    # "(at least 6 units at 4000 level):" — secondary constraint annotation
    # Also catches "(at least 9 units of PHYS courses at 3000 or above level)[a] :"
    if re.match(
        r"^\(at\s+least\s+\d+\s+units?\s+(?:of\s+[A-Z]{4}\s+courses?\s+)?at\s+\d+",
        text, re.IGNORECASE,
    ):
        return True

    # Standalone "OR" row
    if text.strip().upper() == "OR":
        return True

    # Area labels with codes listed: "(1) Language and Linguistics CHLL ..."
    # These have actual course codes following the label, so they're a hybrid
    # Check if text is mostly a label followed by course codes
    if re.match(
        r"^\(\d+\)\s+[A-Z][a-z]+\s+(?:and\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{4}\s*\d{4}",
        text,
    ):
        return True

    return False


def has_area_filter(text):
    """Check if text says 'from {X} Area(s)' — meaning the course selection is
    constrained to a specific conceptual area we can't resolve.
    vs. 'Area' mentioned in passing (like 'Area 2B' in selection guidelines)."""
    return bool(re.search(r"from\s+(?:the\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Areas?", text))


# ── resolution logic ──────────────────────────────────────────────────

def resolve_subject_codes(subject, level_min, level_max, excluded_codes, course_index):
    """Return list of course codes for a subject matching the constraints."""
    prefix = f"{subject} "
    result = []
    for code in sorted(course_index.keys()):
        if not code.startswith(prefix):
            continue
        if code in excluded_codes:
            continue
        # Extract course number
        num_str = code[len(prefix):]
        try:
            num = int(num_str)
        except ValueError:
            continue
        if level_min is not None and num < level_min:
            continue
        if level_max is not None and num > level_max:
            continue
        result.append(code)
    return result


def resolve_row(text, existing_codes, valid_subjects, course_index,
                earlier_codes=None):
    """Analyze a row and return resolved codes.
    Returns (category, resolved_codes_list, reason) where
    category is "AUTO", "PARTIAL", "MANUAL", or "SKIP".

    earlier_codes: set of course codes from rows earlier in the same minor.
                   These are excluded from the resolved set to avoid
                   duplicating courses already listed elsewhere.
    """
    existing_set = set(existing_codes)

    if is_label_row(text):
        return ("SKIP", None, "label row")

    # Extract subjects mentioned in the text
    subjects_in_text = set(re.findall(r"\b([A-Z]{4})\b", text)) & valid_subjects

    if not subjects_in_text:
        # Check if codes are already populated (e.g., compact codes like "CURE2405"
        # where subject extraction misses because there's no space separator)
        if existing_set:
            return ("SKIP", None, "codes already populated")
        # Check if this describes a course requirement using conceptual
        # categories (e.g., "Art History Courses", "Cultural Management Area")
        if re.search(r"\b(?:courses?|units?)\b", text, re.IGNORECASE):
            return ("MANUAL", None, "conceptual category — no subject code found in text")
        return ("SKIP", None, "no valid subject codes found in text")

    # Extract all explicit course codes from text
    text_codes = _extract_codes_with_prefix(text, valid_subjects)

    # If the text only lists specific course codes (no "courses" pattern),
    # and all those codes are already in the codes array → skip
    has_courses_pattern = any(
        re.search(r"\b" + s + r"\s+courses?\b", text, re.IGNORECASE)
        for s in subjects_in_text
    )
    has_any = has_any_pattern(text)
    has_units_pattern = any(
        re.search(r"\d+\s+units?\s+of\s+" + s, text, re.IGNORECASE)
        for s in subjects_in_text
    )

    if not has_courses_pattern and not has_any and not has_units_pattern:
        # Text only lists specific codes (e.g., "GPAD 1020, GPAD 1030")
        if text_codes and text_codes.issubset(existing_set):
            return ("SKIP", None, "all codes already present")
        # Codes listed but parser missed them → MANUAL for human to fix
        if text_codes and not text_codes.issubset(existing_set):
            return ("MANUAL", None, "specific codes listed but not all extracted by parser")
        return ("SKIP", None, "no 'courses' pattern and no unit-based pattern")

    # Extract level constraint
    level = extract_level_constraint(text)
    level_min, level_max = level if level else (None, None)

    # Extract exclusion codes from text
    excluded = extract_exclusion_codes(text, valid_subjects)

    # Only exclude earlier-row courses when the row text has a blanket
    # cross-row reference (e.g., "and those listed above"). Dynamic
    # references ("courses taken to fulfill requirement above") are
    # handled by the checker's cross_row_exclude instead.
    earlier = earlier_codes or set()
    _blanket_above = re.search(r'and\s+those\s+listed\s+above', text, re.IGNORECASE)
    full_exclude = (excluded | earlier) if _blanket_above else excluded

    # Check for area filter that constrains the set of courses
    area_filtered = has_area_filter(text)

    all_resolved = []
    unresolved_subs = set()

    for subj in sorted(subjects_in_text):
        should_resolve = has_any or has_courses_pattern or has_units_pattern

        if should_resolve:
            if area_filtered:
                unresolved_subs.add(subj)
                continue

            codes = resolve_subject_codes(subj, level_min, level_max, full_exclude, course_index)
            if codes:
                all_resolved.extend(codes)
            else:
                unresolved_subs.add(subj)

    if all_resolved:
        # Combine with existing codes, remove earlier+excluded codes
        final = sorted(set(all_resolved) | (existing_set - full_exclude))

        if unresolved_subs:
            return ("PARTIAL", final,
                    f"resolved {len(final)} codes but {unresolved_subs} have area constraints")
        return ("AUTO", final,
                f"resolved {len(final)} codes from {len(subjects_in_text)} subject(s)")

    # Second pass: existing codes might be only exclusions;
    # try resolving anyway if text describes 'any X courses' / 'X courses'
    if has_any or has_courses_pattern or has_units_pattern:
        if area_filtered:
            return ("MANUAL", None, "area-filtered — needs manual input")

        # Re-resolve ignoring the lack of initial resolution
        for subj in sorted(subjects_in_text):
            codes = resolve_subject_codes(subj, level_min, level_max, full_exclude, course_index)
            all_resolved.extend(codes)

        if all_resolved:
            final = sorted(set(all_resolved) | existing_set - full_exclude)
            return ("AUTO", final,
                    f"resolved {len(final)} codes (existing codes were only exclusions/examples)")

    return ("MANUAL", None, "could not resolve — may need manual input")


# ── main logic ────────────────────────────────────────────────────────

def build_overrides(verbose=True):
    """Scan all minor JSONs and build the override dict.
    Returns dict: {source_file: {text: [codes]}}"""
    course_index, valid_subjects = load_course_index()
    overrides = {}

    stats = {"AUTO": 0, "PARTIAL": 0, "MANUAL": 0, "SKIP": 0}

    for jp in sorted(MINOR_JSON_DIR.glob("*.json")):
        data = json.loads(jp.read_text(encoding="utf-8"))
        stem = data["source_file"]

        # Collect codes from all rows in document order (required then elective).
        # This lets later rows exclude courses already listed in earlier rows.
        seen_codes = set()

        for section_name in ("required", "elective"):
            sec = data.get(section_name, {})
            for r in sec.get("rows", []):
                text = r["text"].strip()
                codes = r.get("codes", [])
                if not text:
                    continue

                category, resolved, reason = resolve_row(
                    text, codes, valid_subjects, course_index,
                    earlier_codes=seen_codes
                )

                # Track this row's own codes for exclusion from later rows
                seen_codes.update(codes)
                if resolved:
                    seen_codes.update(resolved)

                if category == "SKIP":
                    stats["SKIP"] += 1
                    continue

                if category == "MANUAL":
                    if verbose:
                        print(f"  MANUAL [{stem}] \"{text[:100]}\"  -- {reason}")
                    overrides.setdefault(stem, {})[text] = []
                    stats["MANUAL"] += 1
                    continue

                if category == "PARTIAL":
                    if verbose:
                        print(f"  PARTIAL [{stem}] \"{text[:100]}\"  -- {reason}")
                    overrides.setdefault(stem, {})[text] = (
                        resolved if resolved else []
                    )
                    stats["PARTIAL"] += 1
                    continue

                if category == "AUTO":
                    if verbose:
                        if resolved:
                            print(
                                f"  AUTO   [{stem}] \"{text[:80]}...\"  "
                                f"-- {reason}"
                            )
                        else:
                            print(
                                f"  AUTO   [{stem}] \"{text[:100]}\"  "
                                f"-- already complete, skipping"
                            )
                    if resolved:
                        overrides.setdefault(stem, {})[text] = resolved
                        stats["AUTO"] += 1
                    else:
                        stats["SKIP"] += 1
                    continue

    return overrides, stats


def diagnostic_mode():
    """Print a categorized report."""
    print("=" * 70)
    print("Course Description Resolution — Diagnostic Report")
    print("=" * 70)
    print()

    overrides, stats = build_overrides(verbose=True)

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  AUTO (resolved):    {stats['AUTO']}")
    print(f"  PARTIAL (partial):  {stats['PARTIAL']}")
    print(f"  MANUAL (placeholder): {stats['MANUAL']}")
    print(f"  SKIP (labels etc.): {stats['SKIP']}")
    print()
    print(f"Total entries in override: {sum(len(v) for v in overrides.values())}")
    print(f"Affected minors: {len(overrides)}")
    print()
    print("Run with --apply to generate course_overrides.json")


def apply_mode():
    """Generate course_overrides.json, preserving manually-filled entries."""
    print("Resolving course descriptions...")
    overrides, stats = build_overrides(verbose=False)

    # Preserve manually-filled codes from existing override file
    if OVERRIDE_FILE.exists():
        existing = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
        preserved = 0
        for stem, rows in existing.items():
            for text, codes in rows.items():
                if codes and len(codes) > 0:  # manually filled
                    if stem in overrides and text in overrides[stem]:
                        if not overrides[stem][text]:  # would be wiped as empty
                            overrides[stem][text] = codes
                            preserved += 1
        if preserved:
            print(f"Preserved {preserved} manually-filled entry(s) from existing overrides.")

    # Write the override file
    OVERRIDE_FILE.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"Written: {OVERRIDE_FILE.name}")
    print(f"  AUTO entries:     {stats['AUTO']}")
    print(f"  PARTIAL entries:  {stats['PARTIAL']}")
    print(f"  MANUAL entries:   {stats['MANUAL']}")
    print(f"  Affected minors:  {len(overrides)}")
    print()
    print("MANUAL entries have empty codes arrays -- edit the JSON to fill them in.")
    print("Then run python -m site_generator.generate_minor_site to update the site.")


def main():
    if "--apply" in sys.argv:
        apply_mode()
    else:
        diagnostic_mode()


if __name__ == "__main__":
    main()

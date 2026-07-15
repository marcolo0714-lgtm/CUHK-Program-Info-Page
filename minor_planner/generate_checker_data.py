"""
Generate checker_data.json — fully resolved minor requirements for the
client-side progress checker.

Usage:  python generate_checker_data.py

Reads:  ../minor_extraction/minor_json/*.json
        ../course_extraction/course_info/*.json
        ../minor_extraction/course_overrides.json

Output: ../site/data/checker_data.json
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).parent.parent
MINOR_JSON_DIR = BASE / "minor_extraction" / "minor_json"
COURSE_INFO_DIR = BASE / "course_extraction" / "course_info"
OVERRIDE_FILE = BASE / "minor_extraction" / "course_overrides.json"
OUTPUT_FILE = BASE / "site" / "data" / "checker_data.json"


# ── Helpers ─────────────────────────────────────────────────────────────

def load_course_index():
    """Build ``{DEPT XXXX: {title, unit}}`` from course_info."""
    index = {}
    for jp in sorted(COURSE_INFO_DIR.glob("*.json")):
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            code = entry.get("code", "")
            if code:
                unit_str = entry.get("unit", "0")
                try:
                    unit = float(unit_str.replace(",", ""))
                except (ValueError, AttributeError):
                    unit = 0.0
                index[code] = {
                    "title": entry.get("title", ""),
                    "unit": unit,
                }
    return index


def load_overrides():
    if OVERRIDE_FILE.exists():
        return json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
    return {}


def apply_overrides(data, overrides):
    stem = data.get("source_file", "")
    minor_overrides = overrides.get(stem, {})
    if not minor_overrides:
        return
    for section_name in ("required", "elective"):
        for r in data.get(section_name, {}).get("rows", []):
            text = r.get("text", "").strip()
            if text in minor_overrides:
                r["codes"] = minor_overrides[text]


# ── Union-Find ──────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_eq_norm(eq_pairs):
    """Return {code: canonical_code} for all equivalent courses."""
    uf = UnionFind()
    for a, b in eq_pairs:
        uf.union(a, b)
    norm = {}
    for code in uf.parent:
        root = uf.find(code)
        if root != code:
            norm[code] = root
    return norm


# ── Level constraint extraction ─────────────────────────────────────────

def extract_level_constraint(text):
    """Extract sub-constraints like 'out of which at least X units at YYYY+ level'."""
    # "out of which at least 6 units at 3000 to 5000 level"
    m = re.search(
        r"out\s+of\s+which\s+at\s+least\s+(\d+)\s+units?"
        r"\s+(?:of\s+courses?\s+)?(?:are\s+)?at\s+(\d{4})\s+to\s+(\d{4})\s+level",
        text, re.IGNORECASE,
    )
    if m:
        return {"min_units_needed": int(m.group(1)), "min_level": int(m.group(2)),
                "max_level": int(m.group(3))}

    # "out of which at least 6 units at 3000 or above level"
    m = re.search(
        r"out\s+of\s+which\s+at\s+least\s+(\d+)\s+units?"
        r"\s+(?:of\s+courses?\s+)?(?:are\s+)?at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        return {"min_units_needed": int(m.group(1)), "min_level": int(m.group(2)),
                "max_level": None}

    # "with at least X courses at YYYY or above level"
    m = re.search(
        r"with\s+at\s+least\s+(\d+)\s+courses?\s+at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        return {"min_courses_needed": int(m.group(1)), "min_level": int(m.group(2)),
                "max_level": None}

    # "with at least X units at YYYY to ZZZZ level"
    m = re.search(
        r"with\s+at\s+least\s+(\d+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})"
        r"\s+to\s+(\d{4})\s+level",
        text, re.IGNORECASE,
    )
    if m:
        return {"min_units_needed": int(m.group(1)), "min_level": int(m.group(2)),
                "max_level": int(m.group(3))}

    # "with at least X units at YYYY or above level"
    m = re.search(
        r"with\s+at\s+least\s+(\d+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})"
        r"\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        return {"min_units_needed": int(m.group(1)), "min_level": int(m.group(2)),
                "max_level": None}

    return None


# ── Row merging (header + code-list) ────────────────────────────────────

_HEADER_PATTERN = re.compile(
    r"from\s+the\s+following|^Any\s+|^Choose\s+|^Select\s+|"
    r"^At\s+least\s+|courses?\s+below|listed\s+below",
    re.IGNORECASE,
)


def _is_header_row(text, codes, units_meta):
    """Check if a row is a selection-instruction header (has no codes but describes a choice)."""
    if codes:
        return False
    if units_meta:
        return True
    return bool(_HEADER_PATTERN.search(text))


def merge_header_code_rows(rows):
    """Merge header rows with subsequent code-list rows.
    A header describes a selection ('Any N courses from the following') and may
    be followed by one or more code-list rows that constitute the candidate pool.
    Sub-label rows (e.g. 'Anthropology courses:') between code rows are skipped."""
    merged = []
    i = 0
    while i < len(rows):
        row = rows[i]
        text = row.get("text", "").strip()
        codes = row.get("codes", [])
        units_meta = row.get("units", "").strip()

        if not text:
            i += 1
            continue

        # Pure digit-only artifacts — skip
        if re.match(r"^\d{1,2}\s*$", text) and not codes:
            i += 1
            continue

        if _is_header_row(text, codes, units_meta):
            # Collect all subsequent code-list rows until the next header row
            all_codes = []
            code_texts = []
            j = i + 1
            while j < len(rows):
                next_row = rows[j]
                next_text = next_row.get("text", "").strip()
                next_codes = next_row.get("codes", [])
                next_units = next_row.get("units", "").strip()

                if _is_header_row(next_text, next_codes, next_units):
                    break

                if next_codes:
                    all_codes.extend(next_codes)
                    if next_text:
                        code_texts.append(next_text)
                # else: sub-label with no codes, silently skip

                j += 1

            i = j - 1  # will advance to j after loop increment

            # Preserve code-list text alongside header
            combined_text = text
            if code_texts:
                combined_text = text + "\n" + "\n".join(code_texts)

            merged.append({
                "text": combined_text,
                "codes": all_codes,
                "units_meta": units_meta,
            })
        else:
            merged.append({
                "text": text,
                "codes": list(codes),
                "units_meta": units_meta,
            })

        i += 1

    return merged


# ── Strategy detection ──────────────────────────────────────────────────

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


def determine_strategy(row, section_type):
    text = row.get("text", "").strip()
    codes = row.get("codes", [])
    units_meta = row.get("units_meta", "").strip()

    # No codes → label (skip)
    if not codes:
        return {"strategy": "label"}

    if section_type == "required":
        # If the row has units metadata and/or "or" in the text, it's not a simple "all"
        has_or = bool(re.search(r"\bor\b", text, re.IGNORECASE))
        if units_meta:
            try:
                u = float(units_meta)
                result = {"strategy": "units", "units_needed": u}
                lc = extract_level_constraint(text)
                if lc:
                    result["level_constraint"] = lc
                return result
            except ValueError:
                pass
        if has_or:
            # Required row with "or" but no units metadata → pick 1 of the deduplicated set
            return {"strategy": "pick_n", "n": 1}
        return {"strategy": "all"}

    # ── Elective section ──
    # Text-based patterns first (more specific), units_meta as fallback.

    # "Any N courses from the following"
    m = re.search(r"Any\s+(\w+)\s+courses?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            result = {"strategy": "pick_n", "n": n}
            lc = extract_level_constraint(text)
            if lc:
                result["level_constraint"] = lc
            return result

    # "Any N [SUBJ] courses" (e.g. "Any 5 TRAN courses, excluding...",
    # "Any two LAWS courses at 3000 or above level")
    m = re.search(r"Any\s+(\w+)\s+[A-Z]{4}\s+courses?\b", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            result = {"strategy": "pick_n", "n": n}
            lc = extract_level_constraint(text)
            if lc:
                result["level_constraint"] = lc
            return result

    # "At least N courses from the following"
    m = re.search(r"At\s+least\s+(\d+)\s+courses?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "pick_n", "n": int(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N [SUBJ] courses at YYYY+ level, with at least M..." (before more generic units patterns)
    # "4 ENGE courses at 2000 and above level, with at least 6 units at 3000..."
    # "6 THEO courses with at least 1 course at 2000+ and another 2 courses at 3000+"
    m = re.search(r"(\d+)\s+[A-Z]{4}\s+courses?\s+(?:at\s+\d{4}|with\s+at\s+least)", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        result = {"strategy": "pick_n", "n": n}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N [SUBJ] courses with at least M courses at XXXX+" (word-number form)
    # "Five GPAD courses, with at least two courses at 3000 or above level"
    m = re.search(r"^\s*(\w+)\s+[A-Z]{4}\s+courses\b", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            result = {"strategy": "pick_n", "n": n}
            lc = extract_level_constraint(text)
            if lc:
                result["level_constraint"] = lc
            return result

    # "N courses from CODE,..." (word-number, e.g. "Two courses from STAT3001, ...")
    m = re.search(r"^\s*(\w+)\s+courses?\s+from\s+[A-Z]{4}\d{4}", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            return {"strategy": "pick_n", "n": n}

    # "(a) Two courses from STAT3001,..." — bracketed prefix + word-number
    m = re.search(r"\([a-z0-9]+\)\s*(\w+)\s+courses?\s+from\s+[A-Z]{4}\d{4}", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            return {"strategy": "pick_n", "n": n}

    # "Any N units ... Area" (e.g., Cultural Management)
    m = re.search(r"Any\s+(\d+)\s+units?\s+(?:Cultural Management|Religious Studies|Cultural Studies)\s+Area", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "Any N units from the following"
    m = re.search(r"Any\s+(\d+)\s+units?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N units from the following"
    m = re.search(r"(\d+)\s+units?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N units of courses selected from any [SUBJ] course at YYYY+" (resolved via overrides)
    m = re.search(r"(\d+)\s+units?\s+of\s+courses?\s+selected\s+from\s+any\s+[A-Z]{4}", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N units of [SUBJ] courses" (resolved via overrides, no "selected from")
    m = re.search(r"(\d+)\s+units?\s+of\s+[A-Z]{4}\s+courses?", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N to M units of courses from the following" — use lower bound
    m = re.search(r"(\d+)\s*[–\-to]+\s*\d+\s+units?\s+of\s+courses?\s+(?:chosen\s+)?from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "(N units of courses from the following...)" — parenthesized
    m = re.search(r"\(\s*(\d+)\s+units?\s+of\s+courses?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "Any N units from CODE,..." (specific codes, no "the following")
    m = re.search(r"Any\s+(\d+)\s+units?\s+from\s+[A-Z]{4}\d{4}", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "At least N units of courses from one, or up to..." (HB CU-ASK)
    m = re.search(r"At\s+least\s+(\d+)\s+units?\s+of\s+courses?\s+from", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "Choose N units of courses from the following" / "of at least M subject areas from"
    m = re.search(r"Choose\s+(\d+)\s+units?\s+of\s+courses?\s+(?:of\s+at\s+least\s+\d+\s+subject\s+areas?\s+)?from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N units of courses chosen from the following..." (with word "chosen")
    m = re.search(r"(\d+)\s+units?\s+of\s+courses?\s+chosen\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "from the following, including a minimum of N units at XXXX+"
    m = re.search(r"from\s+the\s+following,?\s+including\s+a\s+minimum\s+of\s+(\d+)\s+units?", text, re.IGNORECASE)
    if m:
        # This is a continuation of a previous header — use the unit count as target
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N courses from ..." (e.g., "3 courses from RMSC4001, 4002, ...")
    m = re.search(r"(\d+)\s+courses?\s+from\s+[A-Z]{4}\d{4}", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return {"strategy": "pick_n", "n": n}

    # Fallback: row has explicit unit metadata
    if units_meta:
        try:
            u = float(units_meta)
            result = {"strategy": "units", "units_needed": u}
            lc = extract_level_constraint(text)
            if lc:
                result["level_constraint"] = lc
            return result
        except ValueError:
            pass

    # Final fallback: has codes but no explicit rule
    return {"strategy": "any"}


# ── Row target units ────────────────────────────────────────────────────

def compute_row_target(row, strategy_info, course_index):
    codes = row.get("codes", [])
    strat = strategy_info.get("strategy", "label")
    units_meta = row.get("units_meta", "").strip()

    # If row has a units_meta value, prefer it for target
    meta_val = None
    if units_meta:
        try:
            meta_val = float(units_meta)
        except ValueError:
            pass

    if strat == "label":
        return 0.0
    if strat == "all":
        if meta_val is not None:
            return meta_val
        return sum(course_index.get(c, {}).get("unit", 3.0) for c in codes)
    if strat == "units":
        return strategy_info.get("units_needed", 0.0)
    if strat == "pick_n":
        n = strategy_info.get("n", 0)
        if not codes or n == 0:
            return 0.0
        avg_unit = sum(course_index.get(c, {}).get("unit", 3.0) for c in codes) / len(codes)
        return n * avg_unit
    if strat == "any":
        return 0.0
    return 0.0


# ── OR group detection ──────────────────────────────────────────────────

_OR_SPLIT = re.compile(r'\s+OR\s+')


def build_or_groups(text, codes, eq_norm):
    """If text contains ' OR ' (uppercase), split codes into OR groups.
    Each group is a list of deduped codes (after eq_norm canonicalization).
    Returns a list of lists, or None if no OR pattern detected."""
    if not _OR_SPLIT.search(text):
        return None

    # Find positions of ' OR ' boundaries
    or_bounds = [m.start() for m in _OR_SPLIT.finditer(text)]

    # Find position of each code in text (normalized without space)
    code_positions = []
    for c in codes:
        normalized = c.replace(' ', '')
        pos = text.upper().find(normalized.upper())
        code_positions.append((pos if pos >= 0 else 99999, c))
    code_positions.sort()

    # Partition codes into groups separated by OR boundaries
    groups = []
    current = []
    or_idx = 0
    for pos, code in code_positions:
        while or_idx < len(or_bounds) and pos > or_bounds[or_idx]:
            if current:
                groups.append(_dedup_group(current, eq_norm))
                current = []
            or_idx += 1
        current.append(code)

    if current:
        groups.append(_dedup_group(current, eq_norm))

    result = groups if len(groups) > 1 else None
    return result


def _dedup_group(codes, eq_norm):
    seen = set()
    result = []
    for c in codes:
        canon = eq_norm.get(c, c)
        if canon not in seen:
            seen.add(canon)
            result.append(c)
    return result


# ── Main ────────────────────────────────────────────────────────────────

def generate():
    course_index = load_course_index()
    overrides = load_overrides()
    print(f"Loaded course overrides for {len(overrides)} minor(s)")

    minors_data = {}
    strategy_counts = {}

    for jp in sorted(MINOR_JSON_DIR.glob("*.json")):
        data = json.loads(jp.read_text(encoding="utf-8"))
        stem = data["source_file"]

        # Apply course overrides first
        apply_overrides(data, overrides)

        # Build equivalence normalizer from eq_pairs
        eq_pairs = data.get("eq_pairs", [])
        eq_norm = build_eq_norm(eq_pairs)

        sections = []

        for section_name in ("required", "elective"):
            sec = data.get(section_name, {})
            label = sec.get("label", "")
            if not label:
                continue
            # Strip footnote markers [a], [b], etc. from section labels only
            label = re.sub(r'\[[a-z]\]', '', label).strip()

            # Merge header-code-list pairs
            raw_rows = sec.get("rows", [])
            merged_rows = merge_header_code_rows(raw_rows)

            rows_out = []
            section_target = 0.0

            for r in merged_rows:
                st = determine_strategy(r, section_name)
                if st.get("strategy") == "label":
                    continue

                codes = r["codes"]
                # Compute deduplicated count (after canonicalization via eq_pairs)
                seen = set()
                dedup_codes = []
                for c in codes:
                    canon = eq_norm.get(c, c)
                    if canon not in seen:
                        seen.add(canon)
                        dedup_codes.append(c)

                # Use deduped list for target computation
                dedup_row = dict(r, codes=dedup_codes)
                target = compute_row_target(dedup_row, st, course_index)
                if target > 0:
                    section_target += target

                # Embed unit info for each code (original codes, not deduped)
                codes_with_units = []
                for c in codes:
                    info = course_index.get(c, {})
                    codes_with_units.append({
                        "code": c,
                        "unit": info.get("unit", 0.0),
                    })

                row_out = {
                    "text": r["text"],
                    "codes": codes_with_units,
                    "strategy": st["strategy"],
                    "dedup_count": len(dedup_codes),
                }

                # Detect OR groups in the text (overrides strategy if found)
                or_groups = build_or_groups(r["text"], codes, eq_norm)
                if or_groups:
                    row_out["strategy"] = "or_group"
                    row_out.pop("n", None)
                    row_out["or_groups"] = [
                        {"codes": g, "dedup_count": len(g)}
                        for g in or_groups
                    ]
                    # Recompute target: use the smallest group's target
                    min_target = min(
                        compute_row_target(
                            dict(r, codes=g), {"strategy": "all"}, course_index
                        ) for g in or_groups
                    )
                    target = min_target
                    row_out["units_needed"] = min_target

                if "n" in st and "n" not in row_out:
                    row_out["n"] = st["n"]
                if "units_needed" in st:
                    row_out["units_needed"] = st["units_needed"]
                if "level_constraint" in st:
                    row_out["level_constraint"] = st["level_constraint"]

                rows_out.append(row_out)
                strategy_counts[row_out["strategy"]] = strategy_counts.get(row_out["strategy"], 0) + 1

            # After processing all rows: convert "any" rows to "units" if the
            # section has an explicit unit total (e.g. AIST elective: label row
            # describes a level constraint, code-list row has no target of its own)
            if rows_out:
                any_rows = [r for r in rows_out if r.get("strategy") == "any"]
                sec_units_str = sec.get("units", "").strip()
                if any_rows and sec_units_str:
                    try:
                        sec_units_val = float(sec_units_str)
                        if sec_units_val > 0:
                            per_row = sec_units_val / len(any_rows)
                            for r in any_rows:
                                r["strategy"] = "units"
                                r["units_needed"] = per_row
                                strategy_counts["units"] = strategy_counts.get("units", 0) + 1
                                strategy_counts["any"] = max(0, strategy_counts.get("any", 0) - 1)
                                # Recompute target contribution
                                row_codes = [c["code"] for c in r.get("codes", [])]
                                old_target = compute_row_target(
                                    {"codes": row_codes, "units_meta": ""},
                                    {"strategy": "any"}, course_index,
                                )
                                new_target = per_row
                                section_target = section_target - old_target + new_target
                    except ValueError:
                        pass

            if rows_out:
                # If section has a units field that's higher than computed row sum, use it
                sec_units_str = sec.get("units", "").strip()
                if sec_units_str:
                    try:
                        sec_units_val = float(sec_units_str)
                        if sec_units_val > section_target:
                            section_target = sec_units_val
                    except ValueError:
                        pass
                sections.append({
                    "label": label,
                    "target_units": section_target,
                    "rows": rows_out,
                })

        minors_data[stem] = {
            "title": data["title"],
            "faculty": data.get("faculty", "Unknown"),
            "description": data.get("description", ""),
            "eq_norm": eq_norm,
            "sections": sections,
        }

    # Build course summary (title + unit)
    courses_summary = {}
    for code, info in course_index.items():
        courses_summary[code] = {"title": info["title"], "unit": info["unit"]}

    output = {"courses": courses_summary, "minors": minors_data}

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    total_rows = sum(
        len(s["rows"]) for m in minors_data.values() for s in m["sections"]
    )
    print(f"Generated: {OUTPUT_FILE}")
    print(f"  Minors: {len(minors_data)}")
    print(f"  Sections: {sum(len(m['sections']) for m in minors_data.values())}")
    print(f"  Total rows: {total_rows}")
    print(f"  Courses indexed: {len(courses_summary)}")
    print(f"  Strategies: {strategy_counts}")
    label_only = [m["title"] for m in minors_data.values() if not m["sections"]]
    if label_only:
        print(f"  Minors with no sections: {label_only}")


if __name__ == "__main__":
    generate()

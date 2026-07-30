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


# ── Explanatory notes HTML parser ──────────────────────────────────────

def parse_explanatory_notes_html(notes):
    """Parse raw Word-exported explanatory notes HTML into clean point-cards
    matching the info-page format. Returns empty string if notes is empty."""
    if not notes:
        return ""

    # Strip leading "Explanatory Note(s):" header row
    notes = re.sub(
        r'<tr[^>]*>.*?Explanatory\s+Note[s]?\s*:?.*?</tr>',
        '', notes, count=1, flags=re.IGNORECASE | re.DOTALL
    )

    # Flatten nested table/tbody tags
    notes = re.sub(r'</?(?:table|tbody|thead|tfoot)\b[^>]*>', '', notes, flags=re.IGNORECASE)

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', notes, re.DOTALL)
    if not rows:
        return notes if notes.strip() else ""

    point_idx_pat = re.compile(r'^\s*(\d{1,2}\.|\[[a-z]\])')
    find_idx_pat = re.compile(r'(?<!\d)(\d{1,2}\.)(?!\d)|(\[[a-z]\])')

    def _has_point_label(row_html):
        for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
            td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
            if point_idx_pat.match(td_text):
                return True
        return False

    def _collect_indices(row_html):
        indices = []
        seen = set()
        for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
            td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
            if not point_idx_pat.match(td_text):
                continue
            for m in find_idx_pat.finditer(td_text):
                label = m.group(1) or m.group(2)
                if label and label not in seen:
                    indices.append(label)
                    seen.add(label)
        return indices

    classified = []
    for row_html in rows:
        clean = re.sub(r'<[^>]+>', '', row_html).replace('\xa0', ' ').strip()
        if not clean:
            continue
        if _has_point_label(row_html):
            indices = _collect_indices(row_html)
            content_paragraphs = []
            for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                td_text = re.sub(r'<[^>]+>', '', td_html).replace('\xa0', ' ').strip()
                if not td_text or point_idx_pat.match(td_text):
                    continue
                for p_html in re.findall(r'<p[^>]*>(.*?)</p>', td_html, re.DOTALL):
                    p_text = re.sub(r'<[^>]+>', '', p_html).replace('\xa0', ' ').strip()
                    p_text = re.sub(r'\s+', ' ', p_text).strip()
                    if p_text:
                        content_paragraphs.append(p_text)

            if content_paragraphs and len(content_paragraphs) >= len(indices):
                for idx_label, cp in zip(indices, content_paragraphs):
                    classified.append(('point', idx_label, cp))
                for extra in content_paragraphs[len(indices):]:
                    if classified and classified[-1][0] == 'point':
                        prev = classified[-1]
                        classified[-1] = ('point', prev[1], prev[2] + ' ' + extra)
            else:
                if len(indices) > 1:
                    p_texts = []
                    for td_html in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL):
                        for p_html in re.findall(r'<p[^>]*>(.*?)</p>', td_html, re.DOTALL):
                            pt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', p_html).replace('\xa0', ' ')).strip()
                            if pt:
                                p_texts.append(pt)
                    current_label = None
                    current_buf = []
                    for pt in p_texts:
                        m = point_idx_pat.match(pt)
                        if m:
                            if current_label and current_buf:
                                classified.append(('point', current_label, ' '.join(current_buf)))
                            current_label = m.group(1)
                            pt = re.sub(r'^' + re.escape(m.group(1)) + r'\s*', '', pt)
                            current_buf = [pt] if pt else []
                        elif current_label:
                            current_buf.append(pt)
                    if current_label and current_buf:
                        classified.append(('point', current_label, ' '.join(current_buf)))
                else:
                    plain_text = re.sub(r'\s+', ' ', clean).strip()
                    for idx_label in indices:
                        classified.append(('point', idx_label, plain_text))
        else:
            data_norm = re.sub(r'<[^>]+>', '', row_html)
            data_norm = data_norm.replace('&nbsp;', ' ').replace('\xa0', ' ')
            data_norm = re.sub(r'\s+', ' ', data_norm).strip()
            if data_norm:
                classified.append(('data', '', row_html))

    # Deduplicate
    deduped = []
    block_seen = set()
    skipping = False
    for item in classified:
        if item[0] == 'point':
            block_seen.clear()
            skipping = False
            deduped.append(item)
        elif not skipping:
            norm = re.sub(r'\s+', ' ', item[2]).strip()
            if norm in block_seen:
                skipping = True
            else:
                block_seen.add(norm)
                deduped.append(item)

    # Render
    def _render_data_table(rows):
        if not rows:
            return ""
        # Flatten nested <tr> elements
        flat = []
        for r in rows:
            if '<tr' in r.lower():
                inner = re.findall(r'<tr[^>]*>(.*?)</tr>', r, re.DOTALL)
                flat.extend(inner)
            else:
                flat.append(r)
        if not flat:
            return ""
        # Strip leading spacer row (empty after tag removal)
        if flat:
            first_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', flat[0]).replace('\xa0', ' ')).strip()
            if not first_norm:
                flat = flat[1:]
        if len(flat) >= 2:
            first_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', flat[0]).replace('\xa0', ' ')).strip()
            last_norm = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', flat[-1]).replace('\xa0', ' ')).strip()
            if first_norm and first_norm == last_norm:
                flat = flat[:-1]
            else:
                is_header = lambda t: 'courses' in t.lower() and 'equivalent' in t.lower()
                if is_header(last_norm) and not is_header(first_norm):
                    flat = [flat[-1]] + flat[:-1]
        return '<div class="notes-table-section"><table>' + ''.join('<tr>' + r + '</tr>' for r in flat) + '</table></div>'

    parts = []
    buf = []
    buf_type = None
    for item in deduped:
        if item[0] == 'point':
            if buf_type == 'data' and buf:
                parts.append(_render_data_table(buf))
                buf = []
            buf_type = 'point'
            _, label, content = item
            idx_text = label
            prefix = re.escape(label.strip()) + r'\s*'
            content = re.sub(r'^' + prefix, '', content, count=1)
            parts.append(
                '<div class="section notes-point">'
                '<span class="point-idx">' + idx_text + '</span>'
                '<span class="point-text">' + content + '</span>'
                '</div>'
            )
        else:
            if buf_type == 'point' and buf:
                pass  # points already rendered
            buf_type = 'data'
            buf.append(item[2])

    if buf_type == 'data' and buf:
        parts.append(_render_data_table(buf))

    return ''.join(parts)


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
    """Extract level sub-constraints from text.
    Handles 'at least X units/courses at YYYY+ level' and similar patterns.
    X can be a digit ('6') or a word ('two', 'three')."""

    def _n(s):
        """Parse a digit or word-based number string to int."""
        try:
            return int(s)
        except ValueError:
            return WORD_TO_NUM.get(s.lower())

    candidates = []

    def _add(units=None, courses=None, min_level=None, max_level=None):
        if min_level is not None and (units or courses):
            candidates.append({
                "min_units_needed": units,
                "min_courses_needed": courses,
                "min_level": min_level,
                "max_level": max_level,
            })

    # "out of which at least 6 units at 3000 to 5000 level"
    m = re.search(
        r"out\s+of\s+which\s+at\s+least\s+(\w+)\s+units?"
        r"\s+(?:of\s+courses?\s+)?(?:are\s+)?at\s+(\d{4})\s+to\s+(\d{4})\s+level",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)), max_level=int(m.group(3)))

    # "out of which at least 6 units at 3000 or above level"
    m = re.search(
        r"out\s+of\s+which\s+at\s+least\s+(\w+)\s+units?"
        r"\s+(?:of\s+courses?\s+)?(?:are\s+)?at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)))

    # "of which at least N courses (are) at YYYY or above level"
    m = re.search(
        r"of\s+which\s+at\s+least\s+(\w+)\s+courses?\s+(?:are\s+)?at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(courses=_n(m.group(1)), min_level=int(m.group(2)))

    # "with at least N courses at YYYY or above level"
    m = re.search(
        r"with\s+at\s+least\s+(\w+)\s+courses?\s+at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(courses=_n(m.group(1)), min_level=int(m.group(2)))

    # "with at least N at YYYY or above level" (no "courses"/"units" between)
    m = re.search(
        r"with\s+at\s+least\s+(\w+)\s+at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(courses=_n(m.group(1)), min_level=int(m.group(2)))

    # "another N courses at YYYY or above level"
    m = re.search(
        r"another\s+(\w+)\s+courses?\s+at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(courses=_n(m.group(1)), min_level=int(m.group(2)))

    # "N courses at YYYY or above level" (standalone, without "with at least" or "another")
    m = re.search(
        r"(\w+)\s+courses?\s+at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(courses=_n(m.group(1)), min_level=int(m.group(2)))

    # "at least X units at YYYY or above level" / "at YYYY level or above"
    m = re.search(
        r"at\s+least\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})\s+level\s+(?:or|and)\s+above",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)))

    m = re.search(
        r"at\s+least\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)))

    # "at least N units at XXXX level" (exact level, no "or above")
    # CUHK convention: "at 3000 level" = 3000-3999, "at 4000 level" = 4000-4999
    m = re.search(
        r"at\s+least\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})\s+level(?!\s+(?:or|and)\s+above)",
        text, re.IGNORECASE,
    )
    if m:
        lvl = int(m.group(2))
        _add(units=_n(m.group(1)), min_level=lvl, max_level=lvl + 999)

    # "and N units at XXXX level" (second/third exact-level constraint)
    for m in re.finditer(
        r"and\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})\s+level",
        text, re.IGNORECASE,
    ):
        lvl = int(m.group(2))
        _add(units=_n(m.group(1)), min_level=lvl, max_level=lvl + 999)

    # "including a minimum of X units at YYYY or above level"
    m = re.search(
        r"including\s+a\s+minimum\s+of\s+(\w+)\s+units?"
        r"\s+(?:of\s+(?:elective\s+)?courses?\s+)?at\s+(\d{4})"
        r"\s+(?:or|and)\s+above",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)))

    # "with at least X units at YYYY to ZZZZ level"
    m = re.search(
        r"with\s+at\s+least\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})"
        r"\s+to\s+(\d{4})\s+level",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)), max_level=int(m.group(3)))

    # "with at least X units at YYYY or above level"
    m = re.search(
        r"with\s+at\s+least\s+(\w+)\s+units?\s+(?:of\s+courses?\s+)?at\s+(\d{4})"
        r"\s+(?:or|and)\s+above(?:\s+level)?",
        text, re.IGNORECASE,
    )
    if m:
        _add(units=_n(m.group(1)), min_level=int(m.group(2)))

    if not candidates:
        return None

    # Return all unique constraints (remove None fields from each)
    seen = set()
    result = []
    for c in candidates:
        key = (c.get("min_units_needed"), c.get("min_courses_needed"), c.get("min_level"), c.get("max_level"))
        if key not in seen:
            seen.add(key)
            clean = {k: v for k, v in c.items() if v is not None}
            if clean:
                result.append(clean)
    return result if result else None


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
        units_max_meta = row.get("units_max", "").strip()

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
                # Also break on rows with their own unit metadata (standalone requirements)
                if next_units:
                    break

                if next_codes:
                    all_codes.extend(next_codes)
                    if next_text:
                        code_texts.append(next_text)
                elif next_text and not next_units:
                    # Sub-label with no codes and no unit metadata — preserve as context
                    code_texts.append(next_text)

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
                "units_max_meta": units_max_meta,
            })
        else:
            merged.append({
                "text": text,
                "codes": list(codes),
                "units_meta": units_meta,
                "units_max_meta": units_max_meta,
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
    units_max_meta = row.get("units_max_meta", "").strip()

    # No codes → label (skip)
    if not codes:
        return {"strategy": "label"}

    # Patterns that apply regardless of section type (before required default)
    # "(one course chosen from the following):"
    m = re.search(r"\(\s*(\w+)\s+courses?\s+chosen\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try: n = int(w)
            except ValueError: pass
        if n:
            return {"strategy": "pick_n", "n": n}

    if section_type == "required":
        # If the row has units metadata, use it as target
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
        return {"strategy": "all"}

    # ── Elective section ──
    # Unit metadata from the JSON is authoritative — check it first
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

    # Text-based patterns

    # "At least N courses" (word-number form) — floor
    m = re.search(r"At\s+least\s+(\w+)\s+courses?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        n = WORD_TO_NUM.get(w)
        if n is None:
            try:
                n = int(w)
            except ValueError:
                pass
        if n:
            result = {"strategy": "pick_n", "n": n, "allow_surplus": True}
            lc = extract_level_constraint(text)
            if lc:
                result["level_constraint"] = lc
            return result

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

    # "At least N courses from the following" — floor (allow surplus)
    m = re.search(r"At\s+least\s+(\d+)\s+courses?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "pick_n", "n": int(m.group(1)), "allow_surplus": True}
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

    # "Any N units from the following" (allow "of courses" in between)
    m = re.search(r"Any\s+(\d+)\s+units?\s+(?:of\s+courses?\s+)?from\s+the\s+following", text, re.IGNORECASE)
    if m:
        result = {"strategy": "units", "units_needed": float(m.group(1))}
        lc = extract_level_constraint(text)
        if lc:
            result["level_constraint"] = lc
        return result

    # "N units from the following" (allow "of courses" in between)
    m = re.search(r"(\d+)\s+units?\s+(?:of\s+courses?\s+)?from\s+the\s+following", text, re.IGNORECASE)
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
    # The "N units" here is a level constraint, not the row total.
    # Only use as units_needed if the row has no units_meta (heuristic fallback).
    m = re.search(r"from\s+the\s+following,?\s+including\s+a\s+minimum\s+of\s+(\d+)\s+units?", text, re.IGNORECASE)
    if m:
        lc = extract_level_constraint(text)
        if not units_meta:
            # No explicit unit metadata — use the regex match as a fallback target
            result = {"strategy": "units", "units_needed": float(m.group(1))}
        else:
            result = {"strategy": "units"}
        if lc:
            result["level_constraint"] = lc
        return result

    # "N courses from ..." (e.g., "3 courses from RMSC4001, 4002, ...")
    m = re.search(r"(\d+)\s+courses?\s+from\s+[A-Z]{4}\d{4}", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return {"strategy": "pick_n", "n": n}

    # Final fallback: has codes but no explicit rule
    return {"strategy": "any"}


# ── Area-based code lists (Music 2B/2C, etc.) ───────────────────────────

AREA_CODE_LISTS = {
    # Music Area 2B — Choral and Orchestral Ensemble Courses
    "2B": [
        "1001", "1002", "1031", "1032", "1041", "1042",
        "2001", "2002", "2031", "2032", "2041", "2042",
        "3001", "3002", "3031", "3032", "3041", "3042",
        "4001", "4002", "4031", "4032", "4041", "4042",
    ],
    # Music Area 2C — Other Ensemble Courses
    "2C": [
        "1013", "1014", "1017", "1018", "1019",
        "1023", "1024", "1027", "1028", "1029",
        "2013", "2014", "2017", "2018", "2019",
        "2023", "2024", "2027", "2028", "2029",
        "3013", "3014", "3017", "3018", "3019",
        "3023", "3024", "3027", "3028", "3029",
        "4013", "4014", "4017", "4018", "4019",
        "4023", "4024", "4027", "4028", "4029",
    ],
}


def _resolve_area_codes(area_spec):
    """Given e.g. '2B and/or 2C', return (combined_code_list, label)."""
    parts = [p.strip().rstrip('.,;:') for p in re.split(r"\s+and/or\s+", area_spec)]
    combined = []
    for p in parts:
        if p in AREA_CODE_LISTS:
            combined.extend(AREA_CODE_LISTS[p])
    label = ", ".join(f"Area {p}" for p in parts)
    return combined, label


# ── Subject bucket / area detection ──────────────────────────────────────

def detect_subject_constraints(text, codes=None):
    """Detect subject-based constraints in requirement text.
    Returns dict with optional 'subject_min' (int) and 'subject_buckets' (list)
    or None if no subject constraints found."""
    result = {}

    # "at least N subject areas from the following"
    m = re.search(r"at\s+least\s+(\w+)\s+subject\s+areas?\s+from\s+the\s+following", text, re.IGNORECASE)
    if m:
        n = WORD_TO_NUM.get(m.group(1).lower())
        if n is None:
            try: n = int(m.group(1))
            except ValueError: pass
        if n:
            result["subject_min"] = n

    buckets = []

    # "with X units of SUBJ courses and Y units of non-SUBJ courses"
    m = re.search(
        r"with\s+(\w+)\s+units?\s+of\s+([A-Z]{4})\s+courses?\s+and\s+(\w+)\s+units?\s+of\s+non-\2\s+courses?",
        text, re.IGNORECASE,
    )
    if m:
        x = WORD_TO_NUM.get(m.group(1).lower())
        if x is None:
            try: x = int(m.group(1))
            except ValueError: pass
        y = WORD_TO_NUM.get(m.group(3).lower())
        if y is None:
            try: y = int(m.group(3))
            except ValueError: pass
        subj = m.group(2).upper()
        if x: buckets.append({"prefix": subj, "min_units": float(x)})
        if y: buckets.append({"prefix": "!" + subj, "min_units": float(y)})

    # "with a maximum of X units of non-SUBJ courses"
    m = re.search(
        r"with\s+a\s+maximum\s+of\s+(\w+)\s+units?\s+of\s+non-([A-Z]{4})\s+courses?",
        text, re.IGNORECASE,
    )
    if m:
        x = WORD_TO_NUM.get(m.group(1).lower())
        if x is None:
            try: x = int(m.group(1))
            except ValueError: pass
        subj = m.group(2).upper()
        if x: buckets.append({"prefix": "!" + subj, "max_units": float(x)})

    # "with at least N SUBJ courses" (e.g., "with at least 3 CURE courses")
    m = re.search(
        r"with\s+at\s+least\s+(\w+)\s+([A-Z]{4})\s+courses?\b",
        text, re.IGNORECASE,
    )
    if m:
        n = WORD_TO_NUM.get(m.group(1).lower())
        if n is None:
            try: n = int(m.group(1))
            except ValueError: pass
        subj = m.group(2).upper()
        if n: buckets.append({"prefix": subj, "min_courses": int(n)})

    # "not more than N units of courses from Area 2B and/or 2C"
    m = re.search(
        r"not\s+more\s+than\s+(\w+)\s+units?\s+of\s+courses?\s+from\s+Area\s+(\S+)(?:\s+and/or\s+(\S+))?",
        text, re.IGNORECASE,
    )
    if m:
        n = WORD_TO_NUM.get(m.group(1).lower())
        if n is None:
            try: n = int(m.group(1))
            except ValueError: pass
        if n:
            area_spec = m.group(2) + (" and/or " + m.group(3) if m.group(3) else "")
            code_list, label = _resolve_area_codes(area_spec)
            if code_list:
                buckets.append({"code_list": code_list, "max_units": float(n), "label": label})

    if buckets:
        result["subject_buckets"] = buckets

    # AND-of-groups: "from each group" / "each group"
    if re.search(r'from\s+each\s+(?:of\s+the\s+)?groups?\b|each\s+(?:of\s+the\s+)?groups?\s+of\s+courses?\b|at\s+least\s+\w+\s+courses?\s+from\s+each\s+group', text, re.IGNORECASE):
        # Find distinct 4-letter prefixes from codes (group separation)
        prefix_set = set()
        for code in (codes or []):
            if ' ' in code:
                prefix_set.add(code.split(' ')[0])
        # If exactly 2 distinct prefixes, encode each as subject_bucket with min_courses=1
        if len(prefix_set) == 2:
            for prefix in sorted(prefix_set):
                buckets.append({"prefix": prefix, "min_courses": 1})
            result["subject_buckets"] = buckets

    return result if result else None


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
        # Use mode (most common non-zero unit) for clean integer targets
        units = [course_index.get(c, {}).get("unit", 0.0) for c in codes]
        nonzero = [u for u in units if u > 0]
        if not nonzero:
            return n * 3.0
        # Find mode
        from collections import Counter
        mode_unit = Counter(nonzero).most_common(1)[0][0]
        return n * mode_unit
    if strat == "any":
        return 0.0
    return 0.0


# ── OR group detection ──────────────────────────────────────────────────

_OR_SPLIT = re.compile(r'\s+OR\s+')
_OR_AND_SPLIT = re.compile(r'\s+or\s+', re.IGNORECASE)


def build_or_groups(text, codes, eq_norm):
    """If text contains group-separating 'OR'/'or', split codes into groups.
    - Uppercase ' OR ' always indicates group separation.
    - Lowercase 'or' only indicates group separation when 'and' is also
      present in the text (e.g. 'KORE2001 and 3000, or 3050').
      Otherwise 'or' is between equivalent alternatives, handled by eq_pairs.
    Returns a list of lists, or None if no group pattern detected."""
    has_and = bool(re.search(r'\band\b', text, re.IGNORECASE))
    # Use lowercase "or" only when "and" is present AND the "or" is preceded
    # by a comma/punctuation (group separator: "X and Y, or Z").
    # Inline "or" pairs like "HIST2500 or 2501" should NOT create groups.
    or_split = _OR_SPLIT if _OR_SPLIT.search(text) else None
    if or_split is None and has_and:
        # When "or" separates AND-groups like "BIOL3560 and 3570 or BIOL3610 and 3620",
        # the "and" appears between course code patterns, not English text.
        # Only treat as OR-group if "and" connects course numbers (e.g. "\d{4} and \d{4}").
        has_code_and = bool(re.search(r'\d{4}\s+and\s+(?:\d{4}|[A-Z]{4})', text, re.IGNORECASE))
        for m in _OR_AND_SPLIT.finditer(text):
            before = text[max(0, m.start() - 3):m.start()].strip()
            if before.endswith(',') or before.endswith(')') or has_code_and:
                or_split = _OR_AND_SPLIT
                break
    if or_split is None:
        return None

    # Find positions of ' OR ' / 'or' boundaries
    or_bounds = [m.start() for m in or_split.finditer(text)]

    # Find position of each code in text (normalized without space)
    code_positions = []
    for c in codes:
        normalized = c.replace(' ', '')
        pos = text.upper().find(normalized.upper())
        # Fallback: try bare number (for codes like "KORE 3000" where
        # the text only says "3000" with the dept inferred)
        if pos < 0:
            num = normalized[-4:]
            pos = text.upper().find(num)
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

    # Filter out empty groups (false "or" matches like "or above level")
    groups = [g for g in groups if g]
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

        # Extract total units from description ("minimum of X units")
        desc = data.get("description", "")
        total_m = re.search(r'minimum\s+of\s+(\d+)\s+units?', desc, re.IGNORECASE)
        total_units = float(total_m.group(1)) if total_m else None

        # Apply course overrides first (before merging)
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
                # Preserve unit range max from row metadata
                umax = r.get("units_max_meta", "").strip()
                if umax:
                    try:
                        st["units_needed_max"] = float(umax)
                    except ValueError:
                        pass
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
                    section_target = section_target - target + min_target
                    target = min_target
                    row_out["units_needed"] = min_target

                if "n" in st and "n" not in row_out:
                    row_out["n"] = st["n"]
                if "units_needed" in st:
                    row_out["units_needed"] = st["units_needed"]
                if "units_needed_max" in st:
                    row_out["units_needed_max"] = st["units_needed_max"]
                if "level_constraint" in st:
                    row_out["level_constraint"] = st["level_constraint"]
                if "allow_surplus" in st:
                    row_out["allow_surplus"] = st["allow_surplus"]

                # For pick_n rows, precompute mode unit for JS consistency
                if st.get("strategy") == "pick_n" or st.get("strategy") == "pick_n":
                    pick_units = [course_index.get(c, {}).get("unit", 0.0) for c in dedup_codes]
                    pick_nonzero = [u for u in pick_units if u > 0]
                    if pick_nonzero:
                        from collections import Counter
                        pick_mode = Counter(pick_nonzero).most_common(1)[0][0]
                        row_out["pick_n_avg_unit"] = pick_mode

                # Apply subject constraints from text
                subj = detect_subject_constraints(r["text"], codes)
                if subj:
                    if "subject_min" in subj:
                        row_out["subject_min"] = subj["subject_min"]
                    if "subject_buckets" in subj:
                        row_out["subject_buckets"] = subj["subject_buckets"]

                # Detect cross-row references ("excluding requirement X",
                # "including courses not taken in X above", "should not include")
                if re.search(
                    r'(?:excluding|other\s+than|not\s+taken\s+(?:to\s+fulfill|in)|'
                    r'should\s+not\s+include).*?(?:requirement|1\(|2\(|above\))',
                    r["text"], re.IGNORECASE,
                ):
                    row_out["cross_row_exclude"] = True

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
                                # Extract level constraint from text (may have been missed for "any" rows)
                                lc = extract_level_constraint(r["text"])
                                if lc:
                                    r["level_constraint"] = lc
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
                # Use section `units` as target when it exceeds computed row sum
                # (section units capture the total requirement; rows describe allocation)
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
                # Preserve section-level unit range
                sec_units_max_str = sec.get("units_max", "").strip()
                if sec_units_max_str:
                    try:
                        sections[-1]["target_units_max"] = float(sec_units_max_str)
                    except ValueError:
                        pass

        minors_data[stem] = {
            "title": data["title"],
            "faculty": data.get("faculty", "Unknown"),
            "description": desc,
            "total_units": total_units,
            "eq_norm": eq_norm,
            "sections": sections,
            "global_level_constraint": extract_level_constraint(desc),
            "explanatory_notes": parse_explanatory_notes_html(data.get("explanatory_notes", "")),
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

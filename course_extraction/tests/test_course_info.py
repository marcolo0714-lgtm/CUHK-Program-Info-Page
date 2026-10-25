import json
import re
import warnings
from functools import lru_cache
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import ddddocr

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COURSE_INFO_DIR = Path(__file__).parent.parent / "course_info"
COURSE_BACKUP_DIR = COURSE_INFO_DIR.parent / "course_info_copy"
COURSE_HTML_DIR = COURSE_INFO_DIR.parent / "course_html"
CATALOG_URL = (
    "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx"
)
MAX_CAPTCHA_RETRIES = 20

COURSE_REQUIRED_FIELDS = {
    "code", "title", "unit", "term_1", "term_2",
    "term_offerings", "sections",
}
TERM_OFFERING_REQUIRED_FIELDS = {"term_code", "term", "offered"}
SECTION_REQUIRED_FIELDS = {
    "term_code", "term", "section", "component_type", "class_number",
    "status", "class_capacity", "wait_list_capacity", "enrollment_total",
    "wait_list_total", "available_seats", "timetable",
}
TIMETABLE_REQUIRED_FIELDS = {"day_time", "room", "instructor", "dates"}
AVAILABILITY_FIELDS = {
    "class_capacity", "wait_list_capacity", "enrollment_total",
    "wait_list_total", "available_seats",
}
ACADEMIC_TERM_PATTERN = re.compile(
    r"\b\d{4}\s*[-/]\s*\d{2}\s+Term\s*([12])\b",
    re.IGNORECASE,
)


class DuplicateTimetableWarning(UserWarning):
    """A timetable row is duplicated in the source CUHK catalogue."""


class ScrapeComparisonWarning(UserWarning):
    """A change or known gap needs review, but is not proven data corruption."""


@lru_cache(maxsize=None)
def _comparison_manifest(subject):
    path = COURSE_HTML_DIR / subject / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _comparison_source(subject, code):
    """Read only saved summaries, never browse or change course data."""
    from course_extraction.get_course_info import (
        _parse_course_base_html, _parse_term_options_html,
        _parse_schedule_summary_html,
    )
    manifest = _comparison_manifest(subject)
    record = next((r for r in manifest.get("courses", []) if r.get("code") == code), None)
    if record is None:
        return None
    directory = COURSE_HTML_DIR / subject / record["directory"]
    html = (directory / record["course_page"]).read_text(encoding="utf-8")
    sections = set()
    for term in record.get("terms", []):
        if term.get("retrieval_error"):
            continue
        page = (directory / term["schedule_page"]).read_text(encoding="utf-8")
        summaries, *_ = _parse_schedule_summary_html(page)
        sections.update((term["term_code"], s["section"], s["class_number"])
                        for s in summaries)
    return _parse_course_base_html(html), set(_parse_term_options_html(html)), sections


def _comparison_rows(path):
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.fail(f"{path}: cannot read course data: {exc}")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("code"), str)
        for row in rows
    ):
        pytest.fail(f"{path}: expected a list of courses with text codes")
    return {row["code"]: row for row in rows}


@pytest.mark.parametrize("subject", sorted(
    {p.stem for p in COURSE_BACKUP_DIR.glob("*.json")}
    | {p.stem for p in COURSE_INFO_DIR.glob("*.json")}
) or ["__missing_data__"])
def test_course_info_against_backup(subject):
    """Report baseline losses, escalating losses contradicted by saved HTML."""
    if not COURSE_BACKUP_DIR.is_dir() or not any(COURSE_BACKUP_DIR.glob("*.json")):
        pytest.fail(f"Comparison baseline missing or empty: {COURSE_BACKUP_DIR}")
    current_path = COURSE_INFO_DIR / f"{subject}.json"
    backup_path = COURSE_BACKUP_DIR / f"{subject}.json"
    option = _comparison_manifest(subject).get("subject_option", "unknown")
    label = f"{subject}.json (subject option {option})"
    if not current_path.is_file():
        pytest.fail(f"{label}: entire subject file missing: {current_path}")
    current = _comparison_rows(current_path)
    previous = _comparison_rows(backup_path) if backup_path.is_file() else {}
    errors, notices = [], []
    for code in sorted(previous.keys() - current.keys()):
        errors.append(f"{code}: course missing from current JSON")
    for code in sorted(current.keys() - previous.keys()):
        notices.append(f"{code}: added course")
    for code, row in sorted(current.items()):
        for term in row.get("term_offerings", []):
            if term.get("retrieval_error"):
                notices.append(f"{code}: known gap, term {term.get('term_code')}: "
                               f"{term['retrieval_error']}")
        if code not in previous:
            continue
        old = previous[code]
        terms = lambda c: {t.get("term_code") for t in c.get("term_offerings", [])}
        sections = lambda c: {(s.get("term_code"), s.get("section"), s.get("class_number"))
                              for s in c.get("sections", [])}
        lost_terms = terms(old) - terms(row)
        lost_sections = sections(old) - sections(row)
        empty_fields = [key for key in ("title", "unit", "info")
                        if old.get(key) and not row.get(key)]
        changed_core = [key for key in ("title", "unit") if old.get(key) != row.get(key)]
        source = None
        if lost_terms or lost_sections or empty_fields or changed_core:
            try:
                source = _comparison_source(subject, code)
            except (OSError, ValueError, KeyError) as exc:
                notices.append(f"{code}: saved HTML could not be checked: {exc}")
        for term in sorted(lost_terms):
            message = f"{code}: missing previous term {term}"
            (errors if source and term in source[1] else notices).append(message)
        for key in sorted(lost_sections):
            message = f"{code}: missing previous section: term={key[0]}, section={key[1]}, class={key[2]}"
            (errors if source and key in source[2] else notices).append(message)
        for key in sorted(set(empty_fields + changed_core)):
            message = f"{code}: field {key}: {old.get(key)!r} -> {row.get(key)!r}"
            contradicted = source and source[0].get(key, "") != row.get(key, "")
            (errors if contradicted else notices).append(message)
        for term in sorted(terms(row) - terms(old)):
            notices.append(f"{code}: added term {term}")
        for key in sorted(sections(row) - sections(old)):
            notices.append(f"{code}: added section: term={key[0]}, section={key[1]}, class={key[2]}")
    if notices:
        warnings.warn(f"{label}: comparison review (not proof of scrape failure):\n"
                      + "\n".join(notices), ScrapeComparisonWarning, stacklevel=2)
    if errors:
        pytest.fail(f"{label}: backup comparison failed:\n" + "\n".join(errors))

ocr = ddddocr.DdddOcr(show_ad=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_stored_file_paths():
    """Return sorted list of (major_code, filepath) for every JSON in course_info/."""
    return sorted(
        (p.stem, str(p)) for p in COURSE_INFO_DIR.glob("*.json")
    )


def parse_course_number(code):
    """Extract the numeric part from ``"DEPT 1234"`` → 1234.

    Returns *None* when the string does not match the expected format.
    """
    parts = code.strip().split()
    if len(parts) != 2:
        return None
    if not parts[0].isalpha() or len(parts[0]) != 4:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def availability_from_term_labels(records):
    """Derive Term 1/2 availability from academic-year term labels."""
    term_numbers = {
        match.group(1)
        for record in records
        if isinstance(record, dict)
        for match in [ACADEMIC_TERM_PATTERN.search(str(record.get("term", "")))]
        if match
    }
    return "1" in term_numbers, "2" in term_numbers


def solve_captcha(page, max_retries=MAX_CAPTCHA_RETRIES):
    """Replicate captcha solving from ``get_course_info.py`` with a retry limit."""
    for attempt in range(max_retries):
        captcha_image = page.locator("#imgCaptcha").screenshot()
        captcha_text = ocr.classification(captcha_image)
        page.locator("#txt_captcha").fill("")
        page.locator("#txt_captcha").press_sequentially(
            captcha_text.upper(), delay=100
        )
        page.locator("#btn_search").click()
        try:
            page.wait_for_selector("#lbl_error", timeout=2000)
            print(
                f"    Captcha solving failed "
                f"(attempt {attempt + 1}/{max_retries}). Retrying..."
            )
            page.wait_for_timeout(1000)
        except Exception:
            print("    Captcha solved successfully.")
            return True
    raise RuntimeError(f"Captcha solving failed after {max_retries} attempts")


def extract_live_course_info(page, major_code):
    """After a successful captcha, extract count + first/last course codes from grid.

    The grid stores course numbers in ``<a id="..._lbtn_course_nbr">`` links
    (e.g. ``1111``).  We prepend *major_code* to build codes like ``"ACCT 1111"``.

    Returns ``(count, first_code, last_code)`` — all may be 0 / *None* when
    the major has no courses.
    """
    try:
        page.wait_for_selector("table#gv_detail", timeout=5000)
    except Exception:
        return 0, None, None

    number_links = page.locator("#gv_detail a[id$='lbtn_course_nbr']")
    count = number_links.count()

    if count == 0:
        return 0, None, None

    first_number = number_links.first.inner_text().strip("()* ")
    last_number = number_links.last.inner_text().strip("()* ")

    return count, f"{major_code} {first_number}", f"{major_code} {last_number}"


def selected_live_option_indexes(option_count, raw_course_options=None):
    """Return requested dropdown indexes, defaulting to every non-placeholder option."""
    from course_extraction.get_course_info import _parse_option_list

    if option_count <= 1:
        raise ValueError("course subject dropdown contains no selectable options")
    selected = (
        list(range(1, option_count))
        if raw_course_options is None
        else _parse_option_list(raw_course_options)
    )
    invalid = [option for option in selected if option >= option_count]
    if invalid:
        raise ValueError(
            f"indexes outside the dropdown range 1-{option_count - 1}: {invalid}"
        )
    return selected


# ---------------------------------------------------------------------------
# Module-scoped browser fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_page():
    """Launch **one** Chromium session and navigate to the course catalog.

    The same page is reused for all majors, so the test visits each major
    exactly once.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(CATALOG_URL)
        print("\nNavigated to CUHK course catalog page.")
        yield page
        browser.close()


# =================================================================
# Test 1 — Offline validation of stored JSON files
# =================================================================

class TestStoredIntegrity:
    """Verify that every stored ``course_info/*.json`` is internally consistent."""

    @pytest.mark.parametrize("major_code,filepath", get_stored_file_paths())
    def test_course_codes_strictly_increasing(self, major_code, filepath):
        """Per-file: course codes strictly increase, no duplicates, prefix
        matches filename, and every entry has the required keys.

        Aggregate failures so one test run reports every affected course in a
        subject instead of stopping at its first bad entry.
        """
        if major_code.startswith("EX_"):
            pytest.skip(
                f"[{major_code}] Skipping: credit transfer / unit exemption "
                f"codes do not follow the standard DEPT #### format"
            )
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"[{major_code}] Invalid JSON: {e}")

        assert isinstance(data, list), f"[{major_code}] JSON root is not a list"

        prev_number = -1
        seen = set()
        errors = []

        for entry_index, entry in enumerate(data):
            if not isinstance(entry, dict):
                errors.append(f"entry #{entry_index + 1} is not an object")
                continue
            for field in ("code", "title", "unit", "term_1", "term_2"):
                if field not in entry:
                    errors.append(f"entry #{entry_index + 1} missing {field!r}")
            if "code" not in entry:
                continue

            code = entry["code"]

            if not isinstance(entry.get("term_1"), bool):
                errors.append(f"{code}: term_1 is not boolean")
            if not isinstance(entry.get("term_2"), bool):
                errors.append(f"{code}: term_2 is not boolean")

            number = parse_course_number(code)
            if number is None:
                errors.append(f"{code!r}: invalid course code format")
                continue

            if code in seen:
                errors.append(f"{code}: duplicate course entry")
            elif number <= prev_number:
                errors.append(
                    f"{code}: course number {number} is not greater than previous {prev_number}"
                )

            prefix = code.split()[0]
            if prefix != major_code:
                errors.append(f"{code}: prefix {prefix!r} does not match filename {major_code!r}")

            prev_number = number
            seen.add(code)

        if errors:
            pytest.fail(f"[{major_code}] course integrity errors:\n" + "\n".join(errors))

    @pytest.mark.parametrize("major_code,filepath", get_stored_file_paths())
    def test_schedule_schema_and_consistency(self, major_code, filepath):
        """Validate nested sections, timetables, and term relationships.

        Failures are aggregated per subject file so the report identifies every
        affected course that should be scraped again in one run. Exact duplicate
        timetable entries are reported as warnings because the source catalogue
        can genuinely contain them.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                pytest.fail(f"[{major_code}] Invalid JSON: {exc}")

        if not isinstance(data, list):
            pytest.fail(f"[{major_code}] JSON root is not a list")

        errors = []
        duplicate_warnings = []
        for course_index, entry in enumerate(data):
            if not isinstance(entry, dict):
                errors.append(f"entry #{course_index + 1}: course is not an object")
                continue

            code = entry.get("code") or f"entry #{course_index + 1}"
            missing_course_fields = sorted(COURSE_REQUIRED_FIELDS - entry.keys())
            if missing_course_fields:
                errors.append(f"{code}: missing fields {missing_course_fields}")
                continue

            for field in ("code", "title", "unit"):
                if not isinstance(entry[field], str) or not entry[field].strip():
                    errors.append(f"{code}: {field} is empty or not text")

            if not isinstance(entry["term_1"], bool) or not isinstance(entry["term_2"], bool):
                errors.append(f"{code}: term_1 and term_2 must be booleans")
            if not isinstance(entry["term_offerings"], list):
                errors.append(f"{code}: term_offerings is not a list")
                continue
            if not isinstance(entry["sections"], list):
                errors.append(f"{code}: sections is not a list")
                continue

            offerings = {}
            for offering_index, offering in enumerate(entry["term_offerings"]):
                label = f"{code}: term_offerings[{offering_index}]"
                if not isinstance(offering, dict):
                    errors.append(f"{label} is not an object")
                    continue
                missing = sorted(TERM_OFFERING_REQUIRED_FIELDS - offering.keys())
                if missing:
                    errors.append(f"{label} missing fields {missing}")
                    continue
                term_code = offering["term_code"]
                if term_code in offerings:
                    errors.append(f"{code}: duplicate term_offerings entry for {term_code}")
                if not isinstance(offering["offered"], bool):
                    errors.append(f"{label}.offered is not boolean")
                if not isinstance(term_code, str) or not term_code.strip():
                    errors.append(f"{label}.term_code is empty or not text")
                if not isinstance(offering["term"], str) or not offering["term"].strip():
                    errors.append(f"{label}.term is empty or not text")
                offerings[term_code] = offering

            expected_from_offerings = availability_from_term_labels(
                entry["term_offerings"]
            )
            for field, expected in zip(
                ("term_1", "term_2"), expected_from_offerings
            ):
                if entry[field] != expected:
                    errors.append(
                        f"{code}: {field}={entry[field]} but term_offerings "
                        f"term labels say {expected}"
                    )

            seen_sections = {}
            seen_section_keys = {}
            scheduled_term_codes = set()
            for section_index, section in enumerate(entry["sections"]):
                label = f"{code}: sections[{section_index}]"
                if not isinstance(section, dict):
                    errors.append(f"{label} is not an object")
                    continue
                missing = sorted(SECTION_REQUIRED_FIELDS - section.keys())
                if missing:
                    errors.append(f"{label} missing fields {missing}")
                    continue

                fingerprint = json.dumps(section, ensure_ascii=False, sort_keys=True)
                if fingerprint in seen_sections:
                    errors.append(
                        f"{code}: duplicate sections "
                        f"{seen_sections[fingerprint]} and {section_index}"
                    )
                else:
                    seen_sections[fingerprint] = section_index

                term_code = section["term_code"]
                scheduled_term_codes.add(term_code)
                offering = offerings.get(term_code)
                if not offering or not offering.get("offered"):
                    errors.append(f"{label} belongs to term {term_code}, which is not offered")
                elif section["term"] != offering["term"]:
                    errors.append(
                        f"{label}.term {section['term']!r} does not match "
                        f"term_offerings value {offering['term']!r}"
                    )

                for field in ("section", "component_type", "class_number", "status"):
                    if not isinstance(section[field], str) or not section[field].strip():
                        errors.append(f"{label}.{field} is empty or not text")
                invalid_availability = sorted(
                    field for field in AVAILABILITY_FIELDS
                    if not isinstance(section[field], str) or not section[field].isdigit()
                )
                if invalid_availability:
                    errors.append(
                        f"{label} has invalid availability fields {invalid_availability}"
                    )
                for field in ("term_code", "term"):
                    if not isinstance(section[field], str):
                        errors.append(f"{label}.{field} is not text")

                section_key = (term_code, section["section"])
                if section_key in seen_section_keys:
                    errors.append(
                        f"{code}: term {term_code}, section {section['section']!r} "
                        f"appears at indexes {seen_section_keys[section_key]} and {section_index}"
                    )
                else:
                    seen_section_keys[section_key] = section_index

                if not isinstance(section["timetable"], list):
                    errors.append(f"{label}.timetable is not a list")
                    continue
                if not section["timetable"]:
                    errors.append(f"{label}.timetable is empty")
                    continue

                seen_timetable = {}
                for timetable_index, timetable in enumerate(section["timetable"]):
                    timetable_label = f"{label}.timetable[{timetable_index}]"
                    if not isinstance(timetable, dict):
                        errors.append(f"{timetable_label} is not an object")
                        continue
                    missing = sorted(TIMETABLE_REQUIRED_FIELDS - timetable.keys())
                    if missing:
                        errors.append(f"{timetable_label} missing fields {missing}")
                        continue
                    for field in TIMETABLE_REQUIRED_FIELDS:
                        if not isinstance(timetable[field], str):
                            errors.append(f"{timetable_label}.{field} is not text")
                    timetable_fingerprint = json.dumps(
                        timetable, ensure_ascii=False, sort_keys=True
                    )
                    if timetable_fingerprint in seen_timetable:
                        duplicate_warnings.append(
                            f"{code}: duplicate timetable entries in term {term_code}, "
                            f"section {section['section']!r}, indexes "
                            f"{seen_timetable[timetable_fingerprint]} and {timetable_index}"
                        )
                    else:
                        seen_timetable[timetable_fingerprint] = timetable_index

            for term_code, offering in offerings.items():
                retrieval_error = offering.get("retrieval_error")
                if retrieval_error is not None and (
                    not isinstance(retrieval_error, str)
                    or not retrieval_error.strip()
                ):
                    errors.append(
                        f"{code}: term {term_code} retrieval_error is not non-empty text"
                    )
                if (
                    offering.get("offered")
                    and term_code not in scheduled_term_codes
                    and not retrieval_error
                ):
                    errors.append(
                        f"{code}: term {term_code} is marked offered but has no sections"
                    )

            expected_term_1, expected_term_2 = availability_from_term_labels(
                entry["sections"]
            )
            failed_offerings = [
                offering for offering in entry["term_offerings"]
                if isinstance(offering, dict)
                and offering.get("offered")
                and offering.get("retrieval_error")
            ]
            failed_term_1, failed_term_2 = availability_from_term_labels(
                failed_offerings
            )
            expected_term_1 = expected_term_1 or failed_term_1
            expected_term_2 = expected_term_2 or failed_term_2
            if entry["term_1"] != expected_term_1:
                errors.append(
                    f"{code}: term_1={entry['term_1']} but section term labels say "
                    f"{expected_term_1}"
                )
            if entry["term_2"] != expected_term_2:
                errors.append(
                    f"{code}: term_2={entry['term_2']} but section term labels say "
                    f"{expected_term_2}"
                )

        if duplicate_warnings:
            warnings.warn(
                f"[{major_code}] duplicate timetable rows from the source catalogue:\n"
                + "\n".join(duplicate_warnings),
                DuplicateTimetableWarning,
                stacklevel=2,
            )

        if errors:
            pytest.fail(f"[{major_code}] schedule integrity errors:\n" + "\n".join(errors))


# =================================================================
# Test 2 — Online: live catalogue vs stored data
# =================================================================


class TestLiveVsStored:
    """Compare selected (or all) live catalogue options with stored JSON."""

    @pytest.mark.live
    def test_live_scraped_vs_stored(self, browser_page, request):
        page = browser_page
        errors = []
        raw_course_options = request.config.getoption("--course-options")
        dropdown_options = page.locator("#ddl_subject option")
        option_count = dropdown_options.count()
        try:
            selected_options = selected_live_option_indexes(
                option_count, raw_course_options
            )
        except ValueError as exc:
            pytest.fail(f"Invalid --course-options value: {exc}")

        print(f"\nChecking {len(selected_options)} course option(s): {selected_options}")
        for option_index in selected_options:
            option_text = (
                page.locator("#ddl_subject option").nth(option_index).inner_text().strip()
            )
            major_code = option_text.split(" - ", 1)[0].strip()
            filepath = COURSE_INFO_DIR / f"{major_code}.json"
            print(f"\n--- Major: {major_code} ---")

            # Load stored data
            if not filepath.exists():
                errors.append(
                    f"[{major_code}] Option {option_index} has no stored file: {filepath.name}"
                )
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                stored_data = json.load(f)

            stored_count = len(stored_data)
            stored_first = stored_data[0]["code"] if stored_data else None
            stored_last = stored_data[-1]["code"] if stored_data else None
            print(
                f"  Stored: count={stored_count}, "
                f"first='{stored_first}', last='{stored_last}'"
            )

            # Select the major from the dropdown ----------------------------
            try:
                page.locator("#ddl_subject").select_option(index=option_index)
                print(f"  Selected option [{option_index}]: '{option_text}'")
            except Exception as e:
                errors.append(
                    f"[{major_code}] Dropdown selection failed: {e}"
                )
                continue

            # Solve captcha -------------------------------------------------
            try:
                solve_captcha(page)
            except Exception as e:
                errors.append(f"[{major_code}] Captcha error: {e}")
                continue

            page.wait_for_load_state("networkidle")

            # Extract live data from grid -----------------------------------
            try:
                live_count, live_first, live_last = extract_live_course_info(page, major_code)
            except Exception as e:
                errors.append(f"[{major_code}] Grid extraction error: {e}")
                continue

            print(
                f"  Live:    count={live_count}, "
                f"first='{live_first}', last='{live_last}'"
            )

            # Compare -------------------------------------------------------
            if live_count != stored_count:
                errors.append(
                    f"[{major_code}] Count mismatch: "
                    f"live={live_count}, stored={stored_count}"
                )

            if stored_first is not None and live_first != stored_first:
                errors.append(
                    f"[{major_code}] First code mismatch: "
                    f"live='{live_first}', stored='{stored_first}'"
                )

            if stored_last is not None and live_last != stored_last:
                errors.append(
                    f"[{major_code}] Last code mismatch: "
                    f"live='{live_last}', stored='{stored_last}'"
                )

        if errors:
            failed_majors = sorted({
                e.split("]")[0].lstrip("[") for e in errors
            })
            pytest.fail(
                f"Failures in majors: {', '.join(failed_majors)}\n"
                + "\n".join(errors)
            )

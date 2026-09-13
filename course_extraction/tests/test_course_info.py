import json
import re
import warnings
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import ddddocr

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COURSE_INFO_DIR = Path(__file__).parent.parent / "course_info"
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
# Test 2 — Offline teaching-schedule extraction
# =================================================================

class TestTeachingScheduleExtraction:
    """Exercise every Term Offered option without contacting the CUHK site."""

    def test_course_end_uses_explicit_link_count(self):
        from course_extraction.get_course_info import _course_link_count

        class Links:
            @staticmethod
            def count():
                return 3

        class Page:
            @staticmethod
            def locator(selector):
                assert selector == "#gv_detail a[id$='lbtn_course_title']"
                return Links()

        assert _course_link_count(Page()) == 3

    def test_course_recovery_keeps_completed_sections(self, monkeypatch):
        import course_extraction.get_course_info as scraper

        class Button:
            @staticmethod
            def click():
                return None

        class Page:
            def __init__(self, name):
                self.name = name

            @staticmethod
            def locator(_selector):
                return Button()

            @staticmethod
            def wait_for_selector(_selector):
                return None

        first_page = Page("first")
        recovered_page = Page("recovered")
        resume_calls = []
        recovery_calls = []

        monkeypatch.setattr(scraper, "_open_course_by_index", lambda _page, _index: None)
        monkeypatch.setattr(
            scraper,
            "_course_base_info",
            lambda _page: {"code": "TEST 1000", "title": "Test", "unit": "3.00"},
        )

        def resume(_page, state):
            resume_calls.append(len(state["current_sections"]))
            if len(resume_calls) == 1:
                state["current_sections"].append({"section": "A-LEC"})
                raise RuntimeError("simulated stalled page")
            assert state["current_sections"] == [{"section": "A-LEC"}]
            state["schedules"] = [{"sections": list(state["current_sections"])}]

        def recover(*_args, **_kwargs):
            recovery_calls.append(True)
            return True, recovered_page

        monkeypatch.setattr(scraper, "_resume_course_schedules", resume)
        monkeypatch.setattr(scraper, "recover_with_new_tab", recover)
        monkeypatch.setattr(scraper, "_try_return_to_course_list", lambda _page: True)
        monkeypatch.setattr(
            scraper,
            "_finish_course_info",
            lambda base, schedules: {**base, "sections": schedules[0]["sections"]},
        )

        errors = []
        course, page, ready = scraper._scrape_course_with_recovery(
            first_page, 1, "TEST - Test", 0, errors
        )

        assert ready is True
        assert page is recovered_page
        assert course["sections"] == [{"section": "A-LEC"}]
        assert resume_calls == [0, 1]
        assert len(recovery_calls) == 1
        assert len(errors) == 1

    def test_course_recovery_stops_after_three_new_tabs(self, monkeypatch):
        import course_extraction.get_course_info as scraper

        class Page:
            pass

        page = Page()
        recovery_calls = []
        monkeypatch.setattr(scraper, "_open_course_by_index", lambda _page, _index: None)
        monkeypatch.setattr(
            scraper,
            "_course_base_info",
            lambda _page: {"code": "TEST 1000", "title": "Test", "unit": "3.00"},
        )
        monkeypatch.setattr(
            scraper,
            "_resume_course_schedules",
            lambda _page, _state: (_ for _ in ()).throw(RuntimeError("still stuck")),
        )

        def recover(*_args, **_kwargs):
            recovery_calls.append(True)
            return True, page

        monkeypatch.setattr(scraper, "recover_with_new_tab", recover)
        monkeypatch.setattr(scraper, "_try_return_to_course_list", lambda _page: True)

        errors = []
        course, returned_page, ready = scraper._scrape_course_with_recovery(
            page, 1, "TEST - Test", 0, errors
        )

        assert course is None
        assert returned_page is page
        assert ready is True
        assert len(recovery_calls) == 3
        assert len(errors) == 4

    def test_option_list_is_entered_at_runtime(self, monkeypatch):
        from course_extraction.get_course_info import _parse_option_list, _prompt_option_list

        answers = iter([
            "",
            "1, not-a-number",
            "0-3",
            "5-2",
            "1-3, 5, 3-6; 10",
        ])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

        assert _prompt_option_list() == [1, 2, 3, 5, 4, 6, 10]
        assert _parse_option_list("1-270") == list(range(1, 271))
        assert _parse_option_list("1-50, 101-150") == [
            *range(1, 51),
            *range(101, 151),
        ]

    def test_availability_uses_section_term_labels_not_term_codes(self):
        from course_extraction.get_course_info import _availability_from_sections

        sections = [
            {"term_code": "not-2420", "term": "2027-28 Term 1"},
            {"term_code": "not-2430", "term": "2027-28 Term 2 - special"},
        ]
        assert _availability_from_sections(sections) == (True, True)
        assert _availability_from_sections([
            {"term_code": "2420", "term": "Summer Session"}
        ]) == (False, False)

    def test_stored_availability_uses_term_offering_labels_even_if_flag_is_false(self):
        offerings = [{
            "term_code": "2430",
            "term": "2026/27 Term 2",
            "offered": False,
        }]

        assert availability_from_term_labels(offerings) == (False, True)

    def test_live_option_filter_defaults_to_all_and_accepts_ranges(self):
        assert selected_live_option_indexes(6) == [1, 2, 3, 4, 5]
        assert selected_live_option_indexes(271, "7, 42 44-45, 42") == [
            7, 42, 44, 45,
        ]
        with pytest.raises(ValueError, match="outside the dropdown range"):
            selected_live_option_indexes(10, "9-10")

    def test_all_terms_and_meeting_fields_are_scraped(self):
        from course_extraction.get_course_info import (
            _flatten_sections,
            _scrape_term_schedules,
            _term_offerings,
        )

        mock_page = """
        <select id="uc_course_ddl_class_term">
          <option value="2420">2026-27 Term 1</option>
          <option value="2430">2026-27 Term 2</option>
          <option value="2440">2026-27 Summer Session</option>
        </select>
        <button id="uc_course_btn_class_section" type="button" onclick="showSections()">Show sections</button>
        <input id="uc_course_hf_show_course_section" value="0">
        <div id="schedule"></div>
        <script>
        function showDetail(component, classNumber, status, isLab, isTermOne) {
          const firstMeeting = isLab ? `
            <tr><td>We 5:30PM - 6:15PM</td><td>Lab ${component[0]}</td>
            <td>Prof. Lab</td><td>2/9 - 1/12</td></tr>` : `
            <tr>
              <td>${isTermOne ? 'Mo 10:30AM - 12:15PM' : 'Tu 2:30PM - 4:15PM'}</td>
              <td>${isTermOne ? 'Room T1' : 'Room T2'}</td>
              <td>${isTermOne ? 'Prof. Term One' : 'Prof. Term Two'}</td>
              <td>${isTermOne ? '1/9 - 30/11' : '8/1 - 30/4'}</td>
            </tr><tr>
              <td>Th 3:30PM - 4:15PM</td><td>Room Thursday</td>
              <td>Prof. Thursday</td><td>10/9 - 3/12</td>
            </tr>`;
          document.querySelector('#schedule').innerHTML = `
            <span id="uc_class_lbl_course">TEST 1000 - ${component}</span>
            <span id="uc_class_lbl_ssr_component">${isLab ? 'Laboratory' : 'Lecture'}</span>
            <span id="uc_class_lbl_class_nbr">${classNumber}</span>
            <span id="uc_class_lbl_class_status">${status}</span>
            <span id="uc_class_lbl_enrl_cap">120</span>
            <span id="uc_class_lbl_wait_cap">5</span>
            <span id="uc_class_lbl_enrl_tot">110</span>
            <span id="uc_class_lbl_wait_tot">2</span>
            <span id="uc_class_lbl_available_seat">10</span>
            <table id="uc_class_gv_meet"><tbody>
              <tr><th>Days &amp; Times</th><th>Room</th><th>Instructor</th><th>Dates</th></tr>
              ${firstMeeting}
            </tbody></table>
            <button id="btn_class_return" type="button" onclick="showSections()">Return</button>`;
        }

        function showSections() {
          const code = document.querySelector('#uc_course_ddl_class_term').value;
          const isTermOne = code === '2420';
          if (code === '2440') {
            document.querySelector('#uc_course_hf_show_course_section').value = '0';
            document.querySelector('#schedule').innerHTML = '';
            return;
          }
          document.querySelector('#uc_course_hf_show_course_section').value = '1';
          const sectionLetters = isTermOne ? ['A', 'B', 'C', 'D', 'E', 'F'] : ['G'];
          const rows = sectionLetters.map((letter, index) => `
              <tr>
                <td><a href="#" onclick="showDetail('${letter}-LEC', '${index}001', '${isTermOne ? 'Open' : 'Closed'}', false, ${isTermOne}); return false" id="uc_course_gv_sched_ctl${index}2_lkbtn_class_section">${letter}-LEC (${index}001)</a></td>
                <td><img id="uc_course_gv_sched_ctl${index}2_img_status" src="class_${isTermOne ? 'open' : 'closed'}.gif"></td>
                <td><table id="uc_course_gv_sched_ctl${index}2_gv_meet"><tbody><tr>
                  <td>${isTermOne ? 'Mo 10:30AM - 12:15PM' : 'Tu 2:30PM - 4:15PM'}</td>
                  <td>${isTermOne ? 'Room T1' : 'Room T2'}</td>
                  <td>${isTermOne ? 'Prof. Term One' : 'Prof. Term Two'}</td>
                  <td>${isTermOne ? '1/9 - 30/11' : '8/1 - 30/4'}</td>
                </tr><tr>
                  <td>Th 3:30PM - 4:15PM</td>
                  <td>Room Thursday</td>
                  <td>Prof. Thursday</td>
                  <td>10/9 - 3/12</td>
                </tr></tbody></table></td>
              </tr>
              <tr>
                <td><a href="#" onclick="showDetail('${letter}L01-LAB', '${index}101', 'Open', true, ${isTermOne}); return false" id="uc_course_gv_sched_ctl${index}3_lkbtn_class_section">${letter}L01-LAB (${index}101)</a></td>
                <td><img id="uc_course_gv_sched_ctl${index}3_img_status" src="class_open.gif"></td>
                <td><table id="uc_course_gv_sched_ctl${index}3_gv_meet"><tbody><tr>
                  <td>We 5:30PM - 6:15PM</td><td>Lab ${letter}</td>
                  <td>Prof. Lab</td><td>2/9 - 1/12</td>
                </tr></tbody></table></td>
              </tr>`).join('');
          document.querySelector('#schedule').innerHTML = `
            <table id="uc_course_gv_sched"><tbody>
              <tr><th>Section</th><th>Status</th><th>Meetings</th></tr>
              ${rows}
            </tbody></table>`;
        }
        </script>
        """

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(mock_page)
            schedules = _scrape_term_schedules(page)
            browser.close()

        assert [term["term_code"] for term in schedules] == ["2420", "2430", "2440"]
        assert [term["offered"] for term in schedules] == [True, True, False]
        assert len(schedules[0]["sections"]) == 12
        assert len(schedules[1]["sections"]) == 2
        assert [section["section"] for section in schedules[0]["sections"][:3]] == [
            "A-LEC", "AL01-LAB", "B-LEC",
        ]
        assert schedules[0]["sections"][0] == {
            "section": "A-LEC",
            "component_type": "LEC",
            "class_number": "0001",
            "status": "Open",
            "class_capacity": "120",
            "wait_list_capacity": "5",
            "enrollment_total": "110",
            "wait_list_total": "2",
            "available_seats": "10",
            "timetable": [
                {
                    "day_time": "Mo 10:30AM - 12:15PM",
                    "room": "Room T1",
                    "instructor": "Prof. Term One",
                    "dates": "1/9 - 30/11",
                },
                {
                    "day_time": "Th 3:30PM - 4:15PM",
                    "room": "Room Thursday",
                    "instructor": "Prof. Thursday",
                    "dates": "10/9 - 3/12",
                },
            ],
        }
        assert [section["section"] for section in schedules[1]["sections"]] == [
            "G-LEC", "GL01-LAB",
        ]
        assert schedules[1]["sections"][0]["status"] == "Closed"
        assert (
            schedules[1]["sections"][0]["timetable"][0]["instructor"]
            == "Prof. Term Two"
        )
        assert schedules[2]["sections"] == []

        flattened = _flatten_sections(schedules)
        assert len(flattened) == 14
        assert flattened[0]["term_code"] == "2420"
        assert flattened[0]["term"] == "2026-27 Term 1"
        assert len(flattened[0]["timetable"]) == 2
        assert "sections" not in flattened[0]
        assert _term_offerings(schedules) == [
            {"term_code": "2420", "term": "2026-27 Term 1", "offered": True},
            {"term_code": "2430", "term": "2026-27 Term 2", "offered": True},
            {"term_code": "2440", "term": "2026-27 Summer Session", "offered": False},
        ]

    def test_saved_html_is_the_only_source_for_current_schema(self, tmp_path):
        from course_extraction.get_course_info import parse_saved_subject

        subject_dir = tmp_path / "TEST"
        course_dir = subject_dir / "courses" / "0000"
        (course_dir / "terms").mkdir(parents=True)
        (course_dir / "sections" / "000_2420").mkdir(parents=True)

        (course_dir / "course.html").write_text("""
          <span id="uc_course_lbl_course">TEST 1000 - Saved Course</span>
          <span id="uc_course_lbl_units">3.00</span>
          <div id="uc_course_tc_enrl_requirement">Not for TEST0000.</div>
          <select id="uc_course_ddl_class_term">
            <option value="2420">2026-27 Term 1</option>
          </select>
        """, encoding="utf-8")
        (course_dir / "terms" / "000_2420.html").write_text("""
          <button id="uc_course_btn_class_section">Show sections</button>
          <input id="uc_course_hf_show_course_section" value="1">
          <table id="uc_course_gv_sched"><tbody><tr>
            <td><a id="x_lkbtn_class_section">A-LEC (9700)</a></td>
            <td><img id="x_img_status" src="class_open.gif"></td>
            <td><table id="x_gv_meet"><tbody><tr>
              <td>Mo 12:30PM - 2:15PM</td><td>Summary Room</td>
              <td>Summary Teacher</td><td>7/9 - 30/11</td>
            </tr></tbody></table></td>
          </tr></tbody></table>
        """, encoding="utf-8")
        (course_dir / "sections" / "000_2420" / "0000.html").write_text("""
          <span id="uc_class_lbl_course">TEST 1000 - Saved Course</span>
          <span id="uc_class_lbl_ssr_component">Lecture</span>
          <span id="uc_class_lbl_class_nbr">9700</span>
          <span id="uc_class_lbl_class_status">Open</span>
          <span id="uc_class_lbl_enrl_cap">100</span>
          <span id="uc_class_lbl_wait_cap">5</span>
          <span id="uc_class_lbl_enrl_tot">90</span>
          <span id="uc_class_lbl_wait_tot">1</span>
          <span id="uc_class_lbl_available_seat">10</span>
          <table id="uc_class_gv_meet"><tbody>
            <tr><th>Days</th><th>Room</th><th>Instructor</th><th>Dates</th></tr>
            <tr><td>Mo 12:30PM - 2:15PM</td><td>Saved Room</td>
              <td>Saved Teacher</td><td>7/9 - 30/11</td></tr>
          </tbody></table>
        """, encoding="utf-8")

        course_record = {
            "capture_schema_version": 1,
            "course_index": 0,
            "code": "TEST 1000",
            "course_page": "course.html",
            "complete": True,
            "directory": "courses/0000",
            "terms": [{
                "term_code": "2420",
                "term": "2026-27 Term 1",
                "schedule_page": "terms/000_2420.html",
                "show_button_disabled": False,
                "sections": [{
                    "section_index": 0,
                    "section": "A-LEC",
                    "component_type": "LEC",
                    "class_number": "9700",
                    "detail_page": "sections/000_2420/0000.html",
                }],
            }],
        }
        (subject_dir / "manifest.json").write_text(json.dumps({
            "capture_schema_version": 1,
            "subject": "TEST",
            "course_count": 1,
            "courses": [course_record],
            "complete": True,
        }), encoding="utf-8")

        courses = parse_saved_subject(subject_dir)
        assert courses == [{
            "code": "TEST 1000",
            "title": "Saved Course",
            "unit": "3.00",
            "info": "Not for TEST0000.",
            "term_1": True,
            "term_2": False,
            "term_offerings": [{
                "term_code": "2420",
                "term": "2026-27 Term 1",
                "offered": True,
            }],
            "sections": [{
                "term_code": "2420",
                "term": "2026-27 Term 1",
                "section": "A-LEC",
                "component_type": "LEC",
                "class_number": "9700",
                "status": "Open",
                "class_capacity": "100",
                "wait_list_capacity": "5",
                "enrollment_total": "90",
                "wait_list_total": "1",
                "available_seats": "10",
                "timetable": [{
                    "day_time": "Mo 12:30PM - 2:15PM",
                    "room": "Saved Room",
                    "instructor": "Saved Teacher",
                    "dates": "7/9 - 30/11",
                }],
            }],
        }]

    def test_enabled_empty_saved_term_is_rejected_not_marked_unavailable(
        self, tmp_path
    ):
        from course_extraction.get_course_info import _parse_saved_course

        (tmp_path / "terms").mkdir()
        (tmp_path / "course.html").write_text("""
          <span id="uc_course_lbl_course">MATH 1018 - Honours University Mathematics</span>
          <span id="uc_course_lbl_units">3.00</span>
        """, encoding="utf-8")
        (tmp_path / "terms" / "000_2420.html").write_text("""
          <select id="uc_course_ddl_class_term">
            <option value="2420" selected>2026-27 Term 1</option>
          </select>
          <button id="uc_course_btn_class_section">Show sections</button>
          <input id="uc_course_hf_show_course_section" value="0">
        """, encoding="utf-8")
        record = {
            "code": "MATH 1018",
            "course_page": "course.html",
            "terms": [{
                "term_code": "2420",
                "term": "2026-27 Term 1",
                "schedule_page": "terms/000_2420.html",
                "show_button_disabled": False,
                "sections": [],
            }],
        }
        with pytest.raises(ValueError, match="incomplete postback"):
            _parse_saved_course(tmp_path, record)


# =================================================================
# Test 3 — Online: live scrape vs stored data
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

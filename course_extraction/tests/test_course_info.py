import json
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
    "term_offerings", "teaching_schedule",
}
TERM_OFFERING_REQUIRED_FIELDS = {"term_code", "term", "offered"}
SCHEDULE_REQUIRED_FIELDS = {
    "term_code", "term", "section", "component_type", "class_number",
    "status", "class_capacity", "wait_list_capacity", "enrollment_total",
    "wait_list_total", "available_seats", "day_time", "room",
    "instructor", "dates",
}
AVAILABILITY_FIELDS = {
    "class_capacity", "wait_list_capacity", "enrollment_total",
    "wait_list_total", "available_seats",
}

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
        """Validate the new flat schedule schema and term relationships.

        Failures are aggregated per subject file so the report identifies every
        affected course that should be scraped again in one run.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                pytest.fail(f"[{major_code}] Invalid JSON: {exc}")

        if not isinstance(data, list):
            pytest.fail(f"[{major_code}] JSON root is not a list")

        errors = []
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
            if not isinstance(entry["teaching_schedule"], list):
                errors.append(f"{code}: teaching_schedule is not a list")
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

            expected_term_1 = bool(offerings.get("2420", {}).get("offered", False))
            expected_term_2 = bool(offerings.get("2430", {}).get("offered", False))
            if entry["term_1"] != expected_term_1:
                errors.append(
                    f"{code}: term_1={entry['term_1']} but term_offerings says {expected_term_1}"
                )
            if entry["term_2"] != expected_term_2:
                errors.append(
                    f"{code}: term_2={entry['term_2']} but term_offerings says {expected_term_2}"
                )

            seen_rows = {}
            class_values = {}
            scheduled_term_codes = set()
            for row_index, row in enumerate(entry["teaching_schedule"]):
                label = f"{code}: teaching_schedule[{row_index}]"
                if not isinstance(row, dict):
                    errors.append(f"{label} is not an object")
                    continue
                missing = sorted(SCHEDULE_REQUIRED_FIELDS - row.keys())
                if missing:
                    errors.append(f"{label} missing fields {missing}")
                    continue

                fingerprint = json.dumps(row, ensure_ascii=False, sort_keys=True)
                if fingerprint in seen_rows:
                    errors.append(
                        f"{code}: duplicate teaching_schedule rows "
                        f"{seen_rows[fingerprint]} and {row_index}"
                    )
                else:
                    seen_rows[fingerprint] = row_index

                term_code = row["term_code"]
                scheduled_term_codes.add(term_code)
                offering = offerings.get(term_code)
                if not offering or not offering.get("offered"):
                    errors.append(f"{label} belongs to term {term_code}, which is not offered")
                elif row["term"] != offering["term"]:
                    errors.append(
                        f"{label}.term {row['term']!r} does not match "
                        f"term_offerings value {offering['term']!r}"
                    )

                for field in ("section", "component_type", "class_number", "status"):
                    if not isinstance(row[field], str) or not row[field].strip():
                        errors.append(f"{label}.{field} is empty or not text")
                invalid_availability = sorted(
                    field for field in AVAILABILITY_FIELDS
                    if not isinstance(row[field], str) or not row[field].isdigit()
                )
                if invalid_availability:
                    errors.append(
                        f"{label} has invalid availability fields {invalid_availability}"
                    )
                for field in ("term_code", "term", "day_time", "room", "instructor", "dates"):
                    if not isinstance(row[field], str):
                        errors.append(f"{label}.{field} is not text")

                class_key = (term_code, row["class_number"])
                current_values = tuple(row[field] for field in sorted(AVAILABILITY_FIELDS))
                if class_key in class_values and class_values[class_key] != current_values:
                    errors.append(
                        f"{code}: inconsistent availability across rows for "
                        f"term {term_code}, class {row['class_number']}"
                    )
                else:
                    class_values[class_key] = current_values

            for term_code, offering in offerings.items():
                if offering.get("offered") and term_code not in scheduled_term_codes:
                    errors.append(
                        f"{code}: term {term_code} is marked offered but has no teaching_schedule rows"
                    )

        if errors:
            pytest.fail(f"[{major_code}] schedule integrity errors:\n" + "\n".join(errors))


# =================================================================
# Test 2 — Offline teaching-schedule extraction
# =================================================================

class TestTeachingScheduleExtraction:
    """Exercise every Term Offered option without contacting the CUHK site."""

    def test_option_list_is_entered_at_runtime(self, monkeypatch):
        from course_extraction.get_course_info import _prompt_option_list

        answers = iter(["", "1, not-a-number", "0 3", "13, 14 97;13"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

        assert _prompt_option_list() == [13, 14, 97]

    def test_all_terms_and_meeting_fields_are_scraped(self):
        from course_extraction.get_course_info import (
            _flatten_teaching_schedule,
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
        assert len(schedules[0]["rows"]) == 18
        assert len(schedules[1]["rows"]) == 3
        assert [row["section"] for row in schedules[0]["rows"][:3]] == [
            "A-LEC", "A-LEC", "AL01-LAB",
        ]
        assert schedules[0]["rows"][0] == {
            "section": "A-LEC",
            "component_type": "LEC",
            "class_number": "0001",
            "status": "Open",
            "class_capacity": "120",
            "wait_list_capacity": "5",
            "enrollment_total": "110",
            "wait_list_total": "2",
            "available_seats": "10",
            "day_time": "Mo 10:30AM - 12:15PM",
            "room": "Room T1",
            "instructor": "Prof. Term One",
            "dates": "1/9 - 30/11",
        }
        assert schedules[0]["rows"][1]["day_time"] == "Th 3:30PM - 4:15PM"
        assert [row["section"] for row in schedules[1]["rows"]] == [
            "G-LEC", "G-LEC", "GL01-LAB",
        ]
        assert schedules[1]["rows"][0]["status"] == "Closed"
        assert schedules[1]["rows"][0]["instructor"] == "Prof. Term Two"
        assert schedules[2]["rows"] == []

        flattened = _flatten_teaching_schedule(schedules)
        assert len(flattened) == 21
        assert flattened[0]["term_code"] == "2420"
        assert flattened[0]["term"] == "2026-27 Term 1"
        assert "rows" not in flattened[0]
        assert "meetings" not in flattened[0]
        assert _term_offerings(schedules) == [
            {"term_code": "2420", "term": "2026-27 Term 1", "offered": True},
            {"term_code": "2430", "term": "2026-27 Term 2", "offered": True},
            {"term_code": "2440", "term": "2026-27 Summer Session", "offered": False},
        ]


# =================================================================
# Test 3 — Online: live scrape vs stored data
# =================================================================

class TestLiveVsStored:
    """Re-scrape the CUHK website to obtain course count + first/last course
    code per major, then compare with the stored JSON."""

    @pytest.mark.live
    def test_live_scraped_vs_stored(self, browser_page):
        page = browser_page
        errors = []
        stored_files = get_stored_file_paths()

        if not stored_files:
            pytest.skip("No JSON files found in course_info/")

        for major_code, filepath in stored_files:
            print(f"\n--- Major: {major_code} ---")

            # Load stored data
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
                options = page.locator("#ddl_subject option")
                opt_count = options.count()
                found = False
                for i in range(opt_count):
                    text = options.nth(i).inner_text()
                    if text.startswith(major_code):
                        page.locator("#ddl_subject").select_option(index=i)
                        print(f"  Selected option [{i}]: '{text}'")
                        found = True
                        break
                if not found:
                    errors.append(
                        f"[{major_code}] No dropdown option starts with "
                        f"'{major_code}'"
                    )
                    continue
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

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
        matches filename, and every entry has the required keys."""
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

        for entry in data:
            assert "code" in entry, f"[{major_code}] entry missing 'code' key"
            assert "title" in entry, f"[{major_code}] entry missing 'title' key"
            assert "unit" in entry, f"[{major_code}] entry missing 'unit' key"

            code = entry["code"]
            number = parse_course_number(code)

            assert number is not None, (
                f"[{major_code}] Invalid course code format: '{code}'"
            )

            assert number > prev_number, (
                f"[{major_code}] Course codes not strictly increasing: "
                f"'{code}' (num={number}) follows num={prev_number}"
            )

            assert code not in seen, (
                f"[{major_code}] Duplicate course code: '{code}'"
            )

            prefix = code.split()[0]
            assert prefix == major_code, (
                f"[{major_code}] Code prefix '{prefix}' != filename '{major_code}'"
            )

            prev_number = number
            seen.add(code)


# =================================================================
# Test 2 — Online: live scrape vs stored data
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

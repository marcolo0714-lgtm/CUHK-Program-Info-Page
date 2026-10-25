from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import argparse
from datetime import datetime
import json
import sys
import os
import re
import shutil
import stat
import time
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
COURSE_HTML_DIR = ROOT / "course_html"
COURSE_INFO_DIR = ROOT / "course_info"
LOG_DIR = ROOT / "logs"
CAPTURE_SCHEMA_VERSION = 1

import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)

# Subject options refer to the dropdown order at
# https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx
MAX_CAPTCHA_ATTEMPTS = 20
MAX_RECOVERY_ATTEMPTS = 3
PAGE_TIMEOUT = 60000
ACADEMIC_TERM_PATTERN = re.compile(
    r"\b\d{4}\s*-\s*\d{2}\s+Term\s*([12])\b",
    re.IGNORECASE,
)


class _TeeOutput:
    """Write a text stream to both its original destination and a log file."""

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, value):
        original_result = self._original.write(value)
        self._log_file.write(value)
        self._log_file.flush()
        return original_result

    def flush(self):
        self._original.flush()
        self._log_file.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)


class _LoggedInput:
    """Copy console input into the log, where the terminal would echo it."""

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def readline(self, *args, **kwargs):
        value = self._original.readline(*args, **kwargs)
        self._log_file.write(value)
        self._log_file.flush()
        return value

    def __getattr__(self, name):
        return getattr(self._original, name)


def _new_log_path(log_dir=LOG_DIR):
    """Return a unique timestamped path for one scraper invocation."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = log_dir / f"get_course_info_{timestamp}.txt"
    suffix = 2
    while candidate.exists():
        candidate = log_dir / f"get_course_info_{timestamp}_{suffix}.txt"
        suffix += 1
    return candidate


class BrowserDisconnected(KeyboardInterrupt):
    """Stop all nested retry loops when their browser is no longer usable."""


def _run_with_terminal_log(action, log_dir=LOG_DIR):
    """Run *action* while preserving the complete Python console transcript."""
    log_path = _new_log_path(log_dir)
    original_stdout, original_stderr, original_stdin = (
        sys.stdout,
        sys.stderr,
        sys.stdin,
    )
    exit_code = 0
    with log_path.open("w", encoding="utf-8", buffering=1) as log_file:
        sys.stdout = _TeeOutput(original_stdout, log_file)
        sys.stderr = _TeeOutput(original_stderr, log_file)
        sys.stdin = _LoggedInput(original_stdin, log_file)
        try:
            print(f"Log file: {log_path.resolve()}")
            action()
        except BrowserDisconnected as exc:
            print(f"\nStopped: {exc}. Partial captures have been retained.", file=sys.stderr)
            exit_code = 1
        except KeyboardInterrupt:
            print("\nStopped by user.", file=sys.stderr)
            exit_code = 130
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        except Exception:
            traceback.print_exc()
            exit_code = 1
        finally:
            print(f"\nLog saved to: {log_path.resolve()}")
            sys.stdout, sys.stderr, sys.stdin = (
                original_stdout,
                original_stderr,
                original_stdin,
            )
    return exit_code, log_path


def _postback(page, locator):
    """Await the new HTML document, without depending on window animation frames."""
    with page.expect_navigation(wait_until="domcontentloaded", timeout=PAGE_TIMEOUT):
        locator.dispatch_event("click", timeout=PAGE_TIMEOUT)


def _ensure_browser_connected(page):
    browser = page.context.browser
    if browser is not None and not browser.is_connected():
        # Do not retry every remaining subject against a dead browser.
        raise BrowserDisconnected("Browser was closed or disconnected")


def _solve_captcha_attempt(page, max_attempts=MAX_CAPTCHA_ATTEMPTS):
    """Try to solve captcha up to *max_attempts* times.

    Returns True if solved, False if all attempts fail (e.g. stale error label
    persists despite correct input).
    """
    for attempt in range(max_attempts):
        captcha_image = page.locator("#imgCaptcha").screenshot()
        captcha_text = ocr.classification(captcha_image)
        page.locator("#txt_captcha").fill(captcha_text.upper())
        _postback(page, page.locator("#btn_search"))
        # A slow response is not evidence of success. Require the results table
        # or an explicit rejection in the completed response document.
        result = page.wait_for_function(
            """() => {
                const error = document.querySelector('#lbl_error');
                if (error && error.textContent.trim()) return 'rejected';
                return document.querySelector('#gv_detail') ? 'success' : false;
            }""",
            polling=250, timeout=PAGE_TIMEOUT,
        ).json_value()
        if result == "rejected":
            print(f"Captcha solving failed (attempt {attempt + 1}/{max_attempts}). Retrying...")
            page.wait_for_timeout(min(1000 * (attempt + 1), 5000))
        else:
            print("Captcha solved successfully.")
            return True
    return False


def solve_captcha_with_reload(page, option):
    """Solve captcha.  If all attempts fail, open a new tab, navigate to the
    course catalog, re-select the major, and try one more batch.  Returns
    (True, page) on success (page may be the new tab), (False, original_page)
    if the captcha error label persists even in a fresh tab.
    """
    if _solve_captcha_attempt(page):
        return True, page

    print("Captcha failed after all attempts. Opening a new tab and retrying...")
    new_page = page.context.new_page()
    keep_page = False
    try:
        new_page.goto("https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx",
                      wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        new_page.locator("#ddl_subject").select_option(index=option)
        if _solve_captcha_attempt(new_page):
            page.close()
            keep_page = True
            return True, new_page
        print("Captcha still failed in the new tab.")
        return False, page
    finally:
        if not keep_page:
            try:
                new_page.close()
            except Exception:
                pass


def _normalize_schedule_text(value):
    """Collapse whitespace used for visual table alignment into JSON-friendly text."""
    return re.sub(r"\s+", " ", value or "").strip()


def _write_text_atomic(path, value):
    """Write a UTF-8 snapshot without leaving a half-written final file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(value, encoding="utf-8")
    try:
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                # OneDrive can briefly hold the previous manifest while it is
                # syncing. This is a storage retry, not a browser-session error.
                time.sleep(min(0.25 * (attempt + 1), 2.0))
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _write_json_atomic(path, value):
    _write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=4) + "\n",
    )


def _save_page_html(page, path):
    """Persist the browser's complete current DOM for later offline parsing."""
    _write_text_atomic(path, page.content())


def _soup_text(root, selector):
    element = root.select_one(selector)
    if element is None:
        return ""
    return _normalize_schedule_text(element.get_text(" ", strip=True))


def _parse_course_base_html(html):
    """Read course-level fields from a saved CUHK course page."""
    soup = BeautifulSoup(html, "html.parser")
    code_and_title = _soup_text(soup, "#uc_course_lbl_course")
    parts = code_and_title.split(" - ", 1)
    if len(parts) != 2:
        raise ValueError(f"unexpected saved course heading: {code_and_title!r}")
    course = {
        "code": parts[0].strip(),
        "title": parts[1].strip(),
        "unit": _soup_text(soup, "#uc_course_lbl_units"),
    }
    info = soup.select_one("#uc_course_tc_enrl_requirement")
    if info is not None:
        course["info"] = _normalize_schedule_text(info.get_text(" ", strip=True))
    return course


def _parse_term_options_html(html):
    """Return term-code labels from a saved course page."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        option.get("value", ""): _normalize_schedule_text(
            option.get_text(" ", strip=True)
        )
        for option in soup.select("#uc_course_ddl_class_term option[value]")
        if option.get("value", "")
    }


def _parse_timetable_html(meeting_grid):
    entries = []
    if meeting_grid is not None:
        body = meeting_grid.find("tbody", recursive=False)
        rows = body.find_all("tr", recursive=False) if body is not None else []
        for row in rows:
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue
            values = [
                _normalize_schedule_text(cell.get_text(" ", strip=True))
                for cell in cells
            ]
            values += [""] * (4 - len(values))
            entries.append({
                "day_time": values[0],
                "room": values[1],
                "instructor": values[2],
                "dates": values[3],
            })
    if not entries:
        entries.append({
            "day_time": "",
            "room": "",
            "instructor": "",
            "dates": "",
        })
    return entries


def _saved_section_status(row):
    if row is None:
        return ""
    image = row.select_one("img[id$='img_status']")
    if image is None:
        return ""
    for attribute in ("alt", "title"):
        value = _normalize_schedule_text(image.get(attribute, ""))
        if value:
            return value
    source = image.get("src", "")
    match = re.search(
        r"class_(open|closed|wait)(?:\.[a-z]+)?(?:\?.*)?$",
        source,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return "Wait List" if match.group(1).lower() == "wait" else match.group(1).title()


def _parse_schedule_summary_html(html):
    """Read section identities and summary fallbacks from a saved term page."""
    soup = BeautifulSoup(html, "html.parser")
    summaries = []
    for link in soup.select("#uc_course_gv_sched a[id$='lkbtn_class_section']"):
        component, component_type, class_number = _component_identity(
            link.get_text(" ", strip=True)
        )
        row = link.find_parent("tr")
        meeting_grid = row.select_one("table[id$='gv_meet']") if row else None
        summaries.append({
            "section": component,
            "component_type": component_type,
            "class_number": class_number,
            "status": _saved_section_status(row),
            "class_capacity": "",
            "wait_list_capacity": "",
            "enrollment_total": "",
            "wait_list_total": "",
            "available_seats": "",
            "timetable": _parse_timetable_html(meeting_grid),
        })
    hidden = soup.select_one("#uc_course_hf_show_course_section")
    current_term = soup.select_one("#uc_course_hf_current_course_term")
    show_button = soup.select_one("#uc_course_btn_class_section")
    show_button_disabled = (
        show_button.has_attr("disabled") if show_button is not None else None
    )
    reported_offered = bool(
        summaries or (hidden is not None and hidden.get("value") == "1")
    )
    return (
        summaries,
        reported_offered,
        show_button_disabled,
        current_term.get("value", "") if current_term is not None else "",
    )


def _parse_class_detail_html(html, summary, expected_course_code):
    """Read one saved class-detail page and verify it belongs to the course."""
    soup = BeautifulSoup(html, "html.parser")
    detail_heading = _soup_text(soup, "#uc_class_lbl_course")
    if detail_heading and not re.match(
        rf"^{re.escape(expected_course_code)}(?:\s|$|-)", detail_heading
    ):
        raise ValueError(
            f"saved class page belongs to {detail_heading!r}, expected "
            f"{expected_course_code!r}"
        )
    detail_component = _soup_text(soup, "#uc_class_lbl_ssr_component")
    detail_class_number = _soup_text(soup, "#uc_class_lbl_class_nbr")
    if (
        summary["class_number"]
        and detail_class_number
        and detail_class_number != summary["class_number"]
    ):
        raise ValueError(
            f"saved class number {detail_class_number!r} does not match "
            f"summary {summary['class_number']!r}"
        )
    return {
        "section": summary["section"],
        "component_type": summary["component_type"] or detail_component.upper(),
        "class_number": detail_class_number or summary["class_number"],
        "status": _soup_text(soup, "#uc_class_lbl_class_status")
        or summary["status"],
        "class_capacity": _soup_text(soup, "#uc_class_lbl_enrl_cap"),
        "wait_list_capacity": _soup_text(soup, "#uc_class_lbl_wait_cap"),
        "enrollment_total": _soup_text(soup, "#uc_class_lbl_enrl_tot"),
        "wait_list_total": _soup_text(soup, "#uc_class_lbl_wait_tot"),
        "available_seats": _soup_text(soup, "#uc_class_lbl_available_seat"),
        "timetable": _parse_timetable_html(
            soup.select_one("#uc_class_gv_meet")
        ),
    }


def _parse_saved_course(course_dir, course_record):
    """Build one current-schema course solely from saved HTML snapshots."""
    course_dir = Path(course_dir)
    course_page = course_dir / course_record["course_page"]
    if not course_page.is_file():
        raise FileNotFoundError(f"missing saved course page: {course_page}")
    course_html = course_page.read_text(encoding="utf-8")
    base_info = _parse_course_base_html(course_html)
    saved_term_options = _parse_term_options_html(course_html)
    expected_code = course_record.get("code", "")
    if expected_code and base_info["code"] != expected_code:
        raise ValueError(
            f"saved course page is {base_info['code']!r}, expected {expected_code!r}"
        )

    schedules = []
    for term in course_record.get("terms", []):
        retrieval_error = term.get("retrieval_error")
        if retrieval_error:
            if not isinstance(retrieval_error, str) or not retrieval_error.strip():
                raise ValueError(
                    f"{base_info['code']}: retrieval_error must be non-empty text"
                )
            term_code = term["term_code"]
            term_label = saved_term_options.get(term_code, term.get("term", ""))
            if saved_term_options and term_code not in saved_term_options:
                raise ValueError(
                    f"{base_info['code']}: failed term {term_code!r} is absent "
                    "from the saved course page"
                )
            schedules.append({
                "term_code": term_code,
                "term": term_label,
                "offered": True,
                "sections": [],
                "retrieval_error": retrieval_error.strip(),
            })
            continue
        term_path = course_dir / term["schedule_page"]
        if not term_path.is_file():
            raise FileNotFoundError(f"missing saved term page: {term_path}")
        (
            summaries,
            reported_offered,
            saved_button_disabled,
            saved_current_term,
        ) = _parse_schedule_summary_html(term_path.read_text(encoding="utf-8"))
        term_code = term["term_code"]
        term_label = saved_term_options.get(term_code, term.get("term", ""))
        if saved_term_options and term_code not in saved_term_options:
            raise ValueError(
                f"{base_info['code']}: captured term {term_code!r} is absent "
                "from the saved course page"
            )
        if saved_current_term and saved_current_term != term_code:
            raise ValueError(
                f"{base_info['code']} {term_label}: saved schedule belongs to "
                f"term {saved_current_term!r}, expected {term_code!r}"
            )
        manifest_button_disabled = term.get("show_button_disabled")
        if (
            saved_button_disabled is not None
            and manifest_button_disabled is not None
            and saved_button_disabled != manifest_button_disabled
        ):
            raise ValueError(
                f"{base_info['code']} {term_label}: saved Show sections state "
                "does not match the capture manifest"
            )
        show_button_disabled = (
            saved_button_disabled
            if saved_button_disabled is not None
            else bool(manifest_button_disabled)
        )
        captured_sections = term.get("sections", [])
        if len(summaries) != len(captured_sections):
            raise ValueError(
                f"{base_info['code']} {term_label}: saved schedule contains "
                f"{len(summaries)} section links but the capture manifest contains "
                f"{len(captured_sections)} class pages"
            )
        if not show_button_disabled and not summaries:
            raise ValueError(
                f"{base_info['code']} {term_label}: enabled Show sections "
                "page contains no captured sections; treating it as an incomplete "
                "postback instead of marking the course unavailable"
            )

        sections = []
        for summary, captured in zip(summaries, captured_sections):
            for field in ("section", "component_type", "class_number"):
                captured_value = captured.get(field, "")
                if captured_value and captured_value != summary[field]:
                    raise ValueError(
                        f"{base_info['code']} {term_label}: captured {field} "
                        f"{captured_value!r} does not match saved schedule "
                        f"{summary[field]!r}"
                    )
            detail_path = course_dir / captured["detail_page"]
            if not detail_path.is_file():
                raise FileNotFoundError(
                    f"missing saved class page: {detail_path}"
                )
            sections.append(
                _parse_class_detail_html(
                    detail_path.read_text(encoding="utf-8"),
                    summary,
                    base_info["code"],
                )
            )
        schedules.append({
            "term_code": term_code,
            "term": term_label,
            "offered": bool(reported_offered or sections),
            "sections": sections,
        })
    return _finish_course_info(base_info, schedules)


def _load_capture_manifest(subject_dir):
    manifest_path = Path(subject_dir) / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing capture manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("capture_schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported capture schema in {manifest_path}: "
            f"{manifest.get('capture_schema_version')!r}"
        )
    if not manifest.get("complete"):
        raise ValueError(f"capture is incomplete: {manifest_path}")
    return manifest


def parse_saved_subject(subject_dir):
    """Convert a complete subject snapshot directory to current-schema data."""
    subject_dir = Path(subject_dir)
    manifest = _load_capture_manifest(subject_dir)
    courses = []
    for course_record in manifest.get("courses", []):
        courses.append(
            _parse_saved_course(
                subject_dir / course_record["directory"], course_record
            )
        )
    if len(courses) != manifest.get("course_count"):
        raise ValueError(
            f"{manifest.get('subject')}: parsed {len(courses)} courses, expected "
            f"{manifest.get('course_count')}"
        )
    return courses


def process_saved_catalog(subjects=None):
    """Rebuild JSON from complete saved pages without opening a browser."""
    if subjects:
        subject_dirs = [COURSE_HTML_DIR / subject.upper() for subject in subjects]
    else:
        subject_dirs = sorted(
            path for path in COURSE_HTML_DIR.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        ) if COURSE_HTML_DIR.exists() else []
    if not subject_dirs:
        raise ValueError("no complete saved subject captures were found")
    for subject_dir in subject_dirs:
        data = parse_saved_subject(subject_dir)
        _write_course_info(subject_dir.name, data)
        print(f"Processed saved HTML for {subject_dir.name}: {len(data)} courses")


def _remove_capture_tree(path):
    """Remove a capture tree, retrying Windows read-only OneDrive entries."""
    path = Path(path)

    def make_writable_and_retry(function, failed_path, _exc_info):
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _publish_subject_capture(staging_dir, final_dir):
    """Replace a raw snapshot while restoring the old one if the move fails."""
    staging_dir = Path(staging_dir)
    final_dir = Path(final_dir)
    backup_dir = staging_dir.parent / f"_previous_{final_dir.name}"
    if backup_dir.exists():
        _remove_capture_tree(backup_dir)
    had_previous = final_dir.exists()
    if had_previous:
        final_dir.replace(backup_dir)
    try:
        staging_dir.replace(final_dir)
    except Exception:
        if had_previous and backup_dir.exists() and not final_dir.exists():
            backup_dir.replace(final_dir)
        raise
    if backup_dir.exists():
        try:
            _remove_capture_tree(backup_dir)
        except OSError as exc:
            # The new snapshot is already safely in place. OneDrive can keep a
            # transient lock on the renamed backup, so cleanup must not prevent
            # the parsed JSON from being written.
            print(f"Warning: could not remove old raw snapshot {backup_dir}: {exc}")


def _section_status(section_row):
    """Read a section status from its icon metadata or image filename."""
    image = section_row.locator("img[id$='img_status']")
    if image.count():
        for attribute in ("alt", "title"):
            value = _normalize_schedule_text(image.get_attribute(attribute))
            if value:
                return value
        source = image.get_attribute("src") or ""
        match = re.search(r"class_(open|closed|wait)(?:\.[a-z]+)?(?:\?.*)?$", source, re.IGNORECASE)
        if match:
            return "Wait List" if match.group(1).lower() == "wait" else match.group(1).title()
    return ""


def _component_identity(label):
    """Return (component label, component type, class number) from a grid label."""
    normalized = _normalize_schedule_text(label)
    class_match = re.search(r"\(([^()]*)\)\s*$", normalized)
    class_number = class_match.group(1).strip() if class_match else ""
    component = normalized[:class_match.start()].strip() if class_match else normalized
    type_match = re.search(r"-([A-Za-z]+)$", component)
    component_type = type_match.group(1).upper() if type_match else ""
    return component, component_type, class_number


def _text_or_empty(page, selector):
    """Return normalized text for an optional element."""
    locator = page.locator(selector)
    if not locator.count():
        return ""
    return _normalize_schedule_text(locator.first.inner_text())


def _class_availability(page):
    """Extract Class Availability fields from a class-detail page."""
    return {
        "class_capacity": _text_or_empty(page, "#uc_class_lbl_enrl_cap"),
        "wait_list_capacity": _text_or_empty(page, "#uc_class_lbl_wait_cap"),
        "enrollment_total": _text_or_empty(page, "#uc_class_lbl_enrl_tot"),
        "wait_list_total": _text_or_empty(page, "#uc_class_lbl_wait_tot"),
        "available_seats": _text_or_empty(page, "#uc_class_lbl_available_seat"),
    }


def _timetable_entries(meeting_grid):
    """Create one timetable entry per data row in a meeting grid."""
    entries = []
    if meeting_grid.count():
        meeting_rows = meeting_grid.locator(":scope > tbody > tr")
        for meeting_index in range(meeting_rows.count()):
            cells = meeting_rows.nth(meeting_index).locator(":scope > td").all_inner_texts()
            if not cells:
                continue
            cells = [_normalize_schedule_text(cell) for cell in cells]
            cells += [""] * (4 - len(cells))
            entries.append({
                "day_time": cells[0],
                "room": cells[1],
                "instructor": cells[2],
                "dates": cells[3],
            })

    if not entries:
        entries.append({
            "day_time": "",
            "room": "",
            "instructor": "",
            "dates": "",
        })
    return entries


def _scrape_class_detail(page, component, component_type, class_number, status=""):
    """Extract one section and its timetable from an open class page."""
    detail_component = _text_or_empty(page, "#uc_class_lbl_ssr_component")
    return {
        "section": component,
        "component_type": component_type or detail_component.upper(),
        "class_number": _text_or_empty(page, "#uc_class_lbl_class_nbr") or class_number,
        "status": _text_or_empty(page, "#uc_class_lbl_class_status") or status,
        **_class_availability(page),
        "timetable": _timetable_entries(page.locator("#uc_class_gv_meet")),
    }


def _scrape_grid_row(row, component, component_type, class_number):
    """Fallback to the summary grid if a class-detail page cannot be opened."""
    return {
        "section": component,
        "component_type": component_type,
        "class_number": class_number,
        "status": _section_status(row),
        "class_capacity": "",
        "wait_list_capacity": "",
        "enrollment_total": "",
        "wait_list_total": "",
        "available_seats": "",
        "timetable": _timetable_entries(row.locator("table[id$='gv_meet']")),
    }


def _scrape_current_schedule(page):
    """Open every class option and extract one object per section."""
    schedule_grid = page.locator("#uc_course_gv_sched")
    if not schedule_grid.count():
        return []

    sections = []
    link_selector = "#uc_course_gv_sched a[id$='lkbtn_class_section']"
    class_count = page.locator(link_selector).count()
    for class_index in range(class_count):
        # Re-locate after each class-detail postback because the DOM is replaced.
        section_link = page.locator(link_selector).nth(class_index)
        row = section_link.locator("xpath=ancestor::tr[1]")
        component, component_type, class_number = _component_identity(section_link.inner_text())
        fallback_section = _scrape_grid_row(row, component, component_type, class_number)

        try:
            section_link.click()
            page.wait_for_selector("#btn_class_return", timeout=10000)
            sections.append(
                _scrape_class_detail(
                    page,
                    component,
                    component_type,
                    class_number,
                    fallback_section["status"],
                )
            )
        except Exception as exc:
            print(f"Could not read class detail for {component} ({class_number}): {exc}")
            if page.locator("#uc_class_lbl_course").count():
                sections.append(
                    _scrape_class_detail(
                        page,
                        component,
                        component_type,
                        class_number,
                        fallback_section["status"],
                    )
                )
            else:
                sections.append(fallback_section)
        finally:
            return_button = page.locator("#btn_class_return")
            if return_button.count():
                return_button.click()
                page.wait_for_selector("#uc_course_gv_sched", timeout=10000)
    return sections


def _scrape_term_schedules(page):
    """Select and submit every entry under ``Term Offered``.

    Each returned term records whether the catalogue reports sections and, when
    present, each section's metadata and timetable. Terms with no sections are
    retained with an empty ``sections`` list.
    """
    term_select = page.locator("#uc_course_ddl_class_term")
    if not term_select.count():
        return []

    term_options = term_select.locator("option").evaluate_all(
        "options => options.map(option => ({value: option.value, "
        "term: (option.textContent || '').trim()})).filter(option => option.value)"
    )
    schedules = []
    for option in term_options:
        term_code = option["value"]
        term_label = option["term"]
        try:
            # Re-locate controls after each ASP.NET postback because the DOM is replaced.
            page.locator("#uc_course_ddl_class_term").select_option(value=term_code)
            show_button = page.locator("#uc_course_btn_class_section")
            if show_button.count() and not show_button.is_disabled():
                show_button.click()
                page.wait_for_load_state("load")

            sections = _scrape_current_schedule(page)
            shown_field = page.locator("#uc_course_hf_show_course_section")
            reported_offered = shown_field.count() and shown_field.input_value() == "1"
            schedules.append({
                "term_code": term_code,
                "term": term_label,
                "offered": bool(reported_offered or sections),
                "sections": sections,
            })
        except Exception as exc:
            print(f"Could not read schedule for {term_label} ({term_code}): {exc}")
            schedules.append({
                "term_code": term_code,
                "term": term_label,
                "offered": False,
                "sections": [],
            })
    return schedules


def _availability_from_sections(sections):
    """Derive Term 1/2 availability from academic-year section labels."""
    available_terms = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        match = ACADEMIC_TERM_PATTERN.search(str(section.get("term", "")))
        if match:
            available_terms.add(match.group(1))
    return "1" in available_terms, "2" in available_terms


def _availability_from_schedules(schedules):
    """Backward-compatible wrapper deriving availability from nested sections."""
    return _availability_from_sections(_flatten_sections(schedules))


def _flatten_sections(schedules):
    """Add term metadata to each section scraped under a term option."""
    flattened = []
    for schedule in schedules:
        for section in schedule.get("sections", []):
            flattened.append({
                "term_code": schedule["term_code"],
                "term": schedule["term"],
                **section,
            })
    return flattened


def _term_offerings(schedules):
    """Retain every checked term, including terms with no schedule rows."""
    offerings = []
    for schedule in schedules:
        offering = {
            "term_code": schedule["term_code"],
            "term": schedule["term"],
            "offered": schedule["offered"],
        }
        if schedule.get("retrieval_error"):
            offering["retrieval_error"] = schedule["retrieval_error"]
        offerings.append(offering)
    return offerings


def _scrape_term_availability(page):
    """Backward-compatible availability helper used by external callers."""
    return _availability_from_schedules(_scrape_term_schedules(page))


def _record_error(error_log, option, major, location, exc):
    """Retain an error for the final report while also showing it immediately."""
    message = f"option {option} ({major}), {location}: {exc}"
    error_log.append(message)
    print(f"ERROR: {message}")


def _course_base_info(page):
    """Extract fields shared by the whole course from its detail page."""
    code_and_title = page.locator("#uc_course_lbl_course").inner_text(timeout=PAGE_TIMEOUT)
    parts = code_and_title.split(" - ", 1)
    if len(parts) != 2:
        raise ValueError(f"unexpected course heading: {code_and_title!r}")
    course = {
        "code": parts[0].strip(),
        "title": parts[1].strip(),
        "unit": page.locator("#uc_course_lbl_units").inner_text(timeout=PAGE_TIMEOUT),
    }
    info = page.locator("#uc_course_tc_enrl_requirement")
    if info.count():
        course["info"] = info.inner_text(timeout=2000)
    return course


def _term_option_records(page):
    term_select = page.locator("#uc_course_ddl_class_term")
    if not term_select.count():
        return []
    return term_select.locator("option").evaluate_all(
        "options => options.map(option => ({value: option.value, "
        "term: (option.textContent || '').trim()})).filter(option => option.value)"
    )


def _open_course_by_index(page, course_index):
    """Open a known course index; exhaustion is handled before this function."""
    page.wait_for_selector("#gv_detail", state="attached", timeout=PAGE_TIMEOUT)
    links = page.locator("#gv_detail a[id$='lbtn_course_title']")
    if course_index >= links.count():
        raise IndexError(f"course index {course_index} is no longer present")
    _postback(page, links.nth(course_index))
    page.wait_for_selector("#uc_course_lbl_course", state="attached", timeout=PAGE_TIMEOUT)


def _course_link_count(page):
    """Return the explicit number of course links in the result table."""
    return page.locator("#gv_detail a[id$='lbtn_course_title']").count()


def _capture_manifest_path(state):
    return state["course_dir"] / "capture.json"


def _save_course_capture_state(state):
    _write_json_atomic(_capture_manifest_path(state), state["record"])


def _wait_for_selected_term(page, term_code):
    """Select a term and verify that the browser control accepted it."""
    selector = page.locator("#uc_course_ddl_class_term")
    selector.select_option(value=term_code)
    page.wait_for_load_state("load")
    selected = page.locator("#uc_course_ddl_class_term").input_value()
    if selected != term_code:
        raise RuntimeError(
            f"term postback selected {selected!r} instead of {term_code!r}"
        )


def _wait_for_schedule_result(page, term_code, timeout=PAGE_TIMEOUT):
    """Require a successful Show-sections postback, never infer empty on timeout."""
    page.wait_for_function(
        """termCode => {
          const term = document.querySelector('#uc_course_ddl_class_term');
          const shown = document.querySelector('#uc_course_hf_show_course_section');
          const current = document.querySelector('#uc_course_hf_current_course_term');
          const grid = document.querySelector('#uc_course_gv_sched');
          return term && term.value === termCode && shown && shown.value === '1' &&
                 current && current.value === termCode && grid;
        }""",
        arg=term_code,
        polling=250,
        timeout=timeout,
    )


def _schedule_is_current(page, term_code):
    term = page.locator("#uc_course_ddl_class_term")
    shown = page.locator("#uc_course_hf_show_course_section")
    current = page.locator("#uc_course_hf_current_course_term")
    return bool(
        term.count()
        and term.input_value() == term_code
        and shown.count()
        and shown.input_value() == "1"
        and current.count()
        and current.input_value() == term_code
        and page.locator("#uc_course_gv_sched").count()
    )


def _return_to_schedule(page, term_code):
    """Retry CUHK's occasionally stalled class-return postback in place."""
    last_error = None
    for _attempt in range(3):
        if _schedule_is_current(page, term_code):
            return
        return_button = page.locator("#btn_class_return")
        if not return_button.count():
            break
        try:
            _postback(page, return_button)
        except Exception as exc:
            last_error = exc
        try:
            _wait_for_schedule_result(page, term_code, timeout=20000)
            return
        except Exception as exc:
            last_error = exc
    if _schedule_is_current(page, term_code):
        return
    raise RuntimeError(
        f"could not return to the saved schedule for term {term_code} after "
        f"three local attempts: {last_error}"
    )


def _return_to_course_list(page):
    """Retry the course-return postback before considering session recovery."""
    last_error = None
    for _attempt in range(3):
        if page.locator("table#gv_detail").count():
            return
        return_button = page.locator("#btn_course_return")
        if not return_button.count():
            break
        try:
            _postback(page, return_button)
        except Exception as exc:
            last_error = exc
        try:
            page.wait_for_selector("table#gv_detail", state="attached", timeout=PAGE_TIMEOUT)
            return
        except Exception as exc:
            last_error = exc
    if page.locator("table#gv_detail").count():
        return
    raise RuntimeError(
        "could not return to the course list after three local attempts: "
        f"{last_error}"
    )


def _capture_course_schedules(page, state):
    """Save every term summary and class-detail page, resuming after recovery."""
    current_options = _term_option_records(page)
    if state["term_options"] is None:
        state["term_options"] = current_options
    elif current_options != state["term_options"]:
        raise RuntimeError("Term Offered options changed after recovery")

    while state["term_index"] < len(state["term_options"]):
        option = state["term_options"][state["term_index"]]
        term_code = option["value"]
        term_label = option["term"]
        if len(state["record"]["terms"]) == state["term_index"]:
            state["record"]["terms"].append({
                "term_code": term_code,
                "term": term_label,
                "schedule_page": f"terms/{state['term_index']:03d}_{term_code}.html",
                "show_button_disabled": None,
                "sections": [],
            })
            _save_course_capture_state(state)
        term_record = state["record"]["terms"][state["term_index"]]

        _wait_for_selected_term(page, term_code)
        show_button = page.locator("#uc_course_btn_class_section")
        if not show_button.count():
            raise RuntimeError(f"Show sections button missing for {term_label}")

        disabled = show_button.is_disabled()
        term_record["show_button_disabled"] = disabled
        if not disabled:
            _postback(page, show_button)
            _wait_for_schedule_result(page, term_code)
        elif page.locator("#uc_course_gv_sched").count():
            current = page.locator("#uc_course_hf_current_course_term")
            if not current.count() or current.input_value() != term_code:
                raise RuntimeError(
                    f"displayed schedule belongs to another term while "
                    f"{term_label} is selected"
                )

        schedule_path = state["course_dir"] / term_record["schedule_page"]
        _save_page_html(page, schedule_path)

        link_selector = "#uc_course_gv_sched a[id$='lkbtn_class_section']"
        class_count = page.locator(link_selector).count()
        if not disabled and class_count == 0:
            raise RuntimeError(
                f"enabled Show sections returned no section links for {term_label}"
            )
        if len(term_record["sections"]) > class_count:
            raise RuntimeError(
                f"section count fell from {len(term_record['sections'])} to "
                f"{class_count} for {term_label}"
            )

        for class_index in range(len(term_record["sections"]), class_count):
            section_link = page.locator(link_selector).nth(class_index)
            component, component_type, class_number = _component_identity(
                section_link.inner_text()
            )
            _postback(page, section_link)
            page.wait_for_selector("#btn_class_return", state="attached", timeout=PAGE_TIMEOUT)
            detail_heading = _text_or_empty(page, "#uc_class_lbl_course")
            if detail_heading and not re.match(
                rf"^{re.escape(state['record']['code'])}(?:\s|$|-)",
                detail_heading,
            ):
                raise RuntimeError(
                    f"class page belongs to {detail_heading!r}, expected "
                    f"{state['record']['code']!r}"
                )
            detail_page = (
                f"sections/{state['term_index']:03d}_{term_code}/"
                f"{class_index:04d}.html"
            )
            _save_page_html(page, state["course_dir"] / detail_page)
            term_record["sections"].append({
                "section_index": class_index,
                "section": component,
                "component_type": component_type,
                "class_number": class_number,
                "detail_page": detail_page,
            })
            _save_course_capture_state(state)

            if not page.locator("#btn_class_return").count():
                raise RuntimeError(
                    f"class return button missing after {component} ({class_number})"
                )
            _return_to_schedule(page, term_code)

        state["term_index"] += 1
        _save_course_capture_state(state)


def _capture_course_with_recovery(
    page, option, major_text, course_index, subject_capture_dir, error_log
):
    """Capture one complete course to disk, reopening it after up to three errors."""
    course_dir = Path(subject_capture_dir) / "courses" / f"{course_index:04d}"
    state = {
        "course_dir": course_dir,
        "term_options": None,
        "term_index": 0,
        "record": {
            "capture_schema_version": CAPTURE_SCHEMA_VERSION,
            "course_index": course_index,
            "code": "",
            "course_page": "course.html",
            "terms": [],
            "complete": False,
        },
    }
    recovery_attempts = 0

    while True:
        try:
            _open_course_by_index(page, course_index)
            reopened_base = _course_base_info(page)
            if not state["record"]["code"]:
                state["record"]["code"] = reopened_base["code"]
                _save_page_html(page, course_dir / "course.html")
                _save_course_capture_state(state)
            elif reopened_base["code"] != state["record"]["code"]:
                raise RuntimeError(
                    f"recovery opened {reopened_base['code']} instead of "
                    f"{state['record']['code']}"
                )

            _capture_course_schedules(page, state)
            state["record"]["complete"] = True
            _save_course_capture_state(state)
            _return_to_course_list(page)
            return state["record"], page, True
        except OSError as exc:
            _record_error(
                error_log,
                option,
                major_text,
                f"course index {course_index + 1}, saving raw snapshot",
                exc,
            )
            try:
                return None, page, _try_return_to_course_list(page)
            except Exception as return_exc:
                _record_error(
                    error_log,
                    option,
                    major_text,
                    "returning to course list after snapshot write failure",
                    return_exc,
                )
                return None, page, False
        except Exception as exc:
            location = (
                f"course index {course_index + 1}, term index "
                f"{state['term_index'] + 1}, next section index "
                f"{len(state['record']['terms'][state['term_index']]['sections']) + 1}"
                if state["term_index"] < len(state["record"]["terms"])
                else f"course index {course_index + 1}, opening course/term"
            )
            _record_error(error_log, option, major_text, location, exc)
            _ensure_browser_connected(page)
            if recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
                try:
                    return None, page, _try_return_to_course_list(page)
                except Exception as return_exc:
                    _record_error(
                        error_log,
                        option,
                        major_text,
                        "returning to course list after final retry",
                        return_exc,
                    )
                    return None, page, False

            recovered = False
            while recovery_attempts < MAX_RECOVERY_ATTEMPTS and not recovered:
                recovery_attempts += 1
                try:
                    recovered, page = recover_with_new_tab(
                        page,
                        option,
                        max_retries=1,
                        error_log=error_log,
                        major_text=major_text,
                    )
                except Exception as recovery_exc:
                    _record_error(
                        error_log,
                        option,
                        major_text,
                        f"recovery attempt {recovery_attempts}",
                        recovery_exc,
                    )
            if not recovered:
                return None, page, False


def _resume_course_schedules(page, state):
    """Resume at the first term/section not yet saved in ``state``."""
    current_options = _term_option_records(page)
    if state["term_options"] is None:
        state["term_options"] = current_options
    elif current_options != state["term_options"]:
        raise RuntimeError("Term Offered options changed after recovery")

    while state["term_index"] < len(state["term_options"]):
        option = state["term_options"][state["term_index"]]
        term_code = option["value"]
        term_label = option["term"]
        page.locator("#uc_course_ddl_class_term").select_option(value=term_code)
        show_button = page.locator("#uc_course_btn_class_section")
        if not show_button.count():
            raise RuntimeError(f"Show sections button missing for {term_label}")

        if show_button.is_disabled():
            if state["current_sections"]:
                raise RuntimeError(
                    f"Show sections button became disabled while resuming {term_label}"
                )
            sections = []
            reported_offered = False
        else:
            show_button.click()
            page.wait_for_load_state("load")
            schedule_grid = page.locator("#uc_course_gv_sched")
            link_selector = "#uc_course_gv_sched a[id$='lkbtn_class_section']"
            class_count = page.locator(link_selector).count() if schedule_grid.count() else 0
            sections = state["current_sections"]
            if len(sections) > class_count:
                raise RuntimeError(
                    f"section count fell from {len(sections)} to {class_count} for {term_label}"
                )

            for class_index in range(len(sections), class_count):
                section_link = page.locator(link_selector).nth(class_index)
                row = section_link.locator("xpath=ancestor::tr[1]")
                component, component_type, class_number = _component_identity(
                    section_link.inner_text()
                )
                status = _section_status(row)
                section_link.click()
                page.wait_for_selector("#btn_class_return", timeout=10000)
                sections.append(
                    _scrape_class_detail(
                        page, component, component_type, class_number, status
                    )
                )

                return_button = page.locator("#btn_class_return")
                if not return_button.count():
                    raise RuntimeError(
                        f"class return button missing after {component} ({class_number})"
                    )
                return_button.click()
                page.wait_for_selector("#uc_course_gv_sched", timeout=10000)

            shown_field = page.locator("#uc_course_hf_show_course_section")
            reported_offered = bool(
                (shown_field.count() and shown_field.input_value() == "1") or sections
            )

        state["schedules"].append({
            "term_code": term_code,
            "term": term_label,
            "offered": reported_offered,
            "sections": list(sections),
        })
        state["term_index"] += 1
        state["current_sections"] = []


def _finish_course_info(base_info, schedules):
    sections = _flatten_sections(schedules)
    term_1, term_2 = _availability_from_sections(sections)
    failed_offered_terms = [
        schedule for schedule in schedules
        if schedule.get("offered") and schedule.get("retrieval_error")
    ]
    failed_term_1, failed_term_2 = _availability_from_sections(
        failed_offered_terms
    )
    return {
        **base_info,
        "term_1": term_1 or failed_term_1,
        "term_2": term_2 or failed_term_2,
        "term_offerings": _term_offerings(schedules),
        "sections": sections,
    }


def _try_return_to_course_list(page):
    """Use available return buttons to leave a failed class/course page."""
    class_return = page.locator("#btn_class_return")
    if class_return.count():
        class_return.click()
        page.wait_for_selector("#uc_course_gv_sched", timeout=10000)

    course_return = page.locator("#btn_course_return")
    if course_return.count():
        course_return.click()
        page.wait_for_selector("table#gv_detail", timeout=10000)

    return bool(page.locator("table#gv_detail").count())


def _scrape_course_with_recovery(page, option, major_text, course_index, error_log):
    """Scrape one course, reopening it and resuming after up to three errors."""
    state = {
        "base_info": None,
        "term_options": None,
        "term_index": 0,
        "current_sections": [],
        "schedules": [],
        "finished_course": None,
    }
    recovery_attempts = 0

    while True:
        try:
            if state["finished_course"] is not None:
                return state["finished_course"], page, True

            _open_course_by_index(page, course_index)
            reopened_base = _course_base_info(page)
            if state["base_info"] is None:
                state["base_info"] = reopened_base
            elif reopened_base["code"] != state["base_info"]["code"]:
                raise RuntimeError(
                    f"recovery opened {reopened_base['code']} instead of "
                    f"{state['base_info']['code']}"
                )

            _resume_course_schedules(page, state)
            state["finished_course"] = _finish_course_info(
                state["base_info"], state["schedules"]
            )
            page.locator("#btn_course_return").click()
            page.wait_for_selector("table#gv_detail")
            return state["finished_course"], page, True
        except Exception as exc:
            location = (
                f"course index {course_index + 1}, term index "
                f"{state['term_index'] + 1}, next section index "
                f"{len(state['current_sections']) + 1}"
            )
            _record_error(error_log, option, major_text, location, exc)
            if recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
                try:
                    return None, page, _try_return_to_course_list(page)
                except Exception as return_exc:
                    _record_error(
                        error_log,
                        option,
                        major_text,
                        "returning to course list after final retry",
                        return_exc,
                    )
                    return None, page, False

            recovered = False
            while recovery_attempts < MAX_RECOVERY_ATTEMPTS and not recovered:
                recovery_attempts += 1
                try:
                    recovered, page = recover_with_new_tab(
                        page,
                        option,
                        max_retries=1,
                        error_log=error_log,
                        major_text=major_text,
                    )
                except Exception as recovery_exc:
                    _record_error(
                        error_log,
                        option,
                        major_text,
                        f"recovery attempt {recovery_attempts}",
                        recovery_exc,
                    )
            if not recovered:
                return None, page, False


def _write_course_info(major_text, scraped_data):
    COURSE_INFO_DIR.mkdir(parents=True, exist_ok=True)
    subject = major_text.split(" - ", 1)[0].strip()
    _write_json_atomic(COURSE_INFO_DIR / f"{subject}.json", scraped_data)


def course_info_to_json(page, major_text, option, error_log):
    """Capture every page first, then build JSON exclusively from saved HTML."""
    page.wait_for_selector("table#gv_detail")
    course_count = _course_link_count(page)
    subject = major_text.split(" - ", 1)[0].strip()
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    subject_capture_dir = (
        COURSE_HTML_DIR / "_incomplete" / f"{subject}_{run_stamp}"
    )
    subject_capture_dir.mkdir(parents=True, exist_ok=False)
    subject_manifest = {
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "subject_option": option,
        "subject": subject,
        "subject_label": major_text,
        "course_count": course_count,
        "course_list_page": "course_list.html",
        "courses": [],
        "complete": False,
    }
    _save_page_html(page, subject_capture_dir / "course_list.html")
    _write_json_atomic(subject_capture_dir / "manifest.json", subject_manifest)
    processed_slots = 0
    print(f"Found {course_count} courses for {major_text}.")

    for course_index in range(course_count):
        course_record, page, page_ready = _capture_course_with_recovery(
            page,
            option,
            major_text,
            course_index,
            subject_capture_dir,
            error_log,
        )
        if course_record is not None:
            subject_manifest["courses"].append({
                **course_record,
                "directory": f"courses/{course_index:04d}",
            })
            _write_json_atomic(
                subject_capture_dir / "manifest.json", subject_manifest
            )
            print(
                f"Captured course {course_index + 1}/{course_count}: "
                f"{course_record['code']}"
            )
        else:
            _record_error(
                error_log,
                option,
                major_text,
                f"course index {course_index + 1}",
                "skipped after three recovery attempts",
            )
        processed_slots += 1
        if not page_ready and processed_slots < course_count:
            # Course retries are exhausted. Restore only the subject list;
            # never reopen the failed course during this separate recovery.
            print(
                f"Restoring {subject}'s course list to continue with course "
                f"{course_index + 2}/{course_count}."
            )
            for attempt in range(MAX_RECOVERY_ATTEMPTS):
                try:
                    page_ready, page = recover_with_new_tab(
                        page, option, max_retries=1,
                        error_log=error_log, major_text=major_text,
                    )
                    if page_ready:
                        break
                except Exception as exc:
                    _record_error(
                        error_log, option, major_text,
                        f"restoring subject list after skipped course "
                        f"(attempt {attempt + 1}/{MAX_RECOVERY_ATTEMPTS})",
                        exc,
                    )
            if page_ready:
                continue
            _record_error(
                error_log,
                option,
                major_text,
                "major",
                "could not restore the course list; skipping remaining courses",
            )
            break

    capture_complete = (
        processed_slots == course_count
        and len(subject_manifest["courses"]) == course_count
    )
    if capture_complete:
        subject_manifest["complete"] = True
        _write_json_atomic(subject_capture_dir / "manifest.json", subject_manifest)
        final_capture_dir = COURSE_HTML_DIR / subject
        try:
            # Validate and parse the staging capture before replacing the last
            # known-good raw snapshot or its generated JSON.
            scraped_data = parse_saved_subject(subject_capture_dir)
        except Exception as exc:
            _record_error(
                error_log,
                option,
                major_text,
                "offline processing of saved pages",
                exc,
            )
            print(
                f"Saved pages were retained at {subject_capture_dir}, but the "
                "existing course_info JSON was not replaced."
            )
            return page
        _publish_subject_capture(subject_capture_dir, final_capture_dir)
        _write_course_info(major_text, scraped_data)
        print(
            f"Reached the known end of {major_text}: {course_count} complete "
            f"course snapshots saved to {final_capture_dir} and processed offline."
        )
    else:
        print(
            f"Incomplete capture for {major_text}: processed "
            f"{processed_slots}/{course_count} course slots, "
            f"{len(subject_manifest['courses'])} complete courses. The incomplete raw "
            f"capture was retained at {subject_capture_dir}; the existing "
            "course_info JSON was not replaced."
        )
    return page
            

def recover_with_new_tab(
    page,
    option,
    max_retries=MAX_RECOVERY_ATTEMPTS,
    error_log=None,
    major_text=None,
):
    """When the current page session dies (select_option timeout), open a new
    tab, navigate to the catalog, select the major, and solve captcha.
    Returns (True, new_page) on success, (False, original_page) on failure."""
    for attempt in range(max_retries):
        _ensure_browser_connected(page)
        print(f"Page operation failed. Reopening catalogue (attempt {attempt + 1}/{max_retries})...")
        # The old page may itself be closed while its browser is still usable.
        time.sleep(min(2 * (attempt + 1), 10))
        new_page = None
        try:
            new_page = page.context.new_page()
            new_page.goto(
                "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx",
                timeout=PAGE_TIMEOUT, wait_until="domcontentloaded",
            )
            new_page.locator("#ddl_subject").select_option(index=option)
            new_page.wait_for_timeout(500)
        except Exception as exc:
            if error_log is not None:
                _record_error(
                    error_log,
                    option,
                    major_text or f"option {option}",
                    f"new-tab setup attempt {attempt + 1}",
                    exc,
                )
            else:
                print(f"New tab setup failed for option {option}: {exc}")
            if new_page is not None and not new_page.is_closed():
                new_page.close()
            continue

        try:
            captcha_success, result_page = solve_captcha_with_reload(new_page, option)
        except Exception as exc:
            if error_log is not None:
                _record_error(
                    error_log,
                    option,
                    major_text or f"option {option}",
                    f"recovery captcha attempt {attempt + 1}",
                    exc,
                )
            if not new_page.is_closed():
                new_page.close()
            continue
        if captcha_success:
            try:
                page.close()
            except Exception:
                pass
            return True, result_page
        else:
            if error_log is not None:
                _record_error(
                    error_log,
                    option,
                    major_text or f"option {option}",
                    f"recovery captcha attempt {attempt + 1}",
                    "captcha could not be solved",
                )
            try:
                result_page.close()
            except Exception:
                pass

    print(f"Could not recover at option {option} after {max_retries} attempts.")
    return False, page


def _parse_option_list(value):
    """Parse individual indexes and inclusive ranges such as ``1-50, 101``."""
    normalized = re.sub(r"\s*-\s*", "-", value.strip())
    tokens = [token for token in re.split(r"[,;\s]+", normalized) if token]
    if not tokens:
        raise ValueError("Enter at least one option index.")

    options = []
    seen = set()
    for token in tokens:
        range_match = re.fullmatch(r"(\d+)-(\d+)", token)
        if range_match:
            start, end = (int(part) for part in range_match.groups())
            if start < 1 or end < 1:
                raise ValueError("Option indexes must be at least 1.")
            if start > end:
                raise ValueError(f"Option range must be ascending: {token!r}.")
            expanded = range(start, end + 1)
        else:
            try:
                option = int(token)
            except ValueError as exc:
                raise ValueError(f"Invalid option index or range: {token!r}.") from exc
            if option < 1:
                raise ValueError("Option indexes must be at least 1.")
            expanded = (option,)

        for option in expanded:
            if option not in seen:
                options.append(option)
                seen.add(option)
    return options


def _prompt_option_list():
    """Prompt for subject-dropdown indexes and inclusive ranges to scrape."""
    while True:
        try:
            return _parse_option_list(
                input("Subject option indexes/ranges (for example 1-50, 101-150): ")
            )
        except ValueError as exc:
            print(exc)
            continue


def _print_error_summary(error_log):
    print("\n=== Scraper error summary ===")
    if not error_log:
        print("No errors encountered.")
        return
    print(f"{len(error_log)} error(s) encountered:")
    for index, message in enumerate(error_log, start=1):
        print(f"{index}. {message}")


def crawl_course_catalog(options=None, headless=False):
    if options is None:
        options = _prompt_option_list()
    else:
        options = _parse_option_list(" ".join(str(option) for option in options))

    error_log = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.set_default_timeout(PAGE_TIMEOUT)
        context.set_default_navigation_timeout(PAGE_TIMEOUT)
        page = context.new_page()
        try:
            page.goto(
                "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx"
            )
            for option in options:
                major_text = f"option {option}"
                ready = False
                try:
                    page.locator("#ddl_subject").select_option(index=option)
                    major_text = page.locator(
                        "#ddl_subject option:checked"
                    ).inner_text()
                    print(f"Selected major: {major_text}")
                    captcha_success, page = solve_captcha_with_reload(page, option)
                    if captcha_success:
                        page.wait_for_load_state("load")
                        ready = True
                    else:
                        _record_error(
                            error_log,
                            option,
                            major_text,
                            "captcha",
                            "persistent captcha failure",
                        )
                except Exception as exc:
                    _record_error(
                        error_log, option, major_text, "initial subject setup", exc
                    )

                if not ready:
                    recovered, page = recover_with_new_tab(
                        page,
                        option,
                        error_log=error_log,
                        major_text=major_text,
                    )
                    if not recovered:
                        _record_error(
                            error_log,
                            option,
                            major_text,
                            "major",
                            "skipped after three recovery attempts",
                        )
                        continue
                    major_text = page.locator(
                        "#ddl_subject option:checked"
                    ).inner_text()
                    print(f"Recovered. Selected major: {major_text}")

                try:
                    page = course_info_to_json(
                        page, major_text, option, error_log
                    )
                except Exception as exc:
                    _record_error(
                        error_log, option, major_text, "unexpected major failure", exc
                    )
        except Exception as exc:
            _record_error(error_log, "?", "catalogue", "fatal setup", exc)
        finally:
            try:
                browser.close()
            finally:
                _print_error_summary(error_log)

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Capture CUHK course/class HTML before converting it to course_info JSON."
        )
    )
    parser.add_argument(
        "--process-saved",
        nargs="*",
        metavar="SUBJECT",
        help=(
            "skip the browser and rebuild JSON from saved subject directories; "
            "omit subject codes after the flag to process every complete capture"
        ),
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="run without browser windows (recommended for long/background runs)",
    )
    args = parser.parse_args(argv)
    if args.process_saved is not None:
        process_saved_catalog(args.process_saved)
    else:
        crawl_course_catalog(headless=args.headless)


if __name__ == "__main__":
    status, _ = _run_with_terminal_log(main)
    raise SystemExit(status)

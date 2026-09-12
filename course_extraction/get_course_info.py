from playwright.sync_api import sync_playwright
import sys
import os
import re
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent

import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)

# Subject options refer to the dropdown order at
# https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx
MAX_CAPTCHA_ATTEMPTS = 20
MAX_RECOVERY_ATTEMPTS = 3
ACADEMIC_TERM_PATTERN = re.compile(
    r"\b\d{4}\s*-\s*\d{2}\s+Term\s*([12])\b",
    re.IGNORECASE,
)


def _solve_captcha_attempt(page, max_attempts=MAX_CAPTCHA_ATTEMPTS):
    """Try to solve captcha up to *max_attempts* times.

    Returns True if solved, False if all attempts fail (e.g. stale error label
    persists despite correct input).
    """
    for attempt in range(max_attempts):
        captcha_image = page.locator("#imgCaptcha").screenshot()
        captcha_text = ocr.classification(captcha_image)
        page.locator("#txt_captcha").fill("")
        page.locator("#txt_captcha").press_sequentially(captcha_text.upper(), delay=100)
        page.locator("#btn_search").click()
        try:
            page.wait_for_selector("#lbl_error", timeout=2000)
            print(f"Captcha solving failed (attempt {attempt + 1}/{max_attempts}). Retrying...")
            page.wait_for_timeout(1000)
        except Exception:
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
    new_page.goto("https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx")
    new_page.wait_for_load_state("load")
    new_page.locator("#ddl_subject").select_option(index=option)
    new_page.wait_for_timeout(500)

    if _solve_captcha_attempt(new_page):
        page.close()
        return True, new_page

    print("Captcha still failed in the new tab.")
    new_page.close()
    return False, page


def _normalize_schedule_text(value):
    """Collapse whitespace used for visual table alignment into JSON-friendly text."""
    return re.sub(r"\s+", " ", value or "").strip()


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
    return [
        {
            "term_code": schedule["term_code"],
            "term": schedule["term"],
            "offered": schedule["offered"],
        }
        for schedule in schedules
    ]


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
    code_and_title = page.locator("#uc_course_lbl_course").inner_text(timeout=5000)
    parts = code_and_title.split(" - ", 1)
    if len(parts) != 2:
        raise ValueError(f"unexpected course heading: {code_and_title!r}")
    course = {
        "code": parts[0].strip(),
        "title": parts[1].strip(),
        "unit": page.locator("#uc_course_lbl_units").inner_text(timeout=2000),
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
    links = page.locator("#gv_detail a[id$='lbtn_course_title']")
    if course_index >= links.count():
        raise IndexError(f"course index {course_index} is no longer present")
    with page.expect_navigation():
        links.nth(course_index).click()


def _course_link_count(page):
    """Return the explicit number of course links in the result table."""
    return page.locator("#gv_detail a[id$='lbtn_course_title']").count()


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
    return {
        **base_info,
        "term_1": term_1,
        "term_2": term_2,
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
    import json

    os.makedirs(ROOT / "course_info", exist_ok=True)
    subject = major_text.split(" - ", 1)[0].strip()
    with open(ROOT / "course_info" / f"{subject}.json", "w", encoding="utf-8") as handle:
        json.dump(scraped_data, handle, ensure_ascii=False, indent=4)


def course_info_to_json(page, major_text, option, error_log):
    """Scrape exactly the courses listed, never using an error as end-of-list."""
    page.wait_for_selector("table#gv_detail")
    course_count = _course_link_count(page)
    scraped_data = []
    processed_slots = 0
    print(f"Found {course_count} courses for {major_text}.")

    for course_index in range(course_count):
        course_info, page, page_ready = _scrape_course_with_recovery(
            page, option, major_text, course_index, error_log
        )
        if course_info is not None:
            scraped_data.append(course_info)
            print(
                f"Scraped course {course_index + 1}/{course_count}: "
                f"{course_info['code']}"
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
        if not page_ready:
            _record_error(
                error_log,
                option,
                major_text,
                "major",
                "could not restore the course list; skipping remaining courses",
            )
            break

    _write_course_info(major_text, scraped_data)
    if processed_slots == course_count:
        print(
            f"Reached the known end of {major_text}: "
            f"{course_count} course slots processed."
        )
    else:
        print(
            f"Stopped {major_text} before the known end: processed "
            f"{processed_slots}/{course_count} course slots."
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
        print(f"Page session lost. Opening new tab to recover (attempt {attempt + 1}/{max_retries})...")
        new_page = page.context.new_page()
        try:
            new_page.goto(
                "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx",
                timeout=30000,
            )
            new_page.wait_for_load_state("load")
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
            if not new_page.is_closed():
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


def crawl_course_catalog(options=None):
    if options is None:
        options = _prompt_option_list()
    else:
        options = _parse_option_list(" ".join(str(option) for option in options))

    error_log = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
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
            browser.close()
            _print_error_summary(error_log)

if __name__ == "__main__":
    crawl_course_catalog()

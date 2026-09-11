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
    """Extract the flat Class Availability fields from a class-detail page."""
    return {
        "class_capacity": _text_or_empty(page, "#uc_class_lbl_enrl_cap"),
        "wait_list_capacity": _text_or_empty(page, "#uc_class_lbl_wait_cap"),
        "enrollment_total": _text_or_empty(page, "#uc_class_lbl_enrl_tot"),
        "wait_list_total": _text_or_empty(page, "#uc_class_lbl_wait_tot"),
        "available_seats": _text_or_empty(page, "#uc_class_lbl_available_seat"),
    }


def _meeting_records(meeting_grid, base_record):
    """Create one flat record per data row in a meeting grid."""
    records = []
    if meeting_grid.count():
        meeting_rows = meeting_grid.locator(":scope > tbody > tr")
        for meeting_index in range(meeting_rows.count()):
            cells = meeting_rows.nth(meeting_index).locator(":scope > td").all_inner_texts()
            if not cells:
                continue
            cells = [_normalize_schedule_text(cell) for cell in cells]
            cells += [""] * (4 - len(cells))
            records.append({
                **base_record,
                "day_time": cells[0],
                "room": cells[1],
                "instructor": cells[2],
                "dates": cells[3],
            })

    if not records:
        records.append({
            **base_record,
            "day_time": "",
            "room": "",
            "instructor": "",
            "dates": "",
        })
    return records


def _scrape_class_detail(page, component, component_type, class_number, status=""):
    """Extract meetings and availability from the currently open class page."""
    detail_component = _text_or_empty(page, "#uc_class_lbl_ssr_component")
    base_record = {
        "section": component,
        "component_type": component_type or detail_component.upper(),
        "class_number": _text_or_empty(page, "#uc_class_lbl_class_nbr") or class_number,
        "status": _text_or_empty(page, "#uc_class_lbl_class_status") or status,
        **_class_availability(page),
    }
    return _meeting_records(page.locator("#uc_class_gv_meet"), base_record)


def _scrape_grid_row(row, component, component_type, class_number):
    """Fallback to the summary grid if a class-detail page cannot be opened."""
    base_record = {
        "section": component,
        "component_type": component_type,
        "class_number": class_number,
        "status": _section_status(row),
        "class_capacity": "",
        "wait_list_capacity": "",
        "enrollment_total": "",
        "wait_list_total": "",
        "available_seats": "",
    }
    return _meeting_records(row.locator("table[id$='gv_meet']"), base_record)


def _scrape_current_schedule(page):
    """Open every class option and extract one flat record per meeting row.

    Component metadata is repeated for each meeting row.  This mirrors the
    source table and avoids a deeply nested section/component/meeting schema.
    """
    schedule_grid = page.locator("#uc_course_gv_sched")
    if not schedule_grid.count():
        return []

    schedule_rows = []
    link_selector = "#uc_course_gv_sched a[id$='lkbtn_class_section']"
    class_count = page.locator(link_selector).count()
    for class_index in range(class_count):
        # Re-locate after each class-detail postback because the DOM is replaced.
        section_link = page.locator(link_selector).nth(class_index)
        row = section_link.locator("xpath=ancestor::tr[1]")
        component, component_type, class_number = _component_identity(section_link.inner_text())
        fallback_rows = _scrape_grid_row(row, component, component_type, class_number)

        try:
            section_link.click()
            page.wait_for_selector("#btn_class_return", timeout=10000)
            schedule_rows.extend(
                _scrape_class_detail(
                    page,
                    component,
                    component_type,
                    class_number,
                    fallback_rows[0]["status"],
                )
            )
        except Exception as exc:
            print(f"Could not read class detail for {component} ({class_number}): {exc}")
            if page.locator("#uc_class_lbl_course").count():
                schedule_rows.extend(
                    _scrape_class_detail(
                        page,
                        component,
                        component_type,
                        class_number,
                        fallback_rows[0]["status"],
                    )
                )
            else:
                schedule_rows.extend(fallback_rows)
        finally:
            return_button = page.locator("#btn_class_return")
            if return_button.count():
                return_button.click()
                page.wait_for_selector("#uc_course_gv_sched", timeout=10000)
    return schedule_rows


def _scrape_term_schedules(page):
    """Select and submit every entry under ``Term Offered``.

    Each returned term records whether the catalogue reports sections and, when
    present, the section status plus every day/time, room, instructor and date
    row.  Terms with no sections are retained with an empty ``rows`` list.
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

            rows = _scrape_current_schedule(page)
            shown_field = page.locator("#uc_course_hf_show_course_section")
            reported_offered = shown_field.count() and shown_field.input_value() == "1"
            schedules.append({
                "term_code": term_code,
                "term": term_label,
                "offered": bool(reported_offered or rows),
                "rows": rows,
            })
        except Exception as exc:
            print(f"Could not read schedule for {term_label} ({term_code}): {exc}")
            schedules.append({
                "term_code": term_code,
                "term": term_label,
                "offered": False,
                "rows": [],
            })
    return schedules


def _availability_from_schedules(schedules):
    """Return the existing 2026-27 Term 1/2 booleans from schedule records."""
    offered_terms = {item["term_code"] for item in schedules if item.get("offered")}
    return "2420" in offered_terms, "2430" in offered_terms


def _flatten_teaching_schedule(schedules):
    """Add term metadata to each flat meeting row."""
    flattened = []
    for schedule in schedules:
        for row in schedule.get("rows", []):
            flattened.append({
                "term_code": schedule["term_code"],
                "term": schedule["term"],
                **row,
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


def course_info_to_json(page, major_text):
    scraped_data = []  # Initialize an empty list to store the scraped course information
    element_id = 2  # Start from the first course element (assuming the first course has an ID of 2)

    # ---------------------------------------------------------
    # STEP 1: The Crawl Loop
    # ---------------------------------------------------------
    while True:
        element_id_str = '0' + str(element_id) if element_id < 10 else str(element_id)
        command = f"__doPostBack('gv_detail$ctl{element_id_str}$lbtn_course_title','')"

        # print(f"Executing: {command}")
        
        # Trigger the postback and wait for the new page to load
        try:
            with page.expect_navigation():
                page.evaluate(command)
                # ---------------------------------------------------------
                # STEP 2: Scrape the Detail Page
                # ---------------------------------------------------------
                try:
                    course_code_and_title = page.locator("#uc_course_lbl_course").inner_text(timeout=5000)
                    course_info = {
                        "code": course_code_and_title.split(" - ", 1)[0].strip(),
                        "title": course_code_and_title.split(" - ", 1)[1].strip(),
                        "unit": page.locator("#uc_course_lbl_units").inner_text(timeout=2000),
                        "info": page.locator("#uc_course_tc_enrl_requirement").inner_text(timeout=2000)
                    }
                except:    # if the info field is not present, we can just skip it
                    course_info = {
                        "code": course_code_and_title.split(" - ", 1)[0].strip(),
                        "title": course_code_and_title.split(" - ", 1)[1].strip(),
                        "unit": page.locator("#uc_course_lbl_units").inner_text(timeout=2000),
                    }
                term_schedules = _scrape_term_schedules(page)
                term_1, term_2 = _availability_from_schedules(term_schedules)
                course_info["term_1"] = term_1
                course_info["term_2"] = term_2
                course_info["term_offerings"] = _term_offerings(term_schedules)
                course_info["teaching_schedule"] = _flatten_teaching_schedule(term_schedules)
                scraped_data.append(course_info)
                # print("Successfully scraped course details: ", course_info)
                element_id += 1  # Move to the next course
                page.locator("#btn_course_return").click()  # Return to the course list page

                # CRITICAL: Wait for the table to exist again before continuing
                page.wait_for_selector("table#gv_detail")

        # ---------------------------------------------------------
        # STEP 3: Handle the case when there are no more courses to scrape
        # ---------------------------------------------------------  
        except Exception as e:
            print(f"All courses for major {major_text} have been processed or an error occurred: {e}.")
            os.makedirs(ROOT / "course_info", exist_ok=True)
            with open(ROOT / "course_info" / f"{major_text.split(" - ", 1)[0].strip()}.json", "w", encoding="utf-8") as f:
                import json
                json.dump(scraped_data, f, ensure_ascii=False, indent=4)
            return
            

def recover_with_new_tab(page, option, max_retries=3):
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
        except Exception:
            print(f"New tab setup failed for option {option}.")
            new_page.close()
            continue

        captcha_success, result_page = solve_captcha_with_reload(new_page, option)
        if captcha_success:
            try:
                page.close()
            except Exception:
                pass
            return True, result_page
        else:
            try:
                result_page.close()
            except Exception:
                pass

    print(f"Could not recover at option {option} after {max_retries} attempts.")
    return False, page


def _parse_option_list(value):
    """Parse comma-, semicolon-, or whitespace-separated dropdown indexes."""
    tokens = [token for token in re.split(r"[,;\s]+", value.strip()) if token]
    if not tokens:
        raise ValueError("Enter at least one option index.")

    options = []
    seen = set()
    for token in tokens:
        try:
            option = int(token)
        except ValueError as exc:
            raise ValueError(f"Invalid option index: {token!r}.") from exc
        if option < 1:
            raise ValueError("Option indexes must be at least 1.")
        if option not in seen:
            options.append(option)
            seen.add(option)
    return options


def _prompt_option_list():
    """Prompt for the exact subject-dropdown indexes to scrape."""
    while True:
        try:
            return _parse_option_list(
                input("Subject option indexes (comma or space separated): ")
            )
        except ValueError as exc:
            print(exc)
            continue


def crawl_course_catalog(options=None):
    if options is None:
        options = _prompt_option_list()
    else:
        options = _parse_option_list(" ".join(str(option) for option in options))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. Navigate to the page and perform the initial search
        page.goto("https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx")
        for option in options:
            try:
                dropdown = page.locator("#ddl_subject")
                dropdown.select_option(index=option)
            except Exception as e:
                print(f"Select-option failed at option {option}: {e}")
                recovered, page = recover_with_new_tab(page, option)
                if not recovered:
                    print(f"Skipping option {option}...")
                    continue
                page.wait_for_load_state("load")
                major_text = page.locator("#ddl_subject option:checked").inner_text()
                print(f"Recovered. Selected major: {major_text}")
                course_info_to_json(page, major_text)
                continue
            major_text = page.locator("#ddl_subject option:checked").inner_text()
            print(f"Selected major: {major_text}")
            
            
            captcha_success, page = solve_captcha_with_reload(page, option)
            if not captcha_success:
                print(f"Skipping major {major_text} and exiting: persistent captcha failure even in a new tab.")
                print(f"Current option: {option}")
                break

            page.wait_for_load_state("load")
            
            course_info_to_json(page, major_text)

        browser.close()

if __name__ == "__main__":
    crawl_course_catalog()

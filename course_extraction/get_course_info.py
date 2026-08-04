from playwright.sync_api import sync_playwright
import sys
import io
import os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(__file__).parent

import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)

# Major to be scrapped, option refers to the dropdown order of https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx
start_option, end_option = 238,238
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


def _scrape_term_availability(page):
    """Check which 2026-27 terms a course is actually offered in.
    Returns (term_1: bool, term_2: bool)."""
    term_1, term_2 = False, False
    try:
        # Check if term dropdown exists
        term_select = page.locator("#uc_course_ddl_class_term")
        if not term_select.count():
            return term_1, term_2

        # Get all term options
        options = term_select.locator("option")
        option_values = [opt.get_attribute("value") for opt in options.all() if opt.get_attribute("value")]
        if not option_values:
            return term_1, term_2

        # Check current term first (no postback needed)
        current_term = page.locator("#uc_course_hf_current_course_term").input_value()
        show_sections = page.locator("#uc_course_hf_show_course_section").input_value() == "1"
        
        if current_term == "2420" and show_sections:
            term_1 = True
        elif current_term == "2430" and show_sections:
            term_2 = True

        # Check other terms via postback
        for opt_val in option_values:
            if opt_val == current_term:
                continue
            if opt_val not in ("2420", "2430"):
                continue
            try:
                term_select.select_option(value=opt_val)
                page.wait_for_timeout(300)
                # Click "Show sections" if button exists and is enabled
                show_btn = page.locator("#uc_course_btn_class_section")
                if show_btn.count() and not show_btn.is_disabled():
                    with page.expect_navigation(timeout=5000):
                        show_btn.click()
                    show_sections_other = page.locator("#uc_course_hf_show_course_section").input_value() == "1"
                    if opt_val == "2420" and show_sections_other:
                        term_1 = True
                    elif opt_val == "2430" and show_sections_other:
                        term_2 = True
            except Exception:
                pass

    except Exception:
        pass
    return term_1, term_2


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
                term_1, term_2 = _scrape_term_availability(page)
                course_info["term_1"] = term_1
                course_info["term_2"] = term_2
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


def crawl_course_catalog():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. Navigate to the page and perform the initial search
        page.goto("https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx")
        option = start_option
        
        while option <= end_option:   # Try a small number of options first, you can increase this later
            try:
                dropdown = page.locator("#ddl_subject")
                dropdown.select_option(index=option)
            except Exception as e:
                print(f"Select-option failed at option {option}: {e}")
                recovered, page = recover_with_new_tab(page, option)
                if not recovered:
                    print(f"Skipping option {option}...")
                    option += 1
                    continue
                page.wait_for_load_state("load")
                major_text = page.locator("#ddl_subject option:checked").inner_text()
                print(f"Recovered. Selected major: {major_text}")
                course_info_to_json(page, major_text)
                option += 1
                continue
            major_text = page.locator("#ddl_subject option:checked").inner_text()
            print(f"Selected major: {major_text}")
            
            
            captcha_success, page = solve_captcha_with_reload(page, option)
            if not captcha_success:
                print(f"Skipping major {major_text} and exiting: persistent captcha failure even in a new tab.")
                print(f"Current option: {option}")
                option += 1
                break

            page.wait_for_load_state("load")
            
            course_info_to_json(page, major_text)

            option += 1  # Move to the next major

        browser.close()

if __name__ == "__main__":
    crawl_course_catalog()
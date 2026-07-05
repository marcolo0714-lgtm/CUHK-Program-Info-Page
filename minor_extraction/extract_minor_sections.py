from playwright.sync_api import sync_playwright
import sys
import io
import os
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(__file__).parent

import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)

MAX_CAPTCHA_ATTEMPTS = 20
URL = "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx"


def sanitise_filename(name):
    """Convert a minor programme title into a safe filename."""
    keep = ""
    for ch in name:
        if ch.isalnum() or ch in " -_(),.":
            keep += ch
        else:
            keep += "_"
    keep = keep.strip().replace(" ", "_")
    # Collapse multiple underscores
    while "__" in keep:
        keep = keep.replace("__", "_")
    keep = keep.rstrip("_-.,")
    return keep or "Unknown"


def _solve_captcha_attempt(page, max_attempts=MAX_CAPTCHA_ATTEMPTS):
    """Try to solve captcha up to *max_attempts* times.

    Returns True if solved, False if all attempts fail.
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


def solve_captcha_with_new_tab(page):
    """Solve captcha.  If all attempts fail, open a new tab, navigate to the
    course catalog, and try one more batch.  Returns (True, page) on success
    (page may be the new tab), (False, original_page) on failure.
    """
    if _solve_captcha_attempt(page):
        return True, page

    print("Captcha failed after all attempts. Opening a new tab and retrying...")
    new_page = page.context.new_page()
    new_page.goto(URL)
    new_page.wait_for_load_state("load")
    new_page.locator("#ddl_acad_career").select_option(value="UG")
    new_page.locator("#ddl_acad_year").select_option(value="2025")
    new_page.locator("#ddl_acad_load").select_option(value="F")
    new_page.wait_for_timeout(500)

    if _solve_captcha_attempt(new_page):
        page.close()
        return True, new_page

    print("Captcha still failed in the new tab.")
    new_page.close()
    return False, page


def extract_minor_boxes(page):
    """Find all minor programme boxes on the current program detail page.

    Returns a list of (outerHTML, minor_title) tuples.  Only tables whose
    FIRST <td> contains 'Minor Programme Title' as a heading are matched,
    avoiding false positives from the 'Study Scheme' wrapper table.
    """
    boxes = page.evaluate("""() => {
        // Find elements whose trimmed text starts with 'Minor Programme Title'
        // and is short enough to be a heading (not a cell containing it
        // incidentally).  Then walk up to the enclosing <table>.
        const candidates = document.querySelectorAll('b, strong, p, span, h1, h2, h3, h4, h5, h6');
        const seenTables = new Set();
        const results = [];
        for (const el of candidates) {
            const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
            if (!txt.startsWith('Minor Programme Title') || txt.length > 50) continue;

            let table = el;
            while (table && table.tagName !== 'TABLE') table = table.parentElement;
            if (!table) continue;

            const key = table.outerHTML.slice(0, 800);
            if (seenTables.has(key)) continue;
            seenTables.add(key);

            // Find the enclosing <td> to extract the minor title
            let titleTd = el;
            while (titleTd && titleTd.tagName !== 'TD') titleTd = titleTd.parentElement;
            const cellText = titleTd ? (titleTd.innerText || titleTd.textContent || '') : '';
            const lines = cellText.split('\\n').map(s => s.trim()).filter(Boolean);
            const stopWords = ['Minor Programme Requirement', 'Explanatory Notes',
                               'Required Courses', 'Elective Courses', 'Units', 'Total:'];
            let title = '';
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].startsWith('Minor Programme Title')) {
                    let j = i + 1;
                    while (j < lines.length) {
                        const line = lines[j++];
                        if (!line || stopWords.some(w => line.includes(w))) break;
                        title += (title ? ' ' : '') + line;
                        if (title.split(' ').length >= 5) break;
                    }
                    break;
                }
            }
            // Fallback: regex on titleTd's innerHTML
            if (!title && titleTd) {
                const m = titleTd.innerHTML.match(
                    /Minor Programme Title<\\/[^>]+>\\s*(?:<[^>]+>)*\\s*([^<\\n]+)/
                );
                if (m) title = m[1].trim();
            }
            results.push({html: table.outerHTML, title: title || 'Unknown'});
        }
        return results;
    }""")
    return boxes


def crawl_programs():
    programs_without_minor = []
    programs_with_one_minor = []
    multi_minor_programs = []
    faculties = {}                 # adms -> faculty short name
    total_extracted = 0

    os.makedirs(ROOT / "minor_html", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(URL)
        page.locator("#ddl_acad_career").select_option(value="UG")
        page.locator("#ddl_acad_year").select_option(value="2025")
        page.locator("#ddl_acad_load").select_option(value="F")
        page.wait_for_timeout(500)

        success, page = solve_captcha_with_new_tab(page)
        if not success:
            print("Cannot solve captcha. Exiting.")
            browser.close()
            return

        page.wait_for_load_state("networkidle")

        try:
            page.wait_for_selector("table#gv_detail", timeout=10000)
        except Exception:
            print("Search results grid not found. Exiting.")
            browser.close()
            return

        element_id = 2

        while True:
            element_id_str = f"{element_id:02d}"
            command = f"__doPostBack('gv_detail$ctl{element_id_str}$lbtn_prog_descr','')"

            try:
                # Capture faculty from the grid row before navigating away
                faculty_locator = page.locator(f"#gv_detail_ctl{element_id_str}_lbtn_faculty")
                try:
                    faculty_raw = faculty_locator.inner_text(timeout=2000)
                    # Strip "Faculty of " prefix for shorter form
                    faculty = faculty_raw.replace("Faculty of ", "").strip()
                except Exception:
                    faculty = "Unknown"

                with page.expect_navigation(timeout=30000):
                    page.evaluate(command)
                page.wait_for_load_state("networkidle")
                # Page loads slowly — wait up to 10s for content to appear
                try:
                    page.locator("body").get_by_text("Major Programme Requirement").first.wait_for(timeout=10000)
                except Exception:
                    print("  Page not loaded, trying reload...")
                    page.reload()
                    page.wait_for_load_state("networkidle")
                    try:
                        page.locator("body").get_by_text("Major Programme Requirement").first.wait_for(timeout=10000)
                    except Exception:
                        pass  # proceed anyway

                adm_code = page.input_value("#uc_scheme_hf_admission_code")
                prog_descr = page.input_value("#uc_scheme_hf_prog_descr")
                print(f"\n[{adm_code}] {prog_descr}")

                minor_boxes = extract_minor_boxes(page)
                num_minors = len(minor_boxes)

                if num_minors == 0:
                    print(f"  -> No minor programme")
                    programs_without_minor.append(adm_code)
                else:
                    if num_minors == 1:
                        programs_with_one_minor.append(adm_code)
                    elif num_minors > 1:
                        multi_minor_programs.append((adm_code, num_minors))
                    for box in minor_boxes:
                        safe_name = sanitise_filename(box["title"])
                        filepath = ROOT / "minor_html" / f"{adm_code}_{safe_name}.html"
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(box["html"])
                        # Record faculty for this minor
                        faculties[f"{adm_code}_{safe_name}"] = faculty
                    print(f"  -> Saved {num_minors} minor section(s): " + ", ".join(b["title"] for b in minor_boxes))
                    total_extracted += num_minors

                page.locator("#btn_scheme_return2").click()
                page.wait_for_selector("table#gv_detail")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(500)  # brief pause between majors

                element_id += 1

            except Exception as e:
                print(f"\nAll programs processed or error at element {element_id}: {e}")
                break

        browser.close()

    # Save faculty mapping
    if faculties:
        fac_path = ROOT / "minor_html" / "_faculties.json"
        fac_path.write_text(json.dumps(faculties, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFaculty info saved: {fac_path}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total minor sections extracted: {total_extracted}")

    if programs_without_minor:
        print(f"\nPrograms with 0 minors ({len(programs_without_minor)}):")
        for code in programs_without_minor:
            print(f"  {code}")

    if programs_with_one_minor:
        print(f"\nPrograms with 1 minor ({len(programs_with_one_minor)}):")
        for code in programs_with_one_minor:
            print(f"  {code}")

    if multi_minor_programs:
        print(f"\nPrograms with 2+ minors ({len(multi_minor_programs)}):")
        for code, count in multi_minor_programs:
            print(f"  {code}: {count} minors")

    print("\nDone.")


if __name__ == "__main__":
    crawl_programs()

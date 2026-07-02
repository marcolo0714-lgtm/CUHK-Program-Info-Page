from playwright.sync_api import sync_playwright
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
        const tables = document.querySelectorAll('table[border="1"]');
        const results = [];
        for (const table of tables) {
            const firstTd = table.querySelector('td');
            if (!firstTd) continue;
            if (!firstTd.textContent.includes('Minor Programme Title')) continue;

            // innerText preserves <p> line breaks; textContent does not
            const cellText = firstTd.innerText || firstTd.textContent || '';
            const lines = cellText.split('\\n').map(s => s.trim()).filter(Boolean);
            let title = '';
            for (let i = 0; i < lines.length; i++) {
                if (lines[i] === 'Minor Programme Title') {
                    let j = i + 1;
                    while (j < lines.length && lines[j]) title += (title ? ' ' : '') + lines[j++];
                    break;
                }
            }
            // Fallback: extract from raw HTML via regex
            if (!title) {
                const m = firstTd.outerHTML.match(
                    /Minor Programme Title<\\/[^>]+>\\s*(?:<[^>]+>)*\\s*([^<]+)/
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
    multi_minor_programs = []
    total_extracted = 0

    os.makedirs("minor_html", exist_ok=True)

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
                with page.expect_navigation():
                    page.evaluate(command)

                page.wait_for_load_state("networkidle")

                adm_code = page.input_value("#uc_scheme_hf_admission_code")
                prog_descr = page.input_value("#uc_scheme_hf_prog_descr")
                print(f"\n[{adm_code}] {prog_descr}")

                minor_boxes = extract_minor_boxes(page)
                num_minors = len(minor_boxes)

                if num_minors == 0:
                    print(f"  -> No minor programme")
                    programs_without_minor.append(adm_code)
                elif num_minors == 1:
                    box = minor_boxes[0]
                    safe_name = sanitise_filename(box["title"])
                    filepath = f"minor_html/{safe_name}.html"
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(box["html"])
                    print(f"  -> Saved: {box['title']}")
                    total_extracted += 1
                else:
                    multi_minor_programs.append((adm_code, num_minors))
                    for box in minor_boxes:
                        safe_name = sanitise_filename(box["title"])
                        # If there are multiple minors with the same safe_name, disambiguate
                        base = safe_name
                        counter = 1
                        filepath = f"minor_html/{base}.html"
                        while os.path.exists(filepath):
                            filepath = f"minor_html/{base}_{counter:02d}.html"
                            counter += 1
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(box["html"])
                    print(f"  -> Saved {num_minors} minor sections: " + ", ".join(b["title"] for b in minor_boxes))
                    total_extracted += num_minors

                page.locator("#btn_scheme_return2").click()
                page.wait_for_selector("table#gv_detail")
                page.wait_for_load_state("networkidle")

                element_id += 1

            except Exception as e:
                print(f"\nAll programs processed or error at element {element_id}: {e}")
                break

        browser.close()

    # --- Summary ---
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total minor sections extracted: {total_extracted}")

    if programs_without_minor:
        print(f"\nPrograms with 0 minors ({len(programs_without_minor)}):")
        for code in programs_without_minor:
            print(f"  {code}")

    if multi_minor_programs:
        print(f"\nPrograms with 2+ minors ({len(multi_minor_programs)}):")
        for code, count in multi_minor_programs:
            print(f"  {code}: {count} minors")

    print("\nDone.")


if __name__ == "__main__":
    crawl_programs()

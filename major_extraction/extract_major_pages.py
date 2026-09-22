"""Scrape complete CUHK undergraduate major programme pages.

The original minor project extracts only the minor requirement component from
each academic-programme page. This scraper intentionally preserves the entire
detail document, then writes a small metadata index for parsing and generation.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import ddddocr
from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding="utf-8",
    line_buffering=True,
    write_through=True,
)

URL = "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_acad_prog.aspx"
ROOT = Path(__file__).resolve().parent
MAX_CAPTCHA_ATTEMPTS = 20
MAX_PAGE_ATTEMPTS = 3
# Empty CUHK detail responses observed in saved captures are roughly 58-62 KB,
# while the smallest page containing a real requirement table is over 180 KB.
MIN_COMPLETE_PAGE_BYTES = 100_000
ocr = ddddocr.DdddOcr(show_ad=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2026_27", help="Admission year, e.g. 2026_27")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--faculty",
        action="append",
        default=[],
        help="Only scrape this faculty (repeatable). By default every faculty is scraped.",
    )
    return parser.parse_args()


def sanitise_filename(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in " -_(),." else "_" for ch in name)
    keep = re.sub(r"_+", "_", keep.strip().replace(" ", "_")).rstrip("_-.,")
    return keep or "Unknown"


def configure_search(page: Page, year: str) -> None:
    page.goto(URL)
    page.wait_for_load_state("load")
    page.locator("#ddl_acad_career").select_option(value="UG")
    page.locator("#ddl_acad_year").select_option(value=year[:4])
    page.locator("#ddl_acad_load").select_option(value="F")
    page.wait_for_timeout(500)


def solve_captcha(page: Page, year: str) -> Page:
    for batch in range(2):
        for attempt in range(MAX_CAPTCHA_ATTEMPTS):
            answer = ocr.classification(page.locator("#imgCaptcha").screenshot()).upper()
            page.locator("#txt_captcha").fill("")
            page.locator("#txt_captcha").press_sequentially(answer, delay=100)
            page.locator("#btn_search").click()
            try:
                page.wait_for_selector("#lbl_error", timeout=2_000)
                print(f"Captcha failed ({attempt + 1}/{MAX_CAPTCHA_ATTEMPTS}); retrying")
                page.wait_for_timeout(700)
            except Exception:
                page.wait_for_selector("table#gv_detail", timeout=10_000)
                return page
        if batch == 0:
            print("Opening a fresh tab for another CAPTCHA batch")
            fresh = page.context.new_page()
            configure_search(fresh, year)
            page.close()
            page = fresh
    raise RuntimeError("Unable to solve CAPTCHA after two batches")


def collect_programme_rows(page: Page, faculties: list[str] | None = None) -> list[dict[str, str]]:
    return page.locator("table#gv_detail tr").evaluate_all(
        r"""rows => rows.flatMap(row => {
          const facultyLink = row.querySelector("a[id$='_lbtn_faculty']");
          const programmeLink = row.querySelector("a[id$='_lbtn_prog_descr']");
          if (!facultyLink || !programmeLink) return [];
          const faculty = (facultyLink.textContent || '').replace('Faculty of ', '').trim();
          const href = programmeLink.getAttribute('href') || '';
          const postback = href.match(/__doPostBack\('([^']+)'/);
          if (!postback) return [];
          return [{
            faculty,
            gridTitle: (programmeLink.textContent || '').replace(/\s+/g, ' ').trim(),
            postback: postback[1]
          }];
        })"""
    )


def filter_programme_rows(
    rows: list[dict[str, str]], faculties: list[str] | None = None
) -> list[dict[str, str]]:
    selected = {faculty.casefold() for faculty in (faculties or [])}
    if not selected:
        return rows
    return [row for row in rows if row["faculty"].casefold() in selected]


def consolidate_programme_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Collapse cross-listed catalogue rows while retaining every faculty."""
    programmes: dict[str, dict[str, object]] = {}
    for row in rows:
        key = clean_grid_title(row["gridTitle"]).casefold()
        if key not in programmes:
            programmes[key] = {**row, "faculties": [row["faculty"]]}
        elif row["faculty"] not in programmes[key]["faculties"]:
            programmes[key]["faculties"].append(row["faculty"])
    return list(programmes.values())


def clean_grid_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def value(page: Page, selector: str, fallback: str = "") -> str:
    locator = page.locator(selector)
    if not locator.count():
        return fallback
    try:
        return locator.input_value().strip()
    except Exception:
        return locator.inner_text().strip() or fallback


def is_detail_page(page: Page) -> bool:
    return bool(
        page.locator(
            "#uc_scheme_hf_admission_code, #uc_scheme_lbl_prog_descr, "
            "#btn_scheme_return2, #btn_scheme_return"
        ).count()
    )


def html_size_bytes(content: str) -> int:
    return len(content.encode("utf-8"))


def saved_page_is_complete(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= MIN_COMPLETE_PAGE_BYTES


def return_to_result_grid(page: Page, year: str) -> Page:
    """Return to the programme list, rebuilding the search if necessary."""
    if page.locator("table#gv_detail").count():
        return page
    try:
        return_button = page.locator("#btn_scheme_return2, #btn_scheme_return")
        if return_button.count():
            return_button.last.click()
            page.wait_for_selector("table#gv_detail", timeout=30_000)
            page.wait_for_timeout(400)
            return page
    except Exception:
        pass
    configure_search(page, year)
    return solve_captcha(page, year)


def extract_major_component(page: Page) -> str:
    """Return the innermost useful table containing the major requirement."""
    return page.evaluate(
        r"""() => {
          const tables = [...document.querySelectorAll('table')];
          const matches = tables.filter(table => {
            const text = (table.innerText || table.textContent || '').replace(/\s+/g, ' ');
            return text.includes('Major Programme Requirement') && /[A-Z]{4}\s*\d{4}/.test(text);
          });
          if (!matches.length) return '';
          matches.sort((a, b) => a.outerHTML.length - b.outerHTML.length);
          return matches[0].outerHTML;
        }"""
    )


def saved_record(full_path: Path, stem: str, faculties: list[str]) -> dict[str, object]:
    soup = BeautifulSoup(full_path.read_text(encoding="utf-8"), "html.parser")
    admission = soup.select_one("#uc_scheme_hf_admission_code")
    description = soup.select_one("#uc_scheme_hf_prog_descr")
    return {
        "stem": stem,
        "admission_code": admission.get("value", "") if admission else "",
        "title": description.get("value", stem.replace("_", " ")) if description else stem.replace("_", " "),
        "faculty": faculties[0] if faculties else "",
        "faculties": faculties,
        "component_file": f"{stem}.html",
        "full_page_file": f"full_pages/{stem}.html",
    }


def crawl(year: str, headless: bool, faculties: list[str] | None = None) -> None:
    output = ROOT / "major_html" / year
    full_dir = output / "full_pages"
    full_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        configure_search(page, year)
        page = solve_captcha(page, year)
        raw_rows = filter_programme_rows(collect_programme_rows(page), faculties)
        rows = consolidate_programme_rows(raw_rows)
        scope = ", ".join(faculties or []) or "all faculties"
        print(
            f"Found {len(rows)} unique undergraduate programmes from "
            f"{len(raw_rows)} catalogue rows for {scope}"
        )
        (output / "_programme_rows.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        used_stems: set[str] = set()

        for index, grid_row in enumerate(rows, start=1):
            expected_stem = sanitise_filename(str(grid_row["gridTitle"]))
            if expected_stem in used_stems:
                expected_stem = sanitise_filename(f'{grid_row["gridTitle"]}_{index}')
            used_stems.add(expected_stem)
            existing = full_dir / f"{expected_stem}.html"
            if saved_page_is_complete(existing):
                record = saved_record(existing, expected_stem, list(grid_row["faculties"]))
                records.append(record)
                print(f"[{index}/{len(rows)}] Skipping saved {record['admission_code']} - {record['title']}")
                continue
            if existing.exists():
                print(
                    f"[{index}/{len(rows)}] Re-scraping suspicious saved page "
                    f"({existing.stat().st_size:,} bytes): {grid_row['gridTitle']}"
                )

            full_page_html = ""
            for attempt in range(MAX_PAGE_ATTEMPTS):
                try:
                    with page.expect_navigation(timeout=90_000):
                        page.evaluate("target => __doPostBack(target, '')", grid_row["postback"])
                    page.wait_for_load_state("domcontentloaded")
                    page.locator(
                        "#uc_scheme_hf_admission_code, #uc_scheme_lbl_prog_descr, "
                        "#btn_scheme_return2, #btn_scheme_return"
                    ).first.wait_for(timeout=30_000)
                except Exception:
                    if not is_detail_page(page):
                        print(
                            f"  Warning: unable to open {grid_row['gridTitle']} "
                            f"(attempt {attempt + 1}/{MAX_PAGE_ATTEMPTS})"
                        )

                if is_detail_page(page):
                    candidate = page.content()
                    candidate_size = html_size_bytes(candidate)
                    if candidate_size >= MIN_COMPLETE_PAGE_BYTES:
                        full_page_html = candidate
                        break
                    print(
                        f"  Warning: detail page is only {candidate_size:,} bytes; "
                        f"retrying ({attempt + 1}/{MAX_PAGE_ATTEMPTS})"
                    )

                if attempt + 1 < MAX_PAGE_ATTEMPTS:
                    page = return_to_result_grid(page, year)

            if not full_page_html:
                print(
                    f"  Warning: {grid_row['gridTitle']} remained incomplete after "
                    f"{MAX_PAGE_ATTEMPTS} attempts; no saved page was replaced"
                )
                page = return_to_result_grid(page, year)
                continue

            if not is_detail_page(page):
                continue

            admission_code = value(page, "#uc_scheme_hf_admission_code")
            title = value(
                page,
                "#uc_scheme_hf_prog_descr",
                value(page, "#uc_scheme_lbl_prog_descr", str(grid_row["gridTitle"])),
            )
            stem = expected_stem
            print(f"[{index}/{len(rows)}] {admission_code} - {title}")

            (full_dir / f"{stem}.html").write_text(full_page_html, encoding="utf-8")
            component = extract_major_component(page)
            if not component:
                print("  Warning: major requirement component not found")
            (output / f"{stem}.html").write_text(component, encoding="utf-8")
            records.append({
                "stem": stem,
                "admission_code": admission_code,
                "title": title,
                "faculty": grid_row["faculties"][0] if grid_row["faculties"] else "",
                "faculties": grid_row["faculties"],
                "component_file": f"{stem}.html",
                "full_page_file": f"full_pages/{stem}.html",
            })
            (output / "_programmes.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            page.locator("#btn_scheme_return2, #btn_scheme_return").last.click()
            page.wait_for_selector("table#gv_detail", timeout=30_000)
            page.wait_for_timeout(400)

        (output / "_programmes.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()
    print(f"Saved {len(records)} complete undergraduate programme pages to {output}")


if __name__ == "__main__":
    cli = parse_args()
    crawl(cli.year, cli.headless, cli.faculty)

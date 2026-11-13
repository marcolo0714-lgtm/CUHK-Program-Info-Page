"""Build and verify the complete combined CUHK minor/major static site."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .site_metadata import update_course_schedule_date, write_discovery_files
    from .publication import prune_assets
except ImportError:
    from site_metadata import update_course_schedule_date, write_discovery_files
    from publication import prune_assets


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def run_script(relative_path: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / relative_path), *arguments]
    display_command = [Path(sys.executable).name, relative_path, *arguments]
    print(f"\n> {' '.join(display_command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def year_arguments(years: list[str] | None) -> list[list[str]]:
    if not years:
        return [[]]
    return [["--year", year] for year in years]


def discover_major_years() -> list[str]:
    source = ROOT / "major_extraction" / "major_json"
    return sorted(
        directory.name
        for directory in source.iterdir()
        if directory.is_dir() and any(directory.glob("*.json"))
    )


def resolve_local_link(page: Path, href: str) -> Path | None:
    parts = urlsplit(href)
    # Vercel serves its optional analytics endpoint; it is not a build artifact.
    if parts.path == "/_vercel/insights/script.js":
        return None
    if parts.scheme or parts.netloc or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    clean_path = unquote(parts.path)
    if not clean_path:
        return None
    if clean_path.startswith("/"):
        target = SITE / clean_path.lstrip("/")
    else:
        target = page.parent / clean_path
    return target.resolve()


def link_target_exists(target: Path) -> bool:
    candidates = [target, Path(str(target) + ".html"), target / "index.html"]
    return any(candidate.is_file() for candidate in candidates)


def verify_internal_links() -> None:
    missing: list[str] = []
    # Course tables repeat the same links thousands of times. Resolve and stat
    # each distinct target once, including links in the full-details fallback.
    resolved: dict[tuple[Path, str], Path | None] = {}
    valid: dict[Path, bool] = {}
    site_root = SITE.resolve()
    href_pattern = re.compile(r'''\b(?:href|src|data-src|data-url|data-fallback)=["']([^"']+)["']''', re.IGNORECASE)
    for page in SITE.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        for href in href_pattern.findall(html):
            key = (page.parent, href)
            if key not in resolved:
                resolved[key] = resolve_local_link(page, href)
            target = resolved[key]
            if target is None:
                continue
            try:
                target.relative_to(site_root)
            except ValueError:
                missing.append(f"{page.relative_to(ROOT)} -> {href} (outside site/)")
                continue
            if target not in valid:
                valid[target] = link_target_exists(target)
            if not valid[target]:
                missing.append(f"{page.relative_to(ROOT)} -> {href}")
    if missing:
        preview = "\n".join(f"  {item}" for item in missing[:30])
        remainder = f"\n  ... and {len(missing) - 30} more" if len(missing) > 30 else ""
        raise RuntimeError(f"Generated site contains {len(missing)} broken internal link(s):\n{preview}{remainder}")
    print("Internal-link check: OK")


def verify_expected_pages(major_years: list[str]) -> None:
    for year in major_years:
        expected = set()
        for path in (ROOT / "major_extraction" / "major_json" / year).glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            expected.add(path.with_suffix(".html").name)
            schemes = data.get("requirement_schemes", [])
            default = next(
                (scheme for scheme in schemes if scheme.get("kind") == "standard"),
                next((scheme for scheme in schemes if scheme.get("default")), schemes[0] if schemes else None),
            )
            expected.update(
                f'{path.stem}--{scheme["id"]}.html' for scheme in schemes if scheme is not default
            )
        actual = {path.name for path in (SITE / "major" / year / "majors").glob("*.html")}
        if expected != actual:
            raise RuntimeError(
                f"Major pages mismatch for {year}: missing {sorted(expected - actual)}, "
                f"unexpected {sorted(actual - expected)}"
            )
    print("Generated-page count check: OK")


def verify_javascript() -> None:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for generated JavaScript syntax verification")
    checker = r"""
const fs = require('fs');
const path = require('path');
const root = process.argv[1];
let checked = 0;
function walk(directory) {
  for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.html')) {
      const html = fs.readFileSync(full, 'utf8');
      const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)];
      for (const match of scripts) {
        const attrs = match[1] || '';
        const type = attrs.match(/\btype=["']([^"']+)["']/i);
        if (/\bsrc\s*=/i.test(attrs)) continue;
        if (type && !/(?:java|ecma)script|module/i.test(type[1])) continue;
        if (!match[2].trim()) continue;
        new Function(match[2]);
        checked++;
      }
    } else if (entry.name.endsWith('.js')) {
      new Function(fs.readFileSync(full, 'utf8'));
      checked++;
    }
  }
}
walk(root);
console.log(`JavaScript syntax check: OK (${checked} scripts)`);
"""
    subprocess.run([node, "-e", checker, str(SITE)], cwd=ROOT, check=True)


def build(args: argparse.Namespace) -> None:
    if args.update_course_schedule_date:
        if args.minor_year or args.major_year:
            raise ValueError("--update-course-schedule-date requires a full build; omit year filters")
        print(f"Course teaching schedule date: {update_course_schedule_date()} (Hong Kong)")
    for year_args in year_arguments(args.minor_year):
        run_script("minor_planner/generate_checker_data.py", *year_args)
    for year_args in year_arguments(args.minor_year):
        run_script("site_generator/generate_checker_page.py", *year_args)
    for year_args in year_arguments(args.minor_year):
        run_script("site_generator/generate_minor_site.py", *year_args)

    major_years = args.major_year or discover_major_years()
    if args.rebuild_major_json:
        for year in major_years:
            run_script("major_extraction/generate_major_json.py", "--year", year)
    for year in major_years:
        run_script("site_generator/generate_major_site.py", "--year", year)

    # This must run after both programme generators so the sitemap and
    # redirects contain every minor and major page.
    prune_assets(SITE)
    write_discovery_files(SITE)
    print("\nDiscovery files regenerated: sitemap.xml, robots.txt, _redirects")

    if not args.skip_verify:
        verify_expected_pages(major_years)
        verify_internal_links()
        verify_javascript()
    print("\nCombined site build complete. Deploy the site/ directory.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--minor-year",
        action="append",
        help="Generate only this minor admission year (repeatable); default: all years",
    )
    parser.add_argument(
        "--major-year",
        action="append",
        help="Generate only this major admission year (repeatable); default: all major_json years",
    )
    parser.add_argument(
        "--rebuild-major-json",
        action="store_true",
        help="Reparse saved major HTML before generating major pages",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip generated page-count, internal-link, and JavaScript checks",
    )
    parser.add_argument(
        "--update-course-schedule-date",
        action="store_true",
        help="Set every schedule footer to today's Hong Kong date (full builds only); otherwise retain the saved date",
    )
    build(parser.parse_args())

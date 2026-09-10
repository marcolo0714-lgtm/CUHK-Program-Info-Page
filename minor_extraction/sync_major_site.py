"""Vendor the generated major website into this project's combined site tree."""

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from .seo_config import write_discovery_files
except ImportError:
    from seo_config import write_discovery_files


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAJOR_ROOT = ROOT.parent / "CUHK_major_info"
TARGET = ROOT / "site" / "major"
VERCEL_ANALYTICS = '<script defer src="/_vercel/insights/script.js"></script>'


def _remove_readonly(function, path, _excinfo) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    function(path)


def sync_major_site(major_root: Path) -> None:
    major_root = major_root.resolve()
    generator = major_root / "major_extraction" / "generate_major_site.py"
    expected_target = (ROOT / "site" / "major").resolve()
    target = TARGET.resolve()

    if target != expected_target or target.parent != (ROOT / "site").resolve():
        raise RuntimeError(f"Refusing to replace unexpected target: {target}")
    if not generator.is_file():
        raise FileNotFoundError(f"Major site generator not found: {generator}")

    with tempfile.TemporaryDirectory(prefix="cuhk_engineering_major_") as temp_dir:
        build_root = Path(temp_dir)
        subprocess.run(
            [
                sys.executable,
                str(generator),
                "--year",
                "2026_27",
                "--faculty",
                "Engineering",
                "--output-root",
                str(build_root),
            ],
            cwd=major_root,
            check=True,
        )
        source_year = build_root / "2026_27"
        if target.exists():
            shutil.rmtree(target, onexc=_remove_readonly)
        shutil.copytree(source_year, target / "2026_27", copy_function=shutil.copyfile)

    source_favicon = major_root / "public" / "favicon.ico"
    if source_favicon.is_file():
        shutil.copy2(source_favicon, target / "favicon.ico")

    (target / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=2026_27/index.html">'
        '<title>CUHK Engineering Major Programmes</title>',
        encoding="utf-8",
    )

    for html_path in target.rglob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        cloudflare_html = html.replace(VERCEL_ANALYTICS, "")
        if cloudflare_html != html:
            html_path.write_text(cloudflare_html, encoding="utf-8")

    write_discovery_files(ROOT / "site")

    print("Synced generated major pages to site/major/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--major-root", type=Path, default=DEFAULT_MAJOR_ROOT)
    args = parser.parse_args()
    sync_major_site(args.major_root)

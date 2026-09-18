"""Compatibility wrapper for the in-repository major-site generator.

Major sources now live in ``major_extraction/`` and are generated directly
into ``site/major/``. Keep this command so existing maintenance notes and
local scripts continue to work during the transition to ``generate_all_sites.py``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from .seo_config import write_discovery_files
except ImportError:
    from seo_config import write_discovery_files


ROOT = Path(__file__).resolve().parent.parent


def generate_major_site(year: str) -> None:
    generator = ROOT / "major_extraction" / "generate_major_site.py"
    if not generator.is_file():
        raise FileNotFoundError(f"Major-site generator not found: {generator}")

    subprocess.run(
        [sys.executable, str(generator), "--year", year],
        cwd=ROOT,
        check=True,
    )
    write_discovery_files(ROOT / "site")
    print(f"Generated combined major pages in site/major/{year}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2026_27")
    args = parser.parse_args()
    generate_major_site(args.year)

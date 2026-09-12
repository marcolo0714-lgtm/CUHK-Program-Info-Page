"""Generate subject-to-dropdown-option mappings from course-info filenames."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_COURSE_INFO_DIR = ROOT / "course_info"
DEFAULT_OUTPUT = ROOT / "option_mapping.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build_option_mapping(course_info_dir):
    """Map alphabetically sorted JSON filename stems to one-based indexes."""
    subjects = sorted(
        path.stem for path in course_info_dir.glob("*.json") if path.is_file()
    )
    return {subject: index for index, subject in enumerate(subjects, start=1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--course-info-dir",
        type=Path,
        default=DEFAULT_COURSE_INFO_DIR,
        help="directory containing one JSON file per course subject",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="destination JSON file",
    )
    args = parser.parse_args()

    mapping = build_option_mapping(args.course_info_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(mapping, handle, ensure_ascii=False, indent=4)
        handle.write("\n")

    print(f"Wrote {len(mapping)} subject mappings to {args.output}")


if __name__ == "__main__":
    main()

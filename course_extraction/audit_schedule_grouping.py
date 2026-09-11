"""Audit whether flat timetable rows can be grouped by term and section.

For each course entry, rows sharing ``(term_code, section)`` are compared after
removing ``day_time`` and ``dates``.  A non-zero exit code means at least one
other field differs, so the proposed grouping invariant does not hold.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_COURSE_INFO_DIR = Path(__file__).parent / "course_info"
ALLOWED_TO_DIFFER = {"day_time", "dates"}


def audit_course_info(course_info_dir: Path):
    compared_groups = 0
    violations = []

    for json_path in sorted(course_info_dir.glob("*.json")):
        entries = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            continue

        for entry_index, course in enumerate(entries):
            if not isinstance(course, dict):
                continue
            groups = defaultdict(list)
            for row_index, row in enumerate(course.get("teaching_schedule", [])):
                if isinstance(row, dict):
                    groups[(row.get("term_code"), row.get("section"))].append(
                        (row_index, row)
                    )

            for (term_code, section), rows in groups.items():
                if len(rows) < 2:
                    continue
                compared_groups += 1
                reference_index, reference = rows[0]
                reference_common = {
                    key: value
                    for key, value in reference.items()
                    if key not in ALLOWED_TO_DIFFER
                }
                for row_index, row in rows[1:]:
                    common = {
                        key: value
                        for key, value in row.items()
                        if key not in ALLOWED_TO_DIFFER
                    }
                    differing_fields = sorted(
                        key
                        for key in reference_common.keys() | common.keys()
                        if reference_common.get(key) != common.get(key)
                    )
                    if differing_fields:
                        violations.append({
                            "file": json_path.name,
                            "course": course.get("code", f"entry #{entry_index + 1}"),
                            "course_entry": entry_index,
                            "term_code": term_code,
                            "section": section,
                            "reference_row": reference_index,
                            "row": row_index,
                            "differing_fields": differing_fields,
                        })

    return compared_groups, violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--course-info-dir",
        type=Path,
        default=DEFAULT_COURSE_INFO_DIR,
        help="Directory containing subject JSON files",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=50,
        help="Maximum number of violations to print",
    )
    args = parser.parse_args()

    compared_groups, violations = audit_course_info(args.course_info_dir)
    violating_groups = {
        (
            item["file"], item["course_entry"], item["term_code"], item["section"]
        )
        for item in violations
    }
    violating_courses = {(item["file"], item["course_entry"]) for item in violations}
    differing_field_counts = Counter(
        field
        for item in violations
        for field in item["differing_fields"]
    )
    print(f"Compared {compared_groups} term-and-section groups with multiple rows.")
    print(f"Found {len(violations)} row comparisons that differ outside day_time/dates.")
    print(
        f"Affected {len(violating_groups)} groups in "
        f"{len(violating_courses)} course entries."
    )
    if differing_field_counts:
        print(
            "Differing fields: "
            + ", ".join(
                f"{field}={count}"
                for field, count in differing_field_counts.most_common()
            )
        )
    for violation in violations[: args.show]:
        print(
            f"{violation['course']} ({violation['file']}), "
            f"term {violation['term_code']}, section {violation['section']}, "
            f"rows {violation['reference_row']} and {violation['row']}: "
            f"{', '.join(violation['differing_fields'])}"
        )
    if len(violations) > args.show:
        print(f"... {len(violations) - args.show} more violation(s) omitted")

    raise SystemExit(1 if violations else 0)


if __name__ == "__main__":
    main()

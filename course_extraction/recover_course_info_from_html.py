"""Rebuild course_info JSON from complete saved CUHK HTML captures.

The normal scraper promotes a successful capture to ``course_html/SUBJECT``.
If capture completed but publishing or JSON conversion failed, the complete
pages can remain under ``course_html/_incomplete``.  This utility audits both
locations, prefers the promoted capture, and falls back to the newest complete
archived capture for every requested subject.

Run without ``--apply`` for an audit.  With ``--apply``, only subjects that can
be reconstructed completely are written; missing subjects are reported and
leave their existing JSON untouched.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from course_extraction.get_course_info import (
        COURSE_HTML_DIR,
        COURSE_INFO_DIR,
        _publish_subject_capture,
        _write_json_atomic,
        parse_saved_subject,
    )
except ImportError:
    from get_course_info import (  # type: ignore
        COURSE_HTML_DIR,
        COURSE_INFO_DIR,
        _publish_subject_capture,
        _write_json_atomic,
        parse_saved_subject,
    )


def _manifest(path: Path) -> dict | None:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_complete_capture(path: Path, subject: str) -> bool:
    manifest = _manifest(path)
    if manifest is None or manifest.get("subject") != subject:
        return False
    courses = manifest.get("courses")
    return (
        manifest.get("complete") is True
        and isinstance(courses, list)
        and len(courses) == manifest.get("course_count")
        and all(
            isinstance(course, dict) and course.get("complete") is True
            for course in courses
        )
    )


def discover_archived_captures() -> dict[str, list[Path]]:
    """Index archived capture directories by their manifest subject."""
    captures: dict[str, list[Path]] = defaultdict(list)
    archive_root = COURSE_HTML_DIR / "_incomplete"
    if not archive_root.is_dir():
        return captures
    for path in archive_root.iterdir():
        if not path.is_dir():
            continue
        manifest = _manifest(path)
        subject = manifest.get("subject") if manifest else None
        if isinstance(subject, str) and subject:
            captures[subject].append(path)
    for paths in captures.values():
        paths.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return captures


def capture_candidates(subject: str, archived: dict[str, list[Path]]) -> list[Path]:
    """Return the promoted capture first, then newest archived captures."""
    candidates = []
    promoted = COURSE_HTML_DIR / subject
    if promoted.is_dir():
        candidates.append(promoted)
    candidates.extend(archived.get(subject, []))
    return candidates


def recover_subject(subject: str, archived: dict[str, list[Path]]):
    """Return ``(courses, source, errors)`` from the first valid full capture."""
    errors = []
    for candidate in capture_candidates(subject, archived):
        if not _is_complete_capture(candidate, subject):
            errors.append(f"{candidate}: incomplete capture")
            continue
        try:
            courses = parse_saved_subject(candidate)
        except Exception as exc:  # Report each unusable fallback and keep trying.
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
            continue
        return courses, candidate, errors
    return None, None, errors


def promote_partial_capture(
    source: Path,
    term_errors: dict[tuple[str, str], str],
):
    """Promote a capture whose only missing pages are documented term errors."""
    source = source.resolve()
    manifest = _manifest(source)
    if manifest is None:
        raise ValueError(f"missing or invalid manifest: {source}")
    subject = manifest.get("subject")
    course_count = manifest.get("course_count")
    if not isinstance(subject, str) or not isinstance(course_count, int):
        raise ValueError(f"invalid subject/course count in {source / 'manifest.json'}")

    records_by_index = {
        record.get("course_index"): record
        for record in manifest.get("courses", [])
        if isinstance(record, dict)
    }
    for course_index in range(course_count):
        directory = f"courses/{course_index:04d}"
        capture_path = source / directory / "capture.json"
        if not capture_path.is_file():
            raise ValueError(f"missing course capture: {capture_path}")
        record = json.loads(capture_path.read_text(encoding="utf-8"))
        code = record.get("code", f"course index {course_index}")
        for term in record.get("terms", []):
            schedule_page = term.get("schedule_page")
            if schedule_page and (source / directory / schedule_page).is_file():
                continue
            key = (code, str(term.get("term_code", "")))
            reason = term_errors.get(key)
            if not reason:
                raise ValueError(
                    f"{code} term {key[1]} has no saved schedule page and no "
                    "documented retrieval error"
                )
            term["retrieval_error"] = reason
        record["complete"] = True
        record["directory"] = directory
        records_by_index[course_index] = record

    if set(records_by_index) != set(range(course_count)):
        raise ValueError(f"{subject}: could not reconstruct every course record")

    recovered_manifest = {
        **manifest,
        "courses": [records_by_index[index] for index in range(course_count)],
        "complete": True,
        "complete_with_retrieval_errors": True,
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    staging = COURSE_HTML_DIR / "_incomplete" / f"{subject}_recovered_{stamp}"
    shutil.copytree(source, staging)
    try:
        for record in recovered_manifest["courses"]:
            _write_json_atomic(
                staging / record["directory"] / "capture.json", record
            )
        _write_json_atomic(staging / "manifest.json", recovered_manifest)
        courses = parse_saved_subject(staging)
        destination = COURSE_HTML_DIR / subject
        _publish_subject_capture(staging, destination)
        _write_json_atomic(COURSE_INFO_DIR / f"{subject}.json", courses)
    except Exception:
        if staging.exists():
            print(f"Recovery staging retained at {staging}")
        raise
    return subject, courses, destination


def _requested_subjects(values: list[str] | None) -> list[str]:
    if values:
        subjects = {
            item.strip().upper()
            for value in values
            for item in value.replace(",", " ").split()
            if item.strip()
        }
    else:
        subjects = {path.stem.upper() for path in COURSE_INFO_DIR.glob("*.json")}
    return sorted(subjects)


def recover_catalog(subjects: list[str], apply: bool = False) -> int:
    archived = discover_archived_captures()
    unchanged = []
    changed = []
    missing = []

    for subject in subjects:
        courses, source, errors = recover_subject(subject, archived)
        if courses is None:
            missing.append((subject, errors))
            print(f"MISSING {subject}: no complete, parseable HTML capture")
            for error in errors:
                print(f"  {error}")
            continue

        output_path = COURSE_INFO_DIR / f"{subject}.json"
        previous = None
        if output_path.is_file():
            try:
                previous = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        relative_source = source.relative_to(COURSE_HTML_DIR)
        if previous == courses:
            unchanged.append(subject)
            print(f"OK      {subject}: {len(courses)} courses from {relative_source}")
        else:
            changed.append(subject)
            action = "RECOVERED" if apply else "WOULD RECOVER"
            print(
                f"{action} {subject}: {len(courses)} courses from {relative_source}"
            )
            if apply:
                _write_json_atomic(output_path, courses)

    mode = "applied" if apply else "audit"
    print(
        f"\nRecovery {mode}: {len(unchanged)} unchanged, "
        f"{len(changed)} {'written' if apply else 'would change'}, "
        f"{len(missing)} missing."
    )
    if missing:
        print("Subjects that still require scraping: " + ", ".join(
            subject for subject, _errors in missing
        ))
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recover course_info JSON from complete saved CUHK HTML."
    )
    parser.add_argument(
        "subjects",
        nargs="*",
        help="optional subject codes, separated by spaces or commas; default: all",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write successfully reconstructed JSON files",
    )
    parser.add_argument(
        "--promote-partial",
        type=Path,
        help="promote one partial capture using documented --term-error entries",
    )
    parser.add_argument(
        "--term-error",
        action="append",
        default=[],
        metavar="'COURSE CODE:TERM_CODE=REASON'",
        help="document a CUHK term page that cannot return its section table",
    )
    args = parser.parse_args(argv)
    if args.promote_partial:
        if not args.apply:
            parser.error("--promote-partial requires --apply")
        term_errors = {}
        for value in args.term_error:
            identity, separator, reason = value.partition("=")
            course_code, colon, term_code = identity.rpartition(":")
            if not separator or not colon or not course_code.strip() or not reason.strip():
                parser.error(
                    "--term-error must use 'COURSE CODE:TERM_CODE=REASON'"
                )
            term_errors[(course_code.strip().upper(), term_code.strip())] = reason.strip()
        subject, courses, destination = promote_partial_capture(
            args.promote_partial, term_errors
        )
        print(
            f"Promoted {subject}: {len(courses)} courses recovered to {destination}"
        )
        return 0
    return recover_catalog(_requested_subjects(args.subjects), apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())

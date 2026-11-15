---
name: course-data-integrity
description: Audit a completed or interrupted CUHK course scrape using its logs, non-live tests, saved HTML, and backup JSON. Identify which courses need another capture and recover JSON from a specific archive when requested.
---

# Audit CUHK course data

Run from the repository root. Read the root `AGENTS.md` for the scraper and data layout. The maintainer runs live scraping. This workflow uses local logs and snapshots. Write recovered data only when requested.

## Reconcile the scrape logs

1. Select `course_extraction/logs/get_course_info_*.txt` for the requested run in Hong Kong time. For parallel runs, record every log included. Read the bodies separately from the repeated final error summaries.
2. Match each requested subject against `Selected major:` and `Reached the known end of ... processed offline`. A `Recovered. Selected major:` line can repeat a subject already counted. Include subject codes containing underscores, such as `EX_UG`. If an attempted subject is absent from the selection lines, check the logged input and initial setup errors before calling it unattempted. Compare each unique successful write against the current JSON and that run's manifest. Report unattempted subjects, attempted subjects without a successful write, and retry errors that ultimately recovered.
3. For an unsaved subject, inspect both `course_extraction/course_html/<SUBJECT>/manifest.json` and the run-specific `course_extraction/course_html/_incomplete/<SUBJECT>_<timestamp>/manifest.json`. Check `subject_option`, `course_count`, the subject and course `complete` flags, and any failed course state under `courses/<position>/capture.json`. A folder under `_incomplete` can hold a **complete** capture if Windows blocked its final move. Confirm by parsing the exact archive with `parse_saved_subject` from `course_extraction.get_course_info`. A successful parse checks that the referenced course, schedule, and class-detail pages can be read and agree with their recorded identities and counts.

## Run and adjudicate the non-live tests

```powershell
python -m pytest course_extraction/tests/test_course_info.py -m "not live" -q --tb=short -p no:cacheprovider
```

Keep the warnings and the final “Missing compared with course_info_copy” summary. Record pass, fail, skip, and warning counts. A missing subject JSON can make the test report every backup course as missing. A backup delta or duplicate meeting warning alone does not establish a bad scrape.

- **Backup deltas.** Compare `course_info/<SUBJECT>.json` with `course_info_copy/<SUBJECT>.json`. Match courses by `code`, terms by `term_code`, and sections by `(term_code, section, class_number)`. Locate the course via the matching run manifest. Read its `course_page` for title, units, enrolment information and available term options. Read each relevant `schedule_page` for the section identities. The scraper's `_parse_course_base_html`, `_parse_term_options_html`, and `_parse_schedule_summary_html` are available for read-only parsing. Check both additions and losses called out by the test. If a lost entry is absent from an intact, correctly identified saved page, report it as a source change. If the page shows an entry omitted from JSON, investigate offline parsing first. Missing, wrong-course, wrong-term, or failed pages leave the result unresolved.
- **Duplicate timetable warnings.** Find the exact section in the manifest by term code, section label, and class number. Inspect the referenced class-detail page's `#uc_class_gv_meet` table. Compare the multiplicity of matching `(day_time, room, instructor, dates)` rows after the scraper's whitespace normalisation. If the saved table contains the same repetitions, report them as source duplicates. If they appear only in JSON, investigate offline parsing. Check distinct class numbers before calling sections duplicates.
- **Documented retrieval gaps.** The known ELTU 1001 Term 2 gap is in term `2430` for the 2026–27 catalogue. Confirm the failed term via the log and the missing schedule file before applying that precedent. The other ELTU courses and ELTU 1001 Term 1 can still be captured successfully. If the maintainer accepts the gap, report it separately from actionable rescrapes and preserve it as an explicit retrieval error if recovering the partial subject.

## Recover authorised JSON and report the next action

Use `parse_saved_subject(explicit_archive_path)` to validate and read the capture. Verify the manifest subject and dropdown index, parse counts, and unique course codes before writing. Use the existing `_write_json_atomic` helper on `course_info/<SUBJECT>.json` and verify the saved JSON matches the parsed result. Re-run the non-live checks after writing. The generic recovery command searches the promoted snapshot first and can pick older HTML. Select the dated archive explicitly when recovering the newest run. Keep the archive as the evidence for that output.

For an authorised recovery that may retain a documented term gap, see `python course_extraction/recover_course_info_from_html.py --help` and its `--promote-partial` and `--term-error` options. This mode also updates the promoted snapshot. Check every missing page against the stated gap before using it.

Report successful writes, unsaved subjects that can be recovered offline, source-confirmed warnings, unresolved evidence, and the smallest actionable rescrape list. For each actionable entry include the course code, subject dropdown index, one-based course position if known, and affected term or section. Use `manifest.subject_option` or the actual log option first, and corroborate with `option_mapping.json`. A manifest's `course_index` is zero-based, while the log displays one-based positions. The interactive scraper accepts **subject dropdown indexes**. It cannot select an individual course by its position.

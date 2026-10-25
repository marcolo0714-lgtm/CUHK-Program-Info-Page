# CUHK Programme Information

This is the single source repository for the combined CUHK minor and major
programme website. It scrapes and validates the shared CUHK course catalogue,
extracts programme requirements, generates minor progress checkers, and builds
all static pages deployed at `https://cuhk-minor.coffeebreak.work/`.

The deployment root is always `site/`. Do not deploy `minor_extraction/`,
`major_extraction/`, or a separate `public/` directory.

## What it does

### Course info (`course_extraction/`)

1. **Capture and parse** — `get_course_info.py` navigates the CUHK course
catalogue, solves the captcha, and first saves the subject result page, every
course page, every selected-term schedule page, and every class-detail page
under `course_html/<SUBJECT>/`. Only after a complete subject capture passes
cross-page checks does the offline parser replace `course_info/<SUBJECT>.json`.
Failed or partial captures are retained under `course_html/_incomplete/` and do
not overwrite the last JSON.

2. **Validate** — `tests/` checks that scraped data is internally consistent (strictly increasing course codes, no duplicates, required fields present) and optionally re-scrapes the live website to compare counts and first/last course codes against the stored JSON.

### Minor programme info (`minor_extraction/`)

3. **Extract (academy)** — `extract_minor_sections.py` scrapes the CUHK academic programs page (captcha + Playwright) to find minor programme boxes for every UG Full-time program and saves them as raw HTML in `minor_html/{year}/`. Use `--year 2025_26` to specify the admission year.

4. **Extract (handbook)** — `extract_handbook_minors.py` scrapes the CUHK Undergraduate Student Handbook (no captcha, plain HTTP) to find additional "Other Minor Programmes" (language minors, interdisciplinary minors) and saves them as `minor_html/{year}/HB_*.html`. Use `--year` flag.

5. **Parse to JSON** — `generate_minor_json.py` parses each minor HTML into structured JSON (`minor_json/{year}/`) with course codes, units, and explanatory notes. Sets `_auto_generated: true` on each file. Use `--year` flag.

6. **Resolve course descriptions** — `resolve_course_descriptions.py` scans all minor JSONs for text-only requirements (e.g., "18 units of MATH courses at 3000+" or "Any two LAWS courses at 3000 or above") and resolves them against the course catalog to generate concrete course code lists in `course_overrides/{year}.json`. Run without flags for a diagnostic report; run with `--apply --year 2025_26` to write the file.

7. **Manually complete overrides** — `course_overrides/{year}.json` maps each minor's text-only requirement rows to a list of course codes. Entries the script cannot auto-resolve (e.g., "2 Art History Courses", "Cultural Management Area") are placed as empty arrays — edit these manually, then re-run the site generator.

8. **Generate site** — `generate_minor_site.py` reads `minor_json/{year}/*.json` and `course_overrides/{year}.json`, resolves every course code against the catalog to attach titles/units/prerequisites, and renders a polished static site with collapsible course tables in `site/{year}/`. Use `--year` flag.

9. **Checker page** — `generate_checker_page.py` and `generate_checker_data.py` build a self-contained interactive checker (`site/{year}/checker.html`) that lets students paste their CUSIS transcript and see their progress toward every minor, including equivalence rules, cross-row exclusions, waiver rules, faculty caps, and level constraints — all auto-detected from explanatory notes.

The checker output also drives `minor_course_index.py`, which builds the
course-to-minor links shown in every course information table. This ensures the
“Also in minor” column uses the same resolved overrides and explanatory-note
equivalences as the checker. On major pages, minors explicitly unavailable to
the current major (including faculty-wide restrictions) are filtered out.

### Major programme info (`major_extraction/`)

10. **Capture major programme pages** — `extract_major_pages.py` solves the
programme-site CAPTCHA and saves the complete official page plus a smaller
requirement-table copy under `major_html/{year}/`. Existing complete pages are
reused, making an interrupted crawl resumable.

11. **Parse majors to JSON** — `generate_major_json.py`, together with
`major_readability.py`, parses the saved full pages into structured JSON under
`major_json/{year}/`. Programme-specific repairs are implemented in Python so
the complete output is reproducible. Major JSON normally must not be edited by
hand; see `major_extraction/MANUAL_EDITS.md`.

12. **Generate major pages** — `generate_major_site.py` resolves course codes
against the same `course_extraction/course_info/` used by minor pages and writes
the complete major catalogue directly to `site/major/{year}/`. There is no
second course catalogue and no sibling repository synchronization step.

13. **Search metadata and discovery** — `seo_config.py` defines the production
origin (`https://cuhk-minor.coffeebreak.work`) and supplies canonical URLs,
descriptions, Open Graph tags, and structured data to the generated pages. Site
generation also refreshes `site/sitemap.xml`, `site/robots.txt`, and the
Cloudflare Pages `site/_redirects` rules.

14. **Unified build** — root-level `generate_all_sites.py` regenerates checker
data, checker pages, minor pages, every available major year, and the final SEO
discovery files. It then checks major page counts, all internal links, and the
syntax of generated inline JavaScript.

## Quick start

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

Node.js must be available when running `generate_all_sites.py`, because the
final verification step compiles generated inline JavaScript. The generators
themselves are Python programs.

### Generate the complete hosted website

From the repository root:

```powershell
python generate_all_sites.py
```

After refreshing course schedules, also update the footer date on all pages:

```powershell
python generate_all_sites.py --update-course-schedule-date
```

This saves the current Hong Kong date for all page generators. Subsequent builds
without the flag retain that date. The flag requires a full build and cannot be
combined with admission-year filters. It changes the displayed freshness date;
it does not scrape or certify that every schedule was retrieved.

This is the normal command after course information or either programme
generator changes. It regenerates every minor year and every year present under
`major_extraction/major_json/`, refreshes the sitemap/redirects last, and runs
the generated-site checks. Deploy the resulting `site/` directory.

Useful variants:

```powershell
# Limit the build to selected admission years.
python generate_all_sites.py --minor-year 2026_27 --major-year 2026_27

# Reparse saved major source HTML before building the site.
python generate_all_sites.py --rebuild-major-json

# Generate without final link/page-count/JavaScript checks.
python generate_all_sites.py --skip-verify
```

`--minor-year` and `--major-year` are repeatable. Without them, all locally
available years are generated.

### 1. Scrape and validate course catalog

```bash
cd course_extraction
python get_course_info.py
python get_course_info.py --process-saved MATH ENGG  # rebuild selected JSON without browsing
python get_course_info.py --process-saved            # rebuild all complete saved subjects
python recover_course_info_from_html.py              # audit promoted + archived captures
python recover_course_info_from_html.py --apply       # recover every reconstructable subject
pytest tests/ -m "not live"       # offline: code ordering, duplicates, required fields
pytest tests/ -m live              # online: compare stored vs live website
pytest tests/ -m live --course-options "1-50, 101-150"  # online: selected dropdown options
```

Every `get_course_info.py` run mirrors its terminal transcript to a timestamped
UTF-8 text file under `course_extraction/logs/`. The log is finalized and its
path is printed when the run completes, fails, or is stopped with Ctrl+C.

For long or background scrapes, use `python get_course_info.py --headless`.
This avoids relying on visible browser windows. Start with one or two concurrent
scrapers; the eight simultaneous runs in the October 19 logs experienced many
browser-operation timeouts. The scraper now waits for completed page responses
and explicit CAPTCHA results, backs off before recovery, and stops cleanly if
the browser disconnects. Temporary snapshot-file locks are retried for up to
about 31 seconds before the incomplete capture is retained.

If a course still fails after three recovery retries, the scraper skips it and
reopens the subject's course list to continue with the next course. Restoring
that list has a separate limit of three attempts; if all fail, the remaining
courses in that subject cannot be reached. A subject with skipped courses stays
under `course_html/_incomplete/` and does not replace its existing JSON.

Without `--course-options`, the live test checks every selectable course-subject option. The flag accepts individual option numbers, commas, spaces, and inclusive ranges using the same syntax as the scraper.

`tests/test_course_info.py` is the only course test module; `conftest.py` and
`__init__.py` provide test configuration and package setup. Offline tests check
the stored JSON's internal consistency, not whether a run fetched every page.
Confirm scrape completeness separately from the latest logs and capture
manifests, including any recorded `retrieval_error`. The optional live test
compares course counts and first/last codes, not every section's contents.

### 2. Scrape minor programmes

```bash
cd ..\minor_extraction
python extract_minor_sections.py --year 2025_26    # academy minors → minor_html/{year}/
python extract_handbook_minors.py --year 2025_26   # handbook minors → minor_html/{year}/HB_*.html
```

### 3. Parse minors to JSON

```bash
python generate_minor_json.py --year 2025_26       # HTML → minor_json/{year}/
```

### 4. Resolve text-only requirements

```bash
python resolve_course_descriptions.py                          # diagnostic: see what's resolvable
python resolve_course_descriptions.py --apply --year 2025_26   # generate course_overrides/{year}.json
# edit course_overrides/{year}.json to fill any MANUAL entries (empty arrays)
```

### 5. Generate site and checker

```bash
python ..\minor_planner\generate_checker_data.py --year 2025_26
python ..\minor_planner\generate_checker_page.py --year 2025_26
python generate_minor_site.py --year 2025_26                    # static site → site/{year}/
cd ..
python major_extraction\generate_major_site.py --year 2026_27   # major site → site/major/{year}/
```

> **Note:** The site auto-reads `course_overrides/{year}.json` if present and injects course tables for resolved text-only rows. If the file is missing, the site still works — just without those tables.

### 6. Update major programme requirements

The current saved official pages are committed, so parser and presentation
work does not require live access:

```powershell
# Optional live crawl. This requires Playwright, Chromium and CAPTCHA solving.
python major_extraction\extract_major_pages.py --year 2026_27 --headless

# Reparse saved full pages and regenerate all major JSON, including ELITE/STAR.
python major_extraction\generate_major_json.py --year 2026_27

# Run major parser/readability tests.
python -m pytest major_extraction\tests

# Generate major HTML only.
python major_extraction\generate_major_site.py --year 2026_27
```

The 87 captured programmes produce 89 JSON/page records because the Engineering
ELITE Stream and Science STAR Stream are generated as standalone entries.
`major_extraction/major_html/{year}/full_pages/` is the authoritative raw
programme snapshot. The smaller HTML copies beside it are retained for auditing.

### Shared course-data rule

`course_extraction/course_info/` is the only course catalogue. Both minor and
major generators read it directly. Never copy course JSON into
`major_extraction/` and do not maintain a second major-repository copy. After a
course re-scrape passes the offline/live tests, run `python generate_all_sites.py`.

`minor_extraction/sync_major_site.py` remains only as a compatibility wrapper.
It now invokes the local major generator and refreshes discovery files; it no
longer reads or modifies a sibling repository.

## Structure

```
├── course_extraction/
│   ├── get_course_info.py              # Main course scraper
│   ├── recover_course_info_from_html.py # Recover JSON from promoted/archived HTML
│   ├── course_html/                    # Auditable raw course/term/class pages
│   ├── course_info/                    # Scraped JSON output (one file per subject)
│   └── tests/
│       ├── test_course_info.py         # Offline + live validation tests
│       └── conftest.py                 # Pytest markers
├── minor_extraction/
│   ├── extract_minor_sections.py       # Academy minor scraper (Playwright + captcha)
│   ├── extract_handbook_minors.py      # Handbook minor scraper (plain HTTP, no captcha)
│   ├── generate_minor_json.py          # HTML → JSON parser
│   ├── generate_minor_site.py          # JSON → HTML static site generator
│   ├── minor_course_index.py           # Checker data → course-to-minor lookup
│   ├── resolve_course_descriptions.py  # Override diagnostic / generator
│   ├── course_overrides/               # Per-year course resolution maps
│   │   └── {year}.json
│   ├── minor_html/                     # Raw extracted minor HTML (per year)
│   │   └── {year}/
│   │       └── _faculties.json          # Faculty name mapping
│   ├── minor_json/                     # Structured minor JSON (per year)
│   │   └── {year}/
├── minor_planner/                      # Checker pipeline
│   ├── generate_checker_data.py        # Builds resolved checker data
│   └── generate_checker_page.py        # Generates interactive checker.html
├── major_extraction/                   # Complete major-programme pipeline
│   ├── extract_major_pages.py          # Live programme scraper
│   ├── generate_major_json.py          # Saved HTML → structured JSON
│   ├── major_readability.py            # General and programme-specific cleanup
│   ├── generate_major_site.py          # Major JSON → site/major/
│   ├── MANUAL_EDITS.md                 # Major JSON manual-edit policy/history
│   ├── major_html/
│   │   └── {year}/
│   │       ├── _programme_rows.json
│   │       ├── _programmes.json
│   │       └── full_pages/             # Authoritative official source pages
│   ├── major_json/
│   │   └── {year}/                     # Structured major data
│   └── tests/                          # Parser/readability regression tests
├── site/                               # Generated static site
│   ├── index.html                      # Redirects to newest year
│   ├── checker_data.json               # Course catalog (year-agnostic)
│   ├── sitemap.xml, robots.txt, _redirects
│   ├── {year}/
│   │   ├── index.html                  # Minor programme list
│   │   ├── checker.html                # Interactive checker
│   │   └── minors/                     # Detail pages
│   └── major/
│       ├── index.html                  # Redirects to newest major year
│       └── {year}/
│           ├── index.html              # Complete major programme list
│           └── majors/                 # Major detail pages
├── site_tempdata/                      # Intermediate checker data (per year)
│   └── checker_minors_{year}.json
├── generate_all_sites.py               # Recommended complete build command
├── requirements.txt                    # Python dependencies
└── user_data_dir/                      # Playwright persistent browser profile
```

### Script roles at a glance

| Script | Input | Output |
|--------|-------|--------|
| `get_course_info.py` | CUHK catalog website | `course_html/<SUBJECT>/` then `course_info/*.json` (270 files) |
| `recover_course_info_from_html.py` | Complete promoted/archived HTML captures | Reconstructed `course_info/*.json` |
| `extract_minor_sections.py` | CUHK academy programs | `minor_html/<name>.html` (59 files) |
| `extract_handbook_minors.py` | CUHK student handbook | `minor_html/HB_<name>.html` (12 files) |
| `generate_minor_json.py` | `minor_html/*.html` | `minor_json/*.json` (71 files) |
| `resolve_course_descriptions.py` | `minor_json/` + `course_info/` | `course_overrides.json` |
| `generate_minor_site.py` | `minor_json/` + `course_info/` + `course_overrides.json` | `site/` (static HTML) |
| `minor_course_index.py` | Generated checker-minor data | Course-to-minor links and major applicability filtering |
| `generate_checker_data.py` | `minor_json/` + `course_info/` + per-year overrides | `site/checker_data.json` + `site_tempdata/checker_minors_{year}.json` |
| `generate_checker_page.py` | Shared checker data + per-year checker-minor data | `site/{year}/checker.html` |
| `extract_major_pages.py` | CUHK programme website | `major_html/{year}/` |
| `generate_major_json.py` | Saved complete major pages | `major_json/{year}/*.json` |
| `generate_major_site.py` | `major_json/` + shared `course_info/` | `site/major/{year}/` |
| `generate_all_sites.py` | All current JSON and generator sources | Complete verified `site/` deployment |

## Deployment

The only public artifact is `site/`. For Cloudflare Pages, set the build output
directory to `site`. The usual workflow is to build and verify locally, commit
the generated files, and let Cloudflare publish that directory without running
the scrapers:

```powershell
python generate_all_sites.py
git status
# Review the generated changes, then commit/push only when intended.
```

The root URL redirects to the newest minor index. `/major` redirects to the
newest major index. `site/sitemap.xml` contains both catalogues and must always
be regenerated after the major pages, which the unified build handles.

The old standalone `CUHK_major_info` repository is no longer needed for builds.
Keep it temporarily as a migration backup until the combined repository has
been reviewed and deployed successfully; future edits belong here.

## Scraped data format

### Course catalog (`course_info/<MAJOR>.json`)

Each file is an array of objects:

```json
{
    "code":  "ACCT 2111",
    "title": "Introductory Financial Accounting",
    "unit":  "3.00",
    "info":  "Not for students who have taken ACCT1111",
    "term_1": true,
    "term_2": false,
    "term_offerings": [
        {"term_code": "2420", "term": "2026-27 Term 1", "offered": true}
    ],
    "sections": [
        {
            "term_code": "2420",
            "term": "2026-27 Term 1",
            "section": "A-LEC",
            "component_type": "LEC",
            "class_number": "9700",
            "status": "Open",
            "class_capacity": "100",
            "wait_list_capacity": "0",
            "enrollment_total": "90",
            "wait_list_total": "0",
            "available_seats": "10",
            "timetable": [
                {"day_time": "Mo 12:30PM - 2:15PM", "room": "Room A", "instructor": "Prof. One", "dates": "7/9 - 12/10"}
            ]
        }
    ]
}
```

The `info` field is only present when the course has enrollment requirements or restrictions. `term_1`/`term_2` are derived from section `term` labels containing an academic year followed by `Term 1`/`Term 2` (for example, `2026-27 Term 1`). Each term/section has one section object, and its meeting rows are stored in `timetable`.

### Minor programme (`minor_json/<Programme>.json`)

Each file is a structured object describing a minor programme's requirements:

```json
{
  "_auto_generated": true,
  "title": "Mathematics",
  "faculty": "Science",
  "source_file": "Mathematics",
  "description": "Students are required to complete a minimum of 18 units...",
  "required": {
    "label": "1. Required Courses: 6 units",
    "units": "6",
    "rows": [
      { "text": "MATH2010, 2020", "codes": ["MATH 2010", "MATH 2020"], "units": "" }
    ]
  },
  "elective": { "... same structure as required ..." },
  "explanatory_notes": "<table>...</table>",
  "eq_pairs": [["MATH 1010", "MATH 1018"]]
}
```

- `rows[].codes` — may be empty (`[]`) if the requirement is written as prose (e.g., "18 units of MATH courses at 3000+") rather than as specific course codes.
- `_auto_generated` — set to `false` after manual edits to the JSON to prevent `generate_minor_json.py` from overwriting your changes.

### Course override (`course_overrides.json`)

Maps text-only requirement rows to concrete course code lists, resolved from the course catalog:

```json
{
  "Mathematics": {
    "18 units of MATH courses, out of which at least 6 units of courses are at 3000 to 5000 level": [
      "MATH 3020", "MATH 3030", "MATH 3040", "..."
    ]
  },
  "Fine_Arts": {
    "(b) 2 Art History Courses[a]": [],
    "(c) 2 Studio Art Courses[a]": []
  }
}
```

- Top-level keys are `source_file` stems matching minor JSON filenames.
- Second-level keys are exact row `text` strings.
- Values are lists of course codes in `"DEPT XXXX"` format.
- Empty arrays `[]` mark MANUAL entries that need human input.

## Course Override Mechanism

### Why it exists

Many minor programme requirements are written as prose descriptions rather than specific course lists. For example, the Mathematics minor says:

> "18 units of MATH courses, out of which at least 6 units of courses are at 3000 to 5000 level"

The HTML parser stores this as a row with `"codes": []`, so the generated site shows only the text — no collapsible course table.

The override mechanism bridges this gap by mapping these text descriptions to concrete course code lists resolved from `course_info/`. The site generator then displays a collapsible course table directly below the text.

### Auto-resolution

`resolve_course_descriptions.py` handles these patterns automatically:

| Pattern | Example | Resolution |
|---------|---------|------------|
| Subject + level filter | `"ECON course at 3000 or above level"` | All ECON 3xxx+ courses |
| Subject + exclusions | `"Any TRAN courses excluding TRAN1000"` | All TRAN courses minus TRAN 1000 |
| "Any X courses" + level | `"Any two LAWS courses at 3000+"` | All LAWS 3xxx+ courses |
| Multi-subject + level | `"ACCT/DOTE/FINA/HTMG/MGNT/MKTG at 3000+"` | Combined across 6 departments |
| Partial codes present | `"Any TRAN courses excluding TRAN1000"` where codes only has `["TRAN 1000"]` | Computes the complement |

The script also distinguishes hard level filters ("ECON course **at** 3000 or above") from selection guidelines ("GPAD courses, **with at least** two at 3000 or above") — only the former restricts which courses are included in the list.

### Manual entries

These patterns cannot be auto-resolved and appear as empty arrays in `course_overrides.json`:

- **Area concepts:** `"from Cultural Studies Area(s)"`, `"from the Religious Studies Areas"` — CUHK groups courses into named areas that aren't encoded in the course catalog.
- **Named groups:** `"Art History Courses"`, `"Studio Art Courses"` — courses belonging to these groups are defined by department convention.
- **Conceptual categories:** `"Cultural Management Area"` — similar to areas above.

To fix these, open `course_overrides.json`, find the empty `[]` entries, and replace them with the appropriate course code lists.

### Workflow

```bash
# 1. See what can be resolved
python resolve_course_descriptions.py

# 2. Generate the override file
python resolve_course_descriptions.py --apply

# 3. Fill any [] entries in course_overrides.json manually

# 4. Rebuild the site
python generate_minor_site.py
```

## Contributing

### Updating course data

```bash
cd course_extraction
python get_course_info.py               # re-scrape the latest catalog
python get_course_info.py --process-saved MATH  # reparse an existing raw capture
pytest tests/ -m "not live"             # verify integrity
cd ..\minor_extraction
python resolve_course_descriptions.py --apply   # refresh overrides with new course lists
cd ..
python generate_all_sites.py                    # rebuild and verify minors + majors
```

### Adding missing courses to the catalog

The course scraper covers most CUHK courses, but some courses referenced in minor
programme descriptions may not appear on the scraped catalog page (e.g., special-topics
courses, newly introduced courses, or courses listed under unusual subject codes).
The generated site marks these as *(not found in course_info)* in orange.

To fix a missing-course entry:

1. **Find the course details** — look up the course on the [CUHK course catalog](https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/tt_dsp_crse_catalog.aspx) or the department website for its title, units, and prerequisites.

2. **Edit the correct JSON file** — open `course_extraction/course_info/<DEPT>.json` (where `<DEPT>` is the 4-letter subject code, e.g., `CURE.json`).

3. **Insert the entry in numeric order** — courses must be stored in ascending order by course number. Find the right position and add an object with these fields:
   ```json
   {
       "code":  "DEPT 1234",
       "title": "Course Title",
       "unit":  "3.00",
       "info":  "Prerequisite: DEPT 1000."
   }
   ```
   - `code` — must be `"DEPT XXXX"` format (space-separated, 4-digit number).
   - `unit` — must be a string like `"3.00"` or `"1.00"`.
   - `info` — optional. Omit the field entirely if the course has no restrictions.

4. **Verify with tests** — run `pytest tests/ -m "not live"` to confirm the course codes are still strictly increasing and the format is valid.

5. **Rebuild** — re-run `python generate_minor_site.py` and confirm the entry no longer shows *(not found)*.


### Future directions

- **Course offering calendar** — ~~add a column to each course info table showing whether the course is offered in Term 1, Term 2, or Summer for the current academic year~~ ✅ Done — T1/T2 columns with green highlights are shown in course tables on the info page.
- **Transcript upload / minor planner** — upload your CUSIS transcript and see which minors you're closest to completing, taking double-counting rules into account. ✅ Done — see `site/checker.html`.
- **Search & filter** — add keyword search and level-range filtering to the minor programme pages to quickly find courses matching specific criteria.
- **Dark mode** — add a theme toggle to the generated site.

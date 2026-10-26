# CUHK Programme Information

This is the single source repository for the combined CUHK minor and major
programme website. It scrapes and validates the shared CUHK course catalogue,
extracts programme requirements, generates minor progress checkers, and builds
all static pages deployed at `https://cuhk-minor.coffeebreak.work/`.

The deployment root is always `site/`. Do not deploy `minor_extraction/`,
`major_extraction/`, or a separate `public/` directory.

## Build and deployment

The repository has four stages that share one course catalogue:

| Stage | Source | Generated output |
|---|---|---|
| Courses | CUHK course catalogue | `course_extraction/course_html/` and `course_extraction/course_info/` |
| Minors | Academy and handbook pages | `minor_extraction/minor_html/{year}/`, `minor_extraction/minor_json/{year}/`, and `minor_extraction/course_overrides/{year}.json` |
| Majors | Programme handbook pages | `major_extraction/major_html/{year}/` and `major_extraction/major_json/{year}/` |
| Website | All structured data | Verified static files under `site/` |

`course_extraction/course_info/` is the only course catalogue used by both
minor and major generators. Checker data also supplies “Also in minor” links
and major-specific minor availability filtering.

### Standard workflow

1. Install the Python dependencies and Playwright browser:

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

   Node.js is also required for the generated JavaScript syntax check.

2. Refresh course, minor, or major source data when needed by following the
   corresponding sections below. Skip this step when rebuilding from existing
   data.

3. From the repository root, generate and verify the complete website:

   ```powershell
   python -m site_generator.generate_all_sites
   ```

   This regenerates all available years, checker pages, metadata,
   `sitemap.xml`, and redirects, then verifies page counts, links, and inline
   JavaScript.

4. If course schedules were refreshed, rebuild once with the current Hong Kong
   date in every page footer:

   ```powershell
   python -m site_generator.generate_all_sites --update-course-schedule-date
   ```

   This updates the persisted display date; it does not scrape or certify the
   schedule data.

5. Deploy only `site/` to Vercel or Cloudflare Pages. The root minor and
   `/major` URLs redirect to their newest available admission years.

Build variants:

```powershell
# Limit the build to selected admission years.
python -m site_generator.generate_all_sites --minor-year 2026_27 --major-year 2026_27

# Reparse saved major source HTML before building the site.
python -m site_generator.generate_all_sites --rebuild-major-json

# Generate without final link/page-count/JavaScript checks.
python -m site_generator.generate_all_sites --skip-verify
```

`--minor-year` and `--major-year` are repeatable. `--skip-verify` is intended
for local iteration, not deployment.

### Refresh course data

```bash
cd course_extraction
python get_course_info.py
python get_course_info.py --process-saved MATH ENGG  # rebuild selected JSON without browsing
python get_course_info.py --process-saved            # rebuild all complete saved subjects
python recover_course_info_from_html.py --apply      # recover reconstructable captures
pytest tests/ -m "not live"                          # stored-data integrity
pytest tests/ -m live                                 # optional live comparison
```

Every `get_course_info.py` run mirrors its terminal transcript to a timestamped
UTF-8 file under `course_extraction/logs/`, including interrupted runs. Complete
raw snapshots are promoted under `course_html/<SUBJECT>/`; incomplete captures
remain under `course_html/_incomplete/` and never replace existing JSON. Use
`--headless` for background scraping and keep concurrency low to reduce browser
timeouts. Offline tests validate stored structure; live tests compare catalogue
counts and boundary codes, not every section field.

### Refresh minor data

```powershell
python minor_extraction\extract_minor_sections.py --year 2025_26
python minor_extraction\extract_handbook_minors.py --year 2025_26
python minor_extraction\generate_minor_json.py --year 2025_26
python minor_extraction\resolve_course_descriptions.py --year 2025_26
python minor_extraction\resolve_course_descriptions.py --apply --year 2025_26
```

The first resolver command is diagnostic; `--apply` writes a complete override
file. It refuses to overwrite the file if any requirement remains unresolved.
Run the unified build afterward.

### Refresh major data

The current saved official pages are committed, so parser and presentation
work does not require live access:

```powershell
# Optional live crawl. This requires Playwright, Chromium and CAPTCHA solving.
python major_extraction\extract_major_pages.py --year 2026_27 --headless

# Reparse saved full pages and regenerate all major JSON, including ELITE/STAR.
python major_extraction\generate_major_json.py --year 2026_27

# Run major parser/readability tests.
python -m pytest major_extraction\tests
```

The 87 captured programmes produce 89 JSON/page records because the Engineering
ELITE Stream and Science STAR Stream are generated as standalone entries.
`major_extraction/major_html/{year}/full_pages/` is the authoritative raw
programme snapshot. Run the unified build after regeneration.

## Repository structure

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
│   ├── resolve_course_descriptions.py  # Override diagnostic / generator
│   ├── course_overrides/               # Per-year course resolution maps
│   │   └── {year}.json
│   ├── minor_html/                     # Raw extracted minor HTML (per year)
│   │   └── {year}/
│   │       └── _faculties.json          # Faculty name mapping
│   ├── minor_json/                     # Structured minor JSON (per year)
│   │   └── {year}/
├── minor_planner/                      # Checker pipeline
│   └── generate_checker_data.py        # Builds resolved checker data
├── major_extraction/                   # Complete major-programme pipeline
│   ├── extract_major_pages.py          # Live programme scraper
│   ├── generate_major_json.py          # Saved HTML → structured JSON
│   ├── major_readability.py            # General and programme-specific cleanup
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
├── site_generator/                     # Static-site rendering and verification
│   ├── generate_all_sites.py           # Recommended complete build command
│   ├── generate_minor_site.py          # Minor JSON → site/{year}/
│   ├── generate_checker_page.py        # Checker data → interactive checker page
│   ├── generate_major_site.py          # Major JSON → site/major/{year}/
│   ├── minor_course_index.py           # Course-to-minor membership lookup
│   ├── site_metadata.py                # SEO, discovery, and schedule-date helpers
│   ├── course_schedule_updated_on.txt  # Persisted schedule footer date
│   └── site_tempdata/                  # Intermediate checker data (per year)
│       └── checker_minors_{year}.json
└── requirements.txt                    # Python dependencies
```

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

### Course override (`minor_extraction/course_overrides/{year}.json`)

Overrides map an exact prose requirement to the eligible courses displayed by
the site and consumed by the checker:

```json
{
  "Fine_Arts": {
    "(b) Two Art History Courses[a]": [
      "FAAS 2100", "FAAS 2101", "FAAS 2102"
    ]
  }
}
```

Top-level keys match each minor's `source_file`; second-level keys match row
text exactly. Entries may also preserve published equivalences such as
`CURE2403 [#CUMT2003]`.

## Course override mechanism

Minor requirements often describe eligible courses in prose instead of listing
codes. `resolve_course_descriptions.py` generates the per-year override file
from two authoritative sources:

- `course_info/` supplies subject, level, range, and exclusion-based lists.
- Same-year saved major handbook pages supply named areas and groups, including
  Cultural Studies, Cultural Management, Religious Studies, Chinese Basic and
  Speciality courses, and Fine Arts history/studio courses.

The resolver distinguishes hard filters (“courses at 3000 or above”) from
selection constraints (“with at least two courses at 3000 or above”), retains
bracketed equivalences, and sorts output deterministically. It does not require
manual JSON completion. If a known source is missing or any row remains
`MANUAL` or `PARTIAL`, `--apply` stops without overwriting the existing file.

Run from the repository root:

```powershell
# Inspect the resolution report.
python minor_extraction\resolve_course_descriptions.py --year 2025_26

# Write a complete override file, then rebuild everything.
python minor_extraction\resolve_course_descriptions.py --apply --year 2025_26
python -m site_generator.generate_all_sites
```

When CUHK introduces a new prose pattern, update the resolver or the shared
source parser rather than editing `course_overrides/{year}.json` manually.

## Future directions

- **Unified search and filters** — search courses, minors, and majors by title,
  subject, level, term availability, faculty, and requirement type.
- **Dark mode and accessibility review** — add theme preferences and audit
  keyboard navigation, contrast, landmarks, and screen-reader labels.
- **Year-to-year change reports** — summarize added, removed, and modified
  courses and programme requirements between admission years.
- **Automated scrape and build** — automate data scraping and updating of the  
  website before course registration periods
- **AI timetable planner** — add a page to assist users in planning courses
  to register based on his/her major, preferred minor, interested topics, etc.

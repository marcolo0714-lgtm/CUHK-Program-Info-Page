# CUHK Major Course Info

Scrapes and validates course catalog data from the Chinese University of Hong Kong (CUHK) for every subject/major. Also extracts minor programme information, resolves text-only course requirements against the catalog, and generates a browsable static site with interactive course tables.

## What it does

### Course info (`course_extraction/`)

1. **Scrape** — `get_course_info.py` navigates the CUHK course catalog page, selects each major from the dropdown, solves the captcha via OCR (`ddddocr`), and scrapes every course's code, title, units, and enrollment requirements into `course_info/<MAJOR>.json`.

2. **Validate** — `tests/` checks that scraped data is internally consistent (strictly increasing course codes, no duplicates, required fields present) and optionally re-scrapes the live website to compare counts and first/last course codes against the stored JSON.

### Minor programme info (`minor_extraction/`)

3. **Extract (academy)** — `extract_minor_sections.py` scrapes the CUHK academic programs page (captcha + Playwright) to find minor programme boxes for every UG Full-time program and saves them as raw HTML in `minor_html/{year}/`. Use `--year 2025_26` to specify the admission year.

4. **Extract (handbook)** — `extract_handbook_minors.py` scrapes the CUHK Undergraduate Student Handbook (no captcha, plain HTTP) to find additional "Other Minor Programmes" (language minors, interdisciplinary minors) and saves them as `minor_html/{year}/HB_*.html`. Use `--year` flag.

5. **Parse to JSON** — `generate_minor_json.py` parses each minor HTML into structured JSON (`minor_json/{year}/`) with course codes, units, and explanatory notes. Sets `_auto_generated: true` on each file. Use `--year` flag.

6. **Resolve course descriptions** — `resolve_course_descriptions.py` scans all minor JSONs for text-only requirements (e.g., "18 units of MATH courses at 3000+" or "Any two LAWS courses at 3000 or above") and resolves them against the course catalog to generate concrete course code lists in `course_overrides/{year}.json`. Run without flags for a diagnostic report; run with `--apply --year 2025_26` to write the file.

7. **Manually complete overrides** — `course_overrides/{year}.json` maps each minor's text-only requirement rows to a list of course codes. Entries the script cannot auto-resolve (e.g., "2 Art History Courses", "Cultural Management Area") are placed as empty arrays — edit these manually, then re-run the site generator.

8. **Generate site** — `generate_minor_site.py` reads `minor_json/{year}/*.json` and `course_overrides/{year}.json`, resolves every course code against the catalog to attach titles/units/prerequisites, and renders a polished static site with collapsible course tables in `site/{year}/`. Use `--year` flag.

9. **Checker page** — `generate_checker_page.py` and `generate_checker_data.py` build a self-contained interactive checker (`site/{year}/checker.html`) that lets students paste their CUSIS transcript and see their progress toward every minor, including equivalence rules, cross-row exclusions, waiver rules, faculty caps, and level constraints — all auto-detected from explanatory notes.

10. **Combined major/minor site** — `sync_major_site.py` copies the generated
major pages from the sibling `CUHK_major_info/public/2026_27/` directory into
`site/major/2026_27/`. The site root redirects to the latest minor index, and
the minor and Engineering-major indexes link to each other.

11. **Search metadata and discovery** — `seo_config.py` defines the production
origin (`https://cuhk-minor.coffeebreak.work`) and supplies canonical URLs,
descriptions, Open Graph tags, and structured data to the generated pages. Site
generation also refreshes `site/sitemap.xml`, `site/robots.txt`, and the
Cloudflare Pages `site/_redirects` rules.

## Quick start

### Install

```bash
pip install playwright ddddocr pytest beautifulsoup4 requests
playwright install chromium
```

### 1. Scrape and validate course catalog

```bash
cd course_extraction
python get_course_info.py
pytest tests/ -m "not live"       # offline: code ordering, duplicates, required fields
pytest tests/ -m live              # online: compare stored vs live website
```

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
python sync_major_site.py                                       # major site → site/major/
```

> **Note:** The site auto-reads `course_overrides/{year}.json` if present and injects course tables for resolved text-only rows. If the file is missing, the site still works — just without those tables.

## Structure

```
├── course_extraction/
│   ├── get_course_info.py              # Main course scraper
│   ├── course_info/                    # Scraped JSON output (one file per major)
│   └── tests/
│       ├── test_course_info.py         # Offline + live validation tests
│       └── conftest.py                 # Pytest markers
├── minor_extraction/
│   ├── extract_minor_sections.py       # Academy minor scraper (Playwright + captcha)
│   ├── extract_handbook_minors.py      # Handbook minor scraper (plain HTTP, no captcha)
│   ├── generate_minor_json.py          # HTML → JSON parser
│   ├── generate_minor_site.py          # JSON → HTML static site generator
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
├── site/                               # Generated static site
│   ├── index.html                      # Redirects to newest year
│   ├── checker_data.json               # Course catalog (year-agnostic)
│   └── {year}/
│       ├── index.html                  # Minor programme list
│       ├── checker.html                # Interactive checker
│       └── minors/                     # Detail pages
├── site_tempdata/                      # Intermediate checker data (per year)
│   └── checker_minors_{year}.json
└── user_data_dir/                      # Playwright persistent browser profile
```

### Script roles at a glance

| Script | Input | Output |
|--------|-------|--------|
| `get_course_info.py` | CUHK catalog website | `course_info/*.json` (235 files) |
| `extract_minor_sections.py` | CUHK academy programs | `minor_html/<name>.html` (59 files) |
| `extract_handbook_minors.py` | CUHK student handbook | `minor_html/HB_<name>.html` (12 files) |
| `generate_minor_json.py` | `minor_html/*.html` | `minor_json/*.json` (71 files) |
| `resolve_course_descriptions.py` | `minor_json/` + `course_info/` | `course_overrides.json` |
| `generate_minor_site.py` | `minor_json/` + `course_info/` + `course_overrides.json` | `site/` (static HTML) |
| `generate_checker_data.py` | `minor_json/` + `course_info/` + `course_overrides.json` | `site/data/checker_data.json` |
| `generate_checker_page.py` | `site/data/checker_data.json` | `site/checker.html` |

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
    "term_2": false
}
```

The `info` field is only present when the course has enrollment requirements or restrictions. `term_1`/`term_2` indicate 2026-27 Term 1/2 availability.

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
pytest tests/ -m "not live"             # verify integrity
cd ..\minor_extraction
python resolve_course_descriptions.py --apply   # refresh overrides with new course lists
python generate_minor_site.py                   # rebuild the site
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

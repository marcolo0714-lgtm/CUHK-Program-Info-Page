# CUHK Major Course Info

Scrapes and validates course catalog data from the Chinese University of Hong Kong (CUHK) for every subject/major.  Also extracts minor programme information and generates a browsable static site.

## What it does

### Course info (`course_extraction/`)

1. **Scrape** — `get_course_info.py` navigates the CUHK course catalog page, selects each major from the dropdown, solves the captcha via OCR (`ddddocr`), and scrapes every course's code, title, units, and enrollment requirements into `course_info/<MAJOR>.json`.

2. **Validate** — `tests/` checks that scraped data is internally consistent (strictly increasing course codes, no duplicates, required fields present) and optionally re-scrapes the live website to compare counts and first/last course codes against the stored JSON.

### Minor programme info (`minor_extraction/`)

3. **Extract** — `extract_minor_sections.py` scrapes the CUHK academic programs page to find minor programme boxes for every UG 2025 Full-time program and saves them as raw HTML in `minor_html/`.

4. **Generate site** — `generate_minor_site.py` reads the extracted minor HTML, cross-references course codes with the course info JSON, and generates a polished static site in `site/` showing each minor's requirements alongside course titles, units, and prerequisites.

## Quick start

```bash
# Install dependencies
pip install playwright ddddocr pytest
playwright install chromium

# --- Course info ---
cd course_extraction
python get_course_info.py

# Run offline integrity checks
pytest tests/ -m "not live"

# Run live comparison against the website (slow — requires network + captcha)
pytest tests/ -m live

# Run everything
pytest tests/

# --- Minor info ---
cd minor_extraction
python extract_minor_sections.py   # scrape all UG 2025 minor programmes
python generate_minor_site.py      # generate static site
# Open site/index.html in a browser
```

## Structure

```
├── course_extraction/
│   ├── get_course_info.py       # Main course scraper
│   ├── course_info/             # Scraped JSON output (one file per major)
│   └── tests/
│       ├── test_course_info.py  # Offline + live validation tests
│       └── conftest.py          # Pytest markers
├── minor_extraction/
│   ├── extract_minor_sections.py  # Minor programme scraper
│   ├── generate_minor_site.py     # Static site generator
│   ├── minor_html/                # Raw extracted minor HTML (per program)
│   └── site/                      # Generated static site (index.html + minors/)
├── webtest.py                   # Interactive browser automation tool
└── user_data_dir/               # Playwright persistent browser profile
```

## Scraped data format

Each `course_info/<MAJOR>.json` is an array of objects:

```json
{
    "code":  "ACCT 2111",
    "title": "Introductory Financial Accounting",
    "unit":  "3.00",
    "info":  "Not for students who have taken ACCT1111"
}
```

The `info` field is only present when the course has enrollment requirements or restrictions.

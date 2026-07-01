# CUHK Major Course Info

Scrapes and validates course catalog data from the Chinese University of Hong Kong (CUHK) for every subject/major.

## What it does

1. **Scrape** — `get_course_info.py` navigates the CUHK course catalog page, selects each major from the dropdown, solves the captcha via OCR (`ddddocr`), and scrapes every course's code, title, units, and enrollment requirements into `course_info/<MAJOR>.json`.

2. **Validate** — `tests/` checks that scraped data is internally consistent (strictly increasing course codes, no duplicates, required fields present) and optionally re-scrapes the live website to compare counts and first/last course codes against the stored JSON.


## Quick start

```bash
# Install dependencies
pip install playwright ddddocr pytest
playwright install chromium

# Scrape course info (edit the option range in get_course_info.py as needed)
python get_course_info.py

# Run offline integrity checks
pytest tests/ -m "not live"

# Run live comparison against the website (slow — requires network + captcha)
pytest tests/ -m live

# Run everything
pytest tests/
```

## Structure

```
├── get_course_info.py     # Main scraper
├── course_info/           # Scraped JSON output (one file per major)
├── tests/
│   ├── test_course_info.py  # Offline + live validation tests
│   └── conftest.py          # Pytest markers
└── user_data_dir/         # Playwright persistent browser profile
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

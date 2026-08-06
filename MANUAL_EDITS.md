# Manual Edits & Hardcoded Constants

## 0. Year Directory Setup

Two new admission years were set up in August 2026:

### 2024_25
- Academy scraping of all major programme pages produced `minor_html/2024_25/`
- `generate_minor_json.py` auto-generated all JSONs from the HTML
- `resolve_course_descriptions.py` resolved elective course codes
- Fewer manual JSON edits were needed than 2025_26 (4 files vs 10)

### 2026_27
- Academy scraping produced `minor_html/2026_27/`
- `generate_minor_json.py` auto-generated all JSONs from the HTML
- **Religion_and_Health** was **not scraped** by the academy extractor (reason unknown).
  Manually inserted by copying the 2024_25 HTML and JSON to 2026_27 and setting
  `_auto_generated: false`.
- `resolve_course_descriptions.py` resolved elective course codes

---

## 1. Manual Entries in `course_overrides.json`

These were manually filled because the resolver flagged them as MANUAL — they
reference conceptual area groupings that cannot be auto-resolved from the catalog.

| Minor | Row text | Codes |
|---|---|---|
| **Cultural_Management** | "(b) Any 9 units Cultural Management Area(a)…" | 32 (ANTH 2xxx+, CURE 2xxx+, FAAS 3xxx+) |
| **Cultural_Studies** | "(b) 5 CURE courses at 2000+ from Cultural Studies Area(s)…" | 43 (CURE 2xxx+) |
| **Fine_Arts** | "(b) 2 Art History Courses[a]" | 36 (FAAS Art History, ex FAAS4180/4183/4280/4283) |
| **Fine_Arts** | "(c) 2 Studio Art Courses[a]" | 37 (FAAS Studio Art, same exclusions) |
| **Philosophy** | Elective row override | 134 (all PHIL except PHIL1110 — originally 122 restricted to 3000+ because the resolver misinterpreted the level constraint as a code filter) |
| **Religious_Studies** | "4 CURE courses at 2000+ from Religious Studies Areas…" | 52 (CURE 2xxx+) |

Sources: CUHK Department of Cultural and Religious Studies website and Fine Arts
Department course listings.

---

## 2. `_auto_generated: false` JSON Files (by Year)

Files with `_auto_generated: false` are skipped by `generate_minor_json.py` on
regeneration to preserve manual structural fixes.

### 2024_25 (4 files)

| File | Edits |
|---|---|
| **Biochemistry.json** | Removed false eq_pair `["BCHE 3030", "BCHE 3730"]` |
| **Biology.json** | Removed false eq_pair `["BIOL 3560", "BIOL 3610"]` |
| **Molecular_Biotechnology.json** | Set `required.units="6"`; `elective.units` to "14" |
| **Music.json** | `elective.rows[0].units` set to "4"; `rows[1].units` set to "7"; row 2b text updated to match override key (355 chars, full excluded-course list) |

### 2025_26 (11 files)

| File | Edits |
|---|---|
| **Artificial_Intelligence_Systems_and_Technologies.json** | Added period to note index "2" → "2." |
| **Biochemistry.json** | Removed false eq_pair `["BCHE 3030", "BCHE 3730"]` |
| **Biology.json** | Removed false eq_pair `["BIOL 3560", "BIOL 3610"]` |
| **Chinese_Language_and_Literature.json** | Manual course code corrections |
| **HB_Minor_Programme_in_Business.json** | `elective.label`: dropped "12 units"; `elective.rows[0].units` set to "12" |
| **HB_Minor_Programme_in_Data_Analytics_and_Informatics.json** | Flattened nested-or rows, removed "OR" row |
| **Japanese_Studies.json** | Moved "6" from section to `rows[0].units`; set `rows[2].units="12"` |
| **Molecular_Biotechnology.json** | Set `required.units="6"`; `elective.units` to "14" |
| **Music.json** | `elective.rows[0].units` set to "4"; `rows[1].units` set to "7" |
| **Philosophy.json** | Merged split `<tr>` for note 2 |
| **Sociology.json** | Set `elective.rows[0].units="15"`; prepended "15 units from the following…" |

### 2026_27 (6 files)

| File | Edits |
|---|---|
| **Biochemistry.json** | Same as 2025_26 (false eq_pair removed, _auto_generated: false) |
| **Biology.json** | Same as 2025_26 (false eq_pair removed, _auto_generated: false) |
| **Japanese_Studies.json** | Same as 2025_26 (_auto_generated: false) |
| **Molecular_Biotechnology.json** | Same as 2025_26 (_auto_generated: false) |
| **Music.json** | Same as 2025_26 (_auto_generated: false) |
| **Religion_and_Health.json** | _auto_generated: false to prevent accidental overwrite. Notes sourced from 2024_25 HTML copy. |

---

## 3. Hardcoded Constants in `generate_checker_data.py`

### `AREA_CODE_LISTS`
64 numeric suffixes for Music Areas 2B (Choral and Orchestral Ensemble) and 2C
(Other Ensemble). Auto-generates `subject_buckets` from `"not more than 4 units
of courses from Area 2B and/or 2C"`.

### `EQ_NOTES`
Equivalence tables/footnotes from Explanatory Notes merged into `eq_pairs`:

| Minor | Key equivalences |
|---|---|
| **Computer_Science** | CSCI1120/1130/ESTR1100/1102 ≡ CSCI1510-40; ENGG1110/ESTR1002 ≡ CSCI1510-40; CENG2400/ELEG2401/3701/ESTR2100 ≡ CSCI2510; CSCI2100/ESTR2102 ≡ CSCI2520; PHYS2061 ≡ CSCI1530 |
| **Statistics** | STAT1011 ≡ STAT1012/2001/DOTE2011/FINA2220/ECON2121/GRMD2102/SOCI2004; STAT2102 ≡ STAT2006/DOTE2021 |
| **Risk_Management_Science** | Same STAT table as Statistics |
| **Physics** | PHYS1002 ≡ PHYS1003; PHYS1111/1113 ≡ PHYS1110; PHYS2041 ≡ ENGG1310/2520/ESTR1003/2006; PHYS2051 ≡ MATH2020/2028 |

> Electronic_Engineering (`BMEG2300 ≡ ELEG2202`) was removed from hardcoding
> and is now auto-detected by `detect_notes_eq_rules()`.

### `AND_EQ_GROUPS`
Multi-course equivalences where two courses together equal one canonical:
- Statistics / Risk_Management_Science: `ENGG2760+ENGG2780` (4u) or `ESTR2018+ESTR2020` (4u) ≡ STAT1011 (3u)

### `SUBJ_BUCKETS_NOTES`
Physics: `max_units: 6` subject bucket for equivalent/closely related courses.

### `KNOWN_GROUPS`
Faculty prefix grouping for E&I cap detection (`MGNT/COMM` → Business Admin,
`CSCI/AIST/…` → Engineering, etc.).

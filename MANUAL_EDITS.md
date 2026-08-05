# Manual Edits & Hardcoded Constants

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

## 2. Manual Edits to `minor_json/*.json`

These files had structural issues requiring direct edits. `_auto_generated` was
set to `false` to prevent overwriting by `generate_minor_json.py`.

| File | Edits |
|---|---|
| **Philosophy.json** | Merged split `<tr>` for note 2 (the "fulfill the requirements…" and "Programme(s) and other Minor…" were in separate rows) |
| **AIST.json** | Added period to note index "2" → "2." so the generator recognises it as a note point |
| **Business.json** (HB) | `elective.label`: dropped "12 units" (only row a); `elective.rows[0].units` set to "12" so total = 12+6=18 |
| **Data_Analytics.json** (HB) | Flattened (a) section: three nested-or rows merged into one, removed "OR" row and "i)/ii)" |
| **Japanese_Studies.json** | `elective.units`: moved "6" from section to `rows[0].units`; set `rows[2].units="12"` (total = 6+12=18) |
| **Music.json** | `elective.rows[0].units` set to "4"; `rows[1].units` set to "7" (total = 4+7=11) |
| **Chinese_Language_and_Literature.json** | (manual edit — appears in `_auto_generated: false` list) |
| **Biochemistry.json** | Removed false eq_pair `["BCHE 3030", "BCHE 3730"]` — courses are NOT equivalent; they were collapsing required total from 11→9 |
| **Biology.json** | Removed false eq_pair `["BIOL 3560", "BIOL 3610"]` — belong to different OR groups; `or_group` strategy now handles separation |
| **Sociology.json** | Set `elective.rows[0].units="15"`; prepended "15 units from the following…" to row text — prevents generator from misinterpreting the "6 units" level constraint as the row target |
| **Molecular_Biotechnology.json** | Set `required.units="6"`; changed `elective.units` from "13" to "14" (uses max of range so 6+14=20 ≥ 19) |


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

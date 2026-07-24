# Manual Edits to course_overrides.json

The following entries in course_overrides.json were manually filled in
because the resolver flagged them as MANUAL — they reference conceptual
area groupings (e.g., "Cultural Studies Area(s)", "Art History Courses",
"Religious Studies Areas") that cannot be auto-resolved from the
course_info/ catalog data alone.

## Cultural_Management
- "(b) Any 9 units Cultural Management Area(a), with at least 3 units at 3000 or above level [a]"
  32 codes added (ANTH 2xxx+, CURE 2xxx+, FAAS 3xxx+ courses belonging to the Cultural Management Area)

## Cultural_Studies
- "(b) 5 CURE courses at 2000 or above level from Cultural Studies Area(s), with at least 2 courses at 3000 or above level, excluding the course taken to fulfill requirement 1(a) above"
  43 codes added (CURE 2xxx+ courses belonging to the Cultural Studies Areas)

## Fine_Arts
- "(b) 2 Art History Courses[a]"
  36 codes added (FAAS Art History-designated courses, excluding FAAS4180, 4183, 4280, 4283 and courses listed under elective 2(a))

- "(c) 2 Studio Art Courses[a]"
  37 codes added (FAAS Studio Art-designated courses, same exclusions as 2(b))

## Religious_Studies
- "4 CURE courses at 2000 or above level from the Religious Studies Areas, of which at least 2 courses are at 3000 or above level"
  52 codes added (CURE 2xxx+ courses belonging to the Religious Studies Areas)

## Sources
Course area groupings were determined from the CUHK Department of Cultural
and Religious Studies website and the Fine Arts Department course listings.

# Manual Edits to minor_json files

These edits were made directly to minor_json/*.json files because the source
HTML had structural issues that the parser could not handle. After editing,
_auto_generated was set to false in each file to prevent overwriting.

## Philosophy (Philosophy.json)
- **explanatory_notes**: Merged note 2's content from two split <tr> elements
  into a single row. The original source HTML had "fulfill the requirements of
  the students' Major" in one row and "Programme(s) and other Minor..." in a
  separate continuation row, causing the site to render two separate text boxes
  for a single note.

## Artificial Intelligence: Systems and Technologies (AIST)
- **explanatory_notes**: Added a period after the note index "2" so it reads
  "2." instead of "2". The missing period caused the site generator to fail to
  recognize it as a note point, rendering it with inconsistent font styling
  as a plain table row instead of a note card.

## Business (HB_Minor_Programme_in_Business)
- **elective.label**: Changed from "1. Elective Courses: 12 units" to
  "1. Elective Courses" because the "12 units" referred only to row (a) of the
  elective section, not the entire section. Row (b) adds 6 more units for a
  correct total of 18.
- **elective.rows[0].units**: Set to "12" so the site generator auto-computes
  the section total as 12 + 6 = 18 units.

## Data Analytics and Informatics (HB_Minor_Programme_in_Data_Analytics_and_Informatics)
- **required.rows**: Flattened the (a) section from three rows:
    `(a) i) ENGG2760/... , ENGG2780/...`
    `OR`
    `ii) IERG2470/...`
  into a single row:
    `(a) ENGG2760/ESTR2018[b] AND ENGG2780/ESTR2020[b], OR IERG2470/ESTR2308[b]`
  Removed the "OR" row and the "i)"/"ii)" indicators for clarity.
  (b) row was left unchanged.

## Japanese Studies (Japanese_Studies.json)
- **elective.units**: Changed from `"6"` to `""` because the "6 units" referred
  only to row (a), not the entire elective section.
- **elective.rows[0].units**: Set to `"6"` (row (a) — 2 courses × 3 units).
- **elective.rows[2].units**: Set to `"12"` (row (b) — 4 courses × 3 units).
  The site generator now auto-computes the section total as 6 + 12 = 18 units.

## Music (Music.json)
- **elective.rows[0].units**: Set to `"4"` (row 2a — 4 units from listed
  courses). Previously empty, causing no unit count to display.
- **elective.rows[1].units**: Set to `"7"` (row 2b — remaining units after
  required 7 + 2a's 4 = 11, to reach 18 total). Previously empty.
  The site generator now auto-computes the section total as 4 + 7 = 11 units,
  and the rows each display their individual unit counts.

## Biochemistry (Biochemistry.json)
- **eq_pairs**: Removed `["BCHE 3030", "BCHE 3730"]` from the equivalence pairs
  list. These are not equivalent courses — BCHE 3030 (3u) and BCHE 3730 (2u) are
  both required separately. Keeping them as equivalents caused the required
  section to show only 9 units instead of the correct 11 (BCHE 2030, 3030, 3730, 3080).

## Sociology (Sociology.json)
- **elective.rows[0].units**: Set to `"15"`. The header row "from the following,
  including a minimum of 6 units of elective courses at 3000 or above level" had
  no unit metadata, causing the generator to incorrectly use the "6" (a level
  constraint) as the row's `units_needed` instead of the correct section total of 15.
  The `units` metadata ensures the generator uses the correct value, while the
  level constraint (≥6 units at 3000+) is still separately extracted.

## Molecular Biotechnology (Molecular_Biotechnology.json)
- **required.units**: Set to `"6"`. Previously empty, causing the generator to
  compute the section target as 3 (row a) + 2 (row b min) = 5. The correct total
  for the required section is 6 (row a 3u + row b max 3u).
- **elective.units**: Changed from `"13"` to `"14"`. The section label says
  "13 or 14 units." Using the max (14) ensures sections sum to 6 + 14 = 20 ≥ 19
  (the description's "minimum of 19 units"), allowing the checker to reach 100%.
  The `units_max: "14"` field remains as the upper bound.

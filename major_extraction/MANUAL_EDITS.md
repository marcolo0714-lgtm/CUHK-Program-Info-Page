# Manual JSON Edits

This file records any edits that must be applied manually to files under
`major_extraction/major_json/<year>/` after running the Python generators.

## 2026–27

**No manual JSON edits are required.**

The current site can be reproduced entirely by running:

```powershell
python major_extraction/extract_major_pages.py --year 2026_27 --headless
python major_extraction/generate_major_json.py --year 2026_27
python major_extraction/generate_major_site.py --year 2026_27
```

All programme-specific corrections and exceptional transformations are
implemented in `major_extraction/generate_major_json.py` and
`major_extraction/major_readability.py`, including:

- first-standard-box selection for pages that also publish senior-entry,
  recommended-pattern, or second-major requirement boxes;
- general Word-table marker recovery for numbered sections, lettered groups,
  roman-numeral children, parenthesized numeric categories, and parallel
  paragraph rows;
- annotated, ranged, alternative, summed, and total-derived unit badges;
- structured explanatory-note headings, rows, concentration lists, and the
  long-list-only course-table rule;
- Anthropology voluntary-concentration course lists;
- Bimodal Bilingual Studies letter/roman hierarchy;
- Chinese Language and Literature first-box-only handling;
- Chinese Studies and Japanese Studies stream hierarchy;
- History's parallel elective minima, Natural Sciences course-list groups,
  and the Chinese Language Studies/Education combined-degree hierarchy;
- Engineering stream and elective hierarchy corrections;
- broad departmental course-rule expansion;
- double-major group and unit handling;
- Biomedical Engineering CSCI course groups;
- Computer Engineering, Computer Science, Information Engineering, and
  Computational Data Science remaining-unit groups;
- Materials Science, interdisciplinary data analytics, and Mathematics and
  Information Engineering area handling;
- Mechanical and Automation Engineering stream nesting;
- Engineering ELITE Stream generation;
- recommended-course-pattern fallback parsing;
- flat single-cell requirement-table fallback parsing; and
- the explicit unavailable-format record for M.B., Ch.B.

Cross-listed faculty affiliations are consolidated by
`major_extraction/extract_major_pages.py`. Missing course-information records
are displayed automatically by `major_extraction/generate_major_site.py` and
are not repaired by editing generated JSON.

## Recording future manual edits

Generated JSON files should normally be treated as build artifacts. If a
manual JSON correction is unavoidable, add an entry below before regenerating
the HTML. Each entry must include:

1. academic year;
2. JSON filename;
3. exact JSON path or section affected;
4. old and new values;
5. reason and official source; and
6. whether the correction still needs to be moved into the Python generator.

Manual corrections should subsequently be implemented in the generator and
removed from this list so that a clean pipeline run remains reproducible.

### Pending manual edits

None.

## Readability and course eligibility refinements

No generated JSON was edited manually for these changes:

- Separate introductory instructions and course expressions into text boxes;
  move long instructional headings into prose while retaining their marker,
  unit value, and nesting.
- Split English and Fine Arts elective/stream requirements into their actual
  course groups. Resolve History's remaining HIST pool separately from the
  stated minima and earlier requirements, including the permitted ANTH options.
- Use the published course-area tables for Linguistics, Music, Philosophy,
  and the applicable Humanities/Theology requirements. Explicit exclusions
  are retained as source text and `excluded_codes`, not eligible table rows.
- Correct Linguistics' source-list typo BMLB3003 to BMBL3003, corroborated by
  the degree schemes on the same saved source page and the course catalogue.
- Show identifiable language-learning options for Linguistics with an explicit
  non-exhaustive/approval caveat; omit culture-only courses and one-unit tasters.
- Preserve Music's conditional options: an alternative not used for required
  courses may remain eligible, but cannot be counted twice.
- Recover the Japanese Local Study Scheme from the selected source requirement
  box. Publish the faculty-wide Science, Technology and Research (STAR) Stream
  once as its own sidebar programme instead of repeating it on Science majors.
- Distinguish course levels from abbreviated course codes and handle a comma
  between a subject and its first course number.
- Promote Anthropology's voluntary concentrations to a peer of Explanatory
  Notes, while retaining a course-information table for every concentration.
- Preserve source line breaks in compound explanatory notes and avoid repeating
  short course-code mentions underneath the note text.
- Use one text box for the specified Faculty Package lists and English elective
  introduction; split Fine Arts' three-stream description into readable lines.
- Normalize Chinese Studies stream formatting, Japanese Studies stream/intake
  instructions, Linguistics' required-course hierarchy, and Music's applicable
  elective areas.
- Nest Public Humanities and Religious Studies concentrations vertically below
  a Concentrations heading, and resolve every reference to Religious Studies
  Areas from that programme's saved course-list table.
- Restore Philosophy's explanatory notes and attach its published minimum and
  maximum area-selection hints.
- Resolve Theology elective Areas 2, 4, and 5 separately and remove courses
  already appearing in its required and other area requirements from the
  generated THEO option pool.
- Retain every explanatory note from the selected requirement box, including
  the three Chinese Language and Literature cross-major exemption notes and
  notes embedded in flat, single-cell programme tables.
- Repair the Integrated BBA concentration hierarchy, and render the Juris
  Doctor second-degree requirements as a peer requirement block rather than
  as part of the first degree's explanatory notes.
- Recover all four Professional Accountancy stream alternatives while keeping
  the original no-stream option clearly labelled.
- Split Biotechnology, Entrepreneurship and Healthcare Management
  concentrations into Required Courses and Elective Courses children, and use
  comma-separated faculty affiliations in the generated breadcrumb.
- Promote interdisciplinary double-major cross-campus course instructions and
  Quantitative Finance's Business-course rule to headings at the correct
  level; keep Quantitative Finance section 3(e)'s expression as body text.
- Render marker-only lettered and roman-numeral rows inline with their text,
  with wrapped text aligned beneath the text rather than beneath the marker.
  The corresponding wrapping rule is also implemented in the minor-site
  generator.
- Combine adjacent prose paragraphs into one visual text box while preserving
  paragraph breaks, instead of drawing a separate bordered box for each source
  row.
- Recover the two explanatory-note markers merged by the English
  Studies/English Language Education source, and normalize multi-column roman
  numeral notes into nested inline points across Engineering programmes.
- Recover labelled course groups such as Chemistry, Life Science, Physics,
  faculty alternatives, Diplomacy cores and elective areas as headings with
  their own course data.
- Restore the 40-unit Core, 6-unit Research Experience and 10-unit Teaching
  Practice groups under Early Childhood Education section 2, giving the
  section its published 56-unit total.
- Structure Mathematics and Mathematics Education's faculty alternatives and
  Subject Knowledge elective hierarchy, resolving the four subject-area
  options under section 3(b)(II) from the saved course catalogue and the
  programme's explanatory-note restrictions.
- Promote stream introductions, Computational Data Science's named option and
  Electronic Engineering's three career-guidance categories to headings.
- Preserve both Mathematics and Information Engineering requirement sets from
  the first CUHK requirement box by rendering the Faculty of Science admission
  route as a parallel 87-unit requirement block.
- Nest the Chinese Law and Global Law streams, including their lettered
  requirements, under the Laws programme's Streams heading.
- Recover Biomedical Sciences and Pharmacy concentration labels as nested
  headings, and split Community Health Practice/Public Health Group A and B
  lists into their own course groups.
- Recover the full Chinese Medicine pre-clinical and clinical introduction.
- Parse MBChB's separate requirement, recommended-pattern, GPS and explanatory-
  note tables into one readable programme page.
- Separate the articulated Mathematical Sciences BSc, PhD pre-candidacy and
  PhD post-candidacy schemes; keep the seven choices under section 3(a)(i) as
  indented prose rows.
- Split every CUHK/CUHK(SZ) campus label in the Mathematical Sciences and
  Artificial Intelligence double major into a heading, and structure the
  Biochemistry/Biology Faculty Package and Biochemistry Lists A-C.
- Treat any requirement title containing a course code as prose globally, so
  course expressions cannot be repeated or mistaken for headings.
- Structure Faculty Package Group A-E choices consistently across every
  Science programme and every recovered Science stream, including requirement
  boxes whose group labels share one source row.
- Recover the complete Earth and Environmental Sciences, Food and Nutritional
  Sciences, Natural Sciences, Physics, Risk Management Science, Statistics and
  Mathematics stream schemes from the saved official tables. Place Natural
  Sciences and Physics stream material after section 2, and place the Risk
  Management Science and Statistics alternatives after the main explanatory
  notes.
- Reorganize Mathematics after its Faculty Package into one top-level section
  per stream, each with Required Courses and Elective Courses children.
- Promote the published Chemistry elective-list labels, EESC Categories A-C,
  Physics Courses, Journalism study options, GPAD fields/free electives/
  capstones and the GRMD nine-course rule to headings. Resolve the broad Global
  Studies language-course and GPAD free-elective tables from the local course
  catalogue.
- Recover Economics, Geography and Resource Management, Psychology, Sociology
  and Urban Studies concentration areas from the rows after the main total and
  render them before the main explanatory notes. Split the merged GRMD [a]/[b]
  note into its two published restrictions.
- Flatten Global Communication items 3(ii)-3(v), show Anthropology voluntary-
  concentration code expressions as prose as well as tables, and change the
  English stream introduction from “the following stream” to “this stream”.
- Publish standalone ELITE and STAR descriptions with the generated list of
  eligible majors, remap STAR note references, and rewrite dependent ELITE note
  wording so it makes sense outside an individual major page.
- Merge near-identical Japanese Studies, Professional Accountancy,
  Mathematics and Information Engineering, Risk Management Science and
  Statistics alternatives into shared requirements with labelled route or
  stream differences.
- Render consecutive Humanities area catalogues and Diplomacy language
  offerings as single course tables with labelled divider rows, avoiding
  repeated copies of identical area tables.
- Restore structured headings and units for Translation notes, Integrated BBA
  concentrations, the JD second degree, Economics and Sociology
  concentrations, Education requirements, Engineering stream guidance, and
  the other programme-specific source rows listed in the September 2026
  readability review.
- Group each double-major choice with its corresponding first- and
  second-major requirements; restore Mathematics' published three-section
  structure; and promote each Natural Sciences stream to a top-level heading.
- Present Earth and Environmental Sciences streams as changes to the shared
  requirement rather than full repeated schemes, and place Physics streams in
  their published position after section 3.
- Restore the complete Chinese Medicine and paragraph-preserving MBChB
  introductions, GPS exclusions and eligibility formatting, plus standalone
  ELITE/STAR eligible-programme headings.
- Preserve explicit and labelled CUHK source links and render every valid web
  address as a safe clickable link; keep explanatory-note subpoints compact,
  unboxed and without divider rules, and sort the Others faculty last.
- Present Japanese Studies' Standard and Local Study Schemes in parallel under
  With/Without Stream, merge consecutive Linguistics area tables with labelled
  divider rows, retain the full Japanese 2(b) resident-study requirement, and
  present Public Humanities 3(a)-3(b) by scheme while rendering the common
  Religious Studies rule in 3(c) only once.
- Repeat the applicable Religious Studies area catalogues in every option,
  retain visible area-name rows, and group 3(a)-3(b) under one peer-level
  Without Concentrations heading.
- Normalize the Integrated BBA/JD first-degree heading and notes, move the
  Professional Accountancy ordinary list under its own heading, and restructure
  all three cross-campus double majors into one shared first-major requirement
  followed by non-duplicated major choices.
- Reassert the reviewed AIST, Information Engineering, SEEM and Computational
  Data Science stream/instruction hierarchy after generic heading cleanup.
- Combine Mathematics and Information Engineering's common requirements and
  admission-route differences into the published 1(a)-1(d) structure, including
  a fully grouped Science Faculty Package.
- Limit ELITE/STAR eligibility to source pages that actually publish those
  schemes, while retaining Statistics in STAR and excluding Interdisciplinary
  Data Analytics from ELITE.
- Preserve the Laws stream introduction, Chinese Medicine introduction
  headings, MBChB note 3(v)(a)-(d), and the articulated Mathematical Sciences
  BSc/PhD hierarchy and `71 + 27 + 78` total.
- Keep Earth and Environmental Sciences' original section 1/2(a-e)/3(a-d)
  structure while nesting only the stream-dependent rows and reading each
  stream's own 3(d) list and unit rule; resolve Mathematics broad eligible-course
  groups into separate Science, Engineering and Economics/Finance tables and
  the Enrichment Stream course table.
- Split every Natural Sciences elective list into Concentration Area Courses
  and Other Science Courses by their source labels (rather than row position),
  and restore the reviewed Physics stream totals, elective heading and note table.
- Restore Risk Management Science and Statistics alternative unit totals and
  notes, and rebuild Sociology's concentration clusters, optional-course
  headings, capstone choices and sustainability Required/Elective groups.
- Derive Japanese Studies route units from the published Standard/Local
  alternatives; align Public Humanities' Standard Scheme labels with their
  lettered markers and all three scheme/concentration rule boxes at one depth;
  preserve the reviewed double-major markers; and render “Without Stream” on
  the Earth and Environmental Sciences 3(a)/3(b) marker lines while keeping all
  named stream alternatives as peers and consolidating the shared other-
  elective pool into one course table.
- Separate Mathematics' BMED 3000-or-above pool, retain Statistics' long
  Data Analytics course expression, and keep Risk Management Science Faculty
  Package alternatives and explanatory notes at their published levels.
- Recalculate grouped course-table column spans from the user's visible-column
  settings, so future grouped catalogues use the available width without
  reserving space for hidden columns.

These rules use the saved official HTML and local course catalogue. Broad
eligibility remains subject to the original programme restrictions and course
availability; a generated table is not an enrolment or graduation approval.

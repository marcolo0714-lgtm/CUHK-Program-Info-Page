"""Availability outside the regular teaching terms and shared row filters."""

import re


REGULAR_TERM = re.compile(r"\b\d{4}\s*-\s*\d{2}\s+Term\s*[12]\b", re.IGNORECASE)


def offered_outside_regular_terms(course):
    """Check positive offerings and saved class sections for other term labels."""
    def is_other_term(entry):
        term = entry.get("term") or ""
        return bool(term.strip() and not REGULAR_TERM.search(term))

    return any(
        entry.get("offered") is True and is_other_term(entry)
        for entry in course.get("term_offerings", [])
    ) or any(is_other_term(section) for section in course.get("sections", []))


T3_HEADER = '<th class="col-term-3" title="Available outside Term 1 and Term 2">T3</th>'


def setting_checkbox(key, label, checked):
    return (
        f'<label class="setting-option"><input type="checkbox" data-table-setting="{key}"'
        f'{" checked" if checked else ""}> <span>{label}</span></label>'
    )


def term_setting_group(group_id, label, options):
    title_id = f"{group_id}-label"
    choices = "".join(
        setting_checkbox(key, f"T{term}", checked)
        for term, (key, checked) in enumerate(options, start=1)
    )
    return (
        f'<div class="term-setting-group" role="group" aria-labelledby="{title_id}">'
        f'<div id="{title_id}">{label}</div>'
        f'<div class="term-setting-choices">{choices}</div></div>'
    )


SETTINGS_DESCRIPTION = (
    '<p class="settings-description">Choose the columns, rows, and table behaviours.<br>'
    'T3 refers to terms outside T1 and T2.</p>'
)
TERM_COLUMN_SETTINGS = term_setting_group(
    "term-availability", "Show availability",
    (("term1", True), ("term2", True), ("otherTermColumn", False)),
)
TERM_SCHEDULE_SETTINGS = term_setting_group(
    "term-schedule", "Show teaching schedule",
    (("schedule", False), ("schedule2", True)),
)
TERM_ROW_SETTINGS = (
    term_setting_group(
        "term-course-rows", "Show courses available in",
        (("rowsT1", True), ("rowsT2", True), ("otherTermRows", True)),
    )
    + setting_checkbox("missingCourseRows", "Show unavailable courses", True)
)


def term_cell(term, available):
    highlighted = " term-yes" if available else ""
    return f'<td class="col-term-{term}{highlighted}"></td>'


COURSE_COUNT_JS = r"""
function updateCourseTableCounts(settings) {
    const allRowsEnabled = settings.rowsT1 && settings.rowsT2 &&
        settings.otherTermRows && settings.missingCourseRows;
    document.querySelectorAll('details.course-details').forEach(details => {
        const summary = details.querySelector(':scope > summary');
        if (!summary) return;
        if (!summary.dataset.fullLabel) summary.dataset.fullLabel = summary.textContent;
        const fullLabel = summary.dataset.fullLabel;
        const count = fullLabel.match(/^Show\s+(\d+)/);
        if (!count) return;
        if (allRowsEnabled) {
            summary.textContent = fullLabel;
            return;
        }
        const rows = details.querySelectorAll(':scope > table > tbody > tr');
        const visible = Array.from(rows).filter(row =>
            (row.classList.contains('nf') || row.querySelector(':scope > td.col-code')) &&
            getComputedStyle(row).display !== 'none'
        ).length;
        summary.textContent = fullLabel.replace(/^Show\s+\d+/, 'Show ' + visible + ' / ' + count[1]);
    });
}
"""


TERM_TABLE_CSS = """\
.term-setting-group { padding:9px 4px 0; border-bottom:1px solid var(--tbl-border-light); }
.term-setting-choices { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); }
.term-setting-choices .setting-option { align-items:center; gap:6px; padding:6px 0;
    min-height:36px; border-bottom:0; }
.term-setting-choices .setting-option input { margin-top:0; }
body.hide-missing-course-rows tbody tr.nf { display:none; }
/* Retain a row when any of its terms is selected. Missing records have no term cells. */
body.filter-course-rows tbody tr:has(> td.col-term-3):not(
    body:not(.hide-rows-t1) tr:has(> .col-term-1.term-yes),
    body:not(.hide-rows-t2) tr:has(> .col-term-2.term-yes),
    body:not(.hide-rows-t3) tr:has(> .col-term-3.term-yes)
) { display:none; }
"""

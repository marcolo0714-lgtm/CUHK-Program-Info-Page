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


# Use new keys for T3 so defaults automatically saved by the previous version
# do not override the corrected defaults. Other saved preferences still apply.
TERM_COLUMN_SETTINGS = (
    setting_checkbox("term1", "Show T1 availability", True)
    + setting_checkbox("term2", "Show T2 availability", True)
    + setting_checkbox("otherTermColumn", "Show T3 (other terms) availability", False)
)
TERM_ROW_SETTINGS = (
    setting_checkbox("rowsT1", "Show courses available in T1", True)
    + setting_checkbox("rowsT2", "Show courses available in T2", True)
    + setting_checkbox("otherTermRows", "Show courses available in T3 (other terms)", True)
    + setting_checkbox("missingCourseRows", "Show unavailable courses", True)
)


def term_cell(term, available):
    highlighted = " term-yes" if available else ""
    return f'<td class="col-term-{term}{highlighted}"></td>'


TERM_ROW_CSS = """\
body.hide-missing-course-rows tbody tr.nf { display:none; }
/* Retain a row when any of its terms is selected. Missing records have no term cells. */
body.filter-course-rows tbody tr:has(> td.col-term-3):not(
    body:not(.hide-rows-t1) tr:has(> .col-term-1.term-yes),
    body:not(.hide-rows-t2) tr:has(> .col-term-2.term-yes),
    body:not(.hide-rows-t3) tr:has(> .col-term-3.term-yes)
) { display:none; }
"""

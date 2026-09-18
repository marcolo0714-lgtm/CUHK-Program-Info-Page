from minor_extraction.minor_course_index import (
    load_minor_course_index,
    minor_applies_to_major,
    minor_matches_major_name,
)


def _minor(index, code, title):
    return next(item for item in index[code] if item["title"] == title)


def test_explanatory_note_equivalences_are_indexed():
    index = load_minor_course_index("2026_27")
    assert _minor(index, "PHYS 2061", "Computer Science")
    assert _minor(index, "STAT 1012", "Statistics")
    assert _minor(index, "ENGG 2760", "Risk Management Science")


def test_waivers_follow_checker_credit_semantics():
    index = load_minor_course_index("2026_27")
    assert _minor(index, "FREN 3051", "French")
    assert not any(item["title"] == "Psychology" for item in index.get("UGED 2581", []))


def test_major_specific_minor_exclusions():
    index = load_minor_course_index("2026_27")
    anthropology = _minor(index, "ANTH 1010", "Anthropology")
    assert not minor_applies_to_major(
        anthropology, {"title": "B.A. in Anthropology", "faculty": "Arts"}
    )

    risk = _minor(index, "STAT 1011", "Risk Management Science")
    assert minor_applies_to_major(
        risk,
        {"title": "B.Sc. in Quantitative Finance", "faculty": "Business Administration"},
    )
    assert not minor_applies_to_major(
        risk,
        {
            "title": "B.Sc. in Quantitative Finance and Risk Management Science",
            "faculty": "Science",
        },
    )


def test_faculty_wide_exclusion():
    index = load_minor_course_index("2026_27")
    business = _minor(index, "MGNT 1020", "Business")
    assert not minor_applies_to_major(
        business,
        {"title": "B.B.A. in Professional Accountancy", "faculty": "Business Administration"},
    )


def test_qualified_programmes_do_not_exclude_the_standalone_major():
    index = load_minor_course_index("2026_27")
    computer_science = _minor(index, "PHYS 2061", "Computer Science")
    assert minor_applies_to_major(
        computer_science,
        {"title": "B.B.A. - Integrated BBA Programme", "faculty": "Business Administration"},
    )
    assert minor_applies_to_major(
        computer_science,
        {"title": "B.Sc. in Mathematics", "faculty": "Science"},
    )

    linguistics = _minor(index, "LING 3204", "Linguistics")
    assert minor_applies_to_major(
        linguistics,
        {"title": "B.S.Sc. in Psychology", "faculty": "Social Science"},
    )


def test_same_named_major_and_minor_are_identified():
    assert minor_matches_major_name(
        {"title": "Artificial Intelligence: Systems and Technologies"},
        {"title": "B.Eng. in Artificial Intelligence: Systems and Technologies"},
    )
    assert minor_matches_major_name(
        {"title": "Economics"},
        {"title": "B.S.Sc. in Economics"},
    )
    assert not minor_matches_major_name(
        {"title": "Risk Management Science"},
        {"title": "B.Sc. in Quantitative Finance and Risk Management Science"},
    )

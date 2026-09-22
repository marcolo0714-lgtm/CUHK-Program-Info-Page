import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from major_extraction.generate_major_json import (
    choose_requirement_table,
    direct_rows,
    extract_course_codes,
    logical_row_cells,
)
from major_extraction.generate_major_site import format_info, format_schedule

ROOT = Path(__file__).resolve().parents[2]
YEAR = "2026_27"
JSON_DIR = ROOT / "major_extraction" / "major_json" / YEAR
HTML_DIR = ROOT / "major_extraction" / "major_html" / YEAR
SITE_DIR = ROOT / "site" / "major" / YEAR


def load_programmes():
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(JSON_DIR.glob("*.json"))]


def walk_test_groups(groups):
    for group in groups:
        yield group
        yield from walk_test_groups(group.get("subsections", []))


def programme_codes(programme):
    def walk(groups):
        for group in groups:
            yield group
            yield from walk(group.get("subsections", []))

    return [code for group in walk(programme["sections"]) for code in group["codes"]]


def test_all_catalogue_programmes_were_scraped_and_generated():
    programmes = load_programmes()
    records = json.loads((HTML_DIR / "_programmes.json").read_text(encoding="utf-8"))
    assert len(records) == 87
    assert len(programmes) == len(records) + 2  # Engineering ELITE and Science STAR streams
    assert len(list((HTML_DIR / "full_pages").glob("*.html"))) >= len(records)
    unavailable = [programme for programme in programmes if programme.get("parse_status") == "unavailable"]
    assert unavailable == []
    assert all(programme["sections"] for programme in programmes)
    faculties = {faculty for programme in programmes for faculty in programme.get("faculties", [])}
    assert {"Arts", "Business Administration", "Education", "Engineering", "Law", "Medicine", "Science", "Social Science"} <= faculties


def test_computer_science_uses_its_engineering_requirement_not_bba():
    data = json.loads((JSON_DIR / "B.Sc._in_Computer_Science.json").read_text(encoding="utf-8"))
    assert "75 units" in data["description"]
    faculty_package = next(section for section in data["sections"] if section["title"] == "Faculty Package")
    assert "ENGG 1110" in faculty_package["codes"]
    assert not any(code.startswith("DOTE ") for code in faculty_package["codes"])


def test_course_codes_are_canonical():
    pattern = re.compile(r"^[A-Z]{4} [0-9]{4}$")
    for programme in load_programmes():
        if programme.get("parse_status") == "unavailable":
            continue
        codes = programme_codes(programme)
        assert codes
        assert all(pattern.fullmatch(code) for code in codes)


def test_only_numbered_rows_are_top_level_sections():
    for programme in load_programmes():
        assert all(re.fullmatch(r"\d+\.?", section["marker"]) for section in programme["sections"])


def test_computer_engineering_streams_and_notes_are_structured_cleanly():
    data = json.loads((JSON_DIR / "B.Eng._in_Computer_Engineering.json").read_text(encoding="utf-8"))
    option_section = next(section for section in data["sections"] if section["marker"].startswith("4"))
    titles = [subsection["title"] for subsection in option_section["subsections"]]
    assert any("General Computer Engineering" in title for title in titles)
    assert any("Embedded Systems" in title for title in titles)
    assert any("VLSI Design and EDA" in title for title in titles)
    note_h = next(note["text"] for note in data["notes"] if note["marker"] == "[h]")
    assert "Engineering courses" in note_h
    assert "ELITE Stream only. It" in note_h
    assert "Major Programme" in note_h
    assert all(fragment not in note_h for fragment in ("E ngineering", "S tream", "I t", "P rogramme"))


def test_aist_preserves_requirement_text_markers_and_nested_stream_groups():
    data = json.loads((JSON_DIR / "B.Eng._in_Artificial_Intelligence_Systems_and_Technologies.json").read_text(encoding="utf-8"))
    assert data["sections"][0]["text"][0].startswith("ENGG1110/ESTR1002")
    required = next(section for section in data["sections"] if section["marker"].startswith("3"))
    assert [group["marker"] for group in required["subsections"]][:3] == ["(a)", "(b)", "(c)"]
    electives = next(section for section in data["sections"] if section["marker"].startswith("4"))
    biomedical = next(group for group in electives["subsections"] if "Biomedical Intelligence" in group["title"])
    assert [group["title"].split(" (")[0] for group in biomedical["subsections"][:2]] == ["Required Courses", "Elective Courses"]
    assert biomedical["subsections"][2]["title"].startswith("Remaining units can be chosen")
    assert required["units"] == "28"
    assert not biomedical["subsections"][0]["text"][0].startswith("Required Courses")
    general = next(group for group in electives["subsections"] if group["marker"] == "(a)")
    assert any(group["title"].startswith("Remaining units can be chosen") for group in general["subsections"])


def test_biomed_expands_csci_groups_with_a_section_level_course_table():
    data = json.loads((JSON_DIR / "B.Eng._in_Biomedical_Engineering.json").read_text(encoding="utf-8"))
    elective = next(section for section in data["sections"] if section["marker"].startswith("4"))
    section_csci = next(group for group in elective["subsections"] if group["title"] == "CSCI Courses")
    assert section_csci["units"] == "max. 3"
    assert section_csci["codes"] and all(code.startswith("CSCI ") for code in section_csci["codes"])
    assert not section_csci.get("embed_in_parent_table")
    streams_intro = next(group for group in elective["subsections"] if group["title"] == "Streams")
    assert streams_intro["hide_course_table"] is True
    assert streams_intro["units"] == "18"
    named_streams = streams_intro["subsections"]
    assert len(named_streams) == 3
    for stream in named_streams:
        elective_group = next(group for group in stream["subsections"] if group["title"] == "Elective Courses")
        csci_group = next(group for group in elective_group["subsections"] if group["title"] == "CSCI Courses")
        assert csci_group["embed_in_parent_table"] is True
        assert csci_group["collapse_course_table"] is True
        assert csci_group["codes"] and all(code.startswith("CSCI ") for code in csci_group["codes"])

    page = BeautifulSoup((SITE_DIR / "majors" / "B.Eng._in_Biomedical_Engineering.html").read_text(encoding="utf-8"), "html.parser")
    csci_headings = [tag for tag in page.find_all(["h3", "h4"]) if tag.get_text(strip=True).startswith("CSCI Courses")]
    section_heading = next(tag for tag in csci_headings if "depth-0" in tag.parent.get("class", []))
    assert section_heading.find_next_sibling("details", class_="course-details") is not None
    embedded_heading = next(tag for tag in csci_headings if tag is not section_heading)
    parent_details = embedded_heading.find_parent("details", class_="course-details")
    embedded_details = embedded_heading.find_next_sibling("details", class_="course-details")
    assert parent_details is not None
    assert embedded_details is not None and embedded_details is not parent_details
    assert not embedded_details.has_attr("open")


def test_computer_engineering_resolves_remaining_unit_course_groups():
    data = json.loads((JSON_DIR / "B.Eng._in_Computer_Engineering.json").read_text(encoding="utf-8"))
    assert data["sections"][1]["units"] == "17"
    assert data["sections"][2]["units"] == "37"
    for option in data["sections"][3]["subsections"]:
        elective = option["subsections"][0]
        remaining = next(group for group in option["subsections"] if group["title"] == "Courses Eligible for Remaining Units")
        assert "ENGG 1820" in remaining["codes"]
        assert "ENGG 1820" not in elective["codes"]
        assert any(code.startswith("AIST ") for code in remaining["codes"])


def test_information_engineering_resolves_remaining_units_as_a_peer_group():
    data = json.loads((JSON_DIR / "B.Eng._in_Information_Engineering.json").read_text(encoding="utf-8"))
    elective = data["sections"][3]
    assert elective["subsections"][0]["title"].startswith("Out of the 16")
    remaining = elective["subsections"][1]
    assert remaining["title"] == "The Remaining Units"
    assert remaining["codes"]
    assert all(re.fullmatch(r"[A-Z]{4} [3-9]\d{3}", code) for code in remaining["codes"])


def test_later_programmes_keep_roman_and_area_groups_indented():
    fintech = json.loads((JSON_DIR / "B.Eng._in_Financial_Technology.json").read_text(encoding="utf-8"))
    assert [(section["title"], section["units"]) for section in fintech["sections"]] == [
        ("Faculty Package", "9"),
        ("Foundation Courses", "13"),
        ("Required Courses", "39"),
        ("Elective Courses", "14"),
    ]

    expected_ranges = {
        "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme.json": ("6-15", "12-21"),
        "B.Eng._in_Materials_Science_and_Engineering_X_Double_Major_Programme.json": ("6-15", "12-21"),
        "B.Sc._in_Aerospace_Science_and_Earth_Informatics_X_Double_Major_Programme.json": ("6-9", "12-15"),
    }
    for filename, ranges in expected_ranges.items():
        data = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
        assert data["sections"][1]["title"] == "1st Major Required Courses"
        choices = data["sections"][2]
        assert choices["title"] == "Major Choices"
        assert choices["units"] == "60"
        for choice in choices["subsections"]:
            assert choice["units"] == "60"
            elective, second_major = choice["subsections"]
            assert [elective["marker"], second_major["marker"]] == ["(a)", "(b)"]
            assert second_major["title"] == "2nd Major Requirements"
            assert second_major["units"] == "33"
            assert elective["title"] == "1st Major Elective Courses"
            group_units = {group["title"]: group["units"] for group in elective["subsections"] if group["title"] in {"Group A", "Group B"}}
            assert group_units == {"Group A": ranges[0], "Group B": ranges[1]}

    cds = json.loads((JSON_DIR / "B.Sc._in_Computational_Data_Science.json").read_text(encoding="utf-8"))
    medicine = next(group for group in cds["sections"][4]["subsections"] if group["title"] == "Computational Medicine")
    medicine_electives = next(group for group in medicine["subsections"] if group["title"] == "Elective Courses")
    assert [group["marker"] for group in medicine_electives["subsections"]] == ["(i)", "(ii)"]
    for option in cds["sections"][4]["subsections"][1:]:
        remaining = [group for group in option["subsections"] if (group["title"] or " ".join(group["text"])).startswith("Remaining units can be chosen")]
        assert len(remaining) == 1
        assert all(
            not any(str(text).startswith("Remaining units can be chosen") for text in group.get("text", []))
            for group in walk_test_groups(option["subsections"]) if group is not remaining[0]
        )

    cs = json.loads((JSON_DIR / "B.Sc._in_Computer_Science.json").read_text(encoding="utf-8"))
    general_cs = cs["sections"][3]["subsections"][0]
    assert not general_cs["codes"]
    general_elective = next(group for group in general_cs["subsections"] if group["title"] == "Elective Courses")
    broad_pool = next(group for group in general_elective["subsections"] if group["title"] == "AIST/CENG/CSCI Courses")
    assert {"AIST", "CENG", "CSCI"} <= {code[:4] for code in broad_pool["codes"]}
    assert len(broad_pool["codes"]) > 100
    intelligence = next(group for group in cs["sections"][3]["subsections"] if "Intelligence Science" in group["title"])
    intelligence_electives = next(group for group in intelligence["subsections"] if group["title"] == "Elective Courses")
    assert [group["title"] for group in intelligence_electives["subsections"]] == [
        "Choose at least 9 units from the following",
        "Remaining units can be chosen from the following",
    ]
    for stream in cs["sections"][3]["subsections"][1:]:
        elective_groups = [group for group in stream.get("subsections", []) if group["title"].startswith("Elective")]
        remaining = [group for elective in elective_groups for group in elective.get("subsections", []) if group["title"].startswith("Remaining")]
        if remaining:
            assert all(any(code.startswith("AIST ") for code in group["codes"]) for group in remaining)
            assert all(any(code.startswith("CSCI ") for code in group["codes"]) for group in remaining)

    mae = json.loads((JSON_DIR / "B.Eng._in_Mechanical_and_Automation_Engineering.json").read_text(encoding="utf-8"))
    assert not mae["sections"][3]["codes"]
    stream_names = {"Design and Manufacturing", "Mechatronics", "Robotics and Automation"}
    stream_heading = next(group for group in mae["sections"][3]["subsections"]
                          if group["title"] == "Streams")
    streams = [group for group in stream_heading["subsections"] if group["title"] in stream_names]
    assert len(streams) == 3
    assert all([child["marker"] for child in stream["subsections"]] == ["(a)", "(b)"] for stream in streams)


def test_ida_and_math_ie_area_hierarchies_are_flattened_and_resolved():
    ida = json.loads((JSON_DIR / "B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme.json").read_text(encoding="utf-8"))
    assert ida["sections"][1]["title"] == "1st Major Required Courses"
    choices = ida["sections"][2]
    first_major_electives = choices["subsections"][0]["subsections"][0]
    assert {group["title"]: group["units"] for group in first_major_electives["subsections"]} == {
        "Group A": "6-15", "Group B": "12-21"}

    information_choice = next(choice for choice in choices["subsections"] if "Information Engineering" in choice["title"])
    group_b = next(group for group in information_choice["subsections"][0]["subsections"] if group["title"] == "Group B")
    assert [group["title"] or group["text"][0] for group in group_b["subsections"]] == [
        "Courses offered by CUHK",
        "Students can also take the following elective courses offered by CUHK(SZ) to fulfill the requirements of Group B",
    ]
    assert len(group_b["subsections"][0]["text"]) == 1
    assert group_b["subsections"][1]["title"].startswith("Students can also take")
    assert group_b["subsections"][1]["text"][0].startswith("DDA4210")

    mie = json.loads((JSON_DIR / "B.Sc._in_Mathematics_and_Information_Engineering.json").read_text(encoding="utf-8"))
    elective = mie["sections"][2]
    expected_areas = [
        "Artificial Intelligence, Machine Learning, Computer Vision",
        "Theoretical Topics in Information Sciences",
        "Theoretical Mathematics",
        "Applied Mathematics",
        "Communications",
        "Software Engineering and Data Science",
        "Cyber Security and Applied Cryptography",
        "Internet Engineering and Networks",
        "Hardware",
        "Software and Professional Practice",
        "Additional Eligible Courses",
    ]
    assert [group["title"] for group in elective["subsections"]] == expected_areas
    assert all(group["codes"] for group in elective["subsections"])
    assert not elective["codes"]
    assert elective["text"] == ["Direct-admission students complete 9 units; students admitted via the Faculty of Science complete 6 units."]


def test_elite_stream_is_generated_as_a_sidebar_programme():
    elite = json.loads((JSON_DIR / "Engineering_ELITE_Stream.json").read_text(encoding="utf-8"))
    assert elite["total_units"] == "15"
    assert len(elite["sections"]) == 3
    assert any(code.startswith("ESTR ") for code in programme_codes(elite))
    research = elite["sections"][2]
    assert research["units"] == "6"
    assert research["codes"] == ["ESTR 4998", "ESTR 4999"]


def test_medicine_science_and_cross_campus_structures_are_recovered():
    biomedical = json.loads((JSON_DIR / "B.Sc._in_Biomedical_Sciences.json").read_text(encoding="utf-8"))
    choice = biomedical["sections"][2]["subsections"][0]
    assert biomedical["sections"][2]["units"] == "32"
    assert [area["title"] for area in choice["subsections"]] == [
        "Concentration Area A: Biomedical Research[d]",
        "Concentration Area B: Strategic Management and Entrepreneurship",
        "Concentration Area C: Health Services and Consultation",
    ]
    assert [area["units"] for area in choice["subsections"]] == ["14", "15", "14"]

    for filename, section_position in (("B.Sc._in_Community_Health_Practice.json", 1), ("B.Sc._in_Public_Health.json", 2)):
        programme = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
        groups = programme["sections"][section_position]["subsections"]
        assert [item["title"].split(" (")[0] for item in groups] == ["Group A", "Group B"]
        assert all(item["codes"] or item["subsections"] for item in groups)

    pharmacy = json.loads((JSON_DIR / "Bachelor_of_Pharmacy.json").read_text(encoding="utf-8"))
    areas = pharmacy["sections"][2]["subsections"][0]["subsections"]
    assert [area["title"] for area in areas] == [
        "Area of Concentration: Pharmacy Clerkship", "Area of Concentration: Research"
    ]

    biochemistry = json.loads((JSON_DIR / "B.Sc._in_Biochemistry.json").read_text(encoding="utf-8"))
    package = biochemistry["sections"][0]["subsections"]
    assert [item["title"] for item in package] == ["Group A", "Group B", "A course from the following"]
    assert [item["title"] for item in package[-1]["subsections"]] == ["Group C", "Group D", "Group E"]
    lists = biochemistry["sections"][2]["subsections"][1]["subsections"]
    assert [item["title"] for item in lists] == ["List A", "List B", "List C"]

    biology = json.loads((JSON_DIR / "B.Sc._in_Biology.json").read_text(encoding="utf-8"))
    biology_electives = biology["sections"][2]["subsections"][1]
    assert biology["sections"][2]["subsections"][0]["title"] == ""
    assert "BIOL 3710" in biology_electives["codes"] and "FNSC 3710" not in biology_electives["codes"]

    star = json.loads((JSON_DIR / "Science_STAR_Stream.json").read_text(encoding="utf-8"))
    assert star["total_units"] == "12" and any(code.startswith("STAR ") for code in programme_codes(star))
    science_programmes = [item for item in load_programmes() if item.get("faculty") == "Science" and item["source_file"] != "Science_STAR_Stream"]
    assert all(not any("Research Stream" in block["title"] for block in item.get("additional_requirements", [])) for item in science_programmes)

    double = json.loads((JSON_DIR / "B.Sc._in_Mathematical_Sciences_and_Artificial_Intelligence_Double_Major_Programme.json").read_text(encoding="utf-8"))
    campus_titles = [item["title"] for item in walk_test_groups(double["sections"]) if item["title"].startswith("Courses offered by")]
    assert "Courses offered by CUHK" in campus_titles and "Courses offered by CUHK(SZ)" in campus_titles
    assert all(not re.search(r"[A-Z]{3,4}\s*\d{4}", item["title"]) for item in walk_test_groups(double["sections"]))

    articulated = json.loads((JSON_DIR / "Articulated_Bachelor_of_Science_Ph.D._Programme_in_Mathematical_Sciences.json").read_text(encoding="utf-8"))
    bachelor = articulated["sections"][0]
    assert bachelor["title"] == "Bachelor of Science in Mathematical Sciences"
    item_i = bachelor["subsections"][2]["subsections"][0]["subsections"][0]
    assert [item["marker"] for item in item_i["subsections"]] == [f"({number})" for number in range(1, 8)]
    assert all(not item["title"] and item["text"] for item in item_i["subsections"])
    assert [block["total_units"] for block in articulated["additional_requirements"]] == ["27", "78"]


def test_declared_option_stream_and_elective_units_are_displayed_without_summing():
    option_totals = {
        "B.Eng._in_Artificial_Intelligence_Systems_and_Technologies.json": "22",
        "B.Eng._in_Computer_Engineering.json": "12",
        "B.Sc._in_Computational_Data_Science.json": "18",
        "B.Sc._in_Computer_Science.json": "17",
    }
    for filename, units in option_totals.items():
        data = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
        section = next(section for section in data["sections"] if section["marker"].rstrip(".") in {"4", "5"})
        assert all(option["units"] == units for option in section["subsections"])

    named_stream_totals = {
        "B.Eng._in_Biomedical_Engineering.json": ({"Medical Instrumentation and Biosensors"}, "18"),
        "B.Eng._in_Energy_and_Environmental_Engineering.json": ({"Sustainable Energy Technology"}, "12"),
        "B.Eng._in_Information_Engineering.json": ({"Telecommunications"}, "12"),
        "B.Eng._in_Mechanical_and_Automation_Engineering.json": ({"Mechatronics"}, "12"),
        "B.Eng._in_Systems_Engineering_and_Engineering_Management.json": ({"Decision Analytics"}, "18"),
    }
    for filename, (titles, units) in named_stream_totals.items():
        data = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
        groups = list(walk_test_groups(data["sections"][-1]["subsections"]))
        assert all(next(group for group in groups if group["title"] == title)["units"] == units for title in titles)

    mae = json.loads((JSON_DIR / "B.Eng._in_Mechanical_and_Automation_Engineering.json").read_text(encoding="utf-8"))
    mae_units = {group["title"]: group["units"] for group in mae["sections"][3]["subsections"]}
    assert mae_units["Breadth Electives (at least 6 units chosen from the following courses)"] == "6"
    assert mae_units["Depth Electives (at least 6 units chosen from the following courses)"] == "6"

    cs = json.loads((JSON_DIR / "B.Sc._in_Computer_Science.json").read_text(encoding="utf-8"))
    general_electives = cs["sections"][3]["subsections"][0]["subsections"][0]
    assert general_electives["units"] == "17"

    cds = json.loads((JSON_DIR / "B.Sc._in_Computational_Data_Science.json").read_text(encoding="utf-8"))
    medicine = next(group for group in cds["sections"][4]["subsections"] if group["title"] == "Computational Medicine")
    electives = next(group for group in medicine["subsections"] if group["title"] == "Elective Courses")
    assert electives["units"] == ""
    assert [group["units"] for group in electives["subsections"]] == ["6", "3"]


def test_arts_examples_are_structured_as_readable_nested_requirements():
    anthropology = json.loads((JSON_DIR / "B.A._in_Anthropology.json").read_text(encoding="utf-8"))
    concentrations = anthropology["supplementary_note_sections"][0]["subsections"]
    assert [group["title"] for group in concentrations] == [
        "Archaeology and Cultural Heritage",
        "Tourism and Cultural Representation",
        "Globalization, Economy and Power",
        "Chinese Cultures and Societies",
        "Values, Beliefs and Worldviews",
        "Health and the Body",
    ]
    assert all(group["force_course_table"] and group["codes"] for group in concentrations)

    bimodal = json.loads((JSON_DIR / "B.A._in_Bimodal_Bilingual_Studies.json").read_text(encoding="utf-8"))
    required = bimodal["sections"][0]
    assert required["units"] == "36"
    sign_language = next(group for group in required["subsections"] if group["marker"] == "(c)")
    assert sign_language["units"] == "18"
    assert [group["marker"] for group in sign_language["subsections"]] == ["(i)", "(ii)", "(iii)"]
    assert [group["units"] for group in sign_language["subsections"]] == ["6", "6", "6"]
    elective = bimodal["sections"][1]
    assert [group["marker"] for group in elective["subsections"]] == ["(a)", "(b)", "(c)"]
    assert [group["marker"] for group in elective["subsections"][1]["subsections"]] == ["(i)", "(ii)"]

    chinese = json.loads((JSON_DIR / "B.A._in_Chinese_Language_and_Literature.json").read_text(encoding="utf-8"))
    assert chinese["total_units"] == "66"
    # Keep the explanatory notes in the first Major Programme Requirement box,
    # including its cross-major exemption notes, but never parse a second
    # programme-requirement box from farther down the source page.
    assert len(chinese["notes"]) == 3
    assert chinese.get("additional_requirements", []) == []
    speciality = chinese["sections"][2]["subsections"][0]
    assert speciality["title"] == "Speciality courses"
    assert [group["marker"] for group in speciality["subsections"]] == ["(1)", "(2)", "(3)", "(4)"]


def test_compound_word_table_rows_and_derived_units_are_recovered():
    history = json.loads((JSON_DIR / "B.A._in_History.json").read_text(encoding="utf-8"))
    elective = history["sections"][2]
    assert [(group["marker"], group["units"]) for group in elective["subsections"][:2]] == [("(a)", "6"), ("(b)", "9")]

    combined = json.loads((JSON_DIR / "B.A._(Chinese_Language_Studies)_and_B.Ed._(Chinese_Language_Education).json").read_text(encoding="utf-8"))
    required = combined["sections"][1]
    assert required["units"] == "78"
    education = required["subsections"][1]
    assert education["title"] == "Chinese Language Education" and education["units"] == "47"
    methodology = education["subsections"][0]
    assert methodology["title"] == "Language Teaching Methodology" and methodology["units"] == "17"
    assert [group["marker"] for group in methodology["subsections"]] == ["(a)", "(b)", "(c)", "(d)", "(e)"]

    for programme in load_programmes():
        if programme.get("parse_status") == "unavailable":
            continue
        missing = {(programme["source_file"], section["marker"]) for section in programme["sections"] if not section.get("units")}
        assert missing <= {("M.B.,_Ch.B", "3."), ("Science_STAR_Stream", "2.")}, programme["title"]


def test_every_explicit_pre_total_source_course_survives_parsing():
    records = json.loads((HTML_DIR / "_programmes.json").read_text(encoding="utf-8"))
    programmes = {programme["source_file"]: programme for programme in load_programmes()}
    for record in records:
        programme = programmes[record["stem"]]
        if programme.get("parse_status") == "unavailable":
            continue
        soup = BeautifulSoup(
            (HTML_DIR / "full_pages" / f"{record['stem']}.html").read_text(encoding="utf-8"),
            "html.parser",
        )
        table = choose_requirement_table(soup, record["admission_code"])
        source_codes = set()
        reached_total = False
        for row in direct_rows(table):
            for cells in logical_row_cells(row):
                text = " ".join(cell for cell in cells if cell)
                if re.search(r"\bTotal\s*:", text, re.IGNORECASE):
                    reached_total = True
                    break
                source_codes.update(extract_course_codes(text))
            if reached_total:
                break
        exclusions = {code for group in walk_test_groups(programme["sections"]) for code in group.get("excluded_codes", [])}
        assert source_codes <= set(programme_codes(programme)) | exclusions, record["title"]


def test_generated_pages_include_requested_course_fields_only():
    pages = sorted((SITE_DIR / "majors").glob("*.html"))
    assert len(pages) == 89
    sample = pages[0].read_text(encoding="utf-8")
    assert "Term 1" in sample and "Term 2" in sample
    assert "T1 Teaching schedule" in sample
    assert "T2 Teaching schedule" in sample
    assert "Enrolment information" in sample
    assert 'id="tableSettings"' in sample
    assert 'data-table-setting="prerequisites"' in sample
    assert 'data-table-setting="unavailable"' in sample
    assert "applyTableSettings()" in sample
    assert "cell.colSpan=visibleColumns" in sample
    assert "cell.colSpan=Math.max(1,visibleColumns-1)" in sample
    assert '<details class="enrol">' not in sample
    assert "checker" not in sample.lower()
    placeholder = '<p class="meta">Course requirement</p>'
    assert all(placeholder not in page.read_text(encoding="utf-8") for page in pages)
    assert "Engineering_ELITE_Stream.html" in sample


def test_term_1_schedule_groups_sections_and_deduplicates_meeting_times():
    rendered = format_schedule([
        {"term": "2026-27 Term 1", "section": "A-LEC", "timetable": [
            {"day_time": "Mo 12:30PM - 2:15PM"},
            {"day_time": "Mo 12:30PM - 2:15PM"},
            {"day_time": "Th 3:30PM - 4:15PM"},
        ]},
        {"term": "2026-27 Term 2", "section": "B-LEC", "timetable": [
            {"day_time": "Tu 9:30AM - 11:15AM"},
        ]},
    ], 1)
    assert rendered.count("A-LEC") == 1
    assert rendered.count("Mo 12:30PM - 2:15PM") == 1
    assert "Th 3:30PM - 4:15PM" in rendered
    assert "B-LEC" not in rendered


def test_generated_index_and_sidebar_links_resolve():
    index = BeautifulSoup((SITE_DIR / "index.html").read_text(encoding="utf-8"), "html.parser")
    card_links = [link.get("href") for link in index.select(".card-grid > a")]
    assert len(card_links) == 89
    assert all((SITE_DIR / href).is_file() for href in card_links)
    assert {heading.get_text(strip=True) for heading in index.find_all("h2")} == {
        "Arts", "Business Administration", "Education", "Engineering", "Law",
        "Medicine", "Others", "Science", "Social Science",
    }

    for page in (SITE_DIR / "majors").glob("*.html"):
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        assert soup.find("h1") is not None
        for link in soup.select(".sidebar a, .page-nav a"):
            assert (page.parent / link["href"]).is_file(), (page.name, link["href"])


def test_nonstandard_medicine_degree_is_fully_transcribed():
    page = (SITE_DIR / "majors" / "M.B.,_Ch.B.html").read_text(encoding="utf-8")
    assert "six-year undergraduate professional programme" in page
    assert "Recommended Course Pattern" in page
    assert "MBChB Global Physician-Leadership Stream" in page
    assert "Explanatory Notes" in page


def test_generated_pages_include_vercel_analytics():
    pages = [SITE_DIR / "index.html", *sorted((SITE_DIR / "majors").glob("*.html"))]
    assert pages
    for page in pages:
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        analytics = soup.find("script", src="/_vercel/insights/script.js")
        assert analytics is not None
        assert analytics.has_attr("defer")


def test_enrolment_information_has_no_leading_spacing():
    sample = next((SITE_DIR / "majors").glob("*.html")).read_text(encoding="utf-8")
    assert ".enrol-text { margin:0;" in sample
    assert ".enrol-text { margin-top:" not in sample
    assert ".prereq-indent { text-indent:0; }" in sample


def test_enrolment_information_splits_numbered_points_onto_new_lines():
    info = (
        "1. Pre-requisites: ENGG1110/ESTR1002 or with course instructor's "
        "approval. 2. Not for students who have taken SEEM3650 or SEEM4480."
    )
    soup = BeautifulSoup(format_info(info), "html.parser")
    lines = [line.get_text() for line in soup.select(".prereq-sentence")]
    assert lines == [
        "1. Pre-requisites: ENGG1110/ESTR1002 or with course instructor's approval.",
        "2. Not for students who have taken SEEM3650 or SEEM4480.",
    ]


def test_enrolment_information_splits_unpunctuated_exclusion_onto_new_line():
    info = (
        "Pre-requisite: ENGG1120/ESTR1005 or MATH1510 "
        "Not for students who have taken AIST3010 or ESTR3114"
    )
    soup = BeautifulSoup(format_info(info), "html.parser")
    lines = [line.get_text() for line in soup.select(".prereq-sentence")]
    assert lines == [
        "Pre-requisite: ENGG1120/ESTR1005 or MATH1510.",
        "Not for students who have taken AIST3010 or ESTR3114.",
    ]


def test_enrolment_information_uses_minor_page_line_break_rules():
    info = (
        "Pre-requisite: CSCI2040. Co-requisite: ENGG1000; "
        "Course Exclusion: TEST1000; or TEST1001"
    )
    soup = BeautifulSoup(format_info(info), "html.parser")
    lines = [line.get_text() for line in soup.select(".prereq-sentence")]
    assert lines == [
        "Pre-requisite: CSCI2040.",
        "Co-requisite: ENGG1000;",
        "Course Exclusion: TEST1000; or TEST1001.",
    ]


def test_sidebar_is_collapsible_and_content_uses_wide_layout_on_all_devices():
    sample = next((SITE_DIR / "majors").glob("*.html")).read_text(encoding="utf-8")
    soup = BeautifulSoup(sample, "html.parser")
    button = soup.find("button", class_="sidebar-toggle")
    sidebar = soup.find("aside", id="majorSidebar")
    assert button is not None and button.get("aria-controls") == "majorSidebar"
    assert button.get("aria-expanded") == "false"
    assert sidebar is not None and sidebar.get("aria-hidden") == "true"
    assert ".sidebar-toggle { display:block;" in sample
    assert ".sidebar nav { min-width:max-content; }" in sample
    assert "white-space:nowrap; overflow:hidden; text-overflow:ellipsis" not in sample
    assert "max-width:1800px" in sample
    assert "padding:16px clamp(42px,6vw,96px)" in sample
    assert ".content-inner { padding:0 30px 12px; }" in sample
    assert ".sidebar { width:calc(100vw - 100px);" in sample
    assert "grid-template-columns:auto minmax(0,1fr)" in sample
    assert ".bar-controls { grid-column:1 / -1; width:100%;" in sample
    assert ".breadcrumb { overflow:visible; white-space:normal; overflow-wrap:anywhere; }" in sample
    assert "text-overflow:ellipsis" not in sample

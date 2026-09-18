import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from major_extraction.generate_major_json import extract_course_codes, choose_requirement_table
from major_extraction.generate_major_site import linked_text
from major_extraction.major_readability import walk, source_areas

ROOT = Path(__file__).resolve().parents[2]
JSON = ROOT / "major_extraction/major_json/2026_27"
SITE = ROOT / "site/major/2026_27/majors"
SOURCE = ROOT / "major_extraction/major_html/2026_27/full_pages"


def load(stem):
    return json.loads((JSON / f"{stem}.json").read_text(encoding="utf-8"))


def codes(groups):
    return {code for item in walk(groups) for code in item["codes"]}


def test_english_and_fine_arts_split_intro_lists_and_streams():
    english = load("B.A._in_English")["sections"][2]
    assert english["text"][0] == "Any twelve courses from the following:"
    assert english["text"][1].startswith("ENGE1520")
    stream = english["subsections"][0]
    assert stream["title"] == "Creative Writing in English Stream"
    assert len(stream["subsections"][0]["codes"]) == 2
    assert len(stream["subsections"][1]["codes"]) == 7
    art = load("B.A._in_Fine_Arts")["sections"][2]
    assert not art["codes"]
    assert [s["title"] for s in art["subsections"][:3]] == ["Art History Stream", "Studio Art Stream", "Art History and Studio Art Stream"]
    assert len(art["subsections"][0]["subsections"][0]["subsections"]) == 2


def test_history_pool_respects_prior_requirements_and_minima():
    data = load("B.A._in_History")
    elective = data["sections"][2]
    additional = next(item for item in elective["subsections"] if item["title"] == "Other Eligible History Courses")
    assert len(additional["codes"]) > 30
    assert not set(additional["codes"]) & codes(data["sections"][:2])
    assert not set(additional["codes"]) & codes(elective["subsections"][:2])
    assert any({"ANTH 2310", "ANTH 2340"} <= set(extract_course_codes(note["text"])) for note in data["notes"])


def test_exclusions_are_not_eligible_linguistics_courses():
    elective = load("B.A._in_Linguistics")["sections"][2]
    a, b = elective["subsections"]
    assert len(a["course_groups"]) == 3
    assert not {"LING 3405", "LING 3406"} & codes([a])
    assert {"LING 3101", "BMBL 3003", "LING 4402"} <= codes([a])
    assert not {"FREN 1001", "GERM 1001", "HKSL 1001", "KORE 1001", "SPAN 1001", "FREN 1100", "HKSL 1100"} & codes([b])
    assert {"FREN 1000", "HKSL 1000", "JASP 1450"} <= codes([b])


def test_music_uses_published_areas_and_preserves_conditional_choices():
    data = load("B.A._in_Music")
    elective = data["sections"][2]
    assert len(elective["subsections"]) == 7
    assert not {"MUSC 1001", "MUSC 2552", "MUSC 1212"} & codes([elective])
    assert {"MUSC 3323", "MUSC 1011", "MUSC 4613"} <= codes([elective])
    areas = source_areas(SOURCE / "B.A._in_Music.html", extract_course_codes)
    assert codes([elective]) <= codes(areas)
    assert len(data["sections"][1]["subsections"][-1]["subsections"]) == 3


def test_star_stream_is_a_standalone_programme_with_units_and_experiential_requirement():
    stream = load("Science_STAR_Stream")
    assert stream["total_units"] == "12"
    assert [g["units"] for g in stream["sections"][0]["subsections"]] == ["3", "6", "3"]
    assert {"STAR 2000", "STAR 3000", "STAR 4000", "STAR 2050", "STAR 3050", "STAR 4050"} <= codes(stream["sections"])
    assert "4 consecutive weeks" in " ".join(stream["sections"][1]["text"])
    cmb = load("B.Sc._in_Cell_and_Molecular_Biology")
    assert not any("Research Stream" in block["title"] for block in cmb.get("additional_requirements", []))


def test_long_headings_and_intros_render_as_separate_boxes():
    data = load("B.A._in_Japanese_Studies")
    requirement = data["sections"][1]["subsections"][1]
    assert requirement["title"] == "For Standard Scheme Only. Not for Local Study Scheme"
    page = BeautifulSoup((SITE / "B.A._in_English.html").read_text(encoding="utf-8"), "html.parser")
    intro = page.find("p", string="Any twelve courses from the following:")
    assert intro is not None and "section" in intro.parent.get("class", [])
    assert "ENGE1520" in intro.parent.get_text()
    cmb = (SITE / "B.Sc._in_Cell_and_Molecular_Biology.html").read_text(encoding="utf-8")
    star = (SITE / "Science_STAR_Stream.html").read_text(encoding="utf-8")
    assert "Science, Technology And Research Stream" not in cmb
    assert "Science, Technology and Research (STAR) Stream" in star and "STAR 4000" in star


def test_course_extractor_does_not_treat_levels_as_abbreviated_codes():
    assert extract_course_codes("JASP1470, 1480 and courses at 3000 or 4000 level") == ["JASP 1470", "JASP 1480"]
    assert extract_course_codes("FINA2010, RMSC, 4001, 4003") == ["FINA 2010", "RMSC 4001", "RMSC 4003"]


def test_external_links_and_faculty_order_are_preserved_in_generated_html():
    url = "https://www.cuhk.edu.hk/clear/download/IPL-Researchskills.pdf"
    assert f'href="{url}"' in linked_text(url + ".")
    index = BeautifulSoup((ROOT / "site/major/2026_27/index.html").read_text(encoding="utf-8"), "html.parser")
    assert [heading.get_text(" ", strip=True) for heading in index.find_all("h2")][-1] == "Others"
    mbchb = BeautifulSoup((SITE / "M.B.,_Ch.B.html").read_text(encoding="utf-8"), "html.parser")
    assert not mbchb.select(".note-subsection .subsection-copy")


def test_all_programmes_keep_exclusions_out_of_tables_and_long_text_out_of_headings():
    for path in JSON.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        roots = data["sections"] + [section for block in data.get("additional_requirements", []) for section in block["sections"]]
        for item in walk(roots):
            # A few explicitly requested Integrated BBA option headings are
            # long source instructions but still need to remain headings.
            if not (path.name == "B.Sc._in_Statistics.json" and item["title"].startswith("Eight courses from the following")):
                assert len(item["title"]) <= 180, (path.name, item["title"])
            assert not set(item.get("excluded_codes", [])) & set(item["codes"]), (path.name, item["title"])


def test_japanese_local_scheme_uses_parallel_stream_groups():
    data = load("B.A._in_Japanese_Studies")
    assert not data["additional_requirements"]
    elective = data["sections"][2]
    assert elective["text"][0].startswith("Students may choose")
    assert [group["title"] for group in elective["subsections"][:2]] == ["Without Stream", "With Stream"]
    assert [group["units"] for group in elective["subsections"][:2]] == ["6 or 24", "12 or 24"]
    assert [group["title"] for group in elective["subsections"][0]["subsections"][:2]] == ["Standard Scheme", "Local Study Scheme"]
    streams = elective["subsections"][1]["subsections"][2:]
    assert [g["marker"] for g in streams] == ["(i)", "(ii)", "(iii)"]
    assert all(g["subsections"] for g in streams)
    requirement_b = data["sections"][1]["subsections"][1]
    assert requirement_b["text"] and "resident study in Japan" in requirement_b["text"][0]


def test_attached_readability_corrections_and_note_layouts():
    anthropology = load("B.A._in_Anthropology")
    assert not any(g.get("title") == "Voluntary Concentrations" for n in anthropology["notes"] for g in n["subsections"])
    voluntary = anthropology["supplementary_note_sections"][0]
    assert voluntary["title"] == "Voluntary Concentrations" and len(voluntary["subsections"]) == 6

    bimodal = load("B.A._in_Bimodal_Bilingual_Studies")
    assert [len(n.get("paragraphs", [])) for n in bimodal["notes"][1:]] == [3, 4]

    chinese = load("B.A._in_Chinese_Studies")
    assert [g["title"] for g in chinese["sections"][1]["subsections"][1]["subsections"]] == [
        "International Stream (IS)", "Chinese Native Stream (CNSS)"]

    art = load("B.A._in_Fine_Arts")
    assert len(art["description_lines"]) == 6
    assert len(art["sections"][1]["subsections"]) == 3
    assert not any("Additional Art History" in g["title"] for g in art["sections"][2]["subsections"])
    history = load("B.A._in_History")
    assert not any("Additional Anthropology" in g["title"] for g in history["sections"][2]["subsections"])

    japanese = load("B.A._in_Japanese_Studies")
    assert japanese["sections"][2]["text"][0].startswith("Students may choose")
    business = japanese["sections"][2]["subsections"][1]["subsections"][2]
    assert business["subsections"][-1]["title"] == "Non-credit bearing internship programme (optional)"

    linguistics = load("B.A._in_Linguistics")
    assert [g["marker"] for g in linguistics["sections"][1]["subsections"]] == ["(a)", "(b)", "(c)"]
    music = load("B.A._in_Music")
    assert not any(g["title"].startswith("Area 1:") for g in music["sections"][2]["subsections"])


def test_science_streams_and_faculty_packages_are_complete_and_structured():
    earth = load("B.Sc._in_Earth_and_Environmental_Sciences")
    assert not earth["additional_requirements"]
    assert [item["marker"] for item in earth["sections"][1]["subsections"]] == ["(a)", "(b)", "(c)", "(d)", "(e)"]
    section_a_choices = earth["sections"][2]["subsections"][:4]
    assert section_a_choices[0]["marker"] == "(a)"
    assert all(not item["marker"] for item in section_a_choices[1:])
    assert [item["title"] for item in section_a_choices] == [
        "Without Stream", "Atmospheric Science Stream", "Geology and Geophysics Stream",
        "Environmental Science and Technology Stream"]
    assert [item["title"] for item in section_a_choices[0]["subsections"]] == [
        "Category A", "Category B", "Category C"]
    for path in JSON.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("faculty") != "Science":
            continue
        roots = data.get("sections", []) + [item for block in data.get("additional_requirements", []) for item in block["sections"]]
        for package in (item for item in roots if "Faculty Package" in item.get("title", "")):
            labels = [item["title"] for item in walk(package.get("subsections", []))]
            assert sum(bool(re.fullmatch(r"Group [A-E]", label)) for label in labels) >= 3

    natural = load("B.Sc._in_Natural_Sciences")
    assert not natural["additional_requirements"]
    assert len(natural["sections"]) == 7
    assert all(any(child["title"] in {"Required Courses", "Elective Courses[a]"} for child in section["subsections"])
               for section in natural["sections"])
    for stream in natural["sections"][1:]:
        elective = next(child for child in stream["subsections"] if child["title"].startswith("Elective Courses"))
        assert [item["title"] for item in elective["subsections"]] == [
            "Concentration Area Courses", "Other Science Courses"]
        assert all(item["codes"] for item in elective["subsections"])
    physics = load("B.Sc._in_Physics")
    assert physics["sections"][1]["subsections"][0]["title"] == "Physics courses"
    assert len(next(block for block in physics["additional_requirements"] if block["title"] == "Streams")["sections"]) == 4


def test_social_science_concentrations_and_requested_headings():
    global_communication = load("B.S.Sc._in_Global_Communication")
    assert [item["marker"] for item in global_communication["sections"][2]["subsections"]] == [
        "(i)", "(ii)", "(iii)", "(iv)", "(v)",
    ]
    global_studies = load("B.S.Sc._in_Global_Studies")
    language = next(item for item in global_studies["sections"][1]["subsections"] if item["marker"] == "(c)")
    assert language["force_course_table"] and len(language["codes"]) > 10

    for stem, count in [("B.S.Sc._in_Economics", 5), ("B.S.Sc._in_Geography_and_Resource_Management", 5),
                        ("B.S.Sc._in_Psychology", 6), ("B.S.Sc._in_Sociology", 4),
                        ("B.S.Sc._in_Urban_Studies", 4)]:
        data = load(stem)
        concentration = next(block for block in data["additional_requirements"] if block["title"].startswith("Concentration"))
        assert concentration["placement"] == "before_notes" and len(concentration["sections"]) == count

    journalism = load("B.S.Sc._in_Journalism_and_Communication")
    assert [item["title"] for item in journalism["sections"][1]["subsections"][1]["subsections"]] == [
        "Chinese Journalism", "English Journalism", "Integrated Strategic Communication", "Creative Media Laboratory",
    ]


def test_humanities_area_hierarchy_and_theology_course_exclusions():
    philosophy = load("B.A._in_Philosophy")
    assert len(philosophy["notes"]) == 4
    assert [g["units"] for g in philosophy["sections"][2]["subsections"][:3]] == ["min. 6"] * 3
    assert philosophy["sections"][2]["subsections"][-1]["units"] == "max. 6"

    public = load("B.A._in_Public_Humanities")
    assert [item["marker"] for item in public["sections"][2]["subsections"]] == ["(a)", "(b)", "(c)"]
    assert [item["title"] for item in public["sections"][2]["subsections"]] == [
        "Standard Scheme", "Standard Scheme", "One course from Religious Studies Areas[a]"]
    standard_rule = public["sections"][2]["subsections"][1]["subsections"][0]
    assert "Nine courses" in standard_rule["text"][0]
    assert all(not concentration["subsections"]
               for item in public["sections"][2]["subsections"][:2]
               for concentration in item["subsections"][1:])
    assert all(concentration["text"]
               for item in public["sections"][2]["subsections"][:2]
               for concentration in item["subsections"][1:])
    religious = load("B.A._in_Religious_Studies")
    assert [item["title"] for item in religious["sections"][2]["subsections"]] == [
        "Without Concentrations", "Concentrations"]
    assert [item["marker"] for item in religious["sections"][2]["subsections"][0]["subsections"]] == ["(a)", "(b)"]
    for item in walk(religious["sections"]):
        if "from Religious Studies Areas" in item["title"] or "from the Religious Studies Areas" in " ".join(item["text"]):
            assert item.get("course_groups")

    theology = load("B.A._in_Theology")
    assert len(theology["sections"][1]["text"]) == 2
    assert [g["label"].split(":", 1)[0] for g in theology["sections"][2]["subsections"][0]["course_groups"]] == ["Area 2", "Area 4", "Area 5"]
    required_codes = codes([theology["sections"][1]])
    theo_options = next(g for g in walk(theology["sections"]) if g["title"] == "THEO Course Options")
    assert not required_codes & set(theo_options["codes"])


def test_selected_faculty_package_and_english_text_share_one_box():
    stems = [
        "B.A._in_Chinese_Language_and_Literature", "B.A._in_Chinese_Studies",
        "B.A._in_Japanese_Studies", "B.A._in_Linguistics", "B.A._in_Public_Humanities",
        "B.A._in_Religious_Studies", "B.A._in_Translation",
    ]
    assert all(load(stem)["sections"][0]["combine_text_boxes"] for stem in stems)
    assert load("B.A._in_English")["sections"][2]["combine_text_boxes"]


def test_business_programme_hierarchies_streams_and_second_degree():
    for stem in ["B.B.A._-_Integrated_BBA_Programme", "B.B.A._(Integrated_BBA_Programme)_and_Juris_Doctor"]:
        data = load(stem)
        elective = next(section for section in data["sections"] if "Elective Courses (Concentration)" in section["title"])
        assert [group["marker"] for group in elective["subsections"][-2:]] == ["(h)", "(i)"]
        assert [group["marker"] for group in elective["subsections"][-2]["subsections"]] == ["(i)", "(ii)"]
        assert [group["marker"] for group in elective["subsections"][-1]["subsections"]] == ["(i)", "(ii)"]
    joint = load("B.B.A._(Integrated_BBA_Programme)_and_Juris_Doctor")
    jd = next(block for block in joint["additional_requirements"] if block["title"] == "2nd Degree: Juris Doctor")
    assert [section["marker"] for section in jd["sections"]] == ["1.", "2."]
    assert jd["total_units"] == "72" and len(jd["notes"]) == 8
    assert not any(note["text"].startswith("Required Courses:") for note in joint["notes"])

    accountancy = load("B.B.A._in_Professional_Accountancy")
    assert accountancy["sections"][2]["title"] == "Elective Courses"
    assert accountancy["sections"][1]["units"] == "51 or 54"
    assert [group["title"] for group in accountancy["sections"][2]["subsections"]] == [
        "Without Stream",
        "Global Tax and Governance Stream", "Finance for Accountants Stream",
        "Accounting Analytics Stream", "Global Accounting Stream",
    ]
    assert not accountancy["additional_requirements"]


def test_business_and_interdisciplinary_heading_rules():
    behm = load("B.Sc._in_Biotechnology,_Entrepreneurship_and_Healthcare_Management")
    for concentration in behm["sections"][2]["subsections"][1:]:
        assert [group["title"] for group in concentration["subsections"]] == ["Required Courses", "Elective Courses"]

    ida = load("B.Sc._in_Interdisciplinary_Data_Analytics_X_Double_Major_Programme")
    offering_labels = [item for item in walk(ida["sections"]) if item.get("title", "").startswith("Students can also take")]
    assert offering_labels and all(item.get("keep_heading") for item in offering_labels)

    qfin = load("B.Sc._in_Quantitative_Finance")
    required_e = next(item for item in qfin["sections"][2]["subsections"] if item["marker"] == "(e)")
    assert not required_e["title"] and required_e["text"][0].startswith("{DOTE2011")
    business = next(item for item in qfin["sections"][3]["subsections"] if item["marker"] == "(b)")
    assert business["title"].startswith("At least 12 units of Business courses") and business["keep_heading"]


def test_every_source_with_explanatory_notes_has_parsed_notes():
    records = json.loads((ROOT / "major_extraction/major_html/2026_27/_programmes.json").read_text(encoding="utf-8"))
    for record in records:
        data = load(record["stem"])
        source_path = ROOT / "major_extraction/major_html/2026_27" / record["full_page_file"]
        soup = BeautifulSoup(source_path.read_text(encoding="utf-8"), "html.parser")
        if data.get("parse_status") == "unavailable":
            continue
        source = choose_requirement_table(soup, record["admission_code"]).get_text(" ", strip=True).lower()
        if "explanatory note" in source:
            assert data["notes"], record["stem"]


def test_education_programmes_recover_published_headings_and_units():
    english = load("B.A._(English_Studies)_and_B.Ed._(English_Language_Education)")
    assert [note["marker"] for note in english["notes"][:2]] == ["1.", "2."]

    childhood = load("B.Ed._in_Early_Childhood_Education")
    required = childhood["sections"][1]
    assert required["units"] == "56"
    assert [(item["title"], item["units"]) for item in required["subsections"]] == [
        ("Core Courses in Early Childhood Education", "40"),
        ("Research Experience", "6"),
        ("Teaching Practice", "10"),
    ]

    mathematics = load("B.Ed._in_Mathematics_and_Mathematics_Education")
    assert [item["title"] for item in mathematics["sections"][0]["subsections"]] == [
        "Faculty of Education", "Faculty of Science",
    ]
    subject = mathematics["sections"][2]["subsections"][0]
    assert subject["title"] == "Subject Knowledge"
    option_ii = next(item for item in walk([subject]) if item["marker"] == "(II)")
    assert len(option_ii["subsections"]) == 4
    assert all(item["codes"] for item in option_ii["subsections"])


def test_engineering_labels_notes_and_admission_variants_are_structured():
    for stem in ["B.Eng._in_Computer_Engineering", "B.Sc._in_Computer_Science"]:
        choice = load(stem)["sections"][1]["subsections"][0]
        assert [item["title"].split("[")[0] for item in choice["subsections"]] == [
            "Chemistry Courses", "Life Science Courses", "Physics Courses",
        ]

    for stem, markers in [
        ("B.Eng._in_Artificial_Intelligence_Systems_and_Technologies", ["(i)", "(ii)", "(iii)", "(iv)"]),
        ("B.Eng._in_Biomedical_Engineering", ["(i)", "(ii)", "(iii)", "(iv)"]),
    ]:
        first_letter_note = next(note for note in load(stem)["notes"] if note["marker"] == "[a]")
        assert [item["marker"] for item in first_letter_note["subsections"]] == markers

    electronic = load("B.Eng._in_Electronic_Engineering")
    guidance = next(note for note in electronic["notes"] if note["marker"] == "3.")
    assert [item["title"] for item in guidance["subsections"]] == [
        "Professional Engineering", "Research", "Entrepreneurship",
    ]

    for stem in [
        "B.Eng._in_Energy_and_Environmental_Engineering",
        "B.Eng._in_Information_Engineering",
        "B.Eng._in_Mechanical_and_Automation_Engineering",
    ]:
        assert any(item["title"] == "Streams" for item in walk(load(stem)["sections"]))

    computational = load("B.Sc._in_Computational_Data_Science")
    assert computational["sections"][4]["subsections"][0]["title"] == "Computational Data Science"

    mie = load("B.Sc._in_Mathematics_and_Information_Engineering")
    assert not mie["additional_requirements"]
    assert [group["marker"] for group in mie["sections"][0]["subsections"]] == ["(a)", "(b)", "(c)", "(d)"]
    science = mie["sections"][0]["subsections"][3]["subsections"][0]
    assert science["title"] == "Science Faculty Package" and science["subsections"]
    assert [group["units"] for group in mie["sections"][0]["subsections"][2:]] == ["6", "9"]
    assert mie["sections"][2]["units"] == "6 or 9"


def test_latest_cross_faculty_readability_fixes_are_source_backed():
    exercise = load("B.Sc._in_Exercise_Science_and_Health_Education")["sections"][1]
    assert all(item["subsections"] for item in exercise["subsections"])

    earth = load("B.Sc._in_Earth_and_Environmental_Sciences")
    assert earth["sections"][1]["units"] == "16-18 or 30-33"
    elective = earth["sections"][2]
    for marker in ("(a)", "(b)"):
        without = next(item for item in elective["subsections"] if item["marker"] == marker)
        assert without["title"] == "Without Stream"
    assert elective["subsections"][0]["text"][0].startswith("Six courses")
    capstone = next(item for item in elective["subsections"] if item["marker"] == "(c)")
    option_iii = capstone["subsections"][2]
    assert not option_iii["title"]
    assert option_iii["text"] == ["6 units from 3(b) section of the stream chosen"]
    assert not option_iii["codes"] and not option_iii["subsections"]
    other = next(item for item in elective["subsections"] if item["marker"] == "(d)")
    assert [(item["title"], item["units"]) for item in other["subsections"][:2]] == [
        ("Without Stream", "9-12"), ("With Stream", "5-6")]
    assert len(other["subsections"]) == 3
    assert len(other["subsections"][2]["codes"]) > 100

    mathematics = load("B.Sc._in_Mathematics")
    streams = {item["title"]: item for item in mathematics["sections"][2]["subsections"]}
    computational = next(item for item in streams["Computational and Applied Mathematics Stream"]["subsections"] if item["marker"] == "(ii)")
    assert {"MATH 3215", "MATH 3320", "MATH 4230", "MATH 4280"} <= set(computational["codes"])
    for stream, marker in (("Mathematics Stream", "(ii)"), ("Mathematics-Multidisciplinary Stream", "(i)")):
        item = next(item for item in streams[stream]["subsections"] if item["marker"] == marker)
        expected = ["Science Courses", "Engineering Courses", "Economics and Finance Courses"]
        if stream == "Mathematics Stream":
            expected.insert(0, "BMED Courses at 3000 or above level")
        assert [group["title"] for group in item["subsections"]] == expected
    mathematics_choice = next(item for item in streams["Mathematics Stream"]["subsections"] if item["marker"] == "(ii)")
    assert all(code.startswith("BMED ") and int(code.split()[1][0]) >= 3
               for code in mathematics_choice["subsections"][0]["codes"])
    assert not any(code.startswith("BMED ") for code in mathematics_choice["subsections"][1]["codes"])
    enrichment_e = next(item for item in streams["Enrichment Stream"]["subsections"] if item["marker"] == "(e)")
    assert not enrichment_e["title"] and enrichment_e["text"]

    public = load("B.A._in_Public_Humanities")["sections"][2]
    for item in public["subsections"][:2]:
        assert item["title"] == "Standard Scheme"
        assert [child["title"] for child in item["subsections"][1:]] == [
            "Cultural Management Concentration", "Cultural Studies Concentration"]
        assert all(not child["subsections"] for child in item["subsections"][1:])

    risk = load("B.Sc._in_Risk_Management_Science")
    package_choice = next(item for item in walk(risk["sections"][0]["subsections"])
                          if item["title"] == "One course from the following")
    assert [item["title"] for item in package_choice["subsections"]][-2:] == [
        "Group D", "Courses from Faculty Package of the Faculty of Business Administration"]
    assert "minimum of 72 units" not in json.dumps(risk["notes"])

    statistics = load("B.Sc._in_Statistics")
    analytics = next(item for item in statistics["sections"][2]["subsections"]
                     if item["title"] == "Data Analytics Stream")
    assert analytics["subsections"][0]["text"]

    sociology = load("B.S.Sc._in_Sociology")
    block = next(item for item in sociology["additional_requirements"] if item["title"] == "Concentration Area")
    assert [item["units"] for item in block["sections"]] == ["18", "24", "15", "18"]
    assert [item["units"] for item in block["sections"][-1]["subsections"]] == ["6", "9"]


def test_diplomacy_and_law_nested_labels_match_the_source_hierarchy():
    diplomacy = load("B.S.Sc._in_Diplomacy_and_International_Studies")
    core = diplomacy["sections"][1]["subsections"][0]
    assert len(core["subsections"]) == 8
    assert all(item["title"].startswith("Core ") and item["codes"] for item in core["subsections"])
    assert [item["title"] for item in diplomacy["sections"][2]["subsections"][1:]] == [
        "Area 1: Intercultural and Interpersonal Competence",
        "Area 2: Area Studies",
        "Area 3: Diplomatic Policy Analysis and International Cooperation",
        "Area 4: International Law and International Dispute Resolution",
    ]

    law = load("LL.B._-_Bachelor_of_Laws_Programme")
    streams = law["sections"][1]["subsections"][0]
    assert streams["title"] == "Streams"
    assert [item["title"] for item in streams["subsections"]] == ["Chinese Law", "Global Law"]
    assert all([item["marker"] for item in stream["subsections"]] == ["(a)", "(b)"] for stream in streams["subsections"])

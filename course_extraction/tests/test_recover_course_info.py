import json

from course_extraction import recover_course_info_from_html as recovery


def _write_manifest(path, subject, course_count, courses, complete):
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps({
            "capture_schema_version": 1,
            "subject": subject,
            "course_count": course_count,
            "courses": courses,
            "complete": complete,
        }),
        encoding="utf-8",
    )


def test_complete_capture_requires_every_course_record(tmp_path):
    capture = tmp_path / "TEST"
    _write_manifest(capture, "TEST", 2, [], complete=True)

    assert recovery._is_complete_capture(capture, "TEST") is False


def test_recovery_falls_back_to_complete_archived_capture(tmp_path, monkeypatch):
    promoted = tmp_path / "TEST"
    archived = tmp_path / "_incomplete" / "TEST_timestamp"
    _write_manifest(promoted, "TEST", 1, [], complete=False)
    _write_manifest(
        archived,
        "TEST",
        1,
        [{"code": "TEST 1000", "complete": True}],
        complete=True,
    )
    expected = [{"code": "TEST 1000"}]

    monkeypatch.setattr(recovery, "COURSE_HTML_DIR", tmp_path)
    monkeypatch.setattr(recovery, "parse_saved_subject", lambda path: expected)

    courses, source, errors = recovery.recover_subject(
        "TEST", {"TEST": [archived]}
    )

    assert courses == expected
    assert source == archived
    assert errors == [f"{promoted}: incomplete capture"]


def test_partial_capture_can_document_an_upstream_term_error(tmp_path, monkeypatch):
    html_root = tmp_path / "course_html"
    info_root = tmp_path / "course_info"
    source = html_root / "_incomplete" / "TEST_timestamp"
    course_dir = source / "courses" / "0000"
    course_dir.mkdir(parents=True)
    (course_dir / "course.html").write_text(
        """
        <span id="uc_course_lbl_course">TEST 1000 - Test Course</span>
        <span id="uc_course_lbl_units">3.00</span>
        <select id="uc_course_ddl_class_term">
          <option value="2430">2026-27 Term 2</option>
        </select>
        """,
        encoding="utf-8",
    )
    record = {
        "capture_schema_version": 1,
        "course_index": 0,
        "code": "TEST 1000",
        "course_page": "course.html",
        "terms": [{
            "term_code": "2430",
            "term": "2026-27 Term 2",
            "schedule_page": "terms/000_2430.html",
            "sections": [],
        }],
        "complete": False,
    }
    (course_dir / "capture.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    _write_manifest(source, "TEST", 1, [], complete=False)

    monkeypatch.setattr(recovery, "COURSE_HTML_DIR", html_root)
    monkeypatch.setattr(recovery, "COURSE_INFO_DIR", info_root)
    reason = "Upstream Show Sections page returns an error."

    subject, courses, destination = recovery.promote_partial_capture(
        source, {("TEST 1000", "2430"): reason}
    )

    assert subject == "TEST"
    assert destination == html_root / "TEST"
    assert courses[0]["term_1"] is False
    assert courses[0]["term_2"] is True
    assert courses[0]["sections"] == []
    assert courses[0]["term_offerings"] == [{
        "term_code": "2430",
        "term": "2026-27 Term 2",
        "offered": True,
        "retrieval_error": reason,
    }]
    assert json.loads((info_root / "TEST.json").read_text(encoding="utf-8")) == courses

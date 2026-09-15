import os
import stat

from course_extraction import get_course_info as scraper


def test_remove_capture_tree_retries_read_only_entries(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    saved_page = capture / "course.html"
    saved_page.write_text("saved", encoding="utf-8")
    os.chmod(saved_page, stat.S_IREAD)
    os.chmod(capture, stat.S_IREAD)

    scraper._remove_capture_tree(capture)

    assert not capture.exists()


def test_published_capture_survives_nonfatal_backup_cleanup_error(
    tmp_path, monkeypatch, capsys
):
    incomplete = tmp_path / "_incomplete"
    staging = incomplete / "TEST_timestamp"
    final = tmp_path / "TEST"
    staging.mkdir(parents=True)
    final.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    (final / "old.txt").write_text("old", encoding="utf-8")

    def locked_backup(_path):
        raise PermissionError("simulated OneDrive lock")

    monkeypatch.setattr(scraper, "_remove_capture_tree", locked_backup)

    scraper._publish_subject_capture(staging, final)

    assert (final / "new.txt").read_text(encoding="utf-8") == "new"
    assert (incomplete / "_previous_TEST" / "old.txt").exists()
    assert "Warning: could not remove old raw snapshot" in capsys.readouterr().out

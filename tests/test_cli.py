import json
from pathlib import Path

from evernote_refinery.cli import main


def test_cli_count_prints_note_count(capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    exit_code = main(["count", str(fixture)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "notes: 1" in captured.out


def test_cli_export_writes_markdown_json_csv_outputs(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    exit_code = main(["export", str(fixture), "--output", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "exported notes: 1" in captured.out
    assert (tmp_path / "index.csv").exists()
    assert list((tmp_path / "notes").glob("*.md"))
    assert list((tmp_path / "metadata").glob("*.json"))
    assert list((tmp_path / "assets").iterdir())


def test_cli_export_writes_summary_report(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    exit_code = main(["export", str(fixture), "--output", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "summary: " in captured.out
    assert "failed notes: 0" in captured.out
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["total_notes"] == 1
    assert summary["exported_notes"] == 1
    assert summary["failed_notes"] == 0
    assert summary["expected_attachments"] == 1
    assert summary["written_attachments"] == 1


def test_cli_export_writes_processing_log_by_default(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    exit_code = main(["export", str(fixture), "--output", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "log: " in captured.out
    events = [json.loads(line) for line in (tmp_path / "export.log").read_text().splitlines()]
    assert events[0]["event"] == "export_started"
    assert events[-1]["event"] == "export_finished"


def test_cli_export_accepts_custom_log_file(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"
    log_path = tmp_path / "logs" / "run.jsonl"

    exit_code = main(["export", str(fixture), "--output", str(tmp_path / "out"), "--log-file", str(log_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"log: {log_path}" in captured.out
    assert log_path.exists()


def test_cli_export_resume_uses_checkpoint_to_skip_completed_notes(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    first_exit = main(["export", str(fixture), "--output", str(tmp_path), "--resume"])
    first_capture = capsys.readouterr()
    second_exit = main(["export", str(fixture), "--output", str(tmp_path), "--resume"])
    second_capture = capsys.readouterr()

    assert first_exit == 0
    assert "exported notes: 1" in first_capture.out
    assert second_exit == 0
    assert "exported notes: 0" in second_capture.out
    assert (tmp_path / ".evernote-refinery-checkpoint.json").exists()

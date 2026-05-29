import csv
import json
from pathlib import Path

from evernote_refinery.cli import main


def test_cli_synthetic_writes_large_test_enex(tmp_path, capsys):
    enex = tmp_path / "stress.enex"

    exit_code = main(["synthetic", str(enex), "--notes", "25", "--attachments-per-note", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "synthetic notes: 25" in captured.out
    assert "synthetic attachments: 50" in captured.out
    assert enex.exists()
    assert main(["count", str(enex)]) == 0
    count_capture = capsys.readouterr()
    assert "notes: 25" in count_capture.out

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


def _ai_vault_cli_fixture(tmp_path: Path) -> Path:
    canonical = tmp_path / "canonical"
    export_dir = canonical / "exports" / "00.行動區" / "$工作" / "策略"
    notes_dir = export_dir / "notes"
    metadata_dir = export_dir / "metadata"
    notes_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    (notes_dir / "策略.md").write_text("AI Vault CLI fixture", encoding="utf-8")
    (metadata_dir / "策略.json").write_text("{}", encoding="utf-8")
    rows = [
        {
            "source_enex": "/input/00.行動區/$工作/策略.enex",
            "output_dir": str(export_dir),
            "title": "策略",
            "created": "20250101T000000Z",
            "updated": "20250102T000000Z",
            "tags": "alpha",
            "markdown_path": "notes/策略.md",
            "metadata_path": "metadata/策略.json",
            "word_count": "3",
            "resource_count": "0",
            "has_attachments": "false",
            "has_tasks": "false",
            "has_encrypted_content": "false",
        },
        {
            "source_enex": "/input/Trash/舊垃圾.enex",
            "output_dir": str(canonical / "exports" / "Trash" / "舊垃圾"),
            "title": "舊垃圾",
            "created": "20240101T000000Z",
            "updated": "20240102T000000Z",
            "tags": "trash",
            "markdown_path": "notes/舊垃圾.md",
            "metadata_path": "metadata/舊垃圾.json",
            "word_count": "5",
            "resource_count": "0",
            "has_attachments": "false",
            "has_tasks": "false",
            "has_encrypted_content": "false",
        },
    ]
    canonical.mkdir(exist_ok=True)
    with (canonical / "aggregate_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (canonical / "aggregate_summary.json").write_text(json.dumps({"notes_exported": 2}), encoding="utf-8")
    return canonical


def test_cli_ai_vault_writes_local_prototype_outputs(tmp_path, capsys):
    canonical = _ai_vault_cli_fixture(tmp_path)
    output = tmp_path / "prototype"

    exit_code = main(["ai-vault", str(canonical), "--output", str(output), "--sample-size", "20"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AI Vault prototype output:" in captured.out
    assert "draft rows: 1" in captured.out
    assert (output / "main_knowledge_map.json").exists()
    assert (output / "trash_safety_map.json").exists()
    assert (output / "source_index.csv").exists()
    assert (output / "ai_vault_draft_sample.csv").exists()
    assert (output / "source_readonly_audit.json").exists()

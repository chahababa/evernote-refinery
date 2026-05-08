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

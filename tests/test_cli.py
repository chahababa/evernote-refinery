from pathlib import Path

from evernote_refinery.cli import main


def test_cli_count_prints_note_count(capsys):
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    exit_code = main(["count", str(fixture)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "notes: 1" in captured.out

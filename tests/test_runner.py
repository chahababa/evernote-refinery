import csv
import json
from pathlib import Path

from evernote_refinery.parser import Note
from evernote_refinery.runner import export_enex


def _write_enex(path: Path, titles: list[str]) -> None:
    notes = []
    for index, title in enumerate(titles, start=1):
        notes.append(
            f"""
  <note>
    <title>{title}</title>
    <created>2024010{index}T000000Z</created>
    <updated>2024010{index}T010000Z</updated>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
<en-note><div>{title} body</div></en-note>]]></content>
    <tag>demo</tag>
  </note>"""
        )
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>"""
        + "".join(notes)
        + """
</en-export>
""",
        encoding="utf-8",
    )


def test_export_enex_writes_reconciliation_summary(tmp_path):
    enex = tmp_path / "two-notes.enex"
    _write_enex(enex, ["First note", "Second note"])

    result = export_enex(enex, tmp_path / "out")

    assert result.total_notes == 2
    assert result.exported_notes == 2
    assert result.failed_notes == 0
    assert result.skipped_notes == 0
    assert result.summary_path == "summary.json"

    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary == {
        "total_notes": 2,
        "exported_notes": 2,
        "failed_notes": 0,
        "skipped_notes": 0,
        "expected_attachments": 0,
        "written_attachments": 0,
        "failures": [],
    }

    rows = list(csv.DictReader((tmp_path / "out" / "index.csv").open()))
    assert [row["title"] for row in rows] == ["First note", "Second note"]


def test_export_enex_writes_processing_log(tmp_path):
    enex = tmp_path / "two-notes.enex"
    _write_enex(enex, ["First note", "Second note"])

    result = export_enex(enex, tmp_path / "out", log_path=tmp_path / "out" / "export.log")

    assert result.log_path == "export.log"
    events = [json.loads(line) for line in (tmp_path / "out" / "export.log").read_text().splitlines()]
    assert [event["event"] for event in events] == ["export_started", "note_exported", "note_exported", "export_finished"]
    assert events[0]["enex_path"] == str(enex)
    assert events[1]["title"] == "First note"
    assert events[2]["title"] == "Second note"
    assert events[-1]["total_notes"] == 2
    assert events[-1]["exported_notes"] == 2
    assert events[-1]["failed_notes"] == 0


def test_export_enex_isolates_failed_notes_and_keeps_exporting(tmp_path):
    enex = tmp_path / "three-notes.enex"
    _write_enex(enex, ["Good one", "Bad one", "Good two"])

    def build_note(note: Note, output_dir: Path, checkpoint_key: str | None = None):
        if note.title == "Bad one":
            raise ValueError("simulated conversion failure")
        from evernote_refinery.export import build_note_export

        return build_note_export(note, output_dir, checkpoint_key=checkpoint_key)

    result = export_enex(enex, tmp_path / "out", build_note=build_note)

    assert result.total_notes == 3
    assert result.exported_notes == 2
    assert result.failed_notes == 1
    assert result.skipped_notes == 0

    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["failures"] == [
        {
            "title": "Bad one",
            "created": "20240102T000000Z",
            "error_type": "ValueError",
            "error": "simulated conversion failure",
        }
    ]

    failed_report = json.loads((tmp_path / "out" / "failed" / "failures.json").read_text())
    assert failed_report == summary["failures"]

    rows = list(csv.DictReader((tmp_path / "out" / "index.csv").open()))
    assert [row["title"] for row in rows] == ["Good one", "Good two"]

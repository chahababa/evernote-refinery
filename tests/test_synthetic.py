import base64
import csv
import json

from evernote_refinery.runner import export_enex
from evernote_refinery.synthetic import write_synthetic_enex


def test_write_synthetic_enex_creates_many_parseable_notes(tmp_path):
    enex = tmp_path / "synthetic.enex"

    result = write_synthetic_enex(enex, note_count=12, attachments_per_note=1)

    assert result.note_count == 12
    assert result.attachment_count == 12
    assert enex.exists()
    content = enex.read_text(encoding="utf-8")
    assert content.count("<note>") == 12
    assert "Synthetic note 0012" in content
    assert base64.b64encode(b"synthetic attachment 12-1").decode("ascii") in content


def test_synthetic_enex_exports_with_reconciliation_and_logs(tmp_path):
    enex = tmp_path / "synthetic.enex"
    write_synthetic_enex(enex, note_count=30, attachments_per_note=1)

    result = export_enex(enex, tmp_path / "out", log_path=tmp_path / "out" / "export.log")

    assert result.total_notes == 30
    assert result.exported_notes == 30
    assert result.failed_notes == 0
    assert result.expected_attachments == 30
    assert result.written_attachments == 30

    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["total_notes"] == 30
    assert summary["exported_notes"] == 30
    assert summary["expected_attachments"] == 30
    assert summary["written_attachments"] == 30

    rows = list(csv.DictReader((tmp_path / "out" / "index.csv").open(encoding="utf-8")))
    assert len(rows) == 30
    assert rows[0]["title"] == "Synthetic note 0001"
    assert rows[-1]["title"] == "Synthetic note 0030"

    first_markdown = (tmp_path / "out" / rows[0]["markdown_path"]).read_text(encoding="utf-8")
    assert "missing attachment" not in first_markdown
    assert "assets/" in first_markdown

    events = [json.loads(line) for line in (tmp_path / "out" / "export.log").read_text(encoding="utf-8").splitlines()]
    assert events[0]["event"] == "export_started"
    assert events[-1]["event"] == "export_finished"
    assert sum(1 for event in events if event["event"] == "note_exported") == 30

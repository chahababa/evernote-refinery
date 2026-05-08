from evernote_refinery.checkpoint import Checkpoint, note_checkpoint_key
from evernote_refinery.export import build_exports_from_enex
from evernote_refinery.parser import parse_enex
from evernote_refinery.writers import write_exports


def test_export_pipeline_skips_completed_notes_when_checkpoint_is_provided(tmp_path):
    fixture = "tests/fixtures/simple.enex"
    note = next(parse_enex(fixture))
    checkpoint = Checkpoint(tmp_path / ".evernote-refinery-checkpoint.json")
    checkpoint.mark_completed(note_checkpoint_key(note))

    exports = list(build_exports_from_enex(fixture, tmp_path, checkpoint=checkpoint))

    assert exports == []
    assert not (tmp_path / "assets").exists()


def test_write_exports_marks_checkpoint_after_successful_note_write(tmp_path):
    fixture = "tests/fixtures/simple.enex"
    note = next(parse_enex(fixture))
    checkpoint = Checkpoint(tmp_path / ".evernote-refinery-checkpoint.json")
    exports = build_exports_from_enex(fixture, tmp_path, checkpoint=checkpoint)

    result = write_exports(exports, tmp_path, checkpoint=checkpoint)

    assert result.note_count == 1
    assert checkpoint.is_completed(note_checkpoint_key(note)) is True

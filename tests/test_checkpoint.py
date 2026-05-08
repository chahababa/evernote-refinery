import json

from evernote_refinery.checkpoint import Checkpoint, note_checkpoint_key
from evernote_refinery.parser import Note


def test_checkpoint_records_completed_notes(tmp_path):
    path = tmp_path / ".evernote-refinery-checkpoint.json"
    checkpoint = Checkpoint(path)

    checkpoint.mark_completed("note-1")
    checkpoint.mark_completed("note-2")

    reloaded = Checkpoint(path)
    assert reloaded.is_completed("note-1") is True
    assert reloaded.is_completed("note-2") is True
    assert reloaded.is_completed("note-3") is False
    assert json.loads(path.read_text()) == {"completed_note_keys": ["note-1", "note-2"]}


def test_note_checkpoint_key_is_stable_for_same_note_content():
    first = Note(
        title="Breakfast SOP",
        created="20240102T030405Z",
        updated="20240103T040506Z",
        tags=["work"],
        content="<en-note>Hello</en-note>",
        resources=[],
    )
    second = Note(
        title="Breakfast SOP",
        created="20240102T030405Z",
        updated="20240103T040506Z",
        tags=["work"],
        content="<en-note>Hello</en-note>",
        resources=[],
    )

    assert note_checkpoint_key(first) == note_checkpoint_key(second)
    assert len(note_checkpoint_key(first)) == 64

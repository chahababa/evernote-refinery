import csv
import json

from evernote_refinery.attachments import AttachmentWriteResult
from evernote_refinery.export import NoteExport
from evernote_refinery.writers import write_exports


def test_write_exports_writes_markdown_json_and_csv_index(tmp_path):
    export = NoteExport(
        title="Trip note",
        markdown="# Trip note\n\nHello Evernote.",
        metadata={
            "title": "Trip note",
            "created": "20260426010101Z",
            "updated": "20260427020202Z",
            "tags": ["travel", "evernote"],
            "resource_count": 1,
        },
        features={
            "word_count": 3,
            "tag_count": 2,
            "resource_count": 1,
            "has_attachments": True,
            "has_encrypted_content": False,
            "has_tasks": False,
        },
        attachments=AttachmentWriteResult(
            paths_by_hash={"abc123": "assets/abc123-photo.png"},
            mime_types_by_hash={"abc123": "image/png"},
        ),
    )

    result = write_exports([export], tmp_path)

    assert result.markdown_paths == ["notes/20260426010101Z-trip-note.md"]
    assert result.metadata_paths == ["metadata/20260426010101Z-trip-note.json"]
    assert result.index_path == "index.csv"
    assert result.note_count == 1
    assert (tmp_path / "notes" / "20260426010101Z-trip-note.md").read_text() == "# Trip note\n\nHello Evernote."

    metadata = json.loads((tmp_path / "metadata" / "20260426010101Z-trip-note.json").read_text())
    assert metadata == {
        "metadata": export.metadata,
        "features": export.features,
        "attachments": {
            "paths_by_hash": {"abc123": "assets/abc123-photo.png"},
            "mime_types_by_hash": {"abc123": "image/png"},
        },
        "markdown_path": "notes/20260426010101Z-trip-note.md",
    }

    rows = list(csv.DictReader((tmp_path / "index.csv").open()))
    assert rows == [
        {
            "title": "Trip note",
            "created": "20260426010101Z",
            "updated": "20260427020202Z",
            "tags": "travel;evernote",
            "markdown_path": "notes/20260426010101Z-trip-note.md",
            "metadata_path": "metadata/20260426010101Z-trip-note.json",
            "word_count": "3",
            "resource_count": "1",
            "has_attachments": "true",
            "has_tasks": "false",
            "has_encrypted_content": "false",
        }
    ]


def test_write_exports_sanitizes_names_and_avoids_collisions(tmp_path):
    first = NoteExport(title="A/B: C?", markdown="first", metadata={"title": "A/B: C?"})
    second = NoteExport(title="A B C", markdown="second", metadata={"title": "A B C"})
    untitled = NoteExport(title="   ", markdown="blank", metadata={"title": "   "})

    result = write_exports([first, second, untitled], tmp_path)

    assert result.markdown_paths == [
        "notes/a-b-c.md",
        "notes/a-b-c-2.md",
        "notes/untitled.md",
    ]
    assert (tmp_path / "notes" / "a-b-c.md").read_text() == "first"
    assert (tmp_path / "notes" / "a-b-c-2.md").read_text() == "second"
    assert (tmp_path / "notes" / "untitled.md").read_text() == "blank"

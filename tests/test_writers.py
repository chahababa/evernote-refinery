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


def test_write_exports_truncates_long_stems_with_deterministic_hash_suffix(tmp_path):
    long_title = "非常長的筆記標題" * 40
    export = NoteExport(
        title=long_title,
        markdown="long note",
        metadata={"title": long_title, "created": "20260526010101Z"},
    )

    result = write_exports([export], tmp_path)

    markdown_rel = result.markdown_paths[0]
    metadata_rel = result.metadata_paths[0]
    markdown_name = markdown_rel.removeprefix("notes/")
    metadata_name = metadata_rel.removeprefix("metadata/")

    assert markdown_rel.startswith("notes/20260526010101Z-")
    assert markdown_rel.endswith(".md")
    assert metadata_rel.endswith(".json")
    assert len(markdown_name.encode("utf-8")) <= 255
    assert len(metadata_name.encode("utf-8")) <= 255
    assert markdown_name.rsplit(".", 1)[0] == metadata_name.rsplit(".", 1)[0]
    assert (tmp_path / markdown_rel).read_text() == "long note"


def test_write_exports_long_stem_collisions_stay_bounded_and_unique(tmp_path):
    title = "同一個超長筆記標題" * 40
    exports = [
        NoteExport(title=title, markdown="first", metadata={"title": title}),
        NoteExport(title=title, markdown="second", metadata={"title": title}),
    ]

    result = write_exports(exports, tmp_path)

    assert len(set(result.markdown_paths)) == 2
    for markdown_rel in result.markdown_paths:
        assert len(markdown_rel.removeprefix("notes/").encode("utf-8")) <= 255


def test_write_exports_sanitizes_created_prefix_before_building_paths(tmp_path):
    export = NoteExport(
        title="Path safe",
        markdown="safe",
        metadata={"title": "Path safe", "created": "2026/05/26:01"},
    )

    result = write_exports([export], tmp_path)

    assert result.markdown_paths == ["notes/2026-05-26-01-path-safe.md"]
    assert (tmp_path / "notes" / "2026-05-26-01-path-safe.md").read_text() == "safe"

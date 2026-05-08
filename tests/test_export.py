from evernote_refinery.export import build_note_export
from evernote_refinery.parser import Note, Resource


def test_build_note_export_writes_attachments_and_builds_markdown(tmp_path):
    note = Note(
        title="Trip note",
        created="20260426010101Z",
        updated="20260427020202Z",
        tags=["travel", "evernote"],
        content='<en-note><div>Hello world from Evernote.</div><div><en-media hash="abc123"/></div></en-note>',
        resources=[
            Resource(
                mime="image/png",
                file_name="photo.png",
                data=b"fake png bytes",
                body_hash="abc123",
            )
        ],
    )

    result = build_note_export(note, tmp_path)

    assert result.title == "Trip note"
    assert result.metadata == {
        "title": "Trip note",
        "created": "20260426010101Z",
        "updated": "20260427020202Z",
        "tags": ["travel", "evernote"],
        "resource_count": 1,
    }
    assert result.attachments.paths_by_hash == {"abc123": "assets/abc123-photo.png"}
    assert (tmp_path / "assets" / "abc123-photo.png").read_bytes() == b"fake png bytes"
    assert "Hello world from Evernote." in result.markdown
    assert "![attachment: abc123](assets/abc123-photo.png)" in result.markdown


def test_build_note_export_calculates_search_features(tmp_path):
    note = Note(
        title="Encrypted task note",
        created=None,
        updated=None,
        tags=["todo"],
        content=(
            '<en-note>'
            '<div><en-todo checked="true"/>Done item</div>'
            '<div><en-crypt hint="private">SECRET</en-crypt></div>'
            '</en-note>'
        ),
        resources=[],
    )

    result = build_note_export(note, tmp_path)

    assert result.features == {
        "word_count": 6,
        "tag_count": 1,
        "resource_count": 0,
        "has_attachments": False,
        "has_encrypted_content": True,
        "has_tasks": True,
    }
    assert "SECRET" not in result.markdown
    assert "- [x] Done item" in result.markdown


def test_build_note_export_counts_cjk_text_for_search_features(tmp_path):
    note = Note(
        title="中文筆記",
        created=None,
        updated=None,
        tags=[],
        content="<en-note><div>檢查瓦斯 已完成</div></en-note>",
        resources=[],
    )

    result = build_note_export(note, tmp_path)

    assert result.features["word_count"] == 2

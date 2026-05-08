from pathlib import Path

from evernote_refinery.parser import parse_enex


def test_parse_enex_streams_note_metadata_content_tags_and_resources():
    fixture = Path(__file__).parent / "fixtures" / "simple.enex"

    notes = list(parse_enex(fixture))

    assert len(notes) == 1
    note = notes[0]
    assert note.title == "早餐店 SOP"
    assert note.created == "20240102T030405Z"
    assert note.updated == "20240103T040506Z"
    assert note.tags == ["工作", "巡店"]
    assert "<en-note>" in note.content
    assert "檢查瓦斯" in note.content
    assert len(note.resources) == 1
    resource = note.resources[0]
    assert resource.mime == "text/plain"
    assert resource.file_name == "hello.txt"
    assert resource.data == b"hello"
    assert resource.body_hash

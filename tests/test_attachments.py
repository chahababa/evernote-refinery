from evernote_refinery.attachments import write_attachments
from evernote_refinery.parser import Resource


def test_write_attachments_writes_resources_and_returns_hash_path_map(tmp_path):
    resources = [
        Resource(
            mime="image/png",
            file_name="photo.png",
            data=b"fake png bytes",
            body_hash="abc123",
        ),
        Resource(
            mime="application/pdf",
            file_name="receipt.pdf",
            data=b"fake pdf bytes",
            body_hash="def456",
        ),
    ]

    result = write_attachments(resources, tmp_path)

    assert result.paths_by_hash == {
        "abc123": "assets/abc123-photo.png",
        "def456": "assets/def456-receipt.pdf",
    }
    assert result.mime_types_by_hash == {
        "abc123": "image/png",
        "def456": "application/pdf",
    }
    assert (tmp_path / "assets" / "abc123-photo.png").read_bytes() == b"fake png bytes"
    assert (tmp_path / "assets" / "def456-receipt.pdf").read_bytes() == b"fake pdf bytes"


def test_write_attachments_sanitizes_missing_or_unsafe_file_names(tmp_path):
    resources = [
        Resource(
            mime="image/jpeg",
            file_name="../My Vacation 01.JPG",
            data=b"jpeg",
            body_hash="hash-a",
        ),
        Resource(
            mime="text/plain",
            file_name=None,
            data=b"notes",
            body_hash="hash-b",
        ),
    ]

    result = write_attachments(resources, tmp_path)

    assert result.paths_by_hash == {
        "hash-a": "assets/hash-a-My_Vacation_01.JPG",
        "hash-b": "assets/hash-b-attachment.txt",
    }
    assert (tmp_path / "assets" / "hash-a-My_Vacation_01.JPG").read_bytes() == b"jpeg"
    assert (tmp_path / "assets" / "hash-b-attachment.txt").read_bytes() == b"notes"


def test_write_attachments_deduplicates_same_hash(tmp_path):
    resources = [
        Resource(mime="text/plain", file_name="first.txt", data=b"same", body_hash="samehash"),
        Resource(mime="text/plain", file_name="second.txt", data=b"same", body_hash="samehash"),
    ]

    result = write_attachments(resources, tmp_path)

    assert result.paths_by_hash == {"samehash": "assets/samehash-first.txt"}
    assert len(list((tmp_path / "assets").iterdir())) == 1
    assert (tmp_path / "assets" / "samehash-first.txt").read_bytes() == b"same"


def test_write_attachments_truncates_long_safe_names_with_hash_suffix(tmp_path):
    body_hash = "a" * 64
    resource = Resource(
        mime="image/png",
        file_name=f"{'long_' * 80}.png",
        data=b"png",
        body_hash=body_hash,
    )

    result = write_attachments([resource], tmp_path)

    relative_path = result.paths_by_hash[body_hash]
    filename = relative_path.removeprefix("assets/")
    assert relative_path.startswith(f"assets/{body_hash}-long_")
    assert relative_path.endswith(".png")
    assert len(filename.encode("utf-8")) <= 255
    assert (tmp_path / relative_path).read_bytes() == b"png"

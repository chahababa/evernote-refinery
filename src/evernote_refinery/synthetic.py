from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class SyntheticEnexResult:
    note_count: int
    attachment_count: int
    path: str


def write_synthetic_enex(path: str | Path, *, note_count: int, attachments_per_note: int = 0) -> SyntheticEnexResult:
    """Write a deterministic ENEX file for repeatable smoke/stress tests."""

    if note_count < 0:
        raise ValueError("note_count must be >= 0")
    if attachments_per_note < 0:
        raise ValueError("attachments_per_note must be >= 0")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?>\n<en-export>\n')
        for note_index in range(1, note_count + 1):
            handle.write(_note_xml(note_index, attachments_per_note))
        handle.write("</en-export>\n")

    return SyntheticEnexResult(
        note_count=note_count,
        attachment_count=note_count * attachments_per_note,
        path=str(output_path),
    )


def _note_xml(note_index: int, attachments_per_note: int) -> str:
    title = f"Synthetic note {note_index:04d}"
    created = f"2024{((note_index - 1) % 12) + 1:02d}{((note_index - 1) % 28) + 1:02d}T000000Z"
    updated = f"2024{((note_index - 1) % 12) + 1:02d}{((note_index - 1) % 28) + 1:02d}T010000Z"
    media_tags = "".join(
        f'<div><en-media type="text/plain" hash="{_attachment_hash_placeholder(note_index, attachment_index)}" /></div>'
        for attachment_index in range(1, attachments_per_note + 1)
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">\n'
        f"<en-note><div>{escape(title)} body for stress testing.</div>{media_tags}</en-note>"
    )
    resources = "".join(_resource_xml(note_index, attachment_index) for attachment_index in range(1, attachments_per_note + 1))
    return f"""  <note>
    <title>{escape(title)}</title>
    <created>{created}</created>
    <updated>{updated}</updated>
    <content><![CDATA[{content}]]></content>
    <tag>synthetic</tag>
    <tag>stress</tag>
{resources}  </note>
"""


def _resource_xml(note_index: int, attachment_index: int) -> str:
    data = _attachment_bytes(note_index, attachment_index)
    encoded = base64.b64encode(data).decode("ascii")
    filename = f"synthetic-{note_index:04d}-{attachment_index:02d}.txt"
    return f"""    <resource>
      <data encoding="base64">{encoded}</data>
      <mime>text/plain</mime>
      <resource-attributes>
        <file-name>{filename}</file-name>
      </resource-attributes>
    </resource>
"""


def _attachment_hash_placeholder(note_index: int, attachment_index: int) -> str:
    return hashlib.sha256(_attachment_bytes(note_index, attachment_index)).hexdigest()


def _attachment_bytes(note_index: int, attachment_index: int) -> bytes:
    return f"synthetic attachment {note_index}-{attachment_index}".encode("utf-8")

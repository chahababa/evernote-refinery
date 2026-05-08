from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from evernote_refinery.attachments import AttachmentWriteResult, write_attachments
from evernote_refinery.checkpoint import Checkpoint, note_checkpoint_key
from evernote_refinery.markdown import enml_to_markdown
from evernote_refinery.parser import Note, parse_enex


@dataclass(frozen=True)
class NoteExport:
    title: str
    markdown: str
    metadata: dict[str, object] = field(default_factory=dict)
    features: dict[str, object] = field(default_factory=dict)
    attachments: AttachmentWriteResult = field(default_factory=AttachmentWriteResult)
    checkpoint_key: str | None = None


def build_exports_from_enex(
    enex_path: str | Path,
    output_dir: str | Path,
    checkpoint: Checkpoint | None = None,
) -> Iterator[NoteExport]:
    """Stream an ENEX file and yield in-memory exports for each note."""

    for note in parse_enex(enex_path):
        key = note_checkpoint_key(note)
        if checkpoint is not None and checkpoint.is_completed(key):
            continue
        yield build_note_export(note, output_dir, checkpoint_key=key)



def build_note_export(note: Note, output_dir: str | Path, checkpoint_key: str | None = None) -> NoteExport:
    """Build the in-memory export representation for a single parsed note."""

    attachments = write_attachments(note.resources, output_dir)
    markdown = enml_to_markdown(
        note.content,
        resource_paths=attachments.paths_by_hash,
        resource_mime_types=attachments.mime_types_by_hash,
    )

    metadata: dict[str, object] = {
        "title": note.title,
        "created": note.created,
        "updated": note.updated,
        "tags": list(note.tags),
        "resource_count": len(note.resources),
    }

    features: dict[str, object] = {
        "word_count": _word_count(markdown),
        "tag_count": len(note.tags),
        "resource_count": len(note.resources),
        "has_attachments": bool(note.resources),
        "has_encrypted_content": "data-evernote-encrypted" in note.content or "<en-crypt" in note.content,
        "has_tasks": "<en-todo" in note.content or "- [ ]" in markdown or "- [x]" in markdown,
    }

    return NoteExport(
        title=note.title,
        markdown=markdown,
        metadata=metadata,
        features=features,
        attachments=attachments,
        checkpoint_key=checkpoint_key,
    )


def _word_count(markdown: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", markdown))

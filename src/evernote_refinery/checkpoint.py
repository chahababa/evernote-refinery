from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evernote_refinery.parser import Note


class Checkpoint:
    """Persistent completed-note checkpoint for resumable exports."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._completed = self._load()

    def is_completed(self, note_key: str) -> bool:
        return note_key in self._completed

    def mark_completed(self, note_key: str) -> None:
        self._completed.add(note_key)
        self._save()

    @property
    def completed_note_keys(self) -> set[str]:
        return set(self._completed)

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        keys = data.get("completed_note_keys", [])
        if not isinstance(keys, list):
            return set()
        return {str(key) for key in keys}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"completed_note_keys": sorted(self._completed)}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def note_checkpoint_key(note: Note) -> str:
    """Build a stable content key for a parsed Evernote note."""

    digest = hashlib.sha256()
    for value in [note.title, note.created or "", note.updated or "", note.content]:
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    for tag in note.tags:
        digest.update(tag.encode("utf-8"))
        digest.update(b"\0")
    for resource in note.resources:
        digest.update(resource.body_hash.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()

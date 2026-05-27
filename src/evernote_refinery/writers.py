from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from evernote_refinery.checkpoint import Checkpoint
from evernote_refinery.export import NoteExport


@dataclass(frozen=True)
class ExportWriteResult:
    markdown_paths: list[str] = field(default_factory=list)
    metadata_paths: list[str] = field(default_factory=list)
    index_path: str = "index.csv"
    note_count: int = 0


def write_exports(
    exports: Iterable[NoteExport],
    output_dir: str | Path,
    checkpoint: Checkpoint | None = None,
) -> ExportWriteResult:
    """Write NoteExport records as Markdown, JSON metadata, and a CSV index."""

    output_path = Path(output_dir)
    notes_dir = output_path / "notes"
    metadata_dir = output_path / "metadata"
    notes_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    markdown_paths: list[str] = []
    metadata_paths: list[str] = []
    rows: list[dict[str, str]] = []
    used_stems: set[str] = set()

    for export in exports:
        stem = _unique_stem(_base_stem(export), used_stems)
        markdown_rel = f"notes/{stem}.md"
        metadata_rel = f"metadata/{stem}.json"

        (output_path / markdown_rel).write_text(export.markdown, encoding="utf-8")
        (output_path / metadata_rel).write_text(
            json.dumps(
                {
                    "metadata": export.metadata,
                    "features": export.features,
                    "attachments": {
                        "paths_by_hash": export.attachments.paths_by_hash,
                        "mime_types_by_hash": export.attachments.mime_types_by_hash,
                    },
                    "markdown_path": markdown_rel,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        markdown_paths.append(markdown_rel)
        metadata_paths.append(metadata_rel)
        rows.append(_index_row(export, markdown_rel, metadata_rel))
        if checkpoint is not None and export.checkpoint_key is not None:
            checkpoint.mark_completed(export.checkpoint_key)

    index_rel = "index.csv"
    with (output_path / index_rel).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return ExportWriteResult(
        markdown_paths=markdown_paths,
        metadata_paths=metadata_paths,
        index_path=index_rel,
        note_count=len(markdown_paths),
    )


_INDEX_FIELDS = [
    "title",
    "created",
    "updated",
    "tags",
    "markdown_path",
    "metadata_path",
    "word_count",
    "resource_count",
    "has_attachments",
    "has_tasks",
    "has_encrypted_content",
]

_MAX_STEM_BYTES = 180
_HASH_BYTES = 10


def _index_row(export: NoteExport, markdown_path: str, metadata_path: str) -> dict[str, str]:
    metadata = export.metadata
    features = export.features
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    return {
        "title": str(metadata.get("title") or export.title),
        "created": str(metadata.get("created") or ""),
        "updated": str(metadata.get("updated") or ""),
        "tags": ";".join(str(tag) for tag in tags),
        "markdown_path": markdown_path,
        "metadata_path": metadata_path,
        "word_count": str(features.get("word_count", "")),
        "resource_count": str(features.get("resource_count", metadata.get("resource_count", ""))),
        "has_attachments": _bool_text(features.get("has_attachments", False)),
        "has_tasks": _bool_text(features.get("has_tasks", False)),
        "has_encrypted_content": _bool_text(features.get("has_encrypted_content", False)),
    }


def _base_stem(export: NoteExport) -> str:
    title = str(export.metadata.get("title") or export.title)
    slug = _slugify(title)
    created = export.metadata.get("created")
    if created:
        return _shorten_stem(f"{_safe_prefix(str(created))}-{slug}")
    return _shorten_stem(slug)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.lower(), flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-_")
    return slug or "untitled"


def _safe_prefix(value: str) -> str:
    prefix = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    prefix = re.sub(r"-+", "-", prefix).strip("-_")
    return prefix or "undated"


def _unique_stem(base: str, used_stems: set[str]) -> str:
    stem = base
    counter = 2
    while stem in used_stems:
        stem = _append_counter(base, counter)
        counter += 1
    used_stems.add(stem)
    return stem


def _shorten_stem(stem: str, max_bytes: int = _MAX_STEM_BYTES) -> str:
    encoded = stem.encode("utf-8")
    if len(encoded) <= max_bytes:
        return stem

    digest = hashlib.sha1(encoded).hexdigest()[:_HASH_BYTES]
    suffix = f"-{digest}"
    prefix = _truncate_utf8(stem, max_bytes - len(suffix.encode("utf-8"))).strip("-_")
    if not prefix:
        prefix = "untitled"
    return f"{prefix}{suffix}"


def _append_counter(base: str, counter: int) -> str:
    return _shorten_stem(f"{base}-{counter}")


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


def _bool_text(value: object) -> str:
    return "true" if bool(value) else "false"

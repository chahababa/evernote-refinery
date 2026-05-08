from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from evernote_refinery.parser import Resource


@dataclass(frozen=True)
class AttachmentWriteResult:
    paths_by_hash: dict[str, str] = field(default_factory=dict)
    mime_types_by_hash: dict[str, str] = field(default_factory=dict)


def write_attachments(resources: Iterable[Resource], output_dir: str | Path) -> AttachmentWriteResult:
    """Write note resources under output_dir/assets and return lookup maps.

    The returned paths are POSIX-style relative paths intended for Markdown links,
    e.g. ``assets/<hash>-photo.png``.
    """

    output_path = Path(output_dir)
    assets_dir = output_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    paths_by_hash: dict[str, str] = {}
    mime_types_by_hash: dict[str, str] = {}

    for resource in resources:
        if resource.body_hash in paths_by_hash:
            continue

        safe_name = _safe_file_name(resource.file_name, resource.mime)
        relative_path = f"assets/{resource.body_hash}-{safe_name}"
        target_path = output_path / relative_path
        target_path.write_bytes(resource.data)

        paths_by_hash[resource.body_hash] = relative_path
        if resource.mime:
            mime_types_by_hash[resource.body_hash] = resource.mime

    return AttachmentWriteResult(
        paths_by_hash=paths_by_hash,
        mime_types_by_hash=mime_types_by_hash,
    )


def _safe_file_name(file_name: str | None, mime: str | None) -> str:
    raw_name = Path(file_name or "").name.strip()
    if not raw_name:
        extension = mimetypes.guess_extension(mime or "") or ".bin"
        raw_name = f"attachment{extension}"

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    if not safe_name:
        extension = mimetypes.guess_extension(mime or "") or ".bin"
        safe_name = f"attachment{extension}"
    return safe_name

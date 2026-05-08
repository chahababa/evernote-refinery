from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evernote_refinery.checkpoint import Checkpoint, note_checkpoint_key
from evernote_refinery.export import NoteExport, build_note_export
from evernote_refinery.parser import Note, parse_enex
from evernote_refinery.writers import write_exports


BuildNote = Callable[[Note, Path, str | None], NoteExport]


@dataclass(frozen=True)
class ExportRunResult:
    total_notes: int = 0
    exported_notes: int = 0
    failed_notes: int = 0
    skipped_notes: int = 0
    expected_attachments: int = 0
    written_attachments: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    summary_path: str = "summary.json"
    failed_report_path: str | None = None


def export_enex(
    enex_path: str | Path,
    output_dir: str | Path,
    *,
    checkpoint: Checkpoint | None = None,
    build_note: BuildNote = build_note_export,
) -> ExportRunResult:
    """Export an ENEX file while writing a reconciliation summary.

    A failed note is recorded in ``failed/failures.json`` and does not stop the
    rest of the export run.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    total_notes = 0
    skipped_notes = 0
    expected_attachments = 0
    exports: list[NoteExport] = []
    failures: list[dict[str, str]] = []

    for note in parse_enex(enex_path):
        total_notes += 1
        key = note_checkpoint_key(note)
        if checkpoint is not None and checkpoint.is_completed(key):
            skipped_notes += 1
            continue

        expected_attachments += len(note.resources)
        try:
            exports.append(build_note(note, output_path, key))
        except Exception as exc:  # noqa: BLE001 - failure isolation must catch per-note export errors
            failures.append(_failure_record(note, exc))

    write_result = write_exports(exports, output_path, checkpoint=checkpoint)
    written_attachments = sum(len(export.attachments.paths_by_hash) for export in exports)

    failed_report_path = None
    if failures:
        failed_dir = output_path / "failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        failed_report_path = "failed/failures.json"
        _write_json(output_path / failed_report_path, failures)

    result = ExportRunResult(
        total_notes=total_notes,
        exported_notes=write_result.note_count,
        failed_notes=len(failures),
        skipped_notes=skipped_notes,
        expected_attachments=expected_attachments,
        written_attachments=written_attachments,
        failures=failures,
        failed_report_path=failed_report_path,
    )
    _write_json(output_path / result.summary_path, _summary_payload(result))
    return result


def _failure_record(note: Note, exc: Exception) -> dict[str, str]:
    return {
        "title": note.title,
        "created": note.created,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _summary_payload(result: ExportRunResult) -> dict[str, object]:
    return {
        "total_notes": result.total_notes,
        "exported_notes": result.exported_notes,
        "failed_notes": result.failed_notes,
        "skipped_notes": result.skipped_notes,
        "expected_attachments": result.expected_attachments,
        "written_attachments": result.written_attachments,
        "failures": result.failures,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

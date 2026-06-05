from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


AI_VAULT_DRAFT_COLUMNS = [
    "title",
    "proposed_area",
    "proposed_topic",
    "draft_summary",
    "source_state",
    "source_enex",
    "source_output_dir",
    "source_markdown_path",
    "source_metadata_path",
    "created",
    "updated",
    "tags",
]

SOURCE_INDEX_COLUMNS = [
    "source_state",
    "source_enex",
    "source_output_dir",
    "source_markdown_path",
    "source_metadata_path",
    "title",
    "created",
    "updated",
    "tags",
    "word_count",
    "resource_count",
    "has_attachments",
    "has_tasks",
    "has_encrypted_content",
]


@dataclass(frozen=True)
class AIVaultPrototypeResult:
    output_dir: Path
    main_knowledge_map_path: Path
    trash_safety_map_path: Path
    source_index_path: Path
    draft_sample_path: Path
    readonly_audit_path: Path
    summary_path: Path
    non_trash_notes: int
    trash_notes: int
    draft_rows: int


def build_ai_vault_prototype(
    canonical_output_dir: str | Path,
    output_dir: str | Path,
    sample_size: int = 50,
) -> AIVaultPrototypeResult:
    """Build local-only AI Vault review artifacts from refinery canonical output.

    The canonical output is opened read-only. This function only writes under
    ``output_dir`` and verifies tracked source file state before and after the
    run so reviewers can confirm no canonical files were changed.
    """

    if not 20 <= sample_size <= 50:
        raise ValueError("AI Vault review sample size must be between 20 and 50 rows")

    canonical_root = Path(canonical_output_dir).resolve()
    output_path = Path(output_dir).resolve()
    if _is_relative_to(output_path, canonical_root):
        raise ValueError("AI Vault output directory must be outside canonical output")

    aggregate_index = canonical_root / "aggregate_index.csv"
    if not aggregate_index.exists():
        raise FileNotFoundError(f"canonical aggregate_index.csv not found: {aggregate_index}")

    rows = _load_rows(aggregate_index)

    source_rows: list[dict[str, str]] = []
    non_trash_rows: list[dict[str, str]] = []
    trash_rows: list[dict[str, str]] = []

    for row in rows:
        source_state = "trash_quarantined" if _is_trash_row(row, canonical_root) else "main"
        source_rows.append(_source_index_row(row, source_state, canonical_root))
        if source_state == "trash_quarantined":
            trash_rows.append(row)
        else:
            non_trash_rows.append(row)

    sampled_non_trash_rows = non_trash_rows[:sample_size]
    tracked_sources = _tracked_source_files(canonical_root, rows)
    pre_source_state = _source_state(tracked_sources)

    output_path.mkdir(parents=True, exist_ok=True)
    main_map = _build_main_knowledge_map(non_trash_rows, canonical_root)
    trash_map = _build_trash_safety_map(trash_rows, len(rows))
    draft_rows = _build_draft_sample(sampled_non_trash_rows, canonical_root)

    main_path = output_path / "main_knowledge_map.json"
    trash_path = output_path / "trash_safety_map.json"
    source_index_path = output_path / "source_index.csv"
    draft_sample_path = output_path / "ai_vault_draft_sample.csv"
    audit_path = output_path / "source_readonly_audit.json"
    summary_path = output_path / "prototype_summary.json"

    _write_json(main_path, main_map)
    _write_json(trash_path, trash_map)
    _write_csv(source_index_path, SOURCE_INDEX_COLUMNS, source_rows)
    _write_csv(draft_sample_path, AI_VAULT_DRAFT_COLUMNS, draft_rows)

    post_source_state = _source_state(tracked_sources)
    audit = {
        "canonical_output_dir": str(canonical_root),
        "output_dir": str(output_path),
        "tracked_source_files": [str(path) for path in tracked_sources],
        "pre_source_state": pre_source_state,
        "post_source_state": post_source_state,
        "read_only_verified": pre_source_state == post_source_state,
    }
    _write_json(audit_path, audit)

    summary = {
        "canonical_output_dir": str(canonical_root),
        "output_dir": str(output_path),
        "artifacts": {
            "main_knowledge_map": str(main_path),
            "trash_safety_map": str(trash_path),
            "source_index": str(source_index_path),
            "ai_vault_draft_sample": str(draft_sample_path),
            "source_readonly_audit": str(audit_path),
        },
        "total_source_rows": len(rows),
        "non_trash_notes": len(non_trash_rows),
        "trash_notes": len(trash_rows),
        "draft_rows": len(draft_rows),
        "sample_size_requested": sample_size,
        "redaction_policy": "secrets/API keys/tokens/connection strings are replaced with [REDACTED:*] before writing draft text fields",
        "trash_policy": "Trash content is quarantined: only counts/risk categories are emitted; titles/content are not summarized or reused",
        "read_only_verified": audit["read_only_verified"],
    }
    _write_json(summary_path, summary)

    return AIVaultPrototypeResult(
        output_dir=output_path,
        main_knowledge_map_path=main_path,
        trash_safety_map_path=trash_path,
        source_index_path=source_index_path,
        draft_sample_path=draft_sample_path,
        readonly_audit_path=audit_path,
        summary_path=summary_path,
        non_trash_notes=len(non_trash_rows),
        trash_notes=len(trash_rows),
        draft_rows=len(draft_rows),
    )


def redact_sensitive_text(text: str) -> str:
    """Mask obvious secret-like values before writing review artifacts."""

    redacted = text
    patterns = [
        (r"\b(?:sk|pk|rk|ghp|github_pat|xox[baprs])-[-A-Za-z0-9_\.]{8,}\b", "[REDACTED:token]"),
        (r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", "Bearer [REDACTED:token]"),
        (r"\b[A-Za-z0-9_\-]{12,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b", "[REDACTED:jwt]"),
        (r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED:secret]"),
        (r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb|redis)://[^\s)\]>'\"]+", "[REDACTED:connection-string]"),
        (r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED:email]"),
    ]
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def _tracked_source_files(canonical_root: Path, rows: list[dict[str, str]]) -> list[Path]:
    candidates = [canonical_root / "aggregate_index.csv", canonical_root / "aggregate_summary.json", canonical_root / "run_manifest.jsonl"]
    for row in rows:
        for column in ("markdown_path", "metadata_path"):
            source_path = _safe_source_path(row, column, canonical_root)
            if source_path is not None:
                candidates.append(source_path)

    seen: set[Path] = set()
    existing: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            existing.append(resolved)
    return sorted(existing)


def _source_state(paths: Iterable[Path]) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for path in paths:
        stat = path.stat()
        state[str(path)] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256(path),
        }
    return state


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_rows(aggregate_index: Path) -> list[dict[str, str]]:
    with aggregate_index.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _is_trash_row(row: dict[str, str], canonical_root: Path) -> bool:
    source_enex = row.get("source_enex", "")
    output_dir = row.get("output_dir", "")
    rel_output = _relative_parts(output_dir, canonical_root)
    candidates = [source_enex, output_dir, *rel_output]
    for value in candidates:
        lowered = str(value).lower()
        if "trash" in lowered or "廢紙" in lowered or "垃圾" in lowered:
            return True
    return False


def _relative_parts(output_dir: str, canonical_root: Path) -> list[str]:
    try:
        rel = Path(output_dir).resolve().relative_to(canonical_root / "exports")
    except (ValueError, OSError):
        return []
    return list(rel.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _safe_source_path(row: dict[str, str], rel_column: str, canonical_root: Path) -> Path | None:
    rel = row.get(rel_column, "")
    output_dir = row.get("output_dir", "")
    if not rel or not output_dir:
        return None

    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None

    exports_root = (canonical_root / "exports").resolve()
    try:
        safe_output_dir = Path(output_dir).resolve()
        safe_output_dir.relative_to(exports_root)
        source_path = (safe_output_dir / rel_path).resolve()
        source_path.relative_to(safe_output_dir)
    except (ValueError, OSError):
        return None
    return source_path


def _source_index_row(row: dict[str, str], source_state: str, canonical_root: Path) -> dict[str, str]:
    if source_state == "trash_quarantined":
        return {
            "source_state": source_state,
            "source_enex": "[TRASH-QUARANTINED]",
            "source_output_dir": "[TRASH-QUARANTINED]",
            "source_markdown_path": "[TRASH-QUARANTINED]",
            "source_metadata_path": "[TRASH-QUARANTINED]",
            "title": "[TRASH-QUARANTINED]",
            "created": row.get("created", ""),
            "updated": row.get("updated", ""),
            "tags": "[TRASH-QUARANTINED]",
            "word_count": row.get("word_count", ""),
            "resource_count": row.get("resource_count", ""),
            "has_attachments": row.get("has_attachments", ""),
            "has_tasks": row.get("has_tasks", ""),
            "has_encrypted_content": row.get("has_encrypted_content", ""),
        }

    return {
        "source_state": source_state,
        "source_enex": redact_sensitive_text(row.get("source_enex", "")),
        "source_output_dir": redact_sensitive_text(row.get("output_dir", "")),
        "source_markdown_path": redact_sensitive_text(_full_source_path(row, "markdown_path", canonical_root)),
        "source_metadata_path": redact_sensitive_text(_full_source_path(row, "metadata_path", canonical_root)),
        "title": redact_sensitive_text(row.get("title", "")),
        "created": row.get("created", ""),
        "updated": row.get("updated", ""),
        "tags": redact_sensitive_text(row.get("tags", "")),
        "word_count": row.get("word_count", ""),
        "resource_count": row.get("resource_count", ""),
        "has_attachments": row.get("has_attachments", ""),
        "has_tasks": row.get("has_tasks", ""),
        "has_encrypted_content": row.get("has_encrypted_content", ""),
    }


def _build_main_knowledge_map(rows: list[dict[str, str]], canonical_root: Path) -> dict[str, object]:
    area_counts: Counter[str] = Counter()
    area_topics: dict[str, Counter[str]] = defaultdict(Counter)
    area_samples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        area, topic = _area_topic(row, canonical_root)
        area_counts[area] += 1
        area_topics[area][topic] += 1
        if len(area_samples[area]) < 5:
            area_samples[area].append(
                {
                    "title": redact_sensitive_text(row.get("title", "")),
                    "source_enex": redact_sensitive_text(row.get("source_enex", "")),
                    "source_markdown_path": redact_sensitive_text(_full_source_path(row, "markdown_path", canonical_root)),
                }
            )

    area_payloads = [
        {
            "area": area,
            "note_count": area_counts[area],
            "topics": [
                {"topic": topic, "note_count": count}
                for topic, count in sorted(area_topics[area].items(), key=lambda item: (-item[1], item[0]))[:20]
            ],
            "sample_sources": area_samples[area],
        }
        for area in area_counts
    ]

    return {
        "totals": {"non_trash_notes": len(rows), "area_count": len(area_payloads)},
        "areas": sorted(area_payloads, key=lambda item: (-int(item["note_count"]), str(item["area"]))),
    }


def _build_trash_safety_map(rows: list[dict[str, str]], total_rows: int) -> dict[str, object]:
    risk_categories = Counter()
    for row in rows:
        risk_categories["trash_content_quarantined"] += 1
        if _truthy(row.get("has_encrypted_content")):
            risk_categories["encrypted_content_present"] += 1
        if _truthy(row.get("has_attachments")) or _int(row.get("resource_count")) > 0:
            risk_categories["attachments_present"] += 1
        if _truthy(row.get("has_tasks")):
            risk_categories["tasks_present"] += 1
        if _int(row.get("word_count")) >= 1000:
            risk_categories["large_note"] += 1

    return {
        "totals": {"trash_notes": len(rows), "source_rows_seen": total_rows},
        "risk_categories": dict(sorted(risk_categories.items())),
        "policy": "Trash content is quarantined. This map intentionally excludes Trash titles, snippets, summaries, source areas, markdown paths, and metadata paths.",
    }


def _build_draft_sample(rows: list[dict[str, str]], canonical_root: Path) -> list[dict[str, str]]:
    sample = []
    for row in rows:
        area, topic = _area_topic(row, canonical_root)
        markdown = _read_markdown(row, canonical_root)
        sample.append(
            {
                "title": redact_sensitive_text(row.get("title", "")),
                "proposed_area": redact_sensitive_text(area),
                "proposed_topic": redact_sensitive_text(topic),
                "draft_summary": _draft_summary(markdown),
                "source_state": "main",
                "source_enex": redact_sensitive_text(row.get("source_enex", "")),
                "source_output_dir": redact_sensitive_text(row.get("output_dir", "")),
                "source_markdown_path": redact_sensitive_text(_full_source_path(row, "markdown_path", canonical_root)),
                "source_metadata_path": redact_sensitive_text(_full_source_path(row, "metadata_path", canonical_root)),
                "created": row.get("created", ""),
                "updated": row.get("updated", ""),
                "tags": redact_sensitive_text(row.get("tags", "")),
            }
        )
    return sample


def _area_topic(row: dict[str, str], canonical_root: Path) -> tuple[str, str]:
    parts = _relative_parts(row.get("output_dir", ""), canonical_root)
    if parts:
        return parts[0], parts[1] if len(parts) > 1 else "未分類"
    source_parts = row.get("source_enex", "").split("/")
    if len(source_parts) >= 2:
        return source_parts[-3] if len(source_parts) >= 3 else "未分類", Path(source_parts[-1]).stem
    return "未分類", "未分類"


def _source_area_from_enex(source_enex: str) -> str:
    parts = [part for part in Path(source_enex).parts if part not in {"/", ""}]
    if not parts:
        return "unknown"
    if "Trash" in parts:
        return "Trash"
    return parts[-2] if len(parts) >= 2 else parts[-1]


def _full_source_path(row: dict[str, str], rel_column: str, canonical_root: Path) -> str:
    source_path = _safe_source_path(row, rel_column, canonical_root)
    return str(source_path) if source_path is not None else ""


def _read_markdown(row: dict[str, str], canonical_root: Path) -> str:
    path = _safe_source_path(row, "markdown_path", canonical_root)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _draft_summary(markdown: str) -> str:
    normalized = re.sub(r"\s+", " ", markdown).strip()
    if not normalized:
        return ""
    return redact_sensitive_text(normalized)[:240]


def _write_json(path: Path, payload: object) -> None:
    _ensure_safe_output_file(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    _ensure_safe_output_file(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _ensure_safe_output_file(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlinked AI Vault artifact: {path}")
    if path.parent.is_symlink():
        raise ValueError(f"Refusing to write through symlinked AI Vault output directory: {path.parent}")
    resolved_parent = path.parent.resolve()
    resolved_path = path.resolve() if path.exists() else resolved_parent / path.name
    try:
        resolved_path.relative_to(resolved_parent)
    except ValueError as exc:
        raise ValueError(f"AI Vault artifact path escapes output directory: {path}") from exc


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _int(value: str | None) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0

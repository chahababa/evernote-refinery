import csv
import json
from pathlib import Path

import pytest

from evernote_refinery.ai_vault import AI_VAULT_DRAFT_COLUMNS, build_ai_vault_prototype, redact_sensitive_text


def _write_note(export_dir: Path, title: str, markdown: str, metadata: dict | None = None) -> tuple[str, str]:
    notes = export_dir / "notes"
    meta = export_dir / "metadata"
    notes.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    stem = title.replace(" ", "-").replace("=", "-")
    note_rel = f"notes/{stem}.md"
    meta_rel = f"metadata/{stem}.json"
    (export_dir / note_rel).write_text(markdown, encoding="utf-8")
    payload = metadata or {
        "metadata": {"title": title, "created": "20250101T000000Z", "updated": "20250102T000000Z", "tags": ["alpha"]},
        "features": {"word_count": 10, "resource_count": 0, "has_attachments": False, "has_tasks": False, "has_encrypted_content": False},
        "markdown_path": note_rel,
    }
    (export_dir / meta_rel).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return note_rel, meta_rel


def _canonical_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    rows = []

    work_dir = root / "exports" / "00.行動區" / "$工作" / "策略"
    work_note, work_meta = _write_note(
        work_dir,
        "api_key=sk-testsecretvalue",
        "這是一篇好初策略筆記。 fake token sk-testsecretvalue should be redacted.",
    )
    rows.append({
        "source_enex": "/input/00.行動區/$工作/策略.enex",
        "output_dir": str(work_dir),
        "title": "api_key=sk-testsecretvalue",
        "created": "20250101T000000Z",
        "updated": "20250102T000000Z",
        "tags": "alpha;token=ghp_exampletokenvalue",
        "markdown_path": work_note,
        "metadata_path": work_meta,
        "word_count": "10",
        "resource_count": "0",
        "has_attachments": "false",
        "has_tasks": "false",
        "has_encrypted_content": "false",
    })

    trash_dir = root / "exports" / "Trash" / "舊垃圾"
    trash_note, trash_meta = _write_note(trash_dir, "舊垃圾", "TRASH_SECRET_SHOULD_NOT_APPEAR 重要但已丟棄的內容")
    rows.append({
        "source_enex": "/input/Trash/舊垃圾.enex",
        "output_dir": str(trash_dir),
        "title": "舊垃圾",
        "created": "20240101T000000Z",
        "updated": "20240102T000000Z",
        "tags": "trash",
        "markdown_path": trash_note,
        "metadata_path": trash_meta,
        "word_count": "5",
        "resource_count": "0",
        "has_attachments": "false",
        "has_tasks": "false",
        "has_encrypted_content": "false",
    })

    with (root / "aggregate_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (root / "aggregate_summary.json").write_text(json.dumps({"notes_exported": 2}), encoding="utf-8")
    return root


def test_redact_sensitive_text_masks_fake_tokens_and_connection_strings():
    text = "api_key=sk-testsecretvalue postgres://user:pass@example.com/db Bearer abc.def.ghi"

    redacted = redact_sensitive_text(text)

    assert "sk-test" not in redacted
    assert "postgres://" not in redacted
    assert "abc.def.ghi" not in redacted
    assert redacted.count("[REDACTED") >= 3


def test_build_ai_vault_prototype_writes_maps_sample_traceability_and_readonly_audit(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    before_mtime = (canonical / "aggregate_index.csv").stat().st_mtime_ns
    output = tmp_path / "ai-vault-output"

    result = build_ai_vault_prototype(canonical, output, sample_size=20)

    assert result.output_dir == output
    assert (output / "main_knowledge_map.json").exists()
    assert (output / "trash_safety_map.json").exists()
    assert (output / "source_index.csv").exists()
    assert (output / "ai_vault_draft_sample.csv").exists()
    assert (output / "source_readonly_audit.json").exists()

    assert (canonical / "aggregate_index.csv").stat().st_mtime_ns == before_mtime
    audit = json.loads((output / "source_readonly_audit.json").read_text(encoding="utf-8"))
    assert audit["read_only_verified"] is True
    assert audit["pre_source_state"] == audit["post_source_state"]
    assert any(path.endswith("api_key-sk-testsecretvalue.md") for path in audit["tracked_source_files"])

    main_map = json.loads((output / "main_knowledge_map.json").read_text(encoding="utf-8"))
    assert main_map["totals"]["non_trash_notes"] == 1
    assert main_map["areas"][0]["area"] == "00.行動區"
    assert "TRASH_SECRET_SHOULD_NOT_APPEAR" not in json.dumps(main_map, ensure_ascii=False)

    trash_map = json.loads((output / "trash_safety_map.json").read_text(encoding="utf-8"))
    assert trash_map["totals"]["trash_notes"] == 1
    assert trash_map["risk_categories"]["trash_content_quarantined"] == 1
    assert "counts_by_source_area" not in trash_map
    assert "舊垃圾" not in json.dumps(trash_map, ensure_ascii=False)
    assert "TRASH_SECRET_SHOULD_NOT_APPEAR" not in json.dumps(trash_map, ensure_ascii=False)

    with (output / "ai_vault_draft_sample.csv").open(encoding="utf-8", newline="") as handle:
        sample_rows = list(csv.DictReader(handle))
    assert len(sample_rows) == 1
    assert list(sample_rows[0].keys()) == AI_VAULT_DRAFT_COLUMNS
    assert "/notes/" in sample_rows[0]["source_markdown_path"]
    assert "[REDACTED" in sample_rows[0]["source_markdown_path"]
    assert "sk-testsecretvalue" not in json.dumps(sample_rows, ensure_ascii=False)
    assert "ghp_exampletokenvalue" not in json.dumps(sample_rows, ensure_ascii=False)
    assert "[REDACTED" in json.dumps(sample_rows, ensure_ascii=False)

    with (output / "source_index.csv").open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    assert len(source_rows) == 2
    assert {row["source_state"] for row in source_rows} == {"main", "trash_quarantined"}
    assert "sk-testsecretvalue" not in json.dumps(source_rows, ensure_ascii=False)
    assert "ghp_exampletokenvalue" not in json.dumps(source_rows, ensure_ascii=False)


def test_build_ai_vault_prototype_rejects_sample_sizes_outside_review_range(tmp_path):
    canonical = _canonical_fixture(tmp_path)

    with pytest.raises(ValueError, match="20 and 50"):
        build_ai_vault_prototype(canonical, tmp_path / "out", sample_size=51)


def test_build_ai_vault_prototype_rejects_output_inside_canonical_root(tmp_path):
    canonical = _canonical_fixture(tmp_path)

    with pytest.raises(ValueError, match="outside canonical output"):
        build_ai_vault_prototype(canonical, canonical / "ai-vault-output", sample_size=20)


def test_build_ai_vault_prototype_rejects_output_artifact_symlinks(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    output = tmp_path / "ai-vault-output"
    output.mkdir()
    target = canonical / "aggregate_summary.json"
    (output / "main_knowledge_map.json").symlink_to(target)

    with pytest.raises(ValueError, match="symlinked AI Vault artifact"):
        build_ai_vault_prototype(canonical, output, sample_size=20)


def test_readonly_audit_tracks_actual_sample_when_trash_precedes_non_trash(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    index = canonical / "aggregate_index.csv"
    with index.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = handle.readline()
    rows = [rows[1], rows[0]]
    with index.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    output = tmp_path / "ai-vault-output"
    build_ai_vault_prototype(canonical, output, sample_size=20)

    audit = json.loads((output / "source_readonly_audit.json").read_text(encoding="utf-8"))
    assert any(path.endswith("api_key-sk-testsecretvalue.md") for path in audit["tracked_source_files"])


def test_build_ai_vault_prototype_does_not_read_escaped_markdown_paths(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    outside = tmp_path / "outside-secret.md"
    outside.write_text("OUTSIDE_SECRET_SHOULD_NOT_APPEAR", encoding="utf-8")

    with (canonical / "aggregate_index.csv").open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_enex",
                "output_dir",
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
            ],
        )
        writer.writerow({
            "source_enex": "/input/00.行動區/$工作/escaped.enex",
            "output_dir": str(canonical / "exports" / "00.行動區" / "$工作" / "escaped"),
            "title": "escaped",
            "created": "20250101T000000Z",
            "updated": "20250102T000000Z",
            "tags": "",
            "markdown_path": f"../../../../{outside.name}",
            "metadata_path": "metadata/escaped.json",
            "word_count": "10",
            "resource_count": "0",
            "has_attachments": "false",
            "has_tasks": "false",
            "has_encrypted_content": "false",
        })

    output = tmp_path / "ai-vault-output"
    build_ai_vault_prototype(canonical, output, sample_size=20)

    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file())
    assert "OUTSIDE_SECRET_SHOULD_NOT_APPEAR" not in artifact_text

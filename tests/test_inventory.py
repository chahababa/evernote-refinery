import csv
import json
import sqlite3
from pathlib import Path

from evernote_refinery.cli import main
from evernote_refinery.inventory import build_inventory, classify_category, classify_sensitivity, search_inventory


def _write_export(root: Path, notebook_parts: list[str], title: str, body: str, *, tags: str = "", created: str = "20250101T000000Z", updated: str = "20250102T000000Z", resource_count: str = "0", has_attachments: str = "false", has_tasks: str = "false", has_encrypted_content: str = "false") -> dict[str, str]:
    export_dir = root / "exports" / Path(*notebook_parts) / title
    notes_dir = export_dir / "notes"
    metadata_dir = export_dir / "metadata"
    notes_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace("/", "-").replace(" ", "-")
    markdown_rel = f"notes/{safe_title}.md"
    metadata_rel = f"metadata/{safe_title}.json"
    (export_dir / markdown_rel).write_text(body, encoding="utf-8")
    (export_dir / metadata_rel).write_text(
        json.dumps({
            "metadata": {"title": title, "created": created, "updated": updated, "tags": tags.split(";") if tags else []},
            "features": {
                "resource_count": int(resource_count),
                "has_attachments": has_attachments == "true",
                "has_tasks": has_tasks == "true",
                "has_encrypted_content": has_encrypted_content == "true",
            },
            "markdown_path": markdown_rel,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "source_enex": str(Path("/input") / Path(*notebook_parts) / f"{title}.enex"),
        "output_dir": str(export_dir),
        "title": title,
        "created": created,
        "updated": updated,
        "tags": tags,
        "markdown_path": markdown_rel,
        "metadata_path": metadata_rel,
        "word_count": str(len(body.split())),
        "resource_count": resource_count,
        "has_attachments": has_attachments,
        "has_tasks": has_tasks,
        "has_encrypted_content": has_encrypted_content,
    }


def _canonical_inventory_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    rows = [
        _write_export(
            root,
            ["HC_營運", "客訴"],
            "牛肉客訴處理",
            "客訴 牛肉 退費流程與門市回報。",
            tags="客訴;牛肉",
            resource_count="1",
            has_attachments="true",
            has_tasks="true",
        ),
        _write_export(
            root,
            ["00.行動區", "$工作"],
            "API 權限盤點",
            "fake api_key=sk-testfixturevalue should be local only",
            tags="credential",
        ),
        _write_export(
            root,
            ["Trash"],
            "舊牛肉資料",
            "客訴 牛肉 trash body should be excluded by default",
            tags="trash",
        ),
        _write_export(
            root,
            ["ZZ.封存"],
            "封存牛肉資料",
            "客訴 牛肉 archived body should be excluded by default",
            tags="archive",
        ),
        _write_export(
            root,
            ["HC_營運", "加密"],
            "加密筆記",
            "encrypted placeholder",
            has_encrypted_content="true",
        ),
    ]
    with (root / "aggregate_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (root / "aggregate_summary.json").write_text(json.dumps({"notes_exported": len(rows)}), encoding="utf-8")
    return root


def test_inventory_build_derives_fields_and_preserves_readonly_sources(tmp_path):
    canonical = _canonical_inventory_fixture(tmp_path)
    before = (canonical / "aggregate_index.csv").stat().st_mtime_ns
    index = tmp_path / "evernote.sqlite"

    result = build_inventory(canonical / "aggregate_index.csv", canonical, index, read_only_source_check=True)

    assert result.total_rows == 5
    assert result.indexed_rows == 5
    assert result.read_only_verified is True
    assert (canonical / "aggregate_index.csv").stat().st_mtime_ns == before

    conn = sqlite3.connect(index)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM notes WHERE title = ?", ("牛肉客訴處理",)).fetchone()
        assert row["notebook_root"] == "HC_營運"
        assert row["notebook_path"] == "HC_營運/客訴"
        assert row["category"] == "operations"
        assert row["sensitivity"] == "normal"
        assert row["has_attachments"] == 1
        assert row["has_tasks"] == 1
        flags = json.loads(row["flags"])
        assert flags["has_attachments"] is True
        assert flags["has_tasks"] is True
        assert flags["search_allowed"] is True
        assert row["summary_allowed"] == 1
        assert row["search_allowed"] == 1
        assert row["body_indexed"] == 1
        assert len(row["body_sha256"]) == 64
        audit = json.loads(conn.execute("SELECT value FROM build_audit WHERE key = 'summary'").fetchone()[0])
        assert audit["read_only_verified"] is True
        assert audit["pre_source_state"] == audit["post_source_state"]
    finally:
        conn.close()


def test_inventory_build_can_rebuild_existing_index_with_current_schema(tmp_path):
    canonical = _canonical_inventory_fixture(tmp_path)
    index = tmp_path / "evernote.sqlite"

    build_inventory(canonical / "aggregate_index.csv", canonical, index)
    build_inventory(canonical / "aggregate_index.csv", canonical, index)

    conn = sqlite3.connect(index)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()]
        assert "flags" in columns
        assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 5
    finally:
        conn.close()


def test_classifiers_detect_taxonomy_sensitivity_and_encrypted_flags():
    assert classify_category("HC_營運/客訴", "牛肉") == "operations"
    assert classify_category("Trash", "舊資料") == "trash"
    assert classify_sensitivity(title="API", tags=["credential"], notebook_path="00.行動區", body="api_key=sk-testfixturevalue") == "credential_risk"
    assert classify_sensitivity(title="加密", tags=[], notebook_path="HC_營運", has_encrypted_content=True) == "encrypted"


def test_search_supports_cjk_filters_and_default_safety_boundaries(tmp_path):
    canonical = _canonical_inventory_fixture(tmp_path)
    index = tmp_path / "evernote.sqlite"
    build_inventory(canonical / "aggregate_index.csv", canonical, index)

    results = search_inventory(index, "客訴 牛肉", notebook_root="HC_營運", has_attachments=True, has_tasks=True, limit=10)

    assert [item.title for item in results] == ["牛肉客訴處理"]
    assert "Trash" not in results[0].notebook_path
    assert "封存" not in results[0].notebook_path
    assert "客訴" in results[0].snippet or "match:" in results[0].snippet


def test_search_requires_opt_in_for_sensitive_trash_archive_and_encrypted_filters(tmp_path):
    canonical = _canonical_inventory_fixture(tmp_path)
    index = tmp_path / "evernote.sqlite"
    build_inventory(canonical / "aggregate_index.csv", canonical, index)

    assert search_inventory(index, "api_key") == []
    assert [r.title for r in search_inventory(index, "api_key", include_sensitive=True)] == ["API 權限盤點"]
    assert "舊牛肉資料" not in [r.title for r in search_inventory(index, "牛肉", include_sensitive=True)]
    assert "舊牛肉資料" in [r.title for r in search_inventory(index, "牛肉", include_trash=True, include_sensitive=True)]
    assert "封存牛肉資料" in [r.title for r in search_inventory(index, "牛肉", include_archive=True, include_sensitive=True)]
    assert [r.title for r in search_inventory(index, "encrypted", encrypted_only=True, include_sensitive=True)] == ["加密筆記"]


def test_query_log_redacts_query_and_never_stores_note_bodies(tmp_path):
    canonical = _canonical_inventory_fixture(tmp_path)
    index = tmp_path / "evernote.sqlite"
    build_inventory(canonical / "aggregate_index.csv", canonical, index)

    search_inventory(index, "api_key=sk-testfixturevalue", include_sensitive=True)

    conn = sqlite3.connect(index)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(query_log)").fetchall()]
        assert "body" not in columns
        query, filters = conn.execute("SELECT query, filters_json FROM query_log").fetchone()
        assert "sk-testfixturevalue" not in query
        assert "fake api_key" not in query
        assert "fake api_key" not in filters
    finally:
        conn.close()


def test_inventory_cli_build_stats_search_and_markdown_output(tmp_path, capsys):
    canonical = _canonical_inventory_fixture(tmp_path)
    index = tmp_path / "cli.sqlite"

    assert main(["inventory", "build", "--aggregate-index", str(canonical / "aggregate_index.csv"), "--canonical-root", str(canonical), "--output", str(index), "--read-only-source-check"]) == 0
    build_out = capsys.readouterr().out
    assert "indexed rows: 5" in build_out
    assert "read-only verified: true" in build_out

    assert main(["inventory", "stats", "--index", str(index)]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["total_notes"] == 5
    assert stats["task_notes"] == 1

    assert main(["search", "客訴 牛肉", "--index", str(index), "--notebook-root", "HC_營運", "--limit", "5", "--output", "paths"]) == 0
    paths_out = capsys.readouterr().out
    assert "牛肉客訴處理.md" in paths_out

    result_md = tmp_path / "results.md"
    assert main(["search", "客訴 牛肉", "--index", str(index), "--notebook-root", "HC_營運", "--output", "markdown", "--markdown-output", str(result_md)]) == 0
    assert result_md.exists()
    assert "牛肉客訴處理" in result_md.read_text(encoding="utf-8")

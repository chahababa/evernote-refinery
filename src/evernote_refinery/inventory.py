from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from evernote_refinery.ai_vault import redact_sensitive_text

SCHEMA_VERSION = 1

SENSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"finance|financial|bank|salary|payroll|invoice|tax|會計|財務|薪資|發票|稅務|銀行",
        r"family|personal|private|medical|health|家庭|家人|私人|隱私|醫療|健康",
        r"credential|password|passwd|secret|token|api[_-]?key|oauth|金鑰|密碼|憑證|登入",
    ]
]
SECRET_LIKE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]|"
    r"\b(?:sk|pk|rk|ghp|github_pat|xox[baprs])-[-A-Za-z0-9_.]{8,}\b|"
    r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"
)
ARCHIVE_ROOTS = {"ZZ.封存", "Archive", "Archives", "封存"}
TRASH_ROOTS = {"Trash", "垃圾桶", "廢紙簍"}


@dataclass(frozen=True)
class InventoryBuildResult:
    index_path: Path
    total_rows: int
    indexed_rows: int
    read_only_verified: bool


@dataclass(frozen=True)
class SearchResult:
    note_id: str
    title: str
    notebook_path: str
    markdown_abs_path: str
    metadata_abs_path: str
    category: str
    sensitivity: str
    created_date: str
    updated_date: str
    tags: list[str]
    snippet: str


def build_inventory(
    aggregate_index: str | Path,
    canonical_root: str | Path,
    output: str | Path,
    read_only_source_check: bool = False,
) -> InventoryBuildResult:
    aggregate_path = Path(aggregate_index).resolve()
    canonical_path = Path(canonical_root).resolve()
    output_path = Path(output).resolve()

    if not aggregate_path.exists():
        raise FileNotFoundError(f"aggregate index not found: {aggregate_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"canonical root not found: {canonical_path}")
    if _is_relative_to(output_path, canonical_path):
        raise ValueError("inventory output must be outside canonical output root")

    tracked = _tracked_readonly_files(canonical_path, aggregate_path) if read_only_source_check else []
    pre_state = _source_state(tracked) if read_only_source_check else {}

    rows = _load_rows(aggregate_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.is_symlink():
        raise ValueError(f"refusing to write inventory through symlink: {output_path}")

    conn = sqlite3.connect(output_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _reset_schema(conn)
        _create_schema(conn)

        indexed_rows = 0
        indexed_at = _utc_now()
        for row in rows:
            note = derive_note_record(row, canonical_path, indexed_at=indexed_at)
            conn.execute(
                """
                INSERT INTO notes (
                    note_id, title, tags, notebook_path, notebook_root, category, sensitivity,
                    created, created_date, created_year, updated, updated_date, updated_year,
                    source_enex, output_dir, markdown_abs_path, metadata_abs_path, flags,
                    word_count, resource_count, has_attachments, has_tasks, has_encrypted_content,
                    is_trash, is_archive, summary_allowed, search_allowed, body_indexed,
                    body_sha256, source_mtime_ns, indexed_at
                ) VALUES (
                    :note_id, :title, :tags_json, :notebook_path, :notebook_root, :category, :sensitivity,
                    :created, :created_date, :created_year, :updated, :updated_date, :updated_year,
                    :source_enex, :output_dir, :markdown_abs_path, :metadata_abs_path, :flags_json,
                    :word_count, :resource_count, :has_attachments, :has_tasks, :has_encrypted_content,
                    :is_trash, :is_archive, :summary_allowed, :search_allowed, :body_indexed,
                    :body_sha256, :source_mtime_ns, :indexed_at
                )
                """,
                note,
            )
            conn.execute(
                "INSERT INTO notes_fts(rowid, title, tags, notebook, body) VALUES ((SELECT rowid FROM notes WHERE note_id = ?), ?, ?, ?, ?)",
                (note["note_id"], note["title"], note["tags_text"], note["notebook_path"], note["body_text"]),
            )
            indexed_rows += 1

        post_state = _source_state(tracked) if read_only_source_check else {}
        read_only_verified = pre_state == post_state if read_only_source_check else True
        conn.execute(
            "INSERT INTO build_audit(key, value) VALUES (?, ?)",
            ("summary", json.dumps({
                "schema_version": SCHEMA_VERSION,
                "aggregate_index": str(aggregate_path),
                "canonical_root": str(canonical_path),
                "output": str(output_path),
                "total_rows": len(rows),
                "indexed_rows": indexed_rows,
                "read_only_source_check": read_only_source_check,
                "read_only_verified": read_only_verified,
                "tracked_source_files": [str(p) for p in tracked],
                "pre_source_state": pre_state,
                "post_source_state": post_state,
            }, ensure_ascii=False, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()

    return InventoryBuildResult(output_path, len(rows), indexed_rows, read_only_verified)


def inventory_stats(index: str | Path) -> dict[str, object]:
    conn = sqlite3.connect(Path(index))
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        return {
            "total_notes": total,
            "body_indexed": conn.execute("SELECT COUNT(*) FROM notes WHERE body_indexed = 1").fetchone()[0],
            "trash_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE is_trash = 1").fetchone()[0],
            "archive_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE is_archive = 1").fetchone()[0],
            "sensitive_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE sensitivity != 'normal'").fetchone()[0],
            "attachments_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE has_attachments = 1").fetchone()[0],
            "task_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE has_tasks = 1").fetchone()[0],
            "encrypted_notes": conn.execute("SELECT COUNT(*) FROM notes WHERE has_encrypted_content = 1").fetchone()[0],
            "notebook_roots": dict(conn.execute("SELECT notebook_root, COUNT(*) FROM notes GROUP BY notebook_root ORDER BY COUNT(*) DESC").fetchall()),
            "categories": dict(conn.execute("SELECT category, COUNT(*) FROM notes GROUP BY category ORDER BY COUNT(*) DESC").fetchall()),
        }
    finally:
        conn.close()


def search_inventory(
    index: str | Path,
    query: str,
    *,
    notebook_root: str | None = None,
    notebook_path: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tags: Sequence[str] | None = None,
    has_attachments: bool | None = None,
    has_tasks: bool | None = None,
    encrypted_only: bool = False,
    include_trash: bool = False,
    include_archive: bool = False,
    include_sensitive: bool = False,
    limit: int = 20,
    log_query: bool = True,
) -> list[SearchResult]:
    conn = sqlite3.connect(Path(index))
    conn.row_factory = sqlite3.Row
    try:
        where, params = _filter_where(
            notebook_root=notebook_root,
            notebook_path=notebook_path,
            category=category,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            has_attachments=has_attachments,
            has_tasks=has_tasks,
            encrypted_only=encrypted_only,
            include_trash=include_trash,
            include_archive=include_archive,
            include_sensitive=include_sensitive,
        )
        terms = _query_terms(query)
        fts_match = _fts_query(terms)
        rows: list[sqlite3.Row] = []
        if fts_match:
            try:
                rows = conn.execute(
                    f"""
                    SELECT notes.*, snippet(notes_fts, 3, '[', ']', ' … ', 16) AS snippet_text,
                           bm25(notes_fts) AS rank
                    FROM notes_fts JOIN notes ON notes_fts.rowid = notes.rowid
                    WHERE notes_fts MATCH ? AND {where}
                    ORDER BY rank LIMIT ?
                    """,
                    [fts_match, *params, limit],
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if len(rows) < limit:
            like_where = " AND ".join(["(title LIKE ? OR tags LIKE ? OR notebook_path LIKE ? OR markdown_abs_path LIKE ? OR note_id IN (SELECT note_id FROM notes WHERE rowid IN (SELECT rowid FROM notes_fts WHERE body LIKE ?)))" for _ in terms])
            like_params: list[object] = []
            for term in terms:
                needle = f"%{term}%"
                like_params.extend([needle, needle, needle, needle, needle])
            if like_where:
                seen = {row["note_id"] for row in rows}
                fallback = conn.execute(
                    f"SELECT notes.*, '' AS snippet_text FROM notes WHERE {where} AND {like_where} ORDER BY updated_date DESC, created_date DESC LIMIT ?",
                    [*params, *like_params, limit],
                ).fetchall()
                rows.extend([row for row in fallback if row["note_id"] not in seen][: max(0, limit - len(rows))])
        if log_query:
            conn.execute(
                "INSERT INTO query_log(query, filters_json, result_count, queried_at) VALUES (?, ?, ?, ?)",
                (redact_sensitive_text(query)[:500], json.dumps({
                    "notebook_root": notebook_root,
                    "notebook_path": notebook_path,
                    "category": category,
                    "date_from": date_from,
                    "date_to": date_to,
                    "tags": list(tags or []),
                    "has_attachments": has_attachments,
                    "has_tasks": has_tasks,
                    "encrypted_only": encrypted_only,
                    "include_trash": include_trash,
                    "include_archive": include_archive,
                    "include_sensitive": include_sensitive,
                    "limit": limit,
                }, ensure_ascii=False, sort_keys=True), len(rows), _utc_now()),
            )
            conn.commit()
        return [_row_to_result(row, terms) for row in rows]
    finally:
        conn.close()


def write_markdown_results(results: Sequence[SearchResult], output: str | Path, query: str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Evernote local search results", "", f"Query: `{redact_sensitive_text(query)}`", "", f"Results: {len(results)}", ""]
    for item in results:
        lines.extend([
            f"## {item.title or '(untitled)'}",
            f"- Notebook: {item.notebook_path}",
            f"- Category: {item.category}",
            f"- Sensitivity: {item.sensitivity}",
            f"- Created: {item.created_date}",
            f"- Updated: {item.updated_date}",
            f"- Markdown: `{item.markdown_abs_path}`",
            f"- Metadata: `{item.metadata_abs_path}`",
        ])
        if item.snippet:
            lines.append(f"- Snippet: {item.snippet}")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def derive_note_record(row: dict[str, str], canonical_root: Path, *, indexed_at: str | None = None) -> dict[str, object]:
    markdown_abs = _safe_source_path(row, "markdown_path", canonical_root)
    metadata_abs = _safe_source_path(row, "metadata_path", canonical_root)
    title = row.get("title", "")
    tags = _parse_tags(row.get("tags", ""))
    notebook_path = _notebook_path(row, canonical_root)
    notebook_root = notebook_path.split("/", 1)[0] if notebook_path else ""
    is_trash = _is_trash(notebook_path, row)
    is_archive = notebook_root in ARCHIVE_ROOTS or notebook_path.lower().startswith("archive/")
    has_encrypted = _bool(row.get("has_encrypted_content"))
    body = ""
    body_sha = ""
    body_indexed = False
    if markdown_abs and markdown_abs.exists():
        body = markdown_abs.read_text(encoding="utf-8", errors="replace")
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        body_indexed = True
    sensitivity = classify_sensitivity(title=title, tags=tags, notebook_path=notebook_path, body=body, has_encrypted_content=has_encrypted)
    created_date, created_year = _evernote_date(row.get("created", ""))
    updated_date, updated_year = _evernote_date(row.get("updated", ""))
    source_mtime_ns = max([p.stat().st_mtime_ns for p in (markdown_abs, metadata_abs) if p and p.exists()] or [0])
    note_id = hashlib.sha256("|".join([row.get("source_enex", ""), row.get("output_dir", ""), row.get("markdown_path", ""), title]).encode("utf-8")).hexdigest()[:24]
    summary_allowed = not (is_trash or is_archive or sensitivity != "normal" or has_encrypted)
    return {
        "note_id": note_id,
        "title": title,
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "tags_text": " ".join(tags),
        "notebook_path": notebook_path,
        "notebook_root": notebook_root,
        "category": classify_category(notebook_path, title, tags),
        "sensitivity": sensitivity,
        "created": row.get("created", ""),
        "created_date": created_date,
        "created_year": created_year,
        "updated": row.get("updated", ""),
        "updated_date": updated_date,
        "updated_year": updated_year,
        "source_enex": row.get("source_enex", ""),
        "output_dir": row.get("output_dir", ""),
        "markdown_abs_path": str(markdown_abs) if markdown_abs else "",
        "metadata_abs_path": str(metadata_abs) if metadata_abs else "",
        "flags_json": json.dumps({
            "has_attachments": _bool(row.get("has_attachments")) or _int(row.get("resource_count")) > 0,
            "has_tasks": _bool(row.get("has_tasks")),
            "has_encrypted_content": has_encrypted,
            "is_trash": is_trash,
            "is_archive": is_archive,
            "summary_allowed": summary_allowed,
            "search_allowed": True,
        }, ensure_ascii=False, sort_keys=True),
        "word_count": _int(row.get("word_count")),
        "resource_count": _int(row.get("resource_count")),
        "has_attachments": int(_bool(row.get("has_attachments")) or _int(row.get("resource_count")) > 0),
        "has_tasks": int(_bool(row.get("has_tasks"))),
        "has_encrypted_content": int(has_encrypted),
        "is_trash": int(is_trash),
        "is_archive": int(is_archive),
        "summary_allowed": int(summary_allowed),
        "search_allowed": 1,
        "body_indexed": int(body_indexed),
        "body_sha256": body_sha,
        "source_mtime_ns": source_mtime_ns,
        "indexed_at": indexed_at or _utc_now(),
        "body_text": body,
    }


def classify_category(notebook_path: str, title: str = "", tags: Sequence[str] | None = None) -> str:
    text = " ".join([notebook_path, title, " ".join(tags or [])]).lower()
    if "trash" in text or "垃圾" in text:
        return "trash"
    if "營運" in text or "operation" in text or "ops" in text:
        return "operations"
    if "行動" in text or "工作" in text or "project" in text:
        return "work"
    if "點甜" in text or "甜" in text:
        return "dessert"
    if "封存" in text or "archive" in text:
        return "archive"
    if "家" in text or "family" in text:
        return "personal"
    return "general"


def classify_sensitivity(*, title: str, tags: Sequence[str], notebook_path: str, body: str = "", has_encrypted_content: bool = False) -> str:
    if has_encrypted_content:
        return "encrypted"
    text = " ".join([title, notebook_path, " ".join(tags), body[:2000]])
    if SECRET_LIKE_PATTERN.search(text):
        return "credential_risk"
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return "sensitive"
    return "normal"


def _reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS notes_fts;
        DROP TABLE IF EXISTS notes;
        DROP TABLE IF EXISTS build_audit;
        DROP TABLE IF EXISTS query_log;
        """
    )


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notes (
            note_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            tags TEXT NOT NULL,
            notebook_path TEXT NOT NULL,
            notebook_root TEXT NOT NULL,
            category TEXT NOT NULL,
            sensitivity TEXT NOT NULL,
            created TEXT NOT NULL,
            created_date TEXT NOT NULL,
            created_year INTEGER,
            updated TEXT NOT NULL,
            updated_date TEXT NOT NULL,
            updated_year INTEGER,
            source_enex TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            markdown_abs_path TEXT NOT NULL,
            metadata_abs_path TEXT NOT NULL,
            flags TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            resource_count INTEGER NOT NULL,
            has_attachments INTEGER NOT NULL,
            has_tasks INTEGER NOT NULL,
            has_encrypted_content INTEGER NOT NULL,
            is_trash INTEGER NOT NULL,
            is_archive INTEGER NOT NULL,
            summary_allowed INTEGER NOT NULL,
            search_allowed INTEGER NOT NULL,
            body_indexed INTEGER NOT NULL,
            body_sha256 TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, tags, notebook, body);
        CREATE TABLE IF NOT EXISTS build_audit (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            filters_json TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            queried_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notes_notebook_root ON notes(notebook_root);
        CREATE INDEX IF NOT EXISTS idx_notes_notebook_path ON notes(notebook_path);
        CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
        CREATE INDEX IF NOT EXISTS idx_notes_dates ON notes(created_date, updated_date);
        """
    )


def _load_rows(aggregate_path: Path) -> list[dict[str, str]]:
    with aggregate_path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _safe_source_path(row: dict[str, str], rel_column: str, canonical_root: Path) -> Path | None:
    rel = row.get(rel_column) or ""
    output_dir = row.get("output_dir") or ""
    if not rel or not output_dir:
        return None
    base = Path(output_dir).resolve()
    candidate = (base / rel).resolve()
    if not _is_relative_to(candidate, canonical_root):
        return None
    return candidate


def _notebook_path(row: dict[str, str], canonical_root: Path) -> str:
    output_dir = row.get("output_dir") or ""
    try:
        rel = Path(output_dir).resolve().relative_to(canonical_root / "exports")
        parts = list(rel.parts)
        if len(parts) > 1:
            return "/".join(parts[:-1])
        return "/".join(parts)
    except (ValueError, OSError):
        source = row.get("source_enex", "")
        parts = list(Path(source).parts)
        if len(parts) > 1:
            return "/".join(parts[-4:-1])
        return ""


def _is_trash(notebook_path: str, row: dict[str, str]) -> bool:
    values = [notebook_path, row.get("source_enex", ""), row.get("output_dir", "")]
    return any("trash" in v.lower() or "垃圾" in v or "廢紙" in v for v in values)


def _evernote_date(value: str) -> tuple[str, int | None]:
    if not value:
        return "", None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.date().isoformat(), dt.year
        except ValueError:
            continue
    return value[:10], _int(value[:4]) or None


def _parse_tags(value: str) -> list[str]:
    if not value:
        return []
    if value.strip().startswith("["):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, list):
                return [str(v).strip() for v in loaded if str(v).strip()]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in re.split(r"[;,|]", value) if part.strip()]


def _bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _int(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _tracked_readonly_files(canonical_root: Path, aggregate_path: Path) -> list[Path]:
    candidates = [aggregate_path, canonical_root / "aggregate_summary.json"]
    return [p.resolve() for p in candidates if p.exists()]


def _source_state(paths: Iterable[Path]) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for path in paths:
        stat = path.stat()
        state[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": _sha256(path)}
    return state


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _filter_where(**kwargs: object) -> tuple[str, list[object]]:
    clauses = ["search_allowed = 1"]
    params: list[object] = []
    if kwargs.get("notebook_root"):
        clauses.append("notebook_root = ?")
        params.append(kwargs["notebook_root"])
    if kwargs.get("notebook_path"):
        clauses.append("notebook_path LIKE ?")
        params.append(f"{kwargs['notebook_path']}%")
    if kwargs.get("category"):
        clauses.append("category = ?")
        params.append(kwargs["category"])
    if kwargs.get("date_from"):
        clauses.append("created_date >= ?")
        params.append(kwargs["date_from"])
    if kwargs.get("date_to"):
        clauses.append("created_date <= ?")
        params.append(kwargs["date_to"])
    tags_value = kwargs.get("tags")
    tags_iter = tags_value if isinstance(tags_value, (list, tuple, set)) else []
    for tag in tags_iter:
        clauses.append("tags LIKE ?")
        params.append(f"%{tag}%")
    if kwargs.get("has_attachments") is not None:
        clauses.append("has_attachments = ?")
        params.append(int(bool(kwargs["has_attachments"])))
    if kwargs.get("has_tasks") is not None:
        clauses.append("has_tasks = ?")
        params.append(int(bool(kwargs["has_tasks"])))
    if kwargs.get("encrypted_only"):
        clauses.append("has_encrypted_content = 1")
    if not kwargs.get("include_trash"):
        clauses.append("is_trash = 0")
    if not kwargs.get("include_archive"):
        clauses.append("is_archive = 0")
    if not kwargs.get("include_sensitive"):
        clauses.append("sensitivity = 'normal'")
    return " AND ".join(clauses), params


def _query_terms(query: str) -> list[str]:
    return [term.strip() for term in re.split(r"\s+", query.strip()) if term.strip()]


def _fts_query(terms: Sequence[str]) -> str:
    return " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)


def _row_to_result(row: sqlite3.Row, terms: Sequence[str]) -> SearchResult:
    snippet = row["snippet_text"] or ""
    snippet = redact_sensitive_text(snippet.replace("\n", " "))[:500]
    if not snippet and terms:
        snippet = "match: " + ", ".join(terms[:3])
    return SearchResult(
        note_id=row["note_id"],
        title=row["title"],
        notebook_path=row["notebook_path"],
        markdown_abs_path=row["markdown_abs_path"],
        metadata_abs_path=row["metadata_abs_path"],
        category=row["category"],
        sensitivity=row["sensitivity"],
        created_date=row["created_date"],
        updated_date=row["updated_date"],
        tags=json.loads(row["tags"] or "[]"),
        snippet=snippet,
    )

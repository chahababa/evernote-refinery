from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from evernote_refinery.ai_vault import build_ai_vault_prototype
from evernote_refinery.checkpoint import Checkpoint
from evernote_refinery.inventory import build_inventory, inventory_stats, search_inventory, write_markdown_results
from evernote_refinery.parser import parse_enex
from evernote_refinery.runner import export_enex
from evernote_refinery.synthetic import write_synthetic_enex


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evernote-refinery",
        description="Convert Evernote ENEX exports into clean, reusable data.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    count = subcommands.add_parser("count", help="Count notes in an ENEX file")
    count.add_argument("enex", type=Path)

    export = subcommands.add_parser("export", help="Export an ENEX file to Markdown, JSON, CSV, and assets")
    export.add_argument("enex", type=Path)
    export.add_argument("--output", "-o", type=Path, required=True)
    export.add_argument("--resume", action="store_true", help="Skip notes already recorded in the checkpoint file")
    export.add_argument(
        "--log-file",
        type=Path,
        help="Write JSONL processing logs to this path; defaults to <output>/export.log",
    )

    synthetic = subcommands.add_parser("synthetic", help="Write a deterministic synthetic ENEX file for stress testing")
    synthetic.add_argument("output", type=Path)
    synthetic.add_argument("--notes", type=int, default=100, help="Number of synthetic notes to write")
    synthetic.add_argument("--attachments-per-note", type=int, default=0, help="Number of text attachments per synthetic note")

    ai_vault = subcommands.add_parser(
        "ai-vault",
        help="Build a local-only AI Vault prototype from canonical refinery output",
    )
    ai_vault.add_argument("canonical_output", type=Path, help="Canonical refinery output root containing aggregate_index.csv")
    ai_vault.add_argument("--output", "-o", type=Path, required=True, help="Local output directory for prototype artifacts")
    ai_vault.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of non-Trash draft rows to emit for review (20-50, default: 50)",
    )

    inventory = subcommands.add_parser("inventory", help="Build and inspect a local-only SQLite/FTS inventory")
    inventory_subcommands = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_build = inventory_subcommands.add_parser("build", help="Build a local SQLite/FTS note inventory")
    inventory_build.add_argument("--aggregate-index", type=Path, required=True, help="Canonical aggregate_index.csv")
    inventory_build.add_argument("--canonical-root", type=Path, required=True, help="Canonical refinery output root")
    inventory_build.add_argument("--output", "-o", type=Path, required=True, help="SQLite index output path")
    inventory_build.add_argument("--read-only-source-check", action="store_true", help="Verify tracked canonical files are unchanged")

    inventory_stats_cmd = inventory_subcommands.add_parser("stats", help="Print inventory counts as JSON")
    inventory_stats_cmd.add_argument("--index", type=Path, required=True, help="SQLite inventory path")

    search = subcommands.add_parser("search", help="Search the local SQLite/FTS inventory")
    search.add_argument("query", help="Keyword or FTS query; whitespace terms are ANDed")
    search.add_argument("--index", type=Path, required=True, help="SQLite inventory path")
    search.add_argument("--notebook-root")
    search.add_argument("--notebook-path")
    search.add_argument("--category")
    search.add_argument("--date-from")
    search.add_argument("--date-to")
    search.add_argument("--tag", action="append", dest="tags", default=[])
    search.add_argument("--has-attachments", action="store_true")
    search.add_argument("--has-tasks", action="store_true")
    search.add_argument("--encrypted-only", action="store_true")
    search.add_argument("--include-trash", action="store_true")
    search.add_argument("--include-archive", action="store_true")
    search.add_argument("--include-sensitive", action="store_true")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--output", choices=["paths", "snippets", "json", "markdown"], default="snippets")
    search.add_argument("--markdown-output", type=Path, help="Write markdown result list to this file when --output markdown")
    search.add_argument("--no-query-log", action="store_true", help="Do not append metadata-only query_log row")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "count":
        total = sum(1 for _note in parse_enex(args.enex))
        print(f"notes: {total}")
        return 0

    if args.command == "export":
        checkpoint = Checkpoint(args.output / ".evernote-refinery-checkpoint.json") if args.resume else None
        log_path = args.log_file or args.output / "export.log"
        result = export_enex(args.enex, args.output, checkpoint=checkpoint, log_path=log_path)
        print(f"exported notes: {result.exported_notes}")
        print(f"failed notes: {result.failed_notes}")
        print(f"output: {args.output}")
        print(f"summary: {args.output / result.summary_path}")
        if result.log_path is not None:
            print(f"log: {log_path}")
        if result.failed_report_path is not None:
            print(f"failures: {args.output / result.failed_report_path}")
        if checkpoint is not None:
            print(f"checkpoint: {checkpoint.path}")
        return 0

    if args.command == "synthetic":
        result = write_synthetic_enex(args.output, note_count=args.notes, attachments_per_note=args.attachments_per_note)
        print(f"synthetic notes: {result.note_count}")
        print(f"synthetic attachments: {result.attachment_count}")
        print(f"output: {result.path}")
        return 0

    if args.command == "ai-vault":
        result = build_ai_vault_prototype(args.canonical_output, args.output, sample_size=args.sample_size)
        print(f"AI Vault prototype output: {result.output_dir}")
        print(f"main knowledge map: {result.main_knowledge_map_path}")
        print(f"trash safety map: {result.trash_safety_map_path}")
        print(f"source index: {result.source_index_path}")
        print(f"draft sample: {result.draft_sample_path}")
        print(f"source readonly audit: {result.readonly_audit_path}")
        print(f"summary: {result.summary_path}")
        print(f"non-trash notes: {result.non_trash_notes}")
        print(f"trash notes: {result.trash_notes}")
        print(f"draft rows: {result.draft_rows}")
        return 0

    if args.command == "inventory":
        if args.inventory_command == "build":
            result = build_inventory(
                args.aggregate_index,
                args.canonical_root,
                args.output,
                read_only_source_check=args.read_only_source_check,
            )
            print(f"inventory index: {result.index_path}")
            print(f"total rows: {result.total_rows}")
            print(f"indexed rows: {result.indexed_rows}")
            print(f"read-only verified: {str(result.read_only_verified).lower()}")
            return 0
        if args.inventory_command == "stats":
            print(json.dumps(inventory_stats(args.index), ensure_ascii=False, indent=2, sort_keys=True))
            return 0

    if args.command == "search":
        results = search_inventory(
            args.index,
            args.query,
            notebook_root=args.notebook_root,
            notebook_path=args.notebook_path,
            category=args.category,
            date_from=args.date_from,
            date_to=args.date_to,
            tags=args.tags,
            has_attachments=True if args.has_attachments else None,
            has_tasks=True if args.has_tasks else None,
            encrypted_only=args.encrypted_only,
            include_trash=args.include_trash,
            include_archive=args.include_archive,
            include_sensitive=args.include_sensitive,
            limit=args.limit,
            log_query=not args.no_query_log,
        )
        if args.output == "paths":
            for item in results:
                print(item.markdown_abs_path)
        elif args.output == "json":
            print(json.dumps([item.__dict__ for item in results], ensure_ascii=False, indent=2, sort_keys=True))
        elif args.output == "markdown":
            output = args.markdown_output or Path("evernote-search-results.md")
            path = write_markdown_results(results, output, args.query)
            print(f"markdown results: {path}")
            print(f"results: {len(results)}")
        else:
            for item in results:
                print(f"{item.title}\t{item.notebook_path}\t{item.markdown_abs_path}")
                if item.snippet:
                    print(f"  {item.snippet}")
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

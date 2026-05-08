from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from evernote_refinery.checkpoint import Checkpoint
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

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

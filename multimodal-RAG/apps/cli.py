"""CLI: ingest, query, documents, delete, health."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import settings
from .ingest import delete_document, ingest_document, list_documents, register_pdf
from .rag import answer, stream_answer
from .telemetry import setup_telemetry, span
from .vectorstore import store


def cmd_ingest(args) -> int:
    setup_telemetry()
    path = Path(args.path)
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 1
    files = sorted(path.glob("*.pdf")) if path.is_dir() else [path]
    if not files:
        print("no PDFs found", file=sys.stderr)
        return 1

    for pdf in files:
        with span("cli.ingest", file=pdf.name):
            manifest = register_pdf(pdf)
            print(f"→ {pdf.name}  [{manifest['document_id']}]  {manifest['status']}")
            manifest = ingest_document(manifest["document_id"], force=args.force)
            counts = manifest.get("counts", {})
            print(f"  {manifest['status']}  text={counts.get('text', 0)} "
                  f"table={counts.get('table', 0)} visual={counts.get('visual', 0)}")
            if manifest.get("error"):
                print(f"  error: {manifest['error']}", file=sys.stderr)
            if manifest.get("warnings"):
                for warning in manifest["warnings"][:5]:
                    print(f"  warn: {warning}")
    return 0


def cmd_query(args) -> int:
    setup_telemetry()
    if args.json:
        with span("cli.query", mode="json"):
            print(json.dumps(answer(args.question, args.k).to_dict(), indent=2, ensure_ascii=False))
        return 0

    started = time.time()
    for event, data in stream_answer(args.question, args.k):
        if event == "meta":
            sources = ", ".join(f"p{s['page']} {s['modality']}" for s in data["sources"]) or "—"
            print(f"\nroute: {data['route']}   sources: {sources}\n")
        elif event == "token":
            print(data["text"], end="", flush=True)
        elif event == "done":
            print(f"\n\n[{time.time() - started:.1f}s]")
        elif event == "error":
            print(f"\nerror: {data['message']}", file=sys.stderr)
            return 1
    return 0


def cmd_docs(args) -> int:
    docs = list_documents()
    if not docs:
        print("no documents")
        return 0
    for d in docs:
        c = d.get("counts", {})
        print(f"{d['document_id']}  {d['status']:<10} p{d.get('pages', 0):<3} "
              f"t={c.get('text', 0)} tb={c.get('table', 0)} v={c.get('visual', 0)}  {d['source']}")
    return 0


def cmd_delete(args) -> int:
    delete_document(args.document_id)
    print(f"deleted {args.document_id}")
    return 0


def cmd_health(args) -> int:
    print(json.dumps(store.health(), indent=2))
    print("openrouter key:", "set" if settings.openrouter_key else "MISSING")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="apps.cli", description="Multimodal RAG")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="ingest a PDF or a folder of PDFs")
    p.add_argument("path")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("query", help="ask a question")
    p.add_argument("question")
    p.add_argument("--k", type=int, default=settings.top_k)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("docs", help="list documents")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("delete", help="delete a document")
    p.add_argument("document_id")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("health", help="check Qdrant")
    p.set_defaults(func=cmd_health)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

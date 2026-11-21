"""Ingestion orchestration: PDF -> chunks -> Qdrant, with a JSON manifest per document."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .assets import storage
from .caption import CaptionError, caption_png
from .config import settings
from .models import Chunk
from .pdf_extract import FigurePiece, TextPiece, extract_pdf
from .vectorstore import store

INGEST_LOCK = threading.Lock()
MAX_TEXT_CHARS = 1500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def doc_id_for(digest: str) -> str:
    return "doc_" + digest[:12]


def manifest_path(document_id: str) -> Path:
    return settings.manifests_dir / f"{document_id}.json"


def load_manifest(document_id: str) -> dict:
    path = manifest_path(document_id)
    if not path.exists():
        raise FileNotFoundError(document_id)
    return json.loads(path.read_text())


def save_manifest(data: dict) -> None:
    data["updated_at"] = _now()
    settings.manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path(data["document_id"]).write_text(json.dumps(data, indent=2))


def list_documents() -> list[dict]:
    if not settings.manifests_dir.exists():
        return []
    docs = []
    for f in sorted(settings.manifests_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            docs.append(json.loads(f.read_text()))
        except Exception:
            continue
    return docs


def register_pdf(path: Path, source_name: str | None = None, copy: bool = True) -> dict:
    settings.ensure_dirs()
    path = Path(path)
    digest = sha256_file(path)
    document_id = doc_id_for(digest)
    existing = manifest_path(document_id)
    if existing.exists():
        return json.loads(existing.read_text())

    stored_path = path
    if copy:
        target = settings.pdfs_dir / path.name
        if path.resolve() != target.resolve():
            target.write_bytes(path.read_bytes())
        stored_path = target

    manifest = {
        "document_id": document_id,
        "source": source_name or path.name,
        "doc_hash": digest,
        "path": str(stored_path),
        "pages": 0,
        "status": "uploaded",
        "progress": {"step": "queued", "done": 0, "total": 0},
        "counts": {"text": 0, "table": 0, "visual": 0},
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_manifest(manifest)
    return manifest


# ---------- chunk building ----------

def _split_text(text: str, limit: int = MAX_TEXT_CHARS) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= limit:
            current = f"{current}\n\n{para}".strip()
            continue
        if current:
            parts.append(current)
        while len(para) > limit:
            cut = para.rfind(". ", 0, limit)
            cut = cut + 1 if cut > limit * 0.5 else limit
            parts.append(para[:cut].strip())
            para = para[cut:].strip()
        current = para
    if current:
        parts.append(current)
    return [p for p in parts if p]


def _text_chunks(document_id: str, source: str, blocks: list[TextPiece]) -> list[Chunk]:
    by_page: dict[int, list[TextPiece]] = {}
    for block in blocks:
        by_page.setdefault(block.page, []).append(block)

    chunks: list[Chunk] = []
    for page, items in sorted(by_page.items()):
        joined = "\n".join(i.text for i in items)
        parts = _split_text(joined)
        for n, part in enumerate(parts, start=1):
            chunks.append(Chunk(
                document_id=document_id,
                chunk_id=f"p{page}_t{n}",
                modality="text",
                content=part,
                source=source,
                page=page,
                part=n if len(parts) > 1 else None,
            ))
    return chunks


# ---------- ingestion ----------

def ingest_document(document_id: str, force: bool = False) -> dict:
    manifest = load_manifest(document_id)
    if manifest["status"] == "indexed" and not force:
        return manifest
    if not INGEST_LOCK.acquire(blocking=False):
        raise RuntimeError("another ingestion is running")

    try:
        settings.ensure_dirs()
        pdf_path = Path(manifest["path"])
        manifest.update(status="extracting", error=None,
                        progress={"step": "extracting", "done": 0, "total": 0})
        save_manifest(manifest)

        extraction = extract_pdf(pdf_path)
        manifest["pages"] = extraction.pages
        if extraction.empty_pages:
            manifest["ocr_required"] = True

        # asset + caption phase
        total_figures = len(extraction.figures)
        manifest.update(status="captioning",
                        progress={"step": "captioning", "done": 0, "total": total_figures})
        save_manifest(manifest)

        # save every asset first (fast), then caption in parallel
        jobs = []
        per_page_counter: dict[int, int] = {}
        for fig in extraction.figures:
            n = per_page_counter.get(fig.page, 0) + 1
            per_page_counter[fig.page] = n
            name = f"p{fig.page:02d}_f{n}.png"
            rel_path, asset_hash = storage.save_png(document_id, name, fig.png)
            jobs.append((fig, rel_path, asset_hash, n))

        caption_failures = 0
        progress_lock = threading.Lock()

        def work(job):
            fig, rel_path, asset_hash, n = job
            try:
                caption, model = caption_png(fig.png)
                return job, caption, model, True
            except CaptionError:
                return job, "", None, False

        results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(work, job) for job in jobs]
            for future in as_completed(futures):
                job, caption, model, ok = future.result()
                results.append((job, caption, model, ok))
                with progress_lock:
                    manifest["progress"]["done"] = len(results)
                    save_manifest(manifest)

        visual_chunks: list[Chunk] = []
        for job, caption, model, ok in results:
            fig, rel_path, asset_hash, n = job
            if not ok:
                caption_failures += 1
            if fig.labels:
                caption = f"{caption}\n\nLabels: {fig.labels}".strip()
            if not caption:
                caption = f"Figure on page {fig.page} (caption unavailable)"

            visual_chunks.append(Chunk(
                document_id=document_id,
                chunk_id=f"p{fig.page}_f{n}",
                modality="visual",
                content=caption,
                source=manifest["source"],
                page=fig.page,
                bbox=fig.bbox,
                asset_path=rel_path,
                asset_hash=asset_hash,
                caption_model=model,
                caption_status="ok" if ok else "failed",
                extra={"figure_kind": fig.kind},
            ))
        visual_chunks.sort(key=lambda c: (c.page, c.chunk_id))

        chunks: list[Chunk] = []
        chunks += _text_chunks(document_id, manifest["source"], extraction.text)
        for table in extraction.tables:
            if table.markdown.strip():
                chunks.append(Chunk(
                    document_id=document_id,
                    chunk_id=f"p{table.page}_tb{table.number}",
                    modality="table",
                    content=table.markdown,
                    source=manifest["source"],
                    page=table.page,
                    bbox=table.bbox,
                    table_number=table.number,
                ))
        chunks += visual_chunks

        manifest.update(status="embedding",
                        progress={"step": "embedding", "done": 0, "total": len(chunks)},
                        counts={
                            "text": sum(1 for c in chunks if c.modality == "text"),
                            "table": sum(1 for c in chunks if c.modality == "table"),
                            "visual": sum(1 for c in chunks if c.modality == "visual"),
                        })
        save_manifest(manifest)

        store.delete_document(document_id)
        written = store.upsert(chunks)

        partial = caption_failures > 0 or bool(extraction.failures)
        manifest.update(
            status="partial" if partial else "indexed",
            progress={"step": "done", "done": written, "total": len(chunks)},
            counts={
                "text": sum(1 for c in chunks if c.modality == "text"),
                "table": sum(1 for c in chunks if c.modality == "table"),
                "visual": sum(1 for c in chunks if c.modality == "visual"),
            },
            indexed_points=written,
            warnings=extraction.failures[:10],
            caption_failures=caption_failures,
        )
        save_manifest(manifest)
        return manifest

    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save_manifest(manifest)
        return manifest
    finally:
        INGEST_LOCK.release()


def delete_document(document_id: str) -> None:
    try:
        store.delete_document(document_id)
    finally:
        storage.delete_doc(document_id)
        manifest_path(document_id).unlink(missing_ok=True)

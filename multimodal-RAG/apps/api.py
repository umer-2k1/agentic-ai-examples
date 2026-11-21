"""FastAPI app: upload, ingest, query (JSON + SSE), documents, health."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, settings
from .ingest import delete_document, ingest_document, list_documents, load_manifest, register_pdf
from .rag import answer as answer_question
from .rag import stream_answer
from .vectorstore import store

WEB = ROOT / "web"

app = FastAPI(title="Multimodal RAG", version="1.0.0")
settings.ensure_dirs()
app.mount("/assets", StaticFiles(directory=str(settings.asset_dir)), name="assets")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

RUNNING = {"extracting", "captioning", "embedding"}


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=6, ge=1, le=20)
    modalities: list[str] | None = None
    stream: bool = False


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    checks = {"qdrant": store.health(), "openrouter": bool(settings.openrouter_key)}
    ok = checks["qdrant"].get("ok", False) and checks["openrouter"]
    return {"ok": ok, "checks": checks, "collection": settings.collection,
            "embed_model": settings.embed_model}


@app.post("/api/documents", status_code=201)
async def upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are accepted")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    settings.pdfs_dir.mkdir(parents=True, exist_ok=True)
    target = settings.pdfs_dir / safe
    target.write_bytes(await file.read())
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "empty file")
    manifest = register_pdf(target, source_name=file.filename, copy=False)
    return manifest


@app.get("/api/documents")
def documents():
    return {"documents": list_documents()}


@app.get("/api/documents/{document_id}")
def document(document_id: str):
    try:
        manifest = load_manifest(document_id)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")
    try:
        manifest["points"] = store.count(document_id)
    except Exception:
        manifest["points"] = None
    return manifest


@app.post("/api/documents/{document_id}/ingest", status_code=202)
def start_ingest(document_id: str, background: BackgroundTasks, force: bool = False):
    try:
        manifest = load_manifest(document_id)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")
    if manifest["status"] in RUNNING:
        raise HTTPException(409, "ingestion already running")
    background.add_task(ingest_document, document_id, force)
    return {"status": "started", "document_id": document_id}


@app.delete("/api/documents/{document_id}")
def remove_document(document_id: str):
    try:
        load_manifest(document_id)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")
    delete_document(document_id)
    return {"deleted": document_id}


@app.post("/api/query")
def query(request: QueryRequest):
    if not request.stream:
        return answer_question(request.question, request.k, request.modalities).to_dict()

    def events():
        yield ": ping\n\n"
        try:
            for event, data in stream_answer(request.question, request.k, request.modalities):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as exc:  # never leave the client hanging
            payload = {"message": f"{type(exc).__name__}: {exc}", "retryable": True}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

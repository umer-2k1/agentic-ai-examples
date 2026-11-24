# Multimodal RAG

Search a PDF by meaning — including the parts that are not text: tables, embedded images and
**vector charts**. Answers are grounded, cited by page, and streamed token by token.

**Docs:** [learning notes](Docs/README.md) · [architecture](ARCHITECTURE.md)

---

## How it works

```
PDF → text blocks · tables · images · vector regions
    → VLM captions for visuals
    → Qdrant Cloud Inference (384-d embeddings, server-side)
    → collection multimodal_rag
question → embed → top-k → text LLM or vision LLM → streamed answer + citations
```

- **Embeddings run inside Qdrant** (`sentence-transformers/all-MiniLM-L6-v2`, 384-d) — no local model, no extra key.
- **Captions come from OpenRouter** free vision models, with a fallback chain.
- **Vector charts** are found with `page.get_drawings()`, merged with their text labels, clipped and rendered to PNG.
- **If the OpenRouter free pool is rate-limited**, text answers fall back to Groq (`openai/gpt-oss-120b`) and visual
  questions degrade to their caption text. Captions are cached by image hash, so re-ingestion never re-captions.

---

## Setup

Uses the repository's existing `venv`. From the repo root:

```bash
./venv/bin/pip install -r multimodal-RAG/requirements.txt
```

`multimodal-RAG/.env`:

```
QDRANT_URL=https://<cluster>.cloud.qdrant.io:6333
QDRANT_API_KEY=...
QDRANT_COLLECTION=multimodal_rag

OPENROUTER_API_KEY=...
# optional — defaults are free models with fallbacks
OPENROUTER_VISION_MODEL=
OPENROUTER_TEXT_MODEL=

# optional — tracing
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=multimodal-rag
```

---

## Tracing

OpenTelemetry spans are created for every stage, then exported to **LangSmith** over OTLP when
`LANGSMITH_API_KEY` is set. Without a key they are written to `data/traces.jsonl` (one JSON per span).

| Span | Attributes |
|---|---|
| `POST /api/query` | http route, status |
| `retrieval.search` | k, candidates, top score |
| `llm.chat` / `llm.stream` | model, provider, tokens, status code |
| `ingest.extract` | pages, figures, tables |
| `ingest.caption` | page, kind, model |
| `ingest.upsert` | points |

Httpx spans for Qdrant and OpenRouter are captured automatically. The answer footer shows the
first 16 characters of the trace id — search it in LangSmith to see the waterfall.

Use another backend (Jaeger, Tempo, Honeycomb) with `OTEL_EXPORTER_OTLP_ENDPOINT=http://…:4318`.
Disable entirely with `OTEL_ENABLED=0`.

---

## Run

```bash
cd multimodal-RAG
../venv/bin/uvicorn apps.api:app --reload --port 8000
```

Open http://localhost:8000

- **Ingest** — drop a PDF, watch extraction → captioning → embedding.
- **Search** — ask, see the route (text/vision), streamed answer, citation chips and evidence cards.
- **Documents** — status, counts, delete.

### CLI

```bash
../venv/bin/python -m apps.cli ingest ../NovaCore_Multimodal_Company_Report_2026.pdf
../venv/bin/python -m apps.cli ingest ../Siddiqui_Children_Pediatric_Medical_History_2026.pdf
../venv/bin/python -m apps.cli query "What share of Penang electricity came from solar?"
../venv/bin/python -m apps.cli docs
```

### Test corpus

| PDF | Charts |
|---|---|
| `NovaCore_Multimodal_Company_Report_2026.pdf` | embedded raster images |
| `Siddiqui_Children_Pediatric_Medical_History_2026.pdf` | 8 raster + 2 vector (p3 chart, p8 relationship map) |

---

## Layout

```
apps/     config, extraction, captions, Qdrant, ingest, rag, api, cli
web/      single-page UI (no build step)
assets/   extracted visuals, per document (gitignored)
data/     uploads + manifests (gitignored)
Docs/     learning notes and diagrams
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data model, thresholds and acceptance tests.

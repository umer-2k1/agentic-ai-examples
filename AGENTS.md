# Working agreement — this repo

Read this before starting work in this repository.

## Commits

- **Commit very frequently.** One logical unit per commit — a diagram, a doc page, a module, a fix.
  Do not batch a session's work into one commit at the end.
- **Push after each commit batch.** The user wants the GitHub graph kept green:
  `git push origin main`.
- **Attribute to the verified GitHub email.** Before the first commit of a session:
  `git config user.email` must be non-empty. Use `umer-2k1@users.noreply.github.com`
  if the local value is missing.
- Conventional prefixes: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- Never commit secrets. `.env` files are gitignored; keep them that way.

## This project — multimodal RAG

- Code and notes live in `multimodal-RAG/`; docs in `multimodal-RAG/Docs/`.
- The learning track (Docs/) is written documentation with Excalidraw diagrams — no code in those pages.
- Implementation decisions already locked:
  - Vector DB: **Qdrant Cloud** (keys in `multimodal-RAG/.env`).
  - VLM: **OpenRouter** free-tier vision model.
  - Embeddings: **option A** — HF text embeddings + VLM captions (no local models, no torch).
  - Python: the existing repo `venv/` (no uv, no new interpreter).
  - UI: FastAPI + plain HTML/CSS/JS.
  - Chunking: page-level text; tables and visuals never split.
  - PDF visuals: embedded images first; vector charts via `get_drawings()` → clip render.
- Sample corpus: `NovaCore_Multimodal_Company_Report_2026.pdf` (raster charts) and
  `Siddiqui_Children_Pediatric_Medical_History_2026.pdf` (mixed raster + vector).

## Documentation

- Keep `multimodal-RAG/Docs/` current when architecture decisions change.
- Record *why*, not just *what*.

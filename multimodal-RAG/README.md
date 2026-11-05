# Multimodal RAG

Learning + implementation notes for RAG over documents that are not just text.

**Start here → [Docs/README.md](Docs/README.md)**

| | |
|---|---|
| Visual notes | [Docs/](Docs/README.md) — one diagram + one cheat sheet per step |
| Interactive walkthrough | open `Docs/index.html` in a browser |
| Diagrams | `Docs/diagrams/` — PNG to read, SVG to zoom, `.excalidraw` to edit |

## The idea

> Turn every useful modality into something **searchable** (text). Keep the original **seeable** (pixels). Search the summary, answer with the evidence.

## Structure

```
multimodal-RAG/
└── Docs/
    ├── README.md              index + colour code
    ├── 00-overview.md         vocabulary, the three stages
    ├── 01-the-problem.md      why text RAG drops tables, images, charts
    ├── 02-ingestion.md        PDF → text / table / vision-summary docs
    ├── 03-vector-store.md     one embedding model, one namespace
    ├── 04-retrieval.md        match the summary, load the original
    ├── 05-generation.md       text LLM vs vision LLM routing
    ├── 06-end-to-end.md       build order + checks
    ├── 07-cheatsheet.md       one page, everything
    ├── index.html             interactive viewer
    └── diagrams/              6 diagrams × (png, svg, excalidraw)
```

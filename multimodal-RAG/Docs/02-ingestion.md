# 02 · Ingestion

![Multimodal ingestion pipeline](diagrams/02-ingestion-pipeline.png)

Runs **once per document**. Expensive, offline, cacheable.

---

## The four steps

| # | Step | Tool | Output |
|---|---|---|---|
| 1 | **Extract** | PyMuPDF | text blocks, tables, embedded images |
| 2 | **Normalise** | LangChain `Document` | one document per modality chunk |
| 3 | **Embed** | one text embedding model | 384-d vector per document |
| 4 | **Store** | Pinecone | vector + metadata, one namespace |

Everything after step 2 is identical for every modality. That is the point: **normalise early, so the rest of the system only ever sees text**.

---

## Step 1 — Extract

```python
import fitz  # PyMuPDF

doc = fitz.open("novacore.pdf")

for pno, page in enumerate(doc, start=1):
    text   = page.get_text("text")
    tables = page.find_tables()          # PyMuPDF >= 1.23
    images = page.get_images(full=True)  # xref ids
```

| Gotcha | Fix |
|---|---|
| Scanned PDF → empty text | run OCR first (`page.get_textpage_ocr()`) |
| Chart is a **vector** drawing, not an image | `get_images()` misses it — render the page region to PNG, or use a layout model |
| Multi-column text interleaves | use `get_text("blocks")` and sort by column |
| Table detection fails on borderless tables | fall back to a VLM page crop |

---

## Step 2 — Normalise into three document types

### Text — one chunk per page

```python
from langchain_core.documents import Document

Document(
    page_content=page.get_text("text").strip(),
    metadata={"page": pno, "modality": "text", "source": "novacore.pdf"},
)
```

### Table — markdown, not CSV

```python
rows = table.extract()
md = "\n".join("| " + " | ".join(c or "" for c in row) + " |" for row in rows)

Document(
    page_content=md,
    metadata={"page": pno, "modality": "table", "table_number": tno},
)
```

Markdown keeps the header row attached to the cells. Flattened CSV does not, and the LLM loses the column meaning.

### Visual — a VLM writes the summary

```python
summary = vision_llm.invoke([
    {"type": "text", "text": "Describe this figure factually. Include every number, "
                            "axis label and trend. No interpretation."},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
]).content

Document(
    page_content=summary,
    metadata={"page": pno, "modality": "visual", "image_path": "images/p3_chart.png"},
)
```

**This summary is the only thing embedded.** The image itself is never vectorised.

---

## The metadata contract

Every document carries these keys. Everything downstream depends on them.

| Key | Type | Present on | Used for |
|---|---|---|---|
| `source` | str | all | citation, filtering |
| `page` | int | all | citation, "page 7" |
| `modality` | `text \| table \| visual` | all | routing, filtering |
| `image_path` | str | visual only | reloading the original |
| `table_number` | int | table only | citation |

> If `modality` or `image_path` is missing, the vision route silently never fires. This is the most common bug in the whole build.

---

## Step 3–4 — Embed and store

```python
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"   # 384-d, local, free
)

store = PineconeVectorStore(
    index_name="multimodal-rag",
    embedding=embeddings,
    namespace="novacore",          # one namespace for all modalities
)

store.add_documents(docs)          # batches of 100
```

| Choice | Default | Why |
|---|---|---|
| Embedding model | `all-MiniLM-L6-v2` (384-d) | free, local, good enough for English |
| Swap to | `text-embedding-3-small` (1536-d) | better recall, paid, API call per chunk |
| Namespace | one | the modality lives in metadata, not in the partition |
| Chunking | page-level for text, one chunk per table, one per visual | structure-aware > fixed-size |

---

## Cost model

| Item | Per document (≈20 pages, 6 figures) |
|---|---|
| PyMuPDF | ~0.2 s |
| VLM summaries | 6 calls — the dominant cost |
| Embeddings | ~30 chunks, local, negligible |
| Upsert | 1 batch |

**Ingestion cost is dominated by the VLM calls.** Cache summaries by image hash; re-ingesting a document should not re-caption the same chart.

---

## Checklist

- [ ] text extraction returns non-empty for every page (OCR if not)
- [ ] every table becomes markdown with a header row
- [ ] every image **and vector chart** gets a summary
- [ ] `image_path` points at a file that still exists at query time
- [ ] `modality` is set on 100% of documents
- [ ] counts match: pages ≈ text docs, tables ≈ table docs, figures ≈ visual docs

Next: [vector store →](03-vector-store.md)

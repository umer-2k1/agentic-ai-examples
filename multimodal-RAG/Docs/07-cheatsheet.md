# 07 · Cheat sheet

One page. Everything. For revision.

---

## The pipeline in twelve lines

1. A PDF is text + tables + images + charts.
2. Text RAG keeps only the text. The rest cannot be retrieved.
3. Convert every modality to **text** so one search can rank it.
4. Text stays text.
5. Tables become **markdown** (keeps headers attached).
6. Images and charts become a **factual VLM summary** (numbers, labels, trend).
7. The original image is **kept**, its path goes into metadata.
8. One embedding model, one namespace, modality in metadata.
9. Query → embed → top-k.
10. Visual hit? Load the original image.
11. Vision LLM answers with pixels; otherwise text LLM answers.
12. Return the answer **with page + image citations**.

---

## The three rules that decide everything

| Rule | Why |
|---|---|
| **Search the summary, answer with the original** | summaries find well, originals answer well |
| **One embedding model for query and documents** | mixing models = random ranking |
| **Modality is metadata, not a separate index** | one search can rank all modalities |

---

## Numbers

| Setting | Default | Range |
|---|---|---|
| Embedding dims | 384 | 384 – 3072 |
| k | 4 | 2 – 10 (+ rerank) |
| Rerank pool | 20 | 10 – 50 |
| Chunk unit | page / table / figure | — |
| Namespace | 1 | 1 |
| Metadata per record | < 4 KB | — |
| Vision call per figure | 1 | 1 |
| Cost: text vs vision answer | 1× | 5 – 15× |

---

## Decision table

| Situation | Do this |
|---|---|
| Corpus is 95% prose | plain text RAG — skip this |
| Scanned pages | OCR first, then treat as normal |
| Chart is a vector drawing | render the page region to an image, then summarise |
| Table has merged cells | markdown, or a VLM read of the crop |
| Answer needs a photo | store image path, route to vision |
| Charts never retrieved | the summary is too generic — rewrite the prompt |
| Everything scores ~0.2 | query and docs use different embedding models |
| Answer cites page 0 | metadata missing at ingestion |
| `image_path` broken | store repo-relative paths, resolve at load |

---

## Where it breaks

| Layer | Silent failure | Detection |
|---|---|---|
| Extract | empty page text | assert non-empty |
| Summarise | vague caption | read 5 random summaries |
| Embed | model mismatch | score distribution |
| Store | missing modality | count by modality |
| Retrieve | right chunk at rank 30 | hit rate @ k |
| Route | vision never fires | log the route per query |
| Generate | invented numbers | faithfulness review |

> Every one of these fails **without an error**. That is why the checks matter more than the code.

---

## Colour code

| Colour | Role |
|---|---|
| Blue | text |
| Green | table |
| Orange | visual |
| Purple | models |
| Cyan | storage / retrieval |
| Red | what breaks |

---

## Diagram index

| Step | File |
|---|---|
| Problem | `diagrams/01-the-problem` |
| Ingestion | `diagrams/02-ingestion-pipeline` |
| Vector store | `diagrams/03-vector-store` |
| Retrieval | `diagrams/04-retrieval` |
| Routing | `diagrams/05-generation-routing` |
| End to end | `diagrams/06-end-to-end` |

Each exists as PNG (read), SVG (zoom), and Excalidraw (edit).

# 03 · Vector store

![What goes into Pinecone](diagrams/03-vector-store.png)

One index. One namespace. One embedding model. **The modality is metadata, not a separate collection.**

---

## Anatomy of a stored record

```
vector   [0.021, -0.118, ..., 0.044]        ← 384 floats, from the text embedding model
payload  { page_content: "...", metadata: { page, modality, image_path, ... } }
```

What differs per modality is **only the text** that was embedded:

| | `page_content` (what is embedded) | `metadata` |
|---|---|---|
| **Text** | `"FY2026 revenue reached USD 132.0M, up 18% year over year."` | `page: 2, modality: text, source: novacore.pdf` |
| **Table** | `"\| Europe \| $41.2M \| 31% \|"` (markdown) | `page: 4, modality: table, table_number: 1` |
| **Visual** | `"Support resolution time falls from 14.2h to 8.1h..."` | `page: 7, modality: visual, image_path: p7_chart.png` |

---

## Why one namespace beats one-per-modality

| | One namespace (chosen) | Namespace per modality |
|---|---|---|
| Cross-modal query | ✅ one search ranks text, tables and charts together | ❌ you must search N times and merge |
| Routing | ✅ read `metadata.modality` from the hit | ⚠️ inferred from which namespace returned it |
| Ranking | ✅ comparable scores (same model, same space) | ⚠️ scores are not comparable across searches |
| Filtering | ✅ `filter={"modality": "visual"}` | ✅ native |
| Ops | ✅ one index, one backup, one metric | ❌ N indexes to keep in sync |

One namespace is the right default. Split only when the modalities need **different embedding models** (e.g. a dedicated image encoder).

---

## Filters, not separate searches

```python
# only visuals — useful when you want a chart-grounded answer
store.similarity_search(q, k=4, filter={"modality": "visual"})

# only one document
store.similarity_search(q, k=4, filter={"source": "novacore.pdf"})

# one page (debugging a bad answer)
store.similarity_search(q, k=4, filter={"page": 7})
```

Pinecone filter syntax is a MongoDB-style dict; LangChain passes it through.

---

## Embedding model choice

| Model | Dim | Cost | Notes |
|---|---|---|---|
| `all-MiniLM-L6-v2` | 384 | free, local | default here; fast; English |
| `BAAI/bge-small-en-v1.5` | 384 | free, local | slightly better recall |
| `text-embedding-3-small` | 1536 | paid API | stronger, multilingual |
| `text-embedding-3-large` | 3072 | paid API | best, 2× storage |

Rules that matter more than the model:

1. **The same model must embed the query and the documents.** Mixing models = random results.
2. **Changing the model means re-ingesting everything.** There is no migration.
3. **Normalise vectors** (or use cosine) so length does not dominate similarity.

---

## Do not embed the raw image

The tempting shortcut is a CLIP-style image encoder with a shared text/image space.

| Approach | Retrieval quality | Complexity | Verdict |
|---|---|---|---|
| **Text summary** (this build) | good for charts, tables, diagrams | low — one text model | ✅ default |
| CLIP dual encoder | weak on charts and text-heavy images | medium — two encoders | ⚠️ photos only |
| ColPali / late interaction | best on documents | high — special index | ⚠️ later |

A chart is not a photo. CLIP matches "a line chart", not "revenue peaked in Q4". A factual VLM summary matches the actual question.

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Every result is a table | tables are long and keyword-dense | cap table chunk length; add a text summary of the table |
| Charts never retrieved | summary is too generic ("a chart of revenue") | prompt the VLM for numbers + axis labels + trend |
| Duplicate hits | same text on consecutive pages | dedupe by hash of `page_content` |
| Score 0.9 but irrelevant | embedding model mismatch | verify query and docs use the same model |
| `image_path` broken | relative path, different cwd | store absolute or repo-relative paths and resolve at load |

---

## Numbers to remember

| Setting | Value |
|---|---|
| Dimensions | 384 (MiniLM) |
| Distance | cosine |
| Metadata per record | keep < 4 KB |
| Namespace | 1 |
| Batch upsert | 100 vectors |

Next: [retrieval →](04-retrieval.md)

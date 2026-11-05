# 06 · End to end

![The complete architecture](diagrams/06-end-to-end.png)

Two pipelines, one shared index. Ingestion runs once per document; retrieval and generation run per question.

---

## The six stages

| # | Stage | Runs | Input | Output |
|---|---|---|---|---|
| 1 | **Extract** | once per PDF | PDF | text, tables, images |
| 2 | **Normalise** | once per PDF | raw pieces | documents with modality + metadata |
| 3 | **Embed** | once per PDF | document text | vectors |
| 4 | **Store** | once per PDF | vectors + payload | Pinecone index |
| 5 | **Retrieve** | per question | question | top-k chunks + image paths |
| 6 | **Generate** | per question | chunks + images | grounded answer + citations |

Stages 1–4 are the **ingestion pipeline**. Stages 5–6 are the **serving pipeline**. They share exactly one thing: the index.

---

## Build order

Do it in this order. Each step is testable on its own, and the failures stay local.

| Order | Build | Prove it works by |
|---|---|---|
| 1 | PDF → text documents | printing 3 documents and seeing real prose |
| 2 | text-only RAG end to end | asking a question that the text answers |
| 3 | tables → markdown documents | asking "which region is highest?" |
| 4 | images → VLM summaries | asking a question only a figure answers |
| 5 | image path in metadata | retrieving the figure and opening the file |
| 6 | vision route | the answer quotes a number that exists only in the chart |

Steps 1–2 first. If plain text RAG does not work, multimodal will not fix it — it will hide it.

---

## What to check at each stage

| Stage | Check | Fails how |
|---|---|---|
| Extract | page text is not empty | scanned PDF, silent |
| Normalise | every doc has a modality | routing dies later |
| Embed | query and docs use one model | ranking becomes random |
| Store | count matches expected | half the document missing |
| Retrieve | right chunk in top 4 | the answer cannot exist |
| Generate | answer cites real pages | unverifiable output |

---

## Evaluation that actually helps

| Metric | Question it answers | How |
|---|---|---|
| **Hit rate @ k** | is the right chunk even retrieved? | label ~20 questions with their page |
| **Route accuracy** | did visual hits reach the VLM? | count how often the vision path fired |
| **Faithfulness** | is every claim in the sources? | read the answer against the page |
| **Citation validity** | do the page + path resolve? | check mechanically |

Hit rate first. If the chunk is not retrieved, faithfulness is irrelevant.

---

## Scaling knobs

| Knob | Effect | Watch out |
|---|---|---|
| chunk size | bigger = more context, less precision | page-level is already large |
| k | more recall, more noise | pair with a reranker |
| embedding model | better recall | full re-ingest required |
| summary length | better visual recall | longer prompts, more cost |
| reranker | precision at the top | added latency |
| namespace split | isolation | cross-modal queries get harder |

Change one at a time, and re-run the same 20 questions.

---

## What "done" looks like

- [ ] one question spans text, table and chart in a single answer
- [ ] every answer cites page numbers that exist
- [ ] visual answers show the original image
- [ ] re-ingesting a document does not duplicate vectors
- [ ] a missing image path degrades gracefully instead of crashing
- [ ] the whole pipeline runs from one command

Next: [cheat sheet →](07-cheatsheet.md)

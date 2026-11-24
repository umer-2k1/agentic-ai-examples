# Prompt for generating the evaluation set

Use this instead of "write 50 questions". It forces coverage, verifiable ground truth, and
negatives that are actually hard.

---

## The prompt

> You are building an evaluation set for a multimodal RAG system over two PDFs:
>
> - **NovaCore** — 9-page company report: narrative, tables, raster charts (line, bar, pie), a supply-chain diagram, a product image.
> - **Siddiqui** — 9-page pediatric record: narrative, tables, raster charts, two **vector** figures (a growth chart on p3, a relationship map on p8).
>
> Produce **50–60 question/answer pairs**. Every pair must be verifiable from the documents alone.
>
> ### Coverage quotas
>
> | Category | Count | What it must exercise |
> |---|---|---|
> | Simple text | 8 | one page, one sentence |
> | Simple table | 8 | a cell or row, including a unit |
> | Visual | 6 | answer exists only in a chart/image/diagram |
> | Relationship | 12 | 2+ hops, cardinality, inverse lookup, constraint |
> | Cross-document | 4 | facts from both PDFs in one answer |
> | Negative | 10 | information genuinely absent |
>
> Cover every section of both documents at least once. No more than 3 questions per page.
>
> ### Ground-truth rules
>
> 1. Every answer must be supported by a **quoted span**. Record `quote`, `doc`, `page`, `modality`.
> 2. Copy numbers and units exactly (`14.2 h`, `USD 132.0M`, `0.8 kU/L`). Never paraphrase a number.
> 3. If two pages support the answer, list both pages.
> 4. The answer must be ≤ 25 words and unambiguous without the question's context.
> 5. If the answer requires combining a table row with a chart, say so in `reasoning`.
>
> ### Negative questions — use these families, not "unrelated topic"
>
> - **Adjacent attribute**: Ayaan's weight at age 2 (the table starts at birth, then age 4).
> - **Right attribute, wrong entity**: Maya's asthma medication (Maya has no asthma).
> - **Temporal**: FY2024 revenue (the report covers FY2025–26 only).
> - **Out of corpus**: Nucleo's headcount (different company, not in these files).
> - **Modality-absent**: Ayaan's BMI at age 2 (the chart is height only; no BMI row).
> - **Unsupported aggregation**: average quarterly revenue (the chart has points, not a computed average).
>
> For each negative, record the **nearest true fact** so a model cannot grab it by accident
> (e.g. "nearest: Maya's weight at 2 is 11.8 kg, but the question asks about Ayaan").
>
> ### Relationship questions — at least one of each
>
> - **Chain**: allergy → medication → who carries it.
> - **Cardinality**: how many active treatments.
> - **Inverse**: which child is sensitised but not allergic.
> - **Constraint**: which drug is contraindicated by the penicillin allergy.
> - **Cross-record**: why Maya was screened (sibling of Ayaan).
> - **Temporal**: which condition resolved in 2024.
>
> ### Output schema
>
> ```json
> {
>   "id": "R07",
>   "category": "simple|visual|relationship|cross_document|negative",
>   "type": "answerable|unanswerable",
>   "question": "...",
>   "expected_answer": "...",
>   "must_include": ["..."],
>   "must_not_include": ["..."],
>   "quote": "exact text from the document",
>   "doc": "NovaCore|Siddiqui",
>   "pages": [3],
>   "modality": "text|table|visual",
>   "reasoning": "why this needs one hop | two hops | chart reading",
>   "nearest_true_fact": "only for negatives"
> }
> ```
>
> ### Quality gates before you return
>
> - No yes/no questions unless the point is refusal.
> - No pronoun whose referent is ambiguous ("his", "the doctor").
> - No duplicate intent — paraphrase only if you also mark it as a `variant_of`.
> - Every page reference exists in the document.
> - At least 3 questions require reading a figure, not text.
> - At least 2 questions require both a table and a figure.
> - Every negative has a nearest true fact.
> - Re-read each `expected_answer` against the document and delete anything you cannot quote.

---

## Why these changes matter

| Weak prompt | Result | Fix |
|---|---|---|
| "50 questions" | 45 easy text lookups, 5 trivial negatives | quotas per category and per page |
| no source span | answers can't be verified, eval arguments | `quote` + `page` + `modality` |
| negative = unrelated topic | any model refuses, no signal | adjacent-attribute negatives |
| no hop count | "relationship" questions are single-fact | chain / inverse / constraint / cardinality |
| no ambiguity rule | two valid answers, scoring breaks | one span, ≤25 words, no pronouns |
| no variants | score hides paraphrase sensitivity | mark `variant_of` |

---

## Answer-side prompt (the one the app uses)

The eval is only meaningful if the system is told how to behave when evidence is missing:

- "If the value is not in the context, say **not recorded** and name what is available
  (e.g. 'weight is recorded at birth, 4, 6, 7 and 10 years')."
- "Do not interpolate a chart. If you read a plotted value, say **approximately**."
- "Cite as `[p3]` and name the document when the answer spans both."
- "Never fill a gap with a plausible number."

---

## Metrics to report alongside accuracy

| Metric | What it catches |
|---|---|
| Answer accuracy (`must_include`) | wrong value |
| Citation hit (`page` ∩ sources) | right answer, wrong evidence |
| Doc attribution | page collisions across the two PDFs |
| Refusal precision / recall | guessing on negatives vs over-refusing |
| Retrieval hit@k | whether the gold page was even retrievable |
| Groundedness (spot-check) | fluent but unsupported claims |

# Diagrams

Six diagrams, each in three formats.

| File | Format | Use |
|---|---|---|
| `*.png` | 2× raster | GitHub preview, slides, quick look |
| `*.svg` | vector, fonts embedded | zoom without blur, dark backgrounds |
| `*.excalidraw` | editable scene | drag into [excalidraw.com](https://excalidraw.com) and edit |

## The set

| File | Shows |
|---|---|
| `01-the-problem` | the four modalities and what text extraction loses |
| `02-ingestion-pipeline` | PDF → text / table / vision-summary → embed → store |
| `03-vector-store` | record anatomy: what is embedded vs what is metadata |
| `04-retrieval` | question → summary hit → load original → grounded answer |
| `05-generation-routing` | visual in top-k? text LLM vs vision LLM |
| `06-end-to-end` | the whole system in three zones |

## Editing

Open the `.excalidraw` file at excalidraw.com. Arrows are **bound** to their boxes: move a box and the arrows follow.

The scenes use:

| Property | Value |
|---|---|
| Font | Helvetica / system sans (no handwriting) |
| Roughness | 0 (clean lines) |
| Corner radius | 14 px |
| Background | white |

## Colour code

| Colour | Hex | Role |
|---|---|---|
| Blue | `#1971c2` | text |
| Green | `#2f9e44` | table |
| Orange | `#e8590c` | visual |
| Purple | `#7048e8` | models |
| Cyan | `#0c8599` | store / retrieval |
| Red | `#e03131` | what breaks |
| Amber | `#f08c00` | highlights, decisions |

Same colour = same role, in every diagram. Do not introduce a new colour without a new role.

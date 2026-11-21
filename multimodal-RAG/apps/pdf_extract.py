"""PyMuPDF extraction: text, tables, embedded images, vector figures."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable

try:  # PyMuPDF >= 1.24
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from .config import settings

MIN_IMAGE_SIDE = 80        # points; smaller images are icons/logos
MIN_REGION_SIDE = 60       # points; smallest vector figure
MIN_REGION_RATIO = 0.02    # of page area
MAX_REGION_RATIO = 0.70    # above this, discard — it is page furniture
MIN_PATHS = 8              # a chart/diagram is made of many paths
PAD_POINTS = 20


@dataclass
class TextPiece:
    page: int
    bbox: tuple[float, float, float, float]
    text: str


@dataclass
class TablePiece:
    page: int
    bbox: tuple[float, float, float, float]
    markdown: str
    number: int


@dataclass
class FigurePiece:
    page: int
    bbox: tuple[float, float, float, float]
    png: bytes
    kind: str  # image | vector | page
    labels: str = ""  # text objects inside the crop (axis labels, names, legends)


@dataclass
class Extraction:
    pages: int
    text: list[TextPiece] = field(default_factory=list)
    tables: list[TablePiece] = field(default_factory=list)
    figures: list[FigurePiece] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _rect_tuple(r: "fitz.Rect") -> tuple[float, float, float, float]:
    return (round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2))


def _union(rects: Iterable["fitz.Rect"]) -> "fitz.Rect":
    it = iter(rects)
    base = fitz.Rect(next(it))
    for r in it:
        base.x0 = min(base.x0, r.x0)
        base.y0 = min(base.y0, r.y0)
        base.x1 = max(base.x1, r.x1)
        base.y1 = max(base.y1, r.y1)
    return base


def _overlap_ratio(a: "fitz.Rect", b: "fitz.Rect") -> float:
    inter = a & b
    if inter.is_empty or a.get_area() <= 0:
        return 0.0
    return inter.get_area() / a.get_area()


def _inter_over_min(a: "fitz.Rect", b: "fitz.Rect") -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    smallest = min(a.get_area(), b.get_area())
    return inter.get_area() / smallest if smallest > 0 else 0.0


def _clean_cell(value: object) -> str:
    if value is None:
        return "—"
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or "—"


def _to_markdown(rows: list[list[object]]) -> str:
    rows = [r for r in rows if r and any(c not in (None, "") for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    grid = [[_clean_cell(c) for c in r] + ["—"] * (width - len(r)) for r in rows]
    header, body = grid[0], grid[1:]
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * width) + "|"]
    for row in body:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def _render(page: "fitz.Page", rect: "fitz.Rect", dpi: int) -> bytes:
    """Render a clipped region, capping the long edge at 2000 px."""
    scale = 1.0
    longest = max(rect.width, rect.height) * dpi / 72
    if longest > 2000:
        scale = 2000 / longest
    pix = page.get_pixmap(clip=rect, dpi=int(dpi * scale), alpha=False)
    return pix.tobytes("png")


def _detect_tables(page: "fitz.Page") -> list[dict]:
    """find_tables() fragments bordered HTML tables into one row per table; merge them back."""
    raw = []
    page_area = page.rect.get_area()
    try:
        finder = page.find_tables(strategy="lines")   # bordered tables; fast and stable
    except Exception:
        finder = page.find_tables()
    for table in finder.tables:
        bbox = fitz.Rect(table.bbox)
        if bbox.get_area() > page_area * 0.6:          # bogus whole-page table
            continue
        rows = table.extract()
        if not rows:
            continue
        raw.append({"bbox": bbox, "rows": rows})

    # group by horizontal span + column count, then merge rows that are close vertically
    buckets: dict[tuple, list[dict]] = {}
    for item in raw:
        cols = len(item["rows"][0]) if item["rows"] else 0
        key = (round(item["bbox"].x0), round(item["bbox"].x1), cols)
        buckets.setdefault(key, []).append(item)

    merged: list[dict] = []
    for items in buckets.values():
        items.sort(key=lambda t: t["bbox"].y0)
        current = items[0]
        for nxt in items[1:]:
            if nxt["bbox"].y0 - current["bbox"].y1 <= 42:
                current["rows"].extend(nxt["rows"])
                a, b = current["bbox"], nxt["bbox"]
                current["bbox"] = fitz.Rect(min(a.x0, b.x0), min(a.y0, b.y0),
                                            max(a.x1, b.x1), max(a.y1, b.y1))
            else:
                merged.append(current)
                current = nxt
        merged.append(current)

    return [m for m in merged if len(m["rows"]) >= 2 and max(len(r) for r in m["rows"]) >= 2]


def _vector_clusters(page: "fitz.Page", table_rects: list["fitz.Rect"]) -> list["fitz.Rect"]:
    """Group drawing paths into figure-sized regions; ignore page furniture."""
    page_rect = page.rect
    page_area = page_rect.get_area()
    rects: list["fitz.Rect"] = []

    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.is_empty:
            continue
        area = r.get_area()
        if area > page_area * 0.8:          # page background
            continue
        if any(_overlap_ratio(r, t) > 0.15 or t.contains(r) for t in table_rects):
            continue
        rects.append(fitz.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2))

    parent = list(range(len(rects)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _inter_over_min(rects[i], rects[j]) > 0.10:
                union(i, j)

    groups: dict[int, list["fitz.Rect"]] = {}
    for i, r in enumerate(rects):
        groups.setdefault(find(i), []).append(r)

    clusters: list["fitz.Rect"] = []
    for group in groups.values():
        if len(group) < MIN_PATHS:          # a card border is a handful of paths
            continue
        box = _union(group)
        if box.width < MIN_REGION_SIDE or box.height < MIN_REGION_SIDE:
            continue
        ratio = box.get_area() / page_area
        if ratio < MIN_REGION_RATIO or ratio > MAX_REGION_RATIO:
            continue
        clusters.append(box)

    clusters.sort(key=lambda r: r.get_area(), reverse=True)
    merged: list["fitz.Rect"] = []
    for c in clusters:
        if any(_overlap_ratio(c, m) > 0.6 for m in merged):
            continue
        merged.append(c)
    return merged


def extract_pdf(path: str | "fitz.Path", dpi: int | None = None) -> Extraction:
    dpi = dpi or settings.page_dpi
    doc = fitz.open(path)
    result = Extraction(pages=doc.page_count)

    for index in range(doc.page_count):
        page_no = index + 1
        try:
            page = doc[index]
            table_rects: list["fitz.Rect"] = []
            tables: list[TablePiece] = []

            # 1. tables
            try:
                for n, table in enumerate(_detect_tables(page), start=1):
                    md = _to_markdown(table["rows"])
                    if not md:
                        continue
                    rect = table["bbox"]
                    table_rects.append(rect)
                    tables.append(TablePiece(page_no, _rect_tuple(rect), md, n))
            except Exception as exc:
                result.failures.append(f"p{page_no} tables: {exc}")

            # 2. embedded images
            figures: list[FigurePiece] = []
            seen_hashes: set[str] = set()
            try:
                for info in page.get_image_info():
                    rect = fitz.Rect(info["bbox"])
                    if rect.width < MIN_IMAGE_SIDE or rect.height < MIN_IMAGE_SIDE:
                        continue
                    if any(_overlap_ratio(rect, t) > 0.3 for t in table_rects):
                        continue
                    png = _render(page, rect, dpi)
                    h = hashlib.sha256(png).hexdigest()
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    labels = " ".join(
                        re.sub(r"\s+", " ", str(b[4])).strip()
                        for b in page.get_text("blocks") if fitz.Rect(b[:4]).intersects(rect)
                    )[:800]
                    figures.append(FigurePiece(page_no, _rect_tuple(rect), png, "image", labels))
            except Exception as exc:
                result.failures.append(f"p{page_no} images: {exc}")

            # 3. vector figures
            try:
                text_blocks = page.get_text("blocks")
                for rect in _vector_clusters(page, table_rects):
                    grown = fitz.Rect(rect.x0 - PAD_POINTS, rect.y0 - PAD_POINTS,
                                      rect.x1 + PAD_POINTS, rect.y1 + PAD_POINTS) & page.rect
                    labels = []
                    for b in text_blocks:
                        br = fitz.Rect(b[:4])
                        if grown.intersects(br):
                            grown = _union([grown, br])
                            labels.append(re.sub(r"\s+", " ", str(b[4])).strip())
                    grown = fitz.Rect(max(0, grown.x0 - 4), max(0, grown.y0 - 4),
                                      min(page.rect.x1, grown.x1 + 4), min(page.rect.y1, grown.y1 + 4))
                    png = _render(page, grown, dpi)
                    h = hashlib.sha256(png).hexdigest()
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    figures.append(FigurePiece(page_no, _rect_tuple(grown), png, "vector", " ".join(labels)[:800]))
            except Exception as exc:
                result.failures.append(f"p{page_no} vectors: {exc}")

            # 4. text, excluding tables and figures
            excluded = table_rects + [fitz.Rect(f.bbox) for f in figures]
            page_text: list[str] = []
            for block in page.get_text("blocks"):
                rect = fitz.Rect(block[:4])
                text = re.sub(r"[ \t]+", " ", str(block[4])).strip()
                if len(text) < 2 or not re.search(r"[A-Za-z]", text):
                    continue
                if any(_overlap_ratio(rect, ex) > 0.3 for ex in excluded):
                    continue
                result.text.append(TextPiece(page_no, _rect_tuple(rect), text))
                page_text.append(text)

            result.tables.extend(tables)
            result.figures.extend(figures)

            if not page_text and not tables and not figures:
                result.empty_pages.append(page_no)
        except Exception as exc:
            result.failures.append(f"p{page_no}: {exc}")

    doc.close()
    return result

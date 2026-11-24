"""Shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Modality = Literal["text", "table", "visual"]


@dataclass
class Chunk:
    document_id: str
    chunk_id: str
    modality: Modality
    content: str
    source: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    asset_path: str | None = None
    asset_hash: str | None = None
    table_number: int | None = None
    part: int | None = None
    caption_model: str | None = None
    caption_status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "modality": self.modality,
            "content": self.content,
            "source": self.source,
            "page": self.page,
        }
        if self.bbox:
            data["bbox"] = list(self.bbox)
        if self.asset_path:
            data["asset_path"] = self.asset_path
        if self.asset_hash:
            data["asset_hash"] = self.asset_hash
        if self.table_number is not None:
            data["table_number"] = self.table_number
        if self.part is not None:
            data["part"] = self.part
        if self.caption_model:
            data["caption_model"] = self.caption_model
        if self.caption_status:
            data["caption_status"] = self.caption_status
        data.update(self.extra)
        return data


@dataclass
class Hit:
    score: float
    payload: dict[str, Any]

    @property
    def modality(self) -> str:
        return self.payload.get("modality", "text")

    @property
    def page(self) -> int:
        return int(self.payload.get("page", 0))

    @property
    def content(self) -> str:
        return self.payload.get("content", "")

    @property
    def asset_path(self) -> str | None:
        return self.payload.get("asset_path")

    def source_ref(self) -> dict[str, Any]:
        return {
            "chunk_id": self.payload.get("chunk_id"),
            "page": self.page,
            "modality": self.modality,
            "score": round(float(self.score), 3),
            "document_id": self.payload.get("document_id"),
            "source": self.payload.get("source"),
            "asset_path": self.asset_path,
        }


@dataclass
class Answer:
    answer: str
    route: str
    sources: list[dict[str, Any]]
    usage: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "route": self.route,
            "sources": self.sources,
            "usage": self.usage,
            "trace_id": self.trace_id,
        }

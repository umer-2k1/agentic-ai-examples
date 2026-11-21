"""Qdrant Cloud: collection setup, upsert, search. Embeddings via Cloud Inference."""

from __future__ import annotations

import uuid
from typing import Iterable

from qdrant_client import QdrantClient, models

from .config import settings
from .models import Chunk, Hit

NAMESPACE = uuid.UUID("6f2b1a5e-3c7d-4f2a-9c11-6d0e2b8a7f31")


def _cloud_doc(text: str):
    """Qdrant Cloud Inference object (name differs across client versions)."""
    cls = getattr(models, "Document", None) or getattr(models, "InferenceObject", None)
    if cls is None:
        raise RuntimeError("qdrant-client too old: no Document/InferenceObject")
    return cls(text=text, model=settings.embed_model)


def point_id(document_id: str, chunk_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{document_id}:{chunk_id}"))


class VectorStore:
    def __init__(self) -> None:
        if not settings.qdrant_url:
            raise RuntimeError("QDRANT_URL is missing")
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=90,
            cloud_inference=True,
        )
        self.collection = settings.collection
        self._ready = False

    # ---------- setup ----------
    def _collection_size(self) -> int | None:
        try:
            info = self.client.get_collection(self.collection)
        except Exception:
            return None
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):  # named vectors
            first = next(iter(vectors.values()))
            return int(first.size)
        return int(getattr(vectors, "size", 0))

    def ensure(self) -> None:
        if self._ready:
            return
        if not self.collection:
            raise RuntimeError("QDRANT_COLLECTION is missing")
        size = self._collection_size()
        if size is None:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=settings.embed_dim, distance=models.Distance.COSINE),
            )
        elif size != settings.embed_dim:
            raise RuntimeError(
                f"Collection {self.collection!r} has vector size {size}, expected {settings.embed_dim}. "
                "Refusing to modify it."
            )

        for field_name, schema in (
            ("modality", models.PayloadSchemaType.KEYWORD),
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("page", models.PayloadSchemaType.INTEGER),
            ("source", models.PayloadSchemaType.KEYWORD),
        ):
            try:
                self.client.create_payload_index(self.collection, field_name, schema)
            except Exception:
                pass  # already exists
        self._ready = True

    # ---------- writes ----------
    def upsert(self, chunks: Iterable[Chunk], batch: int = 32) -> int:
        self.ensure()
        pending: list[models.PointStruct] = []
        total = 0
        for chunk in chunks:
            payload = chunk.payload()
            content = chunk.content.strip()
            if not content:
                continue
            pending.append(
                models.PointStruct(
                    id=point_id(chunk.document_id, chunk.chunk_id),
                    vector=_cloud_doc(content),
                    payload=payload,
                )
            )
            if len(pending) >= batch:
                self.client.upsert(self.collection, points=pending, wait=True)
                total += len(pending)
                pending = []
        if pending:
            self.client.upsert(self.collection, points=pending, wait=True)
            total += len(pending)
        return total

    def delete_document(self, document_id: str) -> None:
        self.ensure()
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )

    # ---------- reads ----------
    def search(self, question: str, k: int = 6, modalities: list[str] | None = None,
               fetch: int | None = None) -> list[Hit]:
        self.ensure()
        query_filter = None
        if modalities:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="modality", match=models.MatchAny(any=modalities))]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=_cloud_doc(question),
            limit=fetch or max(k, 8),
            query_filter=query_filter,
            with_payload=True,
        )
        return [Hit(score=p.score, payload=p.payload or {}) for p in response.points]

    def count(self, document_id: str | None = None) -> int:
        self.ensure()
        flt = None
        if document_id:
            flt = models.Filter(
                must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
            )
        return int(self.client.count(self.collection, count_filter=flt, exact=True).count)

    def health(self) -> dict:
        try:
            self.ensure()
            info = self.client.get_collection(self.collection)
            return {"ok": True, "collection": self.collection,
                    "points": int(getattr(info, "points_count", 0) or 0)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


store = VectorStore()

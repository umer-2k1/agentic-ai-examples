"""Configuration loaded from multimodal-RAG/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def _load_env(path: Path) -> None:
    """Minimal .env loader (no dependency on python-dotenv at import time)."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env(ENV_PATH)
_load_env(ENV_PATH.parent.parent / ".env")

EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    qdrant_url: str = os.getenv("QDRANT_URL", "").rstrip("/")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    collection: str = os.getenv("QDRANT_COLLECTION", "multimodal_rag")

    openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
    vision_model: str = os.getenv("OPENROUTER_VISION_MODEL", "nvidia/nemotron-3.5-super-vl:free")
    text_model: str = os.getenv("OPENROUTER_TEXT_MODEL", "nvidia/nemotron-3.5-lightning:free")
    groq_key: str = os.getenv("GROQ_API_KEY", "")

    embed_model: str = EMBED_MODEL
    embed_dim: int = _int("EMBED_DIM", 384)

    top_k: int = _int("TOP_K", 6)
    page_dpi: int = _int("PAGE_RENDER_DPI", 200)
    image_max_px: int = _int("VLM_IMAGE_MAX_PX", 1600)
    min_visual_score: float = float(os.getenv("MIN_VISUAL_SCORE", "0.35"))

    asset_dir: Path = field(default_factory=lambda: Path(os.getenv("ASSET_DIR", str(ROOT / "assets"))))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(ROOT / "data"))))

    vision_fallbacks: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            m.strip()
            for m in os.getenv(
                "OPENROUTER_VISION_FALLBACKS",
                "google/gemma-4-31b-it:free,particle-ai/particle-1:free,inclusionai/ling-3.2-flash:free",
            ).split(",")
            if m.strip()
        )
    )
    text_fallbacks: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            m.strip()
            for m in os.getenv(
                "OPENROUTER_TEXT_FALLBACKS",
                "nvidia/nemotron-3-ultra-550b-a55b:free,baidu/ernie-5.5-flash-preview:free,groq:openai/gpt-oss-120b",
            ).split(",")
            if m.strip()
        )
    )

    @property
    def manifests_dir(self) -> Path:
        return self.data_dir / "manifests"

    @property
    def pdfs_dir(self) -> Path:
        return self.data_dir / "pdfs"

    def vision_model_chain(self) -> tuple[str, ...]:
        chain = [self.vision_model, *self.vision_fallbacks]
        seen, out = set(), []
        for m in chain:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return tuple(out)

    def text_model_chain(self) -> tuple[str, ...]:
        chain = [self.text_model, *self.text_fallbacks]
        seen, out = set(), []
        for m in chain:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return tuple(out)

    def validate(self) -> list[str]:
        problems = []
        if not self.qdrant_url:
            problems.append("QDRANT_URL is missing")
        if not self.qdrant_api_key:
            problems.append("QDRANT_API_KEY is missing")
        if not self.collection:
            problems.append("QDRANT_COLLECTION is missing")
        if not self.openrouter_key:
            problems.append("OPENROUTER_API_KEY is missing")
        return problems

    def ensure_dirs(self) -> None:
        for d in (self.asset_dir, self.manifests_dir, self.pdfs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()

VISION_PROMPT = (
    "Describe this figure factually in 60-120 words. Include every number, axis label, "
    "unit and trend direction. Do not interpret or speculate. If it is a diagram, state "
    "what connects to what."
)

ANSWER_TEXT_PROMPT = (
    "Answer only from the context below. If the answer is missing, say \"not in the document\". "
    "Cite the page for every number as [p4]. Write plain text: no markdown, no bold, no bullet lists."
)

ANSWER_VISION_PROMPT = (
    "Answer only from the context and the attached images. Read values directly from the image; "
    "do not estimate or interpolate. Cite the page as [p7]. Write plain text: no markdown, no bold. "
    "If a value is not visible, say so."
)

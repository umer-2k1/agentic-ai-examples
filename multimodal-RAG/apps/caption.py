"""VLM captions via OpenRouter (free vision models, with fallbacks)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import time

import httpx
from PIL import Image

from .config import VISION_PROMPT, settings

API = "https://openrouter.ai/api/v1/chat/completions"


class CaptionError(RuntimeError):
    pass


def _downscale(png: bytes, max_px: int) -> bytes:
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGB")
        w, h = im.size
        longest = max(w, h)
        if longest > max_px:
            scale = max_px / longest
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue()


def _extract_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise CaptionError("empty response")
    content = choices[0].get("message", {}).get("content")
    if isinstance(content, list):
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    text = (content or "").strip()
    if not text or text.lower() == "none":
        raise CaptionError("empty content")
    return text


def _cache_path(digest: str):
    folder = settings.data_dir / "captions"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def caption_png(png: bytes) -> tuple[str, str]:
    """Return (caption, model). Raises CaptionError if every model fails."""
    if not settings.openrouter_key:
        raise CaptionError("OPENROUTER_API_KEY missing")

    digest = hashlib.sha256(png).hexdigest()
    cached = _cache_path(digest)
    if cached.exists():
        try:
            data = json.loads(cached.read_text())
            return data["caption"], data["model"]
        except Exception:
            pass

    image_b64 = base64.b64encode(_downscale(png, settings.image_max_px)).decode()
    data_url = f"data:image/jpeg;base64,{image_b64}"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_key}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "multimodal-rag",
    }

    last_error = "no model configured"
    for model in settings.vision_model_chain():
        for attempt in range(3):
            try:
                resp = httpx.post(
                    API,
                    headers=headers,
                    json={
                        "model": model,
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": VISION_PROMPT},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }],
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    text = _extract_text(resp.json())
                    if text:
                        cached.write_text(json.dumps({"caption": text, "model": model}))
                        return text, model
                    last_error = "empty caption"
                elif resp.status_code in (429, 502, 503):
                    last_error = f"{model}: HTTP {resp.status_code}"
                    time.sleep(2 * (attempt + 1))
                else:
                    last_error = f"{model}: HTTP {resp.status_code} {resp.text[:160]}"
                    break
            except Exception as exc:  # network / timeout
                last_error = f"{model}: {type(exc).__name__}"
                time.sleep(2 * (attempt + 1))
    raise CaptionError(last_error)

"""Retrieval, routing and generation (sync + streaming)."""

from __future__ import annotations

import base64
import io
import json
from typing import Generator, Iterable

import httpx
from PIL import Image

from .assets import storage
from .config import ANSWER_TEXT_PROMPT, ANSWER_VISION_PROMPT, settings
from .models import Answer, Hit
from .vectorstore import store

API = "https://openrouter.ai/api/v1/chat/completions"
MAX_CONTEXT_CHARS = 1200
MAX_IMAGES = 2


# ---------- retrieval ----------

def retrieve(question: str, k: int | None = None, modalities: list[str] | None = None) -> list[Hit]:
    k = k or settings.top_k
    candidates = store.search(question, k=k, modalities=modalities, fetch=max(k * 2, 8))
    selected = candidates[:k]

    # keep a visual only when it is genuinely competitive with the top hit
    if not any(h.modality == "visual" for h in selected):
        top = selected[0].score if selected else 0.0
        threshold = max(settings.min_visual_score, top * 0.9)
        visual = next(
            (h for h in candidates if h.modality == "visual" and h.score >= threshold),
            None,
        )
        if visual:
            selected = (selected[: k - 1] + [visual]) if len(selected) >= k else selected + [visual]
    return selected


def context_blocks(hits: Iterable[Hit]) -> str:
    blocks = []
    for hit in hits:
        label = f"[p{hit.page} · {hit.modality}]"
        blocks.append(f"{label}\n{hit.content[:MAX_CONTEXT_CHARS]}")
    return "\n\n".join(blocks)


def route_for(hits: Iterable[Hit]) -> str:
    return "vision" if any(h.modality == "visual" for h in hits) else "text"


# ---------- prompt building ----------

def _image_part(png_path) -> dict | None:
    try:
        with Image.open(png_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            longest = max(w, h)
            if longest > settings.image_max_px:
                s = settings.image_max_px / longest
                im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    except Exception:
        return None


def _messages(question: str, hits: list[Hit], route: str) -> tuple[list[dict], bool]:
    context = context_blocks(hits)
    prompt = ANSWER_VISION_PROMPT if route == "vision" else ANSWER_TEXT_PROMPT
    text = f"CONTEXT\n{context}\n\nQUESTION\n{question}"

    content: list[dict] = [{"type": "text", "text": text}]
    used_image = False
    if route == "vision":
        visuals = [h for h in hits if h.modality == "visual" and h.asset_path][:MAX_IMAGES]
        for hit in visuals:
            path = storage.resolve(hit.asset_path)
            if not storage.exists(hit.asset_path):
                continue
            part = _image_part(path)
            if part:
                content.append(part)
                used_image = True
    if not used_image:
        content = [{"type": "text", "text": text}]
    return [{"role": "system", "content": prompt}, {"role": "user", "content": content}], used_image


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.openrouter_key}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "multimodal-rag",
    }


def _models_for(route: str) -> tuple[str, ...]:
    return settings.vision_model_chain() if route == "vision" else settings.text_model_chain()


def _provider(model: str) -> tuple[str, dict, str]:
    """Route a model id to its API. 'groq:' prefix uses Groq (text only)."""
    if model.startswith("groq:"):
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {settings.groq_key}"},
            model.split(":", 1)[1],
        )
    return API, _headers(), model


def _sources(hits: list[Hit]) -> list[dict]:
    out = []
    for hit in hits:
        ref = hit.source_ref()
        ref["snippet"] = hit.content[:180]
        out.append(ref)
    return out


# ---------- sync ----------

def answer(question: str, k: int | None = None, modalities: list[str] | None = None) -> Answer:
    hits = retrieve(question, k, modalities)
    if not hits:
        return Answer("Not in the document.", "none", [])

    route = route_for(hits)
    messages, used_image = _messages(question, hits, route)
    if route == "vision" and not used_image:
        route = "text"
        messages, _ = _messages(question, hits, route)

    last_error = None
    for model in _models_for(route):
        try:
            url, headers, name = _provider(model)
            resp = httpx.post(
                url,
                headers=headers,
                json={"model": name, "messages": messages, "temperature": 0.1, "max_tokens": 700},
                timeout=180,
            )
            if resp.status_code != 200:
                last_error = f"{model}: HTTP {resp.status_code}"
                continue
            payload = resp.json()
            choices = payload.get("choices") or []
            if not choices:
                last_error = f"{model}: empty response"
                continue
            content = choices[0]["message"]["content"]
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return Answer(content.strip(), route, _sources(hits), payload.get("usage", {}))
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}"

    if route == "vision":
        # last resort: answer from the text context without the images
        text_messages, _ = _messages(question, hits, "text")
        for model in _models_for("text"):
            try:
                url, headers, name = _provider(model)
                resp = httpx.post(url, headers=headers,
                                  json={"model": name, "messages": text_messages,
                                        "temperature": 0.1, "max_tokens": 700}, timeout=180)
                if resp.status_code != 200:
                    last_error = f"{model}: HTTP {resp.status_code}"
                    continue
                payload = resp.json()
                choices = payload.get("choices") or []
                if not choices:
                    continue
                content = choices[0]["message"]["content"]
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                return Answer(content.strip(), "text", _sources(hits), payload.get("usage", {}))
            except Exception as exc:
                last_error = f"{model}: {type(exc).__name__}"

    return Answer(f"Generation failed ({last_error}).", route, _sources(hits))


# ---------- streaming ----------

def stream_answer(question: str, k: int | None = None,
                  modalities: list[str] | None = None) -> Generator[tuple[str, dict], None, None]:
    """Yield (event, data) tuples: meta, token, done, error."""
    hits = retrieve(question, k, modalities)
    route = route_for(hits) if hits else "none"
    yield "meta", {"route": route, "sources": _sources(hits), "k": k or settings.top_k}

    if not hits:
        yield "token", {"text": "Not in the document."}
        yield "done", {"usage": {}, "finish_reason": "stop"}
        return

    messages, used_image = _messages(question, hits, route)
    if route == "vision" and not used_image:
        route = "text"
        messages, _ = _messages(question, hits, route)
        yield "meta", {"route": route, "sources": _sources(hits), "k": k or settings.top_k}

    last_error = None
    for model in _models_for(route):
        try:
            url, headers, name = _provider(model)
            with httpx.stream(
                "POST",
                url,
                headers=headers,
                json={"model": name, "messages": messages, "temperature": 0.1,
                      "max_tokens": 700, "stream": True},
                timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    last_error = f"{model}: HTTP {resp.status_code}"
                    resp.read()
                    continue
                started = False
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        started = True
                        yield "token", {"text": delta}
                    if choices[0].get("finish_reason"):
                        yield "done", {"usage": event.get("usage", {}),
                                       "finish_reason": choices[0]["finish_reason"]}
                        return
                if started:
                    yield "done", {"usage": {}, "finish_reason": "stop"}
                    return
                last_error = f"{model}: empty stream"
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}"

    if route == "vision":
        text_messages, _ = _messages(question, hits, "text")
        for model in _models_for("text"):
            try:
                url, headers, name = _provider(model)
                with httpx.stream("POST", url, headers=headers,
                                  json={"model": name, "messages": text_messages, "temperature": 0.1,
                                        "max_tokens": 700, "stream": True}, timeout=180) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        last_error = f"{model}: HTTP {resp.status_code}"
                        continue
                    started = False
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}).get("content")
                        if delta:
                            started = True
                            yield "token", {"text": delta}
                        if choices[0].get("finish_reason"):
                            yield "done", {"usage": event.get("usage", {}),
                                           "finish_reason": choices[0]["finish_reason"]}
                            return
                    if started:
                        yield "done", {"usage": {}, "finish_reason": "stop"}
                        return
            except Exception as exc:
                last_error = f"{model}: {type(exc).__name__}"

    yield "error", {"message": f"Generation failed ({last_error}).", "retryable": True}

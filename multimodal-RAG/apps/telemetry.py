"""OpenTelemetry setup, exported to LangSmith (OTLP) or a local JSONL file."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from .config import settings

_configured = False
_exporter_name = "none"
log = logging.getLogger("mmrag")


class JsonlSpanExporter(SpanExporter):
    """Writes one JSON object per span. No backend required."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            ctx = span.get_span_context()
            parent = span.parent
            self._fh.write(json.dumps({
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
                "parent_id": format(parent.span_id, "016x") if parent else None,
                "name": span.name,
                "start_ns": span.start_time,
                "end_ns": span.end_time,
                "duration_ms": round(((span.end_time or 0) - span.start_time) / 1e6, 2),
                "status": span.status.status_code.name if span.status else "UNSET",
                "attributes": dict(span.attributes or {}),
            }, ensure_ascii=False) + "\n")
        self._fh.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self._fh.close()


class TraceLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else "-"
        record.span_id = format(ctx.span_id, "016x") if ctx.is_valid else "-"
        return True


def _build_exporter() -> tuple[SpanExporter, str]:
    """LangSmith first (if a key exists), then any OTLP endpoint, then JSONL."""
    langsmith_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    if langsmith_key:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        base = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com/otel").rstrip("/")
        project = os.getenv("LANGSMITH_PROJECT", settings.collection or "multimodal-rag")
        return OTLPSpanExporter(
            endpoint=f"{base}/v1/traces",
            headers={"x-api-key": langsmith_key, "Langsmith-Project": project},
            timeout=20,
        ), f"langsmith:{project}"

    otlp = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otlp:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=f"{otlp.rstrip('/')}/v1/traces", timeout=20), f"otlp:{otlp}"

    return JsonlSpanExporter(settings.data_dir / "traces.jsonl"), "jsonl"


def setup_telemetry(app=None) -> str:
    global _configured, _exporter_name
    if _configured:
        return _exporter_name
    if os.getenv("OTEL_ENABLED", "1") != "1":
        _configured = True
        _exporter_name = "disabled"
        return _exporter_name

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "multimodal-rag"),
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("APP_ENV", "local"),
    })
    provider = TracerProvider(resource=resource)
    exporter, name = _build_exporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _exporter_name = name

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        log.warning("httpx instrumentation failed: %s", exc)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health,api/health,favicon.ico")
        except Exception as exc:  # pragma: no cover
            log.warning("fastapi instrumentation failed: %s", exc)

    # structured app logs with trace ids
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(TraceLogFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(trace_id)s] %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False

    _configured = True
    log.info("telemetry exporter: %s", name)
    return name


def exporter_name() -> str:
    return _exporter_name


@contextmanager
def span(name: str, **attributes):
    """Span with primitive attributes; lists/dicts are stringified."""
    with trace.get_tracer("mmrag").start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is None:
                continue
            if not isinstance(value, (str, int, float, bool)):
                value = str(value)
            current.set_attribute(key, value)
        yield current


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def set_gen_ai(current, model: str, provider: str, usage: dict | None = None) -> None:
    """OTel GenAI semantic conventions — LangSmith renders these as an LLM call."""
    current.set_attribute("gen_ai.system", provider)
    current.set_attribute("gen_ai.request.model", model)
    if usage:
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion = usage.get("completion_tokens") or usage.get("output_tokens")
        if prompt is not None:
            current.set_attribute("gen_ai.usage.input_tokens", int(prompt))
        if completion is not None:
            current.set_attribute("gen_ai.usage.output_tokens", int(completion))

"""OpenTelemetry tracing for the RAG pipeline (optional, config-gated).

When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (e.g. a local LGTM stack, Grafana
Cloud, Honeycomb, or Jaeger), every request to the API is traced end-to-end:
FastAPI auto-instrumentation creates the server span, and the RAG stages are
explicit child spans — ``normalize``, ``retrieve``, ``generate``, and
``verify_quotes`` — so a slow or low-quality answer can be attributed to the
exact stage that caused it.

Without the endpoint configured, no provider is registered and every span is
a no-op: tracing adds no overhead and no dependency on external services.
Attributes carry only model names, document counts, and timings — never
question text, profile data, or API keys.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_tracer = None


def get_tracer():
    """The pipeline tracer (no-op when tracing is not configured)."""
    global _tracer
    if _tracer is None:
        from opentelemetry import trace

        _tracer = trace.get_tracer("schemegpt.rag")
    return _tracer


def setup_tracing(app) -> bool:
    """Configure OTel when an OTLP endpoint is configured. Returns enabled."""
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", "").strip()
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": "schemegpt-api", "service.version": "2.0"}
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry tracing enabled -> %s", endpoint)
        return True
    except Exception:
        # Tracing must never prevent the API from starting.
        logger.warning("OpenTelemetry setup failed; tracing disabled.", exc_info=True)
        return False


def stage_span(name: str, attributes: dict | None = None):
    """Context manager for a RAG stage span; safe when tracing is disabled."""
    return get_tracer().start_as_current_span(name, attributes=attributes or {})

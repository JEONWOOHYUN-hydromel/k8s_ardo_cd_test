import logging
import os
import random
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "orders-api")
APP_ENV = os.getenv("APP_ENV", "local")


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = (
            format(span_context.trace_id, "032x") if span_context.trace_id else "-"
        )
        return True


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s trace_id=%(trace_id)s %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(TraceContextFilter())
    return logging.getLogger("orders_api")


def configure_tracing() -> trace.Tracer:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE_NAME,
                "deployment.environment": APP_ENV,
            }
        )
    )

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(__name__)


logger = configure_logging()
tracer = configure_tracing()

app = FastAPI(title="Kubernetes Observability GitOps Lab")
FastAPIInstrumentor.instrument_app(app)


ORDERS: dict[int, dict[str, Any]] = {
    1: {"id": 1, "item": "notebook", "status": "paid", "total": 18_000},
    2: {"id": 2, "item": "keyboard", "status": "packed", "total": 42_000},
    3: {"id": 3, "item": "monitor", "status": "shipped", "total": 210_000},
}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "env": APP_ENV}


@app.get("/api/orders")
def list_orders() -> dict[str, Any]:
    logger.info("listing orders")
    return {"orders": list(ORDERS.values())}


@app.get("/api/orders/{order_id}")
def get_order(order_id: int) -> dict[str, Any]:
    with tracer.start_as_current_span("fake_db_lookup") as span:
        span.set_attribute("db.system", "fake-postgres")
        span.set_attribute("order.id", order_id)
        time.sleep(random.uniform(0.05, 0.18))

        order = ORDERS.get(order_id)
        if not order:
            logger.warning("order not found: %s", order_id)
            raise HTTPException(status_code=404, detail="order not found")

        logger.info("loaded order: %s", order_id)
        return order


@app.get("/api/error")
def raise_error() -> dict[str, str]:
    with tracer.start_as_current_span("intentional_error"):
        logger.error("raising intentional error")
        raise HTTPException(status_code=500, detail="intentional practice error")

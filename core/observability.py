"""Observabilité LLM optionnelle via OpenInference (traçage OpenTelemetry).

Quand c'est activé, chaque appel LLM (litellm) est tracé selon les conventions
OpenInference (prompt, réponse, modèle, tokens, latence) et exporté en OTLP vers un
collecteur — typiquement **Phoenix** (Arize, auto-hébergeable) qui offre un explorateur
de traces + des évaluations.

100 % OPTIONNEL et sans impact si désactivé ou si les paquets ne sont pas installés :
  pip install openinference-instrumentation-litellm opentelemetry-sdk opentelemetry-exporter-otlp

Activation (variables d'environnement) :
  OPENINFERENCE_ENABLED=true
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces   (défaut Phoenix)
  OTEL_SERVICE_NAME=athena                                       (optionnel)
"""
import logging
import os

logger = logging.getLogger("athena.observability")
_initialized = False


def enabled() -> bool:
    return os.getenv("OPENINFERENCE_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def endpoint() -> str:
    return (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            or os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").strip()
            or "http://localhost:6006/v1/traces")


def setup() -> bool:
    """Initialise le traçage si activé. Best-effort : n'échoue jamais le démarrage.
    Renvoie True si l'instrumentation a bien été posée."""
    global _initialized
    if _initialized or not enabled():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from openinference.instrumentation.litellm import LiteLLMInstrumentor

        resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "athena")})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint())))
        trace.set_tracer_provider(provider)
        LiteLLMInstrumentor().instrument(tracer_provider=provider)

        _initialized = True
        logger.info("OpenInference actif → traces LLM exportées vers %s", endpoint())
        print(f"📡 OpenInference : traçage LLM actif (OTLP → {endpoint()})")
        return True
    except ImportError:
        logger.warning("OPENINFERENCE_ENABLED=true mais paquets manquants "
                       "(pip install openinference-instrumentation-litellm opentelemetry-sdk "
                       "opentelemetry-exporter-otlp). Traçage désactivé.")
        return False
    except Exception as e:
        logger.warning("Initialisation OpenInference échouée : %s", e)
        return False

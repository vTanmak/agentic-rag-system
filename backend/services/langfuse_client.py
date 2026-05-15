

import logging
import uuid

from langfuse import Langfuse

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LangfuseClient:

    def __init__(self):
        self._client: Langfuse | None = None
        self._enabled = bool(
            settings.langfuse_public_key and settings.langfuse_secret_key
        )
        if self._enabled:
            try:
                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                logger.info("Langfuse observability enabled")
            except Exception as e:
                logger.warning(f"Langfuse init failed (tracing disabled): {e}")
                self._enabled = False
        else:
            logger.info("Langfuse keys not set — observability disabled")

    def create_trace(self, name: str, user_id: str = "anonymous") -> str:

        trace_id = str(uuid.uuid4())
        if self._enabled and self._client:
            try:
                if hasattr(self._client, "start_trace"):
                    self._client.start_trace(id=trace_id, name=name, user_id=user_id)
                elif hasattr(self._client, "trace"):
                    self._client.trace(id=trace_id, name=name, user_id=user_id)
                else:
                    self._enabled = False
            except Exception as e:
                logger.warning(f"Failed to create Langfuse trace: {e}")
                self._enabled = False
        return trace_id

    def log_llm_call(
        self,
        trace_id: str,
        step_name: str,
        input_text: str,
        output_text: str,
        model: str = "",
        latency_ms: float = 0.0,
    ) -> None:

        if not (self._enabled and self._client):
            return
        try:
            if hasattr(self._client, "start_trace"):
                self._client.generation(
                    trace_id=trace_id,
                    name=step_name,
                    model=model,
                    input=input_text,
                    output=output_text,
                    metadata={"latency_ms": latency_ms},
                )
            elif hasattr(self._client, "trace"):
                trace = self._client.trace(id=trace_id)
                trace.generation(
                    name=step_name,
                    model=model,
                    input=input_text,
                    output=output_text,
                    metadata={"latency_ms": latency_ms},
                )
        except Exception as e:
            logger.warning(f"Failed to log LLM call to Langfuse: {e}")
            self._enabled = False

    def log_score(self, trace_id: str, name: str, value: float) -> None:
        if not (self._enabled and self._client):
            return
        try:
            self._client.score(
                trace_id=trace_id,
                name=name,
                value=value
            )
        except Exception as e:
            logger.warning(f"Failed to log score to Langfuse: {e}")

    def flush(self) -> None:

        if self._enabled and self._client:
            try:
                self._client.flush()
            except Exception:
                pass


langfuse_client = LangfuseClient()

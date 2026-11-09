"""Puerto del cliente LLM — contrato y DTOs de transporte, sin infraestructura (R-AP-2).

Lo usan P2 y P6. Las etapas dependen de `LlmClient`, nunca de un adaptador concreto;
los adaptadores (`openai_llm.py`, `anthropic_llm.py`, `ollama_llm.py`) y el fake
(`llm_fake.py`) lo implementan por duck typing (R-AP-3).
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """Solicitud al LLM. El prompt ya viene formateado por la etapa.

    La etapa la construye combinando su prompt con los parámetros de `LlmSettings`
    del contrato; así el puerto no depende de `pipeline/contracts/`.
    """

    prompt: str
    model: str  # modelo concreto; viene de `LlmSettings.model` del contrato
    # Instrucciones de sistema (D-LLM-1). Cada adaptador las coloca donde su API las espera.
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    # Parámetros adicionales específicos del proveedor (top_p, seed, etc.).
    # dict: `frozen` no lo hace inmutable por dentro.
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LlmResponse:
    """Respuesta del LLM. Contiene solo lo que el pipeline necesita."""

    text: str  # texto generado (JSON crudo para P2/P6; lo valida el contrato de la etapa)
    input_tokens: int | None  # para `LlmRun` en `StageResult`
    output_tokens: int | None  # para `LlmRun` en `StageResult`
    latency_ms: int | None  # para `LlmRun` en `StageResult`


class LlmClient(Protocol):
    """Puerto de comunicación con el LLM. Lo implementan OpenAI, Anthropic, Ollama y el fake."""

    async def complete(self, request: LlmRequest) -> LlmResponse:
        """Envía el prompt y devuelve la respuesta. Lanza `LlmError` (o un subtipo) ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera las conexiones del cliente. `main.py` lo llama al apagar el servicio."""
        ...

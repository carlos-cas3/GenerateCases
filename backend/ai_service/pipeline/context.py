"""Contexto tipado compartido entre etapas durante una ejecución.

Ciclo de vida
-------------
El orquestador crea un ``PipelineContext`` al inicio y lo pasa a cada etapa en
orden. Cada etapa deposita su output en el campo ``pN_output`` correspondiente
para que las etapas posteriores lo lean.

Los campos de output son ``None`` hasta que la etapa que los produce completa
con éxito. Una etapa nunca debe leer el output de una etapa que aún no corrió.

Por qué acumulador y no encadenamiento directo
----------------------------------------------
P5 necesita P1Output (HU) + P2Output (RF) + P4Output (clusters, opcional).
Con encadenamiento directo ``run(prev_output)`` el orquestador tendría que saber
qué outputs combinar para cada etapa, rompiendo su carácter genérico. El
contexto acumulador mantiene la firma uniforme ``run(context)`` en ``StageBase``
y deja que cada etapa declare sus dependencias leyendo los campos que necesita.

TYPE_CHECKING e imports diferidos
----------------------------------
``from __future__ import annotations`` hace que todas las anotaciones del módulo
se traten como strings en runtime (evaluación diferida), evitando que Python
intente resolver los nombres de los contratos al importar este módulo.

El bloque ``if TYPE_CHECKING`` solo se ejecuta cuando mypy/pyright inspeccionan
el código, nunca en runtime. Resultado: cero imports de ``pipeline/contracts/``
en runtime, pero el análisis estático y el autocompletado funcionan con tipos
completos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from ai_service.pipeline.contracts.p1 import P1Output
    from ai_service.pipeline.contracts.p2 import P2Output
    from ai_service.pipeline.contracts.p3 import P3Output
    from ai_service.pipeline.contracts.p4 import P4Output
    from ai_service.pipeline.contracts.p5 import P5Output


@dataclass(frozen=True, slots=True)
class PipelineConfiguration:
    """Configuración efectiva de la ejecución (valores por defecto ya aplicados)."""

    clustering_enabled: bool
    method_type: str


@dataclass(slots=True)
class PipelineContext:
    """Payload mutable de la ejecución.

    Campos de arranque
    ------------------
    ``generation_id``, ``document_id`` y ``configuration`` los fija el servicio
    de ejecución antes de llamar al orquestador y no se modifican después.

    Outputs de etapa
    ----------------
    Cada campo ``pN_output`` lo escribe la etapa N al completar con éxito.
    Se anotan bajo ``TYPE_CHECKING`` para evitar imports circulares en runtime;
    el análisis estático (mypy/pyright) los ve completamente tipados.

    Regla de lectura por etapa
    --------------------------
    - P2 lee  ``p1_output``
    - P3 lee  ``p2_output``                          (solo si clustering_enabled)
    - P4 lee  ``p2_output``, ``p3_output``           (solo si clustering_enabled)
    - P5 lee  ``p1_output``, ``p2_output``, ``p4_output`` (p4_output puede ser None)
    - P6 lee  ``p5_output``
    - P7 lee  ``p2_output``, ``p6_output``
    """

    # --- arranque (no se modifican tras la construcción) ---
    generation_id: UUID
    document_id: UUID
    configuration: PipelineConfiguration

    # --- outputs de etapa (None hasta que la etapa completa con éxito) ---
    p1_output: P1Output | None = field(default=None)
    p2_output: P2Output | None = field(default=None)
    p3_output: P3Output | None = field(default=None)
    p4_output: P4Output | None = field(default=None)
    p5_output: P5Output | None = field(default=None)

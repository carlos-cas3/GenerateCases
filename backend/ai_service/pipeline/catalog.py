"""Catálogo de etapas P1–P7. El `name` visible de la API sale de aquí; no se almacena."""

from dataclasses import dataclass

from ai_service.schemas.generations import StageKey


@dataclass(frozen=True, slots=True)
class StageDefinition:
    key: StageKey
    name: str
    order: int


STAGE_CATALOG: tuple[StageDefinition, ...] = (
    StageDefinition(StageKey.P1, "Normalización de historias de usuario", 1),
    StageDefinition(StageKey.P2, "Extracción de requisitos funcionales", 2),
    StageDefinition(StageKey.P3, "Generación de embeddings", 3),
    StageDefinition(StageKey.P4, "Clustering semántico", 4),
    StageDefinition(StageKey.P5, "Construcción de contexto estructurado", 5),
    StageDefinition(StageKey.P6, "Generación de casos de prueba funcionales", 6),
    StageDefinition(StageKey.P7, "Evaluación de resultados", 7),
)

_BY_KEY: dict[StageKey, StageDefinition] = {stage.key: stage for stage in STAGE_CATALOG}


def get_stage_definition(key: StageKey) -> StageDefinition:
    """Devuelve la definición de catálogo de una etapa."""
    return _BY_KEY[key]

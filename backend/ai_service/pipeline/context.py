"""Contexto tipado compartido entre etapas durante una ejecución."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PipelineConfiguration:
    """Configuración efectiva de la ejecución (valores por defecto ya aplicados)."""

    clustering_enabled: bool
    method_type: str


@dataclass(slots=True)
class PipelineContext:
    """Datos de una ejecución. Las fases posteriores añadirán aquí historias, requisitos, etc."""

    generation_id: UUID
    document_id: UUID
    configuration: PipelineConfiguration

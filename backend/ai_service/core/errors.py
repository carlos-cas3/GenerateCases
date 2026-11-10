"""Excepciones de dominio. No conocen HTTP; `api/errors.py` las traduce."""

from typing import Any, ClassVar


class AppError(Exception):
    """Error de aplicación con código estable y mensaje seguro para el cliente."""

    code: ClassVar[str] = "INTERNAL_ERROR"
    default_message: ClassVar[str] = "Ocurrió un error interno."

    def __init__(self, message: str | None = None, details: dict[str, Any] | list[Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details: dict[str, Any] | list[Any] = details if details is not None else {}
        super().__init__(self.message)


class DocumentNotFound(AppError):
    code = "DOCUMENT_NOT_FOUND"
    default_message = "El documento indicado no existe."


class DocumentInUse(AppError):
    code = "DOCUMENT_IN_USE"
    default_message = "El documento tiene generaciones asociadas y no puede eliminarse."


class InvalidDocumentUpload(AppError):
    code = "VALIDATION_ERROR"
    default_message = "El archivo está vacío."


class PayloadTooLarge(AppError):
    code = "PAYLOAD_TOO_LARGE"
    default_message = "El archivo supera el tamaño máximo permitido."


class UnsupportedMediaType(AppError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    default_message = "Tipo de archivo no soportado. Use TXT, PDF o DOCX."


class GenerationNotFound(AppError):
    code = "GENERATION_NOT_FOUND"
    default_message = "La generación indicada no existe."


class GenerationInProgress(AppError):
    code = "GENERATION_IN_PROGRESS"
    default_message = "La generación está en procesamiento y no puede eliminarse."


class FeatureNotImplemented(AppError):
    code = "NOT_IMPLEMENTED"
    default_message = "Funcionalidad aún no implementada."


class LlmError(AppError):
    """Fallo en la llamada al LLM. Los adaptadores lo lanzan; las etapas lo capturan."""

    code = "LLM_ERROR"
    default_message = "Falló la llamada al modelo de lenguaje."


class LlmRateLimitError(LlmError):
    """El proveedor rechazó la llamada por límite de tasa. Reintentable."""

    code = "LLM_RATE_LIMIT"
    default_message = "El proveedor del modelo de lenguaje rechazó la llamada por límite de tasa."


class LlmInvalidResponseError(LlmError):
    """La respuesta no es JSON válido o no supera la validación del contrato."""

    code = "LLM_INVALID_OUTPUT"
    default_message = "La respuesta del modelo de lenguaje no es válida."


class LlmContextLengthError(LlmError):
    """El prompt supera el límite de tokens del modelo."""

    code = "LLM_CONTEXT_LENGTH"
    default_message = "El prompt supera el límite de contexto del modelo."


class EmbeddingsError(AppError):
    """Fallo en la generación de embeddings. Los adaptadores lo lanzan; P3 lo captura."""

    code = "EMBEDDING_PROVIDER_UNAVAILABLE"
    default_message = "Falló la generación de embeddings."


class EmbeddingsDimensionError(EmbeddingsError):
    """Los vectores devueltos tienen una dimensión distinta a la esperada."""

    code = "EMBEDDING_DIMENSION_MISMATCH"
    default_message = "Los vectores devueltos tienen una dimensión inesperada."


class EmbeddingsInvalidVectorError(EmbeddingsError):
    """Un vector contiene NaN o valores infinitos."""

    code = "EMBEDDING_INVALID_VECTOR"
    default_message = "El proveedor devolvió un vector con valores no válidos."


class ClusteringError(AppError):
    """Fallo en el clustering. Los adaptadores lo lanzan; P4 lo captura.

    Código alineado con el catálogo de errores de P4 (`pipeline_design.md`).
    """

    code = "CLUSTERING_FAILED"
    default_message = "Falló el algoritmo de clustering."


class StoredDocumentUnavailable(AppError):
    """No se pudo leer el archivo desde Storage. Lo lanza el adaptador; P1 lo captura."""

    code = "DOCUMENT_UNREADABLE"
    default_message = "No se pudo leer el archivo del documento."


class DocumentExtractionError(AppError):
    """Fallo al extraer texto del archivo. Lo lanzan los adaptadores; P1 lo captura."""

    code = "DOCUMENT_UNREADABLE"
    default_message = "No se pudo extraer el texto del documento."


class InvalidStateTransition(Exception):
    """Una actualización con guarda de estado no afectó ninguna fila. Error interno."""


class ConfigurationError(Exception):
    """Falta configuración crítica para arrancar el servicio."""

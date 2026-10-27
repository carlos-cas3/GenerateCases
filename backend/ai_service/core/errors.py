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


class InvalidStateTransition(Exception):
    """Una actualización con guarda de estado no afectó ninguna fila. Error interno."""


class ConfigurationError(Exception):
    """Falta configuración crítica para arrancar el servicio."""

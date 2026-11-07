"""Contratos de P6 — Generación de casos de prueba funcionales (`pipeline_design.md`, P6)."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, ValidationInfo, model_validator

from ai_service.pipeline.contracts.common import (
    ContractModel,
    LlmSettings,
    NonEmptyStr,
    RelationStatus,
    RequirementCode,
    TestCaseCode,
    TestData,
    UnitId,
    code_number,
    ensure_unique,
)
from ai_service.pipeline.contracts.p5 import GenerationContext, TestCaseOutputSpec


class TestStep(ContractModel):
    """Paso de un caso de prueba. Tabla `test_steps`."""

    __test__ = False  # no es una clase de pytest

    step_number: int = Field(ge=1)
    action: NonEmptyStr
    expected_result: str | None = None


def _check_steps(steps: tuple[TestStep, ...]) -> None:
    numbers = [step.step_number for step in steps]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"los pasos deben numerarse consecutivamente desde 1: {numbers}")


class TestCaseDraft(ContractModel):
    """Caso de prueba tal como lo devuelve el LLM en P6 (1.4.3), sin `id` ni `code`.

    Con `context={"target_codes": {...}}` exige que cada RF enlazado sea objetivo de la unidad
    (ni de contexto ni prerrequisito).
    """

    __test__ = False  # no es una clase de pytest

    title: NonEmptyStr
    objective: str | None = None
    preconditions: tuple[NonEmptyStr, ...] = ()
    test_data: TestData | None = None
    steps: tuple[TestStep, ...] = Field(min_length=1)
    expected_result: NonEmptyStr
    requirement_codes: tuple[RequirementCode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self, info: ValidationInfo) -> "TestCaseDraft":
        _check_steps(self.steps)
        ensure_unique(self.requirement_codes, "requirement_codes")
        targets = (info.context or {}).get("target_codes")
        if targets is not None:
            foreign = set(self.requirement_codes) - set(targets)
            if foreign:
                raise ValueError(f"RF que no son objetivo de la unidad: {sorted(foreign)}")
        return self


class P6LlmResponse(ContractModel):
    """Respuesta cruda del LLM para una unidad (modelo intermedio). Se valida con `model_validate_json`.

    El `context` de la validación se propaga a cada `TestCaseDraft`.
    """

    test_cases: tuple[TestCaseDraft, ...] = Field(min_length=1)


def default_output_spec(version: str) -> TestCaseOutputSpec:
    """Especificación de salida de P6 construida a partir de `P6LlmResponse`."""
    return TestCaseOutputSpec(version=version, json_schema=P6LlmResponse.model_json_schema())


class RequirementTestCaseLink(ContractModel):
    """Vínculo RF–CP (`requirement_test_cases`). Al salir de P6: `pending` y sin método (R7, D-14)."""

    requirement_code: RequirementCode
    status: RelationStatus = RelationStatus.PENDING
    validation_method: str | None = None
    validation_notes: str | None = None


class TestCase(ContractModel):
    """Caso de prueba registrado. Lo produce P6. Tablas `test_cases`, `test_steps` y
    `requirement_test_cases` (vía `persist_p6_unit`). `id` es obligatorio: la RPC lo exige.
    """

    __test__ = False  # no es una clase de pytest

    id: UUID
    code: TestCaseCode
    title: NonEmptyStr
    objective: str | None = None
    preconditions: tuple[NonEmptyStr, ...] = ()
    test_data: TestData | None = None
    steps: tuple[TestStep, ...] = Field(min_length=1)
    expected_result: NonEmptyStr
    requirement_links: tuple[RequirementTestCaseLink, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> "TestCase":
        _check_steps(self.steps)
        ensure_unique((link.requirement_code for link in self.requirement_links), "requirement_codes")
        return self

    def requirement_codes(self) -> tuple[str, ...]:
        """Códigos de RF enlazados."""
        return tuple(link.requirement_code for link in self.requirement_links)


class P6UnitOutput(ContractModel):
    """Casos de prueba de una unidad. Se persiste de forma atómica con `persist_p6_unit` (D-15)."""

    unit_id: UnitId
    test_cases: tuple[TestCase, ...] = ()

    @model_validator(mode="after")
    def _as_produced_by_p6(self) -> "P6UnitOutput":
        ensure_unique((case.code for case in self.test_cases), "códigos de CP")
        ensure_unique((case.id for case in self.test_cases), "ids de CP")
        for case in self.test_cases:
            for link in case.requirement_links:
                if link.status != RelationStatus.PENDING or link.validation_method is not None:
                    raise ValueError(f"{case.code}: los vínculos salen de P6 en pending y sin validation_method")
        return self

    def to_rpc_payload(self) -> dict[str, Any]:
        """`p_payload` de `persist_p6_unit`. `generation_id` va aparte (`p_generation_id`).

        La RPC no recibe `validation_notes`: los vínculos se insertan siempre `pending`.
        """
        return {
            "test_cases": [
                {
                    **case.model_dump(
                        mode="json",
                        include={"id", "code", "title", "objective", "preconditions", "test_data", "expected_result"},
                    ),
                    "steps": [step.model_dump(mode="json") for step in case.steps],
                    "requirement_codes": list(case.requirement_codes()),
                }
                for case in self.test_cases
            ]
        }


class UnitFailure(ContractModel):
    """Unidad de P6 que falló tras agotar reintentos (D-15)."""

    unit_id: UnitId
    error_code: NonEmptyStr
    message: NonEmptyStr


class P6Config(ContractModel):
    """Configuración de P6 (servidor, R8). `on_unit_failure`: D-15 solo admite detener la etapa.

    `prompt_version` identifica la familia/versión. P6 resuelve la variante
    (`contexto`/`contexto_sin_clustering`) con `context.strategy` (D-38).
    """

    prompt_version: NonEmptyStr
    llm: LlmSettings
    max_retries: int = Field(ge=0)
    on_unit_failure: Literal["fail"] = "fail"
    link_support_threshold: float | None = Field(default=None, ge=0, le=1)


class P6Input(ContractModel):
    """Entrada de P6: el contexto de P5Output."""

    generation_id: UUID
    context: GenerationContext
    config: P6Config

    @model_validator(mode="after")
    def _same_generation(self) -> "P6Input":
        if self.context.generation_id != self.generation_id:
            raise ValueError("el contexto pertenece a otra generación")
        return self


class P6Output(ContractModel):
    """Salida de P6. Los resultados ya están persistidos unidad a unidad; la consume la API.

    Los códigos `CP-xxx` son globales y consecutivos desde `CP-001` en el orden de las unidades.
    """

    units: tuple[P6UnitOutput, ...] = ()
    uncovered_requirement_codes: tuple[RequirementCode, ...] = ()
    failed_units: tuple[UnitFailure, ...] = Field(default=(), max_length=1)  # D-15: P6 se detiene en el primer fallo

    @property
    def test_cases(self) -> tuple[TestCase, ...]:
        """Todos los casos de prueba, en orden de unidad."""
        return tuple(case for unit in self.units for case in unit.test_cases)

    @model_validator(mode="after")
    def _consistent(self) -> "P6Output":
        ensure_unique((unit.unit_id for unit in self.units), "unit_id")
        cases = self.test_cases
        ensure_unique((case.id for case in cases), "ids de CP")
        numbers = [code_number(case.code) for case in cases]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("los códigos de CP deben ser consecutivos desde CP-001")
        failed = {item.unit_id for item in self.failed_units}
        if failed & {unit.unit_id for unit in self.units}:
            raise ValueError("una unidad fallida no puede tener casos persistidos")
        ensure_unique(self.uncovered_requirement_codes, "uncovered_requirement_codes")
        linked = {code for case in cases for code in case.requirement_codes()}
        if linked & set(self.uncovered_requirement_codes):
            raise ValueError(f"RF marcados sin cubrir que tienen casos: {sorted(linked & set(self.uncovered_requirement_codes))}")
        return self

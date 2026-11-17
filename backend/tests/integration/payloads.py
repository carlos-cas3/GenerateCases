"""Payloads RPC válidos para la capa de integración (D-F8-6).

Reutilizan `tests/contract_factories.py` + `to_rpc_payload()`; solo sustituyen los UUID fijos
de las factories por UUID nuevos para que cada test escriba filas propias (D-F8-3) y una
ejecución abortada no colisione con la siguiente por clave primaria.
"""

from typing import Any
from uuid import uuid4

from tests import contract_factories as f


def p1_payload() -> list[dict[str, Any]]:
    stories = (
        f.user_story(id=uuid4()),
        f.warning_story().model_copy(update={"id": uuid4()}),
        f.invalid_story().model_copy(update={"id": uuid4()}),
    )
    return f.p1_output(user_stories=stories).to_rpc_payload()


def p2_payload() -> dict[str, Any]:
    requirements = (f.requirement(id=uuid4()), f.requirement_2().model_copy(update={"id": uuid4()}))
    return f.p2_output(requirements=requirements).to_rpc_payload()


def p4_payload() -> dict[str, Any]:
    return f.p4_output(clusters=(f.cluster(id=uuid4()),)).to_rpc_payload()


def p6_payload() -> dict[str, Any]:
    return f.unit_output(test_cases=(f.sample_test_case(id=uuid4()),)).to_rpc_payload()

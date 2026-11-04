"""`to_rpc_payload()` produce exactamente las claves que leen las RPC de `supabase/schema.sql`.

Las claves esperadas se extraen de la propia función SQL: los `p_payload -> 'clave'` de primer
nivel y las columnas de cada `jsonb_to_recordset(...) as alias(columna tipo, ...)`.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests import contract_factories as f

SCHEMA_SQL = (Path(__file__).resolve().parents[1] / "supabase" / "schema.sql").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    match = re.search(rf"function public\.{name}\(.*?\$\$(.*?)\$\$", SCHEMA_SQL, re.S)
    assert match, f"no se encontró {name} en schema.sql"
    return match.group(1)


def _rpc_keys(name: str) -> tuple[set[str], set[str]]:
    """(claves de primer nivel, columnas leídas de los registros) de una RPC."""
    body = _function_body(name)
    top_level = set(re.findall(r"p_payload\s*->\s*'(\w+)'", body))
    record_columns: set[str] = set()
    for columns in re.findall(r"\bas\s+\w+\(([^()]*)\)", body):
        for column in columns.split(","):
            parts = column.split()
            if len(parts) >= 2:  # `nombre tipo`; los alias sin tipo son elementos de texto, no claves
                record_columns.add(parts[0])
    return top_level, record_columns


# Columnas `jsonb` que la RPC guarda tal cual: sus claves internas no son columnas.
OPAQUE_JSONB = {"test_data", "preconditions", "clarification_items"}


def _nested_keys(payload: Any) -> set[str]:
    """Claves de todos los objetos anidados en listas del payload (sin las de primer nivel)."""
    keys: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                keys.add(key)
                if key not in OPAQUE_JSONB:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for value in payload.values():
        walk(value)
    return keys


PAYLOADS = {
    "persist_p2_requirements": lambda: f.p2_output().to_rpc_payload(),
    "persist_p4_clusters": lambda: f.p4_output().to_rpc_payload(),
    "persist_p6_unit": lambda: f.unit_output().to_rpc_payload(),
}


@pytest.mark.parametrize("rpc", PAYLOADS)
def test_payload_matches_rpc_keys(rpc: str) -> None:
    payload = PAYLOADS[rpc]()
    top_level, record_columns = _rpc_keys(rpc)

    assert set(payload) == top_level
    nested = _nested_keys(payload)
    assert nested <= record_columns, f"claves que la RPC no lee: {nested - record_columns}"
    assert record_columns <= nested, f"columnas que la RPC espera y faltan: {record_columns - nested}"


@pytest.mark.parametrize("rpc", PAYLOADS)
def test_payload_is_json_serializable(rpc: str) -> None:
    payload = PAYLOADS[rpc]()
    assert json.loads(json.dumps(payload)) == payload


def test_p2_payload_shape() -> None:
    payload = f.p2_output().to_rpc_payload()
    assert payload["classifications"][0] == {
        "user_story_code": "HU-001",
        "classification": "candidata_funcional",
        "classification_rationale": "Describe un acceso al sistema.",
        "clarification_items": [],
    }
    assert payload["requirements"][0] == {
        "id": str(f.RF1_ID),
        "code": "RF-001",
        "description": "El sistema permite iniciar sesión con credenciales válidas.",
        "source_text": "quiero iniciar sesión",
        "user_story_codes": ["HU-001"],
    }


def test_p4_payload_shape() -> None:
    payload = f.p4_output().to_rpc_payload()
    assert payload == {
        "clusters": [
            {
                "id": str(f.CLUSTER_ID),
                "name": "Grupo 0",
                "description": None,
                "cluster_label": 0,
                "assignments": [{"requirement_code": "RF-001", "similarity_to_centroid": 0.92}],
            }
        ],
        "unassigned_requirement_codes": ["RF-002"],
    }


def test_p6_payload_shape() -> None:
    case = f.unit_output().to_rpc_payload()["test_cases"][0]
    assert case["id"] == str(f.CP1_ID)
    assert case["preconditions"] == ["El usuario está registrado"]
    assert case["test_data"] == {"preconditions": [], "inputs": {"email": "usuario@ejemplo.com"},
                                 "expected_results": [], "notes": None}
    assert [step["step_number"] for step in case["steps"]] == [1, 2]
    assert case["requirement_codes"] == ["RF-001"]
    assert "requirement_links" not in case

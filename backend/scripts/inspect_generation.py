r"""Consulta una generación por ID: estado, etapas, avisos de P6 y casos persistidos.

Uso:  py scripts/inspect_generation.py <generation_id>
Lee SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY de .env.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_service.clients.supabase import create_supabase_client
from ai_service.config import get_settings


def _print(label: str, value: object) -> None:
    if isinstance(value, (dict, list)):
        print(f"{label}: {json.dumps(value, ensure_ascii=False, indent=2)}")
    else:
        print(f"{label}: {value}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Falta el generation_id", file=sys.stderr)
        sys.exit(2)
    gen_id = str(UUID(sys.argv[1]))
    client = create_supabase_client(get_settings())

    # 1) Generación + etapas + documento
    row = (
        client.table("generations")
        .select("*, documents(filename), generation_stages(*)")
        .eq("id", gen_id)
        .limit(1)
        .execute()
        .data
    )
    if not row:
        print(f"No existe la generación {gen_id}")
        return
    g = row[0]
    print("=" * 80)
    print(f"GENERACIÓN {g['id']}")
    print("=" * 80)
    _print("documento", (g.get("documents") or {}).get("filename"))
    _print("status", g.get("status"))
    _print("method_type", g.get("method_type"))
    _print("config_snapshot", g.get("config_snapshot"))
    _print("created_at", g.get("created_at"))
    _print("started_at", g.get("started_at"))
    _print("completed_at", g.get("completed_at"))
    _print("error_message", g.get("error_message"))
    _print("summary", g.get("summary"))
    print()

    stages = sorted(g.get("generation_stages") or [], key=lambda s: s["stage_order"])
    print("ETAPAS")
    print("-" * 80)
    for s in stages:
        print(
            f"  {s['stage_key']:<4} order={s['stage_order']} status={s['status']:<9} "
            f"started={s.get('started_at')} completed={s.get('completed_at')}"
        )
        if s.get("error_code") or s.get("error_message"):
            _print(f"    error_code", s.get("error_code"))
            _print(f"    error_message", s.get("error_message"))
        if s.get("runtime_info"):
            _print(f"    runtime_info [{s['stage_key']}]", s.get("runtime_info"))
    print()

    # 2) Avisos y llm_runs de P6 en detalle
    p6 = next((s for s in stages if s["stage_key"] == "p6"), None)
    if p6:
        print("P6 — AVISOS")
        print("-" * 80)
        warnings = p6.get("warnings") or []
        if not warnings:
            print("  (sin avisos)")
        for w in warnings:
            print(f"  code={w.get('code')}")
            print(f"    message={w.get('message')}")
            if w.get("details"):
                _print(f"    details", w.get("details"))
        print()
        print("P6 — LLM_RUNS")
        print("-" * 80)
        runs = p6.get("llm_runs") or []
        if not runs:
            print("  (sin runs)")
        for r in runs:
            print(
                f"  unit_id={r.get('unit_id'):<8} attempts={r.get('attempts')} "
                f"in={r.get('input_tokens')} out={r.get('output_tokens')} "
                f"lat={r.get('latency_ms')}ms model={r.get('model')}"
            )
        print()

    # 3) Casos persistidos con su trazabilidad RF↔CP y pasos.
    # La relación RF↔CP vive en `requirement_test_cases` (no en `test_cases`),
    # así que se junta con `functional_requirements` (id -> código) en Python.
    print("CASOS DE PRUEBA PERSISTIDOS")
    print("-" * 80)

    fr_rows = (
        client.table("functional_requirements")
        .select("id,code")
        .eq("generation_id", gen_id)
        .execute().data
        or []
    )
    rf_by_id = {r["id"]: r["code"] for r in fr_rows}

    rtc_rows = (
        client.table("requirement_test_cases")
        .select("test_case_id,requirement_id,relation_status")
        .eq("generation_id", gen_id)
        .execute().data
        or []
    )
    rfs_by_case: dict[str, list[str]] = {}
    status_by_case: dict[str, dict[str, str]] = {}
    for r in rtc_rows:
        tc_id = r["test_case_id"]
        rf_code = rf_by_id.get(r["requirement_id"]) or str(r["requirement_id"])
        rfs_by_case.setdefault(tc_id, []).append(rf_code)
        if r.get("relation_status") and r["relation_status"] != "pending":
            status_by_case.setdefault(tc_id, {})[rf_code] = r["relation_status"]

    steps_rows = (
        client.table("test_steps")
        .select("test_case_id,step_number,action,expected_result")
        .eq("generation_id", gen_id)
        .order("step_number")
        .execute().data
        or []
    )
    steps_by_case: dict[str, list[dict]] = {}
    for s in steps_rows:
        steps_by_case.setdefault(s["test_case_id"], []).append(s)

    cases = (
        client.table("test_cases")
        .select("*")
        .eq("generation_id", gen_id)
        .order("code")
        .execute().data
        or []
    )

    if not cases:
        print("  (sin casos)")
    for c in cases:
        tc_id = c.get("id")
        code = c.get("code") or "?"
        rf_codes = sorted(set(rfs_by_case.get(tc_id, [])))
        steps = steps_by_case.get(tc_id, [])
        title = (c.get("title") or "").replace("\n", " ")
        objective = (c.get("objective") or "").replace("\n", " ")
        print(f"  {code}  RF={rf_codes or []}  ({len(steps)} paso(s))")
        if title:
            print(f"        título: {title}")
        if objective:
            print(f"        objetivo: {objective}")
        for s in steps:
            print(f"        {s['step_number']}) {s.get('action', '')}")
            if s.get("expected_result"):
                print(f"           espera: {s.get('expected_result')}")
        non_pending = status_by_case.get(tc_id)
        if non_pending:
            print(f"        estado relación: {non_pending}")
    print()
    print(f"TOTAL casos: {len(cases)}")


if __name__ == "__main__":
    main()

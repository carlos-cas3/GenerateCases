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

    # 3) Casos persistidos
    print("CASOS DE PRUEBA PERSISTIDOS")
    print("-" * 80)
    cases = client.table("test_cases").select("*").eq("generation_id", gen_id).order("code").execute().data or []
    if not cases:
        print("  (sin casos)")
    else:
        print(f"  columnas: {list(cases[0].keys())}")
    for c in cases:
        code = c.get("code") or c.get("id") or "?"
        rc = c.get("requirement_codes")
        title = (c.get("title") or "").replace("\n", " ")
        print(f"  {code:<10} requirement_codes={rc}")
        if title:
            print(f"             título: {title}")
    print()
    print(f"TOTAL casos: {len(cases)}")


if __name__ == "__main__":
    main()

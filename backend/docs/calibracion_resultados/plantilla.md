# Iteración de calibración N — <fecha>

> Copiar este archivo como `iteracion_N.md`. Una iteración = el **mismo documento** ejecutado con
> las dos estrategias de P6 (D-F7-9): baseline `by_user_story` (sin clustering) y propuesta
> `by_cluster` (con clustering). Solo cambia `semantic_clustering_enabled`.

## 1. Entrada

| Campo | Valor |
|---|---|
| Documento (nombre / checksum) | |
| Nº de HU en el documento | |
| Commit del backend | |

## 2. Configuración efectiva

| Variable | Valor |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | |
| `LLM_NUM_CTX` / `LLM_TEMPERATURE` | |
| `P2_PROMPT_VERSION` / `P2_MAX_STORIES_PER_CALL` | |
| `EMBEDDINGS_MODEL` | |
| `P4_MIN_CLUSTER_SIZE` / `P4_MIN_SAMPLES` | |
| `P5_MAX_TOKENS_PER_UNIT` | |
| `P6_PROMPT_VERSION` / `P6_MAX_RETRIES` | |
| `P6_FAILURE_THRESHOLD` | |
| `P6_MAX_CASES_MULTIPLIER` / `P6_MAX_CASES_ABSOLUTE` | |

## 3. Resultados

| Métrica | `by_user_story` (baseline) | `by_cluster` (propuesta) |
|---|---|---|
| `generation_id` | | |
| Estado final | | |
| `summary.user_stories_count` | | |
| `summary.requirements_count` | | |
| `summary.clusters_count` | — | |
| RF sin cluster (`UNASSIGNED_REQUIREMENTS`) | — | |
| Unidades P5 / `exceeds_limit` | | |
| `summary.test_cases_count` | | |
| `summary.test_cases_failed_units` | | |
| RF objetivo sin casos (`UNCOVERED_REQUIREMENTS`) | | |
| Avisos de P6 (`CASES_TRUNCATED`, `BATCH_RETRIED`, …) | | |
| Tokens entrada / salida de P6 (Σ `llm_runs`) | | |
| Latencia total de P6 | | |

## 4. Observaciones cualitativas

- Calidad de los casos (grounding, pasos, resultados esperados):
- Errores o enlaces RF–CP dudosos:
- Efecto de los RF de contexto (`by_cluster`):

## 5. Ajustes para la siguiente iteración

- 

# Prueba local con Ollama — configuración de `.env`

> **Estado:** ✅ ejecutada de punta a punta contra Supabase + Ollama local.
> **Alcance:** cómo configurar el backend para que P1 (heurística) y P2 (LLM) reales funcionen
> con un modelo local, mientras P3–P7 siguen como stubs. Complementa a
> [`cierre_documental_fase4.md`](cierre_documental_fase4.md).

---

## 1. Objetivo

Documentar la configuración mínima de `.env` para probar la Fase 4 en local usando **Ollama**
como proveedor LLM (sin clave de API), y el motivo de cada valor.

La lógica de P1/P2 no cambia: `PIPELINE_STAGES=real` construye ambas etapas reales y solo
P3–P7 quedan simuladas (ver `pipeline_roadmap.md`). Lo específico del entorno local es el
bloque del cliente LLM y el timeout.

---

## 2. Configuración de `.env` para local

Sustituye el bloque del cliente LLM por este (el resto de variables de Supabase y de P1 no cambian):

```dotenv
# Etapas: P1 heurística + P2 LLM reales; P3–P7 stubs.
PIPELINE_STAGES=real
# Solo afecta a los stubs (P3–P7); 0 acelera la prueba.
PIPELINE_STUB_DELAY_SECONDS=0

# Cliente LLM local (Ollama). No requiere LLM_API_KEY.
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
# NAME/tag completo tal como aparece en `ollama list` (no el ID/digest).
LLM_MODEL=sachasayan/interimlabs-qwen3.5-4b:q4_k_m
# El modelo tarda varios minutos por lote; 60 s (default) provoca LLM_UNAVAILABLE.
LLM_TIMEOUT_SECONDS=900

# P2 con lotes pequeños para un modelo 4B "thinking".
P2_MAX_STORIES_PER_CALL=1
# Solo durante la validación: cada intento puede costar ~7 min.
P2_MAX_RETRIES=0
```

`P1_RULES_VERSION`, `P1_LANGUAGE`, `P1_STORY_DELIMITER_PATTERN`, `P1_MAX_STORY_CHARS`,
`P2_PROMPT_VERSION` se dejan en sus valores por defecto (`v1`, `es`, `^##\s+.+$`, `5000`, `v1`).

---

## 3. Por qué cada variable

| Variable | Valor local | Motivo |
|---|---|---|
| `PIPELINE_STAGES` | `real` | Activa `NormalizeStage` y `RequirementsStage` reales. `stub` dejaría las siete etapas simuladas y no probaría P1/P2. |
| `PIPELINE_STUB_DELAY_SECONDS` | `0` | Con `real`, solo se aplica a P3–P7. En `0` no añade espera artificial. |
| `LLM_PROVIDER` | `ollama` | Usa `OllamaLlmClient`; la factory no exige `LLM_API_KEY`. |
| `LLM_BASE_URL` | `http://localhost:11434` | Dirección del servidor Ollama. Obligatoria para este proveedor. |
| `LLM_MODEL` | `sachasayan/interimlabs-qwen3.5-4b:q4_k_m` | Es el **NAME/tag** que acepta `POST /api/chat`. El ID que muestra `ollama list` es un digest interno, no el identificador de la llamada. |
| `LLM_TIMEOUT_SECONDS` | `900` | Timeout de red por llamada del adaptador. El modelo tardó **360–417 s** por lote; el default de 60 s corta la llamada y P2 falla con `LLM_UNAVAILABLE`. |
| `P2_MAX_STORIES_PER_CALL` | `1` | Lotes mínimos: el modelo 4B "thinking" produce razonamiento muy largo; menos HU por lote reduce la probabilidad de JSON inválido y el tiempo por llamada. |
| `P2_MAX_RETRIES` | `0` | Durante la validación conviene fallar rápido: con ~7 min por intento, reintentar multiplica la espera. Subir a `1`/`2` cuando ya funcione. |

---

## 4. Prerrequisitos

1. **Esquema desplegado:** ejecutar `supabase/schema.sql` completo en el SQL Editor de Supabase
   (es idempotente). Sin las RPC `persist_p1_user_stories` / `persist_p2_requirements`, P1 falla
   con `PERSISTENCE_FAILED`.
2. **Dependencias instaladas:** `pip install -r requirements.txt`. `main.py` construye los
   clientes de embeddings (`sentence-transformers`) y clustering (`hdbscan`) **al arrancar**,
   aunque P3–P7 sean stubs; también hacen falta `pdfplumber`/`python-docx` si se suben PDF/DOCX.
3. **Ollama activo y modelo descargado:**
   ```bash
   ollama list                 # debe aparecer el modelo
   curl http://localhost:11434/api/version
   ```
   Si Ollama ya está corriendo, `ollama serve` falla con `bind: Only one usage of each socket
   address`; es normal, no hay que levantarlo de nuevo.
4. **Ejecutar desde `backend/`:** `Settings` carga `.env` relativo al directorio actual
   (`env_file=".env"`). Si se arranca desde otra carpeta, se usan los defaults y faltarán las
   credenciales de Supabase.

---

## 5. Flujo ejecutado por API

```bash
# 1) subir documento (TXT/PDF/DOCX con la plantilla de HU)
curl -F "file=@Ejemplo.txt" http://localhost:8000/api/v1/documents

# 2) crear generación con el id devuelto
curl -X POST http://localhost:8000/api/v1/generations \
  -H "Content-Type: application/json" \
  -d '{"document_id":"<ID_DOCUMENTO>"}'

# 3) polling del estado
curl -s http://localhost:8000/api/v1/generations/<ID_GENERACION>
```

El pipeline corre en background: el `POST /generations` responde `202` de inmediato y hay que
hacer polling hasta `completed`/`failed`.

---

## 6. Resultado observado (evidencia)

Generación `f61589a7-b779-4c60-b986-eda98fe938fb`, documento `Ejemplo.txt`, estado final
`completed`:

| Etapa | Resultado | Detalle |
|---|---|---|
| P1 | `completed` (~2 s) | `blocks_found=1`, `stories_identified=1`, `valid_count=1`, `stories_unresolved=0` |
| P2 | `completed` (~6.9 min) | 1 lote, `candidata_funcional=1`, `requirements_count=1`, `retries_used=0` |
| P2 `llm_runs` | `attempts=1` | `input_tokens=1612`, `output_tokens=5788`, `latency_ms=416854`, `provider=ollama` |
| P3–P7 | `completed` (stubs) | Con `PIPELINE_STUB_DELAY_SECONDS=0`, sin espera artificial |
| Persistencia | OK | `HU-001` clasificada `candidata_funcional`; `RF-001`; vínculo en `user_story_requirements` |

---

## 7. Problemas encontrados y solución

1. **`LLM_UNAVAILABLE` con 60 s.** El default de `LLM_TIMEOUT_SECONDS` es 60 s, pero el modelo
   tarda ~360 s en una llamada de P2. Al agotar los 3 intentos (~183 s) la etapa fallaba.
   Solución: `LLM_TIMEOUT_SECONDS=900`.
2. **Typo silencioso en la variable.** Se escribió `LLM_TIMEOT_SECONDS=900` (sin la `U`). Como
   `Settings` usa `extra="ignore"`, pydantic-settings **ignora** la variable desconocida sin
   error y se queda el default de 60 s; el fallo persistía. La variable correcta es
   `LLM_TIMEOUT_SECONDS`.
3. **Reinicio obligatorio.** `get_settings()` está cacheado con `lru_cache`; el hot-reload de
   uvicorn no relee `.env`. Tras cambiarlo hay que **reiniciar el proceso**.
4. **Mojibake en consola.** Al pipear a `py -m json.tool` en Windows se ven `segmentaci\u00c3\u00b3n`
   / `Ã³`. Es solo la codificación de la consola; la API y la BD guardan UTF-8 correcto.

---

## 8. Verificación en Supabase

```sql
select code, position, role, action, goal, validation_status,
       classification, classification_rationale, clarification_items
from public.user_stories
where generation_id = '<ID_GENERACION>' order by position;

select code, description, source_text
from public.functional_requirements
where generation_id = '<ID_GENERACION>' order by code;

select us.code as hu, fr.code as rf
from public.user_story_requirements r
join public.user_stories us on us.id = r.user_story_id
join public.functional_requirements fr on fr.id = r.requirement_id
where r.generation_id = '<ID_GENERACION>';

select stage_key, status, warnings, runtime_info, llm_runs
from public.generation_stages
where generation_id = '<ID_GENERACION>' order by stage_key;
```

Esperado: `HU-001` con `classification='candidata_funcional'`, `RF-001`, su fila en
`user_story_requirements` y P2 `completed` con `llm_runs` de proveedor `ollama`.

---

## 9. Notas y pendientes

- **Latencia alta:** ~7 min por lote por el razonamiento del modelo. Mejora futura: enviar
  `"think": false` a Ollama (hoy `OllamaLlmClient` solo pasa `options`, no el campo `think`) o
  usar un modelo no-thinking.
- **Reintentos:** restaurar `P2_MAX_RETRIES` a `1`/`2` cuando ya no se esté diagnosticando.
- **Un solo proceso:** el pipeline corre en `BackgroundTasks`; no hay worker separado. Un
  reinicio durante P2 deja la generación interrumpida (se marca `failed` al arrancar).
- **API validada:** el flujo E2E por API (`POST /documents` → `POST /generations` →
  `GET /generations/{id}`) ya se ejecutó con `curl`; este documento fija sobre todo la
  configuración de `.env` necesaria para reproducirlo en local.

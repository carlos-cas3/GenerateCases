# Iteración de calibración 1 — pendiente de ejecutar

> **Estado:** 🔲 pendiente. Primera ejecución del pipeline completo P1→P6 con el LLM real
> (Fase 7, T-F7-08). Completar las secciones con los datos reales siguiendo
> [`plantilla.md`](plantilla.md); no rellenar con valores estimados.
>
> **Es el paso final de la calibración** (§6 de [`guia_calibracion.md`](guia_calibracion.md)):
> se ejecuta **después** de que P1, P2, P4 y P5 pasaron sus criterios en sus
> [`bitacora/`](bitacora). No es el primer paso; los sondeos parciales con `stop_after` la
> preceden.

## Cómo ejecutarla

1. Arrancar Ollama con el modelo de `LLM_MODEL` y el backend con `PIPELINE_STAGES=real`.
2. Subir el documento de prueba (`POST /api/v1/documents`).
3. Crear dos generaciones del mismo documento (`POST /api/v1/generations`):
   - `{"configuration": {"semantic_clustering_enabled": false}}` → baseline `by_user_story`.
   - `{"configuration": {"semantic_clustering_enabled": true}}` → propuesta `by_cluster`.
4. Esperar a que terminen y copiar de `GET /api/v1/generations/{id}` el `summary`, los avisos y
   `runtime_info` / `llm_runs` de P4, P5 y P6 en las tablas de la plantilla.

## 1. Entrada

| Campo | Valor |
|---|---|
| Documento (nombre / checksum) | |
| Nº de HU en el documento | |
| Commit del backend | |

## 2. Configuración efectiva

(copiar la tabla de `plantilla.md` §2)

## 3. Resultados

(copiar la tabla de `plantilla.md` §3)

## 4. Observaciones cualitativas

## 5. Ajustes para la siguiente iteración

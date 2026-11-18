"""Convierte user stories de PyUNML (cp1252, una HU por línea) al formato
markdown ``##`` que espera P1 (docs/prompts_fases/Fase 4/plantilla_hu.md).

Lee ``raw/US24.txt`` y escribe ``calibration_doc.txt``. La extensión es
``.txt`` porque la subida de documentos solo acepta TXT/PDF/DOCX por extensión
(ver ``ai_service/services/documents.py``).

Uso::

    python backend/datasets/pyunml/convert.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "US27.txt"
OUT = HERE / "calibration_doc_U27.txt"


def main() -> None:
    text = RAW.read_text(encoding="cp1252")
    stories = [line.strip() for line in text.splitlines() if line.strip()]
    blocks = [f"## Historia {i}\n{story}" for i, story in enumerate(stories, start=1)]
    OUT.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"{len(stories)} historias -> {OUT}")


if __name__ == "__main__":
    main()

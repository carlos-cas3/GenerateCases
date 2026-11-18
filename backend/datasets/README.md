# Datasets de calibración

Inputs de la calibración del pipeline (P1–P6). Ver la metodología en
`docs/calibracion_resultados/guia_calibracion.md`.

## Fuente

**PyUNML-DataSet** — https://github.com/matovaro/PyUNML-DataSet

Versión en español (traducida con Google Translate) de los datasets de
requerimientos de Fabiano Dalpiaz:

- **Dalpiaz2018**: 22 apps, 50+ user stories c/u — Mendeley Data (DOI 10.17632/7zbk8zsd8y.1).
- **Dalpiaz2020**: 3 apps (HOS, SIM, IFA) — Zenodo.

## Archivo elegido: US24

- **App:** HOS (sistema de gestión hospitalaria / recetas electrónicas / EMR), de Dalpiaz2020.
- **~40 user stories** en español, forma "Como X, quiero Y, para Z" (encaja con la regex de P1).
- **Por qué:** dominio claro y coherente, tamaño moderado (balance entre costo de P6 y señal de
  clustering) y usa "quiero" correctamente (a diferencia de US28, que usa "queremos" y no matchea).

## Citación

- Tovar Onofre, M.Á., Camargo, J.E. (2023). *Automatic Class Extraction from Spanish Text of User
  Stories Using Natural Language Processing.* In: Narváez et al. (eds) Smart Technologies, Systems
  and Applications. SmartTech-IC 2022. Communications in Computer and Information Science, vol 1705.
  Springer, Cham. https://doi.org/10.1007/978-3-031-32213-6_3
- Dalpiaz, F. et al. (2019). *Detecting Terminological Ambiguity in User Stories: Tool and
  Experimentation.* Information & Software Technology (110), pp. 3–16.
- Dataset Mendeley: https://data.mendeley.com/datasets/7zbk8zsd8y/1 (DOI 10.17632/7zbk8zsd8y.1).

## Licencia y qué se commitea

Los archivos crudos (`pyunml/raw/US24.txt`) y el convertido
(`pyunml/calibration_doc.txt`) son **datos de terceros** y **no se commitean**
(ver `.gitignore`). El repo PyUNML no declara licencia y los datos derivan de
Dalpiaz; revisar las licencias upstream antes de redistribuir. Solo se commitean
este `README.md` y el conversor `pyunml/convert.py`.

## Cómo (re)generar el input de calibración

1. Descargar `US24.txt` de la carpeta `Translated dataset` del repo PyUNML y
   colocarlo en `pyunml/raw/US24.txt`.
2. Ejecutar:

   ```
   python backend/datasets/pyunml/convert.py
   ```

   Lee `raw/US24.txt` (codificación cp1252) y escribe `pyunml/calibration_doc.txt`
   (UTF-8, formato `## Historia N` + declaración canónica).

3. Subir `calibration_doc.txt` vía `POST /api/v1/documents` (campo multipart
   `file`). La extensión es `.txt` porque la subida solo acepta TXT/PDF/DOCX.

Ese documento queda **fijo** para toda la calibración; registrar nombre +
checksum + nº de HU (40) en `docs/calibracion_resultados/plantilla.md` §1.

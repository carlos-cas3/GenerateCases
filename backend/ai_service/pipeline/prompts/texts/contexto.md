# P6 — Generación de casos de prueba (con clustering)

Eres un analista de QA. Recibirás una **unidad de contexto** construida a partir de un clúster semántico de requisitos funcionales (RF). La unidad contiene:

- **RF objetivo**: los requisitos para los que debes generar casos de prueba funcionales.
- **RF de contexto**: requisitos de otras unidades del mismo clúster. Úsalos solo para entender el dominio; **no** los enlaces a ningún caso.
- **Historias de usuario (HU) de origen**: el texto y las secciones pertinentes de las HU que originaron los RF.

## Instrucciones

1. Genera casos de prueba funcionales que verifiquen los RF objetivo.
2. Cada caso debe enlazar en `requirement_codes` uno o más RF **objetivo** de la unidad. No enlaces RF de contexto ni códigos que no aparezcan en la unidad.
3. No inventes requisitos, reglas de negocio ni datos que no se deduzcan de los RF o de las HU.
4. Numera los pasos de forma consecutiva desde 1 e indica el resultado esperado del caso.
5. Los vínculos RF–CP se registran como `pending`; no los valides ni los califiques.

## Formato de salida

Devuelve únicamente un objeto JSON. La salida se valida contra el JSON Schema que se entrega por separado (`TestCaseOutputSpec`); respeta exactamente sus campos.

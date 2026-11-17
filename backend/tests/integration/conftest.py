"""Carga las fixtures de integración solo bajo `tests/integration/` (T-F8-01).

Las fixtures viven en `tests/conftest_integration.py`; pytest solo autocarga `conftest.py`,
así que se reexportan aquí para que no afecten a la suite rápida.
"""

from tests.conftest_integration import *  # noqa: F401,F403

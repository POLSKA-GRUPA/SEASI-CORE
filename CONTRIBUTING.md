# Contributing

Gracias por tu interés en SEASI-CORE.

## Modelo de contribución

- Las contribuciones llegan por pull request desde un fork.
- Forkear NO otorga derechos de uso fuera de este repositorio (ver LICENSE).
- Cada PR debe dejar verde: `ruff format --check`, `ruff check`, `mypy src`,
  `pytest -q` y el job de higiene (sin literales de marca heredada).

## Reglas del kernel

1. No añadas dependencias sin justificación en el PR.
2. No introduzcas efectos de red, I/O bloqueante ni globals mutables.
3. Todo modelo Pydantic: `frozen=True`, `extra="forbid"` y validators
   explícitos.
4. Toda función pública del `src/` anotada con tipos (mypy estricto).
5. Tests: unit + contract + isolation + integration según la superficie
   tocada.
6. Cambios de contrato → bump de schema version y entrada en CHANGELOG.

## Desarrollo local

```bash
uv sync --all-groups
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

# Cómo contribuir a SynapVolit

1. Haz *fork* y crea una rama desde `main`.
2. Corre `uv sync` y confirma que `uv run pytest -q` pasa antes de tocar nada.
3. Las pruebas van con el cambio, no después.
4. Antes del commit: `uv run ruff check . --fix` y `uv run ruff format .`.
5. Agrégate a `CREDITS.md` con tus roles CRediT en el mismo *pull request*; si tu aportación te hace autor, también a `CITATION.cff`.
6. Abre el *pull request* describiendo qué cambia y cómo lo verificaste.

El CI corre Ruff y pytest en cada *push* y en cada *pull request*.

## Commits

Verbo en infinitivo, sin punto final, menos de 72 caracteres, con ámbito al inicio:

```
datos: validar el esquema al cargar
docs: corregir la instalación en Mac
```

## Estándar

El proyecto sigue el estándar DUNNE, en `docs/estandar/`. Antes de cambiar la
estructura, el entorno o las dependencias, lee `docs/estandar/nucleo.md`.

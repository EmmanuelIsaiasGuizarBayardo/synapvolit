"""Copia la version y la fecha de lanzamiento de pyproject.toml a CITATION.cff.

Se corre despues de ``uv version X.Y.Z`` para que el paquete y la cita nunca
diverjan; ``tests/test_gobernanza.py`` verifica que coincidan.

Uso, desde la raiz del repositorio:
    uv run python tools/sincronizar_cff.py
"""

from __future__ import annotations

import re
import tomllib
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    """Reescribe ``version`` y ``date-released`` de CITATION.cff."""
    version = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    ruta = RAIZ / "CITATION.cff"
    texto = ruta.read_text(encoding="utf-8")
    hoy = date.today().isoformat()
    texto, n = re.subn(r"^version: .*$", f'version: "{version}"', texto, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit("CITATION.cff debe tener exactamente una linea 'version:'")
    linea = f'date-released: "{hoy}"'
    if re.search(r"^date-released: ", texto, flags=re.MULTILINE):
        texto = re.sub(r"^date-released: .*$", linea, texto, flags=re.MULTILINE)
    else:  # la plantilla no la genera: se agrega debajo de la version
        texto = re.sub(r"^(version: .*)$", rf"\1\n{linea}", texto, count=1, flags=re.MULTILINE)
    ruta.write_text(texto, encoding="utf-8", newline="\n")
    print(f"CITATION.cff: version {version}, date-released {hoy}")


if __name__ == "__main__":
    main()

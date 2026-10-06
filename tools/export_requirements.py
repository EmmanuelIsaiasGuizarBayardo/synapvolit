# Archivo del estandar DUNNE: se actualiza con 'copier update'. Propon cambios en la plantilla.
"""Exporta requirements.txt desde uv.lock reponiendo el indice de PyTorch.

`uv export` no emite el `--extra-index-url` de un indice marcado `explicit`
(astral-sh/uv #13572, #15534). Sin esa linea, un colaborador en Windows que
instale con pip recibe la rueda CPU-only de torch sin ningun error visible.
Este script cierra ese hueco y lo invoca un hook local de pre-commit.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "requirements.txt"

CABECERA = (
    "# Generado automaticamente desde uv.lock. No editar a mano.\n"
    "# Regenerar con: uv run python tools/export_requirements.py\n"
)


def indice_pytorch() -> str | None:
    """Devuelve la URL del indice llamado 'pytorch' en pyproject.toml.

    Returns
    -------
    str or None
        URL del indice, o None si el proyecto no declara uno.
    """
    cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    for idx in cfg.get("tool", {}).get("uv", {}).get("index", []):
        if idx.get("name") == "pytorch":
            return idx.get("url")
    return None


def exportar() -> str:
    """Corre `uv export` probando las variantes de banderas entre versiones.

    Returns
    -------
    str
        Contenido del export en formato requirements.

    Raises
    ------
    RuntimeError
        Si ninguna combinacion de banderas funciona.
    """
    formatos = (["--format", "requirements.txt"], ["--format", "requirements-txt"])
    variantes = (["--no-emit-project"], [])
    ultimo = ""
    for fmt in formatos:
        for extra in variantes:
            cmd = ["uv", "export", *fmt, "--no-hashes", "--all-extras", *extra]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=RAIZ)
            if proc.returncode == 0:
                return proc.stdout
            ultimo = proc.stderr
    raise RuntimeError(f"uv export fallo: {ultimo.strip()}")


def main(modo_hook: bool = False) -> int:
    """Escribe requirements.txt si cambio su contenido.

    Parameters
    ----------
    modo_hook : bool, default=False
        Si True, devuelve 1 cuando el archivo cambio. Es la convencion de
        pre-commit: el hook falla, el usuario re-agrega y vuelve a commitear.

    Returns
    -------
    int
        Codigo de salida del proceso.
    """
    cuerpo = "\n".join(linea for linea in exportar().splitlines() if linea.strip() != "-e .")
    contenido = CABECERA
    url = indice_pytorch()
    if url:
        contenido += f"--extra-index-url {url}\n"
    contenido += "\n" + cuerpo.strip() + "\n"

    previo = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
    if previo == contenido:
        return 0

    SALIDA.write_text(contenido, encoding="utf-8", newline="\n")
    print("requirements.txt regenerado")
    return 1 if modo_hook else 0


if __name__ == "__main__":
    sys.exit(main(modo_hook="--hook" in sys.argv))

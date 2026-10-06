"""Publica una versión en un solo paso: número, cita, requisitos, pruebas y etiqueta.

Cada paso depende del anterior y el script se detiene en el primero que falle,
siempre antes de etiquetar. Existe porque publicar a mano, con varios comandos,
dejó dos veces una etiqueta cuyo paquete declaraba otra versión.

Uso, desde la raíz del repositorio, con los cambios de la versión ya hechos:
    uv run python tools/publicar.py 0.1.3 "Qué cambia en esta versión"
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def correr(*orden: str) -> None:
    """Ejecuta un paso; si falla, detiene la publicación."""
    print(f"\n-> {' '.join(orden)}", flush=True)
    subprocess.run(orden, cwd=RAIZ, check=True)


def etiqueta_existe(etiqueta: str) -> bool:
    """True si la etiqueta ya existe en el repositorio local."""
    salida = subprocess.run(
        ["git", "tag", "--list", etiqueta], cwd=RAIZ, capture_output=True, text=True, check=True
    )
    return bool(salida.stdout.strip())


def etiqueta_publicada(etiqueta: str) -> bool:
    """True si la etiqueta ya existe en el remoto origin, aunque se haya borrado aquí."""
    salida = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{etiqueta}"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(salida.stdout.strip())


def commit(mensaje: str) -> None:
    """Commit con los hooks de pre-commit.

    Si no hay nada que commitear, el commit con esta versión ya existe, por ejemplo
    tras una corrida interrumpida, y se sigue a la etiqueta. Si un hook corrige
    archivos, se agregan y se reintenta una vez; si falla sin corregir, se detiene.
    """
    correr("git", "add", "-A")
    sin_cambios = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=RAIZ, check=False)
    if sin_cambios.returncode == 0:
        print("\nNo hay cambios que commitear: el commit con esta versión ya existe.", flush=True)
        return
    orden = ["git", "commit", "-m", mensaje]
    if subprocess.run(orden, cwd=RAIZ, check=False).returncode == 0:
        return
    if subprocess.run(["git", "diff", "--quiet"], cwd=RAIZ, check=False).returncode == 0:
        raise subprocess.CalledProcessError(1, orden)  # un hook falló sin corregir nada
    print("\nUn hook corrigió archivos; se agregan y se reintenta el commit.", flush=True)
    correr("git", "add", "-A")
    correr(*orden)


def main(argumentos: list[str]) -> int:
    """Corre la publicación completa y devuelve 0 solo si todo se subió."""
    if len(argumentos) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argumentos[0]):
        print(__doc__)
        return 2
    version, mensaje = argumentos
    etiqueta = f"v{version}"
    try:
        publicada = etiqueta_publicada(etiqueta)
    except subprocess.CalledProcessError:
        print("No se pudo consultar el remoto origin, y publicar lo necesita.")
        return 1
    if publicada:
        print(f"{etiqueta} ya está publicada en GitHub. Una etiqueta publicada no se mueve:")
        print("usa la versión siguiente.")
        return 1
    if etiqueta_existe(etiqueta):
        print(f"{etiqueta} existe solo en tu máquina, de una publicación interrumpida.")
        print(f"Bórrala con 'git tag -d {etiqueta}' y vuelve a correr.")
        return 1
    try:
        correr("uv", "version", version)
        correr("uv", "run", "python", "tools/sincronizar_cff.py")
        correr("uv", "run", "python", "tools/export_requirements.py")
        correr("uv", "run", "pytest", "-q")
        commit(mensaje)
        correr("git", "tag", "-a", etiqueta, "-m", mensaje)
        correr("git", "push")
        # Explícito, no --follow-tags: si GitHub ya tuviera la etiqueta, --follow-tags
        # la omitiría en silencio; así, el rechazo detiene la publicación.
        correr("git", "push", "origin", f"refs/tags/{etiqueta}")
    except subprocess.CalledProcessError as error:
        paso = " ".join(error.cmd)
        if etiqueta_existe(etiqueta):
            print(f"\nSe detuvo en: {paso}. {etiqueta} existe solo en tu máquina; al corregir,")
            print(f"sube con: git push origin {etiqueta}")
        else:
            print(f"\nSe detuvo en: {paso}. No se creó {etiqueta}: corrige y vuelve a correr.")
        return 1
    print(f"\nPublicada {etiqueta}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

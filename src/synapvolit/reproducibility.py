# Archivo del estandar DUNNE: se actualiza con 'copier update'. Propon cambios en la plantilla.
"""Reproducibilidad: control de semillas y trazabilidad del código."""

from __future__ import annotations

import os
import random
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RunContext:
    """Metadatos mínimos para identificar de forma única una corrida.

    Attributes
    ----------
    seed : int
        Semilla global aplicada por `set_seed`.
    git_sha : str
        SHA del commit HEAD, o "unknown" si no hay repositorio.
    git_dirty : bool
        True si el árbol de trabajo tiene cambios sin commitear. Un resultado
        producido con `git_dirty=True` no es reproducible a partir del SHA.
    """

    seed: int
    git_sha: str
    git_dirty: bool

    def as_dict(self) -> dict[str, Any]:
        """Devuelve el contexto como diccionario serializable."""
        return asdict(self)


def set_seed(seed: int = 42, deterministic: bool = True) -> None:
    """Fija las semillas de random, NumPy y PyTorch.

    Parameters
    ----------
    seed : int, default=42
        Valor de la semilla.
    deterministic : bool, default=True
        Si True, fuerza kernels deterministas en PyTorch y desactiva el
        autotuner de cuDNN. Cuesta rendimiento; desactívalo para entrenamientos
        largos donde solo importe la reproducibilidad aproximada.

    Notes
    -----
    `CUBLAS_WORKSPACE_CONFIG` solo surte efecto si se define antes de que CUDA
    se inicialice. Llama a esta función al inicio del script, antes de mover
    cualquier tensor a la GPU.
    """
    random.seed(seed)
    # NPY002 se ignora aqui a proposito: hay que sembrar el estado global legado
    # de NumPy porque MNE y scikit-learn (random_state=None) leen de ahi. En
    # codigo de analisis nuevo, usar np.random.default_rng(seed).
    np.random.seed(seed)  # noqa: NPY002
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import torch
    except ImportError:
        return

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.backends.cudnn.benchmark = False
        # warn_only: algunas ops no tienen implementación determinista y
        # abortarían el entrenamiento en lugar de solo advertir.
        torch.use_deterministic_algorithms(True, warn_only=True)


def _git(*args: str) -> str:
    """Ejecuta un comando git y devuelve stdout limpio."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_run_context(seed: int = 42) -> RunContext:
    """Captura el estado del repositorio para anexarlo a los resultados.

    Returns
    -------
    RunContext
        Semilla, SHA del commit y estado de limpieza del árbol de trabajo.

    Examples
    --------
    >>> ctx = get_run_context(seed=7)
    >>> ctx.seed
    7
    """
    try:
        sha = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--porcelain"))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        sha, dirty = "unknown", True
    return RunContext(seed=seed, git_sha=sha, git_dirty=dirty)

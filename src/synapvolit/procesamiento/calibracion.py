"""Matriz de calibración en memoria y normalización contra ella.

La matriz guarda, por canal, la envolvente en reposo y la envolvente máxima robusta en cada
movimiento. La activación normalizada de un canal es::

    a = (envolvente - reposo) / (referencia - reposo)

donde la referencia es la del canal en su propio movimiento (el canal 0 contra la extensión,
el 1 contra la flexión...). Así "0.3" significa "30% de lo que este canal alcanzó en su
movimiento durante la calibración", que es lo que el contrato llama fracción de MVC.

En niños con PC la MVC es poco reproducible, así que la referencia de cada movimiento es la
mediana, entre repeticiones, del percentil 95 de la envolvente de cada repetición: un pico
aislado no la infla y una repetición floja no la hunde.

Nada se escribe a disco: la matriz vive en memoria (ver la declaración del README).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MOVIMIENTOS = ("extension", "flexion", "pronacion", "supinacion")  # clases 1..4 del contrato


@dataclass(frozen=True)
class MatrizCalibracion:
    """Reposo y referencia de máxima activación por canal y movimiento (µV de envolvente)."""

    reposo_uv: np.ndarray  # (canales,)
    mvc_uv: np.ndarray  # (movimientos, canales)
    agonista: tuple[int, ...] = (0, 1, 2, 3)  # canal agonista de cada movimiento
    antagonista: tuple[int, ...] = (1, 0, 3, 2)  # extensión ↔ flexión, pronación ↔ supinación

    @property
    def referencia_uv(self) -> np.ndarray:
        """Referencia de cada canal: su envolvente en el movimiento del que es agonista."""
        ref = np.empty(len(self.reposo_uv))
        for m, c in enumerate(self.agonista):
            ref[c] = self.mvc_uv[m, c]
        return ref

    def normalizar(self, env_uv: np.ndarray, out: np.ndarray) -> np.ndarray:
        """Activación normalizada por canal, recortada a [0, 1.5]."""
        np.subtract(env_uv, self.reposo_uv, out=out)
        np.divide(out, self._rango, out=out)
        return np.clip(out, 0.0, 1.5, out=out)

    def coactivacion(self, activacion: np.ndarray, movimiento: int) -> float:
        """Razón antagonista / agonista del movimiento (0 = sin co-contracción)."""
        ag = activacion[self.agonista[movimiento]]
        return float(activacion[self.antagonista[movimiento]] / max(ag, 0.05))

    def __post_init__(self) -> None:
        rango = self.referencia_uv - self.reposo_uv
        if np.any(rango <= 0):
            malos = [MOVIMIENTOS[m] for m, c in enumerate(self.agonista) if rango[c] <= 0]
            raise ValueError(f"calibración inválida: el canal de {malos} no supera su reposo")
        object.__setattr__(self, "_rango", rango)


def _repeticiones(etiquetas: np.ndarray, clase: int) -> list[tuple[int, int]]:
    """Intervalos contiguos ``[ini, fin)`` donde la etiqueta vale ``clase``."""
    m = np.concatenate([[False], etiquetas == clase, [False]])
    bordes = np.flatnonzero(np.diff(m.astype(np.int8)))
    return list(zip(bordes[::2], bordes[1::2], strict=True))


def calibrar(
    env_uv: np.ndarray, valida: np.ndarray, etiquetas: np.ndarray, *, percentil: float = 95.0
) -> MatrizCalibracion:
    """Matriz desde la envolvente de una sesión etiquetada (0 reposo, 1..4 movimientos).

    Raises
    ------
    ValueError
        Si falta reposo o algún movimiento, o si un canal no se activa en su movimiento.
    """
    canales = env_uv.shape[1]
    reposo = np.empty(canales)
    en_reposo = (etiquetas == 0)[:, None] & valida
    for c in range(canales):
        if not en_reposo[:, c].any():
            raise ValueError("la calibración no tiene reposo válido")
        reposo[c] = np.median(env_uv[en_reposo[:, c], c])
    mvc = np.empty((len(MOVIMIENTOS), canales))
    for m in range(len(MOVIMIENTOS)):
        reps = _repeticiones(etiquetas, m + 1)
        if not reps:
            raise ValueError(f"la calibración no tiene repeticiones de {MOVIMIENTOS[m]}")
        picos = []
        for i, j in reps:
            seg, ok = env_uv[i:j], valida[i:j].all(axis=1)
            if ok.sum() > 0.5 * (j - i):
                picos.append(np.percentile(seg[ok], percentil, axis=0))
        if not picos:
            raise ValueError(f"ninguna repetición de {MOVIMIENTOS[m]} tiene señal válida")
        mvc[m] = np.median(picos, axis=0)
    return MatrizCalibracion(reposo, mvc)

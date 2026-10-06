"""Intensidad y co-contracción a partir del patrón multicanal de calibración.

Para cada movimiento ``m`` la calibración da un patrón ``p_m = referencia_m - reposo``: cuánto
sube cada canal cuando la persona hace ``m`` con fuerza. Con la envolvente actual ``e``:

* **Intensidad** de ``m``: el escalar ``I`` que mejor explica ``e - reposo ≈ I · p_m`` por mínimos
  cuadrados, ``I = (e - r)·p_m / (p_m·p_m)``. Vale 0 en reposo y 1 cuando el patrón completo se
  reproduce a la fuerza de la calibración. Usa todos los canales, pesados por cuánto participan
  en ese movimiento, así que no depende de que un canal sea específico.
* **Co-contracción** de ``m``: se explica ``e - r`` con los patrones del movimiento y de su
  antagonista a la vez (extensión ↔ flexión, pronación ↔ supinación),
  ``e - r ≈ a · p_m + c · p_antagonista``, y se reporta ``c / a``. Ajustarlos juntos evita que la
  parte compartida de los patrones (la diafonía) se cuente como antagonista. Si los dos patrones
  son casi paralelos, esa separación no es posible y la co-contracción queda como no disponible.

Todo se precalcula al cargar la calibración: en línea son productos punto sobre arreglos fijos.
"""

from __future__ import annotations

import numpy as np

from ..procesamiento import MatrizCalibracion

ANTAGONISTA = (1, 0, 3, 2)  # por movimiento: extensión ↔ flexión, pronación ↔ supinación


class Intensidades:
    """Intensidad y co-contracción de los cuatro movimientos para una envolvente."""

    COND_MAX = 30.0  # número de condición máximo para separar agonista y antagonista

    def __init__(self, matriz: MatrizCalibracion) -> None:
        self.r = matriz.reposo_uv.astype(np.float64)
        p = matriz.mvc_uv - self.r  # (movimientos, canales)
        self.p = p
        self.norma2 = np.einsum("ij,ij->i", p, p)
        nm = len(p)
        self.pinv = np.zeros((nm, 2, p.shape[1]))
        self.co_fiable = np.zeros(nm, bool)
        for m in range(nm):
            a = np.stack([p[m], p[ANTAGONISTA[m]]], axis=1)  # (canales, 2)
            if np.linalg.cond(a) < self.COND_MAX:
                self.pinv[m] = np.linalg.pinv(a)
                self.co_fiable[m] = True
        self._d = np.empty(p.shape[1])
        self._ac = np.empty((nm, 2))

    def calcular(self, env: np.ndarray, intensidad: np.ndarray, coact: np.ndarray) -> None:
        """Escribe ``intensidad`` y ``coact`` por movimiento (``NaN``: no disponible)."""
        np.subtract(env, self.r, out=self._d)
        np.dot(self.p, self._d, out=intensidad)
        intensidad /= self.norma2
        np.clip(intensidad, 0.0, 1.5, out=intensidad)
        np.einsum("mkc,c->mk", self.pinv, self._d, out=self._ac)
        np.maximum(self._ac, 0.0, out=self._ac)
        np.divide(self._ac[:, 1], np.maximum(self._ac[:, 0], 0.05), out=coact)
        np.clip(coact, 0.0, 1.0, out=coact)
        coact[~self.co_fiable] = np.nan

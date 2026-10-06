"""Envolvente RMS sobre ventana deslizante, exacta y en O(1) por muestra.

Se mantiene la suma de cuadrados de las últimas ``W`` muestras: cada muestra nueva suma su
cuadrado y resta el de la que sale de la ventana. Por bloques se hace con dos sumas
acumuladas (la de los cuadrados que entran y la de los que salen), sin ciclos de Python por
muestra. Las muestras inválidas no cuentan: la RMS se calcula solo con las válidas y la
envolvente se declara inválida si en la ventana hay menos de la fracción mínima.
"""

from __future__ import annotations

import numpy as np


class RMSDeslizante:
    """RMS móvil por canal con validez explícita y búferes preasignados."""

    RECALCULO = 2000  # cada cuántos bloques se recalcula la suma desde cero (deriva de redondeo)

    def __init__(self, canales: int, ventana: int, fraccion_valida: float = 0.8) -> None:
        w = self.ventana = ventana
        self.cuad = np.zeros((w, canales))  # cuadrados en la ventana (0 si la muestra es inválida)
        self.val = np.zeros((w, canales))  # 1.0 si la muestra es válida
        self.suma = np.zeros(canales)
        self.n = np.zeros(canales)
        self.pos = 0
        self.minimo = fraccion_valida * w
        self._bloques = 0
        self._t = [np.empty((w, canales)) for _ in range(6)]  # temporales de tamaño máximo

    def actualizar(
        self, y: np.ndarray, valido: np.ndarray, env: np.ndarray, env_valida: np.ndarray
    ) -> None:
        """Procesa ``y`` ``(k, canales)``; escribe la envolvente de cada muestra en ``env``."""
        for i in range(0, len(y), self.ventana):  # bloques más largos que la ventana, en trozos
            j = min(i + self.ventana, len(y))
            self._trozo(y[i:j], valido[i:j], env[i:j], env_valida[i:j])

    def _trozo(self, y, valido, env, env_valida) -> None:
        k, w, p = len(y), self.ventana, self.pos
        sq, v, osq, ov, cs, cn = (t[:k] for t in self._t)
        np.multiply(y, y, out=sq)
        v[...] = valido
        sq *= v  # las inválidas no suman
        k1 = min(k, w - p)  # lo que sale de la ventana ocupa las mismas posiciones del anillo
        osq[:k1], osq[k1:] = self.cuad[p : p + k1], self.cuad[: k - k1]
        ov[:k1], ov[k1:] = self.val[p : p + k1], self.val[: k - k1]
        self.cuad[p : p + k1], self.cuad[: k - k1] = sq[:k1], sq[k1:]
        self.val[p : p + k1], self.val[: k - k1] = v[:k1], v[k1:]
        np.cumsum(sq, axis=0, out=cs)
        cs -= np.cumsum(osq, axis=0, out=osq)
        cs += self.suma
        np.cumsum(v, axis=0, out=cn)
        cn -= np.cumsum(ov, axis=0, out=ov)
        cn += self.n
        self.suma[:], self.n[:] = cs[-1], cn[-1]
        self.pos = (p + k) % w
        np.greater_equal(cn, self.minimo, out=env_valida)
        np.maximum(cn, 1.0, out=cn)
        np.divide(cs, cn, out=cs)
        np.maximum(cs, 0.0, out=cs)  # una resta acumulada puede dar -1e-12
        np.sqrt(cs, out=env, casting="same_kind")
        self._bloques += 1
        if self._bloques % self.RECALCULO == 0:
            self.suma[:], self.n[:] = self.cuad.sum(axis=0), self.val.sum(axis=0)

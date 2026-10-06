"""Diezmado para el osciloscopio de la interfaz: mínimo y máximo por cubeta de 5 ms.

Mandar 2000 muestras por segundo y canal a la pantalla sería inútil (tiene unos cientos de
píxeles) y caro. Promediar borraría los picos. Lo que hace un osciloscopio digital es guardar el
mínimo y el máximo de cada cubeta: dibujados como una línea vertical por cubeta, la traza se ve
igual que la original a esa escala, con todos sus picos. Una cubeta con alguna muestra inválida
se marca como hueco (``NaN`` → ``null``), nunca como cero.
"""

from __future__ import annotations

import numpy as np


class Osciloscopio:
    """Acumula mín/máx por cubeta del bloque filtrado que entrega el procesador."""

    def __init__(
        self, canales: int, fs: float, cubeta_s: float = 0.005, capacidad: int = 64
    ) -> None:
        self.m = max(1, round(cubeta_s * fs))
        self.dt_ms = 1000.0 * self.m / fs
        self.mn = np.full((capacidad, canales), np.nan)
        self.mx = np.full((capacidad, canales), np.nan)
        self.n = 0  # cubetas listas sin publicar
        self._pmin = np.full(canales, np.inf)
        self._pmax = np.full(canales, -np.inf)
        self._inv = np.zeros(canales, bool)
        self._llenas = 0

    def agregar(self, y: np.ndarray, valido: np.ndarray) -> None:
        i, k = 0, len(y)
        while i < k:
            j = min(i + self.m - self._llenas, k)
            np.minimum(self._pmin, y[i:j].min(axis=0), out=self._pmin)
            np.maximum(self._pmax, y[i:j].max(axis=0), out=self._pmax)
            self._inv |= ~valido[i:j].all(axis=0)
            self._llenas += j - i
            i = j
            if self._llenas == self.m:
                if self.n == len(self.mn):  # nadie publicó a tiempo: se pierde la más vieja
                    self.mn[:-1], self.mx[:-1] = self.mn[1:], self.mx[1:]
                    self.n -= 1
                self.mn[self.n] = np.where(self._inv, np.nan, self._pmin)
                self.mx[self.n] = np.where(self._inv, np.nan, self._pmax)
                self.n += 1
                self._pmin.fill(np.inf)
                self._pmax.fill(-np.inf)
                self._inv[:] = False
                self._llenas = 0

    def extraer(self) -> tuple[np.ndarray, np.ndarray]:
        """Cubetas pendientes ``(n, canales)`` y vacía la cola (copias: la cola se reutiliza)."""
        mn, mx = self.mn[: self.n].copy(), self.mx[: self.n].copy()
        self.n = 0
        return mn, mx

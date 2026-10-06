"""Decisión en línea: LDA + suavizado de posteriores + intensidad del patrón.

Se actualiza una vez por paso del bucle (~100 Hz) y se consulta cuando se publica (~8 Hz). Las
posteriores de los últimos ``n`` pasos se promedian con una suma corriente (O(1) por paso): la
clase decidida es la de mayor probabilidad media y la confianza es esa probabilidad. Así una
ventana aislada mal clasificada no hace parpadear al personaje.

Ausencia explícita: un paso sin rasgos válidos no entra al promedio, y si en la ventana no hay
suficientes pasos válidos, ``decision`` devuelve ``None``.
"""

from __future__ import annotations

import numpy as np

from ..procesamiento import MatrizCalibracion
from .intensidad import Intensidades
from .modelo import ModeloLDA


class Decisor:
    """Modelo, intensidades y suavizado, con todos los arreglos reservados al inicio."""

    def __init__(
        self, modelo: ModeloLDA, matriz: MatrizCalibracion, pasos: int = 12, minimo: float = 0.75
    ) -> None:
        nk, nm = len(modelo.clases), len(matriz.mvc_uv)
        self.modelo, self.int = modelo, Intensidades(matriz)
        self.n, self.minimo = pasos, max(1, round(minimo * pasos))
        self._post = np.zeros((pasos, nk))
        self._inten = np.zeros((pasos, nm))
        self._co = np.zeros((pasos, nm))
        self._ok = np.zeros(pasos, bool)
        self._suma_post = np.zeros(nk)
        self._suma_int = np.zeros(nm)
        self._suma_co = np.zeros(nm)
        self._n_co = np.zeros(nm)
        self._i = 0
        self._p, self._it, self._c = np.empty(nk), np.empty(nm), np.empty(nm)
        self.probabilidades = np.zeros(nk)  # promedio más reciente (para quien quiera mostrarlo)

    def actualizar(self, rasgos: np.ndarray, env_uv: np.ndarray, valido: bool) -> None:
        i = self._i
        if self._ok[i]:  # sale de la ventana lo que se había sumado en esta posición
            self._suma_post -= self._post[i]
            self._suma_int -= self._inten[i]
            co_viejo = self._co[i]
            ok = ~np.isnan(co_viejo)
            self._suma_co[ok] -= co_viejo[ok]
            self._n_co[ok] -= 1
        self._ok[i] = valido
        if valido:
            self.modelo.probabilidades(rasgos, self._post[i])
            self.int.calcular(env_uv, self._inten[i], self._co[i])
            self._suma_post += self._post[i]
            self._suma_int += self._inten[i]
            ok = ~np.isnan(self._co[i])
            self._suma_co[ok] += self._co[i][ok]
            self._n_co[ok] += 1
        self._i = (i + 1) % self.n

    def decision(self) -> tuple[int, float, float, float | None] | None:
        """(clase, confianza, intensidad, co-contracción) o ``None`` si no hay señal suficiente."""
        validos = int(self._ok.sum())
        if validos < self.minimo:
            return None
        np.divide(self._suma_post, validos, out=self.probabilidades)
        k = int(np.argmax(self.probabilidades))
        clase = int(self.modelo.clases[k])
        if clase == 0:
            return 0, float(self.probabilidades[k]), 0.0, None
        m = clase - 1
        inten = float(self._suma_int[m] / validos)
        co = float(self._suma_co[m] / self._n_co[m]) if self._n_co[m] > 0 else None
        return clase, float(self.probabilidades[k]), inten, co

"""Calidad de contacto por canal: BUENO, DUDOSO o MALO, con histéresis.

Cuatro síntomas:

* **Sin contacto o sin datos**: la bandera del brazalete o un hueco en el flujo.
* **Red eléctrica**: un electrodo mal pegado capta mucha más red. Se mide como una *línea*
  espectral: tres demoduladores coherentes (lock-in) estiman la amplitud a 60 Hz y a dos
  frecuencias vecinas (52 y 68 Hz) con un ancho de banda de ~1 Hz. La sEMG es de banda ancha y
  aporta casi lo mismo a las tres; la interferencia solo a 60 Hz. El exceso de 60 Hz sobre sus
  vecinas es la red. Medir la potencia que quita la muesca no sirve: una contracción fuerte tiene
  mucha energía cerca de 60 Hz y se confundiría con un electrodo malo.
* **Señal plana**: RMS en banda por debajo del piso de ruido de cualquier amplificador real; indica
  un corto o un cable suelto.
* **Recorte**: fracción de muestras en el tope del ADC.

Se usan umbrales absolutos en µV. Los valores por defecto son un punto de partida y deben
ajustarse con el brazalete real.

Dos defensas contra los parpadeos. Las métricas se resumen cada 10 ms y el estado usa la
**mediana** de los últimos 250 ms: un artefacto breve (un tirón del cable, un golpe) no la mueve.
Encima, la **histéresis** exige que una condición peor dure ``entrar_s`` y una mejor ``salir_s``.
La bandera de contacto del brazalete no pasa por la mediana: es información directa. Los tiempos
se cuentan en muestras, sin reloj, así que se prueban de forma exacta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SIN_EVALUAR, BUENO, DUDOSO, MALO = -1, 0, 1, 2
NOMBRES = {SIN_EVALUAR: "sin evaluar", BUENO: "bueno", DUDOSO: "dudoso", MALO: "malo"}


@dataclass(frozen=True)
class UmbralesCalidad:
    red_dudoso_uv: float = 20.0
    red_malo_uv: float = 100.0
    plano_uv: float = 0.5
    recorte: float = 0.01
    entrar_s: float = 0.25
    salir_s: float = 0.5
    tau_s: float = 0.25  # ventana de la mediana


UMBRALES = UmbralesCalidad()


class CalidadContacto:
    """Estado de contacto de cada canal a partir de bloques ya filtrados."""

    SUBBLOQUE_S = 0.010

    def __init__(
        self,
        canales: int,
        fs: float,
        tope_uv: float,
        u: UmbralesCalidad = UMBRALES,
        red_hz: float = 60.0,
    ) -> None:
        self.fs, self.u, self.tope = fs, u, 0.999 * tope_uv
        self.m = max(1, round(self.SUBBLOQUE_S * fs))  # muestras por subbloque
        self.r = max(1, round(u.tau_s / self.SUBBLOQUE_S))  # subbloques en la mediana
        self.estado = np.full(canales, SIN_EVALUAR, np.int8)
        self._metricas = np.zeros((3, self.r, canales))  # red (µV RMS), banda², fracción recortada
        self._acc = np.zeros((3, canales))
        self._inv = np.zeros(canales, bool)
        self._llenas = 0
        self._cerrados = 0
        self._cand = np.full(canales, SIN_EVALUAR, np.int8)
        self._cuenta = np.zeros(canales)
        self._obj = np.empty(canales, np.int8)
        f0 = red_hz
        self._w = 2 * np.pi * np.array([f0, f0 - 8.0, f0 + 8.0]) / fs  # línea y sus vecinas
        self._z = np.zeros((3, canales), complex)  # salida de los demoduladores coherentes
        # (red, banda, recorte) del último subbloque evaluado, para mostrarlos en la interfaz
        self.red_uv = np.zeros(canales)
        self.banda_uv = np.zeros(canales)

    def actualizar(
        self, y_banda: np.ndarray, crudo: np.ndarray, valido: np.ndarray, i0: int
    ) -> np.ndarray:
        """Actualiza con un bloque ``(k, canales)``; ``i0``: índice global de su primera muestra."""
        i, k = 0, len(y_banda)
        while i < k:
            j = min(i + self.m - self._llenas, k)
            yb = y_banda[i:j]
            fase = np.outer(self._w, np.arange(i0 + i, i0 + j))
            z = np.exp(-1j * fase) @ yb / (j - i)  # demodulación coherente del trozo
            self._z += (1.0 - np.exp(-(j - i) / (self.u.tau_s * self.fs))) * (z - self._z)
            self._acc[1] += np.einsum("ij,ij->j", yb, yb)
            self._acc[2] += np.count_nonzero(np.abs(crudo[i:j]) >= self.tope, axis=0)
            self._inv |= ~valido[i:j].all(axis=0)
            self._llenas += j - i
            i = j
            if self._llenas == self.m:
                self._cerrar()
        return self.estado

    def _cerrar(self) -> None:
        u = self.u
        amp = 2 * np.abs(self._z)  # amplitud de pico a 60 Hz y en las vecinas
        self._acc[0] = np.maximum(amp[0] - 0.5 * (amp[1] + amp[2]), 0.0) / np.sqrt(2) * self.m
        self._metricas[:, self._cerrados % self.r] = self._acc / self.m
        self._cerrados += 1
        inv = self._inv.copy()
        self._acc[:] = 0.0
        self._inv[:] = False
        self._llenas = 0
        if self._cerrados < self.r:  # todavía no hay 250 ms de evidencia
            return
        red, banda2, rec = np.median(self._metricas, axis=1)
        self.red_uv[:], self.banda_uv[:] = red, np.sqrt(banda2)
        malo = (
            inv | (self.banda_uv < u.plano_uv) | (rec > u.recorte) | (self.red_uv > u.red_malo_uv)
        )
        obj = self._obj
        obj[:] = BUENO
        obj[self.red_uv > u.red_dudoso_uv] = DUDOSO
        obj[malo] = MALO
        primera = self.estado == SIN_EVALUAR
        self.estado[primera] = obj[primera]
        igual = obj == self._cand
        self._cuenta[igual] += self.m
        self._cuenta[~igual] = self.m
        self._cand[:] = obj
        espera = np.where(obj > self.estado, u.entrar_s, u.salir_s) * self.fs
        cambia = (obj != self.estado) & (self._cuenta >= espera)
        self.estado[cambia] = obj[cambia]

"""Cadena completa por bloques: filtros → envolvente → calidad → normalización.

``Procesador`` lee las muestras nuevas del ``BufferCircular`` que llena el decodificador, de
modo que el intérprete del protocolo sigue siendo puro y el procesamiento puede ir a su propio
ritmo. Todo el estado y los temporales se reservan una sola vez.
"""

from __future__ import annotations

import numpy as np

from ..transporte.trama import BufferCircular
from .calibracion import MatrizCalibracion
from .calidad import MALO, UMBRALES, CalidadContacto, UmbralesCalidad
from .config import ConfigProcesamiento
from .envolvente import RMSDeslizante
from .filtros import FiltroEMG

_LEJOS = -(2**62)


class Procesador:
    """Procesa sEMG en línea y deja el último estado listo para quien lo consuma.

    Atributos de salida (se sobrescriben en cada bloque, nunca se reasignan):

    ``env_uv``, ``env_valida``: envolvente RMS por canal y su validez.
    ``activacion``, ``activacion_valida``: fracción de la referencia de calibración por canal;
    solo es válida con envolvente válida, contacto no MALO y una matriz cargada.
    ``calidad``: estado de contacto por canal (ver ``calidad.py``).
    """

    def __init__(
        self,
        cfg: ConfigProcesamiento,
        matriz: MatrizCalibracion | None = None,
        *,
        tope_uv: float = 32767 * 0.5,
        umbrales: UmbralesCalidad = UMBRALES,
    ) -> None:
        nc, b = cfg.canales, cfg.bloque_max
        self.cfg, self.matriz = cfg, matriz
        self.filtro = FiltroEMG(cfg)
        self.rms = RMSDeslizante(nc, cfg.ventana, cfg.fraccion_valida)
        self.cal = CalidadContacto(nc, cfg.fs, tope_uv, umbrales, cfg.red_hz)
        self.env_uv = np.zeros(nc, np.float32)
        self.env_valida = np.zeros(nc, bool)
        self.activacion = np.zeros(nc)
        self.activacion_valida = np.zeros(nc, bool)
        self.procesadas = 0  # muestras procesadas desde el inicio
        self.atrasos = 0  # muestras que se perdieron porque el búfer dio la vuelta sin leerse
        self._leidas = 0
        self._ult_inv = np.full(nc, _LEJOS, np.int64)
        self._x, self._v = np.empty((b, nc)), np.empty((b, nc), bool)
        self._veff, self._inv = np.empty((b, nc), bool), np.empty((b, nc), bool)
        self._gi, self._ti = np.empty(b, np.int64), np.empty((b, nc), np.int64)
        self._rampa = np.arange(b, dtype=np.int64)
        self._env, self._envv = np.empty((b, nc), np.float32), np.empty((b, nc), bool)

    @property
    def calidad(self) -> np.ndarray:
        return self.cal.estado

    def procesar(self, x: np.ndarray, valido: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Procesa un bloque ``(k, canales)`` con ``k <= bloque_max``.

        Returns
        -------
        env, env_valida : np.ndarray
            Vistas a la envolvente de cada muestra del bloque (válidas hasta el siguiente bloque).
        """
        k = len(x)
        # validez efectiva: tras cualquier muestra inválida se descartan las del asentamiento
        gi = self._gi[:k]
        np.add(self._rampa[:k], self.procesadas, out=gi)
        ti, inv, veff = self._ti[:k], self._inv[:k], self._veff[:k]
        np.logical_not(valido, out=inv)
        ti.fill(_LEJOS)
        np.copyto(ti, gi[:, None], where=inv)
        np.maximum.accumulate(ti, axis=0, out=ti)
        np.maximum(ti, self._ult_inv, out=ti)
        self._ult_inv[:] = ti[-1]
        np.subtract(gi[:, None], ti, out=ti)
        np.greater(ti, self.cfg.asentamiento, out=veff)
        veff &= valido
        y_banda, y = self.filtro.aplicar(x)
        env, envv = self._env[:k], self._envv[:k]
        self.rms.actualizar(y, veff, env, envv)
        self.cal.actualizar(y_banda, x, valido, self.procesadas)
        self.env_uv[:] = env[-1]
        np.logical_and(envv[-1], self.cal.estado != MALO, out=self.env_valida)
        if self.matriz is not None:
            self.matriz.normalizar(self.env_uv, self.activacion)
            self.activacion_valida[:] = self.env_valida
        self.procesadas += k
        return env, envv

    def actualizar(self, buf: BufferCircular) -> int:
        """Procesa todo lo que el decodificador escribió desde la última llamada."""
        nuevas = buf.escritas - self._leidas
        if nuevas > buf.capacidad:  # el consumidor se atrasó una vuelta entera: se pierde lo viejo
            self.atrasos += nuevas - buf.capacidad
            self._leidas = buf.escritas - buf.capacidad
            nuevas = buf.capacidad
        hechas = 0
        while hechas < nuevas:
            k = min(nuevas - hechas, self.cfg.bloque_max)
            i = self._leidas % buf.capacidad
            k = min(k, buf.capacidad - i)  # bloques contiguos en el anillo
            self._x[:k] = buf.datos[i : i + k]
            self._v[:k] = buf.valido[i : i + k]
            self.procesar(self._x[:k], self._v[:k])
            self._leidas += k
            hechas += k
        return hechas

    def procesar_todo(
        self, x: np.ndarray, valido: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """Procesa una señal completa con el código del tiempo real (para calibrar y probar)."""
        n = len(x)
        env, envv = (
            np.empty((n, self.cfg.canales), np.float32),
            np.empty((n, self.cfg.canales), bool),
        )
        b = self.cfg.bloque_max
        for i in range(0, n, b):
            j = min(i + b, n)
            self._x[: j - i] = x[i:j]
            self._v[: j - i] = True if valido is None else valido[i:j]
            e, ev = self.procesar(self._x[: j - i], self._v[: j - i])
            env[i:j], envv[i:j] = e, ev
        return env, envv

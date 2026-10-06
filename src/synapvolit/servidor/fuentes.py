"""Fuentes de bytes para la sesión: el brazalete por puerto serie o el paciente simulado.

Las dos producen exactamente los mismos bytes (tramas COBS del protocolo v1), así que todo lo
que sigue en la cadena es idéntico. La fuente se elige con un selector obligatorio en la línea
de comandos y se anuncia en cada mensaje de estado: lo simulado nunca se presenta como real.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import numpy as np

from ..datasets import Senal
from ..transporte import ESCENARIOS, Escenario, SimuladorESP32

Entregar = Callable[[bytes | bytearray | memoryview], object]


class FuenteSimulada:
    """Paciente simulado: reproduce sEMG real y hace el movimiento que se le pide.

    Divide la señal en tramos por clase (reposo, extensión...) y, cuando la sesión pide una
    clase, reproduce en bucle el siguiente tramo de esa clase. Así la calibración guiada y el
    juego se pueden probar de punta a punta con sEMG real, sin brazalete.
    """

    nombre = "simulada"

    def __init__(
        self, senal: Senal, escenario: Escenario = ESCENARIOS["limpio"], minimo_s: float = 0.5
    ) -> None:
        self.sim = SimuladorESP32(senal.datos, senal.fs, escenario=escenario)
        self.fs, self.error = senal.fs, None
        n = self.sim.n
        etq = senal.etiquetas[: self.sim.tramas_ciclo * n : n]  # etiqueta de cada trama
        bordes = np.flatnonzero(np.diff(etq)) + 1
        self.tramos: dict[int, list[tuple[int, int]]] = {}
        for i, f in zip(np.r_[0, bordes], np.r_[bordes, len(etq)], strict=True):
            if (f - i) * n / senal.fs >= minimo_s:
                self.tramos.setdefault(int(etq[i]), []).append((int(i), int(f)))
        self._siguiente: dict[int, int] = {}
        self.clase = -1
        self.pedir(0)

    def pedir(self, clase: int) -> None:
        """Cambia al siguiente tramo de ``clase`` (sin efecto si ya la está haciendo)."""
        if clase == self.clase or clase not in self.tramos:
            return
        k = self._siguiente.get(clase, 0)
        self._siguiente[clase] = k + 1
        self.sim.reproducir(*self.tramos[clase][k % len(self.tramos[clase])])
        self.clase = clase

    async def correr(self, entregar: Entregar, reloj: Callable[[], float]) -> None:
        """Emite tramas al ritmo del ESP32 contra un tiempo objetivo absoluto (sin deriva)."""
        t0, emitidas = reloj(), 0
        while True:
            debidas = int((reloj() - t0) * self.sim.tramas_por_segundo)
            while emitidas < debidas:
                self.sim.emitir(entregar)
                emitidas += 1
            await asyncio.sleep(0.004)


class FuenteSerie:
    """Brazalete real por puerto serie (o cualquier URL de pyserial, como ``loop://``).

    La lectura bloqueante corre en un hilo con tiempo límite de 10 ms, así que nunca detiene el
    bucle de eventos. Si el puerto no existe o se desconecta, lo reporta en ``error`` y reintenta:
    el motor sigue vivo y la interfaz muestra qué falta.
    """

    nombre = "serie"
    fs = None  # lo fija el saludo del brazalete

    def __init__(self, puerto, baudios: int = 921600) -> None:
        self.puerto, self.baudios, self.error = puerto, baudios, None

    def pedir(self, clase: int) -> None:  # un paciente real no recibe órdenes del motor
        return None

    async def correr(self, entregar: Entregar, reloj: Callable[[], float]) -> None:
        import serial

        while True:
            try:
                s = (
                    self.puerto
                    if not isinstance(self.puerto, str)
                    else serial.serial_for_url(self.puerto, self.baudios, timeout=0.01)
                )
                s.timeout = 0.01
            except (serial.SerialException, ValueError) as e:
                self.error = f"no se pudo abrir {self.puerto}: {e}"
                await asyncio.sleep(2.0)
                continue
            self.error = None
            try:
                while True:
                    datos = await asyncio.to_thread(s.read, 4096)
                    if datos:
                        entregar(datos)
            except serial.SerialException as e:
                self.error = f"se perdió {self.puerto}: {e}"
                await asyncio.sleep(1.0)

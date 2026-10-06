"""Simulador del ESP32: reproduce sEMG real con las mismas tramas que enviará el hardware.

La señal base es siempre un registro real (ver ``synapvolit.datasets``). Lo único que el
simulador agrega son las fallas que exige el estándar DUNNE para probar la ruta completa
(desconexión, pérdida de contacto y ruido de red), y solo cuando el escenario las pide. Las
fallas son sembrables: la misma semilla reproduce exactamente los mismos eventos.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .trama import BIT_SATURACION, Empaquetador


@dataclass(frozen=True)
class Escenario:
    """Fallas del enlace y de los electrodos, todas apagadas por defecto."""

    nombre: str = "limpio"
    perdida_tramas: float = 0.0  # probabilidad de perder una trama completa
    corrupcion: float = 0.0  # probabilidad de alterar un byte de una trama
    desconexion_cada_s: float = 0.0  # 0: nunca se desconecta
    desconexion_dur_s: float = 1.5
    contacto_canal: int = -1  # -1: ningún electrodo pierde contacto
    contacto_cada_s: float = 0.0
    contacto_dur_s: float = 2.0
    red_uv: float = 0.0  # amplitud de interferencia de red (60 Hz) añadida a todos los canales
    semilla: int = 0


ESCENARIOS = {
    "limpio": Escenario(),
    "fallas": Escenario(
        "fallas",
        perdida_tramas=0.01,
        corrupcion=0.005,
        desconexion_cada_s=20.0,
        contacto_canal=2,
        contacto_cada_s=15.0,
        red_uv=40.0,
        semilla=7,
    ),
}


class SimuladorESP32:
    """Genera las tramas del ESP32 a partir de una señal real en µV.

    Parameters
    ----------
    senal_uv : np.ndarray
        ``(N, canales)`` en µV. Se reproduce en bucle.
    fs : float
        Frecuencia de muestreo de ``senal_uv``.
    por_trama : int
        Muestras por canal en cada trama (20 a 2 kHz = 10 ms).
    lsb_uv : float
        µV por cuenta del ADC simulado; lo que exceda ``int16`` se satura y se marca.
    escenario : Escenario
        Fallas a inyectar.
    hola_cada_s : float
        Periodo del saludo de control, para que un receptor que llega tarde conozca la escala.
    t0_us : int
        Reloj inicial del microcontrolador (sirve para probar la vuelta del ``uint32``).
    """

    def __init__(
        self,
        senal_uv: np.ndarray,
        fs: float,
        *,
        por_trama: int = 20,
        lsb_uv: float = 0.5,
        escenario: Escenario = ESCENARIOS["limpio"],
        hola_cada_s: float = 2.0,
        t0_us: int = 0,
    ) -> None:
        nfr = len(senal_uv) // por_trama
        if nfr < 1:
            raise ValueError("la señal es más corta que una trama")
        cuentas = np.rint(senal_uv[: nfr * por_trama] / lsb_uv)
        satura = np.abs(cuentas) > 32767
        # conversión a cuentas una sola vez: en el bucle solo se copian bloques
        self.cuentas = np.clip(cuentas, -32768, 32767).astype(np.int16)
        self._sat = satura.reshape(nfr, por_trama, -1).any(axis=(1, 2))
        self.fs, self.n, self.lsb_uv, self.esc = fs, por_trama, lsb_uv, escenario
        self.canales = self.cuentas.shape[1]
        self.tramas_ciclo, self.k = nfr, 0
        self._ini, self._fin, self._j = (
            0,
            nfr,
            0,
        )  # tramo que se reproduce en bucle (por defecto, todo)
        self._emp = Empaquetador(self.canales, por_trama)
        self._rng = np.random.default_rng(escenario.semilla)
        self._hola_cada = max(1, round(hola_cada_s * fs / por_trama))
        self._t0 = t0_us
        self._bloque = np.empty((por_trama, self.canales), np.int16)
        self._mezcla = np.empty((por_trama, self.canales), np.float64)
        self._viejo = np.empty((por_trama, self.canales), np.float64)
        # fundido de 2 tramas (20 ms) al cambiar de tramo: sin él, el salto de un registro a otro
        # aparece como un pico que el filtro convierte en un artefacto visible en el osciloscopio
        self._fade_n = 2
        rampa = (np.arange(self._fade_n * por_trama) + 1.0) / (self._fade_n * por_trama + 1.0)
        self._fade_w = rampa.reshape(self._fade_n, por_trama, 1)
        self._fade_k, self._jv = self._fade_n, 0
        self._fase = np.arange(por_trama, dtype=np.float64)
        self._sen = np.empty(por_trama, np.float64)
        self._hola = {
            "tipo": "hola",
            "version": 1,
            "fs": fs,
            "canales": self.canales,
            "por_trama": por_trama,
            "lsb_uv": lsb_uv,
            "fuente": "simulada",
            "escenario": escenario.nombre,
        }

    @property
    def tramas_por_segundo(self) -> float:
        return self.fs / self.n

    def reproducir(self, ini: int, fin: int) -> None:
        """Reproduce en bucle las tramas ``[ini, fin)`` a partir de la siguiente emisión.

        La fuente guiada lo usa para que el "paciente simulado" haga el movimiento que se le pide.
        """
        if not 0 <= ini < fin <= self.tramas_ciclo:
            raise ValueError(f"tramo fuera de la señal: [{ini}, {fin})")
        if self.k > 0:  # ya se estaba reproduciendo algo: se funde con lo nuevo
            self._jv, self._fade_k = self._j, 0
        self._ini, self._fin, self._j = ini, fin, ini

    def _en_ventana(self, t_s: float, cada: float, dur: float) -> bool:
        return cada > 0 and t_s >= cada and (t_s % cada) < dur

    def emitir(self, destino: Callable[[memoryview], object]) -> None:
        """Entrega a ``destino`` los bytes de la trama ``k`` (y el saludo si toca) y avanza."""
        k, e = self.k, self.esc
        self.k += 1
        t_s = k / self.tramas_por_segundo
        if k % self._hola_cada == 0:
            destino(self._emp.control(self._hola))
        if self._en_ventana(t_s, e.desconexion_cada_s, e.desconexion_dur_s):
            return  # enlace caído: el ESP32 sigue contando, pero nada llega
        if e.perdida_tramas and self._rng.random() < e.perdida_tramas:
            return
        j = self._j
        self._j = self._j + 1 if self._j + 1 < self._fin else self._ini
        bloque = self.cuentas[j * self.n : (j + 1) * self.n]
        banderas = BIT_SATURACION if self._sat[j] else 0
        contacto = (
            self._en_ventana(t_s, e.contacto_cada_s, e.contacto_dur_s) and e.contacto_canal >= 0
        )
        fundir = self._fade_k < self._fade_n
        if e.red_uv or contacto or fundir:
            # interferencia de red (60 Hz) con fase continua entre tramas
            np.add(self._fase, k * self.n, out=self._sen)
            np.multiply(self._sen, 2 * np.pi * 60.0 / self.fs, out=self._sen)
            np.sin(self._sen, out=self._sen)
            np.copyto(self._mezcla, bloque)
            if fundir:
                w = self._fade_w[self._fade_k]
                np.copyto(self._viejo, self.cuentas[self._jv * self.n : (self._jv + 1) * self.n])
                self._mezcla *= w
                self._viejo *= 1.0 - w
                self._mezcla += self._viejo
                self._fade_k += 1
                self._jv = self._jv + 1 if self._jv + 1 < self.tramas_ciclo else 0
            if e.red_uv:
                self._mezcla += (e.red_uv / self.lsb_uv) * self._sen[:, None]
            if contacto:  # electrodo flotante: domina la red y el canal se marca sin contacto
                self._mezcla[:, e.contacto_canal] = (3000.0 / self.lsb_uv) * self._sen
                banderas |= 1 << e.contacto_canal
            np.clip(self._mezcla, -32768, 32767, out=self._mezcla)
            np.copyto(self._bloque, self._mezcla, casting="unsafe")
            bloque = self._bloque
        t_us = self._t0 + round(k * self.n * 1e6 / self.fs)
        trama = self._emp.emg(k, t_us, bloque, banderas)
        if e.corrupcion and self._rng.random() < e.corrupcion:
            i = int(self._rng.integers(0, len(trama) - 1))
            trama[i] ^= int(self._rng.integers(1, 256))
        destino(trama)


def correr(
    sim: SimuladorESP32,
    destino: Callable[[memoryview], object],
    segundos: float,
    *,
    tiempo_real: bool = True,
    reloj: Callable[[], float] = time.perf_counter,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Emite ``segundos`` de tramas; con ``tiempo_real`` respeta la cadencia del ESP32.

    La cadencia se calcula contra un tiempo objetivo absoluto, así que los retrasos de un
    ``sleep`` no se acumulan. Devuelve el número de tramas emitidas.
    """
    total = round(segundos * sim.tramas_por_segundo)
    t0 = reloj()
    for i in range(total):
        if tiempo_real:
            espera = t0 + i / sim.tramas_por_segundo - reloj()
            if espera > 0:
                dormir(espera)
        sim.emitir(destino)
    return total

"""Puente entre la sesión en vivo y el registro de eventos.

Traduce lo que pasa en el motor a hechos del registro:

* los eventos del juego (inicio y fin de ejercicio, pausas) llegan como órdenes y se anotan;
* al terminar cada ejercicio, el motor le agrega lo que solo él sabe: intensidad pico del
  movimiento pedido, co-contracción media, fracción del tiempo con decisión válida y la MDF del
  agonista (para el índice de fatiga);
* la validez de la señal se anota solo cuando cambia, con un filtro de dos pasos de 125 ms para
  no llenar el registro de parpadeos.

Escribir a disco y exportar corre en hilos; esta clase nunca bloquea el bucle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from ..procesamiento import MOVIMIENTOS
from ..registro import Registro, exportar, resumen


class Bitacora:
    VOLCADO_S = 1.0
    SIN_CLIENTE_S = 60.0  # sin nadie conectado tanto tiempo, la sesión se cierra y se exporta

    def __init__(self, raiz: Path, reloj: Callable[[], float]) -> None:
        self.raiz, self.reloj = Path(raiz), reloj
        self.registro: Registro | None = None
        self.minutos = 30.0
        self._ej: dict[int, dict] = {}
        self._senal, self._cand = False, 0
        self._t_volcado = -1e9
        self._volcando: asyncio.Future | None = None
        self._exportando: asyncio.Future | None = None
        self._codigo_export: str | None = None

    @property
    def codigo(self) -> str | None:
        return None if self.registro is None else self.registro.codigo

    def iniciar(self, codigo: str, minutos: float, **info) -> None:
        self.registro = Registro(self.raiz, codigo, self.reloj, **info)
        self.minutos, self._ej, self._senal, self._cand = minutos, {}, False, 0

    def evento(self, orden: dict, mdf: Callable[[str, float], float | None]) -> None:
        r, tipo = self.registro, orden["tipo"]
        if tipo == "ejercicio_inicio":
            r.anotar(tipo, id=orden["id"], movimiento=orden["movimiento"])
            self._ej[orden["id"]] = {
                "mov": orden["movimiento"],
                "t0": r.ahora(),
                "n": 0,
                "ok": 0,
                "pico": None,
                "co": 0.0,
                "nco": 0,
            }
        elif tipo == "ejercicio_fin":
            a = self._ej.pop(orden["id"], None)
            extra = {}
            if a is not None:
                extra = {
                    "movimiento": a["mov"],
                    "intensidad_pico": a["pico"],
                    "coactivacion_media": round(a["co"] / a["nco"], 3) if a["nco"] else None,
                    "fraccion_valida": round(a["ok"] / a["n"], 3) if a["n"] else None,
                    "mdf_hz": mdf(a["mov"], r.ahora() - a["t0"])
                    if orden["resultado"] == "acierto"
                    else None,
                }
            r.anotar(
                tipo, id=orden["id"], resultado=orden["resultado"], rt_s=orden["rt_s"], **extra
            )
        else:
            r.anotar(tipo)

    def tick_decision(self, decisor, valida: bool) -> None:
        """Cada 125 ms: acumula por ejercicio abierto y anota los cambios de validez de la señal."""
        if self.registro is None:
            return
        for a in self._ej.values():
            a["n"] += 1
            a["ok"] += valida
            if decisor is not None and a["mov"] in MOVIMIENTOS:
                d = decisor.del_movimiento(MOVIMIENTOS.index(a["mov"]))
                if d is not None:
                    a["pico"] = round(max(a["pico"] or 0.0, d[0]), 3)
                    if d[1] is not None:
                        a["co"], a["nco"] = a["co"] + d[1], a["nco"] + 1
        if valida != self._senal:
            self._cand += 1
            if self._cand >= 2:
                self._senal, self._cand = valida, 0
                self.registro.anotar("senal", valida=valida)
        else:
            self._cand = 0

    def resumen(self) -> dict:
        return {} if self.registro is None else resumen(list(self.registro.eventos), self.minutos)

    def terminar(self, motivo: str) -> None:
        """Cierra y exporta en un hilo; el resultado se recoge en ``tick``."""
        reg, self.registro, self._ej = self.registro, None, {}
        if reg is not None:
            self._codigo_export = reg.codigo
            loop = asyncio.get_running_loop()
            self._exportando = loop.run_in_executor(
                None, self._cerrar_exportar, reg, motivo, self.minutos
            )

    @staticmethod
    def _cerrar_exportar(reg: Registro, motivo: str, minutos: float) -> dict:
        reg.cerrar(motivo)
        return exportar(reg.eventos, reg.carpeta, reg.sesion, minutos)

    def terminar_ya(self, motivo: str) -> None:
        """Para el apagado del motor: cierra y exporta sin hilos."""
        if self.registro is not None:
            self._cerrar_exportar(self.registro, motivo, self.minutos)
            self.registro = None

    def tick(self, t: float, hay_clientes: bool) -> tuple[str, dict] | None:
        """Vuelca a disco cada segundo; tras una exportación devuelve ``(codigo, resumen)``."""
        r = self.registro
        if r is not None and r.pendientes and t - self._t_volcado >= self.VOLCADO_S:
            if self._volcando is None or self._volcando.done():
                self._t_volcado = t
                self._volcando = asyncio.get_running_loop().run_in_executor(None, r.volcar)
        if (
            r is not None
            and not hay_clientes
            and r.ahora() - (r.eventos[-1]["t"]) > self.SIN_CLIENTE_S
        ):
            self.terminar("sin_cliente")
        if self._exportando is not None and self._exportando.done():
            fut, self._exportando = self._exportando, None
            return self._codigo_export, fut.result()
        return None

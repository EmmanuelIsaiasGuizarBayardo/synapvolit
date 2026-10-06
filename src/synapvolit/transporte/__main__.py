"""Demostración sin hardware: simulador del ESP32 → decodificador, con estadísticas por segundo.

Uso::

    uv run python -m synapvolit.transporte --escenario limpio --segundos 10
    uv run python -m synapvolit.transporte --escenario fallas --segundos 30

La fuente es siempre SIMULADA y se anuncia así: reproduce un registro real de GRABMyo.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from ..datasets import cargar_senal
from .simulador import ESCENARIOS, SimuladorESP32, correr
from .trama import BufferCircular, Decodificador


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Simulador del ESP32 con datos reales y decodificador en vivo."
    )
    ap.add_argument("--csv", type=Path, default=Path("data/processed/grabmyo/s1_p01.csv"))
    ap.add_argument("--escenario", choices=sorted(ESCENARIOS), default="limpio")
    ap.add_argument("--segundos", type=float, default=10.0)
    ap.add_argument("--rapido", action="store_true", help="sin esperar: tan rápido como se pueda")
    a = ap.parse_args(argv)
    try:
        senal = cargar_senal(a.csv)
    except FileNotFoundError as e:  # arrancar siempre: decir qué falta y cómo se resuelve
        print(f"Falta la señal de demostración.\n  {e}\n  La descarga se explica en docs/datos.md.")
        return 2
    sim = SimuladorESP32(senal.datos, senal.fs, escenario=ESCENARIOS[a.escenario])
    buf = BufferCircular(sim.canales, capacidad=int(4 * senal.fs))
    dec = Decodificador(buf)
    print(
        f"FUENTE SIMULADA: {senal.meta.get('dataset', '?')} s{senal.meta.get('sesion')} "
        f"p{senal.meta.get('participante')}, {senal.fs:g} Hz, escenario '{a.escenario}'"
    )
    m = int(senal.fs)
    val = np.empty((m, sim.canales), bool)
    datos, t_us = np.empty((m, sim.canales), np.float32), np.empty(m, np.int64)
    inicio = time.perf_counter()
    for s in range(int(np.ceil(a.segundos))):
        correr(sim, dec.alimentar, min(1.0, a.segundos - s), tiempo_real=not a.rapido)
        k = buf.ultimas(m, datos, val, t_us)
        validos = val[:k].mean(axis=0) * 100
        print(
            f"t={s + 1:>3} s | tramas {dec.tramas:>6} | perdidas {dec.perdidas:>4} "
            f"| CRC {dec.crc_malos:>3} "
            f"| COBS {dec.cobs_malos:>3} | válidas por canal "
            + " ".join(f"{v:5.1f}%" for v in validos)
        )
    dur = time.perf_counter() - inicio
    print(
        f"Fin: {dec.tramas} tramas en {dur:.1f} s ({dec.tramas / dur:.0f}/s), "
        f"reinicios {dec.reinicios}, saturadas {dec.saturadas}, formato {dec.formato_malo}"
    )
    if a.escenario == "limpio":  # autoverificación: lo decodificado debe ser idéntico a lo enviado
        g = np.arange(buf.escritas - min(buf.escritas, buf.capacidad), buf.escritas)
        enviado = (sim.cuentas[g % len(sim.cuentas)] * sim.lsb_uv).astype(np.float32)
        ok = np.array_equal(buf.datos[g % buf.capacidad], enviado)
        print(
            "Integridad:",
            "exacta, bit a bit" if ok else "DIFERENCIAS ENTRE LO ENVIADO Y LO RECIBIDO",
        )
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Motor SynapVolit en vivo: sirve sEMG procesada y calibración guiada por WebSocket.

Uso::

    uv run python -m synapvolit.servidor --fuente simulada
    uv run python -m synapvolit.servidor --fuente serie --puerto-serie COM3

La fuente es obligatoria y no tiene valor por defecto: quien opera declara si la señal es real
o simulada. Después se abre el juego con ``?motor=ws://127.0.0.1:8765``.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import sys
from pathlib import Path

from ..datasets import cargar_senal
from ..transporte import ESCENARIOS
from .fuentes import FuenteSerie, FuenteSimulada
from .sesion import Sesion


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Motor SynapVolit: sEMG procesada y calibración por WebSocket."
    )
    ap.add_argument("--fuente", choices=["simulada", "serie"], required=True)
    ap.add_argument("--csv", type=Path, default=Path("data/processed/grabmyo/s1_p01.csv"))
    ap.add_argument("--escenario", choices=sorted(ESCENARIOS), default="limpio")
    ap.add_argument(
        "--puerto-serie", default="", help='p. ej. "COM3"; obligatorio con --fuente serie'
    )
    ap.add_argument("--baudios", type=int, default=921600)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args(argv)
    if a.fuente == "serie":
        if not a.puerto_serie:
            ap.error("--fuente serie requiere --puerto-serie")
        fuente = FuenteSerie(a.puerto_serie, a.baudios)
        descripcion = f"BRAZALETE en {a.puerto_serie} a {a.baudios} baudios"
    else:
        try:
            senal = cargar_senal(a.csv)
        except FileNotFoundError as e:
            print(
                f"Falta la señal de demostración.\n  {e}\n"
                "  La descarga se explica en docs/datos.md."
            )
            return 2
        fuente = FuenteSimulada(senal, ESCENARIOS[a.escenario])
        descripcion = (
            f"FUENTE SIMULADA: {senal.meta.get('dataset', '?')}, escenario '{a.escenario}'"
        )
    host = "127.0.0.1" if a.host == "localhost" else a.host
    if not ipaddress.ip_address(host).is_loopback:
        print(
            f"AVISO: escuchando fuera de la máquina local ({a.host}): "
            "la señal de un paciente quedará expuesta en la red"
        )
    sesion = Sesion(fuente)
    print(f"Motor en ws://{a.host}:{a.puerto} | {descripcion}")
    print(f"Abre el juego con ?motor=ws://{a.host}:{a.puerto}   (Ctrl+C para salir)")
    try:
        asyncio.run(sesion.servir(a.host, a.puerto))
    except KeyboardInterrupt:
        print("Motor detenido")
    except OSError as e:
        print(
            f"No se pudo abrir el puerto {a.puerto}: {e}. "
            "¿Hay otro motor o el puente viejo corriendo?"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

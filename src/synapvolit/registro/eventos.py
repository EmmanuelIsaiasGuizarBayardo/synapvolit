"""Registro de eventos de una sesión (event sourcing): solo se agregan hechos, nunca se editan.

Cada línea del archivo es un evento JSON con su número de orden ``n``, su tiempo ``t`` en segundos
desde el inicio de la sesión (reloj monotónico del motor, el único reloj del registro) y su
``tipo``. Todas las métricas (minutos efectivos, fatiga, exportación) se calculan después con
funciones puras sobre esta lista: si mañana cambia la definición de una métrica, se recalcula
sobre los mismos registros sin tocar el juego ni el motor.

No se guarda sEMG cruda: solo hechos y resúmenes por ejercicio (minimización de datos).

Escritura sin bloquear: ``anotar`` solo agrega a memoria; ``volcar`` escribe lo pendiente y la
sesión la llama desde un hilo una vez por segundo. Cada línea se escribe completa, así que un
cierre abrupto pierde a lo más el último segundo, nunca corrompe lo anterior.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

CODIGO = re.compile(r"^[A-Za-z0-9-]{3,24}$")  # seudónimo del estudio: nunca un nombre


def raiz_por_defecto() -> Path:
    """``%LOCALAPPDATA%\\SynapVolit\\pacientes`` en Windows; ``~/.local/share/...`` en otros."""
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "SynapVolit" / "pacientes"


class Registro:
    """Bitácora de eventos de una sesión de un paciente, en ``raiz/<codigo>/``."""

    def __init__(self, raiz: Path, codigo: str, reloj: Callable[[], float], **info) -> None:
        if not CODIGO.match(codigo):
            raise ValueError("el código debe tener de 3 a 24 letras, números o guiones")
        self.codigo, self.reloj, self.t0 = codigo, reloj, reloj()
        ahora = datetime.now()
        self.carpeta = Path(raiz) / codigo
        self.sesion = f"{ahora:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        self.archivo = self.carpeta / f"{self.sesion}.jsonl"
        self.eventos: list[dict] = []
        self._pendientes: list[str] = []
        self.cerrado = False
        self._cerrojo = threading.Lock()  # volcar puede correr en un hilo mientras se cierra
        self.anotar(
            "sesion_inicio", codigo=codigo, fecha=f"{ahora:%Y-%m-%d}", hora=f"{ahora:%H:%M}", **info
        )

    def ahora(self) -> float:
        return round(self.reloj() - self.t0, 3)

    def anotar(self, tipo: str, **campos) -> dict:
        """Agrega un evento (solo en memoria; ``volcar`` lo lleva a disco)."""
        if self.cerrado:
            raise RuntimeError("el registro ya está cerrado")
        e = {"n": len(self.eventos), "t": self.ahora(), "tipo": tipo, **campos}
        self.eventos.append(e)
        self._pendientes.append(json.dumps(e, ensure_ascii=False, separators=(",", ":")))
        return e

    def volcar(self) -> int:
        """Escribe lo pendiente al final del archivo. Seguro de llamar desde otro hilo."""
        with self._cerrojo:
            lineas, self._pendientes = self._pendientes, []
            if lineas:
                self.carpeta.mkdir(parents=True, exist_ok=True)
                with open(self.archivo, "a", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(lineas) + "\n")
            return len(lineas)

    @property
    def pendientes(self) -> int:
        return len(self._pendientes)

    def cerrar(self, motivo: str) -> None:
        if not self.cerrado:
            self.anotar("sesion_fin", motivo=motivo)
            self.cerrado = True
            self.volcar()


def leer(archivo: Path) -> list[dict]:
    """Lee un registro; una última línea incompleta (un corte de luz) se descarta sin error."""
    eventos = []
    for linea in Path(archivo).read_text(encoding="utf-8").splitlines():
        try:
            eventos.append(json.loads(linea))
        except json.JSONDecodeError:
            break
    return eventos

"""Contrato JSON motor ↔ interfaz, versión 2 (especificación en ``docs/contrato_ws.md``).

Todo lo que entra desde la interfaz se valida aquí antes de tocar la sesión: un comando
malformado produce un mensaje de error para ese cliente, nunca una excepción en el motor.
Lo que sale usa ``null`` para cualquier valor ausente o inválido (ausencia explícita).
"""

from __future__ import annotations

import json
from dataclasses import fields

import numpy as np

from ..procesamiento import MOVIMIENTOS, NOMBRES
from .calibracion import TERMINALES, MaquinaCalibracion, Protocolo

VERSION = 2
LIMITES = {  # parámetro: (mínimo, máximo)
    "repeticiones": (1, 10),
    "reposo_s": (0.5, 30.0),
    "preparar_s": (0.0, 10.0),
    "contraccion_s": (0.3, 10.0),
    "descanso_s": (0.0, 30.0),
}


class ErrorOrden(ValueError):
    """Orden de la interfaz que no cumple el contrato."""


def leer_orden(texto: str | bytes) -> dict:
    """Valida una orden. Devuelve ``{"cmd": ...}`` con sus parámetros ya convertidos.

    Raises
    ------
    ErrorOrden
        Con un mensaje que se reenvía tal cual a la interfaz.
    """
    try:
        m = json.loads(texto)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErrorOrden("la orden no es JSON válido") from e
    if not isinstance(m, dict) or not isinstance(m.get("cmd"), str):
        raise ErrorOrden('falta "cmd"')
    cmd = m["cmd"]
    if cmd in ("cancelar", "ping"):
        return {"cmd": cmd}
    if cmd == "simular":
        clase = m.get("clase")
        if (
            not isinstance(clase, int)
            or isinstance(clase, bool)
            or not 0 <= clase <= len(MOVIMIENTOS)
        ):
            raise ErrorOrden(f'"clase" debe ser un entero de 0 a {len(MOVIMIENTOS)}')
        return {"cmd": cmd, "clase": clase}
    if cmd == "calibrar":
        params = {}
        for nombre, (lo, hi) in LIMITES.items():
            if nombre not in m:
                continue
            v = m[nombre]
            if not isinstance(v, int | float) or isinstance(v, bool) or not lo <= v <= hi:
                raise ErrorOrden(f'"{nombre}" debe estar entre {lo} y {hi}')
            params[nombre] = int(v) if nombre == "repeticiones" else float(v)
        return {"cmd": cmd, "protocolo": Protocolo(**params)}
    raise ErrorOrden(f'orden desconocida: "{cmd}"')


def _json(m: dict) -> str:
    return json.dumps(m, ensure_ascii=False, separators=(",", ":"))


def _lista(x: np.ndarray, valida: np.ndarray, dec: int) -> list[float | None]:
    return [round(float(v), dec) if ok else None for v, ok in zip(x, valida, strict=True)]


def m_hola(fuente: str, fs: float, canales: int) -> str:
    return _json(
        {
            "tipo": "hola",
            "version": VERSION,
            "fuente": fuente,
            "fs": fs,
            "canales": canales,
            "movimientos": list(MOVIMIENTOS),
        }
    )


def m_estado(
    fuente: str,
    activa: bool,
    calibrado: bool,
    calidad: np.ndarray,
    perdidas: int,
    descartadas: int,
    error_fuente: str | None,
) -> str:
    return _json(
        {
            "tipo": "estado",
            "version": VERSION,
            "fuente": fuente,
            "activa": activa,
            "calibrado": calibrado,
            "calidad": [NOMBRES[int(c)] for c in calidad],
            "perdidas": perdidas,
            "descartadas": descartadas,
            "error_fuente": error_fuente,
        }
    )


def m_niveles(
    t_ms: int, env: np.ndarray, env_val: np.ndarray, act: np.ndarray, act_val: np.ndarray
) -> str:
    return _json(
        {
            "tipo": "niveles",
            "t": t_ms,
            "env_uv": _lista(env, env_val, 1),
            "act": _lista(act, act_val, 3),
        }
    )


def m_calibracion(c: MaquinaCalibracion, t: float) -> str:
    prog, resta = c.progreso(t)
    return _json(
        {
            "tipo": "calibracion",
            "fase": c.fase,
            "paso": c.paso,
            "movimiento": c.movimiento,
            "repeticion": c.rep + 1,
            "de": c.p.repeticiones,
            "progreso": round(prog, 3),
            "restante_s": round(resta, 2),
            "mensaje": c.mensaje,
            "duracion_s": round(c.p.duracion_s, 1),
            "activa": c.fase not in TERMINALES,
        }
    )


def m_resultado(c: MaquinaCalibracion) -> str:
    m = c.matriz if c.fase == "lista" else None
    return _json(
        {
            "tipo": "calibracion_resultado",
            "ok": m is not None,
            "mensaje": c.mensaje,
            "reposo_uv": None if m is None else [round(float(v), 1) for v in m.reposo_uv],
            "referencia_uv": None if m is None else [round(float(v), 1) for v in m.referencia_uv],
            "advertencias": list(c.advertencias),
        }
    )


def m_error(detalle: str) -> str:
    return _json({"tipo": "error", "detalle": detalle})


PARAMETROS = [f.name for f in fields(Protocolo)]

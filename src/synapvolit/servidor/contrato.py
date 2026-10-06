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
from ..registro import CODIGO
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
    if cmd == "osciloscopio":
        if not isinstance(m.get("activo"), bool):
            raise ErrorOrden('"activo" debe ser true o false')
        return {"cmd": cmd, "activo": m["activo"]}
    if cmd == "sesion":
        return _orden_sesion(m)
    if cmd == "evento":
        return _orden_evento(m)
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


MOV_EVENTO = (*MOVIMIENTOS, "cofre", "distractor", "otro")
RESULTADOS = ("acierto", "fallo", "tiempo", "interrumpido")


def _orden_sesion(m: dict) -> dict:
    accion = m.get("accion")
    if accion in ("resumen", "terminar"):
        return {"cmd": "sesion", "accion": accion}
    if accion != "iniciar":
        raise ErrorOrden('"accion" debe ser iniciar, resumen o terminar')
    codigo = m.get("codigo")
    if not isinstance(codigo, str) or not CODIGO.match(codigo):
        raise ErrorOrden("el código del paciente debe tener de 3 a 24 letras, números o guiones")
    minutos = m.get("minutos_prescritos", 30)
    if not isinstance(minutos, int | float) or isinstance(minutos, bool) or not 1 <= minutos <= 180:
        raise ErrorOrden('"minutos_prescritos" debe estar entre 1 y 180')
    return {
        "cmd": "sesion",
        "accion": "iniciar",
        "codigo": codigo,
        "minutos_prescritos": float(minutos),
    }


def _entero(m: dict, campo: str) -> int:
    v = m.get(campo)
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise ErrorOrden(f'"{campo}" debe ser un entero no negativo')
    return v


def _orden_evento(m: dict) -> dict:
    tipo = m.get("tipo")
    if tipo in ("pausa", "reanudar"):
        return {"cmd": "evento", "tipo": tipo}
    if tipo == "ejercicio_inicio":
        if m.get("movimiento") not in MOV_EVENTO:
            raise ErrorOrden(f'"movimiento" debe ser uno de {", ".join(MOV_EVENTO)}')
        return {
            "cmd": "evento",
            "tipo": tipo,
            "id": _entero(m, "id"),
            "movimiento": m["movimiento"],
        }
    if tipo == "ejercicio_fin":
        if m.get("resultado") not in RESULTADOS:
            raise ErrorOrden(f'"resultado" debe ser uno de {", ".join(RESULTADOS)}')
        rt = m.get("rt_s")
        if rt is not None and (
            not isinstance(rt, int | float) or isinstance(rt, bool) or not 0 <= rt <= 120
        ):
            raise ErrorOrden('"rt_s" debe ser null o segundos entre 0 y 120')
        return {
            "cmd": "evento",
            "tipo": tipo,
            "id": _entero(m, "id"),
            "resultado": m["resultado"],
            "rt_s": None if rt is None else float(rt),
        }
    raise ErrorOrden('"tipo" de evento desconocido')


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
    sesion: str | None = None,
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
            "sesion": sesion,
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
            "exactitud": None
            if m is None or c.modelo is None or c.modelo.exactitud is None
            else round(c.modelo.exactitud, 3),
        }
    )


def m_decodificador(
    t_ms: int,
    clase: int,
    confianza: float,
    intensidad: float,
    coactivacion: float | None,
    probabilidades: np.ndarray,
) -> str:
    """Decisión para el juego (mismo formato que ya consume ``WQ.feedDecoder``)."""
    return _json(
        {
            "tipo": "decodificador",
            "t": t_ms,
            "clase": clase,
            "confianza": round(confianza, 3),
            "intensidad": round(intensidad, 3),
            "coactivacion": None if coactivacion is None else round(coactivacion, 3),
            "probabilidades": [round(float(p), 3) for p in probabilidades],
        }
    )


def m_osc(dt_ms: float, mn: np.ndarray, mx: np.ndarray) -> str:
    """Cubetas mín/máx por canal en µV enteros; ``null`` donde hay hueco."""

    def canal(v: np.ndarray) -> list[int | None]:
        return [None if np.isnan(x) else int(round(x)) for x in v]

    return _json(
        {
            "tipo": "osc",
            "dt_ms": dt_ms,
            "min": [canal(mn[:, c]) for c in range(mn.shape[1])],
            "max": [canal(mx[:, c]) for c in range(mx.shape[1])],
        }
    )


def m_sesion(codigo: str | None, final: bool, resumen: dict) -> str:
    return _json({"tipo": "sesion_resumen", "codigo": codigo, "final": final, **resumen})


def m_error(detalle: str) -> str:
    return _json({"tipo": "error", "detalle": detalle})


PARAMETROS = [f.name for f in fields(Protocolo)]

"""Sesión de paciente y osciloscopio por WebSocket, sin calibrar (rápido)."""

import asyncio
import json

import numpy as np
from websockets.asyncio.client import connect

from synapvolit.datasets import Senal
from synapvolit.servidor import FuenteSimulada, Sesion


def _senal(fs=2000.0):
    rng = np.random.default_rng(0)
    x = rng.standard_normal((int(8 * fs), 4)).astype(np.float32) * 20
    y = np.repeat(np.array([0, 1, 0, 2], np.int8), int(2 * fs))
    return Senal(x, y, fs, {"dataset": "prueba"})


async def _con_sesion(prueba, raiz):
    sesion = Sesion(FuenteSimulada(_senal()), raiz_datos=raiz)
    listo = asyncio.Event()
    tarea = asyncio.create_task(sesion.servir("127.0.0.1", 0, listo))
    await listo.wait()
    try:
        return await prueba(sesion, f"ws://127.0.0.1:{sesion.puerto_real}")
    finally:
        tarea.cancel()


async def _esperar(ws, tipo, segundos=5.0):
    async with asyncio.timeout(segundos):
        while (m := json.loads(await ws.recv()))["tipo"] != tipo:
            pass
    return m


def test_sesion_eventos_y_exportacion(tmp_path):
    async def prueba(sesion, url):
        async with connect(url) as ws:
            await ws.send(json.dumps({"cmd": "evento", "tipo": "pausa"}))
            assert "no hay una sesión" in (await _esperar(ws, "error"))["detalle"]
            await ws.send(json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "PRUEBA01"}))
            await ws.send(
                json.dumps(
                    {"cmd": "evento", "tipo": "ejercicio_inicio", "id": 1, "movimiento": "flexion"}
                )
            )
            await asyncio.sleep(0.5)
            await ws.send(
                json.dumps(
                    {
                        "cmd": "evento",
                        "tipo": "ejercicio_fin",
                        "id": 1,
                        "resultado": "acierto",
                        "rt_s": 0.4,
                    }
                )
            )
            await ws.send(json.dumps({"cmd": "sesion", "accion": "resumen"}))
            parcial = await _esperar(ws, "sesion_resumen")
            await ws.send(json.dumps({"cmd": "sesion", "accion": "terminar"}))
            final = await _esperar(ws, "sesion_resumen")
            return parcial, final

    parcial, final = asyncio.run(_con_sesion(prueba, tmp_path))
    assert not parcial["final"] and parcial["aciertos"] == 1
    assert final["final"] and final["codigo"] == "PRUEBA01"
    assert final["minutos_efectivos"] == 0  # sin calibrar no hay señal válida del decodificador
    carpeta = tmp_path / "PRUEBA01"
    assert len(list(carpeta.glob("*.jsonl"))) == 1 and (carpeta / "resumen_sesiones.csv").exists()


def test_osciloscopio_solo_para_quien_lo_pide(tmp_path):
    async def prueba(sesion, url):
        async with connect(url) as ws:
            assert sesion.proc.observador is None  # sin suscriptores no cuesta nada
            await ws.send(json.dumps({"cmd": "osciloscopio", "activo": True}))
            m = await _esperar(ws, "osc")
            await ws.send(json.dumps({"cmd": "osciloscopio", "activo": False}))
            await asyncio.sleep(0.2)
            return m, sesion.proc.observador

    m, observador = asyncio.run(_con_sesion(prueba, tmp_path))
    assert len(m["min"]) == 4 and m["dt_ms"] == 5.0
    assert all(lo <= hi for lo, hi in zip(m["min"][0], m["max"][0], strict=True) if lo is not None)
    assert observador is None


def test_apagar_el_motor_exporta_la_sesion_abierta(tmp_path):
    async def prueba(sesion, url):
        async with connect(url) as ws:
            await ws.send(json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "ABC-1"}))
            await asyncio.sleep(0.3)

    asyncio.run(_con_sesion(prueba, tmp_path))
    assert (tmp_path / "ABC-1" / "resumen_sesiones.csv").exists()

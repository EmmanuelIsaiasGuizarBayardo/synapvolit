"""Sesión real por WebSocket con el paciente simulado: la calibración no detiene el flujo."""

import asyncio
import json

import numpy as np
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

from synapvolit.datasets import Senal
from synapvolit.servidor import FuenteSimulada, Sesion

FS = 2000.0


def _senal():
    """Reposo y cada movimiento, 2 s cada uno; el agonista del movimiento sube a ~100 µV."""
    rng = np.random.default_rng(0)
    xs, ys = [], []
    for _ in range(2):
        for clase in (0, 1, 0, 2, 0, 3, 0, 4):
            x = rng.standard_normal((int(2 * FS), 4)) * 5
            if clase:
                x[:, clase - 1] = rng.standard_normal(int(2 * FS)) * 100
            xs.append(x)
            ys.append(np.full(int(2 * FS), clase, np.int8))
    return Senal(np.vstack(xs).astype(np.float32), np.concatenate(ys), FS, {"dataset": "prueba"})


async def _con_sesion(prueba):
    sesion = Sesion(FuenteSimulada(_senal()))
    listo = asyncio.Event()
    tarea = asyncio.create_task(sesion.servir("127.0.0.1", 0, listo))
    await listo.wait()
    try:
        return await prueba(sesion, f"ws://127.0.0.1:{sesion.puerto_real}")
    finally:
        tarea.cancel()


def test_calibracion_por_websocket_sin_detener_los_niveles():
    async def prueba(sesion, url):
        async with connect(url) as ws:
            tipos = [json.loads(await ws.recv())["tipo"] for _ in range(3)]
            assert tipos == ["hola", "estado", "calibracion"]
            await ws.send(
                json.dumps(
                    {
                        "cmd": "calibrar",
                        "repeticiones": 1,
                        "reposo_s": 0.5,
                        "preparar_s": 0.1,
                        "contraccion_s": 1.2,
                        "descanso_s": 0.1,
                    }
                )
            )
            niveles, resultado, t0 = 0, None, asyncio.get_running_loop().time()
            while resultado is None and asyncio.get_running_loop().time() - t0 < 15:
                m = json.loads(await ws.recv())
                niveles += m["tipo"] == "niveles"
                if m["tipo"] == "calibracion_resultado":
                    resultado = m
            dur = asyncio.get_running_loop().time() - t0
            assert resultado and resultado["ok"], resultado
            assert niveles / dur > 20  # ~30 por segundo aunque se esté calibrando
            ref = np.array(resultado["referencia_uv"])
            assert np.all(ref > 5 * np.array(resultado["reposo_uv"]))
            assert resultado["exactitud"] is None  # una repetición: sin estimación honesta
            while (m := json.loads(await ws.recv()))["tipo"] != "niveles" or m["act"][0] is None:
                pass
            # el paciente simulado hace flexión: el decodificador debe decidirlo
            await ws.send(json.dumps({"cmd": "simular", "clase": 2}))
            decisiones, t0 = [], asyncio.get_running_loop().time()
            while asyncio.get_running_loop().time() - t0 < 2.0:
                d = json.loads(await ws.recv())
                if d["tipo"] == "decodificador":
                    decisiones.append(d)
            return m, decisiones

    m, decisiones = asyncio.run(_con_sesion(prueba))
    assert all(a is not None for a in m["act"])  # ya calibrado: hay activación normalizada
    assert 12 <= len(decisiones) <= 20  # ~8 por segundo
    finales = decisiones[-6:]
    assert all(d["clase"] == 2 and d["confianza"] > 0.8 for d in finales), finales
    assert all(0.5 < d["intensidad"] < 1.5 for d in finales)


def test_origen_ajeno_se_rechaza():
    async def prueba(sesion, url):
        async with connect(url, origin="https://ejemplo.com") as ws:
            try:
                await ws.recv()
            except ConnectionClosedError as e:
                return e.rcvd.code
        return None

    assert asyncio.run(_con_sesion(prueba)) == 1008


def test_cliente_que_no_lee_no_frena_el_procesamiento():
    async def prueba(sesion, url):
        async with connect(url):
            await asyncio.sleep(0.3)
            antes = sesion.proc.procesadas
            await asyncio.sleep(1.5)  # el cliente no lee nada en 1.5 s
            return (sesion.proc.procesadas - antes) / FS

    procesado_s = asyncio.run(_con_sesion(prueba))
    assert 1.2 < procesado_s < 1.8


def test_orden_invalida_responde_error_y_la_sesion_sigue():
    async def prueba(sesion, url):
        async with connect(url) as ws:
            await ws.send('{"cmd":"borrar"}')
            while (m := json.loads(await ws.recv()))["tipo"] != "error":
                pass
            await ws.send('{"cmd":"ping"}')
            while json.loads(await ws.recv())["tipo"] != "pong":
                pass
            return m["detalle"]

    assert "desconocida" in asyncio.run(_con_sesion(prueba))

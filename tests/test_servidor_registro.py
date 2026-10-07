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
    assert len(m["min"]) == 4 and m["dt_ms"] == 10.0
    assert all(lo <= hi for lo, hi in zip(m["min"][0], m["max"][0], strict=True) if lo is not None)
    assert observador is None


def test_apagar_el_motor_exporta_la_sesion_abierta(tmp_path):
    async def prueba(sesion, url):
        async with connect(url) as ws:
            await ws.send(json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "ABC-1"}))
            await asyncio.sleep(0.3)

    asyncio.run(_con_sesion(prueba, tmp_path))
    assert (tmp_path / "ABC-1" / "resumen_sesiones.csv").exists()


def test_perfil_al_iniciar_y_abrir_carpeta(tmp_path):
    abiertas = []

    async def prueba(sesion, url):
        sesion.abridor = abiertas.append
        async with connect(url) as ws:
            await ws.send(json.dumps({"cmd": "abrir_carpeta"}))
            assert "todavía no hay datos" in (await _esperar(ws, "error"))["detalle"]
            await ws.send(json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "NUEVO1"}))
            perfil = await _esperar(ws, "perfil")
            await ws.send(json.dumps({"cmd": "calibrar", "modo": "verificar"}))
            error = await _esperar(ws, "error")
            await asyncio.sleep(1.2)  # el registro ya se volcó: la carpeta existe
            await ws.send(json.dumps({"cmd": "abrir_carpeta"}))
            await asyncio.sleep(0.3)
            return perfil, error

    perfil, error = asyncio.run(_con_sesion(prueba, tmp_path))
    assert perfil["estado"] == "no_existe" and "no hay un perfil" in error["detalle"]
    assert abiertas == [tmp_path / "NUEVO1"]


def test_cambiar_de_paciente_borra_la_calibracion_anterior(tmp_path):
    async def prueba(sesion, url):
        async with connect(url) as ws:
            sesion.cal.fase = "lista"  # como si el paciente anterior hubiera calibrado
            sesion.proc.matriz = object()
            await ws.send(json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "OTRO-2"}))
            await _esperar(ws, "perfil")
            await asyncio.sleep(0.1)
            return sesion.cal.fase, sesion.proc.matriz, sesion.decisor

    assert asyncio.run(_con_sesion(prueba, tmp_path)) == ("inactiva", None, None)


def test_apagado_ordenado_solo_desde_un_programa_local(tmp_path):
    async def prueba():
        sesion = Sesion(FuenteSimulada(_senal()), raiz_datos=tmp_path)
        listo = asyncio.Event()
        tarea = asyncio.create_task(sesion.servir("127.0.0.1", 0, listo))
        await listo.wait()
        url = f"ws://127.0.0.1:{sesion.puerto_real}"
        async with connect(url, origin="http://127.0.0.1:8000") as pagina:
            await pagina.send(json.dumps({"cmd": "apagar"}))
            assert "no puede apagar" in (await _esperar(pagina, "error"))["detalle"]
        async with connect(url) as programa:
            await programa.send(
                json.dumps({"cmd": "sesion", "accion": "iniciar", "codigo": "APAG-1"})
            )
            await asyncio.sleep(0.2)
            await programa.send(json.dumps({"cmd": "apagar"}))
            async with asyncio.timeout(5):
                await tarea  # servir termina solo, sin cancelarlo

    asyncio.run(prueba())
    assert (tmp_path / "APAG-1" / "resumen_sesiones.csv").exists()  # la sesión se exportó al apagar
